# Decklog — Commander Deck Tracker

Decklog is a personal tool for tracking Commander deckbuilding progress, statistics, and card data.

## Card Data Generation & Correction

Decklog uses two JSON datasets to support card lookup and Commander deckbuilding:

- **`data/card_index.json`** — A broad index of cards from Scryfall's Oracle Cards bulk dataset. It contains cards with an Oracle ID, regardless of game availability. It is intended to provide the card data needed for decklists, lookups, and future deck analysis.
- **`data/commander_catalogue.json`** — A catalogue of cards eligible to serve as commanders under the Scryfall search query `game:paper legal:commander is:commander`. It includes additional image URL data for displaying commanders in the application.

Both datasets are generated or corrected using scripts in `scripts/`. The raw source file is `data/raw/oracle-cards.jsonl`.

### Prerequisites

- Python 3.10 or newer
- Internet access for commander catalogue generation
- Scryfall's Oracle Cards bulk dataset

### Install dependencies

Run these commands from the **repository root**, where `requirements.txt` is located.

Create and activate a virtual environment (recommended).

**Windows — PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

### Verify the source dataset



Decklog uses [Scryfall](https://scryfall.com/) for card data. Download the **Oracle Cards** dataset from the [Scryfall Bulk Data page](https://scryfall.com/docs/api/bulk-data) and place it at:.

```text
data/raw/oracle-cards.jsonl
```

The source file is excluded from Git via `.gitignore`, so each developer must download it locally. Scryfall data changes over time; regenerate and correct the datasets when a refresh is needed.

The card index is intentionally broader than the commander catalogue. A card's presence in the index does not guarantee paper availability, Commander legality, or eligibility to be a commander.

### Script execution

Run all commands from the repository root with the virtual environment activated.

#### 1. Generate the datasets

```bash
python scripts/build_commander_catalogue.py
```

This script builds both datasets:

- **Card index:** Reads the local bulk file, retains records with an Oracle ID, and sorts them by name. All cards, regardless of legality, type, or playability, are entered initially.
- **Commander catalogue:** Queries Scryfall for paper-available, Commander-legal cards eligible to be commanders. It fetches results page by page, deduplicates by Oracle ID, and includes image URL data.

The script displays progress and reports the number of records written to each file. If output files already exist, it asks whether to overwrite them. A "y" or "yes" input (case insensitive) allows them to be overwritten; any other input declines overwriting. If overwriting is declined, existing files are preserved and only missing outputs are generated. Commander-fetch progress is saved in a temporary checkpoint so an interrupted fetch can resume.

#### 2. Correct the card index

```bash
python scripts/correct_card_index.py
```

Reviews `card_index.json` against the local source. It removes identified non-gameplay and auxiliary listings, adds normalized `card_faces` data for multi-faced cards, and reports unmatched or missing records for review. It does not automatically add missing cards.

The script reports the number of records retained, removals, and face-data updates. It validates the proposed JSON before replacing the existing file.

#### 3. Correct the commander catalogue

```bash
python scripts/correct_commander_catalogue.py
```

Reviews `commander_catalogue.json` against the local source and corrects `mana_cost` and `type_line` where possible. Multi-faced display values are handled using face-level data. Commander membership and existing image URLs are preserved.

The script reports mismatches, corrections, and unresolved issues. It validates the result before replacing the existing file.

#### Recommended workflow

For a fresh build or refresh, run:

```bash
python scripts/build_commander_catalogue.py
python scripts/correct_card_index.py
python scripts/correct_commander_catalogue.py
```

The correction scripts can also be run individually when only one dataset needs attention.

### JSON dataset fields

Both JSON files contain a top-level `metadata` object and an array of card records: `cards` in the index and `commanders` in the commander catalogue.

#### Metadata

| Field | Meaning |
|---|---|
| `project` | Project name: Decklog. |
| `source` | Data source, such as Scryfall bulk data or Scryfall API. |
| `source_dataset` | Local bulk dataset filename, used in the card index. |
| `generated_at` | UTC timestamp when the dataset was generated. |
| `card_query` / `commander_query` | Description of the selection criteria used. |
| `unique_cards` / `unique_commanders` | Number of records in the corresponding array. |
| `pages_processed` | Number of Scryfall API pages processed for the commander catalogue. |

Correction scripts may add `correction_source` and `correction_script` to record the source and script used during correction.

#### Card fields

| Field | Meaning |
|---|---|
| `oracle_id` | Scryfall identifier for the card's Oracle identity; used for matching and deduplication. |
| `name` | Card name. |
| `scryfall_uri` | Link to the card's Scryfall page. |
| `mana_cost` | Mana cost in Scryfall notation, such as `{2}{U}`. |
| `cmc` | Converted mana cost, also known as mana value. |
| `type_line` | Card types and subtypes. |
| `oracle_text` | Official Oracle rules text. |
| `colors` | The card's colors, represented by abbreviations such as `W`, `U`, `B`, `R`, and `G`. |
| `color_identity` | Colors used to determine Commander color identity. |
| `card_faces` | Added or normalized by the card-index correction script for multi-faced cards. Contains face-level names, mana costs, type lines, Oracle text, and colors. |
| `image_urls` | Image URL data for display. Present in the commander catalogue, not the card index. For multi-faced cards, URLs are grouped by face when available. |

Fields may be absent when the source does not provide them. `card_faces` is added or updated by the correction script; it is not part of the initial card-index projection.


