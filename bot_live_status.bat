@echo off
setlocal
chcp 65001 >nul
set "ROOT=%~dp0"
set "NOPAUSE=0"

:parse_args
if "%~1"=="" goto :run
if /I "%~1"=="/nopause" set "NOPAUSE=1"
shift
goto :parse_args

:run
cd /d "%ROOT%"
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -X utf8 "bot_live_status.py"
) else (
    python -X utf8 "bot_live_status.py"
)
if "%NOPAUSE%"=="0" pause
