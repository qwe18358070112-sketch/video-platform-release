#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package a parsed container auth result directory into a zip and operator-friendly text summary."
    )
    parser.add_argument("result_dir", help="Path to a directory created by analyze_container_auth_result.py")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_operator_packet_text(result_dir: Path, analysis: dict | None, review: dict | None) -> str:
    summary = (analysis or {}).get("summary") or {}
    lines = [
        f"resultDir={result_dir}",
        f"bridgeMode={summary.get('bridge_mode', '')}",
        f"runtimeMode={summary.get('runtime_mode', '')}",
        f"platformBaseUrl={summary.get('platform_base_url', '')}",
        f"userIndexCode={summary.get('user_index_code', '')}",
        f"xresContext={summary.get('xres_context', '')}",
        f"tvmsContext={summary.get('tvms_context', '')}",
        f"recommendation={summary.get('recommendation', '')}",
        f"nextStep={summary.get('next_step', '')}",
    ]
    if review:
        lines.append(f"operatorStep={review.get('operatorStep', '')}")
    return "\n".join(lines) + "\n"


def make_zip(result_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(result_dir.iterdir()):
            if path.is_file():
                archive.write(path, arcname=path.name)


def main() -> int:
    args = parse_args()
    result_dir = Path(args.result_dir).resolve()
    try:
        if not result_dir.exists():
            raise FileNotFoundError(f"Result directory does not exist: {result_dir}")
        if not result_dir.is_dir():
            raise NotADirectoryError(f"Result path is not a directory: {result_dir}")

        analysis_json_path = result_dir / "analysis.json"
        if not analysis_json_path.exists():
            raise FileNotFoundError(f"analysis.json is missing under: {result_dir}")
        analysis = load_json(analysis_json_path)
        review_json_path = result_dir / "operator_review.json"
        review = load_json(review_json_path) if review_json_path.exists() else None

        packet_text = build_operator_packet_text(result_dir, analysis, review)
        packet_text_path = result_dir / "operator_packet.txt"
        packet_text_path.write_text(packet_text, encoding="utf-8")

        zip_path = result_dir.parent / f"{result_dir.name}.zip"
        make_zip(result_dir, zip_path)

        latest_zip_pointer = result_dir.parent / "latest_container_auth_result_zip.txt"
        latest_packet_pointer = result_dir.parent / "latest_container_auth_operator_packet.txt"
        latest_zip_pointer.write_text(str(zip_path), encoding="utf-8")
        latest_packet_pointer.write_text(packet_text, encoding="utf-8")

        result = {
            "ok": True,
            "resultDir": str(result_dir),
            "zipPath": str(zip_path),
            "operatorPacketPath": str(packet_text_path),
            "latestZipPointer": str(latest_zip_pointer),
            "latestOperatorPacket": str(latest_packet_pointer),
        }
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
