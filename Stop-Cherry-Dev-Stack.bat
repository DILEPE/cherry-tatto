@echo off
setlocal EnableExtensions
title Cherry Tattoo — detener stack

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\scripts\stop-dev-stack.ps1" (
  echo [error] No se encuentra scripts\stop-dev-stack.ps1
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\stop-dev-stack.ps1"
echo.
pause
