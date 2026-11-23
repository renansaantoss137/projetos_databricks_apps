# -*- coding: utf-8 -*-
"""
Backend Python Flask para Databricks Apps (Portal de Distribuidores Bimbo QSR)
Alinhado ao Guia de Boas Práticas Databricks Apps (Bruno Fellipe)
Correção P1 (Admin por Coluna Explícita), P2 (Padronização LPAD 14), P3 (Valor/Volume) e P4 (Meta sem Fanout FULL OUTER JOIN)
"""

import os
import json
import re
import gzip
import calendar
import html as html_lib
import secrets
import time
import uuid
import traceback
import threading
from datetime import date, datetime, timezone, timedelta
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_from_directory, send_file, session, redirect, Response, g, has_request_context
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState
from forecast_engine import build_forecast_payload
from executivo_ai import build_executivo_brief

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# static_folder=None: nada é servido automaticamente. Só as rotas explícitas abaixo
# (evita expor app.py, app.yaml, sql/, config/ etc. pela URL).
app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get('APP_SESSION_SECRET') or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('DATABRICKS_APP_PORT') is not None,
)

CATALOG  = os.environ.get('DATABRICKS_CATALOG', 'cat_dnabb_dv')
SCHEMA   = os.environ.get('DATABRICKS_SCHEMA', 'opebrapodis_sz')
WAREHOUSE_ID = os.environ.get('SQL_WAREHOUSE_ID') or os.environ.get('MY_DATABRICKS_PATH', '').split('/')[-1] or 'f4a2e26b8410f1e3'

JOB_ID = os.environ.get('DATABRICKS_JOB_ID', '570453512159476')

# Modo somente leitura desativado por padrão (permite alterações de governança de acesso).
# Para ativar modo estrito somente-leitura, definir V2_READ_ONLY=1.
READ_ONLY = os.environ.get('V2_READ_ONLY', '0') == '1'
_WRITE_SQL_RE = re.compile(r'^\s*(INSERT|UPDATE|MERGE|DELETE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE)\b', re.I)

# Cache em memória simples com TTL + fallback stale-while-revalidate
_CACHE_STORAGE = {}

def get_from_cache(key, ttl_seconds=300):
    if key in _CACHE_STORAGE:
        val, timestamp = _CACHE_STORAGE[key]
        if time.time() - timestamp < ttl_seconds:
            return val
    return None

def get_stale_from_cache(key):
    if key in _CACHE_STORAGE:
        return _CACHE_STORAGE[key][0]
    return None

def set_in_cache(key, val):
    _CACHE_STORAGE[key] = (val, time.time())

# ─── Helper Execução SQL via Statement Execution API ───────────────────────────
_WORKSPACE_CLIENT = None

def get_workspace_client():
    global _WORKSPACE_CLIENT
    if _WORKSPACE_CLIENT is not None:
        return _WORKSPACE_CLIENT

    token = os.environ.get('MY_DATABRICKS_TOKEN') or os.environ.get('DATABRICKS_TOKEN')
    raw_host = os.environ.get('MY_DATABRICKS_HOST') or os.environ.get('DATABRICKS_HOST', 'adb-8674310331778219.19.azuredatabricks.net')
    host = f"https://{raw_host.replace('https://', '').replace('http://', '').strip('/')}"

    if token:
        client_id = os.environ.pop("DATABRICKS_CLIENT_ID", None)
        client_secret = os.environ.pop("DATABRICKS_CLIENT_SECRET", None)
        try:
            _WORKSPACE_CLIENT = WorkspaceClient(host=host, token=token)
        finally:
            if client_id: os.environ["DATABRICKS_CLIENT_ID"] = client_id
            if client_secret: os.environ["DATABRICKS_CLIENT_SECRET"] = client_secret
    else:
        _WORKSPACE_CLIENT = WorkspaceClient()

    return _WORKSPACE_CLIENT

def execute_sql(query, params=None, timeout=60):
    """Executa instrução SQL no Databricks SQL Warehouse com polling de StatementState otimizado.
    timeout: segundos máximos de espera total (warehouse frio pode levar minutos para subir)."""
    if READ_ONLY and _WRITE_SQL_RE.match(query or ''):
        raise PermissionError('V2 em modo somente leitura: escrita bloqueada')
    wh_id = WAREHOUSE_ID
    if wh_id == '8674310331778219' or not wh_id:
        wh_id = 'f4a2e26b8410f1e3'

    w = get_workspace_client()

    stmt_params = None
    if params:
        from databricks.sdk.service.sql import StatementParameterListItem
        stmt_params = [StatementParameterListItem(name=k, value=str(v)) for k, v in params.items()]

    t0 = time.perf_counter()
    timeout_start = time.time()
    response = w.statement_execution.execute_statement(
        statement=query,
        warehouse_id=wh_id,
        parameters=stmt_params,
        wait_timeout=f"{int(min(30, max(5, timeout)))}s"
    )

    statement_id = response.statement_id
    while response.status.state in (StatementState.PENDING, StatementState.RUNNING):
        if time.time() - timeout_start > timeout:
            raise TimeoutError("Tempo limite excedido aguardando o SQL Warehouse iniciar.")
        time.sleep(0.2)
        response = w.statement_execution.get_statement(statement_id)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    if has_request_context():
        try:
            if not hasattr(g, '_sql_timings'):
                g._sql_timings = []
            g._sql_timings.append(elapsed_ms)
        except Exception:
            pass

    if response.status.state != StatementState.SUCCEEDED:
        error_msg = response.status.error.message if response.status.error else str(response.status.state)
        raise Exception(f"Erro SQL: {error_msg}")

    cols = [col.name for col in response.manifest.schema.columns] if response.manifest and response.manifest.schema else []
    data = response.result.data_array if response.result and response.result.data_array else []

    rows = []
    for r in data:
        row_dict = {}
        for col_name, val in zip(cols, r):
            row_dict[col_name] = val
        rows.append(row_dict)

    return rows


def order_nf_col_available():
    """True quando tbl_factdy_order já tem VL_FATURADO_LIQUIDO_NF (valor real da nota, igual ao Power BI).
    Rechecado a cada 10 min, para o app passar a usar a coluna sozinho assim que o job a criar."""
    cached = get_from_cache('order_nf_col', ttl_seconds=600)
    if cached is not None:
        return cached
    try:
        execute_sql(f"SELECT VL_FATURADO_LIQUIDO_NF FROM {CATALOG}.{SCHEMA}.tbl_factdy_order LIMIT 0")
        ok = True
    except Exception:
        ok = False
    set_in_cache('order_nf_col', ok)
    return ok

_LAST_JOB_LOCK = threading.Lock()

def _fetch_last_job_execution_sync(cache_key):
    from datetime import date, datetime, timezone, timedelta

    # 1. Tenta obter o commit mais recente das tabelas fato Delta no SQL Warehouse
    try:
        rows = execute_sql(f"DESCRIBE HISTORY {CATALOG}.{SCHEMA}.tbl_factdy_sellin LIMIT 1")
        if rows and rows[0].get('timestamp'):
            ts_str = str(rows[0]['timestamp'])
            dt_iso = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            dt_bsb = dt_iso.astimezone(timezone(timedelta(hours=-3)))
            formatted = dt_bsb.strftime('%d/%m/%Y às %H:%M')
            res = {'status': 'success', 'source': 'delta_history', 'last_updated': formatted, 'timestamp': ts_str, 'job_id': JOB_ID}
            set_in_cache(cache_key, res)
            return res
    except Exception as sql_err:
        app.logger.warning(f"[get_last_job_execution] DESCRIBE HISTORY falhou: {sql_err}")

    # 2. Tenta obter via Databricks Jobs API
    token = os.environ.get('MY_DATABRICKS_TOKEN') or os.environ.get('DATABRICKS_TOKEN')
    raw_host = os.environ.get('MY_DATABRICKS_HOST') or os.environ.get('DATABRICKS_HOST', 'adb-8674310331778219.19.azuredatabricks.net')
    host = f"https://{raw_host.replace('https://', '').replace('http://', '').strip('/')}"

    try:
        client = WorkspaceClient(host=host, token=token) if token else WorkspaceClient()
        runs = list(client.jobs.list_runs(job_id=int(JOB_ID), limit=3))
        for r in runs:
            if r.state and str(r.state.result_state) == 'RunResultState.SUCCESS' and r.end_time:
                dt_utc = datetime.fromtimestamp(r.end_time / 1000, tz=timezone.utc)
                dt_bsb = dt_utc.astimezone(timezone(timedelta(hours=-3)))
                formatted = dt_bsb.strftime('%d/%m/%Y às %H:%M')
                res = {'status': 'success', 'source': 'jobs_api', 'last_updated': formatted, 'timestamp': r.end_time, 'job_id': JOB_ID}
                set_in_cache(cache_key, res)
                return res
    except Exception as e:
        app.logger.warning(f"[get_last_job_execution] Erro ao buscar runs do Job {JOB_ID}: {e}")

    # Fallback seguro
    res = {'status': 'fallback', 'last_updated': '15/10/2026 às 16:10', 'timestamp': None, 'job_id': JOB_ID}
    return res

def get_last_job_execution():
    """
    Obtém data e hora de término da última carga/execução do Job em horário de Brasília (UTC-3).
    Estratégia 1 (100% Confiável): Consulta de commit mais recente das tabelas fato Delta via SQL Warehouse.
    Estratégia 2 (Secundária): Consulta da API de Jobs Databricks WorkspaceClient.
    Cache dinâmico de 900s com stale-while-revalidate em background para não bloquear /api/me.
    """
    cache_key = f"last_job_run_{CATALOG}_{SCHEMA}"
    cached = get_from_cache(cache_key, ttl_seconds=900)
    if cached:
        return cached

    stale = get_stale_from_cache(cache_key)
    if stale is not None:
        if _LAST_JOB_LOCK.acquire(blocking=False):
            def _bg():
                try:
                    _fetch_last_job_execution_sync(cache_key)
                finally:
                    _LAST_JOB_LOCK.release()
            threading.Thread(target=_bg, daemon=True).start()
        return stale

    with _LAST_JOB_LOCK:
        cached = get_from_cache(cache_key, ttl_seconds=900)
        if cached:
            return cached
        return _fetch_last_job_execution_sync(cache_key)

# ─── Helper de Autenticação Estrita SSO ─────────────────────────────────────────
def get_authenticated_user():
    email = request.headers.get('x-forwarded-email') or request.headers.get('X-Forwarded-Email')
    
    if not email and os.environ.get('DATABRICKS_APP_PORT') is None:
        email = 'renan.ferreira@grupobimbo.com' # Dev local

    if not email or '@' not in str(email):
        return None
    return str(email).lower().strip()

# ─── Papéis de Acesso (tbl_dim_app_admin) ──────────────────────────────────────
# MASTER: vê tudo + gerencia administradores | ADMIN: vê tudo (leitura na gestão)
# VISUALIZADOR: vê todos os distribuidores, sem acesso à governança (ADMIN_ROLES governam).
# Qualquer outro usuário: distribuidor, restrito ao(s) CNPJ(s) do mapeamento.
ADMIN_ROLES = ('MASTER', 'ADMIN')
ACCESS_ROLES = ADMIN_ROLES + ('VISUALIZADOR',)
ADMIN_EMAIL_DOMAIN = '@grupobimbo.com'
ADMIN_ROLE_TTL = 1800
_CNPJ_RE = re.compile(r'^\d{14}$')
_EMAIL_RE = re.compile(r'^[a-z0-9._%+\-]+@grupobimbo\.com$')

def normalize_cnpj(value):
    digits = re.sub(r'\D', '', str(value or ''))
    return digits.zfill(14) if digits else ''

def format_cnpj(cnpj):
    c = normalize_cnpj(cnpj)
    if len(c) != 14:
        return c
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"

def invalidate_admin_cache(keep_portal_rows=False):
    for k in list(_CACHE_STORAGE.keys()):
        if k == 'dist_groups_all_uc':
            continue
        if keep_portal_rows and k in ('portal_dists_rows', 'portal_dist_ids'):
            continue
        if k.startswith(('admin_role_', 'admin_roles_all', 'user_map_', 'kpi_', 'forecast_', 'filtros_', 'portal_dist_', 'portal_dists_', 'dist_groups', 'dist_catalog')):
            _CACHE_STORAGE.pop(k, None)

_PORTAL_DIST_TBL = f"{CATALOG}.{SCHEMA}.tbl_dim_distribuidor_portal"
_ACCESS_LOG_TBL = f"{CATALOG}.{SCHEMA}.tbl_log_app_access"
_ACCESS_DEDUP = {}

def invalidate_portal_dist_cache(keep_rows=False):
    invalidate_admin_cache(keep_portal_rows=keep_rows)

def get_portal_dists_rows():
    """Linhas de tbl_dim_distribuidor_portal em cache (15 min), atualizadas em memória a cada escrita."""
    cached = get_from_cache('portal_dists_rows', ttl_seconds=900)
    if cached is not None:
        return cached
    try:
        rows = execute_sql(f"""
            SELECT CAST(id_distribuidor AS STRING) AS id,
                   nome_referencia,
                   cnpj_referencia,
                   is_active,
                   notes,
                   created_by,
                   unix_millis(to_utc_timestamp(created_at, 'America/Sao_Paulo')) AS created_ms,
                   updated_by,
                   unix_millis(to_utc_timestamp(updated_at, 'America/Sao_Paulo')) AS updated_ms
            FROM {_PORTAL_DIST_TBL}
            WHERE id_distribuidor IS NOT NULL AND id_distribuidor > 0
        """)
        norm = []
        for r in rows:
            did = str(r.get('id') or '').strip()
            if not did.isdigit() or int(did) <= 0:
                continue
            norm.append({
                'id': str(int(did)),
                'nome_referencia': r.get('nome_referencia') or '',
                'cnpj_referencia': normalize_cnpj(r.get('cnpj_referencia')) or '',
                'is_active': str(r.get('is_active')).lower() == 'true',
                'notes': r.get('notes') or '',
                'created_by': r.get('created_by') or '',
                'created_ms': r.get('created_ms'),
                'updated_by': r.get('updated_by') or '',
                'updated_ms': r.get('updated_ms'),
            })
        set_in_cache('portal_dists_rows', norm)
        active_ids = sorted({x['id'] for x in norm if x['is_active']}, key=int)
        set_in_cache('portal_dist_ids', active_ids)
        return norm
    except Exception as e:
        app.logger.error(f"[get_portal_dists_rows] falha ao ler {_PORTAL_DIST_TBL}: {e}")
        stale = get_stale_from_cache('portal_dists_rows')
        return stale if stale is not None else []

def get_portal_dist_ids():
    """IDs de distribuidor ativos no portal (tbl_dim_distribuidor_portal). Cache 15 min."""
    cached = get_from_cache('portal_dist_ids', ttl_seconds=900)
    if cached is not None:
        return cached
    rows = get_portal_dists_rows()
    ids = sorted({r['id'] for r in rows if r.get('is_active') and str(r.get('id') or '').isdigit()}, key=int)
    set_in_cache('portal_dist_ids', ids)
    return ids

def log_app_access_async(email, role, perfil, pagina, dist_ids=None, sid=None):
    """Registra acesso em tbl_log_app_access em background (máx. 1 por usuário/página a cada 30 min)."""
    if READ_ONLY or not email:
        return
    is_cloud = os.environ.get('DATABRICKS_APP_PORT') is not None
    if not is_cloud and os.environ.get('LOG_ACCESS_LOCAL', '1') == '0':
        return
    clean_email = str(email).lower().strip()
    clean_page = str(pagina or 'dashboard').strip()[:80]
    now_ts = time.time()
    dedup_key = (clean_email, clean_page)
    last_ts = _ACCESS_DEDUP.get(dedup_key, 0)
    if now_ts - last_ts < 1800:
        return
    _ACCESS_DEDUP[dedup_key] = now_ts
    source = 'APP' if is_cloud else 'LOCAL'
    dist_str = ','.join(str(x) for x in (dist_ids or []) if x)[:500]
    session_id = str(sid or '')[:64]

    def _writer():
        try:
            execute_sql(f"""
                INSERT INTO {_ACCESS_LOG_TBL}
                (event_id, event_ts, event_date, user_email, role, perfil, pagina, dist_ids, session_id, source)
                SELECT :eid,
                       from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo'),
                       CAST(from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo') AS DATE),
                       :email, NULLIF(:role, ''), :perfil, :pagina, NULLIF(:dists, ''), NULLIF(:sid, ''), :src
            """, {
                'eid': str(uuid.uuid4()),
                'email': clean_email,
                'role': str(role or ''),
                'perfil': str(perfil or 'distribuidor'),
                'pagina': clean_page,
                'dists': dist_str,
                'sid': session_id,
                'src': source,
            }, timeout=45)
        except Exception as e:
            app.logger.warning(f"[log_app_access] {e}")

    import threading
    threading.Thread(target=_writer, daemon=True).start()

def preload_admin_roles(timeout=60):
    """Pré-carrega todos os papéis ativos de tbl_dim_app_admin em memória."""
    try:
        rows = execute_sql(
            f"""SELECT LOWER(TRIM(user_email)) AS email, UPPER(TRIM(role)) AS role
                FROM {CATALOG}.{SCHEMA}.tbl_dim_app_admin
                WHERE is_active = TRUE""",
            timeout=timeout
        )
        role_map = {}
        now_ts = time.time()
        for r in (rows or []):
            em = str(r.get('email') or '').strip()
            rl = str(r.get('role') or '').strip()
            if em and rl in ACCESS_ROLES:
                role_map[em] = rl
                _CACHE_STORAGE[f"admin_role_{em}"] = (rl, now_ts)
        set_in_cache('admin_roles_all', role_map)
        return role_map
    except Exception as e:
        app.logger.warning(f"[preload_admin_roles] {e}")
        return get_stale_from_cache('admin_roles_all')

def get_admin_role(email, timeout=60, raise_on_timeout=False):
    """Retorna 'MASTER', 'ADMIN', 'VISUALIZADOR' ou None. Usa cache em memória + fallback stale."""
    clean = str(email or '').lower().strip()
    if not clean:
        return None
    key = f"admin_role_{clean}"
    hit = _CACHE_STORAGE.get(key)
    if hit and time.time() - hit[1] < ADMIN_ROLE_TTL:
        return hit[0]
    all_map = get_from_cache('admin_roles_all', ttl_seconds=ADMIN_ROLE_TTL)
    if all_map is not None:
        role = all_map.get(clean)
        _CACHE_STORAGE[key] = (role, time.time())
        return role
    try:
        rows = execute_sql(
            f"""SELECT UPPER(TRIM(role)) AS role
                FROM {CATALOG}.{SCHEMA}.tbl_dim_app_admin
                WHERE LOWER(TRIM(user_email)) = :email AND is_active = TRUE
                LIMIT 1""",
            {'email': clean}, timeout=timeout
        )
    except TimeoutError as e:
        app.logger.error(f"[get_admin_role] warehouse ainda iniciando: {e}")
        if hit is not None:
            _warm_warehouse_async()
            return hit[0]
        stale_all = get_stale_from_cache('admin_roles_all')
        if stale_all is not None:
            _warm_warehouse_async()
            return stale_all.get(clean)
        if raise_on_timeout:
            raise
        return None
    except Exception as e:
        app.logger.error(f"[get_admin_role] falha ao consultar tbl_dim_app_admin: {e}")
        if hit is not None:
            return hit[0]
        return None
    role = rows[0].get('role') if rows else None
    role = role if role in ACCESS_ROLES else None
    _CACHE_STORAGE[key] = (role, time.time())
    return role

def get_simulation(email, role):
    """Simulação 'Ver como distribuidor' guardada só no cookie de sessão (nada vai para o mapeamento)."""
    sim = session.get('sim')
    if not sim:
        return None
    sim_id = str(sim.get('id') or '').strip()
    sim_cnpj = str(sim.get('cnpj') or '').strip()
    valid_id = sim_id.isdigit() and int(sim_id) > 0
    valid_cnpj = bool(_CNPJ_RE.match(sim_cnpj))
    if not role or sim.get('by') != email or (not valid_id and not valid_cnpj):
        session.pop('sim', None)
        return None
    out = {'cnpj': sim_cnpj, 'nome': sim.get('nome') or sim_cnpj or f"Distribuidor {sim_id}"}
    if valid_id:
        out['id'] = str(int(sim_id))
    return out

def resolve_access(email):
    """Contexto de acesso. Admin (tbl_dim_app_admin) tem prioridade sobre o mapeamento de distribuidor."""
    role = get_admin_role(email)
    ctx = {
        'email': email, 'role': role, 'is_admin': role is not None, 'is_master': role == 'MASTER',
        'simulacao': get_simulation(email, role), 'cnpjs': [], 'ids': [], 'distribuidores': [],
        'blocked_unvalidated': False, 'unvalidated_names': []
    }
    if not role:
        m = get_user_mapping_details(email)
        ctx['cnpjs'] = m['cnpjs']
        ctx['ids'] = m.get('ids', [])
        ctx['distribuidores'] = m['distribuidores']
        ctx['blocked_unvalidated'] = bool(m.get('blocked_unvalidated'))
        ctx['unvalidated_names'] = m.get('unvalidated_names', [])
    return ctx

def data_scope(ctx, args):
    """(cnpjs, sem_restricao, rotulo). ?dist_id aceita 1 ou mais IDs separados por vírgula.
    Todos os modos respeitam a lista ativa de tbl_dim_distribuidor_portal."""
    g.user_dist_ids = []
    g.admin_dist_id = None
    portal_ids = get_portal_dist_ids()
    portal_set = set(portal_ids)

    if ctx.get('simulacao'):
        sim = ctx['simulacao']
        sim_id = str(sim.get('id') or '').strip()
        if sim_id.isdigit() and str(int(sim_id)) in portal_set:
            sid = str(int(sim_id))
            g.user_dist_ids = [sid]
            g.admin_dist_id = sid
            return ['00000000000000'], False, f"sim_id:{sid}"
        c = normalize_cnpj(sim.get('cnpj'))
        if _CNPJ_RE.match(c):
            for prow in get_portal_dists_rows():
                if prow.get('is_active') and prow.get('cnpj_referencia') == c:
                    sid = str(int(prow['id']))
                    g.user_dist_ids = [sid]
                    g.admin_dist_id = sid
                    return ['00000000000000'], False, f"sim_id:{sid}"
            for grp in get_active_distributor_groups():
                if c == grp.get('cnpj') or c in (grp.get('cnpjs') or []):
                    g.user_dist_ids = [grp['id']]
                    g.admin_dist_id = grp['id']
                    return ['00000000000000'], False, f"sim_id:{grp['id']}"
        return [], False, 'sim:blocked'

    if ctx.get('is_admin'):
        raw_dist_id = str(args.get('dist_id') or '').strip()
        if raw_dist_id:
            req_ids = sorted(
                {str(int(x.strip())) for x in raw_dist_id.split(',') if x.strip().isdigit() and int(x.strip()) > 0},
                key=int
            )
            valid_ids = req_ids
            if not valid_ids:
                return [], False, 'dist_id:none'
            g.user_dist_ids = valid_ids
            if len(valid_ids) == 1:
                g.admin_dist_id = valid_ids[0]
            return ['00000000000000'], False, 'dist_id:' + ','.join(valid_ids)
        d = normalize_cnpj(args.get('dist'))
        if _CNPJ_RE.match(d):
            for prow in get_portal_dists_rows():
                if prow.get('is_active') and prow.get('cnpj_referencia') == d:
                    sid = str(int(prow['id']))
                    g.user_dist_ids = [sid]
                    g.admin_dist_id = sid
                    return ['00000000000000'], False, f"dist_id:{sid}"
            for grp in get_active_distributor_groups():
                if d == grp.get('cnpj') or d in (grp.get('cnpjs') or []):
                    g.user_dist_ids = [grp['id']]
                    g.admin_dist_id = grp['id']
                    return ['00000000000000'], False, f"dist_id:{grp['id']}"
            return [], False, f"dist_blocked:{d}"
        if not portal_ids:
            return [], False, 'all_portal:empty'
        g.user_dist_ids = portal_ids
        return ['00000000000000'], False, 'all_portal:' + ','.join(portal_ids)

    ids = [str(int(x)) for x in ctx.get('ids', []) if str(x).isdigit() and str(int(x)) in portal_set]
    if ids:
        g.user_dist_ids = sorted(set(ids), key=int)
        return ['00000000000000'], False, 'ids:' + ','.join(g.user_dist_ids)
    return ctx.get('cnpjs', []), False, 'own:' + ','.join(sorted(ctx.get('cnpjs', [])))

def _wants_json():
    return request.path.startswith('/api/')

def require_role(master=False, viewer=False):
    """Bloqueio no servidor: rotas/APIs de admin. Páginas redirecionam; APIs devolvem 403.
    viewer=True libera também o VISUALIZADOR (somente rotas de visualização, nunca de governança)."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            email = get_authenticated_user()
            role = get_admin_role(email) if email else None
            allowed = role == 'MASTER' if master else role in (ACCESS_ROLES if viewer else ADMIN_ROLES)
            if not allowed:
                app.logger.warning(f"[ACL] negado: email={email} role={role} path={request.path}")
                if _wants_json():
                    return jsonify({'error': 'Acesso negado: permissão de administrador necessária'}), 403
                return redirect('/dashboard.html')
            request.admin_email = email
            request.admin_role = role
            return fn(*a, **kw)
        return wrapper
    return deco

def log_admin_audit(actor, action, target=None, old_role=None, new_role=None, details=None):
    """Inclusão assíncrona em tbl_log_admin_audit (não trava a resposta ao usuário)."""
    if READ_ONLY:
        app.logger.info(f"[AUDIT SKIPPED read-only] {actor} {action} {target} {details}")
        return
    params = {
        'event_id': str(uuid.uuid4()),
        'actor': actor,
        'action': action,
        'target': target or '',
        'old_role': old_role or '',
        'new_role': new_role or '',
        'details': (details or '')[:1000]
    }
    def _audit_writer():
        try:
            execute_sql(
                f"""INSERT INTO {CATALOG}.{SCHEMA}.tbl_log_admin_audit
                    (event_id, event_ts, actor_email, action, target_email, old_role, new_role, details, source)
                    SELECT :event_id, current_timestamp(), :actor, :action,
                           NULLIF(:target, ''), NULLIF(:old_role, ''), NULLIF(:new_role, ''), NULLIF(:details, ''), 'APP'""",
                params, timeout=60
            )
        except Exception as e:
            app.logger.error(f"[AUDIT FAIL] {params}: {e}")
    import threading
    threading.Thread(target=_audit_writer, daemon=True).start()

def get_user_mapping_details(email):
    """
    Vínculos ativos de distribuidor do usuário (somente modo distribuidor).
    O papel de admin vem exclusivamente de tbl_dim_app_admin.
    Somente distribuidores ativos em tbl_dim_distribuidor_portal têm acesso liberado.
    """
    clean_em = str(email or '').lower().strip()
    cache_key = f"user_map_{clean_em}"
    cached_map = get_from_cache(cache_key, ttl_seconds=900)
    if cached_map is not None:
        return cached_map
    portal_set = set(get_portal_dist_ids())
    try:
        id_rows = execute_sql(f"""
            SELECT CAST(id_distribuidor AS STRING) AS id, distributor_name, is_active,
                   CAST(valid_to_date AS STRING) AS valid_to_date
            FROM {_ID_MAP_TBL}
            WHERE LOWER(TRIM(user_email)) = LOWER(TRIM(:email))
        """, {'email': email})
        if id_rows:
            mapped_ids = sorted({str(int(r['id'])) for r in id_rows
                                 if str(r.get('is_active')).lower() == 'true'
                                 and (not r.get('valid_to_date') or str(r['valid_to_date']) >= time.strftime('%Y-%m-%d'))
                                 and str(r.get('id') or '').isdigit() and int(r['id']) > 0}, key=int)
            names = {str(int(r['id'])): r.get('distributor_name') for r in id_rows if str(r.get('id') or '').isdigit()}
            try:
                for grp in get_active_distributor_groups():
                    if grp.get('id') and grp.get('nome'):
                        names[str(grp['id'])] = grp['nome']
            except Exception:
                pass
            valid_ids = [x for x in mapped_ids if x in portal_set]
            blocked = bool(mapped_ids and not valid_ids)
            unval_names = [names.get(x) or f"Distribuidor {x}" for x in mapped_ids if x not in portal_set]
            res = {
                'cnpjs': [],
                'ids': valid_ids,
                'distribuidores': [{'id': x, 'nome': names.get(x) or ('Distribuidor ' + x)} for x in valid_ids],
                'blocked_unvalidated': blocked,
                'unvalidated_names': unval_names,
            }
            set_in_cache(cache_key, res)
            return res
        query = f"""
            SELECT 
                distributor_cnpj_code, 
                distributor_name
            FROM {CATALOG}.{SCHEMA}.tbl_dim_distributor_user_mapping
            WHERE LOWER(TRIM(user_email)) = LOWER(TRIM(:email))
              AND is_active = TRUE
              AND (valid_to_date IS NULL OR valid_to_date >= CURRENT_DATE())
        """
        rows = execute_sql(query, {'email': email})

        active_groups = []
        try:
            active_groups = get_active_distributor_groups()
        except Exception:
            pass
        cnpj_to_group = {}
        for grp in active_groups:
            for c in (grp.get('cnpjs') or []):
                cnpj_to_group[c] = grp

        cnpjs = []
        ids = []
        distribuidores = []
        had_rows = False
        unval_names = []

        for r in rows:
            cnpj_raw = str(r.get('distributor_cnpj_code') or '').strip()
            cnpj = cnpj_raw.zfill(14) if cnpj_raw else ''
            if not cnpj:
                continue
            had_rows = True
            grp = cnpj_to_group.get(cnpj)
            if grp and grp.get('id') in portal_set:
                gid = grp['id']
                if gid not in ids:
                    ids.append(gid)
                    distribuidores.append({'id': gid, 'cnpj': cnpj, 'nome': grp.get('nome') or r.get('distributor_name') or cnpj})
            else:
                unval_names.append(r.get('distributor_name') or cnpj)

        blocked = bool(had_rows and not ids and not cnpjs)
        res = {
            'cnpjs': cnpjs,
            'ids': ids,
            'distribuidores': distribuidores,
            'blocked_unvalidated': blocked,
            'unvalidated_names': unval_names,
        }
        set_in_cache(cache_key, res)
        return res
    except Exception as e:
        app.logger.error(f"[Mapping Query Fail] {e}")
        stale = get_stale_from_cache(cache_key)
        if stale is not None:
            return stale
        return {'cnpjs': [], 'ids': [], 'distribuidores': [], 'blocked_unvalidated': False, 'unvalidated_names': []}

def _dist_display_name(cnpj, fallback=None):
    """Nome de exibição do distribuidor (DESC_DISTRIBUIDOR_DNA via catálogo); sem catálogo, usa o fallback."""
    try:
        match = next((d for d in get_distributor_catalog() if d['cnpj'] == cnpj), None)
        if match and match.get('nome') and match['nome'] != cnpj:
            return match['nome']
    except Exception as e:
        app.logger.warning(f"[dist_display_name] catálogo indisponível: {e}")
    return fallback

# ─── Rotas de Healthcheck & Diagnóstico ─────────────────────────────────────────
@app.route('/health')
@app.route('/_health')
def healthcheck():
    return 'OK', 200

@app.route('/_diag/headers')
@require_role()
def diag_headers():
    forwarded = {}
    for k, v in request.headers.items():
        if k.lower().startswith('x-forwarded') or k.lower().startswith('x-databricks'):
            if 'token' in k.lower() or 'authorization' in k.lower():
                forwarded[k] = f"{v[:10]}..." if v else None
            else:
                forwarded[k] = v
    return jsonify(forwarded)

# ─── Rotas Estáticas ──────────────────────────────────────────────────────────
# Distribuidor: Início (index.html) e dashboard.html (KPIs + Pedidos de Compra).
# Blocos <!-- ADMIN_ONLY_START --> ... <!-- ADMIN_ONLY_END --> são removidos no servidor
# para distribuidores e durante a simulação. <!-- SIM_BANNER --> recebe a faixa de simulação.
_ADMIN_BLOCK_RE = re.compile(r'<!--\s*ADMIN_ONLY_START\s*-->.*?<!--\s*ADMIN_ONLY_END\s*-->', re.S)
# Blocos <!-- GOVERNANCE_ONLY_START --> ... <!-- GOVERNANCE_ONLY_END --> também somem para o VISUALIZADOR.
_GOVERNANCE_BLOCK_RE = re.compile(r'<!--\s*GOVERNANCE_ONLY_START\s*-->.*?<!--\s*GOVERNANCE_ONLY_END\s*-->', re.S)
_NO_STORE = {'Cache-Control': 'no-store, max-age=0'}

def _read_page(filename):
    with open(os.path.join(BASE_DIR, filename), encoding='utf-8') as f:
        return f.read()

def _sim_banner_html(sim):
    nome = html_lib.escape(str(sim.get('nome') or ''))
    return f"""<div id="sim-banner" class="sim-banner" role="status">
  <span>Você está vendo o portal como <strong>{nome}</strong></span>
  <button type="button" class="btn-exit-sim" onclick="(function(){{fetch('/api/admin/simulacao',{{method:'DELETE',credentials:'include'}}).finally(function(){{location.href='/dashboard.html?sair_sim=1';}});}})()">Sair da simulação</button>
</div>"""

# Tela leve exibida enquanto o SQL Warehouse sobe (evita o 502 do proxy, que corta em ~60s).
_WARMING_HTML = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="refresh" content="6">
<title>Preparando o portal…</title>
<style>
  html,body{height:100%;margin:0}
  body{display:grid;place-items:center;background:#F6F7FB;color:#1B2440;font:15px/1.5 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
  .c{max-width:420px;padding:32px;text-align:center;background:#fff;border:1px solid #E3E7F0;border-radius:14px;box-shadow:0 1px 2px rgba(12,33,103,.06)}
  .s{width:28px;height:28px;margin:0 auto 16px;border-radius:50%;border:3px solid #E3E7F0;border-top-color:#0C2167;animation:r .9s linear infinite}
  h1{margin:0 0 6px;font-size:18px;font-weight:600;color:#0C2167}p{margin:0;color:#5B6478}
  @keyframes r{to{transform:rotate(360deg)}}@media (prefers-reduced-motion:reduce){.s{animation:none}}
</style></head><body><div class="c" role="status" aria-live="polite"><div class="s" aria-hidden="true"></div>
<h1>Preparando o portal</h1><p>Estamos iniciando a conexão com os dados. A página recarrega sozinha em instantes.</p></div></body></html>"""

def render_portal_page(filename):
    email = get_authenticated_user()
    try:
        role = get_admin_role(email, timeout=25, raise_on_timeout=True) if email else None
    except TimeoutError:
        _warm_warehouse_async()
        return Response(_WARMING_HTML, status=200, mimetype='text/html', headers=_NO_STORE)
    if request.args.get('sair_sim') or request.args.get('exit_sim'):
        session.pop('sim', None)
        return redirect(request.path)
    sim = get_simulation(email, role) if role else None
    page = _read_page(filename)
    if not role or sim:
        page = _ADMIN_BLOCK_RE.sub('', page)
    if role not in ADMIN_ROLES or sim:
        page = _GOVERNANCE_BLOCK_RE.sub('', page)
    page = page.replace('<!-- SIM_BANNER -->', _sim_banner_html(sim) if sim else '')
    return Response(page, mimetype='text/html', headers=_NO_STORE)

@app.route('/')
@app.route('/index.html')
def index():
    # Capa virou a aba Início do app (dashboard.html abre nela pela raiz)
    return render_portal_page('dashboard.html')

@app.route('/home.html')
def home():
    return redirect('/index.html')

@app.route('/dashboard.html')
def dashboard():
    return render_portal_page('dashboard.html')

# Páginas exclusivas de administrador (bloqueadas no servidor)
@app.route('/guia.html')
@app.route('/guia')
@require_role(viewer=True)
def serve_guia():
    log_app_access_async(request.admin_email, request.admin_role, 'admin', 'guia')
    return send_file(os.path.join(BASE_DIR, 'guia.html'))

@app.route('/gestao_acesso.html')
@app.route('/gestao-acessos')
@require_role()
def serve_gestao_acesso():
    # Tela Gestão de Acessos (MASTER edita, ADMIN só lê). O antigo seletor de perfil
    # (gestao_acesso.html, com link para ?perfil=admin) não é mais servido.
    # V2: tela redesenhada (tokens.css + v2.css). admin_acessos.html antigo fica sem uso.
    log_app_access_async(request.admin_email, request.admin_role, 'admin', 'gestao-acessos')
    return Response(_read_page('acessos_v2.html'), mimetype='text/html', headers=_NO_STORE)

@app.route('/uso_portal.html')
@app.route('/uso-portal')
@require_role()
def serve_uso_portal():
    log_app_access_async(request.admin_email, request.admin_role, 'admin', 'uso-portal')
    return Response(_read_page('acessos_v2.html'), mimetype='text/html', headers=_NO_STORE)

@app.route('/dashboard_admin.html')
@require_role()
def serve_dashboard_admin():
    return send_file(os.path.join(BASE_DIR, 'dashboard_admin.html'))

@app.route('/preview_dashboard.html')
@require_role()
def serve_preview_dashboard():
    return send_file(os.path.join(BASE_DIR, 'preview_dashboard.html'))

# Página legada de login por formulário (o acesso é pelo SSO do Databricks Apps)
@app.route('/login.html')
def legacy_login():
    return redirect('/index.html')

# Scripts exclusivos de admin
_ADMIN_JS = {'admin_mode.js', 'gestao_acesso.js'}

@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'css'), filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    if filename in _ADMIN_JS:
        email = get_authenticated_user()
        role = get_admin_role(email) if email else None
        if role not in (ADMIN_ROLES if filename == 'gestao_acesso.js' else ACCESS_ROLES):
            return jsonify({'error': 'Acesso negado'}), 403
    return send_from_directory(os.path.join(BASE_DIR, 'js'), filename)

@app.route('/img/<path:filename>')
def serve_img(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'img'), filename)

# ─── API GET /api/me ──────────────────────────────────────────────────────────
@app.route('/api/me')
def api_me():
    email = get_authenticated_user()
    if not email:
        return jsonify({'error': 'Acesso Negado: Header x-forwarded-email ausente ou inválido'}), 403

    ctx = resolve_access(email)
    sim = ctx['simulacao']
    # Na simulação o front recebe exatamente o perfil de distribuidor.
    is_admin_ui = ctx['is_admin'] and not sim

    if not ctx['is_admin']:
        if ctx.get('blocked_unvalidated'):
            return jsonify({
                'error': 'Portal indisponível para o seu distribuidor no momento (Sell-out em validação).',
                'email': email,
                'blocked_unvalidated': True,
                'distribuidores_inativos': ctx.get('unvalidated_names', [])
            }), 403
        if not ctx.get('distribuidores'):
            return jsonify({
                'error': 'Usuário sem distribuidor vinculado.',
                'email': email,
                'blocked_unvalidated': False
            }), 403

    if sim:
        distribuidores = [{'id': sim.get('id'), 'cnpj': sim.get('cnpj', ''), 'nome': sim['nome']}]
        desc_distribuidor = sim['nome']
    elif is_admin_ui:
        distribuidores = []
        desc_distribuidor = 'Visualizador Bimbo QSR' if ctx['role'] == 'VISUALIZADOR' else 'Administrador Bimbo QSR'
    else:
        distribuidores = ctx['distribuidores']
        desc_distribuidor = distribuidores[0]['nome'] if distribuidores and distribuidores[0].get('nome') else None
        # Vários distribuidores: os dados somam todos; a saudação deixa isso visível
        if desc_distribuidor and len(distribuidores) > 1:
            desc_distribuidor += f" +{len(distribuidores) - 1}"

    last_exec = get_last_job_execution()
    log_dist_ids = [sim.get('id') or sim.get('cnpj')] if sim else ctx.get('ids', [])
    log_app_access_async(email, ctx.get('role'), 'simulacao' if sim else ('admin' if is_admin_ui else 'distribuidor'), 'dashboard', log_dist_ids)

    payload = {
        'email': email,
        'admin': is_admin_ui,
        'perfil': 'admin' if is_admin_ui else 'distribuidor',
        'distribuidores': distribuidores,
        'desc_distribuidor': desc_distribuidor,
        'ultima_atualizacao': last_exec.get('last_updated', '15/10/2026 às 12:33'),
        'job_id': JOB_ID
    }
    if ctx['is_admin']:
        payload['role'] = ctx['role']
        payload['simulacao'] = sim
    return jsonify(payload)

@app.route('/api/system/last-update')
def api_system_last_update():
    return jsonify(get_last_job_execution())

# ─── Helper Cláusulas WHERE por Tabela (RLS Preservando Data Skipping) ──────────
def build_where_table(date_col, mapped_cnpjs, args, has_orders=False, param_prefix='', is_admin=False, ignore_mes=False):
    """
    Constrói a cláusula WHERE com RLS por CNPJ e filtros opcionais.
    param_prefix: prefixo para nomes de parâmetros, evitando conflito
                  quando a mesma tabela é usada em múltiplas CTEs.
    """
    conds = []
    params = {}
    pfx = param_prefix

    if not mapped_cnpjs:
        if not is_admin:
            conds.append("1 = 0")
    group_ids = getattr(g, 'user_dist_ids', [])
    group_id = getattr(g, 'admin_dist_id', None)
    if group_ids and not is_admin:
        if all(str(v).strip().isdigit() for v in group_ids):
            int_ids = [str(int(str(v).strip())) for v in group_ids]
            if len(int_ids) == 1:
                conds.append(f"f.ID_DISTRIBUIDOR = {int_ids[0]}")
            else:
                conds.append(f"f.ID_DISTRIBUIDOR IN ({', '.join(int_ids)})")
        else:
            keys = []
            for i, value in enumerate(group_ids):
                key = f'{pfx}user_dist_id_{i}'
                params[key] = value
                keys.append(':' + key)
            conds.append(f"CAST(f.ID_DISTRIBUIDOR AS STRING) IN ({', '.join(keys)})")
    elif group_id and not is_admin:
        if str(group_id).strip().isdigit():
            conds.append(f"f.ID_DISTRIBUIDOR = {int(str(group_id).strip())}")
        else:
            params[f'{pfx}dist_id'] = group_id
            conds.append(f"CAST(f.ID_DISTRIBUIDOR AS STRING) = :{pfx}dist_id")
    elif mapped_cnpjs and not is_admin:
        placeholders = []
        unique_cnpjs = []
        for c in mapped_cnpjs:
            clean = str(c).strip()
            if clean:
                unique_cnpjs.append(clean)
                formatted = clean.zfill(14)
                if formatted != clean:
                    unique_cnpjs.append(formatted)
        
        unique_cnpjs = [u for u in set(unique_cnpjs) if u]
        for idx, cnpj in enumerate(unique_cnpjs):
            pkey = f"{pfx}rls_cnpj_{idx}"
            params[pkey] = cnpj
            placeholders.append(f":{pkey}")
        
        conds.append(f"(f.CNPJ_DISTRIBUIDOR IN ({', '.join(placeholders)}) OR CAST(TRY_CAST(f.CNPJ_DISTRIBUIDOR as BIGINT) as STRING) IN ({', '.join(placeholders)}))")

    # Se estiver filtrando pedido específico em tabela de pedidos, não restringe data (ano, mês, dia, semana)
    # para encontrar o pedido mesmo que emitido/entregue em outro período ou com data nula
    skip_date_filter_for_order = has_orders and bool(args.get('pedido'))

    years = [a.strip() for a in (args.get('ano') or '').split(',') if a.strip()] if not skip_date_filter_for_order else []
    months = [m.strip() for m in (args.get('mes') or '').split(',') if m.strip().isdigit()] if (not ignore_mes and not skip_date_filter_for_order) else []
    years_int = [int(y) for y in years if y.isdigit() and 2000 <= int(y) <= 2100]
    months_int = [int(m) for m in months if 1 <= int(m) <= 12]

    if years_int:
        y_min, y_max = min(years_int), max(years_int)
        if months_int:
            m_min, m_max = min(months_int), max(months_int)
            _, last_d = calendar.monthrange(y_max, m_max)
            params[f"{pfx}dt_min"] = f"{y_min:04d}-{m_min:02d}-01"
            params[f"{pfx}dt_max"] = f"{y_max:04d}-{m_max:02d}-{last_d:02d}"
            conds.append(f"f.{date_col} >= :{pfx}dt_min AND f.{date_col} <= :{pfx}dt_max")
            if len(years_int) > 1 or len(months_int) > 1:
                conds.append(f"YEAR(f.{date_col}) IN ({', '.join(str(y) for y in years_int)})")
                conds.append(f"MONTH(f.{date_col}) IN ({', '.join(str(m) for m in months_int)})")
        else:
            params[f"{pfx}dt_min"] = f"{y_min:04d}-01-01"
            params[f"{pfx}dt_max"] = f"{y_max:04d}-12-31"
            conds.append(f"f.{date_col} >= :{pfx}dt_min AND f.{date_col} <= :{pfx}dt_max")
            if len(years_int) > 1 and (y_max - y_min + 1) != len(set(years_int)):
                conds.append(f"YEAR(f.{date_col}) IN ({', '.join(str(y) for y in years_int)})")
    else:
        if years:
            p_years = []
            for i, y in enumerate(years):
                pkey = f"{pfx}ano_{i}"
                params[pkey] = y
                p_years.append(f":{pkey}")
            conds.append(f"CAST(YEAR(f.{date_col}) as STRING) IN ({', '.join(p_years)})")
        if months_int:
            conds.append(f"MONTH(f.{date_col}) IN ({', '.join(str(m) for m in months_int)})")

    if args.get('dia') and not skip_date_filter_for_order:
        days = [d.strip() for d in args['dia'].split(',') if d.strip().isdigit()]
        if days:
            p_days = []
            for i, d in enumerate(days):
                pkey = f"{pfx}dia_{i}"
                params[pkey] = int(d)
                p_days.append(f":{pkey}")
            conds.append(f"DAY(f.{date_col}) IN ({', '.join(p_days)})")

    if args.get('semana') and not skip_date_filter_for_order:
        weeks = [w.strip() for w in args['semana'].split(',') if w.strip().isdigit()]
        if weeks:
            p_weeks = []
            for i, w in enumerate(weeks):
                pkey = f"{pfx}sem_{i}"
                params[pkey] = int(w)
                p_weeks.append(f":{pkey}")
            conds.append(f"WEEKOFYEAR(f.{date_col}) IN ({', '.join(p_weeks)})")

    if args.get('categoria'):
        cats = [c.strip().lower() for c in args['categoria'].split(',') if c.strip()]
        has_paes = any(('pão' in c or 'pao' in c or 'paes' in c or 'pães' in c or c.startswith('pã') or c.startswith('pa')) for c in cats)
        has_esp = any(('esp' in c or 'especialidade' in c or 'doce' in c or 'bolo' in c) for c in cats)
        paes_kw = ['pão', 'pao', 'brioche', 'hamb', 'hb', 'hot dog', 'hotdog', 'artesano', 'australiano', 'nuvem', 'buns', 'tradicional', 'baguete', 'ciabata', 'bola', 'sweet honey']
        if has_paes and not has_esp:
            or_parts = [f"LOWER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%{kw}%'" for kw in paes_kw]
            conds.append(f"({' OR '.join(or_parts)})")
        elif has_esp and not has_paes:
            or_parts = [f"LOWER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%{kw}%'" for kw in paes_kw]
            conds.append(f"(f.DESC_PROD_BQ IS NOT NULL AND f.DESC_PROD_BQ NOT IN ('META', 'META SEMANAL', 'META POSITIVACAO SEMANAL', 'SEM DESCRIÇÃO') AND NOT ({' OR '.join(or_parts)}))")

    if args.get('produto'):
        prods = [p.strip() for p in args['produto'].split(',') if p.strip()]
        if prods:
            p_prods = []
            for i, pr in enumerate(prods):
                pkey = f"{pfx}prod_{i}"
                params[pkey] = pr
                p_prods.append(f":{pkey}")
            conds.append(f"f.DESC_PROD_BQ IN ({', '.join(p_prods)})")

    if args.get('sku'):
        skus = [s.split(' - ')[0].strip() if ' - ' in s else s.strip() for s in args['sku'].split(',') if s.strip()]
        if skus:
            p_skus = []
            for i, sk in enumerate(skus):
                pkey = f"{pfx}sku_{i}"
                params[pkey] = sk
                p_skus.append(f":{pkey}")
            conds.append(f"(f.SKU_PROD_BQ IN ({', '.join(p_skus)}) OR CAST(f.SKU_PROD_DIST as STRING) IN ({', '.join(p_skus)}))")

    if args.get('pedido'):
        peds = [p.strip() for p in args['pedido'].split(',') if p.strip()]
        if peds:
            p_peds = []
            for i, pd in enumerate(peds):
                pkey = f"{pfx}ped_{i}"
                params[pkey] = pd
                p_peds.append(f":{pkey}")
            if has_orders:
                conds.append(f"(TRIM(CAST(f.NUMERO_PEDIDO as STRING)) IN ({', '.join(p_peds)}) OR CAST(TRY_CAST(f.NUMERO_PEDIDO as BIGINT) as STRING) IN ({', '.join(p_peds)}))")
            else:
                ped_cond = f"(TRIM(CAST(ord.NUMERO_PEDIDO as STRING)) IN ({', '.join(p_peds)}) OR CAST(TRY_CAST(ord.NUMERO_PEDIDO as BIGINT) as STRING) IN ({', '.join(p_peds)}))"
                conds.append(f"f.SKU_PROD_BQ IN (SELECT DISTINCT ord.SKU_PROD_BQ FROM {CATALOG}.{SCHEMA}.tbl_factdy_order ord WHERE {ped_cond} AND ord.SKU_PROD_BQ IS NOT NULL)")
                if is_admin and not mapped_cnpjs:
                    conds.append(f"f.CNPJ_DISTRIBUIDOR IN (SELECT DISTINCT ord.CNPJ_DISTRIBUIDOR FROM {CATALOG}.{SCHEMA}.tbl_factdy_order ord WHERE {ped_cond} AND ord.CNPJ_DISTRIBUIDOR IS NOT NULL)")

    where_str = f"WHERE {' AND '.join(conds)}" if conds else ""
    return where_str, params

def _py_biz_day_cutoff(ref_dt=None):
    tz_br = timezone(timedelta(hours=-3))
    today_dt = ref_dt or datetime.now(tz_br).date()
    cur_bdays = 0
    for day_num in range(1, today_dt.day):
        if today_dt.replace(day=day_num).weekday() < 6:
            cur_bdays += 1
    py_year = today_dt.year - 1
    py_month = today_dt.month
    _, py_last = calendar.monthrange(py_year, py_month)
    if cur_bdays <= 0:
        prev_day = today_dt.replace(year=py_year, day=1) - timedelta(days=1)
        return 0, prev_day.isoformat()
    seen = 0
    matched_dt = today_dt.replace(year=py_year, day=py_last)
    for day_num in range(1, py_last + 1):
        d_cand = today_dt.replace(year=py_year, day=day_num)
        if d_cand.weekday() < 6:
            seen += 1
            if seen == cur_bdays:
                matched_dt = d_cand
                break
    return cur_bdays, matched_dt.isoformat()

# ─── API GET /api/kpi ──────────────────────────────────────────────────────────
@app.route('/api/kpi')
def api_kpi():
    email = get_authenticated_user()
    if not email:
        return jsonify({'error': 'Acesso Negado: Header x-forwarded-email ausente ou inválido'}), 403

    ctx = resolve_access(email)
    # is_admin aqui significa "sem filtro de CNPJ" (admin em "Todos os distribuidores").
    # Admin com ?dist=<CNPJ> ou em simulação: filtrado pelo CNPJ escolhido.
    # Distribuidor: ?dist é ignorado e vale sempre o CNPJ do mapeamento.
    mapped_cnpjs, is_admin, scope_label = data_scope(ctx, request.args)

    if not mapped_cnpjs and not is_admin:
        if ctx.get('blocked_unvalidated'):
            return jsonify({
                'error': f"Portal indisponível para o seu distribuidor no momento (Sell-out em validação).",
                'blocked_unvalidated': True
            }), 403
        app.logger.warning(f"[RLS /api/kpi] BLOQUEADO: email={email} sem CNPJ no mapping")
        return jsonify({'error': f"Acesso Negado: Usuário '{email}' não possui nenhum distribuidor cadastrado no mapping"}), 403

    args = request.args

    # Cache de performance /api/kpi (TTL: 900s - 15 minutos)
    # A chave inclui o escopo efetivo (all_portal / dist_id:<IDs> / sim_id:<ID> / ids:<IDs>)
    cache_args = sorted((k, v) for k, v in args.items() if k not in ('dist', 'dist_id', 'perfil'))
    cache_key_kpi = f"kpi_{email}_{scope_label}_{str(cache_args)}"
    cached_kpi = get_from_cache(cache_key_kpi, ttl_seconds=900)
    if cached_kpi:
        return jsonify(cached_kpi)

    # Cada query recebe um prefixo de parâmetros distinto para evitar conflito de nomes
    # Sell-In e Sell-Out usam ignore_mes=True para alimentar o gráfico com histórico completo de 12 meses
    w_sellin, p_sellin   = build_where_table('DT_SELL_IN', mapped_cnpjs, args, has_orders=False, param_prefix='si_', is_admin=is_admin, ignore_mes=True)
    # Filtros sem recorte de data (ano/mês/dia/semana): usados por estoque (sempre mês vigente),
    # base esperada de DTs no tracking e ano anterior (YoY)
    _DATE_KEYS = ('ano', 'mes', 'dia', 'semana')
    args_nodate = {k: v for k, v in args.items() if k not in _DATE_KEYS}
    multi_dist = is_admin or len(getattr(g, 'user_dist_ids', [])) > 1 or bool(getattr(g, 'admin_dist_id', None)) or len({str(c).strip().lstrip('0') for c in (mapped_cnpjs or []) if str(c).strip()}) > 1

    # Dias de estoque: independe do mês filtrado e usa somente o mês vigente.
    w_stock, p_stock     = build_where_table('DATA_ESTOQUE', mapped_cnpjs, args_nodate, has_orders=False, param_prefix='sk_', is_admin=is_admin)
    w_stock = f"{w_stock} AND f.DATA_ESTOQUE >= date_trunc('MM', current_date()) AND f.DATA_ESTOQUE <= current_date()" if w_stock else "WHERE f.DATA_ESTOQUE >= date_trunc('MM', current_date()) AND f.DATA_ESTOQUE <= current_date()"
    w_positiv, p_positiv = build_where_table('DATA_SELL_OUT', mapped_cnpjs, args, has_orders=False, param_prefix='pv_', is_admin=is_admin)
    w_positiv_monthly, p_positiv_monthly = build_where_table('DATA_SELL_OUT', mapped_cnpjs, args, has_orders=False, param_prefix='pm_', is_admin=is_admin, ignore_mes=True)
    w_orders, p_orders   = build_where_table('DATA_PREVISAO_ENTREGA', mapped_cnpjs, args, has_orders=True, param_prefix='od_', is_admin=is_admin)
    w_tracking, p_tracking = build_where_table('DATA_SELL_OUT', mapped_cnpjs, args, has_orders=False, param_prefix='tr_', is_admin=is_admin)
    # Carteira em aberto (regra DNA de Vendas / Power BI): pedido aberto conta no mês de
    # GREATEST(entrega prevista, hoje) — a origem regrava o aberto em DT_REGISTRO = hoje enquanto não fatura.
    w_orders_cart, p_orders_cart = build_where_table('DT_CARTEIRA', mapped_cnpjs, args, has_orders=True, param_prefix='oc_', is_admin=is_admin)

    # Ano anterior: meses completos, com corte proporcional apenas no mês corrente.
    py_years = []
    for _y in (args.get('ano') or '').split(','):
        _y = _y.strip()
        if _y.isdigit():
            py_years.append(str(int(_y) - 1))
    args_py = dict(args_nodate)
    if py_years:
        args_py['ano'] = ','.join(py_years)
    w_si_py, p_si_py = build_where_table('DT_SELL_IN', mapped_cnpjs, args_py, has_orders=False, param_prefix='sipy_', is_admin=is_admin, ignore_mes=True)
    w_so_py, p_so_py = build_where_table('DATA_SELL_OUT', mapped_cnpjs, args_py, has_orders=False, param_prefix='sopy_', is_admin=is_admin, ignore_mes=True)

    cur_bdays_yoy, py_biz_cutoff_dt = _py_biz_day_cutoff()
    py_cur_year = datetime.now(timezone(timedelta(hours=-3))).year
    py_cur_month = datetime.now(timezone(timedelta(hours=-3))).month

    # Tracking (vários DTs): mês exibido = 1º ano/mês filtrado ou mês atual (mesma regra do front)
    _now = time.localtime()
    try:
        trk_year = int((args.get('ano') or '').split(',')[0].strip())
    except ValueError:
        trk_year = _now.tm_year
    try:
        trk_month = int((args.get('mes') or '').split(',')[0].strip())
        if not 1 <= trk_month <= 12:
            trk_month = _now.tm_mon
    except ValueError:
        trk_month = _now.tm_mon
    w_trk_exp, p_trk_exp = build_where_table('DATA_SELL_OUT', mapped_cnpjs, args_nodate, has_orders=False, param_prefix='tx_', is_admin=is_admin)
    p_trk_exp['tx_ini'] = f"{trk_year:04d}-{trk_month:02d}-01"

    w_mix_cur, p_mix_cur = build_where_table('DATA_SELL_OUT', mapped_cnpjs, args, has_orders=False, param_prefix='mxc_', is_admin=is_admin)
    args_mix_py = dict(args)
    if py_years:
        args_mix_py['ano'] = ','.join(py_years)
    w_mix_py, p_mix_py = build_where_table('DATA_SELL_OUT', mapped_cnpjs, args_mix_py, has_orders=False, param_prefix='mxp_', is_admin=is_admin)
    w_rx, p_rx = build_where_table('DATA_SELL_OUT', mapped_cnpjs, args_nodate, has_orders=False, param_prefix='rx_', is_admin=is_admin)
    p_rx['rx_m_ini'] = f"{trk_year:04d}-{trk_month:02d}-01"

    results = {'sellin': [], 'sellout': [], 'stock': [], 'positiv': [], 'orders': [], 'order_metrics': [], 'positiv_monthly': [], 'tracking': [],
               'order_open': [], 'sellin_py': [], 'sellout_py': [], 'tracking_expected': [], 'mix': [], 'reactivate': []}
    error_msg = None

    try:
        # Invoiced: soma sem arredondamento da origem curada; volume e meta da fato semântica.
        q_sellin = f"""
            WITH semantica AS (
                SELECT MONTH(f.DT_SELL_IN) AS MES, YEAR(f.DT_SELL_IN) AS ANO,
                       SUM(f.VL_FORECAST) AS total_vl_forecast,
                       SUM(f.QTDE_SELL_IN) AS total_qty_sell_in,
                       SUM(f.QTDE_FORECAST) AS total_qty_forecast
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellin f
                {w_sellin}
                GROUP BY MONTH(f.DT_SELL_IN), YEAR(f.DT_SELL_IN)
            ), invoiced AS (
                SELECT MONTH(f.DT_SELL_IN) AS MES, YEAR(f.DT_SELL_IN) AS ANO,
                       SUM(f.VL_CYW_LIQ_VENDIDO) AS total_vl_sell_in
                FROM (SELECT c.*, c.SKU_DIST AS SKU_PROD_DIST FROM {CATALOG}.opebrapodis_cz.sellin c) f
                {w_sellin} {'AND' if w_sellin else 'WHERE'} f.CNPJ_BIMBO <> 0
                GROUP BY MONTH(f.DT_SELL_IN), YEAR(f.DT_SELL_IN)
            )
            SELECT COALESCE(s.ANO, i.ANO) AS ANO, COALESCE(s.MES, i.MES) AS MES,
                   COALESCE(i.total_vl_sell_in, 0) AS total_vl_sell_in,
                   COALESCE(s.total_vl_forecast, 0) AS total_vl_forecast,
                   COALESCE(s.total_qty_sell_in, 0) AS total_qty_sell_in,
                   COALESCE(s.total_qty_forecast, 0) AS total_qty_forecast
            FROM semantica s FULL OUTER JOIN invoiced i ON s.ANO = i.ANO AND s.MES = i.MES
            ORDER BY ANO, MES
        """

        # Sell-Out com Meta sem Fanout (FULL OUTER JOIN no grão ANO, MES) com histórico completo
        w_so_meta, p_so_meta = build_where_table('DATA_SELL_OUT', mapped_cnpjs, args, has_orders=False, param_prefix='som_', is_admin=is_admin, ignore_mes=True)
        w_so_real, p_so_real = build_where_table('DATA_SELL_OUT', mapped_cnpjs, args, has_orders=False, param_prefix='sor_', is_admin=is_admin, ignore_mes=True)
        p_sellout_merged = {**p_so_meta, **p_so_real}

        w_so_meta_clause = f"{w_so_meta} AND (f.SKU_PROD_BQ = 'META' OR f.VL_SELL_OUT = 0) AND f.VL_META IS NOT NULL AND f.VL_META > 0" if w_so_meta else "WHERE (f.SKU_PROD_BQ = 'META' OR f.VL_SELL_OUT = 0) AND f.VL_META IS NOT NULL AND f.VL_META > 0"
        w_so_real_clause = f"{w_so_real} AND (f.SKU_PROD_BQ != 'META' OR f.SKU_PROD_BQ IS NULL)" if w_so_real else "WHERE (f.SKU_PROD_BQ != 'META' OR f.SKU_PROD_BQ IS NULL)"

        q_sellout = f"""
            WITH meta_agg AS (
                SELECT 
                    MONTH(f.DATA_SELL_OUT) as MES,
                    YEAR(f.DATA_SELL_OUT)  as ANO,
                    SUM(f.VL_META)         as total_vl_meta
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
                {w_so_meta_clause}
                GROUP BY MONTH(f.DATA_SELL_OUT), YEAR(f.DATA_SELL_OUT)
            ),
            realizado_agg AS (
                SELECT 
                    MONTH(f.DATA_SELL_OUT)         as MES,
                    YEAR(f.DATA_SELL_OUT)          as ANO,
                    SUM(f.VL_SELL_OUT)            as total_vl_sell_out,
                    SUM(f.QTDE_UNITARIO_SELL_OUT) as total_qty_sell_out,
                    SUM(f.QTDE_DUZIA_SELL_OUT)    as total_qty_dz_sell_out
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
                {w_so_real_clause}
                GROUP BY MONTH(f.DATA_SELL_OUT), YEAR(f.DATA_SELL_OUT)
            )
            SELECT 
                COALESCE(r.ANO, m.ANO)                 as ANO,
                COALESCE(r.MES, m.MES)                 as MES,
                COALESCE(r.total_vl_sell_out, 0)       as total_vl_sell_out,
                COALESCE(r.total_qty_sell_out, 0)      as total_qty_sell_out,
                COALESCE(r.total_qty_dz_sell_out, 0)   as total_qty_dz_sell_out,
                COALESCE(m.total_vl_meta, 0)           as total_vl_meta
            FROM realizado_agg r
            FULL OUTER JOIN meta_agg m ON r.ANO = m.ANO AND r.MES = m.MES
            ORDER BY ANO, MES
        """

        # Dias de estoque por SKU:
        #   - posição mais recente de cada DT x SKU no mês vigente (independe do filtro de mês)
        #   - só SKUs com sell-out do próprio DT nos últimos 3 meses
        #   - vários DTs ("Todos"): consolida por SKU = soma estoque / soma média de venda (antes: 200 menores
        #     linhas DT x SKU, quase todas 0, e o front pegava a primeira por SKU -> tudo zerado)
        q_stock = f"""
            WITH latest_stock AS (
                SELECT 
                    f.CNPJ_DISTRIBUIDOR,
                    COALESCE(NULLIF(TRIM(f.DESC_DISTRIBUIDOR_DNA), ''), f.DESC_DISTRIBUIDOR, 'Distribuidor') as desc_distribuidor,
                    f.SKU_PROD_BQ,
                    COALESCE(f.DESC_PROD_BQ, f.DESC_PROD_ARQUIVO_DIST, 'Produto') as desc_prod,
                    f.DATA_ESTOQUE,
                    COALESCE(f.QTDE_ESTOQUE, 0) as QTDE_ESTOQUE,
                    COALESCE(f.MEDIA_VENDA, 0)  as MEDIA_VENDA,
                    ROW_NUMBER() OVER (
                        PARTITION BY f.CNPJ_DISTRIBUIDOR, f.SKU_PROD_BQ
                        ORDER BY f.DATA_ESTOQUE DESC
                    ) as rn
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_stock f
                {w_stock} AND f.SKU_PROD_BQ IS NOT NULL
            ),
            sold_3m AS (
                SELECT DISTINCT s.CNPJ_DISTRIBUIDOR, s.SKU_PROD_BQ
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout s
                WHERE s.DATA_SELL_OUT >= add_months(current_date(), -3)
                  AND s.DATA_SELL_OUT <= current_date()
                  AND s.SKU_PROD_BQ IS NOT NULL AND s.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO')
                  AND (COALESCE(s.VL_SELL_OUT, 0) > 0 OR COALESCE(s.QTDE_DUZIA_SELL_OUT, 0) > 0)
            ),
            cur AS (
                SELECT l.* FROM latest_stock l
                JOIN sold_3m s ON s.CNPJ_DISTRIBUIDOR = l.CNPJ_DISTRIBUIDOR AND s.SKU_PROD_BQ = l.SKU_PROD_BQ
                WHERE l.rn = 1
            )
            SELECT 
                MAX(DATA_ESTOQUE) as DATA_ESTOQUE,
                CASE WHEN SUM(MEDIA_VENDA) > 0 THEN CAST(FLOOR(SUM(QTDE_ESTOQUE) / SUM(MEDIA_VENDA)) AS INT) ELSE 0 END as dias_estoque,
                CASE WHEN COUNT(DISTINCT CNPJ_DISTRIBUIDOR) = 1 THEN MAX(desc_distribuidor)
                     ELSE CONCAT(CAST(COUNT(DISTINCT CNPJ_DISTRIBUIDOR) AS STRING), ' distribuidores') END as desc_distribuidor,
                COUNT(DISTINCT CNPJ_DISTRIBUIDOR) as qtd_distribuidores,
                'SP' as uf_cliente,
                SKU_PROD_BQ as sku_prod_dist,
                MAX(desc_prod) as DESC_PROD_ARQUIVO_DIST,
                CASE WHEN SUM(MEDIA_VENDA) > 0 THEN SUM(QTDE_ESTOQUE) / SUM(MEDIA_VENDA) ELSE 0 END as giro_estoque,
                SUM(MEDIA_VENDA) as media_venda,
                SUM(QTDE_ESTOQUE) as total_qty_stock,
                MONTH(MAX(DATA_ESTOQUE)) as MES,
                YEAR(MAX(DATA_ESTOQUE)) as ANO
            FROM cur
            GROUP BY SKU_PROD_BQ
            ORDER BY dias_estoque ASC
            LIMIT 1000
        """

        w_pos_meta = f"{w_positiv} AND (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)" if w_positiv else "WHERE (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)"
        q_positiv = f"""
            SELECT 
                CASE 
                    WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%BRIOCHE%' THEN 'Linha Gourmet & Brioche'
                    WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%HB%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%HAMB%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%TRADICIONAL%' THEN 'Pães de Hambúrguer Tradicionais'
                    WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%HOT DOG%' THEN 'Pães de Hot Dog'
                    WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%AUSTRALIANO%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%ARTESANO%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%NUVEM%' THEN 'Pães Especiais & Artesanais'
                    WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%ANA MARIA%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%BOLO%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%BISNAG%' THEN 'Bolos, Snacks & Doces'
                    ELSE 'Outros Produtos'
                END as grupo_produto_desc_bq,
                COALESCE(f.DESC_CLIENTE, NULLIF(TRIM(f.DESC_DISTRIBUIDOR_DNA), ''), f.DESC_DISTRIBUIDOR, 'Cliente') as razao_social_cliente,
                COALESCE(f.CNPJ_CLIENTE, f.CNPJ_DISTRIBUIDOR) as cnpj_cliente,
                COUNT(DISTINCT f.DATA_SELL_OUT) as compras_mes_atual,
                COUNT(DISTINCT f.DATA_SELL_OUT) as total_compras_periodo,
                SUM(COALESCE(f.QTDE_DUZIA_SELL_OUT, 0)) as volume_duzia,
                SUM(COALESCE(f.VL_SELL_OUT, 0)) as valor_total,
                'POSITIVADO' as status,
                TRUE as isPositivado
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
            {w_pos_meta}
            GROUP BY 1, 2, 3
            ORDER BY grupo_produto_desc_bq, volume_duzia DESC
            LIMIT 500
        """

        if order_nf_col_available():
            grid_value_expr = ("SUM(CASE WHEN f.ID_STATUS_PEDIDO IN (1, 2) AND f.VL_FATURADO_LIQUIDO_NF IS NOT NULL "
                               "THEN f.VL_FATURADO_LIQUIDO_NF ELSE COALESCE(f.VL_PEDIDO_TOTAL_LIQUIDO, f.VL_PEDIDO_LIQUIDO, 0) END)")
        else:
            grid_value_expr = "SUM(COALESCE(f.VL_PEDIDO_TOTAL_LIQUIDO, f.VL_PEDIDO_LIQUIDO, 0))"

        q_orders = f"""
            SELECT 
                CAST(f.NUMERO_PEDIDO as STRING)                      as numero_pedido,
                f.DATA_EMISSAO_PEDIDO                                as data_emissao_pedido,
                f.DATA_PREVISAO_ENTREGA                             as data_previsao_entrega,
                f.DATA_ENTREGA                                      as data_entrega,
                COALESCE(f.DESC_STATUS_PEDIDO, 'ENTREGUE')           as desc_status_pedido,
                f.SKU_PROD_BQ                                        as sku,
                COALESCE(f.DESC_PROD_BQ, 'Produto')                  as produto,
                SUM(COALESCE(f.QTDE_PEDIDO_UN, 0))                   as qtde_pedido_un,
                SUM(COALESCE(f.QTDE_PEDIDO_ATENDIDO_UN, 0))          as qtde_pedido_atendido_un,
                SUM(COALESCE(f.QTDE_PEDIDO_CX, 0))                   as qtde_pedido_cx,
                SUM(COALESCE(f.QTDE_PEDIDO_ATENDIDO_CX, 0))          as qtde_pedido_atendido_cx,
                SUM(COALESCE(f.VL_PEDIDO_BRUTO, 0))                  as vl_pedido_bruto,
                SUM(COALESCE(f.VL_PEDIDO_ATENDIDO_BRUTO, 0))         as vl_pedido_atendido_bruto,
                SUM(COALESCE(f.VL_PEDIDO_LIQUIDO, f.VL_PEDIDO_BRUTO * 0.8, 0)) as vl_pedido_liquido,
                SUM(COALESCE(f.VL_PEDIDO_ATENDIDO_LIQUIDO, f.VL_PEDIDO_ATENDIDO_BRUTO * 0.8, 0)) as vl_pedido_atendido_liquido,
                SUM(COALESCE(f.VL_PEDIDO_ABERTO_LIQUIDO, f.VL_PEDIDO_ABERTO_BRUTO * 0.8, 0)) as vl_pedido_aberto_liquido,
                -- Valor exibido na Grade de Pedidos:
                --   faturados (1, 2) com nota: líquido real da NF (= Power BI, SUM(VL_CYW_LIQ_VENDIDO))
                --   demais: total líquido estimado (bruto - ICMS - PIS/COFINS)
                {grid_value_expr} as vl_pedido_total_liquido
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_order f
            {w_orders}
            GROUP BY
                f.NUMERO_PEDIDO, f.DATA_EMISSAO_PEDIDO, f.DATA_PREVISAO_ENTREGA, f.DATA_ENTREGA,
                f.DESC_STATUS_PEDIDO, f.SKU_PROD_BQ, f.DESC_PROD_BQ
            ORDER BY f.DATA_PREVISAO_ENTREGA DESC, f.DATA_EMISSAO_PEDIDO DESC
            LIMIT 1000
        """

        # Métricas Consolidadas de Pedidos: Faturado (Invoiced Líquido), Em Aberto (Open Order Líquido) e Total Líquido
        # Equalização Líquida com Sell-In: utiliza valores líquidos com deduções fiscais aplicadas
        q_order_metrics = f"""
            SELECT 
                SUM(COALESCE(f.VL_PEDIDO_ATENDIDO_LIQUIDO, f.VL_PEDIDO_ATENDIDO_BRUTO * 0.8, 0)) as total_vl_invoiced,
                SUM(COALESCE(f.VL_PEDIDO_ABERTO_LIQUIDO, f.VL_PEDIDO_ABERTO_BRUTO * 0.8, 0))       as total_vl_open,
                SUM(COALESCE(f.VL_PEDIDO_ATENDIDO_LIQUIDO, f.VL_PEDIDO_ATENDIDO_BRUTO * 0.8, 0) + 
                    COALESCE(f.VL_PEDIDO_ABERTO_LIQUIDO, f.VL_PEDIDO_ABERTO_BRUTO * 0.8, 0))       as total_vl_total,
                SUM(COALESCE(f.VL_PEDIDO_ATENDIDO_BRUTO, 0))                                     as total_vl_invoiced_bruto,
                SUM(COALESCE(f.VL_PEDIDO_ABERTO_BRUTO, 0))                                       as total_vl_open_bruto,
                SUM(COALESCE(f.VL_PEDIDO_BRUTO, 0))                                              as total_vl_total_bruto,
                SUM(COALESCE(f.QTDE_PEDIDO_ATENDIDO_DZ, 0))                                      as total_qty_invoiced_dz,
                SUM(COALESCE(f.QTDE_PEDIDO_ABERTO_DZ, 0))                                        as total_qty_open_dz,
                SUM(COALESCE(f.QTDE_PEDIDO_DZ, 0))                                               as total_qty_total_dz,
                SUM(COALESCE(f.QTDE_PEDIDO_ATENDIDO_UN, 0))                                      as total_qty_invoiced_un,
                SUM(COALESCE(f.QTDE_PEDIDO_ABERTO_UN, 0))                                        as total_qty_open_un,
                SUM(COALESCE(f.QTDE_PEDIDO_UN, 0))                                               as total_qty_total_un
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_order f
            {w_orders}
        """

        # Carteira em aberto do card (regra DNA de Vendas): mês = GREATEST(entrega prevista, hoje).
        # A aba Pedidos continua com a regra atual (data de entrega prevista).
        q_order_open = f"""
            SELECT
                SUM(COALESCE(f.VL_PEDIDO_ABERTO_LIQUIDO, f.VL_PEDIDO_ABERTO_BRUTO * 0.8, 0)) as total_vl_open,
                SUM(COALESCE(f.VL_PEDIDO_ABERTO_BRUTO, 0))                                 as total_vl_open_bruto,
                SUM(COALESCE(f.QTDE_PEDIDO_ABERTO_DZ, 0))                                  as total_qty_open_dz,
                SUM(COALESCE(f.QTDE_PEDIDO_ABERTO_UN, 0))                                  as total_qty_open_un
            FROM (
                SELECT o.*, GREATEST(COALESCE(o.DATA_PREVISAO_ENTREGA, current_date()), current_date()) as DT_CARTEIRA
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_order o
                WHERE COALESCE(o.ID_STATUS_PEDIDO, 0) NOT IN (1, 2)
            ) f
            {w_orders_cart}
        """

        # Ano anterior (YoY): meses completos; mês corrente comparado pelos mesmos N dias úteis transcorridos.
        p_si_py['sipy_cutoff'] = py_biz_cutoff_dt
        p_so_py['sopy_cutoff'] = py_biz_cutoff_dt
        si_py_cutoff = f"""(YEAR(f.DT_SELL_IN) <> {py_cur_year - 1}
               OR MONTH(f.DT_SELL_IN) <> {py_cur_month}
               OR f.DT_SELL_IN <= CAST(:sipy_cutoff AS DATE))"""
        q_sellin_py = f"""
            WITH semantica AS (
                SELECT MONTH(f.DT_SELL_IN) AS MES, YEAR(f.DT_SELL_IN) AS ANO,
                       SUM(f.QTDE_SELL_IN) AS total_qty_sell_in
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellin f
                {w_si_py} {'AND' if w_si_py else 'WHERE'} {si_py_cutoff}
                GROUP BY MONTH(f.DT_SELL_IN), YEAR(f.DT_SELL_IN)
            ), invoiced AS (
                SELECT MONTH(f.DT_SELL_IN) AS MES, YEAR(f.DT_SELL_IN) AS ANO,
                       SUM(f.VL_CYW_LIQ_VENDIDO) AS total_vl_sell_in
                FROM (SELECT c.*, c.SKU_DIST AS SKU_PROD_DIST FROM {CATALOG}.opebrapodis_cz.sellin c) f
                {w_si_py} {'AND' if w_si_py else 'WHERE'} {si_py_cutoff} AND f.CNPJ_BIMBO <> 0
                GROUP BY MONTH(f.DT_SELL_IN), YEAR(f.DT_SELL_IN)
            )
            SELECT COALESCE(s.ANO, i.ANO) AS ANO, COALESCE(s.MES, i.MES) AS MES,
                   COALESCE(i.total_vl_sell_in, 0) AS total_vl_sell_in,
                   COALESCE(s.total_qty_sell_in, 0) AS total_qty_sell_in
            FROM semantica s FULL OUTER JOIN invoiced i ON s.ANO = i.ANO AND s.MES = i.MES
        """
        so_py_cutoff = f"""(YEAR(f.DATA_SELL_OUT) <> {py_cur_year - 1}
               OR MONTH(f.DATA_SELL_OUT) <> {py_cur_month}
               OR f.DATA_SELL_OUT <= CAST(:sopy_cutoff AS DATE))"""
        q_sellout_py = f"""
            SELECT SUM(f.VL_SELL_OUT) as total_vl_sell_out, SUM(f.QTDE_DUZIA_SELL_OUT) as total_qty_dz_sell_out,
                   MONTH(f.DATA_SELL_OUT) as MES, YEAR(f.DATA_SELL_OUT) as ANO
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
            {w_so_py} {'AND' if w_so_py else 'WHERE'}
              {so_py_cutoff}
              AND (f.SKU_PROD_BQ != 'META' OR f.SKU_PROD_BQ IS NULL)
            GROUP BY MONTH(f.DATA_SELL_OUT), YEAR(f.DATA_SELL_OUT)
        """

        _seg_expr = """CASE
            WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%BRIOCHE%'
              OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%AUSTRALIANO%'
              OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%ARTESANO%'
              OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%NUVEM%' THEN 'Brioche & Gourmet'
            WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%HB%'
              OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%HAMB%'
              OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%TRADICIONAL%' THEN 'Hambúrguer Tradicional'
            WHEN UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%HOT DOG%'
              OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%HOTDOG%' THEN 'Hot Dog'
            ELSE 'Especiais & Doces'
        END"""
        w_mix_cur_sql = f"{w_mix_cur} {'AND' if w_mix_cur else 'WHERE'} (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)"
        if py_years:
            p_mix_merged = {**p_mix_cur, **p_mix_py, 'mxp_cutoff': py_biz_cutoff_dt}
            w_mix_py_sql = f"""{w_mix_py} {'AND' if w_mix_py else 'WHERE'} (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)
              AND (YEAR(f.DATA_SELL_OUT) <> {py_cur_year - 1} OR MONTH(f.DATA_SELL_OUT) <> {py_cur_month} OR f.DATA_SELL_OUT <= CAST(:mxp_cutoff AS DATE))"""
            q_mix = f"""
                WITH mix_cur AS (
                    SELECT {_seg_expr} AS segmento,
                           SUM(COALESCE(f.VL_SELL_OUT, 0)) AS vl_atual,
                           SUM(COALESCE(f.QTDE_DUZIA_SELL_OUT, 0)) AS dz_atual
                    FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
                    {w_mix_cur_sql}
                    GROUP BY {_seg_expr}
                ),
                mix_py AS (
                    SELECT {_seg_expr} AS segmento,
                           SUM(COALESCE(f.VL_SELL_OUT, 0)) AS vl_py,
                           SUM(COALESCE(f.QTDE_DUZIA_SELL_OUT, 0)) AS dz_py
                    FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
                    {w_mix_py_sql}
                    GROUP BY {_seg_expr}
                )
                SELECT COALESCE(c.segmento, p.segmento) AS segmento,
                       COALESCE(c.vl_atual, 0) AS vl_atual,
                       COALESCE(c.dz_atual, 0) AS dz_atual,
                       COALESCE(p.vl_py, 0) AS vl_py,
                       COALESCE(p.dz_py, 0) AS dz_py
                FROM mix_cur c FULL OUTER JOIN mix_py p ON c.segmento = p.segmento
                ORDER BY COALESCE(c.vl_atual, 0) DESC
            """
        else:
            p_mix_merged = p_mix_cur
            q_mix = f"""
                SELECT {_seg_expr} AS segmento,
                       SUM(COALESCE(f.VL_SELL_OUT, 0)) AS vl_atual,
                       SUM(COALESCE(f.QTDE_DUZIA_SELL_OUT, 0)) AS dz_atual,
                       0 AS vl_py,
                       0 AS dz_py
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
                {w_mix_cur_sql}
                GROUP BY {_seg_expr}
                ORDER BY vl_atual DESC
            """

        w_rx_base = f"{w_rx} {'AND' if w_rx else 'WHERE'} f.CNPJ_CLIENTE IS NOT NULL AND (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)"
        q_reactivate = f"""
            WITH cur_cli AS (
                SELECT DISTINCT REGEXP_REPLACE(CAST(f.CNPJ_CLIENTE AS STRING), '[^0-9]', '') AS cnpj_norm
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
                {w_rx_base}
                  AND f.DATA_SELL_OUT >= CAST(:rx_m_ini AS DATE)
                  AND f.DATA_SELL_OUT <= last_day(CAST(:rx_m_ini AS DATE))
                  AND (COALESCE(f.VL_SELL_OUT, 0) > 0 OR COALESCE(f.QTDE_DUZIA_SELL_OUT, 0) > 0)
            ),
            hist_90 AS (
                SELECT
                    REGEXP_REPLACE(CAST(f.CNPJ_CLIENTE AS STRING), '[^0-9]', '') AS cnpj_norm,
                    MAX(CAST(f.CNPJ_CLIENTE AS STRING)) AS cnpj_cliente,
                    MAX(COALESCE(NULLIF(TRIM(f.DESC_CLIENTE), ''), 'Cliente')) AS cliente,
                    REGEXP_REPLACE(MAX(CAST(f.CNPJ_DISTRIBUIDOR AS STRING)), '[^0-9]', '') AS dt_norm,
                    SUM(COALESCE(f.VL_SELL_OUT, 0)) AS vl_90d,
                    SUM(COALESCE(f.QTDE_DUZIA_SELL_OUT, 0)) AS dz_90d,
                    CAST(MAX(f.DATA_SELL_OUT) AS STRING) AS ultima_compra,
                    MAX({_seg_expr}) AS principal_categoria
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
                {w_rx_base}
                  AND f.DATA_SELL_OUT >= add_months(CAST(:rx_m_ini AS DATE), -3)
                  AND f.DATA_SELL_OUT < CAST(:rx_m_ini AS DATE)
                  AND (COALESCE(f.VL_SELL_OUT, 0) > 0 OR COALESCE(f.QTDE_DUZIA_SELL_OUT, 0) > 0)
                GROUP BY REGEXP_REPLACE(CAST(f.CNPJ_CLIENTE AS STRING), '[^0-9]', '')
            ),
            geo AS (
                SELECT
                    REGEXP_REPLACE(CAST(CNPJ_CLIENTE AS STRING), '[^0-9]', '') AS cnpj_norm,
                    MAX(COALESCE(NULLIF(TRIM(MUNICIPIO), ''), '')) AS municipio,
                    MAX(COALESCE(NULLIF(TRIM(BAIRRO), ''), '')) AS bairro,
                    MAX(COALESCE(NULLIF(TRIM(UF), ''), '')) AS uf
                FROM {CATALOG}.opebrapodis_cz.dim_clientes_distribuidores
                WHERE CNPJ_CLIENTE IS NOT NULL
                GROUP BY REGEXP_REPLACE(CAST(CNPJ_CLIENTE AS STRING), '[^0-9]', '')
            )
            SELECT
                h.cnpj_cliente,
                h.cliente,
                COALESCE(NULLIF(g.municipio, ''), 'Não informado') AS municipio,
                COALESCE(NULLIF(g.bairro, ''), '-') AS bairro,
                COALESCE(g.uf, '') AS uf,
                h.principal_categoria,
                ROUND(h.vl_90d, 2) AS vl_90d,
                ROUND(h.vl_90d / 3.0, 2) AS media_mensal_90d,
                ROUND(h.dz_90d, 1) AS dz_90d,
                h.ultima_compra,
                DATEDIFF(LEAST(current_date(), last_day(CAST(:rx_m_ini AS DATE))), CAST(h.ultima_compra AS DATE)) AS dias_sem_compra
            FROM hist_90 h
            LEFT JOIN cur_cli c ON h.cnpj_norm = c.cnpj_norm
            LEFT JOIN geo g ON h.cnpj_norm = g.cnpj_norm
            WHERE c.cnpj_norm IS NULL AND h.vl_90d > 0
            ORDER BY h.vl_90d DESC
            LIMIT 200
        """

        # Tracking com vários DTs: base esperada = DTs com sell-out no mês exibido ou no anterior
        q_tracking_expected = f"""
            SELECT CAST(f.CNPJ_DISTRIBUIDOR AS STRING) as cnpj,
                   MAX(COALESCE(NULLIF(TRIM(f.DESC_DISTRIBUIDOR_DNA), ''), f.DESC_DISTRIBUIDOR, CAST(f.CNPJ_DISTRIBUIDOR AS STRING))) as nome
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
            {w_trk_exp} {'AND' if w_trk_exp else 'WHERE'} f.DATA_SELL_OUT BETWEEN add_months(CAST(:tx_ini AS DATE), -1) AND last_day(CAST(:tx_ini AS DATE))
              AND (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)
              AND (COALESCE(f.VL_SELL_OUT, 0) > 0 OR COALESCE(f.QTDE_DUZIA_SELL_OUT, 0) > 0)
            GROUP BY f.CNPJ_DISTRIBUIDOR
        """

        w_pm_realizado = f"{w_positiv_monthly} AND (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)" if w_positiv_monthly else "WHERE (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)"
        w_pm_meta = f"{w_positiv_monthly} AND (f.SKU_PROD_BQ = 'META_POSITIVACAO' OR (f.POSITIVACAO_META IS NOT NULL AND f.POSITIVACAO_META > 0))" if w_positiv_monthly else "WHERE (f.SKU_PROD_BQ = 'META_POSITIVACAO' OR (f.POSITIVACAO_META IS NOT NULL AND f.POSITIVACAO_META > 0))"

        q_positiv_monthly = f"""
            WITH base_ano AS (
                SELECT 
                    YEAR(f.DATA_SELL_OUT) as ANO,
                    COUNT(DISTINCT f.CNPJ_CLIENTE) as total_base_clientes
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
                {w_pm_realizado}
                GROUP BY YEAR(f.DATA_SELL_OUT)
            ),
            realizado_mes AS (
                SELECT
                    MONTH(f.DATA_SELL_OUT) as MES,
                    YEAR(f.DATA_SELL_OUT)  as ANO,
                    COUNT(DISTINCT f.CNPJ_CLIENTE) as clientes_positivados
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
                {w_pm_realizado}
                GROUP BY MONTH(f.DATA_SELL_OUT), YEAR(f.DATA_SELL_OUT)
            ),
            meta_mes AS (
                SELECT
                    MONTH(f.DATA_SELL_OUT) as MES,
                    YEAR(f.DATA_SELL_OUT)  as ANO,
                    CAST(COALESCE(SUM(f.POSITIVACAO_META), 0) AS INT) as meta_positivacao
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
                {w_pm_meta}
                GROUP BY MONTH(f.DATA_SELL_OUT), YEAR(f.DATA_SELL_OUT)
            )
            SELECT
                COALESCE(r.MES, m.MES) as MES,
                COALESCE(r.ANO, m.ANO) as ANO,
                COALESCE(r.clientes_positivados, 0) as clientes_positivados,
                COALESCE(m.meta_positivacao, 0)     as meta_positivacao,
                COALESCE(b.total_base_clientes, 0)  as total_base_clientes,
                ROUND((COALESCE(r.clientes_positivados, 0) * 100.0) / NULLIF(b.total_base_clientes, 0), 1) as pct_positivacao
            FROM realizado_mes r
            FULL OUTER JOIN meta_mes m ON r.ANO = m.ANO AND r.MES = m.MES
            LEFT JOIN base_ano b ON COALESCE(r.ANO, m.ANO) = b.ANO
            ORDER BY ANO, MES
        """

        w_tr_clause = f"{w_tracking} AND (f.SKU_PROD_BQ != 'META' OR f.SKU_PROD_BQ IS NULL)" if w_tracking else "WHERE (f.SKU_PROD_BQ != 'META' OR f.SKU_PROD_BQ IS NULL)"
        q_tracking = f"""
            SELECT 
                CAST(f.DATA_SELL_OUT as STRING) as data_sell_out,
                DAY(f.DATA_SELL_OUT)            as dia,
                MONTH(f.DATA_SELL_OUT)          as mes,
                YEAR(f.DATA_SELL_OUT)           as ano,
                COUNT(DISTINCT f.CNPJ_CLIENTE)  as total_clientes,
                SUM(COALESCE(f.VL_SELL_OUT, 0)) as total_vl_sell_out,
                SUM(COALESCE(f.QTDE_DUZIA_SELL_OUT, 0)) as total_qty_dz_sell_out,
                CONCAT_WS(',', COLLECT_SET(CASE WHEN COALESCE(f.VL_SELL_OUT, 0) > 0 OR COALESCE(f.QTDE_DUZIA_SELL_OUT, 0) > 0
                                                THEN CAST(f.CNPJ_DISTRIBUIDOR AS STRING) END)) as dists_envio
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
            {w_tr_clause}
            GROUP BY f.DATA_SELL_OUT
            ORDER BY f.DATA_SELL_OUT ASC
        """

        # Execução Paralela Concorrente de Todas as Queries via ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=14) as executor:
            f_sellin = executor.submit(execute_sql, q_sellin, p_sellin)
            f_sellout = executor.submit(execute_sql, q_sellout, p_sellout_merged)
            f_stock = executor.submit(execute_sql, q_stock, p_stock)
            f_positiv = executor.submit(execute_sql, q_positiv, p_positiv)
            f_orders = executor.submit(execute_sql, q_orders, p_orders)
            f_order_metrics = executor.submit(execute_sql, q_order_metrics, p_orders)
            f_positiv_monthly = executor.submit(execute_sql, q_positiv_monthly, p_positiv_monthly)
            f_tracking = executor.submit(execute_sql, q_tracking, p_tracking)
            f_order_open = executor.submit(execute_sql, q_order_open, p_orders_cart)
            f_mix = executor.submit(execute_sql, q_mix, p_mix_merged)
            f_reactivate = executor.submit(execute_sql, q_reactivate, p_rx)
            extra = [('order_open', f_order_open), ('mix', f_mix), ('reactivate', f_reactivate)]
            if py_years:
                extra.append(('sellin_py', executor.submit(execute_sql, q_sellin_py, p_si_py)))
                extra.append(('sellout_py', executor.submit(execute_sql, q_sellout_py, p_so_py)))
            if multi_dist:
                extra.append(('tracking_expected', executor.submit(execute_sql, q_tracking_expected, p_trk_exp)))

            for key, future in [('sellin', f_sellin), ('sellout', f_sellout), ('stock', f_stock), ('positiv', f_positiv), ('orders', f_orders), ('order_metrics', f_order_metrics), ('positiv_monthly', f_positiv_monthly), ('tracking', f_tracking)] + extra:
                try:
                    results[key] = future.result()
                except Exception as ex:
                    app.logger.error(f"[API KPI Query {key} Error] {ex}")
                    results[key] = []

    except Exception as e:
        app.logger.error(f"[API KPI Fail] {e}")
        error_msg = str(e)

    response_payload = {
        'usuario': email,
        'multi_dist': bool(multi_dist),
        'has_py': bool(py_years),
        'py_meta': {
            'cur_bdays': cur_bdays_yoy,
            'py_cutoff_dt': py_biz_cutoff_dt,
            'mode': 'business_days',
        },
        'dados': results,
        'error': error_msg
    }
    if not error_msg:
        set_in_cache(cache_key_kpi, response_payload)
    else:
        stale_kpi = get_stale_from_cache(cache_key_kpi)
        if stale_kpi is not None:
            return jsonify(stale_kpi)

    return jsonify(response_payload)

# ─── API GET /api/forecast ─────────────────────────────────────────────────────
@app.route('/api/forecast')
def api_forecast():
    email = get_authenticated_user()
    if not email:
        return jsonify({'error': 'Acesso Negado: Header x-forwarded-email ausente ou inválido'}), 403

    ctx = resolve_access(email)
    mapped_cnpjs, is_admin, scope_label = data_scope(ctx, request.args)

    if not mapped_cnpjs and not is_admin:
        if ctx.get('blocked_unvalidated'):
            return jsonify({
                'error': 'Portal indisponível para o seu distribuidor no momento (Sell-out em validação).',
                'blocked_unvalidated': True
            }), 403
        return jsonify({'error': f"Acesso Negado: Usuário '{email}' não possui nenhum distribuidor cadastrado no mapping"}), 403

    args = request.args
    cache_args = sorted((k, v) for k, v in args.items() if k not in ('dist', 'dist_id', 'perfil'))
    cache_key_fc = f"forecast_{email}_{scope_label}_{str(cache_args)}"
    cached_fc = get_from_cache(cache_key_fc, ttl_seconds=900)
    if cached_fc:
        return jsonify(cached_fc)

    try:
        payload = build_forecast_payload(
            execute_sql_fn=execute_sql,
            build_where_fn=build_where_table,
            catalog=CATALOG,
            schema=SCHEMA,
            mapped_cnpjs=mapped_cnpjs,
            args=args,
            is_admin=is_admin,
        )
        payload['usuario'] = email
        payload['scope_label'] = scope_label
        payload['error'] = None
        set_in_cache(cache_key_fc, payload)
        return jsonify(payload)
    except Exception as e:
        app.logger.error(f"[API Forecast Fail] {e}\n{traceback.format_exc()}")
        stale_fc = get_stale_from_cache(cache_key_fc)
        if stale_fc is not None:
            return jsonify(stale_fc)
        return jsonify({'error': str(e), 'usuario': email}), 500

# ─── API GET /api/executivo & /api/executivo/resumo-ia (Admin-Only) ────────────
def _parse_executivo_args():
    """Valida contexto Admin (sem simulação ativa) e extrai (ano, mes, categoria, today_dt)."""
    email = get_authenticated_user()
    if not email:
        return None, (jsonify({'error': 'Acesso Negado'}), 403)

    ctx = resolve_access(email)
    if not ctx.get('is_admin') or ctx.get('simulacao') or request.args.get('perfil') == 'distribuidor':
        return None, (jsonify({'error': 'Acesso restrito a administradores'}), 403)

    tz_br = timezone(timedelta(hours=-3))
    today_dt = datetime.now(tz_br).date()
    try:
        ano = int((request.args.get('ano') or '').split(',')[0].strip() or today_dt.year)
    except ValueError:
        ano = today_dt.year
    try:
        mes_raw = (request.args.get('mes') or '').strip()
        mes = int(mes_raw.split(',')[0].strip()) if mes_raw and mes_raw.isdigit() else today_dt.month
        if not 1 <= mes <= 12:
            mes = today_dt.month
    except ValueError:
        mes = today_dt.month
    categoria = (request.args.get('categoria') or '').strip()
    return (ano, mes, categoria, today_dt), None


def _compute_executivo_payload(ano, mes, categoria, today_dt):
    """Calcula ou recupera do cache o consolidado executivo do canal e retorna (payload, ref_dt, py_cutoff_dt)."""
    _, last_d = calendar.monthrange(ano, mes)
    is_cur_month = (ano == today_dt.year and mes == today_dt.month)
    ref_dt = today_dt if is_cur_month else date(ano, mes, last_d)
    py_ano = ano - 1
    _, py_last_d = calendar.monthrange(py_ano, mes)
    if is_cur_month:
        elapsed_bdays, py_cutoff_dt = _py_biz_day_cutoff(today_dt)
        if elapsed_bdays <= 0:
            elapsed_bdays = 1
        rem_bdays = max(0, sum(1 for d in range(1, last_d + 1) if date(ano, mes, d).weekday() < 6) - elapsed_bdays)
    elif date(ano, mes, last_d) < today_dt:
        elapsed_bdays = sum(1 for d in range(1, last_d + 1) if date(ano, mes, d).weekday() < 6)
        rem_bdays = 0
        py_cutoff_dt = f"{py_ano:04d}-{mes:02d}-{py_last_d:02d}"
    else:
        elapsed_bdays = 0
        rem_bdays = sum(1 for d in range(1, last_d + 1) if date(ano, mes, d).weekday() < 6)
        py_cutoff_dt = (date(py_ano, mes, 1) - timedelta(days=1)).isoformat()

    cache_key_ex = f"executivo_{ano}_{mes}_{categoria}"
    cached_ex = get_from_cache(cache_key_ex, ttl_seconds=900)
    if cached_ex:
        return cached_ex, ref_dt, py_cutoff_dt

    total_bdays = elapsed_bdays + rem_bdays
    args_exec = {'ano': str(ano), 'mes': str(mes)}
    if categoria:
        args_exec['categoria'] = categoria

    portal_active_ids = get_portal_dist_ids()
    active_ids_sql = ', '.join(str(int(x)) for x in portal_active_ids if str(x).isdigit())
    active_filter = f" AND CAST(f.ID_DISTRIBUIDOR AS INT) IN ({active_ids_sql})" if active_ids_sql else " AND 1=0"

    w_so, p_so = build_where_table('DATA_SELL_OUT', None, args_exec, has_orders=False, param_prefix='exso_', is_admin=True)
    w_si, p_si = build_where_table('DT_SELL_IN', None, args_exec, has_orders=False, param_prefix='exsi_', is_admin=True)
    w_oc, p_oc = build_where_table('DT_CARTEIRA', None, args_exec, has_orders=True, param_prefix='exoc_', is_admin=True)

    args_py_ex = dict(args_exec)
    args_py_ex['ano'] = str(py_ano)
    w_so_py, p_so_py = build_where_table('DATA_SELL_OUT', None, args_py_ex, has_orders=False, param_prefix='expy_', is_admin=True)
    p_so_py['expy_cut'] = py_cutoff_dt

    q_ex_so = f"""
        SELECT
            CAST(f.ID_DISTRIBUIDOR AS INT) AS dist_id,
            MAX(COALESCE(NULLIF(TRIM(f.DESC_DISTRIBUIDOR_DNA), ''), f.DESC_DISTRIBUIDOR)) AS nome,
            MAX(LPAD(REGEXP_REPLACE(CAST(f.CNPJ_DISTRIBUIDOR AS STRING), '[^0-9]', ''), 14, '0')) AS cnpj,
            SUM(CASE WHEN f.SKU_PROD_BQ NOT IN ('META','META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL THEN COALESCE(f.VL_SELL_OUT, 0) ELSE 0 END) AS so_real_vl,
            SUM(CASE WHEN f.SKU_PROD_BQ NOT IN ('META','META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL THEN COALESCE(f.QTDE_DUZIA_SELL_OUT, 0) ELSE 0 END) AS so_real_dz,
            SUM(CASE WHEN (f.SKU_PROD_BQ = 'META' OR f.VL_SELL_OUT = 0) AND f.VL_META IS NOT NULL AND f.VL_META > 0 THEN COALESCE(f.VL_META, 0) ELSE 0 END) AS so_meta_vl,
            SUM(CASE WHEN (f.SKU_PROD_BQ NOT IN ('META','META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)
                      AND (UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%BRIOCHE%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%AUSTRALIANO%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%ARTESANO%' OR UPPER(COALESCE(f.DESC_PROD_BQ, '')) LIKE '%NUVEM%')
                     THEN COALESCE(f.VL_SELL_OUT, 0) ELSE 0 END) AS so_brioche_vl,
            CAST(MAX(CASE WHEN (f.SKU_PROD_BQ NOT IN ('META','META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL) AND COALESCE(f.VL_SELL_OUT, 0) > 0 THEN f.DATA_SELL_OUT END) AS STRING) AS ultimo_envio,
            COUNT(DISTINCT CASE WHEN (f.SKU_PROD_BQ NOT IN ('META','META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL) AND COALESCE(f.VL_SELL_OUT, 0) > 0 THEN f.DATA_SELL_OUT END) AS dias_ativos
        FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
        {w_so} {active_filter}
        GROUP BY CAST(f.ID_DISTRIBUIDOR AS INT)
    """
    q_ex_so_py = f"""
        SELECT
            CAST(f.ID_DISTRIBUIDOR AS INT) AS dist_id,
            SUM(COALESCE(f.VL_SELL_OUT, 0)) AS so_py_vl,
            SUM(COALESCE(f.QTDE_DUZIA_SELL_OUT, 0)) AS so_py_dz
        FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout f
        {w_so_py} {'AND' if w_so_py else 'WHERE'} f.DATA_SELL_OUT <= CAST(:expy_cut AS DATE) {active_filter}
          AND (f.SKU_PROD_BQ NOT IN ('META','META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)
        GROUP BY CAST(f.ID_DISTRIBUIDOR AS INT)
    """
    q_ex_si = f"""
        WITH sem AS (
            SELECT CAST(f.ID_DISTRIBUIDOR AS INT) AS dist_id,
                   SUM(COALESCE(f.VL_FORECAST, 0)) AS si_fcst_vl,
                   SUM(COALESCE(f.QTDE_SELL_IN, 0)) AS si_real_dz,
                   SUM(COALESCE(f.QTDE_FORECAST, 0)) AS si_fcst_dz
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellin f
            {w_si} {active_filter}
            GROUP BY CAST(f.ID_DISTRIBUIDOR AS INT)
        ), inv AS (
            SELECT CAST(f.ID_DISTRIBUIDOR AS INT) AS dist_id,
                   SUM(COALESCE(f.VL_CYW_LIQ_VENDIDO, 0)) AS si_real_vl
            FROM (SELECT c.*, c.SKU_DIST AS SKU_PROD_DIST FROM {CATALOG}.opebrapodis_cz.sellin c) f
            {w_si} {'AND' if w_si else 'WHERE'} f.CNPJ_BIMBO <> 0 {active_filter}
            GROUP BY CAST(f.ID_DISTRIBUIDOR AS INT)
        )
        SELECT COALESCE(s.dist_id, i.dist_id) AS dist_id,
               COALESCE(i.si_real_vl, 0) AS si_real_vl,
               COALESCE(s.si_fcst_vl, 0) AS si_fcst_vl,
               COALESCE(s.si_real_dz, 0) AS si_real_dz,
               COALESCE(s.si_fcst_dz, 0) AS si_fcst_dz
        FROM sem s FULL OUTER JOIN inv i ON s.dist_id = i.dist_id
    """
    q_ex_ord = f"""
        SELECT CAST(f.ID_DISTRIBUIDOR AS INT) AS dist_id,
               SUM(COALESCE(f.VL_PEDIDO_ABERTO_LIQUIDO, f.VL_PEDIDO_ABERTO_BRUTO * 0.8, 0)) AS carteira_vl,
               SUM(COALESCE(f.QTDE_PEDIDO_ABERTO_DZ, 0)) AS carteira_dz
        FROM (
            SELECT o.*, GREATEST(COALESCE(o.DATA_PREVISAO_ENTREGA, current_date()), current_date()) AS DT_CARTEIRA
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_order o
            WHERE COALESCE(o.ID_STATUS_PEDIDO, 0) NOT IN (1, 2)
        ) f
        {w_oc} {active_filter}
        GROUP BY CAST(f.ID_DISTRIBUIDOR AS INT)
    """
    q_ex_st = f"""
        WITH latest AS (
            SELECT CAST(f.ID_DISTRIBUIDOR AS INT) AS dist_id,
                   f.SKU_PROD_BQ,
                   COALESCE(f.QTDE_ESTOQUE, 0) AS qtde_estoque,
                   COALESCE(f.MEDIA_VENDA, 0) AS media_venda,
                   ROW_NUMBER() OVER (PARTITION BY f.ID_DISTRIBUIDOR, f.SKU_PROD_BQ ORDER BY f.DATA_ESTOQUE DESC) AS rn
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_stock f
            WHERE f.DATA_ESTOQUE >= date_trunc('MM', current_date()) AND f.DATA_ESTOQUE <= current_date()
              AND f.SKU_PROD_BQ IS NOT NULL {active_filter}
        )
        SELECT dist_id,
               CASE WHEN SUM(media_venda) > 0
                    THEN CAST(ROUND(SUM(CASE WHEN media_venda > 0 THEN FLOOR(qtde_estoque / media_venda) * media_venda ELSE 0 END) / SUM(media_venda)) AS INT)
                    ELSE 0 END AS dias_estoque
        FROM latest WHERE rn = 1
        GROUP BY dist_id
    """

    try:
        with ThreadPoolExecutor(max_workers=6) as ex:
            f_so = ex.submit(execute_sql, q_ex_so, p_so)
            f_py = ex.submit(execute_sql, q_ex_so_py, p_so_py)
            f_si = ex.submit(execute_sql, q_ex_si, p_si)
            f_ord = ex.submit(execute_sql, q_ex_ord, p_oc)
            f_st = ex.submit(execute_sql, q_ex_st)
            f_dists = ex.submit(get_portal_dists_rows)

            so_rows = f_so.result()
            py_rows = f_py.result()
            si_rows = f_si.result()
            ord_rows = f_ord.result()
            st_rows = f_st.result()
            portal_rows = f_dists.result()

        portal_active_map = {}
        for pr in (portal_rows or []):
            if pr.get('is_active') and str(pr.get('id') or '').isdigit():
                did_int = int(pr['id'])
                portal_active_map[did_int] = pr

        by_id = {}
        for did_int, pr in portal_active_map.items():
            by_id[did_int] = {
                'dist_id': did_int,
                'nome': str(pr.get('nome_referencia') or f'ID {did_int}').strip(),
                'cnpj': str(pr.get('cnpj_referencia') or '').strip(),
                'so_real_vl': 0.0, 'so_real_dz': 0.0, 'so_meta_vl': 0.0, 'so_brioche_vl': 0.0,
                'so_py_vl': 0.0, 'so_py_dz': 0.0,
                'si_real_vl': 0.0, 'si_fcst_vl': 0.0, 'si_real_dz': 0.0, 'si_fcst_dz': 0.0,
                'carteira_vl': 0.0, 'carteira_dz': 0.0,
                'dias_estoque': 0, 'ultimo_envio': None, 'dias_ativos': 0,
            }

        for r in so_rows:
            if r.get('dist_id') is None: continue
            try:
                did_int = int(r['dist_id'])
            except (ValueError, TypeError):
                continue
            if did_int not in by_id: continue
            d = by_id[did_int]
            if r.get('nome') and (not d['nome'] or d['nome'].startswith('ID ')):
                d['nome'] = str(r['nome']).strip()
            if r.get('cnpj') and not d['cnpj']:
                d['cnpj'] = str(r['cnpj']).strip()
            d['so_real_vl'] = float(r.get('so_real_vl') or 0)
            d['so_real_dz'] = float(r.get('so_real_dz') or 0)
            d['so_meta_vl'] = float(r.get('so_meta_vl') or 0)
            d['so_brioche_vl'] = float(r.get('so_brioche_vl') or 0)
            d['ultimo_envio'] = r.get('ultimo_envio')
            d['dias_ativos'] = int(r.get('dias_ativos') or 0)

        for r in py_rows:
            if r.get('dist_id') is None: continue
            try:
                did_int = int(r['dist_id'])
            except (ValueError, TypeError):
                continue
            if did_int not in by_id: continue
            d = by_id[did_int]
            d['so_py_vl'] = float(r.get('so_py_vl') or 0)
            d['so_py_dz'] = float(r.get('so_py_dz') or 0)

        for r in si_rows:
            if r.get('dist_id') is None: continue
            try:
                did_int = int(r['dist_id'])
            except (ValueError, TypeError):
                continue
            if did_int not in by_id: continue
            d = by_id[did_int]
            d['si_real_vl'] = float(r.get('si_real_vl') or 0)
            d['si_fcst_vl'] = float(r.get('si_fcst_vl') or 0)
            d['si_real_dz'] = float(r.get('si_real_dz') or 0)
            d['si_fcst_dz'] = float(r.get('si_fcst_dz') or 0)

        for r in ord_rows:
            if r.get('dist_id') is None: continue
            try:
                did_int = int(r['dist_id'])
            except (ValueError, TypeError):
                continue
            if did_int not in by_id: continue
            d = by_id[did_int]
            d['carteira_vl'] = float(r.get('carteira_vl') or 0)
            d['carteira_dz'] = float(r.get('carteira_dz') or 0)

        for r in st_rows:
            if r.get('dist_id') is None: continue
            try:
                did_int = int(r['dist_id'])
            except (ValueError, TypeError):
                continue
            if did_int in by_id:
                by_id[did_int]['dias_estoque'] = int(r.get('dias_estoque') or 0)

        items = []
        tot = {
            'so_real_vl': 0.0, 'so_proj_vl': 0.0, 'so_meta_vl': 0.0,
            'so_real_dz': 0.0, 'so_proj_dz': 0.0, 'so_py_vl': 0.0,
            'so_brioche_vl': 0.0, 'si_real_vl': 0.0, 'si_fcst_vl': 0.0,
            'si_real_dz': 0.0, 'si_fcst_dz': 0.0, 'carteira_vl': 0.0, 'carteira_dz': 0.0,
        }
        sem_envio_cnt = 0
        for d in by_id.values():
            if (d['so_real_vl'] + d['so_meta_vl'] + d['si_real_vl'] + d['si_fcst_vl'] + d['carteira_vl']) <= 0:
                continue
            rate_vl = (d['so_real_vl'] / elapsed_bdays) if elapsed_bdays > 0 else 0.0
            rate_dz = (d['so_real_dz'] / elapsed_bdays) if elapsed_bdays > 0 else 0.0
            so_proj_vl = round(d['so_real_vl'] + rate_vl * rem_bdays, 2) if is_cur_month else round(d['so_real_vl'], 2)
            so_proj_dz = round(d['so_real_dz'] + rate_dz * rem_bdays, 1) if is_cur_month else round(d['so_real_dz'], 1)
            att_proj = round((so_proj_vl / d['so_meta_vl']) * 100, 1) if d['so_meta_vl'] > 0 else None
            yoy_pct = round(((d['so_real_vl'] - d['so_py_vl']) / d['so_py_vl']) * 100, 1) if d['so_py_vl'] > 0 else None
            preco_dz = round(d['so_real_vl'] / d['so_real_dz'], 2) if d['so_real_dz'] > 0 else None
            mix_brioche = round((d['so_brioche_vl'] / d['so_real_vl']) * 100, 1) if d['so_real_vl'] > 0 else 0.0

            atraso_dias = None
            if d['ultimo_envio'] and is_cur_month:
                try:
                    u_dt = datetime.strptime(d['ultimo_envio'][:10], '%Y-%m-%d').date()
                    atraso_dias = (today_dt - u_dt).days
                except Exception:
                    atraso_dias = None
            if is_cur_month and (d['so_real_vl'] <= 0 or (atraso_dias is not None and atraso_dias > 3)):
                sem_envio_cnt += 1

            d.update({
                'so_proj_vl': so_proj_vl,
                'so_proj_dz': so_proj_dz,
                'ating_proj_pct': att_proj,
                'yoy_pct': yoy_pct,
                'preco_medio_dz': preco_dz,
                'mix_brioche_pct': mix_brioche,
                'atraso_envio_dias': atraso_dias,
            })
            items.append(d)
            for k in ('so_real_vl', 'so_meta_vl', 'so_real_dz', 'so_py_vl', 'so_brioche_vl', 'si_real_vl', 'si_fcst_vl', 'si_real_dz', 'si_fcst_dz', 'carteira_vl', 'carteira_dz'):
                tot[k] += d[k]
            tot['so_proj_vl'] += so_proj_vl
            tot['so_proj_dz'] += so_proj_dz

        items.sort(key=lambda x: x['so_real_vl'], reverse=True)
        tot['ating_proj_pct'] = round((tot['so_proj_vl'] / tot['so_meta_vl']) * 100, 1) if tot['so_meta_vl'] > 0 else None
        tot['yoy_pct'] = round(((tot['so_real_vl'] - tot['so_py_vl']) / tot['so_py_vl']) * 100, 1) if tot['so_py_vl'] > 0 else None
        tot['preco_medio_dz'] = round(tot['so_real_vl'] / tot['so_real_dz'], 2) if tot['so_real_dz'] > 0 else None
        tot['mix_brioche_pct'] = round((tot['so_brioche_vl'] / tot['so_real_vl']) * 100, 1) if tot['so_real_vl'] > 0 else 0.0
        tot['total_dists'] = len(items)
        tot['sem_envio_recente'] = sem_envio_cnt

        payload = {
            'ano': ano,
            'mes': mes,
            'py_meta': {'cur_bdays': elapsed_bdays, 'py_cutoff_dt': py_cutoff_dt, 'total_bdays': total_bdays},
            'consolidado': tot,
            'distribuidores': items,
        }
        set_in_cache(cache_key_ex, payload)
        return payload, ref_dt, py_cutoff_dt
    except Exception:
        raise


@app.route('/api/executivo')
def api_executivo():
    parsed, err = _parse_executivo_args()
    if err:
        return err
    ano, mes, categoria, today_dt = parsed
    try:
        payload, _, _ = _compute_executivo_payload(ano, mes, categoria, today_dt)
        return jsonify(payload)
    except Exception as e:
        app.logger.error(f"[API Executivo Fail] {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/executivo/resumo-ia')
def api_executivo_resumo_ia():
    parsed, err = _parse_executivo_args()
    if err:
        return err
    ano, mes, categoria, today_dt = parsed
    modo = request.args.get('modo', 'mensal')
    force = str(request.args.get('force', '')).lower() in ('1', 'true', 'yes')
    use_llm = str(request.args.get('llm', '')).lower() in ('1', 'true', 'yes')
    try:
        exec_payload, ref_dt, py_cutoff_dt = _compute_executivo_payload(ano, mes, categoria, today_dt)
        brief = build_executivo_brief(
            execute_sql=execute_sql,
            get_ws_client=get_workspace_client,
            catalog=CATALOG,
            schema=SCHEMA,
            exec_payload=exec_payload,
            ref_dt=ref_dt,
            py_cutoff_dt=py_cutoff_dt,
            modo=modo,
            categoria=categoria,
            force=force,
            use_llm=use_llm,
        )
        return jsonify(brief)
    except Exception as e:
        app.logger.error(f"[API Executivo Resumo IA Fail] {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

# ─── API GET /api/filtros (com Cache TTL & Execução Paralela) ───────────────────
_FILTROS_GLOBAL_LOCK = threading.Lock()

def _get_filtros_global_catalog():
    cached = get_from_cache('filtros_global_catalog', ttl_seconds=1800)
    if cached is not None:
        return cached
    stale = get_stale_from_cache('filtros_global_catalog')
    if stale is not None and not _FILTROS_GLOBAL_LOCK.acquire(blocking=False):
        return stale
    def _load():
        q_prods = f"""
            SELECT DISTINCT desc_produto FROM (
                SELECT DISTINCT DESC_PROD_BQ as desc_produto FROM {CATALOG}.{SCHEMA}.tbl_factdy_order WHERE DESC_PROD_BQ IS NOT NULL AND TRIM(DESC_PROD_BQ) != ''
                UNION
                SELECT DISTINCT DESC_PROD_BQ as desc_produto FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout WHERE DESC_PROD_BQ IS NOT NULL AND TRIM(DESC_PROD_BQ) != '' AND SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO')
                UNION
                SELECT DISTINCT DESC_PROD_BQ as desc_produto FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellin WHERE DESC_PROD_BQ IS NOT NULL AND TRIM(DESC_PROD_BQ) != ''
            ) ORDER BY desc_produto LIMIT 1000
        """
        q_skus = f"SELECT DISTINCT SKU_DISTRIB as sku FROM {CATALOG}.bracatlg_lz.produtos_distribuidores WHERE SKU_DISTRIB IS NOT NULL AND TRIM(SKU_DISTRIB) != '' ORDER BY sku LIMIT 1000"
        q_grupos = f"""
            SELECT DISTINCT
                COALESCE(NULLIF(dp.GRUPO_PRODUTO_DESC_BQ, '0'), f.DESC_PROD_BQ) as grupo,
                f.DESC_PROD_BQ as produto
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_order f
            LEFT JOIN {CATALOG}.opebrapodis_cz.dim_produtos dp
                ON TRIM(f.DESC_PROD_BQ) = TRIM(dp.DESCRICAO_PRODUTO)
            WHERE f.DESC_PROD_BQ IS NOT NULL AND TRIM(f.DESC_PROD_BQ) != ''
            ORDER BY grupo, produto
        """
        produtos, skus, categorias_map = [], [], {"Pães": [], "Especialidades": []}
        with ThreadPoolExecutor(max_workers=3) as executor:
            f_prods = executor.submit(execute_sql, q_prods)
            f_skus = executor.submit(execute_sql, q_skus)
            f_grupos = executor.submit(execute_sql, q_grupos)
            try:
                produtos = [str(r.get('desc_produto')) for r in f_prods.result() if r.get('desc_produto')]
            except Exception as ep:
                app.logger.warning(f"Aviso: consulta produtos filtros: {ep}")
            try:
                skus = [str(r.get('sku')) for r in f_skus.result() if r.get('sku')]
            except Exception as es:
                app.logger.warning(f"Aviso: consulta skus filtros: {es}")
            try:
                for r in f_grupos.result():
                    grupo = str(r.get('grupo', '')).strip()
                    produto = str(r.get('produto', '')).strip()
                    if not produto:
                        continue
                    if grupo == 'BUNS FOOD' or 'nuvem' in produto.lower() or 'brioche' in produto.lower():
                        if produto not in categorias_map["Pães"]:
                            categorias_map["Pães"].append(produto)
                    else:
                        if produto not in categorias_map["Especialidades"]:
                            categorias_map["Especialidades"].append(produto)
            except Exception as eg:
                app.logger.warning(f"Aviso: consulta categorias filtros: {eg}")
                categorias_map = {}

            if not categorias_map or not any(categorias_map.values()):
                categorias_map = {"Pães": [], "Especialidades": []}
                for p in produtos:
                    pl = p.lower()
                    if any(k in pl for k in ['pão', 'pao', 'brioche', 'hamb', 'hb', 'hot dog', 'hotdog', 'artesano', 'australiano', 'nuvem', 'buns', 'tradicional']):
                        categorias_map["Pães"].append(p)
                    else:
                        categorias_map["Especialidades"].append(p)
        res = (produtos, skus, categorias_map)
        set_in_cache('filtros_global_catalog', res)
        return res

    if stale is not None:
        def _bg():
            try:
                _load()
            finally:
                _FILTROS_GLOBAL_LOCK.release()
        threading.Thread(target=_bg, daemon=True).start()
        return stale

    with _FILTROS_GLOBAL_LOCK:
        cached = get_from_cache('filtros_global_catalog', ttl_seconds=1800)
        if cached is not None:
            return cached
        return _load()

@app.route('/api/filtros')
def api_filtros():
    email = get_authenticated_user()
    ctx = resolve_access(email) if email else {}
    mapped_cnpjs, is_admin, scope_label = data_scope(ctx, request.args)

    cache_key = f"filtros_metadata_{scope_label}"
    cached_data = get_from_cache(cache_key, ttl_seconds=900)
    if cached_data:
        return jsonify(cached_data)

    anos = ['2025', '2026']
    meses = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
    semanas = [str(i) for i in range(1, 53)]
    dias = [str(i).zfill(2) for i in range(1, 32)]
    produtos, skus, pedidos, categorias_map = [], [], [], {"Pães": [], "Especialidades": []}

    try:
        p_pedidos = {}
        group_ids = getattr(g, 'user_dist_ids', [])
        group_id = getattr(g, 'admin_dist_id', None)
        if group_ids and not is_admin:
            if all(str(v).strip().isdigit() for v in group_ids):
                int_ids = [str(int(str(v).strip())) for v in group_ids]
                id_cond = f"f.ID_DISTRIBUIDOR = {int_ids[0]}" if len(int_ids) == 1 else f"f.ID_DISTRIBUIDOR IN ({', '.join(int_ids)})"
                q_pedidos = f"SELECT DISTINCT CAST(f.NUMERO_PEDIDO AS STRING) AS numero_pedido FROM {CATALOG}.{SCHEMA}.tbl_factdy_order f WHERE f.NUMERO_PEDIDO IS NOT NULL AND {id_cond} ORDER BY numero_pedido DESC LIMIT 500"
            else:
                keys = []
                for i, value in enumerate(group_ids):
                    key = f'filter_user_id_{i}'
                    p_pedidos[key] = value
                    keys.append(':' + key)
                q_pedidos = f"SELECT DISTINCT CAST(f.NUMERO_PEDIDO AS STRING) AS numero_pedido FROM {CATALOG}.{SCHEMA}.tbl_factdy_order f WHERE f.NUMERO_PEDIDO IS NOT NULL AND CAST(f.ID_DISTRIBUIDOR AS STRING) IN ({', '.join(keys)}) ORDER BY numero_pedido DESC LIMIT 500"
        elif group_id and not is_admin:
            if str(group_id).strip().isdigit():
                q_pedidos = f"SELECT DISTINCT CAST(f.NUMERO_PEDIDO AS STRING) AS numero_pedido FROM {CATALOG}.{SCHEMA}.tbl_factdy_order f WHERE f.NUMERO_PEDIDO IS NOT NULL AND f.ID_DISTRIBUIDOR = {int(str(group_id).strip())} ORDER BY numero_pedido DESC LIMIT 500"
            else:
                q_pedidos = f"""
                    SELECT DISTINCT CAST(f.NUMERO_PEDIDO AS STRING) AS numero_pedido
                    FROM {CATALOG}.{SCHEMA}.tbl_factdy_order f
                    WHERE f.NUMERO_PEDIDO IS NOT NULL AND CAST(f.ID_DISTRIBUIDOR AS STRING) = :filter_dist_id
                    ORDER BY numero_pedido DESC LIMIT 500
                """
                p_pedidos['filter_dist_id'] = group_id
        elif mapped_cnpjs and not is_admin:
            clean_cnpjs = [f"'{str(c).strip().zfill(14)}'" for c in mapped_cnpjs if str(c).strip()]
            clean_cnpjs.extend([f"'{str(c).strip()}'" for c in mapped_cnpjs if str(c).strip()])
            cnpj_in = ", ".join(set(clean_cnpjs))
            q_pedidos = f"""
                SELECT DISTINCT CAST(f.NUMERO_PEDIDO as STRING) as numero_pedido 
                FROM {CATALOG}.{SCHEMA}.tbl_factdy_order f 
                WHERE f.NUMERO_PEDIDO IS NOT NULL 
                  AND (f.CNPJ_DISTRIBUIDOR IN ({cnpj_in}) OR CAST(TRY_CAST(f.CNPJ_DISTRIBUIDOR as BIGINT) as STRING) IN ({cnpj_in}))
                ORDER BY numero_pedido DESC 
                LIMIT 500
            """
        elif is_admin:
            q_pedidos = f"SELECT DISTINCT CAST(f.NUMERO_PEDIDO as STRING) as numero_pedido FROM {CATALOG}.{SCHEMA}.tbl_factdy_order f WHERE f.NUMERO_PEDIDO IS NOT NULL ORDER BY numero_pedido DESC LIMIT 500"
        else:
            q_pedidos = f"SELECT DISTINCT CAST(f.NUMERO_PEDIDO as STRING) as numero_pedido FROM {CATALOG}.{SCHEMA}.tbl_factdy_order f WHERE 1=0"

        with ThreadPoolExecutor(max_workers=2) as executor:
            f_cat = executor.submit(_get_filtros_global_catalog)
            f_pedidos = executor.submit(execute_sql, q_pedidos, p_pedidos)
            try:
                produtos, skus, categorias_map = f_cat.result()
            except Exception as ec:
                app.logger.warning(f"Aviso: catalogo global filtros: {ec}")
            try:
                pedidos = [str(r.get('numero_pedido')) for r in f_pedidos.result() if r.get('numero_pedido')]
            except Exception as epd:
                app.logger.warning(f"Aviso: consulta pedidos filtros: {epd}")

    except Exception as e:
        app.logger.error(f"Erro em /api/filtros: {e}")

    response_payload = {
        'anos': anos, 'meses': meses, 'semanas': semanas, 'dias': dias,
        'produtos': produtos, 'skus': skus, 'pedidos': pedidos,
        'categorias': categorias_map, 'erro': None
    }
    set_in_cache(cache_key, response_payload)
    return jsonify(response_payload)

# ─── APIs de Administração (todas bloqueadas no servidor por papel) ──────────────────────────
_ADMIN_TBL = f"{CATALOG}.{SCHEMA}.tbl_dim_app_admin"
_AUDIT_TBL = f"{CATALOG}.{SCHEMA}.tbl_log_admin_audit"

def _json_body():
    return request.get_json(silent=True) or {}

@app.before_request
def _v2_block_admin_writes():
    g._req_start = time.perf_counter()
    g._sql_timings = []
    # Não permitir novos vínculos por CNPJ enquanto o portal usa permissões por ID.
    if request.method in ('POST', 'PATCH') and request.path.startswith('/api/admin/distribuidores-acessos'):
        return jsonify({'error': 'Concessão por CNPJ desativada. Use o ID do distribuidor.'}), 410
    if READ_ONLY and request.method in ('POST', 'PATCH', 'DELETE', 'PUT') and request.path.startswith(('/api/admin/acessos', '/api/admin/distribuidores-acessos', '/api/admin/distribuidores-ids', '/api/admin/distribuidores-portal')):
        # Validação da carga em massa (dry_run) só lê: continua liberada em somente leitura
        if request.path == '/api/admin/distribuidores-acessos/lote' and _json_body().get('dry_run', True):
            return None
        return jsonify({'error': 'Somente leitura na v2: alterações de acesso estão desativadas.'}), 403

_COMPRESSIBLE_MIMETYPES = {
    'application/json',
    'application/javascript',
    'text/javascript',
    'text/css',
    'text/html',
    'text/plain',
    'image/svg+xml',
}

@app.after_request
def _v2_perf_headers_and_gzip(response):
    try:
        total_ms = (time.perf_counter() - getattr(g, '_req_start', time.perf_counter())) * 1000.0
        sql_list = getattr(g, '_sql_timings', None) or []
        sql_ms = sum(sql_list)
        response.headers['Server-Timing'] = f'sql;dur={sql_ms:.1f};desc="sql({len(sql_list)})", total;dur={total_ms:.1f}'
    except Exception:
        pass

    try:
        accept_enc = request.headers.get('Accept-Encoding', '').lower()
        if (
            'gzip' in accept_enc
            and response.status_code == 200
            and 'Content-Encoding' not in response.headers
            and (response.mimetype in _COMPRESSIBLE_MIMETYPES or (response.mimetype and response.mimetype.startswith('text/')))
        ):
            if response.direct_passthrough:
                response.direct_passthrough = False
            raw_data = response.get_data()
            if len(raw_data) >= 500:
                gz_data = gzip.compress(raw_data, compresslevel=6)
                response.set_data(gz_data)
                response.headers['Content-Encoding'] = 'gzip'
                response.headers['Content-Length'] = str(len(gz_data))
                vary = response.headers.get('Vary', '')
                if 'Accept-Encoding' not in vary:
                    response.headers['Vary'] = f"{vary}, Accept-Encoding".strip(', ')
    except Exception:
        pass

    return response

def _audit_safe(*a, **kw):
    """Grava auditoria; retorna None em sucesso ou a mensagem de erro (a falha é registrada no log do app)."""
    try:
        log_admin_audit(*a, **kw)
        return None
    except Exception as e:
        app.logger.error(f"[AUDIT FAIL] {a} {kw}: {e}")
        return str(e)

def get_distributor_catalog():
    """Lista de distribuidores (CNPJ + nome) a partir das fatos e do mapeamento. Cache 30 min.
    Nome: DESC_DISTRIBUIDOR_DNA (nome curto do DNA de Vendas); sem ele, DESC_DISTRIBUIDOR e por fim o mapping."""
    cached = get_from_cache('dist_catalog', ttl_seconds=1800)
    if cached is not None:
        return cached
    q = f"""
        WITH src AS (
            SELECT DISTINCT CNPJ_DISTRIBUIDOR AS c, DESC_DISTRIBUIDOR_DNA AS n, 1 AS p FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellin
            UNION ALL SELECT DISTINCT CNPJ_DISTRIBUIDOR, DESC_DISTRIBUIDOR_DNA, 1 FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout
            UNION ALL SELECT DISTINCT CNPJ_DISTRIBUIDOR, DESC_DISTRIBUIDOR_DNA, 1 FROM {CATALOG}.{SCHEMA}.tbl_factdy_stock
            UNION ALL SELECT DISTINCT CNPJ_DISTRIBUIDOR, DESC_DISTRIBUIDOR_DNA, 1 FROM {CATALOG}.{SCHEMA}.tbl_factdy_order
            UNION ALL SELECT DISTINCT CNPJ_DISTRIBUIDOR, DESC_DISTRIBUIDOR, 2 FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellin
            UNION ALL SELECT DISTINCT CNPJ_DISTRIBUIDOR, DESC_DISTRIBUIDOR, 2 FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout
            UNION ALL SELECT DISTINCT CNPJ_DISTRIBUIDOR, DESC_DISTRIBUIDOR, 2 FROM {CATALOG}.{SCHEMA}.tbl_factdy_stock
            UNION ALL SELECT DISTINCT CNPJ_DISTRIBUIDOR, DESC_DISTRIBUIDOR, 2 FROM {CATALOG}.{SCHEMA}.tbl_factdy_order
            UNION ALL SELECT DISTINCT distributor_cnpj_code, distributor_name, 3 FROM {CATALOG}.{SCHEMA}.tbl_dim_distributor_user_mapping
        ), norm AS (
            SELECT LPAD(regexp_replace(TRIM(CAST(c AS STRING)), '[^0-9]', ''), 14, '0') AS cnpj,
                   NULLIF(TRIM(n), '') AS nome, p
            FROM src
            WHERE c IS NOT NULL AND regexp_replace(TRIM(CAST(c AS STRING)), '[^0-9]', '') <> ''
        ), ranked AS (
            SELECT cnpj, nome,
                   ROW_NUMBER() OVER (PARTITION BY cnpj ORDER BY CASE WHEN nome IS NULL THEN 1 ELSE 0 END, p, nome) AS rn
            FROM norm
        )
        SELECT cnpj, nome FROM ranked WHERE rn = 1 ORDER BY nome NULLS LAST, cnpj
    """
    rows = execute_sql(q)
    items = [{'cnpj': r['cnpj'], 'nome': r.get('nome') or r['cnpj'], 'cnpj_fmt': format_cnpj(r['cnpj'])}
             for r in rows if _CNPJ_RE.match(str(r.get('cnpj') or ''))]
    set_in_cache('dist_catalog', items)
    return items

@app.route('/api/admin/distribuidores')
@require_role()
def api_admin_distribuidores():
    try:
        return jsonify({'items': get_distributor_catalog()})
    except Exception as e:
        app.logger.error(f"[api_admin_distribuidores] {e}")
        return jsonify({'error': 'Falha ao carregar distribuidores', 'items': []}), 500

@app.route('/api/admin/distribuidores/referencia')
@require_role()
def api_admin_distribuidores_referencia():
    """Referência oficial dos distribuidores ativos no portal para exportação."""
    try:
        active_groups = get_active_distributor_groups()
        items = []
        for g_item in active_groups:
            cnpjs = g_item.get('cnpjs') or ([g_item['cnpj']] if g_item.get('cnpj') else [''])
            for c in cnpjs:
                items.append({
                    'id': g_item.get('id'),
                    'nome': g_item.get('nome') or '',
                    'cnpj': format_cnpj(c) if c else ''
                })
        return jsonify({'items': items})
    except Exception as e:
        app.logger.error(f"[dist_referencia] {e}")
        return jsonify({'error': 'Falha ao carregar a referência de distribuidores'}), 500

_UC_GROUPS_LOCK = threading.Lock()

def get_all_uc_distributor_groups():
    """Todos os distribuidores por ID encontrados na UC (sellin, sellout, grupo_clientes_view). Cache 30 min com singleflight."""
    items = get_from_cache('dist_groups_all_uc', ttl_seconds=1800)
    if items is not None:
        return items
    stale = get_stale_from_cache('dist_groups_all_uc')
    if stale is not None and not _UC_GROUPS_LOCK.acquire(blocking=False):
        return stale

    def _load_uc():
        q_dists = f"""
            SELECT DISTINCT CAST(ID_DISTRIBUIDOR AS STRING) AS id,
                   CAST(CNPJ_DISTRIBUIDOR AS STRING) AS cnpj,
                   DESC_DISTRIBUIDOR_DNA AS nome, 1 AS prioridade
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellin
            UNION ALL
            SELECT DISTINCT CAST(ID_DISTRIBUIDOR AS STRING),
                   CAST(CNPJ_DISTRIBUIDOR AS STRING), DESC_DISTRIBUIDOR_DNA, 2
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellout
            UNION ALL
            SELECT DISTINCT CAST(COD_GR_CLIENTE AS STRING), CAST(CNPJ_CLIENTE AS STRING), GRUPO_CLIENTE_DESC, 3
            FROM {CATALOG}.bracatlg_lz.grupo_clientes_view WHERE NM_CANAL = 'DISTRIBUIDORES'
        """
        q_compras = f"""
            SELECT DISTINCT CAST(ID_DISTRIBUIDOR AS STRING) AS id,
                   date_format(DT_SELL_IN, 'yyyy-MM') AS periodo
            FROM {CATALOG}.{SCHEMA}.tbl_factdy_sellin
            WHERE QTDE_SELL_IN > 0 AND DT_SELL_IN <= current_date()
        """
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_rows = ex.submit(execute_sql, q_dists)
            f_compras = ex.submit(execute_sql, q_compras)
            rows = f_rows.result()
            compras_rows = f_compras.result()

        compras_id = {}
        for row in compras_rows:
            compra_id = str(row.get('id') or '').strip()
            if compra_id.isdigit() and int(compra_id) > 0:
                compras_id.setdefault(str(int(compra_id)), set()).add(row.get('periodo'))
        groups = {}
        for row in rows:
            group_id = str(row.get('id') or '').strip()
            if not group_id.isdigit() or int(group_id) <= 0:
                continue
            group_id = str(int(group_id))
            group = groups.setdefault(group_id, {'id': group_id, 'cnpjs': set(), 'nomes': []})
            raw = re.sub(r'\D', '', str(row.get('cnpj') or ''))
            if raw and len(raw) <= 14 and int(raw) != 0:
                group['cnpjs'].add(raw.zfill(14))
            nome = str(row.get('nome') or '').strip()
            if nome and nome != '0':
                group['nomes'].append((int(row.get('prioridade') or 9), nome))
        res_items = []
        for group in groups.values():
            cnpjs = sorted(group['cnpjs'])
            first = cnpjs[0] if cnpjs else ''
            nome = min(group['nomes'], default=(9, first or ('Distribuidor ' + group['id'])))[1]
            res_items.append({
                'id': group['id'],
                'nome': nome,
                'cnpj': first,
                'cnpjs': cnpjs,
                'compras': sorted(compras_id.get(group['id'], ()))
            })
        res_items.sort(key=lambda d: (d['nome'].casefold(), int(d['id']) if str(d['id']).isdigit() else 999999))
        set_in_cache('dist_groups_all_uc', res_items)
        return res_items

    if stale is not None:
        def _bg():
            try:
                _load_uc()
            finally:
                _UC_GROUPS_LOCK.release()
        threading.Thread(target=_bg, daemon=True).start()
        return stale

    with _UC_GROUPS_LOCK:
        items = get_from_cache('dist_groups_all_uc', ttl_seconds=1800)
        if items is not None:
            return items
        return _load_uc()

def get_active_distributor_groups():
    """Somente distribuidores ativos em tbl_dim_distribuidor_portal, com nome curto DNA (DESC_DISTRIBUIDOR_DNA)."""
    cached = get_from_cache('dist_groups', ttl_seconds=1800)
    if cached is not None:
        return cached
    portal_rows = [r for r in get_portal_dists_rows() if r.get('is_active')]
    portal_map = {}
    for r in portal_rows:
        rid = str(r.get('id') or '').strip()
        if rid.isdigit() and int(rid) > 0:
            portal_map[str(int(rid))] = r
    all_uc = {g_item['id']: g_item for g_item in get_all_uc_distributor_groups() if g_item.get('id')}
    items = []
    for pid, prow in portal_map.items():
        if pid in all_uc:
            g_item = dict(all_uc[pid])
            if not g_item.get('cnpj') and prow.get('cnpj_referencia'):
                c = normalize_cnpj(prow.get('cnpj_referencia'))
                if c:
                    g_item['cnpj'] = c
                    g_item['cnpjs'] = [c]
            items.append(g_item)
        else:
            c = normalize_cnpj(prow.get('cnpj_referencia'))
            items.append({
                'id': pid,
                'nome': str(prow.get('nome_referencia') or f"Distribuidor {pid}").strip(),
                'cnpj': c,
                'cnpjs': [c] if c else [],
                'compras': []
            })
    items.sort(key=lambda d: (d['nome'].casefold(), int(d['id']) if str(d['id']).isdigit() else 999999))
    set_in_cache('dist_groups', items)
    return items

@app.route('/api/admin/distribuidores/grupos')
@require_role(viewer=True)
def api_admin_distributor_groups():
    try:
        return jsonify({'items': get_active_distributor_groups()})
    except Exception as e:
        app.logger.error(f"[api_admin_distributor_groups] {e}")
        return jsonify({'error': 'Falha ao carregar distribuidores', 'items': []}), 500

@app.route('/api/admin/simulacao', methods=['POST'])
@require_role(viewer=True)
def api_admin_sim_start():
    body = _json_body()
    raw_id = str(body.get('id') or '').strip()
    cnpj = normalize_cnpj(body.get('cnpj'))
    try:
        active_groups = get_active_distributor_groups()
    except Exception as e:
        app.logger.error(f"[sim_start] {e}")
        active_groups = []
    match = None
    if raw_id.isdigit() and int(raw_id) > 0:
        sid = str(int(raw_id))
        match = next((d for d in active_groups if d.get('id') == sid), None)
    if not match and _CNPJ_RE.match(cnpj):
        match = next((d for d in active_groups if d.get('cnpj') == cnpj or cnpj in (d.get('cnpjs') or [])), None)
    if not match:
        return jsonify({'error': 'Distribuidor não encontrado ou inativo no portal'}), 404
    sim_obj = {'id': match['id'], 'cnpj': match.get('cnpj') or '', 'nome': match['nome'], 'by': request.admin_email}
    session['sim'] = sim_obj
    _audit_safe(request.admin_email, 'SIMULATE_START', details=f"Ver como distribuidor: {match['nome']} (ID {match['id']})")
    return jsonify({'ok': True, 'simulacao': {'id': match['id'], 'cnpj': match.get('cnpj') or '', 'nome': match['nome']}})

@app.route('/api/admin/simulacao', methods=['DELETE', 'POST', 'GET'])
@app.route('/api/admin/simulacao/sair', methods=['GET', 'POST', 'DELETE'])
@require_role(viewer=True)
def api_admin_sim_stop():
    sim = session.pop('sim', None)
    if sim:
        _audit_safe(request.admin_email, 'SIMULATE_END', details=f"Fim da simulação: {sim.get('nome')} ({sim.get('cnpj')})")
    if request.method == 'GET':
        return redirect('/dashboard.html?sair_sim=1')
    return jsonify({'ok': True})

def _get_admin_row(email):
    rows = execute_sql(
        f"""SELECT LOWER(TRIM(user_email)) AS user_email, UPPER(TRIM(role)) AS role, is_active
            FROM {_ADMIN_TBL} WHERE LOWER(TRIM(user_email)) = :email LIMIT 1""",
        {'email': email}
    )
    if not rows:
        return None
    r = rows[0]
    r['is_active'] = str(r.get('is_active')).lower() == 'true'
    return r

def _count_active_masters():
    rows = execute_sql(f"SELECT COUNT(*) AS n FROM {_ADMIN_TBL} WHERE is_active = TRUE AND UPPER(TRIM(role)) = 'MASTER'")
    return int(rows[0]['n']) if rows else 0

def _clean_target(email):
    return str(email or '').lower().strip()

@app.route('/api/admin/acessos', methods=['GET'])
@require_role()
def api_admin_acessos_list():
    try:
        rows = execute_sql(f"""
            SELECT LOWER(TRIM(user_email)) AS user_email, UPPER(TRIM(role)) AS role, is_active,
                   granted_by, unix_millis(granted_at) AS granted_ms,
                   revoked_by, unix_millis(revoked_at) AS revoked_ms, notes
            FROM {_ADMIN_TBL}
            ORDER BY is_active DESC, CASE UPPER(TRIM(role)) WHEN 'MASTER' THEN 0 WHEN 'ADMIN' THEN 1 ELSE 2 END, user_email
        """)
    except Exception as e:
        app.logger.error(f"[acessos_list] {e}")
        return jsonify({'error': 'Falha ao carregar administradores'}), 500
    for r in rows:
        r['is_active'] = str(r.get('is_active')).lower() == 'true'
    return jsonify({
        'me': {'email': request.admin_email, 'role': request.admin_role},
        # MASTER: tudo. ADMIN: concede/revoga ADMIN e distribuidores, mas não mexe em MASTER.
        'can_edit': True,
        'can_manage_masters': request.admin_role == 'MASTER',
        'items': rows
    })

@app.route('/api/admin/acessos', methods=['POST'])
@require_role()
def api_admin_acessos_add():
    body = _json_body()
    target = _clean_target(body.get('email'))
    role = str(body.get('role') or '').upper().strip()
    notes = str(body.get('notes') or '').strip()[:500]
    actor = request.admin_email
    if not _EMAIL_RE.match(target):
        return jsonify({'error': f'Informe um e-mail válido {ADMIN_EMAIL_DOMAIN}'}), 400
    if role not in ACCESS_ROLES:
        return jsonify({'error': 'Papel inválido (MASTER, ADMIN ou VISUALIZADOR)'}), 400
    if role == 'MASTER' and request.admin_role != 'MASTER':
        return jsonify({'error': 'Somente um MASTER pode conceder acesso MASTER'}), 403
    try:
        existing = _get_admin_row(target)
        if existing and existing['is_active']:
            return jsonify({'error': f"{target} já possui acesso ativo como {existing['role']}"}), 409
        if existing:
            execute_sql(f"""
                UPDATE {_ADMIN_TBL}
                SET role = :role, is_active = TRUE, granted_by = :actor, granted_at = current_timestamp(),
                    revoked_by = NULL, revoked_at = NULL, notes = NULLIF(:notes, ''), storeday = current_timestamp()
                WHERE LOWER(TRIM(user_email)) = :email
            """, {'role': role, 'actor': actor, 'notes': notes, 'email': target})
            action, old_role = 'REACTIVATE', existing['role']
        else:
            execute_sql(f"""
                INSERT INTO {_ADMIN_TBL} (user_email, role, is_active, granted_by, granted_at, revoked_by, revoked_at, notes, storeday)
                VALUES (:email, :role, TRUE, :actor, current_timestamp(), NULL, NULL, NULLIF(:notes, ''), current_timestamp())
            """, {'role': role, 'actor': actor, 'notes': notes, 'email': target})
            action, old_role = 'GRANT', None
    except Exception as e:
        app.logger.error(f"[acessos_add] {e}")
        return jsonify({'error': 'Falha ao gravar o acesso'}), 500
    invalidate_admin_cache()
    audit_err = _audit_safe(actor, action, target, old_role, role, notes or None)
    return jsonify({'ok': True, 'action': action, 'audit_error': audit_err})

@app.route('/api/admin/acessos/<path:target_email>', methods=['PATCH'])
@require_role(master=True)
def api_admin_acessos_role(target_email):
    target = _clean_target(target_email)
    new_role = str(_json_body().get('role') or '').upper().strip()
    actor = request.admin_email
    if new_role not in ACCESS_ROLES:
        return jsonify({'error': 'Papel inválido (MASTER, ADMIN ou VISUALIZADOR)'}), 400
    if target == actor:
        return jsonify({'error': 'Não é permitido alterar o próprio papel'}), 409
    try:
        existing = _get_admin_row(target)
        if not existing or not existing['is_active']:
            return jsonify({'error': 'Usuário não possui acesso ativo'}), 404
        if existing['role'] == new_role:
            return jsonify({'error': f'Usuário já é {new_role}'}), 400
        if existing['role'] == 'MASTER' and _count_active_masters() <= 1:
            return jsonify({'error': 'Não é permitido rebaixar o último MASTER'}), 409
        execute_sql(f"""
            UPDATE {_ADMIN_TBL} SET role = :role, storeday = current_timestamp()
            WHERE LOWER(TRIM(user_email)) = :email AND is_active = TRUE
        """, {'role': new_role, 'email': target})
    except Exception as e:
        app.logger.error(f"[acessos_role] {e}")
        return jsonify({'error': 'Falha ao alterar o papel'}), 500
    invalidate_admin_cache()
    action = 'PROMOTE' if ACCESS_ROLES.index(new_role) < ACCESS_ROLES.index(existing['role']) else 'DEMOTE'
    audit_err = _audit_safe(actor, action, target, existing['role'], new_role)
    return jsonify({'ok': True, 'action': action, 'audit_error': audit_err})

@app.route('/api/admin/acessos/<path:target_email>', methods=['DELETE'])
@require_role()
def api_admin_acessos_revoke(target_email):
    target = _clean_target(target_email)
    motivo = str(_json_body().get('motivo') or '').strip()[:500]
    actor = request.admin_email
    if target == actor:
        return jsonify({'error': 'Não é permitido revogar o próprio acesso'}), 409
    try:
        existing = _get_admin_row(target)
        if not existing or not existing['is_active']:
            return jsonify({'error': 'Usuário não possui acesso ativo'}), 404
        if existing['role'] == 'MASTER' and request.admin_role != 'MASTER':
            return jsonify({'error': 'Somente um MASTER pode alterar o acesso de outro MASTER'}), 403
        if existing['role'] == 'MASTER' and _count_active_masters() <= 1:
            return jsonify({'error': 'Não é permitido remover o último MASTER'}), 409
        execute_sql(f"""
            UPDATE {_ADMIN_TBL}
            SET is_active = FALSE, revoked_by = :actor, revoked_at = current_timestamp(), storeday = current_timestamp()
            WHERE LOWER(TRIM(user_email)) = :email AND is_active = TRUE
        """, {'actor': actor, 'email': target})
    except Exception as e:
        app.logger.error(f"[acessos_revoke] {e}")
        return jsonify({'error': 'Falha ao revogar o acesso'}), 500
    invalidate_admin_cache()
    audit_err = _audit_safe(actor, 'REVOKE', target, existing['role'], None, motivo or None)
    return jsonify({'ok': True, 'action': 'REVOKE', 'audit_error': audit_err})

# ─── Busca de usuários Databricks (autocomplete de e-mail) ──────────────────────────────
# Usa o diretório de usuários da conta (via workspace), com fallback para o SCIM do workspace.
# Leve: mín. 3 caracteres, 8 resultados, só userName/displayName, timeout curto e cache de 10 min.
_USER_Q_RE = re.compile(r'^[a-z0-9._@\-]{3,64}$')
_USER_SEARCH_TTL = 600
_USER_SEARCH_PATHS = ('/api/2.0/account/scim/v2/Users', '/api/2.0/preview/scim/v2/Users')

def search_databricks_users(term, limit=8):
    key = f"user_search:{term}"
    cached = get_from_cache(key, ttl_seconds=_USER_SEARCH_TTL)
    if cached is not None:
        return cached
    import requests as _rq
    w = get_workspace_client()
    headers = w.config.authenticate()
    params = {'filter': f'userName co "{term}" or displayName co "{term}"',
              'attributes': 'userName,displayName,active', 'count': limit}
    last_err = None
    for path in _USER_SEARCH_PATHS:
        try:
            r = _rq.get(w.config.host.rstrip('/') + path, headers=headers, params=params, timeout=6)
            if r.status_code != 200:
                last_err = f"{path} HTTP {r.status_code}"
                continue
            items = []
            for u in r.json().get('Resources', []) or []:
                email = str(u.get('userName') or '').strip().lower()
                if '@' not in email or u.get('active') is False:
                    continue
                items.append({'email': email, 'nome': u.get('displayName') or ''})
            set_in_cache(key, items)
            return items
        except Exception as e:
            last_err = f"{path} {e}"
    raise RuntimeError(last_err or 'busca indisponível')

@app.route('/api/admin/usuarios')
@require_role()
def api_admin_user_search():
    term = str(request.args.get('q') or '').strip().lower()
    if not _USER_Q_RE.match(term):
        return jsonify({'items': []})
    try:
        return jsonify({'items': search_databricks_users(term)})
    except Exception as e:
        app.logger.warning(f"[user_search] {e}")
        return jsonify({'items': [], 'unavailable': True})

# ─── Acessos de Distribuidor (tbl_dim_distributor_user_mapping) ────────────────────────────
# Qualquer ADMIN/MASTER gerencia. Cada linha é um vínculo (e-mail, CNPJ): um e-mail pode ter
# vários distribuidores, e o portal soma os dados de todos os CNPJs ativos do usuário.
_MAP_TBL = f"{CATALOG}.{SCHEMA}.tbl_dim_distributor_user_mapping"
_ANY_EMAIL_RE = re.compile(r'^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$')
# CNPJ da tabela comparado sempre como 14 dígitos (a coluna pode ter vindo sem zeros à esquerda)
_MAP_CNPJ_SQL = "LPAD(REGEXP_REPLACE(CAST(distributor_cnpj_code AS STRING), '[^0-9]', ''), 14, '0')"
_BULK_MAX = 1000
_SQL_CHUNK = 200

def _get_map_link(email, cnpj):
    """Vínculo (e-mail, CNPJ), ativo ou não. None se nunca existiu."""
    rows = execute_sql(
        f"""SELECT LOWER(TRIM(user_email)) AS user_email, distributor_cnpj_code, distributor_name, is_active
            FROM {_MAP_TBL}
            WHERE LOWER(TRIM(user_email)) = :email AND {_MAP_CNPJ_SQL} = :cnpj
            ORDER BY is_active DESC LIMIT 1""",
        {'email': email, 'cnpj': cnpj}
    )
    if not rows:
        return None
    r = rows[0]
    r['is_active'] = str(r.get('is_active')).lower() == 'true'
    r['cnpj'] = normalize_cnpj(r.get('distributor_cnpj_code'))
    return r

def _catalog_match(cnpj):
    c = normalize_cnpj(cnpj)
    if not _CNPJ_RE.match(c):
        return None
    return next((d for d in get_distributor_catalog() if d['cnpj'] == c), None)

def _in_chunks(emails, sql_builder):
    """Executa uma consulta por bloco de e-mails (parâmetros :e0..:eN) e junta as linhas."""
    emails = sorted(set(emails))
    out = []
    for i in range(0, len(emails), _SQL_CHUNK):
        params = {f'e{j}': e for j, e in enumerate(emails[i:i + _SQL_CHUNK])}
        out.extend(execute_sql(sql_builder(', '.join(':' + k for k in params)), params))
    return out

def _active_admin_emails(emails):
    """Subconjunto dos e-mails com acesso de administrador ativo."""
    rows = _in_chunks(emails, lambda ph: f"""
        SELECT DISTINCT LOWER(TRIM(user_email)) AS e FROM {_ADMIN_TBL}
        WHERE is_active = TRUE AND LOWER(TRIM(user_email)) IN ({ph})""")
    return {r['e'] for r in rows}

def _existing_links(emails):
    """{(email, cnpj): ativo?} de todos os vínculos já gravados para esses e-mails."""
    rows = _in_chunks(emails, lambda ph: f"""
        SELECT LOWER(TRIM(user_email)) AS e, {_MAP_CNPJ_SQL} AS c, MAX(CAST(is_active AS INT)) AS a
        FROM {_MAP_TBL} WHERE LOWER(TRIM(user_email)) IN ({ph}) GROUP BY 1, 2""")
    return {(r['e'], r['c']): str(r.get('a')) == '1' for r in rows}

def _plan_grants(items):
    """
    Valida e classifica cada linha {email, cnpj}. Status:
      new (vínculo novo) · reactivate (vínculo revogado volta) · exists (já ativo, nada a fazer)
      error (e-mail/CNPJ inválido, CNPJ fora da base, administrador ativo ou linha repetida)
    """
    plan, seen = [], set()
    for idx, it in enumerate(items):
        it = it if isinstance(it, dict) else {}
        email = _clean_target(it.get('email'))
        digits = re.sub(r'\D', '', str(it.get('cnpj') or ''))
        # Até 3 zeros à esquerda perdidos (Excel tratando CNPJ como número) são repostos; menos que isso é erro
        cnpj = digits.zfill(14) if 11 <= len(digits) <= 14 else digits
        row = {'linha': it.get('linha') or idx + 1, 'email': email, 'cnpj': cnpj,
               'cnpj_fmt': format_cnpj(cnpj), 'nome': None, 'motivo': None}
        dist = _catalog_match(cnpj) if _CNPJ_RE.match(cnpj) else None
        if not _ANY_EMAIL_RE.match(email):
            row.update(status='error', motivo='E-mail inválido')
        elif not _CNPJ_RE.match(cnpj):
            row.update(status='error', motivo='CNPJ inválido (precisa de 14 dígitos)')
        elif not dist:
            row.update(status='error', motivo='CNPJ não encontrado na base de distribuidores')
        elif (email, cnpj) in seen:
            row.update(status='error', motivo='Repetido neste lote', nome=dist['nome'])
        else:
            seen.add((email, cnpj))
            row.update(status='ok', nome=dist['nome'])
        plan.append(row)
    valid = [r for r in plan if r['status'] == 'ok']
    admins = _active_admin_emails(r['email'] for r in valid)
    links = _existing_links(r['email'] for r in valid)
    for r in valid:
        if r['email'] in admins:
            r.update(status='error', motivo='É administrador ativo (já vê todos os distribuidores)')
        else:
            active = links.get((r['email'], r['cnpj']))
            r['status'] = 'exists' if active else ('reactivate' if active is False else 'new')
    return plan

def _merge_grants(rows, actor):
    """Grava vínculos novos e reativa os revogados, em MERGEs de até _SQL_CHUNK linhas."""
    for i in range(0, len(rows), _SQL_CHUNK):
        chunk = rows[i:i + _SQL_CHUNK]
        params = {'actor': actor}
        values = []
        for j, r in enumerate(chunk):
            params.update({f'e{j}': r['email'], f'c{j}': r['cnpj'], f'n{j}': r['nome'] or r['cnpj']})
            values.append(f"(:e{j}, :c{j}, :n{j})")
        execute_sql(f"""
            MERGE INTO {_MAP_TBL} t
            USING (SELECT * FROM VALUES {', '.join(values)} AS s(email, cnpj, nome)) s
              ON LOWER(TRIM(t.user_email)) = s.email
             AND LPAD(REGEXP_REPLACE(CAST(t.distributor_cnpj_code AS STRING), '[^0-9]', ''), 14, '0') = s.cnpj
            WHEN MATCHED AND t.is_active = FALSE THEN UPDATE SET
              distributor_name = s.nome, is_active = TRUE, valid_from_date = current_date(), valid_to_date = NULL,
              created_by_user = :actor, storeday = current_timestamp()
            WHEN NOT MATCHED THEN INSERT (user_email, distributor_cnpj_code, distributor_name, is_active,
                                          valid_from_date, valid_to_date, storeday, created_by_user)
              VALUES (s.email, s.cnpj, s.nome, TRUE, current_date(), NULL, current_timestamp(), :actor)
        """, params, timeout=120)

def _send_grant_emails(rows, actor):
    """Um e-mail por usuário, listando todos os distribuidores liberados agora. Retorna {status: qtd}."""
    by_email = {}
    for r in rows:
        by_email.setdefault(r['email'], []).append({'nome': r['nome'], 'cnpj': r['cnpj']})
    stats = {}
    for email, dists in by_email.items():
        st = send_access_granted_email(email, dists, actor)
        stats[st] = stats.get(st, 0) + 1
    return stats

@app.route('/api/admin/distribuidores-acessos', methods=['GET'])
@require_role()
def api_admin_dist_access_list():
    try:
        rows = execute_sql(f"""
            SELECT LOWER(TRIM(m.user_email)) AS user_email, m.distributor_cnpj_code, m.distributor_name, m.is_active,
                   CAST(m.valid_from_date AS STRING) AS valid_from_date, CAST(m.valid_to_date AS STRING) AS valid_to_date,
                   m.created_by_user, unix_millis(m.storeday) AS storeday_ms,
                   UPPER(TRIM(a.role)) AS admin_role
            FROM {_MAP_TBL} m
            LEFT JOIN {_ADMIN_TBL} a
              ON LOWER(TRIM(a.user_email)) = LOWER(TRIM(m.user_email)) AND a.is_active = TRUE
            ORDER BY m.is_active DESC, user_email, m.distributor_name
        """)
    except Exception as e:
        app.logger.error(f"[dist_access_list] {e}")
        return jsonify({'error': 'Falha ao carregar acessos de distribuidores'}), 500
    for r in rows:
        r['is_active'] = str(r.get('is_active')).lower() == 'true'
        r['cnpj'] = normalize_cnpj(r.get('distributor_cnpj_code'))
        r['cnpj_fmt'] = format_cnpj(r['cnpj'])
    return jsonify({'me': {'email': request.admin_email, 'role': request.admin_role}, 'items': rows})

# ─── E-mail de acesso concedido ────────────────────────────────────────────────────────────
# SMTP configurado por variáveis de ambiente (app.yaml). Sem SMTP_HOST o envio é ignorado.
#   SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD (via secret), SMTP_FROM, APP_PUBLIC_URL
import smtplib
from email.message import EmailMessage

def send_access_granted_email(to_email, dists, actor):
    """Envia o aviso de acesso concedido (dists = [{nome, cnpj}] liberados agora).
    Retorna 'sent', 'disabled' ou 'failed' (nunca levanta)."""
    host = os.environ.get('SMTP_HOST')
    if not host:
        return 'disabled'
    if len(dists) == 1:
        dist_lines = f"Distribuidor: {dists[0]['nome']} ({format_cnpj(dists[0]['cnpj'])})\n"
    else:
        dist_lines = "Distribuidores:\n" + "".join(f"  - {d['nome']} ({format_cnpj(d['cnpj'])})\n" for d in dists)
    sender = os.environ.get('SMTP_FROM') or os.environ.get('SMTP_USER')
    link = (os.environ.get('APP_PUBLIC_URL') or request.host_url).rstrip('/') + '/dashboard.html'
    msg = EmailMessage()
    msg['Subject'] = 'Acesso liberado - Portal Distribuidores Bimbo QSR'
    msg['From'] = sender
    msg['To'] = to_email
    msg['Reply-To'] = actor
    msg.set_content(
        "Olá,\n\n"
        "Seu acesso ao Portal Distribuidores Bimbo QSR foi liberado.\n\n"
        + dist_lines +
        f"Usuário: {to_email}\n"
        f"Link de acesso: {link}\n\n"
        "Para entrar, abra o link e faça login com este e-mail.\n"
        "No portal você acompanha sell-in, sell-out, pedidos e estoque dos CNPJs liberados.\n\n"
        f"Dúvidas: responda este e-mail ou fale com {actor}.\n\n"
        "Grupo Bimbo Brasil - Data & Analytics\n"
    )
    try:
        with smtplib.SMTP(host, int(os.environ.get('SMTP_PORT', 587)), timeout=15) as smtp:
            smtp.starttls()
            if os.environ.get('SMTP_USER'):
                smtp.login(os.environ['SMTP_USER'], os.environ.get('SMTP_PASSWORD', ''))
            smtp.send_message(msg)
        return 'sent'
    except Exception as e:
        app.logger.error(f"[access_email] falha ao enviar para {to_email}: {e}")
        return 'failed'

# Gestão por ID. A tabela anterior continua disponível apenas para usuários legados.
_ID_MAP_TBL = f"{CATALOG}.{SCHEMA}.tbl_dim_distributor_user_id_mapping"

@app.route('/api/admin/distribuidores-ids', methods=['GET'])
@require_role()
def api_admin_dist_ids_list():
    try:
        rows = execute_sql(f"""
            SELECT LOWER(TRIM(m.user_email)) AS user_email, CAST(m.id_distribuidor AS STRING) AS id,
                   m.distributor_name, m.is_active, CAST(m.valid_from_date AS STRING) AS valid_from_date,
                   CAST(m.valid_to_date AS STRING) AS valid_to_date, m.created_by_user,
                   UPPER(TRIM(a.role)) AS admin_role
            FROM {_ID_MAP_TBL} m LEFT JOIN {_ADMIN_TBL} a
              ON LOWER(TRIM(a.user_email)) = LOWER(TRIM(m.user_email)) AND a.is_active = TRUE
            ORDER BY user_email, m.distributor_name
        """)
        for r in rows:
            r['is_active'] = str(r.get('is_active')).lower() == 'true'
        legacy = execute_sql(f"""
            SELECT LOWER(TRIM(m.user_email)) user_email, m.distributor_cnpj_code, m.distributor_name,
                   m.is_active, CAST(m.valid_from_date AS STRING) valid_from_date,
                   CAST(m.valid_to_date AS STRING) valid_to_date, m.created_by_user
            FROM {_MAP_TBL} m WHERE m.is_active = TRUE AND NOT EXISTS (
              SELECT 1 FROM {_ID_MAP_TBL} i WHERE LOWER(TRIM(i.user_email)) = LOWER(TRIM(m.user_email))
            )
        """)
        for r in legacy:
            r.update(id=None, legacy=True, is_active=str(r.get('is_active')).lower() == 'true',
                     cnpj=normalize_cnpj(r.get('distributor_cnpj_code')))
        return jsonify({'items': rows + legacy})
    except Exception as e:
        app.logger.error(f"[dist_ids_list] {e}")
        return jsonify({'error': 'Falha ao carregar acessos por ID'}), 500

@app.route('/api/admin/distribuidores-ids', methods=['POST'])
@require_role()
def api_admin_dist_ids_grant():
    body = _json_body()
    email = _clean_target(body.get('email'))
    raw_ids = body.get('ids')
    if not _ANY_EMAIL_RE.match(email) or not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 100:
        return jsonify({'error': 'Informe e-mail e IDs válidos'}), 400
    ids = sorted({str(int(str(x))) for x in raw_ids if str(x).isdigit() and int(str(x)) > 0})
    if len(ids) != len(raw_ids):
        return jsonify({'error': 'IDs inválidos ou repetidos'}), 400
    try:
        if _active_admin_emails([email]):
            return jsonify({'error': 'Usuário é administrador ativo'}), 409
        # IDs vêm da lista ativa do portal / UC; nenhum CNPJ é usado para inferir autorização.
        uc_map = {g_item['id']: g_item.get('nome') or ('Distribuidor ' + str(g_item['id']))
                  for g_item in (get_active_distributor_groups() + get_all_uc_distributor_groups())
                  if g_item.get('id') and str(g_item.get('id')) != '99'}
        names = {i_val: uc_map[i_val] for i_val in ids if i_val in uc_map}
        if set(names) != set(ids):
            return jsonify({'error': 'ID de distribuidor não encontrado no cadastro'}), 400
        # Usuários legados precisam ter os vínculos resolvidos antes de trocar de modelo.
        legacy = execute_sql(f"SELECT 1 FROM {_MAP_TBL} m WHERE LOWER(TRIM(m.user_email))=:email AND m.is_active=TRUE AND NOT EXISTS (SELECT 1 FROM {_ID_MAP_TBL} i WHERE LOWER(TRIM(i.user_email))=:email) LIMIT 1", {'email': email})
        if legacy:
            return jsonify({'error': 'Este usuário possui vínculo legado por CNPJ; associe o ID antes de migrá-lo.'}), 409
        params = {'email': email, 'actor': request.admin_email}
        vals = []
        for i, value in enumerate(ids):
            params[f'i{i}'] = value; params[f'n{i}'] = names[value]
            vals.append(f"(:i{i}, :n{i})")
        execute_sql(f"""
            MERGE INTO {_ID_MAP_TBL} t USING (SELECT * FROM VALUES {', '.join(vals)} AS v(id,nome)) s
            ON LOWER(TRIM(t.user_email))=:email AND CAST(t.id_distribuidor AS STRING)=s.id
            WHEN MATCHED AND t.is_active=FALSE THEN UPDATE SET is_active=TRUE, valid_from_date=CURRENT_DATE(),
                 valid_to_date=NULL, distributor_name=s.nome, created_by_user=:actor, storeday=CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT (user_email,id_distribuidor,distributor_name,is_active,valid_from_date,valid_to_date,created_by_user,storeday)
                 VALUES (:email,s.id,s.nome,TRUE,CURRENT_DATE(),NULL,:actor,CURRENT_TIMESTAMP())
        """, params, timeout=120)
        invalidate_admin_cache()
        audit_error = _audit_safe(request.admin_email, 'DIST_GRANT', email, None, 'DISTRIBUIDOR', 'IDs: ' + ', '.join(ids))
        return jsonify({'ok': True, 'ids': ids, 'audit_error': audit_error})
    except Exception as e:
        app.logger.error(f"[dist_ids_grant] {e}")
        return jsonify({'error': 'Falha ao conceder acesso por ID'}), 500

@app.route('/api/admin/distribuidores-ids/<path:target_email>/<dist_id>', methods=['DELETE'])
@require_role()
def api_admin_dist_ids_revoke(target_email, dist_id):
    email = _clean_target(target_email)
    if not _ANY_EMAIL_RE.match(email) or not dist_id.isdigit() or int(dist_id) <= 0:
        return jsonify({'error': 'E-mail ou ID inválido'}), 400
    dist_id = str(int(dist_id))
    try:
        result = execute_sql(f"""UPDATE {_ID_MAP_TBL} SET is_active=FALSE, valid_to_date=CURRENT_DATE(), storeday=CURRENT_TIMESTAMP()
             WHERE LOWER(TRIM(user_email))=:email AND CAST(id_distribuidor AS STRING)=:id AND is_active=TRUE""",
             {'email': email, 'id': dist_id})
        if not result or int(result[0].get('num_affected_rows') or 0) == 0:
            return jsonify({'error': 'Vínculo ativo não encontrado'}), 404
        invalidate_admin_cache()
        audit_error = _audit_safe(request.admin_email, 'DIST_REVOKE', email, 'DISTRIBUIDOR', None, 'ID: ' + dist_id)
        return jsonify({'ok': True, 'audit_error': audit_error})
    except Exception as e:
        app.logger.error(f"[dist_ids_revoke] {e}")
        return jsonify({'error': 'Falha ao revogar acesso por ID'}), 500

@app.route('/api/admin/distribuidores-ids/revogar', methods=['POST'])
@require_role()
def api_admin_dist_ids_revoke_bulk():
    """Revoga vários vínculos (e-mail, ID) em uma única atualização; o histórico registra um evento por e-mail."""
    body = _json_body()
    raw = body.get('items')
    motivo = str(body.get('motivo') or '').strip()[:500]
    if not isinstance(raw, list) or not raw or len(raw) > 500:
        return jsonify({'error': 'Informe de 1 a 500 vínculos'}), 400
    by_email = {}
    for item in raw:
        email = _clean_target(item.get('email')) if isinstance(item, dict) else ''
        dist_id = str(item.get('id') or '') if isinstance(item, dict) else ''
        if not _ANY_EMAIL_RE.match(email) or not dist_id.isdigit() or int(dist_id) <= 0:
            return jsonify({'error': 'E-mail ou ID inválido'}), 400
        by_email.setdefault(email, set()).add(str(int(dist_id)))
    params, conds = {}, []
    for i, (email, ids) in enumerate(by_email.items()):
        params[f'e{i}'] = email
        # IDs já validados como dígitos
        marks = ', '.join(f"'{x}'" for x in sorted(ids))
        conds.append(f"(LOWER(TRIM(user_email))=:e{i} AND CAST(id_distribuidor AS STRING) IN ({marks}))")
    try:
        result = execute_sql(f"""UPDATE {_ID_MAP_TBL} SET is_active=FALSE, valid_to_date=CURRENT_DATE(), storeday=CURRENT_TIMESTAMP()
             WHERE is_active=TRUE AND ({' OR '.join(conds)})""", params, timeout=120)
    except Exception as e:
        app.logger.error(f"[dist_ids_revoke_bulk] {e}")
        return jsonify({'error': 'Falha ao revogar os acessos'}), 500
    invalidate_admin_cache()
    audit_error = None
    for email, ids in by_email.items():
        details = 'IDs: ' + ', '.join(sorted(ids)) + (f" | motivo: {motivo}" if motivo else '')
        audit_error = _audit_safe(request.admin_email, 'DIST_REVOKE', email, 'DISTRIBUIDOR', None, details) or audit_error
    revoked = int(result[0].get('num_affected_rows') or 0) if result else 0
    return jsonify({'ok': True, 'revoked': revoked, 'audit_error': audit_error})

@app.route('/api/admin/distribuidores-acessos', methods=['POST'])
@require_role()
def api_admin_dist_access_grant():
    """Concede um vínculo (e-mail, CNPJ). Um e-mail pode somar vários distribuidores."""
    body = _json_body()
    actor = request.admin_email
    try:
        row = _plan_grants([{'email': body.get('email'), 'cnpj': body.get('cnpj')}])[0]
        if row['status'] == 'error':
            return jsonify({'error': row['motivo']}), 400 if 'administrador' not in row['motivo'] else 409
        if row['status'] == 'exists':
            return jsonify({'error': f"{row['email']} já tem acesso a {row['nome']} ({row['cnpj_fmt']})"}), 409
        _merge_grants([row], actor)
    except Exception as e:
        app.logger.error(f"[dist_access_grant] {e}")
        return jsonify({'error': 'Falha ao gravar o acesso do distribuidor'}), 500
    invalidate_admin_cache()
    action = 'DIST_REACTIVATE' if row['status'] == 'reactivate' else 'DIST_GRANT'
    audit_err = _audit_safe(actor, action, row['email'], None, 'DISTRIBUIDOR', f"{row['nome']} ({row['cnpj']})")
    email_status = 'disabled' if body.get('send_email') is False else \
        send_access_granted_email(row['email'], [{'nome': row['nome'], 'cnpj': row['cnpj']}], actor)
    return jsonify({'ok': True, 'action': action, 'audit_error': audit_err, 'email': email_status})

@app.route('/api/admin/distribuidores-acessos/lote', methods=['POST'])
@require_role()
def api_admin_dist_access_bulk():
    """
    Carga em massa. body = {items: [{email, cnpj, linha?}], dry_run: bool, send_email: bool}.
    dry_run=true só valida e devolve o plano linha a linha; false grava os válidos (new/reactivate)
    num MERGE e ignora erros e vínculos já ativos.
    """
    body = _json_body()
    items = body.get('items') or []
    actor = request.admin_email
    if not isinstance(items, list) or not items:
        return jsonify({'error': 'Nenhuma linha para importar'}), 400
    if len(items) > _BULK_MAX:
        return jsonify({'error': f'Máximo de {_BULK_MAX} linhas por carga. Divida o arquivo.'}), 400
    try:
        plan = _plan_grants(items)
    except Exception as e:
        app.logger.error(f"[dist_access_bulk plan] {e}")
        return jsonify({'error': 'Falha ao validar as linhas'}), 500
    summary = {k: sum(1 for r in plan if r['status'] == k) for k in ('new', 'reactivate', 'exists', 'error')}
    if body.get('dry_run', True):
        return jsonify({'ok': True, 'dry_run': True, 'summary': summary, 'items': plan})
    todo = [r for r in plan if r['status'] in ('new', 'reactivate')]
    if not todo:
        return jsonify({'error': 'Nenhuma linha nova para gravar'}), 400
    try:
        _merge_grants(todo, actor)
    except Exception as e:
        app.logger.error(f"[dist_access_bulk merge] {e}")
        return jsonify({'error': 'Falha ao gravar os acessos. Nenhuma linha deste bloco foi aplicada.'}), 500
    invalidate_admin_cache()
    audit_errs = 0
    for r in todo:
        action = 'DIST_REACTIVATE' if r['status'] == 'reactivate' else 'DIST_GRANT'
        if _audit_safe(actor, action, r['email'], None, 'DISTRIBUIDOR', f"{r['nome']} ({r['cnpj']}) | carga em massa"):
            audit_errs += 1
    emails = _send_grant_emails(todo, actor) if body.get('send_email') else {}
    return jsonify({'ok': True, 'dry_run': False, 'summary': summary, 'gravados': len(todo),
                    'audit_errors': audit_errs, 'emails': emails})

@app.route('/api/admin/distribuidores-acessos/<path:target_email>', methods=['PATCH'])
@require_role()
def api_admin_dist_access_change(target_email):
    """Troca um vínculo específico (from_cnpj → cnpj) do e-mail; os demais vínculos não mudam."""
    target = _clean_target(target_email)
    actor = request.admin_email
    body = _json_body()
    from_cnpj = normalize_cnpj(body.get('from_cnpj'))
    try:
        dist = _catalog_match(body.get('cnpj'))
        if not dist:
            return jsonify({'error': 'Selecione um distribuidor válido da lista'}), 400
        existing = _get_map_link(target, from_cnpj) if _CNPJ_RE.match(from_cnpj) else None
        if not existing or not existing['is_active']:
            return jsonify({'error': 'Vínculo ativo não encontrado para este e-mail e CNPJ'}), 404
        if from_cnpj == dist['cnpj']:
            return jsonify({'error': 'O e-mail já está vinculado a este distribuidor'}), 400
        dest = _get_map_link(target, dist['cnpj'])
        if dest and dest['is_active']:
            return jsonify({'error': f"{target} já tem acesso a {dist['nome']}. Revogue este vínculo em vez de alterá-lo."}), 409
        execute_sql(f"""
            UPDATE {_MAP_TBL}
            SET distributor_cnpj_code = :cnpj, distributor_name = :nome, valid_from_date = current_date(),
                created_by_user = :actor, storeday = current_timestamp()
            WHERE LOWER(TRIM(user_email)) = :email AND {_MAP_CNPJ_SQL} = :from_cnpj AND is_active = TRUE
        """, {'email': target, 'cnpj': dist['cnpj'], 'nome': dist['nome'], 'actor': actor, 'from_cnpj': from_cnpj})
    except Exception as e:
        app.logger.error(f"[dist_access_change] {e}")
        return jsonify({'error': 'Falha ao alterar o distribuidor'}), 500
    invalidate_admin_cache()
    details = f"de {existing.get('distributor_name')} ({from_cnpj}) para {dist['nome']} ({dist['cnpj']})"
    audit_err = _audit_safe(actor, 'DIST_CHANGE', target, 'DISTRIBUIDOR', 'DISTRIBUIDOR', details)
    return jsonify({'ok': True, 'action': 'DIST_CHANGE', 'audit_error': audit_err})

@app.route('/api/admin/distribuidores-acessos/<path:target_email>', methods=['DELETE'])
@require_role()
def api_admin_dist_access_revoke(target_email):
    """Revoga um vínculo específico (body.cnpj); os outros distribuidores do e-mail continuam ativos."""
    target = _clean_target(target_email)
    actor = request.admin_email
    body = _json_body()
    cnpj = normalize_cnpj(body.get('cnpj'))
    motivo = str(body.get('motivo') or '').strip()[:500]
    try:
        existing = _get_map_link(target, cnpj) if _CNPJ_RE.match(cnpj) else None
        if not existing or not existing['is_active']:
            return jsonify({'error': 'Vínculo ativo não encontrado para este e-mail e CNPJ'}), 404
        execute_sql(f"""
            UPDATE {_MAP_TBL}
            SET is_active = FALSE, valid_to_date = current_date(), storeday = current_timestamp()
            WHERE LOWER(TRIM(user_email)) = :email AND {_MAP_CNPJ_SQL} = :cnpj AND is_active = TRUE
        """, {'email': target, 'cnpj': cnpj})
    except Exception as e:
        app.logger.error(f"[dist_access_revoke] {e}")
        return jsonify({'error': 'Falha ao revogar o acesso do distribuidor'}), 500
    invalidate_admin_cache()
    details = f"{existing.get('distributor_name')} ({cnpj})" + (f" | motivo: {motivo}" if motivo else '')
    audit_err = _audit_safe(actor, 'DIST_REVOKE', target, 'DISTRIBUIDOR', None, details)
    return jsonify({'ok': True, 'action': 'DIST_REVOKE', 'audit_error': audit_err})

# ─── Distribuidores no Portal (tbl_dim_distribuidor_portal) ────────────────────────────
def _build_portal_dists_payload():
    rows = get_portal_dists_rows()
    uc_groups = {g_item['id']: g_item for g_item in get_all_uc_distributor_groups() if g_item.get('id')}
    active_ids = set()
    items = []
    for r in rows:
        did = str(r.get('id') or '').strip()
        if not did.isdigit() or int(did) <= 0:
            continue
        if not r.get('is_active'):
            continue
        did = str(int(did))
        active_ids.add(did)
        uc = uc_groups.get(did, {})
        cnpj_ref = normalize_cnpj(r.get('cnpj_referencia')) or uc.get('cnpj') or ''
        items.append({
            'id': did,
            'nome': uc.get('nome') or r.get('nome_referencia') or f"Distribuidor {did}",
            'nome_referencia': r.get('nome_referencia') or uc.get('nome') or '',
            'cnpj_referencia': cnpj_ref,
            'cnpjs_uc': uc.get('cnpjs') or ([cnpj_ref] if cnpj_ref else []),
            'compras': uc.get('compras') or [],
            'in_uc': bool(uc),
            'is_active': True,
            'notes': r.get('notes') or '',
            'created_by': r.get('created_by') or '',
            'created_ms': r.get('created_ms'),
            'updated_by': r.get('updated_by') or '',
            'updated_ms': r.get('updated_ms'),
        })
    items.sort(key=lambda d: (d['nome'].casefold(), int(d['id'])))
    candidates = []
    for did, uc in uc_groups.items():
        if did not in active_ids:
            candidates.append({
                'id': did,
                'nome': uc.get('nome') or f"Distribuidor {did}",
                'cnpj': uc.get('cnpj') or '',
                'cnpjs': uc.get('cnpjs') or [],
                'compras': uc.get('compras') or [],
            })
    candidates.sort(key=lambda d: (d['nome'].casefold(), int(d['id'])))
    return {'items': items, 'candidates': candidates}

@app.route('/api/admin/distribuidores-portal', methods=['GET'])
@require_role()
def api_admin_portal_dists_list():
    try:
        return jsonify(_build_portal_dists_payload())
    except Exception as e:
        app.logger.error(f"[portal_dists_list] {e}")
        return jsonify({'error': 'Falha ao carregar os distribuidores do portal', 'items': [], 'candidates': []}), 500

@app.route('/api/admin/distribuidores-portal', methods=['POST'])
@require_role()
def api_admin_portal_dists_add():
    body = _json_body()
    actor = request.admin_email
    raw_ids = body.get('ids') if isinstance(body.get('ids'), list) else [body.get('id')]
    clean_ids = sorted({str(int(str(x).strip())) for x in raw_ids if str(x or '').strip().isdigit() and int(str(x).strip()) > 0}, key=int)
    if not clean_ids:
        return jsonify({'error': 'Selecione ao menos um distribuidor válido (ID > 0)'}), 400
    notes = str(body.get('notes') or '').strip()[:500]
    custom_nome = str(body.get('nome_referencia') or '').strip()[:200]
    custom_cnpj = normalize_cnpj(body.get('cnpj_referencia'))

    try:
        uc_groups = {g_item['id']: g_item for g_item in get_all_uc_distributor_groups() if g_item.get('id')}
        cur_rows = list(get_portal_dists_rows())
        by_id = {r['id']: dict(r) for r in cur_rows}
        now_ms = int(time.time() * 1000)

        values_sql = []
        params = {'actor': actor, 'notes': notes}
        audit_items = []
        for idx, did in enumerate(clean_ids):
            uc = uc_groups.get(did, {})
            nome_ref = (custom_nome if len(clean_ids) == 1 and custom_nome else '') or uc.get('nome') or f"Distribuidor {did}"
            cnpj_ref = (custom_cnpj if len(clean_ids) == 1 and custom_cnpj else '') or uc.get('cnpj') or ''
            params[f'id_{idx}'] = int(did)
            params[f'nm_{idx}'] = nome_ref
            params[f'cj_{idx}'] = cnpj_ref
            values_sql.append(f"(CAST(:id_{idx} AS INT), :nm_{idx}, NULLIF(:cj_{idx}, ''))")
            audit_items.append((did, nome_ref))
            if did in by_id:
                by_id[did]['is_active'] = True
                if nome_ref:
                    by_id[did]['nome_referencia'] = nome_ref
                if cnpj_ref:
                    by_id[did]['cnpj_referencia'] = cnpj_ref
                if notes:
                    by_id[did]['notes'] = notes
                by_id[did]['updated_by'] = actor
                by_id[did]['updated_ms'] = now_ms
            else:
                by_id[did] = {
                    'id': did,
                    'nome_referencia': nome_ref,
                    'cnpj_referencia': cnpj_ref,
                    'is_active': True,
                    'notes': notes,
                    'created_by': actor,
                    'created_ms': now_ms,
                    'updated_by': actor,
                    'updated_ms': now_ms,
                }

        updated_rows = list(by_id.values())
        set_in_cache('portal_dists_rows', updated_rows)
        set_in_cache('portal_dist_ids', sorted({x['id'] for x in updated_rows if x['is_active']}, key=int))
        invalidate_portal_dist_cache(keep_rows=True)

        def _bg_merge():
            try:
                execute_sql(f"""
                    MERGE INTO {_PORTAL_DIST_TBL} t
                    USING (SELECT * FROM VALUES {', '.join(values_sql)} AS v(id_distribuidor, nome_referencia, cnpj_referencia)) s
                    ON t.id_distribuidor = s.id_distribuidor
                    WHEN MATCHED THEN UPDATE SET
                        is_active = TRUE,
                        nome_referencia = COALESCE(NULLIF(s.nome_referencia, ''), t.nome_referencia),
                        cnpj_referencia = COALESCE(s.cnpj_referencia, t.cnpj_referencia),
                        notes = CASE WHEN :notes <> '' THEN :notes ELSE t.notes END,
                        updated_by = :actor,
                        updated_at = from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo')
                    WHEN NOT MATCHED THEN INSERT
                        (id_distribuidor, nome_referencia, cnpj_referencia, is_active, notes, created_by, created_at, updated_by, updated_at)
                    VALUES
                        (s.id_distribuidor, s.nome_referencia, s.cnpj_referencia, TRUE, NULLIF(:notes, ''), :actor, from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo'), :actor, from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo'))
                """, params, timeout=120)
            except Exception as e:
                app.logger.error(f"[portal_dists_add bg] {e}")
                invalidate_portal_dist_cache(keep_rows=False)

        import threading
        threading.Thread(target=_bg_merge, daemon=True).start()
    except Exception as e:
        app.logger.error(f"[portal_dists_add] {e}")
        return jsonify({'error': 'Falha ao liberar distribuidor no portal'}), 500

    for did, nome_ref in audit_items:
        det = f"{nome_ref} (ID {did})" + (f" | {notes}" if notes else '')
        _audit_safe(actor, 'PORTAL_DIST_ENABLE', f"ID:{did}", None, 'PORTAL_ATIVO', det)
    payload = _build_portal_dists_payload()
    payload.update({'ok': True, 'added': len(clean_ids), 'audit_error': None})
    return jsonify(payload)

@app.route('/api/admin/distribuidores-portal/<int:dist_id>', methods=['PATCH'])
@require_role()
def api_admin_portal_dists_toggle(dist_id):
    if dist_id <= 0:
        return jsonify({'error': 'ID de distribuidor inválido'}), 400
    body = _json_body()
    actor = request.admin_email
    sid = str(dist_id)
    try:
        cur_rows = list(get_portal_dists_rows())
        by_id = {r['id']: dict(r) for r in cur_rows}
        cur = by_id.get(sid)
        if not cur:
            return jsonify({'error': 'Distribuidor não encontrado na lista do portal'}), 404
        cur_active = bool(cur.get('is_active'))
        new_active = cur_active if body.get('is_active') is None else bool(body.get('is_active'))
        notes_passed = 'notes' in body
        new_notes = str(body.get('notes') or '').strip()[:500] if notes_passed else (cur.get('notes') or '')

        if cur_active and not new_active:
            active_ids = [x['id'] for x in by_id.values() if x.get('is_active')]
            if len(active_ids) <= 1 and sid in active_ids and not body.get('force_last'):
                return jsonify({
                    'error': 'Este é o último distribuidor ativo no portal. Se desativá-lo, o portal ficará sem dados para todos os usuários.',
                    'last_active': True
                }), 409

        cur['is_active'] = new_active
        cur['notes'] = new_notes
        cur['updated_by'] = actor
        cur['updated_ms'] = int(time.time() * 1000)

        updated_rows = list(by_id.values())
        set_in_cache('portal_dists_rows', updated_rows)
        set_in_cache('portal_dist_ids', sorted({x['id'] for x in updated_rows if x['is_active']}, key=int))
        invalidate_portal_dist_cache(keep_rows=True)

        def _bg_update():
            try:
                execute_sql(f"""
                    UPDATE {_PORTAL_DIST_TBL}
                    SET is_active = :act,
                        notes = NULLIF(:notes, ''),
                        updated_by = :actor,
                        updated_at = from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo')
                    WHERE id_distribuidor = CAST(:id AS INT)
                """, {'act': 'true' if new_active else 'false', 'notes': new_notes, 'actor': actor, 'id': dist_id}, timeout=120)
            except Exception as e:
                app.logger.error(f"[portal_dists_toggle bg] {e}")
                invalidate_portal_dist_cache(keep_rows=False)

        import threading
        threading.Thread(target=_bg_update, daemon=True).start()
    except Exception as e:
        app.logger.error(f"[portal_dists_toggle] {e}")
        return jsonify({'error': 'Falha ao atualizar distribuidor do portal'}), 500

    uc_groups = {g_item['id']: g_item for g_item in get_all_uc_distributor_groups() if g_item.get('id')}
    nome_exib = (uc_groups.get(sid) or {}).get('nome') or cur.get('nome_referencia') or f"Distribuidor {sid}"
    if new_active != cur_active:
        action = 'PORTAL_DIST_ENABLE' if new_active else 'PORTAL_DIST_DISABLE'
        old_r = 'PORTAL_ATIVO' if cur_active else 'PORTAL_INATIVO'
        new_r = 'PORTAL_ATIVO' if new_active else 'PORTAL_INATIVO'
    else:
        action = 'PORTAL_DIST_NOTES'
        old_r = 'PORTAL_ATIVO' if cur_active else 'PORTAL_INATIVO'
        new_r = old_r
    det = f"{nome_exib} (ID {sid})" + (f" | {new_notes}" if new_notes else '')
    _audit_safe(actor, action, f"ID:{sid}", old_r, new_r, det)
    payload = _build_portal_dists_payload()
    payload.update({'ok': True, 'id': sid, 'is_active': new_active, 'notes': new_notes, 'audit_error': None})
    return jsonify(payload)

# ─── Histórico de Uso do Portal (tbl_log_app_access) ────────────────────────────
@app.route('/api/admin/uso-portal', methods=['GET'])
@require_role()
def api_admin_uso_portal():
    ano_raw = str(request.args.get('ano') or '').strip()
    mes_raw = str(request.args.get('mes') or '').strip()
    dia_raw = str(request.args.get('dia') or '').strip()
    anos = [int(x.strip()) for x in ano_raw.split(',') if re.match(r'^\d{4}$', x.strip())]
    meses = [int(x.strip()) for x in mes_raw.split(',') if re.match(r'^\d{1,2}$', x.strip()) and 1 <= int(x.strip()) <= 12]
    dias = [int(x.strip()) for x in dia_raw.split(',') if re.match(r'^\d{1,2}$', x.strip()) and 1 <= int(x.strip()) <= 31]
    where_parts = ["source = 'APP'"]
    if anos:
        where_parts.append(f"YEAR(event_date) IN ({','.join(map(str, anos))})")
    if meses:
        where_parts.append(f"MONTH(event_date) IN ({','.join(map(str, meses))})")
    if dias:
        where_parts.append(f"DAY(event_date) IN ({','.join(map(str, dias))})")
    where_sql = " AND ".join(where_parts)

    try:
        log_rows = execute_sql(f"""
            SELECT user_email, role, perfil, pagina, dist_ids,
                   unix_millis(to_utc_timestamp(event_ts, 'America/Sao_Paulo')) AS event_ms,
                   CAST(event_date AS STRING) AS event_date
            FROM {_ACCESS_LOG_TBL}
            WHERE {where_sql}
            ORDER BY event_ts DESC
            LIMIT 5000
        """)
    except Exception as e:
        app.logger.error(f"[uso_portal] {e}")
        return jsonify({'error': 'Falha ao carregar dados de uso do portal'}), 500

    active_groups = {g_item['id']: g_item['nome'] for g_item in get_active_distributor_groups() if g_item.get('id')}
    daily_agg = {}

    for r in log_rows:
        em = str(r.get('user_email') or '').lower().strip()
        if not em:
            continue
        perfil = str(r.get('perfil') or 'distribuidor').lower()
        role = str(r.get('role') or '')
        ems = int(r.get('event_ms') or 0)
        ev_date = str(r.get('event_date') or '')[:10]
        if not ev_date and ems:
            ev_date = datetime.fromtimestamp(ems / 1000.0, tz=timezone(timedelta(hours=-3))).strftime('%Y-%m-%d')
        if not ev_date:
            continue
        dids = [x.strip() for x in str(r.get('dist_ids') or '').split(',') if x.strip()]

        key = (em, ev_date)
        entry = daily_agg.get(key)
        if not entry:
            try:
                dia_num = int(ev_date[8:10])
            except (TypeError, ValueError, IndexError):
                dia_num = 0
            entry = {
                'data': ev_date,
                'dia': dia_num,
                'user_email': em,
                'perfil': perfil,
                'role': role,
                'dist_ids': set(),
                'ultimo_acesso_ms': ems,
                'total_acessos': 0,
            }
            daily_agg[key] = entry
        if ems > entry['ultimo_acesso_ms']:
            entry['ultimo_acesso_ms'] = ems
            entry['perfil'] = perfil
            if role:
                entry['role'] = role
        elif role and not entry['role']:
            entry['role'] = role
        entry['total_acessos'] += 1
        for d_id in dids:
            if d_id:
                entry['dist_ids'].add(d_id)

    rows_list = []
    for (_, _), u in daily_agg.items():
        all_dids = sorted(u['dist_ids'], key=lambda x: int(x) if x.isdigit() else 999999)
        d_nomes = [active_groups.get(x) or f"ID {x}" for x in all_dids]
        rows_list.append({
            'data': u['data'],
            'dia': u['dia'],
            'user_email': u['user_email'],
            'perfil': u['perfil'],
            'role': u['role'],
            'dist_ids': all_dids,
            'dist_nomes': d_nomes,
            'ultimo_acesso_ms': u['ultimo_acesso_ms'],
            'total_acessos': u['total_acessos'],
        })
    rows_list.sort(key=lambda x: (-int(x['data'].replace('-', '') or 0), -x['ultimo_acesso_ms'], x['user_email']))

    return jsonify({
        'ano': ano_raw,
        'mes': mes_raw,
        'dia': dia_raw,
        'rows': rows_list,
    })

@app.route('/api/admin/auditoria')
@require_role()
def api_admin_auditoria():
    try:
        limit = max(1, min(int(request.args.get('limit', 300)), 1000))
    except ValueError:
        limit = 300
    try:
        rows = execute_sql(f"""
            SELECT event_id, unix_millis(event_ts) AS event_ms, actor_email, action, target_email,
                   old_role, new_role, details, source
            FROM {_AUDIT_TBL}
            ORDER BY event_ts DESC
            LIMIT {limit}
        """)
    except Exception as e:
        app.logger.error(f"[auditoria] {e}")
        return jsonify({'error': 'Falha ao carregar o histórico'}), 500
    return jsonify({'items': rows})

# ─── Aquecimento e Keep-Alive do SQL Warehouse ────────────────────────────────────────────
# Dispara SELECT 1 + pré-carga de permissões/distribuidores no start e a cada 10 min em background
# (auto_stop do warehouse PRO é 15 min), evitando cold start de 4 min e tela "Preparando o portal".
import threading
_WARM_LOCK = threading.Lock()
_KEEPALIVE_INTERVAL_SEC = int(os.environ.get('WAREHOUSE_KEEPALIVE_SEC', '600'))

def _warm_warehouse_async():
    if not _WARM_LOCK.acquire(blocking=False):
        return
    def run():
        try:
            execute_sql("SELECT 1", timeout=600)
            with ThreadPoolExecutor(max_workers=4) as ex:
                ex.submit(preload_admin_roles, 60)
                ex.submit(get_portal_dists_rows)
                ex.submit(get_last_job_execution)
                ex.submit(_get_filtros_global_catalog)
            get_active_distributor_groups()
            app.logger.info("[warmup] SQL Warehouse pronto e caches aquecidos")
        except Exception as e:
            app.logger.warning(f"[warmup] falhou: {e}")
        finally:
            _WARM_LOCK.release()
    threading.Thread(target=run, daemon=True).start()

def _start_keepalive_loop():
    if _KEEPALIVE_INTERVAL_SEC <= 0:
        return
    def loop():
        while True:
            time.sleep(_KEEPALIVE_INTERVAL_SEC)
            try:
                _warm_warehouse_async()
            except Exception as e:
                app.logger.warning(f"[keepalive] {e}")
    threading.Thread(target=loop, daemon=True).start()

_warm_warehouse_async()
_start_keepalive_loop()

# ─── MÓDULOS NOVOS: PRODUTOS, CAMPANHAS, SUPORTE E TREINAMENTOS TRADE ───────
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

def _read_local_json(filename):
    fpath = os.path.join(_DATA_DIR, filename)
    if os.path.exists(fpath):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            app.logger.error(f"Erro ao ler {filename}: {e}")
    return {}

def _write_local_json(filename, data):
    fpath = os.path.join(_DATA_DIR, filename)
    try:
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        app.logger.error(f"Erro ao salvar {filename}: {e}")
        return False

@app.route('/api/produtos', methods=['GET'])
def api_produtos():
    data = _read_local_json('produtos_catalogo.json')
    prods = data.get('produtos', [])
    q = request.args.get('q', '').strip().lower()
    fam = request.args.get('familia', '').strip().lower()
    tag = request.args.get('tag', '').strip().lower()

    filtered = prods
    if fam:
        filtered = [p for p in filtered if p.get('familia', '').lower() == fam]
    if tag:
        filtered = [p for p in filtered if str(p.get('tag', '')).lower() == tag]
    if q:
        filtered = [p for p in filtered if q in p.get('nome', '').lower() or q in p.get('sku', '') or q in p.get('destaque_comercial', '').lower()]

    return jsonify({
        'versao': data.get('versao'),
        'total': len(filtered),
        'produtos': filtered
    })

@app.route('/api/produtos/<sku>/download', methods=['GET'])
def api_produtos_download(sku):
    tipo = request.args.get('tipo', 'ficha')
    content = f"BIMBO QSR BRASIL - DOCUMENTO TECNICO OFICIAL\nSKU: {sku}\nTipo: {tipo}\nGerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    res = Response(content, mimetype='text/plain')
    res.headers['Content-Disposition'] = f'attachment; filename="bimbo_qsr_{sku}_{tipo}.txt"'
    return res

@app.route('/api/campanhas', methods=['GET'])
def api_campanhas():
    data = _read_local_json('campanhas_ativas.json')
    return jsonify(data)

@app.route('/api/suporte', methods=['GET'])
def api_suporte_list():
    data = _read_local_json('suporte_chamados.json')
    is_admin = g.get('is_admin', True)
    active_id = g.get('active_dist_id')
    chamados = data.get('chamados', [])
    if not is_admin and active_id:
        chamados = [c for c in chamados if str(c.get('dist_id')) == str(active_id)]
    return jsonify({
        'versao': data.get('versao'),
        'categorias': data.get('categorias_disponiveis', []),
        'chamados': chamados
    })

@app.route('/api/suporte/novo', methods=['POST'])
def api_suporte_novo():
    body = request.get_json(silent=True) or request.form.to_dict() or {}
    assunto = body.get('assunto', '').strip()
    categoria = body.get('categoria', '').strip()
    mensagem = body.get('mensagem', '').strip()
    pedido_sap = body.get('pedido_sap', '').strip()

    if not assunto or not mensagem or not categoria:
        return jsonify({'error': 'Assunto, categoria e mensagem são obrigatórios'}), 400

    data = _read_local_json('suporte_chamados.json')
    chamados = data.get('chamados', [])
    novo_prot = f"BQ-2026-{len(chamados) + 1:04d}"
    dist_nome = g.get('user_name', 'Distribuidor')
    dist_id = g.get('active_dist_id', 1)

    novo_chamado = {
        'protocolo': novo_prot,
        'dist_id': dist_id,
        'dist_nome': dist_nome,
        'categoria': categoria,
        'assunto': assunto,
        'pedido_sap': pedido_sap,
        'status': 'aberto',
        'prioridade': 'normal',
        'data_abertura': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'ultima_atualizacao': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'sla_limite': (datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S'),
        'mensagens': [
            {
                'autor': dist_nome,
                'tipo': 'distribuidor',
                'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'texto': mensagem
            }
        ]
    }
    chamados.insert(0, novo_chamado)
    data['chamados'] = chamados
    _write_local_json('suporte_chamados.json', data)
    return jsonify({'success': True, 'chamado': novo_chamado})

@app.route('/api/treinamentos', methods=['GET'])
def api_treinamentos():
    data = _read_local_json('academia_trade.json')
    return jsonify(data)

@app.route('/api/treinamentos/concluir', methods=['POST'])
def api_treinamentos_concluir():
    body = request.get_json(silent=True) or request.form.to_dict() or {}
    mod_id = body.get('modulo_id')
    data = _read_local_json('academia_trade.json')
    for trilha in data.get('trilhas', []):
        for mod in trilha.get('modulos', []):
            if mod.get('id') == mod_id:
                mod['concluido'] = True
    _write_local_json('academia_trade.json', data)
    return jsonify({'success': True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT') or os.environ.get('DATABRICKS_APP_PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
