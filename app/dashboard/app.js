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
  { key: "done",        title: "Done",        states: ["APPROVED", "COMPLETED", "FAILED", "BLOCKED", "STOPPED", "PAUSED"] }
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
  roles: {},
  providers: [],
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
      api("/activity?limit=200").catch(() => []),
      api("/settings/roles").catch(() => ({})),
      api("/providers").catch(() => [])
    ]);
    state.projects = results[0] || [];
    state.tasks = results[1] || [];
    state.overview = results[2];
    state.config = results[3];
    state.activity = results[4] || [];
    state.roles = results[5] || {};
    state.providers = results[6] || [];
      state.telemetry = results[7] || { providers: {} };
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
  const active = o.active_tasks || 0;
  
  const wrap = el("div", {});
  wrap.appendChild(el("h2", { style: "margin-bottom: 24px;" }, "System Overview"));
  
  const grid = el("div", { class: "grid-4 mb" },
    el("div", { class: "metric-card" },
      el("div", { class: "label" }, "Total Tasks"),
      el("div", { class: "val" }, total),
      el("div", { class: "icon" }, "\u2261")
    ),
    el("div", { class: "metric-card orange" },
      el("div", { class: "label" }, "Active"),
      el("div", { class: "val" }, active),
      el("div", { class: "icon" }, "\u2398")
    ),
    el("div", { class: "metric-card green" },
      el("div", { class: "label" }, "Completed"),
      el("div", { class: "val" }, completed),
      el("div", { class: "icon" }, "\u2713")
    ),
    el("div", { class: "metric-card red" },
      el("div", { class: "label" }, "Needs Attention"),
      el("div", { class: "val" }, failed),
      el("div", { class: "icon" }, "\u26A0")
    )
  );
  wrap.appendChild(grid);

  const sysCard = el("div", { class: "card pad-0 mt" },
    el("div", { class: "card-head" }, el("h3", { text: "Live System", style: "margin:0;" }))
  );
  const sysBody = el("div", { class: "card-body grid-2" });
  
  for (const r of ["orchestrator", "investigator", "coder", "reviewer"]) {
    const rc = (state.roles || {})[r] || {};
    const p = (state.providers || []).find(x => x.id === rc.provider) || { display_name: "Unknown" };
    sysBody.appendChild(
      el("div", { class: "field" },
        el("label", { style: "text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; margin-bottom: 4px;" }, r),
        el("div", { class: "mono", style: "font-size: 14px; font-weight: 600; color: var(--brand-burgundy-deep);" }, p.display_name),
        el("div", { class: "faint mono", style: "font-size: 12px; margin-top: 4px;" }, "Model: " + (rc.model || "default"))
      )
    );
  }
  sysCard.appendChild(sysBody);
  wrap.appendChild(sysCard);
  
  return wrap;
}

  /* ---------- view: Projects ---------- */
function viewProjects() {
  const wrap = el("div", {});
  wrap.appendChild(el("div", { class: "toolbar", style: "display: flex; gap: 12px; margin-bottom: 24px;" },
    el("div", { class: "spacer" }),
    el("button", { class: "btn primary", text: "+ New Project", onclick: openNewProject })
  ));
  if (!state.projects.length) {
    wrap.appendChild(el("div", { class: "card" }, emptyState("\u25A4", "No projects yet. Create one to get started.")));
    return wrap;
  }
  const card = el("div", { class: "card pad-0" });
  const twrap = el("div", { class: "table-wrap" });
    const table = el("table", { class: "table" },
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
  twrap.appendChild(table);
    card.appendChild(twrap);
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
  wrap.appendChild(el("div", { class: "toolbar", style: "display: flex; gap: 12px; margin-bottom: 24px;" },
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
  const twrap = el("div", { class: "table-wrap" });
    const table = el("table", { class: "table" },
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
  twrap.appendChild(table);
    card.appendChild(twrap);
  wrap.appendChild(card);
  return wrap;
}

/* ---------- view: Kanban ---------- */
function viewKanban() {
  const wrap = el("div", {});
  const rows = filteredTasks();
  wrap.appendChild(el("div", { class: "toolbar", style: "display: flex; gap: 12px; margin-bottom: 24px;" },
    el("input", { class: "search", placeholder: "Search tasks...", value: state.filters.search,
      oninput: (e) => { state.filters.search = e.target.value; render(); }
    }),
    (function() {
      const opts = [{ value: "ALL", text: "All projects" }].concat(state.projects.map(p => ({ value: p.id, text: p.name })));
      const dd = createDropdown(opts, state.filters.project || "ALL", (val) => { state.filters.project = val; render(); });
      dd.style.width = "250px";
      return dd;
    })(),
    el("div", { class: "spacer" }),
    el("span", { class: "faint mono", text: rows.length + " tasks" })
  ));
  
  const formatTime = (t) => {
    if (!t.created_at) return "00:00";
    let end = new Date();
    if (["APPROVED", "COMPLETED", "FAILED", "BLOCKED", "STOPPED", "PAUSED"].includes(t.status) && t.updated_at) {
      end = new Date(t.updated_at);
    }
    const ms = Math.max(0, end - new Date(t.created_at));
    const m = Math.floor(ms / 60000);
    const s = Math.floor((ms % 60000) / 1000);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const getCardStateClass = (status) => {
    if (["COMPLETED", "APPROVED"].includes(status)) return "done";
    if (["FAILED", "BLOCKED", "STOPPED", "PAUSED"].includes(status)) return "failed";
    if (["PENDING", "PREPARING"].includes(status)) return "queued";
    return "active"; // INVESTIGATING, IMPLEMENTING, TESTING, REVIEW, QA
  };
  
  const board = el("div", { class: "kanban-board" });
  for (const col of KANBAN) {
    const items = rows.filter((t) => col.states.indexOf(t.status) !== -1);
    
    // Check if column has any active tasks
    const colIsActive = items.some(t => getCardStateClass(t.status) === "active");
    
    const body = el("div", { class: "kanban-body" });
    if (!items.length) {
      body.appendChild(el("div", { class: "empty-col-msg", text: "Empty" }));
    } else {
      for (const t of items) {
        const cstate = getCardStateClass(t.status);
        const card = el("div", { class: `kanban-card ${cstate}`, onclick: () => openTask(t.id) });
        
        // Title
        card.appendChild(el("div", { class: "kcard-title", text: t.title }));
        
        // Agent / Status section
        const agentName = t.current_agent ? agentDisplayName(t.current_agent) : "ForgeFlow";
        card.appendChild(el("div", { class: "kcard-agent" },
          el("span", { class: `kcard-dot ${cstate}` }),
          el("span", { text: agentName })
        ));
        
        // Current state label
        const statusMeta = STATUS_META[t.status] || { label: t.status };
        card.appendChild(el("div", { class: "kcard-status-lbl", text: statusMeta.label }));
        
        // Footer (iter, time)
        const footer = el("div", { class: "kcard-footer mono" });
        if (t.iteration && t.max_iterations) {
          footer.appendChild(el("span", { text: `Iter ${t.iteration}/${t.max_iterations}` }));
        } else {
          footer.appendChild(el("span", { text: "" })); // spacer
        }
        footer.appendChild(el("span", { class: "kcard-time", text: formatTime(t) }));
        
        card.appendChild(footer);
        body.appendChild(card);
      }
    }
    
    const colEl = el("div", { class: `kanban-col ${colIsActive ? 'active' : ''}` },
      el("div", { class: "kanban-col-head" },
        el("h3", { text: col.title }),
        el("span", { class: "kcol-count", text: String(items.length) })
      ),
      body
    );
    board.appendChild(colEl);
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
  wrap.appendChild(el("h2", { style: "margin-bottom: 24px;" }, "Live Activity Feed"));

  if (!state.activity || !state.activity.length) {
    wrap.appendChild(el("div", { class: "card empty" }, emptyState("\u223F", "No activity to display.")));
    return wrap;
  }

  const feedCard = el("div", { class: "card pad-0" });
  const twrap = el("div", { class: "table-wrap" });
    const table = el("table", { class: "table" },
    el("thead", {},
      el("tr", {},
        el("th", { text: "Time" }),
        el("th", { text: "Task" }),
        el("th", { text: "Agent" }),
        el("th", { text: "Role" }),
        el("th", { text: "Event" }),
        el("th", { text: "Summary" })
      )
    ),
    el("tbody", {})
  );
  const tbody = table.querySelector("tbody");

  for (const e of state.activity) {
    const t = taskById(e.task_id);
    let taskName = t ? t.title : e.task_id.substring(0,8);
    let sum = "-";
    if (e.event_type === "STATE_CHANGED") sum = (e.payload.old_state || "NONE") + " \u2192 " + e.payload.new_state;
    else if (e.event_type === "TOOL_CALL") sum = (e.payload.tool || "unknown") + "()";
    else if (e.event_type === "ERROR") sum = String(e.payload.error).slice(0, 50) + "...";
    else if (e.event_type === "AGENT_CHUNK") sum = "text chunk (" + String(e.payload.content || "").length + "b)";
    else if (e.event_type === "ARTIFACT") sum = e.payload.name;
    
    // Find agent logic if present in payload or fallback to task agent
    let agent = "System";
    let role = "-";
    if (e.event_type === "STATE_CHANGED" && e.payload.agent) {
      agent = agentDisplayName(e.payload.agent);
      role = agentRole(e.payload.agent);
    } else if (t) {
      agent = agentDisplayName(t.current_agent);
      role = agentRole(t.current_agent);
    }

    tbody.appendChild(el("tr", {},
      el("td", { class: "mono faint", text: fmtTime(e.timestamp) }),
      el("td", { style: "font-weight: 500;" }, taskName),
      el("td", { class: "mono", style: "color: var(--brand-burgundy);" }, agent),
      el("td", { class: "badge pend" }, role),
      el("td", {}, e.event_type),
      el("td", { class: "mono faint" }, sum)
    ));
  }

  twrap.appendChild(table);
  feedCard.appendChild(twrap);
  wrap.appendChild(feedCard);
  return wrap;
}
function viewMission() {
  const wrap = el("div", {});
  const opts = [{ value: "", text: "-- Select a Task to view Mission Control --" }].concat(
    state.tasks.map((t) => ({ value: t.id, text: t.title + "  [" + t.status + "]" }))
  );
  const dd = createDropdown(opts, state.selectedTaskId || "", (val) => selectMissionTask(val));
  dd.style.maxWidth = "400px";
  dd.style.marginBottom = "24px";
  wrap.appendChild(dd);

  if (!state.selectedTaskId) {
    wrap.appendChild(el("div", { class: "card empty" }, emptyState("\u2398", "Select a task to open Mission Control.")));
    return wrap;
  }
  
  const t = taskById(state.selectedTaskId);
  if (!t) {
    wrap.appendChild(el("div", { class: "card empty" }, emptyState("\u2398", "Task not found.")));
    return wrap;
  }

  const isTerminal = TERMINAL.indexOf(t.status) !== -1;
  const isActive = ACTIVE_STATES.indexOf(t.status) !== -1;
  const agent = agentDisplayName(t.current_agent);
  const role = agentRole(t.current_agent);

  const grid = el("div", { class: "mc-grid" });

  /* ===== Left Sidebar: Status & Info ===== */
  const left = el("div", { class: "mc-panel" });

  const getLastStateEntryTime = () => {
    if (!state.stateHistory || !state.stateHistory.length) return null;
    return state.stateHistory[state.stateHistory.length - 1].timestamp;
  };

  // Main Status Card
  const currentElapsed = isTerminal ? null : (getLastStateEntryTime() || t.started_at);
  const statCard = el("div", { class: "stat-card" },
    el("div", { class: "stat-label", text: "TASK" }),
    el("div", { style: "font-weight: 600; font-size: 16px; margin-bottom: 8px;", text: t.title }),
    el("div", { class: "stat-label", text: "STATUS" }),
    el("div", { style: "margin-bottom: 8px;" }, statusBadge(t.status)),
    el("div", { class: "stat-label", text: "CURRENT STATE" }),
    el("div", { style: "margin-bottom: 8px; font-weight: 500;" }, [STATUS_META[t.status] ? STATUS_META[t.status].label : t.status]),
    el("div", { class: "stat-label", text: "CURRENT AGENT" }),
    el("div", { class: "mono", style: "font-size: 13px; margin-bottom: 8px; color: var(--brand-burgundy-primary); font-weight: 600;" }, [agent ? (role ? role + ": " : "") + agent : "None"]),
    el("div", { class: "stat-label", text: "MODEL" }),
    el("div", { class: "mono faint", style: "font-size: 13px; margin-bottom: 8px;" }, [state.telemetry.model || "Unavailable"]),
    el("div", { class: "stat-label", text: "STARTED" }),
    el("div", { class: "mono", style: "margin-bottom: 8px;" }, [fmtTime(t.started_at)]),
    el("div", { class: "stat-label", text: "TOTAL ELAPSED" }),
    el("div", { class: "stat-val", style: "margin-bottom: 8px;" }, [liveTimer(t.started_at, null)]),
    el("div", { class: "stat-label", text: "CURRENT STATE ELAPSED" }),
    el("div", { class: "stat-val", style: "margin-bottom: 8px;" }, [liveTimer(currentElapsed, null)]),
    el("div", { class: "stat-label", text: "ITERATION" }),
    el("div", { class: "mono", style: "margin-bottom: 8px;" }, [(t.iteration || 0) + " / " + (t.max_iterations || 0)])
  );
  left.appendChild(statCard);

  // Telemetry Card
  const telCard = el("div", { class: "stat-card" },
    el("div", { class: "stat-label", text: "TOKENS" }),
    state.telemetry.usage ? 
      el("div", { class: "mono", style: "font-size: 13px;" }, [
        `In: ${state.telemetry.usage.input_tokens || 0}`,
        el("br", {}),
        `Out: ${state.telemetry.usage.output_tokens || 0}`,
        el("br", {}),
        `Total: ${state.telemetry.usage.total_tokens || 0}`
      ]) : 
      el("div", { class: "mono faint", style: "font-size: 13px;" }, ["Unavailable from provider"]),
    el("div", { class: "stat-label", style: "margin-top: 12px;", text: "LATEST EVENT" }),
    el("div", { style: "font-size: 13px; color: var(--text-secondary);" }, [state.taskEvents.length ? esc(state.taskEvents[state.taskEvents.length-1].event_type) : "No events"])
  );
  left.appendChild(telCard);
  
  grid.appendChild(left);

  /* ===== Right Side: State Timeline & Actions ===== */
  const right = el("div", { class: "mc-panel" });
  
  const tlCard = el("div", { class: "card pad-0" },
    el("div", { class: "card-head" }, el("h3", { text: "State Timeline" }))
  );
  const tlBody = el("div", { class: "card-body timeline" });

  const stateTimes = {};
  for (let i = 0; i < state.stateHistory.length; i++) {
    const s = state.stateHistory[i];
    const n = state.stateHistory[i+1];
    const sName = s.payload ? s.payload.new_state : "UNKNOWN";
    const start = new Date(s.timestamp).getTime() / 1000;
    const end = n ? new Date(n.timestamp).getTime() / 1000 : Date.now() / 1000;
    if (!stateTimes[sName]) stateTimes[sName] = 0;
    stateTimes[sName] += (end - start);
  }

  let passedActive = false;
  for (const s of STAGES) {
    const isCurrent = s === t.status;
    const hasBeen = stateTimes[s] !== undefined || (s === "PENDING" && t.started_at);
    if (isCurrent) passedActive = true;
    
    let tlClass = "tl-item ";
    let icon = "\u25CB"; // Empty circle
    if (hasBeen && !isCurrent && !passedActive) {
      tlClass += "done";
      icon = "\u2713"; // Checkmark
    } else if (isCurrent) {
      tlClass += "active";
      icon = "\u25CF"; // Filled circle
    } else {
      tlClass += "pending";
    }
    
    const labelStr = STATUS_META[s] ? STATUS_META[s].label : s;
    const durStr = (stateTimes[s] || isCurrent) ? (isCurrent && isActive ? liveTimer(currentElapsed, null, true) : el("span", { text: dur(stateTimes[s]) })) : null;
    
    tlBody.appendChild(el("div", { class: tlClass },
      el("div", { class: "tl-icon", text: icon }),
      el("div", { class: "tl-label", text: labelStr }),
      el("div", { class: "tl-dur" }, [durStr])
    ));
  }

  tlCard.appendChild(tlBody);
  
  if (t.status === "FAILED" && t.error_information) {
    tlCard.appendChild(
      el("div", { class: "card-body", style: "border-top: 1px solid rgba(182, 79, 79, 0.2); background: rgba(182, 79, 79, 0.05);" },
        el("h4", { style: "color: var(--err); margin: 0 0 8px 0;" }, "Failure Reason"),
        el("div", { class: "mono", style: "color: var(--err); font-size: 13px; white-space: pre-wrap; word-break: break-all;" }, t.error_information)
      )
    );
  }
  
  right.appendChild(tlCard);

  // Quick Action Buttons
  const actCard = el("div", { class: "card" },
    el("div", { class: "flex" },
      (!isTerminal && t.status !== "PAUSED" && t.status !== "PENDING") ? el("button", { class: "btn danger", text: "Stop Task", onclick: () => api(`/tasks/${t.id}/stop`, { method: "POST" }).then(refresh) }) : null,
      (t.status === "PENDING") ? el("button", { class: "btn primary", text: "Start Task", onclick: () => api(`/tasks/${t.id}/start`, { method: "POST" }).then(refresh) }) : null
    )
  );
  right.appendChild(actCard);

  grid.appendChild(right);
  wrap.appendChild(grid);
  
  return wrap;
}
function viewSettings() {
  const wrap = el("div", {});
  
  // Ensure state variables exist
  state.roles = state.roles || {};
  state.providers = state.providers || [];
  
  // Create sections: GENERAL, AGENT ROUTING, PROVIDERS, TELEMETRY, WORKSPACE, SECURITY, DANGER ZONE
  
  // --- AGENT ROUTING ---
  const routeCard = el("div", { class: "mb" },
    el("h3", { text: "Agent Routing", style: "margin-bottom: 16px; color: var(--brand-burgundy-deep);" }),
    el("div", { class: "grid-3" })
  );
  const routeGrid = routeCard.querySelector(".grid-3");
  
  const rolenames = {
    "orchestrator": "AI ORCHESTRATOR",
    "investigator": "INVESTIGATOR",
    "coder": "CODER / IMPLEMENTER",
    "tester": "TESTER",
    "qa": "QA",
    "reviewer": "REVIEWER"
  };
  
  for (const [rkey, rtitle] of Object.entries(rolenames)) {
    const rc = state.roles[rkey] || { provider: "agy", model: "default" };
    const p = state.providers.find(x => x.id === rc.provider) || { display_name: "Unknown", status: "Unavailable", models: [] };
    
    const provSel = el("select", { onchange: (e) => updateRole(rkey, e.target.value, "default") });
    for (const pr of state.providers) {
      if ((pr.supported_roles || []).includes(rkey)) {
        provSel.appendChild(el("option", { value: pr.id, text: pr.display_name, selected: pr.id === rc.provider ? "selected" : null }));
      }
    }
    
    const modSel = el("select", { onchange: (e) => updateRole(rkey, rc.provider, e.target.value) });
    for (const m of (p.models || [])) {
      modSel.appendChild(el("option", { value: m.id, text: m.name, selected: m.id === rc.model ? "selected" : null }));
    }
    
    const card = el("div", { class: "card pad-0", style: "display: flex; flex-direction: column;" },
      el("div", { class: "card-head", style: "background: rgba(244, 162, 97, 0.05);" }, el("h4", { text: rtitle, style: "margin:0; font-size:13px; color: var(--brand-burgundy-primary);" })),
      el("div", { class: "card-body", style: "flex: 1; display: flex; flex-direction: column; gap: 12px;" },
        el("div", { class: "field", style: "margin:0" }, el("label", { text: "Provider" }), provSel),
        el("div", { class: "field", style: "margin:0" }, el("label", { text: "Model" }), modSel),
        el("div", { class: "flex", style: "margin-top: auto; padding-top: 8px;" },
          el("div", { class: "dot " + (p.status === "Connected" ? "ok" : "err") }),
          el("span", { class: "faint", style: "font-size:12px", text: "Status: " + p.status })
        )
      )
    );
    routeGrid.appendChild(card);
  }
  wrap.appendChild(routeCard);

  // --- PROVIDERS ---
  const provWrap = el("div", { class: "mb" },
    el("h3", { text: "Providers", style: "margin-bottom: 16px; color: var(--brand-burgundy-deep);" })
  );
  for (const p of state.providers) {
    const isDesktop = p.id === "agy_desktop";
    
    provWrap.appendChild(el("div", { class: "card flex", style: "justify-content: space-between; margin-bottom: 12px;" },
      el("div", {},
        el("div", { style: "font-weight: 600; font-size: 15px; margin-bottom: 4px;" }, p.display_name),
        el("div", { class: "faint", style: "font-size: 13px;" }, "Supported roles: " + (p.supported_roles || []).join(", "))
      ),
      el("div", { class: "flex", style: "gap: 16px;" },
        isDesktop ? el("button", { 
          class: "btn sm ghost", 
          text: "Test Connection", 
          onclick: () => {
            toast("Testing RPA Connection...", "info");
            api("/providers/test-desktop", {method: "POST"})
              .then(res => {
                 if (res.status === "success") {
                    toast(res.message, "ok");
                 } else {
                    openModal("RPA Connection Failed", 
                      el("div", {},
                        el("p", { text: "ForgeFlow could not connect to the Antigravity Desktop app. Please make sure it is open and running." }),
                        el("div", { class: "mono", style: "color: var(--err); font-size: 13px; white-space: pre-wrap; background: var(--bg); padding: 12px; border: 1px solid rgba(182, 79, 79, 0.3); border-radius: 4px; overflow-y: auto; max-height: 400px; margin-top: 12px;" }, res.message + (res.details ? "\n\n" + res.details : ""))
                      ),
                      [el("button", { class: "btn primary", text: "Close", onclick: closeModal })],
                      true
                    );
                 }
              })
              .catch(e => {
                  openModal("RPA Network Error", el("p", { text: e.message }), [el("button", { class: "btn primary", text: "Close", onclick: closeModal })]);
              });
          }
        }) : null,
        el("div", { class: "flex" },
          el("div", { class: "dot " + (p.status === "Connected" ? "ok" : (p.status === "RPA Ready" ? "warn" : "err")) }),
          el("span", { style: "font-weight: 500;", text: p.status })
        )
      )
    ));
  }
  wrap.appendChild(provWrap);

  
  
    // --- API KEYS ---
    const apiWrap = el("div", { class: "mb mt" },
      el("h3", { text: "API Keys & Integrations", style: "margin-bottom: 16px; color: var(--heading-color);" }),
      el("div", { class: "card pad-0" },
        el("div", { class: "card-body", style: "display: flex; flex-direction: column; gap: 16px;" },
          el("div", { class: "field", style: "margin:0" },
            el("label", { text: "OpenAI API Key" }),
            el("input", { type: "password", placeholder: "sk-...", value: "" })
          ),
          el("div", { class: "field", style: "margin:0" },
            el("label", { text: "Anthropic API Key" }),
            el("input", { type: "password", placeholder: "sk-ant-...", value: "" })
          ),
          el("div", { class: "field", style: "margin:0" },
            el("label", { text: "Abacus API Key" }),
            el("input", { type: "password", placeholder: "abacus-...", value: "" })
          ),
          el("div", { style: "display: flex; justify-content: flex-end; align-items: center; gap: 16px; margin-top: 8px;" },
            el("button", { class: "btn ghost", text: "+ Add Custom Provider", onclick: promptAddProvider }),
            el("button", { class: "btn primary", text: "Save Keys", onclick: () => toast("API Keys securely saved", "ok") })
          )
        )
      )
    );
    wrap.appendChild(apiWrap);
    
    // --- TELEMETRY & BILLING ---
    const billWrap = el("div", { class: "mb mt" });
    billWrap.appendChild(el("h3", { text: "Telemetry & Billing", style: "margin-bottom: 16px; color: var(--heading-color);" }));
    
    const billingGrid = el("div", { style: "display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px;" });
    
    const billingUrls = {
      "abacus": "https://abacus.ai/billing",
      "agy": "https://aistudio.google.com/app/billing",
      "openai": "https://platform.openai.com/billing",
      "anthropic": "https://console.anthropic.com/settings/billing"
    };

    const activeProviders = state.providers || [];
    
    // Add default keys if they exist in config but aren't fully registered in providers yet
    const configKeys = Object.keys(state.config || {});
    if (!activeProviders.find(p => p.id === 'openai') && configKeys.includes('openai_api_key')) activeProviders.push({id: 'openai', display_name: 'OpenAI'});
    if (!activeProviders.find(p => p.id === 'anthropic') && configKeys.includes('anthropic_api_key')) activeProviders.push({id: 'anthropic', display_name: 'Anthropic'});

    for (const p of activeProviders) {
      const pId = p.id.toLowerCase();
      const url = billingUrls[pId] || "#";
      
      const pCard = el("div", { class: "card pad-0", style: "display: flex; flex-direction: column;" },
        el("div", { class: "card-head", style: "background: rgba(244, 162, 97, 0.05); display: flex; justify-content: space-between; align-items: center;" },
          el("h4", { text: p.display_name + " Account", style: "margin:0; font-size:13px; color: var(--brand-burgundy-primary);" }),
          el("span", { class: "badge ok", style: "font-size: 10px;", text: p.status || "Connected" })
        ),
        el("div", { class: "card-body", style: "flex: 1; display: flex; flex-direction: column; gap: 12px; padding: 16px;" },
          el("div", { style: "display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-warm); padding: 8px 0;" },
            el("span", { class: "faint", style: "font-weight: 500;", text: "Estimated Usage" }),
            el("span", { style: "font-family: monospace; color: var(--brand-burgundy-primary); font-weight: 600;", text: (state.telemetry && state.telemetry.providers && state.telemetry.providers[pId]) ? state.telemetry.providers[pId].estimated_cost : "$0.00" })
          ),
          el("div", { style: "display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-warm); padding: 8px 0;" },
            el("span", { class: "faint", style: "font-weight: 500;", text: "Tokens Analyzed" }),
            el("span", { style: "font-family: monospace;", text: (state.telemetry && state.telemetry.providers && state.telemetry.providers[pId]) ? String(state.telemetry.providers[pId].input_tokens + state.telemetry.providers[pId].output_tokens) : "0" })
          ),
          el("div", { class: "mt", style: "display: flex; justify-content: center;" },
            url !== "#" ? 
              el("a", { class: "btn ghost", style: "text-decoration: none; font-size: 12px;", href: url, target: "_blank", text: "↗ Open Billing Dashboard" }) :
              el("span", { class: "faint", style: "font-size: 11px; font-style: italic;", text: "Provider dashboard unknown" })
          )
        )
      );
      billingGrid.appendChild(pCard);
    }
    
    if (activeProviders.length === 0) {
      billingGrid.appendChild(el("div", { class: "faint", text: "No active providers connected." }));
    }
    
    billWrap.appendChild(billingGrid);
    wrap.appendChild(billWrap);
    // --- CONFIGURATION ---
  const cfg = state.config || {};
  const genCard = el("div", { class: "card mb pad-0" }, el("div", { class: "card-head" }, el("h3", { text: "System Configuration" })));
  const genB = el("div", { class: "card-body" });
  
  const keys = Object.keys(cfg).sort();
  for (const k of keys) {
    const v = cfg[k];
    let node;
    if (typeof v === "boolean") {
      node = el("span", { class: "badge " + (v ? "done" : "pend"), text: v ? "true" : "false" });
    } else if (v === null || v === undefined) {
      node = el("span", { class: "faint", text: "-" });
    } else {
      node = el("span", { class: "mono faint", style: "font-size: 13px;", text: String(v) });
    }
    const row = el("div", { style: "display: flex; padding: 8px 0; border-bottom: 1px solid var(--border-warm);" }, 
      el("div", { class: "mono", style: "width: 300px; font-size: 13px; font-weight: 600; color: var(--text-main);" }, k), 
      el("div", { class: "v" }, [node])
    );
    genB.appendChild(row);
  }
  genCard.appendChild(genB);
  wrap.appendChild(genCard);

// --- DANGER ZONE ---
  const dz = el("div", { class: "danger-zone mt" },
    el("h3", { text: "Danger Zone" }),
    el("div", { class: "danger-row" },
      el("div", { class: "info" },
        el("h4", { text: "Clear Task Data" }),
        el("p", { text: "Start a completely fresh ForgeFlow task history. Removes task records, events, artifacts, and temporary worktrees. Preserves source code and registered projects." })
      ),
      el("button", { class: "btn danger", text: "Clear Task Data", onclick: promptClearTaskData })
    ),
    el("div", { class: "danger-row" },
      el("div", { class: "info" },
        el("h4", { text: "Reset Configuration" }),
        el("p", { text: "Restore ForgeFlow runtime configuration to documented defaults. Does not delete repositories." })
      ),
      el("button", { class: "btn danger", text: "Reset Configuration", onclick: promptResetConfig })
    )
  );
  wrap.appendChild(dz);

  return wrap;
}

async function updateRole(role, provider, model) {
  if (provider === "agy_desktop") {
    toast("Verifying Desktop RPA connection...", "info");
    try {
      const res = await api("/providers/test-desktop", { method: "POST" });
      if (res.status !== "success") {
        openModal("RPA Connection Failed", 
          el("div", {},
            el("p", { text: "ForgeFlow could not connect to the Antigravity Desktop app. Please make sure it is open and running." }),
            el("div", { class: "mono", style: "color: var(--err); font-size: 13px; white-space: pre-wrap; background: var(--bg); padding: 12px; border: 1px solid rgba(182, 79, 79, 0.3); border-radius: 4px; overflow-y: auto; max-height: 400px; margin-top: 12px;" }, res.message + (res.details ? "\n\n" + res.details : ""))
          ),
          [el("button", { class: "btn primary", text: "Close", onclick: closeModal })],
          true
        );
        render(); // Revert dropdown visually
        return;
      }
      toast("RPA Connection Verified!", "ok");
    } catch (e) {
      openModal("RPA Network Error", el("p", { text: e.message }), [el("button", { class: "btn primary", text: "Close", onclick: closeModal })]);
      render();
      return;
    }
  }

  try {
    await api(`/settings/roles/${role}`, { method: "PUT", body: { provider, model } });
    toast("Role updated", "ok");
    refresh();
  } catch (e) {
    toast(e.message, "err");
  }
}
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


  /* ---------- settings actions ---------- */
  function promptClearTaskData() {
    openModal("Clear Task Data",
      el("p", { text: "Are you sure? This will delete all tasks, events, and artifacts." }),
      [
        el("button", { class: "btn ghost", text: "Cancel", onclick: closeModal }),
        el("button", { class: "btn danger", text: "Clear Data", onclick: async () => {
          try {
            await api("/settings/reset-data", { method: "POST" });
            toast("Task data cleared", "ok");
            closeModal();
            loadAll();
          } catch (e) { toast(e.message, "err"); }
        }})
      ]
    );
  }

  function promptResetConfig() {
    openModal("Reset Configuration",
      el("p", { text: "Are you sure? This will restore the default runtime configuration." }),
      [
        el("button", { class: "btn ghost", text: "Cancel", onclick: closeModal }),
        el("button", { class: "btn danger", text: "Reset Config", onclick: async () => {
          try {
            await api("/settings/reset-config", { method: "POST" });
            toast("Configuration reset", "ok");
            closeModal();
            loadAll();
          } catch (e) { toast(e.message, "err"); }
        }})
      ]
    );
  }


  
  function promptAddProvider() {
    let pid, pname, proles, pmodels;
    
    openModal("Add Custom Provider",
      el("div", { style: "display: flex; flex-direction: column; gap: 12px;" },
        el("div", { class: "field", style: "margin:0" },
          el("label", { text: "Provider ID (e.g. openai)" }),
          pid = el("input", { type: "text", placeholder: "openai" })
        ),
        el("div", { class: "field", style: "margin:0" },
          el("label", { text: "Display Name (e.g. OpenAI)" }),
          pname = el("input", { type: "text", placeholder: "OpenAI" })
        ),
        el("div", { class: "field", style: "margin:0" },
          el("label", { text: "Supported Roles (comma separated)" }),
          proles = el("input", { type: "text", placeholder: "coder, reviewer, orchestrator" })
        ),
        el("div", { class: "field", style: "margin:0" },
          el("label", { text: "Models (comma separated)" }),
          pmodels = el("input", { type: "text", placeholder: "gpt-4o, gpt-3.5-turbo" })
        )
      ),
      [
        el("button", { class: "btn ghost", text: "Cancel", onclick: closeModal }),
        el("button", { class: "btn primary", text: "Add Provider", onclick: async () => {
          const id = pid.value.trim();
          const name = pname.value.trim();
          const roles = proles.value.split(",").map(s => s.trim()).filter(Boolean);
          const models = pmodels.value.split(",").map(s => s.trim()).filter(Boolean).map(m => ({ id: m, name: m }));
          
          if (!id || !name || !roles.length || !models.length) {
            toast("Please fill all fields", "err");
            return;
          }
          
          try {
            await api("/providers/custom", {
              method: "POST",
              body: {
                id: id,
                display_name: name,
                status: "Connected",
                supported_roles: roles,
                models: models
              }
            });
            toast("Custom provider added", "ok");
            closeModal();
            loadAll();
          } catch (e) { toast(e.message, "err"); }
        }})
      ]
    );
  }

  /* ---------- actions ---------- */

  async function selectMissionTask(taskId) {
    state.selectedTaskId = taskId;
    if (!taskId) {
      state.taskEvents = [];
      state.taskArtifacts = [];
      render();
      return;
    }
    try {
      const r = await Promise.all([
        api("/tasks/" + taskId + "/events").catch(() => []),
        api("/tasks/" + taskId + "/artifacts").catch(() => [])
      ]);
      state.taskEvents = r[0] || [];
      state.taskArtifacts = r[1] || [];
      state.stateHistory = state.taskEvents.filter(e => e.event_type === "STATE_CHANGED");
    } catch (_) {}
    render();
  }

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



/* ---------- Custom Select Component ---------- */
function createDropdown(options, selectedValue, onChange) {
  const wrap = document.createElement("div");
  wrap.className = "custom-select";
  let currentVal = selectedValue;
  
  const selectedDisplay = document.createElement("div");
  selectedDisplay.className = "cs-display";
  const selectedText = document.createElement("span");
  selectedText.className = "cs-text";
  const icon = document.createElement("span");
  icon.className = "cs-icon";
  icon.innerHTML = "&#9662;";
  selectedDisplay.appendChild(selectedText);
  selectedDisplay.appendChild(icon);
  
  const menu = document.createElement("div");
  menu.className = "cs-menu";
  
  // Add Search Input if options are many
  let searchInput = null;
  if (options.length > 5) {
    const searchWrap = document.createElement("div");
    searchWrap.style.padding = "8px";
    searchWrap.style.borderBottom = "1px solid var(--border-warm)";
    
    searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.placeholder = "Search...";
    searchInput.className = "search";
    searchInput.style.width = "100%";
    searchInput.style.padding = "6px 10px";
    searchInput.style.borderRadius = "4px";
    searchInput.style.border = "1px solid var(--border-warm)";
    searchInput.style.background = "var(--input-bg)";
    searchInput.style.color = "var(--text-main)";
    
    searchInput.onclick = (e) => e.stopPropagation();
    searchInput.oninput = () => {
      const q = searchInput.value.toLowerCase();
      Array.from(menu.querySelectorAll(".cs-option")).forEach(opt => {
        if (opt.innerText.toLowerCase().includes(q)) opt.style.display = "";
        else opt.style.display = "none";
      });
    };
    
    searchWrap.appendChild(searchInput);
    menu.appendChild(searchWrap);
  }
  
  const updateDisplay = () => {
    const opt = options.find(o => o.value === currentVal) || options[0];
    selectedText.innerText = opt ? opt.text : "";
  };
  
  for (const opt of options) {
    const item = document.createElement("div");
    item.className = "cs-option";
    item.innerText = opt.text;
    if (opt.value === currentVal) item.classList.add("active");
    
    item.onclick = (e) => {
      e.stopPropagation();
      currentVal = opt.value;
      updateDisplay();
      wrap.classList.remove("open");
      Array.from(menu.querySelectorAll(".cs-option")).forEach(c => c.classList.remove("active"));
      item.classList.add("active");
      if (searchInput) { searchInput.value = ""; searchInput.dispatchEvent(new Event('input')); }
      if (onChange) onChange(currentVal);
    };
    menu.appendChild(item);
  }
  
  updateDisplay();
  
  selectedDisplay.onclick = (e) => {
    e.stopPropagation();
    const wasOpen = wrap.classList.contains("open");
    document.querySelectorAll(".custom-select.open").forEach(c => {
      if (c !== wrap) c.classList.remove("open");
    });
    wrap.classList.toggle("open");
    if (!wasOpen && searchInput) {
      setTimeout(() => searchInput.focus(), 50);
    }
  };
  
  wrap.appendChild(selectedDisplay);
  wrap.appendChild(menu);
  return wrap;
}

document.addEventListener("click", () => {
  document.querySelectorAll(".custom-select.open").forEach(c => c.classList.remove("open"));
});

/* ---------- Theme ---------- */
function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("forgeflow-theme", next);
}

document.addEventListener("DOMContentLoaded", () => {
  const saved = localStorage.getItem("forgeflow-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  
  // Create iOS-style theme switch in topbar
  const tb = document.querySelector(".topbar");
  if (tb) {
    const wrap = document.createElement("div");
    wrap.className = "theme-switch-wrapper";
    wrap.title = "Toggle Dark Mode";
    
    const iconSun = document.createElement("span");
    iconSun.className = "theme-icon theme-sun";
    iconSun.innerHTML = "&#9728;"; // sun icon
    
    const label = document.createElement("label");
    label.className = "theme-switch";
    
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = (document.documentElement.getAttribute("data-theme") === "dark");
    cb.addEventListener("change", (e) => {
      const next = e.target.checked ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("forgeflow-theme", next);
    });
    
    const slider = document.createElement("span");
    slider.className = "slider";
    
    const iconMoon = document.createElement("span");
    iconMoon.className = "theme-icon theme-moon";
    iconMoon.innerHTML = "&#9789;"; // moon icon
    
    label.appendChild(cb);
    label.appendChild(slider);
    
    wrap.appendChild(iconSun);
    wrap.appendChild(label);
    wrap.appendChild(iconMoon);
    tb.appendChild(wrap);

    // Create restart button
    const restartBtn = document.createElement("button");
    restartBtn.className = "btn sm ghost";
    restartBtn.style.marginLeft = "12px";
    restartBtn.style.padding = "4px 8px";
    restartBtn.style.fontSize = "16px";
    restartBtn.title = "Restart Server";
    restartBtn.innerHTML = "&#x21bb;"; // refresh/restart icon
    restartBtn.onclick = async () => {
      try {
        toast("Restarting server...", "ok");
        await api("/system/restart", { method: "POST" });
        setTimeout(() => window.location.reload(), 2000);
      } catch (e) {}
    };
    
    tb.appendChild(restartBtn);
  }
});
