@echo off
cd /d "%~dp0"
echo === Gerando AcessoRemotoSaoGeraldo.exe ===
if not exist ".venv" (
  py -3.12 -m venv .venv
  if errorlevel 1 python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
set "ICON="
if exist "..\agente_pesagem\sao_geraldo.ico" set "ICON=--icon ..\agente_pesagem\sao_geraldo.ico"
pyinstaller --noconfirm --onefile --windowed --name AcessoRemotoSaoGeraldo %ICON% --hidden-import PIL --hidden-import PIL.Image --hidden-import PIL.ImageGrab --hidden-import pystray --hidden-import requests agente.py
if errorlevel 1 (
  echo Falha ao gerar o executavel.
  if /I not "%~1"=="nopause" pause
  exit /b 1
)
set "VER=1.0.0"
for /f "tokens=2 delims='" %%V in ('findstr /R /C:"^APP_VERSION" agente.py') do set "VER=%%V"
set "PUB=..\static\downloads\acesso_remoto"
mkdir "%PUB%" 2>nul
copy /Y dist\AcessoRemotoSaoGeraldo.exe "%PUB%\AcessoRemotoSaoGeraldo.exe" >nul
copy /Y dist\AcessoRemotoSaoGeraldo.exe "%PUB%\AcessoRemotoSaoGeraldo-%VER%.exe" >nul
echo Pronto: %PUB%\AcessoRemotoSaoGeraldo-%VER%.exe
if /I not "%~1"=="nopause" pause
