#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  echo "[ERROR] Missing .venv. Run ./install_deps.sh first."
  exit 1
fi

. .venv/bin/activate
python self_test.py "$@"
