from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import keyboard

from admin_utils import current_integrity_level
from common import load_config
from controller import Controller
from detector import Detector
from layout_switcher import LayoutSwitchError, LayoutSwitcher
from logger_setup import setup_logger
from native_runtime_client import NativeRuntimeClient
from window_manager import WindowManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Windows-side runtime regression driver for the video platform client.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("inspect", help="Inspect current target window mode/layout state.")

    switch_mode_parser = subparsers.add_parser("switch-mode", help="Switch runtime mode via the fullscreen toggle.")
    switch_mode_parser.add_argument("mode", choices=["windowed", "fullscreen"])

    switch_layout_parser = subparsers.add_parser("switch-layout", help="Switch runtime layout via the toolbar layout panel.")
    switch_layout_parser.add_argument("layout", type=int, choices=[4, 6, 9, 12, 13])

    send_key_parser = subparsers.add_parser("send-key", help="Send a global hotkey into the active Windows session.")
    send_key_parser.add_argument("key", help="Key name accepted by the keyboard package, for example: f2")
    send_key_parser.add_argument("--repeat", type=int, default=1, help="How many times to send the key.")
    send_key_parser.add_argument("--interval", type=float, default=0.35, help="Delay between repeated key sends.")
    send_key_parser.add_argument("--settle", type=float, default=0.2, help="Initial settle delay before the first send.")

    dump_controls_parser = subparsers.add_parser("dump-controls", help="Dump visible top-area UIA controls for the target window.")
    dump_controls_parser.add_argument("--max-top", type=int, default=220, help="Only include controls above this Y coordinate.")
    dump_controls_parser.add_argument(
        "--types",
        nargs="*",
        default=["Button", "CheckBox", "Pane", "Text", "GroupBox"],
        help="Friendly UIA class names to include.",
    )

    click_control_parser = subparsers.add_parser("click-control", help="Click a visible top-area UIA control by filtered index.")
    click_control_parser.add_argument("index", type=int, help="Zero-based index within the filtered control list.")
    click_control_parser.add_argument("--max-top", type=int, default=220, help="Only include controls above this Y coordinate.")
    click_control_parser.add_argument(
        "--types",
        nargs="*",
        default=["Button", "CheckBox"],
        help="Friendly UIA class names to include.",
    )
    click_control_parser.add_argument("--post-wait", type=float, default=1.0, help="Delay after the click before re-inspecting state.")

    return parser.parse_args()


def build_runtime(config_path: str):
    config = load_config(config_path)
    logger = setup_logger(config.logging, config.path.parent)
    native_client = NativeRuntimeClient(config.path.parent, config.window, logger) if config.window.native_runtime_enabled else None
    window_manager = WindowManager(config.window, logger, native_client=native_client)
    controller = Controller(
        config.timing,
        logger,
        backend="native_engine" if config.window.native_runtime_enabled else config.window.control_backend,
        autohotkey_path=config.window.autohotkey_path,
        native_client=native_client,
    )
    detector = Detector(config.detection, logger)
    layout_switcher = LayoutSwitcher(
        window_manager,
        controller,
        logger,
        config=config,
        detector=detector,
        native_client=native_client,
    )
    return config, logger, native_client, window_manager, layout_switcher


def inspect_state(
    window_manager: WindowManager,
    layout_switcher: LayoutSwitcher,
    *,
    include_layout: bool = True,
) -> dict[str, object]:
    target_window = window_manager.find_target_window()
    current_integrity = current_integrity_level()
    detected_mode = window_manager.detect_mode(target_window, "auto")
    detected_layout = None
    # 固定 fullscreen 程序的布局本来就是外部锁定值；这里如果再跑 layout probe，
    # 测试驱动本身就会主动拉开“窗口分割”面板污染现场状态。
    should_probe_layout = include_layout and detected_mode != "fullscreen"
    if should_probe_layout:
        detected_layout = layout_switcher.detect_current_layout(target_window=target_window)
    return {
        "integrity": current_integrity.label,
        "target_integrity": target_window.integrity_label,
        "hwnd": target_window.hwnd,
        "pid": target_window.process_id,
        "title": target_window.title,
        "mode": detected_mode,
        "layout": detected_layout,
        "client_rect": target_window.client_rect.to_bbox(),
        "monitor_rect": target_window.monitor_rect.to_bbox(),
    }


def send_keys(key: str, *, repeat: int, interval: float, settle: float) -> dict[str, object]:
    time.sleep(max(0.0, settle))
    for index in range(max(1, int(repeat))):
        keyboard.send(key)
        if index + 1 < repeat:
            time.sleep(max(0.0, interval))
    return {
        "key": key,
        "repeat": max(1, int(repeat)),
        "interval": max(0.0, interval),
        "settle": max(0.0, settle),
    }


def dump_controls(window_manager: WindowManager, *, max_top: int, allowed_types: list[str]) -> dict[str, object]:
    from pywinauto import Desktop

    target_window = window_manager.find_target_window()
    root = Desktop(backend="uia").window(handle=target_window.hwnd)
    rows: list[dict[str, object]] = []
    allowed = set(allowed_types)
    for control in root.descendants():
        try:
            rect = control.rectangle()
            friendly_name = control.friendly_class_name()
            if friendly_name not in allowed:
                continue
            if rect.width() <= 0 or rect.height() <= 0 or rect.top > max_top:
                continue
            rows.append(
                {
                    "top": rect.top,
                    "left": rect.left,
                    "right": rect.right,
                    "bottom": rect.bottom,
                    "type": friendly_name,
                    "text": (control.window_text() or "").strip(),
                }
            )
        except Exception:
            continue
    rows.sort(key=lambda item: (int(item["top"]), int(item["left"]), str(item["type"]), str(item["text"])))
    return {
        "target": {
            "hwnd": target_window.hwnd,
            "pid": target_window.process_id,
            "title": target_window.title,
            "client_rect": target_window.client_rect.to_bbox(),
            "monitor_rect": target_window.monitor_rect.to_bbox(),
            "mode": window_manager.detect_mode(target_window, "auto"),
        },
        "controls": rows,
    }


def click_control(window_manager: WindowManager, layout_switcher: LayoutSwitcher, *, index: int, max_top: int, allowed_types: list[str], post_wait: float) -> dict[str, object]:
    from pywinauto import Desktop

    target_window = window_manager.find_target_window()
    root = Desktop(backend="uia").window(handle=target_window.hwnd)
    allowed = set(allowed_types)
    candidates = []
    for control in root.descendants():
        try:
            rect = control.rectangle()
            friendly_name = control.friendly_class_name()
            if friendly_name not in allowed:
                continue
            if rect.width() <= 0 or rect.height() <= 0 or rect.top > max_top:
                continue
            candidates.append((rect.top, rect.left, friendly_name, (control.window_text() or "").strip(), control))
        except Exception:
            continue

    candidates.sort(key=lambda item: (int(item[0]), int(item[1]), str(item[2]), str(item[3])))
    if index < 0 or index >= len(candidates):
        raise SystemExit(f"Control index out of range: index={index} candidate_count={len(candidates)}")

    _, _, friendly_name, text, control = candidates[index]
    rect = control.rectangle()
    control.click_input()
    time.sleep(max(0.0, post_wait))
    return {
        "clicked": {
            "index": index,
            "type": friendly_name,
            "text": text,
            "rect": [rect.left, rect.top, rect.right, rect.bottom],
        },
        "current_state": inspect_state(window_manager, layout_switcher),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = parse_args()
    if platform.system() != "Windows":
        raise SystemExit("runtime_test_driver.py must run inside a Windows desktop session.")

    config, _, native_client, window_manager, layout_switcher = build_runtime(args.config)
    try:
        if args.command == "inspect":
            payload = inspect_state(window_manager, layout_switcher)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.command == "switch-mode":
            result = layout_switcher.switch_mode(args.mode)
            payload = {
                "requested_mode": args.mode,
                "switch_result": result,
                "current_state": inspect_state(window_manager, layout_switcher),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.command == "switch-layout":
            result = layout_switcher.switch_layout(args.layout)
            payload = {
                "requested_layout": args.layout,
                "switch_result": result,
                "current_state": inspect_state(window_manager, layout_switcher),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.command == "send-key":
            payload = {
                "send_result": send_keys(
                    args.key,
                    repeat=args.repeat,
                    interval=args.interval,
                    settle=args.settle,
                ),
                # send-key 常用于现场暂停/恢复回归；这里不能再隐式跑 layout probe，
                # 否则固定 fullscreen 程序会被测试工具自己拉开“窗口分割”面板污染现场状态。
                "current_state": inspect_state(window_manager, layout_switcher, include_layout=False),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.command == "dump-controls":
            payload = dump_controls(
                window_manager,
                max_top=args.max_top,
                allowed_types=list(args.types),
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.command == "click-control":
            payload = click_control(
                window_manager,
                layout_switcher,
                index=args.index,
                max_top=args.max_top,
                allowed_types=list(args.types),
                post_wait=args.post_wait,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        raise SystemExit(f"Unsupported command: {args.command}")
    except LayoutSwitchError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        if native_client is not None:
            native_client.close()


if __name__ == "__main__":
    raise SystemExit(main())
