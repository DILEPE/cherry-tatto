# Arranca API Litestar y opcionalmente el panel Angular y n8n (Windows PowerShell).
# Uso (desde la raíz del repo):
#   .\scripts\dev-stack.ps1
# Opcional:
#   $env:START_N8N = "0"; .\scripts\dev-stack.ps1
#   $env:START_PANEL = "1"; .\scripts\dev-stack.ps1   # npm start en cherry_tattoo_angular
#   .\scripts\dev-stack.ps1 -N8nMode none
#   .\scripts\dev-stack.ps1 -Background   # sin ventanas; la API no se queda en esta consola
# Red local: API y panel escuchan en 0.0.0.0 por defecto.
# Solo este PC: $env:DEV_BIND_HOST='127.0.0.1'
# Logs y PID del modo -Background: %LOCALAPPDATA%\CherryTattoo

[CmdletBinding()]
param(
    [int]$ApiPort = $(if ($env:API_PORT) { [int]$env:API_PORT } else { 5000 }),
    [int]$PanelPort = $(if ($env:PANEL_PORT) { [int]$env:PANEL_PORT } else { 4200 }),
    [int]$N8nPort = $(if ($env:N8N_PORT) { [int]$env:N8N_PORT } else { 5678 }),
    [string]$N8nMode = "",
    [switch]$Background
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

foreach ($extraPath in @(
    (Join-Path $env:ProgramFiles "nodejs"),
    (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin")
)) {
    if ($extraPath -and (Test-Path -LiteralPath $extraPath)) {
        $env:PATH = "$extraPath;$env:PATH"
    }
}

$StateDir = Join-Path $env:LOCALAPPDATA "CherryTattoo"
$LogDir = Join-Path $StateDir "logs"
$PidDir = Join-Path $StateDir "pids"
if ($Background) {
    New-Item -ItemType Directory -Force -Path $LogDir, $PidDir | Out-Null
}

function Write-StackLine {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::Gray
    )
    Write-Host $Message -ForegroundColor $Color
    if (-not $Background) { return }
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath (Join-Path $LogDir "stack.log") -Value "$stamp $Message" -Encoding UTF8
}

function Test-PortOpen {
    param([int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(500, $false)
        if (-not $ok) { return $false }
        try { $client.EndConnect($iar) } catch { return $false }
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Save-ChildPid {
    param(
        [string]$Name,
        [int]$ProcessId
    )
    Set-Content -LiteralPath (Join-Path $PidDir "$Name.pid") -Value "$ProcessId" -Encoding ASCII
}

function Start-HiddenCmd {
    param(
        [string]$Command,
        [string]$WorkDir,
        [string]$LogName,
        [string]$PidName
    )
    $log = Join-Path $LogDir $LogName
    $inner = "$Command >> `"$log`" 2>&1"
    $proc = Start-Process -FilePath $env:ComSpec -ArgumentList "/c", $inner -WindowStyle Hidden -WorkingDirectory $WorkDir -PassThru
    Save-ChildPid -Name $PidName -ProcessId $proc.Id
    return $proc
}

function Start-N8nNpxProcess {
    param([string]$NpxPath)
    $env:N8N_PORT = "$N8nPort"
    if ($Background) {
        if (Test-PortOpen -Port $N8nPort) {
            Write-StackLine "[ok] n8n ya escucha en el puerto $N8nPort" Green
            return
        }
        Start-HiddenCmd -Command "`"$NpxPath`" --yes n8n" -WorkDir $Root -LogName "n8n.log" -PidName "n8n" | Out-Null
        Set-Content -LiteralPath (Join-Path $PidDir "n8n.mode") -Value "npx" -Encoding ASCII
        Write-StackLine "[ok] n8n (npx) en segundo plano → http://127.0.0.1:$N8nPort" Green
        return
    }
    Start-Process -WindowStyle Minimized -FilePath $NpxPath -ArgumentList @("--yes", "n8n") -WorkingDirectory $Root
    Write-Host "[ok] n8n (npx) → http://127.0.0.1:$N8nPort" -ForegroundColor Green
}

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
    if ($Background -and (Test-PortOpen -Port $N8nPort)) {
        Write-StackLine "[ok] n8n ya escucha en el puerto $N8nPort" Green
        return $false
    }
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
    if ($npxExePath) { Start-N8nNpxProcess -NpxPath $npxExePath }
}
elseif ($N8nMode -eq "auto") {
    $npxExePath = Get-NpxExe
    if ($npxExePath) {
        Start-N8nNpxProcess -NpxPath $npxExePath
    }
    else {
        $script:DockerExePath = Get-DockerExe
        if ($script:DockerExePath) { $n8nDockerStarted = Start-N8nDocker }
    }
}

if ($Background -and $n8nDockerStarted) {
    Set-Content -LiteralPath (Join-Path $PidDir "n8n.mode") -Value "docker" -Encoding ASCII
}

$BindHost = $env:DEV_BIND_HOST
if ([string]::IsNullOrWhiteSpace($BindHost)) { $BindHost = "0.0.0.0" }

function Write-LanUrls {
    if ($BindHost -eq "127.0.0.1" -or $BindHost -eq "localhost") { return }
    try {
        $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object {
                $_.IPAddress -notmatch '^127\.' -and
                $_.IPAddress -notmatch '^169\.254\.'
            } |
            Select-Object -ExpandProperty IPAddress -Unique
        foreach ($ip in $ips) {
            Write-Host "[lan] Panel http://${ip}:$PanelPort   API http://${ip}:$ApiPort" -ForegroundColor Cyan
        }
    }
    catch { }
}

function Resolve-PanelRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:CHERRY_ANGULAR_ROOT)) {
        $p = $env:CHERRY_ANGULAR_ROOT.Trim().TrimEnd('\')
        if (Test-Path (Join-Path $p "package.json")) { return $p }
    }
    $sibling = Join-Path (Split-Path $Root -Parent) "cherry_tattoo_angular"
    if (Test-Path (Join-Path $sibling "package.json")) { return $sibling }
    return $null
}

function Should-StartPanel {
    if ($env:START_PANEL -match '^(0|false|no|off)$') { return $false }
    if ($env:START_PANEL -match '^(1|true|yes|on)$') { return $true }
    # Sin variable: arrancar panel si existe cherry_tattoo_angular (p. ej. Launch-Cherry-Dev-Stack.bat).
    return $null -ne (Resolve-PanelRoot)
}

$panelProc = $null
if (Should-StartPanel) {
    $panelRoot = Resolve-PanelRoot
    if ($panelRoot) {
        $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if ($npm) {
            $panelArgs = @("start", "--", "--host", $BindHost, "--port", "$PanelPort")
            if ($BindHost -ne "127.0.0.1" -and $BindHost -ne "localhost") {
                $panelArgs += @("--allowed-hosts", "all")
            }
            if ($Background) {
                if (Test-PortOpen -Port $PanelPort) {
                    Write-StackLine "[ok] Panel ya escucha en el puerto $PanelPort" Green
                }
                else {
                    $panelCmd = "npm.cmd start -- --host $BindHost --port $PanelPort"
                    if ($BindHost -ne "127.0.0.1" -and $BindHost -ne "localhost") {
                        $panelCmd += " --allowed-hosts all"
                    }
                    Start-HiddenCmd -Command $panelCmd -WorkDir $panelRoot -LogName "panel.log" -PidName "panel" | Out-Null
                    Write-StackLine "[ok] Panel Angular en segundo plano → http://127.0.0.1:$PanelPort (host $BindHost, proxy API :$ApiPort)" Green
                }
            }
            else {
                $panelProc = Start-Process -PassThru -WindowStyle Minimized -FilePath $npm.Source -ArgumentList $panelArgs -WorkingDirectory $panelRoot
                Write-Host "[ok] Panel Angular → http://127.0.0.1:$PanelPort (host $BindHost, proxy API :$ApiPort)" -ForegroundColor Green
            }
        }
    }
    else {
        Write-Host "[aviso] START_PANEL=1 pero no hay package.json en ../cherry_tattoo_angular." -ForegroundColor Yellow
    }
}

$apiArgs = @("-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", "$ApiPort")

if ($Background) {
    if (Test-PortOpen -Port $ApiPort) {
        Write-StackLine "[ok] API ya escucha en el puerto $ApiPort" Green
    }
    else {
        $apiOut = Join-Path $LogDir "api-out.log"
        $apiErr = Join-Path $LogDir "api-err.log"
        $apiProc = Start-Process -FilePath $venvPy -ArgumentList $apiArgs -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr -PassThru
        Save-ChildPid -Name "api" -ProcessId $apiProc.Id
        Write-StackLine "[ok] API Litestar en segundo plano → http://127.0.0.1:$ApiPort (bind $BindHost)" Green
    }
    $urlLines = @(
        "Panel  http://127.0.0.1:$PanelPort",
        "API    http://127.0.0.1:$ApiPort",
        "n8n    http://127.0.0.1:$N8nPort"
    )
    if ($BindHost -ne "127.0.0.1" -and $BindHost -ne "localhost") {
        try {
            $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.IPAddress -notmatch '^127\.' -and
                    $_.IPAddress -notmatch '^169\.254\.'
                } |
                Select-Object -ExpandProperty IPAddress -Unique
            foreach ($ip in $ips) {
                $urlLines += "LAN    Panel http://${ip}:$PanelPort    API http://${ip}:$ApiPort"
                Write-StackLine "[lan] Panel http://${ip}:$PanelPort   API http://${ip}:$ApiPort" Cyan
            }
        }
        catch { }
    }
    Set-Content -LiteralPath (Join-Path $StateDir "urls.txt") -Value $urlLines -Encoding UTF8
    Write-StackLine "[info] Logs: $LogDir" DarkGray
    Write-StackLine "[info] Para detener: scripts\stop-dev-stack.ps1 o Stop-Cherry-Dev-Stack.bat" DarkGray
    return
}

Write-Host "[ok] API Litestar → http://127.0.0.1:$ApiPort (bind $BindHost)" -ForegroundColor Green
Write-LanUrls
if (-not $panelProc) {
    Write-Host "[info] Panel Angular: en otra terminal, cd cherry_tattoo_angular && npx.cmd ng serve --host $BindHost --port $PanelPort" -ForegroundColor DarkGray
    Write-Host "[info] O: `$env:START_PANEL='1'; .\scripts\dev-stack.ps1" -ForegroundColor DarkGray
}
Write-Host "[info] Ctrl+C detiene la API. Si se abrió el panel en otra ventana, ciérrala aparte si sigue en :$PanelPort." -ForegroundColor DarkGray

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
