@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d %~dp0\..\..
set "PYTHON_CMD="
if exist .venv\Scripts\python.exe set "PYTHON_CMD=.venv\Scripts\python.exe"
if not defined PYTHON_CMD py -3.12 --version >nul 2>&1 && set "PYTHON_CMD=py -3.12"
if not defined PYTHON_CMD py -3.11 --version >nul 2>&1 && set "PYTHON_CMD=py -3.11"
if not defined PYTHON_CMD python --version >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
  echo [ERROR] Python runtime not found.
  exit /b 1
)
%PYTHON_CMD% platform_spike\scripts\create_fixed_layout_disaster_backup.py %*
endlocal
