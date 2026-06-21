from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from spektrafilm.gpu.backend import BackendUnavailableError
from spektrafilm.gpu.residency import record_conversion


_CMY_TO_LOG_RAW_KERNEL = None
_CMY_TO_LOG_RAW_PIXEL_THREAD_KERNEL = None
_CMY_TO_LOG_RAW_PIXEL_THREAD_K_TEMPLATE_KERNELS: dict[int, Any] = {}
_CMY_TO_LOG_RAW_PIXEL_THREAD_TABLE_CACHE_KERNELS: dict[tuple[int, int], Any] = {}


def _get_cmy_to_log_raw_kernel(mx):
    global _CMY_TO_LOG_RAW_KERNEL
    if _CMY_TO_LOG_RAW_KERNEL is not None:
        return _CMY_TO_LOG_RAW_KERNEL

    source = """
        uint elem = thread_position_in_grid.x;
        uint total = density_cmy_shape[0];
        if (elem >= total) {
            return;
        }

        uint c = elem % 3;
        uint pixel = elem / 3;
        uint K = channel_density_shape[0] / 3;

        float c0 = float(density_cmy[pixel * 3 + 0]);
        float c1 = float(density_cmy[pixel * 3 + 1]);
        float c2 = float(density_cmy[pixel * 3 + 2]);
        float raw = 0.0f;

        for (uint k = 0; k < K; k++) {
            float d = (
                c0 * float(channel_density[k * 3 + 0])
                + c1 * float(channel_density[k * 3 + 1])
                + c2 * float(channel_density[k * 3 + 2])
                + float(base_density[k])
            );
            if (!(d == d)) {
                continue;
            }
            if (d < -35.0f) {
                d = -35.0f;
            }
            float light = pow(10.0f, -d) * float(print_illuminant[k]);
            raw += light * float(sensitivity[k * 3 + c]);
        }

        raw = raw * float(exposure_factor[0]) + float(preflash[c]);
        if (!(raw == raw)) {
            raw = 0.0f;
        }
        if (raw < 0.0f) {
            raw = 0.0f;
        }
        out[elem] = T(log10(raw + 1e-10f));
    """
    _CMY_TO_LOG_RAW_KERNEL = mx.fast.metal_kernel(
        name="spektrafilm_cmy_to_log_raw",
        input_names=[
            "density_cmy",
            "channel_density",
            "base_density",
            "print_illuminant",
            "sensitivity",
            "exposure_factor",
            "preflash",
        ],
        output_names=["out"],
        source=source,
    )
    return _CMY_TO_LOG_RAW_KERNEL


def _get_cmy_to_log_raw_pixel_thread_kernel(mx):
    global _CMY_TO_LOG_RAW_PIXEL_THREAD_KERNEL
    if _CMY_TO_LOG_RAW_PIXEL_THREAD_KERNEL is not None:
        return _CMY_TO_LOG_RAW_PIXEL_THREAD_KERNEL

    source = """
        uint pixel = thread_position_in_grid.x;
        uint total = density_cmy_shape[0] / 3;
        if (pixel >= total) {
            return;
        }

        uint K = channel_density_shape[0] / 3;

        float c0 = float(density_cmy[pixel * 3 + 0]);
        float c1 = float(density_cmy[pixel * 3 + 1]);
        float c2 = float(density_cmy[pixel * 3 + 2]);
        float raw0 = 0.0f;
        float raw1 = 0.0f;
        float raw2 = 0.0f;

        for (uint k = 0; k < K; k++) {
            float d = (
                c0 * float(channel_density[k * 3 + 0])
                + c1 * float(channel_density[k * 3 + 1])
                + c2 * float(channel_density[k * 3 + 2])
                + float(base_density[k])
            );
            if (!(d == d)) {
                continue;
            }
            if (d < -35.0f) {
                d = -35.0f;
            }
            float light = pow(10.0f, -d) * float(print_illuminant[k]);
            raw0 += light * float(sensitivity[k * 3 + 0]);
            raw1 += light * float(sensitivity[k * 3 + 1]);
            raw2 += light * float(sensitivity[k * 3 + 2]);
        }

        float exposure = float(exposure_factor[0]);
        raw0 = raw0 * exposure + float(preflash[0]);
        raw1 = raw1 * exposure + float(preflash[1]);
        raw2 = raw2 * exposure + float(preflash[2]);

        if (!(raw0 == raw0)) {
            raw0 = 0.0f;
        }
        if (!(raw1 == raw1)) {
            raw1 = 0.0f;
        }
        if (!(raw2 == raw2)) {
            raw2 = 0.0f;
        }
        if (raw0 < 0.0f) {
            raw0 = 0.0f;
        }
        if (raw1 < 0.0f) {
            raw1 = 0.0f;
        }
        if (raw2 < 0.0f) {
            raw2 = 0.0f;
        }

        out[pixel * 3 + 0] = T(log10(raw0 + 1e-10f));
        out[pixel * 3 + 1] = T(log10(raw1 + 1e-10f));
        out[pixel * 3 + 2] = T(log10(raw2 + 1e-10f));
    """
    _CMY_TO_LOG_RAW_PIXEL_THREAD_KERNEL = mx.fast.metal_kernel(
        name="spektrafilm_cmy_to_log_raw_pixel_thread_v1",
        input_names=[
            "density_cmy",
            "channel_density",
            "base_density",
            "print_illuminant",
            "sensitivity",
            "exposure_factor",
            "preflash",
        ],
        output_names=["out"],
        source=source,
    )
    return _CMY_TO_LOG_RAW_PIXEL_THREAD_KERNEL


def _get_cmy_to_log_raw_pixel_thread_k_template_kernel(mx, K: int):
    global _CMY_TO_LOG_RAW_PIXEL_THREAD_K_TEMPLATE_KERNELS
    cached = _CMY_TO_LOG_RAW_PIXEL_THREAD_K_TEMPLATE_KERNELS.get(K)
    if cached is not None:
        return cached

    source = """
        uint pixel = thread_position_in_grid.x;
        uint total = density_cmy_shape[0] / 3;
        if (pixel >= total) {
            return;
        }

        float c0 = float(density_cmy[pixel * 3 + 0]);
        float c1 = float(density_cmy[pixel * 3 + 1]);
        float c2 = float(density_cmy[pixel * 3 + 2]);
        float raw0 = 0.0f;
        float raw1 = 0.0f;
        float raw2 = 0.0f;

        for (uint k = 0; k < K; k++) {
            float d = (
                c0 * float(channel_density[k * 3 + 0])
                + c1 * float(channel_density[k * 3 + 1])
                + c2 * float(channel_density[k * 3 + 2])
                + float(base_density[k])
            );
            if (!(d == d)) {
                continue;
            }
            if (d < -35.0f) {
                d = -35.0f;
            }
            float light = pow(10.0f, -d) * float(print_illuminant[k]);
            raw0 += light * float(sensitivity[k * 3 + 0]);
            raw1 += light * float(sensitivity[k * 3 + 1]);
            raw2 += light * float(sensitivity[k * 3 + 2]);
        }

        float exposure = float(exposure_factor[0]);
        raw0 = raw0 * exposure + float(preflash[0]);
        raw1 = raw1 * exposure + float(preflash[1]);
        raw2 = raw2 * exposure + float(preflash[2]);

        if (!(raw0 == raw0)) {
            raw0 = 0.0f;
        }
        if (!(raw1 == raw1)) {
            raw1 = 0.0f;
        }
        if (!(raw2 == raw2)) {
            raw2 = 0.0f;
        }
        if (raw0 < 0.0f) {
            raw0 = 0.0f;
        }
        if (raw1 < 0.0f) {
            raw1 = 0.0f;
        }
        if (raw2 < 0.0f) {
            raw2 = 0.0f;
        }

        out[pixel * 3 + 0] = T(log10(raw0 + 1e-10f));
        out[pixel * 3 + 1] = T(log10(raw1 + 1e-10f));
        out[pixel * 3 + 2] = T(log10(raw2 + 1e-10f));
    """
    kernel = mx.fast.metal_kernel(
        name=f"spektrafilm_cmy_to_log_raw_pixel_thread_k_template_K{K}",
        input_names=[
            "density_cmy",
            "channel_density",
            "base_density",
            "print_illuminant",
            "sensitivity",
            "exposure_factor",
            "preflash",
        ],
        output_names=["out"],
        source=source,
    )
    _CMY_TO_LOG_RAW_PIXEL_THREAD_K_TEMPLATE_KERNELS[K] = kernel
    return kernel


def _get_cmy_to_log_raw_pixel_thread_table_cache_kernel(mx, K: int, threadgroup_size: int):
    global _CMY_TO_LOG_RAW_PIXEL_THREAD_TABLE_CACHE_KERNELS
    key = (K, threadgroup_size)
    cached = _CMY_TO_LOG_RAW_PIXEL_THREAD_TABLE_CACHE_KERNELS.get(key)
    if cached is not None:
        return cached

    source = """
        uint pixel = thread_position_in_grid.x;
        uint total = density_cmy_shape[0] / 3;
        uint local_id = thread_position_in_threadgroup.x;

        threadgroup float channel_density_cache[256 * 3];
        threadgroup float sensitivity_cache[256 * 3];
        threadgroup float base_density_cache[256];
        threadgroup float print_illuminant_cache[256];

        uint threads_in_group = threads_per_threadgroup.x;
        for (uint idx = local_id; idx < K; idx += threads_in_group) {
            channel_density_cache[idx * 3 + 0] = float(channel_density[idx * 3 + 0]);
            channel_density_cache[idx * 3 + 1] = float(channel_density[idx * 3 + 1]);
            channel_density_cache[idx * 3 + 2] = float(channel_density[idx * 3 + 2]);
            sensitivity_cache[idx * 3 + 0] = float(sensitivity[idx * 3 + 0]);
            sensitivity_cache[idx * 3 + 1] = float(sensitivity[idx * 3 + 1]);
            sensitivity_cache[idx * 3 + 2] = float(sensitivity[idx * 3 + 2]);
            base_density_cache[idx] = float(base_density[idx]);
            print_illuminant_cache[idx] = float(print_illuminant[idx]);
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);

        if (pixel >= total) {
            return;
        }

        float c0 = float(density_cmy[pixel * 3 + 0]);
        float c1 = float(density_cmy[pixel * 3 + 1]);
        float c2 = float(density_cmy[pixel * 3 + 2]);
        float raw0 = 0.0f;
        float raw1 = 0.0f;
        float raw2 = 0.0f;

        for (uint k = 0; k < K; k++) {
            float d = (
                c0 * channel_density_cache[k * 3 + 0]
                + c1 * channel_density_cache[k * 3 + 1]
                + c2 * channel_density_cache[k * 3 + 2]
                + base_density_cache[k]
            );
            if (!(d == d)) {
                continue;
            }
            if (d < -35.0f) {
                d = -35.0f;
            }
            float light = pow(10.0f, -d) * print_illuminant_cache[k];
            raw0 += light * sensitivity_cache[k * 3 + 0];
            raw1 += light * sensitivity_cache[k * 3 + 1];
            raw2 += light * sensitivity_cache[k * 3 + 2];
        }

        float exposure = float(exposure_factor[0]);
        raw0 = raw0 * exposure + float(preflash[0]);
        raw1 = raw1 * exposure + float(preflash[1]);
        raw2 = raw2 * exposure + float(preflash[2]);

        if (!(raw0 == raw0)) {
            raw0 = 0.0f;
        }
        if (!(raw1 == raw1)) {
            raw1 = 0.0f;
        }
        if (!(raw2 == raw2)) {
            raw2 = 0.0f;
        }
        if (raw0 < 0.0f) {
            raw0 = 0.0f;
        }
        if (raw1 < 0.0f) {
            raw1 = 0.0f;
        }
        if (raw2 < 0.0f) {
            raw2 = 0.0f;
        }

        out[pixel * 3 + 0] = T(log10(raw0 + 1e-10f));
        out[pixel * 3 + 1] = T(log10(raw1 + 1e-10f));
        out[pixel * 3 + 2] = T(log10(raw2 + 1e-10f));
    """
    kernel = mx.fast.metal_kernel(
        name=f"spektrafilm_cmy_to_log_raw_pixel_thread_table_cache_K{K}_TG{threadgroup_size}",
        input_names=[
            "density_cmy",
            "channel_density",
            "base_density",
            "print_illuminant",
            "sensitivity",
            "exposure_factor",
            "preflash",
        ],
        output_names=["out"],
        source=source,
    )
    _CMY_TO_LOG_RAW_PIXEL_THREAD_TABLE_CACHE_KERNELS[key] = kernel
    return kernel


class MlxBackend:
    name = "mlx"
    supports_gpu = True
    fallback_reason = None
    requires_serial_runtime = True

    def __init__(self, *, precision: str = "float32"):
        try:
            import mlx.core as mx
        except ModuleNotFoundError as exc:
            raise BackendUnavailableError(
                "compute_backend='mlx' requires the optional dependency: "
                "install spektrafilm[gpu-apple]."
            ) from exc

        metal = getattr(mx, "metal", None)
        is_available = getattr(metal, "is_available", None)
        if is_available is None or not bool(is_available()):
            raise BackendUnavailableError(
                "compute_backend='mlx' requires Apple Metal support through MLX."
            )

        if precision not in {"float32", "float16"}:
            raise ValueError("gpu_precision must be 'float32' or 'float16'")

        self.mx = mx
        self.precision = precision
        self.default_dtype = mx.float32 if precision == "float32" else mx.float16
        self._compiled_elementwise_cache: dict[tuple[Any, ...], Callable[..., Any]] = {}
        self._probe_device()

    def _probe_device(self) -> None:
        try:
            probe = self.mx.array([0.0], dtype=self.default_dtype)
            self.mx.eval(probe)
        except (RuntimeError, OSError, ValueError) as exc:
            raise BackendUnavailableError(
                "compute_backend='mlx' requires a usable Apple Metal device."
            ) from exc

    @staticmethod
    def _is_mlx_array(value: Any) -> bool:
        return type(value).__module__.startswith("mlx.")

    def asarray(self, value: Any, dtype: Any | None = None):
        if self._is_mlx_array(value):
            if dtype is None or value.dtype == dtype:
                result = value
            else:
                result = value.astype(dtype)
        else:
            result = self.mx.array(value, dtype=dtype or self.default_dtype)
        record_conversion("asarray", self.name, value, result)
        return result

    def to_numpy(self, value: Any) -> np.ndarray:
        if not self._is_mlx_array(value):
            result = np.asarray(value)
            record_conversion("to_numpy", self.name, value, result)
            return result
        self.eval(value)
        result = np.asarray(value)
        record_conversion("to_numpy", self.name, value, result)
        return result

    def eval(self, *values: Any) -> None:
        mlx_values = [value for value in values if self._is_mlx_array(value)]
        if mlx_values:
            self.mx.eval(*mlx_values)

    def synchronize(self) -> None:
        self.mx.synchronize()

    def cleanup(self) -> None:
        import gc
        gc.collect()
        self.synchronize()
        clear_cache = getattr(self.mx, "clear_cache", None)
        if not callable(clear_cache):
            metal = getattr(self.mx, "metal", None)
            clear_cache = getattr(metal, "clear_cache", None)
        if callable(clear_cache):
            clear_cache()

    def _compile_arg_signature(self, value: Any) -> tuple[Any, ...]:
        if self._is_mlx_array(value):
            return (
                "mlx",
                tuple(int(dim) for dim in value.shape),
                str(value.dtype),
            )
        return ("python", type(value).__module__, type(value).__qualname__)

    def compiled_elementwise(
        self,
        name: str,
        function: Callable[..., Any],
        *sample_args: Any,
    ) -> Callable[..., Any]:
        compile_fn = getattr(self.mx, "compile", None)
        if not callable(compile_fn):
            return function

        key = (
            str(name),
            id(function),
            hash(function.__code__.co_code),
            tuple(self._compile_arg_signature(arg) for arg in sample_args),
        )
        compiled = self._compiled_elementwise_cache.get(key)
        if compiled is None:
            if len(self._compiled_elementwise_cache) >= 128:
                self._compiled_elementwise_cache.clear()
            compiled = compile_fn(function)
            self._compiled_elementwise_cache[key] = compiled
        return compiled

    def exp(self, x: Any):
        return self.mx.exp(x)

    def log10(self, x: Any):
        return self.mx.log10(x)

    def maximum(self, x: Any, y: Any):
        return self.mx.maximum(x, y)

    def max_array(self, x: Any):
        return self.mx.max(x)

    def max(self, x: Any) -> float:
        value = self.mx.max(x)
        self.eval(value)
        return float(np.asarray(value))

    def clip(self, x: Any, lo: float, hi: float):
        return self.mx.clip(x, lo, hi)

    def matmul(self, a: Any, b: Any):
        return self.mx.matmul(a, b)

    def einsum(self, pattern: str, *values: Any):
        return self.mx.einsum(pattern, *values)

    def power(self, base: float, x: Any):
        # MLX: base**x = exp(x * ln(base))
        import math
        return self.mx.exp(x * math.log(base))

    def pow(self, x: Any, exponent: float):
        power = getattr(self.mx, "power", None)
        if power is not None:
            return power(x, exponent)
        return x ** exponent

    def fmax(self, x: Any, y: float):
        return self.mx.where(
            self.mx.isnan(x),
            y,
            self.mx.where(self.mx.isnan(y), x, self.mx.maximum(x, y)),
        )

    def nan_to_num(self, x: Any, nan: float = 0.0):
        x = self.mx.where(self.mx.isnan(x), nan, x)
        dtype = getattr(x, "dtype", self.default_dtype)
        np_dtype = np.float16 if "float16" in str(dtype) else np.float32
        big = self.mx.array(np.finfo(np_dtype).max, dtype=dtype)
        x = self.mx.where(self.mx.isinf(x) & (x > 0), big, x)
        x = self.mx.where(self.mx.isinf(x) & (x < 0), -big, x)
        return x

    def where(self, condition: Any, x: Any, y: Any):
        return self.mx.where(condition, x, y)

    def abs(self, x: Any):
        return self.mx.abs(x)

    def cmy_to_log_raw(
        self,
        density_cmy: Any,
        channel_density: Any,
        base_density: Any,
        print_illuminant: Any,
        sensitivity: Any,
        exposure_factor: Any,
        preflash: Any,
    ):
        # Use the table-cache variant for small spectral lengths (the cache
        # fits in threadgroup memory for K <= 256). Larger K falls back to the
        # pixel-thread baseline inside the table-cache implementation.
        return self.cmy_to_log_raw_pixel_thread_table_cache(
            density_cmy,
            channel_density,
            base_density,
            print_illuminant,
            sensitivity,
            exposure_factor,
            preflash,
        )

    def cmy_to_log_raw_channel_thread_baseline(
        self,
        density_cmy: Any,
        channel_density: Any,
        base_density: Any,
        print_illuminant: Any,
        sensitivity: Any,
        exposure_factor: Any,
        preflash: Any,
    ):
        density_cmy_mx = self.asarray(density_cmy, dtype=self.default_dtype)
        channel_density_mx = self.asarray(channel_density, dtype=self.default_dtype)
        base_density_mx = self.asarray(base_density, dtype=self.default_dtype)
        print_illuminant_mx = self.asarray(print_illuminant, dtype=self.default_dtype)
        sensitivity_mx = self.asarray(sensitivity, dtype=self.default_dtype)
        exposure_factor_mx = self.asarray(exposure_factor, dtype=self.default_dtype).reshape(-1)
        preflash_mx = self.asarray(preflash, dtype=self.default_dtype).reshape(-1)

        shape = tuple(int(dim) for dim in density_cmy_mx.shape)
        if len(shape) != 3 or shape[-1] != 3:
            raise ValueError("density_cmy must have shape (H, W, 3)")

        flat_density = self.mx.reshape(density_cmy_mx, (-1,))
        flat_channel_density = self.mx.reshape(channel_density_mx, (-1,))
        flat_base_density = self.mx.reshape(base_density_mx, (-1,))
        flat_print_illuminant = self.mx.reshape(print_illuminant_mx, (-1,))
        flat_sensitivity = self.mx.reshape(sensitivity_mx, (-1,))

        kernel = _get_cmy_to_log_raw_kernel(self.mx)
        out = kernel(
            inputs=[
                flat_density,
                flat_channel_density,
                flat_base_density,
                flat_print_illuminant,
                flat_sensitivity,
                exposure_factor_mx,
                preflash_mx,
            ],
            template=[("T", density_cmy_mx.dtype)],
            grid=(int(np.prod(shape)), 1, 1),
            threadgroup=(256, 1, 1),
            output_shapes=[(int(np.prod(shape)),)],
            output_dtypes=[density_cmy_mx.dtype],
        )[0]
        return self.mx.reshape(out, shape)

    def cmy_to_log_raw_pixel_thread_v1(
        self,
        density_cmy: Any,
        channel_density: Any,
        base_density: Any,
        print_illuminant: Any,
        sensitivity: Any,
        exposure_factor: Any,
        preflash: Any,
        *,
        threadgroup_size: int = 256,
    ):
        density_cmy_mx = self.asarray(density_cmy, dtype=self.default_dtype)
        channel_density_mx = self.asarray(channel_density, dtype=self.default_dtype)
        base_density_mx = self.asarray(base_density, dtype=self.default_dtype)
        print_illuminant_mx = self.asarray(print_illuminant, dtype=self.default_dtype)
        sensitivity_mx = self.asarray(sensitivity, dtype=self.default_dtype)
        exposure_factor_mx = self.asarray(exposure_factor, dtype=self.default_dtype).reshape(-1)
        preflash_mx = self.asarray(preflash, dtype=self.default_dtype).reshape(-1)

        shape = tuple(int(dim) for dim in density_cmy_mx.shape)
        if len(shape) != 3 or shape[-1] != 3:
            raise ValueError("density_cmy must have shape (H, W, 3)")

        flat_density = self.mx.reshape(density_cmy_mx, (-1,))
        flat_channel_density = self.mx.reshape(channel_density_mx, (-1,))
        flat_base_density = self.mx.reshape(base_density_mx, (-1,))
        flat_print_illuminant = self.mx.reshape(print_illuminant_mx, (-1,))
        flat_sensitivity = self.mx.reshape(sensitivity_mx, (-1,))
        total_pixels = int(np.prod(shape[:2]))
        total_elements = int(np.prod(shape))

        kernel = _get_cmy_to_log_raw_pixel_thread_kernel(self.mx)
        out = kernel(
            inputs=[
                flat_density,
                flat_channel_density,
                flat_base_density,
                flat_print_illuminant,
                flat_sensitivity,
                exposure_factor_mx,
                preflash_mx,
            ],
            template=[("T", density_cmy_mx.dtype)],
            grid=(total_pixels, 1, 1),
            threadgroup=(int(threadgroup_size), 1, 1),
            output_shapes=[(total_elements,)],
            output_dtypes=[density_cmy_mx.dtype],
        )[0]
        return self.mx.reshape(out, shape)

    def cmy_to_log_raw_pixel_thread_k_template(
        self,
        density_cmy: Any,
        channel_density: Any,
        base_density: Any,
        print_illuminant: Any,
        sensitivity: Any,
        exposure_factor: Any,
        preflash: Any,
        *,
        threadgroup_size: int = 256,
    ):
        density_cmy_mx = self.asarray(density_cmy, dtype=self.default_dtype)
        channel_density_mx = self.asarray(channel_density, dtype=self.default_dtype)
        base_density_mx = self.asarray(base_density, dtype=self.default_dtype)
        print_illuminant_mx = self.asarray(print_illuminant, dtype=self.default_dtype)
        sensitivity_mx = self.asarray(sensitivity, dtype=self.default_dtype)
        exposure_factor_mx = self.asarray(exposure_factor, dtype=self.default_dtype).reshape(-1)
        preflash_mx = self.asarray(preflash, dtype=self.default_dtype).reshape(-1)

        shape = tuple(int(dim) for dim in density_cmy_mx.shape)
        if len(shape) != 3 or shape[-1] != 3:
            raise ValueError("density_cmy must have shape (H, W, 3)")

        flat_density = self.mx.reshape(density_cmy_mx, (-1,))
        flat_channel_density = self.mx.reshape(channel_density_mx, (-1,))
        flat_base_density = self.mx.reshape(base_density_mx, (-1,))
        flat_print_illuminant = self.mx.reshape(print_illuminant_mx, (-1,))
        flat_sensitivity = self.mx.reshape(sensitivity_mx, (-1,))
        total_pixels = int(np.prod(shape[:2]))
        total_elements = int(np.prod(shape))
        spectral_length = int(flat_channel_density.shape[0]) // 3

        kernel = _get_cmy_to_log_raw_pixel_thread_k_template_kernel(self.mx, spectral_length)
        out = kernel(
            inputs=[
                flat_density,
                flat_channel_density,
                flat_base_density,
                flat_print_illuminant,
                flat_sensitivity,
                exposure_factor_mx,
                preflash_mx,
            ],
            template=[("T", density_cmy_mx.dtype), ("K", spectral_length)],
            grid=(total_pixels, 1, 1),
            threadgroup=(int(threadgroup_size), 1, 1),
            output_shapes=[(total_elements,)],
            output_dtypes=[density_cmy_mx.dtype],
        )[0]
        return self.mx.reshape(out, shape)

    def cmy_to_log_raw_pixel_thread_table_cache(
        self,
        density_cmy: Any,
        channel_density: Any,
        base_density: Any,
        print_illuminant: Any,
        sensitivity: Any,
        exposure_factor: Any,
        preflash: Any,
        *,
        threadgroup_size: int = 256,
    ):
        density_cmy_mx = self.asarray(density_cmy, dtype=self.default_dtype)
        channel_density_mx = self.asarray(channel_density, dtype=self.default_dtype)
        base_density_mx = self.asarray(base_density, dtype=self.default_dtype)
        print_illuminant_mx = self.asarray(print_illuminant, dtype=self.default_dtype)
        sensitivity_mx = self.asarray(sensitivity, dtype=self.default_dtype)
        exposure_factor_mx = self.asarray(exposure_factor, dtype=self.default_dtype).reshape(-1)
        preflash_mx = self.asarray(preflash, dtype=self.default_dtype).reshape(-1)

        shape = tuple(int(dim) for dim in density_cmy_mx.shape)
        if len(shape) != 3 or shape[-1] != 3:
            raise ValueError("density_cmy must have shape (H, W, 3)")

        flat_density = self.mx.reshape(density_cmy_mx, (-1,))
        flat_channel_density = self.mx.reshape(channel_density_mx, (-1,))
        flat_base_density = self.mx.reshape(base_density_mx, (-1,))
        flat_print_illuminant = self.mx.reshape(print_illuminant_mx, (-1,))
        flat_sensitivity = self.mx.reshape(sensitivity_mx, (-1,))
        total_pixels = int(np.prod(shape[:2]))
        total_elements = int(np.prod(shape))
        spectral_length = int(flat_channel_density.shape[0]) // 3
        if spectral_length > 256:
            return self.cmy_to_log_raw_pixel_thread_v1(
                density_cmy_mx,
                channel_density_mx,
                base_density_mx,
                print_illuminant_mx,
                sensitivity_mx,
                exposure_factor_mx,
                preflash_mx,
                threadgroup_size=threadgroup_size,
            )

        kernel = _get_cmy_to_log_raw_pixel_thread_table_cache_kernel(
            self.mx, spectral_length, int(threadgroup_size)
        )
        out = kernel(
            inputs=[
                flat_density,
                flat_channel_density,
                flat_base_density,
                flat_print_illuminant,
                flat_sensitivity,
                exposure_factor_mx,
                preflash_mx,
            ],
            template=[
                ("T", density_cmy_mx.dtype),
                ("K", spectral_length),
                ("THREADGROUP_SIZE", int(threadgroup_size)),
            ],
            grid=(total_pixels, 1, 1),
            threadgroup=(int(threadgroup_size), 1, 1),
            output_shapes=[(total_elements,)],
            output_dtypes=[density_cmy_mx.dtype],
        )[0]
        return self.mx.reshape(out, shape)
