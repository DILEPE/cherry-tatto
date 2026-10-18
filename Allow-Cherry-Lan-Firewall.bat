@echo off
setlocal EnableExtensions
title Cherry Tattoo — firewall red local

REM Necesita administrador. Si no lo es, relanza con UAC.
net session >nul 2>&1
if %errorLevel% neq 0 (
  echo Solicitando permisos de administrador...
  powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

set "ROOT=%~dp0"
set "_T=%ROOT%"
if "%_T:~-1%"=="\" set "_T=%_T:~0,-1%"

if exist "%_T%\scripts\allow-lan-firewall.ps1" goto :found

if not defined CHERRY_TATTOO_ROOT goto :notfound
set "_T=%CHERRY_TATTOO_ROOT%"
if "%_T:~-1%"=="\" set "_T=%_T:~0,-1%"
if exist "%_T%\scripts\allow-lan-firewall.ps1" (
  set "ROOT=%_T%\"
  goto :found
)

:notfound
echo.
echo [error] No se encuentra scripts\allow-lan-firewall.ps1
echo Carpeta probada: "%_T%"
echo Ejecuta este BAT desde la carpeta del proyecto, o define CHERRY_TATTOO_ROOT.
echo.
pause
exit /b 1

:found
cd /d "%ROOT%"
echo Abriendo puertos LAN: panel 4200, API 5000, n8n 5678 ...
echo Al terminar veras la red y la IP para conectar desde otro equipo.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\allow-lan-firewall.ps1"
if errorlevel 1 (
  echo.
  echo [error] No se pudieron crear las reglas de firewall.
  pause
  exit /b 1
)
echo.
pause
exit /b 0
