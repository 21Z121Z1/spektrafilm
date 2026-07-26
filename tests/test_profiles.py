import json
import numpy as np
import pytest
import ast
import inspect

from spektrafilm.model import stocks
from spektrafilm.profiles.io import (
    PROFILE_PROVENANCE_FIELDS,
    Profile,
    ProfileData,
    ProfileFieldProvenance,
    ProfileProvenance,
    _json_safe,
    list_profiles,
    load_profile,
    profile_to_dict,
    profile_from_dict,
    save_profile,
)


class TestLoadProfile:
    def test_profile_has_required_fields(self, portra_400_profile):
        p = portra_400_profile
        assert hasattr(p.metadata, 'provenance')
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
        assert (
            profile_to_dict(profile_rt.metadata.provenance)
            == profile_to_dict(portra_400_profile.metadata.provenance)
        )

    def test_legacy_profile_without_provenance_remains_loadable(self, portra_400_profile):
        profile_dict = profile_to_dict(portra_400_profile)
        profile_dict['metadata'].pop('provenance')

        profile_rt = profile_from_dict(profile_dict)

        assert profile_rt.metadata.provenance.measurement_status == 'unknown'
        assert profile_rt.metadata.provenance.fields == {}

    def test_field_provenance_rejects_unknown_origin(self):
        with pytest.raises(ValueError, match='origin'):
            ProfileFieldProvenance(origin='manufacturer-direct')

    def test_profile_provenance_rejects_undefined_source_reference(self):
        with pytest.raises(ValueError, match='undefined sources'):
            ProfileProvenance(fields={
                'channel_density': {
                    'origin': 'generic-reference',
                    'status': 'reconstructed',
                    'sources': ['MISSING_SOURCE'],
                },
            })

    def test_instrument_measured_field_requires_retained_measurement_status(self):
        with pytest.raises(ValueError, match='retained or partial instrument data'):
            ProfileProvenance(fields={
                'channel_density': {
                    'origin': 'instrument-measurement',
                    'status': 'instrument-measured',
                },
            })

    def test_all_bundled_profiles_have_complete_field_provenance(self):
        for stock in list_profiles():
            provenance = load_profile(stock).metadata.provenance

            assert provenance.measurement_status == 'no-raw-instrument-data', stock
            assert set(provenance.fields) == PROFILE_PROVENANCE_FIELDS, stock
            assert all(
                field.status != 'instrument-measured'
                for field in provenance.fields.values()
            ), stock

    @pytest.mark.parametrize(
        'stock',
        [
            'fujifilm_c200',
            'fujifilm_pro_400h',
            'fujifilm_xtra_400',
            'kodak_ektar_100',
            'kodak_gold_200',
            'kodak_portra_160',
            'kodak_portra_400',
            'kodak_portra_800',
            'kodak_ultramax_400',
        ],
    )
    def test_generic_negative_cmy_basis_is_labeled_as_reconstruction(self, stock):
        provenance = load_profile(stock).metadata.provenance.fields['channel_density']

        assert provenance.origin == 'generic-reference'
        assert provenance.status == 'reconstructed'
        assert 'DIGITAL_COLOR_MANAGEMENT_FILM_A' in provenance.sources

    @pytest.mark.parametrize(
        ('stock', 'source_id'),
        [
            (
                'fujifilm_velvia_100',
                'AVIAN_ROCHESTER_MICROCALT24_VELVIA100',
            ),
            ('kodak_kodachrome_64', 'SCARPACE_FRIEDERICHS_1978_K64'),
            ('kodak_gold_200', 'WANG_ET_AL_2014_GOLD_200'),
            ('kodak_vision3_500t', 'PLUTINO_ET_AL_2024_VISION3_500T'),
        ],
    )
    def test_validation_only_references_do_not_claim_field_derivation(
        self,
        stock,
        source_id,
    ):
        provenance = load_profile(stock).metadata.provenance

        assert source_id in provenance.source_references
        assert all(
            source_id not in field.sources
            for field in provenance.fields.values()
        )

    @pytest.mark.parametrize('stock', ['kodak_portra_800_push1', 'kodak_portra_800_push2'])
    def test_push_profile_spectral_fields_are_labeled_as_inherited(self, stock):
        fields = load_profile(stock).metadata.provenance.fields

        for field_name in (
            'log_sensitivity',
            'channel_density',
            'base_density',
            'midscale_neutral_density',
        ):
            field = fields[field_name]
            assert field.origin == 'related-profile'
            assert field.status == 'inherited'
            assert field.derived_from == f'kodak_portra_800.data.{field_name}'

    def test_cross_profile_donors_are_labeled_explicitly(self):
        verita = load_profile('kodak_verita_200d').metadata.provenance.fields
        crystal = load_profile(
            'fujifilm_crystal_archive_typeii'
        ).metadata.provenance.fields
        supra = load_profile('kodak_supra_endura').metadata.provenance.fields

        assert verita['channel_density'].derived_from == (
            'kodak_vision3_50d.data.channel_density'
        )
        assert crystal['density_curves'].derived_from == (
            'kodak_supra_endura.data.density_curves'
        )
        assert supra['log_sensitivity'].derived_from == (
            'kodak_portra_endura.data.log_sensitivity'
        )
        assert supra['channel_density'].derived_from == (
            'kodak_portra_endura.data.channel_density'
        )

    def test_normalized_and_reduced_source_graphs_keep_semantic_caveats(self):
        pro_400h = load_profile('fujifilm_pro_400h').metadata.provenance.fields
        assert pro_400h['log_sensitivity'].status == 'reconstructed'
        assert 'three-channel-reduction' in pro_400h['log_sensitivity'].transformations

        for stock in (
            'kodak_vision3_50d',
            'kodak_vision3_250d',
            'kodak_vision3_200t',
            'kodak_vision3_500t',
        ):
            channel = load_profile(stock).metadata.provenance.fields['channel_density']
            assert channel.status == 'reconstructed'
            assert 'peak-normalized' in channel.notes

        for stock in ('kodak_ektachrome_100', 'kodak_kodachrome_64'):
            channel = load_profile(stock).metadata.provenance.fields['channel_density']
            assert channel.status == 'source-derived'
            assert 'visual neutral' in channel.notes

    def test_positive_and_printing_base_neutral_fields_are_labeled_reconstructed(self):
        for stock in list_profiles():
            profile = load_profile(stock)
            if profile.info.type != 'positive' and profile.info.stage != 'printing':
                continue

            fields = profile.metadata.provenance.fields
            assert fields['base_density'].status == 'reconstructed', stock
            assert fields['midscale_neutral_density'].status == 'reconstructed', stock

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
