@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   MeuApp - Inicializacao
echo ========================================
echo.

REM --- Codigo do GitHub (o atalho da area de trabalho so sobe o que esta nesta pasta) ---
echo [1/4] Atualizando codigo do mapa de producao...
if exist "%~dp0.git" (
    git -C "%~dp0" fetch origin cursor/mapa-producao-clinica-leitos-7e7c 2>nul
    if errorlevel 1 (
        echo       AVISO: nao consegui buscar origin/cursor/mapa-producao-clinica-leitos-7e7c
        echo               O app vai subir com o codigo que ja esta nesta pasta.
    ) else (
        git -C "%~dp0" checkout -B cursor/mapa-producao-clinica-leitos-7e7c origin/cursor/mapa-producao-clinica-leitos-7e7c
        if errorlevel 1 (
            echo       AVISO: nao deu para trocar de branch. Feche arquivos abertos e tente de novo.
        ) else (
            echo       Branch:
            git -C "%~dp0" rev-parse --abbrev-ref HEAD
            echo       Commit:
            git -C "%~dp0" log -1 --oneline
        )
    )
) else (
    echo       AVISO: esta pasta nao e um clone git. O .bat nao consegue puxar o PR.
    echo               Aponte o atalho da area de trabalho para a pasta do repositorio meuapp.
)

REM --- MySQL84 ---
echo [2/4] Verificando MySQL84...
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
echo [3/4] Definindo interpretador Python...
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

REM --- Browser ---
echo [4/4] Abrindo http://127.0.0.1/nutricao em alguns segundos...
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1/nutricao"

echo.
echo Iniciando app.py...
echo Logs abaixo. Feche esta janela ou use parar_meuapp.bat para encerrar.
echo ========================================
echo.

"%PYTHON%" app.py

echo.
echo App encerrado.
pause
