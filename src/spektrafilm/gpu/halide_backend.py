from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from opt_einsum import contract

from spektrafilm.gpu.backend import BackendUnavailableError


@dataclass(slots=True)
class _HalideTrilinear3DPipeline:
    lut_param: Any
    image_param: Any
    output: Any


class HalideBackend:
    """Optional Halide JIT backend.

    Halide is a staged image DSL rather than an eager ndarray library. The
    generic ArrayBackend methods intentionally delegate to NumPy while selected
    hot kernels use cached Halide Funcs.
    """

    name = "halide"
    supports_gpu = True
    fallback_reason = None
    requires_serial_runtime = True

    def __init__(
        self,
        *,
        precision: str = "float32",
        halide_module: Any | None = None,
        _halide: Any | None = None,
    ) -> None:
        if precision != "float32":
            raise BackendUnavailableError("compute_backend='halide' currently supports float32 precision only.")
        if _halide is not None and halide_module is not None:
            raise ValueError("Pass only one of halide_module or _halide.")
        if _halide is not None:
            halide_module = _halide
        if halide_module is None:
            try:
                import halide as hl
            except Exception as exc:
                raise BackendUnavailableError(
                    "compute_backend='halide' requires the optional dependency: "
                    "install with `pip install halide` or `uv sync --extra halide`."
                ) from exc
        else:
            hl = halide_module

        self.hl = hl
        self.precision = precision
        self.default_dtype = np.float32
        self.target = hl.get_host_target()
        self._trilinear_3d_cache: dict[int, _HalideTrilinear3DPipeline] = {}
        self._rgb_matrix_pipeline: tuple[Any, Any, Any] | None = None

    def asarray(self, value: Any, dtype: Any | None = None) -> np.ndarray:
        return np.asarray(value, dtype=dtype or self.default_dtype)

    def to_numpy(self, value: Any) -> np.ndarray:
        return np.asarray(value)

    def eval(self, *values: Any) -> None:
        return None

    def synchronize(self) -> None:
        return None

    def cleanup(self) -> None:
        self._trilinear_3d_cache.clear()
        self._rgb_matrix_pipeline = None

    def exp(self, x: Any) -> np.ndarray:
        return np.exp(x)

    def log10(self, x: Any) -> np.ndarray:
        return np.log10(x)

    def maximum(self, x: Any, y: Any) -> np.ndarray:
        return np.maximum(x, y)

    def max(self, x: Any) -> float:
        return float(np.max(x))

    def clip(self, x: Any, lo: float, hi: float) -> np.ndarray:
        return np.clip(x, lo, hi)

    def matmul(self, a: Any, b: Any) -> np.ndarray:
        return np.matmul(a, b)

    def einsum(self, pattern: str, *values: Any) -> np.ndarray:
        return contract(pattern, *values)

    def power(self, base: float, x: Any) -> np.ndarray:
        return np.power(base, x)

    def pow(self, x: Any, exponent: float) -> np.ndarray:
        return np.power(x, exponent)

    def fmax(self, x: Any, y: float) -> np.ndarray:
        return np.fmax(x, y)

    def nan_to_num(self, x: Any, nan: float = 0.0) -> np.ndarray:
        return np.nan_to_num(x, nan=nan)

    def where(self, condition: Any, x: Any, y: Any) -> np.ndarray:
        return np.where(condition, x, y)

    def abs(self, x: Any) -> np.ndarray:
        return np.abs(x)

    def rgb_to_xyz(self, rgb: Any, matrix_3x3: Any) -> np.ndarray:
        rgb_np = np.asarray(rgb, dtype=np.float32)
        matrix_np = np.asarray(matrix_3x3, dtype=np.float32)
        if rgb_np.ndim != 3 or rgb_np.shape[-1] != 3:
            return np.matmul(rgb_np, matrix_np.T)
        if matrix_np.shape != (3, 3):
            raise ValueError(f"matrix_3x3 must have shape (3, 3), got {matrix_np.shape}")

        height, width = rgb_np.shape[:2]
        image_param, matrix_param, output = self._build_rgb_matrix_pipeline()
        image_param.set(self.hl.Buffer(np.ascontiguousarray(np.transpose(rgb_np, (2, 0, 1)))))
        matrix_param.set(self.hl.Buffer(np.ascontiguousarray(matrix_np)))
        output_chw = np.asarray(output.realize([width, height, 3]))
        return np.ascontiguousarray(np.transpose(output_chw, (1, 2, 0)), dtype=np.float32)

    def apply_lut_trilinear_3d(self, lut: Any, image: Any) -> np.ndarray:
        """Sample a normalized 3D LUT with a cached Halide JIT pipeline."""
        lut_np = np.asarray(lut, dtype=np.float32)
        image_np = np.asarray(image, dtype=np.float32)
        if lut_np.ndim != 4 or lut_np.shape[-1] != 3:
            raise ValueError("3D LUT must have shape LxLxLx3")
        size = int(lut_np.shape[0])
        if size == 0 or lut_np.shape[1] != size or lut_np.shape[2] != size:
            raise ValueError("3D LUT must have equal non-empty dimensions")
        if image_np.ndim != 3 or image_np.shape[-1] != 3:
            raise ValueError("3D LUT coordinates must have shape HxWx3")

        pipeline = self._trilinear_3d_cache.get(size)
        if pipeline is None:
            pipeline = self._build_trilinear_3d_pipeline(size)
            self._trilinear_3d_cache[size] = pipeline

        height, width = image_np.shape[:2]
        image_chw = np.ascontiguousarray(np.transpose(image_np, (2, 0, 1)))
        lut_cbgr = np.ascontiguousarray(np.transpose(lut_np, (3, 2, 1, 0)))
        pipeline.image_param.set(self.hl.Buffer(image_chw))
        pipeline.lut_param.set(self.hl.Buffer(lut_cbgr))

        output_chw = np.asarray(pipeline.output.realize([width, height, 3]))
        return np.ascontiguousarray(np.transpose(output_chw, (1, 2, 0)), dtype=np.float32)

    def _build_trilinear_3d_pipeline(self, lut_size: int) -> _HalideTrilinear3DPipeline:
        hl = self.hl
        x = hl.Var(f"sf_halide_lut3d_x_{lut_size}")
        y = hl.Var(f"sf_halide_lut3d_y_{lut_size}")
        c = hl.Var(f"sf_halide_lut3d_c_{lut_size}")
        lut_param = hl.ImageParam(hl.Float(32), 4, f"sf_halide_lut3d_lut_{lut_size}")
        image_param = hl.ImageParam(hl.Float(32), 3, f"sf_halide_lut3d_image_{lut_size}")
        output = hl.Func(f"sf_halide_lut3d_output_{lut_size}")

        upper = float(lut_size - 1)

        def coordinate(channel: int):
            return hl.clamp(image_param[x, y, channel] * upper, 0.0, upper)

        coord_r = coordinate(0)
        coord_g = coordinate(1)
        coord_b = coordinate(2)
        r0 = hl.cast(hl.Int(32), hl.floor(coord_r))
        g0 = hl.cast(hl.Int(32), hl.floor(coord_g))
        b0 = hl.cast(hl.Int(32), hl.floor(coord_b))
        r1 = hl.min(r0 + 1, lut_size - 1)
        g1 = hl.min(g0 + 1, lut_size - 1)
        b1 = hl.min(b0 + 1, lut_size - 1)
        fr = coord_r - hl.cast(hl.Float(32), r0)
        fg = coord_g - hl.cast(hl.Float(32), g0)
        fb = coord_b - hl.cast(hl.Float(32), b0)

        def lerp(a, b, t):
            return a + t * (b - a)

        c000 = lut_param[r0, g0, b0, c]
        c100 = lut_param[r1, g0, b0, c]
        c010 = lut_param[r0, g1, b0, c]
        c110 = lut_param[r1, g1, b0, c]
        c001 = lut_param[r0, g0, b1, c]
        c101 = lut_param[r1, g0, b1, c]
        c011 = lut_param[r0, g1, b1, c]
        c111 = lut_param[r1, g1, b1, c]
        c00 = lerp(c000, c100, fr)
        c10 = lerp(c010, c110, fr)
        c01 = lerp(c001, c101, fr)
        c11 = lerp(c011, c111, fr)
        c0 = lerp(c00, c10, fg)
        c1 = lerp(c01, c11, fg)
        output[x, y, c] = lerp(c0, c1, fb)
        output.reorder(c, x, y).bound(c, 0, 3).unroll(c).parallel(y)
        output.compile_jit(self.target)
        return _HalideTrilinear3DPipeline(
            lut_param=lut_param,
            image_param=image_param,
            output=output,
        )

    def _build_rgb_matrix_pipeline(self) -> tuple[Any, Any, Any]:
        if self._rgb_matrix_pipeline is not None:
            return self._rgb_matrix_pipeline

        hl = self.hl
        c = hl.Var("sf_halide_rgb_matrix_c")
        x = hl.Var("sf_halide_rgb_matrix_x")
        y = hl.Var("sf_halide_rgb_matrix_y")
        image_param = hl.ImageParam(hl.Float(32), 3, "sf_halide_rgb_matrix_image")
        matrix_param = hl.ImageParam(hl.Float(32), 2, "sf_halide_rgb_matrix_matrix")
        output = hl.Func("sf_halide_rgb_matrix_output")

        output[x, y, c] = (
            image_param[x, y, 0] * matrix_param[0, c]
            + image_param[x, y, 1] * matrix_param[1, c]
            + image_param[x, y, 2] * matrix_param[2, c]
        )
        output.reorder(c, x, y).bound(c, 0, 3).unroll(c).parallel(y)
        output.compile_jit(self.target)
        self._rgb_matrix_pipeline = (image_param, matrix_param, output)
        return self._rgb_matrix_pipeline
