"""FastAPI application entry point for Decklog.

Run locally from the repository root with:
    uvicorn app.main:app --reload

The homepage serves the commander catalogue and enriches it with the local decklist.
The API reads the committed JSON datasets without making runtime Scryfall requests.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

# Repository paths are resolved relative to this file, not the process working directory.
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
COMMANDER_CATALOGUE_PATH = DATA_DIR / "commander_catalogue.json"
DECKLIST_PATH = DATA_DIR / "users" / "decklist.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Decklog",
    description="A personal Commander deckbuilding catalogue and tracker.",
    version="0.1.0",
)

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

# Mount static assets only when the directory exists, so the module can still import
# while the frontend is being set up. In the expected repository, this path exists.
STATIC_DIR = APP_DIR / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk and raise a useful error if it is unavailable."""
    if not path.is_file():
        raise FileNotFoundError(f"Required Decklog data file was not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Expected the top level of {path} to be a JSON object.")

    return payload


def _load_datasets() -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the catalogue and user decklist from their repository locations."""
    catalogue = _read_json(COMMANDER_CATALOGUE_PATH)
    decklist = _read_json(DECKLIST_PATH)

    if not isinstance(catalogue.get("commanders"), list):
        raise ValueError(
            f"{COMMANDER_CATALOGUE_PATH} must contain a 'commanders' list."
        )
    if not isinstance(decklist.get("decks"), list):
        raise ValueError(f"{DECKLIST_PATH} must contain a 'decks' list.")

    return catalogue, decklist


def _normalise_colors(value: Any) -> list[str]:
    """Return a colour list, tolerating missing or malformed optional values."""
    if not isinstance(value, list):
        return []
    return [str(color) for color in value if color is not None]


def _build_commander_response(
    catalogue: dict[str, Any], decklist: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return catalogue entries enriched with matching deck metadata where possible.

    The decklist's commander_id is checked against known catalogue identifier fields.
    Name-based matching is intentionally not attempted because the decklist schema
    shown so far contains IDs, not a canonical commander name.
    """
    decks = decklist.get("decks", [])
    decks_by_commander_id: dict[str, list[dict[str, Any]]] = {}

    for deck in decks:
        if not isinstance(deck, dict):
            continue

        # A deck may reference the same card in more than one role field.
        # Associate it once per unique identifier to avoid duplicate deck rows.
        commander_ids = {
            str(commander_id)
            for commander_id in (
                deck.get("commander_id"),
                deck.get("secondary_commander_id"),
                deck.get("companion_id"),
            )
            if commander_id is not None
        }
        for commander_id in commander_ids:
            decks_by_commander_id.setdefault(commander_id, []).append(deck)

    results: list[dict[str, Any]] = []
    for commander in catalogue["commanders"]:
        if not isinstance(commander, dict):
            continue

        # Keep the source record's useful card fields, while giving the frontend a
        # predictable shape for the catalogue view.
        commander_id = (
            commander.get("oracle_id")
            or commander.get("id")
            or commander.get("scryfall_id")
        )
        linked_decks = (
            decks_by_commander_id.get(str(commander_id), [])
            if commander_id is not None
            else []
        )
        linked_decks = sorted(
            linked_decks,
            key=lambda deck: str(deck.get("deck_name", "")).casefold(),
        )

        results.append(
            {
                "oracle_id": commander.get("oracle_id"),
                "name": commander.get("name", ""),
                "scryfall_uri": commander.get("scryfall_uri"),
                "mana_cost": commander.get("mana_cost", ""),
                "cmc": commander.get("cmc"),
                "type_line": commander.get("type_line", ""),
                "colors": _normalise_colors(commander.get("colors")),
                "color_identity": _normalise_colors(
                    commander.get("color_identity")
                ),
                "image_urls": commander.get("image_urls", {}),
                "decks": [
                    {
                        "deck_id": deck.get("deck_id"),
                        "deck_name": deck.get("deck_name", ""),
                        "bracket": deck.get("bracket"),
                        "done": bool(deck.get("done", False)),
                    }
                    for deck in linked_decks
                ],
                "built": bool(linked_decks),
            }
        )

    return results


@app.get("/", include_in_schema=False)
async def homepage(request: Request):
    """Render the homepage shell; the client loads catalogue data from the API."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"page_title": "Decklog | Commanders"},
    )


@app.get("/decks", include_in_schema=False)
async def decks_page(request: Request):
    """Render the deck-centric collection page."""
    return templates.TemplateResponse(
        request=request,
        name="decks.html",
        context={"page_title": "Decklog | Decks"},
    )


@app.get("/stats", include_in_schema=False)
async def stats_page(request: Request):
    """Render the collection statistics page; data is loaded from the local API."""
    return templates.TemplateResponse(
        request=request,
        name="stats.html",
        context={"page_title": "Decklog | Stats"},
    )


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Lightweight health endpoint suitable for Render's health check."""
    return {"status": "ok", "service": "decklog"}


@app.get("/api/commanders")
async def get_commanders() -> JSONResponse:
    """Return the commander catalogue with any matching deck metadata.

    The homepage uses this endpoint to populate the commander table.
    """
    try:
        catalogue, decklist = _load_datasets()
        commanders = _build_commander_response(catalogue, decklist)
    except FileNotFoundError as exc:
        logger.exception("Decklog dataset is missing.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        logger.exception("Decklog dataset could not be parsed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(
        {
            "count": len(commanders),
            "deck_count": len(decklist.get("decks", [])),
            "commanders": commanders,
        }
    )


@app.get("/api/decks")
async def get_decks() -> JSONResponse:
    """Return the user's decklist without modifying the source file."""
    try:
        decklist = _read_json(DECKLIST_PATH)
        decks = decklist.get("decks")
        if not isinstance(decks, list):
            raise ValueError(f"{DECKLIST_PATH} must contain a 'decks' list.")
    except FileNotFoundError as exc:
        logger.exception("Decklist is missing.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        logger.exception("Decklist could not be parsed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(
        {
            "count": len(decks),
            "metadata": decklist.get("metadata", {}),
            "decks": decks,
        }
    )
