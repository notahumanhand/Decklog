/* Client-side interactions for the hard-coded homepage wireframe. */
(() => {
  const commanderSearch = document.getElementById("commander-search");
  const deckSearch = document.getElementById("deck-search");
  const colorFilter = document.getElementById("color-filter");
  const colorTrigger = document.getElementById("color-filter-trigger");
  const colorMenu = document.getElementById("color-filter-menu");
  const colorLabel = document.getElementById("color-filter-label");
  const bracketFilter = document.getElementById("bracket-filter");
  const resetButton = document.getElementById("reset-filters");
  const resultCount = document.getElementById("result-count");
  const emptyState = document.getElementById("empty-state");
  const rows = Array.from(document.querySelectorAll("#commander-table-body tr"));
  const colorOrder = "WUBRG";

  function normalize(value) {
    return String(value || "").toLocaleLowerCase().trim();
  }

  function canonicalColors(value) {
    const letters = new Set(String(value || "").toUpperCase().split(""));
    return colorOrder.split("").filter((letter) => letters.has(letter)).join("") || "C";
  }

  function getRowDeckName(row) {
    return row.dataset.deckName || row.querySelector(".deck-link")?.textContent || "";
  }

  function applyFilters() {
    const commanderQuery = normalize(commanderSearch.value);
    const deckQuery = normalize(deckSearch.value);
    const selectedColor = colorFilter.value;
    const selectedBracket = bracketFilter.value;
    let visible = 0;

    rows.forEach((row) => {
      const name = normalize(row.dataset.name);
      const deckName = normalize(getRowDeckName(row));
      const rowColors = canonicalColors(row.dataset.colors);
      const rowBracket = row.dataset.bracket || "";

      // String.includes enforces a contiguous, case-insensitive substring match.
      const matchesCommander = !commanderQuery || name.includes(commanderQuery);
      const matchesDeck = !deckQuery || deckName.includes(deckQuery);
      const matchesColor = !selectedColor || rowColors === selectedColor;
      const matchesBracket = !selectedBracket ||
        (selectedBracket === "unassigned" ? !rowBracket : rowBracket === selectedBracket);
      const matches = matchesCommander && matchesDeck && matchesColor && matchesBracket;

      row.hidden = !matches;
      if (matches) visible += 1;
    });

    resultCount.textContent = `Showing ${visible} of ${rows.length} sample commanders`;
    emptyState.hidden = visible !== 0;
  }

  function selectColor(value, label) {
    colorFilter.value = value;
    colorLabel.textContent = label;
    colorTrigger.setAttribute("aria-expanded", "false");
    colorMenu.hidden = true;
    colorMenu.querySelectorAll("[data-color]").forEach((option) => {
      const selected = option.dataset.color === value;
      option.setAttribute("aria-pressed", String(selected));
    });
    applyFilters();
  }

  colorTrigger.addEventListener("click", () => {
    const isOpen = colorTrigger.getAttribute("aria-expanded") === "true";
    colorTrigger.setAttribute("aria-expanded", String(!isOpen));
    colorMenu.hidden = isOpen;
  });

  colorMenu.querySelectorAll("[data-color]").forEach((option) => {
    option.addEventListener("click", () => {
      selectColor(option.dataset.color, option.dataset.label);
    });
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".color-filter")) {
      colorMenu.hidden = true;
      colorTrigger.setAttribute("aria-expanded", "false");
    }
  });

  [commanderSearch, deckSearch, bracketFilter].forEach((control) => {
    control.addEventListener("input", applyFilters);
    control.addEventListener("change", applyFilters);
  });

  resetButton.addEventListener("click", () => {
    commanderSearch.value = "";
    deckSearch.value = "";
    bracketFilter.value = "";
    selectColor("", "All Colors");
    applyFilters();
    commanderSearch.focus();
  });

  // Render letter circles from the readable text already in each cell.
  const symbolColors = {
    W: ["#F4F2DD", "#212117"],
    U: ["#ADDDF4", "#121B38"],
    B: ["#DDD1DB", "#121212"],
    R: ["#EFA487", "#330A10"],
    G: ["#9AD1A9", "#1D2315"],
    C: ["#CCCCCC", "#000000"]
  };

  function makeBadge(label, color, className = "mana-badge") {
    const badge = document.createElement("span");
    badge.className = className;
    badge.textContent = label;
    badge.style.setProperty("--symbol-bg", color[0]);
    badge.style.setProperty("--symbol-text", color[1]);
    badge.setAttribute("aria-hidden", "true");
    return badge;
  }

  document.querySelectorAll(".colour-identity").forEach((cell) => {
    const raw = cell.dataset.value || cell.textContent.trim();
    const letters = raw.toUpperCase().split("").filter((letter) => symbolColors[letter]);
    cell.textContent = "";
    if (!letters.length) {
      cell.append(makeBadge("C", symbolColors.C, "mana-badge colorless-badge"));
      return;
    }
    letters.forEach((letter) => cell.append(makeBadge(letter, symbolColors[letter])));
  });

  document.querySelectorAll(".mana-cost").forEach((cell) => {
    const raw = cell.dataset.value || cell.textContent.trim();
    const symbols = raw.match(/\{[^}]+\}|[^{}]+/g) || [];
    cell.textContent = "";
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
        background = symbolColors.C;
        badgeClass += " generic-badge";
      } else if (symbol.includes("/")) {
        // Preserve hybrid/phyrexian costs as one legible circle.
        const letters = symbol.split("/");
        const known = letters.find((letter) => symbolColors[letter]);
        background = known ? symbolColors[known] : symbolColors.C;
        label = symbol.replaceAll("P", "ᵖ");
        badgeClass += " hybrid-badge";
      } else {
        background = symbolColors.C;
      }

      cell.append(makeBadge(label, background, badgeClass));
    });
  });

  document.querySelectorAll("[data-placeholder-link]").forEach((link) => {
    link.addEventListener("click", (event) => event.preventDefault());
  });

  selectColor("", "All Colors");
  applyFilters();
})();
