$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Streamlit = Join-Path $ProjectRoot ".venv\Scripts\streamlit.exe"
$App = Join-Path $ProjectRoot "app.py"

Set-Location $ProjectRoot

& $Streamlit run $App `
  --server.port 8501 `
  --server.address 0.0.0.0 `
  --server.headless true

