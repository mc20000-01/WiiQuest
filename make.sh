#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$ROOT_DIR/android"
GRADLE_VERSION="8.7"
ANDROID_COMPILE_SDK="34"
ANDROID_BUILD_TOOLS="34.0.0"
ANDROID_CMDLINE_TOOLS_URL="https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
ANDROID_SDK_ROOT_DEFAULT="$HOME/Android/Sdk"

log() { printf '\n==> %s\n' "$*"; }
warn() { printf '\nWARNING: %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

install_packages() {
  local packages=("$@")
  if ((${#packages[@]} == 0)); then
    return 0
  fi

  if have pacman; then
    log "Installing packages with pacman: ${packages[*]}"
    sudo pacman -S --needed --noconfirm "${packages[@]}"
  elif have apt-get; then
    log "Installing packages with apt-get: ${packages[*]}"
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"
  elif have dnf; then
    log "Installing packages with dnf: ${packages[*]}"
    sudo dnf install -y "${packages[@]}"
  elif have brew; then
    log "Installing packages with brew: ${packages[*]}"
    brew install "${packages[@]}"
  else
    warn "No supported package manager found. Please install: ${packages[*]}"
    return 1
  fi
}

ensure_basic_tools() {
  local missing=()
  for tool in curl unzip; do
    have "$tool" || missing+=("$tool")
  done
  if ((${#missing[@]})); then
    install_packages "${missing[@]}"
  fi
}

ensure_jdk() {
  if have java && java -version 2>&1 | grep -Eq 'version "(17|1[8-9]|[2-9][0-9])'; then
    return 0
  fi

  log "Java 17+ was not found; installing a JDK"
  if have pacman; then
    install_packages jdk17-openjdk
  elif have apt-get; then
    install_packages openjdk-17-jdk
  elif have dnf; then
    install_packages java-17-openjdk-devel
  elif have brew; then
    install_packages openjdk@17
    export PATH="$(brew --prefix openjdk@17)/bin:$PATH"
  else
    warn "Please install JDK 17 or newer and rerun this script."
    exit 1
  fi
}

ensure_gradle() {
  if have gradle; then
    return 0
  fi

  log "Gradle was not found; installing Gradle"
  if have pacman; then
    install_packages gradle
  elif have apt-get; then
    install_packages gradle
  elif have dnf; then
    install_packages gradle
  elif have brew; then
    install_packages gradle
  else
    local gradle_home="$ROOT_DIR/.gradle-dist/gradle-$GRADLE_VERSION"
    mkdir -p "$ROOT_DIR/.gradle-dist"
    curl -L "https://services.gradle.org/distributions/gradle-$GRADLE_VERSION-bin.zip" -o "$ROOT_DIR/.gradle-dist/gradle.zip"
    unzip -q -o "$ROOT_DIR/.gradle-dist/gradle.zip" -d "$ROOT_DIR/.gradle-dist"
    export PATH="$gradle_home/bin:$PATH"
  fi
}

ensure_android_sdk() {
  export ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$ANDROID_SDK_ROOT_DEFAULT}}"
  export ANDROID_SDK_ROOT="$ANDROID_HOME"
  local sdkmanager="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"

  if [[ ! -x "$sdkmanager" ]]; then
    log "Android command-line tools were not found; installing into $ANDROID_HOME"
    ensure_basic_tools
    mkdir -p "$ANDROID_HOME/cmdline-tools"
    local zipfile="$ANDROID_HOME/cmdline-tools.zip"
    curl -L "$ANDROID_CMDLINE_TOOLS_URL" -o "$zipfile"
    rm -rf "$ANDROID_HOME/cmdline-tools/latest" "$ANDROID_HOME/cmdline-tools/cmdline-tools"
    unzip -q "$zipfile" -d "$ANDROID_HOME/cmdline-tools"
    mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
    rm -f "$zipfile"
  fi

  log "Accepting Android SDK licenses"
  yes | "$sdkmanager" --licenses >/dev/null || true

  log "Installing Android SDK platform/build tools"
  "$sdkmanager" \
    "platform-tools" \
    "platforms;android-$ANDROID_COMPILE_SDK" \
    "build-tools;$ANDROID_BUILD_TOOLS"
}

ensure_gradle_wrapper() {
  if [[ -x "$ANDROID_DIR/gradlew" && -f "$ANDROID_DIR/gradle/wrapper/gradle-wrapper.jar" ]]; then
    return 0
  fi

  log "Creating local Gradle wrapper in android/"
  (cd "$ANDROID_DIR" && gradle wrapper --gradle-version "$GRADLE_VERSION" --distribution-type bin)
}

build_android() {
  log "Building Android debug APK"
  (cd "$ANDROID_DIR" && ./gradlew assembleDebug)
}

main() {
  if [[ ! -d "$ANDROID_DIR" ]]; then
    warn "Android project directory not found: $ANDROID_DIR"
    exit 1
  fi

  ensure_basic_tools
  ensure_jdk
  ensure_gradle
  ensure_android_sdk
  ensure_gradle_wrapper
  build_android

  log "Done. APK output should be under android/app/build/outputs/apk/debug/."
}

main "$@"
