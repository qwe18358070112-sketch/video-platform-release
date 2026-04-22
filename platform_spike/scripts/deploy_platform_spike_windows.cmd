@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy_platform_spike_windows.ps1" %*
endlocal
