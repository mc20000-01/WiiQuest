#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APK="${APK:-$ROOT_DIR/dist/WiiQuest-Debug.apk}"
QUEST_IP="${QUEST_IP:-}"
PACKAGE="${PACKAGE:-}"
PYTHON="${PYTHON:-python3}"
PORT="${PORT:-50123}"
HZ="${HZ:-60}"

if [[ ! -f "$APK" ]]; then
  echo "APK not found at $APK. Run ./build.sh first or set APK=/path/app.apk." >&2
  exit 2
fi
if ! command -v adb >/dev/null 2>&1; then
  echo "adb was not found. Install Android platform-tools and enable Quest developer mode." >&2
  exit 2
fi
if [[ -z "$QUEST_IP" ]]; then
  QUEST_IP="$(adb shell ip -o -4 addr show wlan0 2>/dev/null | awk '{split($4,a,"/"); print a[1]; exit}' | tr -d '\r')"
fi
if [[ -z "$QUEST_IP" ]]; then
  echo "Could not detect Quest IP. Set QUEST_IP=192.168.x.x ./run.sh" >&2
  exit 2
fi

adb install -r "$APK"
if [[ -n "$PACKAGE" ]]; then
  adb shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1 >/dev/null
else
  echo "PACKAGE is not set, so the APK was installed but not auto-launched."
  echo "Example: PACKAGE=com.example.wiiquest ./run.sh"
fi

exec "$PYTHON" "$ROOT_DIR/bridge/wbb_bridge.py" "$QUEST_IP" --port "$PORT" --hz "$HZ" "$@"
