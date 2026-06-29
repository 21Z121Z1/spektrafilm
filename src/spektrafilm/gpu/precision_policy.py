from __future__ import annotations

from dataclasses import dataclass
from math import log10
from typing import Any, Literal

import numpy as np


PrecisionPolicyName = Literal["fast", "balanced", "strict"]

POLICY_FAST: PrecisionPolicyName = "fast"
POLICY_BALANCED: PrecisionPolicyName = "balanced"
POLICY_STRICT: PrecisionPolicyName = "strict"
VALID_PRECISION_POLICIES: tuple[PrecisionPolicyName, ...] = (
    POLICY_FAST,
    POLICY_BALANCED,
    POLICY_STRICT,
)
DEFAULT_PRECISION_POLICY: PrecisionPolicyName = POLICY_BALANCED

OP_LUT_2D_MITCHELL = "lut_2d_mitchell"
OP_GAMUT_JZAZBZ = "gamut_jzazbz"
OP_SPECTRAL_REDUCTION = "spectral_reduction"
OP_RGB_XYZ_MATRIX = "rgb_xyz_matrix"
OP_CCTF = "cctf"
OP_HDR_GAIN_MAP = "hdr_gain_map"

VALID_OPERATIONS = {
    OP_LUT_2D_MITCHELL,
    OP_GAMUT_JZAZBZ,
    OP_SPECTRAL_REDUCTION,
    OP_RGB_XYZ_MATRIX,
    OP_CCTF,
    OP_HDR_GAIN_MAP,
}


@dataclass(frozen=True, slots=True)
class PrecisionDecision:
    operation: str
    policy: PrecisionPolicyName
    allow_gpu: bool
    fallback_to_cpu: bool
    l1_compliant_claim: bool
    status: str
    reason: str
    max_abs_budget: float | None = None
    mean_abs_budget: float | None = None
    psnr_budget_db: float | None = None

    @property
    def is_exception(self) -> bool:
        return self.status == "exception"


def normalize_precision_policy(value: str | None) -> PrecisionPolicyName:
    policy = DEFAULT_PRECISION_POLICY if value is None else str(value).strip().lower()
    if policy not in VALID_PRECISION_POLICIES:
        allowed = ", ".join(VALID_PRECISION_POLICIES)
        raise ValueError(f"color_precision_policy must be one of: {allowed}")
    return policy  # type: ignore[return-value]


def _normalize_operation(operation: str) -> str:
    op = str(operation).strip().lower()
    if op not in VALID_OPERATIONS:
        allowed = ", ".join(sorted(VALID_OPERATIONS))
        raise ValueError(f"Unknown precision operation {operation!r}; expected one of: {allowed}")
    return op


def _normalize_backend_name_for_policy(backend_name: str | None) -> str:
    backend = "cpu" if backend_name is None else str(backend_name).strip().lower()
    if backend in {"none", ""}:
        return "cpu"
    return backend


def precision_decision(
    operation: str,
    *,
    policy: str | None = None,
    backend_name: str | None = "mlx",
    gpu_precision: str | None = "float32",
) -> PrecisionDecision:
    op = _normalize_operation(operation)
    resolved_policy = normalize_precision_policy(policy)
    backend = _normalize_backend_name_for_policy(backend_name)
    precision = "float32" if gpu_precision is None else str(gpu_precision).strip().lower()
    is_gpu = backend in {"mlx", "cupy", "cuda", "halide"}
    is_float32_gpu = is_gpu and precision == "float32"

    if not is_gpu:
        return PrecisionDecision(
            operation=op,
            policy=resolved_policy,
            allow_gpu=False,
            fallback_to_cpu=True,
            l1_compliant_claim=True,
            status="compliant",
            reason="CPU/reference path is used for non-float32-GPU execution.",
            max_abs_budget=1e-12,
            mean_abs_budget=1e-13,
        )

    if not is_float32_gpu:
        return PrecisionDecision(
            operation=op,
            policy=resolved_policy,
            allow_gpu=True,
            fallback_to_cpu=False,
            l1_compliant_claim=False,
            status="conditional",
            reason=(
                "This governance surface targets GPU float32; other GPU "
                "precisions are conditional and must not claim L1 parity."
            ),
            max_abs_budget=None,
            mean_abs_budget=None,
        )

    if op == OP_LUT_2D_MITCHELL:
        if resolved_policy == POLICY_FAST:
            return PrecisionDecision(
                operation=op,
                policy=resolved_policy,
                allow_gpu=True,
                fallback_to_cpu=False,
                l1_compliant_claim=False,
                status="exception",
                reason=(
                    "2D Mitchell LUT is a documented MLX float32 L1 exception; "
                    "fast mode preserves backend residency."
                ),
                max_abs_budget=2e-5,
                mean_abs_budget=2e-6,
                psnr_budget_db=90.0,
            )
        return PrecisionDecision(
            operation=op,
            policy=resolved_policy,
            allow_gpu=False,
            fallback_to_cpu=True,
            l1_compliant_claim=True,
            status="fallback",
            reason=(
                "2D Mitchell LUT is non-compliant at L1 on the resident GPU path; "
                f"{resolved_policy} mode uses the CPU float64 reference."
            ),
            max_abs_budget=1e-6 if resolved_policy == POLICY_STRICT else 2e-5,
            mean_abs_budget=2e-7 if resolved_policy == POLICY_STRICT else 2e-6,
            psnr_budget_db=100.0 if resolved_policy == POLICY_STRICT else 90.0,
        )

    if op == OP_GAMUT_JZAZBZ:
        if resolved_policy == POLICY_STRICT:
            return PrecisionDecision(
                operation=op,
                policy=resolved_policy,
                allow_gpu=False,
                fallback_to_cpu=True,
                l1_compliant_claim=True,
                status="fallback",
                reason=(
                    "JzAzBz gamut compression has a structural float32/Metal "
                    "precision floor; strict mode uses the CPU float64 reference."
                ),
                max_abs_budget=1e-6,
                mean_abs_budget=2e-7,
                psnr_budget_db=100.0,
            )
        return PrecisionDecision(
            operation=op,
            policy=resolved_policy,
            allow_gpu=True,
            fallback_to_cpu=False,
            l1_compliant_claim=False,
            status="exception",
            reason=(
                "JzAzBz resident GPU compression is kept for residency, but it "
                "must not be claimed as L1-compliant CPU-float64 parity."
            ),
            max_abs_budget=1.5e-4,
            mean_abs_budget=2e-5,
            psnr_budget_db=75.0,
        )

    if op == OP_SPECTRAL_REDUCTION:
        if resolved_policy == POLICY_STRICT:
            return PrecisionDecision(
                operation=op,
                policy=resolved_policy,
                allow_gpu=False,
                fallback_to_cpu=True,
                l1_compliant_claim=True,
                status="fallback",
                reason=(
                    "Strict spectral reductions require CPU float64 accumulation "
                    "unless a same-order compensated GPU kernel is selected."
                ),
                max_abs_budget=1e-6,
                mean_abs_budget=2e-7,
                psnr_budget_db=100.0,
            )
        return PrecisionDecision(
            operation=op,
            policy=resolved_policy,
            allow_gpu=True,
            fallback_to_cpu=False,
            l1_compliant_claim=False,
            status="conditional",
            reason=(
                "Float32 spectral reductions are conditionally accepted under "
                "budget tests and audit metrics, not bit-identical float64 parity."
            ),
            max_abs_budget=5e-5,
            mean_abs_budget=5e-6,
            psnr_budget_db=85.0,
        )

    if op in {OP_RGB_XYZ_MATRIX, OP_CCTF}:
        return PrecisionDecision(
            operation=op,
            policy=resolved_policy,
            allow_gpu=True,
            fallback_to_cpu=False,
            l1_compliant_claim=True,
            status="compliant",
            reason=(
                "CPU float64 constants are precomputed, then uploaded to the "
                "float32 backend with explicit branch thresholds/no-op semantics."
            ),
            max_abs_budget=1e-6,
            mean_abs_budget=2e-7,
            psnr_budget_db=100.0,
        )

    if op == OP_HDR_GAIN_MAP:
        return PrecisionDecision(
            operation=op,
            policy=resolved_policy,
            allow_gpu=True,
            fallback_to_cpu=False,
            l1_compliant_claim=resolved_policy != POLICY_STRICT,
            status="conditional",
            reason=(
                "HDR/gain-map float32 operations remain governed by existing HDR "
                "tests; this policy does not change projection/export semantics."
            ),
            max_abs_budget=5e-5,
            mean_abs_budget=5e-6,
            psnr_budget_db=85.0,
        )

    raise AssertionError(f"Unhandled precision operation: {op}")


def should_fallback_to_cpu(operation: str, **kwargs: Any) -> bool:
    return precision_decision(operation, **kwargs).fallback_to_cpu


def documented_precision_exceptions(
    *,
    policy: str | None = None,
    backend_name: str | None = "mlx",
    gpu_precision: str | None = "float32",
) -> list[PrecisionDecision]:
    return [
        decision
        for operation in sorted(VALID_OPERATIONS)
        if (
            decision := precision_decision(
                operation,
                policy=policy,
                backend_name=backend_name,
                gpu_precision=gpu_precision,
            )
        ).is_exception
    ]


def precision_metrics(
    reference: Any,
    candidate: Any,
    *,
    data_range: float | None = None,
    luminance_weights: tuple[float, float, float] | None = (0.2126, 0.7152, 0.0722),
) -> dict[str, float]:
    ref = np.asarray(reference, dtype=np.float64)
    got = np.asarray(candidate, dtype=np.float64)
    if ref.shape != got.shape:
        raise ValueError(f"reference and candidate shapes differ: {ref.shape} != {got.shape}")

    diff = got - ref
    abs_diff = np.abs(diff)
    finite = np.isfinite(ref) & np.isfinite(got)
    if not np.all(finite):
        ref = np.where(finite, ref, 0.0)
        got = np.where(finite, got, 0.0)
        diff = got - ref
        abs_diff = np.abs(diff)

    denom = np.maximum(np.abs(ref), 1e-12)
    rel = abs_diff / denom
    mse = float(np.mean(diff * diff)) if diff.size else 0.0
    rmse = float(np.sqrt(mse))
    if data_range is None:
        ref_range = float(np.nanmax(ref) - np.nanmin(ref)) if ref.size else 1.0
        data_range = max(ref_range, 1.0)
    psnr = float("inf") if mse == 0.0 else float(20.0 * log10(float(data_range)) - 10.0 * log10(mse))

    metrics = {
        "max_abs": float(np.max(abs_diff)) if abs_diff.size else 0.0,
        "mean_abs": float(np.mean(abs_diff)) if abs_diff.size else 0.0,
        "max_rel": float(np.max(rel)) if rel.size else 0.0,
        "mean_rel": float(np.mean(rel)) if rel.size else 0.0,
        "rmse": rmse,
        "psnr_db": psnr,
    }

    if luminance_weights is not None and ref.ndim >= 1 and ref.shape[-1] == 3:
        weights = np.asarray(luminance_weights, dtype=np.float64)
        ref_y = np.tensordot(ref, weights, axes=([-1], [0]))
        got_y = np.tensordot(got, weights, axes=([-1], [0]))
        y_abs = np.abs(got_y - ref_y)
        metrics["max_luminance_abs"] = float(np.max(y_abs)) if y_abs.size else 0.0
        metrics["mean_luminance_abs"] = float(np.mean(y_abs)) if y_abs.size else 0.0

    return metrics
