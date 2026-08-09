@echo off
setlocal EnableExtensions
title Instalar Agente Pesagem no inicio do Windows

set "SRC=%~dp0"
set "DEST=%LOCALAPPDATA%\SaoGeraldo\AgentePesagem"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LNK=%STARTUP%\AgentePesagem.lnk"

echo.
echo === Agente Pesagem - Iniciar com o Windows ===
echo Origem: %SRC%
echo Destino: %DEST%
echo.

if not exist "%SRC%AgentePesagem.exe" (
  echo ERRO: AgentePesagem.exe nao encontrado nesta pasta.
  pause
  exit /b 1
)

mkdir "%DEST%" 2>nul
copy /Y "%SRC%AgentePesagem.exe" "%DEST%\AgentePesagem.exe" >nul
if exist "%SRC%config.json" copy /Y "%SRC%config.json" "%DEST%\config.json" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%LNK%'); $s.TargetPath = '%DEST%\AgentePesagem.exe'; $s.WorkingDirectory = '%DEST%'; $s.WindowStyle = 1; $s.Description = 'Agente Pesagem Sao Geraldo'; $s.Save()"

if errorlevel 1 (
  echo Falha ao criar atalho na pasta Inicializar.
  pause
  exit /b 1
)

echo OK: instalado em %DEST%
echo OK: atalho criado em Inicializar do Windows
echo.
echo Edite o config.json em %DEST% se precisar mudar COM / servidor.
echo O agente iniciara automaticamente no proximo login.
echo.
choice /C SN /M "Deseja iniciar o agente agora"
if errorlevel 2 goto fim
if errorlevel 1 start "" "%DEST%\AgentePesagem.exe"

:fim
echo.
pause
