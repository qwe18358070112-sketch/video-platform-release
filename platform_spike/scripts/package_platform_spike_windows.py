from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import zipfile


INCLUDE_PATHS = [
    "platform_spike/web_demo/webcontainer_probe.html",
    "platform_spike/web_demo/webcontainer_probe.js",
    "platform_spike/web_demo/platform_spike_poc.html",
    "platform_spike/web_demo/platform_spike_poc.js",
    "platform_spike/web_demo/implementation_package_harness.html",
    "platform_spike/web_demo/implementation_package_harness.js",
    "platform_spike/scripts/check_windows_platform_spike_env.ps1",
    "platform_spike/scripts/check_windows_platform_spike_env.cmd",
    "platform_spike/scripts/inspect_client_menu_sources.ps1",
    "platform_spike/scripts/inspect_client_menu_sources.cmd",
    "platform_spike/scripts/deploy_platform_spike_windows.ps1",
    "platform_spike/scripts/deploy_platform_spike_windows.cmd",
    "platform_spike/scripts/platform_quick_capture_bundle_windows.cmd",
    "platform_spike/scripts/platform_quick_capture_bundle.ps1",
    "platform_spike/scripts/platform_live_probe.ps1",
    "platform_spike/scripts/generate_fixed_layout_programs.py",
    "platform_spike/scripts/generate_fixed_layout_programs.cmd",
    "platform_spike/scripts/package_fixed_layout_programs.py",
    "platform_spike/scripts/package_fixed_layout_programs.cmd",
    "platform_spike/scripts/stop_fixed_layout_runtime.py",
    "platform_spike/docs/WINDOWS_MULTI_HOST_DEPLOY.md",
    "platform_spike/docs/CLIENT_MENU_SOURCE_DIAGNOSIS.md",
    "platform_spike/docs/GOV_NETWORK_OPERATOR_STEPS.md",
    "platform_spike/docs/LIVE_PLATFORM_PROBE.md",
    "platform_spike/docs/LOCAL_WEBCONTAINER_MENU_INJECTION.md",
    "platform_spike/README.md",
    "FIXED_LAYOUT_PROGRAMS.md",
    "fixed_layout_programs/README.md",
    "fixed_layout_programs/fixed_layout_manifest.json",
    "fixed_layout_programs/config.layout4.yaml",
    "fixed_layout_programs/config.layout6.yaml",
    "fixed_layout_programs/config.layout9.yaml",
    "fixed_layout_programs/config.layout12.yaml",
    "fixed_layout_programs/run_layout4_fixed.bat",
    "fixed_layout_programs/run_layout6_fixed.bat",
    "fixed_layout_programs/run_layout9_fixed.bat",
    "fixed_layout_programs/run_layout12_fixed.bat",
    "fixed_layout_programs/run_fixed_layout_selector.bat",
    "fixed_layout_programs/stop_fixed_layout_selector.bat",
]


def iter_harness_files(repo_root: Path) -> list[Path]:
    harness_root = repo_root / "platform_spike" / "web_demo" / "harness_packages"
    if not harness_root.is_dir():
        return []
    return [path for path in harness_root.rglob("*") if path.is_file()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Package platform_spike Windows deployment bundle.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root. Defaults to current working directory.",
    )
    parser.add_argument(
        "--output-root",
        default="tmp/windows_probe_packages",
        help="Directory where the bundle zip will be written.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_root = (repo_root / args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_name = f"platform_spike_windows_bundle_{timestamp}"
    bundle_dir = output_root / bundle_name
    bundle_dir.mkdir(parents=True, exist_ok=True)

    included: list[str] = []
    for relative in INCLUDE_PATHS:
        source = repo_root / relative
        if not source.is_file():
            raise SystemExit(f"Missing required file: {source}")
        target = bundle_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        included.append(relative)

    for source in iter_harness_files(repo_root):
        relative = source.relative_to(repo_root).as_posix()
        target = bundle_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        included.append(relative)

    manifest = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "bundleName": bundle_name,
        "includedFiles": sorted(included),
    }
    manifest_path = bundle_dir / "bundle_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    zip_path = output_root / f"{bundle_name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(bundle_dir.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(bundle_dir))

    print(f"BUNDLE_DIR={bundle_dir}")
    print(f"BUNDLE_ZIP={zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
