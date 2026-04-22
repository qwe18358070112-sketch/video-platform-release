#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR"

usage() {
  cat <<'EOF'
Usage:
  ./windows_bridge.sh sync
  ./windows_bridge.sh install-deps
  ./windows_bridge.sh self-test
  ./windows_bridge.sh build-release [build_release.py args...]
  ./windows_bridge.sh run [app.py args...]
  ./windows_bridge.sh calibrate windowed|fullscreen [app.py args...]
  ./windows_bridge.sh inspect-calibration windowed|fullscreen [app.py args...]
  ./windows_bridge.sh inspect-runtime [app.py args...]
  ./windows_bridge.sh dump-favorites [app.py args...]
  ./windows_bridge.sh switch-layout 4|6|9|12|13 [app.py args...]
  ./windows_bridge.sh native-probe [native probe args...]

Environment:
  VIDEO_PLATFORM_WINDOWS_WORKDIR  WSL path or Windows path for the synced runtime copy
  VIDEO_PLATFORM_ALLOW_AUTO_ELEVATE=1  Pass through the app's auto-elevate behavior
EOF
}

normalize_windows_workdir() {
  local raw="${1:-}"
  if [[ -z "$raw" ]]; then
    return 1
  fi

  case "$raw" in
    [A-Za-z]:\\*|[A-Za-z]:/*)
      wslpath -u "$raw"
      ;;
    *)
      printf '%s\n' "$raw"
      ;;
  esac
}

default_windows_workdir() {
  if [[ -d /mnt/d ]]; then
    printf '%s\n' "/mnt/d/video_platform_release_windows_runtime"
    return 0
  fi
  if [[ -d /mnt/c ]]; then
    printf '%s\n' "/mnt/c/video_platform_release_windows_runtime"
    return 0
  fi
  return 1
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

ACTION="$1"
shift

if [[ -n "${VIDEO_PLATFORM_WINDOWS_WORKDIR:-}" ]]; then
  WINDOWS_WORKDIR="$(normalize_windows_workdir "$VIDEO_PLATFORM_WINDOWS_WORKDIR")"
else
  WINDOWS_WORKDIR="$(default_windows_workdir)" || {
    echo "[ERROR] Could not determine a Windows work directory. Set VIDEO_PLATFORM_WINDOWS_WORKDIR." >&2
    exit 1
  }
fi

WINDOWS_WORKDIR="${WINDOWS_WORKDIR%/}"
WINDOWS_REPO_PATH=""

ensure_windows_workdir() {
  mkdir -p "$WINDOWS_WORKDIR"
}

sync_repo_to_windows() {
  ensure_windows_workdir

  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude '.git/' \
      --exclude '.venv/' \
      --exclude '__pycache__/' \
      --exclude 'dist/' \
      --exclude 'logs/' \
      --exclude 'tmp/' \
      "$SOURCE_DIR/" "$WINDOWS_WORKDIR/"
  else
    find "$WINDOWS_WORKDIR" -mindepth 1 -maxdepth 1 \
      ! -name '.venv' \
      ! -name 'dist' \
      ! -name 'logs' \
      ! -name 'tmp' \
      -exec rm -rf {} +
    tar -C "$SOURCE_DIR" \
      --exclude='.git' \
      --exclude='.venv' \
      --exclude='__pycache__' \
      --exclude='dist' \
      --exclude='logs' \
      --exclude='tmp' \
      -cf - . | tar -C "$WINDOWS_WORKDIR" -xf -
  fi
}

pull_runtime_artifacts_back() {
  local item

  if [[ -f "$WINDOWS_WORKDIR/config.yaml" ]]; then
    cp -f "$WINDOWS_WORKDIR/config.yaml" "$SOURCE_DIR/config.yaml"
  fi

  for item in logs tmp dist; do
    if [[ -d "$WINDOWS_WORKDIR/$item" ]]; then
      mkdir -p "$SOURCE_DIR/$item"
      if command -v rsync >/dev/null 2>&1; then
        rsync -a "$WINDOWS_WORKDIR/$item/" "$SOURCE_DIR/$item/"
      else
        cp -a "$WINDOWS_WORKDIR/$item/." "$SOURCE_DIR/$item/"
      fi
    fi
  done
}

ensure_windows_repo_path() {
  WINDOWS_REPO_PATH="$(wslpath -w "$WINDOWS_WORKDIR")"
}

run_windows_bridge() {
  local ps_args=(
    -NoProfile
    -ExecutionPolicy Bypass
    -File "$WINDOWS_REPO_PATH\\windows_bridge.ps1"
    -RepoPath "$WINDOWS_REPO_PATH"
    -Action "$ACTION"
  )

  if [[ "${VIDEO_PLATFORM_ALLOW_AUTO_ELEVATE:-0}" == "1" ]]; then
    ps_args+=(-AllowAutoElevate)
  fi

  if [[ $# -gt 0 ]]; then
    ps_args+=("$@")
  fi

  powershell.exe "${ps_args[@]}"
}

case "$ACTION" in
  sync)
    sync_repo_to_windows
    echo "[OK] Synced WSL source to $WINDOWS_WORKDIR"
    ;;
  install-deps|self-test|build-release|run|calibrate|inspect-calibration|inspect-runtime|dump-favorites|switch-layout|native-probe)
    sync_repo_to_windows
    ensure_windows_repo_path
    status=0
    if run_windows_bridge "$@"; then
      status=0
    else
      status=$?
    fi
    pull_runtime_artifacts_back
    exit "$status"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "[ERROR] Unknown action: $ACTION" >&2
    usage
    exit 1
    ;;
esac
