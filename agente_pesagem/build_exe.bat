@echo off
cd /d "%~dp0"
echo === Gerando AgentePesagem.exe (GUI) ===
if not exist ".venv" (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
pyinstaller --noconfirm --onefile --windowed --name AgentePesagem agente_pesagem.py
if errorlevel 1 (
  echo Falha ao gerar o executavel.
  pause
  exit /b 1
)
copy /Y config.json dist\config.json >nul

set "PUB=..\static\downloads\agente_pesagem"
mkdir "%PUB%" 2>nul
copy /Y dist\AgentePesagem.exe "%PUB%\AgentePesagem.exe" >nul
copy /Y config.json "%PUB%\config.json" >nul

echo.
echo Pronto: dist\AgentePesagem.exe
echo Publicado em: %PUB%\AgentePesagem.exe
pause
