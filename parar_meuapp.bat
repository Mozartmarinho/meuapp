@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Encerrando processos python que executam app.py (e python na porta 80)...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='SilentlyContinue'; $killed=$false;" ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'app.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $killed=$true; Write-Host ('       Encerrando PID ' + $_.ProcessId) };" ^
  "Get-NetTCPConnection -LocalPort 80 -State Listen | ForEach-Object { $p=Get-Process -Id $_.OwningProcess; if ($p -and $p.ProcessName -match 'python') { Stop-Process -Id $p.Id -Force; $killed=$true; Write-Host ('       Encerrando python porta 80 PID ' + $p.Id) } };" ^
  "if (-not $killed) { Write-Host 'Nenhum processo app.py encontrado.' } else { Write-Host 'Concluido.' }"

pause
