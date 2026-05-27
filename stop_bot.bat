@echo off
setlocal
set "ROOT=%~dp0"
set "LOCK=%ROOT%bot.lock"
set "STOP=%ROOT%bot.stop"
set "BOT_PID="
set "FORCE=0"
set "NOPAUSE=0"
set "HELP=0"
set "WAIT_SECONDS=%BOT_STOP_WAIT_SEC%"

if "%WAIT_SECONDS%"=="" set "WAIT_SECONDS=930"

:parse_args
if "%~1"=="" goto :parsed_args
if /I "%~1"=="/force" set "FORCE=1"
if /I "%~1"=="/nopause" set "NOPAUSE=1"
if /I "%~1"=="/?" set "HELP=1"
if /I "%~1"=="-?" set "HELP=1"
if /I "%~1"=="--help" set "HELP=1"
if /I "%~1"=="help" set "HELP=1"
shift
goto :parse_args

:parsed_args
if "%HELP%"=="1" goto :usage

if exist "%LOCK%" (
    set /p BOT_PID=<"%LOCK%"
)

if "%BOT_PID%"=="" (
    echo No bot.lock PID found. Nothing stopped.
    if "%NOPAUSE%"=="0" pause
    exit /b 0
)

> "%STOP%" echo stop requested
if "%FORCE%"=="0" (
    echo Controlled stop requested. Waiting up to %WAIT_SECONDS%s for queue drain and clean exit.
    echo Use stop_bot.bat /force for immediate hard kill.
    set "BOT_LOCK=%LOCK%"
    set "BOT_STOP_WAIT=%WAIT_SECONDS%"
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$lock=$env:BOT_LOCK; $wait=[double]$env:BOT_STOP_WAIT; $deadline=(Get-Date).AddSeconds($wait); while((Get-Date) -lt $deadline){ if(-not (Test-Path -LiteralPath $lock)){ Write-Host 'Bot exited cleanly.'; exit 0 }; Start-Sleep -Seconds 2 }; Write-Host 'Controlled stop wait timed out.'; exit 2"
    if not errorlevel 1 (
        if "%NOPAUSE%"=="0" pause
        exit /b 0
    )
    echo Controlled stop did not finish before timeout.
    echo No hard kill was performed. Use stop_bot.bat /force only if RAM queue loss is acceptable.
    if "%NOPAUSE%"=="0" pause
    exit /b 2
)

set "BOT_LOCK=%LOCK%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$pidText=$env:BOT_PID; $lock=$env:BOT_LOCK; if(-not ($pidText -match '^\d+$')){ Write-Host 'Bad bot.lock PID:' $pidText; exit 1 }; $leaf=[int]$pidText; $allProcs=Get-CimInstance Win32_Process; $root=$leaf; $current=$allProcs | Where-Object { $_.ProcessId -eq $leaf }; while($current){ $parent=$allProcs | Where-Object { $_.ProcessId -eq $current.ParentProcessId }; if(-not $parent){ break }; $cmd=[string]$parent.CommandLine; $currentCmd=[string]$current.CommandLine; if($cmd -like '*start_bot.bat*' -or $cmd -like '*bot_watchdog.py*' -or (($cmd -like '*main.py*') -and ($currentCmd -like '*main.py*'))){ $root=[int]$parent.ProcessId; $current=$parent; continue }; break }; $ids=@($root); do { $children=$allProcs | Where-Object { $ids -contains $_.ParentProcessId -and $ids -notcontains $_.ProcessId } | Select-Object -ExpandProperty ProcessId; if($children){ $ids += $children } } while($children); $ids=$ids | Sort-Object -Unique; Write-Host ('Stopping bot process tree: ' + ($ids -join ',')); foreach($processId in ($ids | Sort-Object -Descending)){ Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue }; Start-Sleep -Seconds 2; if(Test-Path -LiteralPath $lock){ Remove-Item -LiteralPath $lock -Force; Write-Host 'Removed bot.lock' }"

if errorlevel 1 (
    echo Stop tree resolver failed. Falling back to taskkill on bot PID %BOT_PID%.
    taskkill /PID %BOT_PID% /T /F
    timeout /t 2 >nul
    if exist "%LOCK%" (
        del "%LOCK%"
        echo Removed bot.lock
    )
)

if "%NOPAUSE%"=="0" pause
exit /b 0

:usage
echo Usage: stop_bot.bat [/force] [/nopause]
echo.
echo Default: request controlled stop and wait for RAM queue drain. No hard kill after timeout.
echo /force: immediate hard process-tree stop.
echo BOT_STOP_WAIT_SEC overrides the controlled-stop wait window.
if "%NOPAUSE%"=="0" pause
exit /b 0
