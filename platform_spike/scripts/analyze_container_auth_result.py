#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class ContainerAuthSummary:
    bridge_mode: str
    runtime_mode: str
    platform_base_url: str
    user_index_code: str
    xres_context: str
    tvms_context: str
    xres_status: str
    tvms_all_status: str
    tvms_ruok_status: str
    recommendation: str
    next_step: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse a CONTAINER_AUTH_RESULT block and emit JSON/markdown analysis."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Optional text file containing a CONTAINER_AUTH_RESULT block. Defaults to stdin.",
    )
    parser.add_argument(
        "--output-root",
        default="tmp/container_auth_results",
        help="Directory where parsed result folders are written.",
    )
    return parser.parse_args()


def read_input(path_arg: str | None) -> str:
    if path_arg:
      return Path(path_arg).read_text(encoding="utf-8-sig")
    return sys.stdin.read()


def extract_block(text: str) -> list[str]:
    started = False
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip("\r")
        if line.strip() == "=== CONTAINER_AUTH_RESULT ===":
            started = True
            lines.append(line.strip())
            continue
        if not started:
            continue
        lines.append(line)
        if line.strip() == "CONTAINER_AUTH_RESULT_END":
            break
    if not lines or lines[-1].strip() != "CONTAINER_AUTH_RESULT_END":
        raise ValueError("CONTAINER_AUTH_RESULT block not found or incomplete.")
    return lines


def parse_key_values(lines: list[str]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("===") or stripped.endswith("_END"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload


def summarize(payload: dict[str, str]) -> ContainerAuthSummary:
    xres_status = payload.get("xres.status", "")
    tvms_all_status = payload.get("tvmsAll.status", "")
    tvms_ruok_status = payload.get("tvmsRuok.status", "")

    if xres_status == "ok" and (tvms_all_status == "ok" or tvms_ruok_status == "ok"):
        recommendation = "ready-for-platform-spike-live"
        next_step = "Keep the client logged in and continue with live previewURLs / tvwall wiring."
    elif "auth-failed" in {xres_status, tvms_all_status, tvms_ruok_status}:
        recommendation = "auth-header-mismatch"
        next_step = "Gateway and service contexts are reachable through the container, but token/proxy auth shape still needs adjustment."
    elif all(status in {"transport-failed", "", "failed"} for status in [xres_status, tvms_all_status, tvms_ruok_status]):
        recommendation = "network-or-proxy-blocked"
        next_step = "Wait for a stable gov network window, then reopen 视频监控 and capture CONTAINER_AUTH_RESULT again."
    else:
        recommendation = "partial-platform-readiness"
        next_step = "At least one service path is reachable. Inspect xres/tvms separately and continue with the more complete path first."

    return ContainerAuthSummary(
        bridge_mode=payload.get("bridgeMode", ""),
        runtime_mode=payload.get("runtimeMode", ""),
        platform_base_url=payload.get("platformBaseUrl", ""),
        user_index_code=payload.get("userIndexCode", ""),
        xres_context=payload.get("xresContext", ""),
        tvms_context=payload.get("tvmsContext", ""),
        xres_status=xres_status,
        tvms_all_status=tvms_all_status,
        tvms_ruok_status=tvms_ruok_status,
        recommendation=recommendation,
        next_step=next_step,
    )


def slug_now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_markdown(result_dir: Path, payload: dict[str, str], summary: ContainerAuthSummary) -> str:
    return "\n".join(
        [
            "# Container Auth Result Analysis",
            "",
            f"- Result Dir: `{result_dir}`",
            f"- Bridge Mode: `{summary.bridge_mode}`",
            f"- Runtime Mode: `{summary.runtime_mode}`",
            f"- Platform Base URL: `{summary.platform_base_url}`",
            f"- User Index Code: `{summary.user_index_code}`",
            f"- XRES Context: `{summary.xres_context}`",
            f"- TVMS Context: `{summary.tvms_context}`",
            "",
            "## Probe Status",
            "",
            f"- XRES: `{summary.xres_status}`",
            f"- XRES Candidate: `{payload.get('xres.bestCandidate', '')}`",
            f"- XRES Summary: {payload.get('xres.summary', '')}",
            f"- TVMS All: `{summary.tvms_all_status}`",
            f"- TVMS All Candidate: `{payload.get('tvmsAll.bestCandidate', '')}`",
            f"- TVMS All Summary: {payload.get('tvmsAll.summary', '')}",
            f"- TVMS Ruok: `{summary.tvms_ruok_status}`",
            f"- TVMS Ruok Candidate: `{payload.get('tvmsRuok.bestCandidate', '')}`",
            f"- TVMS Ruok Summary: {payload.get('tvmsRuok.summary', '')}",
            "",
            "## Ticket Variants",
            "",
            f"- type0 token1: `{payload.get('ticket.type0_token1', '')}`",
            f"- type0 token2: `{payload.get('ticket.type0_token2', '')}`",
            f"- type2: `{payload.get('ticket.type2', '')}`",
            "",
            "## Recommendation",
            "",
            f"- Recommendation: `{summary.recommendation}`",
            f"- Next Step: {summary.next_step}",
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    try:
        raw_text = read_input(args.input)
        block_lines = extract_block(raw_text)
        payload = parse_key_values(block_lines)
        summary = summarize(payload)

        output_root = Path(args.output_root).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        result_dir = output_root / f"container_auth_result_{slug_now()}"
        result_dir.mkdir(parents=True, exist_ok=True)

        raw_path = result_dir / "container_auth_result.txt"
        json_path = result_dir / "container_auth_result.json"
        analysis_json_path = result_dir / "analysis.json"
        analysis_md_path = result_dir / "analysis.md"
        latest_pointer = output_root / "latest_container_auth_result.txt"

        raw_path.write_text("\n".join(block_lines) + "\n", encoding="utf-8")
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        analysis = {
            "resultDir": str(result_dir),
            "payload": payload,
            "summary": asdict(summary),
        }
        analysis_json_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        analysis_md_path.write_text(build_markdown(result_dir, payload, summary), encoding="utf-8")
        latest_pointer.write_text(str(result_dir), encoding="utf-8")

        print(
            json.dumps(
                {
                    "ok": True,
                    "resultDir": str(result_dir),
                    "rawPath": str(raw_path),
                    "jsonPath": str(json_path),
                    "analysisJsonPath": str(analysis_json_path),
                    "analysisMarkdownPath": str(analysis_md_path),
                    "latestPointer": str(latest_pointer),
                    "summary": asdict(summary),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
