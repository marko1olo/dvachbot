@echo off
setlocal
chcp 65001 >nul
set "ROOT=%~dp0"
set "LOG_FILE=%ROOT%logs\bot_stdout_utf8.log"

if not exist "%LOG_FILE%" (
    if exist "%ROOT%logs\bot_runtime.log" (
        set "LOG_FILE=%ROOT%logs\bot_runtime.log"
    ) else (
        echo [!] Лог-файлы не найдены в %ROOT%logs\
        pause
        exit /b 1
    )
)

echo ========================================================
echo        ТГАЧ - ПРОСМОТР ЛОГОВ (БЕЗ ЗАВИСАНИЯ И СКРОЛЛ-ЛОКА)
echo ========================================================
echo Файл: %LOG_FILE%
echo.
echo 1. Открыть лог в Блокноте (Notepad / листать скроллом, Ctrl+F поиск)
echo 2. Показать последние 200 строк в этом окне (статично, без автоскролла)
echo 3. Показать только последние ОШИБКИ (ERROR / Crit / Traceback)
echo 4. Следить за новыми строками в реальном времени (live tail)
echo 5. Выход
echo.

set /p CHOICE="Выберите вариант [1-5] (по умолчанию 1): "
if "%CHOICE%"=="" set "CHOICE=1"

if "%CHOICE%"=="1" (
    echo Открываю в Блокноте...
    start notepad "%LOG_FILE%"
    exit /b 0
)

if "%CHOICE%"=="2" (
    echo.
    echo --- ПОСЛЕДНИЕ 200 СТРОК ---
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -Encoding UTF8 -LiteralPath $env:LOG_FILE -Tail 200 | Out-Host -Paging"
    echo.
    pause
    exit /b 0
)

if "%CHOICE%"=="3" (
    echo.
    echo --- ПОСЛЕДНИЕ ОШИБКИ И СБОИ ---
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -Encoding UTF8 -LiteralPath $env:LOG_FILE -Tail 500 | Select-String -Pattern 'ERROR|Crit fail|Traceback|Exception|WARNING' | Select-Object -Last 50"
    echo.
    pause
    exit /b 0
)

if "%CHOICE%"=="4" (
    echo.
    echo Запуск живого потока (Ctrl+C для остановки)...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -Encoding UTF8 -LiteralPath $env:LOG_FILE -Tail 100 -Wait"
    exit /b 0
)

exit /b 0
