// Brawl Drafting AI — frontend
const SLOTS = 3;
const LS_OWNED = "bda.ownedBrawlerIds";
const LS_FILTER = "bda.filterToOwned";

const state = {
  brawlers: [],         // [{id, name, className, rarity, imageUrl}]
  brawlersByName: {},
  maps: [],             // [{id, name, mode, imageUrl}]
  mapsByMode: {},
  selectedMode: null,
  selectedMapId: null,
  yourTeam: [null, null, null],
  enemyTeam: [null, null, null],
  yourSlot: 0,
  pickerTarget: null,   // { side: 'you'|'enemy', index: 0..2 }
  ownedBrawlerIds: new Set(),  // hydrated from localStorage in init()
  filterToOwned: false,
};

const $ = (id) => document.getElementById(id);
const setStatus = (msg) => { $("status").textContent = msg || ""; };

// ---------------------------- Init ----------------------------
async function init() {
  const [brawlers, maps] = await Promise.all([
    fetch("/api/brawlers").then((r) => r.json()),
    fetch("/api/maps").then((r) => r.json()),
  ]);
  state.brawlers = brawlers.sort((a, b) => a.name.localeCompare(b.name));
  state.brawlersByName = Object.fromEntries(brawlers.map((b) => [b.name.toLowerCase(), b]));
  state.maps = maps;
  state.mapsByMode = maps.reduce((acc, m) => {
    (acc[m.mode] ||= []).push(m);
    return acc;
  }, {});

  hydrateCollection();
  populateModes();
  renderSlots();
  renderOwnedCount();
  bindActions();
}

function hydrateCollection() {
  try {
    const ids = JSON.parse(localStorage.getItem(LS_OWNED) || "null");
    if (Array.isArray(ids)) {
      state.ownedBrawlerIds = new Set(ids);
    } else {
      // First run: default to "all owned" so the filter is useful immediately if toggled on.
      state.ownedBrawlerIds = new Set(state.brawlers.map((b) => b.id));
      persistOwned();
    }
    state.filterToOwned = localStorage.getItem(LS_FILTER) === "1";
    $("filter-owned").checked = state.filterToOwned;
  } catch {
    state.ownedBrawlerIds = new Set(state.brawlers.map((b) => b.id));
  }
}

function persistOwned() {
  localStorage.setItem(LS_OWNED, JSON.stringify([...state.ownedBrawlerIds]));
}

function renderOwnedCount() {
  $("owned-count").textContent = state.ownedBrawlerIds.size;
}

// ---------------------------- Mode/map selectors ----------------------------
function populateModes() {
  const modes = Object.keys(state.mapsByMode).sort();
  const sel = $("mode-select");
  sel.innerHTML = modes.map((m) => `<option value="${m}">${m}</option>`).join("");
  sel.onchange = () => {
    state.selectedMode = sel.value;
    populateMaps();
  };
  state.selectedMode = modes[0];
  sel.value = state.selectedMode;
  populateMaps();
}

function populateMaps() {
  $("map-search").value = "";
  renderMapOptions("");
  $("map-search").oninput = (e) => renderMapOptions(e.target.value);
  $("map-select").onchange = () => {
    state.selectedMapId = parseInt($("map-select").value, 10);
    renderMapImage();
  };
}

function renderMapOptions(query) {
  const all = state.mapsByMode[state.selectedMode] || [];
  const q = (query || "").trim().toLowerCase();
  const filtered = q ? all.filter((m) => m.name.toLowerCase().includes(q)) : all;
  const sel = $("map-select");
  sel.innerHTML = filtered
    .map((m) => `<option value="${m.id}">${m.name}</option>`)
    .join("");
  // If the previously selected map is still in the filtered set, keep it; otherwise pick first.
  const stillThere = filtered.some((m) => m.id === state.selectedMapId);
  if (stillThere) {
    sel.value = state.selectedMapId;
  } else {
    state.selectedMapId = filtered[0]?.id || null;
    sel.value = state.selectedMapId || "";
  }
  renderMapImage();
}

function renderMapImage() {
  const m = state.maps.find((x) => x.id === state.selectedMapId);
  $("map-image").src = m?.imageUrl || "";
  $("map-image").alt = m?.name || "";
}

// ---------------------------- Team slots ----------------------------
function renderSlots() {
  $("slots-you").innerHTML = state.yourTeam.map((b, i) => slotHtml(b, "you", i)).join("");
  $("slots-enemy").innerHTML = state.enemyTeam.map((b, i) => slotHtml(b, "enemy", i)).join("");

  document.querySelectorAll(".slot-portrait").forEach((el) => {
    el.onclick = () => openPicker({ side: el.dataset.side, index: parseInt(el.dataset.index, 10) });
  });
  document.querySelectorAll(".slot-marker input").forEach((el) => {
    el.onchange = () => {
      state.yourSlot = parseInt(el.value, 10);
      renderSlots();
    };
  });
}

function slotHtml(brawler, side, index) {
  const isYouMarker = side === "you" && index === state.yourSlot;
  const cls = `slot ${isYouMarker ? "is-you-marker" : ""}`;
  const portrait = brawler
    ? `<img src="${brawler.imageUrl}" alt="${brawler.name}" />`
    : `<span class="placeholder">+</span>`;
  const name = brawler ? brawler.name : "—";
  const klass = brawler ? brawler.className : "";
  const marker = side === "you"
    ? `<label class="slot-marker"><input type="radio" name="yourSlot" value="${index}" ${isYouMarker ? "checked" : ""}/>my slot</label>`
    : "";
  return `
    <div class="${cls}">
      <div class="slot-portrait" data-side="${side}" data-index="${index}">${portrait}</div>
      <div class="slot-name">${name}</div>
      <div class="slot-class">${klass}</div>
      ${marker}
    </div>
  `;
}

// ---------------------------- Picker ----------------------------
function openPicker(target) {
  state.pickerTarget = target;
  const taken = new Set([
    ...state.yourTeam.filter(Boolean).map((b) => b.id),
    ...state.enemyTeam.filter(Boolean).map((b) => b.id),
  ]);
  // Allow re-picking the slot's current brawler (so "clear" is implicit via re-select)
  const current = (target.side === "you" ? state.yourTeam : state.enemyTeam)[target.index];
  if (current) taken.delete(current.id);

  $("picker-title").textContent = `Pick for ${target.side === "you" ? "your" : "enemy"} slot ${target.index + 1}`;
  $("picker-search").value = "";
  renderPickerGrid("", taken);
  $("picker").classList.remove("hidden");
  $("picker-search").focus();

  $("picker-search").oninput = (e) => renderPickerGrid(e.target.value, taken);
}

function renderPickerGrid(query, taken) {
  const q = query.trim().toLowerCase();
  const cells = state.brawlers
    .filter((b) => !q || b.name.toLowerCase().includes(q))
    .map((b) => {
      const isTaken = taken.has(b.id);
      return `
        <div class="picker-cell ${isTaken ? "taken" : ""}" data-id="${b.id}">
          <img src="${b.imageUrl}" alt="${b.name}" loading="lazy" />
          <div class="name">${b.name}</div>
        </div>
      `;
    })
    .join("");

  // Add a "clear slot" cell at the front if the slot is filled
  const target = state.pickerTarget;
  const current = target && (target.side === "you" ? state.yourTeam : state.enemyTeam)[target.index];
  const clearCell = current
    ? `<div class="picker-cell" data-id="__clear__"><div style="width:64px;height:64px;border-radius:50%;background:#1a1d2e;display:flex;align-items:center;justify-content:center;color:#e26d6d;font-size:28px;">×</div><div class="name">Clear</div></div>`
    : "";

  $("picker-grid").innerHTML = clearCell + cells;
  document.querySelectorAll(".picker-cell").forEach((el) => {
    if (el.classList.contains("taken")) return;
    el.onclick = () => {
      const id = el.dataset.id;
      assignSlot(id === "__clear__" ? null : parseInt(id, 10));
    };
  });
}

function assignSlot(brawlerId) {
  const target = state.pickerTarget;
  if (!target) return;
  const team = target.side === "you" ? state.yourTeam : state.enemyTeam;
  team[target.index] = brawlerId == null ? null : state.brawlers.find((b) => b.id === brawlerId);
  closePicker();
  renderSlots();
}

function closePicker() {
  $("picker").classList.add("hidden");
  state.pickerTarget = null;
}

// ---------------------------- Actions ----------------------------
function bindActions() {
  $("picker-close").onclick = closePicker;
  $("picker").onclick = (e) => {
    if (e.target === $("picker")) closePicker();
  };
  $("btn-recommend").onclick = doRecommend;
  $("btn-evaluate").onclick = doEvaluate;
  $("btn-clear").onclick = () => {
    state.yourTeam = [null, null, null];
    state.enemyTeam = [null, null, null];
    state.yourSlot = 0;
    renderSlots();
    $("results").innerHTML = "";
    $("results").classList.add("empty");
    setStatus("");
  };
  $("filter-owned").onchange = (e) => {
    state.filterToOwned = e.target.checked;
    localStorage.setItem(LS_FILTER, state.filterToOwned ? "1" : "0");
  };
  $("btn-collection").onclick = openCollection;
  $("collection-close").onclick = closeCollection;
  $("collection").onclick = (e) => {
    if (e.target === $("collection")) closeCollection();
  };
  $("collection-all").onclick = () => {
    state.ownedBrawlerIds = new Set(state.brawlers.map((b) => b.id));
    persistOwned();
    renderCollectionGrid($("collection-search").value);
    renderOwnedCount();
  };
  $("collection-none").onclick = () => {
    state.ownedBrawlerIds = new Set();
    persistOwned();
    renderCollectionGrid($("collection-search").value);
    renderOwnedCount();
  };
  $("collection-search").oninput = (e) => renderCollectionGrid(e.target.value);
}

function buildPayload() {
  const payload = {
    map_id: state.selectedMapId,
    your_team: state.yourTeam.map((b) => b?.name || null),
    enemy_team: state.enemyTeam.map((b) => b?.name || null),
    your_slot: state.yourSlot,
  };
  if (state.filterToOwned) {
    payload.owned_brawlers = state.brawlers
      .filter((b) => state.ownedBrawlerIds.has(b.id))
      .map((b) => b.name);
  }
  return payload;
}

// ---------------------------- Collection editor ----------------------------
function openCollection() {
  $("collection-search").value = "";
  renderCollectionGrid("");
  $("collection").classList.remove("hidden");
  $("collection-search").focus();
}

function closeCollection() {
  $("collection").classList.add("hidden");
  renderOwnedCount();
}

function renderCollectionGrid(query) {
  const q = (query || "").trim().toLowerCase();
  const cells = state.brawlers
    .filter((b) => !q || b.name.toLowerCase().includes(q))
    .map((b) => {
      const owned = state.ownedBrawlerIds.has(b.id);
      return `
        <div class="picker-cell ${owned ? "owned" : "unowned"}" data-id="${b.id}">
          <img src="${b.imageUrl}" alt="${b.name}" loading="lazy" />
          <div class="name">${b.name}</div>
        </div>
      `;
    })
    .join("");
  $("collection-grid").innerHTML = cells;
  $("collection-grid").querySelectorAll(".picker-cell").forEach((el) => {
    el.onclick = () => {
      const id = parseInt(el.dataset.id, 10);
      if (state.ownedBrawlerIds.has(id)) {
        state.ownedBrawlerIds.delete(id);
        el.classList.replace("owned", "unowned");
      } else {
        state.ownedBrawlerIds.add(id);
        el.classList.replace("unowned", "owned");
      }
      persistOwned();
    };
  });
}

async function doRecommend() {
  if (state.yourTeam[state.yourSlot] !== null) {
    setStatus("Clear your marked slot first — recommend is for an empty slot.");
    return;
  }
  setStatus("Thinking...");
  $("btn-recommend").disabled = true;
  try {
    const r = await fetch("/api/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    renderRecommendations(data.recommendations);
    setStatus("");
  } catch (e) {
    setStatus("Error: " + e.message);
  } finally {
    $("btn-recommend").disabled = false;
  }
}

async function doEvaluate() {
  const candidate = state.yourTeam[state.yourSlot];
  if (!candidate) {
    setStatus("Pick a brawler in your marked slot first to evaluate it.");
    return;
  }
  setStatus("Evaluating...");
  $("btn-evaluate").disabled = true;
  try {
    const payload = { ...buildPayload(), candidate: candidate.name };
    const r = await fetch("/api/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    renderEvaluation(candidate, data);
    setStatus("");
  } catch (e) {
    setStatus("Error: " + e.message);
  } finally {
    $("btn-evaluate").disabled = false;
  }
}

function renderRecommendations(recs) {
  const results = $("results");
  results.classList.remove("empty");
  if (!recs?.length) {
    results.innerHTML = "<p>No recommendations returned.</p>";
    return;
  }
  results.innerHTML = `<div class="rec-grid">${recs
    .map((r, i) => {
      const b = state.brawlersByName[r.brawler.toLowerCase()];
      const img = r.imageUrl || b?.imageUrl || "";
      const cls = r.className || b?.className || "";
      return `
        <div class="rec-card rank-${i + 1}">
          <img src="${img}" alt="${r.brawler}" />
          <div class="rec-body">
            <h4>#${i + 1} ${r.brawler}</h4>
            <div class="class">${cls}</div>
            <div class="reason">${r.reason}</div>
          </div>
        </div>
      `;
    })
    .join("")}</div>`;
}

function renderEvaluation(candidate, data) {
  const results = $("results");
  results.classList.remove("empty");
  const alt = data.betterAlternativeArchetype
    ? `<p class="alt">Consider an archetype like: <strong>${data.betterAlternativeArchetype}</strong></p>`
    : "";
  results.innerHTML = `
    <div class="eval-card">
      <div class="eval-rating ${data.rating}">${data.rating}</div>
      <div class="eval-body">
        <p><strong>${candidate.name}</strong> (${candidate.className})</p>
        <p>${data.reason}</p>
        ${alt}
      </div>
    </div>
  `;
}

init().catch((e) => {
  setStatus("Failed to load: " + e.message);
});
