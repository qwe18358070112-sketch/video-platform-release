#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from analyze_container_auth_result import summarize


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review the latest or specified container auth result directory and print the next operator step."
    )
    parser.add_argument(
        "result_dir",
        nargs="?",
        help="Optional result directory. Defaults to tmp/container_auth_results/latest_container_auth_result.txt",
    )
    return parser.parse_args()


def normalize(path_str: str) -> Path:
    value = path_str.strip()
    if re.match(r"^\\\\wsl\.localhost\\[^\\]+\\", value, re.I):
        value = re.sub(r"^\\\\wsl\.localhost\\[^\\]+", "", value, flags=re.I)
        value = value.replace("\\", "/")
    return Path(value).resolve()


def resolve_result_dir(argument: str | None) -> Path:
    if argument:
        return normalize(argument)
    latest_pointer = Path("tmp/container_auth_results/latest_container_auth_result.txt").resolve()
    if not latest_pointer.exists():
        raise FileNotFoundError(f"Latest container auth result pointer is missing: {latest_pointer}")
    result_dir = normalize(latest_pointer.read_text(encoding="utf-8-sig"))
    if not result_dir.exists():
        raise FileNotFoundError(f"Latest container auth result directory does not exist: {result_dir}")
    return result_dir


def operator_step(recommendation: str) -> str:
    if recommendation == "ready-for-platform-spike-live":
        return "容器认证已经通过。下次在线时保持客户端登录，准备继续做真实 previewURLs / tvwall 接线。"
    if recommendation == "auth-header-mismatch":
        return "容器已经打到真实服务了，但认证头还没对上。暂时不要多点页面，把结果发回后等 probe 更新。"
    if recommendation == "network-or-proxy-blocked":
        return "等稳定政务网窗口时，再进入视频监控并重新复制 CONTAINER_AUTH_RESULT。"
    return "先保持客户端登录，等待下一次更稳定的在线窗口再重试。"


def main() -> int:
    args = parse_args()
    try:
        result_dir = resolve_result_dir(args.result_dir)
        payload_path = result_dir / "container_auth_result.json"
        if not payload_path.exists():
            raise FileNotFoundError(f"container_auth_result.json is missing under: {result_dir}")
        payload = json.loads(payload_path.read_text(encoding="utf-8-sig"))
        summary = summarize(payload)
        review = {
            "resultDir": str(result_dir),
            "bridgeMode": summary.bridge_mode,
            "runtimeMode": summary.runtime_mode,
            "xresContext": summary.xres_context,
            "tvmsContext": summary.tvms_context,
            "recommendation": summary.recommendation,
            "nextStep": summary.next_step,
            "operatorStep": operator_step(summary.recommendation),
        }

        root_dir = result_dir.parent
        bundle_json_path = result_dir / "operator_review.json"
        bundle_txt_path = result_dir / "operator_review.txt"
        latest_json_path = root_dir / "latest_operator_review.json"
        latest_txt_path = root_dir / "latest_operator_review.txt"
        review_json = json.dumps(review, ensure_ascii=False, indent=2)
        review_text = "\n".join(
            [
                f"resultDir={review['resultDir']}",
                f"bridgeMode={review['bridgeMode']}",
                f"runtimeMode={review['runtimeMode']}",
                f"xresContext={review['xresContext']}",
                f"tvmsContext={review['tvmsContext']}",
                f"recommendation={review['recommendation']}",
                f"nextStep={review['nextStep']}",
                f"operatorStep={review['operatorStep']}",
            ]
        )
        bundle_json_path.write_text(review_json, encoding="utf-8")
        bundle_txt_path.write_text(review_text, encoding="utf-8")
        latest_json_path.write_text(review_json, encoding="utf-8")
        latest_txt_path.write_text(review_text, encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": True,
                    "review": review,
                    "bundleReviewJson": str(bundle_json_path.resolve()),
                    "bundleReviewText": str(bundle_txt_path.resolve()),
                    "latestReviewJson": str(latest_json_path.resolve()),
                    "latestReviewText": str(latest_txt_path.resolve()),
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
