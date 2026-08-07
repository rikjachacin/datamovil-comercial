$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$generator = Join-Path $projectRoot "tools\generate_weekly_report.py"

if (-not (Test-Path -LiteralPath $python)) {
    throw "No se encontro el Python del proyecto en $python"
}

$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument ('"{0}"' -f $generator) `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At 9:00AM
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask `
    -TaskName "Bruncas - Informe semanal" `
    -Description "Genera el Excel semanal de desempeno de vendedores." `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Force

Write-Host "Tarea instalada: Bruncas - Informe semanal (sabados 09:00)."
