$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
$privatePath = Join-Path $workspacePath '.local'
$runtimePath = Join-Path $privatePath 'payment-tunnel.json'
$recordsPath = Join-Path $privatePath 'payment-processes.json'
$pythonPath = Join-Path $workspacePath '.venv\Scripts\python.exe'
$cloudflaredPath = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'

if (-not (Test-Path -LiteralPath $cloudflaredPath)) { throw 'No se encontro cloudflared instalado.' }
if (Test-Path -LiteralPath $recordsPath) {
    $previous = Get-Content -LiteralPath $recordsPath -Raw | ConvertFrom-Json
    foreach ($record in $previous) {
        $running = Get-Process -Id ([int]$record.id) -ErrorAction SilentlyContinue
        if ($running -and $running.Path -and $running.StartTime -and $running.Path -ieq $record.executable -and $running.StartTime.ToUniversalTime().Ticks.ToString() -eq $record.started) {
            if (Test-Path -LiteralPath $runtimePath) {
                $runtime = Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json
                Write-Output ('La prueba ya tiene procesos activos. URL registrada: ' + $runtime.public_url)
            }
            throw 'Para reiniciar, ejecuta primero detener-pagos.cmd. No se crearon procesos duplicados.'
        }
    }
}
$portCheck = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,8001)
try { $portCheck.Start() } catch { throw 'El puerto 8001 esta ocupado. No se modifico el servicio que lo usa.' } finally { $portCheck.Stop() }

New-Item -ItemType Directory -Path $privatePath -Force | Out-Null
$utf8 = [System.Text.UTF8Encoding]::new($false)
$records = @()
function Save-ProcessRecord($process, $label) {
    return @{id=$process.Id;name=$label;executable=$process.Path;started=$process.StartTime.ToUniversalTime().Ticks.ToString()}
}
foreach ($file in @('payment-tunnel.stdout.log','payment-tunnel.stderr.log','payment-test-server.stdout.log','payment-test-server.stderr.log')) {
    $oldLog = Join-Path $privatePath $file
    if (Test-Path -LiteralPath $oldLog) {
        $archive = Join-Path $privatePath 'tunnel-logs'
        New-Item -ItemType Directory -Path $archive -Force | Out-Null
        Copy-Item -LiteralPath $oldLog -Destination (Join-Path $archive ((Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + $file))
    }
}
$tunnel = Start-Process -FilePath $cloudflaredPath -ArgumentList @('tunnel','--no-autoupdate','--url','http://127.0.0.1:8001','--http-host-header','localhost','--protocol','http2') -WorkingDirectory $workspacePath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $privatePath 'payment-tunnel.stdout.log') -RedirectStandardError (Join-Path $privatePath 'payment-tunnel.stderr.log')
$records += Save-ProcessRecord $tunnel 'Tunel Cloudflare'
[System.IO.File]::WriteAllText($recordsPath, (ConvertTo-Json -InputObject @($records)), $utf8)
$publicUrl = $null
for ($attempt = 0; $attempt -lt 90; $attempt++) {
    $logPath = Join-Path $privatePath 'payment-tunnel.stderr.log'
    if (Test-Path -LiteralPath $logPath) {
        $logContent = ''
        try { $logContent = Get-Content -LiteralPath $logPath -Raw -ErrorAction Stop } catch { }
        if ($logContent) {
            $match = [regex]::Match([string]$logContent,'https://[a-z0-9-]+\.trycloudflare\.com')
            if ($match.Success) { $publicUrl = $match.Value; break }
        }
    }
    if ($tunnel.HasExited) { throw 'El tunel se cerro. Revisar .local/payment-tunnel.stderr.log.' }
    Start-Sleep -Milliseconds 500
}
if (-not $publicUrl) { throw 'El tunel todavia no asigno una URL. Ejecuta detener-pagos.cmd antes de reintentar.' }
# Cada URL nueva necesita reconfigurar Webhooks antes de volver a probar pagos.
$runtime = @{public_url=$publicUrl;tunnel_pid=$tunnel.Id;port=8001;payments_enabled=$false}
[System.IO.File]::WriteAllText($runtimePath,($runtime | ConvertTo-Json),$utf8)
$server = Start-Process -FilePath $pythonPath -ArgumentList @('manage.py','runserver','127.0.0.1:8001','--noreload','--settings=config.payment_test_settings') -WorkingDirectory $workspacePath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $privatePath 'payment-test-server.stdout.log') -RedirectStandardError (Join-Path $privatePath 'payment-test-server.stderr.log')
$records += Save-ProcessRecord $server 'Django de prueba'
[System.IO.File]::WriteAllText($recordsPath,(ConvertTo-Json -InputObject @($records)),$utf8)
[System.IO.File]::WriteAllText((Join-Path $privatePath 'payment-tunnel.pid'),$tunnel.Id.ToString(),$utf8)
[System.IO.File]::WriteAllText((Join-Path $privatePath 'payment-test-server.pid'),$server.Id.ToString(),$utf8)
Write-Output ('URL para probar desde el celular: ' + $publicUrl)
Write-Output 'Los pagos quedan desactivados hasta actualizar y comprobar las notificaciones con esta URL nueva.'
Write-Output 'Para apagarlo: detener-pagos.cmd. La computadora debe permanecer encendida y sin suspension.'
