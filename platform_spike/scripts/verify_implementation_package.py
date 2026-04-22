#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a materialized platform_spike implementation package directory."
    )
    parser.add_argument("package_dir", help="Path to the materialized implementation package directory.")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def run_node_check(path: Path) -> dict:
    node_path = shutil.which("node")
    if not node_path:
        return {"checked": False, "reason": "node-not-found"}
    completed = subprocess.run(
        [node_path, "--check", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "checked": True,
        "ok": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def verify_package(package_dir: Path) -> dict:
    require(package_dir.exists(), f"Package directory does not exist: {package_dir}")
    require(package_dir.is_dir(), f"Package path is not a directory: {package_dir}")

    manifest_path = package_dir / "manifest.json"
    package_json_path = package_dir / "package.json"
    readme_path = package_dir / "README.md"
    require(manifest_path.exists(), "manifest.json is missing")
    require(package_json_path.exists(), "package.json is missing")
    require(readme_path.exists(), "README.md is missing")

    manifest = load_json(manifest_path)
    package_json = load_json(package_json_path)
    required_manifest_keys = {
        "driverKind",
        "bridgePreset",
        "driverPreset",
        "hostType",
        "runtimePrefix",
        "runtimeSupportFiles",
        "requiredBridgeMethods",
        "moduleType",
    }
    missing_manifest_keys = sorted(required_manifest_keys - set(manifest.keys()))
    require(not missing_manifest_keys, f"Manifest is missing keys: {missing_manifest_keys}")
    require(package_json.get("type") == "module", "package.json must declare type=module")
    require(manifest.get("moduleType") == "module", "manifest.moduleType must equal 'module'")

    bridge_file = package_dir / "bridge" / f"{manifest['bridgePreset']}.js"
    driver_file = package_dir / "driver" / f"{manifest['driverPreset']}.js"
    require(bridge_file.exists(), f"Bridge file is missing: {bridge_file}")
    require(driver_file.exists(), f"Driver file is missing: {driver_file}")

    support_files = []
    for relative_name in manifest["runtimeSupportFiles"]:
        target = package_dir / relative_name
        require(target.exists(), f"Runtime support file is missing: {relative_name}")
        support_files.append(target)

    policy_path = package_dir / "runtime" / "policy.json"
    require(policy_path.exists(), "runtime/policy.json is missing")
    policy = load_json(policy_path)
    required_policy_keys = {"preflight", "admission", "actionPolicy", "health", "templatePresets"}
    missing_policy_keys = sorted(required_policy_keys - set(policy.keys()))
    require(not missing_policy_keys, f"Policy file is missing keys: {missing_policy_keys}")

    wiring_path = package_dir / "runtime" / "wiring.js"
    require(wiring_path.exists(), "runtime/wiring.js is missing")
    wiring_text = wiring_path.read_text(encoding="utf-8")
    require("../bridge/" in wiring_text, "runtime/wiring.js does not reference bridge module")
    require("../driver/" in wiring_text, "runtime/wiring.js does not reference driver module")
    require("../runtime/health.js" in wiring_text, "runtime/wiring.js does not reference health module")

    syntax_checks = {
        "bridge": run_node_check(bridge_file),
        "driver": run_node_check(driver_file),
        "wiring": run_node_check(wiring_path),
        "health": run_node_check(package_dir / "runtime" / "health.js"),
    }

    failed_checks = {
        name: result for name, result in syntax_checks.items() if result.get("checked") and not result.get("ok")
    }
    require(not failed_checks, f"Node syntax checks failed: {failed_checks}")

    summary = {
        "package_dir": str(package_dir.resolve()),
        "manifest": manifest,
        "package_json": package_json,
        "bridge_file": str(bridge_file),
        "driver_file": str(driver_file),
        "runtime_support_files": [str(path) for path in support_files],
        "policy_keys": sorted(policy.keys()),
        "syntax_checks": syntax_checks,
    }
    return summary


def main() -> int:
    args = parse_args()
    package_dir = Path(args.package_dir)
    try:
        summary = verify_package(package_dir)
    except Exception as exc:  # pragma: no cover - command-line failure path
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, "summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
