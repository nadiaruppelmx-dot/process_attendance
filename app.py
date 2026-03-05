"""
app.py — Portal de Reportes de Asistencia
==========================================
App Streamlit para cargar el Excel semanal, procesar los datos y
descargar los CSV listos para conectar con Power BI.

Deploy gratuito en: https://streamlit.io/cloud
"""

import io
import os
import tempfile

import numpy as np
import pandas as pd
import streamlit as st

# ── Importar lógica de procesamiento ────────────────────────────────────────
# Si process_attendance.py está en la misma carpeta que app.py, se importa así.
# Si prefieres tener todo en un solo archivo, puedes pegar aquí las funciones.
from process_attendance import (
    DEDUP_WINDOW_SECONDS,
    MAX_GAP_TURNO_HORAS,
    deduplicate_events,
    detectar_turnos,
    calcular_horas_fuera,
    load_excel,
    procesar_semana,
)

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Reportes de Asistencia",
    page_icon="🕐",
    layout="wide",
)

# ── Estilos mínimos ──────────────────────────────────────────────────────────
st.markdown("""
<style>
  .metric-card {
    background: #f0f2f6;
    border-radius: 8px;
    padding: 16px 20px;
    text-align: center;
  }
  .metric-card h2 { margin: 0; font-size: 2rem; }
  .metric-card p  { margin: 0; color: #555; font-size: 0.9rem; }
  .warning-box {
    background: #fff3cd;
    border-left: 4px solid #ffc107;
    padding: 10px 14px;
    border-radius: 4px;
    margin-bottom: 8px;
  }
</style>
""", unsafe_allow_html=True)


# ── Título ───────────────────────────────────────────────────────────────────
st.title("🕐 Portal de Reportes de Asistencia")
st.caption("Carga el Excel semanal del sistema QR y descarga los reportes para Power BI.")

st.divider()

# ── Sidebar: configuración avanzada ─────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuración")
    gap_horas = st.number_input(
        "Umbral de turno nocturno (horas)",
        min_value=1, max_value=24, value=int(MAX_GAP_TURNO_HORAS),
        help="Brecha mínima entre Salida→Entrada para considerar turno nuevo. "
             "Aumenta si tienes turnos nocturnos muy largos.",
    )
    dedup_seg = st.number_input(
        "Ventana de deduplicación (segundos)",
        min_value=5, max_value=300, value=int(DEDUP_WINDOW_SECONDS),
        help="Registros del mismo tipo dentro de este margen se consideran duplicados.",
    )
    st.divider()
    st.markdown("""
**Columnas esperadas en el Excel:**
- `QR` — tipo de evento (Entrada/Salida Visitas/Residentes)
- `Nombre` — nombre del empleado
- `Fecha` — fecha (DD/MM/YYYY)
- `Hora` — hora (HH:MM:SS)
""")


# ── Carga del archivo ────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Arrastra o selecciona el Excel semanal (.xlsx)",
    type=["xlsx"],
    help="El archivo debe contener la hoja con los registros crudos del sistema QR.",
)

if uploaded is None:
    st.info("Sube un archivo para comenzar.")
    st.stop()


# ── Procesamiento ────────────────────────────────────────────────────────────
import process_attendance as pa
pa.DEDUP_WINDOW_SECONDS = dedup_seg
pa.MAX_GAP_TURNO_HORAS  = gap_horas

with st.spinner("Procesando registros..."):
    # Guardar en archivo temporal para que load_excel lo pueda leer
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

st.success(f"✅ Archivo procesado — {df_raw['nombre'].nunique()} empleados · "
           f"{len(semanas)} semana(s) · {len(df_raw)} registros crudos")


# ── KPIs ─────────────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

turnos_completos  = int((df_diario["sin_entrada"] == 0) & (df_diario["sin_salida"] == 0) & df_diario["horas_trabajadas"].notna()).sum() if not df_diario.empty else 0

# Recalcular correctamente
if not df_diario.empty:
    completos_mask = (df_diario["sin_entrada"] == 0) & (df_diario["sin_salida"] == 0)
    turnos_completos = int(completos_mask.sum())
    nocturnos        = int(df_diario["turno_nocturno"].sum())
    sin_salida       = int(df_diario["sin_salida"].sum())
    total_horas      = df_diario["horas_trabajadas"].sum()
else:
    turnos_completos = nocturnos = sin_salida = 0
    total_horas = 0.0

col1.metric("Turnos registrados", len(df_diario))
col2.metric("Turnos completos",   turnos_completos)
col3.metric("Turnos nocturnos",   nocturnos)
col4.metric("Alertas sin salida", sin_salida, delta=f"-{sin_salida}" if sin_salida else None,
            delta_color="inverse")

st.divider()


# ── Tabs de resultados ───────────────────────────────────────────────────────
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
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Sin datos de resumen.")

with tab2:
    st.subheader("Detalle por turno")
    filtro_emp = st.multiselect(
        "Filtrar por empleado",
        options=sorted(df_diario["empleado"].unique()) if not df_diario.empty else [],
        default=[],
        placeholder="Todos los empleados",
    )
    df_show = df_diario if not filtro_emp else df_diario[df_diario["empleado"].isin(filtro_emp)]

    if not df_show.empty:
        # Resaltar turnos nocturnos
        def highlight_nocturno(row):
            if row["turno_nocturno"] == 1:
                return ["background-color: #e8f4f8"] * len(row)
            return [""] * len(row)

        cols_show = ["semana", "empleado", "fecha", "fecha_salida", "turno_nocturno",
                     "hora_entrada", "hora_salida", "horas_trabajadas",
                     "horas_fuera", "n_salidas_interm", "sin_entrada", "sin_salida"]
        st.dataframe(
            df_show[cols_show].style
                .apply(highlight_nocturno, axis=1)
                .format({"horas_trabajadas": "{:.2f}", "horas_fuera": "{:.2f}"},
                        na_rep="—"),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("🔵 Filas azules = turno nocturno (entrada y salida en días distintos)")
    else:
        st.info("Sin registros.")

with tab3:
    st.subheader("Salidas durante la jornada")
    if not df_interm.empty:
        st.dataframe(
            df_interm.style.format({"minutos_fuera": "{:.1f} min"}),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No se detectaron salidas intermedias en este período.")

with tab4:
    st.subheader("Alertas de datos incompletos")
    if not df_diario.empty:
        sin_sal = df_diario[df_diario["sin_salida"] == 1][
            ["empleado", "fecha", "hora_entrada"]
        ]
        sin_ent = df_diario[df_diario["sin_entrada"] == 1][
            ["empleado", "fecha", "hora_salida"]
        ]

        if not sin_sal.empty:
            st.warning(f"**{len(sin_sal)} turno(s) SIN salida registrada**")
            st.dataframe(sin_sal, use_container_width=True, hide_index=True)
        else:
            st.success("Todos los turnos tienen salida registrada.")

        if not sin_ent.empty:
            st.warning(f"**{len(sin_ent)} turno(s) SIN entrada registrada**")
            st.dataframe(sin_ent, use_container_width=True, hide_index=True)
        else:
            st.success("Todos los turnos tienen entrada registrada.")


st.divider()


# ── Descarga ─────────────────────────────────────────────────────────────────
st.subheader("⬇️ Descargar para Power BI")
st.markdown(
    "Descarga el archivo Excel con las tres tablas en hojas separadas. "
    "Ábrelo en Power BI con **Obtener datos → Excel** y conecta las tres hojas."
)

def generar_excel_multi_hoja(df_d, df_i, df_s) -> bytes:
    """Empaqueta las tres tablas en un Excel de múltiples hojas."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_d.to_excel(writer, sheet_name="registros_diarios",   index=False)
        df_i.to_excel(writer, sheet_name="salidas_intermedias", index=False)
        df_s.to_excel(writer, sheet_name="resumen_semanal",     index=False)
    return buf.getvalue()

nombre_base = uploaded.name.replace(".xlsx", "")

col_a, col_b, col_c, col_d = st.columns(4)

with col_a:
    excel_bytes = generar_excel_multi_hoja(df_diario, df_interm, df_semanal)
    st.download_button(
        label="📊 Excel (3 hojas)",
        data=excel_bytes,
        file_name=f"{nombre_base}_procesado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

with col_b:
    st.download_button(
        label="📄 registros_diarios.csv",
        data=df_diario.to_csv(index=False, encoding="utf-8-sig"),
        file_name=f"{nombre_base}_registros_diarios.csv",
        mime="text/csv",
        use_container_width=True,
    )

with col_c:
    st.download_button(
        label="📄 salidas_intermedias.csv",
        data=df_interm.to_csv(index=False, encoding="utf-8-sig"),
        file_name=f"{nombre_base}_salidas_intermedias.csv",
        mime="text/csv",
        use_container_width=True,
    )

with col_d:
    st.download_button(
        label="📄 resumen_semanal.csv",
        data=df_semanal.to_csv(index=False, encoding="utf-8-sig"),
        file_name=f"{nombre_base}_resumen_semanal.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.caption(
    "💡 **Tip Power BI:** Conecta el Excel de 3 hojas con "
    "Obtener datos → Excel → selecciona las 3 tablas → Transformar datos. "
    "Cada vez que proceses una nueva semana, reemplaza el archivo en la misma "
    "ubicación y haz clic en 'Actualizar' en Power BI."
)
