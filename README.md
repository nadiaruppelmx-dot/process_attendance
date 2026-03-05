# Sistema de Reportes de Asistencia — Arquitectura Python + Power BI

## Resumen del flujo

```
[Sistema QR]
     │
     ▼
[Excel semanal]  ←─── tú depositas aquí cada semana
  data/raw/
     │
     ▼  python process_attendance.py
[3 tablas CSV / SQLite]
  data/processed/
     │
     ▼
[Power BI Desktop]
  → Reporte visual con gráficos de barras
```

---

## 1. Estructura de carpetas recomendada

```
reportes_asistencia/
├── data/
│   ├── raw/                   ← Aquí depositas cada Excel semanal
│   │   ├── Semana 1.xlsx
│   │   ├── Semana 2.xlsx
│   │   └── ...
│   └── processed/             ← Python genera estos archivos automáticamente
│       ├── registros_diarios.csv
│       ├── salidas_intermedias.csv
│       └── resumen_semanal.csv
├── process_attendance.py      ← Script principal
└── Reporte_Asistencia.pbix    ← Archivo de Power BI Desktop
```

---

## 2. Tablas que genera el script Python

### `registros_diarios.csv`
Una fila por empleado por día trabajado.

| Columna             | Descripción                                              |
|---------------------|----------------------------------------------------------|
| `semana`            | Identificador de semana ISO (ej: `2026-S09`)             |
| `empleado`          | Nombre del empleado                                       |
| `fecha`             | Fecha del día                                             |
| `hora_entrada`      | Primera entrada del día (luego de deduplicar)            |
| `hora_salida`       | Última salida del día (luego de deduplicar)              |
| `horas_trabajadas`  | Horas netas (descuenta tiempo fuera)                     |
| `horas_fuera`       | Total de horas fuera en salidas intermedias              |
| `n_salidas_interm`  | Cantidad de salidas durante la jornada                   |
| `sin_salida`        | 1 si el día no tiene salida registrada                   |
| `sin_entrada`       | 1 si el día no tiene entrada registrada                  |

### `salidas_intermedias.csv`
Una fila por cada salida intermedia detectada.

| Columna                  | Descripción                                  |
|--------------------------|----------------------------------------------|
| `semana`                 | Semana ISO                                   |
| `empleado`               | Nombre del empleado                           |
| `fecha`                  | Fecha                                         |
| `hora_salida_intermedia` | Hora en que salió durante la jornada         |
| `hora_reentrada`         | Hora en que volvió a ingresar                |
| `minutos_fuera`          | Minutos que estuvo fuera                     |

### `resumen_semanal.csv`
Una fila por empleado por semana.

| Columna               | Descripción                                    |
|-----------------------|------------------------------------------------|
| `semana`              | Semana ISO                                     |
| `empleado`            | Nombre del empleado                             |
| `dias_con_registro`   | Días con al menos un registro                  |
| `dias_con_entrada`    | Días con entrada registrada                    |
| `dias_con_salida`     | Días con salida registrada                     |
| `total_horas`         | Total horas trabajadas en la semana            |
| `promedio_horas_dia`  | Promedio de horas por día trabajado            |
| `total_horas_fuera`   | Total horas fuera durante la semana            |
| `total_salidas_interm`| Total de salidas intermedias en la semana      |

---

## 3. Cómo usar el script Python

### Instalación de dependencias (una sola vez)
```bash
pip install pandas openpyxl
```

### Uso habitual — procesar todos los archivos en data/raw/
```bash
python process_attendance.py
```

### Procesar un archivo específico
```bash
python process_attendance.py --file "data/raw/Semana 1.xlsx"
```

### Generar también base de datos SQLite (ver sección 4b)
```bash
python process_attendance.py --sqlite
```

El script **siempre acumula** los datos: si ya existían semanas anteriores en los CSV, las nuevas se agregan sin duplicar.

---

## 4. Dónde almacenar los datos — dos opciones

### Opción A — CSV locales (recomendada para empezar)

Los archivos CSV en `data/processed/` son la forma más simple. Power BI Desktop los lee directamente. Ventajas:
- Sin instalación extra
- Fácil de auditar (se pueden abrir en Excel)
- Power BI Desktop puede refrescar automáticamente

**Limitación:** solo funciona en la misma computadora donde está Power BI Desktop. Si varios usuarios necesitan el reporte, ver Opción B.

### Opción B — SQLite (recomendada si hay varios usuarios o automatización)

El script genera `data/attendance.db` con `--sqlite`. Power BI se conecta vía ODBC:

1. Descargar e instalar **SQLite ODBC Driver**: http://www.ch-werner.de/sqliteodbc/
2. En Power BI Desktop → **Obtener datos** → **ODBC**
3. Conectar a `attendance.db`
4. Las tres tablas aparecen directamente en Power Query

**Ventaja sobre CSV:** puede estar en una carpeta compartida de red o OneDrive, y varios usuarios acceden al mismo dato.

### Opción C — OneDrive / SharePoint (para Power BI Service / nube)

1. Guarda la carpeta `data/processed/` en OneDrive for Business
2. En Power BI Desktop → **Obtener datos** → **Carpeta de SharePoint**
3. Conecta y carga los CSV
4. Publica el reporte en Power BI Service
5. Configura **actualización programada** en Power BI Service

---

## 5. Cómo conectar Power BI Desktop a los CSV

1. Abrir **Power BI Desktop**
2. **Inicio → Obtener datos → Texto o CSV**
3. Seleccionar `registros_diarios.csv`  → Cargar
4. Repetir para `salidas_intermedias.csv` y `resumen_semanal.csv`
5. En Power Query Editor, verificar tipos de datos:
   - `fecha` → Fecha
   - `hora_entrada` / `hora_salida` / `hora_salida_intermedia` / `hora_reentrada` → Texto (o Hora)
   - `horas_trabajadas`, `promedio_horas_dia`, etc. → Número decimal

### Relaciones entre tablas
En el panel de Modelo de datos, crear relaciones:

```
registros_diarios [empleado + fecha]  ←→  salidas_intermedias [empleado + fecha]
registros_diarios [empleado + semana] ←→  resumen_semanal [empleado + semana]
```

---

## 6. Visualizaciones sugeridas en Power BI

### Gráfico de barras de jornada diaria (Gantt simplificado)
Este es el gráfico más complejo. Power BI no tiene un Gantt nativo, pero se puede construir con el visual **Charticulator** (gratuito en AppSource) o con un gráfico de barras apiladas:

**Método con barras apiladas:**
1. Crear dos medidas calculadas en DAX:
   ```dax
   Hora Entrada (decimal) =
       HOUR([hora_entrada]) + MINUTE([hora_entrada])/60

   Duración Jornada (horas) = [horas_trabajadas] + [horas_fuera]
   ```
2. Gráfico de barras apiladas:
   - Eje Y: empleado
   - Eje X: valores
   - Primera barra (invisible): "Hora Entrada decimal" → color blanco/transparente
   - Segunda barra: "Horas trabajadas" → color verde/azul
   - Tercera barra: "Horas fuera" → color naranja/rojo
3. Ajustar el eje X para que empiece en las horas de trabajo (ej: 6:00 = 6.0)

**Resultado:** barra por empleado que muestra desde la hora de entrada hasta la de salida, con el tramo de ausencia resaltado en color diferente.

### Otras visualizaciones recomendadas
- **Tarjetas KPI**: total horas semana / promedio diario por empleado
- **Tabla de detalle**: registros_diarios con formato condicional (rojo en `sin_salida = 1`)
- **Gráfico de líneas**: evolución de horas trabajadas semana a semana
- **Segmentador (slicer)**: por semana y por empleado para filtrar toda la página

---

## 7. Automatización — ejecutar el script cada semana

### Windows — Programador de tareas
1. Abrir **Programador de tareas**
2. **Crear tarea básica** → nombre: "Procesar Asistencia"
3. Desencadenador: **Semanalmente** (ej: lunes a las 08:00)
4. Acción: **Iniciar un programa**
   - Programa: `python`
   - Argumentos: `"C:\ruta\reportes_asistencia\process_attendance.py"`
   - Iniciar en: `C:\ruta\reportes_asistencia\`

### Actualización automática de Power BI Desktop
En **Archivo → Opciones → Actualización de datos** se puede configurar que el reporte refresque al abrirse.

---

## 8. Notas sobre la calidad de datos

El sistema QR puede generar registros duplicados (múltiples lecturas en segundos). El script los maneja así:
- **Ventana de deduplicación**: 60 segundos (configurable con `DEDUP_WINDOW_SECONDS`)
- Para entradas duplicadas, conserva la **primera**
- Para salidas duplicadas, conserva la **última**

**Días sin salida registrada** (`sin_salida = 1`): el empleado tiene entrada pero no salida. Las horas de ese día aparecen como vacías. Recomendación: revisar si el sistema QR falló o si el empleado olvidó registrar la salida.

**Días sin entrada registrada** (`sin_entrada = 1`): caso inverso. Puede indicar que entró el día anterior tarde (turno nocturno) y registró su salida al día siguiente.
