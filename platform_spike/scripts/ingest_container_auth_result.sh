#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ANALYZE_PY="${SCRIPT_DIR}/analyze_container_auth_result.py"
REVIEW_PY="${SCRIPT_DIR}/review_container_auth_result.py"
PACKAGE_PY="${SCRIPT_DIR}/package_container_auth_result.py"

INPUT_PATH="${1:-}"

if [ -z "$INPUT_PATH" ]; then
  tmp_input="$(mktemp)"
  cat > "$tmp_input"
  INPUT_PATH="$tmp_input"
fi

analyze_output="$(python3 "$ANALYZE_PY" "$INPUT_PATH")"
printf '%s\n' "$analyze_output"

result_dir="$(printf '%s\n' "$analyze_output" | python3 -c 'import json,sys; print(json.load(sys.stdin)["resultDir"])')"

review_output="$(python3 "$REVIEW_PY" "$result_dir")"
printf '%s\n' "$review_output"

package_output="$(python3 "$PACKAGE_PY" "$result_dir")"
printf '%s\n' "$package_output"

zip_path="$(printf '%s\n' "$package_output" | python3 -c 'import json,sys; print(json.load(sys.stdin)["zipPath"])')"

printf '\n=== CONTAINER_AUTH_OPERATOR_RESULT ===\n'
printf 'LATEST_CONTAINER_AUTH_RESULT_DIR=%s\n' "$result_dir"
printf 'LATEST_CONTAINER_AUTH_RESULT_ZIP=%s\n' "$zip_path"
if [ -f "$result_dir/operator_packet.txt" ]; then
  printf 'OPERATOR_PACKET_START\n'
  cat "$result_dir/operator_packet.txt"
  printf 'OPERATOR_PACKET_END\n'
fi
if [ -f "$result_dir/operator_review.txt" ]; then
  printf 'OPERATOR_REVIEW_START\n'
  cat "$result_dir/operator_review.txt"
  printf '\nOPERATOR_REVIEW_END\n'
fi

if [[ "${1:-}" == "" ]]; then
  rm -f "$INPUT_PATH"
fi
