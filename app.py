import streamlit as st
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
import re
from html import unescape, escape
import streamlit.components.v1 as components
import unicodedata
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


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
    "288762": "Vanderlande",
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

        if object_id:
            refs.append({
                "workspace_id": str(workspace_id or ""),
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

def classify_shift(created_dt):
    if pd.isna(created_dt):
        return "Sin fecha"

    hour = created_dt.hour

    if 7 <= hour < 15:
        return "Mañana"

    if 15 <= hour < 23:
        return "Tarde"

    return "Noche"


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
            "fields": ",".join(base_fields)
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
                None
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
    st.session_state["f_turno"] = []
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

df["_Creado_dt"] = pd.to_datetime(
    df["Creado"],
    format="%d/%m/%Y %H:%M",
    errors="coerce"
)

df["Turno"] = df["_Creado_dt"].apply(classify_shift)

def split_external_providers(value):
    if pd.isna(value):
        return []

    text = str(value).strip()

    if not text or text == "-":
        return []

    providers = re.split(r"\s*,\s*|\s*;\s*|\s*\|\s*", text)

    clean_providers = []

    for provider in providers:
        provider = provider.strip()

        if provider and provider != "-":
            clean_providers.append(provider)

    return list(dict.fromkeys(clean_providers))


df["_proveedores_lista"] = df["Proveedor externo"].apply(split_external_providers)

search_columns = [
    "Clave",
    "Resumen",
    "Estado",
    "Proveedor externo",
    "Responsable",
    "Creador",
    "Prioridad",
    "Tipo",
    "Proyecto",
    "Labels"
]

existing_search_columns = [
    col for col in search_columns
    if col in df.columns
]

df["_search_blob"] = (
    df[existing_search_columns]
    .fillna("")
    .astype(str)
    .agg(" ".join, axis=1)
    .str.lower()
)

st.sidebar.header("🔎 Filtros")

estados = sorted([x for x in df["Estado"].dropna().unique() if x])
proveedores = sorted(
    {
        proveedor
        for proveedores_ticket in df["_proveedores_lista"]
        for proveedor in proveedores_ticket
    }
)
turnos_orden = ["Mañana", "Tarde", "Noche", "Sin fecha"]

turnos = [
    turno for turno in turnos_orden
    if turno in df["Turno"].dropna().unique()
]
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
    get_current_user.clear()
    get_jira_issues.clear()
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

turno_sel = st.sidebar.multiselect(
    "Turno",
    turnos,
    key="f_turno"
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
    texto_lower = texto.strip().lower()

    if texto_lower:
        df_filtered = df_filtered[
            df_filtered["_search_blob"].str.contains(
                re.escape(texto_lower),
                na=False,
                regex=True
            )
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
    df_filtered = df_filtered[
        df_filtered["_proveedores_lista"].apply(
            lambda proveedores_ticket: any(
                proveedor in proveedores_ticket
                for proveedor in proveedor_sel
            )
        )
    ]

if turno_sel:
    df_filtered = df_filtered[df_filtered["Turno"].isin(turno_sel)]

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

seccion = st.radio(
    "Sección",
    [
        "📋 Tickets",
        "📊 Proveedores y tendencias",
        "📈 Panel Operativo"
    ],
    horizontal=True,
    label_visibility="collapsed"
)


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

@st.cache_data(ttl=300, show_spinner=False)
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
                overflow-x: hidden;
                border: 1px solid #e5e7eb;
                border-radius: 14px;
                background: #ffffff;
                box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08);
            }

            table.tickets-table {
                width: 100%;
                max-width: 100%;
                border-collapse: separate;
                border-spacing: 0;
                table-layout: fixed;
                font-size: 13px;
                background: #ffffff;
                box-sizing: border-box;
            }


            .tickets-table th {
                position: sticky;
                top: 0;
                background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
                z-index: 2;
                text-align: center;
                padding: 11px 8px;
                border-bottom: 1px solid #dce1e8;
                font-weight: 700;
                color: #334155;
                white-space: nowrap;
            }

            .tickets-table td {
                padding: 10px 8px;
                border-bottom: 1px solid #eef2f7;
                vertical-align: top;
                color: #1f2937;
                text-align: center;
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
                width: 500px;
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: normal;
                line-height: 1.35;
            }
            
            .col-estado {
                width: 130px;
                white-space: nowrap;
            }
            
            .col-proveedor {
                width: 140px;
                white-space: normal;
            }
            
            .col-responsable {
                width: 160px;
                white-space: normal;
            }
            
            .col-prioridad {
                width: 105px;
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

            .tickets-table td.col-clave,
            .tickets-table td.col-resumen {
                text-align: left;
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

if seccion == "📋 Tickets":
    st.markdown("**Tabla de tickets**")

    if df_table.empty:
        st.info("No hay tickets que coincidan con los filtros seleccionados.")
    else:
        components.html(
            render_tickets_table(df_table),
            height=760,
            scrolling=False
        )

elif seccion == "📈 Panel Operativo":
    st.markdown("**🚨 Panel Operativo**")

    st.info(
        "Panel de accesos rápidos para revisar puntos críticos operativos. "
        "Los enlaces se abren en una nueva pestaña y requieren red Mango o VPN cuando aplique."
    )

    def render_link_button(label, url, help_text=None):
        if help_text:
            st.caption(help_text)

        st.link_button(
            label,
            url,
            use_container_width=True
        )

    # -------------------------
    # CHECKLIST
    # -------------------------
    st.markdown("### ✅ Checklist")

    checklist_links = [
        {
            "label": "Revisión estado pasillos ST45 y ST46 — B2C",
            "url": "http://pappferagwcs01:6061/angularspa/stingray/outbounds",
            "help": "Consulta del estado de los pasillos ST45 y ST46 en B2C."
        },
        {
            "label": "Puntos críticos del Grafana B2C",
            "url": "https://pappgrafana01.intranet.mango.es/d/bessvfn69hq80f/b2c-pocket-sorter-analytical?orgId=1&from=now-24h&to=now&timezone=browser&refresh=1m",
            "help": "Dashboard analítico B2C Pocket Sorter con refresco cada minuto."
        },
        {
            "label": "Revisión estado reposiciones B2C — Macrolet",
            "url": "http://pappferagwcs01:6061/angularspa/shuttle-psorders/in-progress/sku",
            "help": "Seguimiento de reposiciones en curso por SKU."
        },
    ]

    checklist_cols = st.columns(3)

    for idx, item in enumerate(checklist_links):
        with checklist_cols[idx % 3]:
            render_link_button(
                item["label"],
                item["url"],
                item["help"]
            )

    st.divider()

    # -------------------------
    # GRAFANA
    # -------------------------
    st.markdown("### 📈 Grafana")

    grafana_links = {
        "General": [
            {
                "label": "Alertas procesos logísticos — B2B/B2C",
                "url": "https://pappgrafana01.intranet.mango.es/d/50215d42-0a24-4c39-86f0-dff481543616/b2b2b-b2c-alertas-procesos-logisticos?orgId=1&from=now-12h&to=now&timezone=browser&refresh=30s",
                "help": "Vista general de alertas de procesos logísticos con refresco cada 30 segundos."
            },
            {
                "label": "Procesos logísticos — Picking / Sorter S1",
                "url": "https://pappgrafana01.intranet.mango.es/d/beh2sd2ik2ha8a/b2b2b-b2c-procesos-logisticos?orgId=1&from=now-12h&to=now&timezone=browser&var-Tipo=Picking&var-Estado=$__all&var-Origen=$__all&var-Destino=Sorter_S1&var-Prioridad=$__all&var-Group_by=origen&var-plc10_origen=$__all&var-plc10_destino=$__all&var-plc10_group_by=origen_destino&refresh=1m",
                "help": "Procesos logísticos filtrados por Picking y destino Sorter S1."
            },
        ],
        "B2C": [
            {
                "label": "B2C Pocket Sorter Analytical",
                "url": "https://pappgrafana01.intranet.mango.es/d/bessvfn69hq80f/b2c-pocket-sorter-analytical?orgId=1&from=now-24h&to=now&timezone=browser&refresh=1m",
                "help": "Dashboard analítico de B2C Pocket Sorter."
            },
        ],
        "Expediciones": [
            {
                "label": "B2B E3 Expediciones — Métricas",
                "url": "https://pappgrafana01.intranet.mango.es/d/belc9wewp5tz4b/b2b-e3-expediciones-metricas?orgId=1&from=now-24h&to=now&timezone=browser&var-Rechazo=$__all&var-Rampas=$__all&var-Playas=$__all&var-Subrampa=$__all&refresh=5m",
                "help": "Métricas de expediciones, rampas, playas, subrampas y rechazos."
            },
        ],
        "Miniload": [
            {
                "label": "B2B Miniload — Cajas posibles",
                "url": "https://pappgrafana01.intranet.mango.es/d/aexjkawslh9mod/b2b-miniload?orgId=1&from=now-24h&to=now&timezone=browser&var-Metrica=cajas_posibles&var-Tipo_ubicacion=$__all&var-Pasillo=$__all&var-Zona=$__all&var-Tipo_bloque=$__all&refresh=15m",
                "help": "Dashboard B2B Miniload filtrado por métrica cajas posibles."
            },
        ],
    }

    for section_name, links in grafana_links.items():
        with st.expander(section_name, expanded=True):
            grafana_cols = st.columns(2)

            for idx, item in enumerate(links):
                with grafana_cols[idx % 2]:
                    render_link_button(
                        item["label"],
                        item["url"],
                        item["help"]
                    )


def apply_chart_style(ax):
    ax.set_facecolor("#ffffff")
    ax.figure.set_facecolor("#ffffff")

    ax.grid(
        axis="x",
        linestyle="--",
        alpha=0.18,
        color="#64748b"
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#e5e7eb")
    ax.spines["bottom"].set_color("#e5e7eb")

    ax.tick_params(
        axis="both",
        labelsize=9,
        colors="#475569"
    )

    ax.xaxis.label.set_color("#334155")
    ax.yaxis.label.set_color("#334155")


def render_static_horizontal_bar_chart(
    series,
    xlabel="Tickets",
    color="#2563eb",
    max_items=12,
    fig_width=7.5,
    fig_height=4.2
):
    if series is None or series.empty:
        st.info("No hay datos para generar el gráfico.")
        return

    chart_data = series.copy()
    chart_data = chart_data.sort_values(ascending=True).tail(max_items)

    chart_data.index = chart_data.index.map(str)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    bars = ax.barh(
        chart_data.index,
        chart_data.values,
        color=color,
        alpha=0.88
    )

    ax.set_xlabel(xlabel)
    ax.set_ylabel("")

    apply_chart_style(ax)

    max_value = chart_data.max()

    for bar in bars:
        width = bar.get_width()
        ax.text(
            width + max_value * 0.015,
            bar.get_y() + bar.get_height() / 2,
            f"{int(width)}",
            va="center",
            ha="left",
            fontsize=9,
            color="#334155",
            fontweight="bold"
        )

    ax.set_xlim(0, max_value * 1.15 if max_value > 0 else 1)

    fig.tight_layout()

    st.pyplot(fig, clear_figure=True)


def render_static_daily_trend_chart(series):
    if series is None or series.empty:
        st.info("No hay datos para generar la tendencia diaria.")
        return

    chart_data = series.copy()
    chart_data.index = pd.to_datetime(chart_data.index)

    fig, ax = plt.subplots(figsize=(7.5, 4.2))

    ax.plot(
        chart_data.index,
        chart_data.values,
        color="#7c3aed",
        linewidth=2.5,
        marker="o",
        markersize=4
    )

    ax.fill_between(
        chart_data.index,
        chart_data.values,
        color="#7c3aed",
        alpha=0.12
    )

    ax.set_xlabel("Día")
    ax.set_ylabel("Tickets")

    ax.grid(
        axis="y",
        linestyle="--",
        alpha=0.22,
        color="#64748b"
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#e5e7eb")
    ax.spines["bottom"].set_color("#e5e7eb")

    ax.tick_params(
        axis="both",
        labelsize=9,
        colors="#475569"
    )

    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))

    plt.setp(
        ax.get_xticklabels(),
        rotation=35,
        ha="right"
    )

    max_value = chart_data.max()

    if max_value > 0:
        ax.set_ylim(0, max_value * 1.18)

    fig.tight_layout()

    st.pyplot(fig, clear_figure=True)

@st.cache_data(ttl=300, show_spinner=False)
def render_static_html_table(df_table, url_column="URL", max_height=None):

    if df_table is None or df_table.empty:
        return ""

    visible_columns = list(df_table.columns)

    center_columns = set()

    for column in visible_columns:
        if pd.api.types.is_numeric_dtype(df_table[column]):
            center_columns.add(column)

        if "%" in str(column):
            center_columns.add(column)

    wrapper_classes = "static-table-wrapper"

    wrapper_style = ""

    if max_height:
        wrapper_classes += " scrollable-static-table"
        wrapper_style = (
            f'style="max-height: {int(max_height)}px; '
            f'overflow-y: auto; '
            f'overflow-x: hidden;"'
        )

    html = """
    <style>
        .static-table-wrapper {
            width: 100%;
            overflow: visible;
            user-select: none;
            margin-top: 0.5rem;
            margin-bottom: 1.5rem;
            border: 1px solid #e5e7eb;
            border-radius: 14px;
            background: #ffffff;
            box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08);
        }

        .scrollable-static-table {
            overflow-y: auto;
            overflow-x: hidden;
        }

        .static-table {
            width: 100%;
            border-collapse: collapse;
            background: #ffffff;
            font-size: 13px;
        }

        .static-table thead tr {
            background: #f8fafc;
            border-bottom: 1px solid #e5e7eb;
        }

        .static-table th {
            padding: 11px 12px;
            text-align: left;
            color: #334155;
            font-weight: 700;
            white-space: nowrap;
            background: #f8fafc;
        }

        .scrollable-static-table .static-table th {
            position: sticky;
            top: 0;
            z-index: 2;
        }

        .static-table td {
            padding: 10px 12px;
            border-bottom: 1px solid #f1f5f9;
            color: #475569;
            vertical-align: top;
        }

        .static-table tbody tr:last-child td {
            border-bottom: none;
        }

        .static-table tbody tr:nth-child(even) {
            background: #fafafa;
        }

        .static-table .center-cell {
            text-align: center;
            font-variant-numeric: tabular-nums;
        }

        .static-table .url-cell {
            text-align: center;
            white-space: nowrap;
        }

        .static-table .open-ticket-button {
            color: #2563eb !important;
            text-decoration: none;
            font-weight: 700;
            background: transparent;
            padding: 0;
            border-radius: 0;
            font-size: 13px;
            cursor: pointer;
        }

        .static-table .open-ticket-button:hover {
            color: #2563eb !important;
            text-decoration: underline;
        }

        .static-table .empty-url {
            color: #94a3b8;
        }
    </style>
    """

    html += f'<div class="{wrapper_classes}" {wrapper_style}>'
    html += '<table class="static-table">'

    html += "<thead><tr>"

    for column in visible_columns:
        th_class = ""

        if column in center_columns or column == url_column:
            th_class = ' class="center-cell"'

        html += f"<th{th_class}>{escape(str(column))}</th>"

    html += "</tr></thead>"

    html += "<tbody>"

    for _, row in df_table.iterrows():
        html += "<tr>"

        for column in visible_columns:
            value = row[column]

            if pd.isna(value):
                value = ""

            if column == url_column:
                url = str(value).strip()

                if url and url != "-":
                    cell_html = (
                        f'<a class="open-ticket-button" '
                        f'href="{escape(url, quote=True)}" '
                        f'target="_blank" '
                        f'rel="noopener noreferrer">Abrir</a>'
                    )
                else:
                    cell_html = '<span class="empty-url">-</span>'

                html += f'<td class="url-cell">{cell_html}</td>'

            else:
                cell_class = ""

                if column in center_columns:
                    cell_class = ' class="center-cell"'

                html += f"<td{cell_class}>{escape(str(value))}</td>"

        html += "</tr>"

    html += "</tbody>"
    html += "</table>"
    html += "</div>"

    return html


if seccion == "📊 Proveedores y tendencias":
    st.markdown("**Resumen por proveedor externo**")
    st.caption("Los datos de esta pestaña respetan los filtros seleccionados en la barra lateral.")

    df_provider = df_filtered.copy()

    if df_provider.empty:
        st.info("No hay datos para mostrar con los filtros actuales.")
    else:
        df_provider["Proveedor externo"] = (
            df_provider["Proveedor externo"]
            .fillna("-")
            .astype(str)
            .str.strip()
            .replace("", "-")
        )

        estado_norm = (
            df_provider["Estado"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )

        prioridad_norm = (
            df_provider["Prioridad"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )

        responsable_norm = (
            df_provider["Responsable"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        estados_cerrados = {
            "resuelta",
            "resuelto",
            "resolved",
            "done",
            "closed",
            "cerrado",
            "cerrada",
            "cancelado",
            "cancelada",
            "canceled",
            "cancelled"
        }

        estados_escalados = {
            "escalated",
            "escalado",
            "escalada"
        }

        prioridades_altas = {
            "highest",
            "high",
            "alta",
            "muy alta",
            "crítica",
            "critica"
        }

        df_provider["_abierto"] = ~estado_norm.isin(estados_cerrados)
        df_provider["_escalado"] = estado_norm.isin(estados_escalados)
        df_provider["_prioridad_alta"] = prioridad_norm.isin(prioridades_altas)
        df_provider["_sin_asignar"] = responsable_norm.isin(["", "Sin asignar"])

        if "_proveedores_lista" not in df_provider.columns:
            df_provider["_proveedores_lista"] = df_provider["Proveedor externo"].apply(
                split_external_providers
            )

        df_provider_exploded = (
            df_provider
            .explode("_proveedores_lista")
            .rename(columns={"_proveedores_lista": "Proveedor"})
        )

        df_provider_exploded = df_provider_exploded.dropna(subset=["Proveedor"])

        df_provider_exploded["Proveedor"] = (
            df_provider_exploded["Proveedor"]
            .astype(str)
            .str.strip()
        )

        df_provider_exploded = df_provider_exploded[
            df_provider_exploded["Proveedor"] != ""
        ].copy()

        df_provider_exploded = df_provider_exploded.drop_duplicates(
            subset=["Clave", "Proveedor"]
        )

        if df_provider_exploded.empty:
            provider_summary = pd.DataFrame(columns=[
                "Proveedor externo",
                "Tickets",
                "Prioridad Low",
                "Prioridad Medium",
                "Prioridad High",
                "Prioridad Highest",
                "% tickets a proveedor"
            ])
        else:
            prioridad_provider_norm = (
                df_provider_exploded["Prioridad"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.lower()
            )
        
            df_provider_exploded["_prioridad_low"] = prioridad_provider_norm.eq("low")
            df_provider_exploded["_prioridad_medium"] = prioridad_provider_norm.eq("medium")
            df_provider_exploded["_prioridad_high"] = prioridad_provider_norm.eq("high")
            df_provider_exploded["_prioridad_highest"] = prioridad_provider_norm.eq("highest")
        
            provider_summary = (
                df_provider_exploded
                .groupby("Proveedor", dropna=False)
                .agg(
                    Tickets=("Clave", "nunique"),
                    **{
                        "Prioridad Low": ("_prioridad_low", "sum"),
                        "Prioridad Medium": ("_prioridad_medium", "sum"),
                        "Prioridad High": ("_prioridad_high", "sum"),
                        "Prioridad Highest": ("_prioridad_highest", "sum"),
                    }
                )
                .reset_index()
                .rename(columns={"Proveedor": "Proveedor externo"})
            )
        
            total_tickets_abiertos_a_proveedor = int(provider_summary["Tickets"].sum())
        
            provider_summary["% tickets a proveedor"] = provider_summary["Tickets"].apply(
                lambda tickets: (
                    f"{tickets / total_tickets_abiertos_a_proveedor * 100:.1f}%"
                    if total_tickets_abiertos_a_proveedor > 0
                    else "0.0%"
                )
            )
        
            provider_summary = provider_summary[
                [
                    "Proveedor externo",
                    "Tickets",
                    "Prioridad Low",
                    "Prioridad Medium",
                    "Prioridad High",
                    "Prioridad Highest",
                    "% tickets a proveedor"
                ]
            ].sort_values(
                by="Tickets",
                ascending=False
            )

        total_proveedores = provider_summary["Proveedor externo"].nunique()

        tickets_sin_proveedor = int(
            df_provider["_proveedores_lista"].apply(len).eq(0).sum()
        )

        if provider_summary.empty:
            proveedor_top = "Sin proveedor"
            tickets_top = 0
            total_escalados = 0
        else:
            proveedor_top = provider_summary.iloc[0]["Proveedor externo"]
            tickets_top = int(provider_summary.iloc[0]["Tickets"])
            total_escalados = int(df_provider["_escalado"].sum())

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)

        kpi1.metric("Proveedores reales", total_proveedores)
        kpi2.metric("Proveedor con más tickets", proveedor_top, f"{tickets_top} tickets")
        kpi3.metric("Tickets escalados", total_escalados)
        kpi4.metric("Sin proveedor externo", tickets_sin_proveedor)

        st.markdown("**Tabla resumen por proveedor**")

        if provider_summary.empty:
            st.info("No hay proveedores externos asignados en los tickets filtrados.")
        else:
            st.markdown(
                render_static_html_table(
                    provider_summary,
                    url_column=None
                ),
                unsafe_allow_html=True
            )

        st.markdown("---")

        st.markdown("**Agrupación por proveedor externo**")

        provider_options = provider_summary["Proveedor externo"].tolist()

        if not provider_options:
            st.info("No hay proveedores externos asignados en los tickets filtrados.")
        else:
            selected_provider = st.selectbox(
                "Selecciona un proveedor para ver sus tickets",
                provider_options
            )

            provider_detail_keys = df_provider_exploded.loc[
                df_provider_exploded["Proveedor"] == selected_provider,
                "Clave"
            ].unique()

            provider_detail = df_provider[
                df_provider["Clave"].isin(provider_detail_keys)
            ].copy()

            detail_columns = [
                "Clave",
                "Resumen",
                "Estado",
                "Proveedor externo",
                "Responsable",
                "Prioridad",
                "Creado",
                "Actualizado",
                "URL"
            ]

            detail_columns = [
                col for col in detail_columns
                if col in provider_detail.columns
            ]

            detail_max_height = 520 if len(provider_detail) > 20 else None

            st.markdown(
                render_static_html_table(
                    provider_detail[detail_columns],
                    url_column="URL",
                    max_height=detail_max_height
                ),
                unsafe_allow_html=True
            )

        st.markdown("---")

        st.markdown("**Dashboard de tendencias**")

        trend_col1, trend_col2 = st.columns(2)

        with trend_col1:
            st.markdown("**Tickets por proveedor**")

            if provider_summary.empty:
                st.info("No hay proveedores externos para generar el gráfico.")
            else:
                tickets_by_provider = (
                    provider_summary
                    .set_index("Proveedor externo")["Tickets"]
                    .sort_values(ascending=False)
                )

                render_static_horizontal_bar_chart(
                    tickets_by_provider,
                    xlabel="Tickets",
                    color="#2563eb"
                )
                


        with trend_col2:
            st.markdown("**Tickets por estado**")
        
            tickets_by_status = (
                df_provider
                .groupby("Estado")["Clave"]
                .count()
                .sort_values(ascending=False)
            )
        
            render_static_horizontal_bar_chart(
                tickets_by_status,
                xlabel="Tickets",
                color="#10b981"
            )
        

        trend_col3, trend_col4 = st.columns(2)

        with trend_col3:
            st.markdown("**Tickets por prioridad**")
        
            tickets_by_priority = (
                df_provider
                .groupby("Prioridad")["Clave"]
                .count()
                .sort_values(ascending=False)
            )
        
            render_static_horizontal_bar_chart(
                tickets_by_priority,
                xlabel="Tickets",
                color="#f97316"
            )

        with trend_col4:
            st.empty()

        st.markdown("---")

        trend_col5, trend_col6 = st.columns(2)

        with trend_col5:
            st.markdown("**Tickets creados por día**")
        
            df_trend = df_provider.dropna(subset=["_Creado_dt"]).copy()
        
            if df_trend.empty:
                st.info("No hay fechas válidas para generar la tendencia diaria.")
            else:
                df_trend["Día"] = df_trend["_Creado_dt"].dt.date
        
                tickets_by_day = (
                    df_trend
                    .groupby("Día")["Clave"]
                    .count()
                    .sort_index()
                )
        
                render_static_daily_trend_chart(tickets_by_day)

        with trend_col6:
            st.markdown("**Tickets creados por año**")

            df_year = df_provider.dropna(subset=["_Creado_dt"]).copy()

            if df_year.empty:
                st.info("No hay fechas válidas para generar el gráfico por año.")
            else:
                df_year["Año"] = df_year["_Creado_dt"].dt.year.astype(str)

                tickets_by_year = (
                    df_year
                    .groupby("Año")["Clave"]
                    .count()
                    .sort_index()
                )

                render_static_horizontal_bar_chart(
                    tickets_by_year,
                    xlabel="Tickets",
                    color="#7c3aed"
                )


                st.markdown("---")

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
