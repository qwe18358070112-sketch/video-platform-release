#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


LAYOUTS = (12, 9, 6, 4)
MODES = ("fullscreen", "windowed")


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Create disaster-recovery backups for the eight fixed-layout programs."
    )
    parser.add_argument(
        "--source-root",
        default=str(repo_root),
        help="WSL source tree root to back up.",
    )
    parser.add_argument(
        "--windows-root",
        default="/mnt/d/video_platform_release_windows_runtime",
        help="Windows runtime tree root to back up.",
    )
    parser.add_argument(
        "--backup-root",
        default="/mnt/d/video_platform_backups",
        help="Directory outside the project where backup bundles are written.",
    )
    parser.add_argument(
        "--timestamp",
        default=dt.datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="Timestamp suffix for the backup directory.",
    )
    parser.add_argument(
        "--wsl-restore-parent",
        default="/home/lenovo/projects",
        help="Default WSL parent directory used by generated restore scripts.",
    )
    parser.add_argument(
        "--windows-restore-parent",
        default="/mnt/d",
        help="Default Windows parent directory used by generated restore scripts.",
    )
    return parser.parse_args()


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


def ensure_valid_root(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"{label} is not a directory: {path}")


def ensure_backup_root_safe(backup_root: Path, source_root: Path, windows_root: Path) -> None:
    for parent in (source_root, windows_root):
        try:
            backup_root.resolve().relative_to(parent.resolve())
        except ValueError:
            continue
        raise RuntimeError(
            f"Backup root must be outside the tree being archived. Invalid backup root: {backup_root}"
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_windows_path(path: Path) -> str:
    raw = str(path)
    if raw.startswith("/mnt/") and len(raw) >= 6 and raw[5].isalpha():
        drive = raw[5].upper() + ":"
        remainder = raw[6:].replace("/", "\\")
        if not remainder:
            return drive + "\\"
        return drive + remainder
    return raw.replace("/", "\\")


def count_tree(root: Path) -> dict[str, int]:
    file_count = 0
    dir_count = 0
    total_bytes = 0
    for current_root, dirs, files in os.walk(root):
        dir_count += len(dirs)
        for name in files:
            file_count += 1
            path = Path(current_root) / name
            try:
                total_bytes += path.stat().st_size
            except OSError:
                # Keep the backup moving even if a transient file disappears.
                pass
    return {
        "files": file_count,
        "directories": dir_count,
        "bytes": total_bytes,
    }


def get_git_revision(repo_root: Path) -> str | None:
    try:
        completed = run_checked(["git", "rev-parse", "HEAD"], cwd=repo_root)
    except Exception:
        return None
    revision = completed.stdout.strip()
    return revision or None


def detect_python_version(python_exe: Path) -> str | None:
    if not python_exe.exists():
        return None
    try:
        completed = run_checked([str(python_exe), "--version"])
    except Exception:
        return None
    return completed.stdout.strip() or completed.stderr.strip() or None


def create_tar_archive(source_root: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "tar",
        "-I",
        "pigz -1",
        "-cf",
        str(archive_path),
        "-C",
        str(source_root.parent),
        source_root.name,
    ]
    run_checked(command)


def render_program_matrix() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for layout in LAYOUTS:
        for mode in MODES:
            items.append(
                {
                    "name": f"{mode}_layout_{layout}",
                    "windows_launcher": f"fixed_layout_programs\\run_layout{layout}_{mode}_fixed.bat",
                    "wsl_launcher": f"fixed_layout_programs/run_layout{layout}_{mode}_fixed.sh",
                    "config": f"fixed_layout_programs/config.layout{layout}.{mode}.yaml",
                }
            )
    return items


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_restore_scripts(
    backup_dir: Path,
    *,
    windows_archive_name: str,
    source_archive_name: str,
    windows_root_name: str,
    source_root_name: str,
    default_windows_restore_parent: Path,
    default_wsl_restore_parent: Path,
) -> None:
    windows_parent_cmd = to_windows_path(default_windows_restore_parent)
    cmd_content = f"""@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "BACKUP_DIR=%~dp0"
set "ARCHIVE=%BACKUP_DIR%{windows_archive_name}"
set "TARGET_PARENT={windows_parent_cmd}"
if not "%~1"=="" set "TARGET_PARENT=%~1"
if not exist "%ARCHIVE%" (
  echo [ERROR] Missing archive: %ARCHIVE%
  exit /b 1
)
if exist "%TARGET_PARENT%\\{windows_root_name}" (
  echo [ERROR] Target already exists: %TARGET_PARENT%\\{windows_root_name}
  echo [INFO] Rename or remove the old directory first.
  exit /b 1
)
if not exist "%TARGET_PARENT%" mkdir "%TARGET_PARENT%"
tar -xzf "%ARCHIVE%" -C "%TARGET_PARENT%"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo [ERROR] Restore failed with exit code %EXIT_CODE%.
  exit /b %EXIT_CODE%
)
echo [OK] Restored to %TARGET_PARENT%\\{windows_root_name}
endlocal
"""
    write_file(backup_dir / "restore_windows_runtime.cmd", cmd_content)

    sh_content = f"""#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
ARCHIVE="${{BACKUP_DIR}}/{source_archive_name}"
TARGET_PARENT="${{1:-{default_wsl_restore_parent}}}"
TARGET_DIR="${{TARGET_PARENT}}/{source_root_name}"
if [[ ! -f "$ARCHIVE" ]]; then
  echo "[ERROR] Missing archive: $ARCHIVE" >&2
  exit 1
fi
if [[ -e "$TARGET_DIR" ]]; then
  echo "[ERROR] Target already exists: $TARGET_DIR" >&2
  echo "[INFO] Rename or remove the old directory first." >&2
  exit 1
fi
mkdir -p "$TARGET_PARENT"
tar -xzf "$ARCHIVE" -C "$TARGET_PARENT"
echo "[OK] Restored to $TARGET_DIR"
"""
    restore_wsl = backup_dir / "restore_wsl_source.sh"
    write_file(restore_wsl, sh_content)
    restore_wsl.chmod(0o755)

    restore_all_content = f"""#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
WSL_PARENT="${{1:-{default_wsl_restore_parent}}}"
WIN_PARENT="${{2:-{default_windows_restore_parent}}}"
"${{BACKUP_DIR}}/restore_wsl_source.sh" "$WSL_PARENT"
tar -xzf "${{BACKUP_DIR}}/{windows_archive_name}" -C "$WIN_PARENT"
echo "[OK] Restored Windows runtime to $WIN_PARENT/{windows_root_name}"
"""
    restore_all = backup_dir / "restore_all_from_wsl.sh"
    write_file(restore_all, restore_all_content)
    restore_all.chmod(0o755)


def write_readme(
    backup_dir: Path,
    *,
    windows_archive_name: str,
    source_archive_name: str,
    source_root: Path,
    windows_root: Path,
    default_wsl_restore_parent: Path,
    default_windows_restore_parent: Path,
) -> None:
    windows_default_target = f"{to_windows_path(default_windows_restore_parent)}\\{windows_root.name}"
    programs = render_program_matrix()
    program_lines = "\n".join(
        f"- `{item['name']}`: `{item['windows_launcher']}` / `{item['wsl_launcher']}` / `{item['config']}`"
        for item in programs
    )
    content = f"""# Fixed-Layout Disaster Recovery Backup

这是一份面向当前 8 个固定宫格程序的完整灾备备份，不是精简发布包。

包含内容：

- `Windows 可运行副本`：`{windows_archive_name}`
- `WSL 源码与环境`：`{source_archive_name}`
- `恢复脚本`：`restore_windows_runtime.cmd`、`restore_wsl_source.sh`、`restore_all_from_wsl.sh`
- `校验与清单`：`backup_manifest.json`、`CHECKSUMS.sha256`

备份来源：

- WSL 源目录：`{source_root}`
- Windows 运行目录：`{windows_root}`

8 个确认通过的程序：

{program_lines}

默认恢复位置：

- Windows 运行副本：`{windows_default_target}`
- WSL 源码目录：`{default_wsl_restore_parent / source_root.name}`

恢复方法：

1. 恢复 Windows 运行副本  
   在 Windows 中双击 `restore_windows_runtime.cmd`，或命令行运行：  
   `restore_windows_runtime.cmd D:\\`

2. 恢复 WSL 源码目录  
   在 WSL 中运行：  
   `bash restore_wsl_source.sh /home/lenovo/projects`

3. 一次性在 WSL 中恢复两边  
   `bash restore_all_from_wsl.sh /home/lenovo/projects /mnt/d`

恢复后建议做的验证：

1. Windows 运行副本目录执行 `verify_fixed_layout_runtime.cmd`
2. WSL 源码目录执行 `python3 self_test.py`
3. 分别启动以下 8 个 BAT 入口做抽样确认：
   - `run_layout12_fullscreen_fixed.bat`
   - `run_layout9_fullscreen_fixed.bat`
   - `run_layout6_fullscreen_fixed.bat`
   - `run_layout4_fullscreen_fixed.bat`
   - `run_layout12_windowed_fixed.bat`
   - `run_layout9_windowed_fixed.bat`
   - `run_layout6_windowed_fixed.bat`
   - `run_layout4_windowed_fixed.bat`
"""
    write_file(backup_dir / "BACKUP_README.md", content)


def build_manifest(
    *,
    backup_dir: Path,
    source_root: Path,
    windows_root: Path,
    source_archive: Path,
    windows_archive: Path,
) -> dict[str, object]:
    source_stats = count_tree(source_root)
    windows_stats = count_tree(windows_root)
    source_python = detect_python_version(source_root / ".venv" / "bin" / "python")
    windows_python = detect_python_version(windows_root / ".venv" / "Scripts" / "python.exe")
    manifest: dict[str, object] = {
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "backup_dir": str(backup_dir),
        "git_revision": get_git_revision(source_root),
        "programs": render_program_matrix(),
        "source_backup": {
            "root": str(source_root),
            "archive": source_archive.name,
            "sha256": sha256_file(source_archive),
            "archive_bytes": source_archive.stat().st_size,
            "tree": source_stats,
            "python": source_python,
        },
        "windows_backup": {
            "root": str(windows_root),
            "archive": windows_archive.name,
            "sha256": sha256_file(windows_archive),
            "archive_bytes": windows_archive.stat().st_size,
            "tree": windows_stats,
            "python": windows_python,
            "verify_cmd": "verify_fixed_layout_runtime.cmd",
        },
    }
    return manifest


def write_checksums(backup_dir: Path, *, source_archive: Path, windows_archive: Path) -> None:
    lines = [
        f"{sha256_file(source_archive)}  {source_archive.name}",
        f"{sha256_file(windows_archive)}  {windows_archive.name}",
    ]
    write_file(backup_dir / "CHECKSUMS.sha256", "\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    source_root = Path(args.source_root).resolve()
    windows_root = Path(args.windows_root).resolve()
    backup_root = Path(args.backup_root).resolve()
    default_wsl_restore_parent = Path(args.wsl_restore_parent)
    default_windows_restore_parent = Path(args.windows_restore_parent)

    ensure_valid_root(source_root, "source root")
    ensure_valid_root(windows_root, "windows root")
    ensure_backup_root_safe(backup_root, source_root, windows_root)

    backup_dir = backup_root / f"fixed_layout_disaster_backup_{args.timestamp}"
    if backup_dir.exists():
        raise FileExistsError(f"Backup directory already exists: {backup_dir}")
    backup_dir.mkdir(parents=True, exist_ok=False)

    source_archive = backup_dir / f"{source_root.name}_source_wsl.tar.gz"
    windows_archive = backup_dir / f"{windows_root.name}.tar.gz"

    create_tar_archive(source_root, source_archive)
    create_tar_archive(windows_root, windows_archive)
    write_checksums(backup_dir, source_archive=source_archive, windows_archive=windows_archive)
    write_restore_scripts(
        backup_dir,
        windows_archive_name=windows_archive.name,
        source_archive_name=source_archive.name,
        windows_root_name=windows_root.name,
        source_root_name=source_root.name,
        default_windows_restore_parent=default_windows_restore_parent,
        default_wsl_restore_parent=default_wsl_restore_parent,
    )
    write_readme(
        backup_dir,
        windows_archive_name=windows_archive.name,
        source_archive_name=source_archive.name,
        source_root=source_root,
        windows_root=windows_root,
        default_wsl_restore_parent=default_wsl_restore_parent,
        default_windows_restore_parent=default_windows_restore_parent,
    )
    manifest = build_manifest(
        backup_dir=backup_dir,
        source_root=source_root,
        windows_root=windows_root,
        source_archive=source_archive,
        windows_archive=windows_archive,
    )
    write_file(backup_dir / "backup_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    print(
        json.dumps(
            {
                "backup_dir": str(backup_dir),
                "source_archive": str(source_archive),
                "windows_archive": str(windows_archive),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
