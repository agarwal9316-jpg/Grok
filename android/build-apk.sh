#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
if [[ ! -x "$JAVA_HOME/bin/java" ]]; then
  # Fallbacks
  if command -v java >/dev/null 2>&1; then
    export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")"
  fi
fi
export ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/workspace/android-sdk}}"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"

if [[ ! -f local.properties ]]; then
  echo "sdk.dir=$ANDROID_HOME" > local.properties
fi

# Refresh bundled www assets from Python static (optional sync)
STATIC_SRC="$ROOT/../grok_org_os/static"
if [[ -d "$STATIC_SRC" ]]; then
  mkdir -p app/src/main/assets/www
  # Keep offline.html; sync css/js/index
  cp -a "$STATIC_SRC/css" "$STATIC_SRC/js" app/src/main/assets/www/ 2>/dev/null || true
  if [[ -f "$STATIC_SRC/index.html" ]]; then
    cp "$STATIC_SRC/index.html" app/src/main/assets/www/index.html
    sed -i 's|href="/static/css/app.css"|href="css/app.css"|' app/src/main/assets/www/index.html
    sed -i 's|src="/static/js/app.js"|src="js/app.js"|' app/src/main/assets/www/index.html
  fi
fi

chmod +x ./gradlew
./gradlew assembleDebug --no-daemon
mkdir -p dist
cp -f app/build/outputs/apk/debug/app-debug.apk dist/GrokOrgOS-1.1.0-debug.apk
echo "Built: $ROOT/dist/GrokOrgOS-1.1.0-debug.apk"

# Optional unsigned release
./gradlew assembleRelease --no-daemon || true
if [[ -f app/build/outputs/apk/release/app-release-unsigned.apk ]]; then
  cp -f app/build/outputs/apk/release/app-release-unsigned.apk dist/GrokOrgOS-1.1.0-release-unsigned.apk
  echo "Built: $ROOT/dist/GrokOrgOS-1.1.0-release-unsigned.apk"
elif [[ -f app/build/outputs/apk/release/app-release.apk ]]; then
  cp -f app/build/outputs/apk/release/app-release.apk dist/GrokOrgOS-1.1.0-release.apk
  echo "Built: $ROOT/dist/GrokOrgOS-1.1.0-release.apk"
fi

ls -lh dist/
