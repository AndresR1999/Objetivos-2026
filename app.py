import streamlit as st
import pandas as pd
from github import Github
from io import StringIO
import time

# --- 1. CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="Objetivos 2026", layout="wide")
st.title("🎯 Matriz de Objetivos (Sincronizada con GitHub)")

# Recuperar configuración de los Secrets de Streamlit
TOKEN = st.secrets["GITHUB_TOKEN"]
REPO_NAME = st.secrets["REPO_NAME"]
FILE_NAME = "objetivos.csv"

# Conectar con la API de GitHub
g = Github(TOKEN)
repo = g.get_repo(REPO_NAME)

# --- 2. FUNCIONES DE BASE DE DATOS (GITHUB) ---

def load_data_from_github():
    """Descarga el CSV desde GitHub. Si no existe, crea uno por defecto."""
    try:
        content = repo.get_contents(FILE_NAME)
        decoded_data = content.decoded_content.decode('utf-8')
        df = pd.read_csv(StringIO(decoded_data))
        return df, content.sha
    except:
        # Si el archivo no existe, creamos el formato inicial de tu imagen
        df_inicial = pd.DataFrame({
            "OBJETIVOS": ["PROCESOS LOGISTICOS", "CONTROL DE PRODUCCIÓN", "EQUIPO DE PLANIFICACIÓN"],
            "CREAR": ["", "", ""],
            "MIGRAR": ["", "", ""],
            "MODIFICAR": ["", "", ""]
        })
        return df_inicial, None

def save_data_to_github(df, sha):
    """Convierte el DataFrame a CSV y lo sube a GitHub."""
    csv_string = df.to_csv(index=False)
    try:
        if sha: # Si el archivo ya existe, lo actualiza
            repo.update_file(FILE_NAME, "Actualización desde App Streamlit", csv_string, sha)
        else: # Si el archivo no existe, lo crea
            repo.create_file(FILE_NAME, "Creación inicial desde App Streamlit", csv_string)
        return True
    except Exception as e:
        st.error(f"Error al guardar en GitHub: {e}")
        return False

# --- 3. LÓGICA DE LA APLICACIÓN ---

# Cargar datos al iniciar la sesión
if "df" not in st.session_state:
    df_git, sha_git = load_data_from_github()
    st.session_state.df = df_git
    st.session_state.sha = sha_git

tab1, tab2 = st.tabs(["📊 Ver / Editar Matriz", "➕ Añadir Nuevo Objetivo"])

# --- TAB 1: VISUALIZACIÓN Y EDICIÓN ---
with tab1:
    st.subheader("Matriz de Trabajo")
    st.info("Cualquier cambio que hagas aquí se guardará permanentemente en tu GitHub.")
    
    # Editor de tabla interactivo
    edited_df = st.data_editor(
        st.session_state.df, 
        use_container_width=True, 
        num_rows="dynamic",
        key="main_editor"
    )
    
    if st.button("💾 Guardar Cambios en GitHub"):
        with st.spinner("Sincronizando con GitHub..."):
            success = save_data_to_github(edited_df, st.session_state.sha)
            if success:
                st.success("¡Datos guardados correctamente en objetivos.csv!")
                # Recargar datos para actualizar el SHA
                df_git, sha_git = load_data_from_github()
                st.session_state.df = df_git
                st.session_state.sha = sha_git
                time.sleep(1)
                st.rerun()

# --- TAB 2: AÑADIR NUEVO OBJETIVO ---
with tab2:
    st.subheader("Añadir una nueva fila")
    with st.form("nuevo_objetivo_form", clear_on_submit=True):
        nuevo_obj = st.text_input("Nombre del Objetivo:")
        c = st.text_input("Crear:")
        m = st.text_input("Migrar:")
        mod = st.text_input("Modificar:")
        
        if st.form_submit_button("Añadir a la matriz"):
            if nuevo_obj:
                # Crear nueva fila y añadirla al dataframe de la sesión
                nueva_fila = pd.DataFrame([{"OBJETIVOS": nuevo_obj.upper(), "CREAR": c, "MIGRAR": m, "MODIFICAR": mod}])
                st.session_state.df = pd.concat([st.session_state.df, nueva_fila], ignore_index=True)
                
                # Guardar automáticamente
                with st.spinner("Guardando nueva fila..."):
                    save_data_to_github(st.session_state.df, st.session_state.sha)
                    # Actualizar SHA
                    _, sha_git = load_data_from_github()
                    st.session_state.sha = sha_git
                    st.success(f"Objetivo '{nuevo_obj}' añadido y sincronizado.")
                    time.sleep(1)
                    st.rerun()
            else:
                st.error("El nombre del objetivo es obligatorio.")
