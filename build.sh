#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="${ANDROID_DIR:-$ROOT_DIR/android}"
BUILD_TYPE="${BUILD_TYPE:-Debug}"

if [[ ! -d "$ANDROID_DIR" ]]; then
  echo "Android project not found at: $ANDROID_DIR" >&2
  echo "Add/open the Quest Android project there, or run with ANDROID_DIR=/path/to/project ./build.sh" >&2
  exit 2
fi

cd "$ANDROID_DIR"
if [[ -x ./gradlew ]]; then
  ./gradlew "assemble${BUILD_TYPE}"
elif command -v gradle >/dev/null 2>&1; then
  gradle "assemble${BUILD_TYPE}"
else
  echo "Gradle was not found. Install Android Studio/Gradle or include android/gradlew." >&2
  exit 2
fi

apk="$(find . -path "*/build/outputs/apk/*/*.apk" -type f | sort | tail -n 1)"
if [[ -z "$apk" ]]; then
  echo "Build finished, but no APK was found under build/outputs/apk." >&2
  exit 3
fi
mkdir -p "$ROOT_DIR/dist"
cp "$apk" "$ROOT_DIR/dist/WiiQuest-${BUILD_TYPE}.apk"
echo "APK copied to $ROOT_DIR/dist/WiiQuest-${BUILD_TYPE}.apk"
