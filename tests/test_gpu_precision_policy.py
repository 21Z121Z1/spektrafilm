from __future__ import annotations

import pytest

from spektrafilm.gpu.precision_policy import (
    DEFAULT_PRECISION_POLICY,
    OP_CCTF,
    OP_GAMUT_JZAZBZ,
    OP_HDR_GAIN_MAP,
    OP_LUT_2D_MITCHELL,
    OP_RGB_XYZ_MATRIX,
    OP_SPECTRAL_REDUCTION,
    documented_precision_exceptions,
    normalize_precision_policy,
    precision_decision,
    precision_metrics,
    should_fallback_to_cpu,
)
from spektrafilm.runtime.params_schema import RuntimePhotoParams, SettingsParams
from spektrafilm.profiles.io import load_profile


pytestmark = pytest.mark.unit


def test_normalize_precision_policy_accepts_expected_names() -> None:
    assert normalize_precision_policy(None) == DEFAULT_PRECISION_POLICY
    assert normalize_precision_policy("FAST") == "fast"
    assert normalize_precision_policy(" balanced ") == "balanced"
    assert normalize_precision_policy("strict") == "strict"


def test_normalize_precision_policy_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="color_precision_policy"):
        normalize_precision_policy("exact")


def test_runtime_params_validate_color_precision_policy() -> None:
    params = RuntimePhotoParams(
        film=load_profile("kodak_portra_400"),
        print=load_profile("kodak_endura_premier"),
    )
    params.settings.color_precision_policy = "strict"
    params.__post_init__()

    params.settings.color_precision_policy = "exact"
    with pytest.raises(ValueError, match="color_precision_policy"):
        params.__post_init__()


def test_settings_default_precision_policy_is_balanced() -> None:
    assert SettingsParams().color_precision_policy == "balanced"


@pytest.mark.parametrize(
    "operation",
    [OP_RGB_XYZ_MATRIX, OP_CCTF],
)
def test_rgb_xyz_and_cctf_are_l1_claimed_for_float32_gpu(operation: str) -> None:
    decision = precision_decision(operation, policy="balanced", backend_name="mlx", gpu_precision="float32")

    assert decision.allow_gpu is True
    assert decision.fallback_to_cpu is False
    assert decision.l1_compliant_claim is True
    assert decision.status == "compliant"


def test_lut_2d_mitchell_decision_matrix() -> None:
    fast = precision_decision(OP_LUT_2D_MITCHELL, policy="fast", backend_name="mlx")
    balanced = precision_decision(OP_LUT_2D_MITCHELL, policy="balanced", backend_name="mlx")
    strict = precision_decision(OP_LUT_2D_MITCHELL, policy="strict", backend_name="mlx")

    assert fast.allow_gpu is True
    assert fast.l1_compliant_claim is False
    assert fast.status == "exception"
    assert balanced.fallback_to_cpu is True
    assert balanced.status == "fallback"
    assert strict.fallback_to_cpu is True
    assert strict.status == "fallback"


def test_jzazbz_decision_matrix_does_not_claim_l1_except_strict_fallback() -> None:
    fast = precision_decision(OP_GAMUT_JZAZBZ, policy="fast", backend_name="mlx")
    balanced = precision_decision(OP_GAMUT_JZAZBZ, policy="balanced", backend_name="mlx")
    strict = precision_decision(OP_GAMUT_JZAZBZ, policy="strict", backend_name="mlx")

    assert fast.allow_gpu is True
    assert fast.l1_compliant_claim is False
    assert fast.status == "exception"
    assert balanced.allow_gpu is True
    assert balanced.l1_compliant_claim is False
    assert balanced.status == "exception"
    assert strict.fallback_to_cpu is True
    assert strict.l1_compliant_claim is True


def test_spectral_reduction_is_conditional_until_strict_fallback() -> None:
    balanced = precision_decision(OP_SPECTRAL_REDUCTION, policy="balanced", backend_name="mlx")
    strict = precision_decision(OP_SPECTRAL_REDUCTION, policy="strict", backend_name="mlx")

    assert balanced.allow_gpu is True
    assert balanced.status == "conditional"
    assert balanced.l1_compliant_claim is False
    assert strict.fallback_to_cpu is True
    assert should_fallback_to_cpu(OP_SPECTRAL_REDUCTION, policy="strict", backend_name="mlx")


def test_hdr_gain_map_policy_is_conditional_and_non_destructive() -> None:
    decision = precision_decision(OP_HDR_GAIN_MAP, policy="balanced", backend_name="mlx")

    assert decision.allow_gpu is True
    assert decision.status == "conditional"
    assert decision.fallback_to_cpu is False


def test_documented_precision_exceptions_surface_fast_and_balanced_risks() -> None:
    fast_ops = {decision.operation for decision in documented_precision_exceptions(policy="fast")}
    balanced_ops = {decision.operation for decision in documented_precision_exceptions(policy="balanced")}
    strict_ops = {decision.operation for decision in documented_precision_exceptions(policy="strict")}

    assert OP_LUT_2D_MITCHELL in fast_ops
    assert OP_GAMUT_JZAZBZ in fast_ops
    assert OP_LUT_2D_MITCHELL not in balanced_ops
    assert OP_GAMUT_JZAZBZ in balanced_ops
    assert OP_GAMUT_JZAZBZ not in strict_ops


def test_precision_metrics_reports_expected_fields() -> None:
    metrics = precision_metrics([0.0, 0.5, 1.0], [0.0, 0.5, 1.001], data_range=1.0)

    assert metrics["max_abs"] == pytest.approx(0.001)
    assert metrics["mean_abs"] == pytest.approx(0.001 / 3.0)
    assert metrics["psnr_db"] > 50.0
