@echo off
title TGACH System Health Check

echo.
echo  ================================
echo    TGACH System Health Check
echo  ================================
echo.
echo  Running report script...
echo.

:: Запускаем Python скрипт
python status_check.py

echo.
echo  Report finished.
echo.

:: Пауза, чтобы окно не закрылось сразу
pause