#!/usr/bin/env python3
"""Check that the Markdown provenance matrix matches the JSON source registry exactly."""

import json
import os
import re
import sys

# Define target paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY_PATH = os.path.join(PROJECT_ROOT, "tools", "profile_audit", "profile_sources.json")
MATRIX_MD_PATH = os.path.join(PROJECT_ROOT, "docs", "reports", "profile-field-provenance-matrix-20260704.md")


def parse_markdown_matrix(md_path):
    """Parse rows from the markdown matrix table.
    
    Expected headers:
    | Profile | Field | Source support | Classification | Evidence | Notes | Repair tier |
    """
    if not os.path.exists(md_path):
        print(f"WARNING: Markdown matrix not found at {md_path}")
        return {}

    parsed = {}
    row_re = re.compile(r"^\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$")
    
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith("|"):
            continue
        
        # Skip header and divider lines
        if "Profile" in line and "Field" in line:
            continue
        if "---" in line:
            continue
        
        match = row_re.match(line)
        if match:
            profile_slug = match.group(1).strip()
            field_name = match.group(2).strip()
            classification = match.group(4).strip()
            evidence = match.group(5).strip()
            
            # Clean backticks or formatting
            profile_slug = profile_slug.replace("`", "")
            field_name = field_name.replace("`", "")
            classification = classification.replace("`", "")
            
            if profile_slug not in parsed:
                parsed[profile_slug] = {}
            parsed[profile_slug][field_name] = {
                "classification": classification,
                "evidence": evidence,
                "line_num": i + 1
            }
            
    return parsed


def check_coverage():
    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Registry file not found at {REGISTRY_PATH}. Run validate first.")
        return False
        
    if not os.path.exists(MATRIX_MD_PATH):
        print(f"ERROR: Markdown matrix file not found at {MATRIX_MD_PATH}")
        return False

    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)

    json_profiles = registry.get("profiles", {})
    md_parsed = parse_markdown_matrix(MATRIX_MD_PATH)

    errors = []

    # Verify matching entries
    for slug, json_data in json_profiles.items():
        if slug not in md_parsed:
            errors.append(f"Profile '{slug}' exists in JSON registry but is entirely missing from Markdown matrix.")
            continue
            
        md_fields = md_parsed[slug]
        json_fields = json_data.get("fields", {})

        for field_name, json_finfo in json_fields.items():
            if field_name not in md_fields:
                errors.append(f"Profile '{slug}', field '{field_name}' exists in JSON registry but is missing from Markdown matrix.")
                continue

            md_finfo = md_fields[field_name]
            
            # Check classification matches
            json_cls = json_finfo.get("classification")
            md_cls = md_finfo["classification"]
            
            if json_cls != md_cls:
                errors.append(
                    f"Mismatch in Profile '{slug}', Field '{field_name}' (Markdown line {md_finfo['line_num']}):\n"
                    f"  JSON classification:     '{json_cls}'\n"
                    f"  Markdown classification: '{md_cls}'"
                )

            # Check basic evidence consistency
            json_evidence = json_finfo.get("evidence", {})
            md_evidence = md_finfo["evidence"].strip()
            
            if json_cls in ["direct-source", "source-composite"]:
                source_id = json_evidence.get("source_id", "")
                if source_id and source_id not in md_evidence:
                    errors.append(
                        f"Mismatch in Profile '{slug}', Field '{field_name}' (Markdown line {md_finfo['line_num']}):\n"
                        f"  JSON references source_id '{source_id}', but Markdown evidence field does not mention it (Got: '{md_evidence}')."
                    )

    # Check for items in Markdown that aren't in JSON
    for slug, md_fields in md_parsed.items():
        if slug not in json_profiles:
            errors.append(f"Profile '{slug}' exists in Markdown matrix but is missing from JSON registry.")
            continue
        for field_name in md_fields:
            if field_name not in json_profiles[slug].get("fields", {}):
                errors.append(f"Profile '{slug}', field '{field_name}' exists in Markdown matrix but is missing from JSON registry.")

    if errors:
        print(f"Markdown alignment validation FAILED with {len(errors)} errors:")
        for err in errors[:30]:
            print(f"  - {err}")
        if len(errors) > 30:
            print(f"  ... and {len(errors) - 30} more errors.")
        return False

    print("Markdown alignment validation PASSED.")
    return True


if __name__ == "__main__":
    success = check_coverage()
    sys.exit(0 if success else 1)
