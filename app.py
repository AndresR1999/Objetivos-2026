import streamlit as st
import pandas as pd
from github import Github
from io import StringIO
import time
import unicodedata

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

# --- CONFIGURACIÓN ESTRUCTURAL DE LA MATRIZ ---
FILAS_DEPARTAMENTOS = ["Control de Producción", "Procesos Logísticos", "Equipo de Planificación"]
COLUMNAS_ACCIONES = ["AUTOMATISTAS", "CREAR", "MIGRAR", "MODIFICAR"]

# Opciones para los filtros y el formulario
OPCIONES_GT = ["GT1", "GT2", "GT3", "GT4", "GT5"]
OPCIONES_PROVEEDORES = ["TGW", "PSB", "Infios", "Ferag", "Fives"]
OPCIONES_ZONAS = ["Reparto doblado", "Reparto Colgado", "Recepción", "Expediciones", "B2C"]

# --- 1.5. FUNCIÓN AUXILIAR DE NORMALIZACIÓN DE TEXTO ---
def normalizar_texto(texto):
    if not isinstance(texto, str):
        return ""
    texto = texto.upper().strip()
    # Eliminar acentos de forma segura
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def buscar_departamento_coincidente(val):
    val_norm = normalizar_texto(val)
    for depto in FILAS_DEPARTAMENTOS:
        if normalizar_texto(depto) == val_norm:
            return depto
    return None

# --- 2. FUNCIONES DE BASE DE DATOS (CON AUTO-REPARACIÓN) ---

def load_data_from_github():
    try:
        content = repo.get_contents(FILE_NAME)
        decoded_data = content.decoded_content.decode('utf-8')
        df_sucio = pd.read_csv(StringIO(decoded_data))
        
        # Homologar nombre de columna de identificación si viene mutado de versiones previas
        if "OBJETIVOS" in df_sucio.columns and "AUTOMATISTAS" not in df_sucio.columns:
            df_sucio = df_sucio.rename(columns={"OBJETIVOS": "AUTOMATISTAS"})
            
        # MOTOR DE REPARACIÓN: Inicializamos una matriz 100% limpia y perfecta
        matriz_reparada = pd.DataFrame({"AUTOMATISTAS": FILAS_DEPARTAMENTOS})
        for col in ["CREAR", "MIGRAR", "MODIFICAR"]:
            matriz_reparada[col] = ""
            
        # Extraemos y recolocamos de forma inteligente la información del CSV corrupto
        for _, fila in df_sucio.iterrows():
            # Intentar identificar a qué departamento pertenece esta fila por cualquiera de las vías
            depto_crudo = fila.get("AUTOMATISTAS", fila.get("OBJETIVOS", ""))
            depto_destino = buscar_departamento_coincidente(str(depto_crudo))
            
            if depto_destino:
                idx = matriz_reparada[matriz_reparada["AUTOMATISTAS"] == depto_destino].index[0]
                for col in ["CREAR", "MIGRAR", "MODIFICAR"]:
                    celda_origen = str(fila.get(col, "")).strip()
                    # Ignorar celdas vacías o con indicadores temporales planos como 'X'
                    if celda_origen and celda_origen.lower() != "nan" and celda_origen.upper() != "X":
                        celda_actual = matriz_reparada.at[idx, col]
                        if celda_actual:
                            matriz_reparada.at[idx, col] = f"{celda_actual}\n\n{celda_origen}"
                        else:
                            matriz_reparada.at[idx, col] = celda_origen
                            
        return matriz_reparada, content.sha
    except Exception as e:
        # Si el archivo no existe o falla críticamente, generamos la plantilla base limpia
        df_inicial = pd.DataFrame({
            "AUTOMATISTAS": FILAS_DEPARTAMENTOS,
            "CREAR": ["", "", ""], "MIGRAR": ["", "", ""], "MODIFICAR": ["", "", ""]
        })
        return df_inicial, None

def save_data_to_github(df):
    csv_string = df.to_csv(index=False)
    try:
        try:
            current_file = repo.get_contents(FILE_NAME)
            repo.update_file(FILE_NAME, "Sync Matriz", csv_string, current_file.sha)
        except Exception as e:
            if "404" in str(e) or "Not Found" in str(e):
                repo.create_file(FILE_NAME, "Init Matriz", csv_string)
            else:
                raise e
        return True
    except Exception as e:
        st.error(f"Error crítico al guardar en GitHub: {e}")
        return False

# --- 3. LÓGICA DE CARGA DE ESTADO ---
if "df" not in st.session_state:
    df_git, _ = load_data_from_github()
    st.session_state.df = df_git

# --- 4. BARRA LATERAL (FILTROS) ---
st.sidebar.header("🎯 FILTROS")
    
def limpiar_filtros():
    st.session_state["s_txt"] = ""
    st.session_state["rd_dep"] = "Todos"
    st.session_state["rd_gt"] = "Todos"
    st.session_state["rd_prov"] = "Todos"
    st.session_state["rd_zona"] = "Todos"

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

# Botón de emergencia para resetear base de datos corrupta
st.sidebar.markdown("---")
with st.sidebar.expander("⚠️ Zona de Emergencia"):
    if st.button("🚨 REGENERAR MATRIZ LIMPIA", use_container_width=True, type="primary"):
        df_limpio = pd.DataFrame({
            "AUTOMATISTAS": FILAS_DEPARTAMENTOS,
            "CREAR": ["", "", ""], "MIGRAR": ["", "", ""], "MODIFICAR": ["", "", ""]
        })
        if save_data_to_github(df_limpio):
            st.session_state.df = df_limpio
            st.success("¡Base de datos limpiada desde cero!")
            time.sleep(1)
            st.rerun()


# --- 4.5. FUNCIÓN INTERNA PARA FILTRAR BLOQUES DE TEXTO ---
def filtrar_contenido_celda(texto_celda, filtro_gt, filtro_prov, filtro_zona):
    if not str(texto_celda).strip():
        return ""
    
    bloques = str(texto_celda).split("\n\n")
    bloques_filtrados = []
    
    for b in bloques:
        lineas = [l.strip() for l in b.split("\n") if l.strip()]
        if len(lineas) >= 4:
            match_gt = not filtro_gt or lineas[1] in filtro_gt
            match_prov = not filtro_prov or lineas[2] in filtro_prov
            match_zona = not filtro_zona or lineas[3] in filtro_zona
            
            if match_gt and match_prov and match_zona:
                bloques_filtrados.append(b)
                
    return "\n\n".join(bloques_filtrados)


# --- 4.6. EJECUCIÓN COPIA VISUAL ---
df_visual = st.session_state.df.copy()

if s_txt:
    df_visual = df_visual[df_visual.astype(str).apply(lambda x: x.str.contains(s_txt, case=False)).any(axis=1)]

if f_depto != "Todos":
    df_visual = df_visual[df_visual["AUTOMATISTAS"] == f_depto]

filtro_gt_lista = [f_gt] if f_gt != "Todos" else []
filtro_prov_lista = [f_prov] if f_prov != "Todos" else []
filtro_zona_lista = [f_zona] if f_zona != "Todos" else []

if filtro_gt_lista or filtro_prov_lista or filtro_zona_lista:
    for col in ["CREAR", "MIGRAR", "MODIFICAR"]:
        df_visual[col] = df_visual[col].apply(
            lambda x: filtrar_contenido_celda(x, filtro_gt_lista, filtro_prov_lista, filtro_zona_lista)
        )


# --- 5. PESTAÑAS DE INTERFAZ ---
tab1, tab2 = st.tabs(["📊 Matriz de Trabajo", "➕ Inyectar Objetivo"])

with tab1:
    st.subheader("Cuadro de Mandos Operativo")
    
    filtros_activos = bool(s_txt or f_depto != "Todos" or f_gt != "Todos" or f_prov != "Todos" or f_zona != "Todos")
    
    if filtros_activos:
        st.warning("⚠️ Modo Lectura: Los filtros están activos. Limpialos para editar manualmente.")
    
    # Tabla interactiva con celdas multilínea deshabilitada si hay filtros activos
    edited_df = st.data_editor(df_visual, use_container_width=True, disabled=filtros_activos)
    
    if not filtros_activos and st.button("💾 Guardar Cambios Manuales"):
        with st.spinner("Sincronizando cambios con GitHub..."):
            st.session_state.df.update(edited_df)
            if save_data_to_github(st.session_state.df):
                st.success("¡Matriz actualizada y sincronizada!")
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
                # Construir el bloque exacto de 4 líneas deseadas
                nuevo_bloque = f"{nombre.upper()}\n{gt}\n{prov}\n{zona}"
                
                # Localizar el índice correcto de la matriz oficial de 3 filas
                idx = st.session_state.df[st.session_state.df["AUTOMATISTAS"] == depto].index[0]
                actual = st.session_state.df.at[idx, accion]
                
                # Insertar controlando saltos de línea elegantes
                if str(actual).strip():
                    st.session_state.df.at[idx, accion] = f"{actual}\n\n{nuevo_bloque}"
                else:
                    st.session_state.df.at[idx, accion] = nuevo_bloque
                
                if save_data_to_github(st.session_state.df):
                    st.success("¡Objetivo inyectado en la celda correspondiente con éxito!")
                    time.sleep(1)
                    st.rerun()
