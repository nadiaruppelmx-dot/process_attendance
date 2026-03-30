"""
process_attendance.py
=====================
Procesa archivos Excel semanales de control de acceso QR y genera
tablas limpias en CSV/SQLite listas para conectar con Power BI.

Estructura esperada del Excel de entrada:
  Columnas: QR | Nombre | Fecha | Hora
  Valores QR: "Entrada Visitas", "Entrada Residentes", "Salida Visitas", "Salida Residentes"

Tablas generadas:
  1. registros_diarios.csv     → Resumen por empleado/turno (incluye turnos nocturnos)
  2. salidas_intermedias.csv   → Salidas durante la jornada
  3. resumen_semanal.csv       → Totales y promedio por semana
  4. attendance.db             → Base de datos SQLite (opcional, para Power BI vía ODBC)

LÓGICA DE TURNOS NOCTURNOS
  En lugar de agrupar por día de calendario, el script detecta "turnos":
  si entre dos eventos consecutivos de un empleado la brecha supera
  MAX_GAP_TURNO_HORAS (por defecto 8 h), se considera el inicio de un
  turno nuevo. Así, un empleado que entra el martes a las 22:00 y sale
  el miércoles a las 06:00 queda como un solo turno de 8 horas.
  El turno se registra bajo la fecha de la primera entrada.

Uso:
  python process_attendance.py                          # procesa todos los .xlsx en data/raw/
  python process_attendance.py --file "Semana 1.xlsx"  # procesa un archivo específico
  python process_attendance.py --sqlite                 # también genera SQLite
  python process_attendance.py --gap 10                 # cambiar umbral de turno a 10 horas
"""

import pandas as pd
import numpy as np
import sqlite3
import argparse
import os
import glob
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────────────────────────────────────
RAW_DIR       = "data/raw"         # Carpeta donde se depositan los .xlsx semanales
PROCESSED_DIR = "data/processed"  # Carpeta de salida para los CSV
DB_PATH       = "data/attendance.db"

# Ventana de deduplicación: registros del mismo tipo dentro de este margen
# (segundos) se consideran el mismo evento (el sistema QR genera duplicados).
DEDUP_WINDOW_SECONDS = 60

# Brecha máxima entre eventos consecutivos del MISMO turno.
# Si dos eventos están separados por MÁS de este valor (horas), se abre un
# turno nuevo. Aumenta este valor si tus turnos nocturnos duran más de 8 horas
# sin ningún registro intermedio.
MAX_GAP_TURNO_HORAS = 8

# Umbral de turno para guardias (pueden hacer 24hs o más consecutivas)
MAX_GAP_GUARDIA_HORAS = 36

# Categorías de empleados — agregar nuevos empleados aquí
CATEGORIAS_EMPLEADOS = {
    # Administrador
    "XAVIER GONZALEZ ANGULO":              "Administrador",
    # Guardias
    "CARLOS CONTRERAS":                    "Guardia",
    "CHRISTIAN CORTES":                    "Guardia",
    "NOE CONTRERAS GARCIA":                "Guardia",
    "JOSE MANUEL NOLASCO SORIANO":         "Guardia",
    # De planta
    "ALEXIS SERRANO":                      "De planta",
    "JUAN GARCIA":                         "De planta",
    "IRVING GARCIA":                       "De planta",
    "JACOBO JUAREZ CORDOBA":               "De planta",
    "MARIA FERNANDA NUNEZ HERNANDEZ":      "De planta",
    "CATALINA GLORIA HERNANDEZ  SUAREZ":   "De planta",
    # Externos
    "DANIEL SANCHEZ LOPEZ":                "Externo",
}

def normalizar_nombre(nombre):
    """Normaliza un nombre para buscar en el diccionario de categorías."""
    import unicodedata, re
    nombre = nombre.upper().strip()
    # Eliminar acentos
    nombre = ''.join(
        c for c in unicodedata.normalize('NFD', nombre)
        if unicodedata.category(c) != 'Mn'
    )
    # Colapsar espacios multiples en uno solo
    nombre = re.sub(r' +', ' ', nombre)
    return nombre

def obtener_categoria(nombre):
    """Retorna la categoría del empleado o 'Sin categoría' si no está en el diccionario."""
    nombre_norm = normalizar_nombre(nombre)
    # Buscar coincidencia exacta
    if nombre_norm in CATEGORIAS_EMPLEADOS:
        return CATEGORIAS_EMPLEADOS[nombre_norm]
    # Buscar coincidencia parcial
    for key, cat in CATEGORIAS_EMPLEADOS.items():
        if key in nombre_norm or nombre_norm in key:
            return cat
    return "Sin categoria"

def get_gap_horas(nombre):
    """Retorna el umbral de turno según la categoría del empleado."""
    if obtener_categoria(nombre) == "Guardia":
        return MAX_GAP_GUARDIA_HORAS
    return MAX_GAP_TURNO_HORAS


# ──────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ──────────────────────────────────────────────────────────────────────────────

def parse_datetime(fecha_str: str, hora_str: str) -> pd.Timestamp:
    """Combina strings de fecha y hora en un Timestamp."""
    return pd.to_datetime(f"{fecha_str} {hora_str}", dayfirst=True)


def deduplicate_events(df_emp: pd.DataFrame, window_sec: int = 60) -> pd.DataFrame:
    """
    Elimina eventos duplicados de un empleado (ya ordenados por datetime):
    si dos registros del mismo tipo están dentro de `window_sec` segundos,
    conserva solo el primero (para entradas) o el último (para salidas).

    Opera sobre el dataset completo del empleado (no solo por día), de modo
    que los registros de días distintos no interfieren entre sí.
    """
    df_emp = df_emp.sort_values("datetime").copy().reset_index(drop=True)
    rows_to_keep = []
    prev_time = None
    prev_tipo = None

    for _, row in df_emp.iterrows():
        if prev_time is None:
            rows_to_keep.append(row)
        else:
            diff = (row["datetime"] - prev_time).total_seconds()
            same_tipo = row["tipo"] == prev_tipo
            if same_tipo and diff <= window_sec:
                # Duplicado: para salidas reemplaza con el último
                if row["es_salida"]:
                    rows_to_keep[-1] = row
                # Para entradas conserva el primero (no hacer nada)
            else:
                rows_to_keep.append(row)
        prev_time = row["datetime"]
        prev_tipo = row["tipo"]

    return pd.DataFrame(rows_to_keep).reset_index(drop=True)


def detectar_turnos(df_emp_dedup: pd.DataFrame, max_gap_horas: float = MAX_GAP_TURNO_HORAS) -> list:
    """
    Agrupa los eventos deduplicados de un empleado en turnos.

    REGLA CLAVE: Un nuevo turno solo se abre cuando el evento anterior es
    una *Salida* y el siguiente es una *Entrada* con una brecha mayor a
    MAX_GAP_TURNO_HORAS. De este modo:

      • Entrada 08:00 → Salida 17:00 (misma jornada, 9 h de brecha)
        → Entrada→Salida: NO se parte el turno ✓

      • Salida 17:00 → Entrada 08:00 día siguiente (15 h de brecha)
        → Salida→Entrada con brecha > umbral: turno nuevo ✓

      • Salida 23:00 → Entrada 01:00 día siguiente (2 h de brecha)
        → Salida→Entrada con brecha < umbral: turno nocturno, mismo turno ✓

    Retorna una lista de DataFrames, uno por turno.
    """
    if df_emp_dedup.empty:
        return []

    df = df_emp_dedup.sort_values("datetime").reset_index(drop=True)
    turnos = []
    inicio = 0

    for i in range(1, len(df)):
        prev = df.loc[i - 1]
        curr = df.loc[i]
        gap_h = (curr["datetime"] - prev["datetime"]).total_seconds() / 3600

        # Un nuevo turno se abre cuando la brecha supera el umbral, EXCEPTO
        # en el caso Entrada→Salida (empleado trabajando un turno largo sin
        # ningún registro intermedio, p.ej. turno nocturno de 10 h).
        #
        #   Entrada → Salida  (brecha larga): MISMO turno  (trabajando) ✓
        #   Salida  → Entrada (brecha larga): TURNO NUEVO  (volvió al día siguiente) ✓
        #   Salida  → Entrada (brecha corta): MISMO turno  (salida nocturna y regreso) ✓
        #   Entrada → Entrada (brecha larga): TURNO NUEVO  (día sin salida registrada) ✓
        #   Salida  → Salida  (brecha larga): TURNO NUEVO  (día sin entrada registrada) ✓
        es_trabajando = (not prev["es_salida"]) and curr["es_salida"]  # E→S: mismo turno
        if not es_trabajando and gap_h > max_gap_horas:
            turnos.append(df.iloc[inicio:i].copy())
            inicio = i

    turnos.append(df.iloc[inicio:].copy())
    return turnos


def calcular_horas_fuera(turno_eventos: pd.DataFrame):
    """
    Dado el DataFrame de eventos de un turno (deduplicados, ordenados),
    detecta salidas intermedias (salida seguida de reentrada antes de la
    salida final) y calcula el tiempo fuera.

    Retorna:
        salidas_intermedias : lista de dicts
        total_minutos_fuera : float
    """
    eventos = turno_eventos.sort_values("datetime").reset_index(drop=True)

    if len(eventos) == 0:
        return [], 0.0

    entradas = eventos[~eventos["es_salida"]]
    salidas  = eventos[eventos["es_salida"]]

    if entradas.empty or salidas.empty:
        return [], 0.0

    primera_entrada = entradas.iloc[0]["datetime"]
    ultima_salida   = salidas.iloc[-1]["datetime"]

    # Eventos intermedios: todo lo que queda entre entrada y última salida,
    # excluyendo la primera entrada y la última salida
    intermedios = eventos[
        (eventos["datetime"] > primera_entrada) &
        (eventos["datetime"] < ultima_salida)
    ].reset_index(drop=True)

    salidas_inter = []
    total_mins = 0.0
    i = 0

    while i < len(intermedios):
        row = intermedios.iloc[i]
        if row["es_salida"]:
            # Buscar la siguiente entrada
            j = i + 1
            while j < len(intermedios) and intermedios.iloc[j]["es_salida"]:
                j += 1  # saltar salidas duplicadas seguidas

            if j < len(intermedios) and not intermedios.iloc[j]["es_salida"]:
                hora_sal  = row["datetime"]
                hora_reen = intermedios.iloc[j]["datetime"]
                mins = (hora_reen - hora_sal).total_seconds() / 60
                salidas_inter.append({
                    "hora_salida_intermedia": hora_sal,
                    "hora_reentrada":         hora_reen,
                    "minutos_fuera":          round(mins, 2),
                })
                total_mins += mins
                i = j + 1
            else:
                i += 1
        else:
            i += 1

    return salidas_inter, total_mins


# ──────────────────────────────────────────────────────────────────────────────
# CARGA DEL EXCEL
# ──────────────────────────────────────────────────────────────────────────────

def load_excel(filepath: str) -> pd.DataFrame:
    """Carga el Excel y normaliza columnas."""
    df = pd.read_excel(filepath, sheet_name=0)

    # Normalizar nombres de columnas
    df.columns = [c.strip().lower() for c in df.columns]
    col_map = {}
    for c in df.columns:
        if "qr" in c or "tipo" in c:
            col_map[c] = "qr"
        elif "nombre" in c or "empleado" in c:
            col_map[c] = "nombre"
        elif "fecha" in c:
            col_map[c] = "fecha"
        elif "hora" in c:
            col_map[c] = "hora"
    df = df.rename(columns=col_map)[["qr", "nombre", "fecha", "hora"]]

    # Limpiar
    df = df.dropna(subset=["nombre", "fecha", "hora"])
    df["nombre"] = df["nombre"].str.strip().str.upper()

    # Convertir fecha: puede ser string "DD/MM/YYYY" o número de serie de Excel
    def normalizar_fecha(val):
        try:
            # Si es número de serie de Excel
            f = float(str(val).strip())
            if f > 1000:  # Es un número de serie válido
                from datetime import datetime, timedelta
                return (datetime(1899, 12, 30) + timedelta(days=int(f))).strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            pass
        return str(val).strip()

    # Convertir hora: puede ser string "HH:MM:SS", decimal (0.375 = 09:00:00) o datetime
    def normalizar_hora(val):
        try:
            val_str = str(val).strip()
            # Si ya tiene formato HH:MM:SS o HH:MM
            if ":" in val_str:
                return val_str[:8]  # Tomar solo HH:MM:SS
            # Si es decimal de Excel (fracción del día)
            f = float(val_str)
            if 0 <= f < 1:
                total_segundos = round(f * 86400)
                h = total_segundos // 3600
                m = (total_segundos % 3600) // 60
                s = total_segundos % 60
                return f"{h:02d}:{m:02d}:{s:02d}"
        except (ValueError, TypeError):
            pass
        return str(val).strip()

    df["fecha"] = df["fecha"].apply(normalizar_fecha)
    df["hora"]  = df["hora"].apply(normalizar_hora)

    # Tipo de evento
    df["qr_lower"]  = df["qr"].str.lower().fillna("")
    df["es_salida"] = df["qr_lower"].str.contains("salida")
    df["tipo"]      = np.where(df["es_salida"], "Salida", "Entrada")

    # Datetime combinado
    df["datetime"] = df.apply(
        lambda r: parse_datetime(r["fecha"], r["hora"]), axis=1
    )

    # Semana ISO y año (basado en la fecha del evento)
    df["semana"] = df["datetime"].dt.isocalendar().week.astype(int)
    df["anio"]   = df["datetime"].dt.isocalendar().year.astype(int)
    df["semana_label"] = df.apply(
        lambda r: f"{r['anio']}-S{str(r['semana']).zfill(2)}", axis=1
    )

    return df


# ──────────────────────────────────────────────────────────────────────────────
# PROCESAMIENTO POR SEMANA
# ──────────────────────────────────────────────────────────────────────────────

def procesar_semana(df: pd.DataFrame):
    """
    Procesa todos los empleados de una semana usando detección de turnos.
    Los turnos nocturnos (entrada un día, salida al siguiente) se manejan
    como un único turno atribuido a la fecha de la primera entrada.

    Retorna: (df_diario, df_interm, df_semanal)
    """
    registros_diarios   = []
    salidas_interm_rows = []

    for emp in sorted(df["nombre"].unique()):
        df_emp = df[df["nombre"] == emp].copy()

        # Deduplicar sobre el dataset completo del empleado en la semana
        df_emp_dedup = deduplicate_events(df_emp, DEDUP_WINDOW_SECONDS)

        # Detectar turnos con umbral según categoría del empleado
        gap_emp = get_gap_horas(emp)
        turnos = detectar_turnos(df_emp_dedup, gap_emp)

        for turno_idx, turno in enumerate(turnos):
            entradas = turno[~turno["es_salida"]]
            salidas  = turno[turno["es_salida"]]

            # Timestamps de inicio y fin del turno
            ts_entrada = entradas["datetime"].min() if not entradas.empty else pd.NaT
            ts_salida  = salidas["datetime"].max()  if not salidas.empty  else pd.NaT

            # Fechas para el reporte
            fecha_entrada = ts_entrada.date() if pd.notna(ts_entrada) else None
            fecha_salida  = ts_salida.date()  if pd.notna(ts_salida)  else None

            # El turno se atribuye a la fecha de entrada (o de salida si no hay entrada)
            fecha_turno = fecha_entrada or fecha_salida

            # Turno nocturno = entrada y salida en días distintos
            turno_nocturno = (
                fecha_entrada is not None and
                fecha_salida  is not None and
                fecha_entrada != fecha_salida
            )

            # Semana a la que pertenece el turno (según su fecha de entrada)
            sem_turno = turno["semana_label"].iloc[0]
            if fecha_entrada is not None:
                ts_ref = pd.Timestamp(fecha_entrada)
                sem_num = ts_ref.isocalendar().week
                sem_anio = ts_ref.isocalendar().year
                sem_turno = f"{sem_anio}-S{str(sem_num).zfill(2)}"

            # Horas trabajadas brutas
            if pd.notna(ts_entrada) and pd.notna(ts_salida):
                mins_brutos = (ts_salida - ts_entrada).total_seconds() / 60
            else:
                mins_brutos = np.nan

            # Salidas intermedias y tiempo fuera
            sal_inter, mins_fuera = calcular_horas_fuera(turno)

            # Horas netas
            if not np.isnan(mins_brutos):
                horas_trabajadas = round((mins_brutos - mins_fuera) / 60, 4)
                horas_fuera      = round(mins_fuera / 60, 4)
            else:
                horas_trabajadas = np.nan
                horas_fuera      = np.nan

            # Calcular turnos de guardia (cada 24hs)
            cat_emp = obtener_categoria(emp)
            if cat_emp == "Guardia" and not np.isnan(horas_trabajadas):
                turnos_guardia = round(horas_trabajadas / 24, 2)
            else:
                turnos_guardia = None

            registros_diarios.append({
                "semana":           sem_turno,
                "empleado":         emp,
                "categoria":        cat_emp,
                "fecha":            fecha_turno,
                "fecha_salida":     fecha_salida if turno_nocturno else None,
                "turno_nocturno":   int(turno_nocturno),
                "hora_entrada":     ts_entrada.strftime("%H:%M:%S") if pd.notna(ts_entrada) else None,
                "hora_salida":      ts_salida.strftime("%H:%M:%S")  if pd.notna(ts_salida)  else None,
                "horas_trabajadas": horas_trabajadas,
                "horas_fuera":      horas_fuera,
                "n_salidas_interm": len(sal_inter),
                "sin_salida":       int(salidas.empty),
                "sin_entrada":      int(entradas.empty),
                "turnos_guardia":   turnos_guardia,
            })

            # Salidas intermedias detalladas
            for si in sal_inter:
                salidas_interm_rows.append({
                    "semana":                 sem_turno,
                    "empleado":               emp,
                    "fecha":                  fecha_turno,
                    "hora_salida_intermedia": si["hora_salida_intermedia"].strftime("%H:%M:%S"),
                    "hora_reentrada":         si["hora_reentrada"].strftime("%H:%M:%S"),
                    "minutos_fuera":          si["minutos_fuera"],
                })

    df_diario = pd.DataFrame(registros_diarios)
    df_interm  = pd.DataFrame(salidas_interm_rows) if salidas_interm_rows else pd.DataFrame(
        columns=["semana", "empleado", "fecha", "hora_salida_intermedia",
                 "hora_reentrada", "minutos_fuera"]
    )

    # ── Resumen semanal ──────────────────────────────────────────────────────
    if not df_diario.empty:
        # Incluir categoria en el resumen
        cat_map = df_diario.groupby("empleado")["categoria"].first()
        df_sem = df_diario.groupby(["semana", "empleado"]).agg(
            turnos_registrados  = ("fecha",             "count"),
            turnos_con_entrada  = ("sin_entrada",        lambda x: int((x == 0).sum())),
            turnos_con_salida   = ("sin_salida",         lambda x: int((x == 0).sum())),
            turnos_nocturnos    = ("turno_nocturno",     "sum"),
            total_horas         = ("horas_trabajadas",   "sum"),
            promedio_horas_turno= ("horas_trabajadas",   "mean"),
            total_horas_fuera   = ("horas_fuera",        "sum"),
            total_salidas_interm= ("n_salidas_interm",   "sum"),
            total_turnos_guardia= ("turnos_guardia",     "sum"),
        ).reset_index()
        df_sem["categoria"] = df_sem["empleado"].map(cat_map)

        df_sem["total_horas"]          = df_sem["total_horas"].round(2)
        df_sem["promedio_horas_turno"] = df_sem["promedio_horas_turno"].round(2)
        df_sem["total_horas_fuera"]    = df_sem["total_horas_fuera"].round(2)
    else:
        df_sem = pd.DataFrame()

    return df_diario, df_interm, df_sem


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────

def run(files: list, use_sqlite: bool = False):
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    all_diario  = []
    all_interm  = []
    all_semanal = []

    for fpath in files:
        print(f"\n[>] Procesando: {fpath}")
        df_raw = load_excel(fpath)
        semanas = sorted(df_raw["semana_label"].unique())
        print(f"   Semanas detectadas : {', '.join(semanas)}")
        print(f"   Empleados          : {df_raw['nombre'].nunique()}")
        print(f"   Registros crudos   : {len(df_raw)}")

        for sem in semanas:
            df_sem_raw = df_raw[df_raw["semana_label"] == sem]
            d, i, s = procesar_semana(df_sem_raw)
            all_diario.append(d)
            all_interm.append(i)
            all_semanal.append(s)

    # Consolidar
    df_diario  = pd.concat(all_diario,  ignore_index=True) if all_diario  else pd.DataFrame()
    df_interm  = pd.concat(all_interm,  ignore_index=True) if all_interm  else pd.DataFrame()
    df_semanal = pd.concat(all_semanal, ignore_index=True) if all_semanal else pd.DataFrame()

    # Deduplicar en caso de reprocesar el mismo período
    if not df_diario.empty:
        df_diario  = df_diario.drop_duplicates(subset=["semana", "empleado", "fecha", "hora_entrada"])
    if not df_interm.empty:
        df_interm  = df_interm.drop_duplicates(
            subset=["semana", "empleado", "fecha", "hora_salida_intermedia"]
        )
    if not df_semanal.empty:
        df_semanal = df_semanal.drop_duplicates(subset=["semana", "empleado"])

    # ── Guardar CSV ──────────────────────────────────────────────────────────
    out_d = os.path.join(PROCESSED_DIR, "registros_diarios.csv")
    out_i = os.path.join(PROCESSED_DIR, "salidas_intermedias.csv")
    out_s = os.path.join(PROCESSED_DIR, "resumen_semanal.csv")

    df_diario.to_csv(out_d, index=False, encoding="utf-8-sig")
    df_interm.to_csv(out_i, index=False, encoding="utf-8-sig")
    df_semanal.to_csv(out_s, index=False, encoding="utf-8-sig")

    print(f"\n[OK] CSVs guardados en '{PROCESSED_DIR}/':")
    print(f"   -> registros_diarios.csv   ({len(df_diario)} filas)")
    print(f"   -> salidas_intermedias.csv ({len(df_interm)} filas)")
    print(f"   -> resumen_semanal.csv     ({len(df_semanal)} filas)")

    # ── Guardar SQLite ───────────────────────────────────────────────────────
    if use_sqlite:
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            df_diario.to_sql("registros_diarios",   conn, if_exists="replace", index=False)
            df_interm.to_sql("salidas_intermedias",  conn, if_exists="replace", index=False)
            df_semanal.to_sql("resumen_semanal",     conn, if_exists="replace", index=False)
        print(f"\n[OK] SQLite guardado en '{DB_PATH}'")

    # ── Vista previa ─────────────────────────────────────────────────────────
    print("\n--- RESUMEN SEMANAL ---------------------------------------------")
    if not df_semanal.empty:
        print(df_semanal.to_string(index=False))

    print("\n--- REGISTROS DIARIOS / TURNOS ----------------------------------")
    if not df_diario.empty:
        cols_preview = ["semana", "empleado", "fecha", "fecha_salida",
                        "turno_nocturno", "hora_entrada", "hora_salida", "horas_trabajadas"]
        print(df_diario[cols_preview].to_string(index=False))

    # Alertas de turnos sin datos completos
    if not df_diario.empty:
        sin_sal = df_diario[df_diario["sin_salida"] == 1]
        sin_ent = df_diario[df_diario["sin_entrada"] == 1]
        if not sin_sal.empty:
            print(f"\n[!]  Turnos SIN salida registrada ({len(sin_sal)}):")
            for _, r in sin_sal.iterrows():
                print(f"   {r['empleado']}  {r['fecha']}  entrada: {r['hora_entrada']}")
        if not sin_ent.empty:
            print(f"\n[!]  Turnos SIN entrada registrada ({len(sin_ent)}):")
            for _, r in sin_ent.iterrows():
                print(f"   {r['empleado']}  {r['fecha']}  salida: {r['hora_salida']}")

    return df_diario, df_interm, df_semanal


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Procesa archivos de asistencia QR")
    parser.add_argument(
        "--file", "-f",
        help="Ruta a un Excel específico (si no se indica, procesa todos los .xlsx en data/raw/)"
    )
    parser.add_argument(
        "--sqlite", "-db",
        action="store_true",
        help="Además de CSV, guarda una base de datos SQLite en data/attendance.db"
    )
    parser.add_argument(
        "--gap", "-g",
        type=float,
        default=MAX_GAP_TURNO_HORAS,
        help=f"Umbral de horas para separar turnos (default: {MAX_GAP_TURNO_HORAS})"
    )
    args = parser.parse_args()

    MAX_GAP_TURNO_HORAS = args.gap  # Permite ajustar desde CLI

    if args.file:
        files = [args.file]
    else:
        files = sorted(glob.glob(os.path.join(RAW_DIR, "*.xlsx")))
        if not files:
            print(f"[!]  No se encontraron archivos .xlsx en '{RAW_DIR}/'")
            print(f"   Coloca tus archivos semanales en esa carpeta o usa --file")
            exit(1)

    run(files, use_sqlite=args.sqlite)
