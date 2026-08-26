@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal EnableDelayedExpansion

echo ========================================
echo   MeuApp - Inicializacao
echo ========================================
echo.

REM Atalho da area de trabalho deve apontar para ESTE arquivo na pasta do
REM repositorio meuapp (nao uma copia solta). Assim o git pull funciona.

REM --- Encerrar instancia antiga (porta 80 continua servindo o codigo velho) ---
echo [1/5] Encerrando app.py antigo na porta 80...
call :parar_app
if "!PAROU!"=="1" (
    echo       Instancia anterior encerrada. Aguardando a porta 80 liberar...
    timeout /t 2 /nobreak >nul
) else (
    echo       Nenhuma instancia anterior encontrada.
)

REM --- Git no PATH do atalho da area de trabalho (muitas vezes nao vem) ---
set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\Git\bin;C:\Program Files (x86)\Git\cmd"
set "GIT="
where git >nul 2>&1 && for /f "delims=" %%G in ('where git 2^>nul') do (
    if not defined GIT set "GIT=%%G"
)
if not defined GIT if exist "C:\Program Files\Git\cmd\git.exe" set "GIT=C:\Program Files\Git\cmd\git.exe"
if not defined GIT if exist "C:\Program Files\Git\bin\git.exe" set "GIT=C:\Program Files\Git\bin\git.exe"
if not defined GIT if exist "C:\Program Files (x86)\Git\cmd\git.exe" set "GIT=C:\Program Files (x86)\Git\cmd\git.exe"

REM --- Codigo do GitHub (atalho e servidor usam a main) ---
echo [2/5] Atualizando codigo do GitHub (branch main)...
set "GIT_OK=0"
if not exist "%~dp0.git" (
    echo       ERRO: esta pasta nao e um clone git.
    echo               Aponte o atalho da area de trabalho para iniciar_meuapp.bat
    echo               DENTRO da pasta do repositorio meuapp (onde existe a pasta .git).
    echo               Sem isso o http://127.0.0.1/nutricao fica na versao antiga.
) else if not defined GIT (
    echo       ERRO: git nao encontrado. Instale o Git for Windows ou coloque git.exe no PATH.
    echo               O app vai subir com o codigo que ja esta nesta pasta.
) else (
    set "GIT_TERMINAL_PROMPT=0"
    "%GIT%" -C "%~dp0" fetch origin main
    if errorlevel 1 (
        echo       AVISO: nao consegui buscar origin/main (rede ou login do GitHub).
        echo               O app vai subir com o codigo que ja esta nesta pasta.
    ) else (
            "%GIT%" -C "%~dp0" checkout --force -B main origin/main
            if errorlevel 1 (
                echo       AVISO: nao deu para ir para a main. Feche o app e arquivos abertos e tente de novo.
            ) else (
                "%GIT%" -C "%~dp0" reset --hard origin/main
                if errorlevel 1 (
                    echo       AVISO: nao deu para alinhar com origin/main.
                ) else (
                    set "GIT_OK=1"
                    echo       Atualizado para origin/main.
                )
            )
    )
    echo       Git: %GIT%
    echo       Branch:
    "%GIT%" -C "%~dp0" rev-parse --abbrev-ref HEAD
    echo       Commit:
    "%GIT%" -C "%~dp0" log -1 --oneline
)

REM --- MySQL84 ---
echo [3/5] Verificando MySQL84...
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
echo [4/5] Definindo interpretador Python...
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
    echo       Usando: .venv\Scripts\python.exe
) else if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "PYTHON=%LocalAppData%\Programs\Python\Python312\python.exe"
    echo       Usando: Python312 (instalacao local)
) else (
    set "PYTHON=python"
    echo       Usando: python (PATH)
)

REM --- Browser (cache-buster para nao reabrir a tela antiga) ---
echo [5/5] Abrindo http://127.0.0.1/nutricao em alguns segundos...
for /f %%T in ('powershell -NoProfile -Command "Get-Date -UFormat %%s"') do set "TS=%%T"
if not defined TS set "TS=%RANDOM%"
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1/nutricao?v=!TS!"

echo.
if "!GIT_OK!"=="1" (
    echo Codigo alinhado com o GitHub. Iniciando app.py...
) else (
    echo ATENCAO: nao atualizei do GitHub. Se a tela continuar antiga,
    echo          feche esta janela, rode parar_meuapp.bat e tente de novo
    echo          com internet e Git instalado.
)
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
for %%I in (python.exe pythonw.exe) do (
    for /f "tokens=2 delims=," %%P in ('tasklist /FI "IMAGENAME eq %%I" /FO CSV /NH 2^>nul') do (
        set "PID=%%~P"
        wmic process where "ProcessId=!PID!" get CommandLine 2>nul | findstr /i /c:"app.py" >nul 2>&1
        if not errorlevel 1 (
            echo       Encerrando PID !PID! ...
            taskkill /PID !PID! /F >nul 2>&1
            set "PAROU=1"
        )
    )
)
REM Libera a porta 80 se ainda houver python escutando (codigo velho no 127.0.0.1)
for /f "tokens=5" %%A in ('netstat -aon 2^>nul ^| findstr /R /C:":80 .*LISTENING"') do (
    set "PPID=%%A"
    if defined PPID (
        tasklist /FI "PID eq !PPID!" /FO CSV /NH 2>nul | findstr /i "python" >nul 2>&1
        if not errorlevel 1 (
            echo       Encerrando python na porta 80 PID !PPID! ...
            taskkill /PID !PPID! /F >nul 2>&1
            set "PAROU=1"
        )
    )
)
goto :eof
