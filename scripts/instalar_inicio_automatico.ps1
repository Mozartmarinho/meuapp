# Installs MeuApp (São Geraldo Service) to start hidden at Windows logon.
param(
    [switch]$Uninstall,
    [switch]$StartNow,
    [string]$AppDir = ''
)

$ErrorActionPreference = 'Stop'
$TaskName = 'Sao Geraldo Service'
$CfgDir = Join-Path $env:LOCALAPPDATA 'MeuApp'
$RepoPathFile = Join-Path $CfgDir 'repo_path.txt'
$LocalStarter = Join-Path $CfgDir 'iniciar_autostart.ps1'
$StartupDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
$StartupLnk = Join-Path $StartupDir 'Sao Geraldo Service.lnk'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RepoStarter = Join-Path $PSScriptRoot 'iniciar_autostart.ps1'

function Test-MeuAppDir([string]$dir) {
    if (-not $dir) { return $false }
    $dir = $dir.Trim().Trim('"')
    $dir = $dir.TrimEnd('\', '/')
    return (Test-Path -LiteralPath (Join-Path $dir 'app.py')) -and
           (Test-Path -LiteralPath (Join-Path $dir 'iniciar_meuapp.bat'))
}

function Get-NormalizedDir([string]$dir) {
    if (-not $dir) { return $null }
    $dir = $dir.Trim().Trim('"').TrimEnd('\', '/')
    try { return (Resolve-Path -LiteralPath $dir).Path } catch { return $dir }
}

function Find-AppDir {
    $hints = New-Object System.Collections.Generic.List[string]
    if ($AppDir) { [void]$hints.Add($AppDir) }
    [void]$hints.Add($RepoRoot)
    if (Test-Path -LiteralPath $RepoPathFile) {
        [void]$hints.Add((Get-Content -LiteralPath $RepoPathFile -TotalCount 1))
    }
    [void]$hints.Add((Join-Path $env:USERPROFILE 'meuapp'))
    foreach ($h in $hints) {
        if (Test-MeuAppDir $h) { return (Get-NormalizedDir $h) }
    }
    throw "Nao achei a pasta do meuapp (app.py + iniciar_meuapp.bat)."
}

function Uninstall-Autostart {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "OK: tarefa agendada '$TaskName' removida."
    } else {
        Write-Host "Tarefa agendada '$TaskName' nao existia."
    }
    if (Test-Path -LiteralPath $StartupLnk) {
        Remove-Item -LiteralPath $StartupLnk -Force
        Write-Host "OK: atalho de Inicializar removido."
    }
}

function Install-Autostart([string]$found) {
    New-Item -ItemType Directory -Force -Path $CfgDir | Out-Null
    Set-Content -LiteralPath $RepoPathFile -Value $found -Encoding ASCII
    if (-not (Test-Path -LiteralPath $RepoStarter)) {
        throw "Falta $RepoStarter"
    }
    Copy-Item -LiteralPath $RepoStarter -Destination $LocalStarter -Force

    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$LocalStarter`" -AppDir `"$found`""
    $action = New-ScheduledTaskAction -Execute $psExe -Argument $arg
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $trigger.Delay = 'PT20S'
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description 'Inicia o MeuApp (Sao Geraldo Service) ao entrar no Windows' `
        -Force | Out-Null
    Write-Host "OK: tarefa agendada '$TaskName' (20s apos o login, sem janela)."

    if (Test-Path -LiteralPath $StartupLnk) {
        Remove-Item -LiteralPath $StartupLnk -Force
        Write-Host "OK: atalho duplicado em Inicializar removido."
    }
}

if ($Uninstall) {
    Uninstall-Autostart
    exit 0
}

$found = Find-AppDir
Write-Host "Pasta do MeuApp: $found"
Install-Autostart $found
Write-Host "No proximo login o app sobe sozinho. Use parar_meuapp.bat para encerrar."
Write-Host "Desinstalar: powershell -File `"$PSCommandPath`" -Uninstall"

if ($StartNow) {
    Write-Host "Iniciando agora em segundo plano..."
    & $LocalStarter -AppDir $found
}
