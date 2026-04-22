#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


def default_windows_workdir() -> Path:
    script_root = Path(__file__).resolve().parents[2]
    candidates = [
        script_root,
        Path.cwd(),
        Path("/mnt/d/video_platform_release_windows_runtime"),
        Path("/mnt/c/video_platform_release_windows_runtime"),
        Path("D:/video_platform_release_windows_runtime"),
        Path("C:/video_platform_release_windows_runtime"),
    ]
    for candidate in candidates:
        if (candidate / "fixed_layout_programs").exists():
            return candidate
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not determine Windows runtime directory.")


def fixed_layout_lock_name(layout: int, mode: str | None = None) -> str:
    if mode:
        return f"fixed_layout_runtime_{layout}_{mode}"
    return f"fixed_layout_runtime_{layout}"


def fixed_layout_status_path(windows_workdir: Path, layout: int, mode: str | None = None) -> Path:
    suffix = f"_{mode}" if mode else ""
    return windows_workdir / "fixed_layout_programs" / "tmp" / f"runtime_status_layout_{layout}{suffix}.json"


def fixed_layout_control_path(windows_workdir: Path, layout: int, mode: str | None = None) -> Path:
    return fixed_layout_status_path(windows_workdir, layout, mode).with_suffix(".control.json")


def get_windows_process_info(pid: int) -> dict[str, object] | None:
    script = (
        f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; "
        "if ($null -eq $p) { 'NO_PROCESS' } else { "
        "$p | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress }"
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    if proc.returncode != 0 or not stdout or stdout == "NO_PROCESS":
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def process_matches_payload(process_info: dict[str, object] | None, payload: dict[str, object]) -> bool:
    if not process_info:
        return False
    command_line = str(process_info.get("CommandLine") or "")
    if not command_line:
        return False
    normalized_cmdline = [Path(token).name.lower() for token in command_line.replace('"', " ").split() if token.strip()]
    payload_argv = payload.get("argv")
    if not isinstance(payload_argv, list):
        return True
    normalized_payload = [Path(str(token)).name.lower() for token in payload_argv if str(token).strip()]
    return all(token in normalized_cmdline for token in normalized_payload)


def stop_windows_process(pid: int) -> bool:
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def write_control_command(control_path: Path, command: str, *, origin: str) -> bool:
    control_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "command": command,
        "origin": origin,
        "requested_at": time.time(),
    }
    temp_path = control_path.with_suffix(control_path.suffix + ".tmp")
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        temp_path.write_text(body, encoding="utf-8")
        temp_path.replace(control_path)
        return True
    except OSError:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def wait_for_process_exit(pid: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if get_windows_process_info(pid) is None:
            return True
        time.sleep(0.25)
    return get_windows_process_info(pid) is None


def load_lock_payload(path: Path) -> dict[str, object] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def handle_lock(path: Path, *, control_path: Path | None = None, graceful_timeout_seconds: float = 8.0) -> dict[str, object]:
    payload = load_lock_payload(path)
    result: dict[str, object] = {
        "lockPath": str(path),
        "action": "none",
        "removed": False,
        "stopped": False,
        "controlRequested": False,
    }
    if payload is None:
        path.unlink(missing_ok=True)
        result["action"] = "removed-unreadable-lock"
        result["removed"] = True
        return result

    pid = payload.get("pid")
    result["pid"] = pid
    if not isinstance(pid, int) or pid <= 0:
        path.unlink(missing_ok=True)
        result["action"] = "removed-invalid-pid-lock"
        result["removed"] = True
        return result

    process_info = get_windows_process_info(pid)
    result["processInfo"] = process_info
    if process_matches_payload(process_info, payload):
        graceful_requested = False
        if control_path is not None:
            graceful_requested = write_control_command(
                control_path,
                "stop",
                origin="stop_fixed_layout_runtime.py",
            )
            result["controlRequested"] = graceful_requested
            result["controlPath"] = str(control_path)
        if graceful_requested:
            if wait_for_process_exit(pid, graceful_timeout_seconds):
                result["action"] = "requested-graceful-stop"
            else:
                stopped = stop_windows_process(pid)
                result["stopped"] = stopped
                result["action"] = (
                    "forced-stop-after-graceful-timeout" if stopped else "failed-graceful-then-force-stop"
                )
        else:
            stopped = stop_windows_process(pid)
            result["stopped"] = stopped
            result["action"] = "stopped-matching-process" if stopped else "failed-to-stop-matching-process"
    else:
        result["action"] = "removed-stale-lock"

    path.unlink(missing_ok=True)
    result["removed"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop a fixed-layout runtime and clean its lock file.")
    parser.add_argument("--layout", type=int, choices=(4, 6, 9, 12), required=True)
    parser.add_argument("--mode", choices=("windowed", "fullscreen"))
    parser.add_argument("--windows-workdir", help="Windows runtime workdir in WSL form.")
    parser.add_argument("--include-legacy-lock", action="store_true", help="Also remove the old shared fixed_layout_runtime.lock if present.")
    parser.add_argument(
        "--graceful-timeout-seconds",
        type=float,
        default=8.0,
        help="How long to wait for a cooperative stop before forcing the runtime process to exit.",
    )
    args = parser.parse_args()

    windows_workdir = Path(args.windows_workdir) if args.windows_workdir else default_windows_workdir()
    lock_dir = windows_workdir / "fixed_layout_programs" / "tmp" / "runtime_locks"
    targets = [lock_dir / f"{fixed_layout_lock_name(args.layout, args.mode)}.lock"]
    if args.include_legacy_lock:
        targets.append(lock_dir / "fixed_layout_runtime.lock")

    control_path = fixed_layout_control_path(windows_workdir, args.layout, args.mode)
    results = [
        handle_lock(path, control_path=control_path, graceful_timeout_seconds=max(args.graceful_timeout_seconds, 0.0))
        for path in targets
        if path.exists()
    ]
    print(json.dumps({"ok": True, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
