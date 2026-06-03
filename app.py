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

# Columnas estrictamente obligatorias
COLUMNAS_REQUERIDAS = ["OBJETIVOS", "CREAR", "MIGRAR", "MODIFICAR", "AUTOMATISTAS", "PROVEEDORES EXTERNOS", "ZONAS/SECCIONES"]

# --- LISTAS DE OPCIONES FIJAS ---
OPCIONES_AUTOMATISTAS = ["Control de Producción", "Procesos Logísticos", "Equipo de Planificación"]
OPCIONES_ZONAS = ["Reparto doblado", "reparto colgado", "recepciones", "expediciones", "b2c"]
OPCIONES_PROVEEDORES = ["TGp", "thve", "etdf", "etc"]
CATEGORIAS_ACCION = ["CREAR", "MIGRAR", "MODIFICAR"]

# --- 2. FUNCIONES DE BASE DE DATOS (GITHUB) ---

def load_data_from_github():
    try:
        content = repo.get_contents(FILE_NAME)
        decoded_data = content.decoded_content.decode('utf-8')
        df = pd.read_csv(StringIO(decoded_data))
        for col in COLUMNAS_REQUERIDAS:
            if col not in df.columns:
                df[col] = ""
        return df, content.sha
    except:
        df_inicial = pd.DataFrame({
            "OBJETIVOS": ["PROCESOS LOGISTICOS", "CONTROL DE PRODUCCIÓN", "EQUIPO DE PLANIFICACIÓN"],
            "CREAR": ["", "", ""], "MIGRAR": ["", "", ""], "MODIFICAR": ["", "", ""],
            "AUTOMATISTAS": ["", "", ""], "PROVEEDORES EXTERNOS": ["", "", ""], "ZONAS/SECCIONES": ["", "", ""]
        })
        return df_inicial, None

def save_data_to_github(df, sha):
    csv_string = df.to_csv(index=False)
    try:
        if sha:
            repo.update_file(FILE_NAME, "Actualización desde App Streamlit", csv_string, sha)
        else:
            repo.create_file(FILE_NAME, "Creación inicial desde App Streamlit", csv_string)
        return True
    except Exception as e:
        st.error(f"Error al guardar en GitHub: {e}")
        return False

# --- 3. LÓGICA DE LA APLICACIÓN ---

if "df" not in st.session_state:
    df_git, sha_git = load_data_from_github()
    st.session_state.df = df_git
    st.session_state.sha = sha_git

# --- 4. SIDEBAR (FILTROS) ---
st.sidebar.title("🔍 Filtros")
filtro_auto = st.sidebar.multiselect("Automatistas:", options=OPCIONES_AUTOMATISTAS)
filtro_prov = st.sidebar.multiselect("Proveedores Externos:", options=OPCIONES_PROVEEDORES)
filtro_zona = st.sidebar.multiselect("Zonas / Secciones:", options=OPCIONES_ZONAS)

df_filtrado = st.session_state.df.copy()
if filtro_auto:
    df_filtrado = df_filtrado[df_filtrado["AUTOMATISTAS"].astype(str).str.strip().isin(filtro_auto)]
if filtro_prov:
    df_filtrado = df_filtrado[df_filtrado["PROVEEDORES EXTERNOS"].astype(str).str.strip().isin(filtro_prov)]
if filtro_zona:
    df_filtrado = df_filtrado[df_filtrado["ZONAS/SECCIONES"].astype(str).str.strip().isin(filtro_zona)]

# --- 5. PESTAÑAS ---
tab1, tab2 = st.tabs(["📊 Ver / Editar Matriz", "➕ Añadir Nuevo Objetivo"])

with tab1:
    st.subheader("Matriz de Trabajo")
    edited_df = st.data_editor(df_filtrado, use_container_width=True, key="main_editor")
    
    if st.button("💾 Guardar Cambios en GitHub"):
        with st.spinner("Sincronizando..."):
            st.session_state.df.loc[edited_df.index, edited_df.columns] = edited_df
            if save_data_to_github(st.session_state.df, st.session_state.sha):
                st.success("¡Guardado!")
                df_git, sha_git = load_data_from_github()
                st.session_state.df, st.session_state.sha = df_git, sha_git
                time.sleep(1)
                st.rerun()

with tab2:
    st.subheader("Añadir nueva fila")
    with st.form("nuevo_objetivo_form", clear_on_submit=True):
        nuevo_obj = st.text_input("Nombre del Objetivo:")
        
        # AQUÍ ESTÁ EL CAMBIO: Selector único para elegir solo una categoría
        categoria_elegida = st.radio("Selecciona el tipo de acción (Categoría):", options=CATEGORIAS_ACCION, horizontal=True)
        detalle_texto = st.text_area(f"Escribe aquí el detalle para {categoria_elegida}:")
        
        st.write("---")
        auto_val = st.selectbox("Automatista:", options=[""] + OPCIONES_AUTOMATISTAS)
        prov_val = st.selectbox("Proveedor:", options=[""] + OPCIONES_PROVEEDORES)
        zona_val = st.selectbox("Zona / Sección:", options=[""] + OPCIONES_ZONAS)
        
        if st.form_submit_button("Añadir Objetivo 🚀"):
            if nuevo_obj and detalle_texto:
                # Preparamos la fila. Ponemos vacío en las 3 categorías y luego llenamos solo la elegida
                nueva_fila_dict = {
                    "OBJETIVOS": nuevo_obj.upper(),
                    "CREAR": "", "MIGRAR": "", "MODIFICAR": "",
                    "AUTOMATISTAS": auto_val,
                    "PROVEEDORES EXTERNOS": prov_val,
                    "ZONAS/SECCIONES": zona_val
                }
                # Asignamos el texto solo a la columna elegida en el Radio Button
                nueva_fila_dict[categoria_elegida] = detalle_texto
                
                nueva_fila = pd.DataFrame([nueva_fila_dict])
                st.session_state.df = pd.concat([st.session_state.df, nueva_fila], ignore_index=True)
                
                with st.spinner("Guardando..."):
                    save_data_to_github(st.session_state.df, st.session_state.sha)
                    _, sha_git = load_data_from_github()
                    st.session_state.sha = sha_git
                    st.success("¡Añadido correctamente!")
                    time.sleep(1)
                    st.rerun()
            else:
                st.error("Por favor, rellena el nombre y el detalle.")
