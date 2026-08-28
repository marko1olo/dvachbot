@echo off
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

python -X utf8 -u bot_watchdog.py

if exist bot.stop (
    echo.
    echo [INFO] Controlled stop requested (bot.stop detected).
    del bot.stop
    echo Press any key to close window...
    pause >nul
    exit /b 0
)

echo.
echo [WARNING] Supervisor/Bot stopped. Auto-restarting in 3 seconds...
echo (To completely stop the bot, create 'bot.stop' or close this console window)
timeout /t 3 /nobreak >nul
goto loop
