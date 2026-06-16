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


class HDRMappingModes(Enum):
    light_table = "light_table"
    paper = "paper"


class HDRSceneSources(Enum):
    output_layer_metadata = "output_layer_metadata"


class HDRHeadroomModes(Enum):
    content_percentile = "content_percentile"
    modern_recovery_peak_budget = "modern_recovery_peak_budget"


class HDRGainMapModes(Enum):
    rgb = "rgb"
    luma = "luma"


class AutoExposureMethods(Enum):
    center_weighted = "center_weighted"
    matrix = "matrix"
    multi_zone = "multi_zone"
    partial = "partial"
    highlight_weighted = "highlight_weighted"
    median = "median"
    average = "average"


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


class ComputeBackend(Enum):
    cpu = "cpu"
    auto = "auto"
    mlx = "mlx"
    cupy = "cupy"
    halide = "halide"


class GpuPrecision(Enum):
    float64 = "float64"
    float32 = "float32"


class MaterializePolicy(Enum):
    numpy_float64 = "numpy_float64"
    numpy_float32 = "numpy_float32"
    backend = "backend"


class InputGamutCompressAlgorithms(Enum):
    xy = "xy"
    oklch = "oklch"


class OutputGamutCompressAlgorithms(Enum):
    off = "off"
    oklch = "oklch"
    aces_rgc = "aces_rgc"
    oklrab = "oklrab"
    jzazbz = "jzazbz"
    cam16ucs = "cam16ucs"
