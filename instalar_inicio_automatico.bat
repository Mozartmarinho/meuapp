@echo off
chcp 65001 >nul
title Instalar inicio automatico - Sao Geraldo Service

cd /d "%~dp0"

echo.
echo === MeuApp - Iniciar com o Windows ===
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\instalar_inicio_automatico.ps1" -StartNow
if errorlevel 1 (
    echo.
    echo Falha ao instalar. Tente executar este arquivo como Administrador.
    pause
    exit /b 1
)

echo.
pause
