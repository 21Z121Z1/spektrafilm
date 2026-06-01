#!/bin/zsh -f
set -euo pipefail

MODE="${1:-run}"
APP_NAME="SpektrafilmMac"
BUNDLE_ID="org.spektrafilm.mac"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$ROOT_DIR/macos/SpektrafilmMac"
XCODE_PROJECT="$APP_DIR/SpektrafilmMac.xcodeproj"
DERIVED_DATA="$APP_DIR/DerivedData"
DIST_DIR="$APP_DIR/dist"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
APP_BINARY="$APP_BUNDLE/Contents/MacOS/$APP_NAME"
BUILT_APP="$DERIVED_DATA/Build/Products/Debug/$APP_NAME.app"

app_is_running() {
  local pid
  local proc_status
  for pid in $(pgrep -x "$APP_NAME" 2>/dev/null || true) $(pgrep -f "$APP_BINARY" 2>/dev/null || true); do
    proc_status="$(ps -o stat= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
    if [[ -n "$proc_status" && "$proc_status" != *E* && "$proc_status" != *Z* ]]; then
      return 0
    fi
  done
  return 1
}

wait_for_app_exit() {
  for _ in {1..20}; do
    if ! app_is_running; then
      return 0
    fi
    sleep 0.25
  done
  return 0
}

pkill -x "$APP_NAME" >/dev/null 2>&1 || true
pkill -f "$APP_BINARY" >/dev/null 2>&1 || true
wait_for_app_exit

swift build --package-path "$APP_DIR"
BUILD_BINARY="$(swift build --package-path "$APP_DIR" --show-bin-path)/$APP_NAME"

find_sign_identity() {
  if [[ -n "${SPEKTRAFILM_CODESIGN_IDENTITY:-}" ]]; then
    printf '%s\n' "$SPEKTRAFILM_CODESIGN_IDENTITY"
    return 0
  fi
  security find-identity -v -p codesigning 2>/dev/null | awk -F '"' '/Apple Development/ { print $2; exit }'
}

sign_executable_for_local_run() {
  local binary="$1"
  local identity
  identity="$(find_sign_identity || true)"
  if [[ -n "$identity" ]]; then
    codesign --force --sign "$identity" --timestamp=none "$binary" >/dev/null
  else
    echo "warning: no Apple Development signing identity found; local self-check binary may be rejected by macOS" >&2
    codesign --force --sign - --timestamp=none "$binary" >/dev/null 2>&1 || true
  fi
}

xcodegen generate --spec "$APP_DIR/project.yml" --project "$APP_DIR" >/dev/null
rm -rf "$DERIVED_DATA"
xcodebuild \
  -quiet \
  -project "$XCODE_PROJECT" \
  -scheme "$APP_NAME" \
  -configuration Debug \
  -derivedDataPath "$DERIVED_DATA" \
  SPEKTRAFILM_REPO_ROOT="$ROOT_DIR" \
  build

rm -rf "$APP_BUNDLE"
mkdir -p "$DIST_DIR"
ditto "$BUILT_APP" "$APP_BUNDLE"
find "$APP_BUNDLE" -exec xattr -c {} + >/dev/null 2>&1 || true

open_app() {
  if ! /usr/bin/open -n "$APP_BUNDLE" >/dev/null 2>&1; then
    echo "error: failed to ask LaunchServices to open $APP_BUNDLE" >&2
    return 1
  fi
  for _ in {1..60}; do
    if app_is_running; then
      return 0
    fi
    sleep 0.5
  done
  echo "error: $APP_NAME did not stay running after LaunchServices open" >&2
  /usr/bin/log show --last 1m --style compact --predicate "process == \"$APP_NAME\" || eventMessage CONTAINS[c] \"$APP_NAME\"" 2>/dev/null | tail -n 40 >&2 || true
  return 1
}

case "$MODE" in
  run)
    open_app
    ;;
  --debug|debug)
    lldb -- "$APP_BINARY"
    ;;
  --logs|logs)
    open_app
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\""
    ;;
  --telemetry|telemetry)
    open_app
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\""
    ;;
  --verify|verify)
    sign_executable_for_local_run "$BUILD_BINARY"
    SPEKTRAFILM_REPO_ROOT="$ROOT_DIR" "$BUILD_BINARY" --self-check
    open_app
    app_is_running
    ;;
  *)
    echo "usage: $0 [run|--debug|--logs|--telemetry|--verify]" >&2
    exit 2
    ;;
esac
