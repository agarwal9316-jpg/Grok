# Grok Org OS Android 2.0.0

Fully **standalone** APK: on-device NanoHTTPD backend + desk WebView UI.

## Features (v2)

- OpenAI-compatible LLM (key in Settings) + mock fallback
- Multi-agent task collaboration (CoS / Ops / Research / Comms)
- Approvals inbox, routines (run-now), workspace files, connectors list
- Same desk UI as the Python PC app (`Start.bat`)

## Build

```bash
./build-apk.sh
# → dist/GrokOrgOS-2.0.0-debug.apk
```

Requires Android SDK + JDK 17+.
