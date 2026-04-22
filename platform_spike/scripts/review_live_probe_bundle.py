#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from analyze_live_probe_bundle import build_summary, load_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review the latest or specified live probe bundle and print the next recommended operator step."
    )
    parser.add_argument("bundle_dir", nargs="?", help="Optional bundle directory. Defaults to tmp/live_probe_bundles/latest_bundle.txt.")
    return parser.parse_args()


def resolve_bundle_dir(argument: str | None) -> Path:
    def normalize(path_str: str) -> Path:
        value = path_str.strip()
        if re.match(r"^\\\\wsl\.localhost\\[^\\]+\\", value, re.I):
            value = re.sub(r"^\\\\wsl\.localhost\\[^\\]+", "", value, flags=re.I)
            value = value.replace("\\", "/")
            return Path(value).resolve()
        return Path(value).resolve()

    if argument:
        return normalize(argument)
    latest_pointer = Path("tmp/live_probe_bundles/latest_bundle.txt").resolve()
    if not latest_pointer.exists():
        raise FileNotFoundError(f"Latest bundle pointer is missing: {latest_pointer}")
    bundle_dir = normalize(latest_pointer.read_text(encoding="utf-8-sig"))
    if not bundle_dir.exists():
        raise FileNotFoundError(f"Latest bundle directory does not exist: {bundle_dir}")
    return bundle_dir


def operator_step(recommendation: str) -> str:
    if recommendation == "network-blocked":
        return "下次切政务网后，只执行 quick capture bundle，不要额外点页面。"
    if recommendation == "auth-header-mismatch":
        return "这次网关和服务路径都打通了。保持客户端登录，不要切页面；如果视频监控页里出现 CONTAINER_AUTH_RESULT，就把整段复制给我，否则重新执行 quick capture bundle。"
    if recommendation == "endpoint-mismatch":
        return "这次已经连到网关了，不要重复切换页面。等我更新 probe 路径后，你再保持客户端登录并重新执行 quick capture bundle。"
    if recommendation == "run-full-probe":
        return "下次在线时先保持客户端登录，然后执行 full live probe，补 cameras 和 previewURLs。"
    if recommendation == "ready-for-platform-spike-live":
        return "下次在线时进入视频监控，准备做真实 previewURLs / tvwall 接线验证。"
    if recommendation == "session-missing":
        return "先确认客户端仍处于已登录状态，再重新执行 quick capture bundle。"
    return "先保持客户端登录和网络稳定，再重新执行 quick capture bundle。"


def main() -> int:
    args = parse_args()
    try:
        bundle_dir = resolve_bundle_dir(args.bundle_dir)
        bundle_summary = load_json(bundle_dir / "bundle_summary.json")
        probe_output = load_json(bundle_dir / "platform_live_probe_last.json")
        summary = build_summary(bundle_dir, bundle_summary, probe_output)
        service_contexts = probe_output.get("serviceContexts") or bundle_summary.get("serviceContexts") or {}

        review = {
            "bundleDir": str(bundle_dir),
            "stage": summary.stage,
            "probePreset": summary.probe_preset,
            "probeCount": summary.probe_count,
            "xresSearchContext": service_contexts.get("xresSearch") or "",
            "tvmsContext": service_contexts.get("tvms") or "",
            "recommendation": summary.recommendation,
            "nextStep": summary.next_step,
            "operatorStep": operator_step(summary.recommendation),
        }
        auth_context_path = bundle_dir / "clientframe_auth_context.json"
        if auth_context_path.exists():
            auth_context = load_json(auth_context_path)
            service_summaries = auth_context.get("serviceSummaries") or {}
            review["xresSearchTokenCandidate"] = (
                ((service_summaries.get("xres:xres-search") or {}).get("candidateTokens") or [""])[0]
            )
            review["tvmsTokenCandidate"] = (
                ((service_summaries.get("tvms:tvms") or {}).get("candidateTokens") or [""])[0]
            )

        root_dir = bundle_dir.parent
        bundle_json_path = bundle_dir / "operator_review.json"
        bundle_txt_path = bundle_dir / "operator_review.txt"
        latest_json_path = root_dir / "latest_operator_review.json"
        latest_txt_path = root_dir / "latest_operator_review.txt"
        review_json = json.dumps(review, ensure_ascii=False, indent=2)
        review_text = "\n".join(
            [
                f"bundleDir={review['bundleDir']}",
                f"stage={review['stage']}",
                f"probePreset={review['probePreset']}",
                f"probeCount={review['probeCount']}",
                f"xresSearchContext={review['xresSearchContext']}",
                f"tvmsContext={review['tvmsContext']}",
                f"xresSearchTokenCandidate={review.get('xresSearchTokenCandidate', '')}",
                f"tvmsTokenCandidate={review.get('tvmsTokenCandidate', '')}",
                f"recommendation={review['recommendation']}",
                f"nextStep={review['nextStep']}",
                f"operatorStep={review['operatorStep']}",
            ]
        )
        bundle_json_path.write_text(review_json, encoding="utf-8")
        bundle_txt_path.write_text(review_text, encoding="utf-8")
        latest_json_path.write_text(review_json, encoding="utf-8")
        latest_txt_path.write_text(review_text, encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "review": review,
                "bundleReviewJson": str((bundle_dir / "operator_review.json").resolve()),
                "bundleReviewText": str((bundle_dir / "operator_review.txt").resolve()),
                "latestReviewJson": str((bundle_dir.parent / "latest_operator_review.json").resolve()),
                "latestReviewText": str((bundle_dir.parent / "latest_operator_review.txt").resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
