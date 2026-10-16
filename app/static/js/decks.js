/* Deck-centric collection rendering, filters, and pagination. */
(() => {
  const deckSearch = document.getElementById("deck-search");
  const commanderSearch = document.getElementById("commander-search");
  const colorFilter = document.getElementById("color-filter");
  const colorTrigger = document.getElementById("color-filter-trigger");
  const colorMenu = document.getElementById("color-filter-menu");
  const colorLabel = document.getElementById("color-filter-label");
  const bracketFilter = document.getElementById("bracket-filter");
  const statusFilter = document.getElementById("status-filter");
  const pageLengthSelect = document.getElementById("page-length");
  const pageLengthBottom = document.querySelector(".page-length-bottom");
  const paginationControls = document.querySelectorAll(".pagination");
  const resetButton = document.getElementById("reset-filters");
  const resultCount = document.getElementById("result-count");
  const emptyState = document.getElementById("empty-state");
  const tableBody = document.getElementById("decks-table-body");
  const colorOrder = "WUBRG";
  const symbolColors = {
    W: ["#F4F2DD", "#212117"], U: ["#ADDDF4", "#121B38"],
    B: ["#DDD1DB", "#121212"], R: ["#EFA487", "#330A10"],
    G: ["#9AD1A9", "#1D2315"], C: ["#CCCCCC", "#000000"]
  };
  let currentPage = 1;
  let pageLength = 10;
  let decks = [];

  function normalize(value) { return String(value ?? "").toLocaleLowerCase().trim(); }
  function canonicalColors(values) {
    const letters = new Set((Array.isArray(values) ? values.join("") : String(values || "")).toUpperCase().split(""));
    return colorOrder.split("").filter(letter => letters.has(letter)).join("") || "C";
  }
  function makeCell(text, className = "") {
    const cell = document.createElement("td");
    if (className) cell.className = className;
    cell.textContent = text ?? "";
    return cell;
  }
  function makeBadge(letter) {
    const badge = document.createElement("span");
    badge.className = `mana-badge${letter === "C" ? " colorless-badge" : ""}`;
    badge.textContent = letter;
    badge.style.setProperty("--symbol-bg", symbolColors[letter][0]);
    badge.style.setProperty("--symbol-text", symbolColors[letter][1]);
    badge.setAttribute("aria-label", letter);
    return badge;
  }
  function renderColors(cell, colors) {
    cell.className = "colour-identity";
    cell.dataset.value = colors === "C" ? "" : colors;
    cell.replaceChildren(...colors.split("").map(makeBadge));
  }
  function renderCommanders(cell, deck) {
    cell.className = "deck-commanders";
    const names = [];
    if (deck.commander) names.push({name: deck.commander.name, role: "primary"});
    if (deck.secondary_commander) names.push({name: deck.secondary_commander.name, role: "secondary"});
    names.forEach((commander, index) => {
      if (index) cell.append(document.createElement("br"));
      cell.append(document.createTextNode(commander.name));
    });
    if (deck.companion) {
      if (names.length) cell.append(document.createElement("br"));
      const label = document.createElement("span");
      label.className = "companion-label";
      label.textContent = `Companion: ${deck.companion.name}`;
      cell.append(label);
    }
    if (!names.length && !deck.companion) cell.textContent = "—";
  }
  function renderDone(cell, deck) {
    cell.className = "center-cell";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = Boolean(deck.done);
    checkbox.disabled = true;
    checkbox.setAttribute("aria-label", `${deck.deck_name || "Deck"} complete`);
    cell.append(checkbox);
  }
  function renderRow(deck) {
    const row = document.createElement("tr");
    row.dataset.deckName = deck.deck_name || "";
    row.dataset.colors = deck.combined_color_identity;
    row.dataset.bracket = deck.bracket ?? "";
    row.append(makeCell(deck.deck_name || "(Unnamed deck)", "deck-name-cell"));
    const commanders = makeCell("");
    renderCommanders(commanders, deck);
    row.append(commanders);
    const colors = makeCell("");
    renderColors(colors, deck.combined_color_identity);
    row.append(colors);
    const bracket = makeCell(deck.bracket === null || deck.bracket === undefined || deck.bracket === "" ? "" : String(deck.bracket), "bracket-cell");
    if (bracket.textContent) {
      const value = document.createElement("span");
      value.className = "bracket-value";
      value.textContent = bracket.textContent;
      bracket.replaceChildren(value);
    }
    row.append(bracket);
    const done = makeCell("");
    renderDone(done, deck);
    row.append(done);
    return row;
  }
  function updatePagination(pageCount, visibleCount) {
    paginationControls.forEach(nav => {
      nav.querySelector('[data-page="first"]').disabled = currentPage === 1;
      nav.querySelector('[data-page="previous"]').disabled = currentPage === 1;
      nav.querySelector('[data-page="next"]').disabled = currentPage === pageCount;
      nav.querySelector('[data-page="last"]').disabled = currentPage === pageCount;
    });
    const pageItems = Math.min(pageLength, Math.max(0, visibleCount - (currentPage - 1) * pageLength));
    resultCount.textContent = `${allDeckCount.toLocaleString()} decks · Showing ${pageItems.toLocaleString()} of ${visibleCount.toLocaleString()} decks · Page ${currentPage} of ${pageCount}`;
  }
  let allDeckCount = 0;
  function applyFilters() {
    const deckQuery = normalize(deckSearch.value);
    const commanderQuery = normalize(commanderSearch.value);
    const selectedColor = colorFilter.value ? canonicalColors(colorFilter.value) : "";
    const selectedBracket = bracketFilter.value;
    const status = statusFilter.value;
    const filtered = decks.filter(deck => {
      const commanderNames = [deck.commander?.name, deck.secondary_commander?.name, deck.companion?.name].filter(Boolean).join(" ");
      const matchesDeck = !deckQuery || normalize(deck.deck_name).includes(deckQuery);
      const matchesCommander = !commanderQuery || normalize(commanderNames).includes(commanderQuery);
      const matchesColor = !selectedColor || deck.combined_color_identity === selectedColor;
      const hasBracket = deck.bracket !== null && deck.bracket !== undefined && deck.bracket !== "";
      const matchesBracket = !selectedBracket || (selectedBracket === "unassigned" ? !hasBracket : String(deck.bracket) === selectedBracket);
      const matchesStatus = status === "all" || (status === "complete" ? Boolean(deck.done) : !deck.done);
      return matchesDeck && matchesCommander && matchesColor && matchesBracket && matchesStatus;
    }).sort((a, b) => normalize(a.deck_name).localeCompare(normalize(b.deck_name)) || String(a.deck_id).localeCompare(String(b.deck_id)));

    const pageCount = Math.max(1, Math.ceil(filtered.length / pageLength));
    currentPage = Math.min(currentPage, pageCount);
    const start = (currentPage - 1) * pageLength;
    const fragment = document.createDocumentFragment();
    filtered.slice(start, start + pageLength).forEach(deck => fragment.append(renderRow(deck)));
    tableBody.replaceChildren(fragment);
    emptyState.hidden = filtered.length !== 0;
    updatePagination(pageCount, filtered.length);
  }
  function resetPage() { currentPage = 1; applyFilters(); }

  [deckSearch, commanderSearch].forEach(input => input.addEventListener("input", resetPage));
  [bracketFilter, statusFilter].forEach(input => input.addEventListener("change", resetPage));
  colorTrigger.addEventListener("click", () => {
    const opening = colorMenu.hidden;
    colorMenu.hidden = !opening;
    colorTrigger.setAttribute("aria-expanded", String(opening));
  });
  colorMenu.addEventListener("click", event => {
    const option = event.target.closest(".color-option");
    if (!option) return;
    colorFilter.value = option.dataset.color || "";
    colorLabel.textContent = option.dataset.label || "All Colours";
    colorMenu.querySelectorAll(".color-option").forEach(button => button.setAttribute("aria-pressed", String(button === option)));
    colorMenu.hidden = true;
    colorTrigger.setAttribute("aria-expanded", "false");
    resetPage();
  });
  document.addEventListener("click", event => {
    if (!event.target.closest(".color-filter")) {
      colorMenu.hidden = true;
      colorTrigger.setAttribute("aria-expanded", "false");
    }
  });
  resetButton.addEventListener("click", () => {
    deckSearch.value = "";
    commanderSearch.value = "";
    colorFilter.value = "";
    colorLabel.textContent = "All Colours";
    colorMenu.querySelectorAll(".color-option").forEach(button => button.setAttribute("aria-pressed", String(!button.dataset.color)));
    bracketFilter.value = "";
    statusFilter.value = "all";
    resetPage();
  });
  paginationControls.forEach(nav => nav.addEventListener("click", event => {
    const button = event.target.closest("button[data-page]");
    if (!button || button.disabled) return;
    const pageCount = Math.max(1, Math.ceil(getFilteredDecks().length / pageLength));
    if (button.dataset.page === "first") currentPage = 1;
    if (button.dataset.page === "previous") currentPage--;
    if (button.dataset.page === "next") currentPage++;
    if (button.dataset.page === "last") currentPage = pageCount;
    applyFilters();
  }));
  function getFilteredDecks() {
    // Used only to calculate the last page; applyFilters remains the source of display filtering.
    const query = normalize(deckSearch.value), cq = normalize(commanderSearch.value);
    const color = colorFilter.value ? canonicalColors(colorFilter.value) : "";
    return decks.filter(deck => {
      const names = [deck.commander?.name, deck.secondary_commander?.name, deck.companion?.name].filter(Boolean).join(" ");
      const hasBracket = deck.bracket !== null && deck.bracket !== undefined && deck.bracket !== "";
      return (!query || normalize(deck.deck_name).includes(query)) &&
        (!cq || normalize(names).includes(cq)) &&
        (!color || deck.combined_color_identity === color) &&
        (!bracketFilter.value || (bracketFilter.value === "unassigned" ? !hasBracket : String(deck.bracket) === bracketFilter.value)) &&
        (statusFilter.value === "all" || (statusFilter.value === "complete" ? Boolean(deck.done) : !deck.done));
    });
  }
  function changePageLength(value) {
    pageLength = Number(value) || 10;
    pageLengthSelect.value = String(pageLength);
    pageLengthBottom.value = String(pageLength);
    resetPage();
  }
  pageLengthSelect.addEventListener("change", () => changePageLength(pageLengthSelect.value));
  pageLengthBottom.addEventListener("change", () => changePageLength(pageLengthBottom.value));

  function initialiseFiltersFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const requestedColor = params.get("colors") || params.get("color") || "";
    if (!requestedColor) return;

    const canonical = canonicalColors(requestedColor);
    const option = Array.from(colorMenu.querySelectorAll(".color-option"))
      .find(button => button.dataset.color !== undefined && button.dataset.color !== "" && canonicalColors(button.dataset.color) === canonical);
    colorFilter.value = canonical;
    colorLabel.textContent = option?.dataset.label || (canonical === "C" ? "Colourless" : canonical);
    colorMenu.querySelectorAll(".color-option").forEach(button => {
      button.setAttribute("aria-pressed", String(button === option));
    });
  }

  async function loadDecks() {
    try {
      const [commanderResponse, deckResponse] = await Promise.all([fetch("/api/commanders"), fetch("/api/decks")]);
      if (!commanderResponse.ok || !deckResponse.ok) throw new Error("The Decklog API returned an error.");
      const commanderPayload = await commanderResponse.json();
      const deckPayload = await deckResponse.json();
      const commandersById = new Map();
      (commanderPayload.commanders || []).forEach(commander => commandersById.set(String(commander.oracle_id), commander));
      const sourceDecks = deckPayload.decks || [];
      decks = sourceDecks.map(deck => {
        const commander = commandersById.get(String(deck.commander_id)) || null;
        const secondary = deck.secondary_commander_id ? commandersById.get(String(deck.secondary_commander_id)) || null : null;
        const companion = deck.companion_id ? commandersById.get(String(deck.companion_id)) || null : null;
        const colorValues = [...(commander?.color_identity || []), ...(secondary?.color_identity || [])];
        return {...deck, commander, secondary_commander: secondary, companion, combined_color_identity: canonicalColors(colorValues)};
      });
      allDeckCount = decks.length;
      applyFilters();
    } catch (error) {
      resultCount.textContent = "Unable to load decks. Please refresh the page or check the server logs.";
      emptyState.hidden = false;
      emptyState.querySelector("strong").textContent = "Deck data could not be loaded.";
      emptyState.querySelector("span").textContent = error.message;
    }
  }
  initialiseFiltersFromUrl();
  loadDecks();
})();
