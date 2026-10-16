/* Collection statistics derived from Decklog's local catalogue and decklist APIs. */
(() => {
  "use strict";

  const COLOUR_ORDER = "WUBRG";
  const COLOURS = {
    W: "#F4F2DD", U: "#ADDDF4", B: "#DDD1DB",
    R: "#EFA487", G: "#9AD1A9", C: "#CCCCCC"
  };
  const COLOUR_TEXT = {
    W: "#212117", U: "#121B38", B: "#121212",
    R: "#330A10", G: "#1D2315", C: "#000000"
  };
  const IDENTITY_NAMES = {
    C: "Colourless", W: "White", U: "Blue", B: "Black", R: "Red", G: "Green",
    WU: "Azorius", UB: "Dimir", BR: "Rakdos", RG: "Gruul", GW: "Selesnya",
    WB: "Orzhov", UR: "Izzet", BG: "Golgari", RW: "Boros", GU: "Simic",
    WUB: "Esper", UBR: "Grixis", BRG: "Jund", RGW: "Naya", GWU: "Bant",
    WBG: "Abzan", WUR: "Jeskai", UBG: "Sultai", WBR: "Mardu", URG: "Temur",
    WUBR: "Yore-Tiller", WUBG: "Glint-Eye", WURG: "Dune-Brood",
    WBRG: "Ink-Treader", UBRG: "Witch-Maw", WUBRG: "Five Colour"
  };
  const GROUPS = [
    { title: "Zero or One Colour", identities: ["C", "W", "U", "B", "R", "G"] },
    { title: "Two Colours", identities: ["WU", "UB", "BR", "RG", "GW", "WB", "UR", "BG", "RW", "GU"] },
    { title: "Three Colours", identities: ["WUB", "UBR", "BRG", "RGW", "GWU", "WBG", "WUR", "UBG", "WBR", "URG"] },
    { title: "Four or Five Colours", identities: ["WUBR", "WUBG", "WURG", "WBRG", "UBRG", "WUBRG"] }
  ];
  const STATUS_COLOURS = { Unbuilt: "#777a76", Unfinished: "#b39a5b", Complete: "#78a78a" };

  const byId = id => document.getElementById(id);
  const formatNumber = value => Number(value || 0).toLocaleString();
  const percent = (part, total) => total ? `${(part / total * 100).toFixed(1)}%` : "0.0%";

  function canonicalColors(value) {
    const source = Array.isArray(value) ? value.join("") : String(value || "");
    const found = new Set(source.toUpperCase().split(""));
    return COLOUR_ORDER.split("").filter(letter => found.has(letter)).join("") || "C";
  }

  function commanderIdSet(deck) {
    return [deck.commander_id, deck.secondary_commander_id, deck.companion_id]
      .filter(value => value !== null && value !== undefined && String(value).trim() !== "")
      .map(String);
  }

  function setText(id, value) { byId(id).textContent = value; }

  function renderCommanderStatus(commanders, deckCount) {
    const totals = { Unbuilt: 0, Unfinished: 0, Complete: 0 };
    commanders.forEach(commander => {
      const linkedDecks = Array.isArray(commander.decks) ? commander.decks : [];
      if (!linkedDecks.length) totals.Unbuilt += 1;
      else if (linkedDecks.some(deck => Boolean(deck.done))) totals.Complete += 1;
      else totals.Unfinished += 1;
    });

    const total = commanders.length;
    const pie = byId("commander-status-pie");
    let start = 0;
    const segments = Object.entries(totals).map(([name, count]) => {
      const end = start + (total ? count / total * 100 : 0);
      const segment = `${STATUS_COLOURS[name]} ${start}% ${end}%`;
      start = end;
      return segment;
    });
    pie.style.background = total ? `conic-gradient(${segments.join(", ")})` : "#343633";
    pie.innerHTML = `<span>${formatNumber(total)}<small>commanders</small></span>`;
    pie.setAttribute("aria-label", Object.entries(totals).map(([name, count]) => `${name}: ${count}`).join(", "));

    const legend = byId("commander-status-legend");
    legend.replaceChildren();
    Object.entries(totals).forEach(([name, count]) => {
      const item = document.createElement("li");
      const swatch = document.createElement("span");
      swatch.className = "chart-legend-swatch";
      swatch.style.backgroundColor = STATUS_COLOURS[name];
      swatch.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.className = "chart-legend-label";
      label.textContent = name;
      const value = document.createElement("strong");
      value.textContent = `${formatNumber(count)} · ${percent(count, total)}`;
      item.append(swatch, label, value);
      legend.append(item);
    });
  }

  function mixColours(identity) {
    if (identity === "C" || identity.length >= 4) return [COLOURS.C, COLOUR_TEXT.C];
    const letters = identity.split("");
    const rgb = letter => {
      const hex = COLOURS[letter].slice(1);
      return [0, 2, 4].map(index => parseInt(hex.slice(index, index + 2), 16));
    };
    let weights;
    if (letters.length === 1) return [COLOURS[letters[0]], COLOUR_TEXT[letters[0]]];
    if (letters.length === 2) weights = [0.5, 0.5];
    else weights = [0.6, 0.3, 0.1];
    const channels = [0, 1, 2].map(channel => Math.round(letters.reduce((sum, letter, index) => sum + rgb(letter)[channel] * (weights[index] || 0), 0)));
    const background = `#${channels.map(channel => channel.toString(16).padStart(2, "0")).join("")}`;
    // Choose readable dark text for blended backgrounds.
    const luminance = (channels[0] * 299 + channels[1] * 587 + channels[2] * 114) / 1000;
    return [background, luminance < 145 ? "#ffffff" : "#171815"];
  }

  function renderColourIdentities(decks, commandersById) {
    const counts = new Map();
    decks.forEach(deck => {
      const primary = commandersById.get(String(deck.commander_id));
      const secondary = deck.secondary_commander_id ? commandersById.get(String(deck.secondary_commander_id)) : null;
      const colours = [...(primary?.color_identity || []), ...(secondary?.color_identity || [])];
      const identity = canonicalColors(colours);
      counts.set(identity, (counts.get(identity) || 0) + 1);
    });

    const totalDecks = decks.length;
    const container = byId("colour-identity-sections");
    container.replaceChildren();
    GROUPS.forEach(group => {
      const identities = group.identities.filter(identity => counts.get(identity));
      if (!identities.length) return;
      const groupCount = identities.reduce((sum, identity) => sum + counts.get(identity), 0);
      const section = document.createElement("section");
      section.className = "identity-group";
      const heading = document.createElement("div");
      heading.className = "identity-group-heading";
      const title = document.createElement("h3");
      title.textContent = group.title;
      const summary = document.createElement("span");
      summary.textContent = `${formatNumber(groupCount)} decks · ${percent(groupCount, totalDecks)}`;
      heading.append(title, summary);
      const track = document.createElement("div");
      track.className = "identity-group-track";
      track.setAttribute("role", "img");
      track.setAttribute("aria-label", `${group.title}: ${percent(groupCount, totalDecks)} of all decks`);
      const fill = document.createElement("span");
      fill.style.width = `${totalDecks ? groupCount / totalDecks * 100 : 0}%`;
      track.append(fill);
      const grid = document.createElement("div");
      grid.className = "identity-tile-grid";

      identities.forEach(identity => {
        const count = counts.get(identity);
        const [background, foreground] = mixColours(identity);
        const tile = document.createElement("a");
        tile.className = "identity-tile";
        tile.href = `/decks?colors=${encodeURIComponent(identity)}`;
        tile.style.setProperty("--identity-bg", background);
        tile.style.setProperty("--identity-text", foreground);
        tile.setAttribute("aria-label", `${IDENTITY_NAMES[identity]} (${identity}), ${count} decks, ${percent(count, totalDecks)} of all decks`);
        const name = document.createElement("span");
        name.className = "identity-tile-name";
        name.textContent = IDENTITY_NAMES[identity] || identity;
        const code = document.createElement("span");
        code.className = "identity-tile-code";
        code.textContent = identity === "C" ? "C" : identity;
        const value = document.createElement("strong");
        value.className = "identity-tile-percent";
        value.textContent = percent(count, totalDecks);
        const countLabel = document.createElement("span");
        countLabel.className = "identity-tile-count";
        countLabel.textContent = `${formatNumber(count)} ${count === 1 ? "deck" : "decks"}`;
        tile.append(code, name, value, countLabel);
        grid.append(tile);
      });
      section.append(heading, track, grid);
      container.append(section);
    });
    if (!container.children.length) {
      const message = document.createElement("p");
      message.className = "stats-loading";
      message.textContent = "No deck colour identities are available yet.";
      container.append(message);
    }
  }

  function renderBracketChart(decks) {
    const svg = byId("bracket-chart");
    const NS = "http://www.w3.org/2000/svg";
    const chartWidth = 640, chartHeight = 280;
    const margin = { top: 18, right: 20, bottom: 42, left: 42 };
    const width = chartWidth - margin.left - margin.right;
    const height = chartHeight - margin.top - margin.bottom;
    const counts = [1, 2, 3, 4, 5].map(bracket => decks.filter(deck => Number(deck.bracket) === bracket).length);
    const maxCount = Math.max(1, ...counts);
    const excluded = decks.filter(deck => deck.bracket === null || deck.bracket === undefined || deck.bracket === "").length;
    svg.replaceChildren();
    svg.setAttribute("viewBox", `0 0 ${chartWidth} ${chartHeight}`);

    function element(tag, attrs = {}, text = "") {
      const node = document.createElementNS(NS, tag);
      Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
      if (text !== "") node.textContent = text;
      return node;
    }

    for (let tick = 0; tick <= 4; tick += 1) {
      const value = maxCount * tick / 4;
      const y = margin.top + height - value / maxCount * height;
      svg.append(element("line", { x1: margin.left, x2: chartWidth - margin.right, y1: y, y2: y, class: "bracket-grid-line" }));
      svg.append(element("text", { x: margin.left - 10, y: y + 4, "text-anchor": "end", class: "bracket-axis-label" }, String(Math.round(value))));
    }
    const slot = width / 5;
    const barWidth = Math.min(58, slot * 0.56);
    counts.forEach((count, index) => {
      const barHeight = count / maxCount * height;
      const x = margin.left + slot * index + (slot - barWidth) / 2;
      const y = margin.top + height - barHeight;
      svg.append(element("rect", { x, y, width: barWidth, height: Math.max(0, barHeight), rx: 4, class: "bracket-bar" }));
      svg.append(element("text", { x: x + barWidth / 2, y: Math.max(12, y - 7), "text-anchor": "middle", class: "bracket-value-label" }, String(count)));
      svg.append(element("text", { x: x + barWidth / 2, y: chartHeight - 15, "text-anchor": "middle", class: "bracket-axis-label" }, `Bracket ${index + 1}`));
    });
    setText("bracket-excluded-note", `Unassigned Brackets: ${formatNumber(excluded)} ${excluded === 1 ? "deck" : "decks"} excluded`);
  }

  async function loadStats() {
    try {
      const [commanderResponse, deckResponse] = await Promise.all([
        fetch("/api/commanders"), fetch("/api/decks")
      ]);
      if (!commanderResponse.ok || !deckResponse.ok) throw new Error("The Decklog API returned an error while loading statistics.");
      const [commanderPayload, deckPayload] = await Promise.all([commanderResponse.json(), deckResponse.json()]);
      const commanders = Array.isArray(commanderPayload.commanders) ? commanderPayload.commanders : [];
      const decks = Array.isArray(deckPayload.decks) ? deckPayload.decks : [];
      const commandersById = new Map(commanders.map(commander => [String(commander.oracle_id), commander]));

      const builtCommanderCount = commanders.filter(commander => Array.isArray(commander.decks) && commander.decks.length > 0).length;
      const doneDecks = decks.filter(deck => Boolean(deck.done)).length;
      setText("total-commanders", formatNumber(commanders.length));
      setText("total-decks", formatNumber(decks.length));
      setText("commanders-built-percent", percent(builtCommanderCount, commanders.length));
      setText("commanders-built-detail", `${formatNumber(builtCommanderCount)} of ${formatNumber(commanders.length)} commanders`);
      setText("decks-done-percent", percent(doneDecks, decks.length));
      setText("decks-done-detail", `${formatNumber(doneDecks)} of ${formatNumber(decks.length)} decks marked done`);

      const lastUpdated = deckPayload.metadata?.last_updated;
      const updatedElement = byId("last-updated");
      if (lastUpdated) {
        const parsed = new Date(lastUpdated);
        updatedElement.textContent = Number.isNaN(parsed.getTime()) ? String(lastUpdated) : parsed.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
        if (!Number.isNaN(parsed.getTime())) updatedElement.dateTime = parsed.toISOString();
      } else updatedElement.textContent = "Not available";

      renderCommanderStatus(commanders, decks.length);
      renderColourIdentities(decks, commandersById);
      renderBracketChart(decks);
      byId("stats-error").hidden = true;
    } catch (error) {
      const errorBox = byId("stats-error");
      errorBox.textContent = `Unable to load statistics. ${error.message || "Please refresh the page or check the server logs."}`;
      errorBox.hidden = false;
      setText("last-updated", "Unavailable");
      byId("colour-identity-sections").textContent = "Colour identity statistics could not be loaded.";
      byId("commander-status-pie").textContent = "Unavailable";
      byId("bracket-chart").replaceChildren();
    }
  }

  loadStats();
})();
