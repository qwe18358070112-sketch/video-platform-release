from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


LAYOUTS = (4, 6, 9, 12)
MODES = ("windowed", "fullscreen")


def fixed_layout_lock_name(layout: int, mode: str | None = None) -> str:
    if mode:
        return f"fixed_layout_runtime_{layout}_{mode}"
    return f"fixed_layout_runtime_{layout}"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_launcher(layout: int, mode: str | None = None) -> str:
    mode_args = f" --mode {mode}" if mode else ""
    config_name = f"fixed_layout_programs\\config.layout{layout}{'.' + mode if mode else ''}.yaml"
    return (
        "@echo off\n"
        "setlocal EnableExtensions EnableDelayedExpansion\n"
        "set \"LAUNCH_CONFIG="
        + config_name
        + "\"\n"
        "set \"WINDOWS_RUNTIME_ROOT=\"\n"
        "if defined VIDEO_PLATFORM_WINDOWS_WORKDIR if exist \"%VIDEO_PLATFORM_WINDOWS_WORKDIR%\\windows_bridge.ps1\" set \"WINDOWS_RUNTIME_ROOT=%VIDEO_PLATFORM_WINDOWS_WORKDIR%\"\n"
        "if not defined WINDOWS_RUNTIME_ROOT if exist \"D:\\video_platform_release_windows_runtime\\windows_bridge.ps1\" set \"WINDOWS_RUNTIME_ROOT=D:\\video_platform_release_windows_runtime\"\n"
        "if not defined WINDOWS_RUNTIME_ROOT if exist \"C:\\video_platform_release_windows_runtime\\windows_bridge.ps1\" set \"WINDOWS_RUNTIME_ROOT=C:\\video_platform_release_windows_runtime\"\n"
        "echo(%~dp0| findstr /I /C:\"\\\\wsl.localhost\\\\\" /C:\"\\\\wsl$\\\\\" >nul\n"
        "if %ERRORLEVEL% EQU 0 if not defined VIDEO_PLATFORM_WINDOWS_REDIRECTED (\n"
        "  if defined WINDOWS_RUNTIME_ROOT (\n"
        "    echo [INFO] Redirecting WSL launcher to Windows runtime: %WINDOWS_RUNTIME_ROOT%\n"
        "    set \"VIDEO_PLATFORM_WINDOWS_REDIRECTED=1\"\n"
        "    powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%WINDOWS_RUNTIME_ROOT%\\windows_bridge.ps1\" -RepoPath \"%WINDOWS_RUNTIME_ROOT%\" -Action run -AllowAutoElevate --config \"%LAUNCH_CONFIG%\" --layout "
        + str(layout)
        + mode_args
        + "\n"
        "    set \"EXIT_CODE=!ERRORLEVEL!\"\n"
        "    if not \"!EXIT_CODE!\"==\"0\" (\n"
        "      echo.\n"
        "      echo [ERROR] Launcher failed with exit code !EXIT_CODE!.\n"
        "      pause\n"
        "    )\n"
        "    exit /b !EXIT_CODE!\n"
        "  ) else (\n"
        "    echo [ERROR] Windows runtime copy not found.\n"
        "    echo [INFO] Please sync the project to D:\\video_platform_release_windows_runtime first.\n"
        "    echo [INFO] From WSL run: ./windows_bridge.sh sync\n"
        "    pause\n"
        "    exit /b 1\n"
        "  )\n"
        ")\n"
        "pushd \"%~dp0\\..\" >nul\n"
        "if ERRORLEVEL 1 (\n"
        "  echo [ERROR] Failed to enter launcher directory.\n"
        "  pause\n"
        "  exit /b 1\n"
        ")\n"
        "set \"PYTHON_CMD=\"\n"
        "if exist runtime\\python\\python.exe set \"PYTHON_CMD=runtime\\python\\python.exe\"\n"
        "if exist .venv\\Scripts\\python.exe set \"PYTHON_CMD=.venv\\Scripts\\python.exe\"\n"
        "if not defined PYTHON_CMD py -3.12 --version >nul 2>&1 && set \"PYTHON_CMD=py -3.12\"\n"
        "if not defined PYTHON_CMD py -3.11 --version >nul 2>&1 && set \"PYTHON_CMD=py -3.11\"\n"
        "if not defined PYTHON_CMD python --version >nul 2>&1 && set \"PYTHON_CMD=python\"\n"
        "if not defined PYTHON_CMD (\n"
        "  echo [ERROR] Python runtime not found. Install the portable fixed-layout package or run install_deps.bat first.\n"
        "  echo [INFO] If you started this from \\\\wsl.localhost\\..., use the Windows runtime copy under D:\\video_platform_release_windows_runtime.\n"
        "  popd\n"
        "  pause\n"
        "  exit /b 1\n"
        ")\n"
        "if exist platform_spike\\scripts\\verify_fixed_layout_runtime.py (\n"
        "  %PYTHON_CMD% platform_spike\\scripts\\verify_fixed_layout_runtime.py --repo-root \"%CD%\" --quick --quiet\n"
        "  set \"VERIFY_EXIT_CODE=!ERRORLEVEL!\"\n"
        "  if not \"!VERIFY_EXIT_CODE!\"==\"0\" (\n"
        "    echo.\n"
        "    echo [ERROR] Fixed-layout runtime self-check failed with exit code !VERIFY_EXIT_CODE!.\n"
        "    echo [INFO] Run verify_fixed_layout_runtime.cmd for a detailed diagnostic report.\n"
        "    popd\n"
        "    pause\n"
        "    exit /b !VERIFY_EXIT_CODE!\n"
        "  )\n"
        ")\n"
        f"%PYTHON_CMD% app.py --run --config {config_name} --layout {layout}{mode_args}\n"
        "set \"EXIT_CODE=!ERRORLEVEL!\"\n"
        "popd\n"
        "if not \"!EXIT_CODE!\"==\"0\" (\n"
        "  echo.\n"
        "  echo [ERROR] Launcher failed with exit code !EXIT_CODE!.\n"
        "  pause\n"
        ")\n"
        "endlocal & exit /b %EXIT_CODE%\n"
    )


def build_selector_launcher() -> str:
    return (
        "@echo off\n"
        "setlocal\n"
        "set LAYOUT=%~1\n"
        "set MODE=%~2\n"
        "if \"%LAYOUT%\"==\"\" goto usage\n"
        "if \"%MODE%\"==\"\" (\n"
        "  call \"%~dp0run_layout%LAYOUT%_fixed.bat\"\n"
        ") else (\n"
        "  call \"%~dp0run_layout%LAYOUT%_%MODE%_fixed.bat\"\n"
        ")\n"
        "exit /b %ERRORLEVEL%\n"
        ":usage\n"
        "echo Usage: run_fixed_layout_selector.bat ^<4^|6^|9^|12^> [windowed^|fullscreen]\n"
        "echo Examples:\n"
        "echo   run_fixed_layout_selector.bat 4\n"
        "echo   run_fixed_layout_selector.bat 9 fullscreen\n"
        "exit /b 1\n"
    )


def build_wsl_launcher(layout: int, mode: str | None = None) -> str:
    mode_args = f" --mode {mode}" if mode else ""
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "SCRIPT_DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"\n"
        "REPO_ROOT=\"$(cd \"$SCRIPT_DIR/..\" && pwd)\"\n"
        f"printf '[fixed-layout] starting layout={layout} mode={'auto' if mode is None else mode} on Windows runtime.\\n'\n"
        f"exec \"$REPO_ROOT/windows_bridge.sh\" run --config fixed_layout_programs/config.layout{layout}{'.' + mode if mode else ''}.yaml --layout {layout}{mode_args}\n"
    )


def build_wsl_selector_launcher() -> str:
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "SCRIPT_DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"\n"
        "LAYOUT=\"${1:-}\"\n"
        "MODE=\"${2:-}\"\n"
        "if [[ -z \"$LAYOUT\" ]]; then\n"
        "  echo \"Usage: run_fixed_layout_selector.sh <4|6|9|12> [windowed|fullscreen]\" >&2\n"
        "  exit 1\n"
        "fi\n"
        "if [[ -z \"$MODE\" ]]; then\n"
        "  exec bash \"$SCRIPT_DIR/run_layout${LAYOUT}_fixed.sh\"\n"
        "else\n"
        "  exec bash \"$SCRIPT_DIR/run_layout${LAYOUT}_${MODE}_fixed.sh\"\n"
        "fi\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate fixed-layout Windows automation presets.")
    parser.add_argument("--base-config", default="config.yaml", help="Base config file.")
    parser.add_argument("--output-dir", default="fixed_layout_programs", help="Output directory for presets.")
    parser.add_argument(
        "--include-modes",
        action="store_true",
        help="Also generate windowed/fullscreen split presets, expanding the fallback route from 4 programs to 8 programs.",
    )
    args = parser.parse_args()

    base_config_path = Path(args.base_config).resolve()
    output_dir = Path(args.output_dir).resolve()

    raw = yaml.safe_load(base_config_path.read_text(encoding="utf-8-sig"))
    raw.setdefault("profiles", {})
    raw.setdefault("grid", {})
    raw.setdefault("hotkeys", {})
    raw.setdefault("logging", {})
    raw.setdefault("detection", {})
    raw.setdefault("status_overlay", {})
    raw.setdefault("input_guard", {})

    readme_lines = [
        "# Fixed Layout Programs",
        "",
        "这一组是兜底路线：把程序按固定宫格拆成 4 套独立入口。",
        "",
        "设计目标：",
        "",
        "- 每套程序只负责一种布局：4 / 6 / 9 / 12",
        "- 运行时直接锁定 `--layout`，不再依赖布局热键切换",
        "- 禁用最容易把状态搅乱的 `F1 / F7`",
        "- 保留 `F2 / F8 / F9 / F10 / F11`，继续支持暂停、顺序切换、下一路、停止、紧急恢复",
        "",
        "对应入口：",
        "",
    ]
    manifest_entries: list[dict[str, str]] = []

    for layout in LAYOUTS:
        config = yaml.safe_load(yaml.safe_dump(raw, sort_keys=False, allow_unicode=False))
        config["profiles"]["active_mode"] = "auto"
        config["grid"]["layout"] = layout
        config["grid"]["order"] = "row_major"
        config["grid"]["custom_sequence"] = []
        config["grid"]["active_sequence_profile"] = ""
        config["grid"]["sequence_profiles"] = {}
        config["hotkeys"]["profile_source_toggle"] = "disabled"
        config["hotkeys"]["mode_cycle"] = "disabled"
        config["hotkeys"]["layout_cycle"] = "disabled"
        config["hotkeys"]["grid_order_cycle"] = "f8"
        config.setdefault("controls", {})
        config["controls"]["instance_lock_name"] = fixed_layout_lock_name(layout)
        config["controls"]["lock_runtime_layout_to_requested"] = True
        config["input_guard"]["enabled"] = False
        config["hotkeys"]["debounce_ms"] = 120
        config["hotkeys"]["next_cell_debounce_ms"] = 60
        config["logging"]["log_dir"] = f"logs/fixed_layout_{layout}"
        config["detection"]["screenshot_dir"] = f"logs/fixed_layout_{layout}/screenshots"
        config["status_overlay"]["status_file"] = f"tmp/runtime_status_layout_{layout}.json"
        config["status_overlay"]["auto_hide_ms"] = 0
        config["status_overlay"]["stale_hide_ms"] = 6000
        config.setdefault("favorites", {})
        config["favorites"]["enabled"] = False

        config_path = output_dir / f"config.layout{layout}.yaml"
        launcher_path = output_dir / f"run_layout{layout}_fixed.bat"
        write_text(config_path, yaml.safe_dump(config, sort_keys=False, allow_unicode=False))
        write_text(launcher_path, build_launcher(layout))
        wsl_launcher_path = output_dir / f"run_layout{layout}_fixed.sh"
        write_text(wsl_launcher_path, build_wsl_launcher(layout))
        wsl_launcher_path.chmod(0o755)

        readme_lines.append(f"- `run_layout{layout}_fixed.bat`：固定 {layout} 宫格程序")
        readme_lines.append(f"- `run_layout{layout}_fixed.sh`：在当前 WSL 仓库里启动固定 {layout} 宫格程序")
        manifest_entries.append(
            {
                "layout": str(layout),
                "mode": "auto",
                "config": config_path.name,
                "launcher": launcher_path.name,
                "wslLauncher": wsl_launcher_path.name,
                "instanceLockName": fixed_layout_lock_name(layout),
                "lockRuntimeLayoutToRequested": True,
            }
        )

        if args.include_modes:
            for mode in MODES:
                mode_config = yaml.safe_load(yaml.safe_dump(config, sort_keys=False, allow_unicode=False))
                mode_config["profiles"]["active_mode"] = mode
                mode_config["controls"]["instance_lock_name"] = fixed_layout_lock_name(layout, mode)
                mode_config["controls"]["lock_runtime_layout_to_requested"] = True
                mode_config["input_guard"]["enabled"] = False
                mode_config["grid"]["order"] = "row_major"
                mode_config["grid"]["custom_sequence"] = []
                mode_config["grid"]["active_sequence_profile"] = ""
                mode_config["grid"]["sequence_profiles"] = {}
                mode_config["hotkeys"]["grid_order_cycle"] = "f8"
                mode_config["hotkeys"]["debounce_ms"] = 120
                mode_config["hotkeys"]["next_cell_debounce_ms"] = 60
                mode_config["logging"]["log_dir"] = f"logs/fixed_layout_{layout}_{mode}"
                mode_config["detection"]["screenshot_dir"] = f"logs/fixed_layout_{layout}_{mode}/screenshots"
                mode_config["status_overlay"]["status_file"] = (
                    f"tmp/runtime_status_layout_{layout}_{mode}.json"
                )
                mode_config["status_overlay"]["auto_hide_ms"] = 0
                mode_config["status_overlay"]["stale_hide_ms"] = 6000
                mode_config.setdefault("favorites", {})
                mode_config["favorites"]["enabled"] = False
                mode_config_path = output_dir / f"config.layout{layout}.{mode}.yaml"
                mode_launcher_path = output_dir / f"run_layout{layout}_{mode}_fixed.bat"
                write_text(
                    mode_config_path,
                    yaml.safe_dump(mode_config, sort_keys=False, allow_unicode=False),
                )
                write_text(mode_launcher_path, build_launcher(layout, mode=mode))
                mode_wsl_launcher_path = output_dir / f"run_layout{layout}_{mode}_fixed.sh"
                write_text(mode_wsl_launcher_path, build_wsl_launcher(layout, mode=mode))
                mode_wsl_launcher_path.chmod(0o755)
                readme_lines.append(
                    f"- `run_layout{layout}_{mode}_fixed.bat`：固定 {layout} 宫格 + 固定 {mode} 程序"
                )
                readme_lines.append(
                    f"- `run_layout{layout}_{mode}_fixed.sh`：在当前 WSL 仓库里启动固定 {layout} 宫格 + 固定 {mode} 程序"
                )
                manifest_entries.append(
                    {
                        "layout": str(layout),
                        "mode": mode,
                        "config": mode_config_path.name,
                        "launcher": mode_launcher_path.name,
                        "wslLauncher": mode_wsl_launcher_path.name,
                        "instanceLockName": fixed_layout_lock_name(layout, mode),
                        "lockRuntimeLayoutToRequested": True,
                    }
                )

    readme_lines.extend(
        [
            "",
            "- `run_fixed_layout_selector.bat`：统一转发入口，按参数选择具体独立 BAT",
            "",
            "同时会生成：",
            "",
            "- `fixed_layout_manifest.json`：当前固定宫格入口清单，可用于多机分发和验收记录",
            "",
            "注意：",
            "",
            "- 这 4 套程序只保留“全屏 / 窗口”自动识别；宫格不再运行时自动识别，而是固定锁到各自程序对应的布局。",
            "- 但它们不再允许运行中切换宫格，也不会通过 F1/F7/F8 改目标。",
            "- 每套程序现在使用独立实例锁；4 宫格不会再被 12 宫格的旧锁挡住。",
            "- 如果目录里存在 `runtime/python/python.exe`，固定宫格 BAT 会优先使用随包 Python 运行时，不再依赖目标机预装 Python。",
            "- 如果现场继续被“全屏 / 窗口”识别扰动，可以执行 `python3 platform_spike/scripts/generate_fixed_layout_programs.py --include-modes`，直接扩成 8 套程序。",
            "- 也可以用 `run_fixed_layout_selector.bat <layout> [mode]` 作为统一入口；它只是转发到对应独立 BAT，不替代独立程序。",
            "",
        ]
    )
    write_text(output_dir / "README.md", "\n".join(readme_lines) + "\n")
    write_text(output_dir / "run_fixed_layout_selector.bat", build_selector_launcher())
    selector_sh = output_dir / "run_fixed_layout_selector.sh"
    write_text(selector_sh, build_wsl_selector_launcher())
    selector_sh.chmod(0o755)
    write_text(
        output_dir / "fixed_layout_manifest.json",
        json.dumps({"entries": manifest_entries}, ensure_ascii=False, indent=2)
        + "\n",
    )
    print(f"Generated fixed layout presets in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
