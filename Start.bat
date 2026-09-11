@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Grok Org OS
echo ========================================
echo   Grok Org OS — portable desk GUI
echo ========================================
echo.
echo This folder is the portable app — copy it anywhere on Windows.
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python was not found on PATH.
  echo Install Python 3.11+ from https://www.python.org/downloads/
  echo Tip: check "Add python.exe to PATH" during setup.
  pause
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo ERROR: Python 3.11 or newer is required.
  python --version
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment .venv ...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create venv.
    pause
    exit /b 1
  )
)

echo Installing / updating dependencies ...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -e ".[dev,desktop]"
if errorlevel 1 (
  echo Desktop extras failed; installing core + dev ...
  ".venv\Scripts\python.exe" -m pip install -e ".[dev]"
  if errorlevel 1 (
    echo Dependency install failed.
    pause
    exit /b 1
  )
)

if not exist ".env" (
  if exist ".env.example" copy /Y ".env.example" ".env" >nul
)

echo.
echo Starting API + GUI at http://127.0.0.1:8000
echo   Docs: http://127.0.0.1:8000/docs
echo   Stop: close this window or run Stop.bat
echo.

REM Prefer native desktop window when pywebview works; else browser + uvicorn
".venv\Scripts\python.exe" -c "import webview" >nul 2>&1
if errorlevel 1 (
  start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"
  ".venv\Scripts\python.exe" -m uvicorn grok_org_os.api.app:app --host 127.0.0.1 --port 8000
) else (
  ".venv\Scripts\python.exe" -m grok_org_os.cli desktop --host 127.0.0.1 --port 8000
  if errorlevel 1 (
    echo Desktop window failed; falling back to browser...
    start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"
    ".venv\Scripts\python.exe" -m uvicorn grok_org_os.api.app:app --host 127.0.0.1 --port 8000
  )
)

pause
