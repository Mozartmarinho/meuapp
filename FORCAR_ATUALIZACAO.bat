@echo off
chcp 65001 >nul
title Forcar atualizacao - Sao Geraldo Service
cd /d "%~dp0"
echo.
echo Fecha o app antigo e sobe o projeto meuapp da pasta:
echo   %~dp0
echo.
call "%~dp0iniciar_meuapp.bat"
