#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAYOUT="${1:-}"
MODE="${2:-}"
if [[ -z "$LAYOUT" ]]; then
  echo "Usage: run_fixed_layout_selector.sh <4|6|9|12> [windowed|fullscreen]" >&2
  exit 1
fi
if [[ -z "$MODE" ]]; then
  exec bash "$SCRIPT_DIR/run_layout${LAYOUT}_fixed.sh"
else
  exec bash "$SCRIPT_DIR/run_layout${LAYOUT}_${MODE}_fixed.sh"
fi
