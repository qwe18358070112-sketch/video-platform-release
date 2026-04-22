@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_windows_platform_spike_env.ps1" %*
endlocal
