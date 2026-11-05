# Detiene el stack arrancado en segundo plano (API, panel y n8n).
# Uso: .\scripts\stop-dev-stack.ps1

$ErrorActionPreference = "Continue"
$StateDir = Join-Path $env:LOCALAPPDATA "CherryTattoo"
$PidDir = Join-Path $StateDir "pids"

function Stop-PidTree {
    param([int]$ProcessId, [string]$Label)
    if ($ProcessId -le 0) { return }
    $alive = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $alive) { return }
    & taskkill.exe /PID $ProcessId /T /F 1>$null 2>$null
    Write-Host "[ok] $Label (PID $ProcessId) detenido." -ForegroundColor Green
}

if (Test-Path -LiteralPath $PidDir) {
    Get-ChildItem -LiteralPath $PidDir -Filter "*.pid" | ForEach-Object {
        $raw = (Get-Content -LiteralPath $_.FullName -ErrorAction SilentlyContinue | Select-Object -First 1)
        $procId = 0
        if ([int]::TryParse([string]$raw, [ref]$procId)) {
            Stop-PidTree -ProcessId $procId -Label $_.BaseName
        }
        Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
    }
    $modeFile = Join-Path $PidDir "n8n.mode"
    if (Test-Path -LiteralPath $modeFile) {
        Remove-Item -LiteralPath $modeFile -Force -ErrorAction SilentlyContinue
    }
}

$docker = $null
foreach ($name in @("docker.exe", "docker")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { $docker = $cmd.Source; break }
}
if (-not $docker) {
    $candidate = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $candidate) { $docker = $candidate }
}
if ($docker) {
    & $docker rm -f "cherry-n8n-local" 1>$null 2>$null
}

Get-CimInstance Win32_Process | ForEach-Object {
    $line = $_.CommandLine
    if (-not $line) { return }
    $matchApi = $line -match 'app\.main:app'
    $matchPanel = $line -match 'cherry_tattoo_angular' -and $line -match 'ng(\.cmd)?(\s|")'
    $matchN8n = $line -match 'npx(\.cmd)?' -and $line -match '\bn8n\b'
    if (-not ($matchApi -or $matchPanel -or $matchN8n)) { return }
    Stop-PidTree -ProcessId $_.ProcessId -Label "proceso del stack"
}

Write-Host "[ok] Stack detenido. Los puertos quedan libres para el próximo arranque." -ForegroundColor Green
Write-Host "[info] La tarea de inicio de sesión sigue registrada. Para quitarla: .\scripts\install-logon-task.ps1 -Unregister" -ForegroundColor DarkGray
