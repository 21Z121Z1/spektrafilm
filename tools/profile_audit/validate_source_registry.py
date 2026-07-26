#!/usr/bin/env python3
"""Validate the JSON source registry of film and paper profiles."""

import json
import os
import sys

# Define target paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY_PATH = os.path.join(PROJECT_ROOT, "tools", "profile_audit", "profile_sources.json")
PROFILES_DIR = os.path.join(PROJECT_ROOT, "src", "spektrafilm", "data", "profiles")

# Expected enums and fields
VALID_CLASSIFICATIONS = {
    "direct-source",
    "source-composite",
    "reconstructed",
    "optimized",
    "generic",
    "derived-from-related-profile",
    "unknown",
    "likely-wrong"
}

VALID_SOURCE_CLASSES = {
    "manufacturer-current",
    "manufacturer-archived",
    "near-official",
    "third-party-measurement",
    "community"
}

REQUIRED_CORE_FIELDS = [
    "wavelengths",
    "log_sensitivity",
    "channel_density",
    "base_density",
    "midscale_neutral_density",
    "log_exposure",
    "density_curves",
    "density_curves_layers",
    "density_curves_model"
]


def load_bundled_profile_slugs():
    """Load the exact list of bundled profile slugs from directory."""
    slugs = []
    for f in os.listdir(PROFILES_DIR):
        if f.endswith(".json"):
            slugs.append(f[:-5])
    return sorted(slugs)


def validate_registry():
    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Registry file not found at {REGISTRY_PATH}")
        return False

    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON format: {e}")
        return False

    errors = []

    # 1. Check top-level keys
    if "sources" not in registry:
        errors.append("Missing top-level 'sources' dictionary.")
    if "profiles" not in registry:
        errors.append("Missing top-level 'profiles' dictionary.")

    # 2. Check sources dictionary
    sources = registry.get("sources", {})
    if not isinstance(sources, dict):
        errors.append("'sources' must be a dictionary.")
    else:
        for source_id, src_info in sources.items():
            for key in ["title", "manufacturer", "source_class"]:
                if key not in src_info:
                    errors.append(f"Source '{source_id}' is missing required field '{key}'.")
            
            src_class = src_info.get("source_class")
            if src_class and src_class not in VALID_SOURCE_CLASSES:
                errors.append(f"Source '{source_id}' has invalid class '{src_class}'. Allowed: {VALID_SOURCE_CLASSES}")

    # 3. Check profiles dictionary
    profiles = registry.get("profiles", {})
    bundled_slugs = load_bundled_profile_slugs()

    # Verify that all bundled profiles are present in registry
    for slug in bundled_slugs:
        if slug not in profiles:
            errors.append(f"Profile '{slug}' is missing from the registry.")

    # Check each profile in registry
    for slug, prof_data in profiles.items():
        if slug not in bundled_slugs:
            errors.append(f"Profile '{slug}' in registry is not bundled in the package.")
            continue

        # Check info
        info = prof_data.get("info", {})
        if "name" not in info or "type" not in info or "support" not in info:
            errors.append(f"Profile '{slug}' is missing 'info' fields (name, type, support).")

        # Check fields dict
        fields = prof_data.get("fields", {})
        if not isinstance(fields, dict):
            errors.append(f"Profile '{slug}' must have a 'fields' dictionary.")
            continue

        for field_name in REQUIRED_CORE_FIELDS:
            if field_name not in fields:
                errors.append(f"Profile '{slug}' is missing field classification for '{field_name}'.")
                continue

            field_info = fields[field_name]
            classification = field_info.get("classification")
            if not classification:
                errors.append(f"Profile '{slug}', field '{field_name}' is missing 'classification'.")
            elif classification not in VALID_CLASSIFICATIONS:
                errors.append(f"Profile '{slug}', field '{field_name}' has invalid classification '{classification}'.")

            # Validate evidence if classification warrants it
            if classification in ["direct-source", "source-composite", "derived-from-related-profile"]:
                evidence = field_info.get("evidence", {})
                if not evidence:
                    errors.append(f"Profile '{slug}', field '{field_name}' has classification '{classification}' but lacks 'evidence'.")
                else:
                    # Check source_id is in sources
                    source_id = evidence.get("source_id")
                    if not source_id and classification != "derived-from-related-profile":
                        errors.append(f"Profile '{slug}', field '{field_name}' evidence is missing 'source_id'.")
                    elif source_id and source_id not in sources:
                        errors.append(f"Profile '{slug}', field '{field_name}' references undefined source_id '{source_id}'.")

                    if classification == "derived-from-related-profile" and not evidence.get("derived_from"):
                        errors.append(f"Profile '{slug}', field '{field_name}' is derived-from-related-profile but lacks 'derived_from' field name/profile.")

            if classification == "unknown":
                search_hist = field_info.get("search_history")
                if not search_hist:
                    errors.append(f"Profile '{slug}', field '{field_name}' is 'unknown' but lacks 'search_history'.")

        # Check refit_spec
        refit_spec = prof_data.get("refit_spec", {})
        if not refit_spec:
            errors.append(f"Profile '{slug}' is missing 'refit_spec'.")
        else:
            if "refit_candidate" not in refit_spec:
                errors.append(f"Profile '{slug}' 'refit_spec' is missing 'refit_candidate' boolean.")
            if "usable_constraints" not in refit_spec or not isinstance(refit_spec["usable_constraints"], list):
                errors.append(f"Profile '{slug}' 'refit_spec' is missing 'usable_constraints' list.")
            if "missing_constraints" not in refit_spec or not isinstance(refit_spec["missing_constraints"], list):
                errors.append(f"Profile '{slug}' 'refit_spec' is missing 'missing_constraints' list.")
            if "recommended_refit_type" not in refit_spec:
                errors.append(f"Profile '{slug}' 'refit_spec' is missing 'recommended_refit_type' string.")

    if errors:
        print(f"Registry validation FAILED with {len(errors)} errors:")
        for err in errors[:30]:
            print(f"  - {err}")
        if len(errors) > 30:
            print(f"  ... and {len(errors) - 30} more errors.")
        return False

    print("Registry validation PASSED.")
    return True


if __name__ == "__main__":
    success = validate_registry()
    sys.exit(0 if success else 1)
