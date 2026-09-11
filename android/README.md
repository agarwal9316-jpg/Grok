# Grok Org OS — Android

Package: `com.grokorg.desk` · versionName `1.2.0` · versionCode `3`

**Standalone by default** — embeds a local HTTP backend (NanoHTTPD + SQLite) on `127.0.0.1` so the full desk GUI runs on the phone with no PC.

## Quick build

```bash
export ANDROID_HOME=/path/to/android-sdk   # or /workspace/android-sdk
export JAVA_HOME=/path/to/jdk-17-or-21
./build-apk.sh
```

Output: `dist/GrokOrgOS-1.2.0-debug.apk`

## Architecture

- **GrokApplication / LocalBackend** — starts in-process server on a free port (prefer 8765)
- **LocalHttpServer** — serves `assets/www` static desk GUI + `/api/*` JSON (orgs, teams, agents, channels, messages, tasks, bootstrap, demo, settings)
- **OrgStore + TaskRunner + LlmClient** — SQLite persistence, CoS decompose/specialist/mock LLM (optional remote OpenAI-compatible key via desk Settings)
- **Home** — backend status, Open Desk, Help shell, Settings, Check for updates
- **DeskActivity** — WebView → `http://127.0.0.1:<port>/` (or advanced remote URL)
- **Settings** — On-device (default) vs Remote server URL override; auto update-check
- **UpdateChecker** — GitHub Releases API vs `versionName`

Bundled copy of `grok_org_os/static` lives under `app/src/main/assets/www/`.
