#!/usr/bin/env python3
"""Correct data/commander_catalogue.json using data/raw/oracle-cards.jsonl.

This script intentionally uses oracle-cards.jsonl as its only Scryfall source.
It preserves the catalogue's commander membership and image_urls while
correcting display fields that disagree with the source data.

For multi-faced cards, face-level values are joined with " // " where needed.
For mana costs, trailing faces with no mana cost are omitted from the display.

Run from any directory:
    python scripts/correct_commander_catalogue.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "data" / "raw" / "oracle-cards.jsonl"
TARGET_PATH = ROOT / "data" / "commander_catalogue.json"

DISPLAY_FIELDS = ("mana_cost", "type_line")


def log(message: str) -> None:
    print(f"[commander-catalogue] {message}", flush=True)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)

    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object at its root.")

    return value


def load_oracle_source(
    path: Path,
) -> tuple[dict[str, dict[str, Any]], int]:
    by_oracle_id: dict[str, dict[str, Any]] = {}
    issues = 0
    total = 0

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue

            total += 1

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                issues += 1
                log(
                    f"WARNING: malformed source JSON at line "
                    f"{line_number}: {exc.msg}"
                )
                continue

            if not isinstance(record, dict):
                issues += 1
                log(
                    f"WARNING: source record at line {line_number} "
                    "is not a JSON object."
                )
                continue

            oracle_id = record.get("oracle_id")

            if not oracle_id:
                issues += 1
                log(
                    f"WARNING: source record at line {line_number} "
                    "has no oracle_id."
                )
                continue

            if oracle_id in by_oracle_id:
                issues += 1
                log(f"WARNING: duplicate source oracle_id: {oracle_id}")
                continue

            by_oracle_id[oracle_id] = record

    log(
        f"Loaded {len(by_oracle_id):,} source records "
        f"from {path.relative_to(ROOT)}."
    )

    return by_oracle_id, issues


def expected_display_value(
    source: dict[str, Any],
    field: str,
) -> tuple[str | None, bool]:
    """Return the expected display value and whether it was resolvable.

    For multi-faced cards, use card_faces in source order.

    For mana_cost specifically, omit trailing faces that have no mana cost.
    This makes a transforming card with a cost on its front face and no cost
    on its back face display only the front-face cost.

    Empty strings are valid values. None means the field could not be
    resolved reliably from the source.
    """
    faces = source.get("card_faces")

    if not isinstance(faces, list) or len(faces) < 2:
        value = source.get(field)

        if value is None:
            return None, False

        return str(value), True

    values: list[str] = []

    for face_number, face in enumerate(faces, 1):
        if not isinstance(face, dict):
            return None, False

        value = face.get(field)

        if value is None:
            return None, False

        values.append(str(value).strip())

    if field == "mana_cost":
        # Remove trailing faces with no mana cost, without changing the
        # relative order of any faces that do have a cost.
        while values and values[-1] == "":
            values.pop()

        # If every face has an empty cost, represent that as an empty string.
        if not values:
            return "", True

    return " // ".join(values), True


def validate_catalogue(
    commanders: list[Any],
    original_ids: set[str],
) -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()

    for index, card in enumerate(commanders):
        if not isinstance(card, dict):
            issues.append(f"commander record #{index + 1} is not an object")
            continue

        oracle_id = card.get("oracle_id")

        if not oracle_id:
            issues.append(f"commander record #{index + 1} has no oracle_id")
            continue

        if oracle_id in seen:
            issues.append(f"duplicate commander oracle_id: {oracle_id}")

        seen.add(oracle_id)

        mana_cost = card.get("mana_cost")
        if isinstance(mana_cost, str) and mana_cost.endswith(" // "):
            issues.append(
                f"{card.get('name', oracle_id)}: mana_cost has a trailing "
                '" // " delimiter'
            )

    if seen != original_ids:
        missing = len(original_ids - seen)
        added = len(seen - original_ids)
        issues.append(
            f"commander membership changed (missing={missing}, added={added})"
        )

    return issues


def write_temp_json(target: Path, payload: dict[str, Any]) -> Path:
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return temp_path


def main() -> int:
    log("Starting correction.")

    for required in (SOURCE_PATH, TARGET_PATH):
        if not required.is_file():
            log(f"ERROR: required file not found: {required}")
            return 1

    try:
        source_by_id, source_issues = load_oracle_source(SOURCE_PATH)
        document = load_json(TARGET_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        log(f"ERROR: could not load input: {exc}")
        return 1

    commanders = document.get("commanders")

    if not isinstance(commanders, list):
        log(
            "ERROR: commander_catalogue.json does not contain "
            "a 'commanders' array."
        )
        return 1

    original_ids = {
        card.get("oracle_id")
        for card in commanders
        if isinstance(card, dict) and card.get("oracle_id")
    }

    log(f"Reviewing {len(commanders):,} commander listings.")

    updated_fields = 0
    mismatches_found = 0
    corrected_fields = 0
    attention: list[str] = []

    for number, card in enumerate(commanders, 1):
        if number % 500 == 0:
            log(f"Reviewed {number:,}/{len(commanders):,} commanders...")

        if not isinstance(card, dict):
            attention.append(
                f"commander record #{number} is not a JSON object"
            )
            log(f"WARNING: commander record #{number} cannot be corrected.")
            continue

        oracle_id = card.get("oracle_id")
        display_name = card.get("name") or f"record #{number}"

        if not oracle_id:
            attention.append(f"{display_name}: missing oracle_id")
            log(
                f"WARNING: {display_name} has no oracle_id; "
                "cannot compare it with the source."
            )
            continue

        source = source_by_id.get(oracle_id)

        if source is None:
            issue = f"{display_name}: no matching source record for {oracle_id}"
            attention.append(issue)
            log(f"WARNING: {issue}; listing was not corrected.")
            continue

        for field in DISPLAY_FIELDS:
            expected, resolvable = expected_display_value(source, field)

            if not resolvable:
                issue = (
                    f"{display_name}: could not resolve source "
                    f"{field}; existing value was left unchanged"
                )
                attention.append(issue)
                log(f"WARNING: {issue}.")
                continue

            current = card.get(field)

            if current == expected:
                continue

            mismatches_found += 1
            log(
                f"MISMATCH: {display_name} [{oracle_id}] field '{field}' "
                f"was {current!r}; source expects {expected!r}."
            )

            # Correct the display field using the source-derived value.
            card[field] = expected
            updated_fields += 1
            corrected_fields += 1

            log(
                f"CORRECTED: {display_name} field '{field}' "
                f"set to {expected!r}."
            )

    log(
        f"Found {mismatches_found} display-field mismatch(es); "
        f"corrected {corrected_fields}."
    )

    validation_issues = validate_catalogue(commanders, original_ids)

    if validation_issues:
        for issue in validation_issues[:25]:
            log(f"VALIDATION ERROR: {issue}")

        log("ERROR: validation failed; original file was not replaced.")
        return 1

    log(
        "Validating proposed JSON and confirming commander membership "
        "is unchanged..."
    )

    metadata = document.setdefault("metadata", {})

    if isinstance(metadata, dict):
        metadata["correction_source"] = "data/raw/oracle-cards.jsonl"
        metadata["correction_script"] = (
            "scripts/correct_commander_catalogue.py"
        )

    temp_path: Path | None = None

    try:
        temp_path = write_temp_json(TARGET_PATH, document)

        with temp_path.open("r", encoding="utf-8") as handle:
            round_trip = json.load(handle)

        if not isinstance(round_trip, dict):
            raise ValueError("temporary file root is not a JSON object")

        round_trip_commanders = round_trip.get("commanders")

        if not isinstance(round_trip_commanders, list):
            raise ValueError(
                "temporary file failed structural validation: "
                "'commanders' is not an array"
            )

        round_trip_issues = validate_catalogue(
            round_trip_commanders,
            original_ids,
        )

        if round_trip_issues:
            raise ValueError(
                "temporary file failed validation: "
                + "; ".join(round_trip_issues[:5])
            )

        os.replace(temp_path, TARGET_PATH)
        temp_path = None

    except Exception as exc:
        log(
            f"ERROR: could not safely replace {TARGET_PATH.name}: {exc}"
        )
        return 1

    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    log(f"Completed: {len(commanders):,} commander listings preserved.")
    log(f"{updated_fields} display-field update(s) applied.")

    unresolved_count = len(attention) + source_issues

    if unresolved_count:
        log(
            f"WARNING: {unresolved_count} item(s) still need attention; "
            "the script could not resolve all issues automatically."
        )

        if attention:
            log("Attention items (first 25):")
            for issue in attention[:25]:
                log(f"  - {issue}")

        if source_issues:
            log(
                f"{source_issues} source-data issue(s) were encountered; "
                "inspect the source warnings above."
            )
    else:
        log("Validation complete: no unresolved attention items.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(
            "\n[commander-catalogue] Interrupted; "
            "existing JSON file was not replaced.",
            file=sys.stderr,
        )
        raise SystemExit(130)