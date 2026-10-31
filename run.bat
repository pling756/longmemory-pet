@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" app.py %*
    exit /b 0
)

where pythonw >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.10+ and run:
    echo   python -m venv .venv
    echo   .venv\Scripts\python -m pip install -r requirements.txt
    pause
    exit /b 1
)

start "" pythonw app.py %*
exit /b 0
