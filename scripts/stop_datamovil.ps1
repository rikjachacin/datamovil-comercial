$ErrorActionPreference = "SilentlyContinue"

$connections = Get-NetTCPConnection -LocalPort 8501
$processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique

foreach ($processId in $processIds) {
    if ($processId -and $processId -ne 0) {
        Stop-Process -Id $processId -Force
    }
}

