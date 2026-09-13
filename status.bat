@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title TGACH System Health Check

cd /d "%~dp0"
echo.
echo  ================================
echo    TGACH System Health Check
echo  ================================
echo.
echo  Running report script...
echo.

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -X utf8 "scripts\status_check.py"
) else (
    python -X utf8 "scripts\status_check.py"
)

echo.
echo  Report finished.
echo.

pause