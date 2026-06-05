# Muestra URLs para abrir el panel Angular desde otro equipo en la misma red.
$port = if ($env:PANEL_PORT) { [int]$env:PANEL_PORT } else { 4200 }
$apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 5000 }
$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notmatch '^127\.' -and
        $_.IPAddress -notmatch '^169\.254\.'
    } |
    Select-Object -ExpandProperty IPAddress -Unique

Write-Host ""
Write-Host "Panel en este PC:  http://127.0.0.1:$port" -ForegroundColor Green
Write-Host "API en este PC:    http://127.0.0.1:$apiPort" -ForegroundColor Green
if ($ips) {
    foreach ($ip in $ips) {
        Write-Host "Panel desde LAN:   http://${ip}:$port" -ForegroundColor Cyan
        Write-Host "API desde LAN:     http://${ip}:$apiPort" -ForegroundColor Cyan
    }
}
else {
    Write-Host "Desde la LAN:      http://<tu-IPv4>:$port  (panel) y :$apiPort (API)" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Arranca con DEV_BIND_HOST=0.0.0.0 y proxy del panel apuntando a la API." -ForegroundColor DarkGray
