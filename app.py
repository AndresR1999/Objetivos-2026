import streamlit as st
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime


st.set_page_config(
    page_title="Visor de Tickets Jira",
    page_icon="🎫",
    layout="wide"
)

st.title("🎫 Visor de Tickets Jira")
st.caption("Visualización y filtrado de tickets conectados con Jira.")


JIRA_BASE_URL = st.secrets["JIRA_BASE_URL"].rstrip("/")
JIRA_EMAIL = st.secrets["JIRA_EMAIL"]
JIRA_API_TOKEN = st.secrets["JIRA_API_TOKEN"]

JIRA_JQL = st.secrets.get("JIRA_JQL", "project = AUTM ORDER BY updated DESC")
JIRA_MAX_RESULTS = int(st.secrets.get("JIRA_MAX_RESULTS", 300))
JIRA_PROVEEDOR_FIELD_NAME = st.secrets.get(
    "JIRA_PROVEEDOR_FIELD_NAME",
    "Equipos Responsables (Externos)"
)


auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)

headers = {
    "Accept": "application/json"
}


def jira_get(endpoint, params=None):
    url = f"{JIRA_BASE_URL}{endpoint}"

    try:
        response = requests.get(
            url,
            headers=headers,
            auth=auth,
            params=params,
            timeout=30
        )
    except requests.exceptions.RequestException as e:
        st.error("No se ha podido conectar con Jira.")
        st.code(str(e))
        st.stop()

    if response.status_code == 401:
        st.error(
            "Error 401: no se ha podido autenticar con Jira. "
            "Revisa el email y el API token de Atlassian en los Secrets."
        )
        st.stop()

    if response.status_code == 403:
        st.error(
            "Error 403: tu usuario se autentica correctamente, "
            "pero no tiene permisos suficientes para consultar esta información en Jira."
        )
        st.stop()

    if response.status_code >= 400:
        st.error(f"Error consultando Jira: {response.status_code}")
        st.code(response.text)
        st.stop()

    return response.json()


@st.cache_data(ttl=300)
def get_current_user():
    data = jira_get("/rest/api/3/myself")

    return {
        "account_id": data.get("accountId"),
        "display_name": data.get("displayName"),
        "email": data.get("emailAddress")
    }


@st.cache_data(ttl=3600)
def get_jira_fields():
    return jira_get("/rest/api/3/field")


def find_field_id_by_name(field_name):
    if not field_name:
        return None

    fields = get_jira_fields()

    for field in fields:
        jira_name = field.get("name", "").strip().lower()
        expected_name = field_name.strip().lower()

        if jira_name == expected_name:
            return field.get("id")

    return None


def extract_user_name(user_obj):
    if not user_obj:
        return "Sin asignar"

    return user_obj.get("displayName", "Sin asignar")


def extract_user_id(user_obj):
    if not user_obj:
        return None

    return user_obj.get("accountId")


def extract_value(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        values = []

        for item in value:
            if isinstance(item, dict):
                values.append(
                    item.get("value")
                    or item.get("name")
                    or item.get("displayName")
                    or str(item)
                )
            else:
                values.append(str(item))

        return ", ".join(values)

    if isinstance(value, dict):
        return (
            value.get("value")
            or value.get("name")
            or value.get("displayName")
            or str(value)
        )

    return str(value)


def format_date(date_value):
    if not date_value:
        return ""

    try:
        parsed = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
        return parsed.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return date_value


@st.cache_data(ttl=300)
def get_jira_issues(jql, max_results, proveedor_field_name):
    proveedor_field_id = find_field_id_by_name(proveedor_field_name)

    base_fields = [
        "summary",
        "status",
        "assignee",
        "reporter",
        "created",
        "updated",
        "priority",
        "issuetype",
        "project",
        "labels"
    ]

    if proveedor_field_id:
        base_fields.append(proveedor_field_id)

    all_issues = []
    start_at = 0
    page_size = 100

    while len(all_issues) < max_results:
        current_page_size = min(page_size, max_results - len(all_issues))

        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": current_page_size,
            "fields": ",".join(base_fields)
        }

        data = jira_get("/rest/api/3/search", params=params)

        issues = data.get("issues", [])
        total = data.get("total", 0)

        all_issues.extend(issues)

        if not issues:
            break

        start_at += len(issues)

        if start_at >= total:
            break

    rows = []

    for issue in all_issues:
        fields = issue.get("fields", {})

        status = fields.get("status") or {}
        assignee = fields.get("assignee")
        reporter = fields.get("reporter")
        priority = fields.get("priority") or {}
        issue_type = fields.get("issuetype") or {}
        project = fields.get("project") or {}
        labels = fields.get("labels") or []

        proveedor_value = ""

        if proveedor_field_id:
            proveedor_value = extract_value(fields.get(proveedor_field_id))

        issue_key = issue.get("key", "")

        rows.append({
            "Clave": issue_key,
            "Resumen": fields.get("summary", ""),
            "Estado": status.get("name", ""),
            "Proveedor externo": proveedor_value,
            "Responsable": extract_user_name(assignee),
            "Responsable ID": extract_user_id(assignee),
            "Creador": extract_user_name(reporter),
            "Creador ID": extract_user_id(reporter),
            "Prioridad": priority.get("name", ""),
            "Tipo": issue_type.get("name", ""),
            "Proyecto": project.get("name", ""),
            "Labels": ", ".join(labels),
            "Creado": format_date(fields.get("created")),
            "Actualizado": format_date(fields.get("updated")),
            "URL": f"{JIRA_BASE_URL}/browse/{issue_key}"
        })

    df = pd.DataFrame(rows)

    return df, proveedor_field_id


def reset_filters():
    st.session_state["f_texto"] = ""
    st.session_state["f_vista"] = "Todos"
    st.session_state["f_estado"] = []
    st.session_state["f_proveedor"] = []
    st.session_state["f_responsable"] = []
    st.session_state["f_creador"] = []
    st.session_state["f_tipo"] = []
    st.session_state["f_prioridad"] = []


with st.spinner("Cargando información desde Jira..."):
    current_user = get_current_user()

    df, proveedor_field_id = get_jira_issues(
        JIRA_JQL,
        JIRA_MAX_RESULTS,
        JIRA_PROVEEDOR_FIELD_NAME
    )


if df.empty:
    st.warning("No se han encontrado tickets con la consulta configurada.")
    st.stop()


st.sidebar.header("🔎 Filtros")

texto = st.sidebar.text_input(
    "Buscar",
    key="f_texto",
    placeholder="Clave, resumen, proveedor..."
)

vista = st.sidebar.radio(
    "Vista de tickets",
    [
        "Todos",
        "Asignados a mí",
        "Creados por mí",
        "De otros compañeros"
    ],
    key="f_vista"
)

estados = sorted([x for x in df["Estado"].dropna().unique() if x])
proveedores = sorted([x for x in df["Proveedor externo"].dropna().unique() if x])
responsables = sorted([x for x in df["Responsable"].dropna().unique() if x])
creadores = sorted([x for x in df["Creador"].dropna().unique() if x])
tipos = sorted([x for x in df["Tipo"].dropna().unique() if x])
prioridades = sorted([x for x in df["Prioridad"].dropna().unique() if x])

estado_sel = st.sidebar.multiselect(
    "Estado del ticket",
    estados,
    key="f_estado"
)

proveedor_sel = st.sidebar.multiselect(
    "Proveedor externo",
    proveedores,
    key="f_proveedor"
)

responsable_sel = st.sidebar.multiselect(
    "Responsable",
    responsables,
    key="f_responsable"
)

creador_sel = st.sidebar.multiselect(
    "Creador",
    creadores,
    key="f_creador"
)

tipo_sel = st.sidebar.multiselect(
    "Tipo de solicitud",
    tipos,
    key="f_tipo"
)

prioridad_sel = st.sidebar.multiselect(
    "Prioridad",
    prioridades,
    key="f_prioridad"
)

st.sidebar.markdown("---")

if st.sidebar.button("🗑️ Borrar filtros", use_container_width=True):
    reset_filters()
    st.rerun()

if st.sidebar.button("🔄 Refrescar datos", use_container_width=True):
    st.cache_data.clear()
    st.rerun()


df_filtered = df.copy()

if texto:
    texto_lower = texto.lower()

    df_filtered = df_filtered[
        df_filtered.astype(str).apply(
            lambda row: row.str.lower().str.contains(texto_lower, na=False)
        ).any(axis=1)
    ]

if vista == "Asignados a mí":
    df_filtered = df_filtered[
        df_filtered["Responsable ID"] == current_user["account_id"]
    ]

elif vista == "Creados por mí":
    df_filtered = df_filtered[
        df_filtered["Creador ID"] == current_user["account_id"]
    ]

elif vista == "De otros compañeros":
    df_filtered = df_filtered[
        (df_filtered["Responsable ID"] != current_user["account_id"])
        & (df_filtered["Creador ID"] != current_user["account_id"])
    ]

if estado_sel:
    df_filtered = df_filtered[df_filtered["Estado"].isin(estado_sel)]

if proveedor_sel:
    df_filtered = df_filtered[df_filtered["Proveedor externo"].isin(proveedor_sel)]

if responsable_sel:
    df_filtered = df_filtered[df_filtered["Responsable"].isin(responsable_sel)]

if creador_sel:
    df_filtered = df_filtered[df_filtered["Creador"].isin(creador_sel)]

if tipo_sel:
    df_filtered = df_filtered[df_filtered["Tipo"].isin(tipo_sel)]

if prioridad_sel:
    df_filtered = df_filtered[df_filtered["Prioridad"].isin(prioridad_sel)]


total_tickets = len(df)
filtered_tickets = len(df_filtered)
assigned_to_me = len(df[df["Responsable ID"] == current_user["account_id"]])
created_by_me = len(df[df["Creador ID"] == current_user["account_id"]])

col1, col2, col3, col4 = st.columns(4)

col1.metric("Tickets cargados", total_tickets)
col2.metric("Tickets filtrados", filtered_tickets)
col3.metric("Asignados a mí", assigned_to_me)
col4.metric("Creados por mí", created_by_me)


if not proveedor_field_id:
    st.warning(
        f"No se ha encontrado en Jira el campo "
        f"'{JIRA_PROVEEDOR_FIELD_NAME}'. "
        "La columna de proveedor externo aparecerá vacía. "
        "Revisa que el nombre del campo coincida exactamente con Jira."
    )


st.markdown("**Tabla de tickets**")

columns_to_show = [
    "Clave",
    "Resumen",
    "Estado",
    "Proveedor externo",
    "Responsable",
    "Creador",
    "Prioridad",
    "Tipo",
    "Proyecto",
    "Labels",
    "Creado",
    "Actualizado",
    "URL"
]

existing_columns = [
    col for col in columns_to_show
    if col in df_filtered.columns
]

st.dataframe(
    df_filtered[existing_columns],
    use_container_width=True,
    hide_index=True,
    column_config={
        "URL": st.column_config.LinkColumn(
            "Abrir en Jira",
            display_text="Abrir"
        )
    }
)


with st.expander("Configuración de la consulta"):
    st.write("**Usuario conectado:**", current_user.get("display_name"))
    st.write("**Email:**", current_user.get("email"))
    st.write("**URL Jira:**", JIRA_BASE_URL)
    st.write("**JQL:**")
    st.code(JIRA_JQL)
    st.write("**Máximo de tickets cargados:**", JIRA_MAX_RESULTS)
    st.write("**Campo Jira usado como proveedor externo:**", JIRA_PROVEEDOR_FIELD_NAME)

    if proveedor_field_id:
        st.success(
            f"Campo de proveedor encontrado correctamente en Jira: {proveedor_field_id}"
        )
    else:
        st.warning("Campo de proveedor no encontrado.")
