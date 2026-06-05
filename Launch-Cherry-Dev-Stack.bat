@echo off
setlocal EnableExtensions
title Cherry Tattoo — API + panel Angular

REM Raíz del proyecto: carpeta donde está este BAT (si está en el repo).
set "ROOT=%~dp0"

REM Quitar barra final para comprobar rutas
set "_T=%ROOT%"
if "%_T:~-1%"=="\" set "_T=%_T:~0,-1%"

if exist "%_T%\scripts\dev-stack.ps1" goto :found

REM Si copiaste este BAT al escritorio, usa CHERRY_TATTOO_ROOT (ruta al repo, sin barra final).
if not defined CHERRY_TATTOO_ROOT goto :notfound
set "_T=%CHERRY_TATTOO_ROOT%"
if "%_T:~-1%"=="\" set "_T=%_T:~0,-1%"
if exist "%_T%\scripts\dev-stack.ps1" (
  set "ROOT=%_T%\"
  goto :found
)

:notfound
echo.
echo [error] No se encuentra scripts\dev-stack.ps1
echo Carpeta probada: "%_T%"
echo.
echo Soluciones:
echo   - Ejecuta una vez "Install-Cherry-Desktop-Shortcut.bat" en la carpeta del proyecto ^(crea un lanzador en el escritorio^).
echo   - O define variable de usuario CHERRY_TATTOO_ROOT = ruta del repo ^(ej. C:\Proyectos\cherry_tattoo^).
echo   - No copies Launch-Cherry-Dev-Stack.bat al escritorio sin esa variable.
echo.
pause
exit /b 1

:found
cd /d "%ROOT%"
REM Panel Angular: repo hermano cherry_tattoo_angular (npm start, puerto 4200).
REM Solo API sin panel: set START_PANEL=0 antes de ejecutar este BAT.
REM Ruta distinta al panel: set CHERRY_ANGULAR_ROOT=C:\ruta\cherry_tattoo_angular
if not defined START_PANEL set "START_PANEL=1"
REM Al abrir desde el escritorio, Docker y Node suelen faltar en PATH aunque estén instalados.
set "PATH=%ProgramFiles%\Docker\Docker\resources\bin;%PATH%"
set "PATH=%ProgramFiles%\nodejs;%PATH%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\dev-stack.ps1"
if errorlevel 1 (
  echo.
  pause
)
