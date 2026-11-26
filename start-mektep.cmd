@echo off
setlocal
cd /d "%~dp0"
set "MEKTEP_DEMO=1"
if /i "%~1"=="normal" set "MEKTEP_DEMO=0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import main" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" launch.py
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo Mektep could not start. Check the error above and the instructions in README.md.
pause
exit /b 1
