@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3.12"

if not defined PYTHON_CMD (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD goto :error

if not exist ".venv\Scripts\python.exe" (
    echo First launch: preparing the application...
    %PYTHON_CMD% -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
    ".venv\Scripts\python.exe" -m playwright install chromium || goto :error
)

".venv\Scripts\python.exe" avito_monitor.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Failed to start. Check that Python 3.10 or newer is installed.
pause
exit /b 1
