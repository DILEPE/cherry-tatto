# Crea en el escritorio: acceso directo .lnk y Cherry-Tattoo-Iniciar.bat que llama al repo por ruta absoluta.
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot
)

$ErrorActionPreference = "Stop"
$RepoRoot = $RepoRoot.TrimEnd('\', '/')
$launchBat = Join-Path $RepoRoot "Launch-Cherry-Dev-Stack.bat"
if (-not (Test-Path -LiteralPath $launchBat)) {
    Write-Host "No se encuentra Launch-Cherry-Dev-Stack.bat en: $RepoRoot" -ForegroundColor Red
    exit 1
}

$desk = [Environment]::GetFolderPath("Desktop")
if ([string]::IsNullOrWhiteSpace($desk)) {
    Write-Host "No se pudo resolver la carpeta Escritorio." -ForegroundColor Red
    exit 1
}

$w = New-Object -ComObject WScript.Shell
$lnkPath = Join-Path $desk "Cherry Tattoo Dev.lnk"
$s = $w.CreateShortcut($lnkPath)
$s.TargetPath = $launchBat
$s.WorkingDirectory = $RepoRoot
$s.Description = "Cherry Tattoo: API, Streamlit y n8n"
$s.Save()
Write-Host "Acceso directo: $lnkPath"

$stubPath = Join-Path $desk "Cherry-Tattoo-Iniciar.bat"
$stubLines = @(
    "@echo off",
    "title Cherry Tattoo - desarrollo",
    "call `"$launchBat`""
)
Set-Content -LiteralPath $stubPath -Value $stubLines -Encoding OEM
Write-Host "BAT en escritorio: $stubPath"
