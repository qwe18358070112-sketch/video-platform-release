@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d %~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0platform_spike\scripts\repair_fixed_layout_runtime.ps1" -TargetRoot "%CD%"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] Fixed-layout runtime repair failed with exit code %EXIT_CODE%.
  echo [INFO] Check logs\fixed_layout_runtime_verify_latest.json for details.
  pause
)
endlocal & exit /b %EXIT_CODE%
