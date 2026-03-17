@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo  PROCESAMIENTO SEMANAL DE ASISTENCIA
echo  %date% %time%
echo ============================================================

echo.
echo [1/2] Procesando registros de asistencia...
python process_attendance.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] El procesamiento fallo. Revisa los archivos en data\raw\
    pause
    exit /b 1
)

echo.
echo [2/2] Subiendo CSVs a GitHub...
python upload_to_github.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] No se pudo subir a GitHub. Revisa el token y la conexion.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Fin: %date% %time%
echo  Power BI y el portal del director se actualizaran solos.
echo ============================================================
pause
