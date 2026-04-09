@echo off
chcp 65001 >nul
:: ============================================================
:: procesar_semana.bat
:: Ejecutar cada lunes a las 10:00 hs via Programador de tareas
:: ============================================================

echo ============================================================
echo  PROCESAMIENTO SEMANAL DE ASISTENCIA
echo  %date% %time%
echo ============================================================

:: Ir a la carpeta del proyecto
cd /d "C:\Users\nadia\OneDrive\Documents\ASISTENCIA POR SEMANAS\Registro con Parkimovil\reportes_asistencia"

:: Paso 1: Consolidar archivos crudos en Semana_X.xlsx
echo.
echo [1/3] Consolidando archivos crudos de Kigo y Asistencia...
python consolidar_semana.py

if %errorlevel% neq 0 (
    echo.
    echo ERROR: No se pudo consolidar. Revisa los archivos en data\raw\kigo\ y data\raw\asistencia\
    pause
    exit /b 1
)

:: Paso 2: Procesar Excel consolidado
echo.
echo [2/3] Procesando registros de asistencia...
python process_attendance.py

if %errorlevel% neq 0 (
    echo.
    echo ERROR: El procesamiento fallo. Revisa los archivos en data\raw\
    pause
    exit /b 1
)

echo.
echo     CSVs generados en data\processed\

:: Paso 3: Subir a GitHub
echo.
echo [3/3] Subiendo CSVs a GitHub...
python upload_to_github.py

if %errorlevel% neq 0 (
    echo.
    echo ADVERTENCIA: No se pudieron subir los archivos a GitHub.
    echo Los CSVs locales estan correctos. Revisa el token o la conexion.
)

echo.
echo ============================================================
echo  Fin: %date% %time%
echo  Power BI y el portal del director se actualizaran solos.
echo ============================================================
pause
