@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title TGChan Bot - External Watchdog

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

python -X utf8 -u bot_watchdog.py
set "WATCHDOG_EXIT=%ERRORLEVEL%"

if exist bot.stop (
    echo.
    echo [INFO] Controlled stop requested. Supervisor exits.
    del bot.stop
    exit /b 0
)

if "%WATCHDOG_EXIT%"=="0" (
    echo.
    echo [INFO] Supervisor exited normally. Window will stay open.
    exit /b 0
)

echo.
echo [WARNING] Supervisor stopped.
echo [INFO] Restart in 5 seconds...
timeout /t 5 >nul
goto loop
