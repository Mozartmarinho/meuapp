# Starts MeuApp in the background (no window, no git pull, no browser).
# Used by the Windows logon scheduled task. Do not use timeout.exe here.
param(
    [string]$AppDir = ''
)

$ErrorActionPreference = 'Continue'
$cfgDir = Join-Path $env:LOCALAPPDATA 'MeuApp'
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
$log = Join-Path $cfgDir 'autostart.log'
$outLog = Join-Path $cfgDir 'app.out.log'
$errLog = Join-Path $cfgDir 'app.err.log'
$repoFile = Join-Path $cfgDir 'repo_path.txt'

function Write-AutoLog([string]$message) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
}

function Test-MeuAppDir([string]$dir) {
    if (-not $dir) { return $false }
    $dir = $dir.Trim().Trim('"').TrimEnd('\', '/')
    return (Test-Path -LiteralPath (Join-Path $dir 'app.py'))
}

function Get-NormalizedDir([string]$dir) {
    if (-not $dir) { return $null }
    $dir = $dir.Trim().Trim('"').TrimEnd('\', '/')
    try { return (Resolve-Path -LiteralPath $dir).Path } catch { return $dir }
}

$candidates = New-Object System.Collections.Generic.List[string]
if ($AppDir) { [void]$candidates.Add($AppDir) }
if (Test-Path -LiteralPath $repoFile) {
    [void]$candidates.Add((Get-Content -LiteralPath $repoFile -TotalCount 1))
}
[void]$candidates.Add((Join-Path $env:USERPROFILE 'meuapp'))
[void]$candidates.Add('C:\meuapp')

$found = $null
foreach ($c in $candidates) {
    if (Test-MeuAppDir $c) {
        $found = Get-NormalizedDir $c
        break
    }
}

if (-not $found) {
    Write-AutoLog 'ERRO: pasta do meuapp nao encontrada.'
    exit 1
}

Set-Content -LiteralPath $repoFile -Value $found -Encoding ASCII
Write-AutoLog "Iniciando MeuApp em $found"

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'app.py' } |
    ForEach-Object {
        Write-AutoLog "Encerrando app.py PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

$svc = Get-Service -Name 'MySQL84' -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -ne 'Running') {
    try {
        Start-Service -Name 'MySQL84' -ErrorAction Stop
        Write-AutoLog 'MySQL84 iniciado.'
    } catch {
        Write-AutoLog "AVISO: nao iniciou MySQL84 ($($_.Exception.Message))"
    }
} elseif ($svc) {
    Write-AutoLog 'MySQL84 ja em execucao.'
}

Start-Sleep -Seconds 1

$python = Join-Path $found '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $localPy = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (Test-Path -LiteralPath $localPy) { $python = $localPy } else { $python = 'python' }
}

foreach ($old in @($outLog, $errLog)) {
    try { if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Force -ErrorAction Stop } } catch { }
}

$p = Start-Process -FilePath $python -ArgumentList 'app.py' -WorkingDirectory $found `
    -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
Write-AutoLog "python app.py PID $($p.Id) ($python)"
exit 0
