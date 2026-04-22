#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh an exported implementation package JSON to the latest file scaffold format."
    )
    parser.add_argument("input", help="Path to the exported implementation package JSON.")
    parser.add_argument("--output", help="Optional output path. Defaults to overwriting the input file.")
    return parser.parse_args()


def exportify(function_source: str) -> str:
    text = str(function_source or "").strip()
    if text.startswith("export "):
        return text
    return f"export {text}"


def steps_list(lifecycle: dict | None, key: str) -> list[str]:
    if not lifecycle:
        return []
    section = lifecycle.get(key) or {}
    steps = section.get("steps") or []
    return [str(step) for step in steps]


def build_package_files(payload: dict) -> dict:
    bridge_template = payload["bridgeTemplate"]
    driver_template = payload["driverTemplate"]
    preset_snapshot = payload["templatePresets"]
    health_snapshot = payload["healthSnapshot"]
    preflight_snapshot = payload["hostPreflight"]
    admission_snapshot = payload["admission"]
    action_policy_snapshot = payload["actionPolicy"]

    bridge_file_name = f"bridge/{bridge_template.get('resolvedBridgePreset') or bridge_template.get('bridgePreset') or 'auto'}.js"
    driver_file_name = f"driver/{driver_template.get('resolvedDriverPreset') or driver_template.get('driverPreset') or 'auto'}.js"
    health_file_name = "runtime/health.js"
    wiring_file_name = "runtime/wiring.js"
    policy_file_name = "runtime/policy.json"
    package_json_file_name = "package.json"

    required_bridge_methods = list(bridge_template.get("requiredMethods") or [])
    attach_bridge_methods = [name for name in required_bridge_methods if not name.lower().startswith(("stop", "dispose", "close", "detach"))]
    detach_bridge_methods = [name for name in required_bridge_methods if name.lower().startswith(("stop", "close", "detach"))]
    dispose_bridge_methods = [name for name in required_bridge_methods if name.lower().startswith("dispose")]

    bridge_method_body = "\n\n".join(
        exportify(source) for source in (bridge_template.get("methodTemplates") or {}).values()
    )

    runtime_prefix = driver_template.get("runtimePrefix") or "drv-runtime"
    driver_lifecycle = driver_template.get("lifecycle") or {}
    driver_scaffold = "\n".join(
        [
            "const REQUIRED_BRIDGE_METHODS = " + json.dumps(required_bridge_methods, ensure_ascii=False, indent=2) + ";",
            "const ATTACH_BRIDGE_METHODS = " + json.dumps(attach_bridge_methods, ensure_ascii=False, indent=2) + ";",
            "const DETACH_BRIDGE_METHODS = " + json.dumps(detach_bridge_methods, ensure_ascii=False, indent=2) + ";",
            "const DISPOSE_BRIDGE_METHODS = " + json.dumps(dispose_bridge_methods, ensure_ascii=False, indent=2) + ";",
            "",
            "function buildResult(action, extra) {",
            "  return Object.assign({ action: action, ok: true, at: new Date().toISOString() }, extra || {});",
            "}",
            "",
            "async function callBridge(hostBridge, methodName, payload) {",
            "  if (!hostBridge || typeof hostBridge[methodName] !== 'function') {",
            "    return buildResult('bridge-skip', { methodName: methodName, skipped: true, payload: payload || null });",
            "  }",
            "  const value = await hostBridge[methodName](payload || {});",
            "  return buildResult('bridge-call', { methodName: methodName, value: value });",
            "}",
            "",
            "export async function init(ctx, hostBridge) {",
            f"  const runtimeId = String((ctx && ctx.runtimePrefix) || {json.dumps(runtime_prefix, ensure_ascii=False)}) + '-' + Date.now();",
            "  const bootstrap = REQUIRED_BRIDGE_METHODS.length ? await callBridge(hostBridge, REQUIRED_BRIDGE_METHODS[0], Object.assign({}, ctx || {}, { runtimeId: runtimeId })) : null;",
            f"  return buildResult('init', {{ runtimeId: runtimeId, bootstrap: bootstrap, steps: {json.dumps(steps_list(driver_lifecycle, 'init'), ensure_ascii=False)} }});",
            "}",
            "",
            "export async function attach(ctx, payload, hostBridge) {",
            "  const calls = [];",
            "  for (const methodName of ATTACH_BRIDGE_METHODS) {",
            "    calls.push(await callBridge(hostBridge, methodName, Object.assign({}, ctx || {}, payload || {}, { runtimeId: ctx && ctx.runtimeId ? ctx.runtimeId : undefined })));",
            "  }",
            f"  const sessionId = String((ctx && ctx.runtimeId) || {json.dumps(runtime_prefix, ensure_ascii=False)}) + '-session-' + String((payload && payload.tileIndex) || 0);",
            f"  return buildResult('attach', {{ sessionId: sessionId, calls: calls, payload: payload || null, steps: {json.dumps(steps_list(driver_lifecycle, 'attach'), ensure_ascii=False)} }});",
            "}",
            "",
            "export async function refresh(ctx, payload, hostBridge) {",
            "  const methodName = ATTACH_BRIDGE_METHODS.length > 1 ? ATTACH_BRIDGE_METHODS[ATTACH_BRIDGE_METHODS.length - 1] : ATTACH_BRIDGE_METHODS[0];",
            "  const refreshResult = methodName ? await callBridge(hostBridge, methodName, Object.assign({}, ctx || {}, payload || {}, { refresh: true })) : null;",
            f"  return buildResult('refresh', {{ payload: payload || null, refreshResult: refreshResult, steps: {json.dumps(steps_list(driver_lifecycle, 'refresh'), ensure_ascii=False)} }});",
            "}",
            "",
            "export async function detach(ctx, payload, hostBridge) {",
            "  const calls = [];",
            "  for (const methodName of DETACH_BRIDGE_METHODS) {",
            "    calls.push(await callBridge(hostBridge, methodName, Object.assign({}, ctx || {}, payload || {}, { runtimeId: ctx && ctx.runtimeId ? ctx.runtimeId : undefined })));",
            "  }",
            f"  return buildResult('detach', {{ calls: calls, payload: payload || null, steps: {json.dumps(steps_list(driver_lifecycle, 'detach'), ensure_ascii=False)} }});",
            "}",
            "",
            "export async function dispose(ctx, hostBridge) {",
            "  const calls = [];",
            "  for (const methodName of DISPOSE_BRIDGE_METHODS) {",
            "    calls.push(await callBridge(hostBridge, methodName, Object.assign({}, ctx || {}, { runtimeId: ctx && ctx.runtimeId ? ctx.runtimeId : undefined })));",
            "  }",
            f"  return buildResult('dispose', {{ calls: calls, steps: {json.dumps(steps_list(driver_lifecycle, 'dispose'), ensure_ascii=False)} }});",
            "}",
        ]
    )

    health_scaffold = "\n".join(
        [
            "export async function runHealthCheck(ctx) {",
            "  return {",
            f"    bridgeReadiness: {json.dumps(health_snapshot.get('bridgeReadiness') or 'Pending', ensure_ascii=False)},",
            f"    hostReadiness: {json.dumps(health_snapshot.get('hostReadiness') or 'Pending', ensure_ascii=False)},",
            f"    preflight: {json.dumps(preflight_snapshot.get('overall') or 'Pending', ensure_ascii=False)},",
            f"    admission: {json.dumps(admission_snapshot.get('lastDecision') or 'Not evaluated', ensure_ascii=False)},",
            f"    actionPolicy: {json.dumps(action_policy_snapshot.get('summary') or 'Not evaluated', ensure_ascii=False)}",
            "  };",
            "}",
            "",
            "export function startHeartbeat(ctx) {",
            f"  // intervalMs: {int(health_snapshot.get('heartbeatIntervalMs') or 4800)}",
            "}",
            "",
            "export function stopHeartbeat(ctx) {",
            "  // stop runtime heartbeat",
            "}",
            "",
            "export async function recover(ctx) {",
            f"  // policy: {json.dumps(health_snapshot.get('recoveryPolicy') or 'reinit-driver', ensure_ascii=False)}",
            "}",
        ]
    )

    wiring_scaffold = "\n".join(
        [
            f"import * as bridge from '../{bridge_file_name}';",
            f"import * as driver from '../{driver_file_name}';",
            f"import * as health from '../{health_file_name}';",
            "",
            "export function createRuntimeWiring() {",
            "  return { bridge, driver, health };",
            "}",
        ]
    )

    policy_json = json.dumps(
        {
            "preflight": preflight_snapshot or None,
            "admission": admission_snapshot or None,
            "actionPolicy": action_policy_snapshot or None,
            "health": health_snapshot or None,
            "templatePresets": preset_snapshot,
        },
        ensure_ascii=False,
        indent=2,
    )

    readme = "\n".join(
        [
            "# Renderer Implementation Package",
            "",
            f"- Driver kind: `{driver_template.get('driverKind')}`",
            f"- Bridge preset: `{preset_snapshot.get('resolvedBridgePreset')}`",
            f"- Driver preset: `{preset_snapshot.get('resolvedDriverPreset')}`",
            f"- Host type: `{bridge_template.get('hostType')}`",
            f"- Runtime prefix: `{driver_template.get('runtimePrefix')}`",
            "",
            "## Next Step",
            "",
            f"1. Fill the bridge methods in `{bridge_file_name}`.",
            f"2. Fill the lifecycle implementation in `{driver_file_name}`.",
            "3. Wire the exported functions back into the runtime shell.",
            f"4. Validate runtime health and policy using `{health_file_name}` and `{policy_file_name}`.",
            "",
        ]
    )

    return {
        package_json_file_name: json.dumps(
            {
                "name": f"{preset_snapshot.get('resolvedBridgePreset') or 'renderer-package'}-{preset_snapshot.get('resolvedDriverPreset') or 'runtime'}",
                "private": True,
                "type": "module",
            },
            ensure_ascii=False,
            indent=2,
        ),
        "manifest.json": json.dumps(
            {
                "driverKind": driver_template.get("driverKind"),
                "bridgePreset": preset_snapshot.get("resolvedBridgePreset"),
                "driverPreset": preset_snapshot.get("resolvedDriverPreset"),
                "hostType": bridge_template.get("hostType"),
                "runtimePrefix": driver_template.get("runtimePrefix"),
                "runtimeSupportFiles": [health_file_name, wiring_file_name, policy_file_name],
                "requiredBridgeMethods": required_bridge_methods,
                "moduleType": "module",
            },
            ensure_ascii=False,
            indent=2,
        ),
        bridge_file_name: bridge_method_body,
        driver_file_name: driver_scaffold,
        health_file_name: health_scaffold,
        wiring_file_name: wiring_scaffold,
        policy_file_name: policy_json,
        "README.md": readme,
    }


def refresh_payload(payload: dict) -> dict:
    required_top_keys = [
        "bridgeTemplate",
        "driverTemplate",
        "healthSnapshot",
        "hostPreflight",
        "admission",
        "actionPolicy",
        "templatePresets",
    ]
    missing = [key for key in required_top_keys if key not in payload]
    if missing:
        raise ValueError(f"Implementation package export is missing keys: {missing}")
    payload["files"] = build_package_files(payload)
    return payload


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        refreshed = refresh_payload(payload)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(refreshed, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # pragma: no cover - command line failure path
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "input": str(input_path.resolve()),
                "output": str(output_path.resolve()),
                "packageName": refreshed.get("packageName"),
                "fileCount": len(refreshed.get("files") or {}),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
