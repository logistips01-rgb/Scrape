@echo off
chcp 65001 >nul
echo.
echo ============================================================
echo   INSTALADOR — Declarador Automático de Envases
echo   IFCO / Europool / CHEP
echo ============================================================
echo.

SET CARPETA=%~dp0
SET PYTHON=python

:: Verificar Python
%PYTHON% --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python no encontrado.
    echo Descargalo en: https://www.python.org/downloads/
    echo Durante la instalacion marca "Add Python to PATH"
    pause
    exit /b 1
)
echo [OK] Python encontrado.

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

:: Instalar navegador Chromium para Playwright
echo.
echo Instalando navegador Chromium (necesario para el scraping)...
%PYTHON% -m playwright install chromium
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Fallo al instalar Chromium.
    pause
    exit /b 1
)
echo [OK] Chromium instalado.

:: Crear fichero .env si no existe
IF NOT EXIST "%CARPETA%.env" (
    echo.
    echo Creando fichero de configuracion...
    copy "%CARPETA%.env.example" "%CARPETA%.env" >nul
    echo [OK] Creado .env — IMPORTANTE: edita este fichero con tus credenciales.
    echo     Ruta: %CARPETA%.env
) ELSE (
    echo [OK] Fichero .env ya existe.
)

:: Crear carpetas de trabajo
echo.
echo Creando carpetas de trabajo...
mkdir "%CARPETA%input\pendientes" 2>nul
mkdir "%CARPETA%input\procesados" 2>nul
mkdir "%CARPETA%input\errores"    2>nul
mkdir "%CARPETA%output\completados" 2>nul
mkdir "%CARPETA%output\logs"      2>nul
echo [OK] Carpetas creadas.

:: Crear acceso directo en Inicio de Windows (arranca con Windows)
echo.
echo Configurando inicio automatico con Windows...
SET STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
SET VBS_SCRIPT=%CARPETA%arrancar_silencioso.vbs

:: Script VBS para arrancar sin ventana visible
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.Run "cmd /c python ""%CARPETA%watcher.py"" >> ""%CARPETA%output\logs\watcher.log"" 2>&1", 0, False
) > "%VBS_SCRIPT%"

:: Copiar al inicio de Windows
copy "%VBS_SCRIPT%" "%STARTUP%\DeclaradorEnvases.vbs" >nul
echo [OK] Configurado para arrancar automaticamente con Windows.

:: Instalar SumatraPDF para impresión silenciosa (opcional pero recomendado)
echo.
echo Recomendacion: instala SumatraPDF para impresion silenciosa sin ventanas.
echo Descarga gratuita: https://www.sumatrapdfreader.org/download-free-pdf-viewer
echo (Si ya lo tienes instalado, ignora este mensaje)

echo.
echo ============================================================
echo   INSTALACION COMPLETADA
echo ============================================================
echo.
echo Pasos siguientes:
echo.
echo 1. Edita el fichero de configuracion con tus credenciales:
echo    %CARPETA%.env
echo.
echo 2. Configura tu ERP para exportar los CSV en:
echo    %CARPETA%input\pendientes\
echo.
echo 3. Los PDFs completados apareceran en:
echo    %CARPETA%output\completados\
echo.
echo 4. Para arrancar el vigilante ahora mismo:
echo    python watcher.py
echo.
echo    (Tambien arrancara automaticamente la proxima vez que
echo    enciendas el ordenador)
echo.
pause
