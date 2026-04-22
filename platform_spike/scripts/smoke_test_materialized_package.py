#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


NODE_SMOKE_TEST = r"""
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { readFile } from 'node:fs/promises';

const packageDir = process.argv[2];
const wiringUrl = pathToFileURL(path.join(packageDir, 'runtime', 'wiring.js')).href;
const manifest = JSON.parse(await readFile(path.join(packageDir, 'manifest.json'), 'utf8'));
const wiringModule = await import(wiringUrl);
const wiring = wiringModule.createRuntimeWiring();

const bridgeKeys = Object.keys(wiring.bridge || {});
const driverKeys = Object.keys(wiring.driver || {});
const healthKeys = Object.keys(wiring.health || {});

const stubHostBridge = Object.fromEntries(
  bridgeKeys.map((methodName) => [
    methodName,
    async (payload = {}) => ({
      ok: true,
      methodName,
      payload,
      at: new Date().toISOString()
    })
  ])
);

const ctx = {
  runtimePrefix: manifest.runtimePrefix || 'smoke-runtime',
  mountSelector: '#tile-1',
  cameraIndexCode: 'mock-camera-01'
};
const payload = {
  tileIndex: 0,
  tileOrdinal: 1,
  mountSelector: '#tile-1',
  previewUrl: 'mock://preview/01',
  cameraIndexCode: 'mock-camera-01'
};

const initResult = wiring.driver.init ? await wiring.driver.init(ctx, stubHostBridge) : null;
const runtimeCtx = Object.assign({}, ctx, initResult && initResult.runtimeId ? { runtimeId: initResult.runtimeId } : {});
const attachResult = wiring.driver.attach ? await wiring.driver.attach(runtimeCtx, payload, stubHostBridge) : null;
const refreshResult = wiring.driver.refresh ? await wiring.driver.refresh(runtimeCtx, payload, stubHostBridge) : null;
const detachResult = wiring.driver.detach ? await wiring.driver.detach(runtimeCtx, payload, stubHostBridge) : null;
const disposeResult = wiring.driver.dispose ? await wiring.driver.dispose(runtimeCtx, stubHostBridge) : null;
const healthResult = wiring.health.runHealthCheck ? await wiring.health.runHealthCheck(runtimeCtx) : null;

console.log(JSON.stringify({
  ok: true,
  bridgeKeys,
  driverKeys,
  healthKeys,
  initResult,
  attachResult,
  refreshResult,
  detachResult,
  disposeResult,
  healthResult
}, null, 2));
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a minimal runtime smoke test against a materialized implementation package."
    )
    parser.add_argument("package_dir", help="Path to the materialized implementation package directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_dir = Path(args.package_dir).resolve()
    if not package_dir.exists():
        print(json.dumps({"ok": False, "error": f"Package directory does not exist: {package_dir}"}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    node_path = shutil.which("node")
    if not node_path:
        print(json.dumps({"ok": False, "error": "node-not-found"}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    with tempfile.NamedTemporaryFile("w", suffix=".mjs", encoding="utf-8", delete=False) as handle:
        handle.write(NODE_SMOKE_TEST)
        script_path = Path(handle.name)

    try:
        completed = subprocess.run(
            [node_path, str(script_path), str(package_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        script_path.unlink(missing_ok=True)

    if completed.returncode != 0:
        print(
            json.dumps(
                {
                    "ok": False,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return completed.returncode or 1

    print(completed.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
