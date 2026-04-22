#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PS1_PATH="$(wslpath -w "${SCRIPT_DIR}/platform_quick_capture_bundle.ps1")"
ANALYZE_PY="${SCRIPT_DIR}/analyze_live_probe_bundle.py"
PACKAGE_PY="${SCRIPT_DIR}/package_live_probe_bundle.py"
REVIEW_PY="${SCRIPT_DIR}/review_live_probe_bundle.py"
AUTH_CONTEXT_PY="${SCRIPT_DIR}/analyze_clientframe_auth_context.py"

convert_wsl_unc_to_posix() {
  python3 - "$1" <<'PY'
import re
import subprocess
import sys

path = sys.argv[1].strip()
if re.match(r"^\\\\wsl\.localhost\\[^\\]+\\", path, re.I):
    path = re.sub(r"^\\\\wsl\.localhost\\[^\\]+", "", path, flags=re.I)
    print(path.replace("\\", "/"))
elif re.match(r"^[A-Za-z]:\\", path):
    completed = subprocess.run(["wslpath", "-u", path], capture_output=True, text=True, check=False)
    if completed.returncode == 0:
        print(completed.stdout.strip())
    else:
        print(path)
else:
    print(path)
PY
}

read_text_file() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)
print(path.read_text(encoding="utf-8-sig").strip())
PY
}

read_json_field() {
  python3 - "$1" "$2" <<'PY'
from pathlib import Path
import json
import sys

path = Path(sys.argv[1])
key_path = sys.argv[2].split(".")
if not path.exists():
    raise SystemExit(0)
value = json.loads(path.read_text(encoding="utf-8-sig"))
for part in key_path:
    if isinstance(value, dict):
        value = value.get(part)
    else:
        value = None
        break
if value is None:
    raise SystemExit(0)
if isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False))
else:
    print(str(value))
PY
}

printf '[platform_spike] quick capture started, this may take 30-90 seconds depending on logs and network.\n'
printf '[platform_spike] stage=probe\n'
output="$(powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${PS1_PATH}" "$@" | tr -d '\r')"
status=$?
printf '%s\n' "$output"
if [ $status -ne 0 ]; then
  exit $status
fi

bundle_dir_raw="$(printf '%s\n' "$output" | sed -n 's/^BUNDLE_DIR=//p' | tail -n 1)"
if [ -n "$bundle_dir_raw" ]; then
  bundle_dir="$(convert_wsl_unc_to_posix "$bundle_dir_raw")"
  summary_json="$bundle_dir/bundle_summary.json"
  if [ -d "$bundle_dir" ] && [ -f "$AUTH_CONTEXT_PY" ] && [ -f "$summary_json" ]; then
    clientframe_log_raw="$(read_json_field "$summary_json" clientFrameLogPath)"
    date_prefix="$(read_json_field "$summary_json" datePrefix)"
    if [ -n "$clientframe_log_raw" ]; then
      clientframe_log="$(convert_wsl_unc_to_posix "$clientframe_log_raw")"
      if [ -f "$clientframe_log" ]; then
        python3 "$AUTH_CONTEXT_PY" "$clientframe_log" --date-prefix "$date_prefix" --output "$bundle_dir/clientframe_auth_context.json" >/dev/null
      fi
    fi
  fi
  if [ -d "$bundle_dir" ] && [ -f "$ANALYZE_PY" ]; then
    python3 "$ANALYZE_PY" "$bundle_dir"
  fi
  if [ -d "$bundle_dir" ] && [ -f "$REVIEW_PY" ]; then
    python3 "$REVIEW_PY" "$bundle_dir"
  fi
  if [ -d "$bundle_dir" ] && [ -f "$PACKAGE_PY" ]; then
    python3 "$PACKAGE_PY" "$bundle_dir"
  fi
  bundle_root="$(dirname "$bundle_dir")"
  latest_bundle_zip="$(read_text_file "${bundle_root}/latest_bundle_zip.txt")"
  printf '\n=== OPERATOR_RESULT ===\n'
  printf 'LATEST_BUNDLE_DIR=%s\n' "$bundle_dir"
  if [ -n "$latest_bundle_zip" ]; then
    printf 'LATEST_BUNDLE_ZIP=%s\n' "$latest_bundle_zip"
  fi
  if [ -f "$bundle_dir/operator_packet.txt" ]; then
    printf 'OPERATOR_PACKET_START\n'
    cat "$bundle_dir/operator_packet.txt"
    printf 'OPERATOR_PACKET_END\n'
  fi
  if [ -f "$bundle_dir/operator_review.txt" ]; then
    printf 'OPERATOR_REVIEW_START\n'
    cat "$bundle_dir/operator_review.txt"
    printf '\nOPERATOR_REVIEW_END\n'
  fi
fi
