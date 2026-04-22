@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d %~dp0
set "PYTHON_CMD="
if exist runtime\python\python.exe set "PYTHON_CMD=runtime\python\python.exe"
if exist .venv\Scripts\python.exe set "PYTHON_CMD=.venv\Scripts\python.exe"
if not defined PYTHON_CMD py -3.12 --version >nul 2>&1 && set "PYTHON_CMD=py -3.12"
if not defined PYTHON_CMD py -3.11 --version >nul 2>&1 && set "PYTHON_CMD=py -3.11"
if not defined PYTHON_CMD python --version >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
  echo [ERROR] Python runtime not found. Install the portable fixed-layout package or run install_deps.bat first.
  pause
  exit /b 1
)
%PYTHON_CMD% platform_spike\scripts\verify_fixed_layout_runtime.py --repo-root "%CD%"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] Fixed-layout runtime verification failed with exit code %EXIT_CODE%.
  echo [INFO] Check logs\fixed_layout_runtime_verify_latest.json for details.
  pause
)
endlocal & exit /b %EXIT_CODE%
