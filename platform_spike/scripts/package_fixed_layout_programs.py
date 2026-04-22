#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path


LAYOUTS = (4, 6, 9, 12)
MODES = ("windowed", "fullscreen")
DEFAULT_PORTABLE_PYTHON_MINOR = "3.11"
DEFAULT_NATIVE_RUNTIME_RID = "win-x64"
PYTHON_IMPORT_SMOKE = (
    "import cv2, yaml, PIL, psutil, keyboard, pywinauto, win32api, win32gui, win32con, tkinter; "
    "print('portable-python-ok')"
)
PORTABLE_RUNTIME_REQUIRED = (
    ("portablePython", "python/python.exe"),
    ("nativeRuntime", "native_runtime/VideoPlatform.NativeProbe.exe"),
    ("tkinterPackage", "python/Lib/tkinter/__init__.py"),
    ("tclInit", "python/tcl/tcl8.6/init.tcl"),
    ("tkinterBinary", "python/_tkinter.pyd"),
    ("tclBinary", "python/tcl86t.dll"),
    ("tkBinary", "python/tk86t.dll"),
)

CORE_FILES = [
    "admin_utils.py",
    "app.py",
    "calibration.py",
    "common.py",
    "controller.py",
    "detector.py",
    "favorites_reader.py",
    "grid_mapper.py",
    "input_guard.py",
    "layout_switcher.py",
    "logger_setup.py",
    "native_runtime_client.py",
    "requirements.txt",
    "repair_fixed_layout_runtime.cmd",
    "runtime_guard.py",
    "scheduler.py",
    "status_overlay.py",
    "status_runtime.py",
    "video_platform_release/__init__.py",
    "video_platform_release/project_layout.py",
    "video_platform_release/fixed_layout/__init__.py",
    "video_platform_release/fixed_layout/runtime_verifier.py",
    "visual_shell_detector.py",
    "window_manager.py",
    "win_hotkeys.py",
    "install_deps.bat",
    "run_windows_runtime.sh",
    "verify_fixed_layout_runtime.cmd",
    "windows_bridge.ps1",
    "windows_bridge.sh",
    "platform_spike/scripts/repair_fixed_layout_runtime.ps1",
    "platform_spike/scripts/stop_fixed_layout_runtime.py",
    "platform_spike/scripts/verify_fixed_layout_runtime.py",
]

DOC_FILES = [
    "README.md",
    "README_DEPLOY.md",
    "HOW_TO_USE.md",
    "FIXED_LAYOUT_INSTALL_AND_USE.md",
    "FIXED_LAYOUT_PROGRAMS.md",
    "FIXED_LAYOUT_DEPLOY.md",
    "FIXED_LAYOUT_FREEZE_BASELINE.md",
    "fixed_layout_programs/README.md",
]

SUITE_INSTALLER_FILES = [
        "install_fixed_layout_suite.cmd",
        "install_fixed_layout_suite_gui.cmd",
        "uninstall_fixed_layout_suite.cmd",
        "repair_fixed_layout_runtime.cmd",
        "verify_fixed_layout_runtime.cmd",
        "platform_spike/scripts/install_fixed_layout_suite.ps1",
        "platform_spike/scripts/repair_fixed_layout_runtime.ps1",
        "platform_spike/scripts/uninstall_fixed_layout_suite.ps1",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package fixed-layout fallback programs into Windows-ready zip bundles."
    )
    parser.add_argument("--project-root", default=".", help="Project root")
    parser.add_argument(
        "--output-dir",
        default="dist/fixed_layout_bundles",
        help="Output directory for fixed-layout zip bundles.",
    )
    parser.add_argument(
        "--include-modes",
        action="store_true",
        help="Also package windowed/fullscreen split bundles if the generated configs exist.",
    )
    parser.add_argument(
        "--portable-runtime",
        dest="portable_runtime",
        action="store_true",
        default=platform.system() == "Windows",
        help="Bundle portable Python and a published NativeProbe sidecar. Enabled by default on Windows builders.",
    )
    parser.add_argument(
        "--source-only",
        dest="portable_runtime",
        action="store_false",
        help="Keep the old source-only bundle behavior without portable runtimes.",
    )
    parser.add_argument(
        "--python-minor",
        default=DEFAULT_PORTABLE_PYTHON_MINOR,
        help="Windows host Python minor version used for portable packaging, for example 3.11.",
    )
    parser.add_argument(
        "--native-runtime-rid",
        default=DEFAULT_NATIVE_RUNTIME_RID,
        help="RID used when publishing the self-contained NativeProbe sidecar.",
    )
    parser.add_argument(
        "--suite-name",
        default="video_platform_release_fixed_layout_suite.zip",
        help="Output file name for the all-in-one fixed-layout suite zip.",
    )
    return parser.parse_args()


def ensure_file(project_root: Path, relative: str) -> Path:
    path = project_root / relative
    if not path.exists():
        raise FileNotFoundError(f"Missing required file for fixed-layout package: {path}")
    return path


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_checked(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


def resolve_host_python(python_minor: str) -> tuple[list[str], str]:
    if platform.system() != "Windows":
        raise RuntimeError("Portable fixed-layout bundles must be built from a Windows Python environment.")

    launcher = ["py", f"-{python_minor}"]
    try:
        version = run_checked(
            launcher + ["-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"]
        ).stdout.strip()
    except Exception as exc:
        raise RuntimeError(
            f"Host Python {python_minor} was not found. Install Python {python_minor} on the packaging machine first."
        ) from exc
    if not version:
        raise RuntimeError(f"Failed to detect host Python patch version for Python {python_minor}.")
    return launcher, version


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def configure_embedded_python(python_dir: Path) -> None:
    pth_files = sorted(python_dir.glob("python*._pth"))
    if not pth_files:
        raise RuntimeError(f"Embedded Python _pth file was not found under {python_dir}")
    zip_entries = sorted(item.name for item in python_dir.glob("python*.zip"))
    # Add the package root so `python.exe app.py` can import sibling project modules
    # from the installed bundle root (runtime/python -> ../..).
    lines = zip_entries + [".", "..\\..", "Lib", "Lib/site-packages", "import site"]
    for pth_file in pth_files:
        write_text(pth_file, "\n".join(lines) + "\n")


def install_python_requirements(*, host_python: list[str], project_root: Path, python_dir: Path) -> None:
    site_packages = python_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    command = host_python + [
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-warn-script-location",
        "--target",
        str(site_packages),
        "-r",
        str(project_root / "requirements.txt"),
    ]
    run_checked(command, cwd=project_root)
    python_exe = python_dir / "python.exe"
    run_checked([str(python_exe), "-c", PYTHON_IMPORT_SMOKE], cwd=project_root)


def portable_runtime_missing(runtime_root: Path) -> list[str]:
    missing: list[str] = []
    for name, relative in PORTABLE_RUNTIME_REQUIRED:
        if not (runtime_root / relative).exists():
            missing.append(name)
    return missing


def ensure_existing_runtime_ready(*, project_root: Path, runtime_root: Path, python_minor: str) -> None:
    missing = portable_runtime_missing(runtime_root)
    if not missing:
        python_exe = runtime_root / "python" / "python.exe"
        try:
            run_checked([str(python_exe), "-c", PYTHON_IMPORT_SMOKE], cwd=project_root)
            return
        except Exception:
            missing = ["pythonSmoke"]

    if platform.system() != "Windows":
        raise RuntimeError(
            "Existing runtime is incomplete for portable packaging and cannot be repaired outside Windows. "
            f"Missing checks: {missing}"
        )

    host_python, _ = resolve_host_python(python_minor)
    python_dir = runtime_root / "python"
    python_dir.mkdir(parents=True, exist_ok=True)
    copy_tkinter_runtime(host_python=host_python, python_dir=python_dir)
    install_python_requirements(host_python=host_python, project_root=project_root, python_dir=python_dir)


def resolve_host_python_layout(host_python: list[str]) -> dict[str, str]:
    script = (
        "import json, sys, sysconfig; "
        "print(json.dumps({"
        "'base_prefix': sys.base_prefix, "
        "'stdlib': sysconfig.get_path('stdlib')"
        "}, ensure_ascii=False))"
    )
    completed = run_checked(host_python + ["-c", script])
    data = json.loads(completed.stdout.strip())
    if not isinstance(data, dict):
        raise RuntimeError("Failed to resolve host Python layout.")
    return {str(key): str(value) for key, value in data.items()}


def copy_tkinter_runtime(*, host_python: list[str], python_dir: Path) -> None:
    layout = resolve_host_python_layout(host_python)
    base_prefix = Path(layout["base_prefix"])
    stdlib = Path(layout["stdlib"])

    tkinter_package = stdlib / "tkinter"
    if not tkinter_package.exists():
        raise RuntimeError(f"Host tkinter package was not found: {tkinter_package}")
    shutil.copytree(tkinter_package, python_dir / "Lib" / "tkinter", dirs_exist_ok=True)

    tcl_root = base_prefix / "tcl"
    if not tcl_root.exists():
        raise RuntimeError(f"Host Tcl/Tk runtime directory was not found: {tcl_root}")
    shutil.copytree(tcl_root, python_dir / "tcl", dirs_exist_ok=True)

    for dll_name in ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll"):
        copied = False
        for candidate in (base_prefix / "DLLs" / dll_name, base_prefix / dll_name):
            if candidate.exists():
                shutil.copy2(candidate, python_dir / dll_name)
                copied = True
                break
        if not copied:
            raise RuntimeError(f"Host Tcl/Tk binary was not found: {dll_name}")

    python_exe = python_dir / "python.exe"
    run_checked([str(python_exe), "-c", "import tkinter; print('portable-tkinter-ok')"])


def publish_native_runtime(*, project_root: Path, native_runtime_rid: str, output_dir: Path) -> None:
    project_path = ensure_file(project_root, "native_runtime/VideoPlatform.NativeProbe/VideoPlatform.NativeProbe.csproj")
    command = [
        "dotnet",
        "publish",
        str(project_path),
        "-c",
        "Release",
        "-f",
        "net8.0-windows",
        "-r",
        native_runtime_rid,
        "--self-contained",
        "true",
        "/p:PublishSingleFile=true",
        "/p:IncludeNativeLibrariesForSelfExtract=true",
        "/p:DebugType=None",
        "/p:DebugSymbols=false",
        "-o",
        str(output_dir),
    ]
    run_checked(command, cwd=project_root)
    binary_path = output_dir / "VideoPlatform.NativeProbe.exe"
    if not binary_path.exists():
        raise RuntimeError(f"Published native runtime sidecar was not found: {binary_path}")


def prepare_portable_runtime(
    *,
    project_root: Path,
    output_dir: Path,
    python_minor: str,
    native_runtime_rid: str,
) -> Path:
    if platform.system() != "Windows":
        raise RuntimeError("Portable fixed-layout bundles currently require a Windows packaging host.")

    cache_root = output_dir / ".portable_runtime_cache"
    shutil.rmtree(cache_root, ignore_errors=True)
    cache_root.mkdir(parents=True, exist_ok=True)

    host_python, python_version = resolve_host_python(python_minor)
    python_archive = cache_root / f"python-{python_version}-embed-amd64.zip"
    python_url = f"https://www.python.org/ftp/python/{python_version}/python-{python_version}-embed-amd64.zip"
    download_file(python_url, python_archive)

    portable_root = cache_root / "runtime"
    python_dir = portable_root / "python"
    python_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(python_archive, "r") as archive:
        archive.extractall(python_dir)
    configure_embedded_python(python_dir)
    copy_tkinter_runtime(host_python=host_python, python_dir=python_dir)
    install_python_requirements(host_python=host_python, project_root=project_root, python_dir=python_dir)

    native_dir = portable_root / "native_runtime"
    native_dir.mkdir(parents=True, exist_ok=True)
    publish_native_runtime(project_root=project_root, native_runtime_rid=native_runtime_rid, output_dir=native_dir)

    manifest = {
        "portablePythonVersion": python_version,
        "portablePythonMinor": python_minor,
        "nativeRuntimeRid": native_runtime_rid,
        "nativeRuntimeBinary": "runtime/native_runtime/VideoPlatform.NativeProbe.exe",
    }
    write_text(portable_root / "portable_runtime_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return portable_root


def resolve_existing_runtime(project_root: Path, *, python_minor: str) -> Path | None:
    runtime_root = project_root / "runtime"
    if not runtime_root.exists():
        return None
    required = [runtime_root / relative for _, relative in PORTABLE_RUNTIME_REQUIRED[:2]]
    if not all(path.exists() for path in required):
        return None
    ensure_existing_runtime_ready(project_root=project_root, runtime_root=runtime_root, python_minor=python_minor)
    return runtime_root


def copy_file(project_root: Path, bundle_root: Path, relative: str) -> None:
    source = ensure_file(project_root, relative)
    destination = bundle_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def create_placeholder(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def materialize_bundle_tree(
    *,
    project_root: Path,
    bundle_root: Path,
    includes: list[str],
    portable_runtime_root: Path | None,
) -> None:
    for relative in includes:
        copy_file(project_root, bundle_root, relative)
    create_placeholder(bundle_root / "logs" / ".gitkeep")
    create_placeholder(bundle_root / "tmp" / ".gitkeep")
    if portable_runtime_root is not None:
        shutil.copytree(portable_runtime_root, bundle_root / "runtime", dirs_exist_ok=True)


def zip_stage(bundle_path: Path, bundle_root: Path) -> None:
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    stage_root = bundle_root.parent
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle_root.rglob("*")):
            if not path.is_file():
                continue
            archive.write(path, arcname=str(path.relative_to(stage_root)))


def bundle_includes(config_name: str, launcher_name: str) -> list[str]:
    shell_launcher = launcher_name.replace(".bat", ".sh")
    return CORE_FILES + DOC_FILES + [
        "fixed_layout_programs/README.md",
        "fixed_layout_programs/stop_fixed_layout_selector.bat",
        "fixed_layout_programs/stop_fixed_layout_selector.sh",
        f"fixed_layout_programs/{config_name}",
        f"fixed_layout_programs/{launcher_name}",
        f"fixed_layout_programs/{shell_launcher}",
    ]


def bundle_readme(layout: int, mode: str) -> str:
    title = f"固定布局独立包：{layout} 宫格 / {mode}"
    launcher = f"fixed_layout_programs/run_layout{layout}_{mode}_fixed.bat"
    return "\n".join(
        [
            f"# {title}",
            "",
            "这个独立包已经内置运行时，目标 Windows 电脑不需要预装 Python 或 .NET。",
            "",
            "## 使用方法",
            "",
            "1. 解压整个压缩包到本地目录，例如 `D:\\video_platform_release_layout_bundle`。",
            f"2. 直接双击 `{launcher}`。",
            "3. 如需停止当前固定布局实例，可执行：",
            "   `fixed_layout_programs/stop_fixed_layout_selector.bat <layout> <mode>`",
            "4. 如需检查或修复运行时，可执行：",
            "   `verify_fixed_layout_runtime.cmd`",
            "   `repair_fixed_layout_runtime.cmd`",
            "",
            "## 当前包信息",
            "",
            f"- layout: `{layout}`",
            f"- mode: `{mode}`",
            f"- launcher: `{launcher}`",
            "- portable runtime: `runtime/python/python.exe`",
            "- native sidecar: `runtime/native_runtime/VideoPlatform.NativeProbe.exe`",
            "",
        ]
    ) + "\n"


def write_bundle_metadata(bundle_root: Path, *, layout: int, mode: str) -> None:
    metadata = {
        "layout": layout,
        "mode": mode,
        "launcher": f"fixed_layout_programs/run_layout{layout}_{mode}_fixed.bat",
        "portablePython": "runtime/python/python.exe",
        "nativeRuntime": "runtime/native_runtime/VideoPlatform.NativeProbe.exe",
    }
    write_text(
        bundle_root / "fixed_layout_bundle_manifest.json",
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
    )
    write_text(bundle_root / "FIXED_LAYOUT_BUNDLE.md", bundle_readme(layout, mode))


def collect_suite_fixed_layout_files(project_root: Path, *, include_modes: bool) -> list[str]:
    files = [
        "fixed_layout_programs/README.md",
        "fixed_layout_programs/fixed_layout_manifest.json",
        "fixed_layout_programs/run_fixed_layout_selector.bat",
        "fixed_layout_programs/run_fixed_layout_selector.sh",
        "fixed_layout_programs/stop_fixed_layout_selector.bat",
        "fixed_layout_programs/stop_fixed_layout_selector.sh",
    ]
    for layout in LAYOUTS:
        files.extend(
            [
                f"fixed_layout_programs/config.layout{layout}.yaml",
                f"fixed_layout_programs/run_layout{layout}_fixed.bat",
                f"fixed_layout_programs/run_layout{layout}_fixed.sh",
            ]
        )
        if include_modes:
            for mode in MODES:
                mode_config = project_root / "fixed_layout_programs" / f"config.layout{layout}.{mode}.yaml"
                if not mode_config.exists():
                    continue
                files.extend(
                    [
                        f"fixed_layout_programs/config.layout{layout}.{mode}.yaml",
                        f"fixed_layout_programs/run_layout{layout}_{mode}_fixed.bat",
                        f"fixed_layout_programs/run_layout{layout}_{mode}_fixed.sh",
                    ]
                )
    return files


def suite_metadata(*, include_modes: bool, portable_runtime: bool, native_runtime_rid: str, output_name: str) -> str:
    payload = {
        "suiteBundle": output_name,
        "portableRuntime": portable_runtime,
        "nativeRuntimeRid": native_runtime_rid,
        "modesIncluded": include_modes,
        "validatedEntries": [
            {"layout": layout, "mode": mode}
            for layout in LAYOUTS
            for mode in (MODES if include_modes else ("auto",))
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    output_dir = (project_root / args.output_dir).resolve()
    portable_runtime_root = None
    if args.portable_runtime:
        portable_runtime_root = resolve_existing_runtime(project_root, python_minor=args.python_minor)
        if portable_runtime_root is None:
            portable_runtime_root = prepare_portable_runtime(
                project_root=project_root,
                output_dir=output_dir,
                python_minor=args.python_minor,
                native_runtime_rid=args.native_runtime_rid,
            )

    manifests: list[dict[str, str]] = []

    for layout in LAYOUTS:
        auto_config_name = f"config.layout{layout}.yaml"
        auto_launcher_name = f"run_layout{layout}_fixed.bat"
        bundle_path = output_dir / f"video_platform_release_layout{layout}_fixed.zip"
        with tempfile.TemporaryDirectory(prefix=f"layout{layout}_auto_") as temp_dir:
            bundle_root = Path(temp_dir) / "video_platform_release"
            bundle_root.mkdir(parents=True, exist_ok=True)
            materialize_bundle_tree(
                project_root=project_root,
                bundle_root=bundle_root,
                includes=bundle_includes(auto_config_name, auto_launcher_name),
                portable_runtime_root=portable_runtime_root,
            )
            write_bundle_metadata(bundle_root, layout=layout, mode="auto")
            zip_stage(bundle_path, bundle_root)
        manifests.append({"bundle": bundle_path.name, "layout": str(layout), "mode": "auto"})

        if args.include_modes:
            for mode in MODES:
                mode_config = f"config.layout{layout}.{mode}.yaml"
                mode_launcher = f"run_layout{layout}_{mode}_fixed.bat"
                if not (project_root / "fixed_layout_programs" / mode_config).exists():
                    continue
                mode_bundle = output_dir / f"video_platform_release_layout{layout}_{mode}_fixed.zip"
                with tempfile.TemporaryDirectory(prefix=f"layout{layout}_{mode}_") as temp_dir:
                    bundle_root = Path(temp_dir) / "video_platform_release"
                    bundle_root.mkdir(parents=True, exist_ok=True)
                    materialize_bundle_tree(
                        project_root=project_root,
                        bundle_root=bundle_root,
                        includes=bundle_includes(mode_config, mode_launcher),
                        portable_runtime_root=portable_runtime_root,
                    )
                    write_bundle_metadata(bundle_root, layout=layout, mode=mode)
                    zip_stage(mode_bundle, bundle_root)
                manifests.append({"bundle": mode_bundle.name, "layout": str(layout), "mode": mode})

    suite_bundle = output_dir / args.suite_name
    suite_includes = CORE_FILES + DOC_FILES + SUITE_INSTALLER_FILES + collect_suite_fixed_layout_files(
        project_root, include_modes=args.include_modes
    )
    with tempfile.TemporaryDirectory(prefix="fixed_layout_suite_") as temp_dir:
        bundle_root = Path(temp_dir) / "video_platform_release"
        bundle_root.mkdir(parents=True, exist_ok=True)
        materialize_bundle_tree(
            project_root=project_root,
            bundle_root=bundle_root,
            includes=suite_includes,
            portable_runtime_root=portable_runtime_root,
        )
        write_text(
            bundle_root / "fixed_layout_suite_manifest.json",
            suite_metadata(
                include_modes=args.include_modes,
                portable_runtime=args.portable_runtime,
                native_runtime_rid=args.native_runtime_rid,
                output_name=suite_bundle.name,
            ),
        )
        zip_stage(suite_bundle, bundle_root)

    manifest_path = output_dir / "fixed_layout_bundles_manifest.json"
    manifest_path.write_text(json.dumps(manifests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "outputDir": str(output_dir),
                "bundleCount": len(manifests),
                "suiteBundle": str(suite_bundle),
                "portableRuntime": args.portable_runtime,
                "manifest": str(manifest_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
