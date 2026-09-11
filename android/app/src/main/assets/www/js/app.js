/* Grok Org OS 2.1.3 — providers + robust model fetch/test */
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
    models: [],
    currentModel: "gpt-4o-mini",
    hasKey: false,
    config: null,
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
    const timeoutMs = opts.timeoutMs;
    const { timeoutMs: _omit, ...fetchOpts } = opts;
    let timer;
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    if (timeoutMs && controller) {
      timer = setTimeout(() => controller.abort(), timeoutMs);
      fetchOpts.signal = controller.signal;
    }
    let res;
    try {
      res = await fetch(path, { ...fetchOpts, headers });
    } catch (e) {
      if (e && (e.name === "AbortError" || /abort/i.test(String(e.message || "")))) {
        throw new Error(`Request timed out after ${Math.round((timeoutMs || 0) / 1000)}s`);
      }
      throw e;
    } finally {
      if (timer) clearTimeout(timer);
    }
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

  const CUSTOM_PROVIDERS_KEY = "grok_custom_providers";

  function loadCustomProviders() {
    try {
      const raw = localStorage.getItem(CUSTOM_PROVIDERS_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr : [];
    } catch (_) {
      return [];
    }
  }

  function saveCustomProviders(list) {
    localStorage.setItem(CUSTOM_PROVIDERS_KEY, JSON.stringify(list || []));
  }

  function formLlmOverrides() {
    const payload = {};
    const base = ($("#cfg-base")?.value || "").trim();
    const model = ($("#cfg-model")?.value || "").trim();
    const key = ($("#cfg-key")?.value || "").trim();
    if (base) payload.openai_base_url = base;
    if (model) payload.openai_model = model;
    if (key) payload.openai_api_key = key;
    return payload;
  }

  async function populateProviders(selectedBase) {
    const sel = $("#cfg-provider");
    if (!sel) return;
    let providers = [];
    try {
      const res = await api("/api/providers", { timeoutMs: 15000 });
      providers = res.providers || [];
    } catch (_) {
      providers = [
        { id: "openai", name: "OpenAI", base_url: "https://api.openai.com/v1" },
        { id: "nvidia", name: "NVIDIA NIM", base_url: "https://integrate.api.nvidia.com/v1" },
        { id: "custom", name: "Custom", base_url: "" },
      ];
    }
    const customs = loadCustomProviders();
    sel.innerHTML = "";
    providers.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      opt.dataset.baseUrl = p.base_url || "";
      sel.appendChild(opt);
    });
    customs.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = `custom:${c.name}`;
      opt.textContent = `${c.name} (custom)`;
      opt.dataset.baseUrl = c.base_url || "";
      sel.appendChild(opt);
    });
    // Match current base URL
    const base = (selectedBase || $("#cfg-base")?.value || "").trim().replace(/\/+$/, "");
    let matched = "custom";
    for (const opt of sel.options) {
      const bu = (opt.dataset.baseUrl || "").replace(/\/+$/, "");
      if (bu && base && (base === bu || base.startsWith(bu) || bu.startsWith(base))) {
        matched = opt.value;
        break;
      }
    }
    if ([...sel.options].some((o) => o.value === matched)) sel.value = matched;
    else if ([...sel.options].some((o) => o.value === "custom")) sel.value = "custom";
    toggleCustomRow();
  }

  function toggleCustomRow() {
    const row = $("#cfg-custom-row");
    const sel = $("#cfg-provider");
    if (!row || !sel) return;
    const isCustom = !sel.value || sel.value === "custom" || sel.value.startsWith("custom:");
    row.classList.toggle("hidden", !isCustom);
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

  function syncModelUI(model) {
    state.currentModel = model || state.currentModel || "gpt-4o-mini";
    const picker = $("#model-picker");
    if (picker) {
      ensureModelOption(picker, state.currentModel);
      picker.value = state.currentModel;
    }
    const cfg = $("#cfg-model");
    if (cfg) cfg.value = state.currentModel;
    const sel = $("#cfg-model-select");
    if (sel) {
      ensureModelOption(sel, state.currentModel);
      if ([...sel.options].some((o) => o.value === state.currentModel)) {
        sel.value = state.currentModel;
      }
    }
    const hint = $("#compose-model-hint");
    if (hint) {
      hint.textContent = state.hasKey
        ? `Using ${state.currentModel}`
        : `Mock · ${state.currentModel}`;
    }
    const badge = $("#llm-badge");
    if (badge) {
      if (state.hasKey) {
        badge.textContent = `Live · ${state.currentModel}`;
        badge.classList.add("live");
      } else {
        badge.textContent = `Mock · ${state.currentModel}`;
        badge.classList.remove("live");
      }
    }
  }

  function ensureModelOption(selectEl, id) {
    if (!selectEl || !id) return;
    if (![...selectEl.options].some((o) => o.value === id)) {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      selectEl.appendChild(opt);
    }
  }

  function fillModelSelects(models, selected) {
    const ids = (models || []).map((m) => (typeof m === "string" ? m : m.id)).filter(Boolean);
    state.models = ids;
    const pick = selected || state.currentModel || ids[0] || "gpt-4o-mini";
    ["#model-picker", "#cfg-model-select"].forEach((sel) => {
      const el = $(sel);
      if (!el) return;
      const keepFirst = el.id === "cfg-model-select";
      const first = keepFirst ? el.options[0]?.outerHTML || '<option value="">— fetch or type below —</option>' : "";
      el.innerHTML = keepFirst ? first : "";
      ids.forEach((id) => {
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = id;
        el.appendChild(opt);
      });
      ensureModelOption(el, pick);
      el.value = pick;
    });
    syncModelUI(pick);
  }

  async function loadSettingsBadge() {
    try {
      const s = await api("/api/config", { timeoutMs: 15000 });
      state.config = s;
      state.hasKey = !!s.has_llm_key;
      state.currentModel = s.openai_model || "gpt-4o-mini";
      $("#cfg-base").value = s.openai_base_url || "";
      $("#cfg-model").value = s.openai_model || "";
      $("#cfg-key").value = "";
      $("#cfg-key").placeholder = s.api_key_set
        ? "•••••••• (saved — leave blank to keep)"
        : "sk-… (required for full power)";
      await populateProviders(s.openai_base_url || "");
      syncModelUI(state.currentModel);
      // Prefill picker from /api/models (mock or live) — do not hang forever
      try {
        const m = await api("/api/models", { timeoutMs: 45000 });
        if (m && (m.models || m.data)) {
          fillModelSelects(m.models || m.data, state.currentModel);
        } else {
          ensureModelOption($("#model-picker"), state.currentModel);
        }
      } catch (_) {
        ensureModelOption($("#model-picker"), state.currentModel);
      }
    } catch (e) {
      console.warn(e);
    }
  }

  async function saveModel(model) {
    if (!model) return;
    const s = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ openai_model: model }),
    });
    state.currentModel = s.openai_model || model;
    state.hasKey = !!s.has_llm_key;
    syncModelUI(state.currentModel);
    return s;
  }

  async function fetchModelsFromProvider({ saveFirst } = {}) {
    const out = $("#cfg-test-result");
    if (out) {
      out.classList.remove("hidden");
      out.textContent = "Fetching models…";
    }
    try {
      const overrides = formLlmOverrides();
      if (saveFirst && Object.keys(overrides).length) {
        try {
          await api("/api/settings", {
            method: "PUT",
            body: JSON.stringify(overrides),
            timeoutMs: 15000,
          });
        } catch (e) {
          // Still try fetch with body overrides even if save failed
          console.warn("settings save before fetch failed", e);
        }
      }
      const res = await api("/api/models", {
        method: "POST",
        body: JSON.stringify(overrides),
        timeoutMs: 45000,
      });
      if (!res.ok && !(res.models || []).length) {
        const err = res.error || "Failed to fetch models";
        if (out) out.textContent = `FAIL: ${err}`;
        throw new Error(err);
      }
      fillModelSelects(res.models || res.data || [], state.currentModel);
      if (out) {
        const note = res.note ? `\n${res.note}` : "";
        out.textContent = res.ok
          ? `Loaded ${(res.models || []).length} models (${res.mode})${note}`
          : `FAIL: ${res.error || JSON.stringify(res, null, 2)}`;
      }
      return res;
    } catch (e) {
      const msg = e && e.message ? e.message : String(e);
      if (out) {
        out.classList.remove("hidden");
        out.textContent = `FAIL: ${msg}`;
      }
      throw e;
    } finally {
      // Never leave "Fetching models…" forever
      if (out && /Fetching models/i.test(out.textContent || "")) {
        out.textContent = "FAIL: Fetch ended without a result";
      }
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
      box.innerHTML = `<div class="empty-state"><div class="empty-icon">💬</div><strong>Start a conversation</strong>Post as CEO, pick a model in the top bar, or hit <em>Run Demo</em> for live tool-calling collaboration.</div>`;
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
      const rc = roleClass(agent);
      div.innerHTML = `
        ${parentHint}
        <div class="msg-avatar-col"><span class="avatar ${esc(rc)}">${esc(initials(name))}</span></div>
        <div class="msg-bubble">
          <div class="msg-head">
            <span class="name">${esc(name)}</span>
            <span class="role">${esc(role)}</span>
            <span class="time">${esc(formatTime(m.created_at))}</span>
            <button type="button" class="btn btn-xs reply-btn" data-id="${m.id}" title="Reply">↩</button>
          </div>
          <div class="msg-body">${esc(m.content)}</div>
        </div>
      `;
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
    closeMore();
    await loadSettingsBadge();
    $("#cfg-test-result").classList.add("hidden");
    $("#settings-dialog").showModal();
  });

  $("#cfg-fetch-models")?.addEventListener("click", async () => {
    try {
      await fetchModelsFromProvider({ saveFirst: true });
      toast("Models loaded", "success");
    } catch (e) {
      toast(e.message, "error");
    }
  });

  $("#cfg-model-select")?.addEventListener("change", (ev) => {
    const v = ev.target.value;
    if (v) {
      $("#cfg-model").value = v;
      syncModelUI(v);
    }
  });

  $("#model-picker")?.addEventListener("change", async (ev) => {
    const model = ev.target.value;
    try {
      await saveModel(model);
      toast(`Model → ${model}`, "success");
    } catch (e) {
      toast(e.message, "error");
      syncModelUI(state.currentModel);
    }
  });

  function closeMore() {
    $("#more-dropdown")?.classList.add("hidden");
    const btn = $("#btn-more");
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  $("#btn-more")?.addEventListener("click", (ev) => {
    ev.stopPropagation();
    const dd = $("#more-dropdown");
    const open = dd && !dd.classList.contains("hidden");
    if (open) closeMore();
    else {
      dd?.classList.remove("hidden");
      $("#btn-more")?.setAttribute("aria-expanded", "true");
    }
  });
  document.addEventListener("click", (ev) => {
    if (!$(".more-menu")?.contains(ev.target)) closeMore();
  });

  // Mobile pane tabs
  $$(".mobile-tabs .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      $$(".mobile-tabs .tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const pane = tab.dataset.pane || "chat";
      const layout = $("#main-layout");
      if (!layout) return;
      layout.classList.remove("show-chat", "show-org", "show-tasks");
      layout.classList.add(`show-${pane}`);
    });
  });
  $("#btn-sidebar-toggle")?.addEventListener("click", () => {
    const layout = $("#main-layout");
    const showing = layout?.classList.contains("show-org");
    layout?.classList.remove("show-chat", "show-org", "show-tasks");
    layout?.classList.add(showing ? "show-chat" : "show-org");
    $$(".mobile-tabs .tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.pane === (showing ? "chat" : "org"));
    });
  });

  $("#cfg-provider")?.addEventListener("change", () => {
    const sel = $("#cfg-provider");
    const opt = sel?.selectedOptions?.[0];
    const bu = opt?.dataset?.baseUrl || "";
    if (bu && $("#cfg-base")) $("#cfg-base").value = bu;
    toggleCustomRow();
  });

  $("#cfg-add-provider")?.addEventListener("click", async () => {
    const name = ($("#cfg-custom-name")?.value || "").trim();
    const base = ($("#cfg-base")?.value || "").trim();
    if (!name || !base) {
      toast("Enter custom name + base URL", "error");
      return;
    }
    const list = loadCustomProviders().filter((c) => c.name !== name);
    list.push({ name, base_url: base });
    saveCustomProviders(list);
    await populateProviders(base);
    toast(`Saved provider ${name}`, "success");
  });

  $("#cfg-test").addEventListener("click", async () => {
    const out = $("#cfg-test-result");
    out.classList.remove("hidden");
    out.textContent = "Testing…";
    try {
      const overrides = formLlmOverrides();
      if (Object.keys(overrides).length) {
        try {
          await api("/api/settings", {
            method: "PUT",
            body: JSON.stringify(overrides),
            timeoutMs: 15000,
          });
        } catch (e) {
          console.warn("settings save before test failed", e);
        }
      }
      const res = await api("/api/settings/test", {
        method: "POST",
        body: JSON.stringify(overrides),
        timeoutMs: 45000,
      });
      if (res && res.ok === false) {
        out.textContent = `FAIL: ${res.error || JSON.stringify(res, null, 2)}`;
      } else {
        const mode = res?.mode || "?";
        const model = res?.model || overrides.openai_model || "";
        const msg = res?.message || "ok";
        out.textContent = `PASS (${mode}) model=${model}\n${typeof msg === "string" ? msg : JSON.stringify(res, null, 2)}`;
      }
    } catch (e) {
      out.classList.remove("hidden");
      out.textContent = `FAIL: ${e.message || e}`;
    } finally {
      out.classList.remove("hidden");
      if (/^Testing/i.test(out.textContent || "")) {
        out.textContent = "FAIL: Test ended without a result";
      }
    }
  });

  async function saveSettingsFromForm() {
    const out = $("#cfg-test-result");
    const payload = formLlmOverrides();
    // Always include model/base from fields even if empty-trimmed already handled
    if (!payload.openai_base_url) {
      const b = ($("#cfg-base")?.value || "").trim();
      if (b) payload.openai_base_url = b;
    }
    if (!payload.openai_model) {
      const m = ($("#cfg-model")?.value || "").trim();
      if (m) payload.openai_model = m;
    }
    if (!Object.keys(payload).length) {
      toast("Nothing to save", "error");
      if (out) {
        out.classList.remove("hidden");
        out.textContent = "FAIL: Enter base URL, model, and/or API key";
      }
      return false;
    }
    try {
      if (out) {
        out.classList.remove("hidden");
        out.textContent = "Saving…";
      }
      const s = await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify(payload),
        timeoutMs: 20000,
      });
      state.hasKey = !!s.has_llm_key;
      state.currentModel = s.openai_model || payload.openai_model || state.currentModel;
      state.config = s;
      if (out) out.textContent = `Saved. has_llm_key=${!!s.has_llm_key} model=${s.openai_model || ""}`;
      toast("Settings saved", "success");
      syncModelUI(state.currentModel);
      return true;
    } catch (e) {
      const msg = e && e.message ? e.message : String(e);
      toast(msg, "error");
      if (out) {
        out.classList.remove("hidden");
        out.textContent = `FAIL: ${msg}`;
      }
      return false;
    }
  }

  $("#cfg-cancel")?.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    $("#settings-dialog")?.close();
  });

  $("#cfg-save")?.addEventListener("click", async (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    const ok = await saveSettingsFromForm();
    if (ok) {
      $("#settings-dialog")?.close();
      try { await loadSettingsBadge(); } catch (_) {}
    }
  });

  // Keep submit handler as safety net (Enter key) — never use method=dialog
  $("#settings-form")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    const action =
      (ev.submitter && (ev.submitter.dataset?.action || ev.submitter.value || ev.submitter.id)) ||
      "save";
    if (action === "cancel" || action === "cfg-cancel") {
      $("#settings-dialog")?.close();
      return;
    }
    const ok = await saveSettingsFromForm();
    if (ok) {
      $("#settings-dialog")?.close();
      try { await loadSettingsBadge(); } catch (_) {}
    }
  });

  $("#btn-connectors").addEventListener("click", async () => {
    closeMore();
    await loadConnectors();
    $("#connectors-dialog").showModal();
  });
  $("#connectors-close").addEventListener("click", () => $("#connectors-dialog").close());

  $("#btn-routines").addEventListener("click", async () => {
    closeMore();
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
    closeMore();
    if (state.org) {
      state.approvals = await api(`/api/approvals?organisation_id=${state.org.id}`);
    }
    renderApprovalsDialog();
    $("#approvals-dialog").showModal();
  });
  $("#approvals-close").addEventListener("click", () => $("#approvals-dialog").close());

  $("#btn-files").addEventListener("click", async () => {
    closeMore();
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
