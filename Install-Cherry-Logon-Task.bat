@echo off
setlocal EnableExtensions
title Cherry Tattoo — arranque al iniciar sesion

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\scripts\install-logon-task.ps1" (
  echo [error] No se encuentra scripts\install-logon-task.ps1
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\install-logon-task.ps1"
if errorlevel 1 (
  echo.
  echo [error] No se pudo registrar el arranque.
  pause
  exit /b 1
)

echo.
pause
