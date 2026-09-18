"use strict";

/* =========================================================================
   ForgeFlow Command Center – Professional Dashboard
   Talks to the FastAPI backend in app/main.py. No build step, no deps.
   ========================================================================= */

const API = "";

/* ---------- tiny helpers ---------- */
const $ = (sel, root) => (root || document).querySelector(sel);

function el(tag, attrs) {
  const n = document.createElement(tag);
  const a = attrs || {};
  for (const k of Object.keys(a)) {
    const v = a[k];
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k === "text") n.textContent = v;
    else if (k.indexOf("on") === 0 && typeof v === "function") n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (let i = 2; i < arguments.length; i++) {
    const kid = arguments[i];
    if (kid === null || kid === undefined || kid === false) continue;
    if (Array.isArray(kid)) {
      for (const k2 of kid) {
        if (k2 !== null && k2 !== undefined && k2 !== false) n.appendChild(nodeOf(k2));
      }
    } else {
      n.appendChild(nodeOf(kid));
    }
  }
  return n;
}

function nodeOf(x) {
  return (typeof x === "string" || typeof x === "number") ? document.createTextNode(String(x)) : x;
}

const ESC_MAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
function esc(s) {
  return String(s === null || s === undefined ? "" : s).replace(/[&<>"']/g, (c) => ESC_MAP[c]);
}

function toast(msg, kind) {
  const t = el("div", { class: "toast " + (kind || ""), text: msg });
  $("#toasts").appendChild(t);
  setTimeout(() => {
    t.style.opacity = "0";
    t.style.transition = "opacity .3s";
    setTimeout(() => t.remove(), 320);
  }, 3600);
}

async function api(path, opts) {
  const o = opts || {};
  const res = await fetch(API + path, {
    method: o.method || "GET",
    headers: { "Content-Type": "application/json" },
    body: o.body ? JSON.stringify(o.body) : undefined
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch (_) {}
    throw new Error(res.status + " " + detail);
  }
  const txt = await res.text();
  return txt ? JSON.parse(txt) : null;
}

function fmtTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d)) return "-";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDateTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d)) return "-";
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function ago(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d)) return "-";
  const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (s < 60) return Math.floor(s) + "s ago";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  return Math.floor(s / 86400) + "d ago";
}

function shortId(id) {
  return id ? String(id).slice(0, 8) : "-";
}

/** Format seconds into human-readable duration */
function dur(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "m " + (s % 60) + "s";
  return Math.floor(s / 3600) + "h " + Math.floor((s % 3600) / 60) + "m";
}

/** Format seconds into a compact live timer display: MM:SS or HH:MM:SS */
function timerStr(seconds) {
  if (seconds === null || seconds === undefined || seconds < 0) return "00:00";
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  if (h > 0) return String(h).padStart(2, "0") + ":" + mm + ":" + ss;
  return mm + ":" + ss;
}

/* ---------- state machine metadata ---------- */
const STAGES = [
  "PENDING", "PREPARING", "INVESTIGATING", "ROOT_CAUSE_READY", "ROOT_CAUSE_REVIEW",
  "IMPLEMENTING", "IMPLEMENTATION_READY", "TESTING", "QA", "REVIEW",
  "NEEDS_CHANGES", "APPROVED", "COMPLETED"
];
const TERMINAL = ["COMPLETED", "FAILED", "STOPPED", "BLOCKED"];
const ACTIVE_STATES = ["PREPARING", "INVESTIGATING", "ROOT_CAUSE_READY", "ROOT_CAUSE_REVIEW",
  "IMPLEMENTING", "IMPLEMENTATION_READY", "TESTING", "QA", "REVIEW", "NEEDS_CHANGES"];

const STATUS_META = {
  PENDING:              { label: "Pending",              tone: "gray"   },
  PREPARING:            { label: "Preparing",            tone: "blue"   },
  INVESTIGATING:        { label: "Investigating",        tone: "cyan"   },
  ROOT_CAUSE_READY:     { label: "Root Cause Ready",     tone: "cyan"   },
  ROOT_CAUSE_REVIEW:    { label: "Root Cause Review",    tone: "cyan"   },
  IMPLEMENTING:         { label: "Implementing",         tone: "purple" },
  IMPLEMENTATION_READY: { label: "Impl. Ready",          tone: "purple" },
  TESTING:              { label: "Testing",              tone: "amber"  },
  QA:                   { label: "QA",                   tone: "amber"  },
  REVIEW:               { label: "In Review",            tone: "amber"  },
  NEEDS_CHANGES:        { label: "Needs Changes",        tone: "red"    },
  APPROVED:             { label: "Approved",             tone: "green"  },
  COMPLETED:            { label: "Completed",            tone: "green"  },
  FAILED:               { label: "Failed",               tone: "red"    },
  STOPPED:              { label: "Stopped",              tone: "gray"   },
  BLOCKED:              { label: "Blocked",              tone: "red"    },
  PAUSED:               { label: "Paused",               tone: "gray"   }
};

const KANBAN = [
  { key: "queued",      title: "Queued",      states: ["PENDING", "PREPARING"] },
  { key: "investigate", title: "Investigate", states: ["INVESTIGATING", "ROOT_CAUSE_READY", "ROOT_CAUSE_REVIEW"] },
  { key: "implement",   title: "Implement",   states: ["IMPLEMENTING", "IMPLEMENTATION_READY", "NEEDS_CHANGES"] },
  { key: "verify",      title: "Verify",      states: ["TESTING", "QA", "REVIEW"] },
  { key: "done",        title: "Done",        states: ["APPROVED", "COMPLETED"] },
  { key: "halted",      title: "Halted",      states: ["FAILED", "BLOCKED", "STOPPED", "PAUSED"] }
];

function statusBadge(status) {
  const m = STATUS_META[status] || { label: status || "Unknown", tone: "gray" };
  return el("span", { class: "badge " + m.tone, text: m.label });
}
function priorityBadge(p) {
  const key = String(p || "").toLowerCase();
  const tone = { high: "red", medium: "amber", low: "gray" }[key] || "gray";
  return el("span", { class: "badge " + tone, text: String(p || "medium").toUpperCase() });
}

/* ---------- app state ---------- */
const state = {
  route: "overview",
  projects: [],
  tasks: [],
  overview: null,
  config: null,
  activity: [],
  selectedTaskId: null,
  taskEvents: [],
  taskArtifacts: [],
  stateHistory: [],
  telemetry: {},  // { model, usage: {input_tokens, output_tokens, ...}, duration_seconds, num_turns }
  ws: null,
  wsTaskId: null,
  filters: { search: "", status: "ALL", project: "ALL" },
  loading: false
};

/* ---------- agent name helpers ---------- */
function agentDisplayName(agentStr) {
  if (!agentStr) return null;
  if (agentStr.toLowerCase().includes("antigravity") || agentStr.toLowerCase().includes("agy")) return "Google Antigravity";
  if (agentStr.toLowerCase().includes("abacus") || agentStr.toLowerCase().includes("reviewer")) return "Abacus AI";
  return agentStr;
}
function agentRole(agentStr) {
  if (!agentStr) return null;
  if (agentStr.toLowerCase().includes("reviewer") || agentStr.toLowerCase().includes("abacus")) return "Reviewer";
  return "Worker";
}

/* ---------- navigation ---------- */
const NAV = [
  { key: "overview", label: "Overview",        icon: "\u25C8" },
  { key: "projects", label: "Projects",        icon: "\u25A4" },
  { key: "tasks",    label: "Tasks",           icon: "\u2630" },
  { key: "kanban",   label: "Kanban",          icon: "\u25A6" },
  { key: "mission",  label: "Mission Control", icon: "\u25CE" },
  { key: "activity", label: "Activity",        icon: "\u2261" },
  { key: "settings", label: "Settings",        icon: "\u2699" }
];

function renderNav() {
  const nav = $("#nav");
  nav.innerHTML = "";
  for (const item of NAV) {
    let badge = null;
    if (item.key === "projects") badge = state.projects.length;
    if (item.key === "tasks") badge = state.tasks.length;
    if (item.key === "activity") badge = state.activity.length;
    nav.appendChild(el("div", {
      class: "nav-item" + (state.route === item.key ? " active" : ""),
      onclick: () => go(item.key)
    },
      el("span", { class: "nav-icon", text: item.icon }),
      el("span", { text: item.label }),
      badge === null ? null : el("span", { class: "nav-badge", text: String(badge) })
    ));
  }
}

function go(route) {
  state.route = route;
  const meta = NAV.filter((n) => n.key === route)[0];
  $("#page-title").textContent = meta ? meta.label : route;
  renderNav();
  render();
}

/* ---------- data loading ---------- */
function setConn(ok, detail) {
  const dot = $("#conn-dot");
  const txt = $("#conn-text");
  const sub = $("#conn-sub");
  if (!dot) return;
  dot.className = "dot " + (ok ? "ok" : "err");
  txt.textContent = ok ? "Connected" : "Disconnected";
  sub.textContent = detail || (ok ? "live" : "backend unreachable");
}

async function loadAll() {
  state.loading = true;
  try {
    const results = await Promise.all([
      api("/projects").catch(() => []),
      api("/tasks").catch(() => []),
      api("/overview").catch(() => null),
      api("/config").catch(() => null),
      api("/activity?limit=200").catch(() => [])
    ]);
    state.projects = results[0] || [];
    state.tasks = results[1] || [];
    state.overview = results[2];
    state.config = results[3];
    state.activity = results[4] || [];
    setConn(true);
  } catch (e) {
    setConn(false, e.message);
  } finally {
    state.loading = false;
    renderNav();
    render();
  }
}

async function refresh() {
  await loadAll();
  toast("Refreshed", "ok");
}

/* ---------- shared fragments ---------- */
function statCard(label, value, sub, tone) {
  return el("div", { class: "card" },
    el("div", { class: "stat-label", text: label }),
    el("div", { class: "stat-value " + (tone || ""), text: String(value) }),
    sub ? el("div", { class: "stat-sub", text: sub }) : null
  );
}
function emptyState(icon, msg) {
  return el("div", { class: "empty" },
    el("div", { class: "empty-icon", text: icon }),
    el("div", { text: msg })
  );
}
function projectName(id) {
  const p = state.projects.filter((x) => x.id === id || x.name === id)[0];
  return p ? p.name : shortId(id);
}
function taskById(id) {
  return state.tasks.filter((t) => t.id === id)[0] || null;
}

/* ---------- live timer system ---------- */
let _timerInterval = null;

function startTimerTick() {
  if (_timerInterval) return;
  _timerInterval = setInterval(updateLiveTimers, 1000);
}

function updateLiveTimers() {
  // Update all elements with data-timer-since attribute
  document.querySelectorAll("[data-timer-since]").forEach((el) => {
    const since = el.getAttribute("data-timer-since");
    if (!since) return;
    const d = new Date(since);
    if (isNaN(d)) return;
    const elapsed = (Date.now() - d.getTime()) / 1000;
    el.textContent = timerStr(elapsed);
  });
}

function liveTimer(isoSince, extraClass) {
  if (!isoSince) return el("span", { class: "timer-live " + (extraClass || ""), text: "--:--" });
  const d = new Date(isoSince);
  if (isNaN(d)) return el("span", { class: "timer-live " + (extraClass || ""), text: "--:--" });
  const elapsed = (Date.now() - d.getTime()) / 1000;
  return el("span", {
    class: "timer-live " + (extraClass || ""),
    text: timerStr(elapsed),
    "data-timer-since": isoSince
  });
}

/* ---------- view: Overview ---------- */
function viewOverview() {
  const o = state.overview || {};
  const total = state.tasks.length;
  const completed = o.completed_tasks || 0;
  const failed = o.failed_tasks || 0;
  const blocked = o.blocked_tasks || 0;
  const active = o.active_tasks || 0;
  const rate = total ? Math.round((completed / total) * 100) : 0;

  const counts = {};
  for (const t of state.tasks) counts[t.status] = (counts[t.status] || 0) + 1;

  const wrap = el("div", {});

  /* KPI cards */
  wrap.appendChild(el("div", { class: "grid cols-4 mb" },
    statCard("Total Tasks", total, (o.projects || 0) + " projects", ""),
    statCard("Active", active, (o.queued_tasks || 0) + " queued", active ? "info" : ""),
    statCard("Completed", completed, rate + "% of all tasks", "ok"),
    statCard("Needs Attention", failed + blocked, failed + " failed / " + blocked + " blocked", (failed + blocked) ? "err" : "")
  ));

  wrap.appendChild(el("div", { class: "grid cols-4 mb" },
    statCard("Tests Passing", o.tests_passing || 0, "latest result per task", "ok"),
    statCard("Tests Failing", o.tests_failing || 0, "latest result per task", (o.tests_failing || 0) ? "err" : ""),
    statCard("Awaiting Review", o.awaiting_review || 0, "in REVIEW state", (o.awaiting_review || 0) ? "warn" : ""),
    statCard("Projects", o.projects || 0, "registered", "")
  ));

  /* Active tasks - Mission Control summary */
  const running = state.tasks.filter((t) => ACTIVE_STATES.indexOf(t.status) !== -1);
  if (running.length > 0) {
    const activeCard = el("div", { class: "card pad-0 mb" },
      el("div", { class: "card-head" },
        el("h3", { text: "Active Tasks" }),
        el("div", { class: "spacer" }),
        el("span", { class: "badge blue", text: running.length + " running" })
      )
    );
    const ab = el("div", { class: "card-body" });
    for (const t of running) {
      const agent = agentDisplayName(t.current_agent);
      ab.appendChild(el("div", { class: "kv", style: "cursor:pointer", onclick: () => { go("mission"); selectMissionTask(t.id); } },
        el("div", { class: "k" },
          el("strong", { text: t.title }),
          el("span", { style: "margin-left:12px" }, statusBadge(t.status)),
          agent ? el("span", { class: "agent-badge", text: agent, style: "margin-left:8px" }) : null
        ),
        el("div", { class: "v" },
          t.started_at ? liveTimer(t.started_at) : el("span", { class: "faint", text: "-" })
        )
      ));
    }
    activeCard.appendChild(ab);
    wrap.appendChild(activeCard);
  }

  const cols = el("div", { class: "grid cols-2" });

  /* status distribution */
  const dist = el("div", { class: "card pad-0" },
    el("div", { class: "card-head" }, el("h3", { text: "Status Distribution" }))
  );
  const distBody = el("div", { class: "card-body" });
  const keys = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
  if (!keys.length) {
    distBody.appendChild(emptyState("\u25CB", "No tasks yet"));
  } else {
    for (const k of keys) {
      const pct = total ? Math.round((counts[k] / total) * 100) : 0;
      distBody.appendChild(el("div", { class: "mb" },
        el("div", { class: "flex", style: "justify-content:space-between;margin-bottom:5px" },
          statusBadge(k),
          el("span", { class: "mono faint", text: counts[k] + "  (" + pct + "%)" })
        ),
        el("div", { class: "progress" }, el("div", { style: "width:" + pct + "%" }))
      ));
    }
  }
  dist.appendChild(distBody);
  cols.appendChild(dist);

  /* recent tasks */
  const recent = el("div", { class: "card pad-0" },
    el("div", { class: "card-head" },
      el("h3", { text: "Recent Tasks" }),
      el("div", { class: "spacer" }),
      el("button", { class: "btn sm ghost", text: "View all", onclick: () => go("tasks") })
    )
  );
  const recentBody = el("div", { class: "card-body" });
  const sorted = state.tasks.slice().sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || ""))).slice(0, 6);
  if (!sorted.length) {
    recentBody.appendChild(emptyState("\u2630", "No tasks yet"));
  } else {
    for (const t of sorted) {
      recentBody.appendChild(el("div", { class: "kv", style: "cursor:pointer", onclick: () => openTask(t.id) },
        el("div", { class: "k truncate", text: t.title }),
        el("div", { class: "v" }, statusBadge(t.status))
      ));
    }
  }
  recent.appendChild(recentBody);
  cols.appendChild(recent);
  wrap.appendChild(cols);

  /* System health + provider info */
  const cfg = state.config || {};
  const health = el("div", { class: "card pad-0 mt" },
    el("div", { class: "card-head" }, el("h3", { text: "System" }))
  );
  const hb = el("div", { class: "card-body" });
  const providerName = cfg.implementation_provider === "agy" ? "Google Antigravity (agy CLI)" : (cfg.implementation_provider || "antigravity");
  hb.appendChild(el("div", { class: "kv" },
    el("div", { class: "k", text: "Worker Provider" }),
    el("div", { class: "v" }, el("span", { class: "agent-badge", text: providerName }))
  ));
  hb.appendChild(el("div", { class: "kv" },
    el("div", { class: "k", text: "Abacus Reviewer" }),
    el("div", { class: "v" }, el("span", { class: "badge " + (cfg.abacus_reviewer_enabled ? "green" : "gray"), text: cfg.abacus_reviewer_enabled ? "Enabled" : "Disabled" }))
  ));
  hb.appendChild(el("div", { class: "kv" },
    el("div", { class: "k", text: "Review Mode" }),
    el("div", { class: "v mono", text: cfg.abacus_review_mode || "-" })
  ));
  hb.appendChild(el("div", { class: "kv" },
    el("div", { class: "k", text: "Fallback" }),
    el("div", { class: "v" }, el("span", { class: "badge " + (cfg.abacus_fallback_enabled ? "amber" : "gray"), text: cfg.abacus_fallback_enabled ? "Enabled" : "Disabled" }))
  ));
  hb.appendChild(el("div", { class: "kv" },
    el("div", { class: "k", text: "Abacus Usage" }),
    el("div", { class: "v faint", text: "Not exposed by current integration" })
  ));
  health.appendChild(hb);
  wrap.appendChild(health);

  return wrap;
}

/* ---------- view: Projects ---------- */
function viewProjects() {
  const wrap = el("div", {});
  wrap.appendChild(el("div", { class: "toolbar" },
    el("div", { class: "spacer" }),
    el("button", { class: "btn primary", text: "+ New Project", onclick: openNewProject })
  ));
  if (!state.projects.length) {
    wrap.appendChild(el("div", { class: "card" }, emptyState("\u25A4", "No projects yet. Create one to get started.")));
    return wrap;
  }
  const card = el("div", { class: "card pad-0" });
  const table = el("table", {},
    el("thead", {}, el("tr", {},
      el("th", { text: "Name" }), el("th", { text: "Type" }), el("th", { text: "Repository" }),
      el("th", { text: "Test Command" }), el("th", { text: "Tasks" }), el("th", { text: "Created" }), el("th", { text: "" })
    ))
  );
  const tbody = el("tbody", {});
  for (const p of state.projects) {
    const n = state.tasks.filter((t) => t.project_id === p.id || t.project_id === p.name).length;
    tbody.appendChild(el("tr", {},
      el("td", {}, el("strong", { text: p.name })),
      el("td", {}, el("span", { class: "badge blue", text: p.type || "-" })),
      el("td", { class: "mono faint truncate", title: p.repository || "", text: p.repository || "-" }),
      el("td", { class: "mono faint truncate", text: p.test_command || "-" }),
      el("td", { class: "mono", text: String(n) }),
      el("td", { class: "faint nowrap", text: fmtDateTime(p.created_at) }),
      el("td", {},
        el("div", { class: "flex" },
          el("button", { class: "btn sm", text: "Tasks", onclick: () => { state.filters.project = p.id; go("tasks"); } }),
          el("button", { class: "btn sm", text: "New Task", onclick: () => openNewTask(p.id) })
        ))
    ));
  }
  table.appendChild(tbody);
  card.appendChild(table);
  wrap.appendChild(card);
  return wrap;
}

/* ---------- view: Tasks ---------- */
function filteredTasks() {
  const f = state.filters;
  const q = f.search.trim().toLowerCase();
  return state.tasks.filter((t) => {
    if (f.status !== "ALL" && t.status !== f.status) return false;
    if (f.project !== "ALL" && t.project_id !== f.project) return false;
    if (q) {
      const hay = (t.title + " " + (t.description || "") + " " + t.id).toLowerCase();
      if (hay.indexOf(q) === -1) return false;
    }
    return true;
  });
}

function viewTasks() {
  const wrap = el("div", {});
  const f = state.filters;
  const search = el("input", { class: "search", placeholder: "Search tasks...", value: f.search,
    oninput: (e) => { f.search = e.target.value; render(); }
  });
  const statusSel = el("select", { class: "search", onchange: (e) => { f.status = e.target.value; render(); } },
    el("option", { value: "ALL", text: "All statuses" }),
    Object.keys(STATUS_META).map((s) => el("option", { value: s, text: STATUS_META[s].label, selected: f.status === s ? "selected" : null }))
  );
  const projSel = el("select", { class: "search", onchange: (e) => { f.project = e.target.value; render(); } },
    el("option", { value: "ALL", text: "All projects" }),
    state.projects.map((p) => el("option", { value: p.id, text: p.name, selected: f.project === p.id ? "selected" : null }))
  );
  wrap.appendChild(el("div", { class: "toolbar" },
    search, statusSel, projSel,
    el("button", { class: "btn sm ghost", text: "Clear", onclick: () => { state.filters = { search: "", status: "ALL", project: "ALL" }; render(); } }),
    el("div", { class: "spacer" }),
    el("button", { class: "btn primary", text: "+ New Task", onclick: () => openNewTask(null) })
  ));
  const rows = filteredTasks();
  if (!rows.length) {
    wrap.appendChild(el("div", { class: "card" }, emptyState("\u2630", state.tasks.length ? "No tasks match these filters." : "No tasks yet.")));
    return wrap;
  }
  const card = el("div", { class: "card pad-0" });
  const table = el("table", {},
    el("thead", {}, el("tr", {},
      el("th", { text: "Title" }), el("th", { text: "Project" }), el("th", { text: "Status" }),
      el("th", { text: "Agent" }), el("th", { text: "Iter" }), el("th", { text: "Elapsed" }), el("th", { text: "" })
    ))
  );
  const tbody = el("tbody", {});
  for (const t of rows) {
    const isActive = ACTIVE_STATES.indexOf(t.status) !== -1;
    tbody.appendChild(el("tr", {},
      el("td", {},
        el("div", { style: "font-weight:600", text: t.title }),
        el("div", { class: "mono faint", text: shortId(t.id) })
      ),
      el("td", { class: "faint", text: projectName(t.project_id) }),
      el("td", {}, statusBadge(t.status)),
      el("td", {}, t.current_agent ? el("span", { class: "agent-badge", text: agentDisplayName(t.current_agent) }) : el("span", { class: "faint", text: "-" })),
      el("td", { class: "mono", text: (t.iteration || 0) + "/" + (t.max_iterations || 0) }),
      el("td", {}, isActive && t.started_at ? liveTimer(t.started_at) : el("span", { class: "faint", text: ago(t.updated_at) })),
      el("td", {},
        el("div", { class: "flex" },
          el("button", { class: "btn sm", text: "Open", onclick: () => openTask(t.id) }),
          el("button", { class: "btn sm primary", text: isActive ? "Mission" : "Run", onclick: () => {
            if (isActive) { go("mission"); selectMissionTask(t.id); }
            else runTask(t.id);
          }})
        ))
    ));
  }
  table.appendChild(tbody);
  card.appendChild(table);
  wrap.appendChild(card);
  return wrap;
}

/* ---------- view: Kanban ---------- */
function viewKanban() {
  const wrap = el("div", {});
  const rows = filteredTasks();
  wrap.appendChild(el("div", { class: "toolbar" },
    el("input", { class: "search", placeholder: "Search tasks...", value: state.filters.search,
      oninput: (e) => { state.filters.search = e.target.value; render(); }
    }),
    el("select", { class: "search", onchange: (e) => { state.filters.project = e.target.value; render(); } },
      el("option", { value: "ALL", text: "All projects" }),
      state.projects.map((p) => el("option", { value: p.id, text: p.name, selected: state.filters.project === p.id ? "selected" : null }))
    ),
    el("div", { class: "spacer" }),
    el("span", { class: "faint mono", text: rows.length + " tasks" })
  ));
  const board = el("div", { class: "kanban" });
  for (const col of KANBAN) {
    const items = rows.filter((t) => col.states.indexOf(t.status) !== -1);
    const body = el("div", { class: "kcol-body" });
    if (!items.length) {
      body.appendChild(el("div", { class: "kcol-empty", text: "Empty" }));
    } else {
      for (const t of items) {
        body.appendChild(el("div", { class: "kcard", onclick: () => openTask(t.id) },
          el("div", { class: "kcard-title", text: t.title }),
          el("div", { class: "kcard-meta" },
            statusBadge(t.status),
            t.current_agent ? el("span", { class: "agent-badge", text: agentDisplayName(t.current_agent) }) : null,
            el("span", { text: "iter " + (t.iteration || 0) + "/" + (t.max_iterations || 0) })
          )
        ));
      }
    }
    board.appendChild(el("div", { class: "kcol" },
      el("div", { class: "kcol-head" },
        el("span", { text: col.title }),
        el("span", { class: "count", text: String(items.length) })
      ),
      body
    ));
  }
  wrap.appendChild(board);
  return wrap;
}

/* ---------- view: Activity ---------- */
const EVENT_TONE = {
  STATE_CHANGED: "info", TASK_STARTED: "ok", TASK_COMPLETED: "ok",
  TASK_FAILED: "err", TASK_STOPPED: "warn", TASK_BLOCKED: "err",
  TEST_RESULT: "warn", REVIEW_RESULT: "agent", AGENT_MESSAGE: "agent",
  ARTIFACT_CREATED: "info", ARTIFACT: "info", ERROR: "err",
  REVIEW_SKIPPED: "info", REVIEWER_FALLBACK: "warn"
};

function eventSummary(e) {
  const p = e.payload || {};
  switch (e.event_type) {
    case "STATE_CHANGED":
      return (p.old_status || "?") + " \u2192 " + (p.new_status || "?") + (p.agent ? "  [" + agentDisplayName(p.agent) + "]" : "");
    case "TEST_RESULT":
      return "exit " + p.exit_code + (p.command ? "  " + p.command : "");
    case "REVIEW_RESULT":
      return (p.decision || "?") + (p.summary ? "  " + p.summary : "");
    case "AGENT_CHUNK": {
      const tp = p.type || "";
      if (tp === "init_info") return "Model: " + (p.model || "unknown");
      if (tp === "result_telemetry") return "Tokens: " + ((p.usage && p.usage.total_tokens) || "n/a");
      if (tp === "tool_call") return "Tool: " + (p.name || "?");
      if (tp === "text") return (p.content || "").slice(0, 80);
      if (tp === "structured_output") return "Result received";
      return tp;
    }
    case "ARTIFACT": return (p.name || "artifact");
    case "REVIEW_SKIPPED": return p.reason || "skipped";
    case "REVIEWER_FALLBACK": return "Fallback: " + (p.fallback_agent || "?");
    default: {
      const keys = Object.keys(p);
      if (!keys.length) return "";
      return keys.slice(0, 3).map((k) => k + "=" + String(p[k]).slice(0, 60)).join("  ");
    }
  }
}

function logLine(e) {
  const tone = EVENT_TONE[e.event_type] || "";
  const p = e.payload || {};
  const agent = (e.event_type === "STATE_CHANGED" && p.agent) ? agentDisplayName(p.agent) :
                (e.event_type === "AGENT_CHUNK" && p.type === "init_info") ? "Agy" : null;

  return el("div", { class: "log-line " + tone },
    el("span", { class: "log-time", text: fmtTime(e.created_at || e.timestamp) }),
    agent ? el("span", { class: "log-agent", text: agent }) : null,
    el("span", { class: "log-type", text: e.event_type }),
    el("span", { class: "log-msg", text: eventSummary(e) })
  );
}

function viewActivity() {
  const wrap = el("div", {});
  const events = state.activity.slice().reverse();
  wrap.appendChild(el("div", { class: "toolbar" },
    el("span", { class: "faint mono", text: events.length + " events" }),
    el("div", { class: "spacer" }),
    el("button", { class: "btn sm", text: "Refresh", onclick: refresh })
  ));
  const card = el("div", { class: "card pad-0" },
    el("div", { class: "card-head" }, el("h3", { text: "Event Stream" }))
  );
  const body = el("div", { class: "card-body" });
  if (!events.length) {
    body.appendChild(emptyState("\u2261", "No activity recorded yet."));
  } else {
    const log = el("div", { class: "log", style: "height:auto;max-height:620px" });
    for (const e of events) log.appendChild(logLine(e));
    body.appendChild(log);
  }
  card.appendChild(body);
  wrap.appendChild(card);
  return wrap;
}

/* ---------- view: Mission Control ---------- */
function viewMission() {
  const wrap = el("div", {});
  const sel = el("select", { class: "search", onchange: (e) => selectMissionTask(e.target.value) },
    el("option", { value: "", text: "-- select a task --" }),
    state.tasks.map((t) => el("option", {
      value: t.id,
      text: t.title + "  [" + t.status + "]",
      selected: state.selectedTaskId === t.id ? "selected" : null
    }))
  );
  wrap.appendChild(el("div", { class: "toolbar" },
    el("span", { class: "faint", text: "Task:" }), sel,
    el("div", { class: "spacer" }),
    state.selectedTaskId ? el("button", { class: "btn sm", text: "Refresh", onclick: () => selectMissionTask(state.selectedTaskId) }) : null
  ));
  if (!state.selectedTaskId) {
    wrap.appendChild(el("div", { class: "card" }, emptyState("\u25CE", "Select a task to open Mission Control.")));
    return wrap;
  }
  const t = taskById(state.selectedTaskId);
  if (!t) {
    wrap.appendChild(el("div", { class: "card" }, emptyState("\u25CE", "Task not found.")));
    return wrap;
  }

  const isTerminal = TERMINAL.indexOf(t.status) !== -1;
  const isActive = ACTIVE_STATES.indexOf(t.status) !== -1;

  /* ===== Task Header Hero ===== */
  const agent = agentDisplayName(t.current_agent);
  const role = agentRole(t.current_agent);

  const heroLeft = el("div", {},
    el("h2", { style: "margin:0 0 4px 0;font-size:1.25rem", text: t.title }),
    el("div", { class: "flex", style: "gap:8px;align-items:center;flex-wrap:wrap" },
      statusBadge(t.status),
      agent ? el("span", { class: "agent-badge", text: (role ? role + ": " : "") + agent }) : null,
      el("span", { class: "mono faint", text: shortId(t.id) })
    )
  );
  const heroRight = el("div", { style: "text-align:right;min-width:180px" });
  if (t.started_at) {
    heroRight.appendChild(el("div", { class: "stat-label", text: "Elapsed" }));
    heroRight.appendChild(liveTimer(t.started_at, "hero-timer"));
  }
  // Current state timer
  const lastStateEntry = getLastStateEntryTime();
  if (lastStateEntry && isActive) {
    heroRight.appendChild(el("div", { class: "stat-label", style: "margin-top:8px", text: STATUS_META[t.status] ? STATUS_META[t.status].label : t.status }));
    heroRight.appendChild(liveTimer(lastStateEntry, ""));
  }
  heroRight.appendChild(el("div", { style: "margin-top:8px" },
    el("span", { class: "stat-label", text: "Started: " }),
    el("span", { class: "mono", text: fmtTime(t.started_at) })
  ));
  heroRight.appendChild(el("div", {},
    el("span", { class: "stat-label", text: "Iteration: " }),
    el("span", { class: "mono", text: (t.iteration || 0) + " / " + (t.max_iterations || 0) })
  ));

  const hero = el("div", { class: "task-header-hero mb" }, heroLeft, heroRight);
  wrap.appendChild(hero);

  const grid = el("div", { class: "mc-grid" });

  /* ===== Left column ===== */
  const left = el("div", {});

  /* Pipeline + State Timeline */
  const railCard = el("div", { class: "card pad-0 mb" },
    el("div", { class: "card-head" },
      el("h3", { text: "Pipeline" }),
      el("div", { class: "spacer" }),
      statusBadge(t.status)
    )
  );
  const railBody = el("div", { class: "card-body" });

  // Build state durations from state history
  const historyMap = {};
  for (const h of state.stateHistory) {
    historyMap[h.state] = h;
  }

  const rail = el("div", { class: "stage-rail" });
  const curIdx = STAGES.indexOf(t.status);
  for (let i = 0; i < STAGES.length; i++) {
    const s = STAGES[i];
    let cls = "stage";
    if (isTerminal) {
      if (s === t.status) cls += " fail";
    } else if (i < curIdx) cls += " done";
    else if (i === curIdx) cls += " current";

    const hEntry = historyMap[s];
    let durNode = null;
    if (hEntry && hEntry.duration_seconds !== null && hEntry.duration_seconds !== undefined) {
      durNode = el("span", { class: "stage-dur", text: dur(hEntry.duration_seconds) });
    } else if (i === curIdx && !isTerminal && lastStateEntry) {
      durNode = liveTimer(lastStateEntry, "stage-dur");
    }

    rail.appendChild(el("div", { class: cls },
      el("span", { class: "sdot" }),
      el("span", { class: "slabel", text: STATUS_META[s] ? STATUS_META[s].label : s }),
      durNode
    ));
  }
  railBody.appendChild(rail);
  railCard.appendChild(railBody);
  left.appendChild(railCard);

  /* Telemetry card */
  const telCard = el("div", { class: "card pad-0 mb" },
    el("div", { class: "card-head" }, el("h3", { text: "Telemetry" }))
  );
  const tb = el("div", { class: "card-body" });
  const tel = state.telemetry;
  if (tel.model) {
    tb.appendChild(el("div", { class: "kv" },
      el("div", { class: "k", text: "Model" }),
      el("div", { class: "v mono", text: tel.model })
    ));
  }
  if (tel.usage) {
    const u = tel.usage;
    if (u.input_tokens !== undefined) {
      tb.appendChild(el("div", { class: "kv" },
        el("div", { class: "k", text: "Input Tokens" }),
        el("div", { class: "v mono", text: Number(u.input_tokens).toLocaleString() })
      ));
    }
    if (u.output_tokens !== undefined) {
      tb.appendChild(el("div", { class: "kv" },
        el("div", { class: "k", text: "Output Tokens" }),
        el("div", { class: "v mono", text: Number(u.output_tokens).toLocaleString() })
      ));
    }
    if (u.thinking_tokens !== undefined && u.thinking_tokens > 0) {
      tb.appendChild(el("div", { class: "kv" },
        el("div", { class: "k", text: "Thinking Tokens" }),
        el("div", { class: "v mono", text: Number(u.thinking_tokens).toLocaleString() })
      ));
    }
    if (u.total_tokens !== undefined) {
      tb.appendChild(el("div", { class: "kv" },
        el("div", { class: "k", text: "Total Tokens" }),
        el("div", { class: "v mono", text: Number(u.total_tokens).toLocaleString() })
      ));
    }
    tb.appendChild(el("div", { class: "kv" },
      el("div", { class: "k", text: "Source" }),
      el("div", { class: "v faint", text: "reported by provider" })
    ));
  } else {
    tb.appendChild(el("div", { class: "faint", style: "padding:8px 0", text: "Token usage unavailable from current provider" }));
  }
  if (tel.duration_seconds) {
    tb.appendChild(el("div", { class: "kv" },
      el("div", { class: "k", text: "Provider Duration" }),
      el("div", { class: "v mono", text: dur(tel.duration_seconds) })
    ));
  }
  if (tel.num_turns) {
    tb.appendChild(el("div", { class: "kv" },
      el("div", { class: "k", text: "Turns" }),
      el("div", { class: "v mono", text: String(tel.num_turns) })
    ));
  }
  telCard.appendChild(tb);
  left.appendChild(telCard);

  /* Task Detail */
  const detail = el("div", { class: "card pad-0" },
    el("div", { class: "card-head" }, el("h3", { text: "Task Detail" }))
  );
  const db = el("div", { class: "card-body" });
  db.appendChild(el("div", { class: "kv" }, el("div", { class: "k", text: "Project" }), el("div", { class: "v", text: projectName(t.project_id) })));
  db.appendChild(el("div", { class: "kv" }, el("div", { class: "k", text: "Priority" }), el("div", { class: "v" }, priorityBadge(t.priority))));
  db.appendChild(el("div", { class: "kv" }, el("div", { class: "k", text: "Created" }), el("div", { class: "v", text: fmtDateTime(t.created_at) })));
  if (t.completed_at) {
    db.appendChild(el("div", { class: "kv" }, el("div", { class: "k", text: "Completed" }), el("div", { class: "v", text: fmtDateTime(t.completed_at) })));
  }
  if (t.description) {
    db.appendChild(el("div", { class: "mt" },
      el("div", { class: "stat-label mb", text: "Description" }),
      el("div", { class: "pre", text: t.description })
    ));
  }
  if (t.error_information) {
    db.appendChild(el("div", { class: "mt" },
      el("div", { class: "stat-label mb", text: "Error" }),
      el("div", { class: "pre err-pre", text: t.error_information })
    ));
  }
  detail.appendChild(db);
  left.appendChild(detail);
  grid.appendChild(left);

  /* ===== Right column ===== */
  const right = el("div", {});

  /* Controls */
  const ctrl = el("div", { class: "card pad-0 mb" },
    el("div", { class: "card-head" }, el("h3", { text: "Controls" }))
  );
  const cb = el("div", { class: "card-body" });
  cb.appendChild(el("div", { class: "flex wrap" },
    el("button", { class: "btn primary", text: "Start", disabled: isActive ? "disabled" : null, onclick: () => runTask(t.id) }),
    el("button", { class: "btn danger", text: "Stop", disabled: isActive ? null : "disabled", onclick: () => stopTask(t.id) }),
    el("button", { class: "btn", text: "Refresh", onclick: () => selectMissionTask(t.id) })
  ));
  cb.appendChild(el("div", { class: "mt faint", text: isActive ? "Task is running. Live events stream below." : (isTerminal ? "Task has finished." : "Task is idle.") }));
  ctrl.appendChild(cb);
  right.appendChild(ctrl);

  /* Live Event Stream */
  const logCard = el("div", { class: "card pad-0 mb" },
    el("div", { class: "card-head" },
      el("h3", { text: "Live Event Stream" }),
      el("div", { class: "spacer" }),
      el("span", { class: "dot " + (state.ws && state.ws.readyState === 1 ? "ok" : "warn") }),
      el("span", { class: "faint mono", text: state.ws && state.ws.readyState === 1 ? "live" : "poll" })
    )
  );
  const lb = el("div", { class: "card-body" });
  const log = el("div", { class: "log", id: "mission-log" });
  if (!state.taskEvents.length) {
    log.appendChild(el("div", { class: "faint", text: "No events yet." }));
  } else {
    // Filter out noisy AGENT_CHUNK text events for the log, keep tool calls and state changes
    for (const e of state.taskEvents) {
      const p = e.payload || {};
      if (e.event_type === "AGENT_CHUNK" && p.type === "text") continue;
      if (e.event_type === "AGENT_CHUNK" && p.type === "step_telemetry") continue;
      log.appendChild(logLine(e));
    }
  }
  lb.appendChild(log);
  logCard.appendChild(lb);
  right.appendChild(logCard);

  /* Artifacts */
  const artCard = el("div", { class: "card pad-0" },
    el("div", { class: "card-head" },
      el("h3", { text: "Artifacts" }),
      el("div", { class: "spacer" }),
      el("span", { class: "faint mono", text: String(state.taskArtifacts.length) })
    )
  );
  const ab = el("div", { class: "card-body" });
  if (!state.taskArtifacts.length) {
    ab.appendChild(el("div", { class: "faint", text: "No artifacts recorded." }));
  } else {
    for (const a of state.taskArtifacts) {
      ab.appendChild(el("div", { class: "kv" },
        el("div", { class: "k" },
          el("span", { class: "badge cyan", text: a.kind || "artifact" }),
          el("span", { class: "mono faint", style: "margin-left:8px", text: a.path || a.name || shortId(a.id) })
        ),
        el("div", { class: "v faint", text: fmtDateTime(a.created_at) })
      ));
    }
  }
  artCard.appendChild(ab);
  right.appendChild(artCard);

  grid.appendChild(right);
  wrap.appendChild(grid);
  return wrap;
}

/** Get the ISO timestamp of when the current state was entered */
function getLastStateEntryTime() {
  if (!state.stateHistory.length) return null;
  const last = state.stateHistory[state.stateHistory.length - 1];
  return last.entered_at || null;
}

async function selectMissionTask(id) {
  state.selectedTaskId = id || null;
  state.taskEvents = [];
  state.taskArtifacts = [];
  state.stateHistory = [];
  state.telemetry = {};
  closeWs();
  if (!id) { render(); return; }
  render();
  try {
    const [events, artifacts, history] = await Promise.all([
      api("/tasks/" + id + "/events").catch(() => []),
      api("/tasks/" + id + "/artifacts").catch(() => []),
      api("/tasks/" + id + "/state-history").catch(() => [])
    ]);
    state.taskEvents = events || [];
    state.taskArtifacts = artifacts || [];
    state.stateHistory = history || [];
    // Extract telemetry from events
    extractTelemetryFromEvents(events || []);
  } catch (e) {
    toast("Failed to load task detail: " + e.message, "err");
  }
  render();
  openWs(id);
}

/** Scan events for telemetry data (init_info, result_telemetry) */
function extractTelemetryFromEvents(events) {
  state.telemetry = {};
  for (const e of events) {
    if (e.event_type !== "AGENT_CHUNK") continue;
    const p = e.payload || {};
    if (p.type === "init_info") {
      if (p.model) state.telemetry.model = p.model;
    }
    if (p.type === "result_telemetry") {
      if (p.model) state.telemetry.model = p.model;
      if (p.usage) state.telemetry.usage = p.usage;
      if (p.duration_seconds) state.telemetry.duration_seconds = p.duration_seconds;
      if (p.num_turns) state.telemetry.num_turns = p.num_turns;
    }
  }
}

/* ---------- WebSocket ---------- */
function openWs(taskId) {
  try {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(proto + "//" + location.host + "/ws/tasks/" + taskId);
    state.ws = ws;
    state.wsTaskId = taskId;
    ws.onmessage = (ev) => {
      if (state.wsTaskId !== taskId) return;
      let msg = null;
      try { msg = JSON.parse(ev.data); } catch (_) { return; }
      if (msg && msg.event_type) {
        state.taskEvents.push(msg);
        // Handle telemetry events inline
        if (msg.event_type === "AGENT_CHUNK" && msg.payload) {
          const p = msg.payload;
          if (p.type === "init_info" && p.model) {
            state.telemetry.model = p.model;
          }
          if (p.type === "result_telemetry") {
            if (p.model) state.telemetry.model = p.model;
            if (p.usage) state.telemetry.usage = p.usage;
            if (p.duration_seconds) state.telemetry.duration_seconds = p.duration_seconds;
            if (p.num_turns) state.telemetry.num_turns = p.num_turns;
          }
        }
        // Filter out text chunks from log
        const payload = msg.payload || {};
        if (!(msg.event_type === "AGENT_CHUNK" && (payload.type === "text" || payload.type === "step_telemetry"))) {
          appendLogLine(msg);
        }
        if (msg.event_type === "STATE_CHANGED" && msg.payload) {
          const t = taskById(taskId);
          if (t) {
            t.status = msg.payload.new_status || t.status;
            if (msg.payload.agent) t.current_agent = msg.payload.agent;
            if (msg.payload.error) t.error_information = msg.payload.error;
          }
          // Update state history
          state.stateHistory.push({
            state: msg.payload.new_status,
            agent: msg.payload.agent,
            entered_at: msg.created_at,
            exited_at: null,
            duration_seconds: null
          });
          // Close previous entry
          if (state.stateHistory.length > 1) {
            const prev = state.stateHistory[state.stateHistory.length - 2];
            if (!prev.exited_at) {
              prev.exited_at = msg.created_at;
              const entered = new Date(prev.entered_at);
              const exited = new Date(prev.exited_at);
              if (!isNaN(entered) && !isNaN(exited)) {
                prev.duration_seconds = Math.round((exited - entered) / 1000 * 10) / 10;
              }
            }
          }
          if (state.route === "mission" && state.selectedTaskId === taskId) {
            render();
          }
        }
      }
    };
    ws.onclose = () => { if (state.ws === ws) state.ws = null; };
    ws.onerror = () => {};
  } catch (_) {
    state.ws = null;
  }
}

function closeWs() {
  if (state.ws) {
    try { state.ws.close(); } catch (_) {}
    state.ws = null;
  }
  state.wsTaskId = null;
}

function appendLogLine(e) {
  const log = $("#mission-log");
  if (!log) return;
  if (log.firstChild && log.firstChild.className === "faint") log.innerHTML = "";
  log.appendChild(logLine(e));
  log.scrollTop = log.scrollHeight;
}

/* ---------- view: Settings ---------- */
function viewSettings() {
  const wrap = el("div", {});
  const cfg = state.config || {};
  const card = el("div", { class: "card pad-0 mb" },
    el("div", { class: "card-head" },
      el("h3", { text: "Runtime Configuration" }),
      el("div", { class: "spacer" }),
      el("button", { class: "btn sm", text: "Reload", onclick: refresh })
    )
  );
  const b = el("div", { class: "card-body" });
  const keys = Object.keys(cfg).sort();
  if (!keys.length) {
    b.appendChild(emptyState("\u2699", "Configuration unavailable."));
  } else {
    for (const k of keys) {
      const v = cfg[k];
      let node;
      if (typeof v === "boolean") {
        node = el("span", { class: "badge " + (v ? "green" : "gray"), text: v ? "true" : "false" });
      } else if (v === null || v === undefined) {
        node = el("span", { class: "faint", text: "-" });
      } else if (typeof v === "object") {
        node = el("span", { class: "mono faint", text: JSON.stringify(v) });
      } else {
        node = el("span", { class: "mono", text: String(v) });
      }
      b.appendChild(el("div", { class: "kv" }, el("div", { class: "k mono", text: k }), el("div", { class: "v" }, node)));
    }
  }
  card.appendChild(b);
  wrap.appendChild(card);

  const info = el("div", { class: "card pad-0" },
    el("div", { class: "card-head" }, el("h3", { text: "Endpoints" }))
  );
  const ib = el("div", { class: "card-body" });
  const endpoints = [
    ["GET", "/health"], ["GET", "/overview"], ["GET", "/config"],
    ["GET", "/projects"], ["POST", "/projects"], ["GET", "/projects/{id}"],
    ["PUT", "/projects/{id}"], ["DELETE", "/projects/{id}"],
    ["GET", "/tasks"], ["POST", "/tasks"], ["GET", "/tasks/{id}"],
    ["PUT", "/tasks/{id}"], ["DELETE", "/tasks/{id}"],
    ["POST", "/tasks/{id}/start"], ["POST", "/tasks/{id}/stop"],
    ["POST", "/tasks/{id}/pause"], ["POST", "/tasks/{id}/resume"],
    ["POST", "/tasks/{id}/retry"], ["POST", "/tasks/{id}/cancel"],
    ["GET", "/tasks/{id}/events"], ["GET", "/tasks/{id}/state-history"],
    ["GET", "/tasks/{id}/artifacts"],
    ["GET", "/artifacts/{id}/content"], ["GET", "/activity"],
    ["WS", "/ws/tasks/{id}"]
  ];
  for (const pair of endpoints) {
    ib.appendChild(el("div", { class: "kv" },
      el("div", { class: "k mono", text: pair[1] }),
      el("div", { class: "v" }, el("span", { class: "badge " + (pair[0] === "WS" ? "purple" : pair[0] === "GET" ? "blue" : "green"), text: pair[0] }))
    ));
  }
  info.appendChild(ib);
  wrap.appendChild(info);
  return wrap;
}

/* ---------- modals ---------- */
function closeModal() { $("#modal-root").innerHTML = ""; }

function openModal(title, bodyNode, footNodes, wide) {
  const root = $("#modal-root");
  root.innerHTML = "";
  const overlay = el("div", { class: "overlay", onclick: (e) => { if (e.target === overlay) closeModal(); } },
    el("div", { class: "modal" + (wide ? " wide" : "") },
      el("div", { class: "modal-head" },
        el("h2", { text: title }),
        el("div", { class: "spacer" }),
        el("button", { class: "btn sm ghost", text: "\u2715", onclick: closeModal })
      ),
      el("div", { class: "modal-body" }, bodyNode),
      el("div", { class: "modal-foot" }, footNodes)
    )
  );
  root.appendChild(overlay);
}

function openNewProject() {
  const name = el("input", { placeholder: "my-project" });
  const repository = el("input", { placeholder: "C:\\path\\to\\repo" });
  const type = el("select", {},
    el("option", { value: "python", text: "python" }), el("option", { value: "javascript", text: "javascript" }),
    el("option", { value: "typescript", text: "typescript" }), el("option", { value: "go", text: "go" }),
    el("option", { value: "rust", text: "rust" }), el("option", { value: "java", text: "java" })
  );
  const test = el("input", { placeholder: "pytest -q" });
  const body = el("div", {},
    el("div", { class: "field" }, el("label", { text: "Name" }), name),
    el("div", { class: "field" }, el("label", { text: "Repository Path" }), repository, el("div", { class: "hint", text: "Absolute path to the local git repository." })),
    el("div", { class: "row" },
      el("div", { class: "field" }, el("label", { text: "Type" }), type),
      el("div", { class: "field" }, el("label", { text: "Test Command" }), test)
    )
  );
  const submit = async () => {
    if (!name.value.trim() || !repository.value.trim()) { toast("Name and repository path are required", "err"); return; }
    try {
      await api("/projects", { method: "POST", body: { name: name.value.trim(), repository: repository.value.trim(), type: type.value, test_command: test.value.trim() || null } });
      closeModal(); toast("Project created", "ok"); await loadAll();
    } catch (e) { toast("Create failed: " + e.message, "err"); }
  };
  openModal("New Project", body, [
    el("button", { class: "btn", text: "Cancel", onclick: closeModal }),
    el("button", { class: "btn primary", text: "Create", onclick: submit })
  ]);
}

function openNewTask(projectId) {
  const title = el("input", { placeholder: "Fix the flaky login test" });
  const desc = el("textarea", { placeholder: "Describe the problem, expected behaviour, and any constraints." });
  const proj = el("select", {},
    state.projects.map((p) => el("option", { value: p.id, text: p.name, selected: projectId === p.id ? "selected" : null }))
  );
  const prio = el("select", {},
    el("option", { value: "medium", text: "medium" }), el("option", { value: "high", text: "high" }), el("option", { value: "low", text: "low" })
  );
  const maxIter = el("input", { type: "number", value: "3", min: "1", max: "10" });
  const body = el("div", {},
    el("div", { class: "field" }, el("label", { text: "Title" }), title),
    el("div", { class: "field" }, el("label", { text: "Description" }), desc),
    el("div", { class: "field" }, el("label", { text: "Project" }), proj),
    el("div", { class: "row" },
      el("div", { class: "field" }, el("label", { text: "Priority" }), prio),
      el("div", { class: "field" }, el("label", { text: "Max Iterations" }), maxIter)
    )
  );
  const submit = async () => {
    if (!title.value.trim()) { toast("Title is required", "err"); return; }
    if (!proj.value) { toast("Create a project first", "err"); return; }
    try {
      await api("/tasks", { method: "POST", body: {
        title: title.value.trim(), description: desc.value.trim(), project_id: proj.value,
        priority: prio.value, max_iterations: parseInt(maxIter.value, 10) || 3
      }});
      closeModal(); toast("Task created", "ok"); await loadAll();
    } catch (e) { toast("Create failed: " + e.message, "err"); }
  };
  openModal("New Task", body, [
    el("button", { class: "btn", text: "Cancel", onclick: closeModal }),
    el("button", { class: "btn primary", text: "Create", onclick: submit })
  ]);
}

async function openTask(id) {
  const t = taskById(id);
  if (!t) { toast("Task not found", "err"); return; }
  let events = [], artifacts = [];
  try {
    const r = await Promise.all([
      api("/tasks/" + id + "/events").catch(() => []),
      api("/tasks/" + id + "/artifacts").catch(() => [])
    ]);
    events = r[0] || [];
    artifacts = r[1] || [];
  } catch (_) {}

  const body = el("div", {},
    el("div", { class: "kv" }, el("div", { class: "k", text: "Status" }), el("div", { class: "v" }, statusBadge(t.status))),
    el("div", { class: "kv" }, el("div", { class: "k", text: "Agent" }), el("div", { class: "v" }, t.current_agent ? el("span", { class: "agent-badge", text: agentDisplayName(t.current_agent) }) : el("span", { class: "faint", text: "-" }))),
    el("div", { class: "kv" }, el("div", { class: "k", text: "Project" }), el("div", { class: "v", text: projectName(t.project_id) })),
    el("div", { class: "kv" }, el("div", { class: "k", text: "Priority" }), el("div", { class: "v" }, priorityBadge(t.priority))),
    el("div", { class: "kv" }, el("div", { class: "k", text: "Iteration" }), el("div", { class: "v mono", text: (t.iteration || 0) + " / " + (t.max_iterations || 0) })),
    el("div", { class: "kv" }, el("div", { class: "k", text: "Updated" }), el("div", { class: "v", text: fmtDateTime(t.updated_at) })),
    t.description ? el("div", { class: "mt" }, el("div", { class: "stat-label mb", text: "Description" }), el("div", { class: "pre", text: t.description })) : null,
    t.error_information ? el("div", { class: "mt" }, el("div", { class: "stat-label mb", text: "Error" }), el("div", { class: "pre err-pre", text: t.error_information })) : null,
    el("div", { class: "mt" },
      el("div", { class: "stat-label mb", text: "Recent Events (" + events.length + ")" }),
      events.length
        ? el("div", { class: "log", style: "height:200px" }, events.slice(-40).map(logLine))
        : el("div", { class: "faint", text: "No events." })
    ),
    el("div", { class: "mt" },
      el("div", { class: "stat-label mb", text: "Artifacts (" + artifacts.length + ")" }),
      artifacts.length
        ? el("div", {}, artifacts.map((a) => el("div", { class: "kv" },
            el("div", { class: "k" }, el("span", { class: "badge cyan", text: a.kind || "artifact" }), el("span", { class: "mono faint", style: "margin-left:8px", text: a.path || a.name || shortId(a.id) })),
            el("div", { class: "v faint", text: fmtDateTime(a.created_at) })
          )))
        : el("div", { class: "faint", text: "No artifacts." })
    )
  );

  openModal(t.title, body, [
    el("button", { class: "btn", text: "Close", onclick: closeModal }),
    el("button", { class: "btn", text: "Mission Control", onclick: () => { closeModal(); go("mission"); selectMissionTask(id); } }),
    el("button", { class: "btn primary", text: "Run", onclick: () => { closeModal(); runTask(id); } })
  ], true);
}

/* ---------- actions ---------- */
async function runTask(id) {
  try {
    await api("/tasks/" + id + "/start", { method: "POST" });
    toast("Task started", "ok");
    await loadAll();
    if (state.route === "mission") selectMissionTask(id);
  } catch (e) { toast("Run failed: " + e.message, "err"); }
}

async function stopTask(id) {
  try {
    await api("/tasks/" + id + "/stop", { method: "POST" });
    toast("Stop requested", "ok");
    await loadAll();
    if (state.route === "mission") selectMissionTask(id);
  } catch (e) { toast("Stop failed: " + e.message, "err"); }
}

/* ---------- render ---------- */
function render() {
  const view = $("#view");
  if (!view) return;
  view.innerHTML = "";
  let node;
  switch (state.route) {
    case "projects": node = viewProjects(); break;
    case "tasks":    node = viewTasks();    break;
    case "kanban":   node = viewKanban();   break;
    case "mission":  node = viewMission();  break;
    case "activity": node = viewActivity(); break;
    case "settings": node = viewSettings(); break;
    default:         node = viewOverview();
  }
  view.appendChild(node);
}

/* ---------- bootstrap ---------- */
function tickClock() {
  const c = $("#clock");
  if (c) c.textContent = new Date().toLocaleTimeString();
}

document.addEventListener("DOMContentLoaded", () => {
  $("#btn-refresh").addEventListener("click", refresh);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
  tickClock();
  setInterval(tickClock, 1000);
  startTimerTick();
  renderNav();
  render();
  loadAll();
  setInterval(() => { if (!state.ws) loadAll(); }, 15000);
});
