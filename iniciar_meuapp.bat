@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   MeuApp - Inicializacao
echo ========================================
echo.

REM --- MySQL84 ---
echo [1/3] Verificando MySQL84...
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
echo [2/3] Definindo interpretador Python...
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
    echo       Usando: .venv\Scripts\python.exe
) else (
    set "PYTHON=python"
    echo       Usando: python (PATH)
)

REM --- Browser (opcional, apos breve atraso) ---
echo [3/3] Abrindo navegador em alguns segundos...
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1/"

echo.
echo Iniciando app.py...
echo Logs abaixo. Feche esta janela ou use parar_meuapp.bat para encerrar.
echo ========================================
echo.

"%PYTHON%" app.py

echo.
echo App encerrado.
pause
