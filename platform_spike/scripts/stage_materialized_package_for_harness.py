#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy a materialized implementation package into web_demo/harness_packages for browser harness testing."
    )
    parser.add_argument("package_dir", help="Path to the materialized implementation package directory.")
    parser.add_argument(
        "--target-root",
        default="platform_spike/web_demo/harness_packages",
        help="Target root directory for staged harness packages.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the target directory if it already exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.package_dir).resolve()
    target_root = Path(args.target_root).resolve()

    try:
        if not source.exists():
            raise FileNotFoundError(f"Package directory does not exist: {source}")
        if not source.is_dir():
            raise NotADirectoryError(f"Package path is not a directory: {source}")
        if not (source / "manifest.json").exists():
            raise FileNotFoundError(f"manifest.json is missing under: {source}")

        target_root.mkdir(parents=True, exist_ok=True)
        target = target_root / source.name
        if target.exists():
            if not args.force:
                raise FileExistsError(f"Target directory already exists: {target}")
            shutil.rmtree(target)
        shutil.copytree(source, target)

        summary = {
            "ok": True,
            "source": str(source),
            "target": str(target),
            "files": sorted(str(path.relative_to(target)) for path in target.rglob("*") if path.is_file()),
        }
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
