"use strict";

/* =========================================================================
   ForgeFlow Command Center - single-page dashboard.
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
    } catch (_) { /* non-JSON error body */ }
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

function dur(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "m " + (s % 60) + "s";
  return Math.floor(s / 3600) + "h " + Math.floor((s % 3600) / 60) + "m";
}

/* ---------- state machine metadata (mirrors app/models/state.py) ---------- */
const STAGES = [
  "PENDING", "PREPARING", "INVESTIGATING", "ROOT_CAUSE_READY", "ROOT_CAUSE_REVIEW",
  "IMPLEMENTING", "IMPLEMENTATION_READY", "TESTING", "QA", "REVIEW",
  "NEEDS_CHANGES", "APPROVED", "COMPLETED"
];

const TERMINAL = ["COMPLETED", "FAILED", "STOPPED", "BLOCKED"];

const STATUS_META = {
  PENDING:              { label: "Pending",              tone: "gray"   },
  PREPARING:            { label: "Preparing",            tone: "blue"   },
  INVESTIGATING:        { label: "Investigating",        tone: "cyan"   },
  ROOT_CAUSE_READY:     { label: "Root Cause Ready",     tone: "cyan"   },
  ROOT_CAUSE_REVIEW:    { label: "Root Cause Review",    tone: "cyan"   },
  IMPLEMENTING:         { label: "Implementing",         tone: "purple" },
  IMPLEMENTATION_READY: { label: "Implementation Ready", tone: "purple" },
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

/* Kanban columns: each display column maps to the backend states it holds. */
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
  ws: null,
  wsTaskId: null,
  filters: { search: "", status: "ALL", project: "ALL" },
  loading: false
};

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

  /* reviewer / provider health */
  const cfg = state.config || {};
  const health = el("div", { class: "card pad-0 mt" },
    el("div", { class: "card-head" }, el("h3", { text: "System" }))
  );
  const hb = el("div", { class: "card-body" });
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
    el("div", { class: "k", text: "Implementation Provider" }),
    el("div", { class: "v mono", text: cfg.implementation_provider || "antigravity" })
  ));
  health.appendChild(hb);
  wrap.appendChild(health);

  return wrap;
}

/* ---------- view: Projects ---------- */
function viewProjects() {
  const wrap = el("div", {});

  const bar = el("div", { class: "toolbar" },
    el("div", { class: "spacer" }),
    el("button", { class: "btn primary", text: "+ New Project", onclick: openNewProject })
  );
  wrap.appendChild(bar);

  if (!state.projects.length) {
    wrap.appendChild(el("div", { class: "card" }, emptyState("\u25A4", "No projects yet. Create one to get started.")));
    return wrap;
  }

  const card = el("div", { class: "card pad-0" });
  const table = el("table", {},
    el("thead", {}, el("tr", {},
      el("th", { text: "Name" }),
      el("th", { text: "Type" }),
      el("th", { text: "Repository" }),
      el("th", { text: "Test Command" }),
      el("th", { text: "Tasks" }),
      el("th", { text: "Created" }),
      el("th", { text: "" })
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
        )
      )
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

  const search = el("input", {
    class: "search",
    placeholder: "Search tasks...",
    value: f.search,
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
    search,
    statusSel,
    projSel,
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
      el("th", { text: "Title" }),
      el("th", { text: "Project" }),
      el("th", { text: "Status" }),
      el("th", { text: "Priority" }),
      el("th", { text: "Iter" }),
      el("th", { text: "Updated" }),
      el("th", { text: "" })
    ))
  );
  const tbody = el("tbody", {});
  for (const t of rows) {
    tbody.appendChild(el("tr", {},
      el("td", {},
        el("div", { style: "font-weight:600", text: t.title }),
        el("div", { class: "mono faint", text: shortId(t.id) })
      ),
      el("td", { class: "muted", text: projectName(t.project_id) }),
      el("td", {}, statusBadge(t.status)),
      el("td", {}, priorityBadge(t.priority)),
      el("td", { class: "mono", text: (t.iteration || 0) + "/" + (t.max_iterations || 0) }),
      el("td", { class: "faint nowrap", text: ago(t.updated_at) }),
      el("td", {},
        el("div", { class: "flex" },
          el("button", { class: "btn sm", text: "Open", onclick: () => openTask(t.id) }),
          el("button", { class: "btn sm primary", text: "Run", onclick: () => runTask(t.id) })
        )
      )
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
    el("input", {
      class: "search",
      placeholder: "Search tasks...",
      value: state.filters.search,
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
            priorityBadge(t.priority),
            el("span", { text: projectName(t.project_id) }),
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
  STATE_CHANGED: "info",
  TASK_STARTED: "ok",
  TASK_COMPLETED: "ok",
  TASK_FAILED: "err",
  TASK_STOPPED: "warn",
  TASK_BLOCKED: "err",
  TEST_RESULT: "warn",
  REVIEW_RESULT: "agent",
  AGENT_MESSAGE: "agent",
  ARTIFACT_CREATED: "info",
  ERROR: "err"
};

function eventSummary(e) {
  const p = e.payload || {};
  switch (e.event_type) {
    case "STATE_CHANGED":
      return (p.old_status || "?") + " → " + (p.new_status || "?") + (p.error ? "  [Error: " + p.error + "]" : (p.reason ? "  (" + p.reason + ")" : ""));
    case "TEST_RESULT":
      return "exit " + p.exit_code + (p.command ? "  " + p.command : "");
    case "REVIEW_RESULT":
      return (p.decision || "?") + (p.summary ? "  " + p.summary : "");
    case "AGENT_MESSAGE":
      return (p.role ? p.role + ": " : "") + (p.message || p.content || "");
    case "ARTIFACT_CREATED":
      return (p.kind || "artifact") + "  " + (p.path || p.name || "");
    default: {
      const keys = Object.keys(p);
      if (!keys.length) return "";
      return keys.slice(0, 3).map((k) => k + "=" + String(p[k]).slice(0, 60)).join("  ");
    }
  }
}

function logLine(e) {
  const tone = EVENT_TONE[e.event_type] || "";
  return el("div", { class: "log-line " + tone },
    el("span", { class: "log-time", text: fmtTime(e.created_at || e.timestamp) }),
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
    el("span", { class: "faint", text: "Task:" }),
    sel,
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

  const grid = el("div", { class: "mc-grid" });

  /* left: stage rail + task detail */
  const left = el("div", {});

  const railCard = el("div", { class: "card pad-0 mb" },
    el("div", { class: "card-head" },
      el("h3", { text: "Pipeline" }),
      el("div", { class: "spacer" }),
      statusBadge(t.status)
    )
  );
  const railBody = el("div", { class: "card-body" });
  const rail = el("div", { class: "stage-rail" });
  const curIdx = STAGES.indexOf(t.status);
  const isTerminal = TERMINAL.indexOf(t.status) !== -1;
  for (let i = 0; i < STAGES.length; i++) {
    const s = STAGES[i];
    let cls = "stage";
    if (isTerminal) {
      if (s === t.status) cls += " fail";
      else if (curIdx === -1) cls += "";
    } else if (i < curIdx) cls += " done";
    else if (i === curIdx) cls += " current";
    rail.appendChild(el("div", { class: cls },
      el("span", { class: "sdot" }),
      el("span", { text: STATUS_META[s] ? STATUS_META[s].label : s })
    ));
  }
  railBody.appendChild(rail);
  railCard.appendChild(railBody);
  left.appendChild(railCard);

  const detail = el("div", { class: "card pad-0" },
    el("div", { class: "card-head" }, el("h3", { text: "Task Detail" }))
  );
  const db = el("div", { class: "card-body" });
  db.appendChild(el("div", { class: "kv" }, el("div", { class: "k", text: "Title" }), el("div", { class: "v", text: t.title })));
  db.appendChild(el("div", { class: "kv" }, el("div", { class: "k", text: "ID" }), el("div", { class: "v mono", text: t.id })));
  db.appendChild(el("div", { class: "kv" }, el("div", { class: "k", text: "Project" }), el("div", { class: "v", text: projectName(t.project_id) })));
  db.appendChild(el("div", { class: "kv" }, el("div", { class: "k", text: "Priority" }), el("div", { class: "v" }, priorityBadge(t.priority))));
  db.appendChild(el("div", { class: "kv" }, el("div", { class: "k", text: "Iteration" }), el("div", { class: "v mono", text: (t.iteration || 0) + " / " + (t.max_iterations || 0) })));
  db.appendChild(el("div", { class: "kv" }, el("div", { class: "k", text: "Created" }), el("div", { class: "v", text: fmtDateTime(t.created_at) })));
  db.appendChild(el("div", { class: "kv" }, el("div", { class: "k", text: "Updated" }), el("div", { class: "v", text: fmtDateTime(t.updated_at) })));
  if (t.description) {
    db.appendChild(el("div", { class: "mt" },
      el("div", { class: "stat-label mb", text: "Description" }),
      el("div", { class: "pre", text: t.description })
    ));
  }
  if (t.error_information) {
    db.appendChild(el("div", { class: "mt" },
      el("div", { class: "stat-label mb", text: "Error" }),
      el("div", { class: "pre", style: "border-color:rgba(255,92,92,.4)", text: t.error_information })
    ));
  }
  detail.appendChild(db);
  left.appendChild(detail);

  grid.appendChild(left);

  /* right: controls + live log + artifacts */
  const right = el("div", {});

  const ctrl = el("div", { class: "card pad-0 mb" },
    el("div", { class: "card-head" }, el("h3", { text: "Controls" }))
  );
  const cb = el("div", { class: "card-body" });
  const running = !isTerminal;
  cb.appendChild(el("div", { class: "flex wrap" },
    el("button", { class: "btn primary", text: "Start", disabled: running ? "disabled" : null, onclick: () => runTask(t.id) }),
    el("button", { class: "btn danger", text: "Stop", disabled: running ? null : "disabled", onclick: () => stopTask(t.id) }),
    el("button", { class: "btn", text: "Refresh", onclick: () => selectMissionTask(t.id) })
  ));
  cb.appendChild(el("div", { class: "mt faint", text: running ? "Task is running. Live events stream below." : "Task is idle." }));
  ctrl.appendChild(cb);
  right.appendChild(ctrl);

  const logCard = el("div", { class: "card pad-0 mb" },
    el("div", { class: "card-head" },
      el("h3", { text: "Live Event Stream" }),
      el("div", { class: "spacer" }),
      el("span", { class: "dot " + (state.ws && state.ws.readyState === 1 ? "ok" : "warn") }),
      el("span", { class: "faint mono", text: state.ws && state.ws.readyState === 1 ? "ws" : "poll" })
    )
  );
  const lb = el("div", { class: "card-body" });
  const log = el("div", { class: "log", id: "mission-log" });
  if (!state.taskEvents.length) {
    log.appendChild(el("div", { class: "faint", text: "No events yet." }));
  } else {
    for (const e of state.taskEvents) log.appendChild(logLine(e));
  }
  lb.appendChild(log);
  logCard.appendChild(lb);
  right.appendChild(logCard);

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

async function selectMissionTask(id) {
  state.selectedTaskId = id || null;
  state.taskEvents = [];
  state.taskArtifacts = [];
  closeWs();
  if (!id) { render(); return; }
  render();
  try {
    const [events, artifacts] = await Promise.all([
      api("/tasks/" + id + "/events").catch(() => []),
      api("/tasks/" + id + "/artifacts").catch(() => [])
    ]);
    state.taskEvents = events || [];
    state.taskArtifacts = artifacts || [];
  } catch (e) {
    toast("Failed to load task detail: " + e.message, "err");
  }
  render();
  openWs(id);
}

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
        appendLogLine(msg);
        if (msg.event_type === "STATE_CHANGED" && msg.payload) {
          const t = taskById(taskId);
          if (t) {
            t.status = msg.payload.new_status || t.status;
            if (msg.payload.agent) t.current_agent = msg.payload.agent;
            if (msg.payload.error) t.error_information = msg.payload.error;
            if (state.route === "mission" && state.selectedTaskId === taskId) {
              render();
            }
          }
        }
      }
    };
    ws.onclose = () => { if (state.ws === ws) state.ws = null; };
    ws.onerror = () => { /* fall back to polling via Refresh */ };
  } catch (_) {
    state.ws = null;
  }
}

function closeWs() {
  if (state.ws) {
    try { state.ws.close(); } catch (_) { /* already closed */ }
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
    ["GET", "/tasks/{id}/events"], ["GET", "/tasks/{id}/artifacts"],
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
function closeModal() {
  $("#modal-root").innerHTML = "";
}

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
    el("option", { value: "python", text: "python" }),
    el("option", { value: "javascript", text: "javascript" }),
    el("option", { value: "typescript", text: "typescript" }),
    el("option", { value: "go", text: "go" }),
    el("option", { value: "rust", text: "rust" }),
    el("option", { value: "java", text: "java" })
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
    if (!name.value.trim() || !repository.value.trim()) {
      toast("Name and repository path are required", "err");
      return;
    }
    try {
      await api("/projects", { method: "POST", body: {
        name: name.value.trim(),
        repository: repository.value.trim(),
        type: type.value,
        test_command: test.value.trim() || null
      } });
      closeModal();
      toast("Project created", "ok");
      await loadAll();
    } catch (e) {
      toast("Create failed: " + e.message, "err");
    }
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
    el("option", { value: "medium", text: "medium" }),
    el("option", { value: "high", text: "high" }),
    el("option", { value: "low", text: "low" })
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
        title: title.value.trim(),
        description: desc.value.trim(),
        project_id: proj.value,
        priority: prio.value,
        max_iterations: parseInt(maxIter.value, 10) || 3
      } });
      closeModal();
      toast("Task created", "ok");
      await loadAll();
    } catch (e) {
      toast("Create failed: " + e.message, "err");
    }
  };

  openModal("New Task", body, [
    el("button", { class: "btn", text: "Cancel", onclick: closeModal }),
    el("button", { class: "btn primary", text: "Create", onclick: submit })
  ]);
}

async function openTask(id) {
  const t = taskById(id);
  if (!t) { toast("Task not found", "err"); return; }
  let events = [];
  let artifacts = [];
  try {
    const r = await Promise.all([
      api("/tasks/" + id + "/events").catch(() => []),
      api("/tasks/" + id + "/artifacts").catch(() => [])
    ]);
    events = r[0] || [];
    artifacts = r[1] || [];
  } catch (_) { /* detail is best-effort */ }

  const body = el("div", {},
    el("div", { class: "kv" }, el("div", { class: "k", text: "Status" }), el("div", { class: "v" }, statusBadge(t.status))),
    el("div", { class: "kv" }, el("div", { class: "k", text: "Project" }), el("div", { class: "v", text: projectName(t.project_id) })),
    el("div", { class: "kv" }, el("div", { class: "k", text: "Priority" }), el("div", { class: "v" }, priorityBadge(t.priority))),
    el("div", { class: "kv" }, el("div", { class: "k", text: "Iteration" }), el("div", { class: "v mono", text: (t.iteration || 0) + " / " + (t.max_iterations || 0) })),
    el("div", { class: "kv" }, el("div", { class: "k", text: "Updated" }), el("div", { class: "v", text: fmtDateTime(t.updated_at) })),
    t.description ? el("div", { class: "mt" }, el("div", { class: "stat-label mb", text: "Description" }), el("div", { class: "pre", text: t.description })) : null,
    t.error_information ? el("div", { class: "mt" }, el("div", { class: "stat-label mb", text: "Error" }), el("div", { class: "pre", text: t.error_information })) : null,
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
  } catch (e) {
    toast("Run failed: " + e.message, "err");
  }
}

async function stopTask(id) {
  try {
    await api("/tasks/" + id + "/stop", { method: "POST" });
    toast("Stop requested", "ok");
    await loadAll();
    if (state.route === "mission") selectMissionTask(id);
  } catch (e) {
    toast("Stop failed: " + e.message, "err");
  }
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
  renderNav();
  render();
  loadAll();
  setInterval(() => { if (!state.ws) loadAll(); }, 15000);
});
