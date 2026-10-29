@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo Instalacion de Bruncas Comercial
echo ==========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_new_computer.ps1"
if errorlevel 1 (
    echo.
    echo La instalacion no pudo terminar. Guarda esta ventana para revisar el mensaje.
    pause
    exit /b 1
)

echo.
echo Instalacion base terminada correctamente.
pause
