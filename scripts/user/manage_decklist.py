#!/usr/bin/env python3
"""Interactively add Commander decks to data/users/decklist.json.

Run from the repository root:
    python scripts/manage_decklist.py
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "users"
DECKLIST_PATH = DATA_DIR / "decklist.json"
COMMANDER_CATALOGUE_PATH = PROJECT_ROOT / "data" / "commander_catalogue.json"
SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named"
HEADERS = {
    "User-Agent": "Decklog/0.1 (personal MTG deck tracker)",
    "Accept": "application/json",
}
REQUEST_TIMEOUT = 30
API_REQUEST_INTERVAL = 2.0
LAST_API_REQUEST_TIME: float | None = None


class UserCancelled(Exception):
    """Raised when the user enters the explicit cancellation command."""


def timestamp_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prompt(message: str) -> str:
    value = input(message).strip()
    if value == "CANCEL":
        raise UserCancelled
    return value


def formatting_error() -> ValueError:
    return ValueError(
        "Formatting issues found in decklist.json. "
        "These issues must be corrected before running this script."
    )


def load_decklist() -> tuple[dict[str, Any], bool]:
    """Load and validate the file, or prepare a new document in memory."""
    if not DECKLIST_PATH.exists():
        now = timestamp_now()
        return ({
            "metadata": {
                "project": "Decklog",
                "created_at": now,
                "last_updated": now,
                "deck_count": 0,
            },
            "decks": [],
        }, True)

    try:
        with DECKLIST_PATH.open("r", encoding="utf-8") as file:
            document = json.load(file)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise formatting_error() from exc

    if not isinstance(document, dict):
        raise formatting_error()

    metadata = document.get("metadata")
    decks = document.get("decks")
    if not isinstance(metadata, dict) or not isinstance(decks, list):
        raise formatting_error()

    # Validate the fields this script relies on while allowing extra metadata.
    for deck in decks:
        if not isinstance(deck, dict):
            raise formatting_error()
        bracket = deck.get("bracket")
        if (
            not isinstance(deck.get("deck_name"), str)
            or not isinstance(deck.get("commander_id"), str)
            or not isinstance(bracket, int)
            or isinstance(bracket, bool)
            or bracket not in range(0, 6)
            or not isinstance(deck.get("done"), bool)
        ):
            raise formatting_error()

    return document, False


def write_json_atomic(document: dict[str, Any]) -> None:
    """Serialize to a temporary file, validate it, then replace the target."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".decklist.", suffix=".tmp", dir=str(DATA_DIR)
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(
            descriptor, "w", encoding="utf-8", newline="\n"
        ) as file:
            json.dump(document, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

        with temporary_path.open("r", encoding="utf-8") as file:
            json.load(file)

        os.replace(temporary_path, DECKLIST_PATH)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_existing_deck_ids(document: dict[str, Any]) -> set[str]:
    """Collect existing Moxfield deck IDs for efficient duplicate checks."""
    return {
        deck["deck_id"]
        for deck in document["decks"]
        if isinstance(deck.get("deck_id"), str)
    }


def ask_deck_url(existing_deck_ids: set[str]) -> str | None:
    """Validate a Moxfield deck URL and return its deck ID."""
    while True:
        value = prompt("\nMoxfield deck URL (or type CANCEL to exit): ")
        if not value:
            print("Deck URL cannot be empty.")
            continue

        # Accept the Moxfield URL with or without a scheme, but no other path.
        match = re.fullmatch(
            r"(?:https://)?moxfield\.com/decks/([A-Za-z0-9_-]+)",
            value,
        )
        if not match:
            print("Invalid Moxfield URL. Use moxfield.com/decks/{deck_id}.")
            continue

        deck_id = match.group(1)
        if deck_id in existing_deck_ids:
            print("This deck is already in the decklist.json. Cancel entry?")
            answer = prompt("Cancel entry? [y/N]: ").casefold()
            if answer in {"y", "yes"}:
                return None
            continue

        return deck_id


def load_commander_ids() -> set[str]:
    """Load Oracle IDs eligible according to the commander catalogue."""
    try:
        with COMMANDER_CATALOGUE_PATH.open("r", encoding="utf-8") as file:
            catalogue = json.load(file)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(
            f"Could not read commander catalogue: {COMMANDER_CATALOGUE_PATH}"
        ) from exc

    commanders = catalogue.get("commanders") if isinstance(catalogue, dict) else None
    if not isinstance(commanders, list):
        raise RuntimeError(
            "commander_catalogue.json does not contain a valid 'commanders' array."
        )

    return {
        card["oracle_id"]
        for card in commanders
        if isinstance(card, dict) and isinstance(card.get("oracle_id"), str)
    }


def resolve_commander(
    name: str,
    eligible_commander_ids: set[str],
    require_eligible: bool = True,
) -> dict[str, Any] | None:
    """Resolve a name using Scryfall's fuzzy named-card endpoint."""
    global LAST_API_REQUEST_TIME

    # Keep at least two seconds between the start of consecutive API requests.
    if LAST_API_REQUEST_TIME is not None:
        elapsed = time.monotonic() - LAST_API_REQUEST_TIME
        remaining = API_REQUEST_INTERVAL - elapsed

        if remaining > 0:
            print("Wait one moment")
            time.sleep(remaining)

    LAST_API_REQUEST_TIME = time.monotonic()

    try:
        response = requests.get(
            SCRYFALL_NAMED_URL,
            params={"fuzzy": name},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        print(f"Could not contact Scryfall: {exc}")
        return None

    if response.status_code == 404:
        print("Scryfall could not find an unambiguous match. Try another name.")
        return None

    try:
        response.raise_for_status()
        card = response.json()
    except (requests.HTTPError, ValueError):
        print(
            f"Scryfall request failed (HTTP {response.status_code}): "
            f"{response.text[:300]}"
        )
        return None

    if not isinstance(card, dict) or not card.get("oracle_id") or not card.get("name"):
        print("Scryfall's response did not contain the required card information.")
        return None

    if not require_eligible and "Companion" not in card.get("keywords", []):
        print(
            f'"{card["name"]}" does not have the Companion keyword. '
            "Try another name."
        )
        return None

    if require_eligible and card["oracle_id"] not in eligible_commander_ids:
        print(
            f'"{card["name"]}" is not listed as an eligible commander in '
            "data/commander_catalogue.json. Try another name."
        )
        return None

    return card

def ask_deck_name() -> str:
    while True:
        name = prompt("\nDeck name (or type CANCEL to exit): ")
        if not name:
            print("Deck name cannot be empty.")
            continue
        answer = prompt(f'Use deck name "{name}"? [y/N]: ').casefold()
        if answer in {"y", "yes"}:
            return name
        print("Let's try the deck name again.")


def ask_commander(
    eligible_commander_ids: set[str],
    prompt_label: str = "Commander",
    require_eligible: bool = True,
) -> dict[str, Any]:
    while True:
        name = prompt(f"\n{prompt_label} name (or type CANCEL to exit): ")
        if not name:
            print(f"{prompt_label} name cannot be empty.")
            continue

        card = resolve_commander(
            name,
            eligible_commander_ids if require_eligible else set(),
            require_eligible=require_eligible,
        )
        if card is None:
            continue

        print(f"Found commander: {card['name']}")
        answer = prompt("Is this the correct card? [y/N]: ").casefold()
        if answer in {"y", "yes"}:
            return card
        print(f"Let's try the {prompt_label.lower()} name again.")


def ask_optional_card(
    message: str,
    eligible_commander_ids: set[str],
    prompt_label: str,
    require_eligible: bool = True,
) -> dict[str, Any] | None:
    answer = prompt(f"{message} [y/N]: ").casefold()
    if answer in {"y", "yes"}:
        return ask_commander(
            eligible_commander_ids,
            prompt_label,
            require_eligible=require_eligible,
        )
    return None


def ask_bracket() -> int:
    while True:
        value = prompt("Bracket (0-5): ")
        try:
            bracket = int(value)
        except ValueError:
            print("Invalid bracket. Enter a whole number from 0 to 5.")
            continue
        if bracket in range(0, 6):
            return bracket
        print("Invalid bracket. Enter a whole number from 0 to 5.")


def ask_done() -> bool:
    while True:
        value = prompt("Done? (true/false): ").casefold()
        if value in {"true", "t", "1", "y", "yes"}:
            return True
        if value in {"false", "f", "0", "n", "no"}:
            return False
        print("Invalid value. Enter true/t/1/y/yes or false/f/0/n/no.")


def add_deck(
    document: dict[str, Any],
    eligible_commander_ids: set[str],
    existing_deck_ids: set[str],
) -> bool:
    """Collect, confirm, and save one deck; restart collection after rejection."""
    while True:
        name = ask_deck_name()
        commander = ask_commander(eligible_commander_ids)
        secondary_commander = ask_optional_card(
            "Add a partner or background?",
            eligible_commander_ids,
            "Partner or background",
        )
        companion = ask_optional_card(
            "Add a companion?",
            eligible_commander_ids,
            "Companion",
            require_eligible=False,
        )
        bracket = ask_bracket()
        done = False if bracket == 0 else ask_done()
        deck_id = ask_deck_url(existing_deck_ids)

        commander_id = commander["oracle_id"]
        commander_name = commander["name"]
        secondary_commander_id = (
            secondary_commander["oracle_id"] if secondary_commander else None
        )
        secondary_commander_name = (
            secondary_commander["name"] if secondary_commander else None
        )
        companion_id = companion["oracle_id"] if companion else None
        companion_name = companion["name"] if companion else None

        if deck_id is None:
            print("Deck entry cancelled. Restarting deck entry.")
            continue

        print("\nReview deck details")
        print("-" * 40)
        print(f"Deck ID:       {deck_id}")
        print(f"Deck name:     {name}")
        print(f"Commander:     {commander_name}")
        print(f"Commander ID:  {commander_id}")
        if secondary_commander is not None:
            print(f"Partner/Background: {secondary_commander_name}")
            print(f"Secondary ID:  {secondary_commander_id}")
        if companion is not None:
            print(f"Companion:     {companion_name}")
            print(f"Companion ID:  {companion_id}")
        print(f"Bracket:       {bracket}")
        print(f"Done:          {done}")
        print("-" * 40)

        while True:
            answer = prompt("Add this deck? [y=yes, n=no]: ").casefold()
            if answer in {"y", "yes"}:
                record = {
                    "deck_id": deck_id,
                    "deck_name": name,
                    "commander_id": commander_id,
                }
                if secondary_commander_id is not None:
                    record["secondary_commander_id"] = secondary_commander_id
                if companion_id is not None:
                    record["companion_id"] = companion_id
                record["bracket"] = bracket
                record["done"] = done

                document["decks"].append(record)
                existing_deck_ids.add(deck_id)
                metadata = document["metadata"]
                metadata["last_updated"] = timestamp_now()
                metadata["deck_count"] = len(document["decks"])

                try:
                    write_json_atomic(document)
                except (OSError, TypeError, ValueError) as exc:
                    document["decks"].pop()
                    existing_deck_ids.discard(deck_id)
                    metadata["deck_count"] = len(document["decks"])
                    print(f"Could not write decklist.json: {exc}")
                    return False

                print(f'Deck "{name}" was successfully added.')
                return True

            if answer in {"n", "no"}:
                print("Deck entry cancelled. Restarting deck entry.")
                break

            print("Invalid response. Enter y/yes to add or n/no to cancel.")

        # A rejection discards the collected values and restarts at deck name.


def main() -> None:
    added_count = 0
    try:
        document, is_new = load_decklist()
        eligible_commander_ids = load_commander_ids()
        existing_deck_ids = load_existing_deck_ids(document)

        print("=" * 60)
        print("Decklog decklist manager")
        print(f"Decklist: {DECKLIST_PATH}")
        print('Type "CANCEL" in all caps at any prompt to exit.')
        print("=" * 60)
        if is_new:
            print("A new decklist.json will be created when the first deck is saved.")

        while True:
            if add_deck(document, eligible_commander_ids, existing_deck_ids):
                added_count += 1
            answer = prompt("\nAdd another deck? [y/N]: ").casefold()
            if answer not in {"y", "yes"}:
                break

    except UserCancelled:
        print("\nCancellation requested. Exiting the decklist manager.")
    except ValueError as exc:
        print(str(exc))
        return
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Could not read or write decklist.json: {exc}")
        return
    finally:
        if DATA_DIR.exists():
            for temporary_path in DATA_DIR.glob(".decklist.*.tmp"):
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    print(f"\n{added_count} decks added to decklist.json")


if __name__ == "__main__":
    main()
