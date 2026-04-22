#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class ProbeSummary:
    session_present: bool
    connectivity_ok: bool
    any_http_response: bool
    stage: str
    probe_preset: str
    probe_count: int
    resource_ready: bool
    xres_context_ready: bool
    cameras_ready: bool
    preview_urls_ready: bool
    tvwall_ready: bool
    tvms_context_ready: bool
    local_proxy_ready: bool
    video_monitor_menu_source: str
    recommendation: str
    next_step: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze a live probe bundle and emit machine-readable and markdown summaries."
    )
    parser.add_argument("bundle_dir", help="Path to a bundle directory created by platform_quick_capture_bundle.sh")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def last_login_timestamp(session: dict[str, Any]) -> str:
    line = str(session.get("lastLoginLine") or "")
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
    return match.group(1) if match else ""


def probe_by_path(probes: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    for probe in probes:
        if probe.get("path") == path:
            return probe
    return None


def probe_by_key(probes: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    for probe in probes:
        if probe.get("key") == key:
            return probe
    return None


def probe_content_text(probe: dict[str, Any] | None) -> str:
    if not probe:
        return ""
    content = probe.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content and all(isinstance(item, int) and 0 <= item <= 255 for item in content):
        try:
            return bytes(content).decode("utf-8", errors="replace")
        except Exception:
            pass
    if isinstance(content, dict) and "content" in content:
        nested = content.get("content")
        if isinstance(nested, str):
            return nested
        if isinstance(nested, list) and nested and all(isinstance(item, int) and 0 <= item <= 255 for item in nested):
            try:
                return bytes(nested).decode("utf-8", errors="replace")
            except Exception:
                pass
    if content is not None:
        try:
            return json.dumps(content, ensure_ascii=False)
        except Exception:
            return str(content)
    response_body = probe.get("responseBody")
    return response_body if isinstance(response_body, str) else ""


def probe_has_app_auth_failure(probe: dict[str, Any] | None) -> bool:
    text = probe_content_text(probe)
    lowered = text.lower()
    return "token is null" in lowered or "request forbidden" in lowered or "0x11900001" in lowered


def probe_ok(probes: list[dict[str, Any]], path: str) -> bool:
    probe = probe_by_path(probes, path)
    return bool(probe and probe.get("ok") and not probe_has_app_auth_failure(probe))


def probe_ok_by_key(probes: list[dict[str, Any]], key: str) -> bool:
    probe = probe_by_key(probes, key)
    return bool(probe and probe.get("ok") and not probe_has_app_auth_failure(probe))


def build_summary(bundle_dir: Path, bundle_summary: dict[str, Any], probe_output: dict[str, Any]) -> ProbeSummary:
    session = bundle_summary.get("session") or probe_output.get("session") or {}
    probes = probe_output.get("probes") or []
    connectivity = probe_output.get("connectivity") or {}
    windows_env = bundle_summary.get("windowsEnv") or {}
    menu = windows_env.get("menu") or {}
    session_present = bool(session.get("loginUrl") and session.get("ticket"))
    any_http_response = any(probe.get("statusCode") is not None for probe in probes)
    any_app_auth_failure = any(probe_has_app_auth_failure(probe) for probe in probes)
    connectivity_ok = bool(connectivity.get("ok")) or any_http_response
    resource_ready = probe_ok(probes, "/api/resource/v1/unit/getAllTreeCode")
    xres_context_ready = probe_ok_by_key(probes, "xres-org-tree") or probe_ok_by_key(probes, "xres-org-tree-proxy")
    cameras_ready = probe_ok(probes, "/api/resource/v1/cameras")
    preview_urls_ready = probe_ok(probes, "/api/video/v1/cameras/previewURLs")
    tvwall_ready = probe_ok(probes, "/api/tvms/v1/tvwall/allResources")
    tvms_context_ready = (
        probe_ok_by_key(probes, "tvms-all")
        or probe_ok_by_key(probes, "tvms-ruok")
        or probe_ok_by_key(probes, "tvms-all-proxy")
        or probe_ok_by_key(probes, "tvms-ruok-proxy")
    )
    local_proxy_ready = any(
        str(probe.get("authMode") or "").startswith("local_proxy")
        and probe.get("ok")
        and not probe_has_app_auth_failure(probe)
        for probe in probes
    )
    video_monitor_menu_source = str(menu.get("videoMonitorMenuSourceAssessment") or "unknown")

    if not session_present:
        recommendation = "session-missing"
        next_step = "Reconnect gov network, keep client logged in, and rerun quick capture bundle."
    elif xres_context_ready and tvms_context_ready and preview_urls_ready:
        recommendation = "ready-for-platform-spike-live"
        next_step = "Proceed to real platform_spike_poc binding and preview/tvwall runtime verification."
    elif xres_context_ready and tvms_context_ready:
        recommendation = "run-full-probe"
        next_step = "Run full live probe to validate cameras and previewURLs after service-context discovery succeeds."
    elif any_app_auth_failure:
        recommendation = "auth-header-mismatch"
        next_step = "Gateway and service context are reachable, but backend still rejects the current auth shape. Prefer the 视频监控 page-side Container Auth Probe, or rerun quick capture bundle with the updated probe."
    elif any_http_response and not (resource_ready or xres_context_ready or tvwall_ready or tvms_context_ready):
        recommendation = "endpoint-mismatch"
        next_step = "Gateway is reachable, but current probe paths do not match the deployed service contexts. Refresh probe candidates and rerun quick capture bundle."
    elif not connectivity_ok:
        recommendation = "network-blocked"
        next_step = "Wait for a stable gov network window, then rerun quick capture bundle or quick live probe."
    else:
        recommendation = "partial-platform-readiness"
        next_step = "Inspect permissions/auth path for resource/tvwall and retry with a stable gov network window."

    return ProbeSummary(
        session_present=session_present,
        connectivity_ok=connectivity_ok,
        any_http_response=any_http_response,
        stage=str(probe_output.get("stage") or bundle_summary.get("stage") or ""),
        probe_preset=str(probe_output.get("probePreset") or bundle_summary.get("probePreset") or ""),
        probe_count=len(probes),
        resource_ready=resource_ready,
        xres_context_ready=xres_context_ready,
        cameras_ready=cameras_ready,
        preview_urls_ready=preview_urls_ready,
        tvwall_ready=tvwall_ready,
        tvms_context_ready=tvms_context_ready,
        local_proxy_ready=local_proxy_ready,
        video_monitor_menu_source=video_monitor_menu_source,
        recommendation=recommendation,
        next_step=next_step,
    )


def build_markdown(bundle_dir: Path, bundle_summary: dict[str, Any], probe_output: dict[str, Any], summary: ProbeSummary) -> str:
    session = bundle_summary.get("session") or probe_output.get("session") or {}
    probes = probe_output.get("probes") or []
    auth_context_path = bundle_dir / "clientframe_auth_context.json"
    auth_context = load_json(auth_context_path) if auth_context_path.exists() else {}
    windows_env = bundle_summary.get("windowsEnv") or {}
    menu = windows_env.get("menu") or {}
    service_summaries = auth_context.get("serviceSummaries") or {}
    xres_candidates = (service_summaries.get("xres:xres-search") or {}).get("candidateTokens") or []
    tvms_candidates = (service_summaries.get("tvms:tvms") or {}).get("candidateTokens") or []
    lines = [
        "# Live Probe Bundle Analysis",
        "",
        f"- Bundle Dir: `{bundle_dir}`",
        f"- Generated At: `{bundle_summary.get('generatedAt') or probe_output.get('generatedAt') or ''}`",
        f"- Updated At: `{probe_output.get('updatedAt') or bundle_summary.get('updatedAt') or ''}`",
        f"- Stage: `{summary.stage}`",
        f"- Probe Preset: `{summary.probe_preset}`",
        f"- Login URL: `{session.get('loginUrl') or ''}`",
        f"- User Index Code: `{session.get('userIndexCode') or ''}`",
        f"- Last Login Time: `{last_login_timestamp(session)}`",
        "",
        "## Readiness",
        "",
        f"- Session Present: `{summary.session_present}`",
        f"- Connectivity OK: `{summary.connectivity_ok}`",
        f"- Any HTTP Response: `{summary.any_http_response}`",
        f"- Resource Ready: `{summary.resource_ready}`",
        f"- XRES Context Ready: `{summary.xres_context_ready}`",
        f"- Cameras Ready: `{summary.cameras_ready}`",
        f"- Preview URLs Ready: `{summary.preview_urls_ready}`",
        f"- TV Wall Ready: `{summary.tvwall_ready}`",
        f"- TVMS Context Ready: `{summary.tvms_context_ready}`",
        f"- Local Proxy Ready: `{summary.local_proxy_ready}`",
        f"- Video Monitor Menu Source: `{summary.video_monitor_menu_source}`",
        f"- XRES Candidate Tokens: `{len(xres_candidates)}`",
        f"- TVMS Candidate Tokens: `{len(tvms_candidates)}`",
        "",
        "## Recommendation",
        "",
        f"- Recommendation: `{summary.recommendation}`",
        f"- Next Step: {summary.next_step}",
        "",
        "## ClientFrame Auth Context",
        "",
        f"- XRES First Candidate: `{xres_candidates[0] if xres_candidates else ''}`",
        f"- TVMS First Candidate: `{tvms_candidates[0] if tvms_candidates else ''}`",
        "",
        "## Menu Source",
        "",
        f"- Local Menu Patched: `{menu.get('localMenuPatched')}`",
        f"- Video Monitor Redirected: `{menu.get('videoMonitorRedirected')}`",
        f"- Probe Menu Present: `{menu.get('probeMenuPresent')}`",
        f"- Server Delivered Video Monitor: `{menu.get('serverDeliveredVideoMonitor')}`",
        f"- Latest Client0101 Component: `{menu.get('latestClient0101Component') or ''}`",
        "",
        "## Probe Results",
        "",
    ]
    for probe in probes:
        lines.append(
            f"- `{probe.get('path')}` | ok=`{probe.get('ok')}` | auth=`{probe.get('authMode')}` | status=`{probe.get('statusCode')}` | error=`{probe.get('error') or ''}`"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    bundle_dir = Path(args.bundle_dir).resolve()
    try:
        if not bundle_dir.exists():
            raise FileNotFoundError(f"Bundle directory does not exist: {bundle_dir}")
        bundle_summary_path = bundle_dir / "bundle_summary.json"
        probe_output_path = bundle_dir / "platform_live_probe_last.json"
        if not bundle_summary_path.exists():
            raise FileNotFoundError(f"bundle_summary.json is missing under: {bundle_dir}")
        if not probe_output_path.exists():
            raise FileNotFoundError(f"platform_live_probe_last.json is missing under: {bundle_dir}")

        bundle_summary = load_json(bundle_summary_path)
        probe_output = load_json(probe_output_path)
        summary = build_summary(bundle_dir, bundle_summary, probe_output)

        auth_context_path = bundle_dir / "clientframe_auth_context.json"
        auth_context = load_json(auth_context_path) if auth_context_path.exists() else {}
        analysis_json = {
            "bundleDir": str(bundle_dir),
            "summary": asdict(summary),
            "session": bundle_summary.get("session") or probe_output.get("session") or {},
            "connectivity": probe_output.get("connectivity") or {},
            "probePaths": [probe.get("path") for probe in (probe_output.get("probes") or [])],
            "clientFrameAuthContext": auth_context,
        }
        analysis_markdown = build_markdown(bundle_dir, bundle_summary, probe_output, summary)

        analysis_json_path = bundle_dir / "bundle_analysis.json"
        analysis_md_path = bundle_dir / "bundle_analysis.md"
        analysis_json_path.write_text(json.dumps(analysis_json, ensure_ascii=False, indent=2), encoding="utf-8")
        analysis_md_path.write_text(analysis_markdown, encoding="utf-8")

        result = {
            "ok": True,
            "bundleDir": str(bundle_dir),
            "analysisJsonPath": str(analysis_json_path),
            "analysisMarkdownPath": str(analysis_md_path),
            "summary": analysis_json["summary"],
        }
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
