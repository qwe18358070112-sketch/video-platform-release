#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package a live probe bundle into a zip and operator-friendly text summary."
    )
    parser.add_argument("bundle_dir", help="Path to a bundle directory created by platform_quick_capture_bundle.sh")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def first_candidate(auth_context: dict | None, service_key: str) -> str:
    if not auth_context:
        return ""
    service_summaries = auth_context.get("serviceSummaries") or {}
    candidates = (service_summaries.get(service_key) or {}).get("candidateTokens") or []
    return str(candidates[0]) if candidates else ""


def build_operator_packet_text(bundle_dir: Path, summary: dict, probe_output: dict | None, analysis: dict | None, review: dict | None) -> str:
    analysis_summary = (analysis or {}).get("summary") or {}
    service_contexts = summary.get("serviceContexts") or (probe_output or {}).get("serviceContexts") or {}
    auth_context = load_json(bundle_dir / "clientframe_auth_context.json") if (bundle_dir / "clientframe_auth_context.json").exists() else None
    lines = [
        f"bundleDir={bundle_dir}",
        f"generatedAt={summary.get('generatedAt', '')}",
        f"probePreset={summary.get('probePreset', '')}",
        f"stage={summary.get('stage', '')}",
        f"probeCount={summary.get('probeCount', '')}",
        f"loginUrl={(summary.get('session') or {}).get('loginUrl', '')}",
        f"userIndexCode={(summary.get('session') or {}).get('userIndexCode', '')}",
        f"xresSearchContext={service_contexts.get('xresSearch', '')}",
        f"tvmsContext={service_contexts.get('tvms', '')}",
        f"xresSearchTokenCandidate={first_candidate(auth_context, 'xres:xres-search')}",
        f"tvmsTokenCandidate={first_candidate(auth_context, 'tvms:tvms')}",
        f"recommendation={analysis_summary.get('recommendation', '')}",
        f"nextStep={analysis_summary.get('next_step', '')}",
    ]
    if review:
        lines.append(f"operatorStep={review.get('operatorStep', '')}")
    return "\n".join(lines) + "\n"


def make_zip(bundle_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle_dir.iterdir()):
            if path.is_file():
                archive.write(path, arcname=path.name)


def main() -> int:
    args = parse_args()
    bundle_dir = Path(args.bundle_dir).resolve()
    try:
        if not bundle_dir.exists():
            raise FileNotFoundError(f"Bundle directory does not exist: {bundle_dir}")
        if not bundle_dir.is_dir():
            raise NotADirectoryError(f"Bundle path is not a directory: {bundle_dir}")

        bundle_summary_path = bundle_dir / "bundle_summary.json"
        if not bundle_summary_path.exists():
            raise FileNotFoundError(f"bundle_summary.json is missing under: {bundle_dir}")
        bundle_summary = load_json(bundle_summary_path)

        analysis_json_path = bundle_dir / "bundle_analysis.json"
        analysis = load_json(analysis_json_path) if analysis_json_path.exists() else None
        probe_output_path = bundle_dir / "platform_live_probe_last.json"
        probe_output = load_json(probe_output_path) if probe_output_path.exists() else None
        review_json_path = bundle_dir / "operator_review.json"
        review = load_json(review_json_path) if review_json_path.exists() else None

        packet_text = build_operator_packet_text(bundle_dir, bundle_summary, probe_output, analysis, review)
        packet_text_path = bundle_dir / "operator_packet.txt"
        packet_text_path.write_text(packet_text, encoding="utf-8")

        zip_path = bundle_dir.parent / f"{bundle_dir.name}.zip"
        make_zip(bundle_dir, zip_path)

        latest_zip_pointer = bundle_dir.parent / "latest_bundle_zip.txt"
        latest_packet_pointer = bundle_dir.parent / "latest_operator_packet.txt"
        latest_zip_pointer.write_text(str(zip_path), encoding="utf-8")
        latest_packet_pointer.write_text(packet_text, encoding="utf-8")

        result = {
            "ok": True,
            "bundleDir": str(bundle_dir),
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
