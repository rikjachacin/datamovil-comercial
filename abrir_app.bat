@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo DataMovil Comercial - Inicio local
echo ==========================================
echo.

if not exist ".venv\Scripts\streamlit.exe" (
    echo No encuentro .venv\Scripts\streamlit.exe
    echo Abre este proyecto desde la carpeta correcta o avisanos para revisar el entorno.
    pause
    exit /b 1
)

echo Verificando conexion con SisCor por VPN...
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-NetConnection 10.8.0.1 -Port 50672 -InformationLevel Quiet) { exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo.
    echo No puedo conectar con SisCor.
    echo.
    echo Revisa esto:
    echo 1. Abre OpenVPN.
    echo 2. Confirma que diga conectado.
    echo 3. Vuelve a ejecutar este archivo.
    echo.
    pause
    exit /b 1
)

echo Conexion OK.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
    echo La app ya estaba abierta. Abriendo navegador...
    start "" "http://127.0.0.1:8501"
    exit /b 0
)

echo Iniciando Streamlit...
echo.
echo Cuando cierres esta ventana, la app local se detendra.
echo.
start "" "http://127.0.0.1:8501"
".venv\Scripts\streamlit.exe" run app.py --server.address 127.0.0.1 --server.port 8501

pause
