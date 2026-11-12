' Legacy hidden launcher. Prefer scripts\iniciar_autostart.ps1 via the scheduled task.
Option Explicit
Dim sh, starter
Set sh = CreateObject("WScript.Shell")
starter = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\MeuApp\iniciar_autostart.ps1")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & starter & """", 0, False
