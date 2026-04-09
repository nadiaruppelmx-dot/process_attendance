"""
consolidar_semana.py
====================
Convierte los archivos crudos del sistema de fichaje en un Excel
consolidado con el formato Semana_X.xlsx que espera process_attendance.py.

Fuentes:
  - Excel de Placas Kigo (entrada/salida por placa de vehiculo)
  - Excel de Reporte Asistencia Laboral (entrada/salida por QR/telefono)

Uso:
  python consolidar_semana.py
  python consolidar_semana.py --semana 5
  python consolidar_semana.py --placas ruta/placas.xlsx --asistencia ruta/asistencia.xlsx
"""

import os
import glob
import argparse
import pandas as pd

# ── Configuracion ─────────────────────────────────────────────────────────────
RAW_DIR       = "data/raw"
KIGO_DIR      = "data/raw/kigo"       # Carpeta donde se depositan los archivos crudos de Kigo
ASIST_DIR     = "data/raw/asistencia" # Carpeta donde se depositan los archivos de asistencia laboral

# Mapeo de placas a empleados
PLACAS_EMPLEADOS = {
    "TTM699A": "CARLOS CONTRERAS",
    "TWL367B": "CHRISTIAN CORTES",
    "TUM103B": "XAVIER GONZALEZ ANGULO",
    # Agregar nuevas placas aqui
}

# Placas a ignorar
PLACAS_IGNORAR = {"UJA593A"}

# Lista de empleados validos (se filtran los demas)
EMPLEADOS_VALIDOS = {
    "XAVIER GONZALEZ ANGULO",
    "CARLOS CONTRERAS",
    "CHRISTIAN CORTES",
    "NOE CONTRERAS GARCIA",
    "JOSE MANUEL NOLASCO SORIANO",
    "ALEXIS SERRANO",
    "JUAN GARCIA",
    "IRVING GARCIA",
    "JACOBO JUAREZ CORDOBA",
    "MARIA FERNANDA NUNEZ HERNANDEZ",
    "CATALINA GLORIA HERNANDEZ SUAREZ",
    "DANIEL SANCHEZ LOPEZ",
    # Aliases y variantes
    "CARLOS GUARDIA",
    "JOSE SEBASTIAN SANTILLAN DIAZ",
    "JOSE SEBASTIANV SANTILLAN DIAZ",
}

# Nombres a ignorar completamente
NOMBRES_IGNORAR = {"HACIENDA PAZ", "WHATSAPP BOT"}


# ── Normalización ─────────────────────────────────────────────────────────────
def normalizar(texto):
    """Elimina acentos y espacios multiples, convierte a mayusculas."""
    import unicodedata, re
    texto = str(texto).upper().strip()
    tabla = str.maketrans(
        'AEIOUaeiouAEIOUaeiouAEIOUaeiouAEIOUaeiouNnCc',
        'AEIOUaeiouAEIOUaeiouAEIOUaeiouAEIOUaeiouNnCc'
    )
    # Convertir caracteres con acento a ASCII
    texto = ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


def es_empleado_valido(nombre):
    """Verifica si el nombre normalizado está en la lista de empleados válidos."""
    nombre_norm = normalizar(nombre)
    # Verificar si está en ignorar
    for ignorar in NOMBRES_IGNORAR:
        if normalizar(ignorar) in nombre_norm:
            return False
    # Verificar si está en válidos (coincidencia parcial)
    for valido in EMPLEADOS_VALIDOS:
        valido_norm = normalizar(valido)
        if valido_norm == nombre_norm or valido_norm in nombre_norm or nombre_norm in valido_norm:
            return True
    return False


# ── Procesar Placas Kigo ──────────────────────────────────────────────────────
def procesar_placas(filepath):
    """
    Lee el Excel de Placas Kigo y retorna DataFrame con columnas
    QR, Nombre, Fecha, Hora.
    """
    df = pd.read_excel(filepath)

    # Filtrar placas conocidas y no ignoradas
    df = df[df['Placa'].isin(PLACAS_EMPLEADOS.keys())]
    df = df[~df['Placa'].isin(PLACAS_IGNORAR)]

    if df.empty:
        return pd.DataFrame(columns=['QR', 'Nombre', 'Fecha', 'Hora'])

    # Mapear placa a nombre
    df['Nombre'] = df['Placa'].map(PLACAS_EMPLEADOS)

    # Separar Fecha y Hora desde columna combinada
    df['Fecha_dt'] = pd.to_datetime(df['Fecha'])
    df['Fecha']    = df['Fecha_dt'].dt.strftime('%d/%m/%Y')
    df['Hora']     = df['Fecha_dt'].dt.strftime('%H:%M:%S')

    # Quedarse solo con columnas necesarias
    return df[['QR', 'Nombre', 'Fecha', 'Hora']].copy()


# ── Procesar Reporte Asistencia Laboral ───────────────────────────────────────
def procesar_asistencia(filepath):
    """
    Lee el Excel de Reporte Asistencia Laboral y retorna DataFrame con
    columnas QR, Nombre, Fecha, Hora. Filtra solo empleados validos
    y solo registros con Apertura Exitosa.
    """
    df = pd.read_excel(filepath)

    # Filtrar solo aperturas exitosas
    if 'Estado' in df.columns:
        df = df[df['Estado'].str.contains('Exitosa', na=False, case=False)]

    # Filtrar empleados validos
    df = df[df['Nombre'].apply(es_empleado_valido)]

    if df.empty:
        return pd.DataFrame(columns=['QR', 'Nombre', 'Fecha', 'Hora'])

    # La columna Puerta contiene el tipo (Entrada/Salida Visitas/Residentes)
    df = df.rename(columns={'Puerta': 'QR'})

    # Hora ya viene separada — asegurar formato HH:MM:SS
    df['Hora'] = df['Hora'].astype(str).str.strip()
    df['Hora'] = df['Hora'].apply(lambda h: h if len(h) == 8 else h + ':00')

    # Normalizar nombre
    df['Nombre'] = df['Nombre'].str.strip().str.upper()

    return df[['QR', 'Nombre', 'Fecha', 'Hora']].copy()


# ── Consolidar y guardar ──────────────────────────────────────────────────────
def consolidar(archivo_placas, archivo_asistencia, numero_semana, output_dir):
    """
    Combina ambas fuentes, elimina duplicados y guarda el Excel final.
    """
    dfs = []

    if archivo_placas and os.path.exists(archivo_placas):
        df_p = procesar_placas(archivo_placas)
        print(f"[OK] Placas Kigo: {len(df_p)} registros de {df_p['Nombre'].nunique()} empleados")
        dfs.append(df_p)
    else:
        print("[!] No se encontro archivo de Placas Kigo")

    if archivo_asistencia and os.path.exists(archivo_asistencia):
        df_a = procesar_asistencia(archivo_asistencia)
        print(f"[OK] Asistencia Laboral: {len(df_a)} registros de {df_a['Nombre'].nunique()} empleados")
        dfs.append(df_a)
    else:
        print("[!] No se encontro archivo de Asistencia Laboral")

    if not dfs:
        print("[ERROR] No hay datos para consolidar")
        return None

    df_final = pd.concat(dfs, ignore_index=True)

    # Ordenar por fecha y hora
    df_final['datetime_sort'] = pd.to_datetime(
        df_final['Fecha'] + ' ' + df_final['Hora'],
        dayfirst=True, errors='coerce'
    )
    df_final = df_final.sort_values('datetime_sort').drop(columns=['datetime_sort'])
    df_final = df_final.reset_index(drop=True)

    # Guardar
    os.makedirs(output_dir, exist_ok=True)
    nombre_archivo = f"Semana_{numero_semana}.xlsx"
    ruta_salida = os.path.join(output_dir, nombre_archivo)
    df_final.to_excel(ruta_salida, index=False)

    print(f"\n[OK] Archivo generado: {ruta_salida}")
    print(f"     Total registros : {len(df_final)}")
    print(f"     Empleados       : {df_final['Nombre'].nunique()}")
    print(f"     Empleados detectados:")
    for emp in sorted(df_final['Nombre'].unique()):
        print(f"       - {emp}")

    return ruta_salida


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Consolida archivos crudos en Semana_X.xlsx")
    parser.add_argument("--placas",     help="Ruta al Excel de Placas Kigo")
    parser.add_argument("--asistencia", help="Ruta al Excel de Reporte Asistencia Laboral")
    parser.add_argument("--semana",     type=int, default=None, help="Numero de semana (ej: 5)")
    parser.add_argument("--output",     default=RAW_DIR, help="Carpeta de salida")
    args = parser.parse_args()

    # Auto-detectar archivos si no se especifican
    archivo_placas = args.placas
    archivo_asistencia = args.asistencia

    if not archivo_placas:
        kigo_files = sorted(glob.glob(os.path.join(KIGO_DIR, "*.xlsx")))
        if kigo_files:
            archivo_placas = kigo_files[-1]
            print(f"[>] Auto-detectado Placas Kigo: {archivo_placas}")

    if not archivo_asistencia:
        asist_files = sorted(glob.glob(os.path.join(ASIST_DIR, "*.xlsx")))
        if asist_files:
            archivo_asistencia = asist_files[-1]
            print(f"[>] Auto-detectado Asistencia: {archivo_asistencia}")

    # Determinar numero de semana
    numero_semana = args.semana
    if numero_semana is None:
        # Contar semanas existentes en output
        existing = glob.glob(os.path.join(args.output, "Semana_*.xlsx"))
        numero_semana = len(existing) + 1
        print(f"[>] Numero de semana auto-asignado: {numero_semana}")

    consolidar(archivo_placas, archivo_asistencia, numero_semana, args.output)
