@echo off
chcp 65001 > nul 2>&1
echo.
echo ============================================================
echo   INSTALADOR - Declarador de Envases IFCO / Europool / CHEP
echo ============================================================
echo.

SET CARPETA=%~dp0
SET PYTHON=python

:: Verificar Python
%PYTHON% --version > nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python no encontrado.
    echo.
    echo Pasos para instalar Python:
    echo   1. Ve a https://www.python.org/downloads/
    echo   2. Descarga Python 3.11 o superior
    echo   3. Durante la instalacion marca "Add Python to PATH"
    echo   4. Vuelve a ejecutar este instalador
    echo.
    pause
    exit /b 1
)
echo [OK] Python encontrado.
%PYTHON% --version

:: Instalar dependencias
echo.
echo Instalando dependencias Python...
%PYTHON% -m pip install -r "%CARPETA%requirements.txt" --quiet
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Fallo al instalar dependencias.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas.

:: Instalar Chromium para Playwright
echo.
echo Instalando navegador Chromium...
%PYTHON% -m playwright install chromium
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Fallo al instalar Chromium.
    pause
    exit /b 1
)
echo [OK] Chromium instalado.

:: Crear .env si no existe
IF NOT EXIST "%CARPETA%.env" (
    copy "%CARPETA%.env.example" "%CARPETA%.env" > nul
    echo [OK] Creado .env - IMPORTANTE: edita este fichero con tus credenciales.
    echo     Ruta: %CARPETA%.env
) ELSE (
    echo [OK] Fichero .env ya existe.
)

:: Crear carpetas de trabajo
echo.
echo Creando carpetas...
mkdir "%CARPETA%input\pendientes" 2>nul
mkdir "%CARPETA%input\procesados" 2>nul
mkdir "%CARPETA%input\errores"    2>nul
mkdir "%CARPETA%output\completados" 2>nul
mkdir "%CARPETA%output\logs"      2>nul
echo [OK] Carpetas creadas.

:: Configurar inicio automatico con Windows
echo.
echo Configurando inicio automatico...
SET STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.Run "cmd /c cd /d ""%CARPETA%"" && python watcher.py >> ""%CARPETA%output\logs\watcher.log"" 2>>&1", 0, False
) > "%CARPETA%arrancar_silencioso.vbs"

copy "%CARPETA%arrancar_silencioso.vbs" "%STARTUP%\DeclaradorEnvases.vbs" > nul
echo [OK] Configurado para arrancar con Windows.

echo.
echo ============================================================
echo   INSTALACION COMPLETADA
echo ============================================================
echo.
echo Pasos siguientes:
echo.
echo 1. Edita el fichero con tus credenciales:
echo    %CARPETA%.env
echo.
echo 2. Configura el ERP para exportar XLS en:
echo    %CARPETA%input\pendientes\
echo.
echo 3. Los PDFs apareceran en:
echo    %CARPETA%output\completados\
echo.
echo 4. Para arrancar el vigilante ahora mismo:
echo    python watcher.py
echo.
pause
