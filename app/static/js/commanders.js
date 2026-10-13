/* Client-side interactions for the hard-coded homepage wireframe.
   This will be adapted to API-backed data in a later step. */
(() => {
  const searchInput = document.getElementById("commander-search");
  const colorFilter = document.getElementById("color-filter");
  const typeFilter = document.getElementById("type-filter");
  const bracketFilter = document.getElementById("bracket-filter");
  const resetButton = document.getElementById("reset-filters");
  const resultCount = document.getElementById("result-count");
  const emptyState = document.getElementById("empty-state");
  const rows = Array.from(document.querySelectorAll("#commander-table-body tr"));

  function normalize(value) {
    return (value || "").toLowerCase().trim();
  }

  function applyFilters() {
    const query = normalize(searchInput.value);
    const color = colorFilter.value;
    const type = normalize(typeFilter.value);
    const bracket = bracketFilter.value;
    let visible = 0;

    rows.forEach((row) => {
      const name = normalize(row.dataset.name);
      const rowColors = (row.dataset.colors || "").toUpperCase();
      const rowType = normalize(row.dataset.type);
      const rowBracket = row.dataset.bracket || "";
      const matchesQuery = !query || name.includes(query) ||
        normalize(row.textContent).includes(query);
      const matchesColor = !color || (color === "C" ? !rowColors : rowColors === color);
      const matchesType = !type || rowType.includes(type);
      const matchesBracket = !bracket ||
        (bracket === "unassigned" ? !rowBracket : rowBracket === bracket);
      const matches = matchesQuery && matchesColor && matchesType && matchesBracket;

      row.hidden = !matches;
      if (matches) visible += 1;
    });

    resultCount.textContent = `Showing ${visible} of ${rows.length} sample commanders`;
    emptyState.hidden = visible !== 0;
  }

  [searchInput, colorFilter, typeFilter, bracketFilter].forEach((control) => {
    control.addEventListener("input", applyFilters);
    control.addEventListener("change", applyFilters);
  });

  resetButton.addEventListener("click", () => {
    searchInput.value = "";
    colorFilter.value = "";
    typeFilter.value = "";
    bracketFilter.value = "";
    applyFilters();
    searchInput.focus();
  });

  document.querySelectorAll("[data-placeholder-link]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      // Other sections are intentionally placeholders in this first wireframe.
    });
  });

  applyFilters();
})();
