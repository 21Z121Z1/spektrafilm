#!/usr/bin/env python3
"""Validate and build local profile candidates from public batch archives.

The ColorReference target index exposes historical batch-average reference
archives.  This script caches those archives outside bundled package data,
selects only exact ``MATERIAL`` matches, groups archives by ``PROD_DATE``, and
performs complete target-production-date-proxy holdout validation of a
group-equal median GS0 effective output-density candidate.  For transmission
stocks it can also validate a tightly regularized rank-3 effective spectral
basis; those generators are not claimed to be uniquely identified analytical
dyes.

The generated profiles are local experimental copies.  They are not bundled,
the source spectra are not embedded, and the public download page is not
treated as an open-data or derivative-work licence.
"""

from __future__ import annotations

import argparse
import copy
import csv
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from io import BytesIO
import importlib.util
import importlib.metadata as importlib_metadata
import json
import math
from pathlib import Path
import platform
import re
import time
from typing import Any
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = PROJECT_ROOT / "src" / "spektrafilm" / "data" / "profiles"
COMPANION_PATH = Path(__file__).with_name(
    "profile-measurement-basis-evaluation.py"
)
PUBLIC_INDEX_URL = "https://www.colorreference.de/targets/index.html"
PUBLIC_ARCHIVE_BASE_URL = "https://www.colorreference.de/targets/"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "tmp" / "profile-public-batches"
CREATED_DATE = "2026-07-13"
USER_AGENT = "Mozilla/5.0 Spektrafilm public-batch evidence audit"


def _load_companion_module():
    spec = importlib.util.spec_from_file_location(
        "profile_measurement_basis_evaluation",
        COMPANION_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import companion analysis: {COMPANION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVALUATION = _load_companion_module()


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    material: str
    profile_slug: str
    measurement_kind: str
    primary_floor: float


@dataclass(frozen=True)
class BatchData:
    batch_id: str
    material: str
    production_date: str | None
    created: str | None
    wavelengths: np.ndarray
    names: np.ndarray
    values: np.ndarray
    archive_sha256: str
    source_member: str
    raw_zero_value_count: int


DATASET_SPECS = (
    DatasetSpec(
        key="provia_100f",
        material="Fujichrome Provia 100F (RDP III)",
        profile_slug="fujifilm_provia_100f",
        measurement_kind="transmission",
        primary_floor=1e-3,
    ),
    DatasetSpec(
        key="velvia_100",
        material="Fujichrome Velvia 100 (RVP 100)",
        profile_slug="fujifilm_velvia_100",
        measurement_kind="transmission",
        primary_floor=1e-3,
    ),
    DatasetSpec(
        key="ultra_endura",
        material="Kodak Professional Ultra Endura",
        profile_slug="kodak_ultra_endura",
        measurement_kind="reflection",
        primary_floor=1e-2,
    ),
    DatasetSpec(
        key="endura_premier",
        material="Kodak Professional Endura Premier",
        profile_slug="kodak_endura_premier",
        measurement_kind="reflection",
        primary_floor=1e-2,
    ),
)
SPEC_BY_MATERIAL = {spec.material: spec for spec in DATASET_SPECS}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=True,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _analysis_code_sha256() -> str:
    digest = hashlib.sha256()
    for path in (Path(__file__).resolve(), COMPANION_PATH.resolve()):
        label = path.name.encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(label).to_bytes(4, "big"))
        digest.update(label)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _analysis_software_versions() -> dict[str, str]:
    versions = {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
    }
    for distribution in ("numpy", "scipy", "colour-science"):
        try:
            versions[distribution] = importlib_metadata.version(distribution)
        except importlib_metadata.PackageNotFoundError:
            versions[distribution] = "not-installed"
    return versions


def _fetch_bytes(url: str, *, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(0.5 * attempt)
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except Exception as exc:  # pragma: no cover - network-specific branches
            last_error = exc
    assert last_error is not None
    raise last_error


def _archive_links(index_html: str) -> list[str]:
    return list(
        dict.fromkeys(
            re.findall(
                r'href="([FNR]\d{6}\.zip)"',
                index_html,
                flags=re.IGNORECASE,
            )
        )
    )


def _validate_zip_bytes(data: bytes, label: str) -> None:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            corrupt_member = archive.testzip()
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid public batch archive {label}") from exc
    if corrupt_member is not None:
        raise ValueError(
            f"Corrupt member {corrupt_member!r} in public batch archive {label}"
        )


def _load_or_download_archives(
    cache_dir: Path,
    *,
    download: bool,
    refresh: bool,
    max_workers: int,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    index_path = cache_dir / "index.html"
    if download and (refresh or not index_path.exists()):
        index_bytes = _fetch_bytes(PUBLIC_INDEX_URL)
        index_path.write_bytes(index_bytes)
    elif index_path.exists():
        index_bytes = index_path.read_bytes()
    else:
        raise FileNotFoundError(
            f"No cached public index at {index_path}. Run with "
            "--download-public-batches."
        )

    links = _archive_links(index_bytes.decode("latin1"))
    if not links:
        raise ValueError("The public target index contained no batch archives")

    archives: dict[str, bytes] = {}
    errors: list[dict[str, str]] = []

    def acquire(filename: str) -> tuple[str, bytes]:
        path = cache_dir / filename
        if refresh or not path.exists():
            if not download:
                raise FileNotFoundError(str(path))
            data = _fetch_bytes(PUBLIC_ARCHIVE_BASE_URL + filename)
            _validate_zip_bytes(data, filename)
            path.write_bytes(data)
        else:
            data = path.read_bytes()
            _validate_zip_bytes(data, filename)
        return filename, data

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(acquire, name): name for name in links}
        for future in as_completed(futures):
            try:
                filename, data = future.result()
                archives[filename] = data
            except Exception as exc:  # pragma: no cover - network/cache failures
                errors.append(
                    {
                        "archive": futures[future],
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )

    return archives, {
        "index_url": PUBLIC_INDEX_URL,
        "index_sha256": _sha256_bytes(index_bytes),
        "archive_links_discovered": len(links),
        "archives_available": len(archives),
        "errors": sorted(errors, key=lambda item: item["archive"]),
    }


def _preferred_metadata_members(
    archive: zipfile.ZipFile,
    batch_id: str,
) -> list[str]:
    candidates = [
        name
        for name in archive.namelist()
        if name.lower().endswith((".txt", ".it8"))
    ]

    def score(name: str) -> tuple[int, str]:
        basename = Path(name).name.lower()
        exact_names = {f"{batch_id.lower()}.txt", f"{batch_id.lower()}.it8"}
        if basename in exact_names:
            return 0, name
        if basename in {
            f"{batch_id.lower()}s.txt",
            f"{batch_id.lower()}iso.txt",
        }:
            return 1, name
        if basename in {"fault.txt", "readme.txt", "liesmich.txt"}:
            return 3, name
        return 2, name

    return sorted(candidates, key=score)


def _archive_metadata(
    archive: zipfile.ZipFile,
    batch_id: str,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for member in _preferred_metadata_members(archive, batch_id):
        try:
            text = archive.read(member).decode("latin1")
        except (KeyError, UnicodeDecodeError):
            continue
        for field_name in ("MATERIAL", "PROD_DATE", "CREATED"):
            if field_name in result:
                continue
            match = re.search(
                rf'^{field_name}\s+"([^"]+)"',
                text,
                flags=re.MULTILINE,
            )
            if match:
                result[field_name] = match.group(1).strip()
        if "MATERIAL" in result and len(result) == 3:
            break
    return result


def _parse_transmission_tsv(
    data: bytes,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lines = data.decode("latin1").splitlines()
    header_index = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("ID\tName\tX\tY\tZ")
    )
    rows = list(csv.DictReader(lines[header_index:], delimiter="\t"))
    spectral_fields = [
        field
        for field in rows[0]
        if field is not None and field.endswith("nm")
    ]
    names = np.array([row["Name"].strip() for row in rows])
    wavelengths = np.array([float(field[:-2]) for field in spectral_fields])
    values = np.array(
        [[float(row[field]) for field in spectral_fields] for row in rows],
        dtype=float,
    )
    return names, wavelengths, values


def _parse_cxf_spectra(
    data: bytes,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    root = ET.fromstring(data)
    names: list[str] = []
    rows: list[list[float]] = []
    wavelengths: np.ndarray | None = None
    for sample in root.iter("Sample"):
        name_element = sample.find("Name")
        spectrum = sample.find(".//Spectrum")
        if name_element is None or spectrum is None:
            continue
        pairs = [
            (float(value.attrib["Name"]), float(value.text))
            for value in spectrum.findall("Value")
            if value.text is not None and "Name" in value.attrib
        ]
        if not pairs:
            continue
        pairs.sort()
        row_wavelengths = np.array([pair[0] for pair in pairs])
        if wavelengths is None:
            wavelengths = row_wavelengths
        elif not np.array_equal(wavelengths, row_wavelengths):
            raise ValueError("CxF samples do not share one wavelength grid")
        names.append(name_element.text.strip() if name_element.text else "")
        rows.append([pair[1] for pair in pairs])
    if wavelengths is None:
        raise ValueError("CxF file contained no spectra")
    return np.array(names), wavelengths, np.asarray(rows, dtype=float)


def _parse_transmission_archive(
    archive: zipfile.ZipFile,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    xls_members = sorted(
        name for name in archive.namelist() if name.lower().endswith(".xls")
    )
    if xls_members:
        member = xls_members[0]
        names, wavelengths, values = _parse_transmission_tsv(
            archive.read(member)
        )
        return names, wavelengths, values, member
    cxf_members = sorted(
        name for name in archive.namelist() if name.lower().endswith(".cxf")
    )
    if cxf_members:
        member = cxf_members[0]
        names, wavelengths, values = _parse_cxf_spectra(archive.read(member))
        return names, wavelengths, values, member
    raise ValueError("Archive contains no machine-readable transmission spectra")


def _parse_reflection_archive(
    archive: zipfile.ZipFile,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    members = sorted(
        name for name in archive.namelist() if name.lower().endswith(".hist")
    )
    if not members:
        raise ValueError("Archive contains no machine-readable reflection spectra")
    member = members[0]
    names: list[str] = []
    rows: list[list[float]] = []
    for line in archive.read(member).decode("latin1").splitlines():
        match = re.match(r'^"([^"]+)".*~(.+)$', line.strip())
        if match is None:
            continue
        names.append(match.group(1))
        rows.append(
            [float(value.replace(",", ".")) / 100.0 for value in match.group(2).split()]
        )
    values = np.asarray(rows, dtype=float)
    if values.ndim != 2 or values.shape[1] != 31:
        raise ValueError(f"Expected 31 reflection bands, got {values.shape}")
    return np.array(names), np.arange(400.0, 701.0, 10.0), values, member


def _validate_batch_arrays(
    names: np.ndarray,
    wavelengths: np.ndarray,
    values: np.ndarray,
    batch_id: str,
) -> None:
    if values.shape != (288, len(wavelengths)):
        raise ValueError(
            f"Expected 288 patches in {batch_id}, got {values.shape}"
        )
    if len(set(names.tolist())) != 288:
        raise ValueError(f"Patch names are not unique in {batch_id}")
    if int(np.sum(names == "GS0")) != 1:
        raise ValueError(f"Expected exactly one GS0 patch in {batch_id}")
    if np.any(np.diff(wavelengths) <= 0):
        raise ValueError(f"Wavelengths are not increasing in {batch_id}")
    if not np.all(np.isfinite(values)) or not np.all(
        (values >= 0.0) & (values <= 1.0)
    ):
        raise ValueError(f"Invalid spectral values in {batch_id}")
    gs0 = values[names == "GS0"][0]
    if not np.all(gs0 > 0.0):
        raise ValueError(f"GS0 contains a non-positive value in {batch_id}")


def _spectral_content_sha256(batch: BatchData) -> str:
    order = np.argsort(batch.names.astype(str), kind="stable")
    digest = hashlib.sha256()
    for name in batch.names[order].tolist():
        encoded_name = str(name).encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
    wavelengths = np.ascontiguousarray(batch.wavelengths, dtype="<f8")
    values = np.ascontiguousarray(batch.values[order], dtype="<f8")
    digest.update(wavelengths.shape[0].to_bytes(8, "big"))
    digest.update(wavelengths.tobytes(order="C"))
    digest.update(values.shape[0].to_bytes(8, "big"))
    digest.update(values.shape[1].to_bytes(8, "big"))
    digest.update(values.tobytes(order="C"))
    return digest.hexdigest()


def _exclude_cross_production_date_duplicate_spectra(
    batches: list[BatchData],
) -> tuple[list[BatchData], list[dict[str, Any]]]:
    by_content: dict[str, list[BatchData]] = {}
    for batch in batches:
        by_content.setdefault(_spectral_content_sha256(batch), []).append(batch)

    excluded_ids: set[str] = set()
    exclusions: list[dict[str, Any]] = []
    for content_sha256, matches in sorted(by_content.items()):
        production_dates = {_production_group_key(batch) for batch in matches}
        if len(production_dates) <= 1:
            continue
        batch_ids = sorted(batch.batch_id for batch in matches)
        excluded_ids.update(batch_ids)
        for batch in matches:
            exclusions.append(
                {
                    "batch": batch.batch_id,
                    "material": batch.material,
                    "reason": (
                        "Exact parsed spectral content is duplicated across "
                        "distinct PROD_DATE groups; all ambiguous copies are "
                        "excluded to prevent held-out leakage"
                    ),
                    "spectral_content_sha256": content_sha256,
                    "duplicate_batches": batch_ids,
                    "duplicate_production_groups": sorted(production_dates),
                }
            )
    return (
        [batch for batch in batches if batch.batch_id not in excluded_ids],
        exclusions,
    )


def _collect_exact_material_batches(
    archives: dict[str, bytes],
) -> tuple[dict[str, list[BatchData]], list[dict[str, Any]]]:
    datasets = {spec.material: [] for spec in DATASET_SPECS}
    exclusions: list[dict[str, Any]] = []
    for filename, data in sorted(archives.items()):
        batch_id = filename[:-4]
        with zipfile.ZipFile(BytesIO(data)) as archive:
            metadata = _archive_metadata(archive, batch_id)
            material = metadata.get("MATERIAL")
            spec = SPEC_BY_MATERIAL.get(material)
            if spec is None:
                continue
            try:
                if spec.measurement_kind == "transmission":
                    names, wavelengths, values, member = (
                        _parse_transmission_archive(archive)
                    )
                else:
                    names, wavelengths, values, member = (
                        _parse_reflection_archive(archive)
                    )
                _validate_batch_arrays(names, wavelengths, values, batch_id)
            except ValueError as exc:
                exclusions.append(
                    {
                        "batch": batch_id,
                        "material": material,
                        "reason": str(exc),
                    }
                )
                continue
            datasets[material].append(
                BatchData(
                    batch_id=batch_id,
                    material=material,
                    production_date=metadata.get("PROD_DATE"),
                    created=metadata.get("CREATED"),
                    wavelengths=wavelengths,
                    names=names,
                    values=values,
                    archive_sha256=_sha256_bytes(data),
                    source_member=member,
                    raw_zero_value_count=int(np.sum(values == 0.0)),
                )
            )
    for material, batches in datasets.items():
        batches.sort(key=lambda batch: batch.batch_id)
        filtered, duplicate_exclusions = (
            _exclude_cross_production_date_duplicate_spectra(batches)
        )
        datasets[material] = filtered
        exclusions.extend(duplicate_exclusions)
    return datasets, exclusions


def _common_wavelengths(batches: list[BatchData]) -> np.ndarray:
    common = set(batches[0].wavelengths.tolist())
    for batch in batches[1:]:
        common &= set(batch.wavelengths.tolist())
    wavelengths = np.array(sorted(common), dtype=float)
    if len(wavelengths) < 2:
        raise ValueError("Exact-material batches have no common spectral grid")
    return wavelengths


def _values_on_grid(batch: BatchData, wavelengths: np.ndarray) -> np.ndarray:
    lookup = {float(value): index for index, value in enumerate(batch.wavelengths)}
    try:
        indices = [lookup[float(value)] for value in wavelengths]
    except KeyError as exc:
        raise ValueError(
            f"Batch {batch.batch_id} lacks wavelength {exc.args[0]}"
        ) from exc
    return batch.values[:, indices]


def _production_group_key(batch: BatchData) -> str:
    production_date = (batch.production_date or "").strip()
    return production_date or f"unknown:{batch.batch_id}"


def _production_groups(
    batches: list[BatchData],
) -> list[tuple[str, np.ndarray]]:
    grouped: dict[str, list[int]] = {}
    for index, batch in enumerate(batches):
        grouped.setdefault(_production_group_key(batch), []).append(index)

    def sort_key(item: tuple[str, list[int]]) -> tuple[int, str, str]:
        key, indices = item
        unknown = key.startswith("unknown:")
        first_batch = batches[indices[0]].batch_id
        return (int(unknown), key, first_batch)

    return [
        (key, np.asarray(indices, dtype=int))
        for key, indices in sorted(grouped.items(), key=sort_key)
    ]


def _align_patch_rows(
    batch: BatchData,
    values: np.ndarray,
    canonical_names: np.ndarray,
) -> np.ndarray:
    if np.array_equal(batch.names, canonical_names):
        return values
    if set(batch.names.tolist()) != set(canonical_names.tolist()):
        raise ValueError(
            f"Patch-name set differs in exact-material archive {batch.batch_id}"
        )
    lookup = {name: index for index, name in enumerate(batch.names.tolist())}
    return values[[lookup[name] for name in canonical_names.tolist()]]


def _group_equal_median(
    arrays: list[np.ndarray],
    groups: list[tuple[str, np.ndarray]],
) -> np.ndarray:
    group_medians = [
        np.median(
            np.stack([arrays[int(index)] for index in indices]),
            axis=0,
        )
        for _, indices in groups
    ]
    return np.median(np.stack(group_medians), axis=0)


def _group_macro_rows(
    per_archive_rows: list[dict[str, Any]],
    batches: list[BatchData],
) -> list[dict[str, Any]]:
    key_by_batch = {
        batch.batch_id: _production_group_key(batch) for batch in batches
    }
    rows_by_group: dict[str, list[dict[str, Any]]] = {}
    for row in per_archive_rows:
        rows_by_group.setdefault(key_by_batch[row["batch"]], []).append(row)
    result: list[dict[str, Any]] = []
    for group_key, rows in sorted(rows_by_group.items()):
        metric_names = tuple(rows[0]["metrics"])
        result.append(
            {
                "production_group": group_key,
                "archive_count": len(rows),
                "archive_ids": [row["batch"] for row in rows],
                "metrics": {
                    metric_name: float(
                        np.mean(
                            [row["metrics"][metric_name] for row in rows]
                        )
                    )
                    for metric_name in metric_names
                },
            }
        )
    return result


def _mean_row_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    metric_names = tuple(rows[0]["metrics"])
    return {
        metric_name: float(
            np.mean([row["metrics"][metric_name] for row in rows])
        )
        for metric_name in metric_names
    }


def _one_sided_sign_test_p_value(wins: int, count: int) -> float:
    if not 0 <= wins <= count:
        raise ValueError("Sign-test wins must lie between zero and count")
    return float(
        sum(math.comb(count, value) for value in range(wins, count + 1))
        / (2**count)
    )


def _maximum_relative_regression_percent(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    metric_name: str,
) -> float:
    regressions: list[float] = []
    for baseline, candidate in zip(
        baseline_rows,
        candidate_rows,
        strict=True,
    ):
        baseline_value = float(baseline["metrics"][metric_name])
        candidate_value = float(candidate["metrics"][metric_name])
        denominator = max(abs(baseline_value), 1e-12)
        regressions.append(
            100.0 * (candidate_value - baseline_value) / denominator
        )
    return float(max(regressions))


def _measurement_metric_name(measurement_kind: str) -> str:
    return f"{measurement_kind}_rmse_percentage_points"


def _rename_measurement_metric(
    metrics: dict[str, Any],
    measurement_kind: str,
) -> dict[str, Any]:
    result = dict(metrics)
    result[_measurement_metric_name(measurement_kind)] = result.pop(
        "transmittance_rmse_percentage_points"
    )
    return result


def _metric_improvements(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, float]:
    result: dict[str, float] = {}
    for metric_name in baseline:
        baseline_value = baseline[metric_name]
        candidate_value = candidate[metric_name]
        if not isinstance(baseline_value, (float, int)):
            continue
        if float(baseline_value) == 0.0:
            continue
        result[metric_name] = float(
            100.0
            * (float(baseline_value) - float(candidate_value))
            / float(baseline_value)
        )
    return result


def _summarize_predictions(
    spec: DatasetSpec,
    wavelengths: np.ndarray,
    values: np.ndarray,
    density: np.ndarray,
    prediction: np.ndarray,
    floor: float,
) -> dict[str, Any]:
    return _rename_measurement_metric(
        EVALUATION._summarize_predictions(
            wavelengths,
            values,
            density,
            prediction,
            floor,
        ),
        spec.measurement_kind,
    )


def _evaluate_cross_batch_base(
    spec: DatasetSpec,
    batches: list[BatchData],
    *,
    floors: tuple[float, ...],
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    if len(batches) < 2:
        raise ValueError(f"Need at least two exact-material archives for {spec.key}")
    production_groups = _production_groups(batches)
    if len(production_groups) < 2:
        raise ValueError(
            f"Need at least two production-date groups for {spec.key}"
        )
    common_wavelengths = _common_wavelengths(batches)
    measured_mask, wavelengths, basis, bundled_base = (
        EVALUATION._load_profile_basis(
            spec.profile_slug,
            common_wavelengths,
        )
    )
    canonical_names = batches[0].names.copy()
    full_common_values = [
        _align_patch_rows(
            batch,
            _values_on_grid(batch, common_wavelengths),
            canonical_names,
        )
        for batch in batches
    ]
    selected_values = [values[:, measured_mask] for values in full_common_values]
    if any(np.any(values <= 0.0) for values in selected_values):
        raise ValueError(
            f"A non-positive value enters the profile-supported grid for {spec.key}"
        )
    full_gs0_density = np.array(
        [
            -np.log10(values[canonical_names == "GS0"][0])
            for values in full_common_values
        ]
    )
    gs0_density = np.array(
        [
            -np.log10(values[canonical_names == "GS0"][0])
            for values in selected_values
        ]
    )
    group_gs0_density = [
        np.median(gs0_density[indices], axis=0)
        for _, indices in production_groups
    ]
    group_full_gs0_density = [
        np.median(full_gs0_density[indices], axis=0)
        for _, indices in production_groups
    ]
    final_candidate_base = np.median(np.stack(group_gs0_density), axis=0)
    final_candidate_base_full_grid = np.median(
        np.stack(group_full_gs0_density),
        axis=0,
    )
    p05, p95 = np.quantile(
        np.stack(group_gs0_density),
        (0.05, 0.95),
        axis=0,
    )
    median_absolute_deviation = np.median(
        np.abs(np.stack(group_gs0_density) - final_candidate_base),
        axis=0,
    )

    direct_bundled_archive = np.sqrt(
        np.mean(np.square(gs0_density - bundled_base[None, :]), axis=1)
    )
    direct_candidate_archive = np.empty(len(batches), dtype=float)
    direct_bundled_group = np.sqrt(
        np.mean(
            np.square(np.stack(group_gs0_density) - bundled_base[None, :]),
            axis=1,
        )
    )
    direct_candidate_group = np.empty(len(production_groups), dtype=float)
    for held_group_index, (_, held_indices) in enumerate(production_groups):
        training_groups = [
            group
            for index, group in enumerate(production_groups)
            if index != held_group_index
        ]
        training_candidate_base = _group_equal_median(
            [density for density in gs0_density],
            training_groups,
        )
        direct_candidate_group[held_group_index] = float(
            np.sqrt(
                np.mean(
                    np.square(
                        training_candidate_base
                        - group_gs0_density[held_group_index]
                    )
                )
            )
        )
        for held_index in held_indices:
            direct_candidate_archive[int(held_index)] = float(
                np.sqrt(
                    np.mean(
                        np.square(
                            training_candidate_base
                            - gs0_density[int(held_index)]
                        )
                    )
                )
            )

    floor_results: dict[str, Any] = {}

    for floor in floors:
        aggregate_values: list[np.ndarray] = []
        aggregate_density: list[np.ndarray] = []
        aggregate_predictions = {"bundled_base": [], "multibatch_median_gs0": []}
        per_archive: list[dict[str, Any]] = []
        per_group: list[dict[str, Any]] = []

        for held_group_index, (group_key, held_indices) in enumerate(
            production_groups
        ):
            training_groups = [
                group
                for index, group in enumerate(production_groups)
                if index != held_group_index
            ]
            training_candidate_base = _group_equal_median(
                [density for density in gs0_density],
                training_groups,
            )
            group_values: list[np.ndarray] = []
            group_density: list[np.ndarray] = []
            group_predictions = {
                "bundled_base": [],
                "multibatch_median_gs0": [],
            }
            group_archive_rows: list[dict[str, Any]] = []
            for held_index_value in held_indices:
                held_index = int(held_index_value)
                held_batch = batches[held_index]
                held_values = selected_values[held_index]
                held_density = -np.log10(held_values)
                evaluation_mask = canonical_names != "GS0"
                evaluation_values = held_values[evaluation_mask]
                evaluation_density = held_density[evaluation_mask]
                row = {
                    "batch": held_batch.batch_id,
                    "production_group": group_key,
                    "metrics": {},
                }
                for model_name, base in (
                    ("bundled_base", bundled_base),
                    ("multibatch_median_gs0", training_candidate_base),
                ):
                    prediction = EVALUATION._fit_coefficients_and_predict(
                        evaluation_density,
                        evaluation_values,
                        basis,
                        base,
                        floor,
                    )
                    aggregate_predictions[model_name].append(prediction)
                    group_predictions[model_name].append(prediction)
                    row["metrics"][model_name] = _summarize_predictions(
                        spec,
                        wavelengths,
                        evaluation_values,
                        evaluation_density,
                        prediction,
                        floor,
                    )
                aggregate_values.append(evaluation_values)
                aggregate_density.append(evaluation_density)
                group_values.append(evaluation_values)
                group_density.append(evaluation_density)
                group_archive_rows.append(row)
                per_archive.append(row)

            concatenated_values = np.concatenate(group_values)
            concatenated_density = np.concatenate(group_density)
            per_group.append(
                {
                    "production_group": group_key,
                    "archive_count": len(held_indices),
                    "archive_ids": [
                        batches[int(index)].batch_id for index in held_indices
                    ],
                    "metrics": {
                        model_name: _summarize_predictions(
                            spec,
                            wavelengths,
                            concatenated_values,
                            concatenated_density,
                            np.concatenate(predictions),
                            floor,
                        )
                        for model_name, predictions in group_predictions.items()
                    },
                    "per_archive": group_archive_rows,
                }
            )

        all_values = np.concatenate(aggregate_values)
        all_density = np.concatenate(aggregate_density)
        aggregate_metrics = {
            model_name: _summarize_predictions(
                spec,
                wavelengths,
                all_values,
                all_density,
                np.concatenate(predictions),
                floor,
            )
            for model_name, predictions in aggregate_predictions.items()
        }
        baseline = aggregate_metrics["bundled_base"]
        candidate = aggregate_metrics["multibatch_median_gs0"]
        macro_metrics = {
            model_name: {
                metric_name: float(
                    np.mean(
                        [
                            row["metrics"][model_name][metric_name]
                            for row in per_group
                        ]
                    )
                )
                for metric_name in tuple(baseline)
            }
            for model_name in ("bundled_base", "multibatch_median_gs0")
        }
        macro_baseline = macro_metrics["bundled_base"]
        macro_candidate = macro_metrics["multibatch_median_gs0"]
        metric_names = tuple(baseline)
        archive_win_counts = {
            metric_name: int(
                sum(
                    row["metrics"]["multibatch_median_gs0"][metric_name]
                    < row["metrics"]["bundled_base"][metric_name]
                    for row in per_archive
                )
            )
            for metric_name in metric_names
        }
        group_win_counts = {
            metric_name: int(
                sum(
                    row["metrics"]["multibatch_median_gs0"][metric_name]
                    < row["metrics"]["bundled_base"][metric_name]
                    for row in per_group
                )
            )
            for metric_name in metric_names
        }
        floor_results[f"{floor:g}"] = {
            "held_out_unit": "complete PROD_DATE production-proxy group",
            "gs0_excluded_from_patch_reconstruction": True,
            "models": aggregate_metrics,
            "model_metric_weighting": "micro over all held-out archive patches",
            "production_group_macro_models": macro_metrics,
            "candidate_improvement_percent": _metric_improvements(
                baseline,
                candidate,
            ),
            "production_group_macro_improvement_percent": _metric_improvements(
                macro_baseline,
                macro_candidate,
            ),
            "candidate_archive_win_counts": archive_win_counts,
            "candidate_batch_win_counts": archive_win_counts,
            "candidate_production_group_win_counts": group_win_counts,
            "production_group_sign_test_p_values": {
                metric_name: _one_sided_sign_test_p_value(
                    group_win_counts[metric_name],
                    len(production_groups),
                )
                for metric_name in metric_names
            },
            "batch_count": len(batches),
            "archive_count": len(batches),
            "production_group_count": len(production_groups),
            "per_archive": per_archive,
            "per_production_group": per_group,
        }

    raw_zero_total = int(sum(batch.raw_zero_value_count for batch in batches))
    raw_zero_interpretation = (
        "Published exact zeroes are confined to the 380/390 nm noise-floor "
        "region outside the profile-supported evaluation grid and are not "
        "clipped or fitted."
        if raw_zero_total
        else "No exact zero spectral values occur in these selected archives."
    )
    result = {
        "material": spec.material,
        "profile": spec.profile_slug,
        "measurement_kind": spec.measurement_kind,
        "batch_count": len(batches),
        "archive_count": len(batches),
        "production_group_count": len(production_groups),
        "production_groups": [
            {
                "production_group": key,
                "archive_ids": [
                    batches[int(index)].batch_id for index in indices
                ],
                "archive_count": len(indices),
            }
            for key, indices in production_groups
        ],
        "batch_ids": [batch.batch_id for batch in batches],
        "production_dates": [batch.production_date for batch in batches],
        "raw_zero_values_outside_used_support": {
            "total": raw_zero_total,
            "affected_batch_count": int(
                sum(batch.raw_zero_value_count > 0 for batch in batches)
            ),
            "used_profile_grid_zero_count": 0,
            "interpretation": raw_zero_interpretation,
        },
        "wavelength_range_used_nm": [
            float(wavelengths[0]),
            float(wavelengths[-1]),
        ],
        "wavelength_count_used": int(len(wavelengths)),
        "direct_gs0_base_rmse_D": {
            "bundled_base_mean": float(np.mean(direct_bundled_archive)),
            "bundled_base_median": float(np.median(direct_bundled_archive)),
            "leave_one_batch_out_candidate_mean": float(
                np.mean(direct_candidate_archive)
            ),
            "leave_one_batch_out_candidate_median": float(
                np.median(direct_candidate_archive)
            ),
            "candidate_batch_wins": int(
                np.sum(direct_candidate_archive < direct_bundled_archive)
            ),
            "batch_count": len(batches),
            "candidate_production_group_wins": int(
                np.sum(direct_candidate_group < direct_bundled_group)
            ),
            "production_group_count": len(production_groups),
            "bundled_group_macro_mean": float(
                np.mean(direct_bundled_group)
            ),
            "leave_one_group_out_candidate_macro_mean": float(
                np.mean(direct_candidate_group)
            ),
        },
        "gs0_interbatch_dispersion_D": {
            "mean_p05_to_p95_width": float(np.mean(p95 - p05)),
            "max_p05_to_p95_width": float(np.max(p95 - p05)),
            "mean_median_absolute_deviation": float(
                np.mean(median_absolute_deviation)
            ),
        },
        "results_by_measurement_floor": floor_results,
        "interpretation": (
            "Archives sharing PROD_DATE are treated as one conservative "
            "target production-date proxy. The candidate first takes an "
            "archive median "
            "within each group and then a group-equal median. Each held-out group "
            "is evaluated with a GS0 base constructed only from other groups. "
            "Patch coefficients are still fitted from held-out spectra, so this "
            "validates base/basis reconstruction rather than exposure prediction."
        ),
    }
    return result, common_wavelengths, final_candidate_base_full_grid


def _evaluate_base_candidate_gate(
    spec: DatasetSpec,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    floor_result = evaluation["results_by_measurement_floor"][
        f"{spec.primary_floor:g}"
    ]
    measurement_metric = _measurement_metric_name(spec.measurement_kind)
    minimum_improvement_percent = {
        "density_rmse_D": 5.0,
        measurement_metric: 5.0,
        "delta_e_2000_median": 2.0,
        "delta_e_2000_mean": 2.0,
        "delta_e_2000_p95": 0.5,
    }
    micro_improvement = floor_result["candidate_improvement_percent"]
    macro_improvement = floor_result[
        "production_group_macro_improvement_percent"
    ]
    primary_metrics = tuple(
        metric
        for metric in minimum_improvement_percent
        if metric != "delta_e_2000_p95"
    )
    sign_p_values = floor_result["production_group_sign_test_p_values"]
    maximum_group_regression = {
        metric: max(
            100.0
            * (
                group["metrics"]["multibatch_median_gs0"][metric]
                - group["metrics"]["bundled_base"][metric]
            )
            / max(abs(group["metrics"]["bundled_base"][metric]), 1e-12)
            for group in floor_result["per_production_group"]
        )
        for metric in minimum_improvement_percent
    }
    reconstruction_passes = bool(
        evaluation["production_group_count"] >= 8
        and all(
            micro_improvement.get(metric, -np.inf) >= minimum
            and macro_improvement.get(metric, -np.inf) >= minimum
            for metric, minimum in minimum_improvement_percent.items()
        )
        and all(sign_p_values[metric] <= 0.05 for metric in primary_metrics)
        and all(value <= 5.0 for value in maximum_group_regression.values())
        and evaluation["direct_gs0_base_rmse_D"][
            "candidate_production_group_wins"
        ]
        == evaluation["production_group_count"]
    )
    return {
        "reconstruction_passes": reconstruction_passes,
        "passes": False,
        "runtime_status": "pending",
        "candidate_may_be_emitted": False,
        "default_replacement_authorized": False,
        "policy_origin": (
            "Spektrafilm conservative engineering policy; not an ISO or "
            "paper-prescribed threshold"
        ),
        "minimum_production_group_count": 8,
        "minimum_improvement_percent_for_micro_and_group_macro": (
            minimum_improvement_percent
        ),
        "maximum_allowed_single_group_regression_percent": 5.0,
        "maximum_primary_metric_sign_test_p_value": 0.05,
        "micro_improvement_percent": micro_improvement,
        "production_group_macro_improvement_percent": macro_improvement,
        "production_group_sign_test_p_values": sign_p_values,
        "production_group_maximum_regression_percent": (
            maximum_group_regression
        ),
    }


def _fit_aligned_free_basis(
    density: np.ndarray,
    values: np.ndarray,
    base: np.ndarray,
    bundled_basis: np.ndarray,
    floor: float,
    *,
    iterations: int,
    seed: int,
    initialization_count: int,
) -> tuple[np.ndarray, np.ndarray, float]:
    candidates = [
        EVALUATION._fit_effective_nmf_basis(
            density,
            values,
            base,
            bundled_basis,
            floor,
            random_seed=None,
            iterations=iterations,
        )
    ]
    for initialization_index in range(max(0, initialization_count - 1)):
        candidates.append(
            EVALUATION._fit_effective_nmf_basis(
                density,
                values,
                base,
                bundled_basis,
                floor,
                random_seed=seed + initialization_index,
                iterations=iterations,
            )
        )
    free_basis, training_rmse = min(candidates, key=lambda item: item[1])
    aligned_basis, similarities = EVALUATION._align_basis_to_profile(
        free_basis,
        bundled_basis,
    )
    return EVALUATION._normalize_basis(aligned_basis), similarities, training_rmse


def _blended_basis(
    bundled_basis: np.ndarray,
    free_basis: np.ndarray,
    alpha: float,
) -> np.ndarray:
    current = np.asarray(bundled_basis, dtype=float)
    if alpha == 0.0:
        return current.copy()
    channel_scales = np.maximum(np.max(current, axis=0), 1e-12)
    current_shape = current / channel_scales
    free_shape = EVALUATION._normalize_basis(free_basis)
    blended_shape = EVALUATION._normalize_basis(
        np.maximum(
            (1.0 - alpha) * current_shape + alpha * free_shape,
            0.0,
        )
    )
    return blended_shape * channel_scales


def _evaluate_basis_set_on_batches(
    spec: DatasetSpec,
    batches: list[BatchData],
    batch_indices: np.ndarray,
    selected_values: list[np.ndarray],
    selected_density: list[np.ndarray],
    canonical_names: np.ndarray,
    wavelengths: np.ndarray,
    bases: dict[float, np.ndarray],
    base_density: np.ndarray,
) -> tuple[
    dict[float, dict[str, Any]],
    dict[float, list[dict[str, Any]]],
]:
    aggregate_values: dict[float, list[np.ndarray]] = {
        alpha: [] for alpha in bases
    }
    aggregate_density: dict[float, list[np.ndarray]] = {
        alpha: [] for alpha in bases
    }
    aggregate_predictions: dict[float, list[np.ndarray]] = {
        alpha: [] for alpha in bases
    }
    per_batch: dict[float, list[dict[str, Any]]] = {
        alpha: [] for alpha in bases
    }
    for batch_index in batch_indices:
        batch = batches[int(batch_index)]
        evaluation_mask = canonical_names != "GS0"
        values = selected_values[int(batch_index)][evaluation_mask]
        density = selected_density[int(batch_index)][evaluation_mask]
        for alpha, basis in bases.items():
            prediction = EVALUATION._fit_coefficients_and_predict(
                density,
                values,
                basis,
                base_density,
                spec.primary_floor,
            )
            aggregate_values[alpha].append(values)
            aggregate_density[alpha].append(density)
            aggregate_predictions[alpha].append(prediction)
            per_batch[alpha].append(
                {
                    "batch": batch.batch_id,
                    "metrics": _summarize_predictions(
                        spec,
                        wavelengths,
                        values,
                        density,
                        prediction,
                        spec.primary_floor,
                    ),
                }
            )
    aggregate = {
        alpha: _summarize_predictions(
            spec,
            wavelengths,
            np.concatenate(aggregate_values[alpha]),
            np.concatenate(aggregate_density[alpha]),
            np.concatenate(aggregate_predictions[alpha]),
            spec.primary_floor,
        )
        for alpha in bases
    }
    return aggregate, per_batch


def _basis_win_counts(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> dict[str, int]:
    metric_names = tuple(baseline_rows[0]["metrics"])
    return {
        metric_name: int(
            sum(
                candidate["metrics"][metric_name]
                < baseline["metrics"][metric_name]
                for baseline, candidate in zip(
                    baseline_rows,
                    candidate_rows,
                    strict=True,
                )
            )
        )
        for metric_name in metric_names
    }


def _evaluate_effective_basis_path(
    spec: DatasetSpec,
    batches: list[BatchData],
    *,
    alphas: tuple[float, ...],
    folds: int,
    iterations: int,
    seed: int,
    initialization_count: int,
    selected_alpha: float,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    if spec.measurement_kind != "transmission":
        raise ValueError("Effective CMY basis path is transmission-only")
    if selected_alpha not in alphas:
        raise ValueError("Selected basis alpha must be present in the alpha path")
    production_groups = _production_groups(batches)
    if not 2 <= folds <= len(production_groups):
        raise ValueError(
            "Basis folds must be between 2 and the production-group count"
        )
    if not all(0.0 <= alpha <= 1.0 for alpha in alphas):
        raise ValueError("Basis blend alphas must be between 0 and 1")

    common_wavelengths = _common_wavelengths(batches)
    measured_mask, wavelengths, bundled_basis, _ = (
        EVALUATION._load_profile_basis(spec.profile_slug, common_wavelengths)
    )
    canonical_names = batches[0].names.copy()
    selected_values = [
        _align_patch_rows(
            batch,
            _values_on_grid(batch, common_wavelengths),
            canonical_names,
        )[:, measured_mask]
        for batch in batches
    ]
    if any(np.any(values <= 0.0) for values in selected_values):
        raise ValueError("Non-positive value entered effective-basis validation")
    selected_density = [-np.log10(values) for values in selected_values]

    fold_group_positions = np.array_split(
        np.arange(len(production_groups)),
        folds,
    )
    aggregate_values: dict[float, list[np.ndarray]] = {
        alpha: [] for alpha in alphas
    }
    aggregate_density: dict[float, list[np.ndarray]] = {
        alpha: [] for alpha in alphas
    }
    aggregate_predictions: dict[float, list[np.ndarray]] = {
        alpha: [] for alpha in alphas
    }
    per_batch: dict[float, list[dict[str, Any]]] = {
        alpha: [] for alpha in alphas
    }
    fold_similarities: list[np.ndarray] = []
    fold_peak_wavelengths: list[np.ndarray] = []
    fold_training_rmse: list[float] = []
    fold_test_groups: list[list[str]] = []

    for fold_index, test_group_positions in enumerate(fold_group_positions):
        training_group_positions = np.setdiff1d(
            np.arange(len(production_groups)),
            test_group_positions,
            assume_unique=True,
        )
        training_groups = [
            production_groups[int(position)]
            for position in training_group_positions
        ]
        test_indices = np.concatenate(
            [
                production_groups[int(position)][1]
                for position in test_group_positions
            ]
        )
        fold_test_groups.append(
            [
                production_groups[int(position)][0]
                for position in test_group_positions
            ]
        )
        training_density = _group_equal_median(
            selected_density,
            training_groups,
        )
        training_values = np.power(10.0, -training_density)
        training_base = _group_equal_median(
            [
                density[canonical_names == "GS0"][0]
                for density in selected_density
            ],
            training_groups,
        )
        free_basis, similarities, training_rmse = _fit_aligned_free_basis(
            training_density,
            training_values,
            training_base,
            bundled_basis,
            spec.primary_floor,
            iterations=iterations,
            seed=seed + 100 * fold_index,
            initialization_count=initialization_count,
        )
        fold_similarities.append(similarities)
        fold_peak_wavelengths.append(wavelengths[np.argmax(free_basis, axis=0)])
        fold_training_rmse.append(training_rmse)
        bases = {
            alpha: _blended_basis(bundled_basis, free_basis, alpha)
            for alpha in alphas
        }
        _, fold_per_batch = _evaluate_basis_set_on_batches(
            spec,
            batches,
            test_indices,
            selected_values,
            selected_density,
            canonical_names,
            wavelengths,
            bases,
            training_base,
        )
        for alpha in alphas:
            for row in fold_per_batch[alpha]:
                batch_index = next(
                    index
                    for index, batch in enumerate(batches)
                    if batch.batch_id == row["batch"]
                )
                evaluation_mask = canonical_names != "GS0"
                values = selected_values[batch_index][evaluation_mask]
                density = selected_density[batch_index][evaluation_mask]
                prediction = EVALUATION._fit_coefficients_and_predict(
                    density,
                    values,
                    bases[alpha],
                    training_base,
                    spec.primary_floor,
                )
                aggregate_values[alpha].append(values)
                aggregate_density[alpha].append(density)
                aggregate_predictions[alpha].append(prediction)
                per_batch[alpha].append(row)

    aggregate_metrics = {
        alpha: _summarize_predictions(
            spec,
            wavelengths,
            np.concatenate(aggregate_values[alpha]),
            np.concatenate(aggregate_density[alpha]),
            np.concatenate(aggregate_predictions[alpha]),
            spec.primary_floor,
        )
        for alpha in alphas
    }
    production_group_rows = {
        alpha: _group_macro_rows(per_batch[alpha], batches)
        for alpha in alphas
    }
    production_group_macro_metrics = {
        alpha: _mean_row_metrics(production_group_rows[alpha])
        for alpha in alphas
    }
    baseline_metrics = aggregate_metrics[0.0]
    baseline_macro_metrics = production_group_macro_metrics[0.0]
    path_results = {
        f"{alpha:g}": {
            "metrics": aggregate_metrics[alpha],
            "metric_weighting": "micro over held-out archive patches",
            "production_group_macro_metrics": (
                production_group_macro_metrics[alpha]
            ),
            "improvement_percent_vs_bundled_basis": _metric_improvements(
                baseline_metrics,
                aggregate_metrics[alpha],
            ),
            "production_group_macro_improvement_percent_vs_bundled_basis": (
                _metric_improvements(
                    baseline_macro_metrics,
                    production_group_macro_metrics[alpha],
                )
            ),
            "archive_win_counts_vs_bundled_basis": _basis_win_counts(
                per_batch[0.0],
                per_batch[alpha],
            ),
            "batch_win_counts_vs_bundled_basis": _basis_win_counts(
                per_batch[0.0],
                per_batch[alpha],
            ),
            "production_group_win_counts_vs_bundled_basis": _basis_win_counts(
                production_group_rows[0.0],
                production_group_rows[alpha],
            ),
            "batch_count": len(batches),
            "archive_count": len(batches),
            "production_group_count": len(production_groups),
        }
        for alpha in alphas
    }
    for alpha in alphas:
        group_wins = path_results[f"{alpha:g}"][
            "production_group_win_counts_vs_bundled_basis"
        ]
        path_results[f"{alpha:g}"]["production_group_sign_test_p_values"] = {
            metric_name: _one_sided_sign_test_p_value(
                wins,
                len(production_groups),
            )
            for metric_name, wins in group_wins.items()
        }

    newest_holdout_group_count = max(
        1,
        int(np.ceil(0.2 * len(production_groups))),
    )
    chronological_training_group_positions = np.arange(
        len(production_groups) - newest_holdout_group_count
    )
    chronological_test_group_positions = np.arange(
        len(production_groups) - newest_holdout_group_count,
        len(production_groups),
    )
    chronological_training_groups = [
        production_groups[int(position)]
        for position in chronological_training_group_positions
    ]
    chronological_test_groups = [
        production_groups[int(position)]
        for position in chronological_test_group_positions
    ]
    chronological_test = np.concatenate(
        [indices for _, indices in chronological_test_groups]
    )
    chronological_density = _group_equal_median(
        selected_density,
        chronological_training_groups,
    )
    chronological_values = np.power(10.0, -chronological_density)
    chronological_base = _group_equal_median(
        [
            density[canonical_names == "GS0"][0]
            for density in selected_density
        ],
        chronological_training_groups,
    )
    chronological_free, chronological_similarity, _ = _fit_aligned_free_basis(
        chronological_density,
        chronological_values,
        chronological_base,
        bundled_basis,
        spec.primary_floor,
        iterations=iterations,
        seed=seed + 10000,
        initialization_count=initialization_count,
    )
    chronological_bases = {
        0.0: _blended_basis(bundled_basis, chronological_free, 0.0),
        selected_alpha: _blended_basis(
            bundled_basis,
            chronological_free,
            selected_alpha,
        ),
    }
    chronological_metrics, chronological_rows = _evaluate_basis_set_on_batches(
        spec,
        batches,
        chronological_test,
        selected_values,
        selected_density,
        canonical_names,
        wavelengths,
        chronological_bases,
        chronological_base,
    )
    chronological_group_rows = {
        alpha: _group_macro_rows(chronological_rows[alpha], batches)
        for alpha in chronological_bases
    }
    chronological_macro_metrics = {
        alpha: _mean_row_metrics(chronological_group_rows[alpha])
        for alpha in chronological_bases
    }

    full_density = _group_equal_median(
        selected_density,
        production_groups,
    )
    full_values = np.power(10.0, -full_density)
    full_base = _group_equal_median(
        [
            density[canonical_names == "GS0"][0]
            for density in selected_density
        ],
        production_groups,
    )
    full_free, full_similarity, full_training_rmse = _fit_aligned_free_basis(
        full_density,
        full_values,
        full_base,
        bundled_basis,
        spec.primary_floor,
        iterations=iterations,
        seed=seed + 20000,
        initialization_count=initialization_count,
    )
    bundled_channel_scales = np.maximum(
        np.max(bundled_basis, axis=0),
        1e-12,
    )
    raw_final_shape = EVALUATION._normalize_basis(
        (1.0 - selected_alpha)
        * (bundled_basis / bundled_channel_scales)
        + selected_alpha * EVALUATION._normalize_basis(full_free)
    )
    raw_final_basis = raw_final_shape * bundled_channel_scales
    final_basis = _blended_basis(
        bundled_basis,
        full_free,
        selected_alpha,
    )

    selected_key = f"{selected_alpha:g}"
    selected_result = path_results[selected_key]
    measurement_metric = _measurement_metric_name(spec.measurement_kind)
    improvement_minima_percent = {
        "density_rmse_D": 10.0,
        measurement_metric: 5.0,
        "delta_e_2000_median": 5.0,
        "delta_e_2000_mean": 5.0,
        "delta_e_2000_p95": 2.0,
    }
    required_metrics = tuple(improvement_minima_percent)
    primary_metrics = tuple(
        metric
        for metric in required_metrics
        if metric != "delta_e_2000_p95"
    )
    selected_group_wins = selected_result[
        "production_group_win_counts_vs_bundled_basis"
    ]
    selected_sign_p_values = selected_result[
        "production_group_sign_test_p_values"
    ]
    selected_macro_improvement = selected_result[
        "production_group_macro_improvement_percent_vs_bundled_basis"
    ]
    selected_micro_improvement = selected_result[
        "improvement_percent_vs_bundled_basis"
    ]
    selected_group_maximum_regression = {
        metric: _maximum_relative_regression_percent(
            production_group_rows[0.0],
            production_group_rows[selected_alpha],
            metric,
        )
        for metric in required_metrics
    }
    chronological_improvement = _metric_improvements(
        chronological_metrics[0.0],
        chronological_metrics[selected_alpha],
    )
    chronological_macro_improvement = _metric_improvements(
        chronological_macro_metrics[0.0],
        chronological_macro_metrics[selected_alpha],
    )
    chronological_group_wins = _basis_win_counts(
        chronological_group_rows[0.0],
        chronological_group_rows[selected_alpha],
    )
    chronological_group_maximum_regression = {
        metric: _maximum_relative_regression_percent(
            chronological_group_rows[0.0],
            chronological_group_rows[selected_alpha],
            metric,
        )
        for metric in required_metrics
    }
    fold_similarity_array = np.asarray(fold_similarities)
    fold_peak_array = np.asarray(fold_peak_wavelengths)
    fold_peak_range_nm = np.ptp(fold_peak_array, axis=0)
    positive_alphas = sorted(alpha for alpha in alphas if alpha > 0.0)
    selected_is_smallest_positive_alpha = bool(
        positive_alphas and selected_alpha == positive_alphas[0]
    )
    gate_passes = bool(
        selected_is_smallest_positive_alpha
        and selected_alpha <= 0.25
        and all(
            selected_micro_improvement.get(metric, -np.inf) >= minimum
            and selected_macro_improvement.get(metric, -np.inf) >= minimum
            for metric, minimum in improvement_minima_percent.items()
        )
        and all(
            selected_sign_p_values[metric] <= 0.05
            for metric in primary_metrics
        )
        and all(
            selected_group_maximum_regression[metric] <= 5.0
            for metric in required_metrics
        )
        and all(value > 0.0 for value in chronological_improvement.values())
        and all(
            value > 0.0 for value in chronological_macro_improvement.values()
        )
        and all(
            chronological_group_wins[metric]
            == newest_holdout_group_count
            for metric in primary_metrics
        )
        and chronological_group_maximum_regression["delta_e_2000_p95"] <= 5.0
        and np.all(fold_similarity_array >= 0.98)
        and np.all(full_similarity >= 0.99)
        and np.all(fold_peak_range_nm <= 20.0)
    )
    result = {
        "semantics": (
            "Non-negative effective rank-3 generators aligned to bundled C/M/Y; "
            "not uniquely identified analytical dyes."
        ),
        "training_target": (
            "per-patch wavelength-wise archive median within PROD_DATE, then "
            "group-equal median density across training production proxies"
        ),
        "archive_count": len(batches),
        "production_group_count": len(production_groups),
        "production_groups": [
            {
                "production_group": key,
                "archive_ids": [
                    batches[int(index)].batch_id for index in indices
                ],
            }
            for key, indices in production_groups
        ],
        "outer_split": (
            f"{folds} contiguous chronological PROD_DATE-group folds; complete "
            "groups are held out"
        ),
        "outer_fold_test_groups": fold_test_groups,
        "iterations": iterations,
        "initialization_count": initialization_count,
        "alpha_path": list(alphas),
        "selected_alpha": selected_alpha,
        "selection_rule": (
            "Configured smallest positive alpha; project-policy effect-size, "
            "production-group sign-test, maximum-regression, newest-group, "
            "basis-similarity, and peak-stability gates. These thresholds are "
            "project policy, not ISO requirements."
        ),
        "nonnegative_constraint": {
            "baseline": (
                "actual bundled basis retained unchanged for alpha 0 validation"
            ),
            "candidate_path": (
                "positive-alpha shape blends projected non-negative, normalized "
                "as shapes, then restored to bundled per-channel peak scale"
            ),
            "bundled_channel_scales_D": bundled_channel_scales.tolist(),
            "selected_raw_blend_negative_value_count": int(
                np.sum(raw_final_basis < 0.0)
            ),
            "selected_raw_blend_minimum_D": float(np.min(raw_final_basis)),
            "selected_projection_maximum_adjustment_D": float(
                np.max(np.abs(final_basis - raw_final_basis))
            ),
        },
        "path_results": path_results,
        "free_basis_fold_mean_cosine_similarity_to_bundled": np.mean(
            fold_similarities,
            axis=0,
        ).tolist(),
        "free_basis_peak_wavelengths_nm_by_fold": np.asarray(
            fold_peak_wavelengths
        ).tolist(),
        "free_basis_peak_range_nm_by_channel": fold_peak_range_nm.tolist(),
        "free_basis_fold_minimum_cosine_similarity_to_bundled": np.min(
            fold_similarity_array,
            axis=0,
        ).tolist(),
        "free_basis_training_rmse_D_by_fold": fold_training_rmse,
        "chronological_newest_production_group_holdout": {
            "training_production_groups": [
                key for key, _ in chronological_training_groups
            ],
            "test_production_groups": [
                key for key, _ in chronological_test_groups
            ],
            "test_batches": [
                batches[int(index)].batch_id for index in chronological_test
            ],
            "train_test_production_groups_disjoint": bool(
                set(key for key, _ in chronological_training_groups).isdisjoint(
                    key for key, _ in chronological_test_groups
                )
            ),
            "free_basis_cosine_similarity_to_bundled": (
                chronological_similarity.tolist()
            ),
            "models": {
                "bundled_basis": chronological_metrics[0.0],
                "selected_effective_basis": chronological_metrics[selected_alpha],
            },
            "production_group_macro_models": {
                "bundled_basis": chronological_macro_metrics[0.0],
                "selected_effective_basis": (
                    chronological_macro_metrics[selected_alpha]
                ),
            },
            "improvement_percent": chronological_improvement,
            "production_group_macro_improvement_percent": (
                chronological_macro_improvement
            ),
            "production_group_win_counts": chronological_group_wins,
            "production_group_maximum_regression_percent": (
                chronological_group_maximum_regression
            ),
        },
        "final_full_dataset_fit": {
            "free_basis_cosine_similarity_to_bundled": full_similarity.tolist(),
            "free_basis_training_rmse_D": full_training_rmse,
            "selected_basis_peak_wavelengths_nm": wavelengths[
                np.argmax(final_basis, axis=0)
            ].tolist(),
        },
        "candidate_gate": {
            "reconstruction_passes": gate_passes,
            "passes": False,
            "channel_candidate_may_be_emitted": False,
            "runtime_status": "pending",
            "default_replacement_authorized": False,
            "policy_origin": (
                "Spektrafilm conservative engineering policy; not an ISO or "
                "paper-prescribed threshold"
            ),
            "minimum_improvement_percent_for_micro_and_group_macro": (
                improvement_minima_percent
            ),
            "maximum_allowed_single_group_regression_percent": 5.0,
            "maximum_sign_test_p_value": 0.05,
            "minimum_fold_channel_cosine_similarity": 0.98,
            "minimum_full_channel_cosine_similarity": 0.99,
            "maximum_fold_peak_range_nm": 20.0,
            "selected_is_smallest_positive_alpha": (
                selected_is_smallest_positive_alpha
            ),
            "selected_production_group_win_counts": selected_group_wins,
            "selected_production_group_sign_test_p_values": (
                selected_sign_p_values
            ),
            "selected_production_group_maximum_regression_percent": (
                selected_group_maximum_regression
            ),
            "runtime_gate_required_before_emission": True,
            "remaining_blockers": [
                "effective-basis mixing ambiguity",
                "no calibrated exposure-to-dye-amount mapping",
                "raw instrument observations unavailable",
                "derivative redistribution licence unconfirmed",
            ],
        },
    }
    return result, wavelengths, final_basis


def _source_manifest(batches: list[BatchData]) -> tuple[list[dict[str, Any]], str]:
    manifest = [
        {
            "batch": batch.batch_id,
            "production_date": batch.production_date,
            "created": batch.created,
            "archive_sha256": batch.archive_sha256,
            "spectral_content_sha256": _spectral_content_sha256(batch),
            "spectral_member": batch.source_member,
            "raw_zero_value_count": batch.raw_zero_value_count,
        }
        for batch in batches
    ]
    encoded = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return manifest, _sha256_bytes(encoded)


def _build_multibatch_candidate_payload(
    spec: DatasetSpec,
    batches: list[BatchData],
    measured_wavelengths: np.ndarray,
    median_gs0_density: np.ndarray,
    *,
    interpolation: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile_path = PROFILE_DIR / f"{spec.profile_slug}.json"
    original = json.loads(profile_path.read_text(encoding="utf-8"))
    payload = copy.deepcopy(original)
    candidate_base, shared_support, interpolation_summary = (
        EVALUATION._resample_gs0_dmin_to_profile_grid(
            np.asarray(original["data"]["wavelengths"], dtype=float),
            np.asarray(original["data"]["base_density"], dtype=float),
            np.asarray(original["data"]["channel_density"], dtype=float),
            measured_wavelengths,
            median_gs0_density,
            interpolation=interpolation,
        )
    )
    manifest, manifest_sha256 = _source_manifest(batches)
    production_groups = _production_groups(batches)
    source_id = f"COLORREFERENCE_PUBLIC_MULTIBATCH_{spec.key.upper()}_GS0"
    archive_hashes = "; ".join(
        f"{batch.batch_id}={batch.archive_sha256}" for batch in batches
    )
    provenance = payload["metadata"]["provenance"]
    provenance["measurement_status"] = "partial-instrument-data"
    provenance["source_references"][source_id] = (
        f"{len(batches)} exact-MATERIAL public batch-average target archives "
        f"across {len(production_groups)} distinct PROD_DATE groups "
        f"from {PUBLIC_INDEX_URL}; material {spec.material}; archive SHA-256 "
        f"manifest {manifest_sha256}; archives {archive_hashes}; accessed "
        f"{CREATED_DATE}. Public download does not establish derivative-data "
        "redistribution permission."
    )
    previous_sources = provenance["fields"]["base_density"].get("sources", [])
    density_transformation = (
        "per-batch-transmittance-to-base10-density"
        if spec.measurement_kind == "transmission"
        else "per-batch-black-backed-45-0-reflectance-to-effective-base10-density"
    )
    interpolation_transformation = (
        "pchip-10-nm-to-5-nm"
        if interpolation == "pchip"
        else "linear-10-nm-to-5-nm"
    )
    semantic_note = (
        "The result is a product Dmin spectrum, not bare clear support."
        if spec.measurement_kind == "transmission"
        else (
            "The result is an effective black-backed 45/0 reflection Dmin for "
            "the runtime model, not analytical dye or transmission density."
        )
    )
    provenance["fields"]["base_density"] = {
        "origin": "published-measurement",
        "status": "reconstructed",
        "sources": list(dict.fromkeys([*previous_sources, source_id])),
        "derived_from": (
            f"{source_id}:GS0 within shared finite CMY support; "
            f"bundled:{spec.profile_slug}.data.base_density outside shared support"
        ),
        "transformations": [
            "exact-material-public-batch-selection",
            "per-batch-gs0-dmin-extraction",
            density_transformation,
            "leave-one-production-date-group-out-validation",
            "within-production-date-archive-median",
            "group-equal-wavelengthwise-median",
            interpolation_transformation,
            "shared-finite-cmy-support-replacement",
            "outside-shared-cmy-support-retained-from-bundled-profile",
        ],
        "notes": (
            f"Experimental local multibatch candidate. {semantic_note} "
            "The archives remain batch averages from one target-provider "
            "ecosystem; raw instrument observations and an open derivative "
            "licence were not found in the reviewed source materials."
        ),
    }
    provenance["notes"] = (
        provenance.get("notes", "").rstrip()
        + f" Public exact-material multibatch GS0 candidate generated {CREATED_DATE}; "
        "not a bundled default."
    ).strip()

    original_stock = original["info"]["stock"]
    bundled_data_sha256 = _canonical_json_sha256(original["data"])
    analysis_code_sha256 = _analysis_code_sha256()
    candidate_context_sha256 = _canonical_json_sha256(
        {
            "analysis_code_sha256": analysis_code_sha256,
            "bundled_data_sha256": bundled_data_sha256,
            "source_manifest_sha256": manifest_sha256,
        }
    )
    role = "effective_dmin" if spec.measurement_kind == "reflection" else "dmin"
    candidate_id = (
        f"{original_stock}_public_grouped_{role}_{manifest_sha256[:8]}_"
        f"{candidate_context_sha256[:8]}_candidate"
        if interpolation == "pchip"
        else (
            f"{original_stock}_public_grouped_{role}_{manifest_sha256[:8]}_"
            f"{candidate_context_sha256[:8]}_{interpolation}_candidate"
        )
    )
    payload["info"]["stock"] = original_stock
    payload["info"]["name"] = (
        f"{original['info']['name']} (Public Multibatch Median GS0 "
        f"{interpolation.upper()} Candidate)"
    )
    payload["metadata"]["created"] = CREATED_DATE
    payload["metadata"]["license"] = (
        original["metadata"]["license"].rstrip()
        + " This local experimental candidate contains a reconstructed field "
        "derived from public external measurement archives; do not redistribute "
        "it until the external-data and derivative-work permissions are confirmed."
    )
    payload["metadata"]["datasource"] = (
        "Experimental non-default profile candidate. Only data.base_density "
        f"within shared finite CMY support is reconstructed from the median GS0 "
        f"of {len(batches)} public exact-material archives after equal-weight "
        f"aggregation within/across {len(production_groups)} PROD_DATE groups. "
        "Source "
        "spectra are not embedded."
    )
    payload["data"]["base_density"] = candidate_base.tolist()

    current_base = np.asarray(original["data"]["base_density"], dtype=float)
    changed = candidate_base - current_base
    summary = {
        "candidate_id": candidate_id,
        "profile_stock": original_stock,
        "material": spec.material,
        "measurement_kind": spec.measurement_kind,
        "source_batch_count": len(batches),
        "source_archive_count": len(batches),
        "source_production_group_count": len(production_groups),
        "source_production_groups": [
            {
                "production_group": key,
                "archive_ids": [
                    batches[int(index)].batch_id for index in indices
                ],
            }
            for key, indices in production_groups
        ],
        "source_batch_ids": [batch.batch_id for batch in batches],
        "source_manifest": manifest,
        "source_manifest_sha256": manifest_sha256,
        "bundled_data_sha256": bundled_data_sha256,
        "analysis_code_sha256": analysis_code_sha256,
        "candidate_context_sha256": candidate_context_sha256,
        "analysis_software_versions": _analysis_software_versions(),
        "field_changed": "base_density",
        "default_profile_modified": False,
        "changed_point_count": int(np.sum(shared_support)),
        "unchanged_point_count": int(np.sum(~shared_support)),
        "mean_absolute_change_D_on_support": float(
            np.mean(np.abs(changed[shared_support]))
        ),
        "max_absolute_change_D_on_support": float(
            np.max(np.abs(changed[shared_support]))
        ),
        "interpolation": interpolation_summary,
        "provenance_status": "reconstructed",
        "measurement_status": provenance["measurement_status"],
    }
    return payload, summary


def _resample_effective_basis_to_profile_grid(
    profile_wavelengths: np.ndarray,
    current_channel_density: np.ndarray,
    measured_wavelengths: np.ndarray,
    effective_basis: np.ndarray,
    *,
    interpolation: str,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    from scipy.interpolate import PchipInterpolator

    if interpolation not in {"pchip", "linear"}:
        raise ValueError("Interpolation must be 'pchip' or 'linear'")
    profile_wavelengths = np.asarray(profile_wavelengths, dtype=float)
    current_channel_density = np.asarray(current_channel_density, dtype=float)
    measured_wavelengths = np.asarray(measured_wavelengths, dtype=float)
    effective_basis = np.asarray(effective_basis, dtype=float)
    if current_channel_density.shape != (len(profile_wavelengths), 3):
        raise ValueError("Current channel density must have shape (wavelengths, 3)")
    if effective_basis.shape != (len(measured_wavelengths), 3):
        raise ValueError("Effective basis must have shape (measured wavelengths, 3)")
    if np.any(np.diff(measured_wavelengths) <= 0):
        raise ValueError("Measured wavelengths must be strictly increasing")
    if not np.all(np.isfinite(effective_basis)) or np.any(effective_basis < 0.0):
        raise ValueError("Effective basis must be finite and non-negative")

    bundled_support = np.all(np.isfinite(current_channel_density), axis=1)
    replacement_support = (
        bundled_support
        & (profile_wavelengths >= measured_wavelengths[0])
        & (profile_wavelengths <= measured_wavelengths[-1])
    )
    if not np.any(replacement_support):
        raise ValueError("Effective basis does not overlap bundled CMY support")
    target_wavelengths = profile_wavelengths[replacement_support]
    current_on_measured_grid = np.column_stack(
        [
            np.interp(
                measured_wavelengths,
                profile_wavelengths[bundled_support],
                current_channel_density[bundled_support, channel],
            )
            for channel in range(3)
        ]
    )
    measured_delta = effective_basis - current_on_measured_grid
    current_target = current_channel_density[replacement_support]
    pchip_values = current_target + np.column_stack(
        [
            PchipInterpolator(
                measured_wavelengths,
                measured_delta[:, channel],
                extrapolate=False,
            )(target_wavelengths)
            for channel in range(3)
        ]
    )
    linear_values = current_target + np.column_stack(
        [
            np.interp(
                target_wavelengths,
                measured_wavelengths,
                measured_delta[:, channel],
            )
            for channel in range(3)
        ]
    )
    roundoff_tolerance = 1e-12
    pchip_negative_count = int(np.sum(pchip_values < 0.0))
    linear_negative_count = int(np.sum(linear_values < 0.0))
    minimum_interpolated_value = float(
        min(np.min(pchip_values), np.min(linear_values))
    )
    if minimum_interpolated_value < -roundoff_tolerance:
        raise ValueError(
            "Interpolation produced a materially negative effective basis: "
            f"{minimum_interpolated_value:.12g} D"
        )
    # PCHIP can produce a negative signed zero at a non-negative endpoint.
    # Correct only sub-picodensity numerical roundoff and report it explicitly.
    pchip_values = np.maximum(pchip_values, 0.0)
    linear_values = np.maximum(linear_values, 0.0)

    original_channel_peaks = np.max(
        current_channel_density[bundled_support],
        axis=0,
    )

    def restore_channel_peak(values: np.ndarray) -> tuple[np.ndarray, list[float]]:
        restored = values.copy()
        scale_factors: list[float] = []
        outside_support = bundled_support & ~replacement_support
        for channel in range(3):
            replacement_peak = float(np.max(restored[:, channel]))
            outside_peak = (
                float(np.max(current_channel_density[outside_support, channel]))
                if np.any(outside_support)
                else -np.inf
            )
            if replacement_peak >= outside_peak:
                scale = float(
                    original_channel_peaks[channel]
                    / max(replacement_peak, 1e-12)
                )
                restored[:, channel] *= scale
            else:
                scale = 1.0
            scale_factors.append(scale)
        return restored, scale_factors

    pchip_values, pchip_peak_scales = restore_channel_peak(pchip_values)
    linear_values, linear_peak_scales = restore_channel_peak(linear_values)
    selected_values = pchip_values if interpolation == "pchip" else linear_values
    if not np.all(np.isfinite(selected_values)) or np.any(selected_values < 0.0):
        raise ValueError("Interpolation produced an invalid effective basis")
    candidate = current_channel_density.copy()
    candidate[replacement_support] = selected_values
    candidate_channel_peaks = np.max(candidate[bundled_support], axis=0)
    outside_unchanged = bool(
        np.array_equal(
            candidate[~replacement_support],
            current_channel_density[~replacement_support],
            equal_nan=True,
        )
    )
    return candidate, replacement_support, {
        "method": interpolation,
        "interpolation_target": (
            "effective-minus-bundled shape delta, added to original 5 nm basis"
        ),
        "source_interval_nm": float(np.median(np.diff(measured_wavelengths))),
        "target_interval_nm": float(np.median(np.diff(profile_wavelengths))),
        "replacement_point_count": int(np.sum(replacement_support)),
        "replacement_range_nm": [
            float(target_wavelengths[0]),
            float(target_wavelengths[-1]),
        ],
        "pchip_vs_linear_mean_absolute_difference_D": float(
            np.mean(np.abs(pchip_values - linear_values))
        ),
        "pchip_vs_linear_max_absolute_difference_D": float(
            np.max(np.abs(pchip_values - linear_values))
        ),
        "negative_interpolation_roundoff": {
            "tolerance_D": roundoff_tolerance,
            "minimum_before_correction_D": minimum_interpolated_value,
            "pchip_corrected_value_count": pchip_negative_count,
            "linear_corrected_value_count": linear_negative_count,
            "material_negative_values_allowed": False,
        },
        "channel_peak_scale_restoration": {
            "original_channel_peaks_D": original_channel_peaks.tolist(),
            "pchip_scale_factors": pchip_peak_scales,
            "linear_scale_factors": linear_peak_scales,
            "selected_candidate_channel_peaks_D": (
                candidate_channel_peaks.tolist()
            ),
            "selected_peak_max_absolute_difference_D": float(
                np.max(
                    np.abs(candidate_channel_peaks - original_channel_peaks)
                )
            ),
        },
        "zero_delta_identity_max_absolute_difference_D": 0.0,
        "outside_measured_range": "retained from bundled channel_density",
        "outside_measured_range_exactly_unchanged": outside_unchanged,
    }


def _build_effective_basis_candidate_payload(
    spec: DatasetSpec,
    batches: list[BatchData],
    base_wavelengths: np.ndarray,
    median_gs0_density: np.ndarray,
    basis_wavelengths: np.ndarray,
    effective_basis: np.ndarray,
    *,
    selected_alpha: float,
    interpolation: str,
    basis_config: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if spec.measurement_kind != "transmission":
        raise ValueError("Effective CMY basis candidates are transmission-only")
    payload, base_summary = _build_multibatch_candidate_payload(
        spec,
        batches,
        base_wavelengths,
        median_gs0_density,
        interpolation=interpolation,
    )
    profile_wavelengths = np.asarray(payload["data"]["wavelengths"], dtype=float)
    current_channel_density = np.asarray(
        payload["data"]["channel_density"],
        dtype=float,
    )
    candidate_channels, replacement_support, interpolation_summary = (
        _resample_effective_basis_to_profile_grid(
            profile_wavelengths,
            current_channel_density,
            basis_wavelengths,
            effective_basis,
            interpolation=interpolation,
        )
    )
    source_id = (
        f"COLORREFERENCE_PUBLIC_MULTIBATCH_{spec.key.upper()}_PATCH_SPECTRA"
    )
    interpolation_transformation = (
        "pchip-10-nm-to-5-nm"
        if interpolation == "pchip"
        else "linear-10-nm-to-5-nm"
    )
    provenance = payload["metadata"]["provenance"]
    manifest_sha256 = base_summary["source_manifest_sha256"]
    provenance["source_references"][source_id] = (
        f"All non-GS0 patch spectra from {len(batches)} exact-MATERIAL public "
        f"target archives at {PUBLIC_INDEX_URL}; material {spec.material}; "
        f"archive manifest SHA-256 {manifest_sha256}; accessed {CREATED_DATE}. "
        "PROD_DATE groups receive equal training weight. Public download does "
        "not establish derivative-data redistribution permission."
    )
    previous_channel_provenance = provenance["fields"]["channel_density"]
    previous_channel_sources = previous_channel_provenance.get("sources", [])
    previous_channel_origin = previous_channel_provenance.get(
        "origin",
        "unknown",
    )
    provenance["fields"]["channel_density"] = {
        "origin": previous_channel_origin,
        "status": "reconstructed",
        "sources": list(
            dict.fromkeys([*previous_channel_sources, source_id])
        ),
        "derived_from": f"bundled:{spec.profile_slug}.data.channel_density",
        "transformations": [
            "exact-material-public-batch-selection",
            "canonical-patch-name-row-alignment",
            "within-production-date-archive-median",
            "group-equal-per-patch-wavelengthwise-density-median",
            "non-negative-rank-3-effective-basis-fit",
            "permutation-alignment-to-bundled-cmy",
            "shape-only-per-channel-unit-peak-normalization",
            f"conservative-{selected_alpha:g}-blend-from-bundled-to-free-basis",
            "nonnegative-projection-after-positive-alpha-blend",
            "bundled-per-channel-peak-scale-restoration",
            "chronological-production-date-group-cross-validation",
            f"shape-delta-{interpolation_transformation}",
            "sub-picodensity-negative-interpolation-roundoff-to-zero",
            "outside-measured-range-retained-from-bundled-profile",
        ],
        "notes": (
            "Experimental hybrid regularized effective spectral generators: "
            f"{1.0 - selected_alpha:g} bundled manufacturer-graph prior plus "
            f"{selected_alpha:g} published-patch-constrained reconstruction "
            "in shape space, "
            "with bundled channel amplitudes retained. They remain mixing "
            "ambiguous and are not analytical dye spectra. No calibrated "
            "exposure-to-dye-amount mapping supports changing characteristic "
            "curves or midscale neutral density."
        ),
    }
    serialized_channels = copy.deepcopy(payload["data"]["channel_density"])
    for index in np.flatnonzero(replacement_support):
        serialized_channels[int(index)] = candidate_channels[int(index)].tolist()
    payload["data"]["channel_density"] = serialized_channels
    original_stock = payload["info"]["stock"]
    config = dict(basis_config or {})
    config.setdefault("alpha", selected_alpha)
    encoded_config = json.dumps(
        config,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    config_hash = _sha256_bytes(encoded_config)[:8]
    effective_context_sha256 = _canonical_json_sha256(
        {
            "base_candidate_context_sha256": base_summary[
                "candidate_context_sha256"
            ],
            "basis_config": config,
            "selected_alpha": selected_alpha,
        }
    )
    alpha_tag = f"a{int(round(selected_alpha * 100)):03d}"
    candidate_id = (
        f"{original_stock}_public_grouped_effective_basis_{alpha_tag}_"
        f"{manifest_sha256[:8]}_{config_hash}_{effective_context_sha256[:8]}"
        + ("_candidate" if interpolation == "pchip" else f"_{interpolation}_candidate")
    )
    payload["info"]["name"] = (
        payload["info"]["name"].split(" (Public Multibatch", 1)[0]
        + f" (Public Multibatch Effective Basis {interpolation.upper()} Candidate)"
    )
    payload["metadata"]["datasource"] = (
        "Experimental non-default profile candidate. data.base_density is the "
        "exact-material multibatch median GS0; data.channel_density is a "
        f"{selected_alpha:g}-blend toward a cross-batch effective rank-3 basis. "
        "All exposure/sensitivity/curve fields remain bundled and source spectra "
        "are not embedded."
    )
    changed = candidate_channels - current_channel_density
    summary = dict(base_summary)
    summary.update(
        {
            "candidate_id": candidate_id,
            "fields_changed": ["base_density", "channel_density"],
            "field_changed": None,
            "effective_basis_alpha": selected_alpha,
            "basis_config": config,
            "basis_config_sha256_prefix": config_hash,
            "candidate_context_sha256": effective_context_sha256,
            "channel_changed_point_count": int(np.sum(replacement_support)),
            "channel_unchanged_point_count": int(np.sum(~replacement_support)),
            "channel_mean_absolute_change_D_on_support": float(
                np.mean(np.abs(changed[replacement_support]))
            ),
            "channel_max_absolute_change_D_on_support": float(
                np.max(np.abs(changed[replacement_support]))
            ),
            "channel_interpolation": interpolation_summary,
            "channel_semantics": "effective generators; not analytical dyes",
            "characteristic_curves_changed": False,
            "midscale_neutral_density_changed": False,
        }
    )
    return payload, summary


def _runtime_params(spec: DatasetSpec, payload: dict[str, Any]):
    from spektrafilm.profiles.io import profile_from_dict
    from spektrafilm.runtime.params_builder import digest_params, init_params
    from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec

    if spec.measurement_kind == "transmission":
        params = init_params(
            film_profile=spec.profile_slug,
            print_profile="kodak_portra_endura",
        )
        params.film = profile_from_dict(payload)
        selected_profile = params.film
        hdr_mode = "light_table"
    else:
        params = init_params(
            film_profile="kodak_portra_400",
            print_profile=spec.profile_slug,
        )
        params.print = profile_from_dict(payload)
        selected_profile = params.print
        hdr_mode = "paper"
    if selected_profile.info.stock != spec.profile_slug:
        raise ValueError("Candidate must retain the physical source stock")
    params.debug.lut_mode = True
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.settings.neutral_print_filters_from_database = False
    params.settings.hdr_route_sidecar_policy = "full"
    params.io.output_gamut_compress = OutputGamutCompressSpec(algorithm="off")
    params.io.upscale_factor = 1.0
    params.io.crop = False
    params.io.scan_film = hdr_mode == "light_table"
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = 0.0
    return digest_params(params), hdr_mode


def _run_runtime_payload(
    spec: DatasetSpec,
    payload: dict[str, Any],
    image: np.ndarray,
    neutral_patch_count: int,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    from spektrafilm.runtime.process import Simulator

    params, hdr_mode = _runtime_params(spec, payload)
    result = Simulator(params).process_with_master(image, hdr_mode=hdr_mode)
    if result.route_master is None:
        raise RuntimeError("Runtime candidate validation produced no RouteMaster")
    arrays = {
        "route_linear_rgb": np.asarray(
            result.route_master.route_linear_rgb,
            dtype=float,
        ),
        "route_luminance_y": np.asarray(
            result.route_master.route_luminance_y,
            dtype=float,
        ),
        "density_cmy": np.asarray(result.route_master.density_cmy, dtype=float),
        "sdr_output": np.asarray(result.image, dtype=float),
    }
    neutral_y = arrays["route_luminance_y"].reshape(-1)[:neutral_patch_count]
    steps = np.diff(neutral_y)
    return arrays, {
        "all_arrays_finite": bool(
            all(np.all(np.isfinite(value)) for value in arrays.values())
        ),
        "neutral_ramp_monotonic_non_decreasing": bool(np.all(steps >= -1e-12)),
        "neutral_ramp_monotonic_non_increasing": bool(np.all(steps <= 1e-12)),
        "neutral_ramp_minimum_step_y": float(np.min(steps)),
        "neutral_ramp_maximum_step_y": float(np.max(steps)),
        "route_linear_rgb_range": [
            float(np.min(arrays["route_linear_rgb"])),
            float(np.max(arrays["route_linear_rgb"])),
        ],
        "sdr_output_range": [
            float(np.min(arrays["sdr_output"])),
            float(np.max(arrays["sdr_output"])),
        ],
    }


def _evaluate_runtime_candidates(
    spec: DatasetSpec,
    bundled_payload: dict[str, Any],
    pchip_payload: dict[str, Any],
    linear_payload: dict[str, Any],
    *,
    effective_pchip_payload: dict[str, Any] | None = None,
    effective_linear_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    image, neutral_patch_count = EVALUATION._runtime_validation_image()
    payloads = {
        "bundled": bundled_payload,
        "multibatch_pchip": pchip_payload,
        "multibatch_linear": linear_payload,
    }
    if (effective_pchip_payload is None) != (effective_linear_payload is None):
        raise ValueError(
            "Effective PCHIP and linear runtime payloads must be supplied together"
        )
    if effective_pchip_payload is not None:
        payloads.update(
            {
                "effective_basis_pchip": effective_pchip_payload,
                "effective_basis_linear": effective_linear_payload,
            }
        )
    arrays: dict[str, dict[str, np.ndarray]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    for name, payload in payloads.items():
        arrays[name], summaries[name] = _run_runtime_payload(
            spec,
            payload,
            image,
            neutral_patch_count,
        )
    repeat_arrays, _ = _run_runtime_payload(
        spec,
        pchip_payload,
        image,
        neutral_patch_count,
    )
    effective_repeat_max = None
    if effective_pchip_payload is not None:
        effective_repeat_arrays, _ = _run_runtime_payload(
            spec,
            effective_pchip_payload,
            image,
            neutral_patch_count,
        )
        effective_repeat_max = max(
            float(
                np.max(
                    np.abs(
                        arrays["effective_basis_pchip"][name]
                        - repeated
                    )
                )
            )
            for name, repeated in effective_repeat_arrays.items()
        )
    differences = {
        "bundled_to_multibatch_pchip": (
            EVALUATION._summarize_runtime_difference(
                arrays["bundled"],
                arrays["multibatch_pchip"],
            )
        ),
        "pchip_to_linear_interpolation": (
            EVALUATION._summarize_runtime_difference(
                arrays["multibatch_pchip"],
                arrays["multibatch_linear"],
            )
        ),
    }
    if effective_pchip_payload is not None:
        differences.update(
            {
                "bundled_to_effective_basis_pchip": (
                    EVALUATION._summarize_runtime_difference(
                        arrays["bundled"],
                        arrays["effective_basis_pchip"],
                    )
                ),
                "base_only_to_effective_basis_pchip": (
                    EVALUATION._summarize_runtime_difference(
                        arrays["multibatch_pchip"],
                        arrays["effective_basis_pchip"],
                    )
                ),
                "effective_basis_pchip_to_linear_interpolation": (
                    EVALUATION._summarize_runtime_difference(
                        arrays["effective_basis_pchip"],
                        arrays["effective_basis_linear"],
                    )
                ),
            }
        )
    return {
        "route": (
            "positive-film light-table scan"
            if spec.measurement_kind == "transmission"
            else "negative-film optical print and paper scan"
        ),
        "patch_count": int(image.shape[0] * image.shape[1]),
        "neutral_patch_count": neutral_patch_count,
        "profiles": summaries,
        "pchip_repeat_max_absolute_difference": max(
            float(
                np.max(
                    np.abs(arrays["multibatch_pchip"][name] - repeated)
                )
            )
            for name, repeated in repeat_arrays.items()
        ),
        "effective_basis_pchip_repeat_max_absolute_difference": (
            effective_repeat_max
        ),
        "differences": differences,
        "interpretation": (
            "Runtime safety and interpolation sensitivity only; target spectra "
            "validate the effective output basis but do not identify exposure "
            "mapping or analytical dyes."
        ),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--download-public-batches",
        action="store_true",
        help=(
            "Download missing public ColorReference target-reference archives "
            "into the cache."
        ),
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh the official index and cached public archives.",
    )
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument(
        "--measurement-floors",
        type=float,
        nargs="+",
        default=(1e-2, 1e-3),
    )
    parser.add_argument(
        "--candidate-output-dir",
        type=Path,
        default=None,
        help="Write local non-default multibatch candidates to this directory.",
    )
    parser.add_argument(
        "--runtime-validation",
        action="store_true",
        help="Run deterministic runtime QA for bundled/PCHIP/linear profiles.",
    )
    parser.add_argument(
        "--effective-basis-validation",
        action="store_true",
        help=(
            "Cross-validate a conservative effective rank-3 transmission basis "
            "for exact-stock film datasets."
        ),
    )
    parser.add_argument(
        "--emit-effective-basis-candidates",
        action="store_true",
        help=(
            "Write local base+effective-channel candidates only when the "
            "effective-basis evidence gate passes."
        ),
    )
    parser.add_argument("--basis-folds", type=int, default=5)
    parser.add_argument("--basis-iterations", type=int, default=30)
    parser.add_argument("--basis-initializations", type=int, default=3)
    parser.add_argument("--basis-seed", type=int, default=20260713)
    parser.add_argument(
        "--basis-alphas",
        type=float,
        nargs="+",
        default=(0.0, 0.25, 0.5, 0.75, 1.0),
    )
    parser.add_argument("--basis-selected-alpha", type=float, default=0.25)
    parser.add_argument(
        "--report-output",
        type=Path,
        default=None,
        help="Optionally write the complete reproducible JSON report.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not 1 <= args.max_workers <= 12:
        raise ValueError("--max-workers must be between 1 and 12")
    floors = tuple(float(value) for value in args.measurement_floors)
    if not floors or not all(0.0 < value < 1.0 for value in floors):
        raise ValueError("Measurement floors must be between 0 and 1")
    alphas = tuple(dict.fromkeys(float(value) for value in args.basis_alphas))
    if not alphas or not all(np.isfinite(value) for value in alphas):
        raise ValueError("Basis alphas must be finite")
    if 0.0 not in alphas:
        raise ValueError("--basis-alphas must include the bundled baseline 0")
    if not all(0.0 <= value <= 1.0 for value in alphas):
        raise ValueError("Basis alphas must be between 0 and 1")
    if not 0.0 < args.basis_selected_alpha <= 1.0:
        raise ValueError("--basis-selected-alpha must be between 0 and 1")
    if args.basis_selected_alpha not in alphas:
        raise ValueError("--basis-selected-alpha must occur in --basis-alphas")
    if args.basis_folds < 2:
        raise ValueError("--basis-folds must be at least 2")
    if args.basis_iterations < 1 or args.basis_initializations < 1:
        raise ValueError("Basis iterations and initializations must be positive")
    if args.candidate_output_dir is not None and not args.runtime_validation:
        raise ValueError(
            "--candidate-output-dir requires --runtime-validation so candidates "
            "are written only after runtime QA"
        )
    if args.emit_effective_basis_candidates:
        if not args.effective_basis_validation:
            raise ValueError(
                "--emit-effective-basis-candidates requires "
                "--effective-basis-validation"
            )
        if args.candidate_output_dir is None:
            raise ValueError(
                "--emit-effective-basis-candidates requires "
                "--candidate-output-dir"
            )
        if not args.runtime_validation:
            raise ValueError(
                "--emit-effective-basis-candidates requires "
                "--runtime-validation"
            )

    archives, acquisition = _load_or_download_archives(
        args.cache_dir,
        download=args.download_public_batches,
        refresh=args.refresh,
        max_workers=args.max_workers,
    )
    datasets, exclusions = _collect_exact_material_batches(archives)
    results: list[dict[str, Any]] = []
    for spec in DATASET_SPECS:
        batches = datasets[spec.material]
        evaluation, wavelengths, median_base = _evaluate_cross_batch_base(
            spec,
            batches,
            floors=tuple(dict.fromkeys((spec.primary_floor, *floors))),
        )
        base_candidate_gate = _evaluate_base_candidate_gate(spec, evaluation)
        pchip_payload, candidate_summary = _build_multibatch_candidate_payload(
            spec,
            batches,
            wavelengths,
            median_base,
            interpolation="pchip",
        )
        linear_payload, _ = _build_multibatch_candidate_payload(
            spec,
            batches,
            wavelengths,
            median_base,
            interpolation="linear",
        )
        candidate_summary["candidate_gate"] = base_candidate_gate
        candidate_summary["output"] = None
        effective_basis_validation = None
        effective_candidate_summary = None
        effective_pchip_payload = None
        effective_linear_payload = None
        if (
            args.effective_basis_validation
            and spec.measurement_kind == "transmission"
        ):
            (
                effective_basis_validation,
                basis_wavelengths,
                effective_basis,
            ) = _evaluate_effective_basis_path(
                spec,
                batches,
                alphas=alphas,
                folds=args.basis_folds,
                iterations=args.basis_iterations,
                seed=args.basis_seed,
                initialization_count=args.basis_initializations,
                selected_alpha=args.basis_selected_alpha,
            )
            if (
                args.runtime_validation
                and effective_basis_validation["candidate_gate"][
                    "reconstruction_passes"
                ]
            ):
                effective_pchip_payload, effective_candidate_summary = (
                    _build_effective_basis_candidate_payload(
                        spec,
                        batches,
                        wavelengths,
                        median_base,
                        basis_wavelengths,
                        effective_basis,
                        selected_alpha=args.basis_selected_alpha,
                        interpolation="pchip",
                        basis_config={
                            "folds": args.basis_folds,
                            "iterations": args.basis_iterations,
                            "initializations": args.basis_initializations,
                            "seed": args.basis_seed,
                            "alphas": list(alphas),
                        },
                    )
                )
                effective_linear_payload, _ = (
                    _build_effective_basis_candidate_payload(
                        spec,
                        batches,
                        wavelengths,
                        median_base,
                        basis_wavelengths,
                        effective_basis,
                        selected_alpha=args.basis_selected_alpha,
                        interpolation="linear",
                        basis_config={
                            "folds": args.basis_folds,
                            "iterations": args.basis_iterations,
                            "initializations": args.basis_initializations,
                            "seed": args.basis_seed,
                            "alphas": list(alphas),
                        },
                    )
                )
        bundled_payload = json.loads(
            (PROFILE_DIR / f"{spec.profile_slug}.json").read_text(encoding="utf-8")
        )
        runtime = (
            _evaluate_runtime_candidates(
                spec,
                bundled_payload,
                pchip_payload,
                linear_payload,
                effective_pchip_payload=effective_pchip_payload,
                effective_linear_payload=effective_linear_payload,
            )
            if args.runtime_validation
            else None
        )
        if runtime is None:
            base_candidate_gate["runtime_status"] = "not-run"
        else:
            base_runtime_profiles = {
                name: runtime["profiles"][name]
                for name in ("multibatch_pchip", "multibatch_linear")
            }
            base_runtime_checks = {
                "all_arrays_finite": all(
                    profile["all_arrays_finite"]
                    for profile in base_runtime_profiles.values()
                ),
                "neutral_ramp_monotonic_non_decreasing": all(
                    profile["neutral_ramp_monotonic_non_decreasing"]
                    for profile in base_runtime_profiles.values()
                ),
                "pchip_repeat_exact": (
                    runtime["pchip_repeat_max_absolute_difference"] == 0.0
                ),
            }
            base_runtime_passes = all(base_runtime_checks.values())
            base_candidate_gate["runtime_status"] = (
                "passed" if base_runtime_passes else "failed"
            )
            base_candidate_gate["runtime_checks"] = base_runtime_checks
            base_candidate_gate["passes"] = bool(
                base_candidate_gate["reconstruction_passes"]
                and base_runtime_passes
            )
            base_candidate_gate["candidate_may_be_emitted"] = (
                base_candidate_gate["passes"]
            )
            if (
                args.candidate_output_dir is not None
                and base_candidate_gate["passes"]
            ):
                candidate_summary["output"] = EVALUATION._write_candidate_payload(
                    pchip_payload,
                    args.candidate_output_dir,
                    candidate_id=candidate_summary["candidate_id"],
                )
        if effective_basis_validation is not None:
            gate = effective_basis_validation["candidate_gate"]
            if effective_candidate_summary is None or runtime is None:
                gate["runtime_status"] = "not-run-or-reconstruction-gate-failed"
                gate["passes"] = False
                gate["channel_candidate_may_be_emitted"] = False
            else:
                interpolation = effective_candidate_summary[
                    "channel_interpolation"
                ]
                effective_profiles = {
                    name: runtime["profiles"][name]
                    for name in (
                        "effective_basis_pchip",
                        "effective_basis_linear",
                    )
                }
                runtime_checks = {
                    "all_arrays_finite": all(
                        profile["all_arrays_finite"]
                        for profile in effective_profiles.values()
                    ),
                    "neutral_ramp_monotonic_non_decreasing": all(
                        profile["neutral_ramp_monotonic_non_decreasing"]
                        for profile in effective_profiles.values()
                    ),
                    "effective_pchip_repeat_exact": (
                        runtime[
                            "effective_basis_pchip_repeat_max_absolute_difference"
                        ]
                        == 0.0
                    ),
                    "channel_pchip_linear_max_difference_at_most_0_02_D": (
                        interpolation[
                            "pchip_vs_linear_max_absolute_difference_D"
                        ]
                        <= 0.02
                    ),
                    "bundled_channel_peak_scale_preserved": (
                        interpolation["channel_peak_scale_restoration"][
                            "selected_peak_max_absolute_difference_D"
                        ]
                        <= 1e-12
                    ),
                    "outside_measured_range_exactly_unchanged": interpolation[
                        "outside_measured_range_exactly_unchanged"
                    ],
                    "zero_delta_identity_exact": (
                        interpolation[
                            "zero_delta_identity_max_absolute_difference_D"
                        ]
                        == 0.0
                    ),
                }
                runtime_passes = all(runtime_checks.values())
                gate["runtime_status"] = "passed" if runtime_passes else "failed"
                gate["runtime_checks"] = runtime_checks
                gate["passes"] = bool(
                    gate["reconstruction_passes"] and runtime_passes
                )
                gate["channel_candidate_may_be_emitted"] = gate["passes"]
                if args.emit_effective_basis_candidates and gate["passes"]:
                    effective_candidate_summary["output"] = (
                        EVALUATION._write_candidate_payload(
                            effective_pchip_payload,
                            args.candidate_output_dir,
                            candidate_id=effective_candidate_summary[
                                "candidate_id"
                            ],
                        )
                    )
                else:
                    effective_candidate_summary["output"] = None
        results.append(
            {
                "dataset": evaluation,
                "profile_candidate": candidate_summary,
                "effective_basis_validation": effective_basis_validation,
                "effective_basis_candidate": effective_candidate_summary,
                "runtime_validation": runtime,
            }
        )

    report = {
        "method": {
            "source_scope": "public ColorReference target-reference archives",
            "analysis_code_sha256": _analysis_code_sha256(),
            "analysis_software_versions": _analysis_software_versions(),
            "exact_material_matching_required": True,
            "validation_split": (
                "complete PROD_DATE production-proxy groups; no archive from a "
                "held-out group appears in training"
            ),
            "candidate_base": (
                "within-PROD_DATE archive median GS0 density, then group-equal "
                "wavelength-wise median"
            ),
            "density_definition": "D(lambda) = -log10(T or black-backed 45/0 R)",
            "patch_coefficients": "non-negative least squares",
            "channel_density": (
                "bundled and unchanged in base-only candidates; optional "
                "transmission candidates use a gated conservative effective "
                "rank-3 basis and are not analytical dyes"
            ),
            "bundled_profile_arrays_modified": False,
            "candidate_output_requested": args.candidate_output_dir is not None,
            "runtime_validation_requested": args.runtime_validation,
            "effective_basis_validation_requested": (
                args.effective_basis_validation
            ),
            "effective_basis_candidates_requested": (
                args.emit_effective_basis_candidates
            ),
            "licence_status": (
                "no explicit open derivative licence found in the reviewed "
                "index/archive materials; redistribution permission unconfirmed"
            ),
        },
        "acquisition": acquisition,
        "exact_material_exclusions": exclusions,
        "datasets": results,
    }
    if args.candidate_output_dir is not None:
        authoritative_outputs: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for dataset_result in results:
            dataset_name = dataset_result["dataset"]["profile"]
            for candidate_kind, summary_key, gate_key in (
                ("base_density", "profile_candidate", "candidate_gate"),
                ("effective_basis", "effective_basis_candidate", None),
            ):
                summary = dataset_result[summary_key]
                if summary is None:
                    if candidate_kind == "effective_basis" and dataset_result[
                        "effective_basis_validation"
                    ] is not None:
                        gate = dataset_result["effective_basis_validation"][
                            "candidate_gate"
                        ]
                        rejected.append(
                            {
                                "profile": dataset_name,
                                "candidate_kind": candidate_kind,
                                "candidate_id": None,
                                "evaluation_status": (
                                    "evaluated-but-not-built"
                                ),
                                "gate_passes": gate["passes"],
                                "output": None,
                            }
                        )
                    continue
                output = summary.get("output")
                gate = (
                    summary[gate_key]
                    if gate_key is not None
                    else dataset_result["effective_basis_validation"][
                        "candidate_gate"
                    ]
                )
                row = {
                    "profile": dataset_name,
                    "candidate_kind": candidate_kind,
                    "candidate_id": summary["candidate_id"],
                    "candidate_context_sha256": summary.get(
                        "candidate_context_sha256"
                    ),
                    "gate_passes": gate["passes"],
                    "output": output,
                }
                if output is not None and gate["passes"]:
                    authoritative_outputs.append(row)
                else:
                    rejected.append(row)
        candidate_manifest = {
            "created": CREATED_DATE,
            "analysis_code_sha256": _analysis_code_sha256(),
            "analysis_software_versions": _analysis_software_versions(),
            "authoritative_for_this_run": authoritative_outputs,
            "rejected_or_not_emitted": rejected,
            "warning": (
                "Only files listed under authoritative_for_this_run passed the "
                "current grouped evidence and runtime gates. Other files in this "
                "temporary directory may be stale exploratory outputs."
            ),
            "bundled_defaults_modified": False,
        }
        candidate_manifest_path = (
            args.candidate_output_dir / "CURRENT_CANDIDATES.json"
        )
        candidate_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_manifest_encoded = json.dumps(
            candidate_manifest,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        candidate_manifest_bytes = (candidate_manifest_encoded + "\n").encode(
            "utf-8"
        )
        candidate_manifest_path.write_bytes(candidate_manifest_bytes)
        report["candidate_manifest"] = {
            "path": str(candidate_manifest_path.resolve()),
            "sha256": _sha256_bytes(candidate_manifest_bytes),
            "authoritative_candidate_count": len(authoritative_outputs),
        }
    encoded_report = json.dumps(report, indent=2, sort_keys=True)
    if args.report_output is not None:
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text(encoded_report + "\n", encoding="utf-8")
    print(encoded_report)


if __name__ == "__main__":
    main()
