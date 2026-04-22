#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAYOUT="${1:-}"
MODE="${2:-}"
if [[ -z "$LAYOUT" ]]; then
  echo "Usage: stop_fixed_layout_selector.sh <4|6|9|12> [windowed|fullscreen]" >&2
  exit 1
fi
ARGS=(--layout "$LAYOUT" --include-legacy-lock)
if [[ -n "$MODE" ]]; then
  ARGS+=(--mode "$MODE")
fi
exec python3 "$REPO_ROOT/platform_spike/scripts/stop_fixed_layout_runtime.py" "${ARGS[@]}"
