# Grok Org OS 2.1 — Grok-class desk + model picker

Portable multi-agent AI organisation platform with **real OpenAI tool calling**, concurrent agent workers, connectors (files / web / email / REST), CEO approvals, workspace file drops, scheduled routines, and a **Grok-like chat desk** with live **model fetch + topbar picker**.

The **PC / Windows app is first-class** (double-click `Start.bat`). Android APK is a standalone on-device mirror of the same desk UI + API.

---

## What’s new in 2.1

- **Fetch models** from `{openai_base_url}/models` (Bearer key) via `GET|POST /api/models`
- **Settings**: after base URL + key → **Fetch models** fills a `<select>`; choosing one saves `openai_model`
- **Chat topbar model picker** (`#model-picker`) — change model anytime (PUT `/api/settings`); badge updates
- Clear connection errors (401 / 404 / wrong trailing slash / missing `/v1`)
- Base URL normalization (strip trailing `/`; smart `/v1` append for known hosts)
- Polished desk: avatar bubbles, sticky compose, More menu, mobile WebView tabs
- Android **2.1.1** (versionCode 6) mirrors `/api/models` on-device

---

## Windows (double-click) — recommended

**Requirement:** [Python 3.11+](https://www.python.org/downloads/) on PATH  
(check *“Add python.exe to PATH”* during install).

1. Unzip / clone this folder anywhere on your PC.
2. Double-click **`Start.bat`** (or right-click **`Start.ps1`** → Run with PowerShell).
3. Browser / desktop window opens **http://127.0.0.1:8000** — the full desk GUI.
4. Click **⚙ OpenAI** → paste API key + base URL → **Fetch models** → pick a model → **Test connection** → **Save**.
5. Use the **topbar model dropdown** to switch models without reopening Settings.
6. Hit **Run Demo** — with a key set, agents use **live tool calls**. Without a key, offline **mock** still demos the flow.
7. Stop: close the console, or run **`Stop.bat`**.

First launch creates `.venv`, installs deps (including APScheduler), copies `.env.example` → `.env`, creates `workspace/`, and bootstraps a sample org.

### LLM settings

| Setting | Default | Notes |
|---------|---------|--------|
| `OPENAI_API_KEY` | _(empty = mock)_ | Required for live LLM + real tools |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenRouter / Azure / Ollama compatible |
| `OPENAI_MODEL` | `gpt-4o-mini` | Select via Fetch models or topbar picker |

Trailing slash is stripped. If you paste a bare host (e.g. `https://api.openai.com` or `https://openrouter.ai/api`), the server appends `/v1` when appropriate.

Optional connectors in `.env`: `SMTP_*`, `WEBHOOK_URL`, `REST_*`, `GOOGLE_*` (stubs activate when tokens present).

---

## Mac / Linux

```bash
chmod +x start.sh
./start.sh
# → http://127.0.0.1:8000
```

Or:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp -n .env.example .env   # set OPENAI_API_KEY for live mode
grok-org serve
```

---

## How to verify (acceptance checklist)

Do these after `Start.bat` **or** installing the Android APK. Every item is implemented (not stubbed) unless noted under **Known gaps**.

| # | Requirement | How to verify |
|---|-------------|----------------|
| 1 | **Fetch models + dropdown** | OpenAI → paste key + base URL (e.g. `https://api.openai.com/v1` or OpenRouter) → **Fetch models** → `<select>` fills → pick model → Save. Wrong key → clear **401**; wrong URL → clear **404**/connection error. Topbar **model picker** also lists models and PUTs `/api/settings` on change. |
| 2 | **Grok-class chat UX** | Model picker always visible next to LLM badge; message bubbles with avatar initials; sticky compose; soft dark theme; on phone/WebView use **Chat / Org / Tasks** tabs + ☰. |
| 3 | **Live multi-agent + tools** | With key set, badge shows `Live · <model>`. **Run Demo** — HQ channel fills with CoS/specialist messages; tasks appear; mode is `live` (not only mock). |
| 4 | **Core tools** | Demo / task run exercises: `send_message`, `create_task`, `handoff_task`, `read_channel`, `list_agents`, `http_fetch`, `fs_*`, `request_approval` (see pytest + live demo). |
| 5 | **Connectors UI** | **More → Connectors**. Files + Web available; **Test fetch** / **List workspace**. Email needs `SMTP_*` in `.env` (or Android settings when configured). |
| 6 | **Threads, approvals, files, status, routines** | Reply via ↩ on a message; **More → Approvals** + rightbar inbox; **More → Files** drag-drop; agent list shows idle/thinking/tool; **More → Routines** create / Run now / schedule. |
| 7 | **Offline mock** | Clear API key → Save → badge `Mock · …` → Run Demo still works with tool-calling mock. `/api/models` returns curated list + note. |
| 8 | **Android in-app update** | Menu → Check for updates → Download & Install (GitHub APK, prefers `*debug*.apk`). |
| 9 | **Tests green** | `pip install -e ".[dev]" && pytest -q` — includes `/api/models` (mock httpx). |
| 10 | **Ship** | `Start.bat` on PC; APK `android/dist/GrokOrgOS-2.1.1-debug.apk`; GitHub release `v2.1.1`. |

### Surfaces

| Surface | URL |
|---------|-----|
| **Desk GUI** | http://127.0.0.1:8000/ |
| Swagger / OpenAPI | http://127.0.0.1:8000/docs |
| Health | http://127.0.0.1:8000/health |
| Models API | `GET|POST /api/models` |

CLI:

```bash
grok-org bootstrap
grok-org run-demo
grok-org serve
grok-org desktop    # optional native window (needs pywebview)
pytest -q
```

---

## Android standalone

APK: **`android/dist/GrokOrgOS-2.1.1-debug.apk`** (versionName **2.1.1**, versionCode **6**).

- On-device NanoHTTPD backend + same desk UI (assets synced from `grok_org_os/static/`)
- `/api/models` fetches remote models with `HttpURLConnection` when key is set
- OpenAI settings + topbar model picker work offline (mock) or live
- In-app update: download & install APK from GitHub Releases (prefers debug build)

Rebuild:

```bash
cd android && ./build-apk.sh
```

---

## Docker (optional)

```bash
docker compose up --build
```

---

## Architecture

```mermaid
flowchart TB
  subgraph UI["Desk GUI 2.1"]
    picker[Model picker]
    channel[Threaded channels]
    tasks_ui[Tasks]
    approvals[CEO approvals]
    files[Workspace files]
    routines[Routines]
    connectors[Connectors]
    openai[OpenAI settings + Fetch models]
  end

  subgraph API["FastAPI /api"]
    models[/api/models]
    runtime[Agent runtime + tools]
    sched[APScheduler routines]
    conn[Connector registry]
  end

  subgraph LLM["OpenAI-compatible"]
    chat[Chat Completions + tools]
    catalog[GET /models]
  end

  UI --> API
  openai --> models
  picker --> API
  models --> catalog
  runtime --> chat
  runtime --> conn
  sched --> runtime
```

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

Covers `/api/models` (mock + httpx), base URL normalization, tool calling, multi-agent demo, approvals, routines, file upload, connectors, threaded replies, settings.

## Known gaps (explicit)

| Gap | Notes |
|-----|--------|
| **Cursor cloud / remote Cursor agents** | Not part of this product — local PC + Android only. |
| **Google connectors** | Stubs; activate only when OAuth tokens are present — not a full Google product integration. |
| **Azure OpenAI deployments** | Works if you set a full deployments-compatible `base_url`; model list shape may vary by resource. |
| **Native Windows tray / auto-update** | PC uses `Start.bat` + optional `grok-org desktop` (pywebview); no Windows Store updater. Android downloads & installs from GitHub Releases (in-app). |
| **SMTP / REST / webhook** | Implemented; require env configuration — UI shows “needs setup” until configured. |

Everything else in the verification table above is **done and shipped**, not deferred.

## License

MIT
