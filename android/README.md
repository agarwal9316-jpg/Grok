# Grok Org OS — Android

Package: `com.grokorg.desk` · versionName `1.1.0` · versionCode `2`

## Quick build

```bash
export ANDROID_HOME=/path/to/android-sdk   # or /workspace/android-sdk
export JAVA_HOME=/path/to/jdk-17-or-21
./build-apk.sh
```

Output: `dist/GrokOrgOS-1.1.0-debug.apk`

## Architecture

- **Home** — server status probe, Open Desk, Demo/Offline, Settings, Check for updates
- **DeskActivity** — WebView to `{serverUrl}/`; falls back to `assets/www/offline.html`
- **Settings** — Server URL + auto update-check toggle
- **UpdateChecker** — GitHub Releases API comparison vs `versionName`

Bundled copy of `grok_org_os/static` lives under `app/src/main/assets/www/` (plus offline shell).
