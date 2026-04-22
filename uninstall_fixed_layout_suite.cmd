@echo off
setlocal
cd /d %~dp0
set "INSTALL_ROOT=%~dp0."
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0platform_spike\scripts\uninstall_fixed_layout_suite.ps1" -InstallRoot "%INSTALL_ROOT%" -Gui
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] Fixed-layout suite uninstall failed with exit code %EXIT_CODE%.
  pause
)
endlocal & exit /b %EXIT_CODE%
