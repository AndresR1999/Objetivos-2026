import streamlit as st
import pandas as pd
from github import Github
from io import StringIO
import time

# --- 1. CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="Objetivos 2026", layout="wide")
st.title("🎯 Matriz de Objetivos 2026 (Modo Panel Fijo)")

# Recuperar configuración de los Secrets de Streamlit
TOKEN = st.secrets["GITHUB_TOKEN"]
REPO_NAME = st.secrets["REPO_NAME"]
FILE_NAME = "objetivos.csv"

# Conectar con la API de GitHub
g = Github(TOKEN)
repo = g.get_repo(REPO_NAME)

# --- DEFINICIÓN DE FILAS Y COLUMNAS FIJAS SOLICITADAS ---
FILAS_DEPARTAMENTOS = ["Control de Producción", "Procesos Logísticos", "Equipo de Planificación"]
COLUMNAS_ACCIONES = ["AUTOMATISTAS", "CREAR", "MIGRAR", "MODIFICAR"]

# Opciones fijas para los selectores y filtros
OPCIONES_ZONAS = ["Reparto doblado", "reparto colgado", "recepciones", "expediciones", "b2c"]
OPCIONES_PROVEEDORES = ["TGW", "TGp", "thve", "etdf", "etc"]
OPCIONES_GT = ["GT1", "GT2", "GT3", "GT4", "GT5"]

# --- 2. FUNCIONES DE BASE DE DATOS (GITHUB) ---

def load_data_from_github():
    """Descarga la matriz. Si el archivo no cumple el formato fijo de 3x3, lo inicializa correctamente."""
    try:
        content = repo.get_contents(FILE_NAME)
        decoded_data = content.decoded_content.decode('utf-8')
        df = pd.read_csv(StringIO(decoded_data))
        
        # Validar que la columna base exista
        if "AUTOMATISTAS" not in df.columns:
            raise Exception("Formato antiguo detectado, reestructurando...")
            
        # Forzar el orden estricto de filas y columnas solicitado
        df = df.set_index("AUTOMATISTAS").reindex(FILAS_DEPARTAMENTOS).reset_index()
        for col in ["CREAR", "MIGRAR", "MODIFICAR"]:
            if col not in df.columns:
                df[col] = ""
        
        return df[COLUMNAS_ACCIONES].fillna(""), content.sha
    except:
        # Inicialización de la matriz limpia de 3x3 tal como exige la imagen
        df_inicial = pd.DataFrame({
            "AUTOMATISTAS": FILAS_DEPARTAMENTOS,
            "CREAR": ["", "", ""],
            "MIGRAR": ["", "", ""],
            "MODIFICAR": ["", "", ""]
        })
        return df_inicial, None

def save_data_to_github(df, sha):
    """Sube los cambios de la matriz a GitHub."""
    csv_string = df.to_csv(index=False)
    try:
        if sha:
            repo.update_file(FILE_NAME, "Actualización de Matriz Fija", csv_string, sha)
        else:
            repo.create_file(FILE_NAME, "Inicialización de Matriz Fija", csv_string)
        return True
    except Exception as e:
        st.error(f"Error al guardar en GitHub: {e}")
        return False

# --- 3. LOGICA DE SESIÓN ---
if "df" not in st.session_state:
    df_git, sha_git = load_data_from_github()
    st.session_state.df = df_git
    st.session_state.sha = sha_git

# --- 4. BARRA LATERAL (FILTROS DE BLOQUES INTERNOS) ---
st.sidebar.title("🔍 Filtros Globales")
st.sidebar.write("Filtra los objetivos visibles dentro de las celdas:")

f_auto = st.sidebar.multiselect("Filtrar por Departamento (Filas):", options=FILAS_DEPARTAMENTOS)
f_gt = st.sidebar.multiselect("Filtrar por Grupo de Trabajo:", options=OPCIONES_GT)
f_prov = st.sidebar.multiselect("Filtrar por Proveedor:", options=OPCIONES_PROVEEDORES)
f_zona = st.sidebar.multiselect("Filtrar por Zona:", options=OPCIONES_ZONAS)

# --- FUNCIÓN DE FILTRADO DE CONTENIDO DE CELDA ---
def filtrar_bloques_celda(texto_celda, filtro_gt, filtro_prov, filtro_zona):
    if pd.isna(texto_celda) or not str(texto_celda).strip():
        return ""
    
    # Cada objetivo dentro de la celda está separado por un doble salto de línea
    bloques = str(texto_celda).split("\n\n")
    bloques_validos = []
    
    for b in bloques:
        lineas = [l.strip() for l in b.split("\n") if l.strip()]
        if len(lineas) >= 4:
            # Estructura del bloque: 0=Nombre, 1=GT, 2=Proveedor, 3=Zona
            b_gt = lineas[1]
            b_prov = lineas[2]
            b_zona = lineas[3]
            
            # Comprobar si cumple los criterios seleccionados
            match_gt = not filtro_gt or b_gt in filtro_gt
            match_prov = not filtro_prov or b_prov in filtro_prov
            match_zona = not filtro_zona or b_zona in filtro_zona
            
            if match_gt and match_prov and match_zona:
                bloques_validos.append(b)
        else:
            # Si la celda contiene texto libre modificado a mano, se conserva si no hay filtros activos
            if not filtro_gt and not filtro_prov and not filtro_zona:
                bloques_validos.append(b)
                
    return "\n\n".join(bloques_validos)

# Aplicar filtros a la visualización de la matriz
df_display = st.session_state.df.copy()

if f_auto:
    df_display = df_display[df_display["AUTOMATISTAS"].isin(f_auto)]

if f_gt or f_prov or f_zona:
    for accion_col in ["CREAR", "MIGRAR", "MODIFICAR"]:
        df_display[accion_col] = df_display[accion_col].apply(
            lambda x: filtrar_bloques_celda(x, f_gt, f_prov, f_zona)
        )

# --- 5. PESTAÑAS PRINCIPALES ---
tab1, tab2 = st.tabs(["📊 Matriz de Trabajo", "➕ Inyectar Objetivo en Celda"])

# --- TAB 1: VISUALIZACIÓN DE LA MATRIZ ---
with tab1:
    st.subheader("Cuadro de Mandos Operativo")
    
    # Bloqueo de edición directa en celdas si hay filtros puestos para evitar sobreescrituras accidentales
    filtros_activos = bool(f_auto or f_gt or f_prov or f_zona)
    if filtros_activos:
        st.warning("⚠️ Modo Lectura activado por Filtros. Limpia los filtros de la barra lateral para editar el texto directamente.")
    else:
        st.info("Puedes hacer doble clic en cualquier celda para modificar o reordenar el texto a mano.")
        
    # Editor interactivo
    edited_df = st.data_editor(
        df_display, 
        use_container_width=True, 
        disabled=filtros_activos,
        key="matriz_fija_editor"
    )
    
    if not filtros_activos:
        if st.button("💾 Guardar Cambios Manuales"):
            with st.spinner("Sincronizando matriz..."):
                st.session_state.df.update(edited_df)
                if save_data_to_github(st.session_state.df, st.session_state.sha):
                    st.success("¡Matriz actualizada en GitHub!")
                    df_git, sha_git = load_data_from_github()
                    st.session_state.df, st.session_state.sha = df_git, sha_git
                    time.sleep(1)
                    st.rerun()

# --- TAB 2: INYECTOR DE OBJETIVOS EN CELDAS ---
with tab2:
    st.subheader("Formulario de Clasificación de Objetivos")
    with st.form("inyector_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            nombre_obj = st.text_input("Nombre del Objetivo (ej. HOLA):")
            accion_col = st.radio("Columna de la Matriz (Acción):", options=["CREAR", "MIGRAR", "MODIFICAR"], horizontal=True)
            depto_fila = st.selectbox("Fila de la Matriz (Departamento):", options=FILAS_DEPARTAMENTOS)
        
        with col2:
            gt_val = st.selectbox("Grupo de Trabajo (GT):", options=OPCIONES_GT)
            prov_val = st.selectbox("Proveedor Externo:", options=OPCIONES_PROVEEDORES)
            zona_val = st.selectbox("Zona / Sección:", options=OPCIONES_ZONAS)
            
        embed_button = st.form_submit_button("Inyectar Objetivo en la Celda 🚀")
        
        if embed_button:
            if nombre_obj and depto_fila and accion_col and gt_val and prov_val and zona_val:
                # Construcción del bloque de texto exacto solicitado por el usuario
                bloque_objetivo = f"{nombre_obj.upper()}\n{gt_val}\n{prov_val}\n{zona_val}"
                
                # Buscar las coordenadas en nuestro DataFrame de sesión
                idx_fila = st.session_state.df[st.session_state.df["AUTOMATISTAS"] == depto_fila].index[0]
                valor_celda_actual = st.session_state.df.at[idx_fila, accion_col]
                
                # Si la celda ya tiene un objetivo anterior, acumulamos respetando saltos de línea largos
                if str(valor_celda_actual).strip():
                    nuevo_valor_celda = f"{valor_celda_actual}\n\n{bloque_objetivo}"
                else:
                    nuevo_valor_celda = bloque_objetivo
                
                # Actualizar celda en memoria
                st.session_state.df.at[idx_fila, accion_col] = nuevo_valor_celda
                
                # Guardar el estado completo en GitHub
                with st.spinner("Guardando en base de datos..."):
                    if save_data_to_github(st.session_state.df, st.session_state.sha):
                        st.success(f"¡Objetivo '{nombre_obj.upper()}' incrustado con éxito en {depto_fila} ➔ {accion_col}!")
                        df_git, sha_git = load_data_from_github()
                        st.session_state.df, st.session_state.sha = df_git, sha_git
                        time.sleep(1)
                        st.rerun()
            else:
                st.error("Todos los campos del formulario son obligatorios para construir el bloque.")
