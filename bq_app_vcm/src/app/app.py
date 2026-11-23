import os
import csv
import io
import re
import json
import logging
import unicodedata
import uuid
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, request, Response, send_from_directory, redirect, send_file
from flask_cors import CORS
import pandas as pd
import numpy as np
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bq_vcm")

app = Flask(__name__, static_folder=".")
CORS(app)

# ── Gerenciamento de Tarefas Assíncronas (Gravação em Segundo Plano) ───────────
_VCM_ASYNC_TASKS = {}
_VCM_TASKS_LOCK = threading.Lock()

PORT = int(os.environ.get("PORT", 8000))
CATALOG = os.environ.get("CATALOG", "cat_dnabb_dv")
SCHEMA = os.environ.get("SCHEMA", "grobbbqb_sz")
TABLE = os.environ.get("TABLE", "tbl_bq_vcm")


def get_volume_path():
    """
    Retorna dinamicamente o caminho do Volume Unity Catalog de acordo com o ambiente.
    Identifica automaticamente se a aplicação está rodando em DEV ou PROD através do Databricks Apps runtime.
    """
    catalog = os.environ.get("CATALOG", "cat_dnabb_dv")
    schema = os.environ.get("SCHEMA", "grobbbqb_sz")

    # Identificação de ambiente (DEV vs PROD)
    app_name = (os.environ.get("DATABRICKS_APP_NAME") or "").lower()
    app_url = (os.environ.get("DATABRICKS_APP_URL") or "").lower()
    client_id = (os.environ.get("DATABRICKS_CLIENT_ID") or "").lower()

    # O service principal do bq-vcm-prod no Databricks é eacfe293-081c-4fff-8084-4bd8cc43a885
    is_prod = (
        "prod" in app_name
        or "prod" in app_url
        or client_id == "eacfe293-081c-4fff-8084-4bd8cc43a885"
    )

    try:
        from flask import has_request_context, request
        if has_request_context() and request:
            host = (getattr(request, "host", "") or "").lower()
            if "prod" in host:
                is_prod = True
            elif "dev" in host:
                is_prod = False
    except Exception:
        pass

    # Se explicitamente configurado em VOLUME_PATH:
    env_vol = os.environ.get("VOLUME_PATH", "").strip()
    if env_vol:
        if is_prod and "dev_bq_vcm" in env_vol:
            return env_vol.replace("dev_bq_vcm", "prod_bq_vcm")
        if not is_prod and "prod_bq_vcm" in env_vol:
            return env_vol.replace("prod_bq_vcm", "dev_bq_vcm")
        if is_prod and "default_dev_bq_vcm" in env_vol:
            return env_vol.replace("default_dev_bq_vcm", "prod_bq_vcm")
        if not is_prod and "default_prod_bq_vcm" in env_vol:
            return env_vol.replace("default_prod_bq_vcm", "dev_bq_vcm")
        return env_vol

    target_volume = "prod_bq_vcm" if is_prod else "dev_bq_vcm"
    return f"/Volumes/{catalog}/{schema}/{target_volume}/base_vcm.xlsx"


VOLUME_PATH = get_volume_path()

# ── Cache em memória da Base de Dados Real ─────────────────────────────────────
_cached_df = None
_cached_mtime = 0
_cached_path = None
_cached_updated_at = None
_cached_at = 0.0
_CACHE_TTL_SEC = 300.0  # 5 minutos de cache em memória para resposta instantânea


def _format_updated_timestamp(raw_val):
    """Formata timestamp (epoch, datetime ou string HTTP/ISO) para DD/MM/AAAA HH:MM."""
    if raw_val is None or raw_val == "":
        return None
    try:
        if isinstance(raw_val, (int, float)):
            ts = float(raw_val)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")
        if isinstance(raw_val, datetime):
            return raw_val.strftime("%d/%m/%Y %H:%M")
        s = str(raw_val).strip()
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(s)
            if dt is not None:
                return dt.astimezone().strftime("%d/%m/%Y %H:%M") if dt.tzinfo else dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%d/%m/%Y %H:%M") if dt.tzinfo else dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass
        return s[:16]
    except Exception:
        return None


def _get_base_updated_at():
    """Retorna data/hora formatada da última atualização da base VCM."""
    if _cached_updated_at:
        return _cached_updated_at
    local_candidates = [
        os.path.join(os.path.dirname(__file__), "base_vcm.xlsx"),
        os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "base_vcm.xlsx"),
        "base_vcm.xlsx",
    ]
    for p in local_candidates:
        if os.path.exists(p):
            try:
                return _format_updated_timestamp(os.path.getmtime(p))
            except Exception:
                pass
    return None


def _normalize_col(c):
    """Normaliza nomes de coluna removendo acentuação e pontuações para chave maiúscula."""
    nfd = unicodedata.normalize('NFD', str(c))
    no_accents = ''.join(ch for ch in nfd if unicodedata.category(ch) != 'Mn')
    return re.sub(r'[^A-Z0-9]+', '_', no_accents.strip().upper()).strip('_')


def _processar_dataframe_base(df):
    """
    Sanitiza, tipa e calcula colunas analíticas para o módulo VCM:
    VCM = RECEITA LIQ - (INGREDIENTE + EMBALAGEM + MOD + VARIACAO DE PRECO)
    """
    col_map = {}
    for col in df.columns:
        norm = _normalize_col(col)
        col_map[norm] = col

    # Normaliza nomes para convenção padrão
    df_clean = df.copy()

    # Identifica colunas financeiras
    col_rec = None
    col_ing = None
    col_emb = None
    col_mod = None
    col_var_prc = None
    col_cli = None
    col_desc = None
    col_cenario = None
    col_ano = None
    col_mes = None

    for col in df_clean.columns:
        norm = _normalize_col(col)
        if "RECEITA" in norm and "LIQ" in norm:
            col_rec = col
        elif "INGREDIENTE" in norm:
            col_ing = col
        elif "EMBALAGEM" in norm:
            col_emb = col
        elif norm == "MOD" or "MAO_DE_OBRA" in norm:
            col_mod = col
        elif "VARIACAO" in norm and "PRECO" in norm:
            col_var_prc = col
        elif "CLIENTE" in norm and ("NOME" in norm or "DESC" in norm or "GRUPO" in norm):
            col_cli = col
        elif norm in ("DESCRICAO", "DESC_PRODUTO", "DESCRICAO_PRODUTO", "SKU"):
            col_desc = col
        elif "CENARIO" in norm or "SCENARIO" in norm:
            col_cenario = col
        elif norm == "ANO" or "YEAR" in norm:
            col_ano = col
        elif norm in ("MES", "MESES", "MONTH"):
            col_mes = col

    if col_rec is None:
        for col in df_clean.columns:
            if "RECEITA" in _normalize_col(col):
                col_rec = col
                break

    if col_cli is None:
        for col in df_clean.columns:
            if "CLIENTE" in _normalize_col(col):
                col_cli = col
                break

    # Converte colunas numéricas
    for c in [col_rec, col_ing, col_emb, col_mod, col_var_prc]:
        if c and c in df_clean.columns:
            df_clean[c] = pd.to_numeric(df_clean[c], errors="coerce").fillna(0.0)

    # Padroniza nomes essenciais
    df_clean["RECEITA_LIQ"] = df_clean[col_rec] if col_rec else 0.0
    df_clean["INGREDIENTE"] = df_clean[col_ing] if col_ing else 0.0
    df_clean["EMBALAGEM"] = df_clean[col_emb] if col_emb else 0.0
    df_clean["MOD"] = df_clean[col_mod] if col_mod else 0.0
    df_clean["VARIACAO_DE_PRECO"] = df_clean[col_var_prc] if col_var_prc else 0.0

    # FÓRMULA OFICIAL DE VCM:
    # VCM = RECEITA LIQ - (INGREDIENTE + EMBALAGEM + MOD + VARIACAO DE PRECO)
    df_clean["VCM"] = df_clean["RECEITA_LIQ"] - (
        df_clean["INGREDIENTE"] + df_clean["EMBALAGEM"] + df_clean["MOD"] + df_clean["VARIACAO_DE_PRECO"]
    )

    # Padroniza dimensões
    df_clean["CLIENTE_NORM"] = df_clean[col_cli].fillna("OUTROS").astype(str).str.strip().str.upper() if col_cli else "OUTROS"
    df_clean["DESCRICAO_NORM"] = df_clean[col_desc].fillna("SEM DESCRIÇÃO").astype(str).str.strip().str.upper() if col_desc else "SEM DESCRIÇÃO"
    df_clean["CENARIO_NORM"] = df_clean[col_cenario].fillna("").astype(str).str.strip().str.upper() if col_cenario else ""

    # Extrai Ano e Mês numéricos
    if col_ano and col_ano in df_clean.columns:
        df_clean["ANO_NUM"] = pd.to_numeric(df_clean[col_ano].astype(str).str.extract(r'(\d{4})')[0], errors="coerce").fillna(2026).astype(int)
    else:
        df_clean["ANO_NUM"] = 2026

    if col_mes and col_mes in df_clean.columns:
        dt_mes = pd.to_datetime(df_clean[col_mes], errors="coerce")
        if dt_mes.notna().sum() > 0:
            df_clean["MES_NUM"] = dt_mes.dt.month.fillna(1).astype(int)
        else:
            df_clean["MES_NUM"] = pd.to_numeric(df_clean[col_mes].astype(str).str.extract(r'(\d+)')[0], errors="coerce").fillna(1).astype(int)
    else:
        df_clean["MES_NUM"] = 1

    return df_clean


def _read_excel_safe(source):
    """
    Lê o arquivo Excel suportando com segurança abas como 'Base de VCM',
    'Base VCM', 'Base de Dados' ou a primeira aba disponível.
    """
    try:
        xl = pd.ExcelFile(source)
        for cand in ["Base de VCM", "Base VCM", "Base de Dados", "Sheet1", "VCM"]:
            if cand in xl.sheet_names:
                return xl.parse(cand)
        return xl.parse(xl.sheet_names[0])
    except Exception:
        return pd.read_excel(source)


def _carregar_df_local():
    """Tenta carregar base_vcm.xlsx (com cache parquet ultra-rápido) de caminhos locais."""
    caminhos = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "base_vcm.xlsx")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "base_vcm.xlsx")),
        os.path.abspath("base_vcm.xlsx")
    ]
    for caminho in caminhos:
        if caminho and os.path.exists(caminho):
            try:
                mtime = os.path.getmtime(caminho)
                # Tenta ler parquet cache local se existir e mais recente que o xlsx
                caminho_parquet = os.path.splitext(caminho)[0] + ".parquet"
                if os.path.exists(caminho_parquet) and os.path.getmtime(caminho_parquet) >= mtime:
                    try:
                        df_p = pd.read_parquet(caminho_parquet)
                        if not df_p.empty:
                            return df_p, mtime, caminho, _format_updated_timestamp(mtime)
                    except Exception:
                        pass

                df = _read_excel_safe(caminho)
                df = _processar_dataframe_base(df)
                if not df.empty:
                    try:
                        df.to_parquet(caminho_parquet, index=False)
                    except Exception:
                        pass
                    return df, mtime, caminho, _format_updated_timestamp(mtime)
            except Exception as e:
                logger.error(f"Erro ao processar arquivo local {caminho}: {e}")
    return None, None, None, None


def obter_dados_base(force_refresh=False):
    """
    Carrega a base de dados com alto desempenho:
    - Retorna cópia de cache em memória se TTL < 300s (sub-milissegundo).
    - Se estiver em ambiente Databricks (DATABRICKS_APP_ID/RUNTIME), consulta Volume UC.
    - Se local ou sem SDK, carrega direto de src/app/base_vcm.xlsx sem requisições remotas lentas.
    """
    global _cached_df, _cached_mtime, _cached_path, _cached_updated_at, _cached_at

    now = time.time()
    if not force_refresh and _cached_df is not None and not _cached_df.empty and (now - _cached_at) < _CACHE_TTL_SEC:
        return _cached_df.copy()

    is_databricks_env = bool(
        os.environ.get("DATABRICKS_APP_ID")
        or os.environ.get("DATABRICKS_RUNTIME_VERSION")
        or os.environ.get("DATABRICKS_HOST")
    )

    # 1. Se em nuvem Databricks, prioriza Unity Catalog Volume
    if is_databricks_env:
        catalog = os.environ.get("CATALOG", "cat_dnabb_dv")
        schema = os.environ.get("SCHEMA", "grobbbqb_sz")
        candidates_vol = [
            f"/Volumes/{catalog}/{schema}/prod_bq_vcm/base_vcm.xlsx",
            f"/Volumes/{catalog}/{schema}/dev_bq_vcm/base_vcm.xlsx",
        ]
        for vol_path in candidates_vol:
            try:
                from databricks.sdk import WorkspaceClient
                w = WorkspaceClient()
                meta = w.files.get_metadata(vol_path)
                vol_mtime = str(meta.last_modified or meta.content_length)
                if _cached_df is not None and not _cached_df.empty and _cached_path == vol_path and _cached_mtime == vol_mtime:
                    _cached_at = now
                    return _cached_df.copy()

                logger.info(f"Baixando base do Unity Catalog Volume: {vol_path}")
                resp = w.files.download(vol_path)
                excel_bytes = io.BytesIO(resp.contents.read())
                df = _read_excel_safe(excel_bytes)
                df = _processar_dataframe_base(df)
                if not df.empty:
                    _cached_df = df
                    _cached_mtime = vol_mtime
                    _cached_path = vol_path
                    _cached_updated_at = _format_updated_timestamp(getattr(meta, "last_modified", None))
                    _cached_at = now
                    logger.info(f"Base carregada do Volume ({vol_path}): {len(df)} registros.")
                    return df.copy()
            except Exception as e:
                logger.warning(f"Tentativa no Volume ({vol_path}) falhou: {e}. Testando próximo fallback...")

    # 2. Local ou fallback da nuvem: lê arquivo local direto
    df_loc, mtime_loc, path_loc, upd_loc = _carregar_df_local()
    if df_loc is not None and not df_loc.empty:
        _cached_df = df_loc
        _cached_mtime = mtime_loc
        _cached_path = path_loc
        _cached_updated_at = upd_loc
        _cached_at = now
        logger.info(f"Base carregada do arquivo local ({path_loc}): {len(df_loc)} registros.")
        return df_loc.copy()

    logger.warning("Nenhum arquivo de dados encontrado com registros.")
    return pd.DataFrame()


APP_DIR = os.path.dirname(os.path.abspath(__file__))


# ── GERENCIAMENTO DE IDENTIDADE & ACESSO (PADRÃO BQ LANDING) ──────────────────

_DEFAULT_CADASTROS_ADMINS = [
    "renan.ferreira@grupobimbo.com",
    "144204841771543@8674310331778219",
    "DNA - GB Brasil Leaders"
]

_DEFAULT_CADASTROS_MANAGERS = [
    "jessica.sousa@grupobimbo.com"
]

_DEFAULT_CADASTROS_AUTHORIZED = [
    "sabrina.luzpereira@grupobimbo.com",
    "simone.lopes@grupobimbo.com",
    "patricia.ferreira01@grupobimbo.com",
    "sucena.luque@grupobimbo.com",
    "veronica.hirschhorn@grupobimbo.com",
    "rafael.lobo@grupobimbo.com",
    "GRP_BQ_VENDAS"
]


def _get_current_user_email():
    """
    Extrai o e-mail do usuário autenticado a partir dos cabeçalhos Databricks Apps proxy.
    Resolve identificadores numéricos do Databricks SCIM para o e-mail legível.
    """
    email = (
        request.headers.get("X-Forwarded-Preferred-Username")
        or request.headers.get("X-Forwarded-Email")
        or request.headers.get("X-Databricks-User-Email")
        or request.headers.get("X-User-Email")
        or request.headers.get("X-Auth-Request-Email")
    )
    if not email:
        raw_user = (
            request.headers.get("X-Forwarded-User")
            or request.headers.get("X-Databricks-User-Name")
            or os.environ.get("DATABRICKS_USER", "")
        )
        if raw_user:
            # Se vier o ID numérico SCIM do Databricks (ex: 144204841771543@8674310331778219), mapeia para o e-mail corporativo
            if re.match(r"^\d+@\d+$", raw_user.strip()) or "144204841771543" in raw_user:
                email = "renan.ferreira@grupobimbo.com"
            else:
                email = raw_user

    if not email:
        email = "renan.ferreira@grupobimbo.com"

    return str(email).strip().lower()


def _get_current_user_groups():
    """Extrai os grupos do usuário a partir dos cabeçalhos Databricks Apps proxy."""
    raw = (
        request.headers.get("X-Forwarded-Groups")
        or request.headers.get("X-Databricks-Groups")
        or request.headers.get("X-Databricks-User-Groups")
        or ""
    )
    if not raw:
        return []
    return [g.strip().lower() for g in raw.split(",") if g.strip()]


def _get_cadastros_access_filepath():
    """Retorna o caminho oficial de escrita/leitura de cadastros_access.json."""
    candidates = [
        os.path.join(APP_DIR, "cadastros_access.json"),
        os.path.join("src", "app", "cadastros_access.json"),
        "cadastros_access.json"
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


def _load_cadastros_access():
    """Carrega lista de administradores, gestores e usuários autorizados do arquivo cadastros_access.json."""
    admins = [a.lower() for a in _DEFAULT_CADASTROS_ADMINS]
    managers = [m.lower() for m in _DEFAULT_CADASTROS_MANAGERS]
    authorized = [u.lower() for u in _DEFAULT_CADASTROS_AUTHORIZED]

    p = _get_cadastros_access_filepath()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                cfg = json.load(f)
                for a in cfg.get("admins", []):
                    ca = str(a).strip().lower()
                    if ca and ca not in admins:
                        admins.append(ca)
                if "managers" in cfg and isinstance(cfg["managers"], list):
                    managers = []
                    for m in cfg["managers"]:
                        cm = str(m).strip().lower()
                        if cm and cm not in managers:
                            managers.append(cm)
                if "authorized_users" in cfg and isinstance(cfg["authorized_users"], list):
                    authorized = []
                    for u in cfg["authorized_users"]:
                        cu = str(u).strip().lower()
                        if cu and cu not in authorized:
                            authorized.append(cu)
        except Exception as e:
            logger.warning(f"Não foi possível ler {p}: {e}")

    return {"admins": admins, "managers": managers, "authorized_users": authorized}


def _is_current_user_admin():
    """Verifica se o usuário autenticado na requisição tem papel de administrador geral."""
    email = _get_current_user_email()
    cfg = _load_cadastros_access()
    admins = [a.lower() for a in cfg.get("admins", [])]
    user_groups = _get_current_user_groups()
    return (
        str(email).strip().lower() in admins
        or any(g in admins for g in user_groups)
        or email in ("usuario_portal", "postgres", "admin", "renan.ferreira@grupobimbo.com", "144204841771543@8674310331778219")
    )


def _is_current_user_manager():
    """Verifica se o usuário tem papel de gestor de acessos (concede e revoga autorizações, sem ser admin geral)."""
    email = _get_current_user_email()
    cfg = _load_cadastros_access()
    managers = [m.lower() for m in cfg.get("managers", [])]
    user_groups = _get_current_user_groups()
    clean_email = str(email).strip().lower()
    return (
        clean_email in managers
        or any(g in managers for g in user_groups)
    )


def _can_current_user_manage_access():
    """Verifica se o usuário tem permissão de gerenciar governança de acessos (admin OU gestor)."""
    return _is_current_user_admin() or _is_current_user_manager()


def _is_user_authorized_for_cadastros(email):
    """Verifica se o usuário tem permissão para gerenciar a base VCM."""
    if not email:
        return False
    clean_email = str(email).strip().lower()
    if clean_email in ("usuario_portal", "postgres", "admin", "renan.ferreira@grupobimbo.com", "144204841771543@8674310331778219"):
        return True

    cfg = _load_cadastros_access()
    admins = [a.lower() for a in cfg.get("admins", [])]
    managers = [m.lower() for m in cfg.get("managers", [])]
    authorized = [u.lower() for u in cfg.get("authorized_users", [])]

    if clean_email in admins or clean_email in managers or clean_email in authorized:
        return True

    user_groups = _get_current_user_groups()
    for g in user_groups:
        if g in admins or g in managers or g in authorized:
            return True

    return False


# ── ROTAS DE PÁGINAS & ESTÁTICOS ──────────────────────────────────────────────

@app.route("/")
def home():
    return redirect("/vcm.html")


@app.route("/vcm")
def vcm_redirect():
    return redirect("/vcm.html")


@app.route("/cadastros")
def cadastros_redirect():
    return redirect("/cadastros.html")


@app.route("/guia")
def guia_redirect():
    return redirect("/guia.html")


@app.route("/<path:filename>")
def serve_static(filename):
    for base in [APP_DIR, "."]:
        target = os.path.join(base, filename)
        if os.path.exists(target):
            return send_from_directory(base, filename)
    return send_from_directory(APP_DIR, filename)


# ── ENDPOINTS DE AUTENTICAÇÃO E PERMISSÕES ─────────────────────────────────────

@app.route("/api/auth/me", methods=["GET"])
def api_auth_me():
    """Retorna dados e permissões do usuário logado no formato oficial com suporte a gestor de acessos."""
    email = _get_current_user_email()
    is_auth = _is_user_authorized_for_cadastros(email)
    is_admin = _is_current_user_admin()
    is_manager = _is_current_user_manager()
    can_manage_access = _can_current_user_manage_access()

    if is_admin:
        role_label = "Administrador"
    elif is_manager:
        role_label = "Gestor de Acessos"
    elif is_auth:
        role_label = "Edição de Base autorizada"
    else:
        role_label = "Visualização"

    return jsonify({
        "authenticated": True,
        "email": email,
        "is_admin": is_admin,
        "is_manager": is_manager,
        "can_manage_access": can_manage_access,
        "can_access_cadastros": is_auth,
        "role_label": role_label,
        "base_atualizada_em": _get_base_updated_at()
    })


@app.route("/api/admin/cadastros-access", methods=["GET", "POST"])
def api_admin_cadastros_access():
    """Gerenciamento de governança de acessos para o módulo VCM (Admins e Gestores)."""
    if not _can_current_user_manage_access():
        return jsonify({"error": "Acesso não autorizado. Apenas administradores e gestores podem gerenciar acessos."}), 403

    is_admin = _is_current_user_admin()
    is_manager = _is_current_user_manager()

    p = _get_cadastros_access_filepath()
    cfg = {
        "_comentario": "Gerenciamento de permissoes do modulo de Cadastros e Apoio da Base VCM",
        "admins": list(_DEFAULT_CADASTROS_ADMINS),
        "managers": list(_DEFAULT_CADASTROS_MANAGERS),
        "authorized_users": list(_DEFAULT_CADASTROS_AUTHORIZED),
    }
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    cfg.update(loaded)
        except Exception as e:
            logger.warning(f"Erro ao ler cadastros_access.json: {e}")

    if request.method == "GET":
        return jsonify({
            "admins": cfg.get("admins", []),
            "managers": cfg.get("managers", []),
            "authorized_users": cfg.get("authorized_users", []),
            "current_user_is_admin": is_admin,
            "current_user_is_manager": is_manager
        })

    data = request.get_json(silent=True) or {}
    action = str(data.get("action", "")).strip().lower()
    email = str(data.get("email", "")).strip().lower()
    role_target = str(data.get("role", "authorized")).strip().lower()

    if not email or "@" not in email:
        return jsonify({"error": "Informe um endereço de e-mail corporativo válido."}), 400

    authorized = [str(u).strip().lower() for u in cfg.get("authorized_users", []) if str(u).strip()]
    managers = [str(m).strip().lower() for m in cfg.get("managers", []) if str(m).strip()]
    admins = [str(a).strip().lower() for a in cfg.get("admins", []) if str(a).strip()]

    if action == "add":
        if email in authorized or email in managers or email in admins:
            return jsonify({"error": f"{email} já possui acesso atribuído."}), 409

        if role_target == "manager":
            if not is_admin:
                return jsonify({"error": "Apenas administradores gerais podem promover usuários a Gestor de Acessos."}), 403
            managers.append(email)
            msg = f"Acesso de Gestor de Acessos concedido para {email}."
        else:
            authorized.append(email)
            msg = f"Acesso concedido para {email}."

    elif action == "remove":
        if email in admins:
            return jsonify({"error": "Administradores não podem ser removidos por esta tela."}), 409
        if email in managers:
            if not is_admin:
                return jsonify({"error": "Gestores de acesso não podem revogar outros gestores. Apenas administradores gerais podem."}), 403
            managers = [m for m in managers if m != email]
            msg = f"Acesso de gestor revogado para {email}."
        elif email in authorized:
            authorized = [u for u in authorized if u != email]
            msg = f"Acesso revogado para {email}."
        else:
            return jsonify({"error": f"{email} não encontrado na lista de autorizados."}), 404
    else:
        return jsonify({"error": "Ação inválida. Use 'add' ou 'remove'."}), 400

    cfg["admins"] = admins
    cfg["managers"] = managers
    cfg["authorized_users"] = authorized
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        logger.error(f"Erro ao salvar cadastros_access.json: {e}")
        return jsonify({"error": f"Falha ao salvar alterações: {e}"}), 500

    return jsonify({
        "ok": True,
        "message": msg,
        "admins": admins,
        "managers": managers,
        "authorized_users": authorized,
        "current_user_is_admin": is_admin,
        "current_user_is_manager": is_manager
    })


@app.route("/api/user")
def api_user():
    return jsonify({"user": _get_current_user_email()})


@app.route("/api/check_access")
def api_check_access():
    """Valida se o usuário tem permissão para a aba de Cadastros/Base."""
    email = _get_current_user_email()
    is_auth = _is_user_authorized_for_cadastros(email)
    cfg = _load_cadastros_access()
    return jsonify({
        "user": email,
        "authorized": is_auth,
        "authorized_users": cfg.get("authorized_users", []) + cfg.get("admins", [])
    })


@app.route("/api/refresh", methods=["GET", "POST"])
def refresh_cache():
    """Força re-carregamento imediato da base."""
    global _cached_df, _cached_mtime, _cached_path, _cached_updated_at
    _cached_df = None
    _cached_mtime = 0
    _cached_path = None
    try:
        df = obter_dados_base()
        return jsonify({"sucesso": True, "registros": len(df), "mensagem": "Cache atualizado com sucesso."})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


# ── ENDPOINTS DE RESUMO DE BASE (COMPATIBILIDADE CADASTROS.HTML) ───────────────

@app.route("/api/lookups/summary", methods=["GET"])
def lookups_summary():
    """Resumo das estatísticas da Base VCM para alimentar os 4 cards da tela de gestão."""
    df = obter_dados_base()
    total_reg = len(df)
    qtd_clientes = df["CLIENTE_NORM"].nunique() if "CLIENTE_NORM" in df.columns else 0
    cenarios = df["CENARIO_NORM"].unique().tolist() if "CENARIO_NORM" in df.columns else []
    cenarios_limpos = [c for c in cenarios if c]

    tables = [{
        "key": "base_vcm",
        "title": "Base de VCM",
        "description": "Base analítica de VCM, Receita e Custos por Cliente e Produto",
        "total": total_reg,
        "linhas_clientes": qtd_clientes,
        "cenarios_count": len(cenarios_limpos),
        "excel_filename": "Base - VCM.xlsx"
    }]

    return jsonify({
        "success": True,
        "tables": tables,
        "stats": {
            "total": total_reg,
            "clientes": qtd_clientes,
            "cenarios": len(cenarios_limpos)
        },
        "user": _get_current_user_email()
    })



# ── FILTROS E RELATÓRIO ANALÍTICO VCM ─────────────────────────────────────────

@app.route("/api/filtros")
def get_filtros():
    """Retorna opções únicas para cada filtro dropdown."""
    df = obter_dados_base()
    if df.empty:
        return jsonify({
            "sucesso": True,
            "anos": ["2026", "2025", "2024"],
            "meses": [str(m) for m in range(1, 13)],
            "canais": ["DISTRIBUIDORES", "FOOD SERVICE", "KEY ACCOUNT"],
            "diretores": ["ANTONIO VITORINO"],
            "gestores": ["BRUNO UVINHA"],
            "categorias": ["Buns", "No Buns"],
            "linhas": ["BUNS FOOD"],
            "marcas": ["BRIOCHE"]
        })

    def get_unicos(col_name):
        if col_name in df.columns:
            vals = df[col_name].dropna().astype(str).unique().tolist()
            return sorted([v.strip() for v in vals if v.strip() and v != "nan" and v != "-" and v.lower() != "todos" and "CLIENTES E FORNECEDORES" not in v.upper()])
        return []

    anos_unicos = get_unicos("ANO_NUM") or ["2026", "2025", "2024"]
    try:
        anos_ordenados = sorted(list(set(anos_unicos)), key=lambda a: int(a), reverse=True)
    except Exception:
        anos_ordenados = sorted(list(set(anos_unicos)), reverse=True)

    if "MES_NUM" in df.columns:
        m_vals = df["MES_NUM"].dropna().unique().tolist()
        try:
            meses_ordenados = sorted([str(int(m)) for m in m_vals if int(m) >= 1 and int(m) <= 12], key=lambda x: int(x))
        except Exception:
            meses_ordenados = [str(m) for m in range(1, 13)]
    else:
        meses_ordenados = [str(m) for m in range(1, 13)]
    if not meses_ordenados:
        meses_ordenados = [str(m) for m in range(1, 13)]

    ultimo_mes_realizado = None
    try:
        if anos_ordenados and "ANO_NUM" in df.columns and "MES_NUM" in df.columns and "CENARIO_NORM" in df.columns:
            ano_ref = int(anos_ordenados[0])
            df_act_ano = df[(df["ANO_NUM"] == ano_ref) & (df["CENARIO_NORM"].str.contains("CY", na=False))]
            if not df_act_ano.empty:
                grp_m = df_act_ano.groupby("MES_NUM")[["VCM", "RECEITA_LIQ"]].apply(
                    lambda g: (g["VCM"].abs().sum() > 0) or (g["RECEITA_LIQ"].abs().sum() > 0)
                )
                meses_com_act = [int(m) for m, has_val in grp_m.items() if has_val and 1 <= int(m) <= 12]
                if meses_com_act:
                    ultimo_mes_realizado = str(max(meses_com_act))
    except Exception:
        ultimo_mes_realizado = None

    return jsonify({
        "sucesso": True,
        "anos": anos_ordenados,
        "meses": meses_ordenados,
        "ultimo_mes_realizado": ultimo_mes_realizado,
        "base_atualizada_em": _get_base_updated_at(),
        "canais": get_unicos("CHANNEL"),
        "clientes": get_unicos("CLIENTE_NORM") or get_unicos("NOME CLIENTE"),
        "diretores": get_unicos("DIRETOR"),
        "gestores": get_unicos("GESTOR"),
        "supervisores": get_unicos("SUPERVISOR"),
        "coordenadores": get_unicos("COORDENADOR"),
        "categorias": get_unicos("CATEGORIA"),
        "linhas": get_unicos("LINHA"),
        "marcas": get_unicos("MARCA"),
        "familias": get_unicos("FAMILIAPRODUTO"),
        "plantas": get_unicos("PLANTA"),
        "descricoes": get_unicos("DESCRICAO_NORM") or get_unicos("DESCRICAO")
    })


def aplicar_filtros_df(df, args):
    """Filtra DataFrame pelas dimensões selecionadas."""
    if df.empty:
        return df

    df_f = df.copy()
    mapeamento = [
        ("canal", "CHANNEL"),
        ("cliente", "CLIENTE_NORM"),
        ("diretor", "DIRETOR"),
        ("gestor", "GESTOR"),
        ("supervisor", "SUPERVISOR"),
        ("coordenador", "COORDENADOR"),
        ("categoria", "CATEGORIA"),
        ("linha", "LINHA"),
        ("marca", "MARCA"),
        ("familia", "FAMILIAPRODUTO"),
        ("planta", "PLANTA"),
        ("descricao", "DESCRICAO_NORM")
    ]

    for param, col in mapeamento:
        if hasattr(args, "getlist"):
            vals = args.getlist(param)
        else:
            p_val = args.get(param, [])
            vals = p_val if isinstance(p_val, list) else ([p_val] if p_val else [])
        all_vals = []
        for v in vals:
            all_vals.extend([x.strip() for x in str(v).split(",") if x.strip()])
        if not all_vals:
            continue
        if "__NONE__" in all_vals:
            return df_f.iloc[0:0]
        if col in df_f.columns:
            mask = df_f[col].astype(str).str.strip().isin(all_vals)
            df_f = df_f[mask]

    return df_f


def _resolver_periodo_vcm(args):
    """Extrai ano selecionado, ano anterior e lista de meses a partir dos parâmetros da requisição (dict ou MultiDict)."""
    ano_param = args.get("ano", "2026")
    try:
        ano_sel = int(ano_param)
    except Exception:
        ano_sel = 2026
    ano_py = ano_sel - 1

    if hasattr(args, "getlist"):
        meses_param = args.getlist("mes")
    else:
        m_val = args.get("mes", [])
        meses_param = m_val if isinstance(m_val, list) else [m_val]

    meses_sel = []

    if any(str(m).lower() == "all" for m in meses_param):
        meses_sel = list(range(1, 13))
    else:
        for m in meses_param:
            for item in str(m).split(","):
                item = item.strip()
                if item.isdigit():
                    meses_sel.append(int(item))

    if not meses_sel:
        if not args:
            meses_sel = [datetime.now().month]
        else:
            meses_sel = list(range(1, 13))

    return ano_sel, ano_py, meses_sel


def _calcular_linha_vcm(label, key_name, c_act, c_act_r, c_bgt, c_bgt_r, c_py, c_py_r):
    """Calcula variações e margens percentuais para uma linha consolidada de VCM."""
    var_bgt = ((c_act / c_bgt - 1.0) * 100.0) if c_bgt != 0 else 0.0
    var_py = ((c_act / c_py - 1.0) * 100.0) if c_py != 0 else 0.0
    act_pct = (c_act / c_act_r * 100.0) if c_act_r != 0 else 0.0
    bgt_pct = (c_bgt / c_bgt_r * 100.0) if c_bgt_r != 0 else 0.0
    py_pct = (c_py / c_py_r * 100.0) if c_py_r != 0 else 0.0
    return {
        key_name: label,
        "act": c_act,
        "bgt": c_bgt,
        "var_bgt": var_bgt,
        "py": c_py,
        "var_py": var_py,
        "act_pct": act_pct,
        "bgt_pct": bgt_pct,
        "py_pct": py_pct
    }


def _agregar_vcm_por_dimensao(df_raw, args, group_col, output_key, cliente_alvo=None, busca_texto=""):
    """Agrega VCM e Receita Líquida por dimensão (Cliente ou SKU) respeitando filtros e período."""
    df = aplicar_filtros_df(df_raw, args)
    if cliente_alvo and "CLIENTE_NORM" in df.columns:
        df = df[df["CLIENTE_NORM"].astype(str).str.strip().str.upper() == cliente_alvo.strip().upper()]

    ano_sel, ano_py, meses_sel = _resolver_periodo_vcm(args)
    df_periodo = df[df["MES_NUM"].isin(meses_sel)].copy() if meses_sel else df.copy()

    totais_vazios = {
        "act": 0.0, "bgt": 0.0, "var_bgt": 0.0,
        "py": 0.0, "var_py": 0.0,
        "act_pct": 0.0, "bgt_pct": 0.0, "py_pct": 0.0
    }
    if df_periodo.empty or group_col not in df_periodo.columns:
        return [], totais_vazios, ano_sel, meses_sel

    mask_act = (df_periodo["ANO_NUM"] == ano_sel) & (df_periodo["CENARIO_NORM"].str.contains("CY"))
    mask_bgt = (df_periodo["ANO_NUM"] == ano_sel) & (df_periodo["CENARIO_NORM"].str.contains("BGT"))
    mask_py = (df_periodo["ANO_NUM"] == ano_py) & (df_periodo["CENARIO_NORM"].str.contains("CY"))

    df_act = df_periodo[mask_act].groupby(group_col, as_index=False).agg(act_vcm=("VCM", "sum"), act_rec=("RECEITA_LIQ", "sum"))
    df_bgt = df_periodo[mask_bgt].groupby(group_col, as_index=False).agg(bgt_vcm=("VCM", "sum"), bgt_rec=("RECEITA_LIQ", "sum"))
    df_py = df_periodo[mask_py].groupby(group_col, as_index=False).agg(py_vcm=("VCM", "sum"), py_rec=("RECEITA_LIQ", "sum"))

    todos_grupos = sorted(list(set(
        df_act[group_col].tolist() + df_bgt[group_col].tolist() + df_py[group_col].tolist()
    )))
    if group_col == "CLIENTE_NORM":
        todos_grupos = [g for g in todos_grupos if "CLIENTES E FORNECEDORES" not in str(g).upper()]

    map_act_vcm = dict(zip(df_act[group_col], df_act["act_vcm"]))
    map_act_rec = dict(zip(df_act[group_col], df_act["act_rec"]))
    map_bgt_vcm = dict(zip(df_bgt[group_col], df_bgt["bgt_vcm"]))
    map_bgt_rec = dict(zip(df_bgt[group_col], df_bgt["bgt_rec"]))
    map_py_vcm = dict(zip(df_py[group_col], df_py["py_vcm"]))
    map_py_rec = dict(zip(df_py[group_col], df_py["py_rec"]))

    busca_lower = busca_texto.strip().lower()
    tabela = []
    tot_act_vcm = tot_act_rec = tot_bgt_vcm = tot_bgt_rec = tot_py_vcm = tot_py_rec = 0.0

    for grp in todos_grupos:
        if busca_lower and busca_lower not in str(grp).lower():
            continue

        c_act = float(map_act_vcm.get(grp, 0.0))
        c_act_r = float(map_act_rec.get(grp, 0.0))
        c_bgt = float(map_bgt_vcm.get(grp, 0.0))
        c_bgt_r = float(map_bgt_rec.get(grp, 0.0))
        c_py = float(map_py_vcm.get(grp, 0.0))
        c_py_r = float(map_py_rec.get(grp, 0.0))

        tot_act_vcm += c_act
        tot_act_rec += c_act_r
        tot_bgt_vcm += c_bgt
        tot_bgt_rec += c_bgt_r
        tot_py_vcm += c_py
        tot_py_rec += c_py_r

        tabela.append(_calcular_linha_vcm(grp, output_key, c_act, c_act_r, c_bgt, c_bgt_r, c_py, c_py_r))

    totais = _calcular_linha_vcm("TOTAL GERAL", "_total", tot_act_vcm, tot_act_rec, tot_bgt_vcm, tot_bgt_rec, tot_py_vcm, tot_py_rec)
    totais.pop("_total", None)
    return tabela, totais, ano_sel, meses_sel


@app.route("/api/vcm")
def get_vcm_data():
    """
    Retorna o relatório analítico de VCM por Cliente, consolidando ACT, BGT, Var BGT, PY, Var PY, ACT%, BGT% e PY%.
    """
    df_raw = obter_dados_base()
    if df_raw.empty:
        return jsonify({
            "sucesso": True,
            "clientes": [],
            "totais": {},
            "ano": 2026,
            "meses": [datetime.now().month],
            "qtd_clientes": 0
        })

    busca_cli = request.args.get("busca_cliente", "").strip()
    tabela, totais, ano_sel, meses_sel = _agregar_vcm_por_dimensao(
        df_raw, request.args, "CLIENTE_NORM", "client", busca_texto=busca_cli
    )

    return jsonify({
        "sucesso": True,
        "clientes": tabela,
        "totais": totais,
        "ano": ano_sel,
        "meses": meses_sel,
        "qtd_clientes": len(tabela)
    })


@app.route("/api/vcm/skus")
def get_vcm_skus():
    """
    Retorna o detalhamento (drill-down) de VCM por SKU (DESCRICAO) para um cliente específico ou para todos (__ALL__).
    """
    cliente_alvo = request.args.get("cliente_alvo", "").strip()
    if not cliente_alvo:
        return jsonify({"sucesso": False, "erro": "Parâmetro cliente_alvo é obrigatório.", "skus": []}), 400

    df_raw = obter_dados_base()
    if df_raw.empty:
        return jsonify({"sucesso": True, "cliente": cliente_alvo, "skus": [], "skus_por_cliente": {}})

    if cliente_alvo == "__ALL__":
        df = aplicar_filtros_df(df_raw, request.args)
        ano_sel, ano_py, meses_sel = _resolver_periodo_vcm(request.args)
        df_periodo = df[df["MES_NUM"].isin(meses_sel)].copy() if meses_sel else df.copy()
        if df_periodo.empty or "CLIENTE_NORM" not in df_periodo.columns or "DESCRICAO_NORM" not in df_periodo.columns:
            return jsonify({"sucesso": True, "skus_por_cliente": {}, "ano": ano_sel, "meses": meses_sel})

        mask_act = (df_periodo["ANO_NUM"] == ano_sel) & (df_periodo["CENARIO_NORM"].str.contains("CY"))
        mask_bgt = (df_periodo["ANO_NUM"] == ano_sel) & (df_periodo["CENARIO_NORM"].str.contains("BGT"))
        mask_py = (df_periodo["ANO_NUM"] == ano_py) & (df_periodo["CENARIO_NORM"].str.contains("CY"))

        df_act = df_periodo[mask_act].groupby(["CLIENTE_NORM", "DESCRICAO_NORM"])[["VCM", "RECEITA_LIQ"]].sum()
        df_bgt = df_periodo[mask_bgt].groupby(["CLIENTE_NORM", "DESCRICAO_NORM"])[["VCM", "RECEITA_LIQ"]].sum()
        df_py = df_periodo[mask_py].groupby(["CLIENTE_NORM", "DESCRICAO_NORM"])[["VCM", "RECEITA_LIQ"]].sum()

        df_act.columns = ["act", "act_r"]
        df_bgt.columns = ["bgt", "bgt_r"]
        df_py.columns = ["py", "py_r"]

        merged = df_act.join(df_bgt, how="outer").join(df_py, how="outer").fillna(0.0).reset_index()
        skus_por_cliente = {}
        for row in merged.itertuples(index=False):
            c_name = str(row.CLIENTE_NORM).strip()
            if not c_name or "CLIENTES E FORNECEDORES" in c_name.upper():
                continue
            line = _calcular_linha_vcm(str(row.DESCRICAO_NORM).strip(), "sku", row.act, row.act_r, row.bgt, row.bgt_r, row.py, row.py_r)
            if c_name not in skus_por_cliente:
                skus_por_cliente[c_name] = []
            skus_por_cliente[c_name].append(line)

        for c in skus_por_cliente:
            skus_por_cliente[c].sort(key=lambda x: x.get("act", 0.0), reverse=True)

        return jsonify({
            "sucesso": True,
            "skus_por_cliente": skus_por_cliente,
            "ano": ano_sel,
            "meses": meses_sel
        })

    skus, totais, ano_sel, meses_sel = _agregar_vcm_por_dimensao(
        df_raw, request.args, "DESCRICAO_NORM", "sku", cliente_alvo=cliente_alvo
    )
    skus.sort(key=lambda x: x.get("act", 0.0), reverse=True)

    return jsonify({
        "sucesso": True,
        "cliente": cliente_alvo,
        "skus": skus,
        "totais": totais,
        "ano": ano_sel,
        "meses": meses_sel,
        "qtd_skus": len(skus)
    })




@app.route("/api/vcm/export_excel", methods=["POST"])
def api_vcm_export_excel():
    """
    Gera pasta de trabalho Excel (.xlsx) nativa oficial com 2 abas:
    1. 'VCM por SKU': visão granular completa por Cliente e SKU (DESCRICAO)
    2. 'VCM por Cliente': consolidado analítico por cliente
    Ambas com tabela oficial do Excel (TableStyleMedium9), formatação R$ e percentual.
    """
    import io
    import openpyxl
    from openpyxl.worksheet.table import Table, TableStyleInfo
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    data = request.get_json() or {}
    rows_clientes = data.get("rows", [])
    totais = data.get("totais")
    filters = data.get("filters", {})

    # Se rows não foi passado, tenta carregar dados analíticos
    df_raw = obter_dados_base()

    wb = openpyxl.Workbook()

    # Formatação comum
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_align_right = Alignment(horizontal="right", vertical="center", wrap_text=True)
    header_align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    fmt_currency = '"R$" #,##0'
    fmt_pct_var = '+0.0%;-0.0%;0.0%'
    fmt_pct = '0.0%'

    # ── ABA 1: VCM POR SKU (GRANULAR) ─────────────────────────────────────────
    ws_sku = wb.active
    ws_sku.title = "VCM por SKU"
    ws_sku.views.sheetView[0].showGridLines = True

    sku_headers = ["CLIENT", "DESCRICAO / SKU", "ACT VCM", "BGT VCM", "Var BGT", "PY", "Var PY", "ACT%", "BGT%", "PY%"]
    ws_sku.append(sku_headers)

    for col_idx in range(1, len(sku_headers) + 1):
        c = ws_sku.cell(row=1, column=col_idx)
        c.font = header_font
        c.fill = header_fill
        c.alignment = header_align_left if col_idx in (1, 2) else header_align_right

    # Agrupa por CLIENTE e SKU a partir do DataFrame filtrado
    sku_rows_count = 0
    tot_sku_act = 0.0
    tot_sku_bgt = 0.0
    tot_sku_py = 0.0
    tot_sku_act_rec = 0.0
    tot_sku_bgt_rec = 0.0
    tot_sku_py_rec = 0.0

    if not df_raw.empty:
        # Mescla filtros recebidos no body com querystring se houver
        args_filtros = dict(filters) if isinstance(filters, dict) else {}
        for k, v in request.args.items():
            if k not in args_filtros:
                args_filtros[k] = v

        ano_sel, ano_py, meses_sel = _resolver_periodo_vcm(args_filtros)
        df_f = aplicar_filtros_df(df_raw, args_filtros)
        df_periodo = df_f[df_f["MES_NUM"].isin(meses_sel)].copy() if meses_sel else df_f.copy()

        if not df_periodo.empty and "CLIENTE_NORM" in df_periodo.columns and "DESCRICAO_NORM" in df_periodo.columns:
            mask_act = (df_periodo["ANO_NUM"] == ano_sel) & (df_periodo["CENARIO_NORM"].str.contains("CY"))
            mask_bgt = (df_periodo["ANO_NUM"] == ano_sel) & (df_periodo["CENARIO_NORM"].str.contains("BGT"))
            mask_py = (df_periodo["ANO_NUM"] == ano_py) & (df_periodo["CENARIO_NORM"].str.contains("CY"))

            grp_cols = ["CLIENTE_NORM", "DESCRICAO_NORM"]
            df_act = df_periodo[mask_act].groupby(grp_cols, as_index=False).agg(act_vcm=("VCM", "sum"), act_rec=("RECEITA_LIQ", "sum"))
            df_bgt = df_periodo[mask_bgt].groupby(grp_cols, as_index=False).agg(bgt_vcm=("VCM", "sum"), bgt_rec=("RECEITA_LIQ", "sum"))
            df_py = df_periodo[mask_py].groupby(grp_cols, as_index=False).agg(py_vcm=("VCM", "sum"), py_rec=("RECEITA_LIQ", "sum"))

            m = pd.merge(df_act, df_bgt, on=grp_cols, how="outer")
            m = pd.merge(m, df_py, on=grp_cols, how="outer").fillna(0.0)
            m = m[~m["CLIENTE_NORM"].astype(str).str.contains("CLIENTES E FORNECEDORES", case=False, na=False)]
            m.sort_values(by=["CLIENTE_NORM", "act_vcm"], ascending=[True, False], inplace=True)

            r_idx = 2
            for _, r in m.iterrows():
                cli_val = str(r["CLIENTE_NORM"])
                sku_val = str(r["DESCRICAO_NORM"])
                c_act = float(r.get("act_vcm", 0.0))
                c_act_r = float(r.get("act_rec", 0.0))
                c_bgt = float(r.get("bgt_vcm", 0.0))
                c_bgt_r = float(r.get("bgt_rec", 0.0))
                c_py = float(r.get("py_vcm", 0.0))
                c_py_r = float(r.get("py_rec", 0.0))

                var_bgt = (c_act / c_bgt - 1.0) if c_bgt != 0 else 0.0
                var_py = (c_act / c_py - 1.0) if c_py != 0 else 0.0
                act_pct = (c_act / c_act_r) if c_act_r != 0 else 0.0
                bgt_pct = (c_bgt / c_bgt_r) if c_bgt_r != 0 else 0.0
                py_pct = (c_py / c_py_r) if c_py_r != 0 else 0.0

                tot_sku_act += c_act
                tot_sku_bgt += c_bgt
                tot_sku_py += c_py
                tot_sku_act_rec += c_act_r
                tot_sku_bgt_rec += c_bgt_r
                tot_sku_py_rec += c_py_r

                ws_sku.append([cli_val, sku_val, c_act, c_bgt, var_bgt, c_py, var_py, act_pct, bgt_pct, py_pct])

                for col_idx in range(1, 11):
                    cell = ws_sku.cell(row=r_idx, column=col_idx)
                    cell.font = Font(name="Calibri", size=10)
                    if col_idx in (1, 2):
                        cell.alignment = Alignment(horizontal="left", vertical="center")
                    elif col_idx in (3, 4, 6):
                        cell.number_format = fmt_currency
                        cell.alignment = Alignment(horizontal="right", vertical="center")
                    elif col_idx in (5, 7):
                        cell.number_format = fmt_pct_var
                        cell.alignment = Alignment(horizontal="right", vertical="center")
                    elif col_idx in (8, 9, 10):
                        cell.number_format = fmt_pct
                        cell.alignment = Alignment(horizontal="right", vertical="center")
                r_idx += 1
            sku_rows_count = len(m)

    if sku_rows_count > 0:
        tab_sku = Table(displayName="TabelaVCMSKUs", ref=f"A1:J{sku_rows_count + 1}")
        tab_sku.tableStyleInfo = TableStyleInfo(name="TableStyleMedium9", showRowStripes=True)
        ws_sku.add_table(tab_sku)

        # Total SKU
        tot_row_idx = sku_rows_count + 2
        var_bgt_tot = (tot_sku_act / tot_sku_bgt - 1.0) if tot_sku_bgt != 0 else 0.0
        var_py_tot = (tot_sku_act / tot_sku_py - 1.0) if tot_sku_py != 0 else 0.0
        act_pct_tot = (tot_sku_act / tot_sku_act_rec) if tot_sku_act_rec != 0 else 0.0
        bgt_pct_tot = (tot_sku_bgt / tot_sku_bgt_rec) if tot_sku_bgt_rec != 0 else 0.0
        py_pct_tot = (tot_sku_py / tot_sku_py_rec) if tot_sku_py_rec != 0 else 0.0

        ws_sku.append(["TOTAL GERAL", "", tot_sku_act, tot_sku_bgt, var_bgt_tot, tot_sku_py, var_py_tot, act_pct_tot, bgt_pct_tot, py_pct_tot])

        border_total = Border(top=Side(style="thin", color="1E293B"), bottom=Side(style="double", color="1E293B"))
        fill_total = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        font_total = Font(name="Calibri", size=11, bold=True, color="0F172A")

        for col_idx in range(1, 11):
            cell = ws_sku.cell(row=tot_row_idx, column=col_idx)
            cell.font = font_total
            cell.fill = fill_total
            cell.border = border_total
            if col_idx in (1, 2):
                cell.alignment = Alignment(horizontal="left", vertical="center")
            elif col_idx in (3, 4, 6):
                cell.number_format = fmt_currency
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (5, 7):
                cell.number_format = fmt_pct_var
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (8, 9, 10):
                cell.number_format = fmt_pct
                cell.alignment = Alignment(horizontal="right", vertical="center")

    for col in ws_sku.columns:
        max_len = 0
        for cell in col:
            val = str(cell.value or "")
            if len(val) > max_len:
                max_len = len(val)
        col_letter = get_column_letter(col[0].column)
        ws_sku.column_dimensions[col_letter].width = max(max_len + 4, 14)
    ws_sku.column_dimensions["A"].width = max(ws_sku.column_dimensions["A"].width, 24)
    ws_sku.column_dimensions["B"].width = max(ws_sku.column_dimensions["B"].width, 32)

    # ── ABA 2: VCM POR CLIENTE ────────────────────────────────────────────────
    ws_cli = wb.create_sheet(title="VCM por Cliente")
    ws_cli.views.sheetView[0].showGridLines = True

    cli_headers = ["CLIENT", "ACT VCM", "BGT VCM", "Var BGT", "PY", "Var PY", "ACT%", "BGT%", "PY%"]
    ws_cli.append(cli_headers)

    for col_idx in range(1, len(cli_headers) + 1):
        c = ws_cli.cell(row=1, column=col_idx)
        c.font = header_font
        c.fill = header_fill
        c.alignment = header_align_left if col_idx == 1 else header_align_right

    start_row = 2
    for r_idx, r in enumerate(rows_clientes, start=start_row):
        client_name = str(r.get("client") or "")
        act_val = float(r.get("act") or 0)
        bgt_val = float(r.get("bgt") or 0)
        var_bgt_val = float(r.get("var_bgt") or 0) / 100.0
        py_val = float(r.get("py") or 0)
        var_py_val = float(r.get("var_py") or 0) / 100.0
        act_pct_val = float(r.get("act_pct") or 0) / 100.0
        bgt_pct_val = float(r.get("bgt_pct") or 0) / 100.0
        py_pct_val = float(r.get("py_pct") or 0) / 100.0

        row_data = [
            client_name,
            act_val,
            bgt_val,
            var_bgt_val,
            py_val,
            var_py_val,
            act_pct_val,
            bgt_pct_val,
            py_pct_val
        ]
        ws_cli.append(row_data)

        for col_idx in range(1, 10):
            cell = ws_cli.cell(row=r_idx, column=col_idx)
            cell.font = Font(name="Calibri", size=10)
            if col_idx == 1:
                cell.alignment = Alignment(horizontal="left", vertical="center")
            elif col_idx in (2, 3, 5):
                cell.number_format = fmt_currency
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (4, 6):
                cell.number_format = fmt_pct_var
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (7, 8, 9):
                cell.number_format = fmt_pct
                cell.alignment = Alignment(horizontal="right", vertical="center")

    if rows_clientes:
        end_data_row = start_row + len(rows_clientes) - 1
        tab_cli = Table(displayName="TabelaVCMClientes", ref=f"A1:I{end_data_row}")
        tab_cli.tableStyleInfo = TableStyleInfo(name="TableStyleMedium9", showRowStripes=True)
        ws_cli.add_table(tab_cli)

        total_row_idx = end_data_row + 1
        if totais:
            tot_act = float(totais.get("act") or 0)
            tot_bgt = float(totais.get("bgt") or 0)
            tot_var_bgt = float(totais.get("var_bgt") or 0) / 100.0
            tot_py = float(totais.get("py") or 0)
            tot_var_py = float(totais.get("var_py") or 0) / 100.0
            tot_act_pct = float(totais.get("act_pct") or 0) / 100.0
            tot_bgt_pct = float(totais.get("bgt_pct") or 0) / 100.0
            tot_py_pct = float(totais.get("py_pct") or 0) / 100.0

            tot_data = [
                "TOTAL GERAL",
                tot_act,
                tot_bgt,
                tot_var_bgt,
                tot_py,
                tot_var_py,
                tot_act_pct,
                tot_bgt_pct,
                tot_py_pct
            ]
            ws_cli.append(tot_data)

            border_top = Border(top=Side(style="thin", color="1E293B"), bottom=Side(style="double", color="1E293B"))
            total_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
            total_font = Font(name="Calibri", size=11, bold=True, color="0F172A")

            for col_idx in range(1, 10):
                cell = ws_cli.cell(row=total_row_idx, column=col_idx)
                cell.font = total_font
                cell.fill = total_fill
                cell.border = border_top
                if col_idx == 1:
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                elif col_idx in (2, 3, 5):
                    cell.number_format = fmt_currency
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif col_idx in (4, 6):
                    cell.number_format = fmt_pct_var
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif col_idx in (7, 8, 9):
                    cell.number_format = fmt_pct
                    cell.alignment = Alignment(horizontal="right", vertical="center")

    for col in ws_cli.columns:
        max_len = 0
        for cell in col:
            val = str(cell.value or "")
            if len(val) > max_len:
                max_len = len(val)
        col_letter = get_column_letter(col[0].column)
        ws_cli.column_dimensions[col_letter].width = max(max_len + 5, 14)
    ws_cli.column_dimensions["A"].width = max(ws_cli.column_dimensions["A"].width, 28)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"Rentabilidade_VCM_Clientes_SKU_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route("/api/download/base")
def download_base():
    """Download do arquivo base_vcm.xlsx ativo diretamente do Volume oficial."""
    vol_path = get_volume_path()
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        resp = w.files.download(vol_path)
        return send_file(
            io.BytesIO(resp.contents.read()),
            as_attachment=True,
            download_name="Base - VCM.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        logger.warning(f"Download direto do Volume falhou ({e}). Tentando arquivo local...")
        caminho = os.path.join(APP_DIR, "base_vcm.xlsx")
        if not os.path.exists(caminho):
            return jsonify({"sucesso": False, "erro": "Arquivo base_vcm.xlsx não encontrado."}), 404
        return send_file(
            caminho,
            as_attachment=True,
            download_name="Base - VCM.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


@app.route("/api/download/modelo")
def download_modelo():
    """Download do modelo oficial modelo_vcm.xlsx."""
    caminho = os.path.join(APP_DIR, "modelo_vcm.xlsx")
    if not os.path.exists(caminho):
        caminho = os.path.join(APP_DIR, "base_vcm.xlsx")
    return send_file(
        caminho,
        as_attachment=True,
        download_name="Modelo VCM - Dna Vendas.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )





# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DA BASE VCM (LOOKUP_CONFIG) + MOTOR DE MESCLAR INTELIGENTE
# Padrão idêntico ao bq_app_landing para consistência total.
# ═══════════════════════════════════════════════════════════════════════════════

LOOKUP_CONFIG_VCM = {
    "base_vcm": {
        "title": "Base de VCM",
        "description": "Base analítica de VCM, Receita e Custos por Cliente e Produto",
        "table_name": "base_vcm",
        "excel_filename": "base_vcm.xlsx",
        "primary_key": "nome_cliente",
        "composite_keys": [
            "ano",
            "mes",
            "cenario",
            "nome_cliente",
            "id_cliente",
            "gestor",
            "diretor",
            "supervisor",
            "coordenador",
            "tp_produto",
            "planta",
            "marca",
            "familiaproduto",
            "familiaprodutodetalhe",
            "categoria",
            "bpc_category",
            "linha",
            "channel",
            "descricao",
            "item"
        ],
        "columns": [
            {"key": "ano",                    "label": "ANO",                  "required": True,  "type": "number"},
            {"key": "mes",                    "label": "MES",                  "required": True,  "type": "text"},
            {"key": "cenario",                "label": "CENARIO",              "required": True,  "type": "text"},
            {"key": "nome_cliente",           "label": "NOME CLIENTE",         "required": True,  "type": "text"},
            {"key": "id_cliente",             "label": "ID CLIENTE",           "required": False, "type": "number"},
            {"key": "gestor",                 "label": "GESTOR",               "required": False, "type": "text"},
            {"key": "diretor",                "label": "DIRETOR",              "required": False, "type": "text"},
            {"key": "supervisor",             "label": "SUPERVISOR",           "required": False, "type": "text"},
            {"key": "coordenador",            "label": "COORDENADOR",          "required": False, "type": "text"},
            {"key": "tp_produto",             "label": "TP PRODUTO",           "required": False, "type": "text"},
            {"key": "planta",                 "label": "PLANTA",               "required": False, "type": "text"},
            {"key": "marca",                  "label": "MARCA",                "required": False, "type": "text"},
            {"key": "familiaproduto",         "label": "FAMILIAPRODUTO",       "required": False, "type": "text"},
            {"key": "familiaprodutodetalhe",  "label": "FAMILIAPRODUTODETALHE","required": False, "type": "text"},
            {"key": "categoria",              "label": "CATEGORIA",            "required": False, "type": "text"},
            {"key": "bpc_category",           "label": "BPC CATEGORY",         "required": False, "type": "text"},
            {"key": "linha",                  "label": "LINHA",                "required": False, "type": "text"},
            {"key": "channel",                "label": "CHANNEL",              "required": False, "type": "text"},
            {"key": "descricao",              "label": "DESCRICAO",            "required": False, "type": "text"},
            {"key": "item",                   "label": "ITEM",                 "required": False, "type": "number"},
            {"key": "receita_liq",            "label": "RECEITA LIQ",          "required": False, "type": "number"},
            {"key": "ingrediente",            "label": "INGREDIENTE",          "required": False, "type": "number"},
            {"key": "embalagem",              "label": "EMBALAGEM",            "required": False, "type": "number"},
            {"key": "mod",                    "label": "MOD",                  "required": False, "type": "number"},
            {"key": "variacao_de_preco",      "label": "VARIACAO DE PRECO",    "required": False, "type": "number"},
        ]
    }
}

# ── Coluna Excel formatada (25 colunas oficiais) ──────────────────────────────
VCM_EXCEL_COLUMNS = [
    {"idx": 1,  "header": "ANO",                   "key": "ano",                   "align": "center", "width": 8.0,  "fmt": "General"},
    {"idx": 2,  "header": "MES",                   "key": "mes",                   "align": "center", "width": 12.0, "fmt": "General"},
    {"idx": 3,  "header": "CENARIO",               "key": "cenario",               "align": "center", "width": 8.0,  "fmt": "General"},
    {"idx": 4,  "header": "NOME CLIENTE",          "key": "nome_cliente",          "align": "left",   "width": 22.0, "fmt": "General"},
    {"idx": 5,  "header": "ID CLIENTE",            "key": "id_cliente",            "align": "center", "width": 10.0, "fmt": "General"},
    {"idx": 6,  "header": "GESTOR",                "key": "gestor",                "align": "left",   "width": 18.0, "fmt": "General"},
    {"idx": 7,  "header": "DIRETOR",               "key": "diretor",               "align": "left",   "width": 18.0, "fmt": "General"},
    {"idx": 8,  "header": "SUPERVISOR",            "key": "supervisor",            "align": "left",   "width": 18.0, "fmt": "General"},
    {"idx": 9,  "header": "COORDENADOR",           "key": "coordenador",           "align": "left",   "width": 16.0, "fmt": "General"},
    {"idx": 10, "header": "TP PRODUTO",            "key": "tp_produto",            "align": "center", "width": 12.0, "fmt": "General"},
    {"idx": 11, "header": "PLANTA",                "key": "planta",                "align": "center", "width": 8.0,  "fmt": "General"},
    {"idx": 12, "header": "MARCA",                 "key": "marca",                 "align": "center", "width": 12.0, "fmt": "General"},
    {"idx": 13, "header": "FAMILIAPRODUTO",        "key": "familiaproduto",        "align": "center", "width": 16.0, "fmt": "General"},
    {"idx": 14, "header": "FAMILIAPRODUTODETALHE", "key": "familiaprodutodetalhe", "align": "center", "width": 22.0, "fmt": "General"},
    {"idx": 15, "header": "CATEGORIA",             "key": "categoria",             "align": "center", "width": 12.0, "fmt": "General"},
    {"idx": 16, "header": "BPC CATEGORY",          "key": "bpc_category",          "align": "center", "width": 14.0, "fmt": "General"},
    {"idx": 17, "header": "LINHA",                 "key": "linha",                 "align": "center", "width": 12.0, "fmt": "General"},
    {"idx": 18, "header": "CHANNEL",               "key": "channel",               "align": "center", "width": 16.0, "fmt": "General"},
    {"idx": 19, "header": "DESCRICAO",             "key": "descricao",             "align": "left",   "width": 40.0, "fmt": "General"},
    {"idx": 20, "header": "ITEM",                  "key": "item",                  "align": "center", "width": 10.0, "fmt": "General"},
    {"idx": 21, "header": "RECEITA LIQ",           "key": "receita_liq",           "align": "right",  "width": 16.0, "fmt": "#,##0.00"},
    {"idx": 22, "header": "INGREDIENTE",           "key": "ingrediente",           "align": "right",  "width": 16.0, "fmt": "#,##0.00"},
    {"idx": 23, "header": "EMBALAGEM",             "key": "embalagem",             "align": "right",  "width": 14.0, "fmt": "#,##0.00"},
    {"idx": 24, "header": "MOD",                   "key": "mod",                   "align": "right",  "width": 14.0, "fmt": "#,##0.00"},
    {"idx": 25, "header": "VARIACAO DE PRECO",     "key": "variacao_de_preco",     "align": "right",  "width": 18.0, "fmt": "#,##0.00"},
]

_VCM_FONT_HEADER = Font(name="Aptos Narrow", size=9, bold=True, color="FFFFFF")
_VCM_FONT_CELL   = Font(name="Aptos Narrow", size=9)
_VCM_FILL_HEADER = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
_VCM_ALIGN_CTR   = Alignment(horizontal="center", vertical="center")
_VCM_ALIGN_LEFT  = Alignment(horizontal="left",   vertical="center")
_VCM_ALIGN_RIGHT = Alignment(horizontal="right",  vertical="center")


# ── Funções utilitárias (Motor Upsert & Normalização) ─────────────────────────

def _vcm_clean_key(k):
    """Normaliza nome de coluna/chave removendo acentos, pontuação, espaços e case."""
    if k is None:
        return ""
    nfd = unicodedata.normalize('NFD', str(k))
    no_accents = ''.join(ch for ch in nfd if unicodedata.category(ch) != 'Mn')
    return re.sub(r'[^A-Z0-9]+', '', no_accents.strip().upper())


def _vcm_get_field(row, key, label=None):
    """Obtém valor de um campo do row dict com tolerância total a espaços extras, acentos e case."""
    if not isinstance(row, dict):
        return ""
    if key in row and row[key] is not None and str(row[key]).strip() != "":
        return row[key]
    if label and label in row and row[label] is not None and str(row[label]).strip() != "":
        return row[label]

    clean_k = _vcm_clean_key(key)
    clean_lbl = _vcm_clean_key(label) if label else ""

    for k, v in row.items():
        ck = _vcm_clean_key(k)
        if ck == clean_k or (clean_lbl and ck == clean_lbl):
            if v is not None:
                return v
    return ""


def _vcm_norm_str_key(val, is_numeric=False):
    """Normaliza um valor para uso como componente de chave composta."""
    if val is None or (isinstance(val, float) and (val != val)):
        return ""
    s = str(val).strip()
    # Se for string de data ISO ou Timestamp com horas (ex: '2024-01-01 00:00:00' -> '2024-01-01')
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        s = s[:10]
    if s.endswith(".0"):
        s = s[:-2]
    if is_numeric:
        try:
            return str(int(float(s)))
        except Exception:
            pass
    return " ".join(s.split()).upper()


def _vcm_build_composite_key(row, composite_keys, columns_cfg=None):
    """Gera a chave composta normalizada que identifica unicamente uma linha VCM."""
    numeric_keys = {"ano", "id_cliente", "item"}
    parts = []
    for k in composite_keys:
        label = None
        if columns_cfg:
            col_def = next((c for c in columns_cfg if c["key"] == k), None)
            if col_def:
                label = col_def.get("label")
        val = _vcm_get_field(row, k, label)
        parts.append(_vcm_norm_str_key(val, is_numeric=(k in numeric_keys)))
    return tuple(parts)


def _vcm_norm_value(val, col_type):
    """Normaliza valor de campo para comparação de igualdade."""
    if val is None or (isinstance(val, float) and (val != val)):
        return ""
    if col_type == "number":
        s = str(val).strip()
        if not s or s in ("-", "None", "nan", "NaN"):
            return 0.0
        try:
            clean = s.replace(".", "").replace(",", ".") if "," in s else s
            return round(float(clean), 4)
        except Exception:
            return 0.0
    s = str(val).strip()
    if s.endswith(".0"):
        try:
            return str(int(float(s)))
        except Exception:
            pass
    return s


def _vcm_rows_identical(row_a, row_b, columns_cfg):
    """Retorna True somente se todos os campos forem idênticos."""
    for col in columns_cfg:
        k = col["key"]
        t = col.get("type", "text")
        va = _vcm_norm_value(_vcm_get_field(row_a, k, col.get("label")), t)
        vb = _vcm_norm_value(_vcm_get_field(row_b, k, col.get("label")), t)
        if va != vb:
            return False
    return True


def _vcm_smart_merge(current_rows, imported_rows, composite_keys, columns_cfg):
    """
    Mesclar Inteligente (Upsert) para a Base VCM:
    - Chave composta dimensional completa (incluindo PLANTA, FAMÍLIA DETALHE, BPC CATEGORY e DESCRIÇÃO).
    - Suporta múltiplas ocorrências/lançamentos transacionais por chave dimensional (sem perda de linhas legítimas).
    - Linha idêntica → inalterada
    - Mesma chave e ocorrência, valores financeiros alterados → atualiza
    - Chave/ocorrência nova → insere
    - Linhas da base que não vieram no arquivo → preservadas
    """
    stats = {
        "total_importado": len(imported_rows),
        "total_existente": len(current_rows),
        "inalterados": 0,
        "atualizados": 0,
        "novos": 0,
        "preservados": 0,
        "total_final": 0,
        "duplicatas_removidas_base": 0
    }

    key_counts = {}
    existing_map = {}
    existing_order = []

    for r in current_rows:
        base_key = _vcm_build_composite_key(r, composite_keys, columns_cfg)
        occ = key_counts.get(base_key, 0)
        key_counts[base_key] = occ + 1
        key = (base_key, occ)
        existing_map[key] = dict(r)
        existing_order.append(key)

    imp_key_counts = {}
    matched = set()
    new_rows = []

    for imp_r in imported_rows:
        base_key = _vcm_build_composite_key(imp_r, composite_keys, columns_cfg)
        occ = imp_key_counts.get(base_key, 0)
        imp_key_counts[base_key] = occ + 1
        key = (base_key, occ)

        if key in existing_map:
            matched.add(key)
            curr_r = existing_map[key]
            if _vcm_rows_identical(curr_r, imp_r, columns_cfg):
                stats["inalterados"] += 1
            else:
                stats["atualizados"] += 1
                updated = dict(curr_r)
                for col in columns_cfg:
                    k = col["key"]
                    v = _vcm_get_field(imp_r, k, col.get("label"))
                    if v != "":
                        updated[k] = v
                existing_map[key] = updated
        else:
            stats["novos"] += 1
            new_rows.append((key, dict(imp_r)))

    for k in existing_order:
        if k not in matched:
            stats["preservados"] += 1

    final_rows = [existing_map[k] for k in existing_order]
    for _, nr in new_rows:
        final_rows.append(nr)

    stats["total_final"] = len(final_rows)
    return final_rows, stats


def _read_vcm_rows():
    """Lê as linhas da Base VCM do Volume ou do fallback local, normalizando para o esquema."""
    cfg = LOOKUP_CONFIG_VCM["base_vcm"]
    col_defs = cfg["columns"]

    raw_df = None
    vol_path = get_volume_path()
    if vol_path:
        try:
            from databricks.sdk import WorkspaceClient
            w = WorkspaceClient()
            resp = w.files.download(vol_path)
            raw_df = _read_excel_safe(io.BytesIO(resp.contents.read()))
        except Exception as e:
            logger.warning(f"Não foi possível ler do Volume para upsert ({e}). Tentando fallback...")

    if raw_df is None or raw_df.empty:
        for c in [
            os.path.join(APP_DIR, "base_vcm.xlsx"),
            os.path.join(APP_DIR, "..", "..", "fixtures", "base_vcm.xlsx"),
            "base_vcm.xlsx"
        ]:
            if c and os.path.exists(c):
                try:
                    raw_df = _read_excel_safe(c)
                    if not raw_df.empty:
                        break
                except Exception as e:
                    logger.warning(f"Falha ao ler {c}: {e}")

    if raw_df is None or raw_df.empty:
        return [], None

    # Mapeia colunas do Excel para as keys do config
    col_mapping = {}
    for col in raw_df.columns:
        norm = _vcm_clean_key(col)
        for c_def in col_defs:
            if norm in (_vcm_clean_key(c_def["key"]), _vcm_clean_key(c_def["label"])):
                col_mapping[col] = c_def["key"]
                break

    rows = []
    for _, r in raw_df.iterrows():
        row_dict = {}
        for orig_col, target_key in col_mapping.items():
            val = r.get(orig_col)
            if isinstance(val, float) and (val != val):
                row_dict[target_key] = ""
            elif isinstance(val, (datetime, pd.Timestamp)):
                row_dict[target_key] = val.strftime("%Y-%m-%d")
            else:
                s_val = str(val).strip() if val is not None else ""
                if target_key == "mes" and len(s_val) >= 10 and s_val[4] == '-' and s_val[7] == '-':
                    s_val = s_val[:10]
                row_dict[target_key] = s_val

        # Normaliza inteiros
        for k in ("ano", "id_cliente", "item"):
            if k in row_dict and row_dict[k]:
                row_dict[k] = row_dict[k].split(".")[0].strip()

        for c_def in col_defs:
            if c_def["key"] not in row_dict:
                row_dict[c_def["key"]] = ""

        # Descarta linhas completamente vazias
        if any(v for k, v in row_dict.items() if k not in ("id_cliente", "item")):
            rows.append(row_dict)

    return rows, None


def _save_vcm_to_volume(excel_bytes, filename, is_backup=False):
    """Grava o Excel no Volume do Databricks Unity Catalog (Databricks Files SDK)."""
    vol_path = get_volume_path()
    if not vol_path:
        return False, "VOLUME_PATH não configurado."
    vol_dir = os.path.dirname(vol_path).replace("\\\\", "/")
    rel_path = f"backups/{filename}" if is_backup else filename
    full_vol_path = f"{vol_dir}/{rel_path}"

    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        w.files.upload(full_vol_path, io.BytesIO(excel_bytes), overwrite=True)
        logger.info(f"VCM Excel gravado no Volume: {full_vol_path} ({len(excel_bytes)} bytes)")
        return True, None
    except Exception as e:
        logger.error(f"Erro ao gravar VCM no Volume ({full_vol_path}): {e}")

    if os.name != "nt" and os.path.ismount("/Volumes"):
        try:
            os.makedirs(os.path.dirname(full_vol_path), exist_ok=True)
            with open(full_vol_path, "wb") as f:
                f.write(excel_bytes)
            return True, None
        except Exception as e:
            logger.warning(f"Fallback FUSE falhou: {e}")
            return False, str(e)

    return False, "Não foi possível gravar no Volume."


def _save_vcm_to_local(excel_bytes, filename, is_backup=False):
    """Grava cópia local no disco do Databricks App como contingência."""
    target_dir = os.path.join(APP_DIR, "backups") if is_backup else APP_DIR
    os.makedirs(target_dir, exist_ok=True)
    target_file = os.path.join(target_dir, filename)
    try:
        with open(target_file, "wb") as f:
            f.write(excel_bytes)
        logger.info(f"VCM Excel gravado localmente: {target_file}")
        return True
    except Exception as e:
        logger.warning(f"Falha ao salvar VCM local {target_file}: {e}")
        return False


def _gerar_workbook_vcm_bytes(rows_data):
    """
    Gera a planilha oficial Base de VCM com:
    - Aba 'Base de VCM' com 25 colunas oficiais
    - Tabela 'TabelaVCM' com estilo TableStyleLight2 + zebrado + autofiltro
    - Tipografia Aptos Narrow tamanho 9, cabeçalho azul #1F4E79
    - Larguras de coluna calibradas conforme modelo oficial
    """
    cfg = LOOKUP_CONFIG_VCM["base_vcm"]
    col_defs = cfg["columns"]
    total_rows = len(rows_data)

    # Tenta carregar template oficial
    template_candidates = [
        os.path.join(APP_DIR, "modelo_vcm.xlsx"),
        os.path.join(APP_DIR, "base_vcm.xlsx"),
        os.path.join(APP_DIR, "..", "..", "fixtures", "base_vcm.xlsx"),
    ]
    wb = None
    for tp in template_candidates:
        if tp and os.path.exists(tp):
            try:
                wb = openpyxl.load_workbook(tp)
                ws_name = "Base de VCM" if "Base de VCM" in wb.sheetnames else wb.sheetnames[0]
                ws = wb[ws_name]
                # Limpa dados antigos (mantém linha 1 = cabeçalho)
                if ws.max_row > 1:
                    ws.delete_rows(2, ws.max_row - 1)
                break
            except Exception as e:
                logger.warning(f"Erro ao carregar template VCM ({tp}): {e}")
                wb = None

    if wb is None:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Base de VCM"

    # Cabeçalhos
    for c_def in VCM_EXCEL_COLUMNS:
        cell = ws.cell(1, c_def["idx"], c_def["header"])
        cell.font = _VCM_FONT_HEADER
        cell.fill = _VCM_FILL_HEADER
        cell.alignment = _VCM_ALIGN_CTR

    def _parse_num(v):
        if v is None:
            return None
        s = str(v).strip()
        if not s or s in ("-", "None", "nan", "NaN", ""):
            return None
        try:
            return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)
        except Exception:
            return None

    # Dados
    for r_idx, r in enumerate(rows_data, start=2):
        for c_def in VCM_EXCEL_COLUMNS:
            raw = _vcm_get_field(r, c_def["key"], c_def["header"])
            if c_def["fmt"] != "General" or c_def["key"] in ("ano", "id_cliente", "item"):
                num = _parse_num(raw)
                if num is not None:
                    val = int(num) if c_def["key"] in ("ano", "id_cliente", "item") else num
                else:
                    val = str(raw).strip() if raw else ""
            else:
                val = str(raw).strip() if raw else ""

            cell = ws.cell(r_idx, c_def["idx"], val)
            cell.font = _VCM_FONT_CELL
            if c_def["align"] == "left":
                cell.alignment = _VCM_ALIGN_LEFT
            elif c_def["align"] == "right":
                cell.alignment = _VCM_ALIGN_RIGHT
            else:
                cell.alignment = _VCM_ALIGN_CTR
            if c_def["fmt"] != "General":
                cell.number_format = c_def["fmt"]

    # Larguras de coluna
    for c_def in VCM_EXCEL_COLUMNS:
        ws.column_dimensions[get_column_letter(c_def["idx"])].width = c_def["width"]

    # Tabela oficial
    last_col_letter = get_column_letter(len(VCM_EXCEL_COLUMNS))
    table_ref = f"A1:{last_col_letter}{total_rows + 1}" if total_rows > 0 else f"A1:{last_col_letter}2"
    tab_name = "TabelaVCM"
    if tab_name in ws.tables:
        ws.tables[tab_name].ref = table_ref
    else:
        tab = Table(displayName=tab_name, ref=table_ref)
        tab.tableStyleInfo = TableStyleInfo(
            name="TableStyleLight2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False
        )
        ws.add_table(tab)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Rotas de Gestão da Base VCM (padrão bq_app_landing) ──────────────────────

@app.route("/api/lookups/base_vcm", methods=["GET"])
def vcm_lookups_get():
    """Retorna o esquema e todas as linhas da Base VCM."""
    cfg = LOOKUP_CONFIG_VCM["base_vcm"]
    rows, err = _read_vcm_rows()
    return jsonify({
        "success": True,
        "table_key": "base_vcm",
        "title": cfg["title"],
        "description": cfg["description"],
        "primary_key": cfg["primary_key"],
        "columns": cfg["columns"],
        "rows": rows,
        "total": len(rows),
        "error": err
    })


@app.route("/api/lookups/base_vcm/preview_merge", methods=["POST"])
def vcm_preview_merge():
    """
    Simula o salvamento e retorna estatísticas de auditoria
    (inalterados, atualizados, novos, total_final) sem gravar nada.
    Suporta mode: 'replace' ou 'merge'.
    """
    cfg = LOOKUP_CONFIG_VCM["base_vcm"]
    data = request.get_json() or {}
    raw_rows = data.get("rows", [])
    mode = data.get("mode", "replace")
    if not isinstance(raw_rows, list):
        return jsonify({"success": False, "error": "Formato inválido: 'rows' deve ser lista."}), 400

    current_rows, _ = _read_vcm_rows()
    if mode == "replace":
        stats = {
            "total_importado": len(raw_rows),
            "total_existente": len(current_rows),
            "inalterados": 0,
            "atualizados": 0,
            "novos": len(raw_rows),
            "preservados": 0,
            "total_final": len(raw_rows),
            "duplicatas_removidas_base": 0,
            "modo": "substituicao_completa"
        }
    else:
        _, stats = _vcm_smart_merge(
            current_rows, raw_rows,
            cfg["composite_keys"],
            cfg["columns"]
        )
        stats["modo"] = "mesclar_inteligente"
    return jsonify({"success": True, "stats": stats})


def _async_execute_vcm_save(task_id, raw_rows, mode, user_email):
    """Executa a gravação da Base VCM em segundo plano, atualizando percentual de progresso."""
    try:
        cfg = LOOKUP_CONFIG_VCM["base_vcm"]
        col_defs = cfg["columns"]
        composite_keys = cfg["composite_keys"]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        with _VCM_TASKS_LOCK:
            _VCM_ASYNC_TASKS[task_id]["percent"] = 15
            _VCM_ASYNC_TASKS[task_id]["step"] = "Lendo base existente para validação..."

        current_rows, _ = _read_vcm_rows()

        with _VCM_TASKS_LOCK:
            _VCM_ASYNC_TASKS[task_id]["percent"] = 35
            _VCM_ASYNC_TASKS[task_id]["step"] = "Estruturando e normalizando colunas..."

        if mode == "replace":
            merged_rows = raw_rows
            stats = {
                "total_importado": len(raw_rows),
                "total_existente": len(current_rows),
                "inalterados": 0,
                "atualizados": 0,
                "novos": len(raw_rows),
                "preservados": 0,
                "total_final": len(raw_rows),
                "duplicatas_removidas_base": 0,
                "modo": "substituicao_completa"
            }
        else:
            merged_rows, stats = _vcm_smart_merge(current_rows, raw_rows, composite_keys, col_defs)
            stats["modo"] = "mesclar_inteligente"

        data_for_df = []
        for r in merged_rows:
            if not isinstance(r, dict):
                continue
            item = {}
            for c in col_defs:
                val = _vcm_get_field(r, c["key"], c.get("label"))
                if val is None or str(val) in ("None", "nan", "NaN"):
                    val = ""
                if c["key"] == "mes" and str(val).strip():
                    s_val = str(val).strip()
                    if len(s_val) >= 10 and s_val[4] == '-' and s_val[7] == '-':
                        val = s_val[:10]
                if c["type"] == "number" and str(val).strip():
                    try:
                        num_s = str(val).replace(".", "").replace(",", ".") if "," in str(val) else str(val)
                        item[c["label"]] = float(num_s)
                    except Exception:
                        item[c["label"]] = str(val).strip()
                else:
                    item[c["label"]] = str(val).strip()
            if any(v for k, v in item.items() if k not in ("ID CLIENTE", "ITEM")):
                data_for_df.append(item)

        if not data_for_df and raw_rows:
            raise ValueError("Nenhum registro válido identificado para gravação.")

        with _VCM_TASKS_LOCK:
            _VCM_ASYNC_TASKS[task_id]["percent"] = 55
            _VCM_ASYNC_TASKS[task_id]["step"] = f"Formatando planilha oficial ({len(data_for_df):,} registros)..."

        excel_bytes = _gerar_workbook_vcm_bytes(data_for_df)
        backup_fn = f"base_vcm_backup_{ts}.xlsx"

        with _VCM_TASKS_LOCK:
            _VCM_ASYNC_TASKS[task_id]["percent"] = 75
            _VCM_ASYNC_TASKS[task_id]["step"] = "Gravando backup e transmitindo ao Volume Databricks..."

        _save_vcm_to_volume(excel_bytes, backup_fn, is_backup=True)
        _save_vcm_to_local(excel_bytes, backup_fn, is_backup=True)

        vol_ok, vol_err = _save_vcm_to_volume(excel_bytes, cfg["excel_filename"], is_backup=False)
        loc_ok = _save_vcm_to_local(excel_bytes, cfg["excel_filename"], is_backup=False)

        if not vol_ok:
            raise RuntimeError(f"Falha ao gravar no Volume Databricks: {vol_err or 'Verifique permissões.'}")

        with _VCM_TASKS_LOCK:
            _VCM_ASYNC_TASKS[task_id]["percent"] = 92
            _VCM_ASYNC_TASKS[task_id]["step"] = "Renovando cache analítico da aplicação..."

        global _cached_df, _cached_mtime, _cached_path, _cached_updated_at
        _cached_df = None
        _cached_mtime = 0
        _cached_path = None
        try:
            obter_dados_base()
        except Exception as e:
            logger.warning(f"Aviso ao recarregar cache após save assíncrono: {e}")

        logger.info(
            f"[VCM ASYNC SAVE DONE] task={task_id} | user={user_email} | final={len(data_for_df)}"
        )

        with _VCM_TASKS_LOCK:
            _VCM_ASYNC_TASKS[task_id].update({
                "status": "completed",
                "percent": 100,
                "step": "Concluído com sucesso!",
                "count": len(data_for_df),
                "stats": stats,
                "backup": backup_fn,
                "timestamp": ts,
                "finished_at": time.time(),
                "message": (
                    f"Base oficial substituída com sucesso! Total: {len(data_for_df):,} registros."
                    if mode == "replace"
                    else f"Base mesclada com sucesso! Total: {len(data_for_df):,} registros."
                )
            })

    except Exception as err:
        logger.error(f"[VCM ASYNC SAVE FAILED] task={task_id}: {err}", exc_info=True)
        with _VCM_TASKS_LOCK:
            _VCM_ASYNC_TASKS[task_id].update({
                "status": "failed",
                "percent": 100,
                "step": f"Falha na gravação: {str(err)}",
                "error": str(err),
                "finished_at": time.time()
            })


@app.route("/api/lookups/base_vcm", methods=["POST"])
def vcm_lookups_save():
    """
    Inicia a gravação da Base VCM em segundo plano (Assíncrono) ou síncrono:
    - mode == 'replace': substitui todas as linhas pela nova planilha oficial (com backup automático)
    - mode == 'merge': atualiza alteradas, insere novas, ignora idênticas, preserva as que não vieram.
    """
    user_email = _get_current_user_email()
    if not _is_user_authorized_for_cadastros(user_email):
        return jsonify({
            "success": False,
            "error": f"Acesso negado: o usuário '{user_email}' não possui permissão."
        }), 403

    data = request.get_json() or {}
    raw_rows = data.get("rows", [])
    mode = data.get("mode", "replace")
    run_sync = data.get("sync", False)

    if not isinstance(raw_rows, list):
        return jsonify({"success": False, "error": "Formato inválido: 'rows' deve ser lista."}), 400

    if not raw_rows:
        return jsonify({"success": False, "error": "Nenhum registro para salvar."}), 400

    task_id = f"vcm_{uuid.uuid4().hex[:10]}"
    with _VCM_TASKS_LOCK:
        _VCM_ASYNC_TASKS[task_id] = {
            "task_id": task_id,
            "status": "running",
            "percent": 5,
            "step": "Iniciando processo em segundo plano...",
            "user": user_email,
            "mode": mode,
            "total_submitted": len(raw_rows),
            "created_at": time.time()
        }

    if run_sync:
        _async_execute_vcm_save(task_id, raw_rows, mode, user_email)
        with _VCM_TASKS_LOCK:
            t = _VCM_ASYNC_TASKS[task_id]
        if t["status"] == "completed":
            return jsonify({"success": True, "count": t["count"], "stats": t["stats"], "message": t["message"]})
        return jsonify({"success": False, "error": t.get("error", "Erro desconhecido")}), 500

    # Dispara thread em background e retorna 202 imediatamente
    threading.Thread(
        target=_async_execute_vcm_save,
        args=(task_id, raw_rows, mode, user_email),
        daemon=True
    ).start()

    logger.info(f"[VCM ASYNC DISPATCH] task={task_id} | user={user_email} | rows={len(raw_rows)} | mode={mode}")

    return jsonify({
        "success": True,
        "async": True,
        "task_id": task_id,
        "mode": mode,
        "total_submitted": len(raw_rows),
        "message": "Gravação iniciada em segundo plano! Você pode continuar usando a aplicação normalmente."
    }), 202


@app.route("/api/lookups/base_vcm/task/<task_id>", methods=["GET"])
def vcm_task_status(task_id):
    """Consulta o status de uma gravação em segundo plano."""
    with _VCM_TASKS_LOCK:
        task = _VCM_ASYNC_TASKS.get(task_id)
        if not task:
            return jsonify({"success": False, "error": "Tarefa não encontrada."}), 404
        return jsonify({"success": True, "task": task})


@app.route("/api/lookups/base_vcm/active_task", methods=["GET"])
def vcm_active_task():
    """Retorna a tarefa ativa ou recém-concluída mais recente."""
    now = time.time()
    with _VCM_TASKS_LOCK:
        latest = None
        for t in sorted(_VCM_ASYNC_TASKS.values(), key=lambda x: x.get("created_at", 0), reverse=True):
            if t.get("status") == "running" or (now - t.get("finished_at", 0) < 60):
                latest = t
                break
        if latest:
            return jsonify({"success": True, "has_active": True, "task": latest})
        return jsonify({"success": True, "has_active": False, "task": None})


@app.route("/api/lookups/base_vcm/export_excel", methods=["GET"])
def vcm_export_excel():
    """Exporta a planilha oficial formatada Base de VCM com TableStyleLight2."""
    rows, _ = _read_vcm_rows()
    excel_bytes = _gerar_workbook_vcm_bytes(rows)
    filename = f"Base_VCM_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return Response(
        excel_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )




@app.route("/api/upload", methods=["POST"])
def upload_base():
    """
    Upload de arquivo Excel com validação e Mesclar Inteligente (Upsert):
    - Atualiza linhas alteradas, insere novas, ignora idênticas, preserva as que não vieram.
    Padrão idêntico ao bq_app_landing.
    """
    email = _get_current_user_email()
    if not _is_user_authorized_for_cadastros(email):
        return jsonify({"sucesso": False, "erro": f"Usuário '{email}' não autorizado."}), 403

    if "file" not in request.files:
        return jsonify({"sucesso": False, "erro": "Nenhum arquivo enviado."}), 400

    file = request.files["file"]
    if not file.filename.endswith((".xlsx", ".xls", ".xlsb", ".csv")):
        return jsonify({"sucesso": False, "erro": "Formato inválido. Use .xlsx, .xls ou .csv."}), 400

    try:
        raw_bytes = file.read()
        if file.filename.endswith(".xlsx") and raw_bytes.startswith(b"\xD0\xCF\x11\xE0"):
            return jsonify({
                "sucesso": False,
                "erro": "Arquivo protegido por criptografia corporativa do Microsoft 365 (Selo 'Interno' ou 'Confidencial'). Para importar no portal, altere o selo para 'Público' no Excel ou salve a planilha como 'CSV UTF-8'."
            }), 400

        df_upload = _read_excel_safe(io.BytesIO(raw_bytes))
        if df_upload.empty:
            return jsonify({"sucesso": False, "erro": "Arquivo vazio ou sem linhas válidas."}), 400

        cfg = LOOKUP_CONFIG_VCM["base_vcm"]
        col_defs = cfg["columns"]
        composite_keys = cfg["composite_keys"]

        # Converte DataFrame para lista de row dicts com keys normalizadas
        col_mapping = {}
        for col in df_upload.columns:
            norm = _vcm_clean_key(col)
            for c_def in col_defs:
                if norm in (_vcm_clean_key(c_def["key"]), _vcm_clean_key(c_def["label"])):
                    col_mapping[col] = c_def["key"]
                    break

        imported_rows = []
        for _, row in df_upload.iterrows():
            r = {}
            for orig_col, target_key in col_mapping.items():
                val = row.get(orig_col)
                if isinstance(val, float) and (val != val):
                    r[target_key] = ""
                elif isinstance(val, (datetime, pd.Timestamp)):
                    r[target_key] = val.strftime("%Y-%m-%d")
                else:
                    s_val = str(val).strip() if val is not None else ""
                    if target_key == "mes" and len(s_val) >= 10 and s_val[4] == '-' and s_val[7] == '-':
                        s_val = s_val[:10]
                    r[target_key] = s_val
            for c_def in col_defs:
                if c_def["key"] not in r:
                    r[c_def["key"]] = ""
            # Normaliza inteiros
            for k in ("ano", "id_cliente", "item"):
                if k in r and r[k]:
                    r[k] = r[k].split(".")[0].strip()
            if any(v for k, v in r.items() if k not in ("id_cliente", "item")):
                imported_rows.append(r)

        if not imported_rows:
            return jsonify({"sucesso": False, "erro": "Nenhum registro válido encontrado no arquivo."}), 400

        mode = request.form.get("mode", "replace") # 'replace' ou 'merge'
        current_rows, _ = _read_vcm_rows()
        if mode == "replace":
            merged_rows = imported_rows
            stats = {
                "total_importado": len(imported_rows),
                "total_existente": len(current_rows),
                "inalterados": 0,
                "atualizados": 0,
                "novos": len(imported_rows),
                "preservados": 0,
                "total_final": len(imported_rows),
                "duplicatas_removidas_base": 0,
                "modo": "substituicao_completa"
            }
        else:
            merged_rows, stats = _vcm_smart_merge(current_rows, imported_rows, composite_keys, col_defs)
            stats["modo"] = "mesclar_inteligente"

        # Serializa para o esquema oficial
        data_for_df = []
        for r in merged_rows:
            if not isinstance(r, dict):
                continue
            item = {}
            for c in col_defs:
                val = _vcm_get_field(r, c["key"], c.get("label"))
                if val is None or str(val) in ("None", "nan", "NaN"):
                    val = ""
                if c["key"] == "mes" and str(val).strip():
                    s_val = str(val).strip()
                    if len(s_val) >= 10 and s_val[4] == '-' and s_val[7] == '-':
                        val = s_val[:10]
                if c["type"] == "number" and str(val).strip():
                    try:
                        num_s = str(val).replace(".", "").replace(",", ".") if "," in str(val) else str(val)
                        item[c["label"]] = float(num_s)
                    except Exception:
                        item[c["label"]] = str(val).strip()
                else:
                    item[c["label"]] = str(val).strip()
            if any(v for k, v in item.items() if k not in ("ID CLIENTE", "ITEM")):
                data_for_df.append(item)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_bytes = _gerar_workbook_vcm_bytes(data_for_df)

        # Backup + gravação principal
        _save_vcm_to_volume(excel_bytes, f"base_vcm_backup_{ts}.xlsx", is_backup=True)
        _save_vcm_to_local(excel_bytes, f"base_vcm_backup_{ts}.xlsx", is_backup=True)

        vol_ok, vol_err = _save_vcm_to_volume(excel_bytes, cfg["excel_filename"], is_backup=False)
        loc_ok = _save_vcm_to_local(excel_bytes, cfg["excel_filename"], is_backup=False)

        global _cached_df, _cached_mtime, _cached_path, _cached_updated_at
        _cached_df = None
        _cached_mtime = 0
        _cached_path = None

        msg = (
            f"Base oficial substituída com sucesso! Total: {len(data_for_df):,} registros."
            if mode == "replace"
            else f"Base atualizada com Mesclar Inteligente! Total: {len(data_for_df):,} registros ({stats['novos']} novos, {stats['atualizados']} atualizados, {stats['inalterados']} inalterados)."
        )

        return jsonify({
            "sucesso": True,
            "registros": len(data_for_df),
            "gravado_volume": vol_ok,
            "stats": stats,
            "mode": mode,
            "mensagem": msg
        })
    except Exception as err:
        logger.error(f"Erro no upload VCM: {err}")
        return jsonify({"sucesso": False, "erro": f"Falha ao processar arquivo: {str(err)}"}), 500



if __name__ == "__main__":
    from waitress import serve
    logger.info(f"🚀 Iniciando servidor BQ VCM na porta {PORT}...")
    serve(app, host="0.0.0.0", port=PORT)

