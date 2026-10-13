import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "oracle-cards.jsonl"

COMMANDER_OUTPUT_PATH = PROJECT_ROOT / "data" / "commander_catalogue.json"
CARD_OUTPUT_PATH = PROJECT_ROOT / "data" / "card_index.json"
CHECKPOINT_PATH = (
    PROJECT_ROOT / "data" / "raw" / "commander_catalogue_progress.json"
)

SEARCH_URL = "https://api.scryfall.com/cards/search"

HEADERS = {
    "User-Agent": "Decklog/0.1 (personal MTG deck tracker)",
    "Accept": "application/json",
}

COMMANDER_QUERY = "game:paper legal:commander is:commander"

# Scryfall search endpoints are limited to 2 requests per second.
REQUEST_INTERVAL = 1.0
MAX_RETRIES = 3
MIN_429_WAIT = 30.0
MAX_SERVER_ERROR_WAIT = 60.0

CARD_FIELDS = (
    "oracle_id",
    "name",
    "scryfall_uri",
    "mana_cost",
    "cmc",
    "type_line",
    "oracle_text",
    "colors",
    "color_identity",
)


def project_card(card: dict) -> dict:
    """Extract the fields required by Decklog."""
    return {
        field: card[field]
        for field in CARD_FIELDS
        if field in card
    }


def extract_image_urls(card: dict) -> dict:
    """Extract image URLs for single-faced or multi-faced cards."""
    if card.get("image_uris"):
        return card["image_uris"]

    face_images = {}

    for face in card.get("card_faces", []):
        image_uris = face.get("image_uris")

        if image_uris:
            face_images[face.get("name", "Unknown face")] = image_uris

    return face_images


def write_json_atomic(
    path: Path,
    data: dict,
    count_lines: bool = True,
) -> int:
    """Write JSON atomically and optionally return its physical line count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")

    try:
        with temporary_path.open(
            "w", encoding="utf-8", newline="\n"
        ) as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")

        line_count = 0

        if count_lines:
            with temporary_path.open("r", encoding="utf-8") as file:
                line_count = sum(1 for _ in file)

        temporary_path.replace(path)
        return line_count

    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def build_card_index() -> list[dict]:
    """Build the local card index without filtering by game availability."""
    print("\n" + "=" * 72)
    print("STAGE 1/2: Building local card index")
    print(f"Source: {RAW_DATA_PATH}")
    print("=" * 72)

    cards_by_oracle_id = {}
    lines_read = 0
    cards_retained = 0
    skipped_records = 0

    with RAW_DATA_PATH.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue

            lines_read += 1

            try:
                card = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on source line {line_number}: {exc}"
                ) from exc

            # Include all cards with an Oracle ID, regardless of game availability.
            oracle_id = card.get("oracle_id")

            if not oracle_id:
                skipped_records += 1
            elif oracle_id in cards_by_oracle_id:
                raise ValueError(
                    f"Duplicate Oracle ID in oracle-cards.jsonl: "
                    f"{oracle_id} ({card.get('name', 'Unknown card')})"
                )
            else:
                cards_by_oracle_id[oracle_id] = project_card(card)
                cards_retained += 1

            if lines_read % 100_000 == 0:
                print(
                    f"\rScanned {lines_read:,} records | "
                    f"Cards retained: {cards_retained:,} | "
                    f"Skipped: {skipped_records:,}",
                    end="",
                    flush=True,
                )

    print()
    print(f"Source records scanned: {lines_read:,}")
    print(f"Cards retained: {cards_retained:,}")
    print(f"Records skipped: {skipped_records:,}")

    if not cards_by_oracle_id:
        raise RuntimeError(
            "No cards with Oracle IDs were found in oracle-cards.jsonl. "
            "Check the source file."
        )

    cards = list(cards_by_oracle_id.values())
    cards.sort(
        key=lambda card: (
            card.get("name", "").casefold(),
            card.get("oracle_id", ""),
        )
    )

    output = {
        "metadata": {
            "project": "Decklog",
            "source_dataset": RAW_DATA_PATH.name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "Scryfall bulk data",
            "card_query": "all cards with an Oracle ID",
            "unique_cards": len(cards),
        },
        "cards": cards,
    }

    line_count = write_json_atomic(CARD_OUTPUT_PATH, output)

    print(
        f"Written {len(cards):,} cards to "
        f"{CARD_OUTPUT_PATH.name} ({line_count:,} lines)."
    )

    return cards


def fetch_commander_catalogue() -> list[dict]:
    """Fetch commanders page by page with pacing and resumable checkpoints."""
    print("\n" + "=" * 72)
    print("STAGE 2/2: Fetching commander catalogue from Scryfall")
    print(f"Query: {COMMANDER_QUERY}")
    print(f"Minimum request interval: {REQUEST_INTERVAL:.1f} second")
    print("=" * 72)

    commanders_by_id = {}
    pages_processed = 0
    next_url = SEARCH_URL
    params = {"q": COMMANDER_QUERY, "unique": "cards"}
    completed = False

    # Restore progress if an earlier run was interrupted.
    if CHECKPOINT_PATH.is_file():
        try:
            with CHECKPOINT_PATH.open("r", encoding="utf-8") as file:
                checkpoint = json.load(file)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(
                f"Could not read commander checkpoint: {exc}"
            ) from exc

        if checkpoint.get("query") != COMMANDER_QUERY:
            raise RuntimeError(
                "The saved commander checkpoint uses a different query. "
                f"Inspect or remove {CHECKPOINT_PATH} before continuing."
            )

        commanders_by_id = {
            card["oracle_id"]: card
            for card in checkpoint.get("commanders", [])
            if card.get("oracle_id")
        }
        pages_processed = checkpoint.get("pages_processed", 0)
        next_url = checkpoint.get("next_url")
        completed = checkpoint.get("complete", False)

        if completed:
            print(
                f"Restored completed checkpoint: "
                f"{len(commanders_by_id):,} commanders."
            )
        else:
            print(
                f"Resuming after page {pages_processed:,}: "
                f"{len(commanders_by_id):,} commanders already saved."
            )

        # A next-page URL already contains the original search parameters.
        params = None

    def save_checkpoint(next_page_url: str | None, is_complete: bool) -> None:
        checkpoint_data = {
            "query": COMMANDER_QUERY,
            "pages_processed": pages_processed,
            "next_url": next_page_url,
            "complete": is_complete,
            "commanders": list(commanders_by_id.values()),
        }

        write_json_atomic(
            CHECKPOINT_PATH,
            checkpoint_data,
            count_lines=False,
        )

    last_request_time = None

    def wait_for_request_slot() -> None:
        """Maintain a minimum interval between all API requests."""
        nonlocal last_request_time

        if last_request_time is not None:
            elapsed = time.monotonic() - last_request_time
            remaining = REQUEST_INTERVAL - elapsed

            if remaining > 0:
                time.sleep(remaining)

        last_request_time = time.monotonic()

    if not completed:
        with requests.Session() as session:
            session.headers.update(HEADERS)

            while next_url:
                retries = 0

                while True:
                    wait_for_request_slot()

                    try:
                        response = session.get(
                            next_url,
                            params=params,
                            timeout=60,
                        )
                    except requests.RequestException as exc:
                        raise RuntimeError(
                            f"Network error while fetching commanders: {exc}\n"
                            "The last completed page is saved in the checkpoint."
                        ) from exc

                    status = response.status_code

                    if status == 429:
                        if retries >= MAX_RETRIES:
                            raise RuntimeError(
                                "Scryfall continued returning HTTP 429 after "
                                f"{MAX_RETRIES} retries. Stop and try again later."
                            )

                        retry_after = response.headers.get("Retry-After", "")

                        try:
                            delay = max(float(retry_after), MIN_429_WAIT)
                        except ValueError:
                            delay = MIN_429_WAIT

                        retries += 1
                        print(
                            f"\nHTTP 429: rate limited. "
                            f"Waiting {delay:g} seconds "
                            f"(retry {retries}/{MAX_RETRIES})."
                        )
                        time.sleep(delay)
                        continue

                    if status >= 500:
                        if retries >= MAX_RETRIES:
                            raise RuntimeError(
                                "Scryfall continued returning server errors "
                                f"after {MAX_RETRIES} retries."
                            )

                        delay = min(
                            2.0 * (2 ** retries),
                            MAX_SERVER_ERROR_WAIT,
                        )
                        retries += 1

                        print(
                            f"\nScryfall returned HTTP {status}. "
                            f"Waiting {delay:g} seconds "
                            f"(retry {retries}/{MAX_RETRIES})."
                        )
                        time.sleep(delay)
                        continue

                    try:
                        response.raise_for_status()
                    except requests.HTTPError as exc:
                        raise RuntimeError(
                            f"Scryfall request failed: HTTP {status}: "
                            f"{response.text[:500]}"
                        ) from exc

                    try:
                        result = response.json()
                    except ValueError as exc:
                        raise RuntimeError(
                            "Scryfall returned invalid JSON."
                        ) from exc

                    break

                page_cards = result.get("data", [])

                for card in page_cards:
                    oracle_id = card.get("oracle_id")

                    if not oracle_id:
                        continue

                    record = project_card(card)
                    record["image_urls"] = extract_image_urls(card)
                    commanders_by_id[oracle_id] = record

                pages_processed += 1

                has_more = result.get("has_more", False)
                next_page_url = (
                    result.get("next_page") if has_more else None
                )

                if has_more and not next_page_url:
                    raise RuntimeError(
                        "Scryfall reported additional pages but did not "
                        "provide a next-page URL."
                    )

                # Save each completed page before proceeding.
                save_checkpoint(
                    next_page_url,
                    is_complete=not has_more,
                )

                last_card_name = (
                    page_cards[-1].get("name", "Unknown card")
                    if page_cards
                    else "No cards on page"
                )

                print(
                    f"\rCommander page {pages_processed:,} | "
                    f"{len(commanders_by_id):,} unique commanders | "
                    f"Last result: {last_card_name}",
                    end="",
                    flush=True,
                )

                next_url = next_page_url
                params = None

                # The next request is paced by wait_for_request_slot().
                # Do not sleep here as well; that would duplicate the delay.

        print()

    if not commanders_by_id:
        raise RuntimeError(
            "Scryfall returned no commanders. Check the query and API response."
        )

    commanders = list(commanders_by_id.values())
    commanders.sort(
        key=lambda card: (
            card.get("name", "").casefold(),
            card.get("oracle_id", ""),
        )
    )

    print(f"Commander pages processed: {pages_processed:,}")
    print(f"Unique commanders collected: {len(commanders):,}")

    output = {
        "metadata": {
            "project": "Decklog",
            "source": "Scryfall API",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "commander_query": COMMANDER_QUERY,
            "unique_commanders": len(commanders),
            "pages_processed": pages_processed,
        },
        "commanders": commanders,
    }

    line_count = write_json_atomic(COMMANDER_OUTPUT_PATH, output)

    print(
        f"Written {len(commanders):,} commanders to "
        f"{COMMANDER_OUTPUT_PATH.name} ({line_count:,} lines)."
    )

    # Only remove the checkpoint after the final catalogue is written.
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()

    return commanders


def confirm_overwrite(existing_paths: list[Path]) -> bool:
    """Ask whether existing output files may be overwritten."""
    if not existing_paths:
        return True

    print("\nThe following output file(s) already exist:")

    for path in existing_paths:
        print(f"  - {path}")

    response = input(
        "\nOverwrite existing output file(s)? [y/N]: "
    ).strip().casefold()

    return response in {"y", "yes"}


def main() -> None:
    card_index_exists = CARD_OUTPUT_PATH.exists()
    commander_catalogue_exists = COMMANDER_OUTPUT_PATH.exists()

    existing_paths = []

    if card_index_exists:
        existing_paths.append(CARD_OUTPUT_PATH)

    if commander_catalogue_exists:
        existing_paths.append(COMMANDER_OUTPUT_PATH)

    overwrite_existing = confirm_overwrite(existing_paths)

    # If overwriting is declined, preserve existing outputs and build only
    # the outputs that do not currently exist.
    build_card_index_file = (
        not card_index_exists or overwrite_existing
    )
    build_commander_catalogue_file = (
        not commander_catalogue_exists or overwrite_existing
    )

    if not build_card_index_file and not build_commander_catalogue_file:
        print("\nNo changes made to existing output files.")
        print("Exited script without running.")
        return

    if card_index_exists and not overwrite_existing:
        print(
            f"\nNo changes made to existing {CARD_OUTPUT_PATH.name} file."
        )

    if commander_catalogue_exists and not overwrite_existing:
        print(
            f"No changes made to existing "
            f"{COMMANDER_OUTPUT_PATH.name} file."
        )

    if not RAW_DATA_PATH.is_file():
        raise FileNotFoundError(
            f"Oracle Cards dataset not found: {RAW_DATA_PATH}\n"
            "Place the file at data/raw/oracle-cards.jsonl."
        )

    print("=" * 72)
    print("Decklog catalogue generator")
    print(f"Local source: {RAW_DATA_PATH}")
    print(f"Card index output: {CARD_OUTPUT_PATH}")
    print(f"Commander output: {COMMANDER_OUTPUT_PATH}")
    print("=" * 72)

    cards = None
    commanders = None

    # Stage 1 is entirely local and makes no API requests.
    if build_card_index_file:
        cards = build_card_index()
    else:
        print(
            f"\nSkipping card index: "
            f"{CARD_OUTPUT_PATH.name} already exists."
        )

    # Stage 2 uses the API only for commander-specific eligibility.
    if build_commander_catalogue_file:
        commanders = fetch_commander_catalogue()
    else:
        print(
            f"\nSkipping commander catalogue: "
            f"{COMMANDER_OUTPUT_PATH.name} already exists."
        )

    print("\n" + "=" * 72)
    print("CATALOGUE GENERATION COMPLETE")
    print("=" * 72)

    if cards is not None:
        print(f"Cards in card index written: {len(cards):,}")
        print(f"Card index: {CARD_OUTPUT_PATH}")
    else:
        print(f"Card index retained: {CARD_OUTPUT_PATH}")

    if commanders is not None:
        print(f"Eligible commanders written: {len(commanders):,}")
        print(f"Commander catalogue: {COMMANDER_OUTPUT_PATH}")
    else:
        print(f"Commander catalogue retained: {COMMANDER_OUTPUT_PATH}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
        print(f"\nFATAL ERROR: {exc}")
        raise