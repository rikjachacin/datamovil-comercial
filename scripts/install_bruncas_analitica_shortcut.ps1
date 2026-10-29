$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Bruncas Analitica.lnk"
$launcher = Join-Path $PSScriptRoot "start_bruncas_analitica.ps1"
$icon = Join-Path $projectRoot "assets\bruncas_analitica.ico"
$powershell = Join-Path $PSHOME "powershell.exe"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershell
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = "$icon,0"
$shortcut.Description = "Abrir Bruncas Analitica"
$shortcut.Save()

Write-Output $shortcutPath
