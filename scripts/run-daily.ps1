$ProjectRoot = "C:\PROGRAMACION\RESOLVE\Resolve"
$UvExe       = "C:\Users\User\.local\bin\uv.exe"
$LogDir      = "$ProjectRoot\logs"
$DateStamp   = Get-Date -Format 'yyyy-MM-dd'
$LogFile     = "$LogDir\run-$DateStamp.log"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

# Elimina codigos ANSI (colores de rich/Python) para escribir al log limpio
function Strip-Ansi($s) {
    return [regex]::Replace([string]$s, '\x1b\[[\d;]*[a-zA-Z]|\x1b\][\d;]*[a-zA-Z]', '')
}

function Log($msg, $level) {
    if (-not $level) { $level = "INFO" }
    $line = "[$(Get-Date -Format 'HH:mm:ss')] [$level] $msg"
    Write-Host $line
    $clean = "[$(Get-Date -Format 'HH:mm:ss')] [$level] $(Strip-Ansi $msg)"
    try {
        [System.IO.File]::AppendAllText($LogFile, $clean + "`r`n", [System.Text.Encoding]::UTF8)
    } catch {}
}

Log "=========================================="
Log "MTC Casilla Bot -- Run diario $DateStamp"
Log "=========================================="

if (-not (Test-Path $UvExe)) {
    Log "ERROR: uv.exe no encontrado en $UvExe" "ERROR"
    exit 1
}

Set-Location $ProjectRoot
Log "Directorio: $ProjectRoot"

Log "--- doctor check ---"
$doctorOut = & $UvExe run mtc-bot doctor 2>&1
foreach ($l in $doctorOut) { Log "$l" }

if ($LASTEXITCODE -ne 0) {
    Log "Doctor fallo -- abortando" "ERROR"
    exit $LASTEXITCODE
}

Log "--- run --since 2d ---"
$runOut = & $UvExe run mtc-bot run --since 2d 2>&1
foreach ($l in $runOut) { Log "$l" }
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Log "Run completado correctamente" "OK"
} else {
    Log "Run finalizo con errores (exit=$exitCode)" "ERROR"
}

Log "--- reprocess ---"
$reprocessOut = & $UvExe run mtc-bot reprocess 2>&1
foreach ($l in $reprocessOut) { Log "$l" }

Get-ChildItem -Path $LogDir -Filter "run-*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    ForEach-Object { Remove-Item $_.FullName -Force }

Log "Fin del run diario (exit=$exitCode)"
exit $exitCode
