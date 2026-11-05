# Registra el arranque oculto de API + panel + n8n al iniciar sesión.
# Uso (desde la raíz del repo, sin administrador):
#   .\scripts\install-logon-task.ps1
# Quitar la tarea:
#   .\scripts\install-logon-task.ps1 -Unregister
# La red local sigue entrando por 0.0.0.0 en los puertos del stack (4200, 5000, 5678).

[CmdletBinding()]
param(
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$TaskName = "Cherry Tattoo Dev Stack"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$stackScript = Join-Path $Root "scripts\dev-stack.ps1"
if (-not (Test-Path -LiteralPath $stackScript)) {
    Write-Host "[error] No se encuentra $stackScript" -ForegroundColor Red
    exit 1
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "[ok] Tarea anterior '$TaskName' eliminada." -ForegroundColor Yellow
}

if ($Unregister) {
    Write-Host "[ok] El stack ya no arranca al iniciar sesión." -ForegroundColor Green
    exit 0
}

$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$stackScript`" -Background"
$action = New-ScheduledTaskAction -Execute $powershell -Argument $arg -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT30S"
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Arranca Cherry Tattoo (API, panel y n8n) al iniciar sesión, sin ventanas. La red local usa la IP de este equipo." | Out-Null

Write-Host "[ok] Tarea '$TaskName' registrada para $($env:USERNAME) (30 s después de iniciar sesión)." -ForegroundColor Green
Write-Host "[ok] Arrancando ahora en segundo plano..." -ForegroundColor Green
& $stackScript -Background
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "[ok] Direcciones: $env:LOCALAPPDATA\CherryTattoo\urls.txt" -ForegroundColor Cyan
Write-Host "[info] Detener: Stop-Cherry-Dev-Stack.bat" -ForegroundColor DarkGray
