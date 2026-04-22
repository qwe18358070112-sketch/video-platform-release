@echo off
setlocal
cd /d %~dp0
if exist .venv\Scripts\python.exe (
  call .venv\Scripts\activate.bat
)
python build_release.py --output dist\video_platform_release.zip
