@echo off
cd /d "%~dp0"

echo ============================================
echo   Sistema del Taller - Iniciando servidor
echo ============================================
echo.

if not exist venv\Scripts\python.exe (
    echo No se encontro el entorno virtual "venv".
    echo Segui los pasos de INSTALACION.md antes de usar este acceso directo.
    pause
    exit /b 1
)

venv\Scripts\python.exe servidor.py

echo.
echo El servidor se detuvo.
pause
