#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize a platform_spike implementation package JSON into real files."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to an exported implementation package JSON file. Omit to read from stdin.",
    )
    parser.add_argument(
        "--output-root",
        default="tmp/materialized_packages",
        help="Root directory where the package directory will be created.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing output directory.",
    )
    return parser.parse_args()


def read_payload(input_path: str | None) -> dict:
    raw: str
    if input_path:
        raw = Path(input_path).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Implementation package payload must be a JSON object")
    return payload


def sanitize_package_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip())
    cleaned = cleaned.strip(".-")
    return cleaned or "renderer-package"


def ensure_safe_relative_path(relative_path: str) -> Path:
    if not relative_path:
        raise ValueError("Package file path is empty")
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError(f"Absolute file path is not allowed: {relative_path}")
    normalized = candidate.as_posix()
    if normalized.startswith("../") or "/../" in normalized or normalized == "..":
        raise ValueError(f"Unsafe relative file path: {relative_path}")
    return candidate


def materialize_package(payload: dict, output_root: Path, force: bool) -> dict:
    package_name = sanitize_package_name(str(payload.get("packageName") or "renderer-package"))
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Implementation package does not contain a non-empty 'files' object")

    output_dir = output_root / package_name
    if output_dir.exists():
        if not force:
            raise FileExistsError(f"Output directory already exists: {output_dir}")
        if not output_dir.is_dir():
            raise FileExistsError(f"Output path is not a directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    written_files: list[str] = []
    for relative_name, content in files.items():
        safe_path = ensure_safe_relative_path(str(relative_name))
        target_path = output_dir / safe_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            target_path.write_text(content, encoding="utf-8")
        else:
            target_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        written_files.append(str(target_path))

    manifest_path = output_dir / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    summary = {
        "package_name": package_name,
        "output_dir": str(output_dir.resolve()),
        "file_count": len(written_files),
        "written_files": written_files,
        "manifest": manifest,
    }
    return summary


def main() -> int:
    args = parse_args()
    try:
        payload = read_payload(args.input)
        summary = materialize_package(payload, Path(args.output_root), args.force)
    except Exception as exc:  # pragma: no cover - command-line error path
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, "summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
