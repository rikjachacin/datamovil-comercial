$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$streamlit = Join-Path $projectRoot ".venv\Scripts\streamlit.exe"
$app = Join-Path $projectRoot "app_calle.py"
$logDir = Join-Path $projectRoot "reportes"
$url = "http://127.0.0.1:8512"

if (-not (Test-Path -LiteralPath $streamlit)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("No se encontro el entorno local de Bruncas Comercial.", "Efectividad de Calle") | Out-Null
    exit 1
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$portOpen = Test-NetConnection -ComputerName 127.0.0.1 -Port 8512 -InformationLevel Quiet -WarningAction SilentlyContinue

if (-not $portOpen) {
    Start-Process -FilePath $streamlit `
        -ArgumentList @("run", "`"$app`"", "--server.address", "127.0.0.1", "--server.port", "8512", "--server.headless", "true", "--browser.gatherUsageStats", "false") `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir "efectividad_calle.log") `
        -RedirectStandardError (Join-Path $logDir "efectividad_calle_error.log")

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (Test-NetConnection -ComputerName 127.0.0.1 -Port 8512 -InformationLevel Quiet -WarningAction SilentlyContinue) {
            break
        }
    }
}

Start-Process $url
