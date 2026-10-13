# Decklog — Commander Deck Tracker

Decklog is a personal tool for tracking Commander deckbuilding progress, statistics, and card data. This repository and its associated website are configured for my personal Commander decks, but the project can be adapted to track your own decks.

Decklog provides a centralized view of Commander deckbuilding progress, combining a searchable, filterable catalogue of Commander-legal cards with deck-specific information and statistics. It supports tracking individual decks, including their card lists, build status, and relevant deck data, using structured information sourced from Scryfall and locally maintained deck information. The project also includes workflows for managing card and deck data, helping keep the underlying data consistent as decks are developed and updated.

To maintain a forked version of Decklog, you will need to periodically update the Scryfall source dataset at `data/raw/oracle-cards.jsonl` and run the Card Data Manager workflow to refresh `data/card_index.json` and `data/commander_catalogue.json`. You will also need to replace the user-specific data in `data/users/decklist.json` with your own using the Decklist Manager workflow.
## Card Data Manager

Decklog uses two JSON datasets to support card lookup and Commander deckbuilding:

- **`data/card_index.json`** — A broad index of cards from Scryfall's Oracle Cards bulk dataset. It contains cards with an Oracle ID, regardless of game availability. It is intended to provide the card data needed for decklists, lookups, and future deck analysis.
- **`data/commander_catalogue.json`** — A catalogue of cards eligible to serve as commanders under the Scryfall search query `game:paper legal:commander is:commander`. It includes additional image URL data for displaying commanders in the application.

Both datasets are generated or corrected using scripts in `scripts/data`. The raw source file is `data/raw/oracle-cards.jsonl`.

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



Decklog uses [Scryfall](https://scryfall.com/) for card data. Download the **Oracle Cards** dataset from the [Scryfall Bulk Data page](https://scryfall.com/docs/api/bulk-data) and place it at:

```text
data/raw/oracle-cards.jsonl
```

The source file is excluded from Git via `.gitignore`, so each developer must download it locally. Scryfall data changes over time; regenerate and correct the datasets when a refresh is needed.

## Script execution

Run all commands from the repository root with the virtual environment activated.

#### 1. Generate the datasets

```bash
python scripts/data/build_commander_catalogue.py
```

This script builds both datasets:

- **Card index:** Reads the local bulk file, retains records with an Oracle ID, and sorts them by name. All cards, regardless of legality, type, or playability, are entered initially.
- **Commander catalogue:** Queries Scryfall for paper-available, Commander-legal cards eligible to be commanders. It fetches results page by page, deduplicates by Oracle ID, and includes image URL data.

The script displays progress and reports the number of records written to each file. If output files already exist, it asks whether to overwrite them. A "y" or "yes" input (case insensitive) allows them to be overwritten; any other input declines overwriting. If overwriting is declined, existing files are preserved and only missing outputs are generated. Commander-fetch progress is saved in a temporary checkpoint so an interrupted fetch can resume.

#### 2. Correct the card index

```bash
python scripts/data/correct_card_index.py
```

Reviews `card_index.json` against the local source. It removes identified non-gameplay and auxiliary listings, adds normalized `card_faces` data for multi-faced cards, and reports unmatched or missing records for review. It does not automatically add missing cards.

The script reports the number of records retained, removals, and face-data updates. It validates the proposed JSON before replacing the existing file.

#### 3. Correct the commander catalogue

```bash
python scripts/data/correct_commander_catalogue.py
```

Reviews `commander_catalogue.json` against the local source and corrects `mana_cost` and `type_line` where possible. Multi-faced display values are handled using face-level data. Commander membership and existing image URLs are preserved.

The script reports mismatches, corrections, and unresolved issues. It validates the result before replacing the existing file.

#### Recommended workflow

For a fresh build or data refresh, run:

```bash
python scripts/data/build_commander_catalogue.py
python scripts/data/correct_card_index.py
python scripts/data/correct_commander_catalogue.py
```

The correction scripts can also be run individually when only one dataset needs attention.

### JSON dataset fields

Both JSON files contain a top-level `metadata` object and an array of card records: `cards` in the index and `commanders` in the commander catalogue. The card index is intentionally broader than the commander catalogue. A card's presence in the index does not guarantee paper availability, Commander legality, or eligibility to be a commander.

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
| `cmc` | Mana value (formerly called converted mana cost). |
| `type_line` | Card types and subtypes. |
| `oracle_text` | Official Oracle rules text. |
| `colors` | The card's colors, represented by abbreviations such as `W`, `U`, `B`, `R`, and `G`. |
| `color_identity` | Colors used to determine Commander color identity. |
| `card_faces` | Added or normalized by the card-index correction script for multi-faced cards. Contains face-level names, mana costs, type lines, Oracle text, and colors. |
| `image_urls` | Image URL data for display. Present in the commander catalogue, not the card index. For multi-faced cards, URLs are grouped by face when available. |

Fields may be absent when the source does not provide them. `card_faces` is added or updated by the correction script; it is not part of the initial card-index projection.


## Deck List Manager

The deck list manager is used to interactively add Commander decks to `data/users/decklist.json`. It retrieves card information from Scryfall, validates commander eligibility against `data/commander_catalogue.json`, checks for duplicate Moxfield deck IDs, and writes new entries to the decks list.

### Prerequisites

- Python 3.10 or newer
- Dependencies installed using `python -m pip install -r requirements.txt`
- `data/commander_catalogue.json` generated and available
- Internet access to contact the Scryfall API
- A Moxfield deck URL for each deck being added

### Running the script

Run the following command from the **repository root**, with the virtual environment activated:

```bash
python scripts/user/manage_decklist.py
```

If `data/users/decklist.json` does not exist, the script prepares a new decks list in memory. The file is created when the first deck is successfully saved.

### Adding a deck

The script guides the user through the following prompts in order.

#### 1. Enter the deck name

Enter a non-empty deck name. The script asks for confirmation before proceeding.

- `y` or `yes` accepts the name.
- `CANCEL` exits the script.
- Any other input rejects it and restarts the deck-name prompt.

#### 2. Enter and confirm the primary commander

Enter the card name. The script uses Scryfall's fuzzy named-card endpoint to find a match.

The script displays the matched card and asks whether it is correct.

- `y` or `yes` confirms the card.
- `CANCEL` exits the script.
- Any other input returns to the commander-name prompt.
- If Scryfall cannot find a match, the request fails, or the card is not listed in `commander_catalogue.json`, the script displays an error and allows another name to be entered.

The primary commander is required and its Oracle ID is saved as `commander_id`.

#### 3. Optionally add a partner or background

The script asks:

`Add a partner or background? [y/N]:`

- `y` or `yes` opens another card-name prompt with the same lookup and confirmation process.
- `CANCEL` exits the script.
- Any other input skips this field and proceeds to the companion prompt.

The selected card's Oracle ID is saved as `secondary_commander_id`. The field is omitted if no secondary commander is added.

#### 4. Optionally add a companion

The script asks:

`Add a companion? [y/N]:`

- `y` or `yes` opens another card-name prompt with card lookup and confirmation.
- `CANCEL` exits the script.
- Any other input skips this field and proceeds to the bracket prompt.

The companion is looked up through Scryfall, and checked to ensure the Companion keyword is present. Its Oracle ID is saved as `companion_id`. The field is omitted if no companion is added.

#### 5. Enter the bracket

Enter a whole number from `0` to `5`, inclusive.

- `0` indicates a deck that is not yet assigned a bracket. It automatically sets `done` to `false` and skips the Done prompt.
- `1` through `5` are accepted as bracket values and proceed to the Done prompt.
- `CANCEL` exits the script.
- Any other value, including non-numeric input, produces an error and repeats the bracket prompt.

#### 6. Set the completion status

For brackets `1` through `5`, the script asks:

`Done? (true/false):`

Accepted inputs are case-insensitive:

| Result | Accepted input |
|---|---|
| `true` | `true`, `t`, `1`, `y`, `yes` |
| `false` | `false`, `f`, `0`, `n`, `no` |

Invalid input produces an error and repeats the prompt.
`CANCEL` exits the script.

#### 7. Enter the Moxfield URL

Enter the deck's Moxfield URL in this format:

```text
https://moxfield.com/decks/{deck_id}
```

The `https://` scheme is optional. The script accepts the `moxfield.com/decks/` path followed by a deck ID containing letters, numbers, underscores, or hyphens.

- An empty or invalid URL produces an error and repeats the prompt.
- If the deck ID already exists in `decklist.json`, the script reports the duplicate and asks whether to cancel the entry. `y` or `yes` cancels the current entry; any other input returns to the URL prompt.
- The script stores the extracted deck ID, not the full URL.
- `CANCEL` exits the script.

#### 8. Review and save

The script displays a summary containing the deck ID, name, commander, any secondary commander or companion, bracket, and completion status.

It then asks:

`Add this deck? [y=yes, n=no]:`

- `y` or `yes` saves the entry.
- `n` or `no` discards the collected values and restarts the process at the deck-name prompt.
- `CANCEL` exits the script.
- Any other input repeats the confirmation prompt.

After a successful save, the script reports that the deck was added. It then asks whether to add another deck. `y` or `yes` starts another entry; any other input ends the session.

### Input and error handling

At any interactive prompt, entering `CANCEL` in all caps exits the script. Any deck currently being entered is discarded if it has not yet been saved. Previously saved entries remain intact.

The script also handles the following errors:

| Error condition | Script behavior and recommended action |
|---|---|
| Empty deck name or commander name | Displays an error and repeats the relevant prompt. Enter a non-empty value. |
| Scryfall returns no matching card | Displays a message and requests another card name. Check the spelling or try the full card name. |
| Card is not in the commander catalogue | Rejects the card for primary or secondary commander selection. Verify the card's eligibility and regenerate the catalogue if it is outdated. |
| Scryfall request fails or times out | Displays an error and allows another attempt. Check the internet connection and try again. |
| Too many closely spaced API requests | The script waits as needed and prints `Wait one moment`. Allow it to finish waiting. |
| Invalid Moxfield URL | Displays an error and repeats the URL prompt. Check the URL format and deck ID. |
| Duplicate Moxfield deck ID | Asks whether to cancel the entry. Cancel it or provide a different deck URL. |
| Invalid bracket or Done value | Displays an error and repeats the relevant prompt using the accepted values. |
| Invalid or unreadable `decklist.json` | Displays a formatting error and exits. Back up the file, correct its JSON structure or field values, and rerun the script. |
| Missing or invalid `commander_catalogue.json` | Displays an error and exits. Generate or repair the catalogue before rerunning the manager. |
| Failure while writing the decks list | Displays an error and does not retain the attempted deck in the in-memory list. Check file permissions, available disk space, and whether another process is interfering with the file before retrying. |

The script writes the JSON through a temporary file and replaces the target only after validating the serialized JSON. It also updates the deck count and last-updated timestamp after a successful addition.

### `decklist.json` structure

The file contains a top-level `metadata` object and a `decks` array. Each item in `decks` represents one Moxfield deck.

#### Metadata fields

| Field | Meaning |
|---|---|
| `project` | Project name: Decklog. |
| `created_at` | UTC timestamp when the deck list was first created. |
| `last_updated` | UTC timestamp of the most recent successful deck addition. |
| `deck_count` | Number of deck records in the `decks` array. |

#### Deck fields

| Field | Required? | Meaning |
|---|---|---|
| `deck_id` | Yes | Moxfield deck ID extracted from the URL. Used to detect duplicate entries. |
| `deck_name` | Yes | User-provided deck name. |
| `commander_id` | Yes | Scryfall Oracle ID of the primary commander. |
| `secondary_commander_id` | No | Scryfall Oracle ID of the optional second commander, including a partner or Background. |
| `companion_id` | No | Scryfall Oracle ID of the optional companion. |
| `bracket` | Yes | Integer from `0` to `5`. A value of `0` indicates that the deck has not yet been assigned a bracket. |
| `done` | Yes | Boolean indicating whether the deck is considered complete. Bracket `0` automatically sets this to `false`. |

Oracle IDs are used instead of card names so that Decklog can match deck entries to the card records in its datasets. The manager does not store the card names for the secondary commander or companion; those names can be retrieved from the card data when needed.

### Recommended workflow

1. Ensure `data/commander_catalogue.json` is current.
2. Run `python scripts/user/manage_decklist.py` from the repository root.
3. Follow the prompts and review each deck before saving.
4. Inspect `data/users/decklist.json` if you need to verify the saved IDs, bracket, completion status, or metadata.
5. Commit changes to the deck list when appropriate for your repository workflow. The deck list contains personal deck-tracking data, so confirm that it is intended to be tracked by Git before committing it.