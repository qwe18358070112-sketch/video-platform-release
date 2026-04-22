@echo off
setlocal
cd /d %~dp0

set "BOOTSTRAP="
py -3.12 --version >nul 2>&1 && set "BOOTSTRAP=py -3.12"
if not defined BOOTSTRAP py -3.11 --version >nul 2>&1 && set "BOOTSTRAP=py -3.11"

if not defined BOOTSTRAP (
  echo [ERROR] Python 3.11 or 3.12 is required to install dependencies because pywin32 is not available for this machine's Python 3.13 RC.
  exit /b 1
)

if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -c "import sys; raise SystemExit(0 if sys.version_info[:2] in {(3, 11), (3, 12)} else 1)" >nul 2>&1
  if errorlevel 1 (
    echo [WARN] Existing virtual environment uses an unsupported Python version. Recreating .venv with a stable interpreter...
    rmdir /s /q .venv || goto :fail
  )
)

if not exist .venv\Scripts\python.exe (
  echo [INFO] Creating virtual environment with stable interpreter...
  %BOOTSTRAP% -m venv .venv || goto :fail
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto :fail
python -m pip install -r requirements.txt || goto :fail

echo [OK] Dependencies installed.
echo [INFO] Use .venv\Scripts\python.exe for compileall, self_test, calibration, and runtime commands if your system default python still points to 3.13 RC.
goto :eof

:fail
echo [ERROR] Dependency installation failed.
exit /b 1
