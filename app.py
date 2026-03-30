"""
app.py — Portal de Reportes de Asistencia
==========================================
Dos modos de trabajo:
  1. AUTOMÁTICO: lee todos los .xlsx de una carpeta (RAW_DIR) y genera CSVs
  2. MANUAL: sube un archivo desde el navegador

Deploy gratuito en: https://streamlit.io/cloud
"""

import io
import os
import glob
import tempfile

import numpy as np
import pandas as pd
import streamlit as st

from process_attendance import (
    DEDUP_WINDOW_SECONDS,
    MAX_GAP_TURNO_HORAS,
    load_excel,
    procesar_semana,
    run as run_pipeline,
    RAW_DIR,
    PROCESSED_DIR,
)
import process_attendance as pa

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Reportes de Asistencia",
    page_icon="🕐",
    layout="wide",
)

st.markdown("""
<style>
  .metric-card { background:#f0f2f6; border-radius:8px; padding:16px 20px; text-align:center; }
  .metric-card h2 { margin:0; font-size:2rem; }
  .metric-card p  { margin:0; color:#555; font-size:.9rem; }
</style>
""", unsafe_allow_html=True)

st.title("🕐 Portal de Reportes de Asistencia")
st.caption("Procesá el Excel semanal del sistema QR y visualizá los reportes.")
st.divider()

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuración")

    raw_dir = st.text_input(
        "📁 Carpeta de Excel semanales",
        value=RAW_DIR,
        help="Ruta local a la carpeta donde depositás los .xlsx cada semana. "
             "En OneDrive sincronizado, usá la ruta local del Explorador de archivos, "
             "ej: C:\\Users\\nadia\\OneDrive\\ASISTENCIA POR SEMANAS\\data\\raw"
    )
    processed_dir = st.text_input(
        "📁 Carpeta de salida (CSVs)",
        value=PROCESSED_DIR,
        help="Donde se guardarán los CSV para Power BI."
    )

    st.divider()

    gap_horas = st.number_input(
        "Umbral turno nocturno (horas)",
        min_value=1, max_value=24, value=int(MAX_GAP_TURNO_HORAS),
    )
    dedup_seg = st.number_input(
        "Ventana deduplicación (segundos)",
        min_value=5, max_value=300, value=int(DEDUP_WINDOW_SECONDS),
    )

    st.divider()
    st.markdown("""
**Columnas esperadas en el Excel:**
- `QR` — tipo de evento
- `Nombre` — nombre del empleado
- `Fecha` — fecha (DD/MM/YYYY)
- `Hora` — hora (HH:MM:SS)
""")

# Aplicar configuración al módulo
pa.DEDUP_WINDOW_SECONDS = dedup_seg
pa.MAX_GAP_TURNO_HORAS  = gap_horas
pa.RAW_DIR              = raw_dir
pa.PROCESSED_DIR        = processed_dir

# ── Selector de modo ─────────────────────────────────────────────────────────
st.subheader("¿Cómo querés cargar los datos?")
modo = st.radio(
    "Modo",
    options=["🗂️ Automático — leer desde carpeta", "📤 Manual — subir archivo"],
    horizontal=True,
    label_visibility="collapsed",
)

st.divider()

df_diario = df_interm = df_semanal = pd.DataFrame()

# ══════════════════════════════════════════════════════════════════════════════
# MODO AUTOMÁTICO
# ══════════════════════════════════════════════════════════════════════════════
if modo == "🗂️ Automático — leer desde carpeta":

    st.markdown(f"**Carpeta configurada:** `{raw_dir}`")

    if not os.path.isdir(raw_dir):
        st.warning(f"⚠️ La carpeta `{raw_dir}` no existe. Verificá la ruta en el sidebar.")
        try:
            os.makedirs(raw_dir, exist_ok=True)
            st.info(f"📁 Carpeta creada: `{raw_dir}`")
        except Exception as e:
            st.error(f"No se pudo crear la carpeta: {e}")
        st.stop()

    archivos_disponibles = sorted(glob.glob(os.path.join(raw_dir, "*.xlsx")))

    if not archivos_disponibles:
        st.info(f"No hay archivos .xlsx en `{raw_dir}`. Copiá tus Excel semanales allí.")
        st.stop()

    st.success(f"📂 {len(archivos_disponibles)} archivo(s) encontrado(s):")
    for f in archivos_disponibles:
        st.markdown(f"  - `{os.path.basename(f)}`")

    seleccion = st.multiselect(
        "Seleccioná archivos a procesar (vacío = todos)",
        options=[os.path.basename(f) for f in archivos_disponibles],
        placeholder="Todos los archivos",
    )
    files_a_procesar = (
        [os.path.join(raw_dir, f) for f in seleccion]
        if seleccion else archivos_disponibles
    )

    if not st.button("▶️ Procesar ahora", type="primary"):
        st.stop()

    with st.spinner(f"Procesando {len(files_a_procesar)} archivo(s)..."):
        try:
            df_diario, df_interm, df_semanal = run_pipeline(files_a_procesar, use_sqlite=False)
            os.makedirs(processed_dir, exist_ok=True)
        except Exception as e:
            st.error(f"Error al procesar: {e}")
            st.stop()

    st.success(f"Procesado correctamente. Revisá las jornadas sospechosas antes de guardar.")

    # ── Validación de jornadas sospechosas ───────────────────────────────────
    UMBRAL_PLANTA_HS = 16
    mask_sospechosas = (
        (df_diario["categoria"] == "De planta") &
        (pd.to_numeric(df_diario["horas_trabajadas"], errors="coerce") > UMBRAL_PLANTA_HS) &
        (df_diario["sin_salida"] == 0) &
        (df_diario["sin_entrada"] == 0)
    ) if "categoria" in df_diario.columns else pd.Series([False] * len(df_diario))

    df_sospechosas = df_diario[mask_sospechosas].copy()

    if not df_sospechosas.empty:
        st.warning(f"Se detectaron {len(df_sospechosas)} jornada(s) de más de {UMBRAL_PLANTA_HS}hs en empleados de planta. Confirma cada caso antes de guardar.")

        decisiones = {}
        for idx, row in df_sospechosas.iterrows():
            key = f"{row['empleado']}_{row['fecha']}"
            st.markdown(f"**{row['empleado']}** — {str(row['fecha'])[:10]} — {pd.to_numeric(row['horas_trabajadas'], errors='coerce'):.1f}hs ({row['hora_entrada']} a {row['hora_salida']})")
            decision = st.radio(
                "¿Qué es este registro?",
                options=["Excepcion valida (jornada extendida)", "Error (marcar como incompleto)"],
                key=f"decision_{key}",
                horizontal=True,
            )
            decisiones[idx] = decision

        if st.button("Confirmar y guardar", type="primary"):
            for idx, decision in decisiones.items():
                if "Error" in decision:
                    df_diario.loc[idx, "sin_salida"] = 1
                    df_diario.loc[idx, "hora_salida"] = None
                    df_diario.loc[idx, "horas_trabajadas"] = np.nan
                    df_diario.loc[idx, "jornada_excepcional"] = 0
                else:
                    df_diario.loc[idx, "jornada_excepcional"] = 1

            # Recalcular resumen semanal con cambios
            from process_attendance import procesar_semana as _ps
            df_semanal = df_diario.groupby(["semana", "empleado"]).agg(
                categoria           = ("categoria",        "first"),
                turnos_registrados  = ("fecha",            "count"),
                turnos_con_entrada  = ("sin_entrada",      lambda x: int((x == 0).sum())),
                turnos_con_salida   = ("sin_salida",       lambda x: int((x == 0).sum())),
                turnos_nocturnos    = ("turno_nocturno",   "sum"),
                total_horas         = ("horas_trabajadas", "sum"),
                promedio_horas_turno= ("horas_trabajadas", "mean"),
                total_horas_fuera   = ("horas_fuera",      "sum"),
                total_salidas_interm= ("n_salidas_interm", "sum"),
                jornadas_excepcionales = ("jornada_excepcional", "sum"),
            ).reset_index()

            os.makedirs(processed_dir, exist_ok=True)
            df_diario.to_csv(os.path.join(processed_dir, "registros_diarios.csv"),
                             index=False, encoding="utf-8-sig", decimal=",")
            df_interm.to_csv(os.path.join(processed_dir, "salidas_intermedias.csv"),
                             index=False, encoding="utf-8-sig", decimal=",")
            df_semanal.to_csv(os.path.join(processed_dir, "resumen_semanal.csv"),
                              index=False, encoding="utf-8-sig", decimal=",")
            st.success("Guardado correctamente. Ya podés subir a GitHub.")
            st.rerun()
    else:
        # Sin jornadas sospechosas — guardar directamente
        os.makedirs(processed_dir, exist_ok=True)
        df_diario.to_csv(os.path.join(processed_dir, "registros_diarios.csv"),
                         index=False, encoding="utf-8-sig", decimal=",")
        df_interm.to_csv(os.path.join(processed_dir, "salidas_intermedias.csv"),
                         index=False, encoding="utf-8-sig", decimal=",")
        df_semanal.to_csv(os.path.join(processed_dir, "resumen_semanal.csv"),
                          index=False, encoding="utf-8-sig", decimal=",")
        st.info("Sin jornadas sospechosas. CSVs guardados correctamente.")

# ══════════════════════════════════════════════════════════════════════════════
# MODO MANUAL
# ══════════════════════════════════════════════════════════════════════════════
else:
    uploaded = st.file_uploader(
        "Arrastrá o seleccioná el Excel semanal (.xlsx)",
        type=["xlsx"],
    )

    if uploaded is None:
        st.info("Subí un archivo para comenzar.")
        st.stop()

    with st.spinner("Procesando registros..."):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        try:
            df_raw = load_excel(tmp_path)
        finally:
            os.unlink(tmp_path)

        semanas = sorted(df_raw["semana_label"].unique())
        all_d, all_i, all_s = [], [], []
        for sem in semanas:
            d, i, s = procesar_semana(df_raw[df_raw["semana_label"] == sem])
            all_d.append(d); all_i.append(i); all_s.append(s)

        df_diario  = pd.concat(all_d, ignore_index=True)
        df_interm  = pd.concat(all_i, ignore_index=True)
        df_semanal = pd.concat(all_s, ignore_index=True)

    st.success(f"✅ {df_raw['nombre'].nunique()} empleados · "
               f"{len(semanas)} semana(s) · {len(df_raw)} registros crudos")

    # Guardar en carpeta si existe y es accesible
    if os.path.isdir(processed_dir):
        try:
            df_diario.to_csv(os.path.join(processed_dir, "registros_diarios.csv"),
                             index=False, encoding="utf-8-sig", decimal=",")
            df_interm.to_csv(os.path.join(processed_dir, "salidas_intermedias.csv"),
                             index=False, encoding="utf-8-sig", decimal=",")
            df_semanal.to_csv(os.path.join(processed_dir, "resumen_semanal.csv"),
                              index=False, encoding="utf-8-sig", decimal=",")
            st.info(f"📁 CSVs también guardados en `{processed_dir}`")
        except Exception:
            pass  # Si falla silenciosamente, el usuario puede descargar igual

# ══════════════════════════════════════════════════════════════════════════════
# VISUALIZACIÓN (común a ambos modos)
# ══════════════════════════════════════════════════════════════════════════════
if df_diario.empty:
    st.stop()

st.divider()

# KPIs
completos_mask   = (df_diario["sin_entrada"] == 0) & (df_diario["sin_salida"] == 0)
turnos_completos = int(completos_mask.sum())
nocturnos        = int(df_diario["turno_nocturno"].sum())
sin_salida_n     = int(df_diario["sin_salida"].sum())

col1, col2, col3, col4 = st.columns(4)
col1.metric("Turnos registrados", len(df_diario))
col2.metric("Turnos completos",   turnos_completos)
col3.metric("Turnos nocturnos",   nocturnos)
col4.metric("⚠️ Sin salida",      sin_salida_n,
            delta=f"-{sin_salida_n}" if sin_salida_n else None,
            delta_color="inverse")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Resumen semanal",
    "📅 Registros por turno",
    "🚶 Salidas intermedias",
    "⚠️ Alertas",
])

with tab1:
    st.subheader("Resumen por empleado y semana")
    if not df_semanal.empty:
        st.dataframe(
            df_semanal.style.format({
                "total_horas":          "{:.2f}",
                "promedio_horas_turno": "{:.2f}",
                "total_horas_fuera":    "{:.2f}",
            }),
            use_container_width=True, hide_index=True,
        )

with tab2:
    st.subheader("Detalle por turno")
    filtro_emp = st.multiselect(
        "Filtrar por empleado",
        options=sorted(df_diario["empleado"].unique()),
        placeholder="Todos los empleados",
    )
    df_show = df_diario if not filtro_emp else df_diario[df_diario["empleado"].isin(filtro_emp)]
    if not df_show.empty:
        def highlight_nocturno(row):
            return ["background-color:#e8f4f8"] * len(row) if row["turno_nocturno"] == 1 else [""] * len(row)

        cols_show = ["semana", "empleado", "fecha", "fecha_salida", "turno_nocturno",
                     "hora_entrada", "hora_salida", "horas_trabajadas",
                     "horas_fuera", "n_salidas_interm", "sin_entrada", "sin_salida"]
        st.dataframe(
            df_show[cols_show].style
                .apply(highlight_nocturno, axis=1)
                .format({"horas_trabajadas": "{:.2f}", "horas_fuera": "{:.2f}"}, na_rep="—"),
            use_container_width=True, hide_index=True,
        )
        st.caption("🔵 Azul = turno nocturno")

with tab3:
    st.subheader("Salidas durante la jornada")
    if not df_interm.empty:
        st.dataframe(
            df_interm.style.format({"minutos_fuera": "{:.1f} min"}),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No se detectaron salidas intermedias.")

with tab4:
    st.subheader("Alertas de datos incompletos")
    sin_sal = df_diario[df_diario["sin_salida"] == 1][["empleado", "fecha", "hora_entrada"]]
    sin_ent = df_diario[df_diario["sin_entrada"] == 1][["empleado", "fecha", "hora_salida"]]

    if not sin_sal.empty:
        st.warning(f"**{len(sin_sal)} turno(s) SIN salida registrada**")
        st.dataframe(sin_sal, use_container_width=True, hide_index=True)
    else:
        st.success("Todos los turnos tienen salida registrada. ✅")

    if not sin_ent.empty:
        st.warning(f"**{len(sin_ent)} turno(s) SIN entrada registrada**")
        st.dataframe(sin_ent, use_container_width=True, hide_index=True)
    else:
        st.success("Todos los turnos tienen entrada registrada. ✅")

st.divider()

# ── Descarga ─────────────────────────────────────────────────────────────────
st.subheader("⬇️ Descargar reportes")

def generar_excel(df_d, df_i, df_s) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_d.to_excel(writer, sheet_name="registros_diarios",   index=False)
        df_i.to_excel(writer, sheet_name="salidas_intermedias", index=False)
        df_s.to_excel(writer, sheet_name="resumen_semanal",     index=False)
    return buf.getvalue()

col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    st.download_button("📊 Excel (3 hojas)",
        data=generar_excel(df_diario, df_interm, df_semanal),
        file_name="reporte_asistencia.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True)
with col_b:
    st.download_button("📄 registros_diarios.csv",
        data=df_diario.to_csv(index=False, encoding="utf-8-sig", decimal=","),
        file_name="registros_diarios.csv", mime="text/csv",
        use_container_width=True)
with col_c:
    st.download_button("📄 salidas_intermedias.csv",
        data=df_interm.to_csv(index=False, encoding="utf-8-sig", decimal=","),
        file_name="salidas_intermedias.csv", mime="text/csv",
        use_container_width=True)
with col_d:
    st.download_button("📄 resumen_semanal.csv",
        data=df_semanal.to_csv(index=False, encoding="utf-8-sig", decimal=","),
        file_name="resumen_semanal.csv", mime="text/csv",
        use_container_width=True)

st.caption("💡 Conectá el Excel en Power BI: **Obtener datos → Excel** → seleccioná las 3 hojas.")
