/* Client-side catalogue rendering, filters, and mana badges. */
(() => {
  const commanderSearch = document.getElementById("commander-search");
  const deckSearch = document.getElementById("deck-search");
  const colorFilter = document.getElementById("color-filter");
  const colorTrigger = document.getElementById("color-filter-trigger");
  const colorMenu = document.getElementById("color-filter-menu");
  const colorLabel = document.getElementById("color-filter-label");
  const bracketFilter = document.getElementById("bracket-filter");
  const builtFilter = document.getElementById("built-filter");
  const doneFilter = document.getElementById("done-filter");
  const resetButton = document.getElementById("reset-filters");
  const resultCount = document.getElementById("result-count");
  const emptyState = document.getElementById("empty-state");
  const tableBody = document.getElementById("commander-table-body");
  const colorOrder = "WUBRG";

  let commanders = [];

  function normalize(value) {
    return String(value ?? "").toLocaleLowerCase().trim();
  }

  function canonicalColors(value) {
    const letters = new Set(
      (Array.isArray(value) ? value.join("") : String(value || "")).toUpperCase().split("")
    );
    return colorOrder.split("").filter((letter) => letters.has(letter)).join("") || "C";
  }

  function makeCell(text, className = "") {
    const cell = document.createElement("td");
    if (className) cell.className = className;
    cell.textContent = text ?? "";
    return cell;
  }

  function makeStatusCell(checked, label, rowSpan = 1) {
    const cell = makeCell("", "center-cell");
    if (rowSpan > 1) cell.rowSpan = rowSpan;
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = Boolean(checked);
    checkbox.disabled = true;
    checkbox.setAttribute("aria-label", label);
    cell.append(checkbox);
    return cell;
  }

  function makeBadge(label, color, className = "mana-badge") {
    const badge = document.createElement("span");
    badge.className = className;
    badge.textContent = label;
    badge.style.setProperty("--symbol-bg", color[0]);
    badge.style.setProperty("--symbol-text", color[1]);
    badge.setAttribute("aria-hidden", "true");
    return badge;
  }

  const symbolColors = {
    W: ["#F4F2DD", "#212117"],
    U: ["#ADDDF4", "#121B38"],
    B: ["#DDD1DB", "#121212"],
    R: ["#EFA487", "#330A10"],
    G: ["#9AD1A9", "#1D2315"],
    C: ["#CCCCCC", "#000000"]
  };

  function renderColorIdentity(cell, value) {
    cell.classList.add("colour-identity");
    cell.dataset.value = canonicalColors(value) === "C" ? "" : canonicalColors(value);
    const letters = (Array.isArray(value) ? value.join("") : String(value || ""))
      .toUpperCase().split("").filter((letter) => symbolColors[letter]);
    cell.replaceChildren();
    if (!letters.length) {
      cell.append(makeBadge("C", symbolColors.C, "mana-badge colorless-badge"));
      return;
    }
    letters.forEach((letter) => cell.append(makeBadge(letter, symbolColors[letter])));
  }

  function renderManaCost(cell, value) {
    cell.classList.add("mana-cost");
    cell.dataset.value = value || "";
    const symbols = String(value || "").match(/\{[^}]+\}|[^{}]+/g) || [];
    cell.replaceChildren();
    symbols.forEach((part) => {
      const match = part.match(/^\{([^}]+)\}$/);
      if (!match) {
        if (part.trim()) cell.append(document.createTextNode(part));
        return;
      }

      const symbol = match[1].toUpperCase();
      let background = symbolColors.C;
      let label = symbol;
      let badgeClass = "mana-badge";

      if (symbolColors[symbol]) {
        background = symbolColors[symbol];
      } else if (/^\d+$/.test(symbol) || symbol === "X") {
        badgeClass += " generic-badge";
      } else if (symbol.includes("/")) {
        const letters = symbol.split("/");
        const known = letters.find((letter) => symbolColors[letter]);
        background = known ? symbolColors[known] : symbolColors.C;
        label = symbol.replaceAll("P", "ᵖ");
        badgeClass += " hybrid-badge";
      }

      cell.append(makeBadge(label, background, badgeClass));
    });
  }

  function makeCommanderCells(commander, rowSpan) {
    const cells = [];
    const name = makeCell(commander.name);
    if (rowSpan > 1) name.rowSpan = rowSpan;
    cells.push(name);

    const identity = makeCell();
    if (rowSpan > 1) identity.rowSpan = rowSpan;
    renderColorIdentity(identity, commander.color_identity || commander.colors);
    cells.push(identity);

    const manaCost = makeCell();
    if (rowSpan > 1) manaCost.rowSpan = rowSpan;
    renderManaCost(manaCost, commander.mana_cost);
    cells.push(manaCost);

    const cmc = makeCell(
      commander.cmc === null || commander.cmc === undefined ? "" : commander.cmc,
      "numeric-cell"
    );
    if (rowSpan > 1) cmc.rowSpan = rowSpan;
    cells.push(cmc);

    const type = makeCell(commander.type_line || "");
    if (rowSpan > 1) type.rowSpan = rowSpan;
    cells.push(type);

    cells.push(makeStatusCell(commander.built, `${commander.name} built`, rowSpan));
    return cells;
  }

  function makeDeckCells(deck, commanderName) {
    const done = makeStatusCell(deck ? deck.done : false, `${deck?.deck_name || commanderName} done`);
    const deckCell = makeCell("", "");
    if (deck) {
      const link = document.createElement("a");
      link.className = "deck-link";
      link.href = deck.deck_id ? `#deck-${encodeURIComponent(deck.deck_id)}` : "#";
      link.textContent = deck.deck_name || "";
      link.addEventListener("click", (event) => event.preventDefault());
      deckCell.append(link);
    }
    const bracketCell = makeCell("", "");
    if (deck && deck.bracket !== null && deck.bracket !== undefined && deck.bracket !== "") {
      const bracket = document.createElement("span");
      bracket.className = "bracket-value";
      bracket.textContent = String(deck.bracket);
      bracketCell.append(bracket);
    }
    return [done, deckCell, bracketCell];
  }

  function getVisibleDecks(commander) {
    const deckQuery = normalize(deckSearch.value);
    const selectedBracket = bracketFilter.value;

    return commander.decks.filter((deck) => {
      const matchesDeck = !deckQuery || normalize(deck.deck_name).includes(deckQuery);
      const hasBracket = deck.bracket !== null && deck.bracket !== undefined && deck.bracket !== "";
      const matchesBracket = !selectedBracket ||
        (selectedBracket === "unassigned" ? !hasBracket : String(deck.bracket) === selectedBracket);
      const matchesDone = !doneFilter.checked || Boolean(deck.done);
      return matchesDeck && matchesBracket && matchesDone;
    });
  }

  function applyFilters() {
    const commanderQuery = normalize(commanderSearch.value);
    const selectedColor = colorFilter.value ? canonicalColors(colorFilter.value) : "";
    const rows = document.createDocumentFragment();
    let visibleCommanderCount = 0;
    let visibleDeckRows = 0;

    const filteredCommanders = commanders.filter((commander) => {
      const matchesCommander = !commanderQuery || normalize(commander.name).includes(commanderQuery);
      const matchesColor = !selectedColor ||
        canonicalColors(commander.color_identity || commander.colors) === selectedColor;
      const matchesBuilt = !builtFilter.checked || Boolean(commander.built);
      return matchesCommander && matchesColor && matchesBuilt;
    });

    filteredCommanders.forEach((commander) => {
      let visibleDecks = getVisibleDecks(commander);

      // A commander with no associated decks still has a catalogue row, unless a
      // deck-level filter requires a deck to exist.
      if (!commander.decks.length) {
        if (deckSearch.value.trim() || doneFilter.checked ||
            (bracketFilter.value && bracketFilter.value !== "unassigned")) {
          return;
        }
        visibleDecks = [];
      }

      if (commander.decks.length && visibleDecks.length === 0) return;

      visibleCommanderCount += 1;
      const rowCount = Math.max(visibleDecks.length, 1);
      visibleDeckRows += rowCount;

      if (!visibleDecks.length) {
        const row = document.createElement("tr");
        row.dataset.name = commander.name || "";
        row.dataset.colors = canonicalColors(commander.color_identity || commander.colors);
        row.append(...makeCommanderCells(commander, 1));
        row.append(makeCell("", "center-cell"), makeCell(""), makeCell(""));
        rows.append(row);
        return;
      }

      visibleDecks.forEach((deck, index) => {
        const row = document.createElement("tr");
        row.dataset.name = commander.name || "";
        row.dataset.colors = canonicalColors(commander.color_identity || commander.colors);
        row.dataset.deckName = deck.deck_name || "";
        row.dataset.bracket = deck.bracket ?? "";
        if (index === 0) row.append(...makeCommanderCells(commander, rowCount));
        row.append(...makeDeckCells(deck, commander.name));
        rows.append(row);
      });
    });

    tableBody.replaceChildren(rows);
    resultCount.textContent =
      `Showing ${visibleCommanderCount.toLocaleString()} of ${commanders.length.toLocaleString()} commanders · ${visibleDeckRows.toLocaleString()} rows`;
    emptyState.hidden = visibleCommanderCount !== 0;
  }

  function selectColor(value, label) {
    colorFilter.value = value;
    colorLabel.textContent = label;
    colorTrigger.setAttribute("aria-expanded", "false");
    colorMenu.hidden = true;
    colorMenu.querySelectorAll("[data-color]").forEach((option) => {
      option.setAttribute("aria-pressed", String(option.dataset.color === value));
    });
    applyFilters();
  }

  colorTrigger.addEventListener("click", () => {
    const isOpen = colorTrigger.getAttribute("aria-expanded") === "true";
    colorTrigger.setAttribute("aria-expanded", String(!isOpen));
    colorMenu.hidden = isOpen;
  });

  colorMenu.querySelectorAll("[data-color]").forEach((option) => {
    option.addEventListener("click", () => selectColor(option.dataset.color, option.dataset.label));
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".color-filter")) {
      colorMenu.hidden = true;
      colorTrigger.setAttribute("aria-expanded", "false");
    }
  });

  [commanderSearch, deckSearch, bracketFilter, builtFilter, doneFilter].forEach((control) => {
    control.addEventListener("input", applyFilters);
    control.addEventListener("change", applyFilters);
  });

  resetButton.addEventListener("click", () => {
    commanderSearch.value = "";
    deckSearch.value = "";
    bracketFilter.value = "";
    builtFilter.checked = false;
    doneFilter.checked = false;
    selectColor("", "All Colors");
    commanderSearch.focus();
  });

  async function loadCommanders() {
    try {
      resultCount.textContent = "Loading commander catalogue…";
      const response = await fetch("/api/commanders");
      if (!response.ok) throw new Error(`Request failed (${response.status})`);
      const payload = await response.json();
      commanders = (payload.commanders || []).map((commander) => ({
        ...commander,
        decks: Array.isArray(commander.decks) ? commander.decks : []
      })).sort((a, b) => normalize(a.name).localeCompare(normalize(b.name)));

      applyFilters();
      const note = document.querySelector(".prototype-note");
      if (note) note.textContent = "Commander data and deck associations are loaded from the local project datasets.";
    } catch (error) {
      console.error("Unable to load the Decklog commander catalogue:", error);
      tableBody.replaceChildren();
      resultCount.textContent = "Commander data could not be loaded.";
      emptyState.hidden = false;
      const message = emptyState.querySelector("strong");
      if (message) message.textContent = "Unable to load commander data.";
      const detail = emptyState.querySelector("span");
      if (detail) detail.textContent = "Check that the application server is running and the project JSON files are available.";
    }
  }

  selectColor("", "All Colors");
  loadCommanders();
})();
