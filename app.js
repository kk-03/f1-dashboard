// F1 Telemetry Dashboard — stage 1–2
// Pickers (year → race → session → drivers) + interactive lap-time chart.

const API = "https://api.openf1.org/v1";
const FIRST_YEAR = 2023; // OpenF1 historical data starts in 2023
const DEFAULT_DRIVERS = 4; // how many drivers are pre-selected

const els = {
  year: document.getElementById("year"),
  meeting: document.getElementById("meeting"),
  session: document.getElementById("session"),
  hideSlow: document.getElementById("hideSlow"),
  driverList: document.getElementById("driverList"),
  selectAll: document.getElementById("selectAll"),
  selectNone: document.getElementById("selectNone"),
  status: document.getElementById("status"),
  chart: document.getElementById("lapChart"),
};

const state = {
  drivers: [],          // [{driver_number, name_acronym, full_name, team_name, colour}]
  laps: [],             // all laps for the current session
  selected: new Set(),  // selected driver numbers
};

// ---------- Data fetching with caching ----------

const memoryCache = new Map();

async function api(endpoint, params = {}) {
  const query = new URLSearchParams(params).toString();
  const url = `${API}/${endpoint}?${query}`;

  if (memoryCache.has(url)) return memoryCache.get(url);
  try {
    const stored = sessionStorage.getItem(url);
    if (stored) {
      const data = JSON.parse(stored);
      memoryCache.set(url, data);
      return data;
    }
  } catch (e) { /* storage unavailable — ignore */ }

  for (let attempt = 0; attempt < 3; attempt++) {
    const res = await fetch(url);
    if (res.status === 429) {
      // Rate limited (free tier: 30 requests/minute) — wait and retry
      setStatus("Rate limited by OpenF1, retrying in a few seconds…");
      await new Promise(r => setTimeout(r, 3000 * (attempt + 1)));
      continue;
    }
    if (!res.ok) throw new Error(`OpenF1 returned ${res.status} for ${endpoint}`);
    const data = await res.json();
    memoryCache.set(url, data);
    try { sessionStorage.setItem(url, JSON.stringify(data)); } catch (e) { /* full or unavailable */ }
    return data;
  }
  throw new Error("OpenF1 rate limit reached — wait a minute and try again.");
}

// ---------- Helpers ----------

function setStatus(msg, isError = false) {
  els.status.textContent = msg;
  els.status.classList.toggle("error", isError);
}

function fillSelect(select, items, valueKey, labelFn) {
  select.innerHTML = "";
  for (const item of items) {
    const opt = document.createElement("option");
    opt.value = item[valueKey];
    opt.textContent = labelFn(item);
    select.appendChild(opt);
  }
}

function formatLapTime(seconds) {
  if (seconds == null) return "";
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(3).padStart(6, "0");
  return `${m}:${s}`;
}

function median(values) {
  const v = [...values].sort((a, b) => a - b);
  const mid = Math.floor(v.length / 2);
  return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2;
}

const now = () => new Date();

// ---------- Pickers ----------

function initYears() {
  const current = now().getFullYear();
  const years = [];
  for (let y = current; y >= FIRST_YEAR; y--) years.push({ year: y });
  fillSelect(els.year, years, "year", d => d.year);
}

async function loadMeetings() {
  setStatus("Loading races…");
  const meetings = await api("meetings", { year: els.year.value });
  // Only races that have already started, newest first
  const past = meetings
    .filter(m => new Date(m.date_start) < now())
    .sort((a, b) => new Date(b.date_start) - new Date(a.date_start));
  fillSelect(els.meeting, past, "meeting_key", m => m.meeting_name);
  await loadSessions();
}

async function loadSessions() {
  if (!els.meeting.value) return;
  setStatus("Loading sessions…");
  const sessions = await api("sessions", { meeting_key: els.meeting.value });
  // Only finished sessions, in running order
  const done = sessions
    .filter(s => s.date_end && new Date(s.date_end) < now())
    .sort((a, b) => new Date(a.date_start) - new Date(b.date_start));
  fillSelect(els.session, done, "session_key", s => s.session_name);
  // Default to the race if there is one, otherwise the last session
  const race = done.find(s => s.session_name === "Race");
  els.session.value = race ? race.session_key : done.at(-1)?.session_key ?? "";
  await loadSession();
}

async function loadSession() {
  const sessionKey = els.session.value;
  if (!sessionKey) {
    setStatus("No completed sessions for this event yet.");
    return;
  }
  setStatus("Loading drivers and laps…");

  const [drivers, laps] = await Promise.all([
    api("drivers", { session_key: sessionKey }),
    api("laps", { session_key: sessionKey }),
  ]);

  // De-duplicate drivers and keep a usable team colour
  const byNumber = new Map();
  for (const d of drivers) {
    if (!byNumber.has(d.driver_number)) {
      byNumber.set(d.driver_number, {
        ...d,
        colour: d.team_colour ? `#${d.team_colour}` : "#888888",
      });
    }
  }
  state.drivers = [...byNumber.values()];
  state.laps = laps;
  assignTeammateStyles(state.drivers);

  // Pre-select the drivers with the fastest single lap
  const best = new Map();
  for (const lap of laps) {
    if (lap.lap_duration == null) continue;
    const prev = best.get(lap.driver_number);
    if (prev == null || lap.lap_duration < prev) best.set(lap.driver_number, lap.lap_duration);
  }
  const fastest = [...best.entries()].sort((a, b) => a[1] - b[1]).map(([n]) => n);
  state.selected = new Set(fastest.slice(0, DEFAULT_DRIVERS));

  // Order the driver list by fastest lap too
  state.drivers.sort((a, b) =>
    (best.get(a.driver_number) ?? Infinity) - (best.get(b.driver_number) ?? Infinity));

  renderDriverList();
  renderLapChart();
  setStatus("");
}

// ---------- Teammate styling ----------

// Teammates share a team colour, so each driver gets a line/marker style
// based on their position within the team (by car number, so it stays the
// same no matter which drivers are selected).
const TEAMMATE_STYLES = [
  { dash: "solid", symbol: "circle" },
  { dash: "dash", symbol: "diamond" },
  { dash: "dot", symbol: "square" }, // e.g. a mid-season driver swap
];

function assignTeammateStyles(drivers) {
  const teams = new Map();
  for (const d of drivers) {
    const team = d.team_name ?? d.colour;
    if (!teams.has(team)) teams.set(team, []);
    teams.get(team).push(d);
  }
  for (const members of teams.values()) {
    members
      .sort((a, b) => a.driver_number - b.driver_number)
      .forEach((d, i) => {
        d.teamIndex = i;
        d.style = TEAMMATE_STYLES[i % TEAMMATE_STYLES.length];
      });
  }
}

// ---------- Driver chips ----------

function renderDriverList() {
  els.driverList.innerHTML = "";
  for (const d of state.drivers) {
    const chip = document.createElement("label");
    chip.className = "driver-chip";
    chip.style.setProperty("--team", d.colour);
    chip.title = `${d.full_name} — ${d.team_name}`;
    chip.classList.toggle("selected", state.selected.has(d.driver_number));
    chip.classList.toggle("second", d.teamIndex > 0);

    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = state.selected.has(d.driver_number);
    box.addEventListener("change", () => {
      if (box.checked) state.selected.add(d.driver_number);
      else state.selected.delete(d.driver_number);
      chip.classList.toggle("selected", box.checked);
      renderLapChart();
    });

    chip.append(box, document.createTextNode(d.name_acronym ?? d.driver_number));
    els.driverList.appendChild(chip);
  }
}

// ---------- Lap-time chart ----------

function renderLapChart() {
  let laps = state.laps.filter(l => l.lap_duration != null);

  if (els.hideSlow.checked && laps.length) {
    const cutoff = median(laps.map(l => l.lap_duration)) * 1.07;
    laps = laps.filter(l => l.lap_duration <= cutoff && !l.is_pit_out_lap);
  }

  const traces = state.drivers
    .filter(d => state.selected.has(d.driver_number))
    .map(d => {
      const driverLaps = laps
        .filter(l => l.driver_number === d.driver_number)
        .sort((a, b) => a.lap_number - b.lap_number);
      return {
        name: d.name_acronym,
        x: driverLaps.map(l => l.lap_number),
        y: driverLaps.map(l => l.lap_duration),
        text: driverLaps.map(l => formatLapTime(l.lap_duration)),
        mode: "lines+markers",
        line: { color: d.colour, width: 2, dash: d.style.dash },
        marker: { size: d.teamIndex > 0 ? 7 : 6, symbol: d.style.symbol },
        hovertemplate: `<b>${d.name_acronym}</b> lap %{x}<br>%{text}<extra></extra>`,
      };
    });

  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#f0f0f5" },
    margin: { l: 60, r: 20, t: 10, b: 50 },
    xaxis: { title: { text: "Lap" }, gridcolor: "#33334a", zeroline: false },
    yaxis: { title: { text: "Lap time (s)" }, gridcolor: "#33334a", zeroline: false },
    legend: { orientation: "h", y: -0.2 },
    hovermode: "closest",
  };

  Plotly.react(els.chart, traces, layout, { responsive: true, displaylogo: false });
}

// ---------- Wiring ----------

function guard(fn) {
  return async () => {
    try { await fn(); }
    catch (err) { console.error(err); setStatus(err.message, true); }
  };
}

els.year.addEventListener("change", guard(loadMeetings));
els.meeting.addEventListener("change", guard(loadSessions));
els.session.addEventListener("change", guard(loadSession));
els.hideSlow.addEventListener("change", renderLapChart);
els.selectAll.addEventListener("click", () => {
  state.selected = new Set(state.drivers.map(d => d.driver_number));
  renderDriverList();
  renderLapChart();
});
els.selectNone.addEventListener("click", () => {
  state.selected.clear();
  renderDriverList();
  renderLapChart();
});

initYears();
guard(loadMeetings)();