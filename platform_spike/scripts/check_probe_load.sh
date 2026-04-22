#!/usr/bin/env bash
set -euo pipefail

WEB_LOG_DEFAULT="/mnt/d/opsmgr/Infovision Foresight/client/components/webcontainer.1/logs/webcontainer/webcontainer.webcontainer.debug.log"
CLIENT_LOG_DEFAULT="/mnt/d/opsmgr/Infovision Foresight/client/framework/infosightclient.1/logs/clientframe/clientframework.clientframe.debug.log"

WEB_LOG="${WEB_LOG:-$WEB_LOG_DEFAULT}"
CLIENT_LOG="${CLIENT_LOG:-$CLIENT_LOG_DEFAULT}"
PATTERN='platform_spike_probe|Parse Url:.*platform_spike_probe|createBrowserAsPopup with url:.*platform_spike_probe|createBrowserAsChild with url:.*platform_spike_probe|getWndHandle.*platform_spike_probe|ipoint_001'

usage() {
  cat <<EOF
Usage:
  $(basename "$0") once
  $(basename "$0") watch

Environment overrides:
  WEB_LOG="$WEB_LOG_DEFAULT"
  CLIENT_LOG="$CLIENT_LOG_DEFAULT"
EOF
}

require_logs() {
  [[ -f "$WEB_LOG" ]] || { echo "missing $WEB_LOG" >&2; exit 1; }
  [[ -f "$CLIENT_LOG" ]] || { echo "missing $CLIENT_LOG" >&2; exit 1; }
}

show_once() {
  echo "== client log =="
  rg -n "$PATTERN" "$CLIENT_LOG" -S | tail -n 40 || true
  echo
  echo "== webcontainer log =="
  rg -n "$PATTERN" "$WEB_LOG" -S | tail -n 40 || true
}

watch_logs() {
  echo "Watching:"
  echo "  $CLIENT_LOG"
  echo "  $WEB_LOG"
  echo
  tail -n 0 -F "$CLIENT_LOG" "$WEB_LOG" | rg --line-buffered "$PATTERN" -S
}

main() {
  require_logs
  case "${1:-}" in
    once)
      show_once
      ;;
    watch)
      watch_logs
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "${1:-}"
