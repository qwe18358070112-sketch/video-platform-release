from __future__ import annotations

import argparse
import compileall
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_REPORT = PROJECT_ROOT / "tmp" / "public_smoke_test_report.json"


def run_check(name: str, ok: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def run_python(*args: str) -> tuple[int, str, str]:
    completed = subprocess.run(
        [str(PROJECT_ROOT / ".venv" / "bin" / "python"), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def build_report() -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    results.append(run_check("compileall", compileall.compile_dir(str(PROJECT_ROOT), quiet=1), "python sources compiled"))
    results.append(run_check("config_example_exists", (PROJECT_ROOT / "config.example.yaml").exists(), "config.example.yaml"))
    results.append(run_check("install_deps_scripts_exist", (PROJECT_ROOT / "install_deps.bat").exists() and (PROJECT_ROOT / "install_deps.sh").exists(), "install_deps.bat + install_deps.sh"))
    results.append(run_check("runtime_docs_exist", (PROJECT_ROOT / "README.md").exists() and (PROJECT_ROOT / "HOW_TO_USE.md").exists() and (PROJECT_ROOT / "README_DEPLOY.md").exists(), "README / HOW_TO_USE / README_DEPLOY"))
    results.append(run_check("fixed_layout_launchers_exist", (PROJECT_ROOT / "fixed_layout_programs" / "run_fixed_layout_selector.bat").exists() and (PROJECT_ROOT / "fixed_layout_programs" / "run_fixed_layout_selector.sh").exists(), "fixed layout launchers"))

    code, _out, err = run_python("app.py", "--help")
    results.append(run_check("app_help", code == 0, err or "help ok"))

    system_name = platform.system()
    if system_name == "Windows":
        results.append(run_check("platform_runtime_note", True, "Windows environment: runtime commands can be executed on a real desktop session"))
    else:
        code, out, err = run_python("app.py", "--run", "--mode", "auto")
        message = out or err
        results.append(
            run_check(
                "non_windows_runtime_guard",
                code != 0 and "runtime actions require a Windows desktop session" in message,
                message,
            )
        )

    passed = sum(1 for item in results if item["ok"])
    return {
        "project_root": str(PROJECT_ROOT),
        "platform": system_name,
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run public-repo smoke tests and emit a JSON report")
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
