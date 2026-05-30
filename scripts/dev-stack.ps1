# Arranca API Litestar y opcionalmente el panel Angular y n8n (Windows PowerShell).
# Uso (desde la raíz del repo):
#   .\scripts\dev-stack.ps1
# Opcional:
#   $env:START_N8N = "0"; .\scripts\dev-stack.ps1
#   $env:START_PANEL = "1"; .\scripts\dev-stack.ps1   # npm start en panel-frontend o cherry_tattoo_angular
#   .\scripts\dev-stack.ps1 -N8nMode none
# Red local API: $env:DEV_BIND_HOST='0.0.0.0'

[CmdletBinding()]
param(
    [int]$ApiPort = $(if ($env:API_PORT) { [int]$env:API_PORT } else { 5000 }),
    [int]$PanelPort = $(if ($env:PANEL_PORT) { [int]$env:PANEL_PORT } else { 4200 }),
    [int]$N8nPort = $(if ($env:N8N_PORT) { [int]$env:N8N_PORT } else { 5678 }),
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
    $candidates = @((Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"))
    foreach ($p in $candidates) {
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
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
    if (Test-Path -LiteralPath $npxCmdPath) { return $npxCmdPath }
    return $null
}

function Stop-N8nDocker {
    if ([string]::IsNullOrWhiteSpace($script:DockerExePath)) { return }
    $null = & $script:DockerExePath @("rm", "-f", $n8nContainer) 2>&1
}

function Start-N8nDocker {
    if ([string]::IsNullOrWhiteSpace($script:DockerExePath)) { return $false }
    Stop-N8nDocker
    $tz = if ([string]::IsNullOrWhiteSpace($env:TZ)) { "America/Bogota" } else { $env:TZ }
    & $script:DockerExePath @("run", "-d", "--rm", "--name", $n8nContainer, "-p", "${N8nPort}:5678", "-e", "TZ=$tz", "n8nio/n8n:latest")
    if ($LASTEXITCODE -ne 0) { return $false }
    Write-Host "[ok] n8n → http://127.0.0.1:$N8nPort" -ForegroundColor Green
    return $true
}

$script:DockerExePath = $null
$n8nDockerStarted = $false

if ($N8nMode -eq "docker") {
    $script:DockerExePath = Get-DockerExe
    if ($script:DockerExePath) { $n8nDockerStarted = Start-N8nDocker }
}
elseif ($N8nMode -eq "npx") {
    $npxExePath = Get-NpxExe
    if ($npxExePath) {
        $env:N8N_PORT = "$N8nPort"
        Start-Process -WindowStyle Minimized -FilePath $npxExePath -ArgumentList @("--yes", "n8n") -WorkingDirectory $Root
        Write-Host "[ok] n8n (npx) → http://127.0.0.1:$N8nPort" -ForegroundColor Green
    }
}
elseif ($N8nMode -eq "auto") {
    $npxExePath = Get-NpxExe
    if ($npxExePath) {
        $env:N8N_PORT = "$N8nPort"
        Start-Process -WindowStyle Minimized -FilePath $npxExePath -ArgumentList @("--yes", "n8n") -WorkingDirectory $Root
        Write-Host "[ok] n8n (npx) → http://127.0.0.1:$N8nPort" -ForegroundColor Green
    }
    else {
        $script:DockerExePath = Get-DockerExe
        if ($script:DockerExePath) { $n8nDockerStarted = Start-N8nDocker }
    }
}

$BindHost = $env:DEV_BIND_HOST
if ([string]::IsNullOrWhiteSpace($BindHost)) { $BindHost = "127.0.0.1" }

function Resolve-PanelRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:CHERRY_ANGULAR_ROOT)) {
        $p = $env:CHERRY_ANGULAR_ROOT.Trim().TrimEnd('\')
        if (Test-Path (Join-Path $p "package.json")) { return $p }
    }
    $sibling = Join-Path (Split-Path $Root -Parent) "cherry_tattoo_angular"
    if (Test-Path (Join-Path $sibling "package.json")) { return $sibling }
    $embedded = Join-Path $Root "panel-frontend"
    if (Test-Path (Join-Path $embedded "package.json")) { return $embedded }
    return $null
}

function Should-StartPanel {
    if ($env:START_PANEL -match '^(1|true|yes|on)$') { return $true }
    return $false
}

$panelProc = $null
if (Should-StartPanel) {
    $panelRoot = Resolve-PanelRoot
    if ($panelRoot) {
        $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if ($npm) {
            $panelProc = Start-Process -PassThru -WindowStyle Minimized -FilePath $npm.Source -ArgumentList @("start") -WorkingDirectory $panelRoot
            Write-Host "[ok] Panel Angular → http://127.0.0.1:$PanelPort (proxy API :$ApiPort)" -ForegroundColor Green
        }
    }
    else {
        Write-Host "[aviso] START_PANEL=1 pero no hay package.json en cherry_tattoo_angular ni panel-frontend." -ForegroundColor Yellow
    }
}

$apiArgs = @("-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", "$ApiPort")
Write-Host "[ok] API Litestar → http://127.0.0.1:$ApiPort (bind $BindHost)" -ForegroundColor Green
if (-not $panelProc) {
    Write-Host "[info] Panel Angular: en otra terminal, cd cherry_tattoo_angular && npm start" -ForegroundColor DarkGray
    Write-Host "[info] O: `$env:START_PANEL='1'; .\scripts\dev-stack.ps1" -ForegroundColor DarkGray
}
Write-Host "[info] Ctrl+C detiene la API (y n8n Docker si aplica)." -ForegroundColor DarkGray

try {
    & $venvPy $apiArgs
}
finally {
    if ($null -ne $panelProc -and -not $panelProc.HasExited) {
        Stop-Process -Id $panelProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($n8nDockerStarted -and -not [string]::IsNullOrWhiteSpace($script:DockerExePath)) {
        & $script:DockerExePath stop $n8nContainer 2>$null | Out-Null
    }
}
