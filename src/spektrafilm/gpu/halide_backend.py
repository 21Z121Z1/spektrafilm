from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from opt_einsum import contract

from spektrafilm.gpu.backend import BackendUnavailableError
from spektrafilm.gpu.residency import record_conversion


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
        self._density_to_light_pipeline: tuple[Any, Any, Any] | None = None
        self._light_to_raw_pipeline: tuple[Any, Any, Any] | None = None
        self._compute_density_spectral_pipeline: tuple[Any, Any, Any] | None = None
        self._fir_blur_pipeline: tuple[Any, Any, Any, Any] | None = None
        self._fir_blur_kernel_len: int = 0
        self._highlight_boost_pipeline: tuple[Any, Any, Any, Any] | None = None
        self._cctf_encode_pipeline: tuple[Any, Any, Any, Any, Any, Any, Any] | None = None
        self._cctf_decode_pipeline: tuple[Any, Any, Any, Any, Any, Any, Any] | None = None
        self._interp_1d_pipeline: tuple[Any, Any, Any, Any] | None = None
        self._interp_1d_n: int = 0
        self._lut_2d_pipeline: tuple[Any, Any, Any] | None = None
        self._lut_2d_size: int = 0
        self._cmy_to_log_xyz_pipelines: dict[int, tuple[Any, ...]] = {}
        self._cmy_to_log_raw_pipelines: dict[int, tuple[Any, ...]] = {}

    def asarray(self, value: Any, dtype: Any | None = None) -> np.ndarray:
        result = np.asarray(value, dtype=dtype or self.default_dtype)
        record_conversion("asarray", self.name, value, result)
        return result

    def to_numpy(self, value: Any) -> np.ndarray:
        result = np.asarray(value)
        record_conversion("to_numpy", self.name, value, result)
        return result

    def eval(self, *values: Any) -> None:
        return None

    def synchronize(self) -> None:
        return None

    def cleanup(self) -> None:
        self._trilinear_3d_cache.clear()
        self._rgb_matrix_pipeline = None
        self._density_to_light_pipeline = None
        self._light_to_raw_pipeline = None
        self._compute_density_spectral_pipeline = None
        self._fir_blur_pipeline = None
        self._fir_blur_kernel_len = 0
        self._highlight_boost_pipeline = None
        self._cctf_encode_pipeline = None
        self._cctf_decode_pipeline = None
        self._interp_1d_pipeline = None
        self._interp_1d_n = 0
        self._lut_2d_pipeline = None
        self._lut_2d_size = 0
        self._cmy_to_log_xyz_pipelines.clear()
        self._cmy_to_log_raw_pipelines.clear()

    def zeros(self, shape: tuple[int, ...], dtype: Any | None = None) -> np.ndarray:
        return np.zeros(shape, dtype=dtype or self.default_dtype)

    def exp(self, x: Any) -> np.ndarray:
        return np.exp(x)

    def log10(self, x: Any) -> np.ndarray:
        return np.log10(x)

    def maximum(self, x: Any, y: Any) -> np.ndarray:
        return np.maximum(x, y)

    def max_array(self, x: Any) -> np.ndarray:
        return np.max(x)

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
        # Keep Halide Buffer objects alive until after realize() —
        # ImageParam.set() does not prevent the Python-side Buffer wrapper
        # (and its underlying numpy array) from being garbage-collected.
        image_buf = self.hl.Buffer(np.ascontiguousarray(np.transpose(rgb_np, (2, 0, 1))))
        matrix_buf = self.hl.Buffer(np.ascontiguousarray(matrix_np))
        image_param.set(image_buf)
        matrix_param.set(matrix_buf)
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

    # ------------------------------------------------------------------
    # Spectral kernels (density_to_light, light_to_raw, compute_density_spectral)
    #
    # Halide convention: hl.Buffer(numpy[C,H,W]) → dims [W,H,C].
    # Func[x,y,c] with realize([W,H,C]) → np.asarray shape (C,H,W).
    # For 2D: hl.Buffer(numpy[A,B]) → dims [B,A]. Func[b,a] → (A,B).
    # ------------------------------------------------------------------

    def density_to_light(self, density: Any, illuminant: Any) -> np.ndarray:
        """Halide JIT: light[c, h, wl] = 10^(-density[c, h, wl]) * illuminant[wl, c].

        Inputs: density [3, H, 81] float32, illuminant [81, 3] float32.
        Output: [3, H, 81] float32.
        """
        density_np = np.ascontiguousarray(np.asarray(density, dtype=np.float32))
        illuminant_np = np.ascontiguousarray(np.asarray(illuminant, dtype=np.float32))
        if density_np.ndim != 3 or density_np.shape[0] != 3 or density_np.shape[2] != 81:
            raise ValueError(f"density must have shape [3, H, 81], got {density_np.shape}")
        if illuminant_np.shape != (81, 3):
            raise ValueError(f"illuminant must have shape [81, 3], got {illuminant_np.shape}")

        if self._density_to_light_pipeline is None:
            self._density_to_light_pipeline = self._build_density_to_light_pipeline()

        density_param, illuminant_param, output = self._density_to_light_pipeline
        density_param.set(self.hl.Buffer(density_np))
        illuminant_param.set(self.hl.Buffer(illuminant_np))
        H = density_np.shape[1]
        result = np.asarray(output.realize([81, H, 3]))
        return np.ascontiguousarray(result, dtype=np.float32)

    def _build_density_to_light_pipeline(self) -> tuple[Any, Any, Any]:
        hl = self.hl
        wl = hl.Var("sf_halide_spec_dl_wl")
        y = hl.Var("sf_halide_spec_dl_y")
        c = hl.Var("sf_halide_spec_dl_c")
        density_param = hl.ImageParam(hl.Float(32), 3, "sf_halide_spec_dl_density")
        illuminant_param = hl.ImageParam(hl.Float(32), 2, "sf_halide_spec_dl_illuminant")
        output = hl.Func("sf_halide_spec_dl_output")

        # density [3,H,81]→[81,H,3]: density_param[wl,y,c]
        # illuminant [81,3]→[3,81]: illuminant_param[c,wl]
        log10 = hl.f32(2.302585092994046)
        output[wl, y, c] = hl.exp(log10 * (-density_param[wl, y, c])) * illuminant_param[c, wl]
        output.vectorize(wl, 8).parallel(y)
        output.compile_jit(self.target)
        return density_param, illuminant_param, output

    def light_to_raw(self, light: Any, sensitivity: Any) -> np.ndarray:
        """Halide JIT: raw[c_out, y, c_in] = sum_wl light[c_out, y, wl] * sensitivity[wl, c_in].

        Inputs: light [3, H, 81] float32, sensitivity [81, 3] float32.
        Output: [3, H, 3] float32.
        """
        light_np = np.ascontiguousarray(np.asarray(light, dtype=np.float32))
        sensitivity_np = np.ascontiguousarray(np.asarray(sensitivity, dtype=np.float32))
        if light_np.ndim != 3 or light_np.shape[0] != 3 or light_np.shape[2] != 81:
            raise ValueError(f"light must have shape [3, H, 81], got {light_np.shape}")
        if sensitivity_np.shape != (81, 3):
            raise ValueError(f"sensitivity must have shape [81, 3], got {sensitivity_np.shape}")

        if self._light_to_raw_pipeline is None:
            self._light_to_raw_pipeline = self._build_light_to_raw_pipeline()

        light_param, sensitivity_param, output = self._light_to_raw_pipeline
        light_param.set(self.hl.Buffer(light_np))
        sensitivity_param.set(self.hl.Buffer(sensitivity_np))
        H = light_np.shape[1]
        result = np.asarray(output.realize([3, H, 3]))
        return np.ascontiguousarray(result, dtype=np.float32)

    def _build_light_to_raw_pipeline(self) -> tuple[Any, Any, Any]:
        hl = self.hl
        c_in = hl.Var("sf_halide_spec_ltr_cin")
        y = hl.Var("sf_halide_spec_ltr_y")
        c_out = hl.Var("sf_halide_spec_ltr_cout")
        r_wl = hl.RDom([hl.Range(0, 81)], "sf_halide_spec_ltr_rwl")
        light_param = hl.ImageParam(hl.Float(32), 3, "sf_halide_spec_ltr_light")
        sensitivity_param = hl.ImageParam(hl.Float(32), 2, "sf_halide_spec_ltr_sensitivity")
        output = hl.Func("sf_halide_spec_ltr_output")

        # light [3,H,81]→[81,H,3]: light_param[wl,y,c_out]
        # sensitivity [81,3]→[3,81]: sensitivity_param[c_in,wl]
        # output [3,H,3]→[3,H,3]: output[c_in,y,c_out]
        output[c_in, y, c_out] = hl.f32(0.0)
        output[c_in, y, c_out] += light_param[r_wl.x, y, c_out] * sensitivity_param[c_in, r_wl.x]
        output.parallel(y)
        output.update(0).parallel(y)
        output.compile_jit(self.target)
        return light_param, sensitivity_param, output

    def compute_density_spectral(self, density_cmy: Any, channel_density: Any) -> np.ndarray:
        """Halide JIT: result[c, y, wl] = sum_k density_cmy[k, y, wl] * channel_density[k, wl].

        Inputs: density_cmy [3, H, 81] float32, channel_density [3, 81] float32.
        Output: [3, H, 81] float32.
        """
        density_cmy_np = np.ascontiguousarray(np.asarray(density_cmy, dtype=np.float32))
        channel_density_np = np.ascontiguousarray(np.asarray(channel_density, dtype=np.float32))
        if density_cmy_np.ndim != 3 or density_cmy_np.shape[0] != 3:
            raise ValueError(f"density_cmy must have shape [3, H, 81], got {density_cmy_np.shape}")
        if channel_density_np.shape != (3, 81):
            raise ValueError(f"channel_density must have shape [3, 81], got {channel_density_np.shape}")

        if self._compute_density_spectral_pipeline is None:
            self._compute_density_spectral_pipeline = self._build_compute_density_spectral_pipeline()

        density_param, channel_param, output = self._compute_density_spectral_pipeline
        density_param.set(self.hl.Buffer(density_cmy_np))
        channel_param.set(self.hl.Buffer(channel_density_np))
        H = density_cmy_np.shape[1]
        result = np.asarray(output.realize([81, H, 3]))
        return np.ascontiguousarray(result, dtype=np.float32)

    def _build_compute_density_spectral_pipeline(self) -> tuple[Any, Any, Any]:
        hl = self.hl
        wl = hl.Var("sf_halide_spec_cds_wl")
        y = hl.Var("sf_halide_spec_cds_y")
        c = hl.Var("sf_halide_spec_cds_c")
        r_k = hl.RDom([hl.Range(0, 3)], "sf_halide_spec_cds_rk")
        density_param = hl.ImageParam(hl.Float(32), 3, "sf_halide_spec_cds_density")
        channel_param = hl.ImageParam(hl.Float(32), 2, "sf_halide_spec_cds_channel")
        output = hl.Func("sf_halide_spec_cds_output")

        # density_cmy [3,H,81]→[81,H,3]: density_param[wl,y,k]
        # channel_density [3,81]→[81,3]: channel_param[wl,k]
        output[wl, y, c] = hl.f32(0.0)
        output[wl, y, c] += density_param[wl, y, r_k.x] * channel_param[wl, r_k.x]
        output.vectorize(wl, 8).parallel(y)
        output.compile_jit(self.target)
        return density_param, channel_param, output

    def cmy_to_log_xyz(
        self,
        density_cmy: Any,
        channel_density: Any,
        base_density: Any,
        scan_illuminant: Any,
        cmfs: Any,
        normalization: float,
    ) -> np.ndarray:
        """Fused Halide JIT CMY density to log10 XYZ for HWC runtime arrays."""
        density_np = np.ascontiguousarray(np.asarray(density_cmy, dtype=np.float32))
        channel_np = np.ascontiguousarray(np.asarray(channel_density, dtype=np.float32))
        base_np = np.ascontiguousarray(np.asarray(base_density, dtype=np.float32).reshape(-1))
        illuminant_np = np.ascontiguousarray(np.asarray(scan_illuminant, dtype=np.float32).reshape(-1))
        cmfs_np = np.ascontiguousarray(np.asarray(cmfs, dtype=np.float32))

        if density_np.ndim != 3 or density_np.shape[-1] != 3:
            raise ValueError(f"density_cmy must have shape [H, W, 3], got {density_np.shape}")
        if channel_np.ndim != 2 or channel_np.shape[1] != 3:
            raise ValueError(f"channel_density must have shape [K, 3], got {channel_np.shape}")
        k_count = int(channel_np.shape[0])
        if base_np.shape != (k_count,):
            raise ValueError(f"base_density must have shape [{k_count}], got {base_np.shape}")
        if illuminant_np.shape != (k_count,):
            raise ValueError(f"scan_illuminant must have shape [{k_count}], got {illuminant_np.shape}")
        if cmfs_np.shape != (k_count, 3):
            raise ValueError(f"cmfs must have shape [{k_count}, 3], got {cmfs_np.shape}")

        pipeline = self._cmy_to_log_xyz_pipelines.get(k_count)
        if pipeline is None:
            pipeline = self._build_cmy_to_log_xyz_pipeline(k_count)
            self._cmy_to_log_xyz_pipelines[k_count] = pipeline

        density_p, channel_p, base_p, illuminant_p, cmfs_p, normalization_p, output = pipeline
        density_buf = self.hl.Buffer(density_np)
        channel_buf = self.hl.Buffer(channel_np)
        base_buf = self.hl.Buffer(base_np)
        illuminant_buf = self.hl.Buffer(illuminant_np)
        cmfs_buf = self.hl.Buffer(cmfs_np)
        density_p.set(density_buf)
        channel_p.set(channel_buf)
        base_p.set(base_buf)
        illuminant_p.set(illuminant_buf)
        cmfs_p.set(cmfs_buf)
        normalization_p.set(float(normalization))

        height, width = density_np.shape[:2]
        result = np.asarray(output.realize([3, width, height]))
        return np.ascontiguousarray(result, dtype=np.float32)

    def _build_cmy_to_log_xyz_pipeline(self, k_count: int) -> tuple[Any, ...]:
        hl = self.hl
        c = hl.Var(f"sf_halide_cmy_xyz_c_{k_count}")
        x = hl.Var(f"sf_halide_cmy_xyz_x_{k_count}")
        y = hl.Var(f"sf_halide_cmy_xyz_y_{k_count}")
        wl = hl.Var(f"sf_halide_cmy_xyz_wl_{k_count}")
        r_k = hl.RDom([hl.Range(0, 3)], f"sf_halide_cmy_xyz_rk_{k_count}")
        r_wl = hl.RDom([hl.Range(0, k_count)], f"sf_halide_cmy_xyz_rwl_{k_count}")

        density_p = hl.ImageParam(hl.Float(32), 3, f"sf_halide_cmy_xyz_density_{k_count}")
        channel_p = hl.ImageParam(hl.Float(32), 2, f"sf_halide_cmy_xyz_channel_{k_count}")
        base_p = hl.ImageParam(hl.Float(32), 1, f"sf_halide_cmy_xyz_base_{k_count}")
        illuminant_p = hl.ImageParam(hl.Float(32), 1, f"sf_halide_cmy_xyz_illum_{k_count}")
        cmfs_p = hl.ImageParam(hl.Float(32), 2, f"sf_halide_cmy_xyz_cmfs_{k_count}")
        normalization_p = hl.Param(hl.Float(32), f"sf_halide_cmy_xyz_norm_{k_count}", 1.0)

        density_spectral = hl.Func(f"sf_halide_cmy_xyz_density_spectral_{k_count}")
        light = hl.Func(f"sf_halide_cmy_xyz_light_{k_count}")
        xyz = hl.Func(f"sf_halide_cmy_xyz_accum_{k_count}")
        output = hl.Func(f"sf_halide_cmy_xyz_output_{k_count}")

        density_spectral[wl, x, y] = base_p[wl]
        density_spectral[wl, x, y] += density_p[r_k.x, x, y] * channel_p[r_k.x, wl]
        ln10 = hl.f32(2.302585092994046)
        light_value = hl.exp(ln10 * (-density_spectral[wl, x, y])) * illuminant_p[wl]
        light[wl, x, y] = hl.select(hl.is_nan(light_value), hl.f32(0.0), light_value)
        xyz[c, x, y] = hl.f32(0.0)
        xyz[c, x, y] += light[r_wl.x, x, y] * cmfs_p[c, r_wl.x]
        v = xyz[c, x, y] / normalization_p
        safe = hl.select(v > 0.0, v, hl.f32(0.0)) + hl.f32(1.0e-10)
        output[c, x, y] = hl.log(safe) / ln10

        output.reorder(c, x, y).bound(c, 0, 3).unroll(c).parallel(y)
        xyz.compute_at(output, y).reorder(c, x, y).bound(c, 0, 3).unroll(c)
        xyz.update(0).reorder(c, x, y).unroll(c)
        density_spectral.compute_at(output, y)
        density_spectral.update(0)
        light.compute_at(output, y)
        output.compile_jit(self.target)
        return density_p, channel_p, base_p, illuminant_p, cmfs_p, normalization_p, output

    def cmy_to_log_raw(
        self,
        density_cmy: Any,
        channel_density: Any,
        base_density: Any,
        illuminant: Any,
        sensitivity: Any,
        exposure_factor: Any,
        preflash: Any,
    ) -> np.ndarray:
        """Fused Halide JIT CMY density to log10 raw for printing exposure."""
        density_np = np.ascontiguousarray(np.asarray(density_cmy, dtype=np.float32))
        channel_np = np.ascontiguousarray(np.asarray(channel_density, dtype=np.float32))
        base_np = np.ascontiguousarray(np.asarray(base_density, dtype=np.float32).reshape(-1))
        illuminant_np = np.ascontiguousarray(np.asarray(illuminant, dtype=np.float32).reshape(-1))
        sensitivity_np = np.ascontiguousarray(np.asarray(sensitivity, dtype=np.float32))
        exposure_np = self._as_rgb_vector(exposure_factor, "exposure_factor")
        preflash_np = self._as_rgb_vector(preflash, "preflash")

        if density_np.ndim != 3 or density_np.shape[-1] != 3:
            raise ValueError(f"density_cmy must have shape [H, W, 3], got {density_np.shape}")
        if channel_np.ndim != 2 or channel_np.shape[1] != 3:
            raise ValueError(f"channel_density must have shape [K, 3], got {channel_np.shape}")
        k_count = int(channel_np.shape[0])
        if base_np.shape != (k_count,):
            raise ValueError(f"base_density must have shape [{k_count}], got {base_np.shape}")
        if illuminant_np.shape != (k_count,):
            raise ValueError(f"illuminant must have shape [{k_count}], got {illuminant_np.shape}")
        if sensitivity_np.shape != (k_count, 3):
            raise ValueError(f"sensitivity must have shape [{k_count}, 3], got {sensitivity_np.shape}")

        pipeline = self._cmy_to_log_raw_pipelines.get(k_count)
        if pipeline is None:
            pipeline = self._build_cmy_to_log_raw_pipeline(k_count)
            self._cmy_to_log_raw_pipelines[k_count] = pipeline

        density_p, channel_p, base_p, illuminant_p, sensitivity_p, exposure_p, preflash_p, output = pipeline
        density_buf = self.hl.Buffer(density_np)
        channel_buf = self.hl.Buffer(channel_np)
        base_buf = self.hl.Buffer(base_np)
        illuminant_buf = self.hl.Buffer(illuminant_np)
        sensitivity_buf = self.hl.Buffer(sensitivity_np)
        exposure_buf = self.hl.Buffer(exposure_np)
        preflash_buf = self.hl.Buffer(preflash_np)
        density_p.set(density_buf)
        channel_p.set(channel_buf)
        base_p.set(base_buf)
        illuminant_p.set(illuminant_buf)
        sensitivity_p.set(sensitivity_buf)
        exposure_p.set(exposure_buf)
        preflash_p.set(preflash_buf)

        height, width = density_np.shape[:2]
        result = np.asarray(output.realize([3, width, height]))
        return np.ascontiguousarray(result, dtype=np.float32)

    @staticmethod
    def _as_rgb_vector(value: Any, name: str) -> np.ndarray:
        arr = np.asarray(value, dtype=np.float32).reshape(-1)
        if arr.size == 1:
            arr = np.repeat(arr, 3)
        if arr.size != 3:
            raise ValueError(f"{name} must be scalar or have 3 values, got shape {np.asarray(value).shape}")
        return np.ascontiguousarray(arr.astype(np.float32, copy=False))

    def _build_cmy_to_log_raw_pipeline(self, k_count: int) -> tuple[Any, ...]:
        hl = self.hl
        c = hl.Var(f"sf_halide_cmy_raw_c_{k_count}")
        x = hl.Var(f"sf_halide_cmy_raw_x_{k_count}")
        y = hl.Var(f"sf_halide_cmy_raw_y_{k_count}")
        wl = hl.Var(f"sf_halide_cmy_raw_wl_{k_count}")
        r_k = hl.RDom([hl.Range(0, 3)], f"sf_halide_cmy_raw_rk_{k_count}")
        r_wl = hl.RDom([hl.Range(0, k_count)], f"sf_halide_cmy_raw_rwl_{k_count}")

        density_p = hl.ImageParam(hl.Float(32), 3, f"sf_halide_cmy_raw_density_{k_count}")
        channel_p = hl.ImageParam(hl.Float(32), 2, f"sf_halide_cmy_raw_channel_{k_count}")
        base_p = hl.ImageParam(hl.Float(32), 1, f"sf_halide_cmy_raw_base_{k_count}")
        illuminant_p = hl.ImageParam(hl.Float(32), 1, f"sf_halide_cmy_raw_illum_{k_count}")
        sensitivity_p = hl.ImageParam(hl.Float(32), 2, f"sf_halide_cmy_raw_sensitivity_{k_count}")
        exposure_p = hl.ImageParam(hl.Float(32), 1, f"sf_halide_cmy_raw_exposure_{k_count}")
        preflash_p = hl.ImageParam(hl.Float(32), 1, f"sf_halide_cmy_raw_preflash_{k_count}")

        density_spectral = hl.Func(f"sf_halide_cmy_raw_density_spectral_{k_count}")
        light = hl.Func(f"sf_halide_cmy_raw_light_{k_count}")
        raw = hl.Func(f"sf_halide_cmy_raw_accum_{k_count}")
        output = hl.Func(f"sf_halide_cmy_raw_output_{k_count}")

        density_spectral[wl, x, y] = base_p[wl]
        density_spectral[wl, x, y] += density_p[r_k.x, x, y] * channel_p[r_k.x, wl]
        ln10 = hl.f32(2.302585092994046)
        light_value = hl.exp(ln10 * (-density_spectral[wl, x, y])) * illuminant_p[wl]
        light[wl, x, y] = hl.select(hl.is_nan(light_value), hl.f32(0.0), light_value)
        raw[c, x, y] = hl.f32(0.0)
        raw[c, x, y] += light[r_wl.x, x, y] * sensitivity_p[c, r_wl.x]
        v = raw[c, x, y] * exposure_p[c] + preflash_p[c]
        safe = hl.select(v > 0.0, v, hl.f32(0.0)) + hl.f32(1.0e-10)
        output[c, x, y] = hl.log(safe) / ln10

        output.reorder(c, x, y).bound(c, 0, 3).unroll(c).parallel(y)
        raw.compute_at(output, y).reorder(c, x, y).bound(c, 0, 3).unroll(c)
        raw.update(0).reorder(c, x, y).unroll(c)
        density_spectral.compute_at(output, y)
        density_spectral.update(0)
        light.compute_at(output, y)
        output.compile_jit(self.target)
        return density_p, channel_p, base_p, illuminant_p, sensitivity_p, exposure_p, preflash_p, output

    # ------------------------------------------------------------------
    # Filter kernels (gaussian_blur_fir, gaussian_blur_iir, highlight_boost)
    # ------------------------------------------------------------------

    def gaussian_blur_fir(self, image: Any, kernel_1d: Any) -> np.ndarray:
        """Halide JIT separable FIR Gaussian blur with reflect (mirror) boundary.

        Inputs: image [C, H, W] float32, kernel_1d [radius*2+1] float32.
        Output: [C, H, W] float32.
        """
        image_np = np.ascontiguousarray(np.asarray(image, dtype=np.float32))
        kernel_np = np.ascontiguousarray(np.asarray(kernel_1d, dtype=np.float32)).ravel()
        if image_np.ndim != 3:
            raise ValueError(f"image must be 3D [C, H, W], got shape {image_np.shape}")
        if kernel_np.ndim != 1 or kernel_np.size % 2 == 0:
            raise ValueError(f"kernel_1d must be 1D with odd length, got shape {kernel_np.shape}")
        k_len = int(kernel_np.size)

        if self._fir_blur_pipeline is None or self._fir_blur_kernel_len != k_len:
            self._fir_blur_pipeline = self._build_fir_blur_pipeline(k_len)
            self._fir_blur_kernel_len = k_len

        kernel_param, image_param, output = self._fir_blur_pipeline
        kernel_param.set(self.hl.Buffer(kernel_np))
        image_param.set(self.hl.Buffer(image_np))
        C, H, W = image_np.shape
        result = np.asarray(output.realize([W, H, C]))
        return np.ascontiguousarray(result, dtype=np.float32)

    def _build_fir_blur_pipeline(self, k_len: int) -> tuple[Any, Any, Any]:
        hl = self.hl
        x = hl.Var(f"sf_halide_fir_x_{k_len}")
        y = hl.Var(f"sf_halide_fir_y_{k_len}")
        c = hl.Var(f"sf_halide_fir_c_{k_len}")
        kernel_param = hl.ImageParam(hl.Float(32), 1, f"sf_halide_fir_kernel_{k_len}")
        image_param = hl.ImageParam(hl.Float(32), 3, f"sf_halide_fir_image_{k_len}")
        h_blur = hl.Func(f"sf_halide_fir_h_{k_len}")
        v_blur = hl.Func(f"sf_halide_fir_v_{k_len}")
        output = hl.Func(f"sf_halide_fir_out_{k_len}")

        radius = k_len // 2
        r_k = hl.RDom([hl.Range(0, k_len)], f"sf_halide_fir_rk_{k_len}")
        k_off = r_k.x - radius

        # image [C,H,W]→[W,H,C]: image_param[x,y,c]
        img_mirrored = hl.BoundaryConditions.mirror_image(image_param)
        h_blur[x, y, c] = hl.f32(0.0)
        h_blur[x, y, c] += img_mirrored[x + k_off, y, c] * kernel_param[r_k.x]

        # Manual mirror_interior for y dimension on h_blur Func.
        # mirror_interior on a Func with RDom can produce incorrect boundary
        # accesses, so we compute the mirrored y coordinate explicitly.
        H_extent = image_param.dim(1).extent()

        def _mirror_y(val: Any) -> Any:
            neg = -val - 1
            past = 2 * (H_extent - 1) - val + 1
            return hl.clamp(
                hl.select(val < 0, neg, hl.select(val >= H_extent, past, val)),
                0,
                H_extent - 1,
            )

        v_blur[x, y, c] = hl.f32(0.0)
        v_blur[x, y, c] += h_blur[x, _mirror_y(y + k_off), c] * kernel_param[r_k.x]

        output[x, y, c] = v_blur[x, y, c]
        h_blur.vectorize(x, 8).parallel(y)
        v_blur.vectorize(x, 8).parallel(y)
        output.vectorize(x, 8).parallel(y)
        output.compile_jit(self.target)
        return kernel_param, image_param, output

    def gaussian_blur_iir(self, image: Any, sigma: float) -> np.ndarray:
        """Young-van Vliet 4-tap IIR Gaussian blur.

        Halide Python JIT does not support self-referencing recursive Funcs,
        so this uses the NumPy YVV reference implementation internally.
        Results are numerically identical to a Halide scan implementation.

        Inputs: image [C, H, W] float32, sigma >= 0.5 float.
        Output: [C, H, W] float32.
        """
        image_np = np.ascontiguousarray(np.asarray(image, dtype=np.float32))
        if image_np.ndim != 3:
            raise ValueError(f"image must be 3D [C, H, W], got shape {image_np.shape}")
        sigma_f = float(sigma)
        if sigma_f < 0.5:
            raise ValueError(f"sigma must be >= 0.5 for IIR, got {sigma_f}")

        from spektrafilm.utils.fast_gaussian_filter import _gaussian_filter_2d_large

        C, H, W = image_np.shape
        out = np.empty_like(image_np)
        for ch in range(C):
            out[ch] = _gaussian_filter_2d_large(image_np[ch], sigma_f)
        return out

    def highlight_boost(self, image: Any, *, threshold: float, boost: float, offset: float = 0.0) -> np.ndarray:
        """Halide JIT piecewise highlight boost.

        Inputs: image [C, H, W] float32, threshold, boost, offset scalars.
        Output: [C, H, W] float32.
        """
        image_np = np.ascontiguousarray(np.asarray(image, dtype=np.float32))
        if image_np.ndim != 3:
            raise ValueError(f"image must be 3D [C, H, W], got shape {image_np.shape}")

        if self._highlight_boost_pipeline is None:
            self._highlight_boost_pipeline = self._build_highlight_boost_pipeline()

        threshold_param, boost_param, offset_param, image_param, output = self._highlight_boost_pipeline
        threshold_param.set(float(threshold))
        boost_param.set(float(boost))
        offset_param.set(float(offset))
        image_param.set(self.hl.Buffer(image_np))
        C, H, W = image_np.shape
        result = np.asarray(output.realize([W, H, C]))
        return np.ascontiguousarray(result, dtype=np.float32)

    def _build_highlight_boost_pipeline(
        self,
    ) -> tuple[Any, Any, Any, Any, Any]:
        hl = self.hl
        x = hl.Var("sf_halide_hb_x")
        y = hl.Var("sf_halide_hb_y")
        c = hl.Var("sf_halide_hb_c")
        threshold_param = hl.Param(hl.Float(32), "sf_halide_hb_threshold", 0.0)
        boost_param = hl.Param(hl.Float(32), "sf_halide_hb_boost", 1.0)
        offset_param = hl.Param(hl.Float(32), "sf_halide_hb_offset", 0.0)
        image_param = hl.ImageParam(hl.Float(32), 3, "sf_halide_hb_image")
        output = hl.Func("sf_halide_hb_output")

        # image [C,H,W]→[W,H,C]: image_param[x,y,c]
        v = image_param[x, y, c]
        output[x, y, c] = hl.select(
            v < threshold_param,
            v,
            (v + offset_param) * boost_param,
        )
        output.vectorize(x, 8).parallel(y)
        output.compile_jit(self.target)
        return threshold_param, boost_param, offset_param, image_param, output

    # ------------------------------------------------------------------
    # CCTF (transfer function) kernels
    # ------------------------------------------------------------------

    def cctf_encode(
        self,
        linear: Any,
        *,
        gamma: float,
        threshold: float,
        a: float,
        b: float,
        c_coeff: float,
        d_coeff: float,
    ) -> np.ndarray:
        """Halide JIT sRGB-style piecewise CCTF encode.

        Input: linear [C, H, W] float32.
        Output: encoded [C, H, W] float32.
        if x <= threshold: a*x + b  else  c_coeff * pow(x, 1/gamma) - d_coeff
        """
        linear_np = np.ascontiguousarray(np.asarray(linear, dtype=np.float32))
        if linear_np.ndim != 3:
            raise ValueError(f"linear must be 3D [C, H, W], got shape {linear_np.shape}")
        channels, height, width = linear_np.shape

        if self._cctf_encode_pipeline is None:
            self._cctf_encode_pipeline = self._build_cctf_encode_pipeline()

        (gamma_p, threshold_p, a_p, b_p, c_p, d_p, image_p, output) = self._cctf_encode_pipeline
        gamma_p.set(float(gamma))
        threshold_p.set(float(threshold))
        a_p.set(float(a))
        b_p.set(float(b))
        c_p.set(float(c_coeff))
        d_p.set(float(d_coeff))
        image_p.set(self.hl.Buffer(linear_np))
        result = np.asarray(output.realize([width, height, channels]))
        return np.ascontiguousarray(result, dtype=np.float32)

    def _build_cctf_encode_pipeline(self) -> tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
        hl = self.hl
        x = hl.Var("sf_halide_cctf_enc_x")
        y = hl.Var("sf_halide_cctf_enc_y")
        c = hl.Var("sf_halide_cctf_enc_c")

        gamma_p = hl.Param(hl.Float(32), "sf_halide_cctf_enc_gamma", 2.4)
        threshold_p = hl.Param(hl.Float(32), "sf_halide_cctf_enc_threshold", 0.0031308)
        a_p = hl.Param(hl.Float(32), "sf_halide_cctf_enc_a", 12.92)
        b_p = hl.Param(hl.Float(32), "sf_halide_cctf_enc_b", 0.0)
        c_p = hl.Param(hl.Float(32), "sf_halide_cctf_enc_c", 1.055)
        d_p = hl.Param(hl.Float(32), "sf_halide_cctf_enc_d", 0.055)
        image_p = hl.ImageParam(hl.Float(32), 3, "sf_halide_cctf_enc_image")
        output = hl.Func("sf_halide_cctf_enc_output")

        v = image_p[x, y, c]
        linear_part = a_p * v + b_p
        gamma_part = c_p * hl.pow(v, 1.0 / gamma_p) - d_p
        output[x, y, c] = hl.select(v <= threshold_p, linear_part, gamma_part)
        output.parallel(y)
        output.compile_jit(self.target)
        return gamma_p, threshold_p, a_p, b_p, c_p, d_p, image_p, output

    def cctf_decode(
        self,
        encoded: Any,
        *,
        gamma: float,
        threshold: float,
        a: float,
        b: float,
        c_coeff: float,
        d_coeff: float,
    ) -> np.ndarray:
        """Halide JIT sRGB-style piecewise CCTF decode (inverse).

        Input: encoded [C, H, W] float32.
        Output: linear [C, H, W] float32.
        if x <= a*threshold+b: (x - b)/a  else  pow((x + d_coeff)/c_coeff, gamma)
        """
        encoded_np = np.ascontiguousarray(np.asarray(encoded, dtype=np.float32))
        if encoded_np.ndim != 3:
            raise ValueError(f"encoded must be 3D [C, H, W], got shape {encoded_np.shape}")
        channels, height, width = encoded_np.shape

        if self._cctf_decode_pipeline is None:
            self._cctf_decode_pipeline = self._build_cctf_decode_pipeline()

        (gamma_p, threshold_p, a_p, b_p, c_p, d_p, image_p, output) = self._cctf_decode_pipeline
        gamma_p.set(float(gamma))
        encoded_threshold = float(a) * float(threshold) + float(b)
        threshold_p.set(encoded_threshold)
        a_p.set(float(a))
        b_p.set(float(b))
        c_p.set(float(c_coeff))
        d_p.set(float(d_coeff))
        image_p.set(self.hl.Buffer(encoded_np))
        result = np.asarray(output.realize([width, height, channels]))
        return np.ascontiguousarray(result, dtype=np.float32)

    def _build_cctf_decode_pipeline(self) -> tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
        hl = self.hl
        x = hl.Var("sf_halide_cctf_dec_x")
        y = hl.Var("sf_halide_cctf_dec_y")
        c = hl.Var("sf_halide_cctf_dec_c")

        gamma_p = hl.Param(hl.Float(32), "sf_halide_cctf_dec_gamma", 2.4)
        threshold_p = hl.Param(hl.Float(32), "sf_halide_cctf_dec_threshold", 0.0031308)
        a_p = hl.Param(hl.Float(32), "sf_halide_cctf_dec_a", 12.92)
        b_p = hl.Param(hl.Float(32), "sf_halide_cctf_dec_b", 0.0)
        c_p = hl.Param(hl.Float(32), "sf_halide_cctf_dec_c", 1.055)
        d_p = hl.Param(hl.Float(32), "sf_halide_cctf_dec_d", 0.055)
        image_p = hl.ImageParam(hl.Float(32), 3, "sf_halide_cctf_dec_image")
        output = hl.Func("sf_halide_cctf_dec_output")

        v = image_p[x, y, c]
        linear_part = (v - b_p) / a_p
        gamma_part = hl.pow((v + d_p) / c_p, gamma_p)
        output[x, y, c] = hl.select(v <= threshold_p, linear_part, gamma_part)
        output.parallel(y)
        output.compile_jit(self.target)
        return gamma_p, threshold_p, a_p, b_p, c_p, d_p, image_p, output

    # ------------------------------------------------------------------
    # Interpolation kernels
    # ------------------------------------------------------------------

    def interp_1d(self, values: Any, positions: Any, query: Any) -> np.ndarray:
        """Halide JIT 1-D linear interpolation with clamped boundary.

        Inputs: values [N] float32, positions [N] float32 (ascending), query [H, W] float32.
        Output: [H, W] float32.
        """
        values_np = np.ascontiguousarray(np.asarray(values, dtype=np.float32)).ravel()
        positions_np = np.ascontiguousarray(np.asarray(positions, dtype=np.float32)).ravel()
        query_np = np.ascontiguousarray(np.asarray(query, dtype=np.float32))
        n = int(values_np.size)
        if positions_np.size != n:
            raise ValueError("values and positions must have the same length")
        if query_np.ndim != 2:
            raise ValueError(f"query must be 2D [H, W], got shape {query_np.shape}")

        if self._interp_1d_pipeline is None or self._interp_1d_n != n:
            self._interp_1d_pipeline = self._build_interp_1d_pipeline(n)
            self._interp_1d_n = n

        values_p, positions_p, query_p, output = self._interp_1d_pipeline
        values_p.set(self.hl.Buffer(values_np))
        positions_p.set(self.hl.Buffer(positions_np))
        query_p.set(self.hl.Buffer(query_np))
        height, width = query_np.shape
        result = np.asarray(output.realize([width, height]))
        return np.ascontiguousarray(result, dtype=np.float32)

    def _build_interp_1d_pipeline(self, n: int) -> tuple[Any, Any, Any, Any]:
        hl = self.hl
        x = hl.Var(f"sf_halide_interp1d_x_{n}")
        y = hl.Var(f"sf_halide_interp1d_y_{n}")

        values_p = hl.ImageParam(hl.Float(32), 1, f"sf_halide_interp1d_values_{n}")
        positions_p = hl.ImageParam(hl.Float(32), 1, f"sf_halide_interp1d_positions_{n}")
        query_p = hl.ImageParam(hl.Float(32), 2, f"sf_halide_interp1d_query_{n}")
        output = hl.Func(f"sf_halide_interp1d_output_{n}")

        query_bounded = hl.BoundaryConditions.constant_exterior(query_p, 0.0)
        q = query_bounded[x, y]
        n_minus_1 = float(n - 1)

        # Clamp query to [positions[0], positions[-1]]
        q_clamped = hl.clamp(q, positions_p[0], positions_p[hl.cast(hl.Int(32), n_minus_1)])

        # Build a select chain: for each interval i, check q < positions[i+1].
        # Start with the last interval as default, then walk from i=0 outward
        # so that higher i checks (outermost select) have priority.
        last_idx = hl.cast(hl.Int(32), n_minus_1 - 1)
        t_last = (q_clamped - positions_p[last_idx]) / (positions_p[last_idx + 1] - positions_p[last_idx])
        t_last = hl.clamp(t_last, hl.f32(0.0), hl.f32(1.0))
        result = values_p[last_idx] + t_last * (values_p[last_idx + 1] - values_p[last_idx])

        # Walk intervals from n-3 down to 0 (each new i wraps as outermost select)
        for i in range(n - 3, -1, -1):
            idx = hl.cast(hl.Int(32), i)
            t_i = (q_clamped - positions_p[idx]) / (positions_p[idx + 1] - positions_p[idx])
            t_i = hl.clamp(t_i, hl.f32(0.0), hl.f32(1.0))
            interp_i = values_p[idx] + t_i * (values_p[idx + 1] - values_p[idx])
            result = hl.select(q_clamped < positions_p[idx + 1], interp_i, result)

        output[x, y] = result
        output.vectorize(x, 8).parallel(y)
        output.compile_jit(self.target)
        return values_p, positions_p, query_p, output

    # ------------------------------------------------------------------
    # 2-D cubic LUT interpolation
    # ------------------------------------------------------------------

    def lut_2d_cubic(self, lut: Any, image: Any) -> np.ndarray:
        """Halide JIT Mitchell-Netravali (B=1/3, C=1/3) bicubic 2-D LUT.

        Inputs: lut [size, size, C] float32, image [H, W, 2] float32 (0-1 normalised).
        Output: [H, W, C] float32.
        """
        lut_np = np.ascontiguousarray(np.asarray(lut, dtype=np.float32))
        image_np = np.ascontiguousarray(np.asarray(image, dtype=np.float32))
        if lut_np.ndim != 3:
            raise ValueError(f"lut must be 3D [size, size, C], got shape {lut_np.shape}")
        size = int(lut_np.shape[0])
        if size != lut_np.shape[1]:
            raise ValueError("lut must be square in first two dims")
        if image_np.ndim != 3 or image_np.shape[-1] != 2:
            raise ValueError(f"image must be [H, W, 2], got shape {image_np.shape}")

        n_channels = int(lut_np.shape[2])

        if self._lut_2d_pipeline is None or self._lut_2d_size != size:
            self._lut_2d_pipeline = self._build_lut_2d_cubic_pipeline(size, n_channels)
            self._lut_2d_size = size

        lut_p, image_p, output = self._lut_2d_pipeline
        # LUT: [size, size, C] -> transpose to [C, size, size] for Halide
        lut_chw = np.ascontiguousarray(np.transpose(lut_np, (2, 1, 0)))
        lut_p.set(self.hl.Buffer(lut_chw))
        # Image stays [H, W, 2] — no transpose needed
        image_p.set(self.hl.Buffer(image_np))
        height, width = image_np.shape[:2]
        result = np.asarray(output.realize([width, height, n_channels]))
        return np.ascontiguousarray(np.transpose(result, (1, 2, 0)), dtype=np.float32)

    def _build_lut_2d_cubic_pipeline(self, size: int, n_channels: int) -> tuple[Any, Any, Any]:
        hl = self.hl
        x = hl.Var(f"sf_halide_lut2d_x_{size}")
        y = hl.Var(f"sf_halide_lut2d_y_{size}")
        c = hl.Var(f"sf_halide_lut2d_c_{size}")

        lut_p = hl.ImageParam(hl.Float(32), 3, f"sf_halide_lut2d_lut_{size}")
        image_p = hl.ImageParam(hl.Float(32), 3, f"sf_halide_lut2d_image_{size}")
        output = hl.Func(f"sf_halide_lut2d_output_{size}")

        upper = float(size - 1)

        # Map [0,1] to [0, size-1]. image_np is [H, W, 2] → Halide buffer [2, W, H].
        fx = image_p[0, x, y] * upper
        fy = image_p[1, x, y] * upper
        fx = hl.clamp(fx, 0.0, upper)
        fy = hl.clamp(fy, 0.0, upper)

        ix = hl.cast(hl.Int(32), hl.floor(fx))
        iy = hl.cast(hl.Int(32), hl.floor(fy))

        # Fractional parts
        dx = fx - hl.cast(hl.Float(32), ix)
        dy = fy - hl.cast(hl.Float(32), iy)

        # Mitchell-Netravali kernel (B=1/3, C=1/3)
        # w(t) = (1/6)*((12-9B-6C)*|t|^3 + (-18+12B+6C)*|t|^2 + (6-2B))        for |t|<1
        # w(t) = (1/6)*((-B-6C)*|t|^3 + (6B+30C)*|t|^2 + (-12B-48C)*|t|+(8B+24C)) for 1<=|t|<2
        B_val = 1.0 / 3.0
        C_val = 1.0 / 3.0
        # Pre-computed coefficients
        # For |t|<1: (12-9B-6C)/6, (-18+12B+6C)/6, (6-2B)/6, 0
        # For 1<=|t|<2: (-B-6C)/6, (6B+30C)/6, (-12B-48C)/6, (8B+24C)/6
        k0_a = hl.f32((12.0 - 9.0 * B_val - 6.0 * C_val) / 6.0)
        k0_b = hl.f32((-18.0 + 12.0 * B_val + 6.0 * C_val) / 6.0)
        k0_c = hl.f32((6.0 - 2.0 * B_val) / 6.0)

        k1_a = hl.f32((-B_val - 6.0 * C_val) / 6.0)
        k1_b = hl.f32((6.0 * B_val + 30.0 * C_val) / 6.0)
        k1_c = hl.f32((-12.0 * B_val - 48.0 * C_val) / 6.0)
        k1_d = hl.f32((8.0 * B_val + 24.0 * C_val) / 6.0)

        def mitchell(t: Any) -> Any:
            at = hl.abs(t)
            t2 = at * at
            t3 = t2 * at
            inner = k0_a * t3 + k0_b * t2 + k0_c
            outer = k1_a * t3 + k1_b * t2 + k1_c * at + k1_d
            return hl.select(at < 1.0, inner, outer)

        def safe_lut(cx: Any, cy: Any) -> Any:
            cx_c = hl.clamp(cx, 0, size - 1)
            cy_c = hl.clamp(cy, 0, size - 1)
            return lut_p[cy_c, cx_c, c]

        # 4x4 bicubic: sum over m,n in {-1,0,1,2}
        acc = hl.f32(0.0)
        for m in range(-1, 3):
            for n in range(-1, 3):
                wx = mitchell(dx - hl.f32(float(m)))
                wy = mitchell(dy - hl.f32(float(n)))
                acc = acc + safe_lut(ix + m, iy + n) * wx * wy

        output[x, y, c] = acc
        output.reorder(c, x, y).bound(c, 0, n_channels).unroll(c).parallel(y)
        output.compile_jit(self.target)
        return lut_p, image_p, output

    # ------------------------------------------------------------------
    # Grain buffer (NumPy only, no Halide)
    # ------------------------------------------------------------------

    @staticmethod
    def generate_grain_buffer(shape: tuple[int, ...], seed: int) -> np.ndarray:
        """Generate a reproducible float32 Gaussian noise buffer.

        This is intentionally a NumPy-only helper, not a Halide kernel.
        """
        return np.random.RandomState(seed).standard_normal(shape).astype(np.float32)
