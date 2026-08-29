/* Agent Atlas dashboard — talks to the FastAPI service. */
let selected = null;

const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

function statusClass(s) { return "st-" + (s || "PENDING"); }

async function loadTasks() {
  try {
    const { tasks } = await api("/api/tasks");
    const list = $("taskList");
    if (!tasks.length) {
      list.innerHTML = '<p class="empty">No tasks yet — submit one above.</p>';
      return;
    }
    list.innerHTML = "";
    for (const t of tasks) {
      const el = document.createElement("div");
      el.className = "task";
      el.innerHTML = `
        <div>
          <div class="t-title">${esc(t.title)}</div>
          <div class="t-meta">${esc(t.id)} · step ${t.current_step}/${t.total_steps} · ${esc(t.updated_at || "")}</div>
        </div>
        <div class="t-status ${statusClass(t.status)}">${esc(t.status)}</div>`;
      el.onclick = () => selectTask(t.id);
      list.appendChild(el);
    }
    if (selected) selectTask(selected);
  } catch (e) {
    $("taskList").innerHTML = `<p class="empty">Error loading tasks: ${esc(e.message)}</p>`;
  }
}

async function selectTask(id) {
  selected = id;
  const d = await api("/api/tasks/" + id);
  const { task, plan, events } = d;
  $("detail").hidden = false;
  $("dTitle").textContent = task.title;
  const st = $("dStatus");
  st.textContent = task.status;
  st.className = "statuschip " + statusClass(task.status);
  $("dGoal").textContent = task.goal;
  if (task.result) $("dGoal").textContent += "\n\n✓ " + task.result;

  const ol = $("dPlan");
  ol.innerHTML = "";
  plan.forEach((p, i) => {
    const li = document.createElement("li");
    li.textContent = `[${p.kind}] ${p.title}`;
    const s = (p.status || "PENDING").toUpperCase();
    if (s === "DONE") li.className = "done";
    else if (s === "IN_PROGRESS" || i === task.current_step) li.className = "active";
    else if (s === "BLOCKED") li.className = "blocked";
    ol.appendChild(li);
  });

  const ul = $("dEvents");
  ul.innerHTML = "";
  [...events].reverse().slice(0, 60).forEach((ev) => {
    const li = document.createElement("li");
    if (ev.kind === "agent" && ev.payload) {
      const p = ev.payload;
      const calls = (p.function_calls || []).map((c) => `⚙ ${c.name}(${JSON.stringify(c.args || {}).slice(0, 120)})`).join("\n");
      li.innerHTML = `<span class="call">${esc(calls)}</span>` +
        (p.text ? `<span class="text">${esc(p.text.slice(0, 500))}</span>` : "");
    } else if (ev.kind === "plan") {
      li.textContent = `📋 Planned ${ev.payload?.steps} steps`;
    } else if (ev.kind === "error") {
      li.innerHTML = `<span class="call">✖ ${esc(ev.payload?.message || "")}</span>`;
    } else {
      li.textContent = `(${ev.kind}) ${esc(JSON.stringify(ev.payload || {}).slice(0, 200))}`;
    }
    ul.appendChild(li);
  });
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function submitGoal(text) {
  $("submitMsg").textContent = "Planning…";
  try {
    const r = await api("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ goal: text }),
    });
    $("submitMsg").textContent = `Queued ${r.task_id} with ${r.plan.length} steps.`;
    $("goal").value = "";
    await loadTasks();
  } catch (e) {
    $("submitMsg").textContent = "Error: " + e.message;
  }
}

$("submit").onclick = () => submitGoal($("goal").value);
$("refresh").onclick = loadTasks;
$("runNow").onclick = async () => {
  if (!selected) return;
  await api(`/api/tasks/${selected}/run`, { method: "POST" });
  setTimeout(loadTasks, 1500);
};
$("sendMsg").onclick = async () => {
  const m = $("msg").value.trim();
  if (!selected || !m) return;
  await api(`/api/tasks/${selected}/message`, {
    method: "POST",
    body: JSON.stringify({ message: m }),
  });
  $("msg").value = "";
  setTimeout(loadTasks, 1500);
};
document.querySelectorAll(".example").forEach((b) => {
  b.onclick = () => {
    $("goal").value = b.textContent.replace(/^[^ ]+ /, "");
  };
});

async function boot() {
  try {
    const h = await api("/healthz");
    const chip = $("health");
    chip.textContent = `● ${h.model} · ${h.store}`;
    chip.className = "statuschip ok";
  } catch (e) {
    $("health").textContent = "● offline";
  }
  await loadTasks();
  setInterval(loadTasks, 4000);
}
boot();