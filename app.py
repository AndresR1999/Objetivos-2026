import streamlit as st
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
import re
from html import unescape, escape
import streamlit.components.v1 as components
import unicodedata

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

JIRA_JQL = st.secrets.get("JIRA_JQL", "project = AUTM ORDER BY created DESC")
JIRA_MAX_RESULTS = int(st.secrets.get("JIRA_MAX_RESULTS", 300))
JIRA_PROVEEDOR_FIELD_NAME = st.secrets.get(
    "JIRA_PROVEEDOR_FIELD_NAME",
    "Equipos Responsables (Externos)"
)

PROVEEDOR_BY_OBJECT_ID = {
    "288795": "Clustag",
    "346316": "-",
    "288760": "TGW",
    "295882": "DXC",
    "288796": "Infios",
    "288761": "PSB",
    "309628": "Ferag",
    "309627": "Fives",
    "288794": "Macrolet",
    # "XXXXX": "Vanderlande",
}

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

def jira_get_optional(endpoint, params=None):
    url = f"{JIRA_BASE_URL}{endpoint}"

    try:
        response = requests.get(
            url,
            headers=headers,
            auth=auth,
            params=params,
            timeout=30
        )
    except requests.exceptions.RequestException:
        return None

    if response.status_code >= 400:
        return None

    try:
        return response.json()
    except Exception:
        return None


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

def clean_rendered_value(value):
    if not value:
        return ""

    if isinstance(value, list):
        value = ", ".join([str(x) for x in value])

    value = str(value)

    # Quitar etiquetas HTML
    value = re.sub(r"<[^>]+>", " ", value)

    # Decodificar entidades HTML
    value = unescape(value)

    # Limpiar espacios repetidos
    value = re.sub(r"\s+", " ", value).strip()

    return value


def looks_like_technical_asset_value(value):
    if not value:
        return False

    value_str = str(value)

    technical_markers = [
        "workspaceId",
        "objectId",
        "'workspace",
        '"workspace',
        "'id'",
        '"id"'
    ]

    return any(marker in value_str for marker in technical_markers)


def extract_asset_refs(value):
    refs = []

    if value is None:
        return refs

    if isinstance(value, list):
        for item in value:
            refs.extend(extract_asset_refs(item))
        return refs

    if isinstance(value, dict):
        workspace_id = (
            value.get("workspaceId")
            or value.get("workspace")
            or value.get("workspace_id")
        )

        object_id = (
            value.get("objectId")
            or value.get("object_id")
        )

        raw_id = value.get("id")

        if not object_id and raw_id:
            raw_id_str = str(raw_id)

            # Casos tipo "workspaceId:objectId"
            if ":" in raw_id_str:
                parts = raw_id_str.split(":")
                if len(parts) >= 2:
                    if not workspace_id:
                        workspace_id = parts[0]
                    object_id = parts[-1]

            # Casos donde el id termina en número
            if not object_id:
                match = re.search(r"(\d+)$", raw_id_str)
                if match:
                    object_id = match.group(1)

        if workspace_id and object_id:
            refs.append({
                "workspace_id": str(workspace_id),
                "object_id": str(object_id)
            })

        return refs

    return refs


def pick_asset_name(asset_data):
    if not asset_data:
        return ""

    # Primero probamos campos directos habituales
    for key in ["label", "name", "displayName"]:
        value = asset_data.get(key)
        if value:
            return str(value)

    # Después buscamos dentro de atributos de Assets
    attributes = asset_data.get("attributes", [])

    preferred_attribute_names = [
        "name",
        "nombre",
        "proveedor",
        "supplier",
        "vendor",
        "equipo",
        "team",
        "external provider",
        "proveedor externo"
    ]

    fallback_values = []

    for attribute in attributes:
        attr_info = attribute.get("objectTypeAttribute", {}) or {}
        attr_name = str(attr_info.get("name", "")).strip().lower()

        values = attribute.get("objectAttributeValues", []) or []

        for item in values:
            candidate = (
                item.get("displayValue")
                or item.get("searchValue")
                or item.get("value")
            )

            referenced_object = item.get("referencedObject")
            if referenced_object:
                candidate = (
                    referenced_object.get("label")
                    or referenced_object.get("name")
                    or candidate
                )

            if not candidate:
                continue

            candidate = str(candidate)

            if attr_name in preferred_attribute_names:
                return candidate

            fallback_values.append(candidate)

    if fallback_values:
        return fallback_values[0]

    # Último recurso: objectKey
    object_key = asset_data.get("objectKey")
    if object_key:
        return str(object_key)

    return ""


@st.cache_data(ttl=3600)
def resolve_asset_object_name(workspace_id, object_id):
    """
    Convierte el objectId interno de Jira Assets al proveedor externo real.
    """

    object_id = str(object_id)

    if object_id in PROVEEDOR_BY_OBJECT_ID:
        return PROVEEDOR_BY_OBJECT_ID[object_id]

    return f"Objeto {object_id}"



def extract_provider_value(raw_value, rendered_value=None):
    """
    Extrae el proveedor externo.

    Si Jira devuelve un texto normal, lo usa.
    Si devuelve un objeto técnico de Assets, intenta resolverlo
    mediante objectId/workspaceId.
    """

    rendered_clean = clean_rendered_value(rendered_value)

    if rendered_clean and not looks_like_technical_asset_value(rendered_clean):
        return rendered_clean

    if raw_value is None:
        return ""

    # Si ya viene como texto legible, lo usamos
    if isinstance(raw_value, str) and not looks_like_technical_asset_value(raw_value):
        return raw_value

    asset_refs = extract_asset_refs(raw_value)

    if asset_refs:
        names = []

        for ref in asset_refs:
            name = resolve_asset_object_name(
                ref["workspace_id"],
                ref["object_id"]
            )

            if name:
                names.append(name)

        return ", ".join(names)

    # Fallback para otros tipos de campos
    fallback = extract_value(raw_value)

    if looks_like_technical_asset_value(fallback):
        return ""

    return fallback



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
    next_page_token = None
    page_size = 100

    while len(all_issues) < max_results:
        current_page_size = min(page_size, max_results - len(all_issues))

        params = {
            "jql": jql,
            "maxResults": current_page_size,
            "fields": ",".join(base_fields),
            "expand": "renderedFields"
        }


        if next_page_token:
            params["nextPageToken"] = next_page_token

        data = jira_get("/rest/api/3/search/jql", params=params)

        issues = data.get("issues", [])
        all_issues.extend(issues)

        if not issues:
            break

        if data.get("isLast", False):
            break

        next_page_token = data.get("nextPageToken")

        if not next_page_token:
            break

    rows = []

    for issue in all_issues:
        fields = issue.get("fields", {})
        rendered_fields = issue.get("renderedFields", {})
    
        status = fields.get("status") or {}

        assignee = fields.get("assignee")
        reporter = fields.get("reporter")
        priority = fields.get("priority") or {}
        issue_type = fields.get("issuetype") or {}
        project = fields.get("project") or {}
        labels = fields.get("labels") or []

        proveedor_value = ""

        if proveedor_field_id:
            proveedor_value = extract_provider_value(
                fields.get(proveedor_field_id),
                rendered_fields.get(proveedor_field_id)
            )


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
    st.session_state["f_tipo"] = DEFAULT_TIPO_SEL
    st.session_state["f_proyecto"] = DEFAULT_PROYECTO_SEL
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

columns_with_dash_when_empty = [
    "Proveedor externo",
    "Prioridad"
]

for col in columns_with_dash_when_empty:
    if col in df.columns:
        df[col] = (
            df[col]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", "-")
        )

st.sidebar.header("🔎 Filtros")

estados = sorted([x for x in df["Estado"].dropna().unique() if x])
proveedores = sorted([x for x in df["Proveedor externo"].dropna().unique() if x])
responsables = sorted([x for x in df["Responsable"].dropna().unique() if x])
creadores = sorted([x for x in df["Creador"].dropna().unique() if x])
tipos = sorted([x for x in df["Tipo"].dropna().unique() if x])
proyectos = sorted([x for x in df["Proyecto"].dropna().unique() if x])
prioridades = sorted([x for x in df["Prioridad"].dropna().unique() if x])

DEFAULT_TIPO_SEL = ["Incident"] if "Incident" in tipos else []
DEFAULT_PROYECTO_SEL = ["Automatistas Lliçà"] if "Automatistas Lliçà" in proyectos else []

st.sidebar.markdown("---")

if st.sidebar.button("🗑️ Borrar filtros", use_container_width=True):
    reset_filters()
    st.rerun()

if st.sidebar.button("🔄 Refrescar datos", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")

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
    default=DEFAULT_TIPO_SEL,
    key="f_tipo"
)

proyecto_sel = st.sidebar.multiselect(
    "Proyecto",
    proyectos,
    default=DEFAULT_PROYECTO_SEL,
    key="f_proyecto"
)

prioridad_sel = st.sidebar.multiselect(
    "Prioridad",
    prioridades,
    key="f_prioridad"
)


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

if proyecto_sel:
    df_filtered = df_filtered[df_filtered["Proyecto"].isin(proyecto_sel)]

if prioridad_sel:
    df_filtered = df_filtered[df_filtered["Prioridad"].isin(prioridad_sel)]

df_filtered = df_filtered.copy()

df_filtered["_Creado_dt"] = pd.to_datetime(
    df_filtered["Creado"],
    format="%d/%m/%Y %H:%M",
    errors="coerce"
)

df_filtered = df_filtered.sort_values(
    by="_Creado_dt",
    ascending=False
)

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
    "Prioridad",
    "Creado",
    "URL"
]

existing_columns = [
    col for col in columns_to_show
    if col in df_filtered.columns
]

df_table = df_filtered[existing_columns].copy()

def render_tickets_table(df_table):
    def safe_text(value):
        if pd.isna(value):
            return ""
        return escape(str(value))

    def normalize_css_class(value):
        value = str(value or "").strip().lower()

        value = unicodedata.normalize("NFKD", value)
        value = "".join(c for c in value if not unicodedata.combining(c))

        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = value.strip("-")

        return value or "default"

    def render_status_badge(value):
        label = safe_text(value)

        if not label or label == "-":
            return '<span class="badge badge-status-default">-</span>'

        status_class = normalize_css_class(label)

        known_statuses = {
            "resuelta",
            "resuelto",
            "done",
            "closed",
            "escalated",
            "escalado",
            "cancelado",
            "cancelada",
            "canceled",
            "cancelled",
            "en-curso",
            "in-progress",
            "pendiente",
            "pending",
            "open",
            "to-do",
            "reopened"
        }

        if status_class not in known_statuses:
            status_class = "default"

        return f'<span class="badge badge-status-{status_class}">{label}</span>'

    def render_priority_badge(value):
        label = safe_text(value)

        if not label or label == "-":
            return '<span class="badge badge-priority-default">-</span>'

        priority_class = normalize_css_class(label)

        known_priorities = {
            "highest",
            "high",
            "medium",
            "low",
            "lowest"
        }

        if priority_class not in known_priorities:
            priority_class = "default"

        return f'<span class="badge badge-priority-{priority_class}">{label}</span>'

    html_parts = []


    html_parts.append("""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            html, body {
                margin: 0;
                padding: 0;
                font-family: Arial, sans-serif;
                background: #f6f7fb;
            }

            .tickets-table-container {
                width: 100%;
                height: 720px;
                overflow-y: auto;
                overflow-x: auto;
                border: 1px solid #e5e7eb;
                border-radius: 14px;
                background: #ffffff;
                box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08);
            }

            table.tickets-table {
                width: 100%;
                min-width: 1450px;
                border-collapse: separate;
                border-spacing: 0;
                table-layout: fixed;
                font-size: 14px;
                background: #ffffff;
            }

            .tickets-table th {
                position: sticky;
                top: 0;
                background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
                z-index: 2;
                text-align: left;
                padding: 12px 10px;
                border-bottom: 1px solid #dce1e8;
                font-weight: 700;
                color: #334155;
                white-space: nowrap;
            }

            .tickets-table td {
                padding: 11px 10px;
                border-bottom: 1px solid #eef2f7;
                vertical-align: top;
                color: #1f2937;
            }

            .tickets-table tr:nth-child(odd) {
                background-color: #ffffff;
            }

            .tickets-table tr:nth-child(even) {
                background-color: #f9fafb;
            }

            .tickets-table tr:hover {
                background-color: #eef6ff;
            }

            .badge {
                display: inline-block;
                padding: 5px 10px;
                border-radius: 999px;
                font-size: 12px;
                font-weight: 700;
                line-height: 1;
                white-space: nowrap;
                border: 1px solid transparent;
            }

            /* Estados */
            .badge-status-resuelta,
            .badge-status-resuelto,
            .badge-status-done,
            .badge-status-closed {
                background: #dcfce7;
                color: #166534;
                border-color: #bbf7d0;
            }

            .badge-status-escalated,
            .badge-status-escalado {
                background: #dbeafe;
                color: #1d4ed8;
                border-color: #bfdbfe;
            }

            .badge-status-cancelado,
            .badge-status-cancelada,
            .badge-status-canceled,
            .badge-status-cancelled {
                background: #fee2e2;
                color: #b91c1c;
                border-color: #fecaca;
            }

            .badge-status-en-curso,
            .badge-status-in-progress {
                background: #fef3c7;
                color: #92400e;
                border-color: #fde68a;
            }

            .badge-status-pendiente,
            .badge-status-pending,
            .badge-status-open,
            .badge-status-to-do,
            .badge-status-reopened {
                background: #ede9fe;
                color: #6d28d9;
                border-color: #ddd6fe;
            }

            .badge-status-default {
                background: #e5e7eb;
                color: #374151;
                border-color: #d1d5db;
            }

            /* Prioridades */
            .badge-priority-highest {
                background: #fee2e2;
                color: #b91c1c;
                border-color: #fecaca;
            }

            .badge-priority-high {
                background: #ffedd5;
                color: #c2410c;
                border-color: #fed7aa;
            }

            .badge-priority-medium {
                background: #dbeafe;
                color: #1d4ed8;
                border-color: #bfdbfe;
            }

            .badge-priority-low,
            .badge-priority-lowest {
                background: #e5e7eb;
                color: #4b5563;
                border-color: #d1d5db;
            }

            .badge-priority-default {
                background: #f3f4f6;
                color: #374151;
                border-color: #e5e7eb;
            }

            .col-clave {
                width: 95px;
                white-space: nowrap;
                font-weight: 700;
                color: #0f172a;
            }

            .col-resumen {
                width: 520px;
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: normal;
                line-height: 1.35;
            }

            .col-estado {
                width: 140px;
                white-space: nowrap;
            }

            .col-proveedor {
                width: 150px;
                white-space: normal;
            }

            .col-responsable {
                width: 170px;
                white-space: normal;
            }

            .col-prioridad {
                width: 115px;
                white-space: nowrap;
            }

            .col-creado {
                width: 135px;
                white-space: nowrap;
                color: #475569;
            }

            .col-url {
                width: 80px;
                white-space: nowrap;
                text-align: center;
            }

            .tickets-table a {
                color: #2563eb;
                text-decoration: none;
                font-weight: 700;
            }

            .tickets-table a:hover {
                text-decoration: underline;
            }
        </style>
    </head>
    <body>
        <div class="tickets-table-container">
            <table class="tickets-table">
                <thead>
                    <tr>
                        <th class="col-clave">Clave</th>
                        <th class="col-resumen">Resumen</th>
                        <th class="col-estado">Estado</th>
                        <th class="col-proveedor">Proveedor externo</th>
                        <th class="col-responsable">Responsable</th>
                        <th class="col-prioridad">Prioridad</th>
                        <th class="col-creado">Creado</th>
                        <th class="col-url">Jira</th>
                    </tr>
                </thead>
                <tbody>
    """)


    for _, row in df_table.iterrows():
        clave = safe_text(row.get("Clave", ""))
        resumen = safe_text(row.get("Resumen", ""))
        estado = render_status_badge(row.get("Estado", ""))
        proveedor = safe_text(row.get("Proveedor externo", ""))
        responsable = safe_text(row.get("Responsable", ""))
        prioridad = render_priority_badge(row.get("Prioridad", ""))
        creado = safe_text(row.get("Creado", ""))
        url = escape(str(row.get("URL", "")), quote=True)


        if url:
            jira_link = f'<a href="{url}" target="_blank" rel="noopener noreferrer">Abrir</a>'
        else:
            jira_link = ""

        html_parts.append(f"""
            <tr>
                <td class="col-clave">{clave}</td>
                <td class="col-resumen">{resumen}</td>
                <td class="col-estado">{estado}</td>
                <td class="col-proveedor">{proveedor}</td>
                <td class="col-responsable">{responsable}</td>
                <td class="col-prioridad">{prioridad}</td>
                <td class="col-creado">{creado}</td>
                <td class="col-url">{jira_link}</td>
            </tr>
        """)

    html_parts.append("""
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """)

    return "".join(html_parts)

if df_table.empty:
    st.info("No hay tickets que coincidan con los filtros seleccionados.")
else:
    components.html(
        render_tickets_table(df_table),
        height=760,
        scrolling=False
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

