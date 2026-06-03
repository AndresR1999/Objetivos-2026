import streamlit as st
import pandas as pd
from github import Github
from io import StringIO
import time

# --- 1. CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="Objetivos 2026", layout="wide")
st.title("🎯 Gestión de Objetivos 2026")

# Recuperar configuración de los Secrets de Streamlit
TOKEN = st.secrets["GITHUB_TOKEN"]
REPO_NAME = st.secrets["REPO_NAME"]
FILE_NAME = "objetivos.csv"

# Conectar con la API de GitHub
g = Github(TOKEN)
repo = g.get_repo(REPO_NAME)

# Columnas requeridas actualizadas
COLUMNAS_REQUERIDAS = [
    "OBJETIVOS", "CREAR", "MIGRAR", "MODIFICAR", 
    "AUTOMATISTAS", "GRUPO DE TRABAJO", "PROVEEDORES EXTERNOS", "ZONAS/SECCIONES"
]

# --- LISTAS DE OPCIONES FIJAS ---
OPCIONES_AUTOMATISTAS = ["Control de Producción", "Procesos Logísticos", "Equipo de Planificación"]
OPCIONES_ZONAS = ["Reparto doblado", "reparto colgado", "recepciones", "expediciones", "b2c"]
OPCIONES_PROVEEDORES = ["TGp", "thve", "etdf", "etc"]
OPCIONES_GT = ["GT1", "GT2", "GT3", "GT4", "GT5"]
CATEGORIAS_ACCION = ["CREAR", "MIGRAR", "MODIFICAR"]

# --- 2. FUNCIONES DE BASE DE DATOS (GITHUB) ---

def load_data_from_github():
    try:
        content = repo.get_contents(FILE_NAME)
        decoded_data = content.decoded_content.decode('utf-8')
        df = pd.read_csv(StringIO(decoded_data))
        # Verificar y añadir columnas faltantes (como GRUPO DE TRABAJO)
        for col in COLUMNAS_REQUERIDAS:
            if col not in df.columns:
                df[col] = ""
        return df, content.sha
    except:
        # Plantilla inicial si no existe el archivo
        df_inicial = pd.DataFrame(columns=COLUMNAS_REQUERIDAS)
        # Añadimos los 3 ejemplos base
        ejemplos = ["PROCESOS LOGISTICOS", "CONTROL DE PRODUCCIÓN", "EQUIPO DE PLANIFICACIÓN"]
        for ej in ejemplos:
            df_inicial = pd.concat([df_inicial, pd.DataFrame([{"OBJETIVOS": ej}])], ignore_index=True)
        df_inicial = df_inicial.fillna("")
        return df_inicial, None

def save_data_to_github(df, sha):
    csv_string = df.to_csv(index=False)
    try:
        if sha:
            repo.update_file(FILE_NAME, "Update via App", csv_string, sha)
        else:
            repo.create_file(FILE_NAME, "Initial creation", csv_string)
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False

# --- 3. LÓGICA DE CARGA ---
if "df" not in st.session_state:
    df_git, sha_git = load_data_from_github()
    st.session_state.df = df_git
    st.session_state.sha = sha_git

# --- 4. SIDEBAR (FILTROS) ---
st.sidebar.title("🔍 Filtros de Búsqueda")
f_gt = st.sidebar.multiselect("Grupo de Trabajo:", options=OPCIONES_GT)
f_auto = st.sidebar.multiselect("Automatistas:", options=OPCIONES_AUTOMATISTAS)
f_prov = st.sidebar.multiselect("Proveedores:", options=OPCIONES_PROVEEDORES)
f_zona = st.sidebar.multiselect("Zonas:", options=OPCIONES_ZONAS)

# Aplicar filtros
df_display = st.session_state.df.copy()
if f_gt:
    df_display = df_display[df_display["GRUPO DE TRABAJO"].isin(f_gt)]
if f_auto:
    df_display = df_display[df_display["AUTOMATISTAS"].isin(f_auto)]
if f_prov:
    df_display = df_display[df_display["PROVEEDORES EXTERNOS"].isin(f_prov)]
if f_zona:
    df_display = df_display[df_display["ZONAS/SECCIONES"].isin(f_zona)]

# --- 5. PESTAÑAS ---
tab1, tab2 = st.tabs(["📊 Matriz de Objetivos", "➕ Nuevo Objetivo"])

with tab1:
    st.subheader("Visualización y Edición Rápida")
    # Editor interactivo
    edited_df = st.data_editor(df_display, use_container_width=True, key="editor_v3")
    
    if st.button("💾 Guardar Cambios"):
        with st.spinner("Sincronizando con GitHub..."):
            # Actualizar los cambios en el dataframe original
            st.session_state.df.update(edited_df)
            # Si hay filas nuevas o borradas en la vista filtrada (aunque es complejo), esto lo asegura:
            st.session_state.df.loc[edited_df.index] = edited_df
            
            if save_data_to_github(st.session_state.df, st.session_state.sha):
                st.success("¡Sincronizado!")
                time.sleep(1)
                st.rerun()

with tab2:
    st.subheader("Crear Nuevo Objetivo")
    with st.form("form_limpio", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            nombre = st.text_input("Nombre del Objetivo:").upper()
            accion = st.radio("Acción a realizar:", options=CATEGORIAS_ACCION, horizontal=True)
            gt_val = st.selectbox("Asignar Grupo de Trabajo:", options=[""] + OPCIONES_GT)
        
        with col2:
            auto_val = st.selectbox("Automatista:", options=[""] + OPCIONES_AUTOMATISTAS)
            zona_val = st.selectbox("Zona:", options=[""] + OPCIONES_ZONAS)
            prov_val = st.selectbox("Proveedor:", options=[""] + OPCIONES_PROVEEDORES)
        
        enviar = st.form_submit_button("Añadir a la Matriz 🚀")
        
        if enviar:
            if nombre:
                # Crear fila con la "X" en la columna seleccionada
                nueva_fila = {col: "" for col in COLUMNAS_REQUERIDAS}
                nueva_fila["OBJETIVOS"] = nombre
                nueva_fila[accion] = "X"  # Marcamos con X la categoría elegida
                nueva_fila["GRUPO DE TRABAJO"] = gt_val
                nueva_fila["AUTOMATISTAS"] = auto_val
                nueva_fila["ZONAS/SECCIONES"] = zona_val
                nueva_fila["PROVEEDORES EXTERNOS"] = prov_val
                
                # Unir al dataframe
                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nueva_fila])], ignore_index=True)
                
                # Guardar
                if save_data_to_github(st.session_state.df, st.session_state.sha):
                    st.success(f"Objetivo {nombre} añadido correctamente.")
                    time.sleep(1)
                    st.rerun()
            else:
                st.error("Debes poner un nombre al objetivo.")
