@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\manage.ps1" run
set "soundnote_exit=%errorlevel%"
if not "%soundnote_exit%"=="0" pause
exit /b %soundnote_exit%
