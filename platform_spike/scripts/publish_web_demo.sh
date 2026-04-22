#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="$ROOT_DIR/platform_spike/web_demo"
TARGET_DIR="/mnt/d/opsmgr/Infovision Foresight/client/components/webcontainer.1/bin/webcontainer/webapp/platform_spike_probe"

mkdir -p "$TARGET_DIR"

cp "$SRC_DIR/webcontainer_probe.html" "$TARGET_DIR/index.html"
cp "$SRC_DIR/webcontainer_probe.js" "$TARGET_DIR/webcontainer_probe.js"
cp "$SRC_DIR/platform_spike_poc.html" "$TARGET_DIR/platform_spike_poc.html"
cp "$SRC_DIR/platform_spike_poc.js" "$TARGET_DIR/platform_spike_poc.js"
cp "$SRC_DIR/implementation_package_harness.html" "$TARGET_DIR/implementation_package_harness.html"
cp "$SRC_DIR/implementation_package_harness.js" "$TARGET_DIR/implementation_package_harness.js"

if [ -d "$SRC_DIR/harness_packages" ]; then
  rm -rf "$TARGET_DIR/harness_packages"
  mkdir -p "$TARGET_DIR/harness_packages"
  cp -R "$SRC_DIR/harness_packages/." "$TARGET_DIR/harness_packages/"
fi

echo "Published web demo to:"
echo "  $TARGET_DIR"
echo
echo "Files:"
find "$TARGET_DIR" -maxdepth 1 -type f | sort
