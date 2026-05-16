@echo off
setlocal EnableExtensions
title Cherry Tattoo — acceso directo en escritorio

set "CHERRY_REPO=%~dp0"
if "%CHERRY_REPO:~-1%"=="\" set "CHERRY_REPO=%CHERRY_REPO:~0,-1%"

set "LAUNCH_BAT=%CHERRY_REPO%\Launch-Cherry-Dev-Stack.bat"
if not exist "%LAUNCH_BAT%" (
  echo No se encuentra Launch-Cherry-Dev-Stack.bat en la raíz del proyecto.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CHERRY_REPO%\scripts\install-desktop-shortcut.ps1" -RepoRoot "%CHERRY_REPO%"

if errorlevel 1 (
  echo No se pudo crear el acceso directo ni el BAT del escritorio.
  pause
  exit /b 1
)

echo.
echo Listo. En el escritorio tienes "Cherry Tattoo Dev" y Cherry-Tattoo-Iniciar.bat
pause
