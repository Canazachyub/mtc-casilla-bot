# MTC Casilla Bot — Ejecución diaria automática
# ─────────────────────────────────────────────
# Task Scheduler → Acción:
#   powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "C:\PROGRAMACION\RESOLVE\Resolve\scripts\run-daily.ps1"
# Desencadenador: Diario a las 08:00 (o la hora que prefieras)
# Iniciar en: C:\PROGRAMACION\RESOLVE\Resolve

param(
    [string]$Since = "today",
    [switch]$DryRun
)

$ProjectRoot = "C:\PROGRAMACION\RESOLVE\Resolve"
$UvExe       = "C:\Users\User\.local\bin\uv.exe"
$LogDir      = "$ProjectRoot\logs"
$DateStamp   = Get-Date -Format 'yyyy-MM-dd'
$LogFile     = "$LogDir\run-$DateStamp.log"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Log {
    param([string]$msg, [string]$level = "INFO")
    $line = "[$(Get-Date -Format 'HH:mm:ss')] [$level] $msg"
    Write-Output $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# ── Validaciones previas ────────────────────────────────────────────
Log "=========================================="
Log "MTC Casilla Bot — Run diario $DateStamp"
Log "=========================================="

if (-not (Test-Path $UvExe)) {
    Log "ERROR: uv.exe no encontrado en $UvExe" "ERROR"
    Log "Revisá que uv esté instalado: winget install astral-sh.uv" "ERROR"
    exit 1
}

$EnvFile = "$ProjectRoot\.env"
if (-not (Test-Path $EnvFile)) {
    Log "WARN: Archivo .env no encontrado en $ProjectRoot" "WARN"
}

Set-Location $ProjectRoot
Log "Directorio: $(Get-Location)"
Log "Parámetros: --since $Since$(if ($DryRun) { ' --dry-run' })"

# ── Doctor check rápido ─────────────────────────────────────────────
Log "--- doctor check ---"
& $UvExe run mtc-bot doctor 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) {
    Log "Doctor falló (exit=$LASTEXITCODE) — abortando run" "ERROR"
    exit $LASTEXITCODE
}

# ── Ejecución principal ─────────────────────────────────────────────
Log "--- run --since $Since ---"

$RunArgs = @("run", "mtc-bot", "run", "--since", $Since)
if ($DryRun) { $RunArgs += "--dry-run" }

& $UvExe @RunArgs 2>&1 | ForEach-Object { Log $_ }
$ExitCode = $LASTEXITCODE

if ($ExitCode -eq 0) {
    Log "Run completado correctamente" "OK"
} else {
    Log "Run finalizó con errores (exit=$ExitCode)" "ERROR"
}

# ── Reprocess: actualizar campos IA faltantes ───────────────────────
Log "--- reprocess (campos nuevos) ---"
& $UvExe run mtc-bot reprocess 2>&1 | ForEach-Object { Log $_ }

# ── Limpieza de logs viejos (>30 días) ─────────────────────────────
$Deleted = 0
Get-ChildItem -Path $LogDir -Filter "run-*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    ForEach-Object { Remove-Item $_.FullName -Force; $Deleted++ }

if ($Deleted -gt 0) { Log "Limpiados $Deleted logs antiguos" }

Log "=========================================="
Log "Fin del run diario (exit=$ExitCode)"
Log "=========================================="

exit $ExitCode
