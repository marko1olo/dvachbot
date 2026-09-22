# start_site_tunnel.ps1 - Надежный сторожевой скрипт для SSH-туннеля сайта dvachbot
$ErrorActionPreference = "Continue"

# --- Параметры SSH ---
$sshHost = "root@62.84.100.97"

# Строго разделенные аргументы командной строки для OpenSSH
$sshArgs = @(
    "-N",
    "-4",
    "-oServerAliveInterval=10",
    "-oServerAliveCountMax=3",
    "-oExitOnForwardFailure=yes",
    "-oStrictHostKeyChecking=no",
    "-oTCPKeepAlive=yes",
    "-oConnectTimeout=10",
    "-R", "8080:127.0.0.1:8000",
    $sshHost
)

$retryDelay = 2
$maxDelay = 20

while ($true) {
    $startTime = [DateTime]::UtcNow
    Write-Host "--- [$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ЗАПУСК SSH ТУННЕЛЯ (8080 -> 127.0.0.1:8000) ---" -ForegroundColor Green

    # Запуск SSH процесса с правильной передачей аргументов
    & ssh.exe $sshArgs
    $exitCode = $LASTEXITCODE

    $duration = ([DateTime]::UtcNow - $startTime).TotalSeconds
    Write-Host "--- [$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ТУННЕЛЬ ЗАВЕРШИЛСЯ (код: $exitCode, аптайм: $([int]$duration)с) ---" -ForegroundColor Yellow

    # Если туннель проработал больше 60 секунд, считаем сессию успешной и сбрасываем задержку
    if ($duration -gt 60) {
        $retryDelay = 2
    } else {
        # При частых сбоях (например, порт 8080 на сервере еще занят half-open сокетом) увеличиваем паузу
        $retryDelay = [Math]::Min($retryDelay * 2, $maxDelay)
        Write-Host "--- [$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Обнаружен быстрый сбой. Ожидание освобождения порта: $retryDelay сек... ---" -ForegroundColor Red
    }

    Start-Sleep -Seconds $retryDelay
}