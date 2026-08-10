@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Encerrando processos python que executam app.py...

setlocal EnableDelayedExpansion
set "FOUND=0"

for /f "tokens=2 delims=," %%P in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH 2^>nul') do (
    set "PID=%%~P"
    wmic process where "ProcessId=!PID!" get CommandLine 2>nul | findstr /i /c:"app.py" >nul 2>&1
    if not errorlevel 1 (
        echo       Encerrando PID !PID! ...
        taskkill /PID !PID! /F >nul 2>&1
        set "FOUND=1"
    )
)

for /f "tokens=2 delims=," %%P in ('tasklist /FI "IMAGENAME eq pythonw.exe" /FO CSV /NH 2^>nul') do (
    set "PID=%%~P"
    wmic process where "ProcessId=!PID!" get CommandLine 2>nul | findstr /i /c:"app.py" >nul 2>&1
    if not errorlevel 1 (
        echo       Encerrando PID !PID! ...
        taskkill /PID !PID! /F >nul 2>&1
        set "FOUND=1"
    )
)

if "!FOUND!"=="0" (
    echo Nenhum processo app.py encontrado.
) else (
    echo Concluido.
)
endlocal
pause
