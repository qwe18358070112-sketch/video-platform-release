@echo off
setlocal
cd /d %~dp0\..\..
python platform_spike\scripts\generate_fixed_layout_programs.py %*
endlocal
