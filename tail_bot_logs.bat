@echo off
setlocal
chcp 65001 >nul
set "ROOT=%~dp0"
set "MODE=stdout"

if not "%~1"=="" set "MODE=%~1"
if /I "%MODE%"=="/?" goto :usage
if /I "%MODE%"=="help" goto :usage
if /I "%MODE%"=="--help" goto :usage

set "TARGET=%ROOT%logs\bot_stdout_utf8.log"
if /I "%MODE%"=="stdout" set "TARGET=%ROOT%logs\bot_stdout_utf8.log"
if /I "%MODE%"=="runtime" set "TARGET=%ROOT%logs\bot_runtime.log"
if /I "%MODE%"=="supervisor" set "TARGET=%ROOT%logs\bot_supervisor.log"
if /I "%MODE%"=="heartbeat" set "TARGET=%ROOT%logs\bot_heartbeat.json"

if not exist "%TARGET%" (
    if exist "%ROOT%logs\bot_runtime.log" (
        set "TARGET=%ROOT%logs\bot_runtime.log"
    ) else (
        echo Log file not found: %TARGET%
        pause
        exit /b 1
    )
)

title TGACH tail %MODE%
echo Tailing %TARGET%
echo Ctrl+C stops tail only. Bot process is not touched.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -Encoding UTF8 -LiteralPath $env:TARGET -Tail 120 -Wait"
exit /b 0

:usage
echo Usage: tail_bot_logs.bat [stdout^|runtime^|supervisor^|heartbeat]
echo.
echo stdout     visible bot console output mirrored by watchdog (DEFAULT)
echo runtime    delivery_result, runtime_snapshot, durable queue events
echo supervisor watchdog decisions and restarts
echo heartbeat  last event-loop heartbeat json
exit /b 0
