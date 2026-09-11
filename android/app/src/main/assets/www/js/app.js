/* Grok Org OS 2.0 — full-power desk UI */
(() => {
  const state = {
    org: null,
    teams: [],
    agents: [],
    channels: [],
    channel: null,
    messages: [],
    tasks: [],
    approvals: [],
    routines: [],
    connectors: [],
    agentStatus: {},
    selectedAgent: null,
    replyTo: null,
    pollTimer: null,
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => [...document.querySelectorAll(sel)];

  function toast(msg, type = "") {
    const el = $("#toast");
    el.textContent = msg;
    el.className = `toast ${type}`;
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.add("hidden"), 3200);
  }

  async function api(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (!(opts.body instanceof FormData)) {
      headers["Content-Type"] = headers["Content-Type"] || "application/json";
    }
    const res = await fetch(path, { ...opts, headers });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        detail = j.detail || JSON.stringify(j);
      } catch (_) {}
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res;
  }

  function roleClass(agent) {
    if (!agent) return "specialist";
    if (agent.role === "ceo") return "ceo";
    if (agent.role === "chief_of_staff") return "chief_of_staff";
    const name = (agent.name || "").toLowerCase();
    if (name.includes("ops")) return "ops";
    if (name.includes("research")) return "research";
    if (name.includes("comms")) return "comms";
    return "specialist";
  }

  function roleLabel(role) {
    return ({ ceo: "CEO", chief_of_staff: "Chief of Staff", specialist: "Specialist" })[role] || role;
  }

  function agentById(id) {
    return state.agents.find((a) => a.id === id);
  }

  function teamById(id) {
    return state.teams.find((t) => t.id === id);
  }

  function formatTime(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "";
    }
  }

  function initials(name) {
    return (name || "?")
      .split(/\s+/)
      .map((p) => p[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadSettingsBadge() {
    try {
      const s = await api("/api/config");
      const badge = $("#llm-badge");
      if (s.has_llm_key) {
        badge.textContent = `Live · ${s.openai_model}`;
        badge.classList.add("live");
      } else {
        badge.textContent = "Mock LLM";
        badge.classList.remove("live");
      }
      $("#cfg-base").value = s.openai_base_url || "";
      $("#cfg-model").value = s.openai_model || "";
      $("#cfg-key").value = "";
      $("#cfg-key").placeholder = s.api_key_set
        ? "•••••••• (saved — leave blank to keep)"
        : "sk-… (required for full power)";
    } catch (e) {
      console.warn(e);
    }
  }

  async function refreshAll() {
    const orgs = await api("/api/orgs");
    if (!orgs.length) {
      await api("/api/bootstrap", { method: "POST", body: "{}" });
      return refreshAll();
    }
    state.org = orgs[0];
    const oid = state.org.id;
    const [teams, agents, channels, tasks, approvals, statuses] = await Promise.all([
      api(`/api/teams?organisation_id=${oid}`),
      api(`/api/agents?organisation_id=${oid}`),
      api(`/api/channels?organisation_id=${oid}`),
      api(`/api/tasks?organisation_id=${oid}`),
      api(`/api/approvals?organisation_id=${oid}`),
      api("/api/agents/status").catch(() => []),
    ]);
    state.teams = teams;
    state.agents = agents;
    state.channels = channels;
    state.tasks = tasks;
    state.approvals = approvals;
    state.agentStatus = Object.fromEntries((statuses || []).map((s) => [s.id, s.status]));

    if (!state.channel || !channels.find((c) => c.id === state.channel.id)) {
      state.channel = channels.find((c) => c.name === "HQ") || channels[0] || null;
    }

    renderSidebar();
    renderComposeAgents();
    renderAgentDetail();
    renderTasks();
    renderApprovalsMini();
    updateApprovalBadge();
    await refreshMessages();
  }

  async function refreshMessages() {
    if (!state.channel) {
      state.messages = [];
      renderMessages();
      return;
    }
    state.messages = await api(`/api/messages?channel_id=${state.channel.id}`);
    renderMessages();
  }

  async function refreshTasksOnly() {
    if (!state.org) return;
    state.tasks = await api(`/api/tasks?organisation_id=${state.org.id}`);
    state.approvals = await api(`/api/approvals?organisation_id=${state.org.id}`);
    const statuses = await api("/api/agents/status").catch(() => []);
    state.agentStatus = Object.fromEntries((statuses || []).map((s) => [s.id, s.status]));
    renderTasks();
    renderApprovalsMini();
    updateApprovalBadge();
    renderSidebar();
  }

  function statusLabel(a) {
    return state.agentStatus[a.id] || a.status || "idle";
  }

  function renderSidebar() {
    const orgList = $("#org-list");
    orgList.innerHTML = "";
    if (state.org) {
      const btn = document.createElement("button");
      btn.className = "tree-item active";
      btn.innerHTML = `<span class="dot"></span><span class="meta"><strong>${esc(state.org.name)}</strong><span>Organisation</span></span>`;
      orgList.appendChild(btn);
    }

    const teamList = $("#team-list");
    teamList.innerHTML = "";
    state.teams.forEach((t) => {
      const el = document.createElement("button");
      el.className = "tree-item";
      el.innerHTML = `<span class="dot ${esc(t.name.toLowerCase())}"></span><span class="meta"><strong>${esc(t.name)}</strong><span>${esc(t.description || "Team")}</span></span>`;
      teamList.appendChild(el);
    });

    const agentList = $("#agent-list");
    agentList.innerHTML = "";
    state.agents.forEach((a) => {
      const el = document.createElement("button");
      el.className = "tree-item" + (state.selectedAgent?.id === a.id ? " active" : "");
      const st = statusLabel(a);
      const team = a.team_id ? teamById(a.team_id) : null;
      el.innerHTML = `<span class="dot ${roleClass(a)}"></span><span class="meta"><strong>${esc(a.name)}</strong><span>${esc(roleLabel(a.role))}${a.is_human ? " · human" : ""} · <em class="agent-st ${esc(st)}">${esc(st)}</em>${team ? " · " + team.name : ""}</span></span>`;
      el.addEventListener("click", () => {
        state.selectedAgent = a;
        renderSidebar();
        renderAgentDetail();
      });
      agentList.appendChild(el);
    });

    const channelList = $("#channel-list");
    channelList.innerHTML = "";
    state.channels.forEach((c) => {
      const el = document.createElement("button");
      el.className = "tree-item" + (state.channel?.id === c.id ? " active" : "");
      el.innerHTML = `<span class="dot"></span><span class="meta"><strong># ${esc(c.name)}</strong><span>${esc(c.description || "Channel")}</span></span>`;
      el.addEventListener("click", async () => {
        state.channel = c;
        renderSidebar();
        await refreshMessages();
      });
      channelList.appendChild(el);
    });

    $("#channel-title").textContent = state.channel ? `# ${state.channel.name}` : "Channel";
    $("#channel-sub").textContent = state.channel
      ? state.channel.description || "HQ coordination"
      : "Select or bootstrap an org";
  }

  function renderAgentDetail() {
    let panel = $("#agent-detail");
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "agent-detail";
      panel.className = "agent-detail";
      document.querySelector(".sidebar").appendChild(panel);
    }
    const a = state.selectedAgent;
    if (!a) {
      panel.innerHTML = `<h3>Agent persona</h3><p class="muted">Select an agent to view role, status, and system prompt.</p>`;
      return;
    }
    const team = a.team_id ? teamById(a.team_id) : null;
    panel.innerHTML = `
      <h3>${esc(a.name)}</h3>
      <div class="row" style="display:flex;gap:0.35rem;flex-wrap:wrap">
        <span class="badge">${esc(roleLabel(a.role))}</span>
        ${a.is_human ? '<span class="badge">human</span>' : '<span class="badge">AI</span>'}
        <span class="badge">${esc(statusLabel(a))}</span>
        ${team ? `<span class="badge">${esc(team.name)}</span>` : ""}
      </div>
      <div class="prompt">${esc(a.system_prompt || "No system prompt set.")}</div>
    `;
  }

  function renderComposeAgents() {
    const sel = $("#compose-agent");
    const prev = sel.value;
    sel.innerHTML = "";
    state.agents.forEach((a) => {
      const opt = document.createElement("option");
      opt.value = a.id;
      opt.textContent = a.name;
      sel.appendChild(opt);
    });
    const ceo = state.agents.find((a) => a.role === "ceo");
    if (prev && state.agents.some((a) => String(a.id) === prev)) sel.value = prev;
    else if (ceo) sel.value = ceo.id;
  }

  function renderMessages() {
    const box = $("#messages");
    if (!state.messages.length) {
      box.innerHTML = `<div class="empty-state"><strong>No messages yet</strong>Post as CEO or hit <em>Run Demo</em> for tool-calling collaboration.</div>`;
      return;
    }
    const wasAtBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    box.innerHTML = "";
    const byId = Object.fromEntries(state.messages.map((m) => [m.id, m]));
    const roots = state.messages.filter((m) => !m.parent_id);
    const children = {};
    state.messages.forEach((m) => {
      if (m.parent_id) (children[m.parent_id] ||= []).push(m);
    });

    function renderOne(m, depth) {
      const agent = agentById(m.agent_id);
      const name = agent?.name || m.agent_name || `Agent #${m.agent_id}`;
      const role = agent ? roleLabel(agent.role) : m.agent_role || "";
      const div = document.createElement("div");
      div.className = "msg" + (depth ? " msg-reply" : "");
      if (depth) div.style.marginLeft = Math.min(depth * 18, 54) + "px";
      let parentHint = "";
      if (m.parent_id && byId[m.parent_id]) {
        parentHint = `<div class="msg-parent">↩ ${esc((byId[m.parent_id].content || "").slice(0, 80))}</div>`;
      }
      div.innerHTML = `
        ${parentHint}
        <div class="msg-head">
          <span class="avatar">${esc(initials(name))}</span>
          <span class="name">${esc(name)}</span>
          <span class="role">${esc(role)}</span>
          <span class="time">${esc(formatTime(m.created_at))}</span>
          <button type="button" class="btn btn-xs reply-btn" data-id="${m.id}" title="Reply">↩</button>
        </div>
        <div class="msg-body">${esc(m.content)}</div>
      `;
      div.querySelector(".avatar").classList.add(roleClass(agent));
      div.querySelector(".reply-btn").addEventListener("click", () => setReply(m));
      box.appendChild(div);
      (children[m.id] || []).forEach((c) => renderOne(c, depth + 1));
    }

    // orphans whose parent missing
    const rendered = new Set();
    roots.forEach((m) => {
      renderOne(m, 0);
      rendered.add(m.id);
      function mark(id) {
        (children[id] || []).forEach((c) => {
          rendered.add(c.id);
          mark(c.id);
        });
      }
      mark(m.id);
    });
    state.messages.filter((m) => !rendered.has(m.id)).forEach((m) => renderOne(m, 0));

    if (wasAtBottom) box.scrollTop = box.scrollHeight;
  }

  function setReply(m) {
    state.replyTo = m;
    $("#compose-reply-to").value = m.id;
    $("#reply-banner").classList.remove("hidden");
    $("#reply-preview").textContent = `#${m.id}: ${(m.content || "").slice(0, 60)}`;
    $("#compose-text").focus();
  }

  function clearReply() {
    state.replyTo = null;
    $("#compose-reply-to").value = "";
    $("#reply-banner").classList.add("hidden");
  }

  function renderTasks() {
    const list = $("#task-list");
    list.innerHTML = "";
    if (!state.tasks.length) {
      list.innerHTML = `<div class="empty-state" style="padding:1rem"><strong>No tasks</strong>Create a CEO directive above.</div>`;
      return;
    }
    const parents = state.tasks.filter((t) => !t.parent_task_id);
    const children = state.tasks.filter((t) => t.parent_task_id);
    const byParent = {};
    children.forEach((c) => {
      (byParent[c.parent_task_id] ||= []).push(c);
    });

    function card(t, isSub) {
      const assignee = t.assignee_id ? agentById(t.assignee_id) : null;
      const el = document.createElement("div");
      el.className = "task-card" + (isSub ? " sub" : "");
      el.innerHTML = `
        <div class="title">${esc(t.title)}</div>
        <div class="muted" style="font-size:0.78rem">${esc((t.description || "").slice(0, 120))}</div>
        <div class="row">
          <span class="badge ${esc(t.status)}">${esc(t.status)}</span>
          ${assignee ? `<span class="badge">${esc(assignee.name)}</span>` : ""}
          ${!isSub && t.status !== "done" && t.status !== "awaiting_approval" ? `<button class="btn btn-xs run-task" data-id="${t.id}">Run</button>` : ""}
        </div>
        ${t.result ? `<div class="result">${esc(t.result.slice(0, 400))}</div>` : ""}
      `;
      const runBtn = el.querySelector(".run-task");
      if (runBtn) {
        runBtn.addEventListener("click", async () => {
          runBtn.disabled = true;
          try {
            const cos = state.agents.find((a) => a.role === "chief_of_staff");
            if (!t.assignee_id && cos) {
              await api(`/api/tasks/${t.id}/assign?run=true`, {
                method: "POST",
                body: JSON.stringify({ assignee_id: cos.id, channel_id: state.channel?.id || null }),
              });
            } else {
              await api(`/api/tasks/${t.id}/run`, { method: "POST" });
            }
            toast("Task run complete", "success");
            await refreshAll();
          } catch (e) {
            toast(e.message, "error");
          } finally {
            runBtn.disabled = false;
          }
        });
      }
      return el;
    }

    parents.forEach((p) => {
      list.appendChild(card(p, false));
      (byParent[p.id] || []).forEach((c) => list.appendChild(card(c, true)));
    });
    children
      .filter((c) => !parents.find((p) => p.id === c.parent_task_id))
      .forEach((c) => list.appendChild(card(c, true)));
  }

  function updateApprovalBadge() {
    const pending = state.approvals.filter((a) => a.status === "pending");
    const badge = $("#approval-badge");
    if (pending.length) {
      badge.textContent = String(pending.length);
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }
  }

  function renderApprovalsMini() {
    const box = $("#approvals-mini");
    const pending = state.approvals.filter((a) => a.status === "pending").slice(0, 5);
    if (!pending.length) {
      box.innerHTML = `<p class="muted" style="font-size:0.8rem;padding:0.35rem">No pending approvals</p>`;
      return;
    }
    box.innerHTML = "";
    pending.forEach((a) => {
      const el = document.createElement("div");
      el.className = "approval-card";
      el.innerHTML = `
        <div class="title">${esc(a.title)}</div>
        <div class="row">
          <button class="btn btn-xs btn-primary appr-yes" data-id="${a.id}">Approve</button>
          <button class="btn btn-xs appr-no" data-id="${a.id}">Reject</button>
        </div>`;
      el.querySelector(".appr-yes").addEventListener("click", () => decideApproval(a.id, true));
      el.querySelector(".appr-no").addEventListener("click", () => decideApproval(a.id, false));
      box.appendChild(el);
    });
  }

  async function decideApproval(id, yes) {
    try {
      await api(`/api/approvals/${id}/${yes ? "approve" : "reject"}`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      toast(yes ? "Approved" : "Rejected", "success");
      await refreshAll();
      renderApprovalsDialog();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  function renderApprovalsDialog() {
    const box = $("#approvals-list");
    if (!state.approvals.length) {
      box.innerHTML = `<div class="empty-state"><strong>No approvals</strong></div>`;
      return;
    }
    box.innerHTML = "";
    state.approvals.forEach((a) => {
      const el = document.createElement("div");
      el.className = "approval-card";
      el.innerHTML = `
        <div class="title">${esc(a.title)} <span class="badge ${esc(a.status)}">${esc(a.status)}</span></div>
        <div class="muted">${esc(a.description || "")}</div>
        <div class="muted">Requester: ${esc(a.requester_name || a.requester_agent_id || "—")}</div>
        ${
          a.status === "pending"
            ? `<div class="row" style="margin-top:0.5rem">
                <button class="btn btn-xs btn-primary appr-yes" data-id="${a.id}">Approve</button>
                <button class="btn btn-xs appr-no" data-id="${a.id}">Reject</button>
              </div>`
            : `<div class="muted">${esc(a.decision_note || "")}</div>`
        }`;
      el.querySelector(".appr-yes")?.addEventListener("click", () => decideApproval(a.id, true));
      el.querySelector(".appr-no")?.addEventListener("click", () => decideApproval(a.id, false));
      box.appendChild(el);
    });
  }

  async function loadConnectors() {
    state.connectors = await api("/api/connectors");
    const box = $("#connectors-list");
    box.innerHTML = "";
    state.connectors.forEach((c) => {
      const el = document.createElement("div");
      el.className = "connector-card";
      el.innerHTML = `
        <div class="title">${esc(c.label || c.name)}
          <span class="badge ${c.available ? "done" : "pending"}">${c.available ? "available" : "needs setup"}</span>
        </div>
        <div class="muted">${esc(c.setup || c.description || "")}</div>
        <div class="row" style="margin-top:0.4rem">
          <label class="muted"><input type="checkbox" class="conn-en" data-name="${esc(c.name)}" ${c.user_enabled !== false ? "checked" : ""}/> Enabled</label>
          ${c.name === "web" ? `<button class="btn btn-xs conn-test" data-name="web">Test fetch example.com</button>` : ""}
          ${c.name === "files" ? `<button class="btn btn-xs conn-test" data-name="files">List workspace</button>` : ""}
        </div>
        <pre class="test-result hidden conn-out"></pre>`;
      el.querySelector(".conn-en").addEventListener("change", async (ev) => {
        try {
          await api(`/api/connectors/${c.name}/enable`, {
            method: "POST",
            body: JSON.stringify({ enabled: ev.target.checked }),
          });
          toast("Connector updated", "success");
        } catch (e) {
          toast(e.message, "error");
        }
      });
      el.querySelector(".conn-test")?.addEventListener("click", async () => {
        const out = el.querySelector(".conn-out");
        try {
          const payload =
            c.name === "web"
              ? { action: "fetch", url: "https://example.com", max_chars: 200 }
              : { action: "list", path: "." };
          const res = await api(`/api/connectors/${c.name}/invoke`, {
            method: "POST",
            body: JSON.stringify({ payload }),
          });
          out.textContent = JSON.stringify(res, null, 2).slice(0, 800);
          out.classList.remove("hidden");
        } catch (e) {
          toast(e.message, "error");
        }
      });
      box.appendChild(el);
    });
  }

  async function loadRoutines() {
    if (!state.org) return;
    state.routines = await api(`/api/routines?organisation_id=${state.org.id}`);
    const box = $("#routines-list");
    box.innerHTML = "";
    if (!state.routines.length) {
      box.innerHTML = `<p class="muted">No routines yet.</p>`;
      return;
    }
    state.routines.forEach((r) => {
      const el = document.createElement("div");
      el.className = "routine-card";
      el.innerHTML = `
        <div class="title">${esc(r.name)} ${r.enabled ? "" : "(disabled)"}</div>
        <div class="muted">${esc(r.prompt.slice(0, 120))}</div>
        <div class="muted">${r.every_seconds ? `every ${r.every_seconds}s` : `cron ${esc(r.cron || "")}`}
          · last: ${esc(r.last_run_at || "never")}</div>
        <div class="row" style="margin-top:0.4rem">
          <button class="btn btn-xs btn-primary run-r" data-id="${r.id}">Run now</button>
          <button class="btn btn-xs del-r" data-id="${r.id}">Delete</button>
        </div>`;
      el.querySelector(".run-r").addEventListener("click", async () => {
        try {
          await api(`/api/routines/${r.id}/run`, { method: "POST" });
          toast("Routine fired", "success");
          await loadRoutines();
          await refreshAll();
        } catch (e) {
          toast(e.message, "error");
        }
      });
      el.querySelector(".del-r").addEventListener("click", async () => {
        try {
          await api(`/api/routines/${r.id}`, { method: "DELETE" });
          toast("Deleted", "success");
          await loadRoutines();
        } catch (e) {
          toast(e.message, "error");
        }
      });
      box.appendChild(el);
    });
  }

  async function loadFiles() {
    const data = await api("/api/files?path=.");
    const box = $("#files-list");
    box.innerHTML = `<p class="muted">Workspace: <code>${esc(data.workspace || "workspace")}</code></p>`;
    const list = document.createElement("div");
    list.className = "files-entries";
    (data.entries || []).forEach((e) => {
      const row = document.createElement("div");
      row.className = "file-row";
      row.innerHTML = `<span>${e.type === "dir" ? "📂" : "📄"} ${esc(e.name)}</span>
        <span class="muted">${e.size != null ? e.size + " B" : ""}</span>`;
      list.appendChild(row);
    });
    if (!(data.entries || []).length) {
      list.innerHTML = `<p class="muted">Empty — upload a file to get started.</p>`;
    }
    box.appendChild(list);
  }

  async function uploadFile(file) {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/files/upload", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    toast(`Uploaded ${file.name}`, "success");
    await loadFiles();
  }

  function startPolling() {
    clearInterval(state.pollTimer);
    state.pollTimer = setInterval(async () => {
      try {
        await refreshMessages();
        await refreshTasksOnly();
      } catch (_) {}
    }, 2500);
  }

  // Events
  $("#btn-refresh").addEventListener("click", () =>
    refreshAll().then(() => toast("Refreshed")).catch((e) => toast(e.message, "error"))
  );

  $("#btn-bootstrap").addEventListener("click", async () => {
    try {
      await api("/api/bootstrap", { method: "POST", body: "{}" });
      toast("Sample org ready", "success");
      await refreshAll();
    } catch (e) {
      toast(e.message, "error");
    }
  });

  $("#btn-demo").addEventListener("click", async () => {
    const btn = $("#btn-demo");
    btn.disabled = true;
    btn.textContent = "Running…";
    try {
      const res = await api("/api/demo", { method: "POST", body: JSON.stringify({}) });
      toast(`Demo done (${res.mode || "mock"} tools)`, "success");
      await refreshAll();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Run Demo";
    }
  });

  $("#btn-settings").addEventListener("click", async () => {
    await loadSettingsBadge();
    $("#cfg-test-result").classList.add("hidden");
    $("#settings-dialog").showModal();
  });

  $("#cfg-test").addEventListener("click", async () => {
    const out = $("#cfg-test-result");
    out.classList.remove("hidden");
    out.textContent = "Testing…";
    try {
      const res = await api("/api/settings/test", { method: "POST", body: "{}" });
      out.textContent = JSON.stringify(res, null, 2);
    } catch (e) {
      out.textContent = e.message;
    }
  });

  $("#settings-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (ev.submitter && ev.submitter.value === "cancel") {
      $("#settings-dialog").close();
      return;
    }
    const payload = {
      openai_base_url: $("#cfg-base").value.trim() || undefined,
      openai_model: $("#cfg-model").value.trim() || undefined,
    };
    const key = $("#cfg-key").value.trim();
    if (key) payload.openai_api_key = key;
    try {
      await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
      toast("Settings saved", "success");
      $("#settings-dialog").close();
      await loadSettingsBadge();
    } catch (e) {
      toast(e.message, "error");
    }
  });

  $("#btn-connectors").addEventListener("click", async () => {
    await loadConnectors();
    $("#connectors-dialog").showModal();
  });
  $("#connectors-close").addEventListener("click", () => $("#connectors-dialog").close());

  $("#btn-routines").addEventListener("click", async () => {
    await loadRoutines();
    $("#routines-dialog").showModal();
  });
  $("#routines-close").addEventListener("click", () => $("#routines-dialog").close());

  $("#routine-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!state.org) return;
    const every = Number($("#routine-every").value) || null;
    const cron = $("#routine-cron").value.trim() || null;
    if (!every && !cron) {
      toast("Set every_seconds or cron", "error");
      return;
    }
    const cos = state.agents.find((a) => a.role === "chief_of_staff");
    try {
      await api("/api/routines", {
        method: "POST",
        body: JSON.stringify({
          organisation_id: state.org.id,
          name: $("#routine-name").value.trim(),
          prompt: $("#routine-prompt").value.trim(),
          every_seconds: every,
          cron,
          target_agent_id: cos?.id || null,
          channel_id: state.channel?.id || null,
          enabled: true,
        }),
      });
      $("#routine-name").value = "";
      $("#routine-prompt").value = "";
      toast("Routine created", "success");
      await loadRoutines();
    } catch (e) {
      toast(e.message, "error");
    }
  });

  $("#btn-approvals").addEventListener("click", async () => {
    if (state.org) {
      state.approvals = await api(`/api/approvals?organisation_id=${state.org.id}`);
    }
    renderApprovalsDialog();
    $("#approvals-dialog").showModal();
  });
  $("#approvals-close").addEventListener("click", () => $("#approvals-dialog").close());

  $("#btn-files").addEventListener("click", async () => {
    await loadFiles();
    $("#files-dialog").showModal();
  });
  $("#files-close").addEventListener("click", () => $("#files-dialog").close());

  $("#file-input").addEventListener("change", async (ev) => {
    const f = ev.target.files?.[0];
    if (f) {
      try {
        await uploadFile(f);
      } catch (e) {
        toast(e.message, "error");
      }
    }
  });

  const drop = $("#file-drop");
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("drag");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", async (e) => {
    e.preventDefault();
    drop.classList.remove("drag");
    const f = e.dataTransfer?.files?.[0];
    if (f) {
      try {
        await uploadFile(f);
      } catch (err) {
        toast(err.message, "error");
      }
    }
  });

  $("#reply-cancel").addEventListener("click", clearReply);

  $("#compose").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = $("#compose-text").value.trim();
    if (!text || !state.channel) return;
    const parent_id = $("#compose-reply-to").value
      ? Number($("#compose-reply-to").value)
      : null;
    try {
      await api("/api/messages", {
        method: "POST",
        body: JSON.stringify({
          channel_id: state.channel.id,
          agent_id: Number($("#compose-agent").value),
          content: text,
          parent_id,
        }),
      });
      $("#compose-text").value = "";
      clearReply();
      await refreshMessages();
    } catch (e) {
      toast(e.message, "error");
    }
  });

  $("#task-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!state.org) return;
    const title = $("#task-title").value.trim();
    const description = $("#task-desc").value.trim();
    if (!title) return;
    const cos = state.agents.find((a) => a.role === "chief_of_staff");
    try {
      const task = await api("/api/tasks", {
        method: "POST",
        body: JSON.stringify({
          organisation_id: state.org.id,
          title,
          description: description || null,
          channel_id: state.channel?.id || null,
          assignee_id: cos?.id || null,
        }),
      });
      if (cos && state.channel) {
        await api(`/api/tasks/${task.id}/assign?run=true`, {
          method: "POST",
          body: JSON.stringify({ assignee_id: cos.id, channel_id: state.channel.id }),
        });
      }
      $("#task-title").value = "";
      $("#task-desc").value = "";
      toast("Task created & assigned", "success");
      await refreshAll();
    } catch (e) {
      toast(e.message, "error");
    }
  });

  (async () => {
    try {
      await loadSettingsBadge();
      await refreshAll();
      startPolling();
    } catch (e) {
      toast(e.message || "Failed to load", "error");
    }
  })();
})();
