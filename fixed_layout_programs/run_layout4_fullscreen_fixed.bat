@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "LAUNCH_CONFIG=fixed_layout_programs\config.layout4.fullscreen.yaml"
set "WINDOWS_RUNTIME_ROOT="
if defined VIDEO_PLATFORM_WINDOWS_WORKDIR if exist "%VIDEO_PLATFORM_WINDOWS_WORKDIR%\windows_bridge.ps1" set "WINDOWS_RUNTIME_ROOT=%VIDEO_PLATFORM_WINDOWS_WORKDIR%"
if not defined WINDOWS_RUNTIME_ROOT if exist "D:\video_platform_release_windows_runtime\windows_bridge.ps1" set "WINDOWS_RUNTIME_ROOT=D:\video_platform_release_windows_runtime"
if not defined WINDOWS_RUNTIME_ROOT if exist "C:\video_platform_release_windows_runtime\windows_bridge.ps1" set "WINDOWS_RUNTIME_ROOT=C:\video_platform_release_windows_runtime"
echo(%~dp0| findstr /I /C:"\\wsl.localhost\\" /C:"\\wsl$\\" >nul
if %ERRORLEVEL% EQU 0 if not defined VIDEO_PLATFORM_WINDOWS_REDIRECTED (
  if defined WINDOWS_RUNTIME_ROOT (
    echo [INFO] Redirecting WSL launcher to Windows runtime: %WINDOWS_RUNTIME_ROOT%
    set "VIDEO_PLATFORM_WINDOWS_REDIRECTED=1"
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%WINDOWS_RUNTIME_ROOT%\windows_bridge.ps1" -RepoPath "%WINDOWS_RUNTIME_ROOT%" -Action run -AllowAutoElevate --config "%LAUNCH_CONFIG%" --layout 4 --mode fullscreen
    set "EXIT_CODE=!ERRORLEVEL!"
    if not "!EXIT_CODE!"=="0" (
      echo.
      echo [ERROR] Launcher failed with exit code !EXIT_CODE!.
      pause
    )
    exit /b !EXIT_CODE!
  ) else (
    echo [ERROR] Windows runtime copy not found.
    echo [INFO] Please sync the project to D:\video_platform_release_windows_runtime first.
    echo [INFO] From WSL run: ./windows_bridge.sh sync
    pause
    exit /b 1
  )
)
pushd "%~dp0\.." >nul
if ERRORLEVEL 1 (
  echo [ERROR] Failed to enter launcher directory.
  pause
  exit /b 1
)
set "PYTHON_CMD="
if exist runtime\python\python.exe set "PYTHON_CMD=runtime\python\python.exe"
if exist .venv\Scripts\python.exe set "PYTHON_CMD=.venv\Scripts\python.exe"
if not defined PYTHON_CMD py -3.12 --version >nul 2>&1 && set "PYTHON_CMD=py -3.12"
if not defined PYTHON_CMD py -3.11 --version >nul 2>&1 && set "PYTHON_CMD=py -3.11"
if not defined PYTHON_CMD python --version >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
  echo [ERROR] Python runtime not found. Install the portable fixed-layout package or run install_deps.bat first.
  echo [INFO] If you started this from \\wsl.localhost\..., use the Windows runtime copy under D:\video_platform_release_windows_runtime.
  popd
  pause
  exit /b 1
)
if exist platform_spike\scripts\verify_fixed_layout_runtime.py (
  %PYTHON_CMD% platform_spike\scripts\verify_fixed_layout_runtime.py --repo-root "%CD%" --quick --quiet
  set "VERIFY_EXIT_CODE=!ERRORLEVEL!"
  if not "!VERIFY_EXIT_CODE!"=="0" (
    echo.
    echo [ERROR] Fixed-layout runtime self-check failed with exit code !VERIFY_EXIT_CODE!.
    echo [INFO] Run verify_fixed_layout_runtime.cmd for a detailed diagnostic report.
    popd
    pause
    exit /b !VERIFY_EXIT_CODE!
  )
)
%PYTHON_CMD% app.py --run --config fixed_layout_programs\config.layout4.fullscreen.yaml --layout 4 --mode fullscreen
set "EXIT_CODE=!ERRORLEVEL!"
popd
if not "!EXIT_CODE!"=="0" (
  echo.
  echo [ERROR] Launcher failed with exit code !EXIT_CODE!.
  pause
)
endlocal & exit /b %EXIT_CODE%
