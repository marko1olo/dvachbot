@echo off
title TGACH SERVER
:loop
echo Starting Server...
uvicorn Dubsite_tgach.main:app --host 127.0.0.2 --port 7000 --proxy-headers --forwarded-allow-ips '*'
echo Server crashed! Restarting in 2 seconds...
timeout /t 2
goto loop