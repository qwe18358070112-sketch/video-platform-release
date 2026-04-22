#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from verify_implementation_package import verify_package


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Catalog and verify all materialized platform_spike implementation packages under a root directory."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default="tmp/materialized_packages",
        help="Directory containing one or more materialized package directories.",
    )
    parser.add_argument(
        "--json-output",
        help="Optional path to write the catalog JSON.",
    )
    parser.add_argument(
        "--with-smoke-test",
        action="store_true",
        help="Also run smoke_test_materialized_package.py for each package.",
    )
    return parser.parse_args()


def discover_package_dirs(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"Package root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Package root is not a directory: {root}")
    package_dirs = [child for child in sorted(root.iterdir()) if (child / "manifest.json").exists()]
    if not package_dirs:
        raise FileNotFoundError(f"No materialized packages found under: {root}")
    return package_dirs


def run_smoke_test(package_dir: Path) -> dict:
    script_path = Path(__file__).with_name("smoke_test_materialized_package.py")
    completed = subprocess.run(
        [sys.executable, str(script_path), str(package_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": "smoke-test-invalid-json",
        }
    payload["ok"] = True
    return payload


def catalog_package(package_dir: Path, with_smoke_test: bool) -> dict:
    entry = {
        "packageName": package_dir.name,
        "path": str(package_dir.resolve()),
        "ok": False,
    }
    try:
        summary = verify_package(package_dir)
    except Exception as exc:
        entry["error"] = str(exc)
        return entry

    manifest = summary.get("manifest", {})
    entry.update(
        {
            "ok": True,
            "bridgePreset": manifest.get("bridgePreset"),
            "driverPreset": manifest.get("driverPreset"),
            "driverKind": manifest.get("driverKind"),
            "hostType": manifest.get("hostType"),
            "runtimePrefix": manifest.get("runtimePrefix"),
            "runtimeSupportFiles": manifest.get("runtimeSupportFiles", []),
            "policyKeys": summary.get("policy_keys", []),
            "syntaxChecks": {
                name: {
                    "checked": result.get("checked"),
                    "ok": result.get("ok"),
                }
                for name, result in summary.get("syntax_checks", {}).items()
            },
        }
    )
    if with_smoke_test:
        smoke = run_smoke_test(package_dir)
        entry["smokeTest"] = smoke
        entry["ok"] = entry["ok"] and smoke.get("ok", False)
    return entry


def build_catalog(root: Path, with_smoke_test: bool) -> dict:
    package_dirs = discover_package_dirs(root)
    packages = [catalog_package(package_dir, with_smoke_test) for package_dir in package_dirs]
    ok_count = sum(1 for package in packages if package["ok"])
    failed_count = len(packages) - ok_count
    return {
        "root": str(root.resolve()),
        "packageCount": len(packages),
        "okCount": ok_count,
        "failedCount": failed_count,
        "withSmokeTest": with_smoke_test,
        "packages": packages,
    }


def main() -> int:
    args = parse_args()
    try:
        catalog = build_catalog(Path(args.root), args.with_smoke_test)
    except Exception as exc:  # pragma: no cover - command-line failure path
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"ok": catalog["failedCount"] == 0, "catalog": catalog}, ensure_ascii=False, indent=2))
    return 0 if catalog["failedCount"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
