/* Agent Atlas console — talks to the FastAPI service. */
"use strict";

const $ = (id) => document.getElementById(id);
let selected = null;

// API base: same origin by default; override in web/config.js to point this
// static dashboard at a deployed backend (e.g. a Cloud Run URL).
const API_BASE = (window.ATLAS_CONFIG && window.ATLAS_CONFIG.apiBase) || "";
const apiUrl = (path) => API_BASE + path;

async function api(path, opts = {}) {
  const res = await fetch(apiUrl(path), {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
  return res.json();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function fmtTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch {
    return iso;
  }
}

/* ---- tasks table ---- */
async function loadTasks() {
  try {
    const { tasks } = await api("/api/tasks");
    $("taskCount").textContent = tasks.length ? `${tasks.length} task${tasks.length === 1 ? "" : "s"}` : "";
    const tbody = $("taskBody");
    tbody.innerHTML = "";
    if (!tasks.length) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="5" class="empty">No tasks yet — submit one above.</td></tr>';
      return;
    }
    for (const t of tasks) {
      const tr = document.createElement("tr");
      tr.className = "clickable" + (selected === t.id ? " selected" : "");
      tr.innerHTML = `
        <td>
          <div class="t-title">${esc(t.title)}</div>
          <div class="t-goal">${esc(t.goal)}</div>
        </td>
        <td class="col-num">${t.current_step}/${t.total_steps}</td>
        <td class="col-num">${t.attempts}</td>
        <td><span class="pill st-${esc(t.status)}">${esc(t.status)}</span></td>
        <td class="col-time"><span class="t-time">${esc(fmtTime(t.updated_at))}</span></td>`;
      tr.addEventListener("click", () => selectTask(t.id));
      tbody.appendChild(tr);
    }
    if (selected) selectTask(selected);
  } catch (e) {
    $("taskBody").innerHTML = `<tr class="empty-row"><td colspan="5" class="empty">Failed to load tasks: ${esc(e.message)}</td></tr>`;
  }
}

/* ---- detail panel ---- */
async function selectTask(id) {
  selected = id;
  const { task, plan, events } = await api(`/api/tasks/${id}`);
  const detail = $("detail");
  detail.hidden = false;

  $("dTitle").textContent = task.title;
  $("dGoal").textContent = task.goal;
  const status = $("dStatus");
  status.textContent = task.status;
  status.className = "pill st-" + esc(task.status);

  const total = Math.max(task.total_steps, plan.length, 1);
  const done = Math.min(task.current_step, total);
  $("dProgress").style.width = `${Math.round((done / total) * 100)}%`;
  $("dProgressLabel").textContent = `${done} of ${total} steps`;

  const ol = $("dPlan");
  ol.innerHTML = "";
  plan.forEach((p, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="step-kind">${esc(p.kind)}</span> ${esc(p.title)}`;
    const s = (p.status || "PENDING").toUpperCase();
    if (s === "DONE") li.className = "done";
    else if (s === "BLOCKED") li.className = "blocked";
    else if (s === "IN_PROGRESS" || i === task.current_step) li.className = "active";
    ol.appendChild(li);
  });

  $("dResult").textContent = task.result || "";

  renderLog(events);
}

function renderLog(events) {
  const log = $("dEvents");
  log.innerHTML = "";
  if (!events.length) {
    log.innerHTML = '<div class="log-empty">No events yet. Submit a task and run a turn to see the agent work.</div>';
    return;
  }
  // newest first, capped
  [...events].slice(-200).reverse().forEach((ev) => {
    const line = document.createElement("div");
    line.className = "log-line";
    if (ev.kind === "agent" && ev.payload) {
      const p = ev.payload;
      const parts = [];
      (p.function_calls || []).forEach((c) => {
        parts.push(`<span class="kind kind-tool">CALL</span><span class="log-call">${esc(c.name)}</span>`);
        const args = JSON.stringify(c.args || {});
        if (args && args !== "{}") parts.push(`<span class="log-args">(${esc(args.slice(0, 200))})</span>`);
      });
      if (p.text) {
        parts.push(`<span class="kind kind-text">TEXT</span>${esc(p.text.slice(0, 600))}`);
      }
      if (!parts.length) return;
      line.innerHTML = `<span class="log-time">${esc(fmtTime(ev.ts))}</span> ${parts.join(" ")}`;
    } else if (ev.kind === "plan") {
      line.innerHTML = `<span class="kind kind-plan">PLAN</span>${esc(ev.payload?.steps || "")} steps`;
    } else if (ev.kind === "error") {
      line.innerHTML = `<span class="kind kind-error">ERROR</span>${esc(ev.payload?.message || "")}`;
    } else {
      line.innerHTML = `<span class="kind kind-event">${esc(ev.kind.toUpperCase())}</span>${esc(JSON.stringify(ev.payload ?? {}).slice(0, 200))}`;
    }
    log.appendChild(line);
  });
}

/* ---- actions ---- */
$("goalForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("goal").value.trim();
  if (!text) return;
  const msg = $("formMsg");
  msg.textContent = "Planning…";
  msg.className = "form-msg";
  try {
    const r = await api("/api/tasks", { method: "POST", body: JSON.stringify({ goal: text }) });
    msg.textContent = `Queued ${r.task_id} (${r.plan.length} steps).`;
    $("goal").value = "";
    await loadTasks();
  } catch (err) {
    msg.textContent = `Error: ${err.message}`;
    msg.className = "form-msg error";
  }
});

document.querySelectorAll("[data-goal]").forEach((btn) => {
  btn.addEventListener("click", () => { $("goal").value = btn.dataset.goal; $("goal").focus(); });
});

$("refresh").addEventListener("click", loadTasks);

$("runNow").addEventListener("click", async () => {
  if (!selected) return;
  await api(`/api/tasks/${selected}/run`, { method: "POST" });
  await loadTasks();
});

$("steerForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const m = $("msg").value.trim();
  if (!selected || !m) return;
  await api(`/api/tasks/${selected}/message`, { method: "POST", body: JSON.stringify({ message: m }) });
  $("msg").value = "";
  await loadTasks();
});

/* ---- boot ---- */
async function boot() {
  try {
    const h = await api("/healthz");
    const el = $("health");
    el.textContent = `${h.model} · ${h.store} backend`;
    el.className = "health ok";
  } catch {
    $("health").textContent = "offline";
    const host = location.hostname;
    const isDev = host === "localhost" || host === "127.0.0.1";
    if (API_BASE || !isDev) {
      $("backendNotice").hidden = false;
    }
  }
  await loadTasks();
  setInterval(loadTasks, 5000);
}
boot();
