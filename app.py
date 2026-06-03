import streamlit as st
import pandas as pd
from github import Github
from io import StringIO
import time

# --- 1. CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="Objetivos 2026", layout="wide")
st.title("🎯 Matriz de Objetivos 2026")

# Recuperar configuración de los Secrets de Streamlit
TOKEN = st.secrets["GITHUB_TOKEN"]
REPO_NAME = st.secrets["REPO_NAME"]
FILE_NAME = "objetivos.csv"

# Conectar con la API de GitHub
g = Github(TOKEN)
repo = g.get_repo(REPO_NAME)

# --- CONFIGURACIÓN DE FILAS Y COLUMNAS ---
FILAS_DEPARTAMENTOS = ["Control de Producción", "Procesos Logísticos", "Equipo de Planificación"]
COLUMNAS_ACCIONES = ["AUTOMATISTAS", "CREAR", "MIGRAR", "MODIFICAR"]

# Opciones para los filtros y el formulario
OPCIONES_GT = ["GT1", "GT2", "GT3", "GT4", "GT5"]
OPCIONES_PROVEEDORES = ["TGW", "PSB", "Infios", "Ferag", "Fives"]
OPCIONES_ZONAS = ["Reparto doblado", "Reparto Colgado", "Recepción", "Expediciones", "B2C"]

# --- 2. FUNCIONES DE BASE DE DATOS ---

def load_data_from_github():
    try:
        content = repo.get_contents(FILE_NAME)
        decoded_data = content.decoded_content.decode('utf-8')
        df = pd.read_csv(StringIO(decoded_data))
        # Forzar estructura de 3 filas
        df = df.set_index("AUTOMATISTAS").reindex(FILAS_DEPARTAMENTOS).reset_index()
        return df[COLUMNAS_ACCIONES].fillna(""), content.sha
    except:
        df_inicial = pd.DataFrame({
            "AUTOMATISTAS": FILAS_DEPARTAMENTOS,
            "CREAR": ["", "", ""], "MIGRAR": ["", "", ""], "MODIFICAR": ["", "", ""]
        })
        return df_inicial, None

def save_data_to_github(df):
    csv_string = df.to_csv(index=False)
    try:
        # Intentamos obtener el archivo existente para actualizarlo con su SHA correcto
        try:
            current_file = repo.get_contents(FILE_NAME)
            repo.update_file(FILE_NAME, "Sync Matriz", csv_string, current_file.sha)
        except Exception as e:
            # Si el archivo no existe (error 404), lo creamos desde cero
            if "404" in str(e) or "Not Found" in str(e):
                repo.create_file(FILE_NAME, "Init Matriz", csv_string)
            else:
                raise e
        return True
    except Exception as e:
        st.error(f"Error al guardar en GitHub: {e}")
        return False

# --- 3. LÓGICA DE CARGA ---
if "df" not in st.session_state:
    df_git, _ = load_data_from_github()
    st.session_state.df = df_git

# --- 4. BARRA LATERAL (FILTROS) ---
st.sidebar.header("🎯 FILTROS")
    
# Función callback para limpiar los filtros restableciendo sus estados a "Todos"
def limpiar_filtros():
    st.session_state["s_txt"] = ""
    st.session_state["rd_dep"] = "Todos"
    st.session_state["rd_gt"] = "Todos"
    st.session_state["rd_prov"] = "Todos"
    st.session_state["rd_zona"] = "Todos"

# Buscador de texto
s_txt = st.sidebar.text_input("🔍 Buscar objetivo", "", key="s_txt")
    
with st.sidebar.expander("🏢 **Departamento (Filas)**"):
    f_depto = st.sidebar.radio("Selecciona Departamento", ["Todos"] + FILAS_DEPARTAMENTOS, key="rd_dep")

with st.sidebar.expander("📦 **Grupo de Trabajo (GT)**"):
    f_gt = st.sidebar.radio("Selecciona GT", ["Todos"] + OPCIONES_GT, key="rd_gt")

with st.sidebar.expander("🤝 **Proveedor**"):
    f_prov = st.sidebar.radio("Selecciona Proveedor", ["Todos"] + OPCIONES_PROVEEDORES, key="rd_prov")

with st.sidebar.expander("📍 **Zona**"):
    f_zona = st.sidebar.radio("Selecciona Zona", ["Todos"] + OPCIONES_ZONAS, key="rd_zona")
    
st.sidebar.markdown("<br>", unsafe_allow_html=True)
st.sidebar.button("🗑️ BORRAR FILTROS", on_click=limpiar_filtros, use_container_width=True, type="secondary")
st.sidebar.markdown("---")


# --- 4.5. FUNCIÓN PARA FILTRAR EL CONTENIDO DENTRO DE LAS CELDAS ---
def filtrar_contenido_celda(texto_celda, filtro_gt, filtro_prov, filtro_zona):
    if not str(texto_celda).strip():
        return ""
    
    # Separar objetivos (bloques de 4 líneas separados por doble salto de línea)
    bloques = str(texto_celda).split("\n\n")
    bloques_filtrados = []
    
    for b in bloques:
        lineas = [l.strip() for l in b.split("\n") if l.strip()]
        if len(lineas) >= 4:
            # lineas[1] es GT, lineas[2] es Proveedor, lineas[3] es Zona
            match_gt = not filtro_gt or lineas[1] in filtro_gt
            match_prov = not filtro_prov or lineas[2] in filtro_prov
            match_zona = not filtro_zona or lineas[3] in filtro_zona
            
            if match_gt and match_prov and match_zona:
                bloques_filtrados.append(b)
    
    return "\n\n".join(bloques_filtrados)


# --- 4.6. PROCESAMIENTO DEL FILTRADO EN LA COPIA VISUAL ---
df_visual = st.session_state.df.copy()

# 1. Filtro del buscador de texto libre
if s_txt:
    df_visual = df_visual[df_visual.astype(str).apply(lambda x: x.str.contains(s_txt, case=False)).any(axis=1)]

# 2. Filtro de filas (Departamento) -> Comparación directa por String
if f_depto != "Todos":
    df_visual = df_visual[df_visual["AUTOMATISTAS"] == f_depto]

# 3. Filtro de contenido de celdas (Convertimos la selección única del Radio a Lista para la función)
filtro_gt_lista = [f_gt] if f_gt != "Todos" else []
filtro_prov_lista = [f_prov] if f_prov != "Todos" else []
filtro_zona_lista = [f_zona] if f_zona != "Todos" else []

if filtro_gt_lista or filtro_prov_lista or filtro_zona_lista:
    for col in ["CREAR", "MIGRAR", "MODIFICAR"]:
        df_visual[col] = df_visual[col].apply(
            lambda x: filtrar_contenido_celda(x, filtro_gt_lista, filtro_prov_lista, filtro_zona_lista)
        )


# --- 5. PESTAÑAS ---
tab1, tab2 = st.tabs(["📊 Matriz de Trabajo", "➕ Inyectar Objetivo"])

with tab1:
    st.subheader("Cuadro de Mandos Operativo")
    
    # CONTROL DE SEGURIDAD: Verifica si realmente hay algún filtro aplicando restricciones
    filtros_activos = bool(s_txt or f_depto != "Todos" or f_gt != "Todos" or f_prov != "Todos" or f_zona != "Todos")
    
    if filtros_activos:
        st.warning("⚠️ Modo Lectura: Los filtros están activos. Limpialos para editar manualmente.")
    
    # Tabla interactiva (se deshabilita si estás filtrando datos)
    edited_df = st.data_editor(df_visual, use_container_width=True, disabled=filtros_activos)
    
    if not filtros_activos and st.button("💾 Guardar Cambios Manuales"):
        with st.spinner("Guardando..."):
            st.session_state.df.update(edited_df)
            if save_data_to_github(st.session_state.df):
                st.success("¡Matriz actualizada correctamente!")
                st.rerun()

with tab2:
    st.subheader("Formulario de Clasificación")
    with st.form("inyector_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Nombre del Objetivo:")
            accion = st.radio("Acción (Columna):", options=["CREAR", "MIGRAR", "MODIFICAR"], horizontal=True)
            depto = st.selectbox("Departamento (Fila):", options=FILAS_DEPARTAMENTOS)
        with col2:
            gt = st.selectbox("Grupo de Trabajo (GT):", options=OPCIONES_GT)
            prov = st.selectbox("Proveedor:", options=OPCIONES_PROVEEDORES)
            zona = st.selectbox("Zona:", options=OPCIONES_ZONAS)
            
        if st.form_submit_button("Inyectar en Matriz 🚀"):
            if nombre:
                # Crear el bloque estructurado de 4 líneas
                nuevo_bloque = f"{nombre.upper()}\n{gt}\n{prov}\n{zona}"
                
                # Buscar el índice de la fila correspondiente
                idx = st.session_state.df[st.session_state.df["AUTOMATISTAS"] == depto].index[0]
                actual = st.session_state.df.at[idx, accion]
                
                # Inyectar el texto controlando si la celda ya contenía información
                if str(actual).strip():
                    st.session_state.df.at[idx, accion] = f"{actual}\n\n{nuevo_bloque}"
                else:
                    st.session_state.df.at[idx, accion] = nuevo_bloque
                
                if save_data_to_github(st.session_state.df):
                    st.success("¡Objetivo inyectado correctamente!")
                    time.sleep(1)
                    st.rerun()
