#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
if [[ ! -x "$JAVA_HOME/bin/java" ]]; then
  if command -v java >/dev/null 2>&1; then
    export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")"
  fi
fi
export ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/workspace/android-sdk}}"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"

if [[ ! -f local.properties ]]; then
  echo "sdk.dir=$ANDROID_HOME" > local.properties
fi

# Sync bundled www assets from Python static (keep /static/ paths for on-device server)
STATIC_SRC="$ROOT/../grok_org_os/static"
if [[ -d "$STATIC_SRC" ]]; then
  mkdir -p app/src/main/assets/www/css app/src/main/assets/www/js
  cp -a "$STATIC_SRC/css/." app/src/main/assets/www/css/
  cp -a "$STATIC_SRC/js/." app/src/main/assets/www/js/
  if [[ -f "$STATIC_SRC/index.html" ]]; then
    cp "$STATIC_SRC/index.html" app/src/main/assets/www/index.html
  fi
fi

VERSION_NAME="2.1.1"

chmod +x ./gradlew
./gradlew assembleDebug --no-daemon
mkdir -p dist
cp -f app/build/outputs/apk/debug/app-debug.apk "dist/GrokOrgOS-${VERSION_NAME}-debug.apk"
echo "Built: $ROOT/dist/GrokOrgOS-${VERSION_NAME}-debug.apk"

./gradlew assembleRelease --no-daemon || true
if [[ -f app/build/outputs/apk/release/app-release-unsigned.apk ]]; then
  cp -f app/build/outputs/apk/release/app-release-unsigned.apk "dist/GrokOrgOS-${VERSION_NAME}-release-unsigned.apk"
  echo "Built: $ROOT/dist/GrokOrgOS-${VERSION_NAME}-release-unsigned.apk"
elif [[ -f app/build/outputs/apk/release/app-release.apk ]]; then
  cp -f app/build/outputs/apk/release/app-release.apk "dist/GrokOrgOS-${VERSION_NAME}-release.apk"
  echo "Built: $ROOT/dist/GrokOrgOS-${VERSION_NAME}-release.apk"
fi

ls -lh dist/
