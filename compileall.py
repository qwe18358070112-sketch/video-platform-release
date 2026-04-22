from __future__ import annotations

"""项目内 compileall 入口。

目的：
1. 保持用户习惯的 `python -m compileall 项目根目录` 命令不变。
2. 只校验项目源码，不递归编译 `.venv / dist / logs / tmp / __pycache__` 等运行产物目录。
3. 让静态检查结果真正反映“项目代码是否可编译”，而不是被本地虚拟环境和缓存文件干扰。
"""

import argparse
import os
import py_compile
from pathlib import Path


# 这些目录是当前交付目录中的运行期产物，不应作为项目源码参与 compileall。
EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "runtime",
    "__pycache__",
    "dist",
    "logs",
    "tmp",
}


def _is_excluded(path: Path) -> bool:
    return any(part.casefold() in EXCLUDED_DIR_NAMES for part in path.parts)


def _iter_python_files(root: Path):
    if root.is_file():
        if root.suffix.lower() == ".py" and not _is_excluded(root):
            yield root
        return

    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        # 原地裁剪目录，避免继续下钻到虚拟环境和日志产物里。
        dir_names[:] = [name for name in dir_names if name.casefold() not in EXCLUDED_DIR_NAMES]
        if _is_excluded(current_path):
            continue
        for file_name in file_names:
            if not file_name.lower().endswith(".py"):
                continue
            file_path = current_path / file_name
            if _is_excluded(file_path):
                continue
            yield file_path


def compile_file(file: str | Path, quiet: int = 0) -> bool:
    source = Path(file)
    if _is_excluded(source):
        return True
    try:
        py_compile.compile(str(source), doraise=True)
        if quiet <= 0:
            print(f"Compiling '{source}'...")
        return True
    except py_compile.PyCompileError as exc:
        if quiet <= 1:
            print(f"*** Error compiling '{source}'...")
            print(exc.msg)
        return False
    except Exception as exc:  # pragma: no cover - 运行期兜底
        if quiet <= 1:
            print(f"*** Error compiling '{source}'...")
            print(f"{type(exc).__name__}: {exc}")
        return False


def compile_dir(directory: str | Path, quiet: int = 0) -> bool:
    root = Path(directory)
    ok = True
    for file_path in _iter_python_files(root):
        ok = compile_file(file_path, quiet=quiet) and ok
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile project Python files while skipping runtime artifact directories")
    parser.add_argument("paths", nargs="*", default=["."], help="Files or directories to compile")
    parser.add_argument("-q", "--quiet", action="count", default=0, help="Increase quiet level")
    args = parser.parse_args(argv)

    ok = True
    for raw_path in args.paths:
        path = Path(raw_path)
        if path.is_dir():
            ok = compile_dir(path, quiet=args.quiet) and ok
        else:
            ok = compile_file(path, quiet=args.quiet) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
