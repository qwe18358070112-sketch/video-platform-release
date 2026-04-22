@echo off
setlocal
cd /d %~dp0\..\..
python platform_spike\scripts\package_fixed_layout_programs.py %*
endlocal
