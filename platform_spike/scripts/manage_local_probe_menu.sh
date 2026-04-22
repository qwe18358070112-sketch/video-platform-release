#!/usr/bin/env bash
set -euo pipefail

PRODUCT_DIR_DEFAULT="/mnt/d/opsmgr/Infovision Foresight/client/product"
PRODUCT_DIR="${PRODUCT_DIR:-$PRODUCT_DIR_DEFAULT}"
MENU_FILE="$PRODUCT_DIR/META-INF/menus.xml"
TRANSLATE_FILE="$PRODUCT_DIR/META-INF/language/zh_CN/translate.properties"
ICON_DIR="$PRODUCT_DIR/META-INF/icon/menu"
BACKUP_DIR="$PRODUCT_DIR/META-INF/.platform_spike_backup"

PROBE_CODE="platform_spike_probe"
PROBE_MENU_ID="platform_spike_probe_001"
PROBE_URL="${PROBE_URL:-http://127.0.0.1:36753/platform_spike_probe/index.html}"
POC_URL="${POC_URL:-http://127.0.0.1:36753/platform_spike_probe/platform_spike_poc.html?autorun=1}"
VIDEO_MONITOR_CODE="client0101"
VIDEO_MONITOR_REF_ID="vsclient"
VIDEO_MONITOR_MENU_ID="client0101"
PROBE_DISPLAY_NAME="${PROBE_DISPLAY_NAME:-平台联调探针}"
PROBE_DESCRIPTION="${PROBE_DESCRIPTION:-本地 OpenAPI 与预览链路联调页}"

usage() {
  cat <<EOF
Usage:
  $(basename "$0") install
  $(basename "$0") install-ipoint-slot
  $(basename "$0") install-ipoint-poc-slot
  $(basename "$0") install-video-monitor-poc-slot
  $(basename "$0") remove
  $(basename "$0") status

Environment overrides:
  PRODUCT_DIR=/mnt/d/opsmgr/Infovision Foresight/client/product
  PROBE_URL=http://127.0.0.1:36753/platform_spike_probe/index.html
  POC_URL=http://127.0.0.1:36753/platform_spike_probe/platform_spike_poc.html?autorun=1
  PROBE_DISPLAY_NAME=平台联调探针
  PROBE_DESCRIPTION=本地 OpenAPI 与预览链路联调页
EOF
}

require_files() {
  [[ -f "$MENU_FILE" ]] || { echo "missing $MENU_FILE" >&2; exit 1; }
  [[ -f "$TRANSLATE_FILE" ]] || { echo "missing $TRANSLATE_FILE" >&2; exit 1; }
  [[ -d "$ICON_DIR" ]] || { echo "missing $ICON_DIR" >&2; exit 1; }
}

ensure_backup_dir() {
  mkdir -p "$BACKUP_DIR"
}

backup_once() {
  ensure_backup_dir
  [[ -f "$BACKUP_DIR/menus.xml.orig" ]] || cp "$MENU_FILE" "$BACKUP_DIR/menus.xml.orig"
  [[ -f "$BACKUP_DIR/translate.properties.orig" ]] || cp "$TRANSLATE_FILE" "$BACKUP_DIR/translate.properties.orig"
}

probe_present() {
  grep -q "code=\"$PROBE_CODE\"" "$MENU_FILE"
}

ipoint_redirected() {
  grep -q 'code="ipoint".*127.0.0.1:36753/platform_spike_probe/' "$MENU_FILE"
}

video_monitor_redirected() {
  grep -q 'code="client0101".*127.0.0.1:36753/platform_spike_probe/' "$MENU_FILE"
}

install_menu() {
  backup_once
  python3 - "$MENU_FILE" "$PROBE_CODE" "$PROBE_MENU_ID" "$PROBE_URL" <<'PY'
import json
import sys
import xml.etree.ElementTree as ET

menu_file, probe_code, probe_menu_id, probe_url = sys.argv[1:5]
ns_uri = "http://www.hikvision.com/compomentModel/0.5.0/menus"
ns = {"m": ns_uri}
ET.register_namespace("", ns_uri)

tree = ET.parse(menu_file)
root = tree.getroot()
video = root.find(".//m:menu[@code='video']", ns)
if video is None:
    raise SystemExit("video menu not found")
existing = video.find(f"./m:menu[@code='{probe_code}']", ns)
payload = json.dumps(
    {
        "componentId": probe_code,
        "componentMenuId": probe_menu_id,
        "url": probe_url,
    },
    ensure_ascii=False,
    separators=(",", ":"),
)
if existing is None:
    entry = ET.Element(f"{{{ns_uri}}}menu")
    entry.set("code", probe_code)
    entry.set("type", "external")
    entry.set("url", payload)
    entry.set("sort", "13")
    entry.set("openType", "embed")
    inserted = False
    for index, child in enumerate(list(video)):
        if child.get("code") == "ipoint":
            video.insert(index + 1, entry)
            inserted = True
            break
    if not inserted:
        video.append(entry)
else:
    existing.set("url", payload)
tree.write(menu_file, encoding="UTF-8", xml_declaration=True)
PY
}

install_translations() {
  backup_once
  python3 - "$TRANSLATE_FILE" "$PROBE_CODE" "$PROBE_MENU_ID" "$PROBE_DISPLAY_NAME" "$PROBE_DESCRIPTION" <<'PY'
import sys
from pathlib import Path

translate_file, probe_code, probe_menu_id, display_name, description = sys.argv[1:6]
path = Path(translate_file)
lines = path.read_text(encoding="utf-8").splitlines()

required = {
    f"menu.{probe_code}.displayName": display_name,
    f"menu.{probe_code}.description": description,
    f"menu.{probe_menu_id}.displayName": display_name,
    f"menu.{probe_menu_id}.description": description,
}

existing = {}
for idx, line in enumerate(lines):
    if "=" not in line or line.startswith("#"):
        continue
    key, _value = line.split("=", 1)
    existing[key] = idx

for key, value in required.items():
    formatted = f"{key}={value}"
    if key in existing:
        lines[existing[key]] = formatted
    else:
        lines.append(formatted)

path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

install_icon() {
  local source_icon="$ICON_DIR/Infovision Foresight_ipoint.png"
  local target_icon="$ICON_DIR/Infovision Foresight_${PROBE_CODE}.png"
  if [[ -f "$source_icon" ]] && [[ ! -f "$target_icon" ]]; then
    cp "$source_icon" "$target_icon"
  fi
}

install_ipoint_slot() {
  backup_once
  python3 - "$MENU_FILE" "$PROBE_URL" <<'PY'
import json
import sys
import xml.etree.ElementTree as ET

menu_file, probe_url = sys.argv[1:3]
ns_uri = "http://www.hikvision.com/compomentModel/0.5.0/menus"
ns = {"m": ns_uri}
ET.register_namespace("", ns_uri)

tree = ET.parse(menu_file)
root = tree.getroot()
ipoint = root.find(".//m:menu[@code='ipoint']", ns)
if ipoint is None:
    raise SystemExit("ipoint menu not found")
payload = json.loads(ipoint.get("url"))
payload["url"] = probe_url
ipoint.set("url", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
tree.write(menu_file, encoding="UTF-8", xml_declaration=True)
PY
}

restore_original_slot() {
  local code="$1"
  if [[ ! -f "$BACKUP_DIR/menus.xml.orig" ]]; then
    return
  fi
  python3 - "$MENU_FILE" "$BACKUP_DIR/menus.xml.orig" "$code" <<'PY'
import sys
import xml.etree.ElementTree as ET

menu_file, backup_file, code = sys.argv[1:4]
ns_uri = "http://www.hikvision.com/compomentModel/0.5.0/menus"
ns = {"m": ns_uri}
ET.register_namespace("", ns_uri)

current_tree = ET.parse(menu_file)
current_root = current_tree.getroot()
backup_root = ET.parse(backup_file).getroot()

current_parent = current_root.find(".//m:menu[@code='video']", ns)
backup_parent = backup_root.find(".//m:menu[@code='video']", ns)
if current_parent is None or backup_parent is None:
    raise SystemExit("video menu not found")

backup_node = backup_parent.find(f"./m:menu[@code='{code}']", ns)
if backup_node is None:
    raise SystemExit(f"backup node not found for {code}")

for index, child in enumerate(list(current_parent)):
    if child.get("code") == code:
        current_parent.remove(child)
        current_parent.insert(index, backup_node)
        current_tree.write(menu_file, encoding="UTF-8", xml_declaration=True)
        break
else:
    current_parent.append(backup_node)
    current_tree.write(menu_file, encoding="UTF-8", xml_declaration=True)
PY
}

install_video_monitor_slot() {
  backup_once
  python3 - "$MENU_FILE" "$VIDEO_MONITOR_CODE" "$VIDEO_MONITOR_MENU_ID" "$POC_URL" <<'PY'
import json
import sys
import xml.etree.ElementTree as ET

menu_file, menu_code, menu_id, target_url = sys.argv[1:5]
ns_uri = "http://www.hikvision.com/compomentModel/0.5.0/menus"
ns = {"m": ns_uri}
ET.register_namespace("", ns_uri)

tree = ET.parse(menu_file)
root = tree.getroot()
node = root.find(f".//m:menu[@code='{menu_code}']", ns)
if node is None:
    raise SystemExit(f"{menu_code} menu not found")

payload = json.dumps(
    {
        "componentId": menu_code,
        "componentMenuId": menu_id,
        "url": target_url,
    },
    ensure_ascii=False,
    separators=(",", ":"),
)

node.attrib.clear()
node.set("code", menu_code)
node.set("type", "external")
node.set("url", payload)
node.set("sort", "10")
node.set("openType", "embed")

tree.write(menu_file, encoding="UTF-8", xml_declaration=True)
PY
}

remove_menu() {
  if [[ -f "$BACKUP_DIR/menus.xml.orig" ]]; then
    cp "$BACKUP_DIR/menus.xml.orig" "$MENU_FILE"
    return
  fi
  python3 - "$MENU_FILE" "$PROBE_CODE" <<'PY'
import sys
import xml.etree.ElementTree as ET

menu_file, probe_code = sys.argv[1:3]
ns_uri = "http://www.hikvision.com/compomentModel/0.5.0/menus"
ns = {"m": ns_uri}
ET.register_namespace("", ns_uri)
tree = ET.parse(menu_file)
root = tree.getroot()
video = root.find(".//m:menu[@code='video']", ns)
if video is None:
    raise SystemExit("video menu not found")
for child in list(video):
    if child.get("code") == probe_code:
        video.remove(child)
tree.write(menu_file, encoding="UTF-8", xml_declaration=True)
PY
}

remove_translations() {
  if [[ -f "$BACKUP_DIR/translate.properties.orig" ]]; then
    cp "$BACKUP_DIR/translate.properties.orig" "$TRANSLATE_FILE"
    return
  fi
  python3 - "$TRANSLATE_FILE" "$PROBE_CODE" "$PROBE_MENU_ID" <<'PY'
import sys
from pathlib import Path

translate_file, probe_code, probe_menu_id = sys.argv[1:4]
path = Path(translate_file)
lines = path.read_text(encoding="utf-8").splitlines()
prefixes = (
    f"menu.{probe_code}.displayName=",
    f"menu.{probe_code}.description=",
    f"menu.{probe_menu_id}.displayName=",
    f"menu.{probe_menu_id}.description=",
)
filtered = [line for line in lines if not line.startswith(prefixes)]
path.write_text("\n".join(filtered) + "\n", encoding="utf-8")
PY
}

remove_icon() {
  local target_icon="$ICON_DIR/Infovision Foresight_${PROBE_CODE}.png"
  [[ -f "$target_icon" ]] && rm -f "$target_icon"
}

show_status() {
  echo "PRODUCT_DIR=$PRODUCT_DIR"
  echo "MENU_FILE=$MENU_FILE"
  echo "TRANSLATE_FILE=$TRANSLATE_FILE"
  echo "PROBE_URL=$PROBE_URL"
  if probe_present; then
    echo "menu_status=installed"
    grep -n "$PROBE_CODE" "$MENU_FILE" || true
    grep -n "$PROBE_CODE" "$TRANSLATE_FILE" || true
  else
    echo "menu_status=not-installed"
  fi
  if ipoint_redirected; then
    echo "ipoint_slot_status=redirected"
    grep -n 'code="ipoint"' "$MENU_FILE" || true
  else
    echo "ipoint_slot_status=default"
  fi
  if video_monitor_redirected; then
    echo "video_monitor_slot_status=redirected"
    grep -n 'code="client0101"' "$MENU_FILE" || true
  else
    echo "video_monitor_slot_status=default"
  fi
}

main() {
  require_files
  case "${1:-}" in
    install)
      install_menu
      install_translations
      install_icon
      show_status
      ;;
    install-ipoint-slot)
      install_ipoint_slot
      show_status
      ;;
    install-ipoint-poc-slot)
      PROBE_URL="$POC_URL"
      install_ipoint_slot
      show_status
      ;;
    install-video-monitor-poc-slot)
      restore_original_slot "ipoint"
      install_video_monitor_slot
      show_status
      ;;
    remove)
      remove_menu
      remove_translations
      remove_icon
      show_status
      ;;
    status)
      show_status
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "${1:-}"
