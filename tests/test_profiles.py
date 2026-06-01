import json
import numpy as np
import pytest
import ast
import inspect

from spektrafilm.model import stocks
from spektrafilm.profiles.io import (
    Profile,
    ProfileData,
    _json_safe,
    load_profile,
    profile_to_dict,
    profile_from_dict,
    save_profile,
)


class TestLoadProfile:
    def test_profile_has_required_fields(self, portra_400_profile):
        p = portra_400_profile
        assert hasattr(p, 'info')
        assert hasattr(p, 'data')
        assert hasattr(p.data, 'log_sensitivity')
        assert hasattr(p.data, 'hanatos2025_adaptation_window_params')
        assert hasattr(p.data, 'hanatos2025_adaptation_surface_params')
        assert hasattr(p.data, 'density_curves')
        assert hasattr(p.data, 'channel_density')
        assert hasattr(p.data, 'base_density')
        assert hasattr(p.data, 'midscale_neutral_density')
        assert hasattr(p.data, 'log_exposure')
        assert hasattr(p.data, 'wavelengths')

    @pytest.mark.parametrize(
        'stock',
        [
            'kodak_portra_400',
            'fujifilm_c200',
            'kodak_portra_endura',
        ],
    )
    def test_profile_data_shapes_are_consistent(self, stock):
        profile = load_profile(stock)

        assert profile.data.log_exposure.ndim == 1
        assert profile.data.density_curves.ndim == 2
        assert profile.data.density_curves.shape[1] == 3
        assert profile.data.density_curves.shape[0] == profile.data.log_exposure.shape[0]

        assert profile.data.log_sensitivity.ndim == 2
        assert profile.data.log_sensitivity.shape[1] == 3
        assert profile.data.hanatos2025_adaptation_window_params.ndim == 1
        assert profile.data.hanatos2025_adaptation_surface_params.ndim == 2
        assert (
            profile.data.hanatos2025_adaptation_surface_params.size == 0
            or profile.data.hanatos2025_adaptation_surface_params.shape[0] == 3
        )

        assert profile.data.wavelengths.ndim == 1
        assert profile.data.channel_density.ndim == 2
        assert profile.data.channel_density.shape[0] == profile.data.wavelengths.shape[0]
        assert profile.data.channel_density.shape[1] == 3
        assert profile.data.base_density.ndim == 1
        assert profile.data.base_density.shape[0] == profile.data.wavelengths.shape[0]
        assert profile.data.midscale_neutral_density.ndim == 1
        assert profile.data.midscale_neutral_density.shape[0] == profile.data.wavelengths.shape[0]

    def test_profile_namespace_round_trip_preserves_core_fields(self, portra_400_profile):
        profile_dict = profile_to_dict(portra_400_profile)
        profile_rt = profile_from_dict(profile_dict)

        assert profile_rt.info.stock == portra_400_profile.info.stock
        assert np.array(profile_rt.data.log_exposure).shape == portra_400_profile.data.log_exposure.shape
        assert np.array(profile_rt.data.density_curves).shape == portra_400_profile.data.density_curves.shape
        assert (
            np.array(profile_rt.data.hanatos2025_adaptation_window_params).shape
            == portra_400_profile.data.hanatos2025_adaptation_window_params.shape
        )
        assert (
            np.array(profile_rt.data.hanatos2025_adaptation_surface_params).shape
            == portra_400_profile.data.hanatos2025_adaptation_surface_params.shape
        )

    def test_profile_json_payload_converts_nan_to_null(self, portra_400_profile):
        profile = portra_400_profile.clone()
        profile.data.log_sensitivity[0, 0] = np.nan

        payload = json.dumps(_json_safe(profile_to_dict(profile)), allow_nan=False)

        assert 'null' in payload

    def test_profile_json_round_trip_preserves_hanatos2025_adaptation(self, portra_400_profile):
        payload = json.dumps(_json_safe(profile_to_dict(portra_400_profile)), allow_nan=False)

        profile_rt = profile_from_dict(json.loads(payload))

        np.testing.assert_allclose(
            profile_rt.data.hanatos2025_adaptation_window_params,
            portra_400_profile.data.hanatos2025_adaptation_window_params,
        )
        np.testing.assert_allclose(
            profile_rt.data.hanatos2025_adaptation_surface_params,
            portra_400_profile.data.hanatos2025_adaptation_surface_params,
        )

    def test_profile_constructor_rejects_dict_payloads(self):
        with pytest.raises(TypeError, match='ProfileInfo'):
            Profile(info={}, data={})

    def test_profile_from_dict_ignores_extra_unknown_keys(self, portra_400_profile):
        profile_dict = profile_to_dict(portra_400_profile)
        # Inject unknown keys that a future version might add
        profile_dict['metadata']['future_field'] = 'should be ignored'
        profile_dict['info']['new_option'] = 42
        profile_dict['data']['experimental_array'] = [1, 2, 3]

        profile_rt = profile_from_dict(profile_dict)

        assert profile_rt.info.stock == portra_400_profile.info.stock
        np.testing.assert_allclose(
            profile_rt.data.density_curves,
            portra_400_profile.data.density_curves,
        )

    def test_load_profile_rejects_path_traversal_stock_name(self):
        with pytest.raises(ValueError, match="Invalid profile stock"):
            load_profile("../kodak_portra_400")

    def test_save_profile_rejects_path_traversal_stock_name(self, portra_400_profile, monkeypatch):
        class GuardedPackage:
            def __truediv__(self, _filename):
                raise AssertionError("save_profile constructed a resource path before validating stock")

        profile = portra_400_profile.clone()
        profile.info.stock = "../evil"
        monkeypatch.setattr("spektrafilm.profiles.io.pkg_resources.files", lambda _package: GuardedPackage())

        with pytest.raises(ValueError, match="Invalid profile stock"):
            save_profile(profile)

    def test_profile_data_rejects_density_curves_with_wrong_channel_count(self):
        with pytest.raises(ValueError, match="density_curves"):
            ProfileData(
                log_exposure=np.array([0.0, 1.0]),
                density_curves=np.zeros((2, 4)),
            )

    def test_profile_data_rejects_non_finite_density_curves(self):
        with pytest.raises(ValueError, match="density_curves"):
            ProfileData(
                log_exposure=np.array([0.0, 1.0]),
                density_curves=np.array([[0.0, 0.1, 0.2], [np.inf, 0.2, 0.3]]),
            )

    def test_profile_data_allows_nan_channel_density_gaps(self):
        data = ProfileData(
            wavelengths=np.array([450.0, 550.0]),
            channel_density=np.array([[np.nan, np.nan, np.nan], [0.1, 0.2, 0.3]]),
        )

        assert np.isnan(data.channel_density[0]).all()

    def test_profile_data_rejects_infinite_channel_density(self):
        with pytest.raises(ValueError, match="channel_density"):
            ProfileData(
                wavelengths=np.array([450.0, 550.0]),
                channel_density=np.array([[0.1, 0.2, 0.3], [np.inf, 0.4, 0.5]]),
            )

    def test_profile_data_rejects_log_sensitivity_with_wrong_channel_count(self):
        with pytest.raises(ValueError, match="log_sensitivity"):
            ProfileData(log_sensitivity=np.zeros((3, 2)))

    def test_profile_data_rejects_wavelength_length_mismatch(self):
        with pytest.raises(ValueError, match="channel_density"):
            ProfileData(
                wavelengths=np.array([450.0, 550.0]),
                channel_density=np.zeros((3, 3)),
            )

    def test_profile_data_rejects_log_exposure_density_curve_length_mismatch(self):
        with pytest.raises(ValueError, match="log_exposure"):
            ProfileData(
                log_exposure=np.array([0.0]),
                density_curves=np.zeros((2, 3)),
            )

    def test_profile_clone_is_deep_copy(self, portra_400_profile):
        clone = portra_400_profile.clone()

        clone.data.log_exposure[0] += 1

        assert clone is not portra_400_profile
        assert clone.data is not portra_400_profile.data
        assert clone.info is not portra_400_profile.info
        assert clone.data.log_exposure[0] != portra_400_profile.data.log_exposure[0]

    def test_profile_update_helpers_replace_nested_dataclasses(self, portra_400_profile):
        original_data = portra_400_profile.data
        original_info = portra_400_profile.info
        updated_density = np.asarray(portra_400_profile.data.channel_density) * 0.5

        returned = portra_400_profile.update(
            info={'name': 'updated-name'},
            data={'channel_density': updated_density},
        )

        assert returned is portra_400_profile
        assert portra_400_profile.info is not original_info
        assert portra_400_profile.data is not original_data
        assert portra_400_profile.info.name == 'updated-name'
        np.testing.assert_allclose(portra_400_profile.data.channel_density, updated_density)


class TestDependencyBoundaries:
    def test_stocks_module_has_no_top_level_process_import(self):
        tree = ast.parse(inspect.getsource(stocks))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                assert node.module != 'spektrafilm.runtime.process'

    def test_stocks_module_has_no_main_script_block(self):
        tree = ast.parse(inspect.getsource(stocks))
        for node in tree.body:
            assert not isinstance(node, ast.If)

