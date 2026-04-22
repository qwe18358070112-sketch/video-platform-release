#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PS1_PATH="$(wslpath -w "${SCRIPT_DIR}/platform_live_probe.ps1")"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${PS1_PATH}" "$@"
