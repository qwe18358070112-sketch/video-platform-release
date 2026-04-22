#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

pick_python() {
  local candidate
  for candidate in python3.12 python3.11 python3; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] in {(3, 11), (3, 12)} else 1)'; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

bootstrap_virtualenv() {
  local bootstrap_script
  bootstrap_script="$(mktemp)"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$bootstrap_script"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$bootstrap_script" https://bootstrap.pypa.io/get-pip.py
  else
    echo "[ERROR] Missing curl/wget, cannot bootstrap pip."
    return 1
  fi

  "$PYTHON_BIN" "$bootstrap_script" --user --break-system-packages
  "$PYTHON_BIN" -m pip install --user --break-system-packages virtualenv
  rm -f "$bootstrap_script"
}

create_virtualenv() {
  if "$PYTHON_BIN" -m venv .venv; then
    return 0
  fi

  echo "[WARN] Built-in venv is unavailable. Bootstrapping pip + virtualenv..."
  rm -rf .venv
  bootstrap_virtualenv
  "$PYTHON_BIN" -m virtualenv .venv
}

PYTHON_BIN="$(pick_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "[ERROR] Python 3.11 or 3.12 is required."
  exit 1
fi

if [[ -d .venv && ( ! -x .venv/bin/python || ! -f .venv/bin/activate ) ]]; then
  echo "[WARN] Removing incomplete virtual environment left by a previous failed setup..."
  rm -rf .venv
fi

if [[ -x .venv/bin/python ]]; then
  if ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info[:2] in {(3, 11), (3, 12)} else 1)'; then
    echo "[WARN] Existing virtual environment uses an unsupported Python version. Recreating .venv..."
    rm -rf .venv
  fi
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "[INFO] Creating virtual environment with $PYTHON_BIN..."
  create_virtualenv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "[OK] Dependencies installed."
echo "[INFO] WSL/Linux can run self_test.py and build_release.py."
echo "[INFO] Runtime commands in app.py still require Windows."
