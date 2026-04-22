@echo off
setlocal
cd /d %~dp0
if exist .venv\Scripts\python.exe (
  call .venv\Scripts\activate.bat
)
python app.py --dump-favorites
