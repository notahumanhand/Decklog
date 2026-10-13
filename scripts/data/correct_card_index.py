#!/usr/bin/env python3
"""Correct data/card_index.json using data/raw/oracle-cards.jsonl.

This script intentionally uses oracle-cards.jsonl as its only Scryfall source.
It does not depend on default-cards.jsonl.

Changes:
- removes art-series, memorabilia, and identified non-gameplay listings;
- adds structured card_faces data for multi-faced gameplay cards;
- keeps existing top-level values intact instead of guessing face-specific values;
- reports existing listings that cannot be matched to the source;
- reports eligible source cards missing from the index;
- validates the proposed result and writes to a temporary file before replacing
  data/card_index.json.

Run from any directory:
    python scripts/correct_card_index.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "data" / "raw" / "oracle-cards.jsonl"
TARGET_PATH = ROOT / "data" / "card_index.json"

# These layouts represent non-gameplay objects or auxiliary game pieces.
# "double_faced_token" is included because the index is intended to represent
# gameplay cards, not token listings.
NON_GAMEPLAY_LAYOUTS = {
    "art_series",
    "token",
    "double_faced_token",
    "emblem",
    "scheme",
    "planar",
    "vanguard",
    "phenomenon",
    "plane",
    "conspiracy",
    "augment",
    "host",
}

# Some special layouts are valid gameplay cards and must remain in the index.
# In particular, transform, modal_dfc, split, adventure, battle, saga, class,
# leveler, flip, meld, aftermath, mutate, prototype, and case are not removed
# solely because of their layout.
REFERENCE_TYPE_LINES = {
    "card",
    "card // card",
    "double-faced substitute card",
}

# Names used by checklists and other non-gameplay reference listings.
REFERENCE_NAME_PATTERNS = (
    re.compile(r"\bchecklist\b", re.IGNORECASE),
    re.compile(r"\bsubstitute card\b", re.IGNORECASE),
    re.compile(r"\(cont['’]?d\)", re.IGNORECASE),
)

# These are auxiliary markers/reference cards rather than ordinary gameplay
# cards. Match complete normalized names to avoid broad substring removals.
REFERENCE_NAMES = {
    "acorn stash",
    "beyond booster blitz",
    "booster blitz",
    "city's blessing",
    "companion",
    "day // night",
    "energy reserve",
    "experience",
    "foretell",
    "on an adventure",
    "plot",
    "poison counter",
    "radiation",
    "red mana",
    "storm counter",
    "the monarch",
    "ticket bucket-bot",
}


def log(message: str) -> None:
    print(f"[card-index] {message}", flush=True)


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

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue

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


def is_non_gameplay_representation(
    source: dict[str, Any],
) -> tuple[bool, str | None]:
    """Return whether a source record should be removed and why."""
    layout = str(source.get("layout") or "").strip().lower()
    set_type = str(source.get("set_type") or "").strip().lower()
    type_line = str(source.get("type_line") or "").strip().lower()
    name = str(source.get("name") or "").strip()
    normalized_name = name.casefold()

    if layout == "art_series":
        return True, "art-series layout"

    if set_type == "memorabilia":
        return True, "memorabilia set"

    if layout in NON_GAMEPLAY_LAYOUTS:
        return True, f"non-gameplay layout '{layout}'"

    if type_line in REFERENCE_TYPE_LINES:
        return True, f"reference type line '{source.get('type_line')}'"

    for pattern in REFERENCE_NAME_PATTERNS:
        if pattern.search(name):
            return True, f"reference listing name '{name}'"

    if normalized_name in REFERENCE_NAMES:
        return True, f"reference/game-marker listing '{name}'"

    # Bounty cards are auxiliary components from a special multiplayer
    # product, not ordinary deckbuilding cards.
    if normalized_name.startswith("bounty:") and "// wanted!" in normalized_name:
        return True, "Bounty/Wanted auxiliary listing"

    return False, None


def face_value(face: dict[str, Any], key: str) -> Any:
    # Preserve meaningful empty strings (for example, a land's empty mana cost).
    return face[key] if key in face else None


def build_card_faces(
    source: dict[str, Any],
) -> list[dict[str, Any]] | None:
    faces = source.get("card_faces")

    if not isinstance(faces, list) or len(faces) < 2:
        return None

    normalized: list[dict[str, Any]] = []

    for face in faces:
        if not isinstance(face, dict):
            continue

        normalized.append({
            "name": face_value(face, "name"),
            "mana_cost": face_value(face, "mana_cost"),
            "type_line": face_value(face, "type_line"),
            "oracle_text": face_value(face, "oracle_text"),
            "colors": face_value(face, "colors"),
        })

    return normalized if len(normalized) >= 2 else None


def validate_cards(cards: list[Any]) -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()

    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            issues.append(f"result record #{index + 1} is not an object")
            continue

        oracle_id = card.get("oracle_id")

        if not oracle_id:
            issues.append(f"result record #{index + 1} has no oracle_id")
            continue

        if oracle_id in seen:
            issues.append(f"duplicate oracle_id in result: {oracle_id}")

        seen.add(oracle_id)

        faces = card.get("card_faces")

        if faces is not None:
            if not isinstance(faces, list) or len(faces) < 2:
                issues.append(
                    f"{card.get('name', oracle_id)} has invalid card_faces"
                )
            elif any(
                not isinstance(face, dict) or not face.get("name")
                for face in faces
            ):
                issues.append(
                    f"{card.get('name', oracle_id)} has a face without a name"
                )

    return issues


def write_temp_json(target: Path, payload: dict[str, Any]) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)

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

    original_cards = document.get("cards")

    if not isinstance(original_cards, list):
        log("ERROR: card_index.json does not contain a 'cards' array.")
        return 1

    log(f"Reviewing {len(original_cards):,} existing card listings.")

    kept: list[dict[str, Any]] = []
    removed = 0
    faces_updated = 0
    attention: list[str] = []
    removal_counts: dict[str, int] = {}
    original_ids: set[str] = set()
    retained_ids: set[str] = set()

    for number, card in enumerate(original_cards, 1):
        if number % 5000 == 0:
            log(
                f"Reviewed {number:,}/{len(original_cards):,} "
                "existing listings..."
            )

        if not isinstance(card, dict):
            issue = f"record #{number} is not a JSON object"
            attention.append(issue)
            log(f"WARNING: {issue}; record cannot be classified.")
            continue

        oracle_id = card.get("oracle_id")
        display_name = card.get("name") or f"record #{number}"

        if oracle_id:
            original_ids.add(oracle_id)
        else:
            issue = f"{display_name}: missing oracle_id"
            attention.append(issue)
            log(f"WARNING: {issue}; cannot match against source data.")

        source = source_by_id.get(oracle_id) if oracle_id else None

        if source is None:
            issue = (
                f"{display_name}: no matching source record"
                + (f" for {oracle_id}" if oracle_id else "")
            )
            attention.append(issue)
            log(f"WARNING: {issue}; listing was retained for review.")
            kept.append(card)
            if oracle_id:
                retained_ids.add(oracle_id)
            continue

        remove, reason = is_non_gameplay_representation(source)

        if remove:
            removed += 1
            reason_label = reason or "non-gameplay listing"
            removal_counts[reason_label] = (
                removal_counts.get(reason_label, 0) + 1
            )
            log(
                f"REMOVED: {display_name} [{oracle_id}] — {reason_label}."
            )
            continue

        normalized_faces = build_card_faces(source)

        if normalized_faces is not None:
            if card.get("card_faces") != normalized_faces:
                card["card_faces"] = normalized_faces
                faces_updated += 1
        elif "card_faces" in card:
            card.pop("card_faces")
            faces_updated += 1

        kept.append(card)

        if oracle_id:
            retained_ids.add(oracle_id)

    # Compare the resulting index with the source, applying the same exclusion
    # criteria. This reveals potentially missing eligible listings without
    # automatically inserting them into the index.
    eligible_source_ids: set[str] = set()

    for oracle_id, source in source_by_id.items():
        remove, _reason = is_non_gameplay_representation(source)

        if not remove:
            eligible_source_ids.add(oracle_id)

    missing_ids = eligible_source_ids - retained_ids
    # Existing records without a matching source are already reported above.
    # Show a bounded list in the terminal to keep output usable.
    missing_details: list[str] = []

    for oracle_id in sorted(missing_ids):
        source = source_by_id[oracle_id]
        missing_details.append(
            f"{source.get('name', '(unnamed)')} [{oracle_id}] "
            f"({source.get('scryfall_uri', source.get('uri', 'no Scryfall URI'))})"
        )

    document["cards"] = kept

    metadata = document.setdefault("metadata", {})

    if isinstance(metadata, dict):
        metadata["unique_cards"] = len(kept)
        metadata["correction_source"] = "data/raw/oracle-cards.jsonl"
        metadata["correction_script"] = "scripts/correct_card_index.py"

    validation_issues = validate_cards(kept)

    if validation_issues:
        for issue in validation_issues[:25]:
            log(f"VALIDATION ERROR: {issue}")

        log(
            f"ERROR: validation failed ({len(validation_issues)} issue(s)); "
            "original file was not replaced."
        )
        return 1

    log(
        f"Found {removed:,} listing(s) identified for removal and "
        f"{faces_updated:,} face-data update(s)."
    )

    if removal_counts:
        log("Removal summary:")
        for reason, count in sorted(removal_counts.items()):
            log(f"  - {reason}: {count:,}")

    log(
        f"Eligible source listings missing from the resulting index: "
        f"{len(missing_ids):,}."
    )

    if missing_details:
        log("Missing eligible listings (first 25):")
        for detail in missing_details[:25]:
            log(f"  - {detail}")

        if len(missing_details) > 25:
            log(
                f"  ... and {len(missing_details) - 25:,} more; "
                "the source file was not modified."
            )

    log(
        "Validating proposed JSON and confirming the result can be "
        "serialized before replacing the existing file..."
    )

    temp_path: Path | None = None

    try:
        temp_path = write_temp_json(TARGET_PATH, document)

        with temp_path.open("r", encoding="utf-8") as handle:
            round_trip = json.load(handle)

        if not isinstance(round_trip, dict):
            raise ValueError("temporary file root is not a JSON object")

        round_trip_cards = round_trip.get("cards")

        if not isinstance(round_trip_cards, list):
            raise ValueError(
                "temporary file failed structural validation: "
                "'cards' is not an array"
            )

        if len(round_trip_cards) != len(kept):
            raise ValueError(
                "temporary file failed structural validation: "
                "card count does not match proposed result"
            )

        round_trip_issues = validate_cards(round_trip_cards)

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

    log(
        f"Completed: {len(kept):,} card listings retained; "
        f"{removed:,} listings removed; "
        f"{faces_updated:,} face-data updates applied."
    )

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
        log("Validation complete: no unresolved source-matching issues.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(
            "\n[card-index] Interrupted; "
            "existing JSON file was not replaced.",
            file=sys.stderr,
        )
        raise SystemExit(130)