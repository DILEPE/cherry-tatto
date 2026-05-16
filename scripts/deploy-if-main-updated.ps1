# Actualiza la rama main desde origin si hay commits nuevos y reinicia API (uvicorn) y n8n (Docker).
# Pensado para una máquina de despliegue / tarea programada.
#
# Uso (desde la raíz del repo):
#   .\scripts\deploy-if-main-updated.ps1
#
# Variables de entorno opcionales:
#   DEPLOY_BRANCH          Rama a vigilar (por defecto: main)
#   REMOTE_NAME            Remoto git (por defecto: origin)
#   API_PORT               Puerto de Litestar/uvicorn (por defecto: 5000 o env API_PORT)
#   DEV_BIND_HOST          Host uvicorn (por defecto: 127.0.0.1 o env DEV_BIND_HOST)
#   CHERRY_PYTHON          Ruta a python.exe del venv (si no: .venv / venv en la raíz)
#   N8N_CONTAINER_NAME     Contenedor Docker de n8n (por defecto: cherry-n8n-local, igual que dev-stack.ps1)
#   SKIP_N8N_RESTART       "1" para no tocar Docker/n8n
#   SKIP_BACKEND_RESTART   "1" para no reiniciar uvicorn
#   GIT_PULL_EXTRA_ARGS    Ej.: "--ff-only" ya aplicado; puedes añadir más argumentos separados por espacio

[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$msg) { Write-Host "[deploy] $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg) { Write-Host "[deploy] $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "[deploy] $msg" -ForegroundColor Yellow }

$DeployBranch = if ($env:DEPLOY_BRANCH) { $env:DEPLOY_BRANCH.Trim() } else { "main" }
$RemoteName = if ($env:REMOTE_NAME) { $env:REMOTE_NAME.Trim() } else { "origin" }

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
Set-Location -LiteralPath $RepoRoot

if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot ".git"))) {
    Write-Warn "No hay .git en $RepoRoot"
    exit 2
}

$fetchRef = "${RemoteName}/${DeployBranch}"
Write-Info "Fetch $RemoteName $DeployBranch…"
& git fetch $RemoteName $DeployBranch
if ($LASTEXITCODE -ne 0) {
    Write-Warn "git fetch falló. Comprueba red y credenciales."
    exit 1
}

if (-not (git rev-parse --verify -q "refs/remotes/$fetchRef")) {
    Write-Warn "No existe refs/remotes/$fetchRef tras fetch. Comprueba el remoto y la rama."
    exit 3
}

# Confirmar que existe la rama local para comparar y hacer pull
if (-not (git rev-parse --verify -q "refs/heads/$DeployBranch")) {
    Write-Warn "No existe la rama local '$DeployBranch'. Crea y enlázala al remoto antes de usar este script."
    exit 4
}

$localHash = (git rev-parse "refs/heads/$DeployBranch").Trim()
$remoteHash = (git rev-parse "refs/remotes/$fetchRef").Trim()

if ($localHash -eq $remoteHash) {
    Write-Ok "Sin cambios: $DeployBranch local coincide con $fetchRef ($($localHash.Substring(0, 7))). No se reinicia nada."
    exit 0
}

$behind = [int](git rev-list --count "$DeployBranch..$fetchRef" 2>$null)
if ($behind -le 0) {
    Write-Warn "La rama local '$DeployBranch' no está detrás de $fetchRef (posible divergencia o commits locales). Hash local=$($localHash.Substring(0,7)) remoto=$($remoteHash.Substring(0,7)). No se hace pull automático."
    exit 5
}

Write-Info "Hay $behind commit(s) nuevo(s) en $fetchRef. Actualizando…"

if ($WhatIf) {
    Write-Ok "WhatIf: se haría git pull y reinicios."
    exit 0
}

& git checkout $DeployBranch
if ($LASTEXITCODE -ne 0) { exit 6 }

$pullArgs = @("pull", $RemoteName, $DeployBranch, "--ff-only")
if (-not [string]::IsNullOrWhiteSpace($env:GIT_PULL_EXTRA_ARGS)) {
    $pullArgs += ($env:GIT_PULL_EXTRA_ARGS -split '\s+')
}
& git @pullArgs
if ($LASTEXITCODE -ne 0) {
    Write-Warn "git pull falló (¿divergencia?). Resuelve manualmente y vuelve a ejecutar."
    exit 7
}

Write-Ok "Código actualizado a $(git rev-parse --short HEAD)."

# --- Reinicio backend (uvicorn Litestar) ---
$skipBack = $env:SKIP_BACKEND_RESTART -match '^1$|^true$|^yes$'
$skipN8n = $env:SKIP_N8N_RESTART -match '^1$|^true$|^yes$'

function Get-VenvPython {
    if (-not [string]::IsNullOrWhiteSpace($env:CHERRY_PYTHON) -and (Test-Path -LiteralPath $env:CHERRY_PYTHON)) {
        return (Resolve-Path -LiteralPath $env:CHERRY_PYTHON).Path
    }
    foreach ($folder in @(".venv", "venv")) {
        $candidate = Join-Path $RepoRoot "$folder\Scripts\python.exe"
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

function Stop-UvicornCherry {
    $repoEsc = [regex]::Escape($RepoRoot)
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue
        foreach ($p in $procs) {
            $cmd = [string]$p.CommandLine
            if (-not $cmd) { continue }
            if ($cmd -match 'uvicorn' -and $cmd -match 'app\.main:app' -and $cmd -match $repoEsc) {
                Write-Info "Deteniendo uvicorn PID $($p.ProcessId)…"
                Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
    }
    catch {
        Write-Warn "No se pudo enumerar procesos Python: $($_.Exception.Message)"
    }
}

function Start-UvicornCherry {
    $py = Get-VenvPython
    if (-not $py) {
        Write-Warn "No hay CHERRY_PYTHON ni .venv/venv; no se arranca el backend."
        return
    }
    $port = if ($env:API_PORT) { [int]$env:API_PORT } else { 5000 }
    $bind = if ($env:DEV_BIND_HOST) { $env:DEV_BIND_HOST.Trim() } else { "127.0.0.1" }
    $args = @("-m", "uvicorn", "app.main:app", "--host", $bind, "--port", "$port")
    Write-Info "Iniciando API en http://${bind}:${port} …"
    Start-Process -WindowStyle Minimized -FilePath $py -ArgumentList $args -WorkingDirectory $RepoRoot
}

function Restart-N8nDocker {
    $name = if ($env:N8N_CONTAINER_NAME) { $env:N8N_CONTAINER_NAME.Trim() } else { "cherry-n8n-local" }
    $docker = $null
    foreach ($n in @("docker.exe", "docker")) {
        $cmd = Get-Command $n -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
            $docker = $cmd.Source
            break
        }
    }
    $dockerExe = Join-Path ${env:ProgramFiles} "Docker\Docker\resources\bin\docker.exe"
    if (-not $docker -and (Test-Path -LiteralPath $dockerExe)) {
        $docker = $dockerExe
    }
    if (-not $docker) {
        Write-Warn "Docker no encontrado; omitiendo reinicio de n8n."
        return
    }
    Write-Info "Reiniciando contenedor Docker '$name'…"
    & $docker restart $name | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "docker restart falló (¿existe el contenedor?). Código: $LASTEXITCODE"
    }
    else {
        Write-Ok "n8n (Docker) reiniciado."
    }
}

if (-not $skipBack) {
    Stop-UvicornCherry
    Start-Sleep -Seconds 2
    Start-UvicornCherry
}
else {
    Write-Info "SKIP_BACKEND_RESTART activo; no se reinicia uvicorn."
}

if (-not $skipN8n) {
    Restart-N8nDocker
}
else {
    Write-Info "SKIP_N8N_RESTART activo; no se reinicia n8n."
}

Write-Ok "Listo."
exit 0
