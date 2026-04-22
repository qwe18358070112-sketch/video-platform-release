#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
printf '[fixed-layout] starting layout=4 mode=windowed on Windows runtime.\n'
exec "$REPO_ROOT/windows_bridge.sh" run --config fixed_layout_programs/config.layout4.windowed.yaml --layout 4 --mode windowed
