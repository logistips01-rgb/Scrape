@echo off
chcp 65001 >nul
echo.
echo Eliminando inicio automatico con Windows...
SET STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
DEL "%STARTUP%\DeclaradorEnvases.vbs" 2>nul
echo [OK] Eliminado del inicio de Windows.
echo.
echo El programa ya no arrancara automaticamente.
echo Los datos y configuracion NO han sido borrados.
pause
