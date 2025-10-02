@echo off
REM Instalar o serviço do meuapp para iniciar automaticamente com NSSM

REM Caminho do executável Python e do app.py
set PYTHON_PATH=C:\Users\mz\Documents\meuapp\venv\Scripts\python.exe
set APP_PATH=C:\Users\mz\Documents\meuapp\app.py

REM Instalar serviço com NSSM
nssm install meuapp "%PYTHON_PATH%" "%APP_PATH%"

REM Configurar serviço para iniciar automaticamente
nssm set meuapp Start SERVICE_AUTO_START

REM Iniciar serviço
net start meuapp

pause
