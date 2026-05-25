# MTC Casilla Bot — Instalar tarea programada en Windows Task Scheduler
# Ejecutar COMO ADMINISTRADOR una sola vez.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\instalar-tarea-programada.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\instalar-tarea-programada.ps1 -Hora "09:00"

param(
    [string]$Hora = "08:00"   # Hora de ejecución diaria (HH:mm, 24h)
)

$TaskName   = "MTC-Casilla-Bot-Daily"
$ScriptPath = "C:\PROGRAMACION\RESOLVE\Resolve\scripts\run-daily.ps1"
$WorkDir    = "C:\PROGRAMACION\RESOLVE\Resolve"
$PsExe      = "powershell.exe"
$PsArgs     = "-NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`""

Write-Host ""
Write-Host "=== Instalando tarea programada MTC Casilla Bot ===" -ForegroundColor Cyan
Write-Host "Nombre : $TaskName"
Write-Host "Script : $ScriptPath"
Write-Host "Hora   : $Hora (diario)"
Write-Host ""

# Verificar que el script existe
if (-not (Test-Path $ScriptPath)) {
    Write-Host "ERROR: No se encontró el script en $ScriptPath" -ForegroundColor Red
    exit 1
}

# Eliminar tarea anterior si existe
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Eliminando tarea anterior..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Crear trigger diario a la hora indicada
$Trigger  = New-ScheduledTaskTrigger -Daily -At $Hora

# Acción: ejecutar PowerShell con el script
$Action   = New-ScheduledTaskAction `
    -Execute $PsExe `
    -Argument $PsArgs `
    -WorkingDirectory $WorkDir

# Configuración: ejecutar aunque no haya usuario logueado,
# no detener si lleva mucho tiempo, ejecutar perdido si la PC estaba apagada
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew

# Principal: usuario actual, nivel más alto si es admin
$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Highest

# Registrar
try {
    Register-ScheduledTask `
        -TaskName  $TaskName `
        -Trigger   $Trigger `
        -Action    $Action `
        -Settings  $Settings `
        -Principal $Principal `
        -Description "Scraping diario de notificaciones MTC Casilla Bot" `
        -Force | Out-Null

    Write-Host ""
    Write-Host "Tarea registrada correctamente." -ForegroundColor Green
    Write-Host ""
    Write-Host "Para verificarla:" -ForegroundColor Cyan
    Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Format-List"
    Write-Host ""
    Write-Host "Para ejecutarla ahora manualmente:" -ForegroundColor Cyan
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host ""
    Write-Host "Para ver el resultado del último run:" -ForegroundColor Cyan
    Write-Host "  Get-ScheduledTaskInfo -TaskName '$TaskName'"
    Write-Host ""

} catch {
    Write-Host "ERROR al registrar la tarea: $_" -ForegroundColor Red
    Write-Host "Asegurate de ejecutar este script como Administrador." -ForegroundColor Yellow
    exit 1
}
