import streamlit as st
import pandas as pd
from github import Github
from io import StringIO
import time

# --- 1. CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="Objetivos 2026", layout="wide")
st.title("🎯 Matriz de Objetivos 2026 (Sistema Blindado)")

# Recuperar configuración de los Secrets de Streamlit
TOKEN = st.secrets["GITHUB_TOKEN"]
REPO_NAME = st.secrets["REPO_NAME"]
FILE_NAME = "objetivos.csv"

# Conectar con la API de GitHub
g = Github(TOKEN)
repo = g.get_repo(REPO_NAME)

# --- CONFIGURACIÓN FIJA ---
FILAS_DEPARTAMENTOS = ["Control de Producción", "Procesos Logísticos", "Equipo de Planificación"]
COLUMNAS_ACCIONES = ["AUTOMATISTAS", "CREAR", "MIGRAR", "MODIFICAR"]

OPCIONES_ZONAS = ["Reparto doblado", "reparto colgado", "recepciones", "expediciones", "b2c"]
OPCIONES_PROVEEDORES = ["TGW", "PSB", "Infios", "Ferag"]
OPCIONES_GT = ["GT1", "GT2", "GT3", "GT4", "GT5"]

# --- 2. FUNCIONES DE BASE DE DATOS (REPARADAS) ---

def load_data_from_github():
    """Descarga la matriz y su SHA actualizado."""
    try:
        content = repo.get_contents(FILE_NAME)
        decoded_data = content.decoded_content.decode('utf-8')
        df = pd.read_csv(StringIO(decoded_data))
        
        # Forzar estructura fija
        df = df.set_index("AUTOMATISTAS").reindex(FILAS_DEPARTAMENTOS).reset_index()
        for col in ["CREAR", "MIGRAR", "MODIFICAR"]:
            if col not in df.columns:
                df[col] = ""
        
        return df[COLUMNAS_ACCIONES].fillna(""), content.sha
    except:
        df_inicial = pd.DataFrame({
            "AUTOMATISTAS": FILAS_DEPARTAMENTOS,
            "CREAR": ["", "", ""],
            "MIGRAR": ["", "", ""],
            "MODIFICAR": ["", "", ""]
        })
        return df_inicial, None

def save_data_to_github(df):
    """Obtiene el SHA actual justo antes de guardar para evitar errores de validación."""
    csv_string = df.to_csv(index=False)
    try:
        # Intentamos obtener el archivo actual para tener el SHA más reciente
        try:
            current_file = repo.get_contents(FILE_NAME)
            current_sha = current_file.sha
            repo.update_file(FILE_NAME, "Actualización de Matriz", csv_string, current_sha)
        except:
            # Si el archivo no existe en absoluto
            repo.create_file(FILE_NAME, "Creación de Matriz", csv_string)
        return True
    except Exception as e:
        st.error(f"Error crítico al guardar: {e}")
        return False

# --- 3. LÓGICA DE SESIÓN ---
if "df" not in st.session_state:
    df_git, _ = load_data_from_github()
    st.session_state.df = df_git

# --- 4. BARRA LATERAL (FILTROS) ---
st.sidebar.title("🔍 Filtros")
f_auto = st.sidebar.multiselect("Departamento (Filas):", options=FILAS_DEPARTAMENTOS)
f_gt = st.sidebar.multiselect("Grupo de Trabajo:", options=OPCIONES_GT)
f_prov = st.sidebar.multiselect("Proveedor:", options=OPCIONES_PROVEEDORES)
f_zona = st.sidebar.multiselect("Zona:", options=OPCIONES_ZONAS)

def filtrar_bloques_celda(texto_celda, filtro_gt, filtro_prov, filtro_zona):
    if pd.isna(texto_celda) or not str(texto_celda).strip():
        return ""
    bloques = str(texto_celda).split("\n\n")
    bloques_validos = []
    for b in bloques:
        lineas = [l.strip() for l in b.split("\n") if l.strip()]
        if len(lineas) >= 4:
            match_gt = not filtro_gt or lineas[1] in filtro_gt
            match_prov = not filtro_prov or lineas[2] in filtro_prov
            match_zona = not filtro_zona or lineas[3] in filtro_zona
            if match_gt and match_prov and match_zona:
                bloques_validos.append(b)
        elif not filtro_gt and not filtro_prov and not filtro_zona:
            bloques_validos.append(b)
    return "\n\n".join(bloques_validos)

df_display = st.session_state.df.copy()
if f_auto:
    df_display = df_display[df_display["AUTOMATISTAS"].isin(f_auto)]
if f_gt or f_prov or f_zona:
    for col in ["CREAR", "MIGRAR", "MODIFICAR"]:
        df_display[col] = df_display[col].apply(lambda x: filtrar_bloques_celda(x, f_gt, f_prov, f_zona))

# --- 5. PESTAÑAS ---
tab1, tab2 = st.tabs(["📊 Matriz de Trabajo", "➕ Inyectar Objetivo"])

with tab1:
    st.subheader("Cuadro de Mandos")
    filtros_activos = bool(f_auto or f_gt or f_prov or f_zona)
    if filtros_activos:
        st.warning("⚠️ Modo Lectura (Filtros activos)")
    
    edited_df = st.data_editor(df_display, use_container_width=True, disabled=filtros_activos)
    
    if not filtros_activos and st.button("💾 Guardar Cambios Manuales"):
        with st.spinner("Sincronizando..."):
            st.session_state.df.update(edited_df)
            if save_data_to_github(st.session_state.df):
                st.success("¡Guardado!")
                time.sleep(1)
                st.rerun()

with tab2:
    st.subheader("Inyector de Objetivos")
    with st.form("inyector_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nombre_obj = st.text_input("Nombre del Objetivo:")
            accion_col = st.radio("Acción:", options=["CREAR", "MIGRAR", "MODIFICAR"], horizontal=True)
            depto_fila = st.selectbox("Departamento:", options=FILAS_DEPARTAMENTOS)
        with col2:
            gt_val = st.selectbox("GT:", options=OPCIONES_GT)
            prov_val = st.selectbox("Proveedor:", options=OPCIONES_PROVEEDORES)
            zona_val = st.selectbox("Zona:", options=OPCIONES_ZONAS)
            
        if st.form_submit_button("Inyectar Objetivo 🚀"):
            if nombre_obj:
                bloque = f"{nombre_obj.upper()}\n{gt_val}\n{prov_val}\n{zona_val}"
                idx = st.session_state.df[st.session_state.df["AUTOMATISTAS"] == depto_fila].index[0]
                actual = st.session_state.df.at[idx, accion_col]
                st.session_state.df.at[idx, accion_col] = f"{actual}\n\n{bloque}".strip()
                
                if save_data_to_github(st.session_state.df):
                    st.success("¡Objetivo inyectado!")
                    time.sleep(1)
                    st.rerun()
