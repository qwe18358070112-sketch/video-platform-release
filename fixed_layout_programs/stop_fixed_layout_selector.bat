@echo off
setlocal
cd /d %~dp0\..
set "LAYOUT=%~1"
set "MODE=%~2"
if "%LAYOUT%"=="" goto usage
set "PYTHON_CMD="
if exist runtime\python\python.exe set "PYTHON_CMD=runtime\python\python.exe"
if exist .venv\Scripts\python.exe set "PYTHON_CMD=.venv\Scripts\python.exe"
if not defined PYTHON_CMD py -3.12 --version >nul 2>&1 && set "PYTHON_CMD=py -3.12"
if not defined PYTHON_CMD py -3.11 --version >nul 2>&1 && set "PYTHON_CMD=py -3.11"
if not defined PYTHON_CMD python --version >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
  echo [ERROR] Python runtime not found. Install the portable fixed-layout package or run install_deps.bat first.
  exit /b 1
)
if "%MODE%"=="" (
  %PYTHON_CMD% platform_spike\scripts\stop_fixed_layout_runtime.py --layout %LAYOUT% --include-legacy-lock
) else (
  %PYTHON_CMD% platform_spike\scripts\stop_fixed_layout_runtime.py --layout %LAYOUT% --mode %MODE% --include-legacy-lock
)
exit /b %ERRORLEVEL%
:usage
echo Usage: stop_fixed_layout_selector.bat ^<4^|6^|9^|12^> [windowed^|fullscreen]
exit /b 1
