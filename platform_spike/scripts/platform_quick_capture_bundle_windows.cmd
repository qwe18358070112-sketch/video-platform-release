@echo off
setlocal

set REPO_WSL_PATH=/home/lenovo/projects/video_platform_release
echo [platform_spike] 请保持客户端已登录，并在政务网环境下执行。
echo [platform_spike] 执行结束后，只需要把最后的 OPERATOR_RESULT 块发给我。
where wsl.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] wsl.exe not found. Please use Windows PowerShell and run platform_spike\scripts\platform_quick_capture_bundle.ps1 instead.
  exit /b 1
)
wsl.exe -d Ubuntu bash -lc "cd %REPO_WSL_PATH% && bash platform_spike/scripts/platform_quick_capture_bundle.sh %*"
