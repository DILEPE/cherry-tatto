# Actualiza backend + frontend desde origin/main (si hay commits nuevos) y reinicia servicios.
# Pensado para máquina de despliegue / tarea programada / Sync-Main-And-Restart.bat
#
# Uso (desde la raíz del backend cherry_tattoo):
#   .\scripts\deploy-if-main-updated.ps1
#
# Variables de entorno opcionales:
#   DEPLOY_BRANCH          Rama a vigilar (por defecto: main)
#   REMOTE_NAME            Remoto git (por defecto: origin)
#   CHERRY_ANGULAR_ROOT    Ruta del panel (por defecto: ../cherry_tattoo_angular)
#   SKIP_FRONTEND_SYNC     "1" para no tocar el repo Angular
#   SKIP_BACKEND_SYNC      "1" para no tocar el repo API
#   API_PORT               Puerto uvicorn (por defecto: 5000)
#   DEV_BIND_HOST          Host uvicorn (por defecto: 127.0.0.1)
#   PANEL_PORT             Puerto ng serve (por defecto: 4200)
#   CHERRY_PYTHON          python.exe del venv
#   N8N_CONTAINER_NAME     Contenedor Docker n8n (por defecto: cherry-n8n-local)
#   SKIP_N8N_RESTART       "1" para no reiniciar n8n
#   SKIP_BACKEND_RESTART   "1" para no reiniciar uvicorn
#   SKIP_FRONTEND_RESTART  "1" para no reiniciar ng serve
#   GIT_PULL_EXTRA_ARGS    Argumentos extra de git pull (además de --ff-only)

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
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

function Resolve-AngularRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:CHERRY_ANGULAR_ROOT)) {
        $p = $env:CHERRY_ANGULAR_ROOT.Trim().TrimEnd('\', '/')
        if (Test-Path -LiteralPath (Join-Path $p "package.json")) {
            return (Resolve-Path -LiteralPath $p).Path
        }
        Write-Warn "CHERRY_ANGULAR_ROOT no es un panel válido: $p"
        return $null
    }
    $sibling = Join-Path (Split-Path $RepoRoot -Parent) "cherry_tattoo_angular"
    if (Test-Path -LiteralPath (Join-Path $sibling "package.json")) {
        return (Resolve-Path -LiteralPath $sibling).Path
    }
    return $null
}

# Resultado: Updated | Unchanged | Missing | Error
function Sync-GitBranch {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if (-not (Test-Path -LiteralPath (Join-Path $Root ".git"))) {
        Write-Warn "${Label}: no hay .git en $Root"
        return "Missing"
    }

    Push-Location -LiteralPath $Root
    try {
        $fetchRef = "${RemoteName}/${DeployBranch}"
        Write-Info "${Label}: fetch $RemoteName $DeployBranch..."
        & git fetch $RemoteName $DeployBranch
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "${Label}: git fetch falló."
            return "Error"
        }

        if (-not (git rev-parse --verify -q "refs/remotes/$fetchRef")) {
            Write-Warn "${Label}: no existe refs/remotes/$fetchRef."
            return "Error"
        }
        if (-not (git rev-parse --verify -q "refs/heads/$DeployBranch")) {
            Write-Warn "${Label}: no existe rama local '$DeployBranch'. Créala y enlázala al remoto."
            return "Error"
        }

        $localHash = (git rev-parse "refs/heads/$DeployBranch").Trim()
        $remoteHash = (git rev-parse "refs/remotes/$fetchRef").Trim()

        if ($localHash -eq $remoteHash) {
            Write-Ok "${Label}: sin cambios ($DeployBranch = $($localHash.Substring(0, 7)))."
            return "Unchanged"
        }

        $behind = [int](git rev-list --count "$DeployBranch..$fetchRef" 2>$null)
        if ($behind -le 0) {
            Write-Warn "${Label}: local no está detrás de $fetchRef (divergencia?). local=$($localHash.Substring(0,7)) remoto=$($remoteHash.Substring(0,7))."
            return "Error"
        }

        Write-Info "${Label}: $behind commit(s) nuevo(s) en $fetchRef."

        if ($WhatIf) {
            Write-Ok "${Label}: WhatIf - se haría git pull."
            return "Updated"
        }

        & git checkout $DeployBranch
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "${Label}: git checkout $DeployBranch falló."
            return "Error"
        }

        $pullArgs = @("pull", $RemoteName, $DeployBranch, "--ff-only")
        if (-not [string]::IsNullOrWhiteSpace($env:GIT_PULL_EXTRA_ARGS)) {
            $pullArgs += ($env:GIT_PULL_EXTRA_ARGS -split '\s+' | Where-Object { $_ })
        }
        & git @pullArgs
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "${Label}: git pull falló (¿divergencia?)."
            return "Error"
        }

        Write-Ok "${Label}: actualizado a $(git rev-parse --short HEAD)."
        return "Updated"
    }
    finally {
        Pop-Location
    }
}

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
                Write-Info "Deteniendo uvicorn PID $($p.ProcessId)..."
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
    Write-Info "Iniciando API en http://${bind}:${port} ..."
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
    Write-Info "Reiniciando contenedor Docker '$name'..."
    & $docker restart $name | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "docker restart falló (¿existe el contenedor?). Código: $LASTEXITCODE"
    }
    else {
        Write-Ok "n8n (Docker) reiniciado."
    }
}

function Stop-AngularPanel([string]$AngularRoot) {
    $rootEsc = [regex]::Escape($AngularRoot)
    $rootNorm = $AngularRoot.Replace('\', '/')
    $rootNormEsc = [regex]::Escape($rootNorm)
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue
        foreach ($p in $procs) {
            $cmd = [string]$p.CommandLine
            if (-not $cmd) { continue }
            $isNg = ($cmd -match 'ng(\.js)?\s+serve') -or ($cmd -match '@angular\\cli\\bin\\ng') -or ($cmd -match 'npm(\.cmd)?\s+start')
            if (-not $isNg) { continue }
            if ($cmd -match $rootEsc -or $cmd -match $rootNormEsc) {
                Write-Info "Deteniendo panel Angular PID $($p.ProcessId)..."
                Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
        # También procesos en el puerto del panel
        $panelPort = if ($env:PANEL_PORT) { [int]$env:PANEL_PORT } else { 4200 }
        $conns = Get-NetTCPConnection -LocalPort $panelPort -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            if ($c.OwningProcess -gt 0) {
                Write-Info "Deteniendo proceso en puerto $panelPort (PID $($c.OwningProcess))..."
                Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
            }
        }
    }
    catch {
        Write-Warn "No se pudo detener el panel Angular: $($_.Exception.Message)"
    }
}

function Start-AngularPanel([string]$AngularRoot) {
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) {
        $npm = Get-Command npm -ErrorAction SilentlyContinue
    }
    if (-not $npm) {
        Write-Warn "npm no está en el PATH; no se arranca el panel."
        return
    }
    $panelPort = if ($env:PANEL_PORT) { [int]$env:PANEL_PORT } else { 4200 }
    Write-Info "Iniciando panel Angular (npm start) en $AngularRoot (puerto $panelPort)..."
    $env:PORT = "$panelPort"
    Start-Process -WindowStyle Minimized -FilePath $npm.Source -ArgumentList @("start", "--", "--port", "$panelPort") -WorkingDirectory $AngularRoot
}

# --- Sync repos ---
$skipBackSync = $env:SKIP_BACKEND_SYNC -match '^1$|^true$|^yes$'
$skipFrontSync = $env:SKIP_FRONTEND_SYNC -match '^1$|^true$|^yes$'

$backendStatus = "Unchanged"
$frontendStatus = "Missing"

if (-not $skipBackSync) {
    $backendStatus = Sync-GitBranch -Root $RepoRoot -Label "Backend"
}
else {
    Write-Info "SKIP_BACKEND_SYNC activo."
}

$angularRoot = Resolve-AngularRoot
if ($skipFrontSync) {
    Write-Info "SKIP_FRONTEND_SYNC activo."
    $frontendStatus = "Unchanged"
}
elseif ($angularRoot) {
    Write-Info "Panel Angular: $angularRoot"
    $frontendStatus = Sync-GitBranch -Root $angularRoot -Label "Frontend"
}
else {
    Write-Warn "No se encontró cherry_tattoo_angular (usa CHERRY_ANGULAR_ROOT). Solo se gestiona el backend."
    $frontendStatus = "Missing"
}

if ($backendStatus -eq "Error" -or $frontendStatus -eq "Error") {
    Write-Warn "Hubo errores al sincronizar. Revisa los mensajes anteriores."
    exit 1
}

$anyUpdated = ($backendStatus -eq "Updated") -or ($frontendStatus -eq "Updated")
if (-not $anyUpdated) {
    Write-Ok "Backend y frontend al día en '$DeployBranch'. No se reinicia nada."
    exit 0
}

if ($WhatIf) {
    Write-Ok "WhatIf: se reiniciarían los servicios afectados."
    exit 0
}

# --- Reinicios ---
$skipBack = $env:SKIP_BACKEND_RESTART -match '^1$|^true$|^yes$'
$skipN8n = $env:SKIP_N8N_RESTART -match '^1$|^true$|^yes$'
$skipFront = $env:SKIP_FRONTEND_RESTART -match '^1$|^true$|^yes$'

if ($backendStatus -eq "Updated") {
    if (-not $skipBack) {
        Stop-UvicornCherry
        Start-Sleep -Seconds 2
        Start-UvicornCherry
    }
    else {
        Write-Info "SKIP_BACKEND_RESTART activo."
    }
    if (-not $skipN8n) {
        Restart-N8nDocker
    }
    else {
        Write-Info "SKIP_N8N_RESTART activo."
    }
}

if ($frontendStatus -eq "Updated" -and $angularRoot) {
    if (-not $skipFront) {
        Stop-AngularPanel -AngularRoot $angularRoot
        Start-Sleep -Seconds 2
        Start-AngularPanel -AngularRoot $angularRoot
    }
    else {
        Write-Info "SKIP_FRONTEND_RESTART activo."
    }
}

Write-Ok ("Listo (backend={0}, frontend={1})." -f $backendStatus, $frontendStatus)
exit 0
