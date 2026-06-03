import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import extra_streamlit_components as stx
import time

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestión de Objetivos 🐼", layout="wide")

# Inicialización del Cookie Manager para recordar la sesión en el navegador
cookie_manager = stx.CookieManager(key="objetivos_cookie_manager")

# --- 2. INICIALIZACIÓN DE ESTADOS INTERNOS (MATRIZ Y FILTROS) ---
if "objetivos_df" not in st.session_state:
    # DataFrame inicial con las columnas solicitadas y filas Objetivo 1 / Objetivo 2
    st.session_state["objetivos_df"] = pd.DataFrame([
        {
            "Objetivo": "Objetivo 1", 
            "Crear": "Detalle crear 1", 
            "Migrar": "Detalle migrar 1", 
            "Modificar": "Detalle modificar 1", 
            "Automatista": "Automatista A", 
            "Proveedor Externo": "Proveedor X", 
            "Zona/Sección": "Zona 1"
        },
        {
            "Objetivo": "Objetivo 2", 
            "Crear": "Detalle crear 2", 
            "Migrar": "Detalle migrar 2", 
            "Modificar": "Detalle modificar 2", 
            "Automatista": "Automatista B", 
            "Proveedor Externo": "Proveedor Y", 
            "Zona/Sección": "Zona 2"
        }
    ])

if "opciones_filtros" not in st.session_state:
    st.session_state["opciones_filtros"] = {
        "automatistas": ["Automatista A", "Automatista B"],
        "proveedores": ["Proveedor X", "Proveedor Y"],
        "zonas": ["Zona 1", "Zona 2"]
    }

if 'usuario_actual' not in st.session_state:
    st.session_state['usuario_actual'] = None

# Intentar capturar la cookie guardada previamente en el navegador
try:
    cookie_user = cookie_manager.get(cookie="sesion_usuario_objetivos")
    if cookie_user and st.session_state['usuario_actual'] is None:
        st.session_state['usuario_actual'] = cookie_user
except:
    pass

# --- 3. SIDEBAR (LOGIN Y FILTROS) ---
with st.sidebar:
    st.markdown("## 🔐 SESIÓN")
    
    if st.session_state['usuario_actual'] is None:
        st.info("Inicia sesión para desbloquear la aplicación.")
        usuario_input = st.text_input("Introduce tu Usuario:", key="input_login_usuario")
        if st.button("Iniciar Sesión y Recordar 💾", use_container_width=True):
            if usuario_input.strip() != "":
                st.session_state['usuario_actual'] = usuario_input.strip()
                # Guarda la cookie en el navegador por 30 días
                cookie_manager.set("sesion_usuario_objetivos", usuario_input.strip(), expires_at=datetime.now() + timedelta(days=30))
                st.success(f"¡Hola {usuario_input}! Sesión guardada.")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("El nombre de usuario no puede estar vacío.")
    else:
        st.write(f"👤 Sesión activa: **{st.session_state['usuario_actual']}**")
        if st.button("Cerrar Sesión 🚪", use_container_width=True):
            st.session_state['usuario_actual'] = None
            cookie_manager.delete("sesion_usuario_objetivos")
            st.rerun()

    st.markdown("---")
    
    # --- FILTROS DE LA SIDEBAR ---
    st.header("🎯 FILTROS")
    if st.session_state['usuario_actual'] is not None:
        filtro_automatista = st.selectbox(
            "⚙️ Automatistas", 
            ["Todos"] + st.session_state["opciones_filtros"]["automatistas"]
        )
        filtro_proveedor = st.selectbox(
            "🏢 Proveedores Externos", 
            ["Todos"] + st.session_state["opciones_filtros"]["proveedores"]
        )
        filtro_zona = st.selectbox(
            "📍 Zonas/Secciones", 
            ["Todos"] + st.session_state["opciones_filtros"]["zonas"]
        )
    else:
        st.warning("⚠️ Debes iniciar sesión para usar los filtros.")
        filtro_automatista = "Todos"
        filtro_proveedor = "Todos"
        filtro_zona = "Todos"


# --- 4. APLICACIÓN PRINCIPAL (PANTALLA CENTRAL) ---
st.title("🎯 SISTEMA DE GESTIÓN DE OBJETIVOS")

if st.session_state['usuario_actual'] is None:
    st.warning("🔒 Por favor, inicia sesión en la barra lateral para acceder a las matrices de trabajo.")
else:
    # Aplicar los filtros de la barra lateral al DataFrame en memoria
    df_objetivos_filtrado = st.session_state["objetivos_df"].copy()

    if filtro_automatista != "Todos":
        df_objetivos_filtrado = df_objetivos_filtrado[df_objetivos_filtrado["Automatista"] == filtro_automatista]
    if filtro_proveedor != "Todos":
        df_objetivos_filtrado = df_objetivos_filtrado[df_objetivos_filtrado["Proveedor Externo"] == filtro_proveedor]
    if filtro_zona != "Todos":
        df_objetivos_filtrado = df_objetivos_filtrado[df_objetivos_filtrado["Zona/Sección"] == filtro_zona]

    # Control por pestañas
    t = st.tabs([
        "📋 Matriz de Objetivos",
        "➕ Añadir Objetivos/Filtros"
    ])

    # --- PESTAÑA 1: VISUALIZACIÓN Y EDICIÓN DE LA MATRIZ ---
    with t[0]:
        st.subheader("📋 Control y Seguimiento de Objetivos")
        
        columnas_visibles = ["Objetivo", "Crear", "Migrar", "Modificar", "Automatista", "Proveedor Externo", "Zona/Sección"]
        
        df_editado = st.data_editor(
            df_objetivos_filtrado[columnas_visibles], 
            use_container_width=True, 
            key="editor_matriz_objetivos",
            num_rows="dynamic"
        )
        
        if st.button("💾 Guardar Cambios en la Tabla"):
            # Sincroniza las celdas editadas directamente en el estado global
            for idx, row in df_editado.iterrows():
                if idx in st.session_state["objetivos_df"].index:
                    st.session_state["objetivos_df"].loc[idx, columnas_visibles] = row
            st.success("¡Matriz actualizada correctamente!")
            st.rerun()

    # --- PESTAÑA 2: AÑADIR NUEVAS FILAS O ELEMENTOS A LOS FILTROS ---
    with t[1]:
        st.subheader("➕ Añadir elementos a las listas")
        
        opcion_insercion = st.radio(
            "Selecciona qué deseas dar de alta en la aplicación:",
            ["Nuevo Objetivo", "Nuevo Automatista", "Nuevo Proveedor Externo", "Nueva Zona/Sección"],
            horizontal=True
        )
        
        st.markdown("---")
        
        if opcion_insercion == "Nuevo Objetivo":
            st.markdown("### Registrar un nuevo Objetivo")
            with st.form("form_nuevo_objetivo", clear_on_submit=True):
                nombre_obj = st.text_input("Nombre del Objetivo:", placeholder="Ej: Objetivo 3")
                txt_crear = st.text_area("Columna 'Crear':")
                txt_migrar = st.text_area("Columna 'Migrar':")
                txt_modificar = st.text_area("Columna 'Modificar':")
                
                # Desplegables que se alimentan de los filtros dinámicos
                sel_auto = st.selectbox("Asignar Automatista:", st.session_state["opciones_filtros"]["automatistas"])
                sel_prov = st.selectbox("Asignar Proveedor Externo:", st.session_state["opciones_filtros"]["proveedores"])
                sel_zona = st.selectbox("Asignar Zona/Sección:", st.session_state["opciones_filtros"]["zonas"])
                
                if st.form_submit_button("Insertar Objetivo en la Tabla 🚀") and nombre_obj:
                    nuevo_registro = {
                        "Objetivo": nombre_obj,
                        "Crear": txt_crear,
                        "Migrar": txt_migrar,
                        "Modificar": txt_modificar,
                        "Automatista": sel_auto,
                        "Proveedor Externo": sel_prov,
                        "Zona/Sección": sel_zona
                    }
                    st.session_state["objetivos_df"] = pd.concat([
                        st.session_state["objetivos_df"], 
                        pd.DataFrame([nuevo_registro])
                    ], ignore_index=True)
                    st.success(f"✔️ {nombre_obj} añadido correctamente.")
                    st.rerun()

        elif opcion_insercion == "Nuevo Automatista":
            st.markdown("### Añadir nuevo Automatista")
            nuevo_auto = st.text_input("Nombre del Automatista:")
            if st.button("Registrar Automatista ⚙️") and nuevo_auto:
                if nuevo_auto not in st.session_state["opciones_filtros"]["automatistas"]:
                    st.session_state["opciones_filtros"]["automatistas"].append(nuevo_auto)
                    st.success(f"¡{nuevo_auto} añadido a las opciones de filtro!")
                    st.rerun()
                else:
                    st.warning("Este automatista ya existe.")

        elif opcion_insercion == "Nuevo Proveedor Externo":
            st.markdown("### Añadir nuevo Proveedor Externo")
            nuevo_prov = st.text_input("Nombre del Proveedor:")
            if st.button("Registrar Proveedor 🏢") and nuevo_prov:
                if nuevo_prov not in st.session_state["opciones_filtros"]["proveedores"]:
                    st.session_state["opciones_filtros"]["proveedores"].append(nuevo_prov)
                    st.success(f"¡{nuevo_prov} añadido a las opciones de filtro!")
                    st.rerun()
                else:
                    st.warning("Este proveedor ya existe.")

        elif opcion_insercion == "Nueva Zona/Sección":
            st.markdown("### Añadir nueva Zona/Sección")
            nueva_zona = st.text_input("Nombre de la Zona/Sección:")
            if st.button("Registrar Zona 📍") and nueva_zona:
                if nueva_zona not in st.session_state["opciones_filtros"]["zonas"]:
                    st.session_state["opciones_filtros"]["zonas"].append(nueva_zona)
                    st.success(f"¡{nueva_zona} añadida a las opciones de filtro!")
                    st.rerun()
                else:
                    st.warning("Esta zona ya existe.")