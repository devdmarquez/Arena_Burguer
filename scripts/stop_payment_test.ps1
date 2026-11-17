[CmdletBinding(SupportsShouldProcess)]
param([switch]$ServerOnly)

$workspacePath = Split-Path -Parent $PSScriptRoot
$recordFile = Join-Path $workspacePath '.local\payment-processes.json'
if (-not (Test-Path -LiteralPath $recordFile)) { Write-Output 'No hay procesos de prueba registrados.'; exit }
$targets = Get-Content -LiteralPath $recordFile -Raw | ConvertFrom-Json
foreach ($target in $targets) {
    if ($ServerOnly -and $target.name -ne 'Django de prueba') { continue }
    $targetProcessId = [int]$target.id
    $processInfo = Get-Process -Id $targetProcessId -ErrorAction SilentlyContinue
    if (-not $processInfo) { Write-Output ($target.name + ': ya apagado.'); continue }
    if (-not $processInfo.Path -or -not $processInfo.StartTime -or $processInfo.Path -ine $target.executable -or $processInfo.StartTime.ToUniversalTime().Ticks.ToString() -ne $target.started) {
        Write-Warning ('El PID guardado ya no corresponde a ' + $target.name + '. No se detuvo.')
        continue
    }
    if ($PSCmdlet.ShouldProcess(($target.name + ' (PID ' + $targetProcessId + ')'), 'Detener solo la instancia temporal')) {
        & taskkill.exe /PID $targetProcessId /T /F
    }
}
