@echo off
setlocal
set LAYOUT=%~1
set MODE=%~2
if "%LAYOUT%"=="" goto usage
if "%MODE%"=="" (
  call "%~dp0run_layout%LAYOUT%_fixed.bat"
) else (
  call "%~dp0run_layout%LAYOUT%_%MODE%_fixed.bat"
)
exit /b %ERRORLEVEL%
:usage
echo Usage: run_fixed_layout_selector.bat ^<4^|6^|9^|12^> [windowed^|fullscreen]
echo Examples:
echo   run_fixed_layout_selector.bat 4
echo   run_fixed_layout_selector.bat 9 fullscreen
exit /b 1
