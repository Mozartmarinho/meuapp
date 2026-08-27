# Encerra o Flask antigo (app.py / python na porta 80) e espera a porta ficar livre.
# Exit 0 = porta 80 livre; 1 = python ainda ocupa; 2 = outro programa ocupa a porta.
$ErrorActionPreference = 'SilentlyContinue'

function Get-Listeners80 {
    return @(Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue)
}

function Stop-AppPython {
    $killed = $false
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -and
        $_.Name -match '^(python|pythonw|py)(\.exe)?$' -and
        $_.CommandLine -and
        ($_.CommandLine -match 'app\.py' -or $_.CommandLine -match '[\\/]meuapp([\\/]|$)')
    } | ForEach-Object {
        Write-Host ("       Encerrando PID " + $_.ProcessId)
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        $killed = $true
    }
    foreach ($conn in Get-Listeners80) {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -match '^(python|pythonw|py)$') {
            Write-Host ("       Encerrando python porta 80 PID " + $proc.Id)
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            $killed = $true
        }
    }
    return $killed
}

$didKill = Stop-AppPython
Start-Sleep -Seconds 1
if (Stop-AppPython) { $didKill = $true }

$deadline = (Get-Date).AddSeconds(15)
while ((Get-Date) -lt $deadline) {
    $listen = Get-Listeners80
    if (-not $listen -or $listen.Count -eq 0) {
        if ($didKill) {
            Write-Host '       Instancia anterior encerrada. Porta 80 livre.'
        } else {
            Write-Host '       Nenhuma instancia anterior na porta 80.'
        }
        exit 0
    }
    $stillPython = $false
    foreach ($conn in $listen) {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -match '^(python|pythonw|py)$') {
            $stillPython = $true
            Write-Host ("       Aguardando encerrar PID " + $proc.Id)
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if (-not $stillPython) {
        $names = @(
            foreach ($conn in $listen) {
                $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
                if ($proc) { '{0} PID {1}' -f $proc.ProcessName, $proc.Id } else { "PID $($conn.OwningProcess)" }
            }
        ) -join ', '
        Write-Host ("       ERRO: porta 80 ocupada por " + $names + " (nao e o Flask).")
        Write-Host '               Feche esse programa ou rode como Administrador.'
        exit 2
    }
    Start-Sleep -Milliseconds 400
}

Write-Host '       ERRO: porta 80 ainda ocupada pelo Python antigo.'
exit 1
