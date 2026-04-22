@echo off
setlocal
cd /d %~dp0
set "SOURCE_ROOT=%~dp0."
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0platform_spike\scripts\install_fixed_layout_suite.ps1" -SourceRoot "%SOURCE_ROOT%" -Gui
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] Fixed-layout GUI installation failed with exit code %EXIT_CODE%.
  pause
)
endlocal & exit /b %EXIT_CODE%
