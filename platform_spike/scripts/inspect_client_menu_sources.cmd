@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0inspect_client_menu_sources.ps1" %*
endlocal
