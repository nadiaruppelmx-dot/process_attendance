"""
director_app.py — Portal del Director de Asistencia
====================================================
App Streamlit con visualizaciones Plotly para el director.
Lee los CSVs generados por process_attendance.py.

Correr con:
    python -m streamlit run director_app.py
"""

import os
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# ── Configuración ────────────────────────────────────────────────────────────
GITHUB_USER  = "nadiaruppelmx-dot"
REPO_NAME    = "process_attendance"
BRANCH       = "main"
BASE_URL     = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/data/processed"

# Fallback a carpeta local si se corre en la PC
PROCESSED_DIR = r"C:\Users\nadia\OneDrive\Documents\ASISTENCIA POR SEMANAS\Registro con Parkimovil\reportes_asistencia\data\processed"

st.set_page_config(
    page_title="Reporte de Asistencia",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Estilos ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');

  html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background-color: #0f1117;
    color: #e8eaf0;
  }

  .main { background-color: #0f1117; }

  h1, h2, h3 {
    font-family: 'DM Serif Display', serif;
    color: #ffffff;
  }

  .kpi-card {
    background: linear-gradient(135deg, #1a1d2e 0%, #16192a 100%);
    border: 1px solid #2a2d3e;
    border-radius: 12px;
    padding: 24px 20px;
    text-align: center;
    transition: border-color 0.2s;
  }
  .kpi-card:hover { border-color: #4f8ef7; }
  .kpi-value {
    font-size: 2.4rem;
    font-weight: 600;
    color: #4f8ef7;
    margin: 0;
    line-height: 1;
  }
  .kpi-label {
    font-size: 0.8rem;
    color: #8b8fa8;
    margin-top: 6px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .alert-badge {
    background: #2d1a1a;
    border: 1px solid #7f1d1d;
    border-radius: 12px;
    padding: 24px 20px;
    text-align: center;
  }
  .alert-value {
    font-size: 2.4rem;
    font-weight: 600;
    color: #f87171;
    margin: 0;
    line-height: 1;
  }
  .alert-label {
    font-size: 0.8rem;
    color: #f87171;
    margin-top: 6px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    opacity: 0.8;
  }
  .section-title {
    font-family: 'DM Serif Display', serif;
    font-size: 1.3rem;
    color: #ffffff;
    border-left: 3px solid #4f8ef7;
    padding-left: 12px;
    margin: 28px 0 16px 0;
  }
  .stSelectbox label, .stMultiSelect label { color: #8b8fa8 !important; font-size: 0.8rem; }
  div[data-testid="stSidebar"] {
    background-color: #0a0c14;
    border-right: 1px solid #1e2130;
  }
  .sidebar-logo {
    font-family: 'DM Serif Display', serif;
    font-size: 1.4rem;
    color: #ffffff;
    padding: 8px 0 20px 0;
  }
  .sidebar-logo span { color: #4f8ef7; }
</style>
""", unsafe_allow_html=True)

PLOTLY_THEME = dict(
    paper_bgcolor="#0f1117",
    plot_bgcolor="#13162a",
    font_color="#c8cad8",
    font_family="DM Sans",
    title_font_family="DM Serif Display",
    title_font_color="#ffffff",
    colorway=["#4f8ef7", "#34d399", "#f472b6", "#fb923c", "#a78bfa", "#38bdf8"],
)

# ── Carga de datos ───────────────────────────────────────────────────────────
import urllib.request
import io

def leer_csv_github(archivo, token, **kwargs):
    """Lee un CSV desde GitHub usando la API con autenticación."""
    import json, base64
    url = f"https://api.github.com/repos/{GITHUB_USER}/{REPO_NAME}/contents/data/processed/{archivo}?ref={BRANCH}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
        contenido = base64.b64decode(data["content"]).decode("utf-8")
        return pd.read_csv(io.StringIO(contenido), **kwargs)

@st.cache_data(ttl=300)
def cargar_datos():
    """Lee desde GitHub API (cloud) o carpeta local (PC) como fallback."""
    token = None
    try:
        token = st.secrets["GITHUB_TOKEN"]
    except Exception:
        pass

    if token:
        try:
            df_d = leer_csv_github("registros_diarios.csv",
                                   token=token, decimal=",", parse_dates=["fecha"])
            df_s = leer_csv_github("resumen_semanal.csv",
                                   token=token, decimal=",")
            df_i = leer_csv_github("salidas_intermedias.csv",
                                   token=token, decimal=",")
            return df_d, df_s, df_i, None
        except Exception as e:
            return None, None, None, f"Error GitHub API: {e}"

    # Fallback a carpeta local
    try:
        df_d = pd.read_csv(os.path.join(PROCESSED_DIR, "registros_diarios.csv"),
                           decimal=",", parse_dates=["fecha"])
        df_s = pd.read_csv(os.path.join(PROCESSED_DIR, "resumen_semanal.csv"),
                           decimal=",")
        df_i = pd.read_csv(os.path.join(PROCESSED_DIR, "salidas_intermedias.csv"),
                           decimal=",")
        return df_d, df_s, df_i, None
    except Exception as e:
        return None, None, None, str(e)

df_diario, df_semanal, df_interm, error = cargar_datos()

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sidebar-logo">Asistencia<span>.</span></div>', unsafe_allow_html=True)
    st.markdown("---")

    if error:
        st.error(f"Error al cargar datos: {error}")
        st.stop()

    semanas = sorted(df_semanal["semana"].unique(), reverse=True)
    semana_sel = st.multiselect(
        "📅 Semanas",
        options=semanas,
        default=[semanas[0]] if semanas else [],
    )
    if not semana_sel:
        semana_sel = [semanas[0]] if semanas else []

    empleados = sorted(df_semanal[df_semanal["semana"].isin(semana_sel)]["empleado"].unique())
    emp_sel = st.multiselect(
        "👤 Empleados",
        options=empleados,
        default=[],
        placeholder="Todos"
    )
    if not emp_sel:
        emp_sel = empleados

    st.markdown("---")
    st.caption("Los datos se actualizan cada lunes automáticamente.")
    if st.button("🔄 Refrescar datos"):
        cargar_datos.clear()
        st.rerun()

# ── Filtrar datos ────────────────────────────────────────────────────────────
df_sem_fil = df_semanal[
    (df_semanal["semana"].isin(semana_sel)) &
    (df_semanal["empleado"].isin(emp_sel))
]
df_dia_fil = df_diario[
    (df_diario["semana"].isin(semana_sel)) &
    (df_diario["empleado"].isin(emp_sel)) &
    (df_diario["sin_salida"] == 0) &
    (df_diario["sin_entrada"] == 0)
]
df_alertas = df_diario[
    (df_diario["semana"].isin(semana_sel)) &
    (df_diario["empleado"].isin(emp_sel)) &
    ((df_diario["sin_salida"] == 1) | (df_diario["sin_entrada"] == 1))
]

# ── Título ───────────────────────────────────────────────────────────────────
st.markdown(f"# Reporte de Asistencia")
st.markdown(f"<span style='color:#8b8fa8;font-size:0.9rem'>Semanas: {', '.join(str(s) for s in semana_sel)} · {len(emp_sel)} empleado(s)</span>",
            unsafe_allow_html=True)
st.markdown("---")

# ── KPIs ─────────────────────────────────────────────────────────────────────
df_sem_fil["total_horas"]          = pd.to_numeric(df_sem_fil["total_horas"], errors="coerce")
df_sem_fil["promedio_horas_turno"] = pd.to_numeric(df_sem_fil["promedio_horas_turno"], errors="coerce")
df_sem_fil["turnos_registrados"]   = pd.to_numeric(df_sem_fil["turnos_registrados"], errors="coerce")
total_horas    = df_sem_fil["total_horas"].sum()
promedio_horas = df_sem_fil["promedio_horas_turno"].mean()
total_turnos   = df_sem_fil["turnos_registrados"].sum()
alertas_n      = len(df_alertas)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f'<div class="kpi-card"><p class="kpi-value">{total_horas:.1f}h</p><p class="kpi-label">Total horas semana</p></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="kpi-card"><p class="kpi-value">{promedio_horas:.1f}h</p><p class="kpi-label">Promedio por turno</p></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="kpi-card"><p class="kpi-value">{total_turnos}</p><p class="kpi-label">Turnos registrados</p></div>', unsafe_allow_html=True)
with c4:
    if alertas_n > 0:
        st.markdown(f'<div class="alert-badge"><p class="alert-value">⚠️ {alertas_n}</p><p class="alert-label">Turnos incompletos</p></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="kpi-card"><p class="kpi-value" style="color:#34d399">✓ 0</p><p class="kpi-label">Alertas</p></div>', unsafe_allow_html=True)

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# GRÁFICO 1 — Barras comparativo de horas por empleado
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="section-title">Horas trabajadas por empleado</p>', unsafe_allow_html=True)

if not df_sem_fil.empty:
    df_bar = df_sem_fil.sort_values("total_horas", ascending=True)
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        y=df_bar["empleado"],
        x=df_bar["total_horas"],
        orientation="h",
        marker=dict(
            color=df_bar["total_horas"],
            colorscale=[[0, "#1e3a5f"], [1, "#4f8ef7"]],
            line=dict(width=0),
        ),
        text=[f"{h:.1f}h" for h in df_bar["total_horas"]],
        textposition="outside",
        textfont=dict(color="#c8cad8", size=12),
        hovertemplate="<b>%{y}</b><br>%{x:.2f} horas<extra></extra>",
    ))
    fig_bar.update_layout(
        **PLOTLY_THEME,
        height=max(250, len(df_bar) * 55),
        margin=dict(l=10, r=60, t=10, b=10),
        xaxis=dict(showgrid=True, gridcolor="#1e2130", zeroline=False,
                   title="Horas trabajadas", title_font_color="#8b8fa8"),
        yaxis=dict(showgrid=False, tickfont=dict(size=12)),
        showlegend=False,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# GRÁFICO 2 — Jornada diaria por empleado (Gantt)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="section-title">Jornada diaria — entrada, salida y ausencias</p>', unsafe_allow_html=True)

if not df_dia_fil.empty:
    def hora_a_decimal(h_str):
        if pd.isna(h_str) or h_str == "None":
            return None
        try:
            partes = str(h_str).split(":")
            return int(partes[0]) + int(partes[1]) / 60
        except:
            return None

    df_gantt = df_dia_fil.copy()
    df_gantt["entrada_dec"] = df_gantt["hora_entrada"].apply(hora_a_decimal)
    df_gantt["salida_dec"]  = df_gantt["hora_salida"].apply(hora_a_decimal)
    df_gantt["duracion"]    = df_gantt["salida_dec"] - df_gantt["entrada_dec"]
    df_gantt["etiqueta"]    = df_gantt["empleado"] + " · " + df_gantt["fecha"].astype(str).str[:10]
    df_gantt = df_gantt.dropna(subset=["entrada_dec", "salida_dec"])

    fig_gantt = go.Figure()

    # Barra base invisible (desde 0 hasta hora de entrada)
    fig_gantt.add_trace(go.Bar(
        name="",
        y=df_gantt["etiqueta"],
        x=df_gantt["entrada_dec"],
        orientation="h",
        marker=dict(color="rgba(0,0,0,0)"),
        hoverinfo="skip",
        showlegend=False,
    ))

    # Horas trabajadas (azul)
    fig_gantt.add_trace(go.Bar(
        name="Horas trabajadas",
        y=df_gantt["etiqueta"],
        x=df_gantt["horas_trabajadas"],
        orientation="h",
        marker=dict(color="#4f8ef7", opacity=0.85),
        hovertemplate="<b>%{y}</b><br>Trabajadas: %{x:.2f}h<extra></extra>",
    ))

    # Horas fuera (rojo)
    fig_gantt.add_trace(go.Bar(
        name="Ausencias",
        y=df_gantt["etiqueta"],
        x=df_gantt["horas_fuera"].fillna(0),
        orientation="h",
        marker=dict(color="#f87171", opacity=0.85),
        hovertemplate="<b>%{y}</b><br>Fuera: %{x:.2f}h<extra></extra>",
    ))

    fig_gantt.update_layout(
        **PLOTLY_THEME,
        barmode="stack",
        height=max(300, len(df_gantt) * 38),
        margin=dict(l=10, r=20, t=10, b=30),
        xaxis=dict(
            showgrid=True, gridcolor="#1e2130",
            title="Hora del día", title_font_color="#8b8fa8",
            tickvals=list(range(6, 24)),
            ticktext=[f"{h:02d}:00" for h in range(6, 24)],
        ),
        yaxis=dict(showgrid=False, tickfont=dict(size=11)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(size=11)),
    )
    st.plotly_chart(fig_gantt, use_container_width=True)
else:
    st.info("No hay turnos completos para mostrar en esta semana.")

# ══════════════════════════════════════════════════════════════════════════════
# TABLA — Detalle de jornada con salidas intermedias
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="section-title">Detalle de jornada por empleado</p>', unsafe_allow_html=True)

if not df_dia_fil.empty:
    # Convertir columnas a numérico
    df_dia_fil["horas_trabajadas"] = pd.to_numeric(df_dia_fil["horas_trabajadas"], errors="coerce")
    df_dia_fil["horas_fuera"]      = pd.to_numeric(df_dia_fil["horas_fuera"], errors="coerce")

    # Armar tabla base
    df_det = df_dia_fil[["empleado", "fecha", "hora_entrada", "hora_salida",
                          "horas_trabajadas", "horas_fuera"]].copy()
    df_det["fecha"] = df_det["fecha"].astype(str).str[:10]
    df_det["jornada_in_situ"] = (df_det["horas_trabajadas"] - df_det["horas_fuera"].fillna(0)).round(2)

    # Agregar salidas intermedias como texto en la misma columna
    if not df_interm.empty:
        df_interm_filt = df_interm[df_interm["empleado"].isin(emp_sel)].copy()
        if "semana" in df_interm_filt.columns:
            df_interm_filt = df_interm_filt[df_interm_filt["semana"].isin(semana_sel)]

        def formatear_salidas(grupo):
            lineas = []
            for _, row in grupo.iterrows():
                salida  = str(row.get("hora_salida_intermedia", ""))[:5]
                reingreso = str(row.get("hora_reentrada", ""))[:5]
                minutos = row.get("minutos_fuera", "")
                lineas.append(f"{salida} → {reingreso} ({minutos} min)")
            return " | ".join(lineas)

        # Construir tabla de salidas intermedias manualmente
        filas_sal = []
        for (emp, fec), grupo in df_interm_filt.groupby(["empleado", "fecha"]):
            lineas = []
            for _, row in grupo.iterrows():
                salida    = str(row.get("hora_salida_intermedia", ""))[:5]
                reingreso = str(row.get("hora_reentrada", ""))[:5]
                minutos   = row.get("minutos_fuera", "")
                lineas.append(f"{salida} - {reingreso} ({minutos} min)")
            filas_sal.append({
                "empleado": emp,
                "fecha": str(fec)[:10],
                "salidas_intermedias": " | ".join(lineas)
            })
        df_sal_agrup = pd.DataFrame(filas_sal)

        if "salidas_intermedias" in df_det.columns:
            df_det = df_det.drop(columns=["salidas_intermedias"])
        if not df_sal_agrup.empty:
            df_det = df_det.merge(df_sal_agrup, on=["empleado", "fecha"], how="left")
        else:
            df_det["salidas_intermedias"] = "-"
    else:
        df_det["salidas_intermedias"] = "-"

    df_det["salidas_intermedias"] = df_det["salidas_intermedias"].fillna("-")

    # Renombrar columnas
    df_det = df_det.rename(columns={
        "empleado":           "Nombre",
        "fecha":              "Fecha",
        "hora_entrada":       "Hora entrada",
        "hora_salida":        "Hora salida",
        "salidas_intermedias":"Salidas intermedias",
        "horas_fuera":        "Duración salida (h)",
        "horas_trabajadas":   "Duración jornada (h)",
        "jornada_in_situ":    "Jornada in situ (h)",
    })

    st.dataframe(
        df_det.style.format({
            "Duración salida (h)":   "{:.2f}",
            "Duración jornada (h)":  "{:.2f}",
            "Jornada in situ (h)":   "{:.2f}",
        }, na_rep="-"),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No hay datos de jornada para mostrar.")

# ══════════════════════════════════════════════════════════════════════════════
# GRÁFICO 3 — Evolución histórica semanal
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="section-title">Evolución histórica de horas semanales</p>', unsafe_allow_html=True)

df_hist = df_semanal[df_semanal["empleado"].isin(emp_sel)]
if not df_hist.empty and df_hist["semana"].nunique() > 1:
    df_hist_grp = df_hist.groupby(["semana", "empleado"])["total_horas"].sum().reset_index()
    fig_line = px.line(
        df_hist_grp,
        x="semana", y="total_horas", color="empleado",
        markers=True,
        labels={"semana": "Semana", "total_horas": "Horas totales", "empleado": "Empleado"},
    )
    fig_line.update_traces(line=dict(width=2.5), marker=dict(size=8))
    fig_line.update_layout(
        **PLOTLY_THEME,
        height=350,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, title_font_color="#8b8fa8"),
        yaxis=dict(showgrid=True, gridcolor="#1e2130", title_font_color="#8b8fa8"),
        legend=dict(font=dict(size=11)),
        hovermode="x unified",
    )
    st.plotly_chart(fig_line, use_container_width=True)
else:
    st.info("El gráfico histórico aparecerá cuando tengas más de una semana procesada.")

# ══════════════════════════════════════════════════════════════════════════════
# TABLA — Resumen semanal
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="section-title">Resumen semanal por empleado</p>', unsafe_allow_html=True)

if not df_sem_fil.empty:
    cols_mostrar = {
        "empleado":            "Empleado",
        "turnos_registrados":  "Turnos",
        "total_horas":         "Horas totales",
        "promedio_horas_turno":"Promedio/turno",
        "total_horas_fuera":   "Horas fuera",
        "total_salidas_interm":"Salidas interm.",
    }
    df_tabla = df_sem_fil[list(cols_mostrar.keys())].rename(columns=cols_mostrar).copy()
    for col in ["Horas totales", "Promedio/turno", "Horas fuera"]:
        df_tabla[col] = pd.to_numeric(df_tabla[col], errors="coerce")
    st.dataframe(
        df_tabla.style
            .format({"Horas totales": "{:.2f}", "Promedio/turno": "{:.2f}", "Horas fuera": "{:.2f}"}, na_rep="-")
            .background_gradient(subset=["Horas totales"], cmap="Blues"),
        use_container_width=True,
        hide_index=True,
    )

# ══════════════════════════════════════════════════════════════════════════════
# ALERTAS
# ══════════════════════════════════════════════════════════════════════════════
if not df_alertas.empty:
    st.markdown('<p class="section-title">⚠️ Turnos con datos incompletos</p>', unsafe_allow_html=True)
    sin_sal = df_alertas[df_alertas["sin_salida"] == 1][["empleado", "fecha", "hora_entrada"]]
    sin_ent = df_alertas[df_alertas["sin_entrada"] == 1][["empleado", "fecha", "hora_salida"]]

    if not sin_sal.empty:
        st.warning(f"**{len(sin_sal)} turno(s) sin salida registrada**")
        st.dataframe(sin_sal, use_container_width=True, hide_index=True)
    if not sin_ent.empty:
        st.warning(f"**{len(sin_ent)} turno(s) sin entrada registrada**")
        st.dataframe(sin_ent, use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("Portal de Asistencia · Datos actualizados semanalmente")
