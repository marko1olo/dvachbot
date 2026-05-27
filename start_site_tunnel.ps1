$ErrorActionPreference = "Stop" # Принудительно останавливаемся на ошибке

# --- Параметры SSH ---
$sshHost = "root@62.84.100.97"
$sshRemoteForward = "-R 8080:127.0.0.1:8000"

# --- Опции SSH (для надежности) ---
# `-o` указывает опции. Здесь мы их держим в массиве, чтобы PowerShell их не перепутал.
$sshOptions = @(
    "-N"
    "-4"
    "-o ServerAliveInterval=10"
    "-o ServerAliveCountMax=3"
    "-o ExitOnForwardFailure=no" # <--- Твоя новая опция для теста
    "-o StrictHostKeyChecking=no"
    "-o TCPKeepAlive=yes"
    "-o ConnectTimeout=10"
)

# --- Основной цикл ---
while ($true) {
    Write-Host "--- [$(Get-Date)] ЗАПУСК ТОННЕЛЯ (OPTIMIZED) ---" -ForegroundColor Green

    try {
        # @() - это "Splatting". Мы передаем массив опций напрямую в команду ssh, 
        # и PowerShell корректно их интерпретирует как отдельные аргументы.
        
        & ssh $sshOptions $sshRemoteForward $sshHost 
    }
    catch {
        Write-Host "--- [$(Get-Date)] ОШИБКА SSH ИЛИ РАЗРЫВ СВЯЗИ. ---" -ForegroundColor Red
        Write-Host "Сообщение об ошибке: $($_.Exception.Message)" -ForegroundColor Red
    }

    Write-Host "--- [$(Get-Date)] РЕСТАРТ ЧЕРЕЗ 2 СЕК... ---" -ForegroundColor Red
    Start-Sleep -Seconds 2
}