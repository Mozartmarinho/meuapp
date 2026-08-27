# Finds the meuapp git clone and (re)creates the desktop shortcut
# "São Geraldo Service" pointing at iniciar_meuapp.bat in that clone.
param(
    [string]$AppDir = $env:MEUAPP_DIR
)

$ErrorActionPreference = 'SilentlyContinue'

function Test-MeuAppDir([string]$dir) {
    if (-not $dir) { return $false }
    $dir = $dir.Trim().Trim('"')
    if ($dir.EndsWith('\') -or $dir.EndsWith('/')) {
        $dir = $dir.TrimEnd('\', '/')
    }
    return (Test-Path -LiteralPath (Join-Path $dir 'app.py')) -and
           (Test-Path -LiteralPath (Join-Path $dir '.git')) -and
           (Test-Path -LiteralPath (Join-Path $dir 'iniciar_meuapp.bat'))
}

function Get-NormalizedDir([string]$dir) {
    if (-not $dir) { return $null }
    $dir = $dir.Trim().Trim('"')
    if ($dir.EndsWith('\') -or $dir.EndsWith('/')) {
        $dir = $dir.TrimEnd('\', '/')
    }
    try { return (Resolve-Path -LiteralPath $dir).Path } catch { return $dir }
}

$saved = Join-Path $env:LOCALAPPDATA 'MeuApp\repo_path.txt'
$hints = New-Object System.Collections.Generic.List[string]
if ($AppDir) { [void]$hints.Add($AppDir) }
if (Test-Path -LiteralPath $saved) {
    [void]$hints.Add((Get-Content -LiteralPath $saved -TotalCount 1))
}
[void]$hints.Add((Join-Path $env:USERPROFILE 'source\repos\Mozartmarinho\meuapp'))
[void]$hints.Add((Join-Path $env:USERPROFILE 'source\repos\meuapp'))
[void]$hints.Add((Join-Path $env:USERPROFILE 'meuapp'))
[void]$hints.Add((Join-Path $env:USERPROFILE 'Documents\meuapp'))
[void]$hints.Add((Join-Path $env:USERPROFILE 'Downloads\meuapp'))
[void]$hints.Add((Join-Path $env:USERPROFILE 'Desktop\meuapp'))
[void]$hints.Add((Join-Path $env:USERPROFILE 'OneDrive\Desktop\meuapp'))
[void]$hints.Add((Join-Path $env:USERPROFILE 'source\meuapp'))
[void]$hints.Add('C:\meuapp')
[void]$hints.Add('D:\meuapp')
[void]$hints.Add('C:\SaoGeraldo\meuapp')
[void]$hints.Add('C:\sgservico\meuapp')

$found = $null
foreach ($h in $hints) {
    if (Test-MeuAppDir $h) {
        $found = Get-NormalizedDir $h
        break
    }
}

if (-not $found) {
    $roots = @($env:USERPROFILE, 'C:\', 'D:\') | Where-Object { $_ -and (Test-Path $_) }
    foreach ($root in $roots) {
        $dirs = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'meuapp' }
        foreach ($d in $dirs) {
            if (Test-MeuAppDir $d.FullName) {
                $found = Get-NormalizedDir $d.FullName
                break
            }
        }
        if ($found) { break }
    }
}

if (-not $found) {
    $hit = Get-ChildItem -LiteralPath $env:USERPROFILE -Filter 'iniciar_meuapp.bat' -Recurse -Depth 4 -ErrorAction SilentlyContinue |
        Where-Object {
            (Test-Path (Join-Path $_.DirectoryName 'app.py')) -and
            (Test-Path (Join-Path $_.DirectoryName '.git'))
        } |
        Select-Object -First 1
    if ($hit) { $found = Get-NormalizedDir $hit.DirectoryName }
}

if (-not $found) {
    Write-Output ''
    exit 1
}

$cfgDir = Join-Path $env:LOCALAPPDATA 'MeuApp'
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
Set-Content -LiteralPath $saved -Value $found -Encoding ASCII

$desk = [Environment]::GetFolderPath('Desktop')
$ws = New-Object -ComObject WScript.Shell
$lnkPath = Join-Path $desk 'São Geraldo Service.lnk'
$sc = $ws.CreateShortcut($lnkPath)
$sc.TargetPath = Join-Path $found 'iniciar_meuapp.bat'
$sc.WorkingDirectory = $found
$sc.WindowStyle = 1
$sc.Description = 'São Geraldo Service'
$sc.Save()

$stub = @"
@echo off
chcp 65001 >nul
title Sao Geraldo Service
setlocal
set "APP_DIR=$found"
if exist "%APP_DIR%\iniciar_meuapp.bat" (
  cd /d "%APP_DIR%"
  call "%APP_DIR%\iniciar_meuapp.bat"
  exit /b
)
echo Nao achei iniciar_meuapp.bat em %APP_DIR%
pause
"@
$stubPath = Join-Path $desk 'São Geraldo Service.bat'
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($stubPath, $stub, $utf8NoBom)

Write-Output $found
exit 0
