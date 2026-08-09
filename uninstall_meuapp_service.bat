@echo off
REM Desinstalar o serviço do meuapp

net stop meuapp
nssm remove meuapp confirm

pause
