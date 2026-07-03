@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title TGACH SERVER

call venv\scripts\activate.bat
:loop
if not exist logs mkdir logs
echo.
echo ======================================================
echo [%date% %time%] START SITE SERVER
echo Close this window to stop the site process.
echo ======================================================
echo Starting Server...
python -X utf8 -u -m uvicorn site_tgach.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "127.0.0.1" --timeout-keep-alive 30 --limit-concurrency 1000 --backlog 512 --log-level info
echo Server crashed! Restarting in 2 seconds...
timeout /t 2
goto loop
