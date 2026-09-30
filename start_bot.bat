@echo off
if not defined CONHOST_WRAPPED (
    set "CONHOST_WRAPPED=1"
    start "" "%SystemRoot%\System32\conhost.exe" "%ComSpec%" /k call "%~f0" %*
    exit /b 0
)
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title TGChan Bot - External Watchdog

cd /d "%~dp0"
call venv\scripts\activate.bat
if not exist logs mkdir logs
if exist bot.stop del bot.stop

:loop
echo.
echo ======================================================
echo [%date% %time%] START BOT SUPERVISOR
echo Close this window to stop the whole bot tree.
echo stop_bot.bat is only a fallback for a stuck hidden process.
echo ======================================================

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -X utf8 -u bot_watchdog.py
) else (
    python -X utf8 -u bot_watchdog.py
)
set "WATCHDOG_EXIT=%ERRORLEVEL%"

if exist bot.stop (
    echo.
    echo [INFO] Controlled stop requested. Supervisor exits.
    del bot.stop
    exit /b 0
)

if "%WATCHDOG_EXIT%"=="0" (
    echo.
    echo ======================================================
    echo [INFO] Bot Supervisor exited cleanly with code 0.
    echo Another instance is already running or stop was confirmed.
    echo To stop the running instance, run stop_bot.bat.
    echo ======================================================
    echo Press any key to close this window...
    pause >nul
    exit /b 0
)

echo.
echo [WARNING] Bot Supervisor process exited with code %WATCHDOG_EXIT%.
echo [INFO] Self-healing restart in 3 seconds...
timeout /t 3 >nul
goto loop
