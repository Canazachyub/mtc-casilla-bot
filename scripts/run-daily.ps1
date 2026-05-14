# MTC Casilla Bot — Ejecucion diaria automatica
# Configurar en Programador de Tareas de Windows:
#   Accion: powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "C:\PROGRAMACION\RESOLVE\Resolve\scripts\run-daily.ps1"
#   Desencadenador: Diario a las 08:00
#   Iniciar en: C:\PROGRAMACION\RESOLVE\Resolve

$ProjectRoot = "C:\PROGRAMACION\RESOLVE\Resolve"
$UvExe = "C:\Users\User\.local\bin\uv.exe"
$LogDir = "$ProjectRoot\logs"
$LogFile = "$LogDir\run-$(Get-Date -Format 'yyyy-MM-dd').log"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Output $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Log "=== Iniciando run diario ==="
Log "Proyecto: $ProjectRoot"

Set-Location $ProjectRoot

& $UvExe run mtc-bot run --since today 2>&1 | ForEach-Object {
    Log $_
}

$exit = $LASTEXITCODE
Log "=== Run finalizado (exit=$exit) ==="

# Limpiar logs de mas de 30 dias
Get-ChildItem -Path $LogDir -Filter "run-*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force

exit $exit
