/* Grok Org OS — desk UI */
(() => {
  const state = {
    org: null,
    teams: [],
    agents: [],
    channels: [],
    channel: null,
    messages: [],
    tasks: [],
    selectedAgent: null,
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
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        detail = j.detail || JSON.stringify(j);
      } catch (_) {}
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    if (res.status === 204) return null;
    return res.json();
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
    return ({
      ceo: "CEO",
      chief_of_staff: "Chief of Staff",
      specialist: "Specialist",
    })[role] || role;
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
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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
      $("#cfg-key").placeholder = s.api_key_set ? "•••••••• (saved — leave blank to keep)" : "sk-… (optional)";
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
    const [teams, agents, channels, tasks] = await Promise.all([
      api(`/api/teams?organisation_id=${oid}`),
      api(`/api/agents?organisation_id=${oid}`),
      api(`/api/channels?organisation_id=${oid}`),
      api(`/api/tasks?organisation_id=${oid}`),
    ]);
    state.teams = teams;
    state.agents = agents;
    state.channels = channels;
    state.tasks = tasks;

    if (!state.channel || !channels.find((c) => c.id === state.channel.id)) {
      state.channel = channels.find((c) => c.name === "HQ") || channels[0] || null;
    }

    renderSidebar();
    renderComposeAgents();
    renderAgentDetail();
    renderTasks();
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
    renderTasks();
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
      el.addEventListener("click", () => toast(`${t.name}: ${t.description || "team"}`));
      teamList.appendChild(el);
    });

    const agentList = $("#agent-list");
    agentList.innerHTML = "";
    state.agents.forEach((a) => {
      const el = document.createElement("button");
      el.className = "tree-item" + (state.selectedAgent?.id === a.id ? " active" : "");
      const team = a.team_id ? teamById(a.team_id) : null;
      el.innerHTML = `<span class="dot ${roleClass(a)}"></span><span class="meta"><strong>${esc(a.name)}</strong><span>${esc(roleLabel(a.role))}${a.is_human ? " · human" : ""}${team ? " · " + team.name : ""}</span></span>`;
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
      const sidebar = document.querySelector(".sidebar");
      sidebar.appendChild(panel);
    }
    const a = state.selectedAgent;
    if (!a) {
      panel.innerHTML = `<h3>Agent persona</h3><p class="muted">Select an agent in the sidebar to view their role and system prompt.</p>`;
      return;
    }
    const team = a.team_id ? teamById(a.team_id) : null;
    panel.innerHTML = `
      <h3>${esc(a.name)}</h3>
      <div class="row" style="display:flex;gap:0.35rem;flex-wrap:wrap">
        <span class="badge">${esc(roleLabel(a.role))}</span>
        ${a.is_human ? '<span class="badge">human</span>' : '<span class="badge">AI</span>'}
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
      box.innerHTML = `<div class="empty-state"><strong>No messages yet</strong>Post as CEO or hit <em>Run Demo</em> to start collaboration.</div>`;
      return;
    }
    const wasAtBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    box.innerHTML = "";
    state.messages.forEach((m) => {
      const agent = agentById(m.agent_id);
      const name = agent?.name || `Agent #${m.agent_id}`;
      const role = agent ? roleLabel(agent.role) : "";
      const div = document.createElement("div");
      div.className = "msg";
      div.innerHTML = `
        <div class="msg-head">
          <span class="avatar" style="color:inherit">${esc(initials(name))}</span>
          <span class="name">${esc(name)}</span>
          <span class="role">${esc(role)}</span>
          <span class="time">${esc(formatTime(m.created_at))}</span>
        </div>
        <div class="msg-body">${esc(m.content)}</div>
      `;
      const avatar = div.querySelector(".avatar");
      avatar.classList.add(roleClass(agent));
      box.appendChild(div);
    });
    if (wasAtBottom) box.scrollTop = box.scrollHeight;
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
          ${!isSub && t.status !== "done" ? `<button class="btn btn-xs run-task" data-id="${t.id}">Run</button>` : ""}
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
                body: JSON.stringify({
                  assignee_id: cos.id,
                  channel_id: state.channel?.id || null,
                }),
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
    // orphan subtasks
    children
      .filter((c) => !parents.find((p) => p.id === c.parent_task_id))
      .forEach((c) => list.appendChild(card(c, true)));
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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
      await api("/api/demo", {
        method: "POST",
        body: JSON.stringify({}),
      });
      toast("Demo collaboration finished", "success");
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
    $("#settings-dialog").showModal();
  });

  $("#settings-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const submitter = ev.submitter;
    if (submitter && submitter.value === "cancel") {
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

  $("#compose").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = $("#compose-text").value.trim();
    if (!text || !state.channel) return;
    try {
      await api("/api/messages", {
        method: "POST",
        body: JSON.stringify({
          channel_id: state.channel.id,
          agent_id: Number($("#compose-agent").value),
          content: text,
        }),
      });
      $("#compose-text").value = "";
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

  // Boot
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
