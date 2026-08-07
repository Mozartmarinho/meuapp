@echo off
REM Inicia o MeuApp na porta 80 (requer Administrador no Windows)
cd /d "%~dp0"
echo Iniciando Sao Geraldo Service na porta 80...
echo Se der erro de permissao, clique direito neste arquivo e "Executar como administrador".
".venv\Scripts\python.exe" app.py
pause
