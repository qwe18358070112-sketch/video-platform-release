from __future__ import annotations

"""项目自测脚本。

设计原则：
1. 不依赖 Win32 实机桌面，因此可在开发容器、CI、其他电脑上先做静态与纯逻辑验收。
2. 对这次新增的高风险功能做回归：顺序、模板、收藏夹排序、配置加载、动作路径语义、F11/F9 语义。
3. 输出 JSON 报告，便于 Codex / 人工 / 发布脚本复用。
"""

import argparse
import compileall
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Callable

from PIL import Image, ImageDraw

from common import ConfirmState, Rect, RuntimeGuardConfig, VisualViewState, WindowInfo, WindowSnapshot, load_config
from detector import Detector
from favorites_reader import FavoritesReader
from grid_mapper import GridMapper
from layout_switcher import build_layout_option_index, resolve_layout_switch_target
from runtime_guard import RuntimeGuard
if "keyboard" not in sys.modules:
    keyboard_stub = ModuleType("keyboard")
    keyboard_stub.add_hotkey = lambda *args, **kwargs: object()
    keyboard_stub.remove_hotkey = lambda *args, **kwargs: None
    keyboard_stub.press_and_release = lambda *args, **kwargs: None
    keyboard_stub.on_press_key = lambda *args, **kwargs: None
    keyboard_stub.unhook_all = lambda *args, **kwargs: None
    sys.modules["keyboard"] = keyboard_stub
for win32_module_name in ("win32api", "win32con", "win32gui", "win32process"):
    if win32_module_name not in sys.modules:
        sys.modules[win32_module_name] = ModuleType(win32_module_name)
from scheduler import PollingScheduler
from visual_shell_detector import analyze_windowed_shell_image, looks_like_windowed_shell


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_REPORT = PROJECT_ROOT / "tmp" / "self_test_report.json"


DOCS_TO_VALIDATE = {
    "README.md": [
        "单击选中 -> 双击放大 -> 停留 N 秒 -> 双击返回 -> 停留 N 秒 -> 下一路",
        "timing.dwell_seconds",
        "timing.post_restore_dwell_seconds",
        "python -m compileall .",
        "不能只看命令返回成功",
        "优先看界面控件是否仍是非全屏宫格",
        "skip_on_detected_issue: true",
        "`F1`：切换 `自动识别 / 手动锁定`",
    ],
    "README_DEPLOY.md": [
        "单击选中 -> 双击放大 -> 放大停留 dwell_seconds -> 双击返回 -> 返回后停留 post_restore_dwell_seconds -> 下一路",
        "python -m compileall .",
        "命令返回成功",
        "程序仍执行完整动作路径",
    ],
    "HOW_TO_USE.md": [
        "单击选中 -> 双击放大 -> 停留 N 秒 -> 双击返回 -> 停留 N 秒 -> 下一路",
        "F11",
        "F9",
        "python -m compileall .",
        "中央宫格是否真的切换成功",
        "不要直接当成“全屏界面”",
        "继续执行完整动作路径",
        "恢复前都会再次核对“现场实际状态”与“手动目标”是否一致",
    ],
    "提示词.txt": [
        "单击选中 -> 双击放大 -> 停留 dwell_seconds 秒 -> 双击返回 -> 停留 post_restore_dwell_seconds 秒 -> 下一路",
    ],
    "提示词_增强版.txt": [
        "本项目的唯一正确动作路径",
        "post_restore_dwell_seconds",
    ],
    "LAYOUT_SWITCH_MANUAL.md": [
        "自动识别全屏 / 非全屏",
        "自动识别当前更像 4 / 6 / 9 / 12 中的哪一种宫格",
        "python app.py --switch-layout 4",
        "顶部工具栏里的 `窗口分割`",
        "不要把左侧收藏夹树当成布局切换入口",
        "`F1`：切换 `自动识别 / 手动锁定`",
        "是否已闭环匹配",
    ],
    "CODEX_LOCAL_ADMIN_PROMPT.txt": [
        "单击选中 -> 双击放大 -> 停留 dwell_seconds 秒 -> 双击返回 -> 停留 post_restore_dwell_seconds 秒 -> 下一路",
        "python -m compileall .",
        "命令返回成功",
    ],
    "CALIBRATION_GUIDE.md": [
        "整个视频宫格大区域",
        "python app.py --inspect-calibration windowed",
    ],
    "MIGRATION_GUIDE.md": [
        "旧项目目录",
        "新交付目录",
    ],
}

FORBIDDEN_DOC_FRAGMENTS = [
    "单路双击放大 -> 停留 -> 返回宫格 -> 继续下一路",
    "双击返回 -> 切换到下一个窗格",
    "F11 = 返回宫格并直接跳过当前路",
]


def run_check(name: str, fn: Callable[[], Any], results: list[dict[str, Any]]) -> None:
    try:
        value = fn()
        results.append({"name": name, "ok": True, "detail": value})
    except Exception as exc:  # pragma: no cover - 用于自测报告
        results.append({"name": name, "ok": False, "detail": str(exc)})


def _read_optional_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _optional_runtime_driver_text() -> str | None:
    return _read_optional_text(PROJECT_ROOT / "tmp" / "runtime_test_driver.py")


def _make_fullscreen_six_prepare_hint_scheduler() -> PollingScheduler:
    config = load_config(PROJECT_ROOT / "fixed_layout_programs" / "config.layout6.fullscreen.yaml")
    logger = logging.getLogger("self-test.fullscreen6.prepare_hint")
    dummy = SimpleNamespace()
    scheduler = PollingScheduler(
        config,
        dummy,
        dummy,
        dummy,
        dummy,
        dummy,
        logger,
        "fullscreen",
        6,
    )
    scheduler._current_mode = "unknown"
    scheduler._effective_mode = "fullscreen"
    scheduler._effective_layout = 6
    scheduler._runtime_layout = 6
    scheduler._last_pause_reason = "user_pause"
    scheduler._zoom_confirm_poll_boost_cycles_remaining = 2
    return scheduler



def test_compileall() -> dict[str, Any]:
    ok = compileall.compile_dir(str(PROJECT_ROOT), quiet=1)
    if not ok:
        raise RuntimeError("compileall returned False")
    return {"compiled": True}


def test_project_local_compileall_scope() -> dict[str, Any]:
    compileall_text = (PROJECT_ROOT / "compileall.py").read_text(encoding="utf-8")
    required_fragments = [
        "EXCLUDED_DIR_NAMES",
        '".venv"',
        '"dist"',
        '"logs"',
        '"tmp"',
        '"__pycache__"',
        "os.walk",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in compileall_text]
    if missing:
        raise RuntimeError(f"project-local compileall scope mismatch: missing={missing}")
    return {"checked_fragments": len(required_fragments)}


def test_native_runtime_probe_scaffold_is_wired() -> dict[str, Any]:
    bridge_sh = (PROJECT_ROOT / "windows_bridge.sh").read_text(encoding="utf-8")
    bridge_ps1 = (PROJECT_ROOT / "windows_bridge.ps1").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    native_readme = (PROJECT_ROOT / "native_runtime" / "README.md").read_text(encoding="utf-8")
    csproj = (PROJECT_ROOT / "native_runtime" / "VideoPlatform.NativeProbe" / "VideoPlatform.NativeProbe.csproj").read_text(encoding="utf-8")
    program_cs = (PROJECT_ROOT / "native_runtime" / "VideoPlatform.NativeProbe" / "Program.cs").read_text(encoding="utf-8")

    required_fragments = [
        "./windows_bridge.sh native-probe",
        '"native-probe"',
        "dotnet.exe not found. Install .NET SDK 8 on Windows before running native-probe.",
        "native_runtime/",
        "Windows 原生 UIA3 探针",
        "FlaUI.Core",
        "FlaUI.UIA3",
        "TargetFramework>net8.0-windows",
        "class ProbeOptions",
        "--open-layout-panel",
        "RecommendedPath",
        "sdk_or_web_plugin",
        "hybrid_native_uia_plus_sdk_or_readback",
        "窗口分割",
        "退出全屏",
        "VSClient.exe",
    ]
    searchable = "\n".join([bridge_sh, bridge_ps1, readme, native_readme, csproj, program_cs])
    missing = [fragment for fragment in required_fragments if fragment not in searchable]
    if missing:
        raise RuntimeError(f"native runtime probe scaffold missing fragments: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_native_runtime_engine_defaults_are_enabled() -> dict[str, Any]:
    expected_project = "native_runtime/VideoPlatform.NativeProbe/VideoPlatform.NativeProbe.csproj"

    def assert_native_defaults(cfg, *, source: str, expected_mode: str | None = None, expected_layout: int | None = None) -> None:
        if cfg.window.control_backend != "native_engine":
            raise RuntimeError(f"{source} must default to native_engine backend")
        if not cfg.window.native_runtime_enabled:
            raise RuntimeError(f"{source} must enable native runtime by default")
        if cfg.window.native_runtime_project != expected_project:
            raise RuntimeError(
                f"{source} native runtime project mismatch: {cfg.window.native_runtime_project!r}"
            )
        if cfg.window.native_runtime_tree_depth < 1:
            raise RuntimeError(f"{source} native runtime tree depth must be >= 1")
        if cfg.window.native_runtime_startup_timeout_seconds <= 0:
            raise RuntimeError(f"{source} native runtime startup timeout must be positive")
        if cfg.window.native_runtime_command_timeout_seconds <= 0:
            raise RuntimeError(f"{source} native runtime command timeout must be positive")
        if expected_mode is not None and cfg.profiles.active_mode != expected_mode:
            raise RuntimeError(f"{source} active_mode mismatch: {cfg.profiles.active_mode!r} != {expected_mode!r}")
        if expected_layout is not None and cfg.grid.layout != expected_layout:
            raise RuntimeError(f"{source} layout mismatch: {cfg.grid.layout!r} != {expected_layout!r}")

    config = load_config(PROJECT_ROOT / "config.yaml")
    example = load_config(PROJECT_ROOT / "config.example.yaml")
    assert_native_defaults(config, source="config.yaml")
    assert_native_defaults(example, source="config.example.yaml")

    fixed_dir = PROJECT_ROOT / "fixed_layout_programs"
    expected_pairs = {(layout, mode) for layout in (4, 6, 9, 12) for mode in ("windowed", "fullscreen")}
    observed_pairs: set[tuple[int, str]] = set()
    for path in sorted(fixed_dir.glob("config.layout*.*.yaml")):
        parts = path.name.split(".")
        if len(parts) != 4:
            continue
        layout_part = parts[1]
        mode_part = parts[2]
        if not layout_part.startswith("layout") or mode_part not in {"windowed", "fullscreen"}:
            continue
        layout_value = int(layout_part.replace("layout", "", 1))
        if layout_value not in {4, 6, 9, 12}:
            continue
        observed_pairs.add((layout_value, mode_part))
        cfg = load_config(path)
        assert_native_defaults(
            cfg,
            source=path.name,
            expected_mode=mode_part,
            expected_layout=layout_value,
        )

    if observed_pairs != expected_pairs:
        raise RuntimeError(f"fixed-layout native mode configs mismatch: observed={sorted(observed_pairs)}")

    return {
        "base_configs": 2,
        "fixed_layout_mode_configs": len(observed_pairs),
        "native_runtime_project": expected_project,
    }


def test_native_runtime_sidecar_command_surface_is_wired() -> dict[str, Any]:
    server_text = (PROJECT_ROOT / "native_runtime" / "VideoPlatform.NativeProbe" / "NativeAutomationServer.cs").read_text(
        encoding="utf-8"
    )
    client_text = (PROJECT_ROOT / "native_runtime_client.py").read_text(encoding="utf-8")
    controller_text = (PROJECT_ROOT / "controller.py").read_text(encoding="utf-8")
    window_manager_text = (PROJECT_ROOT / "window_manager.py").read_text(encoding="utf-8")
    layout_switcher_text = (PROJECT_ROOT / "layout_switcher.py").read_text(encoding="utf-8")
    app_text = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    required_server_fragments = [
        '"shutdown" => NativeAutomationResponse.Success',
        '"findTargetWindow" => NativeAutomationResponse.Success',
        '"getWindowInfo" => NativeAutomationResponse.Success',
        '"getForegroundWindow" => NativeAutomationResponse.Success',
        '"focusWindow" => NativeAutomationResponse.Success',
        '"listRelatedWindows" => NativeAutomationResponse.Success',
        '"detectWindowedVisualShell" => NativeAutomationResponse.Success',
        '"detectRuntimeSignals" => NativeAutomationResponse.Success',
        '["windowedVisualShellLikely"] = result.WindowedVisualShellLikely,',
        '["windowedVisualShellMetrics"] = result.WindowedVisualShellMetrics,',
        '"getRuntimeLayoutState" => NativeAutomationResponse.Success',
        '"selectRuntimeLayout" => NativeAutomationResponse.Success',
        '"invokeNamedControl" => NativeAutomationResponse.Success',
        '"pointerAction" => NativeAutomationResponse.Success',
        '"sendKey" => NativeAutomationResponse.Success',
        '"escape" => NativeInputBridge.SendEscape()',
        '"alt_f4" => NativeInputBridge.SendAltF4()',
        "public static bool PointerAction(int x, int y, bool isDoubleClick, bool restoreCursor)",
        "public static AutomationElement? FindFirstControlByName(",
        "private static NativeRuntimeLayoutCloseAttemptResult AttemptCloseLayoutPanel(",
        "result.WindowedVisualShellMetrics = NativeWindowedVisualShellProbe.Analyze(target.ClientRect);",
        "public NativeWindowedVisualShellMetrics WindowedVisualShellMetrics { get; set; } = new();",
        "public bool WindowedVisualShellLikely => WindowedVisualShellMetrics.WindowedShellLike;",
        'result.Method = "split_invoke";',
        'result.Method = "escape";',
        'result.Method = "dismiss_click";',
        'result.Method = "failed";',
        "public bool SelectionConfirmed { get; set; }",
        "public string CloseMethod { get; set; } = string.Empty;",
        "public bool CloseFallbackUsed { get; set; }",
    ]
    missing_server = [fragment for fragment in required_server_fragments if fragment not in server_text]
    if missing_server:
        raise RuntimeError(f"native automation server fragments missing: {missing_server}")

    required_client_fragments = [
        "def _resolve_sidecar_command(self) -> list[str]:",
        "published_binary = self._resolve_published_sidecar_binary()",
        'str(published_binary),',
        '"serve"',
        "def _resolve_published_sidecar_binary(self) -> Path | None:",
        'self._repo_root / "runtime" / "native_runtime" / binary_name,',
        'self._request_locked("ping"',
        "self._repo_root = self._resolve_repo_root(Path(repo_root).resolve(), config)",
        "def _resolve_repo_root(candidate_root: Path, config: WindowSearchConfig) -> Path:",
        "for root in (candidate_root, *candidate_root.parents):",
        "if (root / project_rel).exists():",
        "def find_target_window(self) -> dict[str, Any]:",
        "def get_window_info(self, hwnd: int) -> dict[str, Any]:",
        "def focus_window(self, hwnd: int) -> dict[str, Any]:",
        "def list_related_windows(self, hwnd: int, process_id: int, render_process_names: list[str]) -> dict[str, Any]:",
        "def detect_windowed_visual_shell(self, hwnd: int) -> dict[str, Any]:",
        '"detectWindowedVisualShell"',
        "def detect_runtime_signals(",
        "def get_runtime_layout_state(",
        '"getRuntimeLayoutState"',
        "def select_runtime_layout(",
        '"selectRuntimeLayout"',
        "def invoke_named_control(",
        "def pointer_action(self, x: int, y: int, *, double: bool, restore_cursor: bool = True) -> dict[str, Any]:",
        'return self.request("sendKey", key=str(key))',
    ]
    missing_client = [fragment for fragment in required_client_fragments if fragment not in client_text]
    if missing_client:
        raise RuntimeError(f"native runtime client fragments missing: {missing_client}")

    required_python_wiring = [
        "native_client = NativeRuntimeClient(config.path.parent, config.window, logger)",
        'backend="native_engine" if config.window.native_runtime_enabled else "real_mouse"',
        "native_client=native_client",
        'if self._backend == "native_engine" and self._native_client is not None and self._native_client.enabled:',
        "self._native_client.pointer_action(point[0], point[1], double=False)",
        "self._native_client.pointer_action(point[0], point[1], double=True)",
        'self._native_client.send_key("escape")',
        'self._native_client.send_key("alt_f4")',
        "self._native_client.detect_runtime_signals(",
        "self._native_client.get_runtime_layout_state(",
        "self._native_client.select_runtime_layout(",
        'DEFAULT_RENDER_PROCESS_NAMES = ["VSClient.exe"]',
        "self._native_client.detect_windowed_visual_shell(window_info.hwnd)",
        'signal_payload.get("windowedVisualShellMetrics")',
        'signal_payload.get("windowedVisualShellLikely", False)',
        "def _normalize_native_windowed_visual_metrics(raw_metrics: object) -> dict[str, float]:",
        "def _native_get_runtime_layout_state(",
        "def _native_select_runtime_layout(",
        "def _invoke_fullscreen_toggle_native(self, target_window, *, expected_mode: str) -> None:",
        "def _close_layout_panel_native(self, target_window) -> bool:",
        "def _resolve_runtime_option_from_native_state(",
        "def _selected_layout_from_native_state(",
        "close_panel=True,",
        '"layout_switch native panel close not confirmed layout=%s close_method=%s fallback=%s"',
        '"native_panel_close_confirmed": None',
        '"native_panel_close_method": None',
    ]
    searchable_python = "\n".join([app_text, controller_text, window_manager_text, layout_switcher_text])
    missing_python = [fragment for fragment in required_python_wiring if fragment not in searchable_python]
    if missing_python:
        raise RuntimeError(f"native runtime python wiring fragments missing: {missing_python}")

    return {
        "server_fragments": len(required_server_fragments),
        "client_fragments": len(required_client_fragments),
        "python_wiring_fragments": len(required_python_wiring),
    }


def test_windowed_visual_shell_detector_distinguishes_samples() -> dict[str, Any]:
    windowed_samples = [
        PROJECT_ROOT / "非全屏4宫格.png",
        PROJECT_ROOT / "非全屏4宫格1.png",
    ]
    fullscreen_sample = PROJECT_ROOT / "tmp" / "current_fullscreen12_capture.png"
    for sample in windowed_samples:
        if not sample.exists():
            raise RuntimeError(f"missing windowed sample: {sample}")
    if not fullscreen_sample.exists():
        raise RuntimeError(f"missing fullscreen sample: {fullscreen_sample}")

    fullscreen_metrics = analyze_windowed_shell_image(Image.open(fullscreen_sample).convert("RGB"))
    if looks_like_windowed_shell(fullscreen_metrics):
        raise RuntimeError(f"windowed shell detector misclassified fullscreen sample: {fullscreen_metrics}")

    windowed_scores: list[float] = []
    for sample in windowed_samples:
        windowed_metrics = analyze_windowed_shell_image(Image.open(sample).convert("RGB"))
        if not looks_like_windowed_shell(windowed_metrics):
            raise RuntimeError(f"windowed shell detector failed on windowed sample {sample.name}: {windowed_metrics}")
        if windowed_metrics["windowed_shell_score"] <= fullscreen_metrics["windowed_shell_score"]:
            raise RuntimeError(
                "windowed shell score ordering mismatch: "
                f"sample={sample.name} windowed={windowed_metrics['windowed_shell_score']} "
                f"fullscreen={fullscreen_metrics['windowed_shell_score']}"
            )
        windowed_scores.append(float(windowed_metrics["windowed_shell_score"]))

    return {
        "windowed_samples": len(windowed_samples),
        "windowed_score_min": min(windowed_scores),
        "windowed_score_max": max(windowed_scores),
        "fullscreen_score": fullscreen_metrics["windowed_shell_score"],
        "fullscreen_left_bright_ratio": fullscreen_metrics["windowed_shell_left_bright_ratio"],
    }


def test_load_configs() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    example = load_config(PROJECT_ROOT / "config.example.yaml")
    if not config.detection.skip_on_detected_issue:
        raise RuntimeError("config.yaml must keep detected-issue skipping enabled for hard failures by default")
    if not example.detection.skip_on_detected_issue:
        raise RuntimeError("config.example.yaml must keep detected-issue skipping enabled for hard failures by default")
    if config.timing.dwell_seconds != 4 or config.timing.post_restore_dwell_seconds != 4:
        raise RuntimeError("config.yaml default dwell timings must stay aligned with docs at 4 / 4 seconds")
    if example.timing.dwell_seconds != 4 or example.timing.post_restore_dwell_seconds != 4:
        raise RuntimeError("config.example.yaml default dwell timings must stay aligned with docs at 4 / 4 seconds")
    if not config.favorites.enabled:
        raise RuntimeError("config.yaml must keep favorites reader enabled so favorites_name works on the target machine")
    if not example.favorites.enabled:
        raise RuntimeError("config.example.yaml must keep favorites reader enabled by default")
    if not config.layout_switch.require_cleared_scene_before_switch:
        raise RuntimeError("config.yaml must keep layout-switch clear-scene protection enabled by default")
    if not example.layout_switch.require_cleared_scene_before_switch:
        raise RuntimeError("config.example.yaml must keep layout-switch clear-scene protection enabled by default")
    if not config.layout_switch.fail_closed_on_guard_error:
        raise RuntimeError("config.yaml must fail closed when layout-switch scene guard cannot run")
    if not example.layout_switch.fail_closed_on_guard_error:
        raise RuntimeError("config.example.yaml must fail closed when layout-switch scene guard cannot run")
    return {
        "config_mode": config.profiles.active_mode,
        "example_mode": example.profiles.active_mode,
        "queue_depth": config.controls.max_queued_next_steps,
        "dwell_seconds": config.timing.dwell_seconds,
        "post_restore_dwell_seconds": config.timing.post_restore_dwell_seconds,
        "skip_on_detected_issue": config.detection.skip_on_detected_issue,
        "favorites_enabled": config.favorites.enabled,
        "layout_switch_guard_enabled": config.layout_switch.require_cleared_scene_before_switch,
        "layout_switch_fail_closed": config.layout_switch.fail_closed_on_guard_error,
    }


def test_fixed_layout_configs_are_isolated() -> dict[str, Any]:
    details: dict[str, dict[str, Any]] = {}
    for layout in (4, 6, 9, 12):
        cfg = load_config(PROJECT_ROOT / "fixed_layout_programs" / f"config.layout{layout}.yaml")
        if cfg.grid.layout != layout:
            raise RuntimeError(f"fixed layout config mismatch: layout={layout} actual={cfg.grid.layout}")
        if cfg.controls.instance_lock_name != f"fixed_layout_runtime_{layout}":
            raise RuntimeError(
                f"fixed layout instance lock mismatch: layout={layout} actual={cfg.controls.instance_lock_name!r}"
            )
        if not cfg.controls.lock_runtime_layout_to_requested:
            raise RuntimeError(f"fixed layout config must lock runtime layout to requested: layout={layout}")
        disabled_hotkeys = [
            cfg.hotkeys.profile_source_toggle,
            cfg.hotkeys.mode_cycle,
            cfg.hotkeys.layout_cycle,
        ]
        if any(str(value).strip().lower() != "disabled" for value in disabled_hotkeys):
            raise RuntimeError(f"fixed layout hotkeys not fully disabled: layout={layout} values={disabled_hotkeys}")
        if str(cfg.hotkeys.grid_order_cycle).strip().lower() != "f8":
            raise RuntimeError(
                f"fixed layout grid order hotkey must be f8 for operator switching: layout={layout} actual={cfg.hotkeys.grid_order_cycle!r}"
            )
        if f"runtime_status_layout_{layout}.json" not in str(cfg.status_overlay.status_file):
            raise RuntimeError(
                f"fixed layout status file mismatch: layout={layout} path={cfg.status_overlay.status_file}"
            )
        if cfg.input_guard.enabled:
            raise RuntimeError(f"fixed layout should disable input_guard for operator flow: layout={layout}")
        if cfg.status_overlay.auto_hide_ms != 0:
            raise RuntimeError(
                f"fixed layout overlay should stay visible during runtime: layout={layout} auto_hide_ms={cfg.status_overlay.auto_hide_ms}"
            )
        if cfg.hotkeys.debounce_ms > 120 or cfg.hotkeys.next_cell_debounce_ms > 60:
            raise RuntimeError(
                f"fixed layout hotkey debounce is too slow: layout={layout} debounce={cfg.hotkeys.debounce_ms} next={cfg.hotkeys.next_cell_debounce_ms}"
            )
        details[str(layout)] = {
            "instance_lock_name": cfg.controls.instance_lock_name,
            "lock_runtime_layout_to_requested": cfg.controls.lock_runtime_layout_to_requested,
            "status_file": str(cfg.status_overlay.status_file),
            "input_guard_enabled": cfg.input_guard.enabled,
            "auto_hide_ms": cfg.status_overlay.auto_hide_ms,
        }
    return details


def test_fixed_layout_generator_supports_mode_split() -> dict[str, Any]:
    text = (PROJECT_ROOT / "platform_spike" / "scripts" / "generate_fixed_layout_programs.py").read_text(
        encoding="utf-8"
    )
    required_fragments = [
        "--include-modes",
        'MODES = ("windowed", "fullscreen")',
        "def fixed_layout_lock_name(",
        'config["controls"]["instance_lock_name"] = fixed_layout_lock_name(layout)',
        'config["controls"]["lock_runtime_layout_to_requested"] = True',
        'config["input_guard"]["enabled"] = False',
        'config["hotkeys"]["grid_order_cycle"] = "f8"',
        'config["hotkeys"]["debounce_ms"] = 120',
        'config["status_overlay"]["auto_hide_ms"] = 0',
        'mode_config["profiles"]["active_mode"] = mode',
        'mode_config["controls"]["instance_lock_name"] = fixed_layout_lock_name(layout, mode)',
        'mode_config["controls"]["lock_runtime_layout_to_requested"] = True',
        'mode_config["input_guard"]["enabled"] = False',
        'mode_config["hotkeys"]["grid_order_cycle"] = "f8"',
        'mode_config["status_overlay"]["auto_hide_ms"] = 0',
        'run_layout{layout}_{mode}_fixed.bat',
        'run_fixed_layout_selector.bat',
        'run_fixed_layout_selector.sh',
        'fixed_layout_manifest.json',
        "PYTHON_CMD",
        'Install the portable fixed-layout package or run install_deps.bat first.',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in text]
    if missing:
        raise RuntimeError(f"fixed layout mode split fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_fixed_layout_packager_scaffold_is_present() -> dict[str, Any]:
    text = (PROJECT_ROOT / "platform_spike" / "scripts" / "package_fixed_layout_programs.py").read_text(
        encoding="utf-8"
    )
    required_fragments = [
        'f"video_platform_release_layout{layout}_fixed.zip"',
        "video_platform_release_layout{layout}_{mode}_fixed.zip",
        "--include-modes",
        "--portable-runtime",
        "video_platform_release_fixed_layout_suite.zip",
        "fixed_layout_bundles_manifest.json",
        "runtime/native_runtime/VideoPlatform.NativeProbe.exe",
        "runtime/python/python.exe",
        "portable_runtime_manifest.json",
        "..\\\\..",
        "native_runtime_client.py",
        "win_hotkeys.py",
        "FIXED_LAYOUT_PROGRAMS.md",
        "FIXED_LAYOUT_DEPLOY.md",
        "FIXED_LAYOUT_FREEZE_BASELINE.md",
        "FIXED_LAYOUT_INSTALL_AND_USE.md",
        "install_fixed_layout_suite.cmd",
        "install_fixed_layout_suite_gui.cmd",
        "repair_fixed_layout_runtime.cmd",
        "uninstall_fixed_layout_suite.cmd",
        "platform_spike/scripts/install_fixed_layout_suite.ps1",
        "platform_spike/scripts/repair_fixed_layout_runtime.ps1",
        "platform_spike/scripts/uninstall_fixed_layout_suite.ps1",
        "verify_fixed_layout_runtime.cmd",
        "platform_spike/scripts/verify_fixed_layout_runtime.py",
        "video_platform_release/__init__.py",
        "video_platform_release/project_layout.py",
        "video_platform_release/fixed_layout/__init__.py",
        "video_platform_release/fixed_layout/runtime_verifier.py",
        "fixed_layout_programs/fixed_layout_manifest.json",
        "fixed_layout_programs/stop_fixed_layout_selector.bat",
        "fixed_layout_programs/stop_fixed_layout_selector.sh",
        "platform_spike/scripts/stop_fixed_layout_runtime.py",
        "visual_shell_detector.py",
        "copy_tkinter_runtime(",
        "PORTABLE_RUNTIME_REQUIRED = (",
        "def portable_runtime_missing(runtime_root: Path) -> list[str]:",
        "def ensure_existing_runtime_ready(*, project_root: Path, runtime_root: Path, python_minor: str) -> None:",
        "def resolve_existing_runtime(project_root: Path, *, python_minor: str) -> Path | None:",
        "portable_runtime_root = resolve_existing_runtime(project_root, python_minor=args.python_minor)",
        "tcl86t.dll",
        "tk86t.dll",
        "_tkinter.pyd",
        "import cv2, yaml, PIL, psutil, keyboard, pywinauto, win32api, win32gui, win32con, tkinter;",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in text]
    if missing:
        raise RuntimeError(f"fixed layout packager fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_internal_package_scaffold_is_present() -> dict[str, Any]:
    package_init = (PROJECT_ROOT / "video_platform_release" / "__init__.py").read_text(encoding="utf-8")
    project_layout = (PROJECT_ROOT / "video_platform_release" / "project_layout.py").read_text(encoding="utf-8")
    fixed_layout_init = (
        PROJECT_ROOT / "video_platform_release" / "fixed_layout" / "__init__.py"
    ).read_text(encoding="utf-8")
    runtime_verifier = (
        PROJECT_ROOT / "video_platform_release" / "fixed_layout" / "runtime_verifier.py"
    ).read_text(encoding="utf-8")
    build_release_text = (PROJECT_ROOT / "build_release.py").read_text(encoding="utf-8")
    required_fragments = [
        ("package_init", package_init, "Internal package for shared project/runtime utilities."),
        ("project_layout", project_layout, "PROJECT_ROOT_MARKERS = (\"app.py\", \"common.py\", \"requirements.txt\")"),
        ("project_layout", project_layout, "def find_project_root("),
        ("project_layout", project_layout, "def find_script_project_root("),
        ("fixed_layout_init", fixed_layout_init, "Fixed-layout runtime helpers."),
        ("runtime_verifier", runtime_verifier, "EXPECTED_NATIVE_HELP = \"Start the JSON-line native automation sidecar server.\""),
        ("runtime_verifier", runtime_verifier, "def resolve_repo_root(candidate: str) -> Path:"),
        ("runtime_verifier", runtime_verifier, "from video_platform_release.project_layout import find_project_root, find_script_project_root"),
        ("runtime_verifier", runtime_verifier, "def main(argv: list[str] | None = None) -> int:"),
        ("build_release", build_release_text, "\"video_platform_release/project_layout.py\""),
        ("build_release", build_release_text, "\"video_platform_release/fixed_layout/runtime_verifier.py\""),
    ]
    missing = [f"{source}:{fragment}" for source, text, fragment in required_fragments if fragment not in text]
    if missing:
        raise RuntimeError(f"internal package scaffold missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_fixed_layout_windows_launcher_redirects_wsl_paths() -> dict[str, Any]:
    text = (PROJECT_ROOT / "fixed_layout_programs" / "run_layout4_windowed_fixed.bat").read_text(encoding="utf-8")
    required_fragments = [
        "setlocal EnableExtensions EnableDelayedExpansion",
        'findstr /I /C:"\\\\wsl.localhost\\\\" /C:"\\\\wsl$\\\\" >nul',
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%WINDOWS_RUNTIME_ROOT%\\windows_bridge.ps1" -RepoPath "%WINDOWS_RUNTIME_ROOT%" -Action run -AllowAutoElevate',
        'if exist runtime\\python\\python.exe set "PYTHON_CMD=runtime\\python\\python.exe"',
        "Please sync the project to D:\\video_platform_release_windows_runtime first.",
        "Install the portable fixed-layout package or run install_deps.bat first.",
        'pushd "%~dp0\\.." >nul',
        "Launcher failed with exit code !EXIT_CODE!",
        "verify_fixed_layout_runtime.py --repo-root \"%CD%\" --quick --quiet",
        "Run verify_fixed_layout_runtime.cmd for a detailed diagnostic report.",
        "pause",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in text]
    if missing:
        raise RuntimeError(f"fixed layout launcher redirect fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_fixed_layout_installer_scripts_are_present() -> dict[str, Any]:
    install_wrapper = (PROJECT_ROOT / "install_fixed_layout_suite.cmd").read_text(encoding="utf-8")
    gui_wrapper = (PROJECT_ROOT / "install_fixed_layout_suite_gui.cmd").read_text(encoding="utf-8")
    uninstall_wrapper = (PROJECT_ROOT / "uninstall_fixed_layout_suite.cmd").read_text(encoding="utf-8")
    verify_wrapper = (PROJECT_ROOT / "verify_fixed_layout_runtime.cmd").read_text(encoding="utf-8")
    repair_wrapper = (PROJECT_ROOT / "repair_fixed_layout_runtime.cmd").read_text(encoding="utf-8")
    install_ps = (PROJECT_ROOT / "platform_spike" / "scripts" / "install_fixed_layout_suite.ps1").read_text(
        encoding="utf-8"
    )
    repair_ps = (PROJECT_ROOT / "platform_spike" / "scripts" / "repair_fixed_layout_runtime.ps1").read_text(
        encoding="utf-8"
    )
    uninstall_ps = (PROJECT_ROOT / "platform_spike" / "scripts" / "uninstall_fixed_layout_suite.ps1").read_text(
        encoding="utf-8"
    )
    verify_py = (PROJECT_ROOT / "platform_spike" / "scripts" / "verify_fixed_layout_runtime.py").read_text(
        encoding="utf-8"
    )
    verify_module = (
        PROJECT_ROOT / "video_platform_release" / "fixed_layout" / "runtime_verifier.py"
    ).read_text(encoding="utf-8")
    required_fragments = [
        ('install_wrapper', install_wrapper, "install_fixed_layout_suite.ps1"),
        ('install_wrapper', install_wrapper, 'set "SOURCE_ROOT=%~dp0."'),
        ('install_wrapper', install_wrapper, '-SourceRoot "%SOURCE_ROOT%"'),
        ('gui_wrapper', gui_wrapper, "-Gui"),
        ('gui_wrapper', gui_wrapper, 'set "SOURCE_ROOT=%~dp0."'),
        ('gui_wrapper', gui_wrapper, '-SourceRoot "%SOURCE_ROOT%"'),
        ('uninstall_wrapper', uninstall_wrapper, "uninstall_fixed_layout_suite.ps1"),
        ('uninstall_wrapper', uninstall_wrapper, 'set "INSTALL_ROOT=%~dp0."'),
        ('uninstall_wrapper', uninstall_wrapper, '-InstallRoot "%INSTALL_ROOT%"'),
        ('verify_wrapper', verify_wrapper, "platform_spike\\scripts\\verify_fixed_layout_runtime.py"),
        ('verify_wrapper', verify_wrapper, "fixed_layout_runtime_verify_latest.json"),
        ('repair_wrapper', repair_wrapper, "platform_spike\\scripts\\repair_fixed_layout_runtime.ps1"),
        ('repair_wrapper', repair_wrapper, "fixed_layout_runtime_verify_latest.json"),
        ('install_ps', install_ps, "runtime\\python\\python.exe"),
        ('install_ps', install_ps, "runtime\\native_runtime\\VideoPlatform.NativeProbe.exe"),
        ('install_ps', install_ps, "fixed_layout_programs\\fixed_layout_manifest.json"),
        ('install_ps', install_ps, "verify_fixed_layout_runtime.cmd"),
        ('install_ps', install_ps, "repair_fixed_layout_runtime.cmd"),
        ('install_ps', install_ps, "Verify Fixed Layout Installation.lnk"),
        ('install_ps', install_ps, "Repair Fixed Layout Installation.lnk"),
        ('install_ps', install_ps, "Fixed Layout Install and Use Guide.lnk"),
        ('install_ps', install_ps, "FIXED_LAYOUT_INSTALL_AND_USE.md"),
        ('install_ps', install_ps, "fixed_layout_install_metadata.json"),
        ('install_ps', install_ps, "Invoke-PortableRuntimeSmokeChecks"),
        ('install_ps', install_ps, "Write-InstallMetadata"),
        ('install_ps', install_ps, "repair_fixed_layout_runtime.ps1"),
        ('install_ps', install_ps, "Video Platform Fixed Layouts"),
        ('install_ps', install_ps, "UninstallString"),
        ('repair_ps', repair_ps, "fixed_layout_install_metadata.json"),
        ('repair_ps', repair_ps, "Resolve-RecordedSourceRoot"),
        ('repair_ps', repair_ps, "Repair-FromSource"),
        ('repair_ps', repair_ps, "Invoke-VerifyRuntime"),
        ('repair_ps', repair_ps, 'Portable app.py help invocation failed.'),
        ('repair_ps', repair_ps, "robocopy failed with exit code"),
        ('repair_ps', repair_ps, "Missing required runtime files:"),
        ('uninstall_ps', uninstall_ps, "VideoPlatformReleaseFixedLayouts_Backups"),
        ('uninstall_ps', uninstall_ps, "video_platform_release_fixed_layout_cleanup_"),
        ('uninstall_ps', uninstall_ps, "Remove-Item -LiteralPath `$target -Recurse -Force"),
        ('uninstall_ps', uninstall_ps, "-WorkingDirectory $env:TEMP"),
        ('uninstall_ps', uninstall_ps, "Schedule-InstallRootRemoval"),
        ('verify_py', verify_py, "video_platform_release.fixed_layout.runtime_verifier"),
        ('verify_py', verify_py, "raise SystemExit(main())"),
        ('verify_module', verify_module, "Fixed-layout runtime verification"),
        ('verify_module', verify_module, "visual_shell_detector"),
        ('verify_module', verify_module, "status_overlay"),
        ('verify_module', verify_module, "tkinter"),
        ('verify_module', verify_module, "completed.returncode not in (0, 2)"),
        ('verify_module', verify_module, "--quiet"),
        ('verify_module', verify_module, "fixed_layout_runtime_verify_latest.json"),
        ('verify_module', verify_module, "Start the JSON-line native automation sidecar server."),
    ]
    missing = [f"{source}:{fragment}" for source, text, fragment in required_fragments if fragment not in text]
    if missing:
        raise RuntimeError(f"fixed layout installer scaffold missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_fixed_layout_install_and_use_doc_is_present() -> dict[str, Any]:
    text = (PROJECT_ROOT / "FIXED_LAYOUT_INSTALL_AND_USE.md").read_text(encoding="utf-8")
    required_fragments = [
        "video_platform_release_fixed_layout_suite.zip",
        "verify_fixed_layout_runtime.cmd",
        "repair_fixed_layout_runtime.cmd",
        "runtime\\python\\python.exe",
        "runtime\\native_runtime\\VideoPlatform.NativeProbe.exe",
        "F2",
        "F8",
        "F9",
        "F10",
        "F11",
        "还需要标定吗",
        "大多数同类环境下，固定布局安装后可以直接用，不需要先标定。",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in text]
    if missing:
        raise RuntimeError(f"fixed layout install/use doc fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_fixed_layout_instance_lock_auto_clears_stale_pid() -> dict[str, Any]:
    text = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _lock_process_matches_payload(pid: int, payload: dict[str, object]) -> bool:",
        "process = psutil.Process(pid)",
        "cmdline = [str(part).strip() for part in process.cmdline() if str(part).strip()]",
        "normalized_payload = [Path(str(part)).name.lower() for part in payload_argv if str(part).strip()]",
        "if token not in normalized_cmdline:",
        "def _release_stale_lock_if_present() -> None:",
        'payload = json.loads(lock_path.read_text(encoding="utf-8"))',
        "pid = payload.get(\"pid\")",
        "pid_active = psutil.pid_exists(pid)",
        "if pid_active and _lock_process_matches_payload(pid, payload):",
        "lock_path.unlink()",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in text]
    if missing:
        raise RuntimeError(f"fixed layout stale-lock auto cleanup scaffold missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_windows_env_check_tracks_menu_source_assessment() -> dict[str, Any]:
    text = (PROJECT_ROOT / "platform_spike" / "scripts" / "check_windows_platform_spike_env.ps1").read_text(
        encoding="utf-8"
    )
    required_fragments = [
        "function Get-LastRegexMatch",
        "latestClient0101Tab",
        "latestVideoPermission",
        "videoMonitorRedirectTarget",
        "videoMonitorMenuSourceAssessment",
        "server-vsclient",
        "latestClient0101Component",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in text]
    if missing:
        raise RuntimeError(f"windows env menu-source fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_windows_menu_source_inspector_scaffold_is_present() -> dict[str, Any]:
    ps1 = (PROJECT_ROOT / "platform_spike" / "scripts" / "inspect_client_menu_sources.ps1").read_text(
        encoding="utf-8"
    )
    cmd = (PROJECT_ROOT / "platform_spike" / "scripts" / "inspect_client_menu_sources.cmd").read_text(
        encoding="utf-8"
    )
    required_ps1 = [
        "=== CLIENT_MENU_SOURCE_RESULT ===",
        "check_windows_platform_spike_env.ps1",
        "videoMonitorMenuSourceAssessment",
        "latestClient0101Component",
    ]
    missing_ps1 = [fragment for fragment in required_ps1 if fragment not in ps1]
    if missing_ps1:
        raise RuntimeError(f"menu source inspector PowerShell fragments missing: {missing_ps1}")
    required_cmd = [
        "inspect_client_menu_sources.ps1",
    ]
    missing_cmd = [fragment for fragment in required_cmd if fragment not in cmd]
    if missing_cmd:
        raise RuntimeError(f"menu source inspector CMD fragments missing: {missing_cmd}")
    return {"powershell_fragments": len(required_ps1), "cmd_fragments": len(required_cmd)}


def test_regular_layout_counts() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    preview = Rect(0, 0, 1200, 900)
    mapper = GridMapper(config.grid)
    counts = {}
    for layout in (4, 6, 9, 12):
        counts[str(layout)] = len(mapper.build_cells(preview, layout=layout))
        if counts[str(layout)] != layout:
            raise RuntimeError(f"layout={layout} produced {counts[str(layout)]} cells")
    return counts


def test_runtime_layout_override_bypasses_configured_template() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    preview = Rect(0, 0, 1200, 900)
    templated_grid = replace(config.grid, layout=12, layout_template="twelve_4x3")
    mapper = GridMapper(templated_grid)
    templated_cells = mapper.build_cells(preview, layout=12)
    runtime_override_cells = mapper.build_cells(preview, layout=6)
    if len(templated_cells) != 12:
        raise RuntimeError(f"templated 12-grid produced {len(templated_cells)} cells instead of 12")
    if len(runtime_override_cells) != 6:
        raise RuntimeError(
            f"runtime layout override still leaked template cells: produced {len(runtime_override_cells)} instead of 6"
        )
    return {
        "templated_layout_count": len(templated_cells),
        "runtime_override_count": len(runtime_override_cells),
    }


def test_custom_sequence() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    custom_grid = replace(
        config.grid,
        order="custom",
        custom_sequence=(0, 3, 6, 9, 1, 4, 7, 10, 2, 5, 8, 11),
    )
    mapper = GridMapper(custom_grid)
    cells = mapper.build_cells(Rect(0, 0, 1200, 900), layout=12)
    order = [cell.index for cell in cells[:6]]
    expected = [0, 3, 6, 9, 1, 4]
    if order != expected:
        raise RuntimeError(f"custom order mismatch: got={order} expected={expected}")
    return {"first_six": order}



def test_column_major_alias_behavior() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    grid = replace(config.grid, order="column_major")
    mapper = GridMapper(grid)
    cells = mapper.build_cells(Rect(0, 0, 1200, 900), layout=12)
    order = [cell.index for cell in cells[:6]]
    expected = [0, 3, 6, 9, 1, 4]
    if order != expected:
        raise RuntimeError(f"column_major mismatch: got={order} expected={expected}")
    return {"first_six": order}



def test_favorites_name_mapping() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.example.yaml")
    grid = replace(
        config.grid,
        order="favorites_name",
        cell_labels={
            0: "大厅柱子口",
            1: "法雨寺停车场",
            2: "千步沙入口",
            3: "码头入口",
        },
    )
    mapper = GridMapper(grid)
    cells = mapper.build_cells(
        Rect(0, 0, 1200, 900),
        layout=4,
        runtime_label_order=["码头入口", "大厅柱子口", "法雨寺停车场"],
    )
    order = [cell.index for cell in cells[:4]]
    expected_prefix = [3, 0, 1]
    if order[:3] != expected_prefix:
        raise RuntimeError(f"favorites order mismatch: got={order[:3]} expected={expected_prefix}")
    return {"order": order}



def test_favorites_visible_name_filtering() -> dict[str, Any]:
    filtered = FavoritesReader._normalize_collected_names(
        [
            (120, 120, "系统授权部分过期，请联系管理员", "Text"),
            (162, 180, "收藏夹", "Text"),
            (300, 276, "我的收藏", "TreeItem"),
            (364, 308, "春节值班目录", "TreeItem"),
            (428, 340, "每天值班看的12个点位", "TreeItem"),
            (492, 372, "大厅柱子口", "TreeItem"),
            (556, 372, "法雨寺停车场", "TreeItem"),
            (620, 372, "千步沙入口", "TreeItem"),
        ],
        max_entries=16,
    )
    expected = ["大厅柱子口", "法雨寺停车场", "千步沙入口"]
    if filtered != expected:
        raise RuntimeError(f"favorites visible-name filtering mismatch: got={filtered} expected={expected}")
    return {"names": filtered}


def test_layout_template_switch() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.example.yaml")
    grid = replace(config.grid, layout=12, layout_template="twelve_3x4")
    mapper = GridMapper(grid)
    cells = mapper.build_cells(Rect(0, 0, 1200, 900), layout=12)
    if len(cells) != 12:
        raise RuntimeError(f"template produced {len(cells)} cells")
    max_col = max(cell.col for cell in cells)
    max_row = max(cell.row for cell in cells)
    if max_col != 3 or max_row != 2:
        raise RuntimeError(f"template geometry mismatch: max_row={max_row} max_col={max_col}")
    return {"count": len(cells), "max_row": max_row, "max_col": max_col}


def test_zoom_point_uses_middle_upper_bias() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    mapper = GridMapper(config.grid)
    cells = mapper.build_cells(Rect(0, 0, 1200, 900), layout=9)
    invalid = [
        cell.index
        for cell in cells
        if cell.zoom_point[0] != cell.select_point[0] or cell.zoom_point[1] >= cell.select_point[1]
    ]
    if invalid:
        raise RuntimeError(f"zoom points no longer stay in the middle-upper band for cells: {invalid}")
    sample = cells[3]
    return {
        "cell_index": sample.index,
        "row": sample.row,
        "col": sample.col,
        "select_point": sample.select_point,
        "zoom_point": sample.zoom_point,
        "y_offset": sample.select_point[1] - sample.zoom_point[1],
    }


def test_layout12_fullscreen_lower_rows_shift_down() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "fixed_layout_programs" / "config.layout12.fullscreen.yaml")
    mapper = GridMapper(config.grid)
    cells = mapper.build_cells(Rect(7, 7, 1695, 963), layout=12)
    row_ratios: dict[int, list[tuple[float, float]]] = {}
    for cell in cells:
        cell_height = cell.cell_rect.height
        select_ratio = (cell.select_point[1] - cell.cell_rect.top) / max(1, cell_height)
        zoom_ratio = (cell.zoom_point[1] - cell.cell_rect.top) / max(1, cell_height)
        row_ratios.setdefault(cell.row + 1, []).append((round(select_ratio, 3), round(zoom_ratio, 3)))

    upper_rows = row_ratios[1] + row_ratios[2]
    lower_rows = row_ratios[3] + row_ratios[4]
    if any(not (0.49 <= select <= 0.51 and 0.49 <= zoom <= 0.51) for select, zoom in upper_rows):
        raise RuntimeError(f"layout12 fullscreen upper rows must stay centered: rows={row_ratios}")
    if any(select < 0.54 or zoom < 0.54 for select, zoom in lower_rows):
        raise RuntimeError(f"layout12 fullscreen lower rows must shift downward: rows={row_ratios}")
    return {"row_ratios": row_ratios}


def test_layout_switch_target_mapping() -> dict[str, Any]:
    resolved = {
        str(layout): {
            "section": resolve_layout_switch_target(layout).section,
            "label": resolve_layout_switch_target(layout).label,
        }
        for layout in (4, 6, 9, 12, 13)
    }
    expected = {
        "4": {"section": "平均", "label": "4"},
        "6": {"section": "水平", "label": "6"},
        "9": {"section": "平均", "label": "9"},
        "12": {"section": "其他", "label": "12"},
        "13": {"section": "其他", "label": "13"},
    }
    if resolved != expected:
        raise RuntimeError(f"layout switch target mapping mismatch: got={resolved} expected={expected}")
    return resolved


def test_layout_switch_option_grouping() -> dict[str, Any]:
    header_rects = [
        ("平均", Rect(1550, 286, 2510, 322)),
        ("高亮分割", Rect(1550, 456, 2510, 492)),
        ("水平", Rect(1550, 626, 2510, 662)),
        ("垂直", Rect(1550, 796, 2510, 832)),
        ("其他", Rect(1550, 966, 2510, 1002)),
    ]
    checkbox_rects = [
        ("4", Rect(1690, 342, 1774, 426)),
        ("9", Rect(1830, 342, 1914, 426)),
        ("6", Rect(1970, 682, 2054, 766)),
        ("12", Rect(2390, 1022, 2474, 1106)),
        ("13", Rect(1550, 1126, 1634, 1210)),
    ]
    grouped = build_layout_option_index(header_rects, checkbox_rects)
    expected_keys = {
        ("平均", "4"),
        ("平均", "9"),
        ("水平", "6"),
        ("其他", "12"),
        ("其他", "13"),
    }
    if set(grouped.keys()) != expected_keys:
        raise RuntimeError(f"layout switch option grouping mismatch: got={set(grouped.keys())} expected={expected_keys}")
    return {"group_count": len(grouped), "keys": sorted([f"{section}/{label}" for section, label in grouped.keys()])}


def test_prepare_target_captures_grid_probe_before_guard_check() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    start = scheduler_text.index("def _prepare_iteration")
    end = scheduler_text.index("def _select_target")
    block = scheduler_text[start:end]
    if "self._ensure_prepare_target_grid()" not in block:
        raise RuntimeError("PREPARE_TARGET no longer repairs non-grid state before starting the action path")
    probe_marker = "self._last_grid_probe = self._detector.capture_probe"
    guard_marker = 'if not self._guard_stage_view("PREPARE_TARGET", VisualViewState.GRID, refresh_context=False):'
    probe_pos = block.find(probe_marker)
    guard_pos = block.find(guard_marker)
    if probe_pos == -1 or guard_pos == -1:
        raise RuntimeError("PREPARE_TARGET markers missing from scheduler.py")
    if probe_pos > guard_pos:
        raise RuntimeError("PREPARE_TARGET no longer captures grid probe before guard check")
    return {"probe_pos": probe_pos, "guard_pos": guard_pos}


def test_auto_mode_prefers_windowed_ui_markers() -> dict[str, Any]:
    window_manager_text = (PROJECT_ROOT / "window_manager.py").read_text(encoding="utf-8")
    start = window_manager_text.index("def detect_mode")
    end = window_manager_text.index("def _select_candidates")
    block = window_manager_text[start:end]
    attached_surface_call = "attached_surface = self.find_visual_render_surface(window_info)"
    ui_marker_call = "windowed_hits = self._detect_windowed_ui_markers_cached(window_info)"
    fullscreen_toggle_call = "fullscreen_toggle_checked = self._detect_fullscreen_toggle_checked(window_info.hwnd)"
    geometry_marker = "coverage_w = window_info.client_rect.width / max(1, window_info.monitor_rect.width)"
    geometry_fast_path = "if not fullscreen_geometry_candidate:"
    attached_surface_pos = block.find(attached_surface_call)
    ui_marker_pos = block.find(ui_marker_call)
    fullscreen_toggle_pos = block.find(fullscreen_toggle_call)
    geometry_pos = block.find(geometry_marker)
    fast_path_pos = block.find(geometry_fast_path)
    if (
        attached_surface_pos == -1
        or ui_marker_pos == -1
        or fullscreen_toggle_pos == -1
        or geometry_pos == -1
        or fast_path_pos == -1
    ):
        raise RuntimeError("auto mode detection markers missing from window_manager.py")
    if attached_surface_pos < fast_path_pos:
        raise RuntimeError("auto mode still scans attached render surface before the geometry fast-path gate")
    if attached_surface_pos < ui_marker_pos:
        raise RuntimeError("auto mode no longer checks visible windowed UI markers before attached render surface")
    if ui_marker_pos > fullscreen_toggle_pos:
        raise RuntimeError("auto mode no longer gives visible windowed UI markers priority over fullscreen toggle")
    required_markers = ['"收藏夹"', '"打开文件夹"', '"搜索"', '"全部收藏"']
    missing = [marker for marker in required_markers if marker not in window_manager_text]
    if missing:
        raise RuntimeError(f"windowed UI markers missing: {missing}")
    required_fragments = [
        "Auto mode resolved to windowed via geometry fast-path",
        "ctrl = root.child_window(title=marker)",
        "if not ctrl.exists(timeout=0.1):",
        "Auto mode resolved to fullscreen via attached render surface",
        "def _find_attached_render_surface",
        "def _looks_like_attached_render_surface",
        'for title in ("全屏", "退出全屏"):',
        "if fullscreen_toggle_checked:",
        "Auto mode resolved to fullscreen via fullscreen toggle",
    ]
    missing_fragments = [fragment for fragment in required_fragments if fragment not in window_manager_text]
    if missing_fragments:
        raise RuntimeError(f"window_manager.py missing fullscreen/windowed visibility fragments: {missing_fragments}")
    if '"全屏"' not in window_manager_text:
        raise RuntimeError('fullscreen toggle probe marker "全屏" missing from window_manager.py')
    return {
        "attached_surface_pos": attached_surface_pos,
        "ui_marker_pos": ui_marker_pos,
        "fullscreen_toggle_pos": fullscreen_toggle_pos,
        "geometry_pos": geometry_pos,
        "fast_path_pos": fast_path_pos,
    }


def test_window_manager_related_window_prefilter() -> dict[str, Any]:
    window_manager_text = (PROJECT_ROOT / "window_manager.py").read_text(encoding="utf-8")
    required_fragments = [
        "target_pid = target_window.process_id",
        "owner_hwnd = int(win32gui.GetWindow(hwnd, win32con.GW_OWNER) or 0)",
        "_, process_id = win32process.GetWindowThreadProcessId(hwnd)",
        "detached_prefilter = self._looks_like_detached_render_surface_prefilter(",
        "if process_id != target_pid and owner_hwnd != target_hwnd and not detached_prefilter:",
        "先做廉价预筛，避免为桌面上所有可见窗口都取进程名和完整快照",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in window_manager_text]
    if missing:
        raise RuntimeError(f"window_manager related-window prefilter fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_action_path_semantics() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    controller_text = (PROJECT_ROOT / "controller.py").read_text(encoding="utf-8")
    config = load_config(PROJECT_ROOT / "config.yaml")

    required_scheduler_fragments = [
        "SchedulerState.SELECT_CONFIRM",
        "SchedulerState.ZOOM_IN",
        "SchedulerState.ZOOM_CONFIRM",
        "SchedulerState.ZOOM_DWELL",
        "SchedulerState.ZOOM_OUT",
        "SchedulerState.GRID_CONFIRM",
        "SchedulerState.GRID_DWELL",
        "self._transition_state(SchedulerState.ZOOM_OUT, from_state=SchedulerState.ZOOM_DWELL)",
        "self._transition_state(SchedulerState.NEXT, from_state=SchedulerState.GRID_DWELL)",
    ]
    missing_scheduler = [fragment for fragment in required_scheduler_fragments if fragment not in scheduler_text]
    if missing_scheduler:
        raise RuntimeError(f"runtime action path fragments missing: {missing_scheduler}")

    if 'action_type="zoom_out"' not in controller_text:
        raise RuntimeError('controller restore_zoom is missing action_type="zoom_out"')
    if 'self.double_click(point, hwnd=hwnd, client_origin=client_origin, action_type="zoom_out")' not in controller_text:
        raise RuntimeError('controller restore_zoom no longer uses double_click for zoom_out')
    if "allow_paused_action=True" not in scheduler_text:
        raise RuntimeError("scheduler manual-next path no longer allows paused-state selection clicks")
    guard_fragments = [
        "guard_expected_view_before=VisualViewState.GRID",
        "guard_expected_view_before=VisualViewState.ZOOMED",
        'stage=f"before_{action_name}"',
        "expected_view=guard_expected_view_before",
        "inspect_view=guard_expected_view_before is not None",
        "expected_view=guard_expected_view_after",
        "inspect_view=guard_expected_view_after is not None",
    ]
    missing_guard = [fragment for fragment in guard_fragments if fragment not in scheduler_text]
    if missing_guard:
        raise RuntimeError(f"pointer-action runtime guard fragments missing: {missing_guard}")

    if config.timing.dwell_seconds <= 0:
        raise RuntimeError("dwell_seconds must be > 0")
    if config.timing.post_restore_dwell_seconds < 0:
        raise RuntimeError("post_restore_dwell_seconds must be >= 0")

    return {
        "dwell_seconds": config.timing.dwell_seconds,
        "post_restore_dwell_seconds": config.timing.post_restore_dwell_seconds,
    }


def test_zoom_confirm_failure_restarts_current_path() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "self._zoom_partial_signal_seen = False",
        'self._plan_recovery(SchedulerState.PREPARE_TARGET, "zoom_confirm_failed")',
        "forcing grid recovery before restarting current path",
        "放大确认不稳定",
        "low_texture_zoom_confirmed=%s preview_failure_zoom_confirmed=%s continuity_dominant_zoom_confirmed=%s locked_fullscreen_transition_zoom_confirmed=%s expansion_dominant_zoom_confirmed=%s runtime_transition_zoom_confirmed=%s",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"zoom-confirm recovery fragments missing: {missing}")
    forbidden = ['self._plan_recovery(SchedulerState.NEXT, "zoom_confirm_failed")']
    unexpected = [fragment for fragment in forbidden if fragment in scheduler_text]
    if unexpected:
        raise RuntimeError(f"zoom-confirm failure still skips current path: {unexpected}")
    return {"required_fragments": len(required_fragments)}


def test_zoom_confirm_fast_path_accepts_runtime_zoom_signal() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _should_accept_zoom_confirm_fast_path",
        'if not self._detector.matches_expected_view(VisualViewState.ZOOMED, metrics):',
        'runtime_view_zoomed = metrics.get("runtime_view_zoomed") == 1.0',
        'main_view_expansion_confirmed = metrics.get("main_view_expansion_confirmed") == 1.0',
        'layout_change_confirmed = metrics.get("layout_change_confirmed") == 1.0',
        'return runtime_view_zoomed and (main_view_expansion_confirmed or layout_change_confirmed)',
        "ZOOM_CONFIRM fast-path accepted",
        "if poll_index > 0 and not self._wait_interruptible(0.14, allow_pause=True):",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"zoom-confirm fast-path fragments missing: {missing}")
    return {"required_fragments": len(required_fragments)}


def test_startup_runtime_sync_suppresses_input_guard_and_ignores_overlay_foreground() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    input_guard_text = (PROJECT_ROOT / "input_guard.py").read_text(encoding="utf-8")
    required_scheduler = [
        "self._input_guard.start()",
        "启动首轮进入主循环前就要先压住 input_guard",
        "self._suppress_input_guard(duration_ms=12000)",
        "self._suppress_input_guard(duration_ms=max(8000, self._config.input_guard.resume_settle_ms + 2000))",
        "def _suppress_input_guard",
        'suppress_input_guard = getattr(self._input_guard, "suppress_manual_detection", None)',
        'if title == "Video Polling Status" and process_name in {"pythonw.exe", "python.exe"}:',
        'if process_name in {"windowsterminal.exe", "wt.exe"} and lowered_title.startswith("ubuntu"):',
        "FOREGROUND_RECOVER continuing despite ignored auxiliary foreground",
    ]
    missing_scheduler = [fragment for fragment in required_scheduler if fragment not in scheduler_text]
    if missing_scheduler:
        raise RuntimeError(f"startup runtime-sync/input-guard fragments missing: {missing_scheduler}")
    required_input_guard = [
        "def suppress_manual_detection",
        "self.suppress_manual_detection()",
    ]
    missing_input_guard = [fragment for fragment in required_input_guard if fragment not in input_guard_text]
    if missing_input_guard:
        raise RuntimeError(f"input_guard suppression fragments missing: {missing_input_guard}")
    return {
        "scheduler_fragments": len(required_scheduler),
        "input_guard_fragments": len(required_input_guard),
    }


def test_startup_runtime_layout_cache_bootstrap_is_wired() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    layout_switcher_text = (PROJECT_ROOT / "layout_switcher.py").read_text(encoding="utf-8")
    required_scheduler = [
        'self._runtime_layout_cache_path = resolve_output_path(self._config.path, "tmp/runtime_profile_cache.json")',
        "self._runtime_layout_cache_ttl_seconds = 10.0 * 60.0",
        "self._startup_cached_layout_verify_pending = False",
        "self._bootstrap_windowed_runtime_layout_from_cache()",
        "def _save_windowed_runtime_layout_cache(self, *, layout: int, source: str) -> None:",
        "def _load_windowed_runtime_layout_cache(self) -> dict[str, object] | None:",
        "def _bootstrap_windowed_runtime_layout_from_cache(self) -> bool:",
        "def _schedule_startup_cached_layout_reverify(self, *, reason: str) -> None:",
        "def _verify_startup_cached_layout_before_actions(self) -> None:",
        "self._verify_startup_cached_layout_before_actions()",
        'self._schedule_startup_cached_layout_reverify(reason="post_first_cycle")',
        '"RUNTIME_LAYOUT confirm reason=startup_cache layout=%s via=provisional_cache',
        '"RUNTIME_LAYOUT deferred verify scheduled reason=%s layout=%s next_cell=%s"',
        '"RUNTIME_LAYOUT startup quick verify verified=%s layout=%s cell=%s"',
        '"RUNTIME_LAYOUT cache rejected reason=visual_candidate_conflict layout=%s candidate_layout=%s candidate_score=%s"',
        'self._save_windowed_runtime_layout_cache(layout=self._runtime_layout, source=reason)',
        'self._save_windowed_runtime_layout_cache(layout=self._runtime_layout, source=f"{reason}:{resolved_reason}")',
    ]
    missing_scheduler = [fragment for fragment in required_scheduler if fragment not in scheduler_text]
    if missing_scheduler:
        raise RuntimeError(f"startup runtime-layout cache fragments missing: {missing_scheduler}")
    required_layout_switcher = [
        "def detect_active_grid_layout_candidate(self, *, target_window=None) -> dict[str, object] | None:",
        "candidate = self._detect_active_grid_scene(preview_rect, preview_image=preview_image)",
        '"layout_switch visual grid candidate layout=%s score=%s cell=%s view=%s"',
    ]
    missing_layout_switcher = [fragment for fragment in required_layout_switcher if fragment not in layout_switcher_text]
    if missing_layout_switcher:
        raise RuntimeError(f"layout_switcher visual-candidate fragments missing: {missing_layout_switcher}")
    return {
        "scheduler_fragments": len(required_scheduler),
        "layout_switcher_fragments": len(required_layout_switcher),
    }


def test_paused_manual_next_refreshes_grid_probe_after_recover() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    start = scheduler_text.index("def _perform_visible_next_selection")
    end = scheduler_text.index("def _cell_hint")
    block = scheduler_text[start:end]
    required_fragments = [
        "grid_like = actual_view == VisualViewState.GRID",
        "if not grid_like and actual_view != VisualViewState.ZOOMED:",
        'grid_like = self._prepare_target_grid_like(actual_view, view_metrics, reason="manual_next_queue_grid_ready")',
        '"NEXT_QUEUE recover_to_grid_for_visible_select',
        "for attempt in range(2):",
        'action_name="manual_next_queue_recover"',
        '"NEXT_QUEUE post-recover still not grid',
        'reason="manual_next_queue_post_recover_grid_ready"',
        "self._last_grid_probe = self._detector.capture_probe(self._preview_rect, size=(64, 64))",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in block]
    if missing:
        raise RuntimeError(f"paused manual-next grid recovery fragments missing: {missing}")
    recover_pos = block.find('action_name="manual_next_queue_recover"')
    probe_pos = block.find("self._last_grid_probe = self._detector.capture_probe(self._preview_rect, size=(64, 64))")
    click_pos = block.find('action_name="select_next_queue"')
    if recover_pos == -1 or probe_pos == -1 or click_pos == -1:
        raise RuntimeError("paused manual-next markers missing from scheduler.py")
    if not (recover_pos < probe_pos < click_pos):
        raise RuntimeError("paused manual-next no longer refreshes grid probe after recover and before click")
    return {"recover_pos": recover_pos, "probe_pos": probe_pos, "click_pos": click_pos}


def test_paused_manual_next_does_not_treat_zoomed_view_as_visible_grid() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    start = scheduler_text.index("def _perform_visible_next_selection")
    end = scheduler_text.index("def _cell_hint")
    block = scheduler_text[start:end]
    required_fragments = [
        "grid_like = actual_view == VisualViewState.GRID",
        "if not grid_like and actual_view != VisualViewState.ZOOMED:",
        "若当前仍是放大态",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in block]
    if missing:
        raise RuntimeError(f"paused manual-next still allows zoomed views to masquerade as grid: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_fast_locked_resume_does_not_treat_zoomed_view_as_grid() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    start = scheduler_text.index("def _resume_after_pause_locked_runtime_profile")
    end = scheduler_text.index("def _resume_after_pause(")
    block = scheduler_text[start:end]
    required_fragments = [
        'paused_stage = self._paused_stage or ""',
        'paused_during_zoom_transition = (',
        "order_changed_from_zoom_surface = self._grid_order_changed_during_pause and paused_with_zoom_surface",
        "prefer_explicit_zoom_out_recovery = (",
        "or paused_during_zoom_transition",
        "recovered_from_zoom_surface = False",
        'action_name="resume_zoom_surface_recover"',
        "unsafe_grid_frame = (",
        "(paused_during_zoom_transition or order_changed_from_zoom_surface)",
        "grid_like = actual_view == VisualViewState.GRID and not unsafe_grid_frame",
        "if not grid_like and actual_view != VisualViewState.ZOOMED and not unsafe_grid_frame:",
        'grid_like = self._prepare_target_grid_like(actual_view, metrics, reason="resume_grid_ready")',
        'grid_like = self._prepare_target_grid_like(actual_view, metrics, reason="resume_post_recover_grid_ready")',
        'settle_after_recover = 0.95 if actual_view == VisualViewState.ZOOMED or (self._paused_stage or "").startswith("ZOOM_") else 0.35',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in block]
    if missing:
        raise RuntimeError(f"fast locked resume still allows zoomed views to masquerade as grid: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_fast_locked_resume_does_not_trust_zoom_transition_grid_frame() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    start = scheduler_text.index("def _resume_after_pause_locked_runtime_profile")
    end = scheduler_text.index("def _resume_after_pause(")
    block = scheduler_text[start:end]
    required_fragments = [
        'paused_stage in {"ZOOM_IN", "ZOOM_OUT", "ZOOM_CONFIRM"}',
        'or paused_stage.startswith("before_zoom_")',
        'or paused_stage.startswith("after_zoom_")',
        "过渡帧",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in block]
    if missing:
        raise RuntimeError(f"fast locked resume still trusts zoom-transition grid frames: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_paused_grid_order_change_can_fall_back_to_prepare_target() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "self._grid_order_changed_during_pause = False",
        "self._grid_order_changed_during_pause = True",
        "paused_with_zoom_surface = (",
        "order_changed_from_zoom_surface = self._grid_order_changed_during_pause and paused_with_zoom_surface",
        "self._pause_ack_view == VisualViewState.ZOOMED",
        'or paused_stage == "ZOOM_DWELL"',
        "RESUME_ZOOM_SURFACE forcing explicit zoom-out recovery",
        'action_name="resume_zoom_surface_recover"',
        "if order_changed_from_zoom_surface or (recovered_from_zoom_surface and actual_view != VisualViewState.ZOOMED):",
        '"RESUME_FALLBACK continuing via PREPARE_TARGET after zoom-surface recovery cell=%s paused_stage=%s actual_view=%s metrics=%s"',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"paused grid-order change no longer falls back to prepare-target recovery: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_paused_grid_order_change_prefers_explicit_zoom_out_recovery() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    start = scheduler_text.index("def _resume_after_pause_locked_runtime_profile")
    end = scheduler_text.index("def _resume_after_pause(")
    block = scheduler_text[start:end]
    required_fragments = [
        "if prefer_explicit_zoom_out_recovery:",
        "or paused_during_zoom_transition",
        'action_name="resume_zoom_surface_recover"',
        "recovered_from_zoom_surface = True",
        'if not self._wait_interruptible(1.15, allow_pause=False):',
        "actual_view, metrics = self._classify_current_view(refresh_context=True)",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in block]
    if missing:
        raise RuntimeError(f"paused grid-order change no longer prefers explicit zoom-out recovery: {missing}")
    action_pos = block.find('action_name="resume_zoom_surface_recover"')
    unsafe_pos = block.find("unsafe_grid_frame = (")
    if action_pos == -1 or unsafe_pos == -1:
        raise RuntimeError("paused grid-order change recovery markers missing from scheduler.py")
    if not action_pos < unsafe_pos:
        raise RuntimeError("explicit zoom-out recovery must happen before unsafe grid-frame gating")
    return {"action_pos": action_pos, "unsafe_pos": unsafe_pos}


def test_zoom_dwell_resume_prefers_explicit_zoom_out_recovery() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        'paused_stage == "ZOOM_DWELL"',
        "prefer_explicit_zoom_out_recovery = (",
        'action_name="resume_zoom_surface_recover"',
        "recovered_from_zoom_surface and actual_view != VisualViewState.ZOOMED",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"zoom-dwell resume no longer prefers explicit zoom-out recovery: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_zoom_dwell_resume_skips_explicit_recovery_after_manual_return_to_grid() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "operator_returned_to_grid = (",
        'paused_stage == "ZOOM_DWELL"',
        'self._last_pause_reason == "user_pause"',
        "actual_view == VisualViewState.GRID",
        "and not self._grid_order_changed_during_pause",
        "detected operator-returned grid; skipping explicit zoom-out recovery",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"zoom-dwell resume no longer skips explicit recovery after manual return to grid: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_start_pause_toggle_has_settle_lock() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "self._start_pause_toggle_lock_until = 0.0",
        "def _toggle_user_pause",
        "if now < self._start_pause_toggle_lock_until:",
        "self._start_pause_toggle_lock_until = now + 0.35",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"start/pause toggle settle-lock fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_next_hotkey_has_independent_fast_debounce() -> dict[str, Any]:
    common_text = (PROJECT_ROOT / "common.py").read_text(encoding="utf-8")
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_common = [
        "next_cell_debounce_ms: int = 120",
        'next_cell_debounce_ms=int(raw["hotkeys"].get("next_cell_debounce_ms", 120))',
    ]
    missing_common = [fragment for fragment in required_common if fragment not in common_text]
    if missing_common:
        raise RuntimeError(f"common.py missing next-cell debounce fragments: {missing_common}")
    required_scheduler = [
        'if hotkey_name == "next_cell":',
        "debounce_ms = self._config.hotkeys.next_cell_debounce_ms",
    ]
    missing_scheduler = [fragment for fragment in required_scheduler if fragment not in scheduler_text]
    if missing_scheduler:
        raise RuntimeError(f"scheduler.py missing next-cell debounce fragments: {missing_scheduler}")
    return {"common_fragments": len(required_common), "scheduler_fragments": len(required_scheduler)}


def test_single_function_hotkeys_use_keydown_hooks() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "from win_hotkeys import NativeHotkeyManager, parse_hotkey_spec",
        "self._native_hotkeys = NativeHotkeyManager",
        "def _register_native_hotkey",
        "lambda: self._invoke_hotkey(hotkey_name, handler, from_native=True)",
        'self._hotkeys.append(("native", hotkey_id))',
        'elif hotkey_type == "native" and self._native_hotkeys is not None:',
        "self._native_hotkeys.unregister(int(hotkey))",
        "self._native_hotkeys.stop()",
        "keyboard.on_press_key(",
        "keyboard.on_release_key(",
        "keyboard.add_hotkey(",
        "self._hotkey_press_latched: dict[str, bool] = {}",
        "def _register_single_key_hotkey",
        "def _prime_hotkey_press_latch",
        "keyboard.is_pressed(key_name)",
        "def _release_hotkey_press_latch",
        'if hotkey_name in self._hotkey_press_latched:',
        'self._config.hotkeys.start_pause,',
        'self._config.hotkeys.grid_order_cycle,',
        'self._config.hotkeys.next_cell,',
        'self._config.hotkeys.stop,',
        'self._config.hotkeys.emergency_recover,',
        'self._config.hotkeys.clear_cooldown,',
        "suppress=True,",
        'keyboard.unhook(hotkey)',
        'keyboard.remove_hotkey(hotkey)',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"single-function hotkey hook fragments missing: {missing}")
    if scheduler_text.count("suppress=True,") < 4:
        raise RuntimeError("hotkey registration must suppress start/next/stop/recover hooks")
    return {"checked_fragments": len(required_fragments)}


def test_clear_cooldown_hotkey_is_wired() -> dict[str, Any]:
    common_text = (PROJECT_ROOT / "common.py").read_text(encoding="utf-8")
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    app_text = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    required_common = [
        'clear_cooldown: str',
        'CLEAR_COOLDOWN_REQUEST = "CLEAR_COOLDOWN_REQUEST"',
        'clear_cooldown=str(raw["hotkeys"].get("clear_cooldown", "f6"))',
    ]
    required_scheduler = [
        'elif command == HotkeyCommand.CLEAR_COOLDOWN_REQUEST:',
        'self._handle_clear_cooldown_request()',
        'def _handle_clear_cooldown_request',
        'self._config.hotkeys.clear_cooldown',
        '"clear_cooldown",',
        'self._request_clear_cooldown',
        'Hotkey requested CLEAR_COOLDOWN',
        'message="异常冷却已清除"',
        'resume_bypass_index = getattr(self._active_cell, "index", None)',
        'self._resume_clear_cooldown_bypass_index = resume_bypass_index',
        'BYPASS_ISSUE_COOLDOWN cell=%s reason=manual_clear_cooldown_resume',
    ]
    required_app = [
        'clear issue cooldown',
        'config.hotkeys.clear_cooldown,',
    ]
    missing = [fragment for fragment in required_common if fragment not in common_text]
    missing += [fragment for fragment in required_scheduler if fragment not in scheduler_text]
    missing += [fragment for fragment in required_app if fragment not in app_text]
    if missing:
        raise RuntimeError(f"clear cooldown hotkey wiring fragments missing: {missing}")
    return {"checked_fragments": len(required_common) + len(required_scheduler) + len(required_app)}


def test_runtime_grid_order_cycle_hotkey_is_wired() -> dict[str, Any]:
    common_text = (PROJECT_ROOT / "common.py").read_text(encoding="utf-8")
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    app_text = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    required_common = [
        'grid_order_cycle: str = "disabled"',
        'GRID_ORDER_CYCLE_REQUEST = "GRID_ORDER_CYCLE_REQUEST"',
        'grid_order_cycle=str(raw["hotkeys"].get("grid_order_cycle", "disabled"))',
    ]
    missing_common = [fragment for fragment in required_common if fragment not in common_text]
    if missing_common:
        raise RuntimeError(f"common.py missing grid-order hotkey fragments: {missing_common}")
    required_scheduler = [
        "self._runtime_grid_order = self._normalize_runtime_grid_order(self._config.grid.order)",
        "def _handle_grid_order_cycle_request",
        "轮询顺序仅支持暂停态切换",
        "轮询顺序已切换：",
        'self._runtime_grid_order = next_order',
        'self._refresh_window_context(fast=self._window_info is not None)',
        "Hotkey requested GRID_ORDER cycle",
        '"grid_order_cycle",',
        "self._request_grid_order_cycle",
        "HotkeyCommand.GRID_ORDER_CYCLE_REQUEST",
        'self._format_hotkey_hint_entry(self._config.hotkeys.grid_order_cycle, "顺序")',
        'elif hotkey_name in {"mode_cycle", "layout_cycle", "grid_order_cycle"}:',
        "return \"column_major\" if str(order or \"\").strip().lower() == \"column_major\" else \"row_major\"",
    ]
    missing_scheduler = [fragment for fragment in required_scheduler if fragment not in scheduler_text]
    if missing_scheduler:
        raise RuntimeError(f"scheduler.py missing grid-order hotkey fragments: {missing_scheduler}")
    required_app = [
        "config.hotkeys.grid_order_cycle,",
        "order cycle(left-right/top-down)",
    ]
    missing_app = [fragment for fragment in required_app if fragment not in app_text]
    if missing_app:
        raise RuntimeError(f"app.py missing grid-order hotkey fragments: {missing_app}")
    return {
        "common_fragments": len(required_common),
        "scheduler_fragments": len(required_scheduler),
        "app_fragments": len(required_app),
    }


def test_fixed_layout_configs_restrict_operator_grid_orders() -> dict[str, Any]:
    checked = 0
    for layout in (4, 6, 9, 12):
        for mode in ("windowed", "fullscreen"):
            path = PROJECT_ROOT / "fixed_layout_programs" / f"config.layout{layout}.{mode}.yaml"
            cfg = load_config(path)
            if cfg.grid.order != "row_major":
                raise RuntimeError(f"{path.name} grid.order must default to row_major")
            if cfg.grid.custom_sequence:
                raise RuntimeError(f"{path.name} must not retain custom_sequence in fixed preset")
            if cfg.grid.active_sequence_profile:
                raise RuntimeError(f"{path.name} must not retain active_sequence_profile in fixed preset")
            if cfg.grid.sequence_profiles:
                raise RuntimeError(f"{path.name} must not retain sequence_profiles in fixed preset")
            if cfg.favorites.enabled:
                raise RuntimeError(f"{path.name} must disable favorites for fixed preset")
            if str(cfg.hotkeys.grid_order_cycle).strip().lower() != "f8":
                raise RuntimeError(f"{path.name} must keep F8 as the operator order-cycle hotkey")
            checked += 1
    return {"checked_configs": checked}


def test_native_hotkey_manager_uses_register_hotkey_with_message_loop() -> dict[str, Any]:
    hotkey_text = (PROJECT_ROOT / "win_hotkeys.py").read_text(encoding="utf-8")
    required_fragments = [
        "def native_hotkeys_supported() -> bool:",
        "def parse_hotkey_spec(spec: str | None) -> tuple[int, int, str] | None:",
        "MOD_NOREPEAT = 0x4000",
        "user32.RegisterHotKey",
        "user32.UnregisterHotKey",
        "user32.GetMessageW",
        "user32.PostThreadMessageW",
        "WM_HOTKEY = 0x0312",
        "WM_APP_TASK = 0x8001",
        "class NativeHotkeyManager:",
        "self._tasks: Queue[Callable[[], None]] = Queue()",
        "self._callbacks: dict[int, Callable[[], None]] = {}",
        "self._post_task(task, result_ready)",
        "if msg.message == WM_APP_TASK:",
        "if msg.message != WM_HOTKEY:",
        "callback = self._callbacks.get(int(msg.wParam))",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in hotkey_text]
    if missing:
        raise RuntimeError(f"native hotkey manager fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_status_runtime_waits_for_overlay_before_first_action() -> dict[str, Any]:
    text = (PROJECT_ROOT / "status_runtime.py").read_text(encoding="utf-8")
    required_fragments = [
        "self._ensure_overlay_process_for_start()",
        "self._wait_for_overlay_ready(timeout_seconds=0.8)",
        "def _ensure_overlay_process_for_start(self) -> None:",
        "Reusing status overlay pid=%s via startup pid_file",
        "Skipping status overlay startup reuse pid=%s reason=%s",
        "Discarding stale startup overlay pid=%s because it does not match the expected overlay process",
        "def _wait_for_overlay_ready(self, timeout_seconds: float) -> None:",
        "verified = self._verified_overlay_process(existing_pid)",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in text]
    if missing:
        raise RuntimeError(f"status_runtime missing overlay ready fragments: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_next_request_can_buffer_before_pause_ack() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "self._pending_pause_ack_next_requests = 0",
        "Hotkey NEXT buffered while pause acknowledgement is still settling",
        "PAUSE_ACK draining buffered NEXT requests",
        "self._queue_manual_next_request()",
        "暂停确认中，已缓存",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"pause-ack NEXT buffering fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_dwell_status_text_no_longer_repaints_countdown_every_second() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required = [
        'return f"已放大 {self._cell_hint(self._active_cell)}，停留中"',
        'return "已回到宫格，准备切下一路"',
    ]
    missing = [fragment for fragment in required if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"dwell/grid dwell status text fragments missing: {missing}")
    forbidden = [
        'return f"已放大 {self._cell_hint(self._active_cell)}，剩余 {remaining} 秒"',
        'return f"已回到宫格，剩余 {remaining} 秒后切下一路"',
    ]
    stale = [fragment for fragment in forbidden if fragment in scheduler_text]
    if stale:
        raise RuntimeError(f"stale dwell countdown status text is still present: {stale}")
    return {"checked_fragments": len(required)}


def test_select_status_text_no_longer_promises_fixed_half_second() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required = "正在确认后双击放大"
    forbidden = "0.5秒后双击放大"
    if required not in scheduler_text:
        raise RuntimeError("updated select status text is missing")
    if forbidden in scheduler_text:
        raise RuntimeError("stale fixed half-second status text is still present")
    return {"status_text": required}


def test_detected_issue_skip_mode_controls_auto_pause() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _pause_for_detected_issue",
        "self._config.detection.skip_on_detected_issue",
        "ISSUE_FAILURE consecutive issues reached cooldown threshold",
        "continuing recovery without auto-pause",
        "ISSUE_FAILURE auto-pausing after consecutive detected issues",
        "仅在显式需要人工介入的致命异常上暂停",
        'self._reset_issue_failure_streak("grid_confirmed")',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"detected-issue skip-mode fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_low_texture_zoom_confirm_can_still_pass() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    before_preview = Image.new("L", (192, 144), color=40)
    before_cell = Image.new("L", (160, 120), color=48)
    after_preview = Image.new("L", (192, 144), color=46)

    detector.capture_image = lambda rect: after_preview.convert("RGB")  # type: ignore[method-assign]
    metrics_queue = [
        {"mean_diff": 4.3682, "changed_ratio": 0.1129},
        {"mean_diff": 4.6821, "changed_ratio": 0.1837},
    ]
    detector.measure_visual_change = lambda before, after: metrics_queue.pop(0)  # type: ignore[method-assign]
    detector._divider_band_metrics = lambda *args, **kwargs: {  # type: ignore[attr-defined]
        "divider_edge_before": 0.0083,
        "divider_edge_after": 0.0121,
        "divider_edge_reduction": 0.0,
        "divider_rows_estimate": 4.0,
        "divider_cols_estimate": 3.0,
    }
    detector._content_continuity_metrics = lambda *args, **kwargs: {  # type: ignore[attr-defined]
        "continuity_mean_diff": 3.3394,
        "continuity_changed_ratio": 0.1296,
        "continuity_score": 16.2994,
        "histogram_corr": 0.9998,
        "orb_ref_keypoints": 69.0,
        "orb_candidate_keypoints": 41.0,
        "orb_good_matches": 5.0,
        "orb_match_ratio": 0.3846,
        "orb_participated": 1.0,
        "orb_vote": 1.0,
        "orb_mean_distance": 59.2308,
    }
    detector.classify_runtime_view = lambda *args, **kwargs: (  # type: ignore[method-assign]
        VisualViewState.UNKNOWN,
        {
            "flat_interface_like": 1.0,
            "grid_probe_mean_diff": 4.5232,
            "grid_probe_changed_ratio": 0.1199,
            "grid_probe_score": 16.5132,
        },
    )

    result = detector.confirm_zoom(
        Rect(0, 0, 192, 144),
        Rect(0, 0, 64, 48),
        cell_rect=Rect(0, 0, 64, 48),
        before_preview_probe=before_preview,
        before_cell_probe=before_cell,
        grid_probe=None,
    )
    if result.state != ConfirmState.STATE_CONFIRMED:
        raise RuntimeError(f"low-texture zoom confirm sample was rejected: {result}")
    return {
        "confirm_state": result.state.value,
        "low_texture_zoom_confirmed": result.metrics.get("low_texture_zoom_confirmed"),
    }


def test_fullscreen_retry_sample_can_confirm_low_texture_zoom() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._low_texture_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={"flat_interface_like": 1.0},
        continuity_metrics={
            "histogram_corr": 0.9942,
            "orb_vote": 0.0,
        },
        full_change_metrics={
            "mean_diff": 3.1529,
            "changed_ratio": 0.0933,
        },
        main_view_change_metrics={
            "mean_diff": 3.7866,
            "changed_ratio": 0.1446,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("fullscreen retry low-texture sample was rejected by _low_texture_zoom_confirmed")
    return {"confirmed": confirmed}


def test_real_fullscreen_failure_page_sample_can_confirm_low_texture_zoom() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._low_texture_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={"flat_interface_like": 1.0},
        continuity_metrics={
            "histogram_corr": 0.9992,
            "orb_vote": 1.0,
        },
        full_change_metrics={
            "mean_diff": 2.5660,
            "changed_ratio": 0.0807,
        },
        main_view_change_metrics={
            "mean_diff": 3.7866,
            "changed_ratio": 0.1446,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("real fullscreen failure-page sample was rejected by _low_texture_zoom_confirmed")
    return {"confirmed": confirmed}


def test_windowed_dominant_surface_sample_can_confirm_low_texture_zoom() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._low_texture_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 0.0,
            "preview_dominant_ratio": 0.8642,
            "preview_std": 12.5302,
            "preview_entropy": 1.8032,
        },
        continuity_metrics={
            "histogram_corr": 0.9953,
            "orb_vote": 0.0,
        },
        full_change_metrics={
            "mean_diff": 3.4084,
            "changed_ratio": 0.0779,
        },
        main_view_change_metrics={
            "mean_diff": 5.5004,
            "changed_ratio": 0.1977,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("windowed dominant-surface sample was rejected by _low_texture_zoom_confirmed")
    return {"confirmed": confirmed}


def test_windowed_continuity_dominant_sample_can_confirm_zoom() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._continuity_dominant_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9583,
            "preview_std": 6.9089,
            "preview_entropy": 0.5079,
        },
        continuity_metrics={
            "continuity_mean_diff": 3.2622,
            "continuity_changed_ratio": 0.1221,
            "continuity_score": 15.4722,
            "histogram_corr": 0.9995,
            "orb_vote": 1.0,
        },
        full_change_metrics={
            "mean_diff": 3.3083,
            "changed_ratio": 0.0872,
        },
        main_view_change_metrics={
            "mean_diff": 2.608,
            "changed_ratio": 0.0867,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("windowed continuity-dominant sample was rejected by _continuity_dominant_zoom_confirmed")
    return {"confirmed": confirmed}


def test_fullscreen_four_third_cell_sample_can_confirm_zoom_via_continuity_dominant_path() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._continuity_dominant_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9031,
            "preview_std": 12.5929,
            "preview_entropy": 0.8817,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 2.0,
            "divider_edge_before": 0.007,
            "divider_edge_after": 0.0019,
            "divider_edge_reduction": 0.0051,
        },
        continuity_metrics={
            "continuity_mean_diff": 1.175,
            "continuity_changed_ratio": 0.025,
            "continuity_score": 3.675,
            "histogram_corr": 0.9998,
            "orb_vote": 0.0,
        },
        full_change_metrics={
            "mean_diff": 2.5079,
            "changed_ratio": 0.0593,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("fullscreen4 third-cell sample was rejected by generic continuity-dominant zoom path")
    return {"confirmed": confirmed}


def test_fullscreen_four_third_cell_retry_like_sample_is_not_misconfirmed_by_continuity_path() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._continuity_dominant_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.8981,
            "preview_std": 10.9647,
            "preview_entropy": 1.042,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 2.0,
            "divider_edge_before": 0.0019,
            "divider_edge_after": 0.007,
            "divider_edge_reduction": 0.0,
        },
        continuity_metrics={
            "continuity_mean_diff": 2.1258,
            "continuity_changed_ratio": 0.0801,
            "continuity_score": 10.1358,
            "histogram_corr": 0.9985,
            "orb_vote": 0.0,
        },
        full_change_metrics={
            "mean_diff": 2.5079,
            "changed_ratio": 0.0593,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if confirmed:
        raise RuntimeError("fullscreen4 retry-like sample was misconfirmed by generic continuity-dominant zoom path")
    return {"confirmed": confirmed}


def test_fullscreen_four_fourth_cell_sample_can_confirm_zoom_via_continuity_dominant_path() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._continuity_dominant_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9036,
            "preview_std": 12.4392,
            "preview_entropy": 0.8709,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 2.0,
            "divider_edge_before": 0.0063,
            "divider_edge_after": 0.0019,
            "divider_edge_reduction": 0.0044,
        },
        continuity_metrics={
            "continuity_mean_diff": 1.1679,
            "continuity_changed_ratio": 0.0348,
            "continuity_score": 4.6479,
            "histogram_corr": 0.9998,
            "orb_vote": 0.0,
        },
        full_change_metrics={
            "mean_diff": 2.3793,
            "changed_ratio": 0.0597,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("fullscreen4 fourth-cell sample was rejected by generic continuity-dominant zoom path")
    return {"confirmed": confirmed}


def test_fullscreen_four_fourth_cell_retry_like_sample_is_not_misconfirmed_by_continuity_path() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._continuity_dominant_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9014,
            "preview_std": 10.5663,
            "preview_entropy": 1.0352,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 2.0,
            "divider_edge_before": 0.0019,
            "divider_edge_after": 0.0063,
            "divider_edge_reduction": 0.0,
        },
        continuity_metrics={
            "continuity_mean_diff": 4.4004,
            "continuity_changed_ratio": 0.1678,
            "continuity_score": 21.1804,
            "histogram_corr": 1.0,
            "orb_vote": 1.0,
        },
        full_change_metrics={
            "mean_diff": 2.3793,
            "changed_ratio": 0.0597,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if confirmed:
        raise RuntimeError("fullscreen4 fourth-cell retry-like sample was misconfirmed by generic continuity-dominant zoom path")
    return {"confirmed": confirmed}


def test_locked_fullscreen_transition_zoom_confirmed_supports_preview_failure_sample() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._locked_fullscreen_transition_zoom_confirmed(  # type: ignore[attr-defined]
        locked_fullscreen_layout=4,
        runtime_metrics={
            "grid_divider_rows_estimate": 2.0,
            "grid_divider_cols_estimate": 2.0,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 2.0,
            "divider_edge_before": 0.0074,
            "divider_edge_after": 0.0019,
            "divider_edge_reduction": 0.0055,
        },
        continuity_metrics={
            "histogram_corr": 0.9914,
            "orb_vote": 0.0,
            "continuity_score": 25.3252,
            "continuity_changed_ratio": 0.175,
        },
        full_change_metrics={
            "mean_diff": 4.0652,
            "changed_ratio": 0.1063,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("locked fullscreen transition sample was rejected despite a valid divider-collapse transition")
    return {"confirmed": confirmed}


def test_locked_fullscreen_transition_zoom_confirmed_rejects_retry_like_sample() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._locked_fullscreen_transition_zoom_confirmed(  # type: ignore[attr-defined]
        locked_fullscreen_layout=4,
        runtime_metrics={
            "grid_divider_rows_estimate": 2.0,
            "grid_divider_cols_estimate": 2.0,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 2.0,
            "divider_edge_before": 0.0019,
            "divider_edge_after": 0.0074,
            "divider_edge_reduction": 0.0,
        },
        continuity_metrics={
            "histogram_corr": 0.995,
            "orb_vote": 1.0,
            "continuity_score": 15.3395,
            "continuity_changed_ratio": 0.116,
        },
        full_change_metrics={
            "mean_diff": 4.0652,
            "changed_ratio": 0.1063,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if confirmed:
        raise RuntimeError("locked fullscreen transition retry-like sample was misconfirmed without divider collapse")
    return {"confirmed": confirmed}


def test_locked_fullscreen_six_transition_zoom_confirmed_supports_bottom_middle_sample() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._locked_fullscreen_transition_zoom_confirmed(  # type: ignore[attr-defined]
        locked_fullscreen_layout=6,
        runtime_metrics={
            "grid_divider_rows_estimate": 2.0,
            "grid_divider_cols_estimate": 3.0,
            "preview_dominant_ratio": 0.9045,
            "preview_std": 12.0164,
            "preview_entropy": 0.8436,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 3.0,
            "divider_edge_before": 0.0144,
            "divider_edge_after": 0.0057,
            "divider_edge_reduction": 0.0087,
        },
        continuity_metrics={
            "histogram_corr": 0.9977,
            "continuity_score": 16.5766,
            "continuity_changed_ratio": 0.1192,
        },
        full_change_metrics={
            "mean_diff": 5.945,
            "changed_ratio": 0.1462,
        },
        main_view_change_metrics={
            "mean_diff": 0.7013,
            "changed_ratio": 0.0295,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("fullscreen6 bottom-middle transition sample was rejected despite a valid 2x3 divider-collapse transition")
    return {"confirmed": confirmed}


def test_locked_fullscreen_six_transition_zoom_confirmed_supports_bottom_right_sample() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._locked_fullscreen_transition_zoom_confirmed(  # type: ignore[attr-defined]
        locked_fullscreen_layout=6,
        runtime_metrics={
            "grid_divider_rows_estimate": 2.0,
            "grid_divider_cols_estimate": 3.0,
            "preview_dominant_ratio": 0.9036,
            "preview_std": 12.4524,
            "preview_entropy": 0.8724,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 3.0,
            "divider_edge_before": 0.0138,
            "divider_edge_after": 0.0059,
            "divider_edge_reduction": 0.008,
        },
        continuity_metrics={
            "histogram_corr": 0.9997,
            "continuity_score": 2.095,
            "continuity_changed_ratio": 0.0167,
        },
        full_change_metrics={
            "mean_diff": 5.8685,
            "changed_ratio": 0.1464,
        },
        main_view_change_metrics={
            "mean_diff": 0.7013,
            "changed_ratio": 0.0295,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("fullscreen6 bottom-right transition sample was rejected despite a valid 2x3 divider-collapse transition")
    return {"confirmed": confirmed}


def test_locked_fullscreen_six_transition_zoom_confirmed_rejects_retry_like_sample() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._locked_fullscreen_transition_zoom_confirmed(  # type: ignore[attr-defined]
        locked_fullscreen_layout=6,
        runtime_metrics={
            "grid_divider_rows_estimate": 2.0,
            "grid_divider_cols_estimate": 3.0,
            "preview_dominant_ratio": 0.9013,
            "preview_std": 10.5086,
            "preview_entropy": 1.1327,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 3.0,
            "divider_edge_before": 0.0057,
            "divider_edge_after": 0.0144,
            "divider_edge_reduction": 0.0,
        },
        continuity_metrics={
            "histogram_corr": 0.9998,
            "continuity_score": 3.4648,
            "continuity_changed_ratio": 0.0276,
        },
        full_change_metrics={
            "mean_diff": 5.945,
            "changed_ratio": 0.1462,
        },
        main_view_change_metrics={
            "mean_diff": 0.7013,
            "changed_ratio": 0.0295,
        },
        content_continuity_confirmed=True,
    )
    if confirmed:
        raise RuntimeError("fullscreen6 retry-like sample was misconfirmed without a valid 2x3 divider-collapse transition")
    return {"confirmed": confirmed}


def test_dynamic_scene_expansion_dominant_sample_can_confirm_zoom() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._expansion_dominant_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 0.0,
            "structure_mean_diff": 60.4006,
            "structure_changed_ratio": 0.8591,
            "grid_divider_hit_count": 5.0,
            "grid_divider_expected_count": 5.0,
            "grid_divider_row_peak_match_count": 1.0,
            "grid_divider_col_peak_match_count": 2.0,
        },
        continuity_metrics={
            "histogram_corr": 0.4572,
            "orb_good_matches": 1.0,
            "continuity_mean_diff": 65.0884,
        },
        full_change_metrics={
            "mean_diff": 77.7294,
            "changed_ratio": 0.9001,
        },
        main_view_change_metrics={
            "mean_diff": 69.8551,
            "changed_ratio": 0.8892,
        },
        main_view_expansion_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("dynamic-scene expansion-dominant sample was rejected by _expansion_dominant_zoom_confirmed")
    return {"confirmed": confirmed}


def test_black_screen_soft_hint_can_confirm_zoom_without_retry() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    preview_rect = Rect(0, 0, 192, 144)
    active_rect = Rect(0, 0, 64, 48)
    cell_rect = Rect(0, 0, 64, 48)

    def build_detector() -> tuple[Detector, Image.Image, Image.Image]:
        detector = Detector(config.detection, _FakeLogger())
        before_preview = Image.new("L", (192, 144), color=40)
        before_cell = Image.new("L", (160, 120), color=48)
        after_preview = Image.new("L", (192, 144), color=46)
        detector.capture_image = lambda rect: after_preview.convert("RGB")  # type: ignore[method-assign]
        metrics_queue = [
            {"mean_diff": 2.6887, "changed_ratio": 0.0946},
            {"mean_diff": 4.6727, "changed_ratio": 0.1907},
        ]
        detector.measure_visual_change = lambda before, after: metrics_queue.pop(0)  # type: ignore[method-assign]
        detector._divider_band_metrics = lambda *args, **kwargs: {  # type: ignore[attr-defined]
            "divider_edge_before": 0.0069,
            "divider_edge_after": 0.0058,
            "divider_edge_reduction": 0.0011,
            "divider_rows_estimate": 4.0,
            "divider_cols_estimate": 3.0,
        }
        detector._content_continuity_metrics = lambda *args, **kwargs: {  # type: ignore[attr-defined]
            "continuity_mean_diff": 5.1684,
            "continuity_changed_ratio": 0.1708,
            "continuity_score": 22.2484,
            "histogram_corr": 0.9992,
            "orb_ref_keypoints": 68.0,
            "orb_candidate_keypoints": 46.0,
            "orb_good_matches": 4.0,
            "orb_match_ratio": 0.3636,
            "orb_participated": 1.0,
            "orb_vote": 1.0,
            "orb_mean_distance": 54.1818,
        }
        detector.classify_runtime_view = lambda *args, **kwargs: (  # type: ignore[method-assign]
            VisualViewState.UNKNOWN,
            {
                "flat_interface_like": 0.0,
                "grid_probe_mean_diff": 3.0315,
                "grid_probe_changed_ratio": 0.0791,
                "grid_probe_score": 10.9415,
                "preview_entropy": 1.9635,
                "preview_std": 10.6865,
                "preview_edge_ratio": 0.0761,
                "preview_dominant_ratio": 0.8368,
            },
        )
        return detector, before_preview, before_cell

    detector_without_hint, before_preview, before_cell = build_detector()
    without_hint = detector_without_hint.confirm_zoom(
        preview_rect,
        active_rect,
        cell_rect=cell_rect,
        before_preview_probe=before_preview,
        before_cell_probe=before_cell,
        grid_probe=None,
    )
    if without_hint.state != ConfirmState.STATE_CONFIRMED:
        raise RuntimeError(f"generic flat-surface sample should confirm without a soft hint: {without_hint}")

    detector_with_hint, before_preview, before_cell = build_detector()
    with_hint = detector_with_hint.confirm_zoom(
        preview_rect,
        active_rect,
        cell_rect=cell_rect,
        before_preview_probe=before_preview,
        before_cell_probe=before_cell,
        grid_probe=None,
        soft_issue_hint="black_screen",
    )
    if with_hint.state != ConfirmState.STATE_CONFIRMED:
        raise RuntimeError(f"generic flat-surface sample should still confirm with a soft hint: {with_hint}")
    return {
        "without_hint": without_hint.state.value,
        "with_hint": with_hint.state.value,
        "low_texture_zoom_confirmed": with_hint.metrics.get("low_texture_zoom_confirmed"),
    }


def test_fullscreen_four_black_screen_retry_sample_can_confirm_zoom_without_pause() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    without_hint = detector._low_texture_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9033,
            "preview_std": 12.2389,
            "preview_entropy": 0.8808,
        },
        continuity_metrics={
            "histogram_corr": 0.9988,
            "orb_vote": 0.0,
            "continuity_score": 8.688,
        },
        full_change_metrics={
            "mean_diff": 3.6464,
            "changed_ratio": 0.086,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if not without_hint:
        raise RuntimeError("fullscreen4 retry sample should confirm through the generic surface-transition path")

    with_hint = detector._low_texture_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9033,
            "preview_std": 12.2389,
            "preview_entropy": 0.8808,
        },
        continuity_metrics={
            "histogram_corr": 0.9988,
            "orb_vote": 0.0,
            "continuity_score": 8.688,
        },
        full_change_metrics={
            "mean_diff": 3.6464,
            "changed_ratio": 0.086,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
        soft_issue_hint="black_screen",
    )
    if not with_hint:
        raise RuntimeError("fullscreen4 retry sample should also confirm with a soft hint present")
    return {
        "without_hint": without_hint,
        "with_hint": with_hint,
    }


def test_fullscreen_four_low_texture_no_hint_sample_can_confirm_zoom_after_resume() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._low_texture_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.935,
            "preview_std": 8.406,
            "preview_entropy": 0.811,
        },
        continuity_metrics={
            "histogram_corr": 1.0,
            "orb_vote": 1.0,
            "continuity_score": 21.1804,
            "continuity_changed_ratio": 0.1678,
        },
        full_change_metrics={
            "mean_diff": 3.7755,
            "changed_ratio": 0.0911,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("fullscreen4 no-hint low-texture resume sample was rejected by _low_texture_zoom_confirmed")
    return {"confirmed": confirmed}


def test_fullscreen_four_bottom_right_no_hint_sample_can_confirm_zoom_without_pause() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._low_texture_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9036,
            "preview_std": 12.4392,
            "preview_entropy": 0.8709,
        },
        layout_metrics={"divider_rows_estimate": 2.0, "divider_cols_estimate": 2.0},
        continuity_metrics={
            "histogram_corr": 0.9975,
            "orb_vote": 0.0,
            "continuity_score": 15.7889,
            "continuity_changed_ratio": 0.1149,
        },
        full_change_metrics={
            "mean_diff": 6.0607,
            "changed_ratio": 0.1498,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("fullscreen4 bottom-right no-hint sample was rejected by _low_texture_zoom_confirmed")
    return {"confirmed": confirmed}


def test_fullscreen_four_first_cell_black_screen_sample_can_confirm_zoom_without_pause() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._low_texture_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9033,
            "preview_std": 12.2389,
            "preview_entropy": 0.8808,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 2.0,
            "divider_edge_before": 0.0097,
            "divider_edge_after": 0.0019,
            "divider_edge_reduction": 0.0078,
        },
        continuity_metrics={
            "histogram_corr": 0.997,
            "orb_vote": 0.0,
            "continuity_score": 18.3378,
            "continuity_changed_ratio": 0.1352,
        },
        full_change_metrics={
            "mean_diff": 2.0654,
            "changed_ratio": 0.0527,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("fullscreen4 first-cell sample was rejected by the generic surface-transition path")
    return {"confirmed": confirmed}


def test_fullscreen_four_top_right_black_screen_sample_can_confirm_zoom_without_pause() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._low_texture_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9643,
            "preview_std": 6.5888,
            "preview_entropy": 0.4016,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 2.0,
            "divider_edge_before": 0.007,
            "divider_edge_after": 0.0015,
            "divider_edge_reduction": 0.0055,
        },
        continuity_metrics={
            "histogram_corr": 0.9999,
            "orb_vote": 0.0,
            "continuity_score": 2.5763,
            "continuity_changed_ratio": 0.0187,
        },
        full_change_metrics={
            "mean_diff": 1.5899,
            "changed_ratio": 0.0407,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("fullscreen4 top-right sample was rejected by the generic surface-transition path")
    return {"confirmed": confirmed}


def test_fullscreen_four_second_cell_black_screen_sample_can_confirm_zoom_without_pause() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._low_texture_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9039,
            "preview_std": 12.351,
            "preview_entropy": 0.8576,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 2.0,
            "divider_edge_before": 0.007,
            "divider_edge_after": 0.0019,
            "divider_edge_reduction": 0.0051,
        },
        continuity_metrics={
            "histogram_corr": 0.9995,
            "orb_vote": 0.0,
            "continuity_score": 7.3727,
            "continuity_changed_ratio": 0.0525,
        },
        full_change_metrics={
            "mean_diff": 2.5418,
            "changed_ratio": 0.06,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("fullscreen4 second-cell sample was rejected by the generic surface-transition path")
    return {"confirmed": confirmed}


def test_fullscreen_four_bottom_left_black_screen_sample_can_confirm_zoom_without_pause() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._low_texture_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9635,
            "preview_std": 6.5866,
            "preview_entropy": 0.4151,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 2.0,
            "divider_edge_before": 0.007,
            "divider_edge_after": 0.0015,
            "divider_edge_reduction": 0.0055,
        },
        continuity_metrics={
            "histogram_corr": 0.9998,
            "orb_vote": 0.0,
            "continuity_score": 3.675,
            "continuity_changed_ratio": 0.025,
        },
        full_change_metrics={
            "mean_diff": 1.6884,
            "changed_ratio": 0.0414,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("fullscreen4 bottom-left sample was rejected by the generic surface-transition path")
    return {"confirmed": confirmed}


def test_fullscreen_four_bottom_right_black_screen_sample_can_confirm_zoom_without_pause() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    confirmed = detector._low_texture_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.964,
            "preview_std": 6.5678,
            "preview_entropy": 0.4094,
        },
        layout_metrics={
            "divider_rows_estimate": 2.0,
            "divider_cols_estimate": 2.0,
            "divider_edge_before": 0.0063,
            "divider_edge_after": 0.0015,
            "divider_edge_reduction": 0.0047,
        },
        continuity_metrics={
            "histogram_corr": 0.9998,
            "orb_vote": 0.0,
            "continuity_score": 4.6479,
            "continuity_changed_ratio": 0.0348,
        },
        full_change_metrics={
            "mean_diff": 1.5577,
            "changed_ratio": 0.0418,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if not confirmed:
        raise RuntimeError("fullscreen4 bottom-right sample was rejected by the generic surface-transition path")
    return {"confirmed": confirmed}


def test_windowed_black_screen_retry_sample_can_confirm_zoom_without_recovery() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())
    preview_rect = Rect(0, 0, 192, 144)
    active_rect = Rect(0, 0, 64, 48)
    cell_rect = Rect(0, 0, 64, 48)
    before_preview = Image.new("L", (192, 144), color=28)
    before_cell = Image.new("L", (160, 120), color=28)
    after_preview = Image.new("L", (192, 144), color=30)

    detector.capture_image = lambda rect: after_preview.convert("RGB")  # type: ignore[method-assign]
    metrics_queue = [
        {"mean_diff": 2.7252, "changed_ratio": 0.0744},
        {"mean_diff": 4.5807, "changed_ratio": 0.1819},
    ]
    detector.measure_visual_change = lambda before, after: metrics_queue.pop(0)  # type: ignore[method-assign]
    detector._divider_band_metrics = lambda *args, **kwargs: {  # type: ignore[attr-defined]
        "divider_edge_before": 0.0034,
        "divider_edge_after": 0.0011,
        "divider_edge_reduction": 0.0023,
        "divider_rows_estimate": 4.0,
        "divider_cols_estimate": 3.0,
    }
    detector._content_continuity_metrics = lambda *args, **kwargs: {  # type: ignore[attr-defined]
        "continuity_mean_diff": 3.4383,
        "continuity_changed_ratio": 0.1288,
        "continuity_score": 16.3183,
        "histogram_corr": 0.9998,
        "orb_ref_keypoints": 77.0,
        "orb_candidate_keypoints": 39.0,
        "orb_good_matches": 4.0,
        "orb_match_ratio": 0.2667,
        "orb_participated": 1.0,
        "orb_vote": 1.0,
        "orb_mean_distance": 59.8667,
    }
    detector.classify_runtime_view = lambda *args, **kwargs: (  # type: ignore[method-assign]
        VisualViewState.UNKNOWN,
        {
            "flat_interface_like": 1.0,
            "grid_probe_mean_diff": 0.21,
            "grid_probe_changed_ratio": 0.0029,
            "grid_probe_score": 0.5,
            "preview_entropy": 0.2803,
            "preview_std": 3.8958,
            "preview_edge_ratio": 0.0142,
            "preview_dominant_ratio": 0.9787,
            "grid_divider_rows_estimate": 4.0,
            "grid_divider_cols_estimate": 3.0,
        },
    )

    result = detector.confirm_zoom(
        preview_rect,
        active_rect,
        cell_rect=cell_rect,
        before_preview_probe=before_preview,
        before_cell_probe=before_cell,
        grid_probe=None,
    )
    if result.state != ConfirmState.STATE_CONFIRMED:
        raise RuntimeError(f"windowed flat-surface retry sample still failed generic zoom confirm: {result}")
    return {
        "state": result.state.value,
        "low_texture_zoom_confirmed": result.metrics.get("low_texture_zoom_confirmed"),
        "full_frame_changed_ratio": result.metrics.get("full_frame_changed_ratio"),
    }


def test_preview_failure_soft_hint_can_confirm_zoom_without_retry() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    preview_rect = Rect(0, 0, 192, 144)
    active_rect = Rect(0, 0, 64, 48)
    cell_rect = Rect(0, 0, 64, 48)

    def build_detector() -> tuple[Detector, Image.Image, Image.Image]:
        detector = Detector(config.detection, _FakeLogger())
        before_preview = Image.new("L", (192, 144), color=40)
        before_cell = Image.new("L", (160, 120), color=48)
        after_preview = Image.new("L", (192, 144), color=46)
        detector.capture_image = lambda rect: after_preview.convert("RGB")  # type: ignore[method-assign]
        metrics_queue = [
            {"mean_diff": 5.7623, "changed_ratio": 0.1453},
            {"mean_diff": 2.6080, "changed_ratio": 0.0867},
        ]
        detector.measure_visual_change = lambda before, after: metrics_queue.pop(0)  # type: ignore[method-assign]
        detector._divider_band_metrics = lambda *args, **kwargs: {  # type: ignore[attr-defined]
            "divider_edge_before": 0.0128,
            "divider_edge_after": 0.0033,
            "divider_edge_reduction": 0.0096,
            "divider_rows_estimate": 3.0,
            "divider_cols_estimate": 3.0,
        }
        detector._content_continuity_metrics = lambda *args, **kwargs: {  # type: ignore[attr-defined]
            "continuity_mean_diff": 10.0055,
            "continuity_changed_ratio": 0.2555,
            "continuity_score": 35.5555,
            "histogram_corr": 0.9923,
            "orb_ref_keypoints": 56.0,
            "orb_candidate_keypoints": 53.0,
            "orb_good_matches": 13.0,
            "orb_match_ratio": 0.7647,
            "orb_participated": 1.0,
            "orb_vote": 1.0,
            "orb_mean_distance": 36.4118,
        }
        detector.classify_runtime_view = lambda *args, **kwargs: (  # type: ignore[method-assign]
            VisualViewState.UNKNOWN,
            {
                "flat_interface_like": 1.0,
                "grid_probe_mean_diff": 5.6711,
                "grid_probe_changed_ratio": 0.1523,
                "grid_probe_score": 20.9011,
                "preview_entropy": 0.8617,
                "preview_std": 10.9490,
                "preview_edge_ratio": 0.0307,
                "preview_dominant_ratio": 0.9144,
            },
        )
        return detector, before_preview, before_cell

    detector_without_hint, before_preview, before_cell = build_detector()
    without_hint = detector_without_hint.confirm_zoom(
        preview_rect,
        active_rect,
        cell_rect=cell_rect,
        before_preview_probe=before_preview,
        before_cell_probe=before_cell,
        grid_probe=None,
    )
    if without_hint.state != ConfirmState.STATE_CONFIRMED:
        raise RuntimeError(f"preview-failure-like flat-surface sample should confirm without a soft hint: {without_hint}")

    detector_with_hint, before_preview, before_cell = build_detector()
    with_hint = detector_with_hint.confirm_zoom(
        preview_rect,
        active_rect,
        cell_rect=cell_rect,
        before_preview_probe=before_preview,
        before_cell_probe=before_cell,
        grid_probe=None,
        soft_issue_hint="preview_failure",
    )
    if with_hint.state != ConfirmState.STATE_CONFIRMED:
        raise RuntimeError(f"preview-failure-like sample should still confirm with a soft hint present: {with_hint}")
    return {
        "without_hint": without_hint.state.value,
        "with_hint": with_hint.state.value,
        "preview_failure_zoom_confirmed": with_hint.metrics.get("preview_failure_zoom_confirmed"),
    }


def test_fullscreen_four_preview_failure_sample_can_confirm_zoom_without_pause() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    without_hint = detector._preview_failure_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9031,
            "preview_std": 12.5929,
            "preview_entropy": 0.8817,
        },
        layout_metrics={"divider_rows_estimate": 2.0, "divider_cols_estimate": 2.0},
        continuity_metrics={
            "histogram_corr": 0.9914,
            "orb_vote": 0.0,
            "continuity_score": 25.3252,
            "continuity_changed_ratio": 0.175,
        },
        full_change_metrics={
            "mean_diff": 6.2184,
            "changed_ratio": 0.1494,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
    )
    if not without_hint:
        raise RuntimeError("fullscreen4 preview-failure-like sample should confirm without a soft hint")

    with_hint = detector._preview_failure_zoom_confirmed(  # type: ignore[attr-defined]
        runtime_metrics={
            "flat_interface_like": 1.0,
            "preview_dominant_ratio": 0.9031,
            "preview_std": 12.5929,
            "preview_entropy": 0.8817,
        },
        layout_metrics={"divider_rows_estimate": 2.0, "divider_cols_estimate": 2.0},
        continuity_metrics={
            "histogram_corr": 0.9914,
            "orb_vote": 0.0,
            "continuity_score": 25.3252,
            "continuity_changed_ratio": 0.175,
        },
        full_change_metrics={
            "mean_diff": 6.2184,
            "changed_ratio": 0.1494,
        },
        main_view_change_metrics={
            "mean_diff": 2.1286,
            "changed_ratio": 0.0764,
        },
        content_continuity_confirmed=True,
        soft_issue_hint="preview_failure",
    )
    if not with_hint:
        raise RuntimeError("fullscreen4 preview-failure-like sample should still confirm with a soft hint present")
    return {"without_hint": without_hint, "with_hint": with_hint}


def test_runtime_transition_zoom_confirm_can_relax_continuity() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    before_preview = Image.new("L", (192, 144), color=40)
    before_cell = Image.new("L", (160, 120), color=48)
    after_preview = Image.new("L", (192, 144), color=46)

    detector.capture_image = lambda rect: after_preview.convert("RGB")  # type: ignore[method-assign]
    metrics_queue = [
        {"mean_diff": 5.4082, "changed_ratio": 0.1524},
        {"mean_diff": 3.8641, "changed_ratio": 0.1237},
    ]
    detector.measure_visual_change = lambda before, after: metrics_queue.pop(0)  # type: ignore[method-assign]
    detector._divider_band_metrics = lambda *args, **kwargs: {  # type: ignore[attr-defined]
        "divider_edge_before": 0.0071,
        "divider_edge_after": 0.0104,
        "divider_edge_reduction": 0.0,
        "divider_rows_estimate": 4.0,
        "divider_cols_estimate": 3.0,
    }
    detector._content_continuity_metrics = lambda *args, **kwargs: {  # type: ignore[attr-defined]
        "continuity_mean_diff": 42.0,
        "continuity_changed_ratio": 0.58,
        "continuity_score": 100.0,
        "histogram_corr": 0.63,
        "orb_ref_keypoints": 24.0,
        "orb_candidate_keypoints": 22.0,
        "orb_good_matches": 4.0,
        "orb_match_ratio": 0.18,
        "orb_participated": 1.0,
        "orb_vote": 0.0,
    }
    detector.classify_runtime_view = lambda *args, **kwargs: (  # type: ignore[method-assign]
        VisualViewState.ZOOMED,
        {
            "flat_interface_like": 0.0,
            "zoom_probe_mean_diff": 4.0,
            "zoom_probe_changed_ratio": 0.11,
            "zoom_probe_score": 15.0,
        },
    )

    result = detector.confirm_zoom(
        Rect(0, 0, 192, 144),
        Rect(0, 0, 64, 48),
        cell_rect=Rect(0, 0, 64, 48),
        before_preview_probe=before_preview,
        before_cell_probe=before_cell,
        grid_probe=None,
    )
    if result.state != ConfirmState.STATE_CONFIRMED:
        raise RuntimeError(f"runtime-transition zoom confirm sample was rejected: {result}")
    if result.metrics.get("content_continuity_confirmed") == 1.0:
        raise RuntimeError("runtime-transition sample unexpectedly passed the strict continuity gate")
    if result.metrics.get("runtime_transition_zoom_confirmed") != 1.0:
        raise RuntimeError("runtime-transition fallback did not set runtime_transition_zoom_confirmed=1")
    return {
        "confirm_state": result.state.value,
        "runtime_transition_zoom_confirmed": result.metrics.get("runtime_transition_zoom_confirmed"),
    }


def test_real_fullscreen_four_grid_failure_page_is_still_classified_as_grid() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())
    mapper = GridMapper(config.grid)
    sample_path = PROJECT_ROOT / "tmp" / "runtime_test" / "full_path" / "screenshots" / "error_recovery_1774486902.png"
    if not sample_path.exists():
        return {"skipped": True, "reason": f"missing sample: {sample_path}"}
    image = Image.open(sample_path)
    preview_rect = Rect(0, 0, image.width, image.height)

    cells_4 = mapper.build_cells(preview_rect, 4)
    actual_4, metrics_4 = detector.classify_runtime_view(
        preview_rect,
        cells_4[0].rect,
        grid_probe=None,
        zoom_probe=None,
        preview_image=image,
    )
    if actual_4 != VisualViewState.GRID:
        raise RuntimeError(f"fullscreen 4-grid failure-page sample was not classified as GRID: {actual_4} {metrics_4}")

    cells_12 = mapper.build_cells(preview_rect, 12)
    actual_12, metrics_12 = detector.classify_runtime_view(
        preview_rect,
        cells_12[0].rect,
        grid_probe=None,
        zoom_probe=None,
        preview_image=image,
    )
    if actual_12 == VisualViewState.GRID:
        raise RuntimeError(f"fullscreen 12-grid candidate should not win on the 4-grid failure-page sample: {metrics_12}")

    return {
        "layout4_actual": actual_4.value,
        "layout4_mean_strength": metrics_4.get("grid_divider_mean_strength"),
        "layout12_actual": actual_12.value,
        "layout12_mean_strength": metrics_12.get("grid_divider_mean_strength"),
    }



def test_fullscreen_six_grid_flat_fallback_is_wired() -> dict[str, Any]:
    detector_text = (PROJECT_ROOT / "detector.py").read_text(encoding="utf-8")
    required_fragments = [
        "fullscreen_six_resume_failure_grid = (",
        "and estimated_rows == 2",
        "and estimated_cols == 3",
        "and expected_count == 3",
        "and row_peak_support",
        "and col_peak_support",
        "and mean_strength >= 4.5",
        "and preview_dominant_ratio >= 0.90",
        "and preview_entropy <= 1.2",
        "and preview_std <= 11.5",
        "and preview_edge_ratio >= 0.035",
        "and structure_changed_ratio >= 0.10",
        "恢复后的失败页宫格并不一定是超低熵/超低方差",
        "and mean_strength >= 3.8",
        "and preview_dominant_ratio >= 0.93",
        "and preview_entropy <= 0.9",
        "and preview_std <= 7.0",
        "and preview_edge_ratio >= 0.03",
        "and structure_changed_ratio >= 0.075",
        "fullscreen 6 从 UNKNOWN 拉回 GRID",
        "fullscreen_six_weak_post_recover_grid = (",
        "and mean_strength >= 3.5",
        "and preview_std <= 6.0",
        "and structure_changed_ratio >= 0.03",
        "人工回宫格后的恢复链上，还会出现更弱的 2x3 暗色宫格",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in detector_text]
    if missing:
        raise RuntimeError(f"fullscreen 6-grid flat fallback fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_fullscreen_six_grid_flat_fallback_supports_dark_multicell_sample() -> dict[str, Any]:
    metrics = {
        "estimated_rows": 2.0,
        "estimated_cols": 3.0,
        "expected_count": 3.0,
        "row_peak_support": 1.0,
        "col_peak_support": 1.0,
        "mean_strength": 4.6416,
        "preview_dominant_ratio": 0.9042,
        "preview_entropy": 1.169,
        "preview_std": 11.2949,
        "preview_edge_ratio": 0.0373,
        "structure_changed_ratio": 0.1079,
        "flat_interface_like": 1.0,
    }
    checks = {
        "rows": int(round(float(metrics.get("estimated_rows", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("estimated_cols", 0.0)))) == 3,
        "expected_count": int(round(float(metrics.get("expected_count", 0.0)))) == 3,
        "row_peak_support": float(metrics.get("row_peak_support", 0.0)) == 1.0,
        "col_peak_support": float(metrics.get("col_peak_support", 0.0)) == 1.0,
        "mean_strength": float(metrics.get("mean_strength", 0.0)) >= 4.5,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.90,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 1.2,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 11.5,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.035,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.10,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"fullscreen6 resume peak sample no longer satisfies the broad grid fallback gate: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_fullscreen_six_grid_flat_fallback_supports_ultra_flat_dark_sample() -> dict[str, Any]:
    metrics = {
        "estimated_rows": 2.0,
        "estimated_cols": 3.0,
        "expected_count": 3.0,
        "row_peak_support": 1.0,
        "col_peak_support": 1.0,
        "mean_strength": 3.9239,
        "preview_dominant_ratio": 0.9342,
        "preview_entropy": 0.8807,
        "preview_std": 6.9145,
        "preview_edge_ratio": 0.0307,
        "structure_changed_ratio": 0.0791,
        "flat_interface_like": 1.0,
    }
    checks = {
        "rows": int(round(float(metrics.get("estimated_rows", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("estimated_cols", 0.0)))) == 3,
        "expected_count": int(round(float(metrics.get("expected_count", 0.0)))) == 3,
        "row_peak_support": float(metrics.get("row_peak_support", 0.0)) == 1.0,
        "col_peak_support": float(metrics.get("col_peak_support", 0.0)) == 1.0,
        "mean_strength": float(metrics.get("mean_strength", 0.0)) >= 3.8,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.93,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 0.9,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 7.0,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.03,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.075,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"fullscreen6 ultra-flat dark sample no longer satisfies the narrow grid fallback gate: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_fullscreen_six_grid_flat_fallback_supports_weak_post_recover_sample() -> dict[str, Any]:
    metrics = {
        "estimated_rows": 2.0,
        "estimated_cols": 3.0,
        "expected_count": 3.0,
        "row_peak_support": 1.0,
        "col_peak_support": 1.0,
        "mean_strength": 3.6929,
        "preview_dominant_ratio": 0.9342,
        "preview_entropy": 0.8491,
        "preview_std": 5.5297,
        "preview_edge_ratio": 0.0307,
        "structure_changed_ratio": 0.0388,
        "flat_interface_like": 1.0,
    }
    checks = {
        "rows": int(round(float(metrics.get("estimated_rows", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("estimated_cols", 0.0)))) == 3,
        "expected_count": int(round(float(metrics.get("expected_count", 0.0)))) == 3,
        "row_peak_support": float(metrics.get("row_peak_support", 0.0)) == 1.0,
        "col_peak_support": float(metrics.get("col_peak_support", 0.0)) == 1.0,
        "mean_strength": float(metrics.get("mean_strength", 0.0)) >= 3.5,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.93,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 0.9,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 6.0,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.03,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.03,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"fullscreen6 weak post-recover sample no longer satisfies the narrow grid fallback gate: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_fullscreen_six_grid_flat_fallback_supports_real_runtime_weak_sample() -> dict[str, Any]:
    metrics = {
        "estimated_rows": 2.0,
        "estimated_cols": 3.0,
        "expected_count": 3.0,
        "row_peak_support": 1.0,
        "col_peak_support": 1.0,
        "mean_strength": 3.5454,
        "preview_dominant_ratio": 0.9369,
        "preview_entropy": 0.8328,
        "preview_std": 4.6873,
        "preview_edge_ratio": 0.0307,
        "structure_changed_ratio": 0.031,
        "flat_interface_like": 1.0,
    }
    checks = {
        "rows": int(round(float(metrics.get("estimated_rows", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("estimated_cols", 0.0)))) == 3,
        "expected_count": int(round(float(metrics.get("expected_count", 0.0)))) == 3,
        "row_peak_support": float(metrics.get("row_peak_support", 0.0)) == 1.0,
        "col_peak_support": float(metrics.get("col_peak_support", 0.0)) == 1.0,
        "mean_strength": float(metrics.get("mean_strength", 0.0)) >= 3.5,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.93,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 0.9,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 6.0,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.03,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.03,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"fullscreen6 real-runtime weak sample no longer satisfies the narrow grid fallback gate: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_fullscreen_six_grid_flat_fallback_rejects_weak_dark_sample() -> dict[str, Any]:
    metrics = {
        "estimated_rows": 2.0,
        "estimated_cols": 3.0,
        "expected_count": 3.0,
        "mean_strength": 1.3307,
        "preview_dominant_ratio": 0.9045,
        "preview_entropy": 0.8436,
        "preview_std": 12.0164,
        "preview_edge_ratio": 0.0235,
        "structure_changed_ratio": 0.0198,
        "flat_interface_like": 1.0,
    }
    checks = {
        "mean_strength": float(metrics.get("mean_strength", 0.0)) >= 3.5,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.93,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 7.0,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.03,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.075,
    }
    if all(checks.values()):
        raise RuntimeError(f"fullscreen6 weak dark sample unexpectedly satisfies the flat grid fallback gate: metrics={metrics}")
    return {"failed_checks": [name for name, ok in checks.items() if not ok]}



def test_action_path_docs() -> dict[str, Any]:
    validated = {}
    for relative_path, required_fragments in DOCS_TO_VALIDATE.items():
        text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        missing = [fragment for fragment in required_fragments if fragment not in text]
        if missing:
            raise RuntimeError(f"{relative_path} missing fragments: {missing}")
        forbidden = [fragment for fragment in FORBIDDEN_DOC_FRAGMENTS if fragment in text]
        if forbidden:
            raise RuntimeError(f"{relative_path} still contains forbidden fragments: {forbidden}")
        validated[relative_path] = len(required_fragments)
    return validated



def test_build_release_include_list() -> dict[str, Any]:
    build_text = (PROJECT_ROOT / "build_release.py").read_text(encoding="utf-8")
    required = [
        "compileall.py",
        "HOW_TO_USE.md",
        "LAYOUT_SWITCH_MANUAL.md",
        "CODEX_LOCAL_ADMIN_PROMPT.txt",
        "inspect_windowed.bat",
        "inspect_fullscreen.bat",
        "layout_switcher.py",
        "runtime_guard.py",
        "CALIBRATION_GUIDE.md",
        "MIGRATION_GUIDE.md",
    ]
    missing = [item for item in required if f'"{item}"' not in build_text]
    if missing:
        raise RuntimeError(f"build_release missing include entries: {missing}")
    return {"required_entries": required}


def test_semantic_texts() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    app_text = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    required_fragments = [
        "restart current path",
        "current path will be restarted",
        'queue_depth_max_repr = "unlimited" if max_queue_depth == 0 else str(max_queue_depth)',
        "FAVORITES_ORDER count=%s names=%s",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text and fragment not in app_text]
    if missing:
        raise RuntimeError(f"semantic fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}



class _FakeLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


class _FakeDetector:
    def __init__(self, status: str = "ok"):
        self.status = status
        self.saved = 0

    def inspect_runtime_interface(self, *args, **kwargs):
        from common import DetectionResult

        return DetectionResult(status=self.status, metrics={"flat_interface_like": 1.0 if self.status == "unexpected_interface" else 0.0}, reason=self.status)

    def save_cell_snapshot(self, rect, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake")
        self.saved += 1
        return destination


class _FakeController:
    def __init__(self):
        self.escape_count = 0
        self.close_count = 0
        self.recover_count = 0

    def emergency_recover(self, hwnd=None):
        self.escape_count += 1

    def close_foreground_window(self):
        self.close_count += 1

    def recover_to_grid(self, hwnd=None):
        self.recover_count += 1


class _FakeWindowManager:
    def __init__(self, foreground=None, related=None):
        self.foreground = foreground
        self.related = list(related or [])
        self.focused = []

    def get_foreground_window_snapshot(self):
        return self.foreground

    def list_related_visible_windows(self, target_window):
        return list(self.related)

    def classify_window_relation(self, snapshot, target_window):
        if snapshot.process_id == target_window.process_id:
            return "same_process"
        if snapshot.owner_hwnd == target_window.hwnd:
            return "owned_by_target"
        return "other"

    def focus_window(self, hwnd):
        self.focused.append(hwnd)
        return True


def _fake_target_window() -> WindowInfo:
    return WindowInfo(
        hwnd=100,
        process_id=200,
        title="视频融合赋能平台",
        process_name="ClientFrame.exe",
        integrity_rid=0,
        integrity_label="medium",
        window_rect=Rect(0, 0, 1600, 900),
        client_rect=Rect(0, 0, 1600, 900),
        monitor_rect=Rect(0, 0, 1600, 900),
    )


def test_runtime_guard_popup_auto_heal() -> dict[str, Any]:
    target = _fake_target_window()
    popup = WindowSnapshot(
        hwnd=101,
        process_id=target.process_id,
        title="错误提示",
        process_name=target.process_name,
        rect=Rect(100, 100, 600, 300),
        owner_hwnd=target.hwnd,
        is_visible=True,
        is_foreground=True,
    )
    guard = RuntimeGuard(
        RuntimeGuardConfig(),
        _FakeWindowManager(foreground=popup, related=[popup]),
        _FakeDetector(status="ok"),
        _FakeController(),
        _FakeLogger(),
        PROJECT_ROOT / "config.yaml",
    )
    event = guard.check(
        stage="after_zoom_in",
        target_window=target,
        preview_rect=None,
        active_cell_rect=None,
        expected_view=None,
    )
    if event.ok or event.issue not in {"unexpected_related_window", "related_popup_visible"}:
        raise RuntimeError(f"unexpected guard event: {event}")
    controller = guard._controller
    healed = guard.try_auto_heal(event=event, target_window=target)
    if not healed:
        raise RuntimeError("runtime guard failed to heal same-process popup")
    if controller.escape_count < 1:
        raise RuntimeError("runtime guard did not send ESC before healing popup")
    if not guard._window_manager.focused:
        raise RuntimeError("runtime guard did not refocus target window")
    return {"issue": event.issue, "escape_count": controller.escape_count, "close_count": controller.close_count}


def test_runtime_guard_ignores_keywordless_same_process_aux_window() -> dict[str, Any]:
    target = _fake_target_window()
    aux_window = WindowSnapshot(
        hwnd=202,
        process_id=target.process_id,
        title="VSClient",
        process_name=target.process_name,
        rect=Rect(100, 100, 1800, 1100),
        owner_hwnd=0,
        is_visible=True,
        is_foreground=False,
    )
    guard = RuntimeGuard(
        RuntimeGuardConfig(),
        _FakeWindowManager(foreground=None, related=[aux_window]),
        _FakeDetector(status="ok"),
        _FakeController(),
        _FakeLogger(),
        PROJECT_ROOT / "config.yaml",
    )
    event = guard.check(
        stage="PREPARE_TARGET",
        target_window=target,
        preview_rect=None,
        active_cell_rect=None,
        expected_view=None,
    )
    if not event.ok:
        raise RuntimeError(f"keywordless same-process auxiliary window was misclassified as popup: {event}")
    return {"status": event.issue, "title": aux_window.title}


def test_runtime_guard_foreground_aux_window_refocuses_without_escape() -> dict[str, Any]:
    target = _fake_target_window()
    aux_window = WindowSnapshot(
        hwnd=303,
        process_id=999,
        title="VSClient",
        process_name="VSClient.exe",
        rect=Rect(10, 10, 1900, 1200),
        owner_hwnd=target.hwnd,
        is_visible=True,
        is_foreground=True,
    )
    guard = RuntimeGuard(
        RuntimeGuardConfig(),
        _FakeWindowManager(foreground=aux_window, related=[]),
        _FakeDetector(status="ok"),
        _FakeController(),
        _FakeLogger(),
        PROJECT_ROOT / "config.yaml",
    )
    event = guard.check(
        stage="PREPARE_TARGET",
        target_window=target,
        preview_rect=None,
        active_cell_rect=None,
        expected_view=None,
    )
    if not event.ok:
        raise RuntimeError(f"keywordless related auxiliary foreground should be accepted directly, got: {event}")
    controller = guard._controller
    if controller.escape_count != 0 or controller.close_count != 0:
        raise RuntimeError("runtime guard should not heal/close accepted auxiliary foreground windows")
    if guard._window_manager.focused:
        raise RuntimeError(f"runtime guard should not need to refocus accepted auxiliary foreground window: {guard._window_manager.focused}")
    return {"status": event.issue, "escape_count": controller.escape_count, "close_count": controller.close_count}


def test_runtime_guard_allows_attached_foreground_surface() -> dict[str, Any]:
    target = _fake_target_window()
    attached_surface = WindowSnapshot(
        hwnd=404,
        process_id=999,
        title="VSClient",
        process_name="VSClient.exe",
        rect=Rect(0, 0, 1600, 900),
        owner_hwnd=target.hwnd,
        is_visible=True,
        is_foreground=True,
    )
    guard = RuntimeGuard(
        RuntimeGuardConfig(),
        _FakeWindowManager(foreground=attached_surface, related=[]),
        _FakeDetector(status="ok"),
        _FakeController(),
        _FakeLogger(),
        PROJECT_ROOT / "config.yaml",
    )
    event = guard.check(
        stage="PREPARE_TARGET",
        target_window=target,
        preview_rect=None,
        active_cell_rect=None,
        expected_view=None,
    )
    if not event.ok:
        raise RuntimeError(f"attached foreground surface should be accepted, got: {event}")
    return {"status": event.issue, "hwnd": attached_surface.hwnd}


def test_runtime_guard_allows_detached_vsclient_surface() -> dict[str, Any]:
    target = _fake_target_window()
    detached_surface = WindowSnapshot(
        hwnd=505,
        process_id=999,
        title="VSClient",
        process_name="VSClient.exe",
        rect=Rect(0, 0, 1600, 900),
        owner_hwnd=0,
        is_visible=True,
        is_foreground=True,
    )
    guard = RuntimeGuard(
        RuntimeGuardConfig(),
        _FakeWindowManager(foreground=detached_surface, related=[]),
        _FakeDetector(status="ok"),
        _FakeController(),
        _FakeLogger(),
        PROJECT_ROOT / "config.yaml",
    )
    event = guard.check(
        stage="GRID_DWELL",
        target_window=target,
        preview_rect=None,
        active_cell_rect=None,
        expected_view=None,
    )
    if not event.ok:
        raise RuntimeError(f"detached VSClient surface should be accepted, got: {event}")
    return {"status": event.issue, "hwnd": detached_surface.hwnd}


def test_runtime_guard_allows_hex_titled_vsclient_foreground_surface() -> dict[str, Any]:
    target = _fake_target_window()
    hex_surface = WindowSnapshot(
        hwnd=506,
        process_id=999,
        title="0x9db00002",
        process_name="VSClient.exe",
        rect=Rect(250, 180, 1050, 780),
        owner_hwnd=target.hwnd,
        is_visible=True,
        is_foreground=True,
    )
    guard = RuntimeGuard(
        RuntimeGuardConfig(),
        _FakeWindowManager(foreground=hex_surface, related=[]),
        _FakeDetector(status="ok"),
        _FakeController(),
        _FakeLogger(),
        PROJECT_ROOT / "config.yaml",
    )
    event = guard.check(
        stage="after_select_target",
        target_window=target,
        preview_rect=None,
        active_cell_rect=None,
        expected_view=None,
    )
    if not event.ok:
        raise RuntimeError(f"hex-titled VSClient foreground surface should be accepted, got: {event}")
    return {"status": event.issue, "title": hex_surface.title}


def test_runtime_guard_allows_hex_titled_vsclient_foreground_surface_without_relation_hint() -> dict[str, Any]:
    target = _fake_target_window()
    hex_surface = WindowSnapshot(
        hwnd=507,
        process_id=999,
        title="0x9db00804",
        process_name="VSClient.exe",
        rect=Rect(250, 180, 1050, 780),
        owner_hwnd=0,
        is_visible=True,
        is_foreground=True,
    )
    guard = RuntimeGuard(
        RuntimeGuardConfig(),
        _FakeWindowManager(foreground=hex_surface, related=[]),
        _FakeDetector(status="ok"),
        _FakeController(),
        _FakeLogger(),
        PROJECT_ROOT / "config.yaml",
    )
    event = guard.check(
        stage="after_select_target",
        target_window=target,
        preview_rect=None,
        active_cell_rect=None,
        expected_view=None,
    )
    if not event.ok:
        raise RuntimeError(f"hex-titled detached VSClient foreground surface should be accepted, got: {event}")
    return {"status": event.issue, "title": hex_surface.title, "owner_hwnd": hex_surface.owner_hwnd}


def test_runtime_guard_ignores_status_overlay_foreground() -> dict[str, Any]:
    target = _fake_target_window()
    overlay = WindowSnapshot(
        hwnd=606,
        process_id=999,
        title="Video Polling Status",
        process_name="pythonw.exe",
        rect=Rect(100, 100, 900, 180),
        owner_hwnd=0,
        is_visible=True,
        is_foreground=True,
    )
    guard = RuntimeGuard(
        RuntimeGuardConfig(),
        _FakeWindowManager(foreground=overlay, related=[]),
        _FakeDetector(status="ok"),
        _FakeController(),
        _FakeLogger(),
        PROJECT_ROOT / "config.yaml",
    )
    event = guard.check(
        stage="PREPARE_TARGET",
        target_window=target,
        preview_rect=None,
        active_cell_rect=None,
        expected_view=None,
    )
    if not event.ok:
        raise RuntimeError(f"status overlay foreground should be ignored, got: {event}")
    return {"status": event.issue, "title": overlay.title}


def test_runtime_guard_ignores_automation_python_console_foreground() -> dict[str, Any]:
    target = _fake_target_window()
    python_console = WindowSnapshot(
        hwnd=607,
        process_id=999,
        title=r"D:\video_platform_release\.venv\Scripts\python.exe",
        process_name="python.exe",
        rect=Rect(120, 120, 1200, 520),
        owner_hwnd=0,
        is_visible=True,
        is_foreground=True,
    )
    guard = RuntimeGuard(
        RuntimeGuardConfig(),
        _FakeWindowManager(foreground=python_console, related=[]),
        _FakeDetector(status="ok"),
        _FakeController(),
        _FakeLogger(),
        PROJECT_ROOT / "config.yaml",
    )
    event = guard.check(
        stage="after_select_target",
        target_window=target,
        preview_rect=None,
        active_cell_rect=None,
        expected_view=None,
    )
    if not event.ok:
        raise RuntimeError(f"automation python console foreground should be ignored, got: {event}")
    return {"status": event.issue, "title": python_console.title}


def test_runtime_guard_ignores_automation_terminal_foreground() -> dict[str, Any]:
    target = _fake_target_window()
    terminal = WindowSnapshot(
        hwnd=608,
        process_id=1001,
        title="Ubuntu",
        process_name="windowsterminal.exe",
        rect=Rect(120, 120, 1200, 520),
        owner_hwnd=0,
        is_visible=True,
        is_foreground=True,
    )
    guard = RuntimeGuard(
        RuntimeGuardConfig(),
        _FakeWindowManager(foreground=terminal, related=[]),
        _FakeDetector(status="ok"),
        _FakeController(),
        _FakeLogger(),
        PROJECT_ROOT / "config.yaml",
    )
    event = guard.check(
        stage="after_select_target",
        target_window=target,
        preview_rect=None,
        active_cell_rect=None,
        expected_view=None,
    )
    if not event.ok:
        raise RuntimeError(f"automation terminal foreground should be ignored, got: {event}")
    return {"status": event.issue, "title": terminal.title}


def test_runtime_console_is_hardened_against_selection_freeze() -> dict[str, Any]:
    app_text = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    required_fragments = [
        "def harden_runtime_console",
        "enable_quick_edit_mode = 0x0040",
        "enable_insert_mode = 0x0020",
        "enable_mouse_input = 0x0010",
        "new_mode &= ~enable_quick_edit_mode",
        "new_mode &= ~enable_insert_mode",
        "new_mode &= ~enable_mouse_input",
        'logger.info("Hardened runtime console input mode=%s -> %s", mode.value, new_mode)',
        'logger.info("Minimized runtime console hwnd=%s to avoid accidental foreground clicks", console_hwnd)',
        "if args.run:",
        "harden_runtime_console(minimize=True, logger=logger)",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in app_text]
    if missing:
        raise RuntimeError(f"runtime console hardening fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_window_manager_prefers_exact_title_and_process_match() -> dict[str, Any]:
    window_manager_text = (PROJECT_ROOT / "window_manager.py").read_text(encoding="utf-8")
    required_fragments = [
        "exact_matches = [item for item in matches if item.process_match and item.title_match]",
        "if exact_matches:",
        "titled_matches = [item for item in matches if item.title]",
        "item.process_match and item.title_match",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in window_manager_text]
    if missing:
        raise RuntimeError(f"window_manager exact-match preference fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_guard_interface_auto_heal() -> dict[str, Any]:
    target = _fake_target_window()
    guard = RuntimeGuard(
        RuntimeGuardConfig(),
        _FakeWindowManager(foreground=None, related=[]),
        _FakeDetector(status="unexpected_interface"),
        _FakeController(),
        _FakeLogger(),
        PROJECT_ROOT / "config.yaml",
    )
    event = guard.check(
        stage="ZOOM_DWELL",
        target_window=target,
        preview_rect=Rect(0, 0, 1200, 800),
        active_cell_rect=Rect(0, 0, 300, 200),
        expected_view=None,
    )
    if event.issue != "unexpected_interface":
        raise RuntimeError(f"unexpected runtime interface event: {event}")
    controller = guard._controller
    healed = guard.try_auto_heal(event=event, target_window=target)
    if not healed:
        raise RuntimeError("runtime guard failed to heal unexpected interface")
    if controller.recover_count < 1:
        raise RuntimeError("runtime guard did not recover_to_grid for unexpected interface")
    return {"issue": event.issue, "recover_count": controller.recover_count}


def test_runtime_guard_respects_detected_issue_skip_mode() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "if self._config.detection.skip_on_detected_issue:",
        "RUNTIME_GUARD could not safely heal issue=%s; skip_on_detected_issue=%s, restarting current path without auto-pause",
        'message=f"检测异常，继续自动恢复：{event.issue}"',
        'details=f"skip_on_detected_issue 已启用；程序不会自动暂停，会继续重走当前路径。"',
        "self._guard_failure_streak = 0",
        'self._clear_cycle_context(preserve_zoom_state=False, reason=f"runtime_guard_skip:{event.issue}")',
        'self._next_transition_reason = f"runtime_guard_skip:{event.issue}"',
        "self._state = SchedulerState.PREPARE_TARGET",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"runtime guard skip-mode fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_flat_grid_expected_view_is_not_misclassified() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    # 关键回归：当前客户端的“预览失败占位图”可能很平，但只要仍匹配预期宫格，就不能误判成错误界面。
    detector.classify_runtime_view = lambda *args, **kwargs: (
        VisualViewState.UNKNOWN,
        {
            "flat_interface_like": 1.0,
            "preview_entropy": 0.8,
            "preview_edge_ratio": 0.01,
            "preview_dominant_ratio": 0.9,
        },
    )
    detector.matches_expected_view = lambda expected, metrics: True

    result = detector.inspect_runtime_interface(
        Rect(0, 0, 1200, 800),
        Rect(0, 0, 300, 200),
        expected_view=VisualViewState.GRID,
        grid_probe=None,
        zoom_probe=None,
    )
    if result.status != "ok":
        raise RuntimeError(f"flat-but-matching grid was misclassified: {result}")
    return {"status": result.status, "reason": result.reason}


def test_repeated_failure_grid_layout_can_still_be_classified_as_grid() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    image = Image.new("RGB", (600, 400), color=(28, 28, 28))
    draw = ImageDraw.Draw(image)
    for x in (200, 400):
        draw.rectangle((x - 2, 0, x + 2, 399), fill=(76, 76, 76))
    for y in (200,):
        draw.rectangle((0, y - 2, 599, y + 2), fill=(76, 76, 76))
    for row in range(2):
        for col in range(3):
            left = col * 200
            top = row * 200
            draw.rectangle((left + 76, top + 42, left + 124, top + 82), outline=(90, 90, 90), width=3)
            draw.line((left + 90, top + 54, left + 110, top + 54), fill=(90, 90, 90), width=2)
            draw.line((left + 100, top + 54, left + 100, top + 72), fill=(90, 90, 90), width=2)
            draw.text((left + 88, top + 120), "详情", fill=(40, 146, 255))

    actual_view, metrics = detector.classify_runtime_view(
        Rect(0, 0, 600, 400),
        Rect(0, 0, 200, 200),
        preview_image=image,
    )
    if actual_view != VisualViewState.GRID:
        raise RuntimeError(f"repeated failure grid was not classified as grid: {actual_view} metrics={metrics}")
    if metrics.get("repeated_grid_like") != 1.0:
        raise RuntimeError(f"repeated grid heuristic did not mark repeated_grid_like=1: {metrics}")
    return {
        "actual_view": actual_view.value,
        "grid_divider_hits": metrics.get("grid_divider_hit_count"),
        "grid_divider_mean_strength": metrics.get("grid_divider_mean_strength"),
    }


def test_zoom_probe_precedence_over_grid_probe() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    zoom_probe = Image.new("L", (64, 64), color=32)
    grid_probe = Image.new("L", (64, 64), color=64)
    current_preview = Image.new("L", (64, 64), color=96)

    detector.capture_probe = lambda *args, **kwargs: current_preview
    detector._preview_surface_metrics = lambda preview_rect: {  # type: ignore[attr-defined]
        "preview_entropy": 3.2,
        "preview_std": 22.0,
        "preview_edge_ratio": 0.09,
        "preview_dominant_ratio": 0.38,
    }
    detector._looks_like_flat_interface = lambda metrics: False  # type: ignore[attr-defined]

    def fake_change(before_image, after_image):
        if before_image is zoom_probe:
            return {"mean_diff": 1.2, "changed_ratio": 0.01}
        if before_image is grid_probe:
            return {"mean_diff": 5.0, "changed_ratio": 0.05}
        return {"mean_diff": 26.0, "changed_ratio": 0.28}

    detector.measure_visual_change = fake_change  # type: ignore[assignment]

    actual, metrics = detector.classify_runtime_view(
        Rect(0, 0, 1200, 800),
        Rect(0, 0, 300, 200),
        grid_probe=grid_probe,
        zoom_probe=zoom_probe,
        preview_image=current_preview.convert("RGB"),
    )
    if actual != VisualViewState.ZOOMED:
        raise RuntimeError(f"zoom probe precedence lost: actual={actual} metrics={metrics}")
    return {
        "actual": actual.value,
        "zoom_probe_score": metrics.get("zoom_probe_score"),
        "grid_probe_score": metrics.get("grid_probe_score"),
    }


def test_fullscreen_layout_change_can_confirm_zoom() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())

    full_change_metrics = {"mean_diff": 5.1148, "changed_ratio": 0.1263}
    main_view_change_metrics = {"mean_diff": 3.7682, "changed_ratio": 0.1162}

    confirmed = detector._main_view_expansion_confirmed(  # type: ignore[attr-defined]
        full_change_metrics,
        main_view_change_metrics,
        False,
        True,
    )
    if not confirmed:
        raise RuntimeError(
            "fullscreen layout change fallback did not confirm a known-good weak zoom-change sample"
        )
    return {
        "confirmed": confirmed,
        "full_changed_ratio": full_change_metrics["changed_ratio"],
        "main_changed_ratio": main_view_change_metrics["changed_ratio"],
    }


def test_runtime_guard_files_and_config() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    build_text = (PROJECT_ROOT / "build_release.py").read_text(encoding="utf-8")
    runtime_guard_text = (PROJECT_ROOT / "runtime_guard.py").read_text(encoding="utf-8")
    required_runtime_fragments = [
        "unexpected_related_window",
        "unexpected_foreground_window",
        "unexpected_interface",
        "close_foreground_window",
    ]
    missing_runtime = [fragment for fragment in required_runtime_fragments if fragment not in runtime_guard_text]
    if missing_runtime:
        raise RuntimeError(f"runtime_guard.py missing fragments: {missing_runtime}")
    if '"runtime_guard.py"' not in build_text:
        raise RuntimeError("build_release.py is missing runtime_guard.py")
    if not config.runtime_guard.enabled:
        raise RuntimeError("runtime_guard must be enabled in config.yaml")
    return {
        "guard_enabled": config.runtime_guard.enabled,
        "post_action_wait_ms": config.runtime_guard.post_action_wait_ms,
        "flat_entropy_max": config.detection.runtime_flat_entropy_max,
    }


def test_scheduler_tracks_soft_precheck_issue_for_zoom_confirm() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        'self._cycle_soft_issue_hint = ""',
        'self._cycle_soft_issue_hint = result.status if result.status in {"preview_failure", "black_screen"} else ""',
        "soft_issue_hint=self._cycle_soft_issue_hint",
        'self._cycle_soft_issue_hint or "none"',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"scheduler soft-precheck issue tracking fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_repeated_partial_zoom_confirm_respects_skip_mode() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        'current_fail_streak = int(self._issue_registry.get(key, {}).get("fail_streak", current_fail_streak))',
        'cooldown_remaining = int(self._issue_registry.get(key, {}).get("cooldown_remaining", 0))',
        'if partial_signal_seen and (current_fail_streak >= 2 or cooldown_remaining > 0):',
        "continuing grid recovery because skip_on_detected_issue=%s",
        "if not self._config.detection.skip_on_detected_issue:",
        'self._pause_for_detected_issue("zoom_confirm_partial_repeat")',
        "skip_on_detected_issue 已启用；当前路进入失败/冷却时不再自动暂停",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"repeated partial zoom-confirm skip-mode fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_zoom_confirm_failure_keeps_partial_signal_until_handler() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    start = scheduler_text.index("def _perform_zoom_confirm_attempt")
    end = scheduler_text.index("def _handle_zoom_confirm_failure")
    perform_zoom_confirm_text = scheduler_text[start:end]
    forbidden_fragment = "self._clear_cycle_context(preserve_zoom_state=True)"
    if forbidden_fragment in perform_zoom_confirm_text:
        raise RuntimeError("zoom-confirm attempt still clears cycle context before failure handler runs")
    required_fragments = [
        "if confirm_result.state == ConfirmState.PARTIAL_CHANGE:",
        "self._zoom_partial_signal_seen = True",
        'return False',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in perform_zoom_confirm_text]
    if missing:
        raise RuntimeError(f"zoom-confirm partial-signal preservation fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_startup_cached_layout_reverify_is_delayed_past_early_cells() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        'hold_until_cell = min(4, max(0, len(self._cells) - 1))',
        'if hold_until_cell > 0 and self._current_index < hold_until_cell:',
        '"RUNTIME_LAYOUT deferred verify kept pending reason=%s layout=%s next_cell=%s hold_until_cell=%s"',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"startup cached layout reverify deferral fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_dwell_runtime_guard_prefers_lightweight_checks_until_mid_dwell() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "last_view_guard_check = -999.0",
        "view_guard_interval = max(2.8, dwell_seconds * 0.65)",
        "inspect_view = elapsed >= view_guard_interval and elapsed - last_view_guard_check >= view_guard_interval",
        'stage="ZOOM_DWELL"',
        'stage="GRID_DWELL"',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"dwell runtime-guard throttling fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_manual_target_cycles_skip_recovery_when_already_matched() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _handle_runtime_target_update(self, *, changed_label: str) -> None:",
        "if not self._profile_control_manual:",
        "self._drive_manual_target_to_client(changed_label=changed_label)",
        "当前为手动目标闭环；程序会继续核对现场与目标一致后再沿当前路径运行。",
        'details=(',
        "当前为手动目标闭环；程序已重新核对现场模式和宫格，",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"manual target cycle short-circuit fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_profile_pause_message_clears_after_manual_match() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        'if self._last_pause_reason == "runtime_profile_mismatch":',
        "if self._runtime_profile_matches_request():",
        'return f"已暂停：目标已匹配，可按 {self._config.hotkeys.start_pause} 继续"',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"runtime-profile pause message fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_paused_manual_target_cycle_republishes_mismatch_state() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _handle_profile_source_toggle_request(self) -> None:",
        "运行控制已切换：手动锁定",
        "运行控制已切换：自动识别",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"profile-source toggle fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_running_manual_target_mismatch_waits_until_next_prepare_target() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _publish_runtime_target_pending_feedback(self, *, changed_label: str) -> None:",
        "当前运行控制为自动识别。",
        "如果你要手动锁定，请先按",
        "self._handle_runtime_target_update(changed_label=changed_label)",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"runtime target feedback fragments missing: {missing}")
    forbidden_fragments = [
        '_freeze_for_runtime_profile_mismatch(reason="manual_mode_cycle")',
        '_freeze_for_runtime_profile_mismatch(reason="manual_layout_cycle")',
    ]
    present = [fragment for fragment in forbidden_fragments if fragment in scheduler_text]
    if present:
        raise RuntimeError(f"manual target mismatch still freezes immediately: {present}")
    return {"checked_fragments": len(required_fragments)}


def test_resume_request_is_blocked_until_runtime_profile_matches() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        'if self._last_pause_reason == "runtime_profile_mismatch":',
        "Hotkey RESUME blocked because runtime profile is still mismatched",
        'message="目标仍未匹配，继续保持冻结"',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"resume-block-on-runtime-mismatch fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_scheduler_uses_fast_window_refresh_for_runtime_view_checks() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    window_manager_text = (PROJECT_ROOT / "window_manager.py").read_text(encoding="utf-8")
    required_scheduler = [
        "self._refresh_window_context(fast=refresh_context and self._window_info is not None)",
        "def _refresh_window_context(self, *, fast: bool = False) -> None:",
        "self._window_manager.refresh_target_window(self._window_info)",
    ]
    missing_scheduler = [fragment for fragment in required_scheduler if fragment not in scheduler_text]
    if missing_scheduler:
        raise RuntimeError(f"scheduler fast-refresh fragments missing: {missing_scheduler}")
    required_window_manager = [
        "def refresh_target_window(self, current: WindowInfo) -> WindowInfo:",
        "Target window hwnd=",
    ]
    missing_window_manager = [fragment for fragment in required_window_manager if fragment not in window_manager_text]
    if missing_window_manager:
        raise RuntimeError(f"window_manager fast-refresh fragments missing: {missing_window_manager}")
    return {"scheduler_fragments": len(required_scheduler), "window_manager_fragments": len(required_window_manager)}


def test_pause_ack_no_longer_forces_full_context_refresh() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    start = scheduler_text.index("def _acknowledge_pause")
    end = scheduler_text.index("def _run_runtime_guard")
    block = scheduler_text[start:end]
    if "_classify_current_view(refresh_context=True)" in block:
        raise RuntimeError("pause acknowledgement still forces a full context refresh")
    if "_classify_current_view(refresh_context=False)" not in block:
        raise RuntimeError("pause acknowledgement no longer records the current view cheaply")
    return {"checked": True}


def test_guard_stage_view_trusts_runtime_guard_result() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    start = scheduler_text.index("def _guard_stage_view")
    end = scheduler_text.index("def _auto_heal_path_mismatch")
    block = scheduler_text[start:end]
    required_fragments = [
        "if self._runtime_guard is not None and self._config.runtime_guard.enabled:",
        "return self._run_runtime_guard(stage=stage, expected_view=expected, inspect_view=True)",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in block]
    if missing:
        raise RuntimeError(f"guard-stage short-circuit fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_detector_reuses_preview_capture_for_runtime_classification() -> dict[str, Any]:
    detector_text = (PROJECT_ROOT / "detector.py").read_text(encoding="utf-8")
    required_fragments = [
        "preview_image: Image.Image | None = None",
        "preview_capture = preview_image if preview_image is not None else self.capture_image(preview_rect)",
        "surface_metrics = self._preview_surface_metrics_from_image(preview_capture)",
        "def _capture_active_probe_from_preview(",
        "preview_image=after_preview_rgb",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in detector_text]
    if missing:
        raise RuntimeError(f"detector preview-reuse fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_detector_downsamples_surface_metrics_before_heavy_stats() -> dict[str, Any]:
    detector_text = (PROJECT_ROOT / "detector.py").read_text(encoding="utf-8")
    required_fragments = [
        "SURFACE_METRIC_LONG_EDGE = 320",
        "if longest_edge > SURFACE_METRIC_LONG_EDGE:",
        "sample_image = image.resize(sample_size, resize_filter)",
        "rgb = np.asarray(sample_image, dtype=np.uint8)",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in detector_text]
    if missing:
        raise RuntimeError(f"detector surface-metric downsample fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_status_overlay_auto_hide_config() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    status_runtime_text = (PROJECT_ROOT / "status_runtime.py").read_text(encoding="utf-8")
    status_overlay_text = (PROJECT_ROOT / "status_overlay.py").read_text(encoding="utf-8")
    runtime_driver_text = _optional_runtime_driver_text()
    if config.status_overlay.auto_hide_ms <= 0:
        raise RuntimeError("status overlay auto-hide must be positive")
    if config.status_overlay.stale_hide_ms <= 0:
        raise RuntimeError("status overlay stale-hide must be positive")
    if config.status_overlay.auto_hide_ms < 1800:
        raise RuntimeError("status overlay auto-hide is too short for operator-visible prompts")
    if config.status_overlay.stale_hide_ms < 3600:
        raise RuntimeError("status overlay stale-hide is too short to clean stale prompt cards safely")
    required_runtime = [
        '"auto_hide_ms": self._config.auto_hide_ms',
        '"stale_hide_ms": self._config.stale_hide_ms',
    ]
    missing_runtime = [fragment for fragment in required_runtime if fragment not in status_runtime_text]
    if missing_runtime:
        raise RuntimeError(f"status_runtime missing auto-hide fragments: {missing_runtime}")
    required_overlay = [
        "self._hide_after_id = None",
        "payload.get(\"auto_hide_ms\", 2200)",
        "if auto_hide_ms > 0:",
        "self._hide_card",
        "payload.get(\"stale_hide_ms\", DEFAULT_STALE_HIDE_MS)",
        "if stale_hide_ms <= 0:",
        "self._hide_if_stale(payload)",
        "destroy stale close card",
        "self.detail_label",
        'payload.get("details", "")',
        "F1 自动/手动  F2 启停",
    ]
    missing_overlay = [fragment for fragment in required_overlay if fragment not in status_overlay_text]
    if missing_overlay:
        raise RuntimeError(f"status_overlay missing auto-hide fragments: {missing_overlay}")
    if runtime_driver_text is not None:
        required_driver = [
            'data["status_overlay"]["close_delay_ms"] = 2600',
            'data["status_overlay"]["auto_hide_ms"] = 2200',
            'data["status_overlay"]["stale_hide_ms"] = 4800',
        ]
        missing_driver = [fragment for fragment in required_driver if fragment not in runtime_driver_text]
        if missing_driver:
            raise RuntimeError(f"runtime_test_driver missing overlay timing fragments: {missing_driver}")
    return {
        "auto_hide_ms": config.status_overlay.auto_hide_ms,
        "stale_hide_ms": config.status_overlay.stale_hide_ms,
        "safe_strip_height_px": config.status_overlay.safe_strip_height_px,
        "runtime_driver_present": runtime_driver_text is not None,
    }


def test_runtime_test_driver_prefers_send_keys_for_function_hotkeys() -> dict[str, Any]:
    runtime_driver_text = _optional_runtime_driver_text()
    if runtime_driver_text is None:
        return {"skipped": True, "reason": "runtime_test_driver.py is optional in the WSL/static environment"}
    required_fragments = [
        "keyboard.press_and_release(normalized)",
        "if _send_keys is not None and normalized in key_map:",
        "_send_keys(key_map[normalized], pause=0.05)",
        "跨进程实测表明 keyboard.on_press_key 能稳定收到",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in runtime_driver_text]
    if missing:
        raise RuntimeError(f"runtime_test_driver hotkey injection fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_preview_failure_precheck_no_longer_skips_action_path() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        'if result.status in {"preview_failure", "black_screen"}:',
        "预览失败 / 黑屏",
        "continuing action path",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"preview-failure soft-precheck fragments missing: {missing}")
    forbidden_fragments = [
        'elif result.status == "black_screen":',
        'f"黑屏：{self._cell_hint(self._active_cell)}，已跳过"',
    ]
    present = [fragment for fragment in forbidden_fragments if fragment in scheduler_text]
    if present:
        raise RuntimeError(f"black-screen precheck still skips action path: {present}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_test_driver_keeps_real_dwell_timings() -> dict[str, Any]:
    runtime_driver_text = _optional_runtime_driver_text()
    if runtime_driver_text is None:
        return {"skipped": True, "reason": "runtime_test_driver.py is optional in the WSL/static environment"}
    forbidden_fragments = [
        'data["timing"]["dwell_seconds"] =',
        'data["timing"]["post_restore_dwell_seconds"] =',
        'data["timing"]["between_cells_ms"] =',
        'data["timing"]["recovery_wait_ms"] =',
    ]
    present = [fragment for fragment in forbidden_fragments if fragment in runtime_driver_text]
    if present:
        raise RuntimeError(f"runtime_test_driver still overrides real action-path timings: {present}")
    required_fragments = [
        "self._cleanup_stale_scenario_processes()",
        "self._cleanup_stale_scenario_files()",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in runtime_driver_text]
    if missing:
        raise RuntimeError(f"runtime_test_driver cleanup fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_test_driver_tolerates_windows_log_lock() -> dict[str, Any]:
    runtime_driver_text = _optional_runtime_driver_text()
    if runtime_driver_text is None:
        return {"skipped": True, "reason": "runtime_test_driver.py is optional in the WSL/static environment"}
    required_fragments = [
        "for attempt in range(5):",
        "except PermissionError:",
        "Windows 上 app.py 的日志文件在刷盘瞬间可能被短暂锁住",
        "上一轮 app 刚退时，Windows 可能还没释放日志句柄",
        "if attempt == 4:",
        "return []",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in runtime_driver_text]
    if missing:
        raise RuntimeError(f"runtime_test_driver log-lock tolerance fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_test_driver_restores_windowed_grid_between_scenarios() -> dict[str, Any]:
    runtime_driver_text = _optional_runtime_driver_text()
    if runtime_driver_text is None:
        return {"skipped": True, "reason": "runtime_test_driver.py is optional in the WSL/static environment"}
    required_fragments = [
        "def _detect_cleanup_mode(self, config, window_manager: WindowManager, target_window) -> str:",
        'if self.requested_mode in {"windowed", "fullscreen"}:',
        'return window_manager.detect_mode(target_window, "auto")',
        "def _best_effort_restore_windowed_grid(self) -> None:",
        'if self._detect_cleanup_mode(config, window_manager, target_window) != "windowed":',
        "def _best_effort_restore_fullscreen_grid(self) -> None:",
        'if self._detect_cleanup_mode(config, window_manager, target_window) != "fullscreen":',
        "def _best_effort_restore_grid(self) -> None:",
        "def _minimize_known_blockers(self) -> None:",
        "def _restore_known_blockers(self) -> None:",
        'blocker_processes = {"codex.exe", "searchhost.exe"}',
        "controller.recover_to_grid(hwnd=target_window.hwnd)",
        "self._best_effort_restore_grid()",
        "self._best_effort_restore_windowed_grid()",
        "self._best_effort_restore_fullscreen_grid()",
        "self._minimize_known_blockers()",
        "self._restore_known_blockers()",
        "把场景收回到用户手动准备的宫格态",
        "这里同样只在“明确不在宫格”时才发 ESC 回宫格",
        "runtime test driver 也要支持 auto 模式清场",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in runtime_driver_text]
    if missing:
        raise RuntimeError(f"runtime_test_driver windowed-grid reset fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_test_driver_does_not_escape_when_windowed_grid_is_already_visible() -> dict[str, Any]:
    runtime_driver_text = _optional_runtime_driver_text()
    if runtime_driver_text is None:
        return {"skipped": True, "reason": "runtime_test_driver.py is optional in the WSL/static environment"}
    required_fragments = [
        "def _looks_like_grid(self, config, grid_mapper: GridMapper, detector: Detector, preview_rect) -> bool:",
        "detector = Detector(config.detection, logger)",
        "grid_mapper = GridMapper(config.grid)",
        "if self._looks_like_grid(config, grid_mapper, detector, preview_rect):",
        "只有明确不是宫格时，才发 ESC 回宫格",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in runtime_driver_text]
    if missing:
        raise RuntimeError(f"runtime_test_driver windowed-grid visibility guard fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_test_driver_can_override_layout_for_real_grid_regression() -> dict[str, Any]:
    runtime_driver_text = _optional_runtime_driver_text()
    if runtime_driver_text is None:
        return {"skipped": True, "reason": "runtime_test_driver.py is optional in the WSL/static environment"}
    required_fragments = [
        "layout_override: int | None = None",
        'data["grid"]["layout"] = int(self.layout_override)',
        "valid_layouts = {4, 6, 9, 12, 13}",
        'result = run_full_path(requested_mode=requested_mode, layout_override=layout_override)',
        "usage: runtime_test_driver.py [full_path|f11_recovery|f9_pause_queue] [auto|windowed|fullscreen] [4|6|9|12|13]",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in runtime_driver_text]
    if missing:
        raise RuntimeError(f"runtime_test_driver layout-override fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_f9_runtime_driver_recovers_startup_prepare_not_grid_before_queue_check() -> dict[str, Any]:
    runtime_driver_text = _optional_runtime_driver_text()
    if runtime_driver_text is None:
        return {"skipped": True, "reason": "runtime_test_driver.py is optional in the WSL/static environment"}
    required_fragments = [
        "def startup_issue_paused(_payload: dict | None, _lines: list[str], _history: list[dict[str, str]]) -> bool:",
        '"PAUSE_ACK state=SchedulerState.PAUSED"',
        '"prepare_not_grid"',
        '_send_hotkey("f11")',
        'description=f"startup F11 recovery attempt={attempt + 1}"',
        "F9 专项不该把这种“起测现场还没回到正确路径”的情况直接算成 F9 失败",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in runtime_driver_text]
    if missing:
        raise RuntimeError(f"runtime_test_driver F9 startup-recovery fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_test_driver_can_follow_elevated_relaunch() -> dict[str, Any]:
    runtime_driver_text = _optional_runtime_driver_text()
    if runtime_driver_text is None:
        return {"skipped": True, "reason": "runtime_test_driver.py is optional in the WSL/static environment"}
    required_fragments = [
        "from admin_utils import current_integrity_level",
        "self._allow_auto_elevate = False",
        "self._elevated_pid: int | None = None",
        "def _requires_auto_elevate(self) -> bool:",
        "def _adopt_elevated_relaunch(self, *, timeout_seconds: float = 18.0) -> bool:",
        "def _scenario_app_is_running(self) -> bool:",
        '*(["--no-auto-elevate"] if not self._allow_auto_elevate else [])',
        "the elevated relaunch did not start after the UAC handoff",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in runtime_driver_text]
    if missing:
        raise RuntimeError(f"runtime_test_driver elevated-relaunch fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_prepare_target_recovery_refreshes_grid_probe_only_after_true_grid_confirmation() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    classify_pos = scheduler_text.find("actual_view, metrics = self._classify_current_view(refresh_context=False)")
    capture_pos = scheduler_text.find("self._last_grid_probe = self._detector.capture_probe(self._preview_rect, size=(64, 64))", classify_pos)
    comment_pos = scheduler_text.find("只有在“确实已经回到宫格”之后，才能刷新 grid_probe", classify_pos)
    if classify_pos < 0 or capture_pos < 0 or comment_pos < 0:
        raise RuntimeError("prepare-target recovery grid probe ordering fragments missing")
    if capture_pos < classify_pos:
        raise RuntimeError("prepare-target recovery still refreshes grid_probe before classifying the recovered view")
    required_fragments = [
        'reason="prepare_target_post_recover_grid_ready"',
        'reason="prepare_target_post_recover_post_sync_grid_ready"',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"prepare-target recovery helper reuse fragments missing: {missing}")
    return {
        "classify_pos": classify_pos,
        "capture_pos": capture_pos,
    }


def test_resume_locked_profile_reuses_prepare_target_grid_hint() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        'grid_like = actual_view == VisualViewState.GRID',
        'grid_like = self._prepare_target_grid_like(actual_view, metrics, reason="resume_grid_ready")',
        'grid_like = self._prepare_target_grid_like(actual_view, metrics, reason="resume_post_recover_grid_ready")',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"resume locked-profile grid-hint reuse fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_resume_pause_soft_peak_grid_thresholds_cover_manual_step_resume() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        'prepare_target_context_reason == "resume_hard_reset"',
        'self._last_pause_reason == "user_pause"',
        'preview_dominant_ratio >= 0.947',
        'preview_edge_ratio >= 0.024',
        'structure_changed_ratio >= 0.05',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"resume manual-step peak-grid threshold fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_resume_manual_step_grid_like_sample_is_supported_after_recovery() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 2.0,
        "grid_divider_expected_count": 2.0,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 1.0,
        "grid_divider_row_local_peak_mean": 15.6321,
        "grid_divider_col_local_peak_mean": 6.8933,
        "preview_entropy": 0.6408,
        "preview_std": 5.2346,
        "preview_edge_ratio": 0.0249,
        "preview_dominant_ratio": 0.9476,
        "flat_interface_like": 1.0,
        "structure_changed_ratio": 0.0593,
    }
    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 2,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 2,
        "row_peak_match": float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0,
        "col_peak_match": float(metrics.get("grid_divider_col_peak_match_count", 0.0)) >= 1.0,
        "row_peak_mean": float(metrics.get("grid_divider_row_local_peak_mean", 0.0)) >= 12.0,
        "col_peak_mean": float(metrics.get("grid_divider_col_local_peak_mean", 0.0)) >= 6.0,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.947,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 0.7,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 6.5,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.024,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.05,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"resume manual-step fullscreen4 sample no longer satisfies the gated prepare-target hint: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_prepare_target_grid_fast_path_still_syncs_runtime_layout() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    start = scheduler_text.index("def _ensure_prepare_target_grid")
    end = scheduler_text.index("def _acknowledge_pause")
    block = scheduler_text[start:end]
    fast_path_marker = 'if self._prepare_target_grid_like(actual_view, metrics, reason="prepare_target_grid_ready"):'
    sync_marker = 'self._try_sync_runtime_layout(reason=reason)'
    post_recover_marker = 'self._try_sync_runtime_layout(reason="prepare_target_post_recover_grid")'
    fast_path_pos = block.find(fast_path_marker)
    helper_start = block.find("def _prepare_target_grid_like(", fast_path_pos)
    helper_end = block.find("def _prepare_target_fullscreen_four_grid_hint(", helper_start)
    helper_block = block[helper_start:helper_end if helper_end > helper_start else None]
    sync_pos = helper_block.find(sync_marker)
    if fast_path_pos < 0 or helper_start < 0 or sync_pos < 0:
        raise RuntimeError("prepare-target grid fast-path runtime-layout sync fragments missing")
    if post_recover_marker not in block:
        raise RuntimeError("prepare-target post-recover grid branch no longer re-syncs runtime layout")
    return {
        "fast_path_pos": fast_path_pos,
        "helper_start": helper_start,
        "sync_pos": sync_pos,
    }


def test_recent_runtime_layout_sync_prevents_grid_ready_churn() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "self._runtime_layout_recent_sync_at = 0.0",
        "self._runtime_layout_recent_sync_cooldown_seconds = 30.0",
        'reason == "prepare_target_grid_ready"',
        "self._runtime_layout_recent_sync_at = time.monotonic()",
        '"RUNTIME_LAYOUT confirm reason=%s layout=%s via=recent_sync cell=%s"',
        '"RUNTIME_LAYOUT confirm reason=%s layout=%s via=visual_confirm cell=%s"',
        '"RUNTIME_LAYOUT confirm reason=%s layout=%s via=visual_keep_current best_layout=%s current_score=%.4f best_score=%.4f cell=%s"',
        "best_score <= (current_layout_score + 50.0)",
        "视觉回退分支也必须统一走 _apply_runtime_layout",
        "return self._apply_runtime_layout(int(resolved_layout), reason=reason, metrics=resolved_metrics)",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"recent runtime-layout sync guard fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_layout_visual_scoring_penalizes_dense_false_positive_layouts() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _runtime_layout_low_texture_hint(self, metrics: dict[str, float], *, rows: int, cols: int) -> bool:",
        'and int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == cols',
        'and float(metrics.get("structure_changed_ratio", 0.0)) >= 0.075',
        "def _runtime_layout_score(self, metrics: dict[str, float]) -> float:",
        'hit_count = float(metrics.get("grid_divider_hit_count", 0.0))',
        'expected_count = max(1.0, float(metrics.get("grid_divider_expected_count", 0.0)))',
        "hit_ratio = hit_count / expected_count",
        'mean_strength = float(metrics.get("grid_divider_mean_strength", 0.0))',
        'preview_edge_ratio = float(metrics.get("preview_edge_ratio", 0.0))',
        'repeated_grid_like = float(metrics.get("repeated_grid_like", 0.0)) == 1.0',
        "divider_support = mean_strength",
        "repeated_grid_bonus = 0.0",
        'if float(metrics.get("flat_interface_like", 0.0)) == 1.0 and hit_count == 0.0:',
        'self._current_mode == "fullscreen"',
        "and expected_count >= 3.0",
        'and float(metrics.get("preview_edge_ratio", 0.0)) >= 0.06',
        'and float(metrics.get("structure_changed_ratio", 0.0)) >= 0.12',
        "divider_support = mean_strength * expected_count",
        "and preview_edge_ratio >= 0.045",
        "if repeated_grid_like and expected_count <= 3.0:",
        "repeated_grid_bonus = 12.0",
        "+ hit_ratio * 120.0",
        "+ hit_count * 10.0",
        "+ divider_support * 1.8",
        "+ repeated_grid_bonus",
        '+ float(metrics.get("structure_changed_ratio", 0.0)) * 45.0',
        "- expected_count * 2.5",
        "分隔线更多的稠密布局会被错误加分",
        "让 2x3 这类真实存在更多分割线的布局有机会胜出",
        "避免 12 被错误翻成 4",
        'if not candidate_grid_like and self._runtime_layout_low_texture_hint(metrics, rows=2, cols=3):',
        "它更像 6 宫格，而不是被 4 宫格 flat fallback 误认出来的假阳性",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"runtime-layout dense-layout scoring fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_fullscreen_twelve_peak_support_is_wired() -> dict[str, Any]:
    detector_text = (PROJECT_ROOT / "detector.py").read_text(encoding="utf-8")
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    detector_fragments = [
        'metrics["grid_divider_row_peak_match_count"] = float(peak_match_count(row_peaks, expected_row_positions))',
        'metrics["grid_divider_col_peak_match_count"] = float(peak_match_count(col_peaks, expected_col_positions))',
        'metrics["grid_divider_row_local_peak_mean"] = round(local_peak_mean(row_profile, expected_row_positions), 4)',
        'metrics["grid_divider_col_local_peak_mean"] = round(local_peak_mean(col_profile, expected_col_positions), 4)',
    ]
    scheduler_fragments = [
        'row_peak_match_count = float(metrics.get("grid_divider_row_peak_match_count", 0.0))',
        'col_peak_match_count = float(metrics.get("grid_divider_col_peak_match_count", 0.0))',
        'row_local_peak_mean = float(metrics.get("grid_divider_row_local_peak_mean", 0.0))',
        'col_local_peak_mean = float(metrics.get("grid_divider_col_local_peak_mean", 0.0))',
        "and expected_count >= 5.0",
        "and row_peak_match_count >= 3.0",
        "and col_peak_match_count >= 2.0",
        "and row_local_peak_mean >= 40.0",
        "and col_local_peak_mean >= 40.0",
        "peak_support = row_local_peak_mean",
        "这是 12 宫格独有的强信号",
    ]
    missing_detector = [fragment for fragment in detector_fragments if fragment not in detector_text]
    missing_scheduler = [fragment for fragment in scheduler_fragments if fragment not in scheduler_text]
    if missing_detector or missing_scheduler:
        raise RuntimeError(
            f"fullscreen 12 peak-support fragments missing detector={missing_detector} scheduler={missing_scheduler}"
        )
    return {
        "detector_fragments": len(detector_fragments),
        "scheduler_fragments": len(scheduler_fragments),
    }


def test_fullscreen_nine_peak_hint_can_unlock_runtime_layout() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _runtime_layout_fullscreen_peak_hint(self, layout: int, metrics: dict[str, float]) -> bool:",
        "layout == 9",
        "rows == 3",
        "cols == 3",
        "expected_count == 4",
        "row_peak_match_count >= 2.0",
        "col_peak_match_count >= 2.0",
        "row_local_peak_mean >= 60.0",
        "col_local_peak_mean >= 60.0",
        "preview_edge_ratio >= 0.045",
        "structure_changed_ratio >= 0.11",
        "layout == 12",
        'if not candidate_grid_like and self._runtime_layout_fullscreen_peak_hint(int(layout), metrics):',
        "peak_grid_hint_used = True",
        "当前宫格同步需要一套比动作阶段更贴近“几宫格结构”的口径",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"fullscreen 9 peak-hint runtime-layout fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_fullscreen_dense_layout_keep_guard_is_wired() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _runtime_layout_expected_geometry(self, layout: int) -> tuple[int, int] | None:",
        "def _runtime_layout_geometry_matches(self, layout: int, metrics: dict[str, float]) -> bool:",
        "def _runtime_layout_has_strong_fullscreen_signal(self, layout: int, metrics: dict[str, float]) -> bool:",
        "return hit_count >= 2.0 or self._runtime_layout_fullscreen_peak_hint(9, metrics)",
        "return hit_count >= 2.0 or self._runtime_layout_fullscreen_peak_hint(12, metrics)",
        "def _should_hold_fullscreen_dense_layout(",
        "current_layout < 9 or proposed_layout >= current_layout",
        "not self._runtime_layout_geometry_matches(current_layout, current_metrics)",
        "proposed_hits >= max(2.0, current_hits + 1.0)",
        "proposed_has_strong_nine_evidence = (",
        "self._runtime_layout_has_strong_fullscreen_signal(9, proposed_metrics)",
        "current_layout == 12",
        "proposed_layout == 9",
        "proposed_peaks >= max(3.0, current_peaks + 2.0)",
        "proposed_support >= max(current_support * 1.25, 40.0)",
        "current_edge_ratio >= 0.08",
        "current_structure_ratio >= max(0.35, proposed_structure_ratio * 0.9)",
        "(current_peaks + 1.0) >= proposed_peaks",
        "current_support >= max(proposed_support * 0.88, 24.0)",
        "current_edge_ratio >= max(0.05, proposed_edge_ratio * 0.9)",
        "current_structure_ratio >= max(0.12, proposed_structure_ratio * 0.85)",
        "current_peaks >= proposed_peaks",
        "strong_proposed_vote_count = 1 if self._runtime_layout_has_strong_fullscreen_signal(proposed_layout, dict(initial_best[\"metrics\"])) else 0",
        "resolved_layout < 12",
        "self._runtime_layout_has_strong_fullscreen_signal(resolved_layout, resolved_metrics)",
        "fullscreen_startup_dense_keep",
        "self._runtime_layout_geometry_matches(12, current_candidate_metrics)",
        "fullscreen_weak_nine_keep",
        "fullscreen_dense_geometry_keep",
        "避免把真实全屏 12 错翻成 9",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"fullscreen dense-layout keep guard fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_prepare_target_recovers_target_foreground_before_visual_classification() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _ensure_visual_target_foreground(self, *, reason: str) -> bool:",
        'find_visual_surface = getattr(self._window_manager, "find_visual_render_surface", None)',
        "self._window_manager.get_foreground_window_snapshot()",
        '"FOREGROUND_RECOVER reason=%s foreground_hwnd=%s foreground_title=%s target_hwnd=%s attached_hwnd=%s"',
        "focus_hwnds = [self._window_info.hwnd]",
        "focus_hwnds.append(visual_surface.hwnd)",
        'if not self._ensure_visual_target_foreground(reason="prepare_target_preflight"):',
        'if not self._ensure_visual_target_foreground(reason="prepare_target_action"):',
        "当前全屏客户端被浏览器/Codex 覆盖时",
        "真全屏画面常渲染在附属或无 owner 的 VSClient 渲染窗上",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"prepare-target foreground-recover fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_prepare_target_fullscreen_four_peak_hint_is_wired() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "self._prepare_target_context_reason = \"\"",
        "self._prepare_target_context_reason = reason",
        "finally:\n            self._prepare_target_context_reason = \"\"",
        "def _prepare_target_grid_like(",
        "def _prepare_target_fullscreen_four_grid_hint(",
        'if self._prepare_target_grid_like(actual_view, metrics, reason="prepare_target_grid_ready"):',
        'if self._prepare_target_grid_like(actual_view, metrics, reason="prepare_target_post_sync_grid_ready"):',
        '"PREPARE_TARGET accepting fullscreen 4-grid via peak hint cell=%s metrics=%s"',
        'if actual_view != VisualViewState.UNKNOWN:',
        'if self._current_mode != "fullscreen":',
        'if int(self._requested_layout or 0) != 4 and int(self._runtime_layout or 0) != 4:',
        "row_local_peak_mean >= 120.0",
        "col_local_peak_mean >= 120.0",
        "preview_edge_ratio >= 0.04",
        "structure_changed_ratio >= 0.08",
        "flat_interface_like",
        "row_local_peak_mean >= 12.0",
        "col_local_peak_mean >= 6.0",
        "preview_dominant_ratio >= 0.94",
        "preview_entropy <= 0.9",
        'prepare_target_context_reason in {"startup_warmup", "resume_hard_reset"}',
        'if prepare_target_context_reason == "resume_hard_reset" and self._last_pause_reason != "user_pause":',
        "preview_dominant_ratio >= 0.96",
        "preview_entropy <= 0.55",
        "preview_std <= 8.0",
        "preview_edge_ratio >= 0.012",
        "structure_changed_ratio >= 0.025",
        'prepare_target_context_reason == "resume_hard_reset"',
        'and self._last_pause_reason == "user_pause"',
        "preview_dominant_ratio >= 0.947",
        "preview_entropy <= 0.7",
        "preview_std <= 6.5",
        "preview_edge_ratio >= 0.024",
        "structure_changed_ratio >= 0.05",
        "固定 fullscreen 4 程序的 PREPARE_TARGET 阶段放开一条极窄兜底",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"prepare-target fullscreen4 peak-hint fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_prepare_target_locked_fullscreen_grid_hint_is_wired() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _locked_fullscreen_layout_for_hint(",
        "def _prepare_target_locked_fullscreen_grid_hint(",
        "DEFAULT_LAYOUT_SPECS[locked_layout]",
        '"PREPARE_TARGET accepting locked fullscreen %s-grid via layout hint cell=%s metrics=%s"',
        'prepare_target_context_reason == "resume_hard_reset"',
        'prepare_target_context_reason in {"startup_warmup", "resume_hard_reset"}',
        "allow_zoomed_resume_hint = (",
        "actual_view == VisualViewState.ZOOMED",
        "required_row_matches = float(max(1, (expected_rows - 1) - (1 if expected_rows >= 4 else 0)))",
        "required_col_matches = float(max(1, (expected_cols - 1) - (1 if expected_cols >= 4 else 0)))",
        "locked_fullscreen_peak_grid = (",
        "resume_soft_peak_grid = (",
        "startup_soft_peak_grid = (",
        "fullscreen_six_resume_peak_grid = (",
        "fullscreen_six_resume_selected_grid = (",
        "and full_peak_support",
        "and mean_strength >= 4.5",
        "and preview_dominant_ratio >= 0.90",
        "and preview_entropy <= 1.2",
        "and preview_std <= 11.5",
        "and preview_edge_ratio >= 0.035",
        "and structure_changed_ratio >= 0.10",
        "and preview_std <= 10.5",
        "and preview_edge_ratio >= 0.04",
        "and structure_changed_ratio >= 0.065",
        "fullscreen_six_flat_soft_peak_grid = (",
        "fullscreen_six_resume_weak_flat_grid = (",
        "resume_user_pause_context = (",
        "self._zoom_confirm_poll_boost_cycles_remaining > 0",
        "locked_layout == 6",
        "and mean_strength >= 3.8",
        "and mean_strength >= 3.5",
        "and preview_dominant_ratio >= 0.93",
        "and preview_entropy <= 0.9",
        "and preview_std <= 7.0",
        "and preview_std <= 6.0",
        "and structure_changed_ratio >= 0.03",
        "and structure_changed_ratio >= 0.075",
        "人工双击回宫格、再手工点选其他窗格但尚未放大时",
        "resume_textured_soft_peak_grid = (",
        "textured_multicell_soft_peak_grid = (",
        "and preview_dominant_ratio <= 0.86",
        "and 0.88 <= preview_dominant_ratio <= 0.93",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"prepare-target locked-fullscreen fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_prepare_target_locked_fullscreen_six_flat_sample_is_supported() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 3.0,
        "grid_divider_expected_count": 3.0,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 1.0,
        "grid_divider_row_local_peak_mean": 31.3904,
        "grid_divider_col_local_peak_mean": 10.2809,
        "grid_divider_mean_strength": 4.6416,
        "preview_entropy": 1.169,
        "preview_std": 11.2949,
        "preview_edge_ratio": 0.0373,
        "preview_dominant_ratio": 0.9042,
        "flat_interface_like": 1.0,
        "structure_changed_ratio": 0.1079,
    }
    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 3,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 3,
        "row_peak_match": float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0,
        "col_peak_match": float(metrics.get("grid_divider_col_peak_match_count", 0.0)) >= 1.0,
        "mean_strength": float(metrics.get("grid_divider_mean_strength", 0.0)) >= 4.5,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.90,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 1.2,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 11.5,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.035,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.10,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"prepare-target fullscreen6 dark multicell sample no longer satisfies the locked hint gate: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_prepare_target_locked_fullscreen_six_ultra_flat_sample_is_supported() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 3.0,
        "grid_divider_expected_count": 3.0,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 0.0,
        "grid_divider_row_local_peak_mean": 31.3904,
        "grid_divider_col_local_peak_mean": 7.6088,
        "grid_divider_mean_strength": 3.9239,
        "preview_entropy": 0.8807,
        "preview_std": 6.9145,
        "preview_edge_ratio": 0.0307,
        "preview_dominant_ratio": 0.9342,
        "flat_interface_like": 1.0,
        "structure_changed_ratio": 0.0791,
    }
    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 3,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 3,
        "row_peak_match": float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0,
        "col_local_peak_mean": float(metrics.get("grid_divider_col_local_peak_mean", 0.0)) >= 5.5,
        "mean_strength": float(metrics.get("grid_divider_mean_strength", 0.0)) >= 3.8,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.93,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 0.9,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 7.0,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.03,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.075,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"prepare-target fullscreen6 ultra-flat sample no longer satisfies the locked hint gate: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_prepare_target_locked_fullscreen_six_resume_selected_grid_sample_is_supported() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 3.0,
        "grid_divider_expected_count": 3.0,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 2.0,
        "grid_divider_row_local_peak_mean": 31.1398,
        "grid_divider_col_local_peak_mean": 8.34,
        "grid_divider_mean_strength": 4.4063,
        "preview_entropy": 1.1215,
        "preview_std": 10.1591,
        "preview_edge_ratio": 0.0426,
        "preview_dominant_ratio": 0.9042,
        "flat_interface_like": 0.0,
        "structure_changed_ratio": 0.0696,
    }
    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 3,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 3,
        "row_peak_match": float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0,
        "col_peak_match": float(metrics.get("grid_divider_col_peak_match_count", 0.0)) >= 2.0,
        "mean_strength": float(metrics.get("grid_divider_mean_strength", 0.0)) >= 4.3,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.90,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 1.2,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 10.5,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.04,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.065,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 0.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"prepare-target fullscreen6 resume selected-grid sample no longer satisfies the locked hint gate: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_prepare_target_locked_fullscreen_six_weak_post_recover_sample_is_supported() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 3.0,
        "grid_divider_expected_count": 3.0,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 1.0,
        "grid_divider_row_local_peak_mean": 31.1398,
        "grid_divider_col_local_peak_mean": 7.3876,
        "grid_divider_mean_strength": 3.6929,
        "preview_entropy": 0.8491,
        "preview_std": 5.5297,
        "preview_edge_ratio": 0.0307,
        "preview_dominant_ratio": 0.9342,
        "flat_interface_like": 1.0,
        "structure_changed_ratio": 0.0388,
    }
    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 3,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 3,
        "row_peak_match": float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0,
        "col_peak_match": float(metrics.get("grid_divider_col_peak_match_count", 0.0)) >= 1.0,
        "mean_strength": float(metrics.get("grid_divider_mean_strength", 0.0)) >= 3.5,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.93,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 0.9,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 6.0,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.03,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.03,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"prepare-target fullscreen6 weak post-recover sample no longer satisfies the locked hint gate: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_prepare_target_locked_fullscreen_six_real_runtime_weak_sample_is_supported() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 3.0,
        "grid_divider_expected_count": 3.0,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 1.0,
        "grid_divider_row_local_peak_mean": 31.1398,
        "grid_divider_col_local_peak_mean": 7.1663,
        "grid_divider_mean_strength": 3.5454,
        "preview_entropy": 0.8328,
        "preview_std": 4.6873,
        "preview_edge_ratio": 0.0307,
        "preview_dominant_ratio": 0.9369,
        "flat_interface_like": 1.0,
        "structure_changed_ratio": 0.031,
    }
    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 3,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 3,
        "row_peak_match": float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0,
        "col_peak_match": float(metrics.get("grid_divider_col_peak_match_count", 0.0)) >= 1.0,
        "mean_strength": float(metrics.get("grid_divider_mean_strength", 0.0)) >= 3.5,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.93,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 0.9,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 6.0,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.03,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.03,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"prepare-target fullscreen6 real-runtime weak sample no longer satisfies the locked hint gate: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_prepare_target_locked_fullscreen_six_weak_flat_sample_is_rejected() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 3.0,
        "grid_divider_expected_count": 3.0,
        "grid_divider_row_peak_match_count": 0.0,
        "grid_divider_col_peak_match_count": 1.0,
        "grid_divider_row_local_peak_mean": 0.3181,
        "grid_divider_col_local_peak_mean": 3.8086,
        "grid_divider_mean_strength": 1.3307,
        "preview_entropy": 0.8436,
        "preview_std": 12.0164,
        "preview_edge_ratio": 0.0235,
        "preview_dominant_ratio": 0.9045,
        "flat_interface_like": 1.0,
        "structure_changed_ratio": 0.0198,
    }
    checks = {
        "row_peak_match": float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0,
        "mean_strength": float(metrics.get("grid_divider_mean_strength", 0.0)) >= 3.5,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.93,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 7.0,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.03,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.12,
    }
    if all(checks.values()):
        raise RuntimeError(
            f"prepare-target fullscreen6 weak dark sample unexpectedly satisfies the locked hint gate: metrics={metrics}"
        )
    return {"failed_checks": [name for name, ok in checks.items() if not ok]}


def test_prepare_target_locked_fullscreen_six_selected_grid_method_accepts_resume_with_stale_mode_context() -> dict[str, Any]:
    scheduler = _make_fullscreen_six_prepare_hint_scheduler()
    scheduler._prepare_target_context_reason = ""
    metrics = {
        "preview_entropy": 1.1215,
        "preview_std": 10.1591,
        "preview_edge_ratio": 0.0426,
        "preview_dominant_ratio": 0.9042,
        "flat_interface_like": 0.0,
        "structure_changed_ratio": 0.0696,
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 3.0,
        "grid_divider_expected_count": 3.0,
        "grid_divider_mean_strength": 4.4063,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 2.0,
        "grid_divider_row_local_peak_mean": 31.1398,
        "grid_divider_col_local_peak_mean": 8.34,
    }
    locked_layout = scheduler._locked_fullscreen_layout_for_hint()
    accepted = scheduler._prepare_target_locked_fullscreen_grid_hint(VisualViewState.ZOOMED, metrics)
    if locked_layout != 6:
        raise RuntimeError(f"locked fullscreen layout fallback regressed: {locked_layout!r}")
    if not accepted:
        raise RuntimeError(
            f"selected-grid resume sample should be accepted even when current_mode/context are stale: metrics={metrics}"
        )
    return {"locked_layout": locked_layout, "accepted": accepted}


def test_prepare_target_locked_fullscreen_six_selected_grid_method_accepts_without_resume_context() -> dict[str, Any]:
    scheduler = _make_fullscreen_six_prepare_hint_scheduler()
    scheduler._last_pause_reason = ""
    scheduler._prepare_target_context_reason = ""
    scheduler._zoom_confirm_poll_boost_cycles_remaining = 0
    metrics = {
        "preview_entropy": 1.1215,
        "preview_std": 10.1591,
        "preview_edge_ratio": 0.0426,
        "preview_dominant_ratio": 0.9042,
        "flat_interface_like": 0.0,
        "structure_changed_ratio": 0.0696,
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 3.0,
        "grid_divider_expected_count": 3.0,
        "grid_divider_mean_strength": 4.4063,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 2.0,
        "grid_divider_row_local_peak_mean": 31.1398,
        "grid_divider_col_local_peak_mean": 8.34,
    }
    accepted = scheduler._prepare_target_locked_fullscreen_grid_hint(VisualViewState.ZOOMED, metrics)
    if not accepted:
        raise RuntimeError(
            "selected-grid sample should be accepted even without resume context"
        )
    return {"accepted": accepted}


def test_prepare_target_locked_fullscreen_six_weak_grid_method_accepts_real_runtime_sample() -> dict[str, Any]:
    scheduler = _make_fullscreen_six_prepare_hint_scheduler()
    scheduler._prepare_target_context_reason = ""
    metrics = {
        "preview_entropy": 0.8328,
        "preview_std": 4.6873,
        "preview_edge_ratio": 0.0307,
        "preview_dominant_ratio": 0.9369,
        "flat_interface_like": 1.0,
        "structure_changed_ratio": 0.031,
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 3.0,
        "grid_divider_expected_count": 3.0,
        "grid_divider_mean_strength": 3.5454,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 1.0,
        "grid_divider_row_local_peak_mean": 31.1398,
        "grid_divider_col_local_peak_mean": 7.1663,
    }
    accepted = scheduler._prepare_target_locked_fullscreen_grid_hint(VisualViewState.UNKNOWN, metrics)
    if not accepted:
        raise RuntimeError(f"real runtime weak post-recover sample should be accepted: metrics={metrics}")
    return {"accepted": accepted}


def test_prepare_target_locked_fullscreen_six_weak_grid_method_accepts_without_resume_context() -> dict[str, Any]:
    scheduler = _make_fullscreen_six_prepare_hint_scheduler()
    scheduler._last_pause_reason = ""
    scheduler._prepare_target_context_reason = ""
    scheduler._zoom_confirm_poll_boost_cycles_remaining = 0
    metrics = {
        "preview_entropy": 0.8328,
        "preview_std": 4.6873,
        "preview_edge_ratio": 0.0307,
        "preview_dominant_ratio": 0.9369,
        "flat_interface_like": 1.0,
        "structure_changed_ratio": 0.031,
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 3.0,
        "grid_divider_expected_count": 3.0,
        "grid_divider_mean_strength": 3.5454,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 1.0,
        "grid_divider_row_local_peak_mean": 31.1398,
        "grid_divider_col_local_peak_mean": 7.1663,
    }
    accepted = scheduler._prepare_target_locked_fullscreen_grid_hint(VisualViewState.UNKNOWN, metrics)
    if not accepted:
        raise RuntimeError(
            "weak fullscreen6 grid sample should be accepted even without resume context"
        )
    return {"accepted": accepted}


def test_resume_hard_reset_ultra_flat_fullscreen_four_sample_is_supported() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 2.0,
        "grid_divider_expected_count": 2.0,
        "grid_divider_row_peak_match_count": 0.0,
        "grid_divider_col_peak_match_count": 0.0,
        "grid_divider_row_local_peak_mean": 0.3181,
        "grid_divider_col_local_peak_mean": 0.5617,
        "preview_entropy": 0.4151,
        "preview_std": 6.5866,
        "preview_edge_ratio": 0.0158,
        "preview_dominant_ratio": 0.9635,
        "flat_interface_like": 1.0,
        "structure_changed_ratio": 0.032,
    }
    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 2,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 2,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.96,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 0.55,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 8.0,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.012,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.025,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"resume_hard_reset ultra-flat fullscreen4 sample no longer satisfies the gated prepare-target hint: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_resume_hard_reset_soft_peak_fullscreen_four_sample_is_supported() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 2.0,
        "grid_divider_expected_count": 2.0,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 1.0,
        "grid_divider_row_local_peak_mean": 15.8827,
        "grid_divider_col_local_peak_mean": 6.4508,
        "preview_entropy": 0.6502,
        "preview_std": 5.3751,
        "preview_edge_ratio": 0.027,
        "preview_dominant_ratio": 0.9509,
        "flat_interface_like": 1.0,
        "structure_changed_ratio": 0.0696,
    }
    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 2,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 2,
        "row_peak_match": float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0,
        "col_peak_match": float(metrics.get("grid_divider_col_peak_match_count", 0.0)) >= 1.0,
        "row_peak_mean": float(metrics.get("grid_divider_row_local_peak_mean", 0.0)) >= 12.0,
        "col_peak_mean": float(metrics.get("grid_divider_col_local_peak_mean", 0.0)) >= 6.0,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.95,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 0.7,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 6.5,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.024,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.05,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"resume_hard_reset soft-peak fullscreen4 sample no longer satisfies the gated prepare-target hint: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_startup_soft_peak_fullscreen_four_sample_is_supported() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 2.0,
        "grid_divider_expected_count": 2.0,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 1.0,
        "grid_divider_row_local_peak_mean": 15.6321,
        "grid_divider_col_local_peak_mean": 6.4508,
        "preview_entropy": 0.811,
        "preview_std": 8.406,
        "preview_edge_ratio": 0.0304,
        "preview_dominant_ratio": 0.935,
        "flat_interface_like": 1.0,
        "structure_changed_ratio": 0.1038,
    }
    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 2,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 2,
        "row_peak_match": float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0,
        "col_peak_match": float(metrics.get("grid_divider_col_peak_match_count", 0.0)) >= 1.0,
        "row_peak_mean": float(metrics.get("grid_divider_row_local_peak_mean", 0.0)) >= 15.0,
        "col_peak_mean": float(metrics.get("grid_divider_col_local_peak_mean", 0.0)) >= 6.4,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.03,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.10,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.925,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 0.85,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 11.0,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"startup soft-peak fullscreen4 sample no longer satisfies the gated prepare-target hint: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_textured_multicell_fullscreen_six_sample_is_supported() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 3.0,
        "grid_divider_expected_count": 3.0,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 0.0,
        "grid_divider_row_local_peak_mean": 31.1398,
        "grid_divider_col_local_peak_mean": 9.4681,
        "grid_divider_mean_strength": 4.6947,
        "preview_entropy": 1.7913,
        "preview_std": 17.4905,
        "preview_edge_ratio": 0.0637,
        "preview_dominant_ratio": 0.8053,
        "flat_interface_like": 0.0,
        "structure_changed_ratio": 0.1406,
    }
    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 3,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 3,
        "row_peak_support": float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0,
        "col_peak_support": float(metrics.get("grid_divider_col_local_peak_mean", 0.0)) >= 5.5,
        "mean_strength": float(metrics.get("grid_divider_mean_strength", 0.0)) >= 4.5,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.055,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.12,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) <= 0.86,
        "entropy": float(metrics.get("preview_entropy", 0.0)) >= 1.2,
        "preview_std": float(metrics.get("preview_std", 0.0)) >= 15.0,
        "not_flat": float(metrics.get("flat_interface_like", 0.0)) == 0.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"textured multicell fullscreen6 sample no longer satisfies the generic prepare-target hint: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_resume_hard_reset_textured_fullscreen_nine_sample_is_supported() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 3.0,
        "grid_divider_cols_estimate": 3.0,
        "grid_divider_expected_count": 4.0,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 1.0,
        "grid_divider_row_local_peak_mean": 21.8996,
        "grid_divider_col_local_peak_mean": 12.443,
        "grid_divider_mean_strength": 4.3642,
        "preview_entropy": 1.2646,
        "preview_std": 7.8363,
        "preview_edge_ratio": 0.0479,
        "preview_dominant_ratio": 0.8951,
        "flat_interface_like": 0.0,
        "structure_changed_ratio": 0.1086,
    }
    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 3,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 3,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 4,
        "row_peak_support": (
            float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0
            or float(metrics.get("grid_divider_row_local_peak_mean", 0.0)) >= 10.0
        ),
        "col_peak_support": (
            float(metrics.get("grid_divider_col_peak_match_count", 0.0)) >= 1.0
            or float(metrics.get("grid_divider_col_local_peak_mean", 0.0)) >= 5.5
        ),
        "mean_strength": float(metrics.get("grid_divider_mean_strength", 0.0)) >= 4.2,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.045,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.09,
        "dominant_ratio": 0.88 <= float(metrics.get("preview_dominant_ratio", 0.0)) <= 0.93,
        "entropy": 1.0 <= float(metrics.get("preview_entropy", 0.0)) <= 1.6,
        "preview_std": 7.0 <= float(metrics.get("preview_std", 0.0)) <= 12.5,
        "not_flat": float(metrics.get("flat_interface_like", 0.0)) == 0.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"resume_hard_reset textured fullscreen9 sample no longer satisfies the gated prepare-target hint: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_detector_fullscreen_four_peak_grid_classification_is_wired() -> dict[str, Any]:
    detector_text = (PROJECT_ROOT / "detector.py").read_text(encoding="utf-8")
    required_fragments = [
        "row_peak_support = row_peak_match_count >= 1.0 or row_local_peak_mean >= 15.0",
        "col_peak_support = col_peak_match_count >= 1.0 or col_local_peak_mean >= 6.3",
        "and row_peak_match_count >= 1.0",
        "and col_peak_match_count >= 1.0",
        "and row_local_peak_mean >= 120.0",
        "and col_local_peak_mean >= 120.0",
        "and preview_dominant_ratio >= 0.95",
        "and preview_entropy <= 0.7",
        "and preview_std <= 6.5",
        "and preview_dominant_ratio >= 0.90",
        "and preview_entropy <= 1.1",
        "and preview_std <= 11.2",
        "detector 层已经具备稳定的 2x2 峰值结构",
        "首轮启动的全屏 4 宫格样本会比恢复态更“脏”",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in detector_text]
    if missing:
        raise RuntimeError(f"detector fullscreen4 peak-grid classification fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_startup_borderline_fullscreen_four_sample_is_supported_by_detector() -> dict[str, Any]:
    metrics = {
        "grid_divider_rows_estimate": 2.0,
        "grid_divider_cols_estimate": 2.0,
        "grid_divider_expected_count": 2.0,
        "grid_divider_row_peak_match_count": 1.0,
        "grid_divider_col_peak_match_count": 0.0,
        "grid_divider_row_local_peak_mean": 15.8827,
        "grid_divider_col_local_peak_mean": 6.5764,
        "preview_entropy": 1.0485,
        "preview_std": 11.0307,
        "preview_edge_ratio": 0.0393,
        "preview_dominant_ratio": 0.9014,
        "flat_interface_like": 1.0,
        "structure_changed_ratio": 0.1292,
    }
    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 2,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 2,
        "row_peak_support": (
            float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0
            or float(metrics.get("grid_divider_row_local_peak_mean", 0.0)) >= 15.0
        ),
        "col_peak_support": (
            float(metrics.get("grid_divider_col_peak_match_count", 0.0)) >= 1.0
            or float(metrics.get("grid_divider_col_local_peak_mean", 0.0)) >= 6.3
        ),
        "row_peak_mean": float(metrics.get("grid_divider_row_local_peak_mean", 0.0)) >= 15.0,
        "col_peak_mean": float(metrics.get("grid_divider_col_local_peak_mean", 0.0)) >= 6.3,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.03,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.10,
        "dominant_ratio": float(metrics.get("preview_dominant_ratio", 0.0)) >= 0.90,
        "entropy": float(metrics.get("preview_entropy", 999.0)) <= 1.1,
        "preview_std": float(metrics.get("preview_std", 999.0)) <= 11.2,
        "flat_interface_like": float(metrics.get("flat_interface_like", 0.0)) == 1.0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(
            f"borderline startup fullscreen4 sample no longer satisfies detector peak-grid thresholds: failed={failed} metrics={metrics}"
        )
    return {"checked_fragments": len(checks)}


def test_historical_fullscreen_four_sample_is_classified_as_grid() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.yaml")
    detector = Detector(config.detection, _FakeLogger())
    mapper = GridMapper(config.grid)
    sample_path = PROJECT_ROOT / "tmp" / "elevated_probe_full_4" / "00_before.png"
    if not sample_path.exists():
        return {"skipped": True, "reason": f"missing sample: {sample_path}"}

    image = Image.open(sample_path)
    preview_rect = Rect(0, 0, image.width, image.height)
    cells = mapper.build_cells(preview_rect, 4)
    actual_view, metrics = detector.classify_runtime_view(
        preview_rect,
        cells[0].rect,
        grid_probe=None,
        zoom_probe=None,
        preview_image=image,
    )
    if actual_view != VisualViewState.GRID:
        raise RuntimeError(f"historical fullscreen4 sample should now be classified as GRID in detector: {actual_view} {metrics}")

    checks = {
        "rows": int(round(float(metrics.get("grid_divider_rows_estimate", 0.0)))) == 2,
        "cols": int(round(float(metrics.get("grid_divider_cols_estimate", 0.0)))) == 2,
        "expected_count": int(round(float(metrics.get("grid_divider_expected_count", 0.0)))) == 2,
        "row_peak": float(metrics.get("grid_divider_row_peak_match_count", 0.0)) >= 1.0,
        "col_peak": float(metrics.get("grid_divider_col_peak_match_count", 0.0)) >= 1.0,
        "row_local": float(metrics.get("grid_divider_row_local_peak_mean", 0.0)) >= 120.0,
        "col_local": float(metrics.get("grid_divider_col_local_peak_mean", 0.0)) >= 120.0,
        "edge_ratio": float(metrics.get("preview_edge_ratio", 0.0)) >= 0.04,
        "structure_ratio": float(metrics.get("structure_changed_ratio", 0.0)) >= 0.08,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(f"historical fullscreen4 sample no longer supports prepare-target peak hint: failed={failed} metrics={metrics}")

    return {
        "actual_view": actual_view.value,
        "row_local_peak_mean": metrics.get("grid_divider_row_local_peak_mean"),
        "col_local_peak_mean": metrics.get("grid_divider_col_local_peak_mean"),
    }


def test_windowed_mode_detection_caches_ui_marker_probe() -> dict[str, Any]:
    window_manager_text = (PROJECT_ROOT / "window_manager.py").read_text(encoding="utf-8")
    required_fragments = [
        "self._windowed_marker_cache_key",
        "self._windowed_marker_cache_ttl_seconds",
        "def _detect_windowed_ui_markers_cached",
        "windowed_hits = self._detect_windowed_ui_markers_cached(window_info)",
        "Auto mode resolved to windowed via geometry fast-path",
        'ctrl = root.child_window(title=marker)',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in window_manager_text]
    if missing:
        raise RuntimeError(f"windowed mode cache fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_window_manager_tracks_detached_vsclient_render_surface() -> dict[str, Any]:
    window_manager_text = (PROJECT_ROOT / "window_manager.py").read_text(encoding="utf-8")
    required_fragments = [
        "def find_visual_render_surface(self, target_window: WindowInfo) -> WindowSnapshot | None:",
        "def is_visual_render_surface(self, snapshot: WindowSnapshot, target_window: WindowInfo) -> bool:",
        "def _looks_like_detached_render_surface(self, snapshot: WindowSnapshot, target_window: WindowInfo) -> bool:",
        "def _looks_like_detached_render_surface_prefilter(self, *, title: str, rect: Rect, target_window: WindowInfo) -> bool:",
        "detached_prefilter = self._looks_like_detached_render_surface_prefilter(",
        'return process_name == "vsclient.exe" and title == "vsclient"',
        "只要它仍与主窗口近乎完全重叠，就应该继续把它当成真实视觉目标",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in window_manager_text]
    if missing:
        raise RuntimeError(f"detached VSClient render-surface fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_window_manager_focus_requires_foreground_confirmation() -> dict[str, Any]:
    window_manager_text = (PROJECT_ROOT / "window_manager.py").read_text(encoding="utf-8")
    required_fragments = [
        "def focus_window(self, hwnd: int) -> bool:",
        "return True",
        "return False",
        "if win32gui.GetForegroundWindow() == hwnd:",
        'raise RuntimeError(f"Window hwnd={hwnd} did not become the foreground window after repeated activation attempts")',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in window_manager_text]
    if missing:
        raise RuntimeError(f"window_manager foreground confirmation fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_scheduler_clears_stale_runtime_favorites_on_read_failure() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "self._runtime_favorite_labels = []",
        "self._runtime_favorite_labels = list(runtime_label_order)",
        "runtime_label_order = []",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"scheduler favorites reset fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_status_runtime_cleans_duplicate_overlay_processes() -> dict[str, Any]:
    status_runtime_text = (PROJECT_ROOT / "status_runtime.py").read_text(encoding="utf-8")
    required_fragments = [
        "self._persist_payload(payload, signature=signature)",
        "def _matching_overlay_processes(self) -> list[psutil.Process]:",
        'for process in psutil.process_iter(["pid", "name", "exe", "cmdline"]):',
        "for duplicate in matching_processes[1:]:",
        "self._write_overlay_pid(verified_process.pid)",
        "同一个 status_file 只能保留一个浮窗进程",
        "verified_process = self._verified_overlay_process(existing_pid)",
        "blocked_reason = self._overlay_reuse_blocked_reason()",
        "def _overlay_reuse_blocked_reason(self) -> str | None:",
        'if payload.get("close_requested"):',
        'return "close_requested"',
        '"Skipping status overlay reuse pid=%s reason=%s"',
        "Discarding unstable overlay pid=%s because it disappeared during reuse validation",
        "self._terminate_duplicate_overlay_processes(keep_pid=verified_process.pid)",
        'self._logger.info("Reusing status overlay pid=%s via pid_file", verified_process.pid)',
        'self._expected_overlay_process_names = {"python.exe", "pythonw.exe"}',
        "process_name = str(process.name()).strip().lower()",
        "if psutil.pid_exists(verified_process.pid):",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in status_runtime_text]
    if missing:
        raise RuntimeError(f"status_runtime duplicate overlay cleanup fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_status_runtime_overlay_ensure_is_async() -> dict[str, Any]:
    status_runtime_text = (PROJECT_ROOT / "status_runtime.py").read_text(encoding="utf-8")
    required_fragments = [
        "import threading",
        "self._ensure_overlay_process_for_start()",
        "def _ensure_overlay_process_for_start(self) -> None:",
        "self._launch_overlay_process()",
        "self._wait_for_overlay_ready(timeout_seconds=0.8)",
        "self._request_overlay_process_async(reason=\"publish\")",
        "def _request_overlay_process_async(self, *, reason: str) -> None:",
        "target=self._ensure_overlay_process_async_worker,",
        "name=\"status-overlay-ensure\"",
        "daemon=True,",
        "def _ensure_overlay_process_async_worker(self, reason: str) -> None:",
        'self._logger.warning("Status overlay async ensure failed reason=%s error=%s", reason, exc)',
        "固定程序会卡在 startup warmup",
        "启动时先落一份非关闭态 payload",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in status_runtime_text]
    if missing:
        raise RuntimeError(f"status_runtime async overlay ensure fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_native_runtime_client_discards_stale_response_ids() -> dict[str, Any]:
    client_text = (PROJECT_ROOT / "native_runtime_client.py").read_text(encoding="utf-8")
    required_fragments = [
        "stale_response_count = 0",
        'if response.get("id") != request_id:',
        "stale_response_count += 1",
        "Native runtime sidecar response id mismatch expected=%s actual=%s command=%s stale_count=%s; discarding stale response",
        "continue",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in client_text]
    if missing:
        raise RuntimeError(f"native_runtime_client stale-response fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_startup_warmup_uses_fast_refresh_after_first_sample() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "startup warmup 的第二个稳定样本只需要确认窗口矩形仍然稳定",
        "self._refresh_window_context(",
        "fast=(stable_samples > 0 or locked_fast_path) and self._window_info is not None",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"scheduler startup-warmup fast-refresh fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_startup_warmup_clears_stale_manual_input_before_first_action() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        'clear_manual_activity = getattr(self._input_guard, "clear_manual_activity", None)',
        "clear_manual_activity()",
        "预热完成后不再自动执行",
        "self._suppress_input_guard(duration_ms=max(8000, self._config.input_guard.resume_settle_ms + 2000))",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"scheduler startup-warmup input-guard fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_pointer_actions_skip_redundant_runtime_guard_rechecks() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "skip_guard_before: bool = False",
        "if self._config.runtime_guard.verify_before_action and not skip_guard_before:",
        "skip_guard_before=True,",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"redundant runtime-guard skip fragments missing: {missing}")
    if "guard_expected_view_after=VisualViewState.GRID" in scheduler_text:
        raise RuntimeError("scheduler still forces post-click GRID view recheck on pointer actions")
    return {"checked_fragments": len(required_fragments)}


def test_input_guard_tolerates_cursor_probe_access_denied() -> dict[str, Any]:
    input_guard_text = (PROJECT_ROOT / "input_guard.py").read_text(encoding="utf-8")
    required_fragments = [
        "self._cursor_pos_warning_active = False",
        "self._last_mouse_pos = self._safe_get_cursor_pos()",
        "def _safe_get_cursor_pos(self) -> tuple[int, int]:",
        "cursor probe unavailable; mouse-move detection degraded",
        "return fallback",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in input_guard_text]
    if missing:
        raise RuntimeError(f"input_guard cursor-probe fallback fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_scheduler_runtime_layout_sync_is_not_fixed_to_config_layout() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    refresh_start = scheduler_text.index("def _refresh_window_context")
    refresh_end = scheduler_text.index("def _candidate_runtime_layouts")
    refresh_block = scheduler_text[refresh_start:refresh_end]
    init_alternatives = [
        "self._runtime_layout = int(self._requested_layout or self._config.grid.layout)",
        "self._runtime_layout = int(self._config.grid.layout)",
    ]
    if not any(fragment in scheduler_text for fragment in init_alternatives):
        raise RuntimeError(f"scheduler runtime-layout init fragments missing: {init_alternatives}")
    required_fragments = [
        "def _candidate_runtime_layouts(self) -> list[int]:",
        "def _apply_runtime_layout(self, layout: int, *, reason: str, metrics: dict[str, float] | None = None) -> bool:",
        "def _try_sync_runtime_layout(self, *, reason: str) -> bool:",
        "int(self._requested_layout) if self._requested_layout is not None else None",
        'synced_preflight = self._try_sync_runtime_layout(reason="prepare_target_preflight")',
        'if synced_preflight:',
        'synced_post_recover = self._try_sync_runtime_layout(reason="prepare_target_post_recover")',
        'self._invalidate_runtime_observation("resume_reconcile")',
        'observation = self._observe_runtime_profile(reason="resume_reconcile", samples=3, sync_layout=True)',
        "self._runtime_layout,",
        '"RUNTIME_LAYOUT sync reason=%s from=%s to=%s cell=%s metrics=%s"',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"scheduler runtime-layout sync fragments missing: {missing}")
    if "self._config.grid.layout," in refresh_block:
        raise RuntimeError("refresh_window_context still hard-codes config.grid.layout when building cells")
    if "actual_view = VisualViewState.GRID" in scheduler_text:
        raise RuntimeError("resume/preflight still aliases layout sync to grid view success")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_layout_manual_detect_stays_in_layout_switcher_only() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    layout_switcher_text = (PROJECT_ROOT / "layout_switcher.py").read_text(encoding="utf-8")
    app_text = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    required_layout_switcher = [
        "LAYOUT_BY_SECTION_AND_LABEL",
        "def detect_current_layout(self, *, target_window=None) -> int | None:",
        "def _resolve_target_window(self, target_window=None):",
        "def _close_layout_panel(",
        "prefer_pointer_fallback: bool = False",
        "runtime_layout_detected layout=%s section=%s label=%s",
        "self._window_manager.focus_window(target_window.hwnd)",
        "close_layout_panel_center_helper",
        "close_layout_panel_toggle",
        "close_layout_panel_dismiss",
        "close_layout_panel_escape",
        "allow_pointer_fallback=True",
        "prefer_pointer_fallback=True",
        "timeout_seconds=1.4",
        'raise LayoutSwitchError("Timed out waiting for layout panel to become open")',
        "if rect.width <= 0 or rect.height <= 0:",
    ]
    missing_layout_switcher = [fragment for fragment in required_layout_switcher if fragment not in layout_switcher_text]
    if missing_layout_switcher:
        raise RuntimeError(f"layout_switcher current-layout detect fragments missing: {missing_layout_switcher}")

    layout_switcher_alternatives = [
        ["panel_root = self._desktop.window(handle=target_window.hwnd)", "current_root = self._desktop.window(handle=hwnd) if hwnd is not None else root"],
        ["panel_root = desktop.window(handle=target_window.hwnd)", "current_root = self._desktop.window(handle=hwnd) if hwnd is not None else root", "def _require_desktop(self):"],
    ]
    if not any(all(fragment in layout_switcher_text for fragment in option) for option in layout_switcher_alternatives):
        raise RuntimeError("layout_switcher current-layout detect no longer contains a valid desktop/window resolution path")
    forbidden_scheduler = [
        'if self._layout_switcher is not None and self._current_mode == "windowed":',
        "detected_layout = self._layout_switcher.detect_current_layout(target_window=self._window_info)",
        '"RUNTIME_LAYOUT keep reason=%s layout=%s via=windowed_uia_only cell=%s"',
    ]
    present_scheduler = [fragment for fragment in forbidden_scheduler if fragment in scheduler_text]
    if present_scheduler:
        raise RuntimeError(f"scheduler still uses UIA panel detection in windowed auto-sync: {present_scheduler}")
    required_app = [
        "runtime_layout_switcher = LayoutSwitcher(window_manager, controller, logger, config=config, detector=detector)",
        "layout_switcher=runtime_layout_switcher,",
        "target_window=target_window,",
    ]
    missing_app = [fragment for fragment in required_app if fragment not in app_text]
    if missing_app:
        raise RuntimeError(f"app.py layout-switcher wiring fragments missing: {missing_app}")
    return {
        "layout_switcher_fragments": len(required_layout_switcher),
        "scheduler_fragments": len(forbidden_scheduler),
        "app_fragments": len(required_app),
    }


def test_layout_panel_close_prefers_safe_paths_before_hotspot() -> dict[str, Any]:
    layout_switcher_text = (PROJECT_ROOT / "layout_switcher.py").read_text(encoding="utf-8")
    toggle_pos = layout_switcher_text.find('"close_layout_panel_toggle"')
    dismiss_pos = layout_switcher_text.find('"close_layout_panel_dismiss"')
    hotspot_pos = layout_switcher_text.find('"close_layout_panel_hotspot"')
    if min(toggle_pos, dismiss_pos, hotspot_pos) < 0:
        raise RuntimeError("layout close attempt labels missing from layout_switcher.py")
    if not (toggle_pos < hotspot_pos and dismiss_pos < hotspot_pos):
        raise RuntimeError("layout panel close no longer prefers safe toggle/dismiss paths before hotspot")
    return {
        "toggle_pos": toggle_pos,
        "dismiss_pos": dismiss_pos,
        "hotspot_pos": hotspot_pos,
    }


def test_runtime_layout_detection_uses_safe_panel_open_close_only() -> dict[str, Any]:
    layout_switcher_text = (PROJECT_ROOT / "layout_switcher.py").read_text(encoding="utf-8")
    detect_start = layout_switcher_text.find("def detect_current_layout(self, *, target_window=None) -> int | None:")
    open_start = layout_switcher_text.find("def _open_layout_panel(", detect_start)
    close_start = layout_switcher_text.find("def _close_layout_panel(", open_start)
    wait_start = layout_switcher_text.find("def _wait_for_panel(", close_start)
    if min(detect_start, open_start, close_start, wait_start) < 0:
        raise RuntimeError("could not locate detect/open/close panel blocks in layout_switcher.py")
    detect_block = layout_switcher_text[detect_start:open_start]
    close_block = layout_switcher_text[close_start:wait_start]
    detect_required = [
        "allow_pointer_fallback=True",
        "prefer_pointer_fallback=True",
        "_open_layout_panel(",
        "_close_layout_panel(",
    ]
    missing_detect = [fragment for fragment in detect_required if fragment not in detect_block]
    if missing_detect:
        raise RuntimeError(f"runtime layout detect fast-open/close fragments missing: {missing_detect}")
    close_required = [
        "prefer_pointer_fallback: bool = False",
        "pointer_attempts: list[tuple[str, tuple[int, int] | None, callable]] = []",
        'attempt[0] == "close_layout_panel_dismiss"',
        '"close_layout_panel_toggle_click_input", "close_layout_panel_toggle_invoke"',
        "close_layout_panel_toggle_invoke",
        "close_layout_panel_toggle_click_input",
        "close_layout_panel_center_invoke",
        "close_layout_panel_escape",
        "control_attempts + pointer_attempts",
    ]
    missing_close = [fragment for fragment in close_required if fragment not in close_block]
    if missing_close:
        raise RuntimeError(f"layout close fast-path fragments missing: {missing_close}")
    return {
        "detect_fragments": len(detect_required),
        "close_fragments": len(close_required),
    }


def test_windowed_runtime_layout_sync_uses_multisignal_consensus_without_uia_panel() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _windowed_layout_signal_summary(",
        '"windowed_layout_visual_confirmed": 1.0 if candidate.get("grid_like") else 0.0,',
        '"windowed_layout_structure_confirmed": 1.0 if structure_confirmed else 0.0,',
        '"windowed_layout_geometry_confirmed": 1.0 if geometry_confirmed else 0.0,',
        '"windowed_layout_score_margin_confirmed": 1.0 if score_margin_confirmed else 0.0,',
        '"windowed_layout_signal_count": float(signal_count),',
        "score_ranked_candidates = sorted(grid_candidates, key=lambda candidate: float(candidate.get(\"score\") or 0.0), reverse=True)",
        "key=lambda item: (int(item[\"signal_count\"]), float(item[\"score\"]))",
        "def _resolve_windowed_runtime_layout_candidate(",
        "windowed_multisignal_confirm",
        "windowed_visual_keep_current",
        "windowed_multisignal_low_confidence",
        "windowed_dense_downshift_low_structure",
        "and current_layout >= 9",
        "and best_layout <= 4",
        "and not best_structure_confirmed",
        "self._resolve_windowed_runtime_layout_candidate(",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"windowed runtime-layout multisignal fragments missing: {missing}")
    forbidden_fragments = [
        "detect_current_layout(target_window=self._window_info)",
        "windowed_uia_only",
    ]
    present = [fragment for fragment in forbidden_fragments if fragment in scheduler_text]
    if present:
        raise RuntimeError(f"windowed runtime-layout sync still touches the layout panel path: {present}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_hotkeys_can_optionally_drive_client_ui_only_under_pause_guard() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    common_text = (PROJECT_ROOT / "common.py").read_text(encoding="utf-8")
    required_fragments = [
        "runtime_hotkeys_drive_client_ui: bool = False",
        "runtime_hotkeys_require_paused: bool = True",
        "if not self._config.controls.runtime_hotkeys_drive_client_ui:",
        "if self._config.controls.runtime_hotkeys_require_paused and self._state != SchedulerState.PAUSED:",
        "self._layout_switcher.switch_runtime_layout(int(self._requested_layout), target_window=self._window_info)",
        "self._layout_switcher.switch_mode(self._requested_mode, target_window=self._window_info)",
        "暂停态热键直控",
        'changed_label = f"运行模式目标已切换：{self._mode_display_label(next_requested_mode)}"',
        'changed_label = f"宫格模式目标已切换：{self._layout_display_label(self._requested_layout)}"',
        "def _handle_profile_source_toggle_request(self) -> None:",
        'profile_source_toggle: str = "f1"',
        'layout_cycle: str = "f8"',
    ]
    missing = [
        fragment
        for fragment in required_fragments
        if fragment not in scheduler_text and fragment not in common_text
    ]
    if missing:
        raise RuntimeError(f"runtime hotkey optional-drive fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_fullscreen_reconcile_prefers_observed_state_over_keep_heuristics() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _fullscreen_layout_reconcile_prefers_observed_state(reason: str) -> bool:",
        '"manual_profile_lock",',
        '"resume_reconcile",',
        '"resume_post_recover",',
        '"runtime_target_update",',
        '"inspect_runtime",',
        "fullscreen_reconcile_mode = (",
        "self._fullscreen_layout_reconcile_prefers_observed_state(reason)",
        "RUNTIME_LAYOUT reconcile prefers observed fullscreen state",
        "current_layout_trusted = False",
        "and not fullscreen_reconcile_mode",
        "fullscreen_startup_dense_keep",
        "fullscreen_dense_geometry_keep",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"fullscreen reconcile keep-heuristic override fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_manual_runtime_targets_no_longer_override_actual_detection() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    window_manager_text = (PROJECT_ROOT / "window_manager.py").read_text(encoding="utf-8")
    required_scheduler = [
        "def _use_locked_runtime_profile_fast_path(self) -> bool:",
        "def _observe_runtime_profile(",
        "def _observation_matches_requested(",
        "def _lock_manual_profile_to_current(self) -> bool:",
        "当前为手动目标闭环",
        "if self._use_locked_runtime_profile_fast_path():",
        "self._current_mode = str(self._requested_mode)",
        "self._runtime_layout = int(self._requested_layout)",
    ]
    missing_scheduler = [fragment for fragment in required_scheduler if fragment not in scheduler_text]
    if missing_scheduler:
        raise RuntimeError(f"manual runtime observation fragments missing: {missing_scheduler}")
    forbidden_scheduler = [
        '"RUNTIME_LAYOUT confirm reason=%s layout=%s via=manual_profile_lock cell=%s"',
        "手动锁定；程序直接信任你设定的模式和宫格",
    ]
    present_scheduler = [fragment for fragment in forbidden_scheduler if fragment in scheduler_text]
    if present_scheduler:
        raise RuntimeError(f"manual runtime override fragments still present: {present_scheduler}")
    forbidden_window_manager = [
        'if requested_mode in {"windowed", "fullscreen"}:',
        "return requested_mode",
    ]
    present_window_manager = [fragment for fragment in forbidden_window_manager if fragment in window_manager_text]
    if present_window_manager:
        raise RuntimeError(f"window_manager still short-circuits actual mode detection: {present_window_manager}")
    required_fragments = [
        'self._current_mode = self._window_manager.detect_mode(self._window_info, "auto")',
        "self._sync_runtime_profile_state()",
        "def _runtime_profile_mismatch_details(self) -> list[str]:",
        'message="目标状态未匹配，已暂停等待处理"',
        "requested_mode 只表示调度器的目标约束，真实模式始终要靠现场窗口检测",
    ]
    missing = [
        fragment
        for fragment in required_fragments
        if fragment not in scheduler_text and fragment not in window_manager_text
    ]
    if missing:
        raise RuntimeError(f"manual-target closed-loop fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_profile_observation_reanchors_layout_detection_on_manual_lock() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _runtime_profile_observation_requires_fresh_probes(reason: str) -> bool:",
        '"manual_profile_lock",',
        '"resume_reconcile",',
        '"inspect_runtime",',
        "reanchor_for_layout_observation = sync_layout and self._runtime_profile_observation_requires_fresh_probes(reason)",
        "self._last_grid_probe = None",
        "self._last_zoom_probe = None",
        "self._current_index = 0",
        "self._active_cell = self._cells[0]",
        "RUNTIME_OBSERVE cleared stale probes and reanchored layout observation reason=%s original_index=%s",
        "self._current_index = original_index % len(self._cells)",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"runtime profile observation reanchor fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_runtime_status_reports_actual_target_and_closure() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        "def _profile_source_label(self) -> str:",
        "def _requested_runtime_profile_label(self) -> str:",
        "def _runtime_profile_closure_label(self) -> str:",
        '"profile_source": self._profile_source_label(),',
        '"requested_mode": self._requested_mode,',
        '"requested_layout": None if self._requested_layout is None else int(self._requested_layout),',
        '"requested_runtime_profile": self._requested_runtime_profile_label(),',
        '"closure_state": self._runtime_profile_closure_label(),',
        "已暂停：目标未匹配（实际",
        "控制: ",
        " | 目标: ",
        " | 闭环: ",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"runtime status closure fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_scheduler_accepts_external_control_stop_requests() -> dict[str, Any]:
    scheduler_text = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
    required_fragments = [
        'self._runtime_control_path = self._runtime_status_path.with_suffix(".control.json")',
        "def _consume_external_control_commands(self) -> None:",
        "def _read_external_control_payload(self) -> dict[str, object] | None:",
        'raw = control_path.read_text(encoding="utf-8-sig")',
        'if command_name == "stop":',
        'self._logger.warning("External control requested STOP origin=%s", origin)',
        "self._command_queue.put(HotkeyCommand.STOP_REQUEST)",
        "Ignoring malformed external control payload",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in scheduler_text]
    if missing:
        raise RuntimeError(f"scheduler external-control stop fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_fixed_layout_stop_script_prefers_graceful_control_file() -> dict[str, Any]:
    script_text = (PROJECT_ROOT / "platform_spike" / "scripts" / "stop_fixed_layout_runtime.py").read_text(
        encoding="utf-8"
    )
    required_fragments = [
        "def fixed_layout_control_path(",
        "def write_control_command(",
        "def wait_for_process_exit(",
        'origin="stop_fixed_layout_runtime.py"',
        '"action"] = "requested-graceful-stop"',
        '"forced-stop-after-graceful-timeout"',
        "controlRequested",
        "--graceful-timeout-seconds",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in script_text]
    if missing:
        raise RuntimeError(f"fixed-layout graceful stop fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_layout_switch_panel_open_retries_for_fullscreen_runtime_detect() -> dict[str, Any]:
    layout_switcher_text = (PROJECT_ROOT / "layout_switcher.py").read_text(encoding="utf-8")
    required_fragments = [
        '"open_layout_panel_helper"',
        '"open_layout_panel_retry"',
        "backend=layout_open",
        "打开面板必须带重试与辅助点击兜底",
        'timeout_seconds=1.6',
        'raise LayoutSwitchError("Timed out waiting for layout panel to become open")',
        "raise_on_timeout=False",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in layout_switcher_text]
    if missing:
        raise RuntimeError(f"layout-switch panel-open retry fragments missing: {missing}")
    return {"checked_fragments": len(required_fragments)}


def test_layout_switch_requires_cleared_scene() -> dict[str, Any]:
    layout_switcher_text = (PROJECT_ROOT / "layout_switcher.py").read_text(encoding="utf-8")
    app_text = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    required_layout_switcher = [
        "def _ensure_layout_switch_scene_is_clear(self, target_window) -> None:",
        "def _detect_active_grid_scene(self, preview_rect: Rect, *, preview_image: Image.Image) -> dict[str, object] | None:",
        "def _detect_zoomed_scene_state(self, preview_rect: Rect, *, preview_image: Image.Image) -> dict[str, object]:",
        "layout_switch guard allowing stable grid scene",
        "A live monitoring view is still open; close all monitoring views before switching layout.",
        "Could not confirm that the client has been cleared; the preview still looks like a dynamic scene.",
        "self._ensure_layout_switch_scene_is_clear(target_window)",
        'scene_cleared = actual_view == VisualViewState.UNKNOWN and float(metrics.get("flat_interface_like", 0.0)) == 1.0',
    ]
    missing_layout_switcher = [fragment for fragment in required_layout_switcher if fragment not in layout_switcher_text]
    if missing_layout_switcher:
        raise RuntimeError(f"layout-switch clear-scene guard fragments missing: {missing_layout_switcher}")

    required_app = [
        "Protected operation: manually close all live monitoring views first",
        "except LayoutSwitchError as exc:",
        "raise SystemExit(str(exc))",
        "config=config,\n                    detector=detector,",
    ]
    missing_app = [fragment for fragment in required_app if fragment not in app_text]
    if missing_app:
        raise RuntimeError(f"app.py layout-switch clear-scene wiring fragments missing: {missing_app}")
    return {
        "layout_switcher_fragments": len(required_layout_switcher),
        "app_fragments": len(required_app),
    }


def test_layout_switch_post_click_uses_fast_close_path() -> dict[str, Any]:
    layout_switcher_text = (PROJECT_ROOT / "layout_switcher.py").read_text(encoding="utf-8")
    required_fragments = [
        "layout_switch skipping post-click UIA refresh",
        "def _close_layout_panel_after_selection(",
        "close_layout_panel_after_select_toggle",
        "close_layout_panel_after_select_dismiss",
        "close_layout_panel_after_select_escape",
        "backend=layout_close_fast",
        "def _panel_open_quick(self, hwnd: int) -> bool:",
        "def _panel_title_rect_quick(self, root) -> Rect | None:",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in layout_switcher_text]
    if missing:
        raise RuntimeError(f"layout-switch fast post-click close fragments missing: {missing}")
    forbidden_fragments = [
        "self._collect_runtime_options(refreshed_root)",
        "refreshed_option = self._resolve_runtime_option(",
    ]
    present = [fragment for fragment in forbidden_fragments if fragment in layout_switcher_text]
    if present:
        raise RuntimeError(f"layout-switch still uses slow post-click UIA refresh: {present}")
    return {"checked_fragments": len(required_fragments)}


def build_report() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    run_check("compileall", test_compileall, results)
    run_check("compileall_scope", test_project_local_compileall_scope, results)
    run_check("load_configs", test_load_configs, results)
    run_check("fixed_layout_configs_are_isolated", test_fixed_layout_configs_are_isolated, results)
    run_check("fixed_layout_generator_supports_mode_split", test_fixed_layout_generator_supports_mode_split, results)
    run_check("fixed_layout_packager_scaffold_is_present", test_fixed_layout_packager_scaffold_is_present, results)
    run_check("internal_package_scaffold_is_present", test_internal_package_scaffold_is_present, results)
    run_check("fixed_layout_installer_scripts_are_present", test_fixed_layout_installer_scripts_are_present, results)
    run_check("fixed_layout_install_and_use_doc_is_present", test_fixed_layout_install_and_use_doc_is_present, results)
    run_check(
        "fixed_layout_windows_launcher_redirects_wsl_paths",
        test_fixed_layout_windows_launcher_redirects_wsl_paths,
        results,
    )
    run_check(
        "fixed_layout_instance_lock_auto_clears_stale_pid",
        test_fixed_layout_instance_lock_auto_clears_stale_pid,
        results,
    )
    run_check("windows_env_check_tracks_menu_source_assessment", test_windows_env_check_tracks_menu_source_assessment, results)
    run_check("windows_menu_source_inspector_scaffold_is_present", test_windows_menu_source_inspector_scaffold_is_present, results)
    run_check("regular_layout_counts", test_regular_layout_counts, results)
    run_check(
        "runtime_layout_override_bypasses_configured_template",
        test_runtime_layout_override_bypasses_configured_template,
        results,
    )
    run_check("custom_sequence", test_custom_sequence, results)
    run_check("column_major", test_column_major_alias_behavior, results)
    run_check("favorites_name_mapping", test_favorites_name_mapping, results)
    run_check("favorites_visible_name_filtering", test_favorites_visible_name_filtering, results)
    run_check("layout_template_switch", test_layout_template_switch, results)
    run_check("zoom_point_uses_middle_upper_bias", test_zoom_point_uses_middle_upper_bias, results)
    run_check(
        "layout12_fullscreen_lower_rows_shift_down",
        test_layout12_fullscreen_lower_rows_shift_down,
        results,
    )
    run_check("layout_switch_target_mapping", test_layout_switch_target_mapping, results)
    run_check("layout_switch_option_grouping", test_layout_switch_option_grouping, results)
    run_check("prepare_target_probe_order", test_prepare_target_captures_grid_probe_before_guard_check, results)
    run_check("auto_mode_prefers_windowed_ui_markers", test_auto_mode_prefers_windowed_ui_markers, results)
    run_check("runtime_action_path_semantics", test_runtime_action_path_semantics, results)
    run_check("zoom_confirm_failure_restarts_current_path", test_zoom_confirm_failure_restarts_current_path, results)
    run_check(
        "zoom_confirm_fast_path_accepts_runtime_zoom_signal",
        test_zoom_confirm_fast_path_accepts_runtime_zoom_signal,
        results,
    )
    run_check(
        "startup_runtime_sync_suppresses_input_guard_and_ignores_overlay_foreground",
        test_startup_runtime_sync_suppresses_input_guard_and_ignores_overlay_foreground,
        results,
    )
    run_check(
        "startup_runtime_layout_cache_bootstrap_is_wired",
        test_startup_runtime_layout_cache_bootstrap_is_wired,
        results,
    )
    run_check("paused_manual_next_refreshes_grid_probe_after_recover", test_paused_manual_next_refreshes_grid_probe_after_recover, results)
    run_check(
        "paused_manual_next_does_not_treat_zoomed_view_as_visible_grid",
        test_paused_manual_next_does_not_treat_zoomed_view_as_visible_grid,
        results,
    )
    run_check(
        "fast_locked_resume_does_not_treat_zoomed_view_as_grid",
        test_fast_locked_resume_does_not_treat_zoomed_view_as_grid,
        results,
    )
    run_check(
        "fast_locked_resume_does_not_trust_zoom_transition_grid_frame",
        test_fast_locked_resume_does_not_trust_zoom_transition_grid_frame,
        results,
    )
    run_check(
        "paused_grid_order_change_can_fall_back_to_prepare_target",
        test_paused_grid_order_change_can_fall_back_to_prepare_target,
        results,
    )
    run_check(
        "paused_grid_order_change_prefers_explicit_zoom_out_recovery",
        test_paused_grid_order_change_prefers_explicit_zoom_out_recovery,
        results,
    )
    run_check(
        "zoom_dwell_resume_prefers_explicit_zoom_out_recovery",
        test_zoom_dwell_resume_prefers_explicit_zoom_out_recovery,
        results,
    )
    run_check(
        "zoom_dwell_resume_skips_explicit_recovery_after_manual_return_to_grid",
        test_zoom_dwell_resume_skips_explicit_recovery_after_manual_return_to_grid,
        results,
    )
    run_check("start_pause_toggle_has_settle_lock", test_start_pause_toggle_has_settle_lock, results)
    run_check("next_hotkey_has_independent_fast_debounce", test_next_hotkey_has_independent_fast_debounce, results)
    run_check("single_function_hotkeys_use_keydown_hooks", test_single_function_hotkeys_use_keydown_hooks, results)
    run_check("clear_cooldown_hotkey_is_wired", test_clear_cooldown_hotkey_is_wired, results)
    run_check("runtime_grid_order_cycle_hotkey_is_wired", test_runtime_grid_order_cycle_hotkey_is_wired, results)
    run_check(
        "fixed_layout_configs_restrict_operator_grid_orders",
        test_fixed_layout_configs_restrict_operator_grid_orders,
        results,
    )
    run_check(
        "native_hotkey_manager_uses_register_hotkey_with_message_loop",
        test_native_hotkey_manager_uses_register_hotkey_with_message_loop,
        results,
    )
    run_check("next_request_can_buffer_before_pause_ack", test_next_request_can_buffer_before_pause_ack, results)
    run_check(
        "dwell_status_text_no_longer_repaints_countdown_every_second",
        test_dwell_status_text_no_longer_repaints_countdown_every_second,
        results,
    )
    run_check("select_status_text_no_longer_promises_fixed_half_second", test_select_status_text_no_longer_promises_fixed_half_second, results)
    run_check(
        "detected_issue_skip_mode_controls_auto_pause",
        test_detected_issue_skip_mode_controls_auto_pause,
        results,
    )
    run_check(
        "zoom_confirm_failure_keeps_partial_signal_until_handler",
        test_zoom_confirm_failure_keeps_partial_signal_until_handler,
        results,
    )
    run_check("low_texture_zoom_confirm_can_still_pass", test_low_texture_zoom_confirm_can_still_pass, results)
    run_check(
        "fullscreen_retry_sample_can_confirm_low_texture_zoom",
        test_fullscreen_retry_sample_can_confirm_low_texture_zoom,
        results,
    )
    run_check(
        "real_fullscreen_failure_page_sample_can_confirm_low_texture_zoom",
        test_real_fullscreen_failure_page_sample_can_confirm_low_texture_zoom,
        results,
    )
    run_check(
        "windowed_dominant_surface_sample_can_confirm_low_texture_zoom",
        test_windowed_dominant_surface_sample_can_confirm_low_texture_zoom,
        results,
    )
    run_check(
        "windowed_continuity_dominant_sample_can_confirm_zoom",
        test_windowed_continuity_dominant_sample_can_confirm_zoom,
        results,
    )
    run_check(
        "fullscreen_four_third_cell_sample_can_confirm_zoom_via_continuity_dominant_path",
        test_fullscreen_four_third_cell_sample_can_confirm_zoom_via_continuity_dominant_path,
        results,
    )
    run_check(
        "fullscreen_four_third_cell_retry_like_sample_is_not_misconfirmed_by_continuity_path",
        test_fullscreen_four_third_cell_retry_like_sample_is_not_misconfirmed_by_continuity_path,
        results,
    )
    run_check(
        "fullscreen_four_fourth_cell_sample_can_confirm_zoom_via_continuity_dominant_path",
        test_fullscreen_four_fourth_cell_sample_can_confirm_zoom_via_continuity_dominant_path,
        results,
    )
    run_check(
        "fullscreen_four_fourth_cell_retry_like_sample_is_not_misconfirmed_by_continuity_path",
        test_fullscreen_four_fourth_cell_retry_like_sample_is_not_misconfirmed_by_continuity_path,
        results,
    )
    run_check(
        "locked_fullscreen_transition_zoom_confirmed_supports_preview_failure_sample",
        test_locked_fullscreen_transition_zoom_confirmed_supports_preview_failure_sample,
        results,
    )
    run_check(
        "locked_fullscreen_transition_zoom_confirmed_rejects_retry_like_sample",
        test_locked_fullscreen_transition_zoom_confirmed_rejects_retry_like_sample,
        results,
    )
    run_check(
        "locked_fullscreen_six_transition_zoom_confirmed_supports_bottom_middle_sample",
        test_locked_fullscreen_six_transition_zoom_confirmed_supports_bottom_middle_sample,
        results,
    )
    run_check(
        "locked_fullscreen_six_transition_zoom_confirmed_supports_bottom_right_sample",
        test_locked_fullscreen_six_transition_zoom_confirmed_supports_bottom_right_sample,
        results,
    )
    run_check(
        "locked_fullscreen_six_transition_zoom_confirmed_rejects_retry_like_sample",
        test_locked_fullscreen_six_transition_zoom_confirmed_rejects_retry_like_sample,
        results,
    )
    run_check(
        "dynamic_scene_expansion_dominant_sample_can_confirm_zoom",
        test_dynamic_scene_expansion_dominant_sample_can_confirm_zoom,
        results,
    )
    run_check(
        "black_screen_soft_hint_can_confirm_zoom_without_retry",
        test_black_screen_soft_hint_can_confirm_zoom_without_retry,
        results,
    )
    run_check(
        "fullscreen_four_black_screen_retry_sample_can_confirm_zoom_without_pause",
        test_fullscreen_four_black_screen_retry_sample_can_confirm_zoom_without_pause,
        results,
    )
    run_check(
        "fullscreen_four_low_texture_no_hint_sample_can_confirm_zoom_after_resume",
        test_fullscreen_four_low_texture_no_hint_sample_can_confirm_zoom_after_resume,
        results,
    )
    run_check(
        "fullscreen_four_first_cell_black_screen_sample_can_confirm_zoom_without_pause",
        test_fullscreen_four_first_cell_black_screen_sample_can_confirm_zoom_without_pause,
        results,
    )
    run_check(
        "fullscreen_four_top_right_black_screen_sample_can_confirm_zoom_without_pause",
        test_fullscreen_four_top_right_black_screen_sample_can_confirm_zoom_without_pause,
        results,
    )
    run_check(
        "fullscreen_four_second_cell_black_screen_sample_can_confirm_zoom_without_pause",
        test_fullscreen_four_second_cell_black_screen_sample_can_confirm_zoom_without_pause,
        results,
    )
    run_check(
        "fullscreen_four_bottom_left_black_screen_sample_can_confirm_zoom_without_pause",
        test_fullscreen_four_bottom_left_black_screen_sample_can_confirm_zoom_without_pause,
        results,
    )
    run_check(
        "fullscreen_four_bottom_right_black_screen_sample_can_confirm_zoom_without_pause",
        test_fullscreen_four_bottom_right_black_screen_sample_can_confirm_zoom_without_pause,
        results,
    )
    run_check(
        "fullscreen_four_bottom_right_no_hint_sample_can_confirm_zoom_without_pause",
        test_fullscreen_four_bottom_right_no_hint_sample_can_confirm_zoom_without_pause,
        results,
    )
    run_check(
        "windowed_black_screen_retry_sample_can_confirm_zoom_without_recovery",
        test_windowed_black_screen_retry_sample_can_confirm_zoom_without_recovery,
        results,
    )
    run_check(
        "preview_failure_soft_hint_can_confirm_zoom_without_retry",
        test_preview_failure_soft_hint_can_confirm_zoom_without_retry,
        results,
    )
    run_check(
        "fullscreen_four_preview_failure_sample_can_confirm_zoom_without_pause",
        test_fullscreen_four_preview_failure_sample_can_confirm_zoom_without_pause,
        results,
    )
    run_check(
        "runtime_transition_zoom_confirm_can_relax_continuity",
        test_runtime_transition_zoom_confirm_can_relax_continuity,
        results,
    )
    run_check(
        "real_fullscreen_four_grid_failure_page_is_still_classified_as_grid",
        test_real_fullscreen_four_grid_failure_page_is_still_classified_as_grid,
        results,
    )
    run_check(
        "fullscreen_six_grid_flat_fallback_is_wired",
        test_fullscreen_six_grid_flat_fallback_is_wired,
        results,
    )
    run_check(
        "fullscreen_six_grid_flat_fallback_supports_dark_multicell_sample",
        test_fullscreen_six_grid_flat_fallback_supports_dark_multicell_sample,
        results,
    )
    run_check(
        "fullscreen_six_grid_flat_fallback_supports_ultra_flat_dark_sample",
        test_fullscreen_six_grid_flat_fallback_supports_ultra_flat_dark_sample,
        results,
    )
    run_check(
        "fullscreen_six_grid_flat_fallback_supports_weak_post_recover_sample",
        test_fullscreen_six_grid_flat_fallback_supports_weak_post_recover_sample,
        results,
    )
    run_check(
        "fullscreen_six_grid_flat_fallback_supports_real_runtime_weak_sample",
        test_fullscreen_six_grid_flat_fallback_supports_real_runtime_weak_sample,
        results,
    )
    run_check(
        "fullscreen_six_grid_flat_fallback_rejects_weak_dark_sample",
        test_fullscreen_six_grid_flat_fallback_rejects_weak_dark_sample,
        results,
    )
    run_check("action_path_docs", test_action_path_docs, results)
    run_check("build_release_include_list", test_build_release_include_list, results)
    run_check("semantic_texts", test_semantic_texts, results)
    run_check("runtime_guard_popup_auto_heal", test_runtime_guard_popup_auto_heal, results)
    run_check("runtime_guard_ignores_keywordless_same_process_aux_window", test_runtime_guard_ignores_keywordless_same_process_aux_window, results)
    run_check(
        "runtime_guard_foreground_aux_window_refocuses_without_escape",
        test_runtime_guard_foreground_aux_window_refocuses_without_escape,
        results,
    )
    run_check(
        "runtime_guard_allows_attached_foreground_surface",
        test_runtime_guard_allows_attached_foreground_surface,
        results,
    )
    run_check(
        "runtime_guard_allows_detached_vsclient_surface",
        test_runtime_guard_allows_detached_vsclient_surface,
        results,
    )
    run_check(
        "runtime_guard_allows_hex_titled_vsclient_foreground_surface",
        test_runtime_guard_allows_hex_titled_vsclient_foreground_surface,
        results,
    )
    run_check(
        "runtime_guard_allows_hex_titled_vsclient_foreground_surface_without_relation_hint",
        test_runtime_guard_allows_hex_titled_vsclient_foreground_surface_without_relation_hint,
        results,
    )
    run_check(
        "runtime_guard_ignores_status_overlay_foreground",
        test_runtime_guard_ignores_status_overlay_foreground,
        results,
    )
    run_check(
        "runtime_guard_ignores_automation_python_console_foreground",
        test_runtime_guard_ignores_automation_python_console_foreground,
        results,
    )
    run_check(
        "runtime_guard_ignores_automation_terminal_foreground",
        test_runtime_guard_ignores_automation_terminal_foreground,
        results,
    )
    run_check(
        "runtime_console_is_hardened_against_selection_freeze",
        test_runtime_console_is_hardened_against_selection_freeze,
        results,
    )
    run_check("window_manager_related_window_prefilter", test_window_manager_related_window_prefilter, results)
    run_check(
        "window_manager_prefers_exact_title_and_process_match",
        test_window_manager_prefers_exact_title_and_process_match,
        results,
    )
    run_check("runtime_guard_interface_auto_heal", test_runtime_guard_interface_auto_heal, results)
    run_check(
        "runtime_guard_respects_detected_issue_skip_mode",
        test_runtime_guard_respects_detected_issue_skip_mode,
        results,
    )
    run_check("flat_grid_expected_view_is_not_misclassified", test_flat_grid_expected_view_is_not_misclassified, results)
    run_check(
        "repeated_failure_grid_layout_can_still_be_classified_as_grid",
        test_repeated_failure_grid_layout_can_still_be_classified_as_grid,
        results,
    )
    run_check("zoom_probe_precedence_over_grid_probe", test_zoom_probe_precedence_over_grid_probe, results)
    run_check("fullscreen_layout_change_can_confirm_zoom", test_fullscreen_layout_change_can_confirm_zoom, results)
    run_check("runtime_guard_files_and_config", test_runtime_guard_files_and_config, results)
    run_check(
        "scheduler_tracks_soft_precheck_issue_for_zoom_confirm",
        test_scheduler_tracks_soft_precheck_issue_for_zoom_confirm,
        results,
    )
    run_check(
        "repeated_partial_zoom_confirm_respects_skip_mode",
        test_repeated_partial_zoom_confirm_respects_skip_mode,
        results,
    )
    run_check(
        "startup_cached_layout_reverify_is_delayed_past_early_cells",
        test_startup_cached_layout_reverify_is_delayed_past_early_cells,
        results,
    )
    run_check(
        "dwell_runtime_guard_prefers_lightweight_checks_until_mid_dwell",
        test_dwell_runtime_guard_prefers_lightweight_checks_until_mid_dwell,
        results,
    )
    run_check(
        "manual_target_cycles_skip_recovery_when_already_matched",
        test_manual_target_cycles_skip_recovery_when_already_matched,
        results,
    )
    run_check(
        "runtime_profile_pause_message_clears_after_manual_match",
        test_runtime_profile_pause_message_clears_after_manual_match,
        results,
    )
    run_check(
        "paused_manual_target_cycle_republishes_mismatch_state",
        test_paused_manual_target_cycle_republishes_mismatch_state,
        results,
    )
    run_check(
        "running_manual_target_mismatch_waits_until_next_prepare_target",
        test_running_manual_target_mismatch_waits_until_next_prepare_target,
        results,
    )
    run_check(
        "resume_request_is_blocked_until_runtime_profile_matches",
        test_resume_request_is_blocked_until_runtime_profile_matches,
        results,
    )
    run_check(
        "scheduler_uses_fast_window_refresh_for_runtime_view_checks",
        test_scheduler_uses_fast_window_refresh_for_runtime_view_checks,
        results,
    )
    run_check(
        "pause_ack_no_longer_forces_full_context_refresh",
        test_pause_ack_no_longer_forces_full_context_refresh,
        results,
    )
    run_check(
        "guard_stage_view_trusts_runtime_guard_result",
        test_guard_stage_view_trusts_runtime_guard_result,
        results,
    )
    run_check(
        "detector_reuses_preview_capture_for_runtime_classification",
        test_detector_reuses_preview_capture_for_runtime_classification,
        results,
    )
    run_check(
        "detector_downsamples_surface_metrics_before_heavy_stats",
        test_detector_downsamples_surface_metrics_before_heavy_stats,
        results,
    )
    run_check("status_overlay_auto_hide_config", test_status_overlay_auto_hide_config, results)
    run_check(
        "runtime_test_driver_prefers_send_keys_for_function_hotkeys",
        test_runtime_test_driver_prefers_send_keys_for_function_hotkeys,
        results,
    )
    run_check(
        "preview_failure_precheck_no_longer_skips_action_path",
        test_preview_failure_precheck_no_longer_skips_action_path,
        results,
    )
    run_check(
        "runtime_test_driver_keeps_real_dwell_timings",
        test_runtime_test_driver_keeps_real_dwell_timings,
        results,
    )
    run_check(
        "runtime_test_driver_tolerates_windows_log_lock",
        test_runtime_test_driver_tolerates_windows_log_lock,
        results,
    )
    run_check(
        "runtime_test_driver_restores_windowed_grid_between_scenarios",
        test_runtime_test_driver_restores_windowed_grid_between_scenarios,
        results,
    )
    run_check(
        "runtime_test_driver_does_not_escape_when_windowed_grid_is_already_visible",
        test_runtime_test_driver_does_not_escape_when_windowed_grid_is_already_visible,
        results,
    )
    run_check(
        "runtime_test_driver_can_override_layout_for_real_grid_regression",
        test_runtime_test_driver_can_override_layout_for_real_grid_regression,
        results,
    )
    run_check(
        "f9_runtime_driver_recovers_startup_prepare_not_grid_before_queue_check",
        test_f9_runtime_driver_recovers_startup_prepare_not_grid_before_queue_check,
        results,
    )
    run_check(
        "runtime_test_driver_can_follow_elevated_relaunch",
        test_runtime_test_driver_can_follow_elevated_relaunch,
        results,
    )
    run_check(
        "prepare_target_recovery_refreshes_grid_probe_only_after_true_grid_confirmation",
        test_prepare_target_recovery_refreshes_grid_probe_only_after_true_grid_confirmation,
        results,
    )
    run_check(
        "resume_locked_profile_reuses_prepare_target_grid_hint",
        test_resume_locked_profile_reuses_prepare_target_grid_hint,
        results,
    )
    run_check(
        "resume_pause_soft_peak_grid_thresholds_cover_manual_step_resume",
        test_resume_pause_soft_peak_grid_thresholds_cover_manual_step_resume,
        results,
    )
    run_check(
        "resume_manual_step_grid_like_sample_is_supported_after_recovery",
        test_resume_manual_step_grid_like_sample_is_supported_after_recovery,
        results,
    )
    run_check(
        "prepare_target_grid_fast_path_still_syncs_runtime_layout",
        test_prepare_target_grid_fast_path_still_syncs_runtime_layout,
        results,
    )
    run_check(
        "recent_runtime_layout_sync_prevents_grid_ready_churn",
        test_recent_runtime_layout_sync_prevents_grid_ready_churn,
        results,
    )
    run_check(
        "runtime_layout_visual_scoring_penalizes_dense_false_positive_layouts",
        test_runtime_layout_visual_scoring_penalizes_dense_false_positive_layouts,
        results,
    )
    run_check(
        "fullscreen_twelve_peak_support_is_wired",
        test_fullscreen_twelve_peak_support_is_wired,
        results,
    )
    run_check(
        "fullscreen_nine_peak_hint_can_unlock_runtime_layout",
        test_fullscreen_nine_peak_hint_can_unlock_runtime_layout,
        results,
    )
    run_check(
        "fullscreen_dense_layout_keep_guard_is_wired",
        test_fullscreen_dense_layout_keep_guard_is_wired,
        results,
    )
    run_check(
        "prepare_target_recovers_target_foreground_before_visual_classification",
        test_prepare_target_recovers_target_foreground_before_visual_classification,
        results,
    )
    run_check(
        "prepare_target_fullscreen_four_peak_hint_is_wired",
        test_prepare_target_fullscreen_four_peak_hint_is_wired,
        results,
    )
    run_check(
        "prepare_target_locked_fullscreen_grid_hint_is_wired",
        test_prepare_target_locked_fullscreen_grid_hint_is_wired,
        results,
    )
    run_check(
        "prepare_target_locked_fullscreen_six_flat_sample_is_supported",
        test_prepare_target_locked_fullscreen_six_flat_sample_is_supported,
        results,
    )
    run_check(
        "prepare_target_locked_fullscreen_six_ultra_flat_sample_is_supported",
        test_prepare_target_locked_fullscreen_six_ultra_flat_sample_is_supported,
        results,
    )
    run_check(
        "prepare_target_locked_fullscreen_six_resume_selected_grid_sample_is_supported",
        test_prepare_target_locked_fullscreen_six_resume_selected_grid_sample_is_supported,
        results,
    )
    run_check(
        "prepare_target_locked_fullscreen_six_weak_post_recover_sample_is_supported",
        test_prepare_target_locked_fullscreen_six_weak_post_recover_sample_is_supported,
        results,
    )
    run_check(
        "prepare_target_locked_fullscreen_six_real_runtime_weak_sample_is_supported",
        test_prepare_target_locked_fullscreen_six_real_runtime_weak_sample_is_supported,
        results,
    )
    run_check(
        "prepare_target_locked_fullscreen_six_weak_flat_sample_is_rejected",
        test_prepare_target_locked_fullscreen_six_weak_flat_sample_is_rejected,
        results,
    )
    run_check(
        "prepare_target_locked_fullscreen_six_selected_grid_method_accepts_resume_with_stale_mode_context",
        test_prepare_target_locked_fullscreen_six_selected_grid_method_accepts_resume_with_stale_mode_context,
        results,
    )
    run_check(
        "prepare_target_locked_fullscreen_six_selected_grid_method_accepts_without_resume_context",
        test_prepare_target_locked_fullscreen_six_selected_grid_method_accepts_without_resume_context,
        results,
    )
    run_check(
        "prepare_target_locked_fullscreen_six_weak_grid_method_accepts_real_runtime_sample",
        test_prepare_target_locked_fullscreen_six_weak_grid_method_accepts_real_runtime_sample,
        results,
    )
    run_check(
        "prepare_target_locked_fullscreen_six_weak_grid_method_accepts_without_resume_context",
        test_prepare_target_locked_fullscreen_six_weak_grid_method_accepts_without_resume_context,
        results,
    )
    run_check(
        "resume_hard_reset_ultra_flat_fullscreen_four_sample_is_supported",
        test_resume_hard_reset_ultra_flat_fullscreen_four_sample_is_supported,
        results,
    )
    run_check(
        "resume_hard_reset_soft_peak_fullscreen_four_sample_is_supported",
        test_resume_hard_reset_soft_peak_fullscreen_four_sample_is_supported,
        results,
    )
    run_check(
        "startup_soft_peak_fullscreen_four_sample_is_supported",
        test_startup_soft_peak_fullscreen_four_sample_is_supported,
        results,
    )
    run_check(
        "textured_multicell_fullscreen_six_sample_is_supported",
        test_textured_multicell_fullscreen_six_sample_is_supported,
        results,
    )
    run_check(
        "resume_hard_reset_textured_fullscreen_nine_sample_is_supported",
        test_resume_hard_reset_textured_fullscreen_nine_sample_is_supported,
        results,
    )
    run_check(
        "detector_fullscreen_four_peak_grid_classification_is_wired",
        test_detector_fullscreen_four_peak_grid_classification_is_wired,
        results,
    )
    run_check(
        "startup_borderline_fullscreen_four_sample_is_supported_by_detector",
        test_startup_borderline_fullscreen_four_sample_is_supported_by_detector,
        results,
    )
    run_check(
        "historical_fullscreen_four_sample_is_classified_as_grid",
        test_historical_fullscreen_four_sample_is_classified_as_grid,
        results,
    )
    run_check(
        "windowed_mode_detection_caches_ui_marker_probe",
        test_windowed_mode_detection_caches_ui_marker_probe,
        results,
    )
    run_check(
        "window_manager_tracks_detached_vsclient_render_surface",
        test_window_manager_tracks_detached_vsclient_render_surface,
        results,
    )
    run_check(
        "window_manager_focus_requires_foreground_confirmation",
        test_window_manager_focus_requires_foreground_confirmation,
        results,
    )
    run_check(
        "status_runtime_cleans_duplicate_overlay_processes",
        test_status_runtime_cleans_duplicate_overlay_processes,
        results,
    )
    run_check(
        "status_runtime_overlay_ensure_is_async",
        test_status_runtime_overlay_ensure_is_async,
        results,
    )
    run_check(
        "status_runtime_waits_for_overlay_before_first_action",
        test_status_runtime_waits_for_overlay_before_first_action,
        results,
    )
    run_check(
        "native_runtime_client_discards_stale_response_ids",
        test_native_runtime_client_discards_stale_response_ids,
        results,
    )
    run_check(
        "startup_warmup_uses_fast_refresh_after_first_sample",
        test_startup_warmup_uses_fast_refresh_after_first_sample,
        results,
    )
    run_check(
        "startup_warmup_clears_stale_manual_input_before_first_action",
        test_startup_warmup_clears_stale_manual_input_before_first_action,
        results,
    )
    run_check(
        "pointer_actions_skip_redundant_runtime_guard_rechecks",
        test_pointer_actions_skip_redundant_runtime_guard_rechecks,
        results,
    )
    run_check(
        "input_guard_tolerates_cursor_probe_access_denied",
        test_input_guard_tolerates_cursor_probe_access_denied,
        results,
    )
    run_check(
        "scheduler_runtime_layout_sync_is_not_fixed_to_config_layout",
        test_scheduler_runtime_layout_sync_is_not_fixed_to_config_layout,
        results,
    )
    run_check(
        "scheduler_clears_stale_runtime_favorites_on_read_failure",
        test_scheduler_clears_stale_runtime_favorites_on_read_failure,
        results,
    )
    run_check(
        "runtime_layout_manual_detect_stays_in_layout_switcher_only",
        test_runtime_layout_manual_detect_stays_in_layout_switcher_only,
        results,
    )
    run_check(
        "layout_panel_close_prefers_safe_paths_before_hotspot",
        test_layout_panel_close_prefers_safe_paths_before_hotspot,
        results,
    )
    run_check(
        "layout_switch_post_click_uses_fast_close_path",
        test_layout_switch_post_click_uses_fast_close_path,
        results,
    )
    run_check(
        "runtime_layout_detection_uses_safe_panel_open_close_only",
        test_runtime_layout_detection_uses_safe_panel_open_close_only,
        results,
    )
    run_check(
        "windowed_runtime_layout_sync_uses_multisignal_consensus_without_uia_panel",
        test_windowed_runtime_layout_sync_uses_multisignal_consensus_without_uia_panel,
        results,
    )
    run_check(
        "runtime_hotkeys_can_optionally_drive_client_ui_only_under_pause_guard",
        test_runtime_hotkeys_can_optionally_drive_client_ui_only_under_pause_guard,
        results,
    )
    run_check(
        "fullscreen_reconcile_prefers_observed_state_over_keep_heuristics",
        test_fullscreen_reconcile_prefers_observed_state_over_keep_heuristics,
        results,
    )
    run_check(
        "manual_runtime_targets_no_longer_override_actual_detection",
        test_manual_runtime_targets_no_longer_override_actual_detection,
        results,
    )
    run_check(
        "runtime_profile_observation_reanchors_layout_detection_on_manual_lock",
        test_runtime_profile_observation_reanchors_layout_detection_on_manual_lock,
        results,
    )
    run_check(
        "runtime_status_reports_actual_target_and_closure",
        test_runtime_status_reports_actual_target_and_closure,
        results,
    )
    run_check(
        "scheduler_accepts_external_control_stop_requests",
        test_scheduler_accepts_external_control_stop_requests,
        results,
    )
    run_check(
        "fixed_layout_stop_script_prefers_graceful_control_file",
        test_fixed_layout_stop_script_prefers_graceful_control_file,
        results,
    )
    run_check(
        "windowed_visual_shell_detector_distinguishes_samples",
        test_windowed_visual_shell_detector_distinguishes_samples,
        results,
    )
    run_check(
        "native_runtime_probe_scaffold_is_wired",
        test_native_runtime_probe_scaffold_is_wired,
        results,
    )
    run_check(
        "native_runtime_engine_defaults_are_enabled",
        test_native_runtime_engine_defaults_are_enabled,
        results,
    )
    run_check(
        "native_runtime_sidecar_command_surface_is_wired",
        test_native_runtime_sidecar_command_surface_is_wired,
        results,
    )
    run_check(
        "layout_switch_panel_open_retries_for_fullscreen_runtime_detect",
        test_layout_switch_panel_open_retries_for_fullscreen_runtime_detect,
        results,
    )
    run_check("layout_switch_requires_cleared_scene", test_layout_switch_requires_cleared_scene, results)
    passed = sum(1 for item in results if item["ok"])
    failed = len(results) - passed
    return {
        "project_root": str(PROJECT_ROOT),
        "passed": passed,
        "failed": failed,
        "results": results,
    }



def main() -> int:
    parser = argparse.ArgumentParser(description="Run project self tests and emit a JSON report")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Path to JSON report")
    args = parser.parse_args()

    report = build_report()
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
