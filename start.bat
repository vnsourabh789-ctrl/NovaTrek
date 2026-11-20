@echo off
REM NovaTrek one-click launcher (Windows). Creates a venv, installs deps, starts the server.
cd /d "%~dp0"
if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv || (echo Python 3.11+ is required & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt || (echo Dependency install failed & pause & exit /b 1)
if not exist .env copy .env.example .env >nul
start "" http://127.0.0.1:8000
python -m novatrek
pause
