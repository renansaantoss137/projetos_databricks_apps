import os
import re
import json
import time
import copy
import base64
import hashlib
import functools
import threading
import psycopg2
import psycopg2.extras
import requests as http_requests
from psycopg2 import pool
from flask import Flask, render_template, redirect, url_for, request, flash, abort, jsonify
from databricks.sdk.core import Config

# Carrega variáveis do .env em desenvolvimento local
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv não instalado — ok em produção

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'space-portal-secret-key-198273')
app.config['TEMPLATES_AUTO_RELOAD'] = True


# ─────────────────────────────────────────────
#  OBO AUTHORIZATION — Azure AD & SCIM Group Check
# ─────────────────────────────────────────────

# Object ID of the Azure AD group that grants access to /admin.
ADMIN_GROUP_ID = os.environ.get('ADMIN_GROUP_ID', '')

# Caches to avoid hammering SCIM / Graph API
_admin_cache: dict[str, tuple[bool, float]] = {}
_admin_cache_lock = threading.Lock()

_user_groups_cache: dict[str, tuple[list[str], float]] = {}
_user_groups_cache_lock = threading.Lock()

_CACHE_TTL_SECONDS = 300  # 5 minutes


def _token_hash(token: str) -> str:
    """Return a short hash of the token to use as a cache key."""
    return hashlib.sha256(token.encode()).hexdigest()[:32]


def get_user_groups_from_obo(obo_token: str) -> list[str]:
    """Retrieve group memberships (display names and Object IDs) using the user's OBO access token.

    Queries Microsoft Graph API (/v1.0/me/transitiveMemberOf) first using the user's bearer token,
    and falls back to Databricks SCIM API (current_user.me()).
    Does NOT require Service Principal (AZURE_CLIENT_ID / SECRET) credentials.
    """
    if not obo_token:
        return []

    key = _token_hash(obo_token)
    now = time.time()

    with _user_groups_cache_lock:
        cached = _user_groups_cache.get(key)
        if cached is not None:
            groups, expires_at = cached
            if now < expires_at:
                return groups

    groups = []

    # 1. Direct Microsoft Graph API using the user's OBO Token
    try:
        headers = {
            'Authorization': f'Bearer {obo_token}',
            'Accept': 'application/json'
        }
        res = http_requests.get('https://graph.microsoft.com/v1.0/me/transitiveMemberOf?$select=id,displayName', headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            for item in data.get('value', []):
                d_name = item.get('displayName')
                g_id = item.get('id')
                if d_name:
                    groups.append(d_name)
                if g_id:
                    groups.append(g_id)
            if groups:
                print(f"[OBO GRAPH] User groups fetched via MS Graph OBO: {groups}")
    except Exception as graph_err:
        print(f"[OBO GRAPH] MS Graph OBO check skipped/failed: {graph_err}")

    # 2. Databricks SCIM API using OBO Token
    if not groups:
        try:
            from databricks.sdk import WorkspaceClient
            from databricks.sdk.core import Config

            host = os.environ.get("DATABRICKS_HOST")
            if not host:
                try:
                    host = Config().host
                except Exception:
                    pass

            if host:
                w = WorkspaceClient(auth_type='pat', token=obo_token, host=host)
                me = w.current_user.me()
                if me.groups:
                    for g in me.groups:
                        if g.display:
                            groups.append(g.display)
                        if g.value:
                            groups.append(str(g.value))
                    print(f"[OBO SCIM] User {me.user_name} group list fetched: {groups}")
        except Exception as scim_err:
            print(f"[OBO SCIM] Databricks SCIM verification failed: {scim_err}")

    # Cache result
    with _user_groups_cache_lock:
        _user_groups_cache[key] = (groups, now + _CACHE_TTL_SECONDS)

    return groups


def check_admin_email(email: str) -> bool:
    """Check if the email exists in the space_portal.admin_users table."""
    if not email:
        return False
    email = email.strip().lower()
    
    if LOCAL_MODE:
        return email in ['vitor.saes@grupobimbo.com', 'bruno.fellipe@grupobimbo.com', 'renan.ferreira@grupobimbo.com']
        
    ensure_schema()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM space_portal.admin_users WHERE LOWER(email) = %s)",
                (email,)
            )
            row = cur.fetchone()
            return row[0] if row else False
    except Exception as e:
        print(f"[ERROR] Database admin email verification failed: {e}")
        return False
    finally:
        release_conn(conn)


def get_current_user_email() -> str:
    """Get the current user's email based on environment headers or cookies (LOCAL_MODE)."""
    if LOCAL_MODE:
        return request.cookies.get('mock_user_email') or 'renan.ferreira@grupobimbo.com'
    return (
        request.headers.get('x-forwarded-email') or
        request.headers.get('x-forwarded-preferred-username') or
        request.headers.get('x-forwarded-user') or
        'user@example.com'
    )


def get_current_user_groups() -> list[str]:
    """Get list of groups the current user is member of (OBO Token -> Forwarded Header -> Local/Mock)."""
    # 1. Get OBO token from headers
    obo_token = (
        request.headers.get('x-forwarded-access-token', '').strip() or
        request.headers.get('authorization', '').replace('Bearer ', '').strip()
    )
    if obo_token:
        groups = get_user_groups_from_obo(obo_token)
        if groups:
            return groups

    # 2. Check x-forwarded-groups header (if provided by proxy)
    forwarded_groups = request.headers.get('x-forwarded-groups', '')
    if forwarded_groups:
        return [g.strip() for g in forwarded_groups.split(',') if g.strip()]

    # 3. Local mode or mock cookies/env fallback
    if LOCAL_MODE:
        groups_str = request.cookies.get('mock_user_groups') or os.environ.get('MOCK_USER_GROUPS', '')
        if groups_str:
            return [g.strip() for g in groups_str.split(',') if g.strip()]

    return []


def is_current_user_admin() -> bool:
    """Check if the current user is an administrator."""
    if LOCAL_MODE:
        mock_is_admin = request.cookies.get('mock_is_admin')
        if mock_is_admin is not None:
            return mock_is_admin == 'true'
    user_email = get_current_user_email()
    return check_admin_email(user_email)


def user_has_access(required_group: str) -> bool:
    """Check if user has access to a resource based on required group.
    
    A restrição de acesso por área/grupo foi desativada:
    todos os usuários possuem acesso livre a todas as áreas e dashboards.
    """
    return True


def require_admin_group(fn):
    """Flask decorator that restricts a route to administrators in the email list."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_current_user_admin():
            user_email = get_current_user_email()
            print(f"[AUTH] Access denied to {request.path} for user: {user_email}")
            return render_template('403.html', user_email=user_email), 403
        
        print(f"[AUTH] Admin access granted for {request.path} (User: {get_current_user_email()})")
        return fn(*args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────
#  LAKEBASE — connection pool & token refresh
# ─────────────────────────────────────────────

# When deployed on Databricks Apps the platform injects:
#   PGHOST, PGPORT, PGDATABASE, PGUSER, PGSSLMODE, LAKEBASE_ENDPOINT
# For local development set those vars (or use a .env file).

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()
_token_refresh_interval = 45 * 60  # 45 minutes (tokens expire after 1 hour)

# ─────────────────────────────────────────────
#  LOCAL MODE — runs without Lakebase
# ─────────────────────────────────────────────
# Set LOCAL_MODE=true (or leave PGHOST unset) to skip all DB calls and serve
# data from DEFAULT_AREA_DATA in memory. Useful for local UI development.
LOCAL_MODE = os.environ.get('LOCAL_MODE', '').lower() in ('1', 'true', 'yes') or not os.environ.get('PGHOST', '')
if LOCAL_MODE:
    print("[INFO] Running in LOCAL_MODE — Lakebase is disabled. Data served from memory.")

# In-memory store used when LOCAL_MODE is active (populated on first load)
_local_data: dict | None = None
_local_data_lock = threading.Lock()

_LOCAL_SIDEBAR_APPS_FILE = os.path.join(os.path.dirname(__file__), 'local_sidebar_apps.json')
_local_sidebar_apps_lock = threading.Lock()

DEFAULT_SIDEBAR_APPS = [
    {
        'app_key': 'fermenta',
        'title': 'Fermenta',
        'link': 'https://apps.powerapps.com/play/e/b6c0e096-cfa5-4bc7-bef0-da5c2d6cb2a2/a/9a134639-f29d-4867-affc-c15b8cf658c4?tenantId=973ba820-4a58-4246-84bf-170e50b3152a&hint=e330137b-933b-4432-8f94-201d3e1ef682&sourcetime=1764093426234&source=teamsLinkUnfurling',
        'hidden': False,
        'icon': '/static/images/fermenta_card.jpg'
    }
]


def _get_token() -> str:
    """Obtain a fresh OAuth token for the Lakebase endpoint."""
    endpoint_path = os.environ.get("LAKEBASE_ENDPOINT", "")
    if not endpoint_path:
        raise RuntimeError("LAKEBASE_ENDPOINT env var is not set.")
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    cred = w.postgres.generate_database_credential(endpoint_path)
    return cred.token


def _build_pool() -> psycopg2.pool.ThreadedConnectionPool:
    token = _get_token()
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=5,
        host=os.environ.get("PGHOST", ""),
        port=int(os.environ.get("PGPORT", 5432)),
        dbname=os.environ.get("PGDATABASE", "databricks_postgres"),
        user=os.environ.get("PGUSER", ""),
        password=token,
        sslmode=os.environ.get("PGSSLMODE", "require"),
        connect_timeout=10,
    )


def _refresh_pool_periodically():
    """Background thread that recreates the pool before the token expires."""
    while True:
        time.sleep(_token_refresh_interval)
        global _pool
        with _pool_lock:
            try:
                old = _pool
                _pool = _build_pool()
                if old:
                    old.closeall()
                print("Lakebase token refreshed.")
            except Exception as exc:
                print(f"Lakebase token refresh failed: {exc}")


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = _build_pool()
                t = threading.Thread(target=_refresh_pool_periodically, daemon=True)
                t.start()
    return _pool


def get_conn():
    return get_pool().getconn()


def release_conn(conn):
    get_pool().putconn(conn)


# ─────────────────────────────────────────────
#  SCHEMA INIT — runs once on first request
# ─────────────────────────────────────────────

SCHEMA_INITIALIZED = False
SCHEMA_LOCK = threading.Lock()

CREATE_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS space_portal;

CREATE TABLE IF NOT EXISTS space_portal.admin_users (
    email VARCHAR(256) PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS space_portal.area (
    area_key  VARCHAR(64) PRIMARY KEY,
    title_key VARCHAR(128) NOT NULL,
    tagline   TEXT,
    icon      VARCHAR(64),
    hidden    BOOLEAN DEFAULT FALSE,
    required_group VARCHAR(256),
    about     JSONB
);

CREATE TABLE IF NOT EXISTS space_portal.item (
    id        SERIAL PRIMARY KEY,
    area_key  VARCHAR(64) NOT NULL REFERENCES space_portal.area(area_key) ON DELETE CASCADE,
    type      VARCHAR(16) NOT NULL CHECK (type IN ('dashboard', 'application')),
    title     VARCHAR(256) NOT NULL,
    title_key VARCHAR(256) NOT NULL,
    icon      VARCHAR(64),
    link      VARCHAR(512),
    link_mobile VARCHAR(512),
    hidden    BOOLEAN DEFAULT FALSE,
    required_group VARCHAR(256),
    UNIQUE(area_key, type, title_key)
);

CREATE TABLE IF NOT EXISTS space_portal.sidebar_apps (
    app_key   VARCHAR(64) PRIMARY KEY,
    title     VARCHAR(128) NOT NULL,
    link      VARCHAR(512) NOT NULL,
    hidden    BOOLEAN DEFAULT FALSE,
    icon      TEXT
);
ALTER TABLE space_portal.sidebar_apps ADD COLUMN IF NOT EXISTS icon TEXT;

CREATE TABLE IF NOT EXISTS space_portal.acessos_space (
    id          SERIAL PRIMARY KEY,
    user_email  VARCHAR(256),
    accessed_at TIMESTAMP DEFAULT NOW(),
    page_path   VARCHAR(512)
);

CREATE TABLE IF NOT EXISTS space_portal.sugestao_knn (
    email           VARCHAR(256) PRIMARY KEY,
    cargo           VARCHAR(256),
    relatorio_1     VARCHAR(256),
    espaco_1        VARCHAR(128),
    cod_1           VARCHAR(128),
    distancia_1     DOUBLE PRECISION,
    relatorio_2     VARCHAR(256),
    espaco_2        VARCHAR(128),
    cod_2           VARCHAR(128),
    distancia_2     DOUBLE PRECISION,
    relatorio_3     VARCHAR(256),
    espaco_3        VARCHAR(128),
    cod_3           VARCHAR(128),
    distancia_3     DOUBLE PRECISION,
    relatorio_4     VARCHAR(256),
    espaco_4        VARCHAR(128),
    cod_4           VARCHAR(128),
    distancia_4     DOUBLE PRECISION
);
"""

# Default seed data matching the original area_data.json structure
DEFAULT_AREA_DATA = {
    "geral": {
        "title_key": "Geral",
        "icon": "building-2",
        "hidden": False,
        "applications": [],
        "dashboards": [
            {
                "title": "Operational Discipline",
                "title_key": "operational_discipline",
                "icon": "file-text",
                "link": "https://prioridades-bb-8674310331778219.19.azure.databricksapps.com",
                "link_mobile": "",
                "hidden": False,
                "required_group": "Grupo_Executivos"
            }
        ],
        "required_group": ""
    },
    "people": {
        "title_key": "people",
        "tagline": "Gestão de Talentos, Cultura e Desenvolvimento de Pessoas no Grupo Bimbo",
        "about": {
            "description": "A área de Pessoas (Recursos Humanos) é responsável por atrair, desenvolver e valorizar os colaboradores do Grupo Bimbo. Focada em cultura organizacional, gestão do conhecimento e experiência do colaborador, a equipe impulsiona o crescimento contínuo de nossos talentos.",
            "pillars": [
                {
                    "icon": "users",
                    "title": "Gestão de Talentos & Atração",
                    "desc": "Recrutamento estratégico, programas de onboarding e desenvolvimento de planos de carreira."
                },
                {
                    "icon": "award",
                    "title": "T&D e Cultura Organizacional",
                    "desc": "Capacitações contínuas, universidade corporativa e fortalecimento da cultura Grupo Bimbo."
                },
                {
                    "icon": "heart",
                    "title": "Experiência & Bem-Estar",
                    "desc": "Clima organizacional, gestão de benefícios, saúde e qualidade de vida dos colaboradores."
                }
            ],
            "stats": [
                {
                    "label": "Colaboradores",
                    "value": "+5.000"
                },
                {
                    "label": "Satisfação & Clima",
                    "value": "98%"
                },
                {
                    "label": "Capacitações/Ano",
                    "value": "+120"
                }
            ],
            "techs": [
                "Workday",
                "SuccessFactors",
                "Power BI",
                "Microsoft Forms",
                "Azure AD"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 1
                    },
                    {
                        "name": "Portfólio",
                        "value": 1
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 2
                    },
                    {
                        "name": "Estratégia",
                        "value": 1
                    }
                ]
            }
        },
        "applications": [
            {
                "title": "Gestão de Aprovadores e Acessos",
                "title_key": "app_people_approvers",
                "icon": "shield-check",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Controle de Bônus Auto",
                "title_key": "app_people_bonus",
                "icon": "car",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Descrição de Cargos",
                "title_key": "app_people_job_desc",
                "icon": "clipboard-list",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Temporários",
                "title_key": "app_people_temp",
                "icon": "users",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Labour Executive",
                "title_key": "db_people_labour_exec",
                "icon": "users",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "People Analytics",
                "title_key": "db_people_analytics",
                "icon": "users",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "GEP",
                "title_key": "db_people_gep",
                "icon": "users",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Labour",
                "title_key": "db_people_labour",
                "icon": "users",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "users",
        "hidden": False,
        "required_group": ""
    },
    "commercial": {
        "title_key": "Commercial",
        "applications": [
            {
                "title": "Cadastro de Clientes",
                "title_key": "app_comm_cust",
                "icon": "user-plus",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Simulação de Preços",
                "title_key": "app_comm_price",
                "icon": "calculator",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Gestão de Contratos",
                "title_key": "app_comm_contr",
                "icon": "file-text",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Performance de Vendas",
                "title_key": "performance_de_vendas",
                "icon": "trending-up",
                "link": "https://prioridades-bb-8674310331778219.19.azure.databricksapps.com/",
                "link_mobile": "",
                "hidden": False,
                "required_group": "Grupo - Vendas"
            },
            {
                "title": "Faturamento Diário",
                "title_key": "db_comm_revenue",
                "icon": "bar-chart-3",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Metas e Comissões",
                "title_key": "db_comm_targets",
                "icon": "award",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Faturamento Diario",
                "title_key": "faturamento_diario",
                "icon": "trending-up",
                "link": "https://example.com",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "trending-up",
        "hidden": False,
        "required_group": "",
        "tagline": "Estratégia de Vendas, Execução de Mercado e Relacionamento com Clientes",
        "about": {
            "description": "A área Comercial lidera a estratégia de crescimento em vendas do Grupo Bimbo, garantindo forte presença no ponto de venda (PDV), metas regionais e relacionamento de alto valor com clientes e grandes contas.",
            "pillars": [
                {
                    "icon": "trending-up",
                    "title": "Estratégia de Vendas & Metas",
                    "desc": "Planejamento comercial, gestão de metas regionais e expansão de mercado."
                },
                {
                    "icon": "shopping-cart",
                    "title": "Execução no PDV & Trade",
                    "desc": "Gestão de loja, presença de marca e ativação eficiente dos canais de distribuição."
                },
                {
                    "icon": "users",
                    "title": "Relacionamento & Clientes",
                    "desc": "Parcerias estratégicas com Key Accounts e inteligência comercial."
                }
            ],
            "stats": [
                {
                    "label": "Pontos de Venda",
                    "value": "+100k"
                },
                {
                    "label": "Atingimento Meta",
                    "value": "99%"
                },
                {
                    "label": "Canais Ativos",
                    "value": "Omnichannel"
                }
            ],
            "techs": [
                "Salesforce",
                "Power BI",
                "Databricks",
                "Excel Advanced",
                "Azure AD"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 2
                    },
                    {
                        "name": "Portfólio",
                        "value": 2
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 1
                    },
                    {
                        "name": "Estratégia",
                        "value": 2
                    }
                ]
            }
        }
    },
    "marketing": {
        "title_key": "marketing",
        "applications": [
            {
                "title": "Criativo de Campanhas",
                "title_key": "app_mkt_campaign",
                "icon": "image",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Gerador de Links UTM",
                "title_key": "app_mkt_utm",
                "icon": "link",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Performance de Mídia",
                "title_key": "db_mkt_media",
                "icon": "line-chart",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "ROI de Marketing",
                "title_key": "db_mkt_roi",
                "icon": "coins",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Conversão de Funil",
                "title_key": "db_mkt_funnel",
                "icon": "filter",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "line-chart",
        "hidden": False,
        "required_group": "",
        "tagline": "Construção de Marcas, Campanhas e Inteligência de Mercado",
        "about": {
            "description": "A área de Marketing fortalece o posicionamento das marcas do Grupo Bimbo, conectando consumidores através de campanhas impactantes, análise de tendências de mercado e inteligência de dados.",
            "pillars": [
                {
                    "icon": "award",
                    "title": "Gestão de Marcas & Branding",
                    "desc": "Posicionamento estratégico das marcas Bimbo, Wickbold, Pullman e Ana Maria."
                },
                {
                    "icon": "target",
                    "title": "Campanhas & Mídia Digital",
                    "desc": "Estratégia de mídia, marketing de influenciadores e engajamento multi-canal."
                },
                {
                    "icon": "pie-chart",
                    "title": "Pesquisa & Consumer Insights",
                    "desc": "Estudo de comportamento do consumidor, pesquisas de mercado e inovação."
                }
            ],
            "stats": [
                {
                    "label": "Marcas Líderes",
                    "value": "+10"
                },
                {
                    "label": "Brand Awareness",
                    "value": "95%"
                },
                {
                    "label": "Estratégia",
                    "value": "Digital First"
                }
            ],
            "techs": [
                "Google Analytics",
                "Meta Ads",
                "Power BI",
                "Canva",
                "Databricks"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 2
                    },
                    {
                        "name": "Portfólio",
                        "value": 2
                    },
                    {
                        "name": "Autonomia",
                        "value": 2
                    },
                    {
                        "name": "Capacitação",
                        "value": 1
                    },
                    {
                        "name": "Estratégia",
                        "value": 1
                    }
                ]
            }
        }
    },
    "adm_finances": {
        "title_key": "adm_finances",
        "applications": [
            {
                "title": "Solicitação de Reembolso",
                "title_key": "app_fin_reimburse",
                "icon": "receipt",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Cadastro de Fornecedores",
                "title_key": "app_fin_vendors",
                "icon": "folder-plus",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Fluxo de Caixa",
                "title_key": "db_fin_cashflow",
                "icon": "trending-up",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Controle de Custos",
                "title_key": "db_fin_costs",
                "icon": "pie-chart",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Orçado vs Realizado",
                "title_key": "db_fin_budget",
                "icon": "scale",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Dashboard Teste Truncamento de Link Longo",
                "title_key": "dashboard_teste_truncamento_de_link_longo",
                "icon": "coins",
                "link": "https://app.powerbi.com/reportEmbed?reportId=12345678-1234-1234-1234-1234567890ab&autoAuth=True&ctid=87654321-4321-4321-4321-ba0987654321&config=eyJjbHVzdGVyVXJsIjoiaHR0cHM6Ly93YWJpLXVzLWVhc3QyLXJlZGlyZWN0LmFuYWx5c2lzLndpbmRvd3MubmV0LyJ9",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "coins",
        "hidden": False,
        "required_group": "",
        "tagline": "Gestão Financeira, Controladoria e Eficiência Operacional",
        "about": {
            "description": "A área de ADM & Finanças garante a saúde financeira e a sustentabilidade corporativa do Grupo Bimbo através de contabilidade rigorosa, gestão de caixa, governança fiscal e controle de custos.",
            "pillars": [
                {
                    "icon": "dollar-sign",
                    "title": "Controladoria & Contabilidade",
                    "desc": "Gestão fiscal, contábil e conformidade com normas financeiras e auditoria."
                },
                {
                    "icon": "credit-card",
                    "title": "Tesouraria & Fluxo de Caixa",
                    "desc": "Controle de capital de giro, contas a pagar/receber e gestão de liquidez."
                },
                {
                    "icon": "file-text",
                    "title": "Eficiência & Custos",
                    "desc": "Automação financeira, governança de despesas e otimização de custos corporativos."
                }
            ],
            "stats": [
                {
                    "label": "Auditoria Fiscal",
                    "value": "100% OK"
                },
                {
                    "label": "Resultado",
                    "value": "EBITDA Positivo"
                },
                {
                    "label": "ERP Central",
                    "value": "SAP S/4HANA"
                }
            ],
            "techs": [
                "SAP S/4HANA",
                "Power BI",
                "Excel Advanced",
                "Azure AD"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 1
                    },
                    {
                        "name": "Portfólio",
                        "value": 2
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 1
                    },
                    {
                        "name": "Estratégia",
                        "value": 2
                    }
                ]
            }
        }
    },
    "logistics": {
        "title_key": "logistics",
        "applications": [
            {
                "title": "Rastreio de Frota",
                "title_key": "app_log_tracking",
                "icon": "map-pin",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Escala de Motoristas",
                "title_key": "app_log_schedule",
                "icon": "calendar",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Indicadores de Frota (OEE)",
                "title_key": "db_log_oee",
                "icon": "truck",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Custos de Frete",
                "title_key": "db_log_freight",
                "icon": "dollar-sign",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Tempo de Espera (OTIF)",
                "title_key": "db_log_otif",
                "icon": "clock",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "truck",
        "hidden": False,
        "required_group": "",
        "tagline": "Malha Logística Inteligente, Frota e Entrega Eficiente",
        "about": {
            "description": "A área de Logística gerencia a malha de distribuição do Grupo Bimbo, garantindo roteirização eficiente, transporte seguro e pontualidade na entrega de produtos frescos em todos os pontos de venda.",
            "pillars": [
                {
                    "icon": "truck",
                    "title": "Gestão de Frotas & Transporte",
                    "desc": "Roteirização inteligente, frotas sustentáveis e entregas fracionadas com eficiência."
                },
                {
                    "icon": "map-pin",
                    "title": "Centros de Distribuição (CDs)",
                    "desc": "Operação de depósitos, expedição rápida e gestão de estoque em tempo real."
                },
                {
                    "icon": "clock",
                    "title": "SLA de Entrega & On-Time",
                    "desc": "Garantia de frescor dos produtos nas prateleiras dos clientes com alto OTIF."
                }
            ],
            "stats": [
                {
                    "label": "Centros Distribuição",
                    "value": "+50 CDs"
                },
                {
                    "label": "Nível de Serviço",
                    "value": "98.5% OTIF"
                },
                {
                    "label": "Roteirização",
                    "value": "IA Ativa"
                }
            ],
            "techs": [
                "SAP WMS",
                "TMS",
                "Power BI",
                "Databricks",
                "Azure"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 2
                    },
                    {
                        "name": "Portfólio",
                        "value": 1
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 2
                    },
                    {
                        "name": "Estratégia",
                        "value": 1
                    }
                ]
            }
        }
    },
    "rgm": {
        "title_key": "rgm",
        "applications": [
            {
                "title": "Otimização de Preços",
                "title_key": "app_rgm_price_opt",
                "icon": "sliders",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Simulador de Elasticidade",
                "title_key": "app_rgm_elasticity",
                "icon": "activity",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Margens de Categoria",
                "title_key": "db_rgm_margin",
                "icon": "bar-chart-3",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Análise de Mix de Vendas",
                "title_key": "db_rgm_mix",
                "icon": "pie-chart",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "bar-chart-3",
        "hidden": False,
        "required_group": "",
        "tagline": "Preificação Estratégica, Mix de Produtos e Otimização de Margem",
        "about": {
            "description": "A área de RGM (Revenue Growth Management) otimiza a lucratividade da empresa por meio de modelos avançados de preço elástico, eficácia promocional e arquitetura de portfólio por canal.",
            "pillars": [
                {
                    "icon": "dollar-sign",
                    "title": "Preificação & Promoções",
                    "desc": "Modelos elásticos de preços e mensuração do retorno sobre investimento promocional."
                },
                {
                    "icon": "bar-chart-3",
                    "title": "Gestão de Mix & Embalagens",
                    "desc": "Price Pack Architecture e otimização de margens por canal de vendas."
                },
                {
                    "icon": "target",
                    "title": "Lucratividade & Margem",
                    "desc": "Maximização da receita líquida unitária e expansão sustentável da margem."
                }
            ],
            "stats": [
                {
                    "label": "Expansão Margem",
                    "value": "+12%"
                },
                {
                    "label": "Preço Elástico",
                    "value": "Modelado"
                },
                {
                    "label": "ROI Promocional",
                    "value": "Otimizado"
                }
            ],
            "techs": [
                "Databricks",
                "Python",
                "Power BI",
                "SQL",
                "Excel"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 2
                    },
                    {
                        "name": "Portfólio",
                        "value": 2
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 1
                    },
                    {
                        "name": "Estratégia",
                        "value": 2
                    }
                ]
            }
        }
    },
    "supply_chain": {
        "title_key": "supply_chain",
        "applications": [
            {
                "title": "Planejamento de Demanda",
                "title_key": "app_sc_demand",
                "icon": "calendar-days",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Gestão de Rupturas",
                "title_key": "app_sc_ruptures",
                "icon": "alert-triangle",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Cobertura de Estoque",
                "title_key": "db_sc_inventory",
                "icon": "archive",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Desempenho de Fornecedores",
                "title_key": "db_sc_suppliers",
                "icon": "thumbs-up",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Tempo de Ciclo (Lead Time)",
                "title_key": "db_sc_leadtime",
                "icon": "clock",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Fill Rate",
                "title_key": "fill_rate",
                "icon": "archive",
                "link": "https://gestao-pedidos-8674310331778219.19.azure.databricksapps.com/",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "archive",
        "hidden": False,
        "required_group": "",
        "tagline": "Planejamento Integrado de Suprimentos, Demanda e Giro de Estoque",
        "about": {
            "description": "A área de Supply Chain orquestra a integração entre previsão de demanda, insumos e capacidade produtiva, reduzindo rupturas e garantindo a continuidade do fornecimento.",
            "pillars": [
                {
                    "icon": "boxes",
                    "title": "Planejamento de Demanda (S&OP)",
                    "desc": "Previsão de vendas integrada com a capacidade de produção e insumos de fábrica."
                },
                {
                    "icon": "refresh-cw",
                    "title": "Gestão de Estoque & Giro",
                    "desc": "Otimização de matérias-primas e produtos acabados com baixo nível de desperdício."
                },
                {
                    "icon": "layers",
                    "title": "Cadeia de Suprimentos Integrada",
                    "desc": "Sincronização entre fábrica, fornecedores e malha de distribuição."
                }
            ],
            "stats": [
                {
                    "label": "Acurácia Demanda",
                    "value": "99%"
                },
                {
                    "label": "Desperdício",
                    "value": "Mínimo"
                },
                {
                    "label": "S&OP",
                    "value": "Ativo"
                }
            ],
            "techs": [
                "SAP APO",
                "Databricks",
                "Power BI",
                "Python"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 2
                    },
                    {
                        "name": "Portfólio",
                        "value": 2
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 2
                    },
                    {
                        "name": "Estratégia",
                        "value": 1
                    }
                ]
            }
        }
    },
    "purchase": {
        "title_key": "purchase",
        "applications": [
            {
                "title": "Portal de Cotações",
                "title_key": "app_pur_quotes",
                "icon": "file-text",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Aprovação de Pedidos",
                "title_key": "app_pur_approvals",
                "icon": "check-square",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Savings de Compras",
                "title_key": "db_pur_savings",
                "icon": "piggy-bank",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Painel de Spend Analysis",
                "title_key": "db_pur_spend",
                "icon": "credit-card",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "file-text",
        "hidden": False,
        "required_group": "",
        "tagline": "Gestão Estratégica de Insumos, Fornecedores e Savings",
        "about": {
            "description": "A área de Compras (Purchasing) é responsável por negociar matérias-primas essenciais, embalagens, energia e serviços corporativos, gerando economia sustentável e parcerias com fornecedores.",
            "pillars": [
                {
                    "icon": "shopping-bag",
                    "title": "Strategic Sourcing & Commodities",
                    "desc": "Negociação estratégica de trigo, embalagens, energia e insumos agroindustriais."
                },
                {
                    "icon": "handshake",
                    "title": "Gestão de Fornecedores",
                    "desc": "Homologação de parceiros, avaliação de SLAs e compliance com a sustentabilidade."
                },
                {
                    "icon": "trending-down",
                    "title": "Savings & Eficiência",
                    "desc": "Geração contínua de economia de custos e gestão eficiente do Spend corporativo."
                }
            ],
            "stats": [
                {
                    "label": "Savings Gerados",
                    "value": "+R$ 15M"
                },
                {
                    "label": "Fornecedores Ativos",
                    "value": "+300"
                },
                {
                    "label": "Sourcing",
                    "value": "Estratégico"
                }
            ],
            "techs": [
                "SAP Ariba",
                "Power BI",
                "Excel Advanced",
                "Azure AD"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 1
                    },
                    {
                        "name": "Portfólio",
                        "value": 1
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 1
                    },
                    {
                        "name": "Estratégia",
                        "value": 2
                    }
                ]
            }
        }
    },
    "dna": {
        "title_key": "dna",
        "tagline": "Data & Analytics — Transformando dados em decisões inteligentes no Grupo Bimbo",
        "about": {
            "description": "A área de Data & Analytics (DNA) é responsável por estruturar, governar e potencializar o ecossistema de dados da empresa. Combinando a arquitetura moderna de Databricks Lakehouse, Unity Catalog e ferramentas avançadas de self-service BI, o time de DNA gera inteligência estratégica para todas as operações do Grupo Bimbo.",
            "pillars": [
                {
                    "icon": "database",
                    "title": "Lakehouse & Engenharia",
                    "desc": "Pipelines de dados escaláveis, processamento em tempo real com Delta Lake e arquitetura moderna."
                },
                {
                    "icon": "shield-check",
                    "title": "Governança & Qualidade",
                    "desc": "Curadoria de dados, gestão de acessos via Unity Catalog e conformidade com políticas de segurança."
                },
                {
                    "icon": "bar-chart-2",
                    "title": "Analytics & Self-Service BI",
                    "desc": "Dashboards de alta performance, indicadores estratégicos e democratização no uso dos dados."
                },
                {
                    "icon": "cpu",
                    "title": "IA & Ciência de Dados",
                    "desc": "Modelagem preditiva e inteligência artificial para otimização comercial, logística e industrial."
                }
            ],
            "stats": [
                {
                    "label": "Pipelines de Dados",
                    "value": "+50"
                },
                {
                    "label": "Qualidade & Uptime",
                    "value": "99.9%"
                },
                {
                    "label": "Engine Analítica",
                    "value": "Databricks"
                },
                {
                    "label": "Usuários Conectados",
                    "value": "+500"
                }
            ],
            "techs": [
                "Databricks",
                "Delta Lake",
                "Unity Catalog",
                "Power BI",
                "Python",
                "SQL",
                "Azure AD"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 3
                    },
                    {
                        "name": "Portfólio",
                        "value": 3
                    },
                    {
                        "name": "Autonomia",
                        "value": 2
                    },
                    {
                        "name": "Capacitação",
                        "value": 2
                    },
                    {
                        "name": "Estratégia",
                        "value": 3
                    }
                ]
            }
        },
        "applications": [
            {
                "title": "Catálogo de Dados (Data Catalog)",
                "title_key": "app_dna_catalog",
                "icon": "book-open",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Linhagem de Dados",
                "title_key": "app_dna_lineage",
                "icon": "git-fork",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Qualidade de Dados",
                "title_key": "db_dna_quality",
                "icon": "check-circle",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Acessos e Governança",
                "title_key": "db_dna_gov",
                "icon": "shield-check",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "database",
        "hidden": False,
        "required_group": ""
    },
    "industrial": {
        "title_key": "industrial",
        "applications": [
            {
                "title": "Apontamento de Paradas",
                "title_key": "app_ind_stops",
                "icon": "pause-circle",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Checklist de Manutenção",
                "title_key": "app_ind_maintenance",
                "icon": "wrench",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "OEE Industrial",
                "title_key": "db_ind_oee",
                "icon": "activity",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Volume de Produção",
                "title_key": "db_ind_production",
                "icon": "package",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Consumo Energético",
                "title_key": "db_ind_energy",
                "icon": "zap",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "activity",
        "hidden": False,
        "required_group": "",
        "tagline": "Excelência Operacional na Manufatura de Panificados e Segurança",
        "about": {
            "description": "A área Industrial gerencia as plantas fabris do Grupo Bimbo, aplicando automação avançada, manutenção preventiva rigorosa e altos padrões de segurança na produção de alimentos.",
            "pillars": [
                {
                    "icon": "activity",
                    "title": "Manufatura & OEE Industrial",
                    "desc": "Alta eficiência global dos equipamentos, produção contínua 24/7 e automação fabril."
                },
                {
                    "icon": "wrench",
                    "title": "Manutenção Preditiva",
                    "desc": "Confiabilidade das linhas automatizadas de fornada e redução de paradas não programadas."
                },
                {
                    "icon": "shield-check",
                    "title": "Segurança & TPM",
                    "desc": "Manufatura enxuta, segurança do trabalho rigorosa e desperdício zero."
                }
            ],
            "stats": [
                {
                    "label": "OEE Global",
                    "value": "88%"
                },
                {
                    "label": "Segurança Trabalho",
                    "value": "Zero Acidentes"
                },
                {
                    "label": "Operação",
                    "value": "24/7"
                }
            ],
            "techs": [
                "SCADA",
                "MES",
                "SAP PM",
                "Power BI",
                "Databricks"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 1
                    },
                    {
                        "name": "Portfólio",
                        "value": 2
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 2
                    },
                    {
                        "name": "Estratégia",
                        "value": 1
                    }
                ]
            }
        }
    },
    "transformation": {
        "title_key": "transformation",
        "applications": [
            {
                "title": "Cadastro de Projetos (PMO)",
                "title_key": "app_tf_pmo",
                "icon": "folder-kanban",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Acompanhamento de OKRs",
                "title_key": "app_tf_okr",
                "icon": "target",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Cronograma e Marcos",
                "title_key": "db_tf_timeline",
                "icon": "milestone",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Captura de Sinergias",
                "title_key": "db_tf_synergy",
                "icon": "trending-up",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "target",
        "hidden": False,
        "required_group": "",
        "tagline": "Gestão de Projetos Estratégicos, Inovação e OKRs Globais",
        "about": {
            "description": "A área de Transformação (PMO) impulsiona iniciativas estratégicas, governança de projetos e captura de sinergias para manter o Grupo Bimbo na vanguarda do setor alimentício.",
            "pillars": [
                {
                    "icon": "folder-kanban",
                    "title": "PMO & Governança de Projetos",
                    "desc": "Acompanhamento rigoroso de prazos, entregáveis e escopo das iniciativas corporativas."
                },
                {
                    "icon": "trending-up",
                    "title": "Captura de Sinergias",
                    "desc": "Geração de valor financeiro, integração de aquisições e eficiência de processos."
                },
                {
                    "icon": "target",
                    "title": "Gestão de OKRs",
                    "desc": "Alinhamento das metas regionais aos objetivos globais do Grupo Bimbo."
                }
            ],
            "stats": [
                {
                    "label": "Projetos Ativos",
                    "value": "+30"
                },
                {
                    "label": "Acompanhamento OKR",
                    "value": "100%"
                },
                {
                    "label": "Governança",
                    "value": "PMO Ágil"
                }
            ],
            "techs": [
                "Jira",
                "Miro",
                "Power BI",
                "MS Project"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 2
                    },
                    {
                        "name": "Portfólio",
                        "value": 3
                    },
                    {
                        "name": "Autonomia",
                        "value": 2
                    },
                    {
                        "name": "Capacitação",
                        "value": 2
                    },
                    {
                        "name": "Estratégia",
                        "value": 2
                    }
                ]
            }
        }
    },
    "fpa": {
        "title_key": "fpa",
        "applications": [
            {
                "title": "Simulador de Cenários",
                "title_key": "app_fpa_scenarios",
                "icon": "sliders",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Consolidação de Forecast",
                "title_key": "app_fpa_forecast",
                "icon": "briefcase",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "DRE Corporativo",
                "title_key": "db_fpa_pnl",
                "icon": "bar-chart-3",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Margem de Contribuição",
                "title_key": "db_fpa_margin",
                "icon": "percent",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Análise de Desvios (Variação)",
                "title_key": "db_fpa_variance",
                "icon": "split",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Teste",
                "title_key": "teste",
                "icon": "bar-chart-3",
                "link": "https://app.powerbi.com/reportEmbed?reportId=4edf51b7-18ab-4a33-b594-6ca115ba2822&autoAuth=True&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "bar-chart-3",
        "hidden": False,
        "required_group": "",
        "tagline": "Modelagem Financeira, Forecast, Budget e Performance",
        "about": {
            "description": "A área de FP&A (Planejamento Financeiro) lidera a elaboração do orçamento anual, projeções de fluxo de caixa e análises de desempenho para apoiar decisões executivas.",
            "pillars": [
                {
                    "icon": "calculator",
                    "title": "Orçamento & Budget Anual",
                    "desc": "Elaboração e acompanhamento das metas orçamentárias e investimento em capital (CapEx)."
                },
                {
                    "icon": "sliders",
                    "title": "Forecast & Cenários",
                    "desc": "Projeções financeiras contínuas e simulação de impactos macroeconômicos."
                },
                {
                    "icon": "bar-chart-3",
                    "title": "Análise DRE & Variâncias",
                    "desc": "Acompanhamento da Demonstração de Resultado (P&L) e análise explicativa de desvios."
                }
            ],
            "stats": [
                {
                    "label": "Previsão P&L",
                    "value": "99% Acurácia"
                },
                {
                    "label": "Modelo Forecast",
                    "value": "Rolling"
                },
                {
                    "label": "Ciclo Budget",
                    "value": "Anual"
                }
            ],
            "techs": [
                "SAP BPC",
                "Databricks",
                "Power BI",
                "Excel Advanced"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 2
                    },
                    {
                        "name": "Portfólio",
                        "value": 2
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 1
                    },
                    {
                        "name": "Estratégia",
                        "value": 2
                    }
                ]
            }
        }
    },
    "legal": {
        "title_key": "legal",
        "applications": [
            {
                "title": "Gerenciador de Processos",
                "title_key": "app_leg_lawsuits",
                "icon": "scale",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Repositório de Atas",
                "title_key": "app_leg_repository",
                "icon": "archive",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Provisões Financeiras",
                "title_key": "db_leg_provisions",
                "icon": "dollar-sign",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Contratos a Vencer",
                "title_key": "db_leg_contracts",
                "icon": "clock",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "scale",
        "hidden": False,
        "required_group": "",
        "tagline": "Governança Jurídica, Contratos e Conformidade Regulatória",
        "about": {
            "description": "A área Jurídica assegura a segurança jurídica das operações do Grupo Bimbo, gerando valor por meio da prevenção de riscos, compliance com a LGPD e suporte contratual estratégico.",
            "pillars": [
                {
                    "icon": "scale",
                    "title": "Gestão Contratual",
                    "desc": "Elaboração, análise e revisão estratégica de contratos comerciais e operacionais."
                },
                {
                    "icon": "shield",
                    "title": "Contencioso & Prevenção",
                    "desc": "Defesa jurídica da companhia e mitigação proativa de riscos cíveis e trabalhistas."
                },
                {
                    "icon": "check-circle",
                    "title": "Compliance & LGPD",
                    "desc": "Garantia de conformidade com a legislação da indústria e proteção de dados."
                }
            ],
            "stats": [
                {
                    "label": "Conformidade LGPD",
                    "value": "100% OK"
                },
                {
                    "label": "Contratos",
                    "value": "Digitais"
                },
                {
                    "label": "Risco Jurídico",
                    "value": "Mitigado"
                }
            ],
            "techs": [
                "TOTVS Jurídico",
                "DocuSign",
                "Power BI",
                "Excel"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 1
                    },
                    {
                        "name": "Portfólio",
                        "value": 1
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 1
                    },
                    {
                        "name": "Estratégia",
                        "value": 1
                    }
                ]
            }
        }
    },
    "audit": {
        "title_key": "audit",
        "applications": [
            {
                "title": "Checklist de Controles",
                "title_key": "app_aud_checklist",
                "icon": "clipboard-check",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Apontamento de Planos de Ação",
                "title_key": "app_aud_actions",
                "icon": "check-square",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Status de Auditoria",
                "title_key": "db_aud_status",
                "icon": "pie-chart",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Matriz de Riscos",
                "title_key": "db_aud_risks",
                "icon": "shield-alert",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "shield-check",
        "hidden": False,
        "required_group": "",
        "tagline": "Avaliação de Controles Internos, Riscos e Mapeamento de Processos",
        "about": {
            "description": "A área de Auditoria Interna assegura a integridade dos processos corporativos, realizando testes de controles, mitigação de riscos e garantindo governança nas operações.",
            "pillars": [
                {
                    "icon": "clipboard-check",
                    "title": "Auditoria Operacional & Financeira",
                    "desc": "Revisão periódica de processos, inventários e procedimentos internos."
                },
                {
                    "icon": "shield-alert",
                    "title": "Matriz de Riscos Corporativos",
                    "desc": "Identificação, avaliação e monitoramento contínuo de riscos de negócios."
                },
                {
                    "icon": "check-square",
                    "title": "Planos de Ação & Remedias",
                    "desc": "Acompanhamento do cumprimento das recomendações de melhorias e auditorias."
                }
            ],
            "stats": [
                {
                    "label": "Mapeamento Riscos",
                    "value": "100%"
                },
                {
                    "label": "Governança",
                    "value": "SOX Compliance"
                },
                {
                    "label": "Fraudes",
                    "value": "Zero Tolerância"
                }
            ],
            "techs": [
                "ACL Analytics",
                "Power BI",
                "SAP",
                "Databricks"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 1
                    },
                    {
                        "name": "Portfólio",
                        "value": 1
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 1
                    },
                    {
                        "name": "Estratégia",
                        "value": 1
                    }
                ]
            }
        }
    },
    "quality": {
        "title_key": "quality",
        "applications": [
            {
                "title": "Registro de RNC",
                "title_key": "app_qty_rnc",
                "icon": "alert-circle",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Gestão de Certificações",
                "title_key": "app_qty_certificates",
                "icon": "award",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Índice de Reclamações",
                "title_key": "db_qty_complaints",
                "icon": "thumbs-down",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Capabilidade de Processo",
                "title_key": "db_qty_process",
                "icon": "activity",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "award",
        "hidden": False,
        "required_group": "",
        "tagline": "Garantia de Qualidade, Padrões Sanitários e Segurança dos Alimentos",
        "about": {
            "description": "A área de Qualidade assegura o sabor inconfundível e o padrão sanitário rigoroso de todos os produtos do Grupo Bimbo, da recepção do trigo até a mesa do consumidor.",
            "pillars": [
                {
                    "icon": "award",
                    "title": "Segurança Alimentar & FSSC 22000",
                    "desc": "Garantia dos mais altos padrões de higiene, sanidade e certificações internacionais."
                },
                {
                    "icon": "alert-circle",
                    "title": "Gestão de Não Conformidades (RNC)",
                    "desc": "Tratamento de causas raiz e melhoria contínua dos processos de fabricação."
                },
                {
                    "icon": "thumbs-up",
                    "title": "Qualidade na Mesa do Consumidor",
                    "desc": "Monitoramento constante de satisfação, frescor e sabor dos alimentos."
                }
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 1
                    },
                    {
                        "name": "Portfólio",
                        "value": 2
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 1
                    },
                    {
                        "name": "Estratégia",
                        "value": 1
                    }
                ]
            }
        }
    },
    "wickbold": {
        "title_key": "wickbold",
        "applications": [
            {
                "title": "Lançamento de Produção Wickbold",
                "title_key": "app_wb_production",
                "icon": "package-plus",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Ficha de Qualidade (Fornada)",
                "title_key": "app_wb_quality",
                "icon": "clipboard-check",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "dashboards": [
            {
                "title": "Indicadores Industriais Wickbold",
                "title_key": "db_wb_perf",
                "icon": "activity",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            },
            {
                "title": "Relatório de Qualidade",
                "title_key": "db_wb_quality_report",
                "icon": "award",
                "link": "#",
                "link_mobile": "",
                "hidden": False,
                "required_group": ""
            }
        ],
        "icon": "package",
        "hidden": False,
        "required_group": "",
        "tagline": "Integração Operacional, Tradição na Panificação e Excelência Wickbold",
        "about": {
            "description": "A área da Wickbold integra a tradição das fornadas artesanais e pães especiais à força logística e tecnológica do Grupo Bimbo, encantando famílias brasileiras.",
            "pillars": [
                {
                    "icon": "package-plus",
                    "title": "Produção & Fornadas Especiais",
                    "desc": "Fabricação com tradição de pães especiais, torradas e linhas de nutrição."
                },
                {
                    "icon": "clipboard-check",
                    "title": "Fichas de Qualidade & Padrão",
                    "desc": "Controle rigoroso de fermentação, forneamento e textura impecável."
                },
                {
                    "icon": "activity",
                    "title": "Sinergia com Grupo Bimbo",
                    "desc": "Integração logística, comercial e tecnológica das operações em todo o Brasil."
                }
            ],
            "stats": [
                {
                    "label": "Tradição em Pães",
                    "value": "+80 Anos"
                },
                {
                    "label": "Fornadas",
                    "value": "Operação 24/7"
                },
                {
                    "label": "Sinergia",
                    "value": "Grupo Bimbo"
                }
            ],
            "techs": [
                "SAP S/4HANA",
                "SCADA",
                "Power BI",
                "Databricks"
            ],
            "digital_maturity": {
                "title": "Digital Maturity",
                "target": 3.2,
                "frequency": "Atualizado trimestralmente",
                "scale_max": 5,
                "dimensions": [
                    {
                        "name": "Adoção",
                        "value": 1
                    },
                    {
                        "name": "Portfólio",
                        "value": 2
                    },
                    {
                        "name": "Autonomia",
                        "value": 1
                    },
                    {
                        "name": "Capacitação",
                        "value": 1
                    },
                    {
                        "name": "Estratégia",
                        "value": 1
                    }
                ]
            }
        }
    }
}

# ─────────────────────────────────────────────
#  SCHEMA INIT IMPLEMENTATION
# ─────────────────────────────────────────────

def ensure_schema():
    """Ensure database schema, tables, columns and initial seed data exist."""
    global SCHEMA_INITIALIZED
    if SCHEMA_INITIALIZED or LOCAL_MODE:
        return
    with SCHEMA_LOCK:
        if SCHEMA_INITIALIZED:
            return
        conn = get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(CREATE_SCHEMA_SQL)
                    # Safe migrations for existing schemas
                    cur.execute("ALTER TABLE space_portal.area ADD COLUMN IF NOT EXISTS tagline TEXT;")
                    cur.execute("ALTER TABLE space_portal.area ADD COLUMN IF NOT EXISTS about JSONB;")
                    cur.execute("ALTER TABLE space_portal.area ADD COLUMN IF NOT EXISTS hidden BOOLEAN DEFAULT FALSE;")
                    cur.execute("ALTER TABLE space_portal.area ADD COLUMN IF NOT EXISTS required_group VARCHAR(256);")
                    cur.execute("ALTER TABLE space_portal.item ADD COLUMN IF NOT EXISTS link_mobile VARCHAR(512);")
                    cur.execute("ALTER TABLE space_portal.item ADD COLUMN IF NOT EXISTS hidden BOOLEAN DEFAULT FALSE;")
                    cur.execute("ALTER TABLE space_portal.item ADD COLUMN IF NOT EXISTS required_group VARCHAR(256);")

                    # Seed admin users
                    cur.execute("""
                        INSERT INTO space_portal.admin_users (email) VALUES
                        ('renan.ferreira@grupobimbo.com'),
                        ('vitor.saes@grupobimbo.com'),
                        ('bruno.fellipe@grupobimbo.com'),
                        ('pedro.madureira@grupobimbo.com'),
                        ('helio.cillo@grupobimbo.com'),
                        ('lecivaldo.santana@grupobimbo.com'),
                        ('caio.dasilva@grupobimbo.com'),
                        ('maria.carolina@grupobimbo.com')
                        ON CONFLICT (email) DO NOTHING;
                    """)

                    # Seed default areas if table is empty (prefer local_area_data.json for Bimbo QSR)
                    cur.execute("SELECT COUNT(*) FROM space_portal.area")
                    if cur.fetchone()[0] == 0:
                        seed_area_data = DEFAULT_AREA_DATA
                        if os.path.exists(LOCAL_DATA_FILE):
                            try:
                                with open(LOCAL_DATA_FILE, 'r', encoding='utf-8') as f:
                                    loaded_seed = json.load(f)
                                if isinstance(loaded_seed, dict) and loaded_seed:
                                    seed_area_data = loaded_seed
                            except Exception as seed_err:
                                print(f"[WARN] Could not load {LOCAL_DATA_FILE} for seed, using DEFAULT_AREA_DATA: {seed_err}")

                        for ak, ainfo in seed_area_data.items():
                            cur.execute(
                                """INSERT INTO space_portal.area (area_key, title_key, tagline, icon, hidden, required_group, about)
                                   VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                                (ak, ainfo.get('title_key', ak), ainfo.get('tagline', ''), ainfo.get('icon', 'layout-grid'),
                                 ainfo.get('hidden', False), ainfo.get('required_group', ''), json.dumps(ainfo.get('about')) if ainfo.get('about') else None)
                            )
                            for app_item in ainfo.get('applications', []):
                                cur.execute(
                                    """INSERT INTO space_portal.item (area_key, type, title, title_key, icon, link, link_mobile, hidden, required_group)
                                       VALUES (%s, 'application', %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                                    (ak, app_item.get('title', ''), app_item.get('title_key', ''), app_item.get('icon', 'app'), app_item.get('link', '#'),
                                     app_item.get('link_mobile', ''), app_item.get('hidden', False), app_item.get('required_group', ''))
                                )
                            for db_item in ainfo.get('dashboards', []):
                                cur.execute(
                                    """INSERT INTO space_portal.item (area_key, type, title, title_key, icon, link, link_mobile, hidden, required_group)
                                       VALUES (%s, 'dashboard', %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                                    (ak, db_item.get('title', ''), db_item.get('title_key', ''), db_item.get('icon', 'file-text'), db_item.get('link', '#'),
                                     db_item.get('link_mobile', ''), db_item.get('hidden', False), db_item.get('required_group', ''))
                                )

                    # Fix legacy DNA de Vendas reportId if seeded with the old link
                    cur.execute(
                        """UPDATE space_portal.item
                           SET link = %s
                           WHERE link LIKE %s""",
                        (
                            "https://app.powerbi.com/reportEmbed?reportId=c04ce17c-f4e8-4edd-a398-b88b0d920bfe&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
                            "%681a24a6-519d-4930-b780-0c2d81c4429c%",
                        ),
                    )

                    # Seed default sidebar apps if table is empty
                    cur.execute("SELECT COUNT(*) FROM space_portal.sidebar_apps")
                    if cur.fetchone()[0] == 0:
                        seed_sidebar_apps = DEFAULT_SIDEBAR_APPS
                        if os.path.exists(_LOCAL_SIDEBAR_APPS_FILE):
                            try:
                                with open(_LOCAL_SIDEBAR_APPS_FILE, 'r', encoding='utf-8') as f:
                                    loaded_sidebar = json.load(f)
                                if isinstance(loaded_sidebar, list) and loaded_sidebar:
                                    seed_sidebar_apps = loaded_sidebar
                            except Exception as sb_err:
                                print(f"[WARN] Could not load {_LOCAL_SIDEBAR_APPS_FILE} for seed: {sb_err}")

                        for sapp in seed_sidebar_apps:
                            cur.execute(
                                """INSERT INTO space_portal.sidebar_apps (app_key, title, link, hidden, icon)
                                   VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                                (sapp['app_key'], sapp['title'], sapp['link'], sapp.get('hidden', False), sapp.get('icon', ''))
                            )

                    # Sync sugestao_knn from CSV (always refresh on deploy)
                    cur.execute("TRUNCATE TABLE space_portal.sugestao_knn")
                    import csv
                    csv_path = os.path.join(os.path.dirname(__file__), 'sugestao_knn.csv')
                    if os.path.exists(csv_path):
                        with open(csv_path, 'r', encoding='utf-8') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                cur.execute(
                                    """INSERT INTO space_portal.sugestao_knn
                                       (email, cargo, relatorio_1, espaco_1, cod_1, distancia_1,
                                        relatorio_2, espaco_2, cod_2, distancia_2,
                                        relatorio_3, espaco_3, cod_3, distancia_3,
                                        relatorio_4, espaco_4, cod_4, distancia_4)
                                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                       ON CONFLICT (email) DO NOTHING""",
                                    (row.get('EMAIL',''), row.get('CARGO',''),
                                     row.get('RELATORIO_1',''), row.get('ESPACO_1',''), row.get('COD_1',''),
                                     float(row['DISTANCIA_1']) if row.get('DISTANCIA_1') else 0,
                                     row.get('RELATORIO_2',''), row.get('ESPACO_2',''), row.get('COD_2',''),
                                     float(row['DISTANCIA_2']) if row.get('DISTANCIA_2') else 0,
                                     row.get('RELATORIO_3',''), row.get('ESPACO_3',''), row.get('COD_3',''),
                                     float(row['DISTANCIA_3']) if row.get('DISTANCIA_3') else 0,
                                     row.get('RELATORIO_4',''), row.get('ESPACO_4',''), row.get('COD_4',''),
                                     float(row['DISTANCIA_4']) if row.get('DISTANCIA_4') else 0)
                                )
                        print(f"[INFO] Seeded sugestao_knn from CSV.")

            SCHEMA_INITIALIZED = True
            print("[INFO] Lakebase schema initialized successfully.")
        except Exception as e:
            print(f"[ERROR] Lakebase schema init failed: {e}")
            raise e
        finally:
            release_conn(conn)


# ─────────────────────────────────────────────
#  HELPERS (unchanged logic)
# ─────────────────────────────────────────────


def db_update_area_group(area_key: str, required_group: str) -> bool:
    """Update required group for an area."""
    required_group = required_group.strip()
    if LOCAL_MODE:
        global _local_data
        _local_data_snapshot()
        with _local_data_lock:
            area = _local_data.get(area_key)
            if area is None:
                return False
            area['required_group'] = required_group
            _save_local_data()
        return True
    ensure_schema()
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE space_portal.area SET required_group=%s WHERE area_key=%s",
                    (required_group or None, area_key)
                )
                return cur.rowcount > 0
    finally:
        release_conn(conn)


def db_update_item_group(area_key: str, comp_type: str, title_key: str, required_group: str) -> bool:
    """Update required group for a dashboard or application."""
    required_group = required_group.strip()
    if LOCAL_MODE:
        global _local_data
        _local_data_snapshot()
        with _local_data_lock:
            area = _local_data.get(area_key)
            if area is None:
                return False
            lst_key = 'applications' if comp_type == 'application' else 'dashboards'
            for item in area.get(lst_key, []):
                if item['title_key'] == title_key:
                    item['required_group'] = required_group
                    _save_local_data()
                    return True
        return False
    ensure_schema()
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE space_portal.item SET required_group=%s WHERE area_key=%s AND type=%s AND title_key=%s",
                    (required_group or None, area_key, comp_type, title_key)
                )
                return cur.rowcount > 0
    finally:
        release_conn(conn)


def db_save_digital_maturity(area_key: str, dimensions: list, business_owners: list = None) -> bool:
    """Save/update digital maturity dimensions and business owners for a given area."""
    if LOCAL_MODE:
        global _local_data
        if _local_data is None:
            _local_data_snapshot()
        with _local_data_lock:
            if _local_data and area_key in _local_data:
                area = _local_data[area_key]
                if 'about' not in area or not isinstance(area['about'], dict):
                    area['about'] = copy.deepcopy(DEFAULT_AREA_DATA.get(area_key, {}).get('about', {}))
                if 'digital_maturity' not in area['about'] or not isinstance(area['about']['digital_maturity'], dict):
                    area['about']['digital_maturity'] = {
                        'title': 'Digital Maturity',
                        'target': 3.2,
                        'frequency': 'Atualizado trimestralmente',
                        'scale_max': 5,
                        'dimensions': []
                    }
                area['about']['digital_maturity']['dimensions'] = dimensions
                if business_owners is not None:
                    area['about']['digital_maturity']['business_owners'] = business_owners
                _save_local_data()
                return True
        return False
    else:
        ensure_schema()
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT about FROM space_portal.area WHERE area_key = %s", (area_key,))
                row = cur.fetchone()
                db_about = row['about'] if (row and row.get('about')) else None
                if isinstance(db_about, str):
                    try:
                        db_about = json.loads(db_about)
                    except Exception:
                        db_about = None

                default_about = copy.deepcopy(DEFAULT_AREA_DATA.get(area_key, {}).get('about', {})) if area_key in DEFAULT_AREA_DATA else {}
                
                if isinstance(db_about, dict) and db_about:
                    about = copy.deepcopy(default_about)
                    about.update(db_about)
                else:
                    about = default_about if default_about else {}

                if 'digital_maturity' not in about or not isinstance(about['digital_maturity'], dict):
                    about['digital_maturity'] = {
                        'title': 'Digital Maturity',
                        'target': 3.2,
                        'frequency': 'Atualizado trimestralmente',
                        'scale_max': 5,
                        'dimensions': []
                    }
                about['digital_maturity']['dimensions'] = dimensions
                if business_owners is not None:
                    about['digital_maturity']['business_owners'] = business_owners
                cur.execute("UPDATE space_portal.area SET about = %s WHERE area_key = %s", (json.dumps(about), area_key))
                conn.commit()
                return True
        except Exception as e:
            print(f"Error saving digital maturity to DB: {e}")
            return False
        finally:
            release_conn(conn)


def db_add_item(area_key: str, comp_type: str, title: str, title_key: str, icon: str = 'link', link: str = '#', link_mobile: str = '', required_group: str = '') -> bool:
    """Add a new item (dashboard or application) to an area."""
    icon = (icon or 'link').strip()
    link = (link or '#').strip()
    link_mobile = (link_mobile or '').strip()
    required_group = (required_group or '').strip()

    if LOCAL_MODE:
        global _local_data
        _local_data_snapshot()
        with _local_data_lock:
            if not _local_data or area_key not in _local_data:
                return False
            area = _local_data[area_key]
            lst_key = 'applications' if comp_type == 'application' else 'dashboards'
            if lst_key not in area:
                area[lst_key] = []
            for item in area[lst_key]:
                if item.get('title_key') == title_key:
                    return False
            area[lst_key].append({
                'title': title,
                'title_key': title_key,
                'icon': icon,
                'link': link,
                'link_mobile': link_mobile,
                'hidden': False,
                'required_group': required_group
            })
            _save_local_data()
            return True

    ensure_schema()
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO space_portal.item (area_key, type, title, title_key, icon, link, link_mobile, hidden, required_group)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s)
                       ON CONFLICT (area_key, type, title_key) DO NOTHING""",
                    (area_key, comp_type, title, title_key, icon, link, link_mobile, required_group)
                )
                return cur.rowcount > 0
    finally:
        release_conn(conn)


def db_delete_item(area_key: str, comp_type: str, title_key: str) -> bool:
    """Delete an item (dashboard or application) from an area."""
    if LOCAL_MODE:
        global _local_data
        _local_data_snapshot()
        with _local_data_lock:
            if not _local_data or area_key not in _local_data:
                return False
            area = _local_data[area_key]
            lst_key = 'applications' if comp_type == 'application' else 'dashboards'
            items = area.get(lst_key, [])
            new_items = [i for i in items if i.get('title_key') != title_key]
            if len(new_items) < len(items):
                area[lst_key] = new_items
                _save_local_data()
                return True
            return False

    ensure_schema()
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM space_portal.item WHERE area_key = %s AND type = %s AND title_key = %s",
                    (area_key, comp_type, title_key)
                )
                return cur.rowcount > 0
    finally:
        release_conn(conn)


def db_toggle_item_visibility(area_key: str, comp_type: str, title_key: str) -> bool:
    """Toggle visibility (hidden flag) of an item."""
    if LOCAL_MODE:
        global _local_data
        _local_data_snapshot()
        with _local_data_lock:
            if not _local_data or area_key not in _local_data:
                return False
            area = _local_data[area_key]
            lst_key = 'applications' if comp_type == 'application' else 'dashboards'
            for item in area.get(lst_key, []):
                if item.get('title_key') == title_key:
                    item['hidden'] = not item.get('hidden', False)
                    new_val = item['hidden']
                    _save_local_data()
                    return new_val
            return False

    ensure_schema()
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE space_portal.item
                       SET hidden = NOT hidden
                       WHERE area_key = %s AND type = %s AND title_key = %s
                       RETURNING hidden""",
                    (area_key, comp_type, title_key)
                )
                row = cur.fetchone()
                return row[0] if row else False
    finally:
        release_conn(conn)


def db_toggle_area_visibility(area_key: str) -> bool:
    """Toggle visibility (hidden flag) of an area."""
    if LOCAL_MODE:
        global _local_data
        _local_data_snapshot()
        with _local_data_lock:
            if not _local_data or area_key not in _local_data:
                return False
            area = _local_data[area_key]
            area['hidden'] = not area.get('hidden', False)
            new_val = area['hidden']
            _save_local_data()
            return new_val

    ensure_schema()
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE space_portal.area
                       SET hidden = NOT hidden
                       WHERE area_key = %s
                       RETURNING hidden""",
                    (area_key,)
                )
                row = cur.fetchone()
                return row[0] if row else False
    finally:
        release_conn(conn)


def db_add_area(area_key: str, area_title: str, area_icon: str = 'layout-grid', required_group: str = '') -> bool:
    """Add a new area."""
    area_icon = (area_icon or 'layout-grid').strip()
    required_group = (required_group or '').strip()

    if LOCAL_MODE:
        global _local_data
        _local_data_snapshot()
        with _local_data_lock:
            if _local_data is None:
                _local_data = {}
            if area_key in _local_data:
                return False
            _local_data[area_key] = {
                'title_key': area_title,
                'tagline': '',
                'icon': area_icon,
                'hidden': False,
                'required_group': required_group,
                'about': None,
                'applications': [],
                'dashboards': []
            }
            _save_local_data()
            return True

    ensure_schema()
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO space_portal.area (area_key, title_key, tagline, icon, hidden, required_group)
                       VALUES (%s, %s, '', %s, FALSE, %s)
                       ON CONFLICT (area_key) DO NOTHING""",
                    (area_key, area_title, area_icon, required_group)
                )
                return cur.rowcount > 0
    finally:
        release_conn(conn)


def db_edit_item(area_key: str, comp_type: str, old_title_key: str, title: str, icon: str, link: str, link_mobile: str, required_group: str) -> bool:
    """Edit an existing item."""
    icon = (icon or 'link').strip()
    link = (link or '#').strip()
    link_mobile = (link_mobile or '').strip()
    required_group = (required_group or '').strip()
    new_title_key = re.sub(r'[^a-zA-Z0-9]', '_', title.lower()).strip('_') or old_title_key

    if LOCAL_MODE:
        global _local_data
        _local_data_snapshot()
        with _local_data_lock:
            if not _local_data or area_key not in _local_data:
                return False
            area = _local_data[area_key]
            lst_key = 'applications' if comp_type == 'application' else 'dashboards'
            for item in area.get(lst_key, []):
                if item.get('title_key') == old_title_key:
                    item['title'] = title
                    item['title_key'] = new_title_key
                    item['icon'] = icon
                    item['link'] = link
                    item['link_mobile'] = link_mobile
                    item['required_group'] = required_group
                    _save_local_data()
                    return True
            return False

    ensure_schema()
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE space_portal.item
                       SET title = %s, title_key = %s, icon = %s, link = %s, link_mobile = %s, required_group = %s
                       WHERE area_key = %s AND type = %s AND title_key = %s""",
                    (title, new_title_key, icon, link, link_mobile, required_group, area_key, comp_type, old_title_key)
                )
                return cur.rowcount > 0
    finally:
        release_conn(conn)


def db_edit_area(area_key: str, area_title: str, area_icon: str, required_group: str) -> bool:
    """Edit an existing area."""
    area_icon = (area_icon or 'layout-grid').strip()
    required_group = (required_group or '').strip()

    if LOCAL_MODE:
        global _local_data
        _local_data_snapshot()
        with _local_data_lock:
            if not _local_data or area_key not in _local_data:
                return False
            area = _local_data[area_key]
            area['title_key'] = area_title
            area['icon'] = area_icon
            area['required_group'] = required_group
            _save_local_data()
            return True

    ensure_schema()
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE space_portal.area
                       SET title_key = %s, icon = %s, required_group = %s
                       WHERE area_key = %s""",
                    (area_title, area_icon, required_group, area_key)
                )
                return cur.rowcount > 0
    finally:
        release_conn(conn)








LOCAL_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_area_data.json')

def _save_local_data():
    if not LOCAL_MODE:
        return
    global _local_data
    if _local_data is not None:
        try:
            with open(LOCAL_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(_local_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving local_area_data.json: {e}")


def _local_data_snapshot() -> dict:
    """Return a deep copy of the in-memory store, initialising from local file or DEFAULT_AREA_DATA."""
    global _local_data
    with _local_data_lock:
        if os.path.exists(LOCAL_DATA_FILE):
            try:
                with open(LOCAL_DATA_FILE, 'r', encoding='utf-8') as f:
                    _local_data = json.load(f)
            except Exception as e:
                print(f"Error loading local_area_data.json: {e}")
        
        if _local_data is None:
            import copy
            _local_data = copy.deepcopy(DEFAULT_AREA_DATA)
        
        # Ensure structure and default values
        for ak, area in _local_data.items():
            area.setdefault('hidden', False)
            area.setdefault('required_group', '')
            for lst in ('applications', 'dashboards'):
                for item in area.get(lst, []):
                    item.setdefault('link_mobile', '')
    import copy
    return copy.deepcopy(_local_data)


def load_data(include_hidden: bool = False) -> dict:
    """Load area data. In LOCAL_MODE returns _local_data_snapshot()."""
    if LOCAL_MODE:
        data = _local_data_snapshot()
        if include_hidden:
            return data
        return {k: v for k, v in data.items() if not v.get('hidden', False)}
    
    ensure_schema()
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT area_key, title_key, tagline, icon, hidden, required_group, about FROM space_portal.area")
            areas = cur.fetchall()
            
            cur.execute("SELECT area_key, type, title, title_key, icon, link, link_mobile, hidden, required_group FROM space_portal.item")
            items = cur.fetchall()
            
        data = {}
        for a in areas:
            ak = a['area_key']
            db_about = a.get('about')
            if isinstance(db_about, str):
                try:
                    db_about = json.loads(db_about)
                except Exception:
                    db_about = None

            default_about = copy.deepcopy(DEFAULT_AREA_DATA.get(ak, {}).get('about', {})) if (ak in DEFAULT_AREA_DATA and DEFAULT_AREA_DATA[ak].get('about')) else {}

            if isinstance(db_about, dict) and db_about:
                merged_about = copy.deepcopy(default_about) if default_about else {}
                merged_about.update(db_about)
                about_val = merged_about
            elif default_about:
                about_val = default_about
            else:
                about_val = None

            data[ak] = {
                'title_key': a['title_key'],
                'tagline': a.get('tagline', '') or (DEFAULT_AREA_DATA.get(ak, {}).get('tagline', '') if ak in DEFAULT_AREA_DATA else ''),
                'icon': a.get('icon', 'layout-grid'),
                'hidden': a.get('hidden', False),
                'required_group': a.get('required_group', ''),
                'about': about_val,
                'applications': [],
                'dashboards': []
            }
            
        for item in items:
            ak = item['area_key']
            if ak in data:
                comp_type = 'applications' if item['type'] == 'application' else 'dashboards'
                data[ak][comp_type].append({
                    'title': item['title'],
                    'title_key': item['title_key'],
                    'icon': item.get('icon', 'file-text'),
                    'link': item.get('link', '#'),
                    'link_mobile': item.get('link_mobile', ''),
                    'hidden': item.get('hidden', False),
                    'required_group': item.get('required_group', '')
                })
                
        if include_hidden:
            return data
        return {k: v for k, v in data.items() if not v.get('hidden', False)}
    finally:
        release_conn(conn)


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def process_uploaded_icon(file_obj, app_key: str) -> str | None:
    """Helper to save uploaded logo image file and return static URL path."""
    if not file_obj or not file_obj.filename:
        return None
    try:
        from werkzeug.utils import secure_filename
        filename = secure_filename(file_obj.filename)
    except Exception:
        filename = os.path.basename(file_obj.filename)
    if not filename:
        return None
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'):
        return None
    new_filename = f"app_{app_key}_{int(time.time())}{ext}"
    images_dir = os.path.join(os.path.dirname(__file__), 'static', 'images')
    os.makedirs(images_dir, exist_ok=True)
    dest_path = os.path.join(images_dir, new_filename)
    file_obj.save(dest_path)
    return f"/static/images/{new_filename}"


def load_sidebar_apps(include_hidden: bool = False) -> list:
    """Load sidebar apps config. Return list of dicts."""
    if LOCAL_MODE:
        if not os.path.exists(_LOCAL_SIDEBAR_APPS_FILE):
            try:
                with open(_LOCAL_SIDEBAR_APPS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(DEFAULT_SIDEBAR_APPS, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"Error initializing local_sidebar_apps.json: {e}")
            apps = list(DEFAULT_SIDEBAR_APPS)
        else:
            try:
                with open(_LOCAL_SIDEBAR_APPS_FILE, 'r', encoding='utf-8') as f:
                    apps = json.load(f)
            except Exception:
                apps = list(DEFAULT_SIDEBAR_APPS)
        
        if include_hidden:
            return apps
        return [app for app in apps if not app.get('hidden', False)]
    else:
        ensure_schema()
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT app_key, title, link, hidden, icon FROM space_portal.sidebar_apps")
                apps = cur.fetchall()
            
            seq = {
                'space_copilot': 1,
                'threego': 2,
                'fermenta': 3,
                'threegohub': 4,
                'tradego': 4
            }
            apps_list = []
            for app in apps:
                apps_list.append({
                    'app_key': app['app_key'],
                    'title': app['title'],
                    'link': app['link'] or '',
                    'hidden': app.get('hidden', False),
                    'icon': app.get('icon', '') or ''
                })
            apps_list.sort(key=lambda x: seq.get(x['app_key'], 999))
            
            if include_hidden:
                return apps_list
            return [app for app in apps_list if not app['hidden']]
        finally:
            release_conn(conn)


def save_sidebar_app(app_key: str, title: str, link: str, hidden: bool, icon: str = '') -> bool:
    """Save or update sidebar app's title, link, hidden status and icon."""
    if LOCAL_MODE:
        with _local_sidebar_apps_lock:
            apps = load_sidebar_apps(include_hidden=True)
            updated = False
            for app in apps:
                if app['app_key'] == app_key:
                    app['title'] = title
                    app['link'] = link
                    app['hidden'] = hidden
                    if icon is not None and icon != '':
                        app['icon'] = icon
                    updated = True
                    break
            if not updated:
                apps.append({
                    'app_key': app_key,
                    'title': title,
                    'link': link,
                    'hidden': hidden,
                    'icon': icon or ''
                })
            try:
                with open(_LOCAL_SIDEBAR_APPS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(apps, f, ensure_ascii=False, indent=2)
                return True
            except Exception as e:
                print(f"Error saving local_sidebar_apps.json: {e}")
                return False
    else:
        ensure_schema()
        conn = get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO space_portal.sidebar_apps (app_key, title, link, hidden, icon)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (app_key) DO UPDATE SET
                            title = EXCLUDED.title,
                            link = EXCLUDED.link,
                            hidden = EXCLUDED.hidden,
                            icon = EXCLUDED.icon
                        """,
                        (app_key, title, link, hidden, icon or '')
                    )
            return True
        finally:
            release_conn(conn)


def delete_sidebar_app(app_key: str) -> bool:
    """Delete a sidebar app by key."""
    if LOCAL_MODE:
        with _local_sidebar_apps_lock:
            apps = load_sidebar_apps(include_hidden=True)
            new_apps = [app for app in apps if app['app_key'] != app_key]
            try:
                with open(_LOCAL_SIDEBAR_APPS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(new_apps, f, ensure_ascii=False, indent=2)
                return True
            except Exception as e:
                print(f"Error deleting from local_sidebar_apps.json: {e}")
                return False
    else:
        ensure_schema()
        conn = get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM space_portal.sidebar_apps WHERE app_key = %s", (app_key,))
            return True
        finally:
            release_conn(conn)


def get_all_dashboards(data):
    all_dashboards = []
    for area_key, area in data.items():
        has_area_access = user_has_access(area.get('required_group', ''))
        items = list(area.get('dashboards', [])) + list(area.get('applications', []))
        for dash in items:
            if dash.get('hidden', False):
                continue
            direct_link = dash.get('link', '')
            direct_link_mobile = dash.get('link_mobile', '')
            has_dash_access = user_has_access(dash.get('required_group', ''))
            all_dashboards.append({
                'title': dash['title'],
                'title_key': dash.get('title_key', ''),
                'area_key': area_key,
                'link': direct_link,
                'link_mobile': direct_link_mobile,
                'url': direct_link or f"/area/{area_key}",
                'url_mobile': direct_link_mobile or f"/area/{area_key}",
                'has_access': has_dash_access,
                'has_area_access': has_area_access,
                'required_group': dash.get('required_group', ''),
                'icon': dash.get('icon', 'file-text')
            })
    return all_dashboards


# ─────────────────────────────────────────────
#  ACCESS LOGGING — grava acessos em space_portal.acessos_space
# ─────────────────────────────────────────────

_SKIP_LOG_PREFIXES = ('/static/', '/api/', '/favicon', '/health')
_LOG_METHODS = ('GET',)


def _resolve_dashboard_title(dash_key: str) -> str | None:
    """Resolve o título do dashboard a partir do title_key para o log."""
    if not dash_key:
        return None
    try:
        data = load_data()
        for area in data.values():
            for dash in area.get('dashboards', []):
                if dash.get('title_key') == dash_key:
                    return dash.get('title') or dash_key
    except Exception as resolve_err:
        print(f"[ACCESS LOG] Failed to resolve dashboard title '{dash_key}': {resolve_err}")
    return None


def _resolve_area_title(area_key: str) -> str | None:
    """Resolve o título da área a partir do area_key."""
    if not area_key:
        return None
    try:
        data = load_data()
        area = data.get(area_key)
        if area:
            return area.get('title_key', area_key).replace('_', ' ').capitalize()
    except Exception as e:
        print(f"[ACCESS LOG] Failed to resolve area title '{area_key}': {e}")
    return None


def _normalize_page_path(path: str) -> str:
    """Normaliza o valor salvo no log para facilitar análises posteriores."""
    if path == '/':
        return 'home'

    # /area/<area_key> → título da área
    if path.startswith('/area/'):
        area_key = path.replace('/area/', '').strip('/')
        area_title = _resolve_area_title(area_key)
        if area_title:
            return area_title

    if request.endpoint == 'dashboard_redirect':
        dash_key = (request.view_args or {}).get('dash_key', '').strip()
        dash_title = _resolve_dashboard_title(dash_key)
        if dash_title:
            return dash_title

    return path


def _log_local_access(user_email: str, page_path: str):
    """Registra acesso localmente em local_acessos_space.json quando em LOCAL_MODE."""
    if not user_email:
        return
    local_acessos_file = os.path.join(os.path.dirname(__file__), 'local_acessos_space.json')
    logs = []
    if os.path.exists(local_acessos_file):
        try:
            with open(local_acessos_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except Exception:
            logs = []
    logs.append({
        'user_email': user_email,
        'page_path': page_path,
        'accessed_at': time.strftime('%Y-%m-%d %H:%M:%S')
    })
    try:
        with open(local_acessos_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ACCESS LOG] Failed to write local_acessos_space.json: {e}")


def get_user_cargo(user_email: str) -> str:
    """Retorna o cargo do usuário a partir de space_portal.sugestao_knn."""
    if not user_email:
        return ''

    if LOCAL_MODE:
        csv_path = os.path.join(os.path.dirname(__file__), 'sugestao_knn.csv')
        if not os.path.exists(csv_path):
            return ''
        try:
            import csv as _csv
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = _csv.DictReader(f)
                email_clean = user_email.strip().lower()
                for row in reader:
                    if (row.get('EMAIL') or row.get('email') or '').strip().lower() == email_clean:
                        return (row.get('CARGO') or row.get('cargo') or '').strip().title()
        except Exception as e:
            print(f"[CARGO] Error reading sugestao_knn.csv: {e}")
        return ''

    ensure_schema()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cargo FROM space_portal.sugestao_knn WHERE LOWER(email) = LOWER(%s) LIMIT 1",
                (user_email.strip(),)
            )
            row = cur.fetchone()
            return row[0].strip().title() if row and row[0] else ''
    except Exception as db_err:
        print(f"[CARGO] Failed to fetch cargo for {user_email}: {db_err}")
        return ''
    finally:
        release_conn(conn)


def is_first_user_access(user_email: str) -> bool:
    """Verifica se o usuário nunca teve nenhum registro na base de acessos_space."""
    if not user_email:
        return False

    if LOCAL_MODE:
        local_acessos_file = os.path.join(os.path.dirname(__file__), 'local_acessos_space.json')
        if not os.path.exists(local_acessos_file):
            return True
        try:
            with open(local_acessos_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
                email_clean = user_email.strip().lower()
                for log in logs:
                    if (log.get('user_email') or '').strip().lower() == email_clean:
                        return False
                return True
        except Exception as e:
            print(f"[ACCESS CHECK] Error reading local_acessos_space.json: {e}")
            return True

    ensure_schema()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM space_portal.acessos_space WHERE LOWER(user_email) = LOWER(%s))",
                (user_email.strip(),)
            )
            row = cur.fetchone()
            has_accessed = row[0] if row else False
            return not has_accessed
    except Exception as db_err:
        print(f"[ACCESS CHECK] Failed to check first access for {user_email}: {db_err}")
        return False
    finally:
        release_conn(conn)


@app.after_request
def log_page_access(response):
    """Log page views to space_portal.acessos_space (non-blocking)."""
    try:
        if request.method not in _LOG_METHODS:
            return response
        if response.status_code < 200 or response.status_code >= 400:
            return response

        path = request.path
        if any(path.startswith(prefix) for prefix in _SKIP_LOG_PREFIXES):
            return response

        user_email = get_current_user_email()
        if not user_email:
            return response

        logged_path = _normalize_page_path(path)

        if LOCAL_MODE:
            _log_local_access(user_email, logged_path)
            return response

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO space_portal.acessos_space (user_email, page_path)
                       VALUES (%s, %s)""",
                    (user_email, logged_path)
                )
            conn.commit()
        except Exception as db_err:
            print(f"[ACCESS LOG] Failed to log access: {db_err}")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            release_conn(conn)
    except Exception as e:
        print(f"[ACCESS LOG] Unexpected error: {e}")
    return response


# ─────────────────────────────────────────────
#  FLASK ROUTES
# ─────────────────────────────────────────────

@app.route('/api/admin/reset-welcome', methods=['POST'])
@require_admin_group
def api_admin_reset_welcome():
    """Admin: limpa registros de acesso de um usuário para que o welcome popup apareça novamente."""
    target_email = (request.json or {}).get('email', '').strip()
    if not target_email:
        target_email = get_current_user_email()

    if LOCAL_MODE:
        local_acessos_file = os.path.join(os.path.dirname(__file__), 'local_acessos_space.json')
        try:
            with open(local_acessos_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            logs = [l for l in logs if (l.get('user_email') or '').strip().lower() != target_email.lower()]
            with open(local_acessos_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return jsonify({'ok': True, 'email': target_email, 'message': 'Welcome reset (local)'})

    ensure_schema()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM space_portal.acessos_space WHERE LOWER(user_email) = LOWER(%s)",
                (target_email,)
            )
            deleted = cur.rowcount
        conn.commit()
        return jsonify({'ok': True, 'email': target_email, 'deleted_rows': deleted})
    except Exception as db_err:
        print(f"[ADMIN] Reset welcome failed: {db_err}")
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify({'ok': False, 'error': str(db_err)}), 500
    finally:
        release_conn(conn)

@app.route('/api/confirm-welcome', methods=['POST'])
def api_confirm_welcome():
    """Garante o registro de acesso do usuário quando ele clica em Confirmar no popup de boas-vindas."""
    user_email = get_current_user_email()
    if not user_email:
        return jsonify({'ok': True})

    if LOCAL_MODE:
        _log_local_access(user_email, 'welcome_confirm')
        return jsonify({'ok': True})

    ensure_schema()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO space_portal.acessos_space (user_email, page_path) VALUES (%s, %s)",
                (user_email, 'welcome_confirm')
            )
        conn.commit()
    except Exception as db_err:
        print(f"[CONFIRM WELCOME] DB error: {db_err}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        release_conn(conn)

    return jsonify({'ok': True})


@app.route('/api/track-dashboard', methods=['POST'])
def api_track_dashboard():
    """Registra acesso a um dashboard a partir do clique no card (frontend)."""
    if LOCAL_MODE:
        return jsonify({'ok': True})

    try:
        payload = request.get_json(silent=True) or {}
        dashboard_name = (payload.get('dashboard_name') or '').strip()
        area_key = (payload.get('area_key') or '').strip()

        if not dashboard_name:
            return jsonify({'ok': False, 'error': 'dashboard_name required'}), 400

        user_email = get_current_user_email()
        if not user_email or user_email == 'user@example.com':
            return jsonify({'ok': True})

        # Resolve area title for prefix
        area_title = _resolve_area_title(area_key) if area_key else None
        if area_title:
            logged_path = f"{area_title}/{dashboard_name}"
        else:
            logged_path = dashboard_name

        ensure_schema()
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO space_portal.acessos_space (user_email, page_path)
                       VALUES (%s, %s)""",
                    (user_email, logged_path)
                )
            conn.commit()
        except Exception as db_err:
            print(f"[TRACK DASH] DB error: {db_err}")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            release_conn(conn)
    except Exception as e:
        print(f"[TRACK DASH] Unexpected error: {e}")

    return jsonify({'ok': True})


# ─────────────────────────────────────────────
#  DATABRICKS KNN SUGGESTED DASHBOARDS
# ─────────────────────────────────────────────

_user_suggestions_cache: dict[str, tuple[list[dict], float]] = {}
_user_suggestions_cache_lock = threading.Lock()


def _exec_databricks_sql(sql_query: str) -> list[dict]:
    """Execute a SQL query against Databricks SQL Warehouse using databricks-sdk."""
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()

        warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID")
        if not warehouse_id:
            try:
                warehouses = list(w.warehouses.list())
                if warehouses:
                    warehouse_id = warehouses[0].id
            except Exception as wh_err:
                print(f"[DATABRICKS SQL] Could not list SQL Warehouses: {wh_err}")

        if not warehouse_id:
            print("[DATABRICKS SQL] DATABRICKS_WAREHOUSE_ID is not configured and no SQL warehouse found.")
            return []

        res = w.statement_execution.execute_statement(
            statement=sql_query,
            warehouse_id=warehouse_id,
            wait_timeout="30s"
        )

        if res.result and res.result.data_array and res.manifest and res.manifest.schema:
            col_names = [col.name.upper() for col in res.manifest.schema.columns]
            rows = []
            for row in res.result.data_array:
                rows.append(dict(zip(col_names, row)))
            return rows
    except Exception as e:
        print(f"[DATABRICKS SQL] Query execution failed: {e}")
    return []


def get_default_suggested_dashboards(all_dashboards: list[dict]) -> list[dict]:
    """Return default suggested dashboards if user query fails or in LOCAL_MODE."""
    preferred_titles = [
        "dna de vendas",
        "otif e fill rate",
        "painel logístico",
        "estado de resultados"
    ]
    defaults = []
    seen = set()

    for pref in preferred_titles:
        for d in all_dashboards:
            if d['title'].lower().strip() == pref and d['title'] not in seen:
                defaults.append(d)
                seen.add(d['title'])
                break
        if len(defaults) >= 4:
            break

    if len(defaults) < 4:
        for d in all_dashboards:
            if d['title'] not in seen:
                defaults.append(d)
                seen.add(d['title'])
                if len(defaults) >= 4:
                    break

    return defaults


def get_user_suggested_dashboards(user_email: str, all_dashboards: list[dict]) -> list[dict]:
    """Get suggested dashboards for user from sugestao_knn.csv, Lakebase or Unity Catalog Delta table."""
    if not user_email:
        return get_default_suggested_dashboards(all_dashboards)

    cache_key = user_email.strip().lower()
    now = time.time()

    with _user_suggestions_cache_lock:
        cached = _user_suggestions_cache.get(cache_key)
        if cached is not None:
            suggestions, expires_at = cached
            if now < expires_at:
                return suggestions

    suggested_list: list[dict] = []
    raw_reports: list[tuple[str, str]] = []  # list of (name, code) tuples

    # 1. Modo Local ou fallback de arquivo: lê diretamente de sugestao_knn.csv
    if LOCAL_MODE:
        csv_path = os.path.join(os.path.dirname(__file__), 'sugestao_knn.csv')
        if os.path.exists(csv_path):
            try:
                import csv as _csv
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = _csv.DictReader(f)
                    email_clean = user_email.strip().lower()
                    for row in reader:
                        r_email = (row.get('EMAIL') or row.get('email') or '').strip().lower()
                        if r_email == email_clean:
                            raw_reports = [
                                (str(row.get('RELATORIO_1') or row.get('relatorio_1') or '').strip(),
                                 str(row.get('COD_1') or row.get('cod_1') or '').strip()),
                                (str(row.get('RELATORIO_2') or row.get('relatorio_2') or '').strip(),
                                 str(row.get('COD_2') or row.get('cod_2') or '').strip()),
                                (str(row.get('RELATORIO_3') or row.get('relatorio_3') or '').strip(),
                                 str(row.get('COD_3') or row.get('cod_3') or '').strip()),
                                (str(row.get('RELATORIO_4') or row.get('relatorio_4') or '').strip(),
                                 str(row.get('COD_4') or row.get('cod_4') or '').strip()),
                            ]
                            break
            except Exception as e:
                print(f"[SUGGESTIONS] Error reading sugestao_knn.csv in LOCAL_MODE: {e}")

    # 2. Em produção: tenta consultar a tabela Delta no Unity Catalog ou Lakebase
    if not raw_reports and not LOCAL_MODE:
        try:
            # 2a. Tenta consultar a tabela Delta no Unity Catalog
            delta_sql = (
                f"SELECT RELATORIO_1, COD_1, RELATORIO_2, COD_2, RELATORIO_3, COD_3, RELATORIO_4, COD_4 "
                f"FROM cat_dnabb_dv.grobbbqb_sz.sugestao_dashboards_knn_qsr "
                f"WHERE LOWER(EMAIL) = LOWER('{user_email.strip()}') LIMIT 1"
            )
            rows = _exec_databricks_sql(delta_sql)
            if rows:
                raw_reports = [
                    (str(rows[0].get('RELATORIO_1') or '').strip(), str(rows[0].get('COD_1') or '').strip()),
                    (str(rows[0].get('RELATORIO_2') or '').strip(), str(rows[0].get('COD_2') or '').strip()),
                    (str(rows[0].get('RELATORIO_3') or '').strip(), str(rows[0].get('COD_3') or '').strip()),
                    (str(rows[0].get('RELATORIO_4') or '').strip(), str(rows[0].get('COD_4') or '').strip()),
                ]
        except Exception as err_delta:
            print(f"[SUGGESTIONS] Failed to fetch from Unity Catalog Delta table: {err_delta}")

        # 2b. Fallback Lakebase Postgres
        if not raw_reports:
            try:
                ensure_schema()
                conn = get_conn()
                try:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute(
                            "SELECT relatorio_1, relatorio_2, relatorio_3, relatorio_4 FROM space_portal.sugestao_knn WHERE LOWER(email) = LOWER(%s) LIMIT 1",
                            (user_email.strip(),)
                        )
                        row = cur.fetchone()
                        if row:
                            raw_reports = [
                                (str(row.get('relatorio_1') or '').strip(), ''),
                                (str(row.get('relatorio_2') or '').strip(), ''),
                                (str(row.get('relatorio_3') or '').strip(), ''),
                                (str(row.get('relatorio_4') or '').strip(), ''),
                            ]
                finally:
                    release_conn(conn)
            except Exception as err_lakebase:
                print(f"[SUGGESTIONS] Failed to fetch from Lakebase: {err_lakebase}")

    # 3. Mapeia os relatórios encontrados para a lista de dashboards do portal
    if raw_reports:
        def _norm(s: str) -> str:
            import unicodedata
            s = unicodedata.normalize('NFD', (s or '').lower())
            s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
            return re.sub(r'[^a-z0-9]', '', s)

        seen_titles = set()
        for rep_name, rep_code in raw_reports:
            if not rep_name and not rep_code:
                continue
            rep_norm = _norm(rep_name)
            code_norm = _norm(rep_code) if rep_code else ''
            matched_dash = None
            for d in all_dashboards:
                d_title_norm = _norm(d.get('title', ''))
                d_key_norm = _norm(d.get('title_key', ''))

                # 1. Correspondência exata por título ou chave
                if (rep_norm and d_title_norm == rep_norm) or (rep_norm and d_key_norm == rep_norm):
                    matched_dash = d
                    break
                # 2. Correspondência exata por código do KNN
                if code_norm and (d_key_norm == code_norm or d_title_norm == code_norm):
                    matched_dash = d
                    break
                # 3. Correspondência parcial (ex: 'OPEX' dentro de 'OPEX (Custos Operacionais)')
                if rep_norm and len(rep_norm) >= 3 and (rep_norm in d_title_norm or rep_norm in d_key_norm):
                    matched_dash = d
                    break

            if matched_dash and matched_dash['title'] not in seen_titles:
                suggested_list.append(matched_dash)
                seen_titles.add(matched_dash['title'])
            elif not matched_dash and rep_name and rep_name not in seen_titles:
                suggested_list.append({
                    'title': rep_name,
                    'title_key': rep_code or re.sub(r'[^a-zA-Z0-9]', '_', rep_name.lower()),
                    'area_key': 'geral',
                    'link': '#',
                    'link_mobile': '',
                    'url': '#',
                    'has_access': True,
                    'required_group': '',
                    'icon': 'file-text'
                })
                seen_titles.add(rep_name)

    # 4. Garante SEMPRE no mínimo 4 dashboards preenchendo com os padrões caso falte algum
    if len(suggested_list) < 4:
        defaults = get_default_suggested_dashboards(all_dashboards)
        seen_titles = {d['title'] for d in suggested_list}
        for d in defaults:
            if d['title'] not in seen_titles:
                suggested_list.append(d)
                seen_titles.add(d['title'])
                if len(suggested_list) >= 4:
                    break

    with _user_suggestions_cache_lock:
        _user_suggestions_cache[cache_key] = (suggested_list, now + _CACHE_TTL_SECONDS)

    return suggested_list


@app.route('/')
def index():
    all_data     = load_data(include_hidden=True)   # full data to build hidden set
    hidden_areas = {k for k, v in all_data.items() if v.get('hidden', False)}
    data         = {k: v for k, v in all_data.items() if k not in hidden_areas}
    all_dashboards = get_all_dashboards(data)
    area_options = []
    for k, v in data.items():
        has_area_access = user_has_access(v.get('required_group', ''))
        area_options.append({
            'key': k, 
            'title': v.get('title_key', k).capitalize(), 
            'icon': v.get('icon', 'layout-grid'),
            'required_group': v.get('required_group', ''),
            'has_access': has_area_access
        })
        
    user_email = get_current_user_email()
    is_admin = is_current_user_admin()
    user_groups = get_current_user_groups()
    sidebar_apps = load_sidebar_apps()
    
    suggested_dashboards = get_user_suggested_dashboards(user_email, all_dashboards)
    is_first_access = is_first_user_access(user_email)
    user_cargo = get_user_cargo(user_email)
    
    return render_template(
        'index.html', 
        dashboards=all_dashboards, 
        suggested_dashboards=suggested_dashboards,
        area_options=area_options, 
        hidden_areas=hidden_areas,
        user_email=user_email,
        is_admin=is_admin,
        user_groups=",".join(user_groups),
        local_mode=LOCAL_MODE,
        sidebar_apps=sidebar_apps,
        show_welcome_popup=is_first_access,
        user_cargo=user_cargo
    )


def get_area_about(area_key: str, area_info: dict) -> dict:
    if area_info and area_info.get('about'):
        return area_info['about']
    if area_key in DEFAULT_AREA_DATA and DEFAULT_AREA_DATA[area_key].get('about'):
        return DEFAULT_AREA_DATA[area_key]['about']
    title = area_info.get('title_key', area_key).replace('_', ' ').title() if area_info else area_key.title()
    return {
        'description': f"A área de {title} é responsável por impulsionar a inovação, governança e eficiência das operações do Grupo Bimbo.",
        'pillars': [
            {'icon': 'target', 'title': 'Estratégia & Metas', 'desc': f'Planejamento estratégico e execução das metas da área de {title}.'},
            {'icon': 'shield-check', 'title': 'Governança & Processos', 'desc': 'Padronização de processos, qualidade e conformidade operacional.'},
            {'icon': 'trending-up', 'title': 'Eficiência & Performance', 'desc': 'Otimização contínua de indicadores e geração de valor para o negócio.'}
        ],
        'stats': [
            {'label': 'Operação', 'value': '100% OK'},
            {'label': 'Projetos', 'value': 'Ativos'},
            {'label': 'Nível de Serviço', 'value': '99%'}
        ],
        'techs': ['SAP', 'Power BI', 'Databricks', 'Excel', 'Azure']
    }


def get_area_tagline(area_key: str, area_info: dict) -> str:
    if area_info and area_info.get('tagline'):
        return area_info['tagline']
    if area_key in DEFAULT_AREA_DATA and DEFAULT_AREA_DATA[area_key].get('tagline'):
        return DEFAULT_AREA_DATA[area_key]['tagline']
    title = area_info.get('title_key', area_key).replace('_', ' ').title() if area_info else area_key.title()
    return f"{title} — Excelência Operacional e Estratégia no Grupo Bimbo"


@app.route('/area/<area_key>')
def area_detail(area_key):
    area_key = area_key.lower().strip()
    AREA_ALIASES = {
        'purchasing': 'purchase',
        'rh': 'people',
        'recursos_humanos': 'people',
        'finance': 'adm_finances',
        'finances': 'adm_finances',
        'adm': 'adm_finances'
    }
    if area_key in AREA_ALIASES:
        area_key = AREA_ALIASES[area_key]

    data = load_data()
    all_dashboards = get_all_dashboards(data)
    area_options = []
    for k, v in data.items():
        has_area_access = user_has_access(v.get('required_group', ''))
        area_options.append({
            'key': k, 
            'title': v.get('title_key', k).capitalize(), 
            'icon': v.get('icon', 'layout-grid'),
            'required_group': v.get('required_group', ''),
            'has_access': has_area_access
        })
        
    user_email = get_current_user_email()
    is_admin = is_current_user_admin()
    user_groups = get_current_user_groups()
    
    if area_key in data:
        area_info = data[area_key]
        
        # Map accesses for dashboards and applications inside this area
        for db in area_info.get('dashboards', []):
            db['has_access'] = True
            
        for app_item in area_info.get('applications', []):
            app_item['has_access'] = True
            
        about = get_area_about(area_key, area_info)
        tagline = get_area_tagline(area_key, area_info)

        return render_template(
            'area.html', 
            area_key=area_key, 
            data=area_info, 
            area_about=about,
            area_tagline=tagline,
            area_options=area_options, 
            dashboards=all_dashboards,
            user_email=user_email,
            is_admin=is_admin,
            user_groups=",".join(user_groups),
            local_mode=LOCAL_MODE
        )
    return redirect(url_for('index'))


@app.route('/dashboard/<dash_key>')
def dashboard_redirect(dash_key):
    data = load_data()
    all_dashboards = get_all_dashboards(data)
    for dash in all_dashboards:
        if dash['title_key'] == dash_key:
            is_mobile = any(kw in request.headers.get('User-Agent', '').lower() for kw in ['mobile', 'android', 'iphone', 'ipad'])
            if is_mobile and dash.get('link_mobile') and dash['link_mobile'] != '#':
                return redirect(dash['link_mobile'])
            return redirect(dash['url'])
    return redirect(url_for('index'))


@app.route('/admin')
@require_admin_group
def admin_panel():
    AREA_DEFAULT_ICONS = {
        'people': 'users', 'commercial': 'trending-up', 'marketing': 'line-chart',
        'adm_finances': 'coins', 'logistics': 'truck', 'rgm': 'bar-chart-3',
        'supply_chain': 'archive', 'purchase': 'file-text', 'dna': 'database',
        'industrial': 'activity', 'transformation': 'target', 'fpa': 'bar-chart-3',
        'legal': 'scale', 'audit': 'shield-check', 'quality': 'award', 'wickbold': 'package'
    }
    data = load_data(include_hidden=True)  # admin sees everything
    area_options = []
    area_visibility = []  # list of {key, title, icon, hidden, required_group}
    for key, val in data.items():
        area_options.append({
            'key': key,
            'title': val.get('title_key', key).replace('_', ' ').capitalize(),
            'default_icon': AREA_DEFAULT_ICONS.get(key, 'link')
        })
        area_visibility.append({
            'key': key,
            'title': val.get('title_key', key).replace('_', ' ').capitalize(),
            'icon': val.get('icon', AREA_DEFAULT_ICONS.get(key, 'layout-grid')),
            'hidden': val.get('hidden', False),
            'required_group': val.get('required_group', '')
        })
    area_options.sort(key=lambda x: x['title'])
    area_visibility.sort(key=lambda x: x['title'])
    
    user_email = get_current_user_email()
    is_admin = is_current_user_admin()
    user_groups = get_current_user_groups()
    sidebar_apps = load_sidebar_apps(include_hidden=True)
    
    return render_template(
        'admin.html', 
        data=data, 
        area_options=area_options, 
        area_visibility=area_visibility,
        sidebar_apps=sidebar_apps,
        user_email=user_email,
        is_admin=is_admin,
        user_groups=",".join(user_groups),
        local_mode=LOCAL_MODE
    )


@app.route('/admin/add', methods=['POST'])
@require_admin_group
def admin_add():
    comp_type = request.form.get('type')  # 'dashboard' or 'application'
    area_key = request.form.get('area')
    title = request.form.get('title', '').strip()
    link = request.form.get('link', '').strip()
    link_mobile = request.form.get('link_mobile', '').strip()
    icon = request.form.get('icon', 'link').strip()
    required_group = request.form.get('required_group', '').strip()

    if not title or not area_key or not comp_type:
        flash('Erro: Título, Área e Tipo são obrigatórios.', 'danger')
        return redirect(url_for('admin_panel'))

    title_key = re.sub(r'[^a-zA-Z0-9]', '_', title.lower()).strip('_') or 'custom_item'

    added = db_add_item(area_key, comp_type, title, title_key, icon, link, link_mobile, required_group)
    if added:
        flash(f'"{title}" adicionado com sucesso em {area_key.capitalize()}!', 'success')
    else:
        flash(f'Componente "{title}" já existe nesta área.', 'warning')

    return redirect(url_for('admin_panel'))


@app.route('/admin/delete', methods=['POST'])
@require_admin_group
def admin_delete():
    area_key = request.form.get('area')
    comp_type = request.form.get('type')
    title_key = request.form.get('title_key')

    if not area_key or not comp_type or not title_key:
        flash('Erro: Dados inválidos para exclusão.', 'danger')
        return redirect(url_for('admin_panel'))

    deleted = db_delete_item(area_key, comp_type, title_key)
    if deleted:
        flash('Componente excluído com sucesso!', 'success')
    else:
        flash('Erro: Componente não encontrado.', 'danger')

    return redirect(url_for('admin_panel'))


@app.route('/admin/toggle-item', methods=['POST'])
@require_admin_group
def admin_toggle_item():
    area_key  = request.form.get('area')
    comp_type = request.form.get('type')
    title_key = request.form.get('title_key')

    if not area_key or not comp_type or not title_key:
        flash('Erro: Dados inválidos para alteração de visibilidade.', 'danger')
        return redirect(url_for('admin_panel'))

    now_hidden = db_toggle_item_visibility(area_key, comp_type, title_key)
    status = 'ocultado' if now_hidden else 'exibido'
    flash(f'Componente {status} com sucesso!', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/toggle-area', methods=['POST'])
@require_admin_group
def admin_toggle_area():
    area_key = request.form.get('area')

    if not area_key:
        flash('Erro: Área inválida.', 'danger')
        return redirect(url_for('admin_panel'))

    now_hidden = db_toggle_area_visibility(area_key)
    status = 'ocultada' if now_hidden else 'exibida'
    flash(f'Área "{area_key}" {status} com sucesso!', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/add-area', methods=['POST'])
@require_admin_group
def admin_add_area():
    area_key = request.form.get('area_key', '').lower().strip()
    area_title = request.form.get('area_title', '').strip()
    area_icon = request.form.get('area_icon', 'layout-grid').strip()
    required_group = request.form.get('required_group', '').strip()

    if not area_key or not area_title:
        flash('Erro: Chave e Título são obrigatórios.', 'danger')
        return redirect(url_for('admin_panel'))

    # sanitize key (only lowercase, digits, and underscores)
    area_key = re.sub(r'[^a-z0-9_]', '', area_key)

    if not area_key:
        flash('Erro: Chave de área inválida.', 'danger')
        return redirect(url_for('admin_panel'))

    added = db_add_area(area_key, area_title, area_icon, required_group)
    if added:
        flash(f'Área "{area_title}" criada com sucesso!', 'success')
    else:
        flash(f'Erro: Área com chave "{area_key}" já existe.', 'warning')

    return redirect(url_for('admin_panel'))


@app.route('/admin/edit', methods=['POST'])
@require_admin_group
def admin_edit():
    area_key = request.form.get('area')
    comp_type = request.form.get('type')
    old_title_key = request.form.get('old_title_key')
    title = request.form.get('title', '').strip()
    icon = request.form.get('icon', 'link').strip()
    link = request.form.get('link', '').strip()
    link_mobile = request.form.get('link_mobile', '').strip()
    required_group = request.form.get('required_group', '').strip()

    if not area_key or not comp_type or not old_title_key or not title:
        flash('Erro: Dados inválidos para edição.', 'danger')
        return redirect(url_for('admin_panel'))

    updated = db_edit_item(area_key, comp_type, old_title_key, title, icon, link, link_mobile, required_group)
    if updated:
        flash(f'Componente "{title}" atualizado com sucesso!', 'success')
    else:
        flash('Erro ao atualizar o componente.', 'danger')

    return redirect(url_for('admin_panel'))


@app.route('/admin/edit-area', methods=['POST'])
@require_admin_group
def admin_edit_area():
    area_key = request.form.get('area_key')
    area_title = request.form.get('area_title', '').strip()
    area_icon = request.form.get('area_icon', 'layout-grid').strip()
    required_group = request.form.get('required_group', '').strip()

    if not area_key or not area_title:
        flash('Erro: Dados inválidos para edição da área.', 'danger')
        return redirect(url_for('admin_panel'))

    updated = db_edit_area(area_key, area_title, area_icon, required_group)
    if updated:
        flash(f'Área "{area_title}" atualizada com sucesso!', 'success')
    else:
        flash('Erro ao atualizar a área.', 'danger')

    return redirect(url_for('admin_panel'))


@app.route('/admin/save-digital-maturity', methods=['POST'])
@require_admin_group
def admin_save_digital_maturity():
    if request.is_json:
        payload = request.get_json()
    else:
        payload = request.form.to_dict()

    if not payload:
        return jsonify({'success': False, 'error': 'Payload vazio'}), 400

    if 'updates' in payload:
        success_count = 0
        for item in payload['updates']:
            area_key = item.get('area')
            dimensions = item.get('dimensions', [])
            business_owners = item.get('business_owners', None)
            if area_key and db_save_digital_maturity(area_key, dimensions, business_owners):
                success_count += 1
        return jsonify({'success': True, 'updated': success_count})

    area_key = payload.get('area')
    dimensions = payload.get('dimensions', [])
    business_owners = payload.get('business_owners', None)
    if not area_key:
        return jsonify({'success': False, 'error': 'Área não especificada'}), 400

    ok = db_save_digital_maturity(area_key, dimensions, business_owners)
    if ok:
        return jsonify({'success': True, 'area': area_key})
    return jsonify({'success': False, 'error': 'Erro ao salvar maturidade digital'}), 500



@app.route('/admin/toggle-sidebar-app', methods=['POST'])
@require_admin_group
def admin_toggle_sidebar_app():
    app_key = request.form.get('app_key')
    if not app_key:
        flash('Erro: Aplicativo inválido.', 'danger')
        return redirect(url_for('admin_panel'))
    
    apps = load_sidebar_apps(include_hidden=True)
    target_app = next((app for app in apps if app['app_key'] == app_key), None)
    if not target_app:
        flash('Erro: Aplicativo não encontrado.', 'danger')
        return redirect(url_for('admin_panel'))
    
    new_hidden = not target_app.get('hidden', False)
    saved = save_sidebar_app(app_key, target_app.get('title'), target_app.get('link', '#'), new_hidden, target_app.get('icon', ''))
    if saved:
        status = 'ocultado' if new_hidden else 'exibido'
        flash(f'Aplicativo "{target_app.get("title")}" {status} com sucesso!', 'success')
    else:
        flash('Erro ao alterar a visibilidade do aplicativo.', 'danger')
        
    return redirect(url_for('admin_panel'))


@app.route('/admin/add-sidebar-app', methods=['POST'])
@require_admin_group
def admin_add_sidebar_app():
    title = request.form.get('title', '').strip()
    link = request.form.get('link', '').strip()
    icon_text = request.form.get('icon', '').strip()
    
    if not title:
        flash('Erro: O título do aplicativo é obrigatório.', 'danger')
        return redirect(url_for('admin_panel'))
    
    if not link:
        link = '#'
    
    import re
    slug = re.sub(r'[^a-zA-Z0-9_]', '_', title.lower()).strip('_')
    app_key = f"app_{slug}_{int(time.time())}" if slug else f"app_{int(time.time())}"
    
    file_obj = request.files.get('icon_file')
    uploaded_icon = process_uploaded_icon(file_obj, app_key)
    final_icon = uploaded_icon if uploaded_icon else (icon_text if icon_text else 'rocket')
    
    saved = save_sidebar_app(app_key, title, link, False, final_icon)
    if saved:
        flash(f'Aplicativo "{title}" criado com sucesso!', 'success')
    else:
        flash('Erro ao criar o aplicativo.', 'danger')
        
    return redirect(url_for('admin_panel'))


@app.route('/admin/edit-sidebar-app', methods=['POST'])
@require_admin_group
def admin_edit_sidebar_app():
    app_key = request.form.get('app_key')
    title = request.form.get('title', '').strip()
    link = request.form.get('link', '').strip()
    icon_text = request.form.get('icon', '').strip()
    
    if not app_key or not title:
        flash('Erro: Dados inválidos para edição.', 'danger')
        return redirect(url_for('admin_panel'))
    
    if not link:
        link = '#'
        
    apps = load_sidebar_apps(include_hidden=True)
    target_app = next((app for app in apps if app['app_key'] == app_key), None)
    if not target_app:
        flash('Erro: Aplicativo não encontrado.', 'danger')
        return redirect(url_for('admin_panel'))
        
    file_obj = request.files.get('icon_file')
    uploaded_icon = process_uploaded_icon(file_obj, app_key)
    final_icon = uploaded_icon if uploaded_icon else (icon_text if icon_text else target_app.get('icon', ''))

    saved = save_sidebar_app(app_key, title, link, target_app.get('hidden', False), final_icon)
    if saved:
        flash(f'Aplicativo "{title}" atualizado com sucesso!', 'success')
    else:
        flash('Erro ao atualizar o aplicativo.', 'danger')
        
    return redirect(url_for('admin_panel'))


@app.route('/admin/delete-sidebar-app', methods=['POST'])
@require_admin_group
def admin_delete_sidebar_app():
    app_key = request.form.get('app_key')
    if not app_key:
        flash('Erro: Aplicativo inválido.', 'danger')
        return redirect(url_for('admin_panel'))
    
    apps = load_sidebar_apps(include_hidden=True)
    target_app = next((app for app in apps if app['app_key'] == app_key), None)
    app_title = target_app.get('title') if target_app else app_key
    
    deleted = delete_sidebar_app(app_key)
    if deleted:
        flash(f'Aplicativo "{app_title}" excluído com sucesso!', 'success')
    else:
        flash('Erro ao excluir o aplicativo.', 'danger')
        
    return redirect(url_for('admin_panel'))


@app.route('/admin/update-group', methods=['POST'])
@require_admin_group
def admin_update_group():
    area_key = request.form.get('area')
    comp_type = request.form.get('type')
    title_key = request.form.get('title_key')
    required_group = request.form.get('required_group', '').strip()

    if not area_key or not comp_type or not title_key:
        return jsonify({'success': False, 'message': 'Parâmetros inválidos.'}), 400

    updated = db_update_item_group(area_key, comp_type, title_key, required_group)
    if updated:
        return jsonify({'success': True, 'message': 'Grupo atualizado com sucesso!'})
    return jsonify({'success': False, 'message': 'Erro ao atualizar grupo.'}), 500


@app.route('/admin/update-area-group', methods=['POST'])
@require_admin_group
def admin_update_area_group():
    area_key = request.form.get('area')
    required_group = request.form.get('required_group', '').strip()

    if not area_key:
        return jsonify({'success': False, 'message': 'Parâmetros inválidos.'}), 400

    updated = db_update_area_group(area_key, required_group)
    if updated:
        return jsonify({'success': True, 'message': 'Grupo da área atualizado com sucesso!'})
    return jsonify({'success': False, 'message': 'Erro ao atualizar grupo.'}), 500


@app.route('/mock-user', methods=['POST'])
def mock_user_toggle():
    if not LOCAL_MODE:
        return redirect(url_for('index'))
    email = request.form.get('email', 'user@example.com').strip()
    is_admin = request.form.get('is_admin') == 'true'
    groups = request.form.get('groups', '').strip()
    
    response = redirect(request.referrer or url_for('index'))
    response.set_cookie('mock_user_email', email, max_age=30*24*60*60)
    response.set_cookie('mock_is_admin', 'true' if is_admin else 'false', max_age=30*24*60*60)
    response.set_cookie('mock_user_groups', groups, max_age=30*24*60*60)
    
    flash(f"Usuário fictício alterado: {email}", "success")
    return response


@app.route('/api/azure-status')
def azure_status():
    """Diagnostic endpoint for OBO / Azure AD integration and user permissions."""
    user_email = get_current_user_email()
    obo_token_present = bool(
        request.headers.get('x-forwarded-access-token', '').strip() or
        request.headers.get('authorization', '').replace('Bearer ', '').strip()
    )
    current_groups = get_current_user_groups()
    is_admin = is_current_user_admin()

    return jsonify({
        'local_mode': LOCAL_MODE,
        'obo_auth': {
            'token_present': obo_token_present,
            'verification_mode': 'OBO (MS Graph /me/transitiveMemberOf & Databricks SCIM)'
        },
        'user_context': {
            'email': user_email,
            'is_admin': is_admin,
            'active_groups': current_groups
        }
    })


if __name__ == '__main__':
    port = int(os.environ.get('DATABRICKS_APP_PORT', os.environ.get('PORT', 8000)))
    from waitress import serve
    print(f"Starting Waitress server on port {port}...")
    serve(app, host='0.0.0.0', port=port)
else:
    # Run schema creation/migration when imported by gunicorn
    if LOCAL_MODE:
        print("[INFO] LOCAL_MODE active — skipping Lakebase schema init.")
        _local_data_snapshot()  # pre-warm in-memory data
    else:
        try:
            ensure_schema()
        except Exception as startup_err:
            print(f"Startup schema init failed: {startup_err}")
