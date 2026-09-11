# N.E.H.A Android 2.1.4

Fully **standalone** APK: on-device NanoHTTPD backend + desk WebView UI.

## Features (v2)

- OpenAI-compatible LLM (key in Settings) + mock fallback
- Multi-agent task collaboration (CoS / Ops / Research / Comms)
- Approvals inbox, routines (run-now), workspace files, connectors list
- Same desk UI as the Python PC app (`Start.bat`)
- **In-app updater**: Check for updates downloads the debug APK and launches the system installer (FileProvider + `REQUEST_INSTALL_PACKAGES`)

## Build

```bash
./build-apk.sh
# → dist/NEHA-2.1.4-debug.apk
```

Requires Android SDK + JDK 17+.

## Update check fallback

If the GitHub Releases API is rate-limited (HTTP 403/429), the app falls back to
[`android/latest-release.json`](latest-release.json) on `main` (raw.githubusercontent.com).
Keep that file updated on every release.
