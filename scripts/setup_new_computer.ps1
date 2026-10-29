$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvRoot = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$requirements = Join-Path $projectRoot "requirements.txt"

Write-Host "Preparando Bruncas Comercial..." -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $venvPython)) {
    $pyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    $pythonCommand = Get-Command "python.exe" -ErrorAction SilentlyContinue

    if ($pyLauncher) {
        & $pyLauncher.Source -3 -m venv $venvRoot
    }
    elseif ($pythonCommand) {
        & $pythonCommand.Source -m venv $venvRoot
    }
    else {
        throw "No se encontro Python. Instala Python 3.12 y vuelve a ejecutar este archivo."
    }
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r $requirements

$streamlitDir = Join-Path $projectRoot ".streamlit"
New-Item -ItemType Directory -Path $streamlitDir -Force | Out-Null

$privateFiles = @(
    @{ Example = "secrets.example.toml"; Target = "secrets.toml" },
    @{ Example = "users.example.toml"; Target = "users.toml" }
)
foreach ($file in $privateFiles) {
    $target = Join-Path $streamlitDir $file.Target
    $example = Join-Path $streamlitDir $file.Example
    if (-not (Test-Path -LiteralPath $target)) {
        Copy-Item -LiteralPath $example -Destination $target
    }
}

& (Join-Path $PSScriptRoot "install_bruncas_analitica_shortcut.ps1")
& (Join-Path $PSScriptRoot "install_efectividad_calle_shortcut.ps1")

Write-Host ""
Write-Host "Instalacion base terminada." -ForegroundColor Green
Write-Host "Falta completar la configuracion privada y probar la conexion con SisCor." -ForegroundColor Yellow
