from __future__ import annotations

from enum import Enum


class RGBColorSpaces(Enum):
    sRGB = "sRGB"
    DCI_P3 = "DCI-P3"
    DisplayP3 = "Display P3"
    AdobeRGB = "Adobe RGB (1998)"
    ITU_R_BT2020 = "ITU-R BT.2020"
    ProPhotoRGB = "ProPhoto RGB"
    ACES2065_1 = "ACES2065-1"
    ACEScg = "ACEScg"


class ColorManagementWorkflows(Enum):
    manual = "manual"
    aces_reference = "aces_reference"


class RGBtoRAWMethod(Enum):
    hanatos2025 = "hanatos2025"
    mallett2019 = "mallett2019"


class RawWhiteBalance(Enum):
    as_shot = "as_shot"
    daylight = "daylight"
    tungsten = "tungsten"
    custom = "custom"


class AutoExposureMethods(Enum):
    scene_linear = "scene_linear"
    center_weighted = "center_weighted"
    matrix = "matrix"
    multi_zone = "multi_zone"
    partial = "partial"
    highlight_weighted = "highlight_weighted"
    median = "median"
    average = "average"


class ComputeBackends(Enum):
    auto = "auto"
    cpu = "cpu"
    mlx = "mlx"
    cupy = "cupy"


class RuntimeFloatPrecisions(Enum):
    float32 = "float32"
    float64 = "float64"


class HDRMappingModes(Enum):
    generic = "generic"
    profile_aware = "profile_aware"


class EXRModes(Enum):
    scene_linear_archive = "scene_linear_archive"
    hdr_rendition = "hdr_rendition"


class NapariInterpolationModes(Enum):
    nearest = "nearest"
    linear = "linear"
    cubic = "cubic"
    spline16 = "spline16"
    spline36 = "spline36"
    lanczos = "lanczos"
    blackman = "blackman"


class DiffusionFilterFamilies(Enum):
    glimmerglass = "glimmerglass"
    black_pro_mist = "black_pro_mist"
    pro_mist = "pro_mist"
    cinebloom = "cinebloom"
