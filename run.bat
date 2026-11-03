@echo off
rem Start the whole CloudMARL stack on Windows: double-click, or  run.bat [marl^|rr^|random]
rem Press Ctrl+C to stop everything.
cd /d "%~dp0"
if not "%~1"=="" set MODE=%~1
set PY=python
where python >nul 2>nul || set PY=py
%PY% run_local.py
pause
