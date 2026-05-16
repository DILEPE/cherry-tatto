@echo off
setlocal EnableExtensions
title Cherry Tattoo — sincronizar main y reiniciar API / n8n

REM Raíz del proyecto (carpeta donde está este BAT).
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if exist "%ROOT%\scripts\deploy-if-main-updated.ps1" goto :found

if not defined CHERRY_TATTOO_ROOT goto :notfound
set "_T=%CHERRY_TATTOO_ROOT%"
if "%_T:~-1%"=="\" set "_T=%_T:~0,-1%"
if exist "%_T%\scripts\deploy-if-main-updated.ps1" (
  set "ROOT=%_T%"
  goto :found
)

:notfound
echo [error] No se encuentra scripts\deploy-if-main-updated.ps1
echo Carpeta probada: "%ROOT%"
echo Opcional: define CHERRY_TATTOO_ROOT con la ruta del repo.
pause
exit /b 1

:found
cd /d "%ROOT%"
set "PATH=%ProgramFiles%\Docker\Docker\resources\bin;%PATH%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\deploy-if-main-updated.ps1"
set "EC=%ERRORLEVEL%"
if %EC% equ 0 (
  echo.
  echo [ok] Sin acciones o despliegue aplicado correctamente.
) else if %EC% equ 5 (
  echo.
  echo [aviso] Rama local no esta detras del remoto ^(revisa divergencia^).
) else (
  echo.
  echo [error] Codigo de salida: %EC%
)
exit /b %EC%
