# Arranca API Litestar, Streamlit y opcionalmente n8n en Windows (PowerShell nativo).
# Uso (desde la raíz del repo):
#   .\scripts\dev-stack.ps1
# Opcional:
#   $env:START_N8N = "0"; .\scripts\dev-stack.ps1     # sin n8n
#   .\scripts\dev-stack.ps1 -N8nMode none
#   .\scripts\dev-stack.ps1 -N8nMode auto   # por defecto: npx primero, Docker solo si no hay Node
#   .\scripts\dev-stack.ps1 -N8nMode docker
# Red local: $env:DEV_BIND_HOST='0.0.0.0' y abre http://<IP-de-esta-PC>:8501 desde otro equipo

[CmdletBinding()]
param(
    [int]$ApiPort = $(if ($env:API_PORT) { [int]$env:API_PORT } else { 5000 }),
    [int]$StreamlitPort = $(if ($env:STREAMLIT_PORT) { [int]$env:STREAMLIT_PORT } else { 8501 }),
    [int]$N8nPort = $(if ($env:N8N_PORT) { [int]$env:N8N_PORT } else { 5678 }),
    # Vacío = $env:START_N8N o auto (npx primero, sin Docker si tienes Node.js)
    [string]$N8nMode = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($N8nMode)) {
    switch -Regex ($env:START_N8N) {
        "^0$|^false$" { $N8nMode = "none" }
        "^npx$" { $N8nMode = "npx" }
        "^none$" { $N8nMode = "none" }
        "^auto$" { $N8nMode = "auto" }
        "^docker$" { $N8nMode = "docker" }
        default { $N8nMode = "auto" }
    }
}

if ($N8nMode -notin @("docker", "npx", "none", "auto")) {
    Write-Host "[error] -N8nMode debe ser docker, npx, none o auto (recibido: $N8nMode)" -ForegroundColor Red
    exit 1
}
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

# Orden: CHERRY_PYTHON explícito → .venv → venv (muchas máquinas usan la carpeta `venv`).
$venvPy = $null
if (-not [string]::IsNullOrWhiteSpace($env:CHERRY_PYTHON) -and (Test-Path -LiteralPath $env:CHERRY_PYTHON)) {
    $venvPy = (Resolve-Path -LiteralPath $env:CHERRY_PYTHON).Path
}
if (-not $venvPy) {
    foreach ($folder in @(".venv", "venv")) {
        $candidate = Join-Path $Root "$folder\Scripts\python.exe"
        if (Test-Path -LiteralPath $candidate) {
            $venvPy = (Resolve-Path -LiteralPath $candidate).Path
            break
        }
    }
}
if (-not $venvPy) {
    Write-Host "[error] No se encontró Python del entorno virtual (.venv ni venv)." -ForegroundColor Red
    Write-Host "  python -m venv .venv" -ForegroundColor Gray
    Write-Host "  .\.venv\Scripts\python -m pip install -r requirements.txt" -ForegroundColor Gray
    Write-Host "  (o define CHERRY_PYTHON con la ruta completa a python.exe)" -ForegroundColor Gray
    exit 1
}

$n8nContainer = "cherry-n8n-local"

function Get-DockerExe {
    foreach ($name in @("docker.exe", "docker")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
            return $cmd.Source
        }
    }
    $candidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe")
    )
    $pf86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    if ($pf86) {
        $candidates += (Join-Path $pf86 "Docker\Docker\resources\bin\docker.exe")
    }
    foreach ($p in $candidates) {
        if ($p -and (Test-Path -LiteralPath $p)) {
            return $p
        }
    }
    return $null
}

function Get-NpxExe {
    foreach ($name in @("npx.cmd", "npx.exe", "npx")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
            return $cmd.Source
        }
    }
    $npxCmdPath = Join-Path $env:ProgramFiles "nodejs\npx.cmd"
    if (Test-Path -LiteralPath $npxCmdPath) {
        return $npxCmdPath
    }
    $local = [Environment]::GetFolderPath("LocalApplicationData")
    $npxLocal = Join-Path $local "Programs\nodejs\npx.cmd"
    if (Test-Path -LiteralPath $npxLocal) {
        return $npxLocal
    }
    return $null
}

function Stop-N8nDocker {
    if ([string]::IsNullOrWhiteSpace($script:DockerExePath)) {
        return
    }
    # Sin tubería para no pisar $LASTEXITCODE antes de docker run.
    $null = & $script:DockerExePath @("rm", "-f", $n8nContainer) 2>&1
}

function Start-N8nDocker {
    if ([string]::IsNullOrWhiteSpace($script:DockerExePath)) {
        return $false
    }
    Stop-N8nDocker
    $tz = if ([string]::IsNullOrWhiteSpace($env:TZ)) { "America/Bogota" } else { $env:TZ }
    $runArgs = @(
        "run", "-d", "--rm", "--name", $n8nContainer,
        "-p", "${N8nPort}:5678",
        "-e", "TZ=$tz",
        "n8nio/n8n:latest"
    )
    # Sin tubería: con "| Out-Null", $? no refleja el fallo de docker.
    & $script:DockerExePath @runArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[aviso] docker run falló (¿Docker Desktop abierto y el daemon listo?). Código: $LASTEXITCODE" -ForegroundColor Yellow
        return $false
    }
    Write-Host "[ok] n8n → http://127.0.0.1:$N8nPort" -ForegroundColor Green
    return $true
}

$script:DockerExePath = $null
$n8nDockerStarted = $false

if ($N8nMode -eq "docker") {
    $script:DockerExePath = Get-DockerExe
    if ($script:DockerExePath) {
        if (Start-N8nDocker) {
            $n8nDockerStarted = $true
        }
    }
    else {
        Write-Host "[aviso] Docker no encontrado (PATH ni carpeta típica de Docker Desktop)." -ForegroundColor Yellow
    }
}
elseif ($N8nMode -eq "npx") {
    $npxExePath = Get-NpxExe
    if (-not $npxExePath) {
        Write-Host "[error] npx no encontrado (instala Node.js LTS)." -ForegroundColor Red
        exit 1
    }
    $env:N8N_PORT = "$N8nPort"
    Start-Process -WindowStyle Minimized -FilePath $npxExePath -ArgumentList @("--yes", "n8n") -WorkingDirectory $Root
    Write-Host "[ok] n8n (npx, sin Docker) → http://127.0.0.1:$N8nPort" -ForegroundColor Green
}
elseif ($N8nMode -eq "auto") {
    $npxExePath = Get-NpxExe
    if ($npxExePath) {
        $env:N8N_PORT = "$N8nPort"
        Start-Process -WindowStyle Minimized -FilePath $npxExePath -ArgumentList @("--yes", "n8n") -WorkingDirectory $Root
        Write-Host "[ok] n8n (npx, sin Docker) → http://127.0.0.1:$N8nPort" -ForegroundColor Green
    }
    else {
        $script:DockerExePath = Get-DockerExe
        if ($script:DockerExePath) {
            Write-Host "[info] npx no encontrado; intentando n8n con Docker…" -ForegroundColor DarkGray
            if (Start-N8nDocker) {
                $n8nDockerStarted = $true
            }
        }
        else {
            Write-Host "[aviso] Sin Node.js (npx) ni Docker; omitiendo n8n. API y Streamlit siguen." -ForegroundColor Yellow
        }
    }
}

# Escucha: 127.0.0.1 (solo esta máquina) o 0.0.0.0 (red local). Ej.: $env:DEV_BIND_HOST='0.0.0.0'
$BindHost = $env:DEV_BIND_HOST
if ([string]::IsNullOrWhiteSpace($BindHost)) {
    $BindHost = "127.0.0.1"
}

$apiArgs = @("-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", "$ApiPort")
$slArgs = @(
    "-m", "streamlit", "run", "streamlit_app/main.py",
    "--server.address", $BindHost,
    "--server.port", "$StreamlitPort"
)

Write-Host "[ok] API Litestar → http://127.0.0.1:$ApiPort (bind $BindHost)" -ForegroundColor Green
Write-Host "[ok] Streamlit    → http://127.0.0.1:$StreamlitPort (bind $BindHost)" -ForegroundColor Green
if ($BindHost -eq "0.0.0.0") {
    Write-Host "[info] Desde otra máquina en la LAN: http://<IP-de-esta-PC>:$StreamlitPort (panel) y :$ApiPort (API)" -ForegroundColor DarkGray
    Write-Host "[info] El panel sigue usando API en esta PC (API_BASE_URL en .env puede seguir en 127.0.0.1)." -ForegroundColor DarkGray
}

$apiProc = $null
try {
    $apiProc = Start-Process -PassThru -NoNewWindow -FilePath $venvPy -ArgumentList $apiArgs -WorkingDirectory $Root
    Start-Sleep -Seconds 2

    & $venvPy $slArgs
}
finally {
    if ($null -ne $apiProc -and -not $apiProc.HasExited) {
        Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($n8nDockerStarted -and -not [string]::IsNullOrWhiteSpace($script:DockerExePath)) {
        & $script:DockerExePath stop $n8nContainer 2>$null | Out-Null
    }
}
