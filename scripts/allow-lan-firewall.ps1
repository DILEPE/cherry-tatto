# Abre el firewall de Windows para el panel, la API y n8n (TCP inbound).
# Uso (como administrador, desde la raíz del repo):
#   .\scripts\allow-lan-firewall.ps1
# O doble clic en Allow-Cherry-Lan-Firewall.bat
#
# Puertos (variables opcionales): PANEL_PORT (4200), API_PORT (5000), N8N_PORT (5678)

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Host "[error] Este script necesita PowerShell como administrador." -ForegroundColor Red
    exit 1
}

$panelPort = if ($env:PANEL_PORT) { [int]$env:PANEL_PORT } else { 4200 }
$apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 5000 }
$n8nPort = if ($env:N8N_PORT) { [int]$env:N8N_PORT } else { 5678 }

function Set-LanNetworkPrivate {
    $profiles = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue |
        Where-Object { $_.IPv4Connectivity -eq "Internet" -or $_.IPv4Connectivity -eq "LocalNetwork" })
    if (-not $profiles) {
        $profiles = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue)
    }
    foreach ($prof in $profiles) {
        if ($prof.NetworkCategory -eq "Private") {
            Write-Host "[ok] Red '$($prof.Name)' ya es Privada ($($prof.InterfaceAlias))." -ForegroundColor Green
            continue
        }
        try {
            Set-NetConnectionProfile -InterfaceIndex $prof.InterfaceIndex -NetworkCategory Private -ErrorAction Stop
            Write-Host "[ok] Red '$($prof.Name)' pasada a Privada (antes $($prof.NetworkCategory))." -ForegroundColor Green
        }
        catch {
            Write-Host "[aviso] No se pudo pasar '$($prof.Name)' a Privada: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

function Set-CherryFirewallRule {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Protocol = "TCP",
        [string]$LocalPort = "",
        [string]$Program = "",
        [string]$IcmpType = ""
    )
    Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue
    $params = @{
        DisplayName = $Name
        Direction   = "Inbound"
        Action      = "Allow"
        Profile     = "Any"
        ErrorAction = "Stop"
    }
    if ($Program) { $params.Program = $Program }
    if ($Protocol) { $params.Protocol = $Protocol }
    if ($LocalPort) { $params.LocalPort = $LocalPort }
    if ($IcmpType) { $params.IcmpType = $IcmpType }
    New-NetFirewallRule @params | Out-Null
}

Set-LanNetworkPrivate

$rules = @(
    @{ Name = "Cherry Tattoo Panel"; Port = $panelPort },
    @{ Name = "Cherry Tattoo API"; Port = $apiPort },
    @{ Name = "Cherry Tattoo n8n"; Port = $n8nPort }
)

foreach ($rule in $rules) {
    Set-CherryFirewallRule -Name $rule.Name -Protocol TCP -LocalPort "$($rule.Port)"
    Write-Host "[ok] Permitido TCP $($rule.Port) ($($rule.Name))" -ForegroundColor Green
}

Set-CherryFirewallRule -Name "Cherry Tattoo Ping (ICMPv4)" -Protocol ICMPv4 -IcmpType "8"
Write-Host "[ok] Permitido ping (ICMPv4) para probar la red." -ForegroundColor Green

$programs = New-Object System.Collections.Generic.List[string]
foreach ($candidate in @(
        "${env:ProgramFiles}\nodejs\node.exe",
        (Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"),
        (Join-Path $PSScriptRoot "..\venv\Scripts\python.exe"),
        $env:CHERRY_PYTHON,
        "C:\Python314\python.exe"
    )) {
    if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
    try {
        $full = (Resolve-Path -LiteralPath $candidate -ErrorAction Stop).Path
        if (Test-Path -LiteralPath $full) { [void]$programs.Add($full) }
    }
    catch { }
}
try {
    $listen = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in $panelPort, $apiPort, $n8nPort }
    foreach ($c in $listen) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue
        if ($proc -and $proc.ExecutablePath) { [void]$programs.Add($proc.ExecutablePath) }
    }
}
catch { }

$uniquePrograms = $programs | Select-Object -Unique
foreach ($exe in $uniquePrograms) {
    $leaf = Split-Path $exe -Leaf
    $name = "Cherry Tattoo app ($leaf)"
    Set-CherryFirewallRule -Name $name -Program $exe
    Write-Host "[ok] Permitido programa $leaf" -ForegroundColor Green
}

function Write-LanConnectionInfo {
    Write-Host ""
    Write-Host "----------------------------------------------" -ForegroundColor DarkGray
    Write-Host "Como conectar desde otro equipo" -ForegroundColor Cyan
    Write-Host "Usa la misma red Wi-Fi o cable que este PC." -ForegroundColor DarkGray
    Write-Host ""

    $rows = @()
    try {
        $rows = @(Get-NetIPConfiguration -ErrorAction SilentlyContinue | ForEach-Object {
            $ip = $null
            if ($_.IPv4Address) {
                $ip = [string]@($_.IPv4Address | Select-Object -ExpandProperty IPAddress -First 1)
            }
            if ([string]::IsNullOrWhiteSpace($ip)) { return }
            if ($ip -match '^127\.' -or $ip -match '^169\.254\.') { return }

            $alias = [string]$_.InterfaceAlias
            $status = if ($_.NetAdapter) { [string]$_.NetAdapter.Status } else { "?" }
            $netName = if ($_.NetProfile -and $_.NetProfile.Name) { [string]$_.NetProfile.Name } else { $alias }
            $category = if ($_.NetProfile) { [string]$_.NetProfile.NetworkCategory } else { "?" }
            $hasGw = $null -ne $_.IPv4DefaultGateway
            $virtual = $alias -match 'vEthernet|Virtual|VMware|Hyper-V|Loopback|Bluetooth|VPN|TAP|Tunnel'

            [pscustomobject]@{
                Network   = $netName
                Category  = $category
                Adapter   = $alias
                Status    = $status
                IP        = $ip
                HasGw     = $hasGw
                Virtual   = $virtual
            }
        })
    }
    catch { }

    $up = @($rows | Where-Object { $_.Status -eq "Up" })
    $recommended = $up | Where-Object { -not $_.Virtual -and $_.HasGw } | Select-Object -First 1
    if (-not $recommended) {
        $recommended = $up | Where-Object { -not $_.Virtual } | Select-Object -First 1
    }
    if (-not $recommended) {
        $recommended = $up | Select-Object -First 1
    }
    if (-not $recommended) {
        $recommended = $rows | Select-Object -First 1
    }

    if (-not $rows) {
        Write-Host "No se detecto una IPv4 de red. Revisa el Wi-Fi o el cable." -ForegroundColor Yellow
        Write-Host "En el otro PC prueba: http://<IP-de-este-PC>:$panelPort" -ForegroundColor Yellow
        return
    }

    foreach ($row in $rows) {
        $mark = ""
        if ($recommended -and $row.IP -eq $recommended.IP -and $row.Adapter -eq $recommended.Adapter) {
            $mark = "  <-- usa esta"
        }
        $state = if ($row.Status -eq "Up") { "conectado" } else { $row.Status }
        Write-Host ("  Red:       {0} ({1})" -f $row.Network, $row.Category)
        if ($row.Category -eq "Public") {
            Write-Host "  Aviso:     Windows tiene esta red como Publica. En Configuracion > Red e Internet > Wi-Fi > propiedades, elige red Privada." -ForegroundColor Yellow
        }
        Write-Host ("  Adaptador: {0} ({1})" -f $row.Adapter, $state)
        Write-Host ("  IP:        {0}{1}" -f $row.IP, $mark) -ForegroundColor $(if ($mark) { "Green" } else { "Gray" })
        Write-Host ("  Panel:     http://{0}:{1}" -f $row.IP, $panelPort) -ForegroundColor $(if ($mark) { "Cyan" } else { "DarkGray" })
        Write-Host ""
    }

    if ($recommended) {
        Write-Host "En el otro equipo:" -ForegroundColor Green
        Write-Host ("  1. Conectate a la Wi-Fi '{0}' (mismo nombre, no invitado)." -f $recommended.Network)
        Write-Host ("  2. Abre exactamente: http://{0}:{1}" -f $recommended.IP, $panelPort) -ForegroundColor Cyan
        Write-Host "  3. Si no carga, en el otro PC ejecuta:  ping $($recommended.IP)"
        Write-Host "     Si el ping falla, el router aísla equipos (AP isolation). Hay que desactivarlo en el router." -ForegroundColor Yellow
    }
}

Write-LanConnectionInfo
exit 0
