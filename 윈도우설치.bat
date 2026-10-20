@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\manage.ps1" install
set "soundnote_exit=%errorlevel%"
pause
exit /b %soundnote_exit%
