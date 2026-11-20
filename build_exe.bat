@echo off
REM Builds dist\NovaTrek.exe (single file, no Python needed to run it).
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt pyinstaller || exit /b 1
pyinstaller --noconfirm --clean --onefile --name NovaTrek ^
  --add-data "novatrek\web;novatrek\web" ^
  --collect-data airportsdata ^
  --collect-submodules uvicorn ^
  --icon NONE ^
  novatrek\__main__.py || exit /b 1
copy /y .env.example dist\.env.example >nul
echo.
echo Built: dist\NovaTrek.exe
