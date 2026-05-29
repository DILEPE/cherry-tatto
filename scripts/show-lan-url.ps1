# Muestra URLs para abrir el panel desde otro equipo en la misma red.
$port = if ($env:STREAMLIT_PORT) { [int]$env:STREAMLIT_PORT } else { 8501 }
$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notmatch '^127\.' -and
        $_.IPAddress -notmatch '^169\.254\.'
    } |
    Select-Object -ExpandProperty IPAddress -Unique

Write-Host ""
Write-Host "Panel en este PC:  http://127.0.0.1:$port" -ForegroundColor Green
if ($ips) {
    foreach ($ip in $ips) {
        Write-Host "Desde la LAN:      http://${ip}:$port" -ForegroundColor Cyan
    }
}
else {
    Write-Host "Desde la LAN:      http://<tu-IPv4>:$port  (ejecuta ipconfig)" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Comprueba que Streamlit escucha en 0.0.0.0:" -ForegroundColor DarkGray
Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Format-Table LocalAddress, LocalPort, State -AutoSize
