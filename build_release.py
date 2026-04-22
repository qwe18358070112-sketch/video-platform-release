from __future__ import annotations

"""生成精简可交付包。

目标：
1. 不把 .git / .venv / 测试截图 / 历史备份 / 大视频 一起塞进发布包。
2. 统一输出 zip + manifest，便于跨电脑分发与验收。
3. 打包后做 zip 校验，降低“发出去就坏包”的概率。
"""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


DEFAULT_INCLUDE = [
    "admin_utils.py",
    "app.py",
    "build_release.py",
    "compileall.py",
    "calibration.py",
    "common.py",
    "config.yaml",
    "config.example.yaml",
    "controller.py",
    "detector.py",
    "favorites_reader.py",
    "grid_mapper.py",
    "input_guard.py",
    "layout_switcher.py",
    "logger_setup.py",
    "README.md",
    "README_DEPLOY.md",
    "HOW_TO_USE.md",
    "LAYOUT_SWITCH_MANUAL.md",
    "MIGRATION_GUIDE.md",
    "CALIBRATION_GUIDE.md",
    "CODEX_LOCAL_ADMIN_PROMPT.txt",
    "requirements.txt",
    "WSL_MIGRATION.md",
    "runtime_guard.py",
    "scheduler.py",
    "self_test.py",
    "smoke_probe.py",
    "status_overlay.py",
    "status_runtime.py",
    "video_platform_release/__init__.py",
    "video_platform_release/project_layout.py",
    "video_platform_release/fixed_layout/__init__.py",
    "video_platform_release/fixed_layout/runtime_verifier.py",
    "window_manager.py",
    "WINDOWED_ACCEPTANCE.md",
    "提示词.txt",
    "提示词_增强版.txt",
    "install_deps.bat",
    "run_auto.bat",
    "calibrate_windowed.bat",
    "calibrate_fullscreen.bat",
    "inspect_windowed.bat",
    "inspect_fullscreen.bat",
    "dump_favorites.bat",
    "self_test.bat",
    "build_release.bat",
    "install_deps.sh",
    "self_test.sh",
    "build_release.sh",
    "windows_bridge.ps1",
    "windows_bridge.sh",
    "run_windows_runtime.sh",
    "calibrate_windows.sh",
    "inspect_windows_calibration.sh",
    "switch_layout_windows.sh",
    "dump_favorites_windows.sh",
    "FIXED_LAYOUT_PROGRAMS.md",
    "platform_spike/scripts/generate_fixed_layout_programs.py",
    "platform_spike/scripts/generate_fixed_layout_programs.cmd",
    "platform_spike/scripts/package_fixed_layout_programs.py",
    "platform_spike/scripts/package_fixed_layout_programs.cmd",
    "platform_spike/scripts/check_windows_platform_spike_env.ps1",
    "platform_spike/scripts/check_windows_platform_spike_env.cmd",
    "platform_spike/scripts/inspect_client_menu_sources.ps1",
    "platform_spike/scripts/inspect_client_menu_sources.cmd",
    "platform_spike/scripts/deploy_platform_spike_windows.ps1",
    "platform_spike/scripts/deploy_platform_spike_windows.cmd",
    "platform_spike/scripts/package_platform_spike_windows.py",
    "platform_spike/scripts/analyze_clientframe_auth_context.py",
    "platform_spike/scripts/stop_fixed_layout_runtime.py",
    "platform_spike/docs/CLIENTFRAME_AUTH_CONTEXT.md",
    "platform_spike/docs/CLIENT_MENU_SOURCE_DIAGNOSIS.md",
    "platform_spike/docs/WINDOWS_MULTI_HOST_DEPLOY.md",
    "fixed_layout_programs/README.md",
    "fixed_layout_programs/fixed_layout_manifest.json",
    "fixed_layout_programs/config.layout4.yaml",
    "fixed_layout_programs/config.layout6.yaml",
    "fixed_layout_programs/config.layout9.yaml",
    "fixed_layout_programs/config.layout12.yaml",
    "fixed_layout_programs/run_layout4_fixed.bat",
    "fixed_layout_programs/run_layout4_fixed.sh",
    "fixed_layout_programs/run_layout6_fixed.bat",
    "fixed_layout_programs/run_layout6_fixed.sh",
    "fixed_layout_programs/run_layout9_fixed.bat",
    "fixed_layout_programs/run_layout9_fixed.sh",
    "fixed_layout_programs/run_layout12_fixed.bat",
    "fixed_layout_programs/run_layout12_fixed.sh",
    "fixed_layout_programs/run_fixed_layout_selector.bat",
    "fixed_layout_programs/run_fixed_layout_selector.sh",
    "fixed_layout_programs/stop_fixed_layout_selector.bat",
    "fixed_layout_programs/stop_fixed_layout_selector.sh",
]

RUNTIME_PLACEHOLDERS = {
    "video_platform_release/logs/.gitkeep": b"",
    "video_platform_release/tmp/.gitkeep": b"",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_release(project_root: Path, output_zip: Path) -> dict:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for relative in DEFAULT_INCLUDE:
            source = project_root / relative
            if not source.exists():
                raise FileNotFoundError(f"Missing release file: {source}")
            arcname = f"video_platform_release/{relative}"
            zf.write(source, arcname)
            manifest.append(
                {
                    "path": arcname,
                    "size": source.stat().st_size,
                    "sha256": sha256_file(source),
                }
            )

        manifest_payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        zf.writestr("video_platform_release/release_manifest.json", manifest_payload)
        manifest.append(
            {
                "path": "video_platform_release/release_manifest.json",
                "size": len(manifest_payload),
                "sha256": sha256_bytes(manifest_payload),
            }
        )

        for arcname, payload in RUNTIME_PLACEHOLDERS.items():
            zf.writestr(arcname, payload)

    with zipfile.ZipFile(output_zip, "r") as zf:
        corrupted = zf.testzip()
        if corrupted is not None:
            raise RuntimeError(f"Zip verification failed at member: {corrupted}")
        names = zf.namelist()

    return {
        "output": str(output_zip),
        "file_count": len(names),
        "size": output_zip.stat().st_size,
        "top_level": sorted(set(name.split("/")[0] for name in names)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a lean release zip for cross-computer deployment")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parent), help="Project root")
    parser.add_argument("--output", default="dist/video_platform_release.zip", help="Output zip path")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    output_zip = Path(args.output)
    if not output_zip.is_absolute():
        output_zip = (project_root / output_zip).resolve()

    result = build_release(project_root, output_zip)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
