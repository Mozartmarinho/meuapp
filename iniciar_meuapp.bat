@echo off
chcp 65001 >nul
title São Geraldo Service

echo ========================================
echo   São Geraldo Service
echo ========================================
echo.

REM Atalho da area de trabalho: "São Geraldo Service"
REM Sempre trabalha na pasta do clone git (nao numa copia solta).
REM Depois do git pull, relanca este .bat para nao continuar com linhas antigas.

if "%MEUAPP_BOOTSTRAPPED%"=="1" goto :depois_atualizacao

setlocal EnableDelayedExpansion
set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\Git\bin;C:\Program Files (x86)\Git\cmd"

REM --- Encerrar instancia antiga (porta 80 continua servindo o codigo velho) ---
echo [1/6] Encerrando app.py antigo na porta 80...
call :parar_app
if "!PAROU!"=="1" (
    echo       Instancia anterior encerrada. Aguardando a porta 80 liberar...
    timeout /t 2 /nobreak >nul
) else (
    echo       Nenhuma instancia anterior encontrada.
)

REM --- Pasta do repositorio ---
echo [2/6] Localizando pasta do MeuApp...
set "APP_DIR="

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
if exist "%HERE%\scripts\desktop_sao_geraldo.ps1" (
    for /f "usebackq delims=" %%D in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%\scripts\desktop_sao_geraldo.ps1" -AppDir "%HERE%"`) do (
        if not defined APP_DIR set "APP_DIR=%%D"
    )
)

if not defined APP_DIR if exist "%HERE%\app.py" if exist "%HERE%\.git" set "APP_DIR=%HERE%"
if not defined APP_DIR if exist "%LOCALAPPDATA%\MeuApp\repo_path.txt" (
    set /p APP_DIR=<"%LOCALAPPDATA%\MeuApp\repo_path.txt"
)
if defined APP_DIR (
    set "APP_DIR=!APP_DIR:"=!"
    if "!APP_DIR:~-1!"=="\" set "APP_DIR=!APP_DIR:~0,-1!"
)
if defined APP_DIR if not exist "!APP_DIR!\app.py" set "APP_DIR="
if defined APP_DIR if not exist "!APP_DIR!\.git" set "APP_DIR="

if not defined APP_DIR (
    for %%D in (
        "%USERPROFILE%\source\repos\Mozartmarinho\meuapp"
        "%USERPROFILE%\source\repos\meuapp"
        "%USERPROFILE%\meuapp"
        "%USERPROFILE%\Documents\meuapp"
        "%USERPROFILE%\Downloads\meuapp"
        "%USERPROFILE%\Desktop\meuapp"
        "%USERPROFILE%\OneDrive\Desktop\meuapp"
        "C:\meuapp"
        "D:\meuapp"
    ) do (
        if exist "%%~D\app.py" if exist "%%~D\.git" if not defined APP_DIR set "APP_DIR=%%~D"
    )
)

if not defined APP_DIR (
    echo       ERRO: nao achei o clone git do meuapp.
    echo               O atalho "São Geraldo Service" precisa apontar para
    echo               iniciar_meuapp.bat DENTRO da pasta do repositorio
    echo               (onde existem app.py e a pasta .git).
    echo.
    pause
    exit /b 1
)

cd /d "!APP_DIR!"
echo       Pasta: !APP_DIR!

if exist "!APP_DIR!\scripts\desktop_sao_geraldo.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "!APP_DIR!\scripts\desktop_sao_geraldo.ps1" -AppDir "!APP_DIR!" >nul
    echo       Atalho da area de trabalho: São Geraldo Service
)

REM --- Git no PATH do atalho da area de trabalho (muitas vezes nao vem) ---
set "GIT="
where git >nul 2>&1 && for /f "delims=" %%G in ('where git 2^>nul') do (
    if not defined GIT set "GIT=%%G"
)
if not defined GIT if exist "C:\Program Files\Git\cmd\git.exe" set "GIT=C:\Program Files\Git\cmd\git.exe"
if not defined GIT if exist "C:\Program Files\Git\bin\git.exe" set "GIT=C:\Program Files\Git\bin\git.exe"
if not defined GIT if exist "C:\Program Files (x86)\Git\cmd\git.exe" set "GIT=C:\Program Files (x86)\Git\cmd\git.exe"

REM --- Codigo do GitHub ---
echo [3/6] Atualizando codigo do GitHub (branch main)...
set "GIT_OK=0"
if not defined GIT (
    echo       ERRO: git nao encontrado. Instale o Git for Windows.
    echo               O app vai subir com o codigo que ja esta nesta pasta.
) else (
    set "GIT_TERMINAL_PROMPT=0"
    "%GIT%" -C "!APP_DIR!" fetch origin main
    if errorlevel 1 (
        echo       AVISO: nao consegui buscar origin/main (rede ou login do GitHub).
        echo               O app vai subir com o codigo que ja esta nesta pasta.
    ) else (
        "%GIT%" -C "!APP_DIR!" checkout --force -B main origin/main
        if errorlevel 1 (
            echo       AVISO: nao deu para ir para a main. Feche arquivos abertos e tente de novo.
        ) else (
            "%GIT%" -C "!APP_DIR!" reset --hard origin/main
            if errorlevel 1 (
                echo       AVISO: nao deu para alinhar com origin/main.
            ) else (
                set "GIT_OK=1"
                echo       Atualizado para origin/main.
            )
        )
    )
    echo       Git: !GIT!
    echo       Branch:
    "%GIT%" -C "!APP_DIR!" rev-parse --abbrev-ref HEAD
    echo       Commit:
    "%GIT%" -C "!APP_DIR!" log -1 --oneline
)

REM Relanca o .bat ja atualizado (cmd.exe nao deve continuar com linhas do arquivo antigo).
set "RELAUNCH_DIR=!APP_DIR!"
endlocal & set "MEUAPP_BOOTSTRAPPED=1" & set "MEUAPP_DIR=%RELAUNCH_DIR%" & cd /d "%RELAUNCH_DIR%" & call "%RELAUNCH_DIR%\iniciar_meuapp.bat"
exit /b

:depois_atualizacao
setlocal EnableDelayedExpansion
if defined MEUAPP_DIR (
    cd /d "!MEUAPP_DIR!"
) else (
    cd /d "%~dp0"
)

REM --- MySQL84 ---
echo [4/6] Verificando MySQL84...
sc query MySQL84 | findstr /i "RUNNING" >nul 2>&1
if %errorlevel%==0 (
    echo       MySQL84 ja esta em execucao.
) else (
    echo       Tentando iniciar MySQL84...
    net start MySQL84 2>nul
    if %errorlevel%==0 (
        echo       MySQL84 iniciado com sucesso.
    ) else (
        echo.
        echo AVISO: Nao foi possivel iniciar o MySQL84.
        echo         Execute este arquivo como Administrador se o servico
        echo         nao iniciar, ou se a porta 80 falhar ao subir o app.
        echo.
    )
)

REM --- Python ---
echo [5/6] Definindo interpretador Python...
if exist "%CD%\.venv\Scripts\python.exe" (
    set "PYTHON=%CD%\.venv\Scripts\python.exe"
    echo       Usando: .venv\Scripts\python.exe
) else if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "PYTHON=%LocalAppData%\Programs\Python\Python312\python.exe"
    echo       Usando: Python312 (instalacao local)
) else (
    set "PYTHON=python"
    echo       Usando: python (PATH)
)

REM --- Browser ---
echo [6/6] Abrindo http://127.0.0.1/nutricao em alguns segundos...
for /f %%T in ('powershell -NoProfile -Command "Get-Date -UFormat %%s"') do set "TS=%%T"
if not defined TS set "TS=%RANDOM%"
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1/nutricao?v=!TS!"

echo.
echo Codigo deste projeto (meuapp). Iniciando São Geraldo Service...
echo Logs abaixo. Feche esta janela ou use parar_meuapp.bat para encerrar.
echo ========================================
echo.

"%PYTHON%" app.py

echo.
echo App encerrado.
pause
endlocal
goto :eof

:parar_app
set "PAROU=0"
REM wmic some vezes nao existe no Windows 11; PowerShell mata app.py e python na porta 80.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='SilentlyContinue'; $killed=$false;" ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'app.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $killed=$true; Write-Host ('       Encerrando PID ' + $_.ProcessId) };" ^
  "Get-NetTCPConnection -LocalPort 80 -State Listen | ForEach-Object { $p=Get-Process -Id $_.OwningProcess; if ($p -and $p.ProcessName -match 'python') { Stop-Process -Id $p.Id -Force; $killed=$true; Write-Host ('       Encerrando python porta 80 PID ' + $p.Id) } };" ^
  "if ($killed) { exit 0 } else { exit 1 }"
if %errorlevel%==0 set "PAROU=1"
timeout /t 2 /nobreak >nul
goto :eof
