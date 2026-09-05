@echo off
setlocal
cd /d "%~dp0"
set "YUNA_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%YUNA_PYTHON%" goto run
where py >nul 2>nul
if not errorlevel 1 (
  set "YUNA_PYTHON=py"
  goto run
)
where python >nul 2>nul
if not errorlevel 1 (
  set "YUNA_PYTHON=python"
  goto run
)
echo Python 3.10 or newer is required. Install Python, then open this file again.
pause
exit /b 1
:run
echo Yuna Clinic - http://127.0.0.1:8765
echo Keep this window open while using the clinic. Press Ctrl+C to stop.
"%YUNA_PYTHON%" server.py --open
pause
