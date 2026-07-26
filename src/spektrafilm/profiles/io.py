import copy
from datetime import date
import importlib.resources as pkg_resources
import json
import re
from dataclasses import dataclass, field, is_dataclass, replace
from typing import Any, Mapping

import numpy as np


_PROJECT_URL = 'https://github.com/andreavolpato/spektrafilm'
_PROFILE_LICENSE_URL = f'{_PROJECT_URL}/blob/main/SPEKTRAFILM_LICENSE.txt'


PROFILE_TYPES = frozenset({'negative', 'positive'})
PROFILE_SUPPORTS = frozenset({'film', 'paper'})
PROFILE_STAGES = frozenset({'filming', 'printing'})
PROFILE_USES = frozenset({'still', 'cine'})
PROFILE_ANTIHALATION = frozenset({'strong', 'weak', 'no'})
PROFILE_CHANNEL_MODELS = frozenset({'color', 'bw'})
PROFILE_PROVENANCE_SCHEMA_VERSION = 1
PROFILE_PROVENANCE_ORIGINS = frozenset({
    'generated',
    'generic-reference',
    'instrument-measurement',
    'manufacturer-composite-graph',
    'manufacturer-graph',
    'published-measurement',
    'related-profile',
})
PROFILE_PROVENANCE_STATUSES = frozenset({
    'generated',
    'inherited',
    'instrument-measured',
    'optimized',
    'reconstructed',
    'source-derived',
})
PROFILE_MEASUREMENT_STATUSES = frozenset({
    'instrument-raw-data-retained',
    'no-raw-instrument-data',
    'partial-instrument-data',
    'unknown',
})
PROFILE_PROVENANCE_FIELDS = frozenset({
    'wavelengths',
    'log_sensitivity',
    'bandpass_hanatos2025',
    'hanatos2025_adaptation_window_params',
    'hanatos2025_adaptation_surface_params',
    'channel_density',
    'base_density',
    'midscale_neutral_density',
    'log_exposure',
    'density_curves',
    'density_curves_layers',
    'density_curves_model',
})
LEGACY_PROFILE_INFO_KEYS = frozenset({
    'fitted_cmy_midscale_neutral_density',
    'log_exposure_midscale_neutral',
})
_SAFE_PROFILE_STOCK_RE = re.compile(r'^[A-Za-z0-9_-]+$')


def _package_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version as distribution_version

        return distribution_version('spektrafilm')
    except PackageNotFoundError:
        return '0+unknown'

def _created_date() -> str:
    return date.today().isoformat()

def _copyright_statement() -> str:
    return f"Copyright (c) {date.today().year} Andrea Volpato. Licensed under CC BY-SA 4.0."

def _empty_vector() -> np.ndarray:
    return np.empty((0,), dtype=float)

def _empty_matrix() -> np.ndarray:
    return np.empty((0, 3), dtype=float)

def _empty_tensor() -> np.ndarray:
    return np.empty((0, 3, 3), dtype=float)


def _empty_layer_matrix() -> np.ndarray:
    return np.empty((3, 0), dtype=float)


def _validate_profile_stock(stock: str, label: str = "profile stock") -> None:
    if not isinstance(stock, str) or not _SAFE_PROFILE_STOCK_RE.match(stock):
        raise ValueError(
            f"Invalid {label} {stock!r}: must contain only letters, digits, hyphens, and underscores."
        )


def _validate_finite_array(name: str, value: np.ndarray) -> None:
    if value.size and not np.all(np.isfinite(value)):
        raise ValueError(f"{name} must contain only finite values")


def _validate_no_infinite_array(name: str, value: np.ndarray) -> None:
    if value.size and np.any(np.isinf(value)):
        raise ValueError(f"{name} must not contain infinite values")


def _validate_2d_three_columns(name: str, value: np.ndarray, *, allow_nan: bool = False) -> None:
    if value.size and (value.ndim != 2 or value.shape[1] != 3):
        raise ValueError(f"{name} must have shape (n, 3)")
    if allow_nan:
        _validate_no_infinite_array(name, value)
    else:
        _validate_finite_array(name, value)


def _validate_1d(name: str, value: np.ndarray, *, allow_nan: bool = False) -> None:
    if value.size and value.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if allow_nan:
        _validate_no_infinite_array(name, value)
    else:
        _validate_finite_array(name, value)


def _validate_matching_length(name: str, value: np.ndarray, other_name: str, other: np.ndarray) -> None:
    if value.size and other.size and value.shape[0] != other.shape[0]:
        raise ValueError(f"{name} length must match {other_name} length")


@dataclass
class DensityCurvesModel:
    """Parametric model of the density curves.

    `centers`, `amplitudes`, `sigmas` are 2D arrays shaped (n_channels, n_layers).
    n_layers can be 2, 3, ... — set by the array shape.
    """
    model_type: str = 'cdfs'
    centers: np.ndarray = field(default_factory=_empty_layer_matrix)
    amplitudes: np.ndarray = field(default_factory=_empty_layer_matrix)
    sigmas: np.ndarray = field(default_factory=_empty_layer_matrix)

    def __post_init__(self):
        self.centers = np.asarray(self.centers, dtype=float)
        self.amplitudes = np.asarray(self.amplitudes, dtype=float)
        self.sigmas = np.asarray(self.sigmas, dtype=float)

    @property
    def n_channels(self) -> int:
        return self.centers.shape[0] if self.centers.ndim == 2 else 0

    @property
    def n_layers(self) -> int:
        return self.centers.shape[1] if self.centers.ndim == 2 else 0


@dataclass
class ProfileFieldProvenance:
    """Provenance of one final bundled profile field.

    ``origin`` describes the starting evidence while ``status`` describes the
    current array after profile-creator processing. Keeping these separate
    prevents a digitized manufacturer graph from being mistaken for retained
    raw instrument measurements or an untouched runtime array.
    """

    origin: str = 'generated'
    status: str = 'generated'
    sources: tuple[str, ...] = ()
    derived_from: str | None = None
    transformations: tuple[str, ...] = ()
    notes: str = ''

    def __post_init__(self) -> None:
        if not isinstance(self.origin, str) or self.origin not in PROFILE_PROVENANCE_ORIGINS:
            raise ValueError(f'Unsupported profile provenance origin: {self.origin!r}')
        if not isinstance(self.status, str) or self.status not in PROFILE_PROVENANCE_STATUSES:
            raise ValueError(f'Unsupported profile provenance status: {self.status!r}')
        if isinstance(self.sources, str):
            raise TypeError('Profile provenance sources must be a sequence of source identifiers')
        if isinstance(self.transformations, str):
            raise TypeError('Profile provenance transformations must be a sequence of labels')
        self.sources = tuple(self.sources)
        self.transformations = tuple(self.transformations)
        if not all(isinstance(value, str) and value for value in self.sources):
            raise ValueError('Profile provenance source identifiers must be non-empty strings')
        if not all(isinstance(value, str) and value for value in self.transformations):
            raise ValueError('Profile provenance transformation labels must be non-empty strings')
        if len(set(self.sources)) != len(self.sources):
            raise ValueError('Profile provenance sources must not contain duplicates')
        if len(set(self.transformations)) != len(self.transformations):
            raise ValueError('Profile provenance transformations must not contain duplicates')
        if self.derived_from is not None and (
            not isinstance(self.derived_from, str) or not self.derived_from
        ):
            raise ValueError('Profile provenance derived_from must be a non-empty string or None')
        if not isinstance(self.notes, str):
            raise TypeError('Profile provenance notes must be a string')


@dataclass
class ProfileProvenance:
    """Versioned source and processing labels for a processed profile."""

    schema_version: int = PROFILE_PROVENANCE_SCHEMA_VERSION
    measurement_status: str = 'unknown'
    source_references: dict[str, str] = field(default_factory=dict)
    fields: dict[str, ProfileFieldProvenance] = field(default_factory=dict)
    notes: str = ''

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != PROFILE_PROVENANCE_SCHEMA_VERSION
        ):
            raise ValueError(
                'Unsupported profile provenance schema_version '
                f'{self.schema_version!r}'
            )
        if (
            not isinstance(self.measurement_status, str)
            or self.measurement_status not in PROFILE_MEASUREMENT_STATUSES
        ):
            raise ValueError(
                f'Unsupported profile measurement status: {self.measurement_status!r}'
            )
        if not isinstance(self.source_references, Mapping):
            raise TypeError('Profile provenance source_references must be a mapping')
        source_references = dict(self.source_references)
        if not all(
            isinstance(source_id, str)
            and source_id
            and isinstance(reference, str)
            and reference
            for source_id, reference in source_references.items()
        ):
            raise ValueError(
                'Profile provenance source_references must map non-empty strings '
                'to non-empty strings'
            )
        if not isinstance(self.fields, Mapping):
            raise TypeError('Profile provenance fields must be a mapping')

        normalized_fields: dict[str, ProfileFieldProvenance] = {}
        known_field_keys = ProfileFieldProvenance.__dataclass_fields__
        for field_name, field_provenance in self.fields.items():
            if field_name not in PROFILE_PROVENANCE_FIELDS:
                raise ValueError(f'Unsupported profile provenance field {field_name!r}')
            if isinstance(field_provenance, Mapping):
                field_provenance = ProfileFieldProvenance(**{
                    key: value
                    for key, value in field_provenance.items()
                    if key in known_field_keys
                })
            elif not isinstance(field_provenance, ProfileFieldProvenance):
                raise TypeError(
                    f'Provenance for {field_name!r} must be a mapping or '
                    'ProfileFieldProvenance'
                )
            missing_sources = set(field_provenance.sources) - set(source_references)
            if missing_sources:
                raise ValueError(
                    f'Profile provenance field {field_name!r} references undefined '
                    f'sources: {sorted(missing_sources)}'
                )
            if (
                field_provenance.status == 'instrument-measured'
                and field_provenance.origin != 'instrument-measurement'
            ):
                raise ValueError(
                    f'Instrument-measured provenance for {field_name!r} must use '
                    "origin='instrument-measurement'"
                )
            normalized_fields[field_name] = field_provenance
        has_instrument_measured_field = any(
            value.status == 'instrument-measured'
            for value in normalized_fields.values()
        )
        if has_instrument_measured_field and self.measurement_status not in {
            'instrument-raw-data-retained',
            'partial-instrument-data',
        }:
            raise ValueError(
                'instrument-measured fields require retained or partial instrument data'
            )
        if not isinstance(self.notes, str):
            raise TypeError('Profile provenance notes must be a string')
        self.source_references = source_references
        self.fields = normalized_fields


@dataclass
class ProfileMetadata:
    version: str = field(default_factory=_package_version)
    copyright: str = field(default_factory=_copyright_statement)
    created: str = field(default_factory=_created_date)
    license: str = (
        "spektrafilm profile by Andrea Volpato, licensed under CC BY-SA 4.0. "
        "Redistribution and derivatives must credit the author, link the "
        f"project ({_PROJECT_URL}),"
        "preserve this license, and remain CC BY-SA 4.0."
        "Modifications must be noted. Full text of the license and "
        f"attribution requirements: {_PROFILE_LICENSE_URL}."
    )
    citation: str = (
        "If you use this profile in your work, please cite the spektrafilm "
        f"project: {_PROJECT_URL}, see CITATION.cff for details."
    )
    datasource: str = (
        "This processed profile may combine digitized manufacturer graphs, scientific "
        "references, generic priors, related-profile donors, reconstructions, and runtime "
        "optimization. See metadata.provenance for each field's origin and final-array "
        "status. A published graph is not retained raw instrument data, and this profile "
        "must not be treated as an exact-roll measurement unless provenance explicitly "
        "states otherwise."
    )
    provenance: ProfileProvenance = field(default_factory=ProfileProvenance)

    def __post_init__(self) -> None:
        if isinstance(self.provenance, Mapping):
            known = ProfileProvenance.__dataclass_fields__
            self.provenance = ProfileProvenance(**{
                key: value
                for key, value in self.provenance.items()
                if key in known
            })
        elif not isinstance(self.provenance, ProfileProvenance):
            raise TypeError('provenance must be a ProfileProvenance or Mapping')

@dataclass
class ProfileInfo:
    stock: str = None
    name: str = None
    type: str = 'negative'
    support: str = 'film'
    stage: str = 'filming'
    use: str = 'still'
    antihalation: str = 'weak'
    target_print: str | None = None
    channel_model: str = 'color'
    densitometer: str = 'status_M'
    log_sensitivity_density_over_min: float = 0.2
    reference_illuminant: str = 'D55'
    viewing_illuminant: str = 'D50'

@dataclass
class Hanatos2025SensitivityAdaptation:
    window_params: np.ndarray = field(default_factory=_empty_vector)
    surface_params: np.ndarray = field(default_factory=_empty_vector)
    spectral_gaussian_blur: float = 0.0 # sigma in nm for gaussian blur of the spectra
    reference_illuminant: str = None # "D55" or "T"
    apply_window: bool = True
    apply_surface: bool = True
    active: bool = None

@dataclass
class ProfileData:
    wavelengths: np.ndarray = field(default_factory=_empty_vector)
    log_sensitivity: np.ndarray = field(default_factory=_empty_matrix)
    bandpass_hanatos2025: np.ndarray = field(default_factory=_empty_matrix)
    hanatos2025_adaptation_window_params: np.ndarray = field(default_factory=_empty_vector)
    hanatos2025_adaptation_surface_params: np.ndarray = field(default_factory=_empty_vector)
    channel_density: np.ndarray = field(default_factory=_empty_matrix)
    base_density: np.ndarray = field(default_factory=_empty_vector)
    midscale_neutral_density: np.ndarray = field(default_factory=_empty_vector)
    log_exposure: np.ndarray = field(default_factory=_empty_vector)
    density_curves: np.ndarray = field(default_factory=_empty_matrix)
    density_curves_layers: np.ndarray = field(default_factory=_empty_tensor)
    density_curves_model: DensityCurvesModel = field(default_factory=DensityCurvesModel)

    def __post_init__(self):
        self.wavelengths = np.asarray(self.wavelengths, dtype=float)
        self.log_sensitivity = np.asarray(self.log_sensitivity, dtype=float)
        self.bandpass_hanatos2025 = np.asarray(self.bandpass_hanatos2025, dtype=float)
        if self.bandpass_hanatos2025.size == 0:
            self.bandpass_hanatos2025 = _empty_matrix()
        self.hanatos2025_adaptation_window_params = np.asarray(self.hanatos2025_adaptation_window_params, dtype=float)
        if self.hanatos2025_adaptation_window_params.size == 0:
            self.hanatos2025_adaptation_window_params = _empty_vector()
        self.hanatos2025_adaptation_surface_params = np.asarray(self.hanatos2025_adaptation_surface_params, dtype=float)
        if self.hanatos2025_adaptation_surface_params.size == 0:
            self.hanatos2025_adaptation_surface_params = _empty_matrix()
        self.channel_density = np.asarray(self.channel_density, dtype=float)
        self.base_density = np.asarray(self.base_density, dtype=float)
        self.midscale_neutral_density = np.asarray(self.midscale_neutral_density, dtype=float)
        self.log_exposure = np.asarray(self.log_exposure, dtype=float)
        self.density_curves = np.asarray(self.density_curves, dtype=float)
        self.density_curves_layers = np.asarray(self.density_curves_layers, dtype=float)
        if not isinstance(self.density_curves_model, DensityCurvesModel):
            if isinstance(self.density_curves_model, Mapping):
                known = DensityCurvesModel.__dataclass_fields__
                filtered = {k: v for k, v in self.density_curves_model.items() if k in known}
                self.density_curves_model = DensityCurvesModel(**filtered)
            else:
                raise TypeError('density_curves_model must be a DensityCurvesModel or Mapping')
        self._validate_shapes_and_values()

    def _validate_shapes_and_values(self) -> None:
        _validate_1d('wavelengths', self.wavelengths)
        _validate_2d_three_columns('log_sensitivity', self.log_sensitivity, allow_nan=True)
        _validate_2d_three_columns('channel_density', self.channel_density, allow_nan=True)
        _validate_1d('base_density', self.base_density, allow_nan=True)
        _validate_1d('midscale_neutral_density', self.midscale_neutral_density, allow_nan=True)
        _validate_1d('log_exposure', self.log_exposure)
        _validate_2d_three_columns('density_curves', self.density_curves)

        if self.bandpass_hanatos2025.size:
            if self.bandpass_hanatos2025.shape != self.log_sensitivity.shape:
                raise ValueError('bandpass_hanatos2025 must be empty or match log_sensitivity shape')
            _validate_no_infinite_array('bandpass_hanatos2025', self.bandpass_hanatos2025)

        if self.density_curves_layers.size:
            if self.density_curves_layers.ndim != 3 or self.density_curves_layers.shape[1:] != (3, 3):
                raise ValueError('density_curves_layers must have shape (n, 3, 3)')
            _validate_finite_array('density_curves_layers', self.density_curves_layers)

        _validate_matching_length('channel_density', self.channel_density, 'wavelengths', self.wavelengths)
        _validate_matching_length('base_density', self.base_density, 'wavelengths', self.wavelengths)
        _validate_matching_length('midscale_neutral_density', self.midscale_neutral_density, 'wavelengths', self.wavelengths)
        _validate_matching_length('log_exposure', self.log_exposure, 'density_curves', self.density_curves)
        _validate_matching_length('density_curves_layers', self.density_curves_layers, 'log_exposure', self.log_exposure)


@dataclass
class Profile:
    metadata: ProfileMetadata = field(default_factory=ProfileMetadata)
    info: ProfileInfo = field(default_factory=ProfileInfo)
    data: ProfileData = field(default_factory=ProfileData)

    def __post_init__(self):
        if not isinstance(self.metadata, ProfileMetadata):
            raise TypeError('metadata must be a ProfileMetadata instance')
        if not isinstance(self.info, ProfileInfo):
            raise TypeError('info must be a ProfileInfo instance')
        if not isinstance(self.data, ProfileData):
            raise TypeError('data must be a ProfileData instance')

    def clone(self) -> 'Profile':
        return copy.deepcopy(self)

    def update_metadata(self, **changes) -> 'Profile':
        self.metadata = replace(self.metadata, **changes)
        return self

    def update_info(self, **changes) -> 'Profile':
        self.info = replace(self.info, **changes)
        return self

    def update_data(self, **changes) -> 'Profile':
        self.data = replace(self.data, **changes)
        return self

    def update(self, *, metadata=None, info=None, data=None) -> 'Profile':
        if metadata:
            self.update_metadata(**metadata)
        if info:
            self.update_info(**info)
        if data:
            self.update_data(**data)
        return self

    def hanatos2025_adaptation(self) -> Hanatos2025SensitivityAdaptation:
        return Hanatos2025SensitivityAdaptation(
            window_params=self.data.hanatos2025_adaptation_window_params,
            surface_params=self.data.hanatos2025_adaptation_surface_params,
            reference_illuminant=self.info.reference_illuminant,
        )
    
    @property
    def is_positive(self) -> bool:
        return self.info.type == 'positive'

    @property
    def is_negative(self) -> bool:
        return self.info.type == 'negative'

    @property
    def is_paper(self) -> bool:
        return self.info.support == 'paper'

    @property
    def is_film(self) -> bool:
        return self.info.support == 'film'
    
    @property
    def is_color(self) -> bool:
        return self.info.channel_model == 'color'
    
    @property
    def is_bw(self) -> bool:
        return self.info.channel_model == 'bw'

    @property
    def is_filming(self) -> bool:
        return self.info.stage == 'filming'

    @property
    def is_printing(self) -> bool:
        return self.info.stage == 'printing'

    @property
    def is_still(self) -> bool:
        return self.info.use == 'still'

    @property
    def is_cine(self) -> bool:
        return self.info.use == 'cine'


def profile_from_dict(data: Any) -> Profile:
    if isinstance(data, Profile):
        return data

    if not isinstance(data, Mapping):
        raise TypeError('Unsupported profile payload')

    metadata_payload = data.get('metadata', {})
    info_payload = data.get('info', {})
    data_payload = data.get('data', {})
    if not isinstance(metadata_payload, Mapping):
        raise TypeError("Profile 'metadata' must be a mapping")
    if not isinstance(info_payload, Mapping):
        raise TypeError("Profile 'info' must be a mapping")
    if not isinstance(data_payload, Mapping):
        raise TypeError("Profile 'data' must be a mapping")

    info_payload = dict(info_payload)
    for key in LEGACY_PROFILE_INFO_KEYS:
        info_payload.pop(key, None)

    def _filter_known(cls, payload):
        """Keep only keys that are declared dataclass fields of *cls*."""
        known = cls.__dataclass_fields__
        return {k: v for k, v in payload.items() if k in known}

    return Profile(
        metadata=ProfileMetadata(**_filter_known(ProfileMetadata, dict(metadata_payload))),
        info=ProfileInfo(**_filter_known(ProfileInfo, info_payload)),
        data=ProfileData(**_filter_known(ProfileData, dict(data_payload))),
    )


def profile_to_dict(data):
    if is_dataclass(data):
        return {k: profile_to_dict(getattr(data, k)) for k in data.__dataclass_fields__}
    if isinstance(data, dict):
        return {k: profile_to_dict(v) for k, v in data.items()}
    if isinstance(data, list):
        return [profile_to_dict(v) for v in data]
    if isinstance(data, tuple):
        return [profile_to_dict(v) for v in data]
    return data


def _json_safe(data):
    if isinstance(data, dict):
        return {k: _json_safe(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_json_safe(v) for v in data]
    if isinstance(data, tuple):
        return [_json_safe(v) for v in data]
    if isinstance(data, np.ndarray):
        return _json_safe(data.tolist())
    if isinstance(data, (float, np.floating)) and (np.isnan(data) or np.isinf(data)):
        return None
    return data


def _validate_profile_info(info, stock):
    if info.type not in PROFILE_TYPES:
        raise ValueError(f"Invalid profile '{stock}': unsupported type={info.type!r}")
    if info.support not in PROFILE_SUPPORTS:
        raise ValueError(f"Invalid profile '{stock}': unsupported support={info.support!r}")
    if info.stage not in PROFILE_STAGES:
        raise ValueError(f"Invalid profile '{stock}': unsupported stage={info.stage!r}")
    if info.use not in PROFILE_USES:
        raise ValueError(f"Invalid profile '{stock}': unsupported use={info.use!r}")
    if info.antihalation not in PROFILE_ANTIHALATION:
        raise ValueError(f"Invalid profile '{stock}': unsupported antihalation={info.antihalation!r}")
    if info.channel_model not in PROFILE_CHANNEL_MODELS:
        raise ValueError(f"Invalid profile '{stock}': unsupported channel_model={info.channel_model!r}")


def _validate_profile(profile, stock):
    try:
        _validate_profile_info(profile.info, stock)
        data = profile.data
        valid = (
            data.log_exposure.ndim == 1
            and data.density_curves.ndim == 2
            and data.density_curves.shape[1] == 3
            and data.density_curves.shape[0] == data.log_exposure.shape[0]
            and data.log_sensitivity.ndim == 2
            and data.log_sensitivity.shape[1] == 3
            and (data.bandpass_hanatos2025.ndim == 0
                 or data.bandpass_hanatos2025.size == 0
                 or data.bandpass_hanatos2025.shape == data.log_sensitivity.shape)
            and data.wavelengths.ndim == 1
            and data.channel_density.ndim == 2
            and data.channel_density.shape[1] == 3
            and data.channel_density.shape[0] == data.wavelengths.shape[0]
            and data.base_density.ndim == 1
            and data.base_density.shape[0] == data.wavelengths.shape[0]
            and data.midscale_neutral_density.ndim == 1
            and data.midscale_neutral_density.shape[0] == data.wavelengths.shape[0]
        )
    except (AttributeError, IndexError, KeyError, TypeError):
        raise ValueError(f"Invalid profile '{stock}'") from None

    if not valid:
        raise ValueError(f"Invalid profile '{stock}'")

def save_profile(profile, suffix=''):
    if profile.info.stock is None:
        raise ValueError("Cannot save profile: profile.info.stock is None — set a stock name before saving")
    profile = copy.deepcopy(profile)
    profile.info.stock = profile.info.stock + suffix
    _validate_profile_stock(profile.info.stock)

    package = pkg_resources.files('spektrafilm.data.profiles')
    filename = profile.info.stock + '.json'
    resource = package / filename
    print('Saving profile to:', filename)
    with resource.open("w") as file:
        json.dump(_json_safe(profile_to_dict(profile)), file, indent=4, allow_nan=False)

def list_profiles():
    """Return the sorted slugs of all bundled profiles (the JSON file
    stems under ``spektrafilm.data.profiles``)."""
    package = pkg_resources.files('spektrafilm.data.profiles')
    return sorted(
        entry.name[:-len('.json')]
        for entry in package.iterdir()
        if entry.name.endswith('.json')
    )


def load_profile(stock):
    _validate_profile_stock(stock)

    package = pkg_resources.files('spektrafilm.data.profiles')
    filename = stock + '.json'
    resource = package / filename
    with resource.open("r") as file:
        profile = profile_from_dict(json.load(file))
    _validate_profile(profile, stock)
    return profile


# Split-architecture aliases.
load_processed_profile = load_profile
save_processed_profile = save_profile

__all__ = [
    "DensityCurvesModel",
    "Profile",
    "ProfileData",
    "ProfileFieldProvenance",
    "ProfileInfo",
    "ProfileMetadata",
    "ProfileProvenance",
    "PROFILE_ANTIHALATION",
    "PROFILE_CHANNEL_MODELS",
    "PROFILE_MEASUREMENT_STATUSES",
    "PROFILE_PROVENANCE_FIELDS",
    "PROFILE_PROVENANCE_ORIGINS",
    "PROFILE_PROVENANCE_SCHEMA_VERSION",
    "PROFILE_PROVENANCE_STATUSES",
    "PROFILE_STAGES",
    "PROFILE_SUPPORTS",
    "PROFILE_TYPES",
    "PROFILE_USES",
    "profile_from_dict",
    "profile_to_dict",
    "list_profiles",
    "load_profile",
    "save_profile",
    "load_processed_profile",
    "save_processed_profile",
]
