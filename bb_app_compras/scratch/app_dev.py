"""PORTAL COMPRAS — Procurement Intelligence
Flask backend using Lakebase PostgreSQL (direct connection).
"""
import base64
import csv
import io
import logging
import os
import time
import json
import uuid
import threading
from datetime import date, timedelta, datetime
from decimal import Decimal
from flask import Flask, jsonify, request, send_from_directory, Response
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None
from databricks.sdk import WorkspaceClient


class CustomJSONProvider(DefaultJSONProvider):
    """Handle Decimal serialization from PostgreSQL."""
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
_log = logging.getLogger("compras360")

# ── Databricks SDK Client ─────────────────────────────────────────────────────
_w = WorkspaceClient()
_PG_HOST = os.getenv("PGHOST", "ep-wispy-wildflower-e5pbme5k.database.brazilsouth.azuredatabricks.net")
_PG_DATABASE = os.getenv("PGDATABASE", "databricks_postgres")
_PG_USER = os.getenv("PGUSER", "")
_PG_PORT = int(os.getenv("PGPORT", "5432"))
_PG_SCHEMA = "compras"

# Token refresh state
_pg_token = None
_pg_token_time = 0
_token_lock = threading.Lock()


_LAKEBASE_ENDPOINT = os.getenv("LAKEBASE_ENDPOINT", "projects/compras-360/branches/production/endpoints/primary")

def _refresh_token():
    """Get or refresh Lakebase OAuth token (valid ~1h, refresh every 45min)."""
    global _pg_token, _pg_token_time
    with _token_lock:
        if _pg_token and (time.time() - _pg_token_time) < 2700:  # 45 min
            return _pg_token
        try:
            cred = _w.api_client.do("POST", "/api/2.0/postgres/credentials", body={
                "endpoint": _LAKEBASE_ENDPOINT
            })
            _pg_token = cred.get("token", "")
            _pg_token_time = time.time()
            _log.info("Lakebase token refreshed")
            return _pg_token
        except Exception as e:
            _log.error("Token refresh failed: %s", e)
            return _pg_token or ""


def _get_conn():
    """Get a PostgreSQL connection with fresh token."""
    token = _refresh_token()
    return psycopg2.connect(
        host=_PG_HOST,
        database=_PG_DATABASE,
        user=_PG_USER,
        password=token,
        port=_PG_PORT,
        sslmode="require",
        options=f"-c search_path={_PG_SCHEMA}"
    )


# Resolve PGUSER dynamically if not set (injected by platform when postgres resource is configured)
if not _PG_USER:
    try:
        me = _w.current_user.me()
        _PG_USER = me.user_name
        _log.info("Resolved PGUSER dynamically: %s", _PG_USER)
    except Exception as e:
        _log.warning("Could not resolve PGUSER: %s", e)

_log.info("Lakebase config: host=%s schema=%s user=%s", _PG_HOST, _PG_SCHEMA, _PG_USER)

app = Flask(__name__, static_folder='.')
app.json_provider_class = CustomJSONProvider
app.json = CustomJSONProvider(app)
CORS(app)


def query(sql_text, params=None):
    """Execute SQL on Lakebase PostgreSQL and return list of dicts."""
    global _pg_token
    for attempt in range(2):
        try:
            conn = _get_conn()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql_text)
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            err_msg = str(e).lower()
            if attempt == 0 and ("authorization failed" in err_msg or "authentication failed" in err_msg or "password" in err_msg):
                _log.warning("Auth failure detected, invalidating token and retrying: %s", str(e)[:150])
                with _token_lock:
                    _pg_token = None
                continue
            _log.error("Query exception: %s | Query: %s", str(e)[:300], sql_text[:200])
            return []


def query_debug(sql_text):
    """Like query() but returns (rows, error_str). Never raises."""
    global _pg_token
    for attempt in range(2):
        try:
            conn = _get_conn()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql_text)
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            conn.close()
            return rows, None
        except Exception as e:
            err_msg = str(e).lower()
            if attempt == 0 and ("authorization failed" in err_msg or "authentication failed" in err_msg or "password" in err_msg):
                _log.warning("Auth failure in query_debug, invalidating token and retrying: %s", str(e)[:150])
                with _token_lock:
                    _pg_token = None
                continue
            _log.error("Query exception: %s | SQL: %s", str(e)[:300], sql_text[:200])
            return [], str(e)[:300]


@app.route('/api/health')
def api_health():
    """Diagnóstico de conexão com o Lakebase PostgreSQL."""
    rows, err = query_debug("SELECT 1 as ok, current_user, current_database()")
    test_rows, test_err = query_debug("SELECT COUNT(*) as total FROM notas_ri")
    return jsonify({
        "status": "connected" if not err else "error",
        "pg_user_resolved": _PG_USER,
        "pg_host": _PG_HOST,
        "pg_database": _PG_DATABASE,
        "lakebase_endpoint": _LAKEBASE_ENDPOINT,
        "connection_test": rows,
        "connection_error": err,
        "table_test": test_rows,
        "table_error": test_err
    })


# ── Filter Helpers ────────────────────────────────────────────────────────────

def _esc(val):
    """Escape a string value for safe SQL interpolation."""
    return str(val).replace("'", "''")


def _parse_filters(args, date_col="DATA_LANCAMENTO", table_prefix="", empresa_col="EMPRESA", grupo_col="GRUPO_COMPRAS", fornecedor_col="NOME_FORNECEDOR", unidade_col="PLANTA"):
    """Parse common filter parameters. Returns (clauses[], params=[]).
    All values are inlined directly in SQL (Statement Execution API has no params)."""
    clauses = []
    p = f"{table_prefix}." if table_prefix else ""

    # Date filters
    ano = [a.strip() for a in args.getlist('ano') if a.strip()]
    mes = [m.strip() for m in args.getlist('mes') if m.strip()]
    dia = [d.strip() for d in args.getlist('dia') if d.strip()]
    dt_ini = args.get('dt_ini', '').strip()
    dt_fim = args.get('dt_fim', '').strip()

    if ano:
        vals = ','.join([f"'{_esc(a)}'" for a in ano])
        clauses.append(f"SUBSTRING({p}{date_col}, 1, 4) IN ({vals})")
    if mes:
        vals = ','.join([m for m in mes])
        clauses.append(f"CAST(SUBSTRING({p}{date_col}, 6, 2) AS INT) IN ({vals})")
    if dia:
        vals = ','.join([d for d in dia])
        clauses.append(f"CAST(SUBSTRING({p}{date_col}, 9, 2) AS INT) IN ({vals})")
    if dt_ini and not ano:
        clauses.append(f"{p}{date_col} >= '{_esc(dt_ini)}'")
    if dt_fim and not ano:
        clauses.append(f"{p}{date_col} <= '{_esc(dt_fim)}'")

    # Entity filters
    empresa = [e.strip() for e in args.getlist('empresa') if e.strip()]
    if empresa:
        vals = ','.join([f"'{_esc(e)}'" for e in empresa])
        clauses.append(f"{p}{empresa_col} IN ({vals})")

    grupo = [g.strip() for g in args.getlist('grupo_compras') if g.strip()]
    if grupo:
        vals = ','.join([f"'{_esc(g)}'" for g in grupo])
        clauses.append(f"{p}{grupo_col} IN ({vals})")

    fornecedor = [f_.strip() for f_ in args.getlist('fornecedor') if f_.strip()]
    if fornecedor:
        vals = ','.join([f"'{_esc(f_)}'" for f_ in fornecedor])
        clauses.append(f"{p}NOME_FORNECEDOR IN ({vals})")

    unidade = [u.strip() for u in args.getlist('unidade') if u.strip()]
    if unidade:
        vals = ','.join([f"'{_esc(u)}'" for u in unidade])
        clauses.append(f"{p}{unidade_col} IN ({vals})")

    # Advanced filters
    macro_categoria = [v.strip() for v in args.getlist('macro_categoria') if v.strip()]
    if macro_categoria:
        vals = ','.join([f"'{_esc(v)}'" for v in macro_categoria])
        clauses.append(f"COALESCE({p}MACRO_CATEGORIA, 'Indiretos') IN ({vals})")
    ord_macro_categoria = [v.strip() for v in args.getlist('ord_macro_categoria') if v.strip()]
    if ord_macro_categoria:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_macro_categoria])
        clauses.append(f"COALESCE({p}macro_categoria, 'Indiretos') IN ({vals})")
    numero_ri = [v.strip() for v in args.getlist('numero_ri') if v.strip()]
    if numero_ri:
        vals = ','.join([f"'{_esc(v)}'" for v in numero_ri])
        clauses.append(f"{p}NUMERO_RI IN ({vals})")
    nota_fiscal = [v.strip() for v in args.getlist('nota_fiscal') if v.strip()]
    if nota_fiscal:
        vals = ','.join([f"'{_esc(v)}'" for v in nota_fiscal])
        clauses.append(f"{p}NOTA_FISCAL IN ({vals})")
    numero_oc_f = [v.strip() for v in args.getlist('numero_oc') if v.strip()]
    if numero_oc_f:
        vals = ','.join([f"'{_esc(v)}'" for v in numero_oc_f])
        clauses.append(f"{p}NUMERO_OC IN ({vals})")
    ds_item = [v.strip() for v in args.getlist('ds_item') if v.strip()]
    if ds_item:
        vals = ','.join([f"'{_esc(v)}'" for v in ds_item])
        clauses.append(f"{p}DS_ITEM IN ({vals})")
    cnpj_bimbo = [v.strip() for v in args.getlist('cnpj_bimbo') if v.strip()]
    if cnpj_bimbo:
        vals = ','.join([f"'{_esc(v)}'" for v in cnpj_bimbo])
        clauses.append(f"{p}CNPJ_BIMBO IN ({vals})")
    codigo_item = [v.strip() for v in args.getlist('codigo_item') if v.strip()]
    if codigo_item:
        vals = ','.join([f"'{_esc(v)}'" for v in codigo_item])
        clauses.append(f"{p}CODIGO_ITEM IN ({vals})")
    descricao_item = [v.strip() for v in args.getlist('descricao_item') if v.strip()]
    if descricao_item:
        vals = ','.join([f"'{_esc(v)}'" for v in descricao_item])
        clauses.append(f"{p}DESCRICAO_ITEM IN ({vals})")
    centralizado = [v.strip() for v in args.getlist('centralizado') if v.strip()]
    if centralizado:
        vals = ','.join([f"'{_esc(v)}'" for v in centralizado])
        clauses.append(f"{p}CENTRALIZADO IN ({vals})")
    status_pgto = [v.strip() for v in args.getlist('status_pagamento') if v.strip()]
    if status_pgto:
        vals = ','.join([f"'{_esc(v)}'" for v in status_pgto])
        clauses.append(f"{p}STATUS_PAGAMENTO IN ({vals})")
    tipo_nf = [v.strip() for v in args.getlist('tipo_nf') if v.strip()]
    if tipo_nf:
        vals = ','.join([f"'{_esc(v)}'" for v in tipo_nf])
        clauses.append(f"{p}TIPO_NF IN ({vals})")
    is_forn_esp = [v.strip() for v in args.getlist('is_fornecedor_especial') if v.strip()]
    if is_forn_esp:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_esp])
        clauses.append(f"{p}IS_FORNECEDOR_ESPECIAL IN ({vals})")
    is_forn_nn = [v.strip() for v in args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"{p}IS_FORNECEDOR_NAO_NEGOCIAVEL IN ({vals})")
    # Requisicoes-specific filters
    req_requisicao = [v.strip() for v in args.getlist('req_requisicao') if v.strip()]
    if req_requisicao:
        vals = ','.join([f"'{_esc(v)}'" for v in req_requisicao])
        clauses.append(f"{p}REQUISICAO IN ({vals})")
    req_descricao = [v.strip() for v in args.getlist('req_descricao') if v.strip()]
    if req_descricao:
        vals = ','.join([f"'{_esc(v)}'" for v in req_descricao])
        clauses.append(f"{p}DESCRICAO_REQ IN ({vals})")
    req_numero_oc = [v.strip() for v in args.getlist('req_numero_oc') if v.strip()]
    if req_numero_oc:
        vals = ','.join([f"'{_esc(v)}'" for v in req_numero_oc])
        clauses.append(f"{p}NUMERO_OC IN ({vals})")
    req_status = [v.strip() for v in args.getlist('req_status') if v.strip()]
    if req_status:
        vals = ','.join([f"'{_esc(v)}'" for v in req_status])
        clauses.append(f"{p}STATUS IN ({vals})")
    req_status_ordem = [v.strip() for v in args.getlist('req_status_ordem') if v.strip()]
    if req_status_ordem:
        vals = ','.join([f"'{_esc(v)}'" for v in req_status_ordem])
        clauses.append(f"{p}STATUS_ORDEM IN ({vals})")
    # Ordens-specific advanced filters
    ord_numero_oc = [v.strip() for v in args.getlist('ord_numero_oc') if v.strip()]
    if ord_numero_oc:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_numero_oc])
        clauses.append(f"{p}NUMERO_OC IN ({vals})")
    ord_numero_acordo = [v.strip() for v in args.getlist('ord_numero_acordo') if v.strip()]
    if ord_numero_acordo:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_numero_acordo])
        clauses.append(f"{p}numero_acordo IN ({vals})")
    ord_item_aquisicao = [v.strip() for v in args.getlist('ord_item_aquisicao') if v.strip()]
    if ord_item_aquisicao:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_item_aquisicao])
        clauses.append(f"{p}item_aquisicao IN ({vals})")
    ord_comprador = [v.strip() for v in args.getlist('ord_comprador') if v.strip()]
    if ord_comprador:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_comprador])
        clauses.append(f"{p}nome_usuario IN ({vals})")
    ord_status_fech = [v.strip() for v in args.getlist('ord_status_fechamento') if v.strip()]
    if ord_status_fech:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_status_fech])
        clauses.append(f"{p}STATUS_FECHAMENTO IN ({vals})")
    ord_centralizado = [v.strip() for v in args.getlist('ord_centralizado') if v.strip()]
    if ord_centralizado:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_centralizado])
        clauses.append(f"{p}CENTRALIZADO IN ({vals})")
    ord_grupo_compras = [v.strip() for v in args.getlist('ord_grupo_compras') if v.strip()]
    if ord_grupo_compras:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_grupo_compras])
        clauses.append(f"{p}GRUPO_COMPRAS_OC IN ({vals})")
    comprador = [v.strip() for v in args.getlist('comprador') if v.strip()]
    if comprador:
        vals = ','.join([f"'{_esc(v)}'" for v in comprador])
        clauses.append(f"{p}CHAVE_OC_LINHA IN (SELECT DISTINCT CHAVE_OC_LINHA FROM ordens_compra WHERE nome_usuario IN ({vals}))")

    # Cross-filter: item (uses COALESCE to match chart label)
    item_cross = [v.strip() for v in args.getlist('item_cross') if v.strip()]
    if item_cross:
        vals = ','.join([f"'{_esc(v)}'" for v in item_cross])
        clauses.append(f"COALESCE({p}DESCRICAO_ITEM, {p}DS_ITEM, 'Sem descri\u00e7\u00e3o') IN ({vals})")
    # Cross-filter: categoria (uses COALESCE to match chart label)
    categoria_cross = [v.strip() for v in args.getlist('categoria_cross') if v.strip()]
    if categoria_cross:
        vals = ','.join([f"'{_esc(v)}'" for v in categoria_cross])
        clauses.append(f"COALESCE({p}CATEGORIA_ITEM, 'Sem categoria') IN ({vals})")
    # Cross-filter: macro_categoria
    macro_categoria_cross = [v.strip() for v in args.getlist('macro_categoria_cross') if v.strip()]
    if macro_categoria_cross:
        vals = ','.join([f"'{_esc(v)}'" for v in macro_categoria_cross])
        clauses.append(f"COALESCE({p}MACRO_CATEGORIA, 'Indiretos') IN ({vals})")
    # Cross-filter: tipo_vendor
    tipo_vendor_cross = [v.strip() for v in args.getlist('tipo_vendor_cross') if v.strip()]
    if tipo_vendor_cross:
        vals = ','.join([f"'{_esc(v)}'" for v in tipo_vendor_cross])
        clauses.append(f"COALESCE({p}TIPO_VENDOR, 'N\u00e3o classificado') IN ({vals})")

    # OC type filter: com_oc, sem_oc, or both (no filter)
    oc_type = [t.strip() for t in args.getlist('oc_type') if t.strip()]
    if oc_type and len(oc_type) == 1:
        if oc_type[0] == 'com_oc':
            clauses.append(f"{p}NUMERO_OC != 'Nota sem OC'")
        elif oc_type[0] == 'sem_oc':
            clauses.append(f"{p}NUMERO_OC = 'Nota sem OC'")
    # If both are selected or none, no filter applied (show all)

    return clauses, []


def _where(clauses):
    return "WHERE " + " AND ".join(clauses) if clauses else ""


# ── Governance: exclude OCs from buyers in "Compras" area ──────────────────────
# If the buyer belongs to the functional purchasing team (area='Compras' in
# compradores_funcionais), their OCs are inherently centralized and should NOT
# appear as "OC Descentralizada >30K" exceptions — even if notas_ri.CENTRALIZADO
# is incorrectly set to 'DESCENTRALIZADO' due to ETL inconsistency.
_EXCL_COMPRAS_OCS = """
    SELECT DISTINCT oc_x.numero_oc
    FROM ordens_compra oc_x
    INNER JOIN compradores_funcionais cf_x ON cf_x.usuario_oracle = oc_x.usuario
    WHERE cf_x.area = 'Compras' AND oc_x.numero_oc IS NOT NULL
"""

# OCs with a purchase agreement (numero_acordo) are effectively centralized
# and should NOT appear as "OC Descentralizada >30K" exceptions — even if
# CENTRALIZADO is set to 'DESCENTRALIZADO' due to ETL inconsistency.
_EXCL_ACORDO_OCS = """
    SELECT DISTINCT NUMERO_OC FROM ordens_compra
    WHERE numero_acordo IS NOT NULL AND numero_acordo != ''
      AND NUMERO_OC IS NOT NULL
"""


def _default_year_filter():
    """Default: current year."""
    return str(date.today().year)


def _parse_order_filters(args, skip_mes=False):
    """Parse filters for ordens_compra table. All fields from ordens_compra only."""
    clauses = []
    empresa = [e.strip() for e in args.getlist('empresa') if e.strip()]
    if empresa:
        vals = ','.join([f"'{_esc(e)}'" for e in empresa])
        clauses.append(f"org_desc IN ({vals})")
    ano = [a.strip() for a in args.getlist('ano') if a.strip()]
    if ano:
        vals = ','.join([f"'{_esc(a)}'" for a in ano])
        clauses.append(f"SUBSTRING(data_oc, 1, 4) IN ({vals})")
    if not skip_mes:
        mes = [m.strip() for m in args.getlist('mes') if m.strip()]
        if mes:
            vals = ','.join([m for m in mes])
            clauses.append(f"CAST(SUBSTRING(data_oc, 6, 2) AS INT) IN ({vals})")
    grupo = [g.strip() for g in args.getlist('grupo_compras') if g.strip()]
    if grupo:
        vals = ','.join([f"'{_esc(g)}'" for g in grupo])
        clauses.append(f"grupo_compras_oc IN ({vals})")
    fornecedor = [f_.strip() for f_ in args.getlist('fornecedor') if f_.strip()]
    if fornecedor:
        vals = ','.join([f"'{_esc(f_)}'" for f_ in fornecedor])
        clauses.append(f"nome_fornecedor IN ({vals})")
    is_forn_esp = [v.strip() for v in args.getlist('is_fornecedor_especial') if v.strip()]
    if is_forn_esp:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_esp])
        clauses.append(f"is_fornecedor_especial IN ({vals})")
    is_forn_nn = [v.strip() for v in args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"is_fornecedor_nao_negociavel IN ({vals})")
    # Advanced ordens_compra filters
    macro_categoria = [c.strip() for c in args.getlist('macro_categoria') if c.strip()]
    if macro_categoria:
        vals = ','.join([f"'{_esc(c)}'" for c in macro_categoria])
        clauses.append(f"COALESCE(macro_categoria, 'Indiretos') IN ({vals})")
    unidade = [u.strip() for u in args.getlist('unidade') if u.strip()]
    if unidade:
        vals = ','.join([f"'{_esc(u)}'" for u in unidade])
        clauses.append(f"unidade IN ({vals})")
    categoria_item = [c.strip() for c in args.getlist('categoria_item') if c.strip()]
    if categoria_item:
        vals = ','.join([f"'{_esc(c)}'" for c in categoria_item])
        clauses.append(f"categoria_item IN ({vals})")
    tipo_oc = [t.strip() for t in args.getlist('tipo_oc') if t.strip()]
    if tipo_oc:
        vals = ','.join([f"'{_esc(t)}'" for t in tipo_oc])
        clauses.append(f"tipo IN ({vals})")
    status_fech = [s.strip() for s in args.getlist('status_fechamento') if s.strip()]
    if status_fech:
        vals = ','.join([f"'{_esc(s)}'" for s in status_fech])
        clauses.append(f"status_fechamento IN ({vals})")
    status_aprov = [s.strip() for s in args.getlist('status_aprovacao') if s.strip()]
    if status_aprov:
        vals = ','.join([f"'{_esc(s)}'" for s in status_aprov])
        clauses.append(f"status_aprovacao IN ({vals})")
    return clauses


# ── Static Routes ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('.', filename)


# ═══════════════════════════════════════════════════════════════════════════════
# API: FILTER OPTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def _cascading_where(args, exclude_field=None, table='notas_ri'):
    """Build WHERE clauses for cascading filters, excluding one field.
    This implements Power BI-style cross-filtering: each dropdown shows only
    values that exist given the OTHER active filters."""
    clauses = []
    if table == 'notas_ri':
        date_col = 'DATA_LANCAMENTO'
        emp_col = 'EMPRESA'
        grupo_col = 'GRUPO_COMPRAS'
        forn_col = 'NOME_FORNECEDOR'
        unid_col = 'PLANTA'
    else:  # ordens_compra
        date_col = 'DATA_OC'
        emp_col = 'ORG_DESC'
        grupo_col = 'GRUPO_COMPRAS_OC'
        forn_col = 'NOME_FORNECEDOR'
        unid_col = 'UNIDADE'

    if exclude_field != 'ano':
        ano = [a.strip() for a in args.getlist('ano') if a.strip()]
        if ano:
            vals = ','.join([f"'{_esc(a)}'" for a in ano])
            clauses.append(f"SUBSTRING({date_col}, 1, 4) IN ({vals})")
    if exclude_field != 'mes':
        mes = [m.strip() for m in args.getlist('mes') if m.strip()]
        if mes:
            vals = ','.join([m for m in mes])
            clauses.append(f"CAST(SUBSTRING({date_col}, 6, 2) AS INT) IN ({vals})")
    if exclude_field != 'empresa':
        empresa = [e.strip() for e in args.getlist('empresa') if e.strip()]
        if empresa:
            vals = ','.join([f"'{_esc(e)}'" for e in empresa])
            clauses.append(f"{emp_col} IN ({vals})")
    if exclude_field != 'grupo_compras':
        grupo = [g.strip() for g in args.getlist('grupo_compras') if g.strip()]
        if grupo:
            vals = ','.join([f"'{_esc(g)}'" for g in grupo])
            clauses.append(f"{grupo_col} IN ({vals})")
    if exclude_field != 'fornecedor':
        fornecedor = [f_.strip() for f_ in args.getlist('fornecedor') if f_.strip()]
        if fornecedor:
            vals = ','.join([f"'{_esc(f_)}'" for f_ in fornecedor])
            clauses.append(f"{forn_col} IN ({vals})")
    if exclude_field != 'unidade' and table == 'notas_ri':
        unidade = [u.strip() for u in args.getlist('unidade') if u.strip()]
        if unidade:
            vals = ','.join([f"'{_esc(u)}'" for u in unidade])
            clauses.append(f"{unid_col} IN ({vals})")
    if exclude_field != 'is_fornecedor_especial':
        is_forn_esp = [v.strip() for v in args.getlist('is_fornecedor_especial') if v.strip()]
        if is_forn_esp:
            vals = ','.join([f"'{_esc(v)}'" for v in is_forn_esp])
            clauses.append(f"IS_FORNECEDOR_ESPECIAL IN ({vals})")
    if exclude_field != 'is_fornecedor_nao_negociavel':
        is_forn_nn = [v.strip() for v in args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
        if is_forn_nn:
            vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
            clauses.append(f"IS_FORNECEDOR_NAO_NEGOCIAVEL IN ({vals})")
    if exclude_field != 'macro_categoria':
        macro_cat = [v.strip() for v in args.getlist('macro_categoria') if v.strip()]
        if macro_cat:
            vals = ','.join([f"'{_esc(v)}'" for v in macro_cat])
            clauses.append(f"COALESCE(macro_categoria, 'Indiretos') IN ({vals})")
    return clauses


@app.route('/api/filters/cascading')
def filters_cascading():
    """Cascading filter options for notas_ri-based modules.
    Accepts current filter selections and returns filtered options for each dropdown.
    Power BI-style: each dimension shows only values that coexist with other active filters."""
    result = {}
    base_table = 'notas_ri'

    # Anos - filtered by other selections (excl. ano itself)
    w = _cascading_where(request.args, exclude_field='ano', table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['anos'] = [r['v'] for r in query(
        f"SELECT DISTINCT SUBSTRING(DATA_LANCAMENTO, 1, 4) AS v FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL {wc} ORDER BY v DESC"
    )]

    # Meses - filtered by other selections (excl. mes)
    w = _cascading_where(request.args, exclude_field='mes', table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['meses'] = [r['v'] for r in query(
        f"SELECT DISTINCT CAST(SUBSTRING(DATA_LANCAMENTO, 6, 2) AS INT) AS v FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL {wc} ORDER BY v"
    )]

    # Empresas - filtered by other selections (excl. empresa)
    w = _cascading_where(request.args, exclude_field='empresa', table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['empresas'] = [r['v'] for r in query(
        f"SELECT DISTINCT EMPRESA AS v FROM notas_ri WHERE EMPRESA IS NOT NULL AND EMPRESA != '' {wc} ORDER BY v"
    )]

    # Grupos - filtered by other selections (excl. grupo)
    w = _cascading_where(request.args, exclude_field='grupo_compras', table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['grupos'] = [r['v'] for r in query(
        f"SELECT DISTINCT GRUPO_COMPRAS AS v FROM notas_ri WHERE GRUPO_COMPRAS IS NOT NULL AND GRUPO_COMPRAS != '' AND GRUPO_COMPRAS != 'COMERCIAL' {wc} ORDER BY v"
    )]

    # Fornecedores - filtered by other selections (excl. fornecedor)
    w = _cascading_where(request.args, exclude_field='fornecedor', table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['fornecedores'] = [r['v'] for r in query(
        f"SELECT DISTINCT NOME_FORNECEDOR AS v FROM notas_ri WHERE NOME_FORNECEDOR IS NOT NULL AND NOME_FORNECEDOR != '' {wc} ORDER BY v"
    )]

    # Unidades (planta) - filtered by other selections (excl. unidade)
    w = _cascading_where(request.args, exclude_field='unidade', table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['unidades'] = [r['v'] for r in query(
        f"SELECT DISTINCT PLANTA AS v FROM notas_ri WHERE PLANTA IS NOT NULL AND PLANTA != '' {wc} ORDER BY v"
    )]

    return jsonify(result)


@app.route('/api/filters/cascading-ordens')
def filters_cascading_ordens():
    """Cascading filter options for ordens_compra module ONLY.
    All filters sourced exclusively from ordens_compra table using DATA_OC."""
    result = {}
    base_table = 'ordens_compra'

    # Anos from DATA_OC
    w = _cascading_where(request.args, exclude_field='ano', table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['anos'] = [r['v'] for r in query(
        f"SELECT DISTINCT SUBSTRING(DATA_OC, 1, 4) AS v FROM ordens_compra WHERE DATA_OC IS NOT NULL {wc} ORDER BY v DESC"
    )]

    # Meses from DATA_OC
    w = _cascading_where(request.args, exclude_field='mes', table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['meses'] = [r['v'] for r in query(
        f"SELECT DISTINCT CAST(SUBSTRING(DATA_OC, 6, 2) AS INT) AS v FROM ordens_compra WHERE DATA_OC IS NOT NULL {wc} ORDER BY v"
    )]

    # Empresas (ORG_DESC)
    w = _cascading_where(request.args, exclude_field='empresa', table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['empresas'] = [r['v'] for r in query(
        f"SELECT DISTINCT ORG_DESC AS v FROM ordens_compra WHERE ORG_DESC IS NOT NULL AND ORG_DESC != '' {wc} ORDER BY v"
    )]

    # Grupos (GRUPO_COMPRAS_OC)
    w = _cascading_where(request.args, exclude_field='grupo_compras', table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['grupos'] = [r['v'] for r in query(
        f"SELECT DISTINCT GRUPO_COMPRAS_OC AS v FROM ordens_compra WHERE GRUPO_COMPRAS_OC IS NOT NULL AND GRUPO_COMPRAS_OC != '' AND GRUPO_COMPRAS_OC != 'COMERCIAL' {wc} ORDER BY v"
    )]

    # Fornecedores
    w = _cascading_where(request.args, exclude_field='fornecedor', table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['fornecedores'] = [r['v'] for r in query(
        f"SELECT DISTINCT NOME_FORNECEDOR AS v FROM ordens_compra WHERE NOME_FORNECEDOR IS NOT NULL AND NOME_FORNECEDOR != '' {wc} ORDER BY v"
    )]

    # Unidades (planta OC) — sempre mostra todas, sem cascading
    result['unidades'] = [r['v'] for r in query(
        "SELECT DISTINCT UNIDADE AS v FROM ordens_compra WHERE UNIDADE IS NOT NULL AND UNIDADE != '' ORDER BY v"
    )]

    # Status Fechamento
    w = _cascading_where(request.args, exclude_field=None, table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['status'] = [r['v'] for r in query(
        f"SELECT DISTINCT STATUS_FECHAMENTO AS v FROM ordens_compra WHERE STATUS_FECHAMENTO IS NOT NULL {wc} ORDER BY v"
    )]

    # Status Aprovação
    result['status_aprovacao'] = [r['v'] for r in query(
        f"SELECT DISTINCT STATUS_APROVACAO AS v FROM ordens_compra WHERE STATUS_APROVACAO IS NOT NULL AND STATUS_APROVACAO != '' {wc} ORDER BY v"
    )]

    # Tipo OC
    result['tipo_oc'] = [r['v'] for r in query(
        f"SELECT DISTINCT TIPO AS v FROM ordens_compra WHERE TIPO IS NOT NULL AND TIPO != '' {wc} ORDER BY v"
    )]

    # Categoria Item
    result['categorias'] = [r['v'] for r in query(
        f"SELECT DISTINCT CATEGORIA_ITEM AS v FROM ordens_compra WHERE CATEGORIA_ITEM IS NOT NULL AND CATEGORIA_ITEM != '' {wc} ORDER BY v"
    )]

    # Macro Categoria
    result['macro_categorias'] = [r['v'] for r in query(
        f"SELECT DISTINCT COALESCE(macro_categoria, 'Indiretos') AS v FROM ordens_compra WHERE macro_categoria IS NOT NULL AND macro_categoria != '' {wc} ORDER BY v"
    )]

    # Comprador (nome_usuario)
    result['compradores'] = [r['v'] for r in query(
        f"SELECT DISTINCT nome_usuario AS v FROM ordens_compra WHERE nome_usuario IS NOT NULL AND nome_usuario != '' {wc} ORDER BY v"
    )]

    return jsonify(result)


@app.route('/api/filters/notas')
def filters_notas():
    """Get distinct filter values from notas_ri (initial load, no cascading)."""
    result = {}
    result['anos'] = [r['ano'] for r in query(
        "SELECT DISTINCT SUBSTRING(DATA_LANCAMENTO, 1, 4) AS ano FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL ORDER BY ano DESC"
    )]
    result['meses'] = [r['mes'] for r in query(
        "SELECT DISTINCT CAST(SUBSTRING(DATA_LANCAMENTO, 6, 2) AS INT) AS mes FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL ORDER BY mes"
    )]
    result['dias'] = [r['dia'] for r in query(
        "SELECT DISTINCT CAST(SUBSTRING(DATA_LANCAMENTO, 9, 2) AS INT) AS dia FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL ORDER BY dia"
    )]
    result['empresas'] = [r['empresa'] for r in query(
        "SELECT DISTINCT EMPRESA AS empresa FROM notas_ri WHERE EMPRESA IS NOT NULL AND EMPRESA != '' ORDER BY empresa"
    )]
    result['grupos'] = [r['grupo'] for r in query(
        "SELECT DISTINCT GRUPO_COMPRAS AS grupo FROM notas_ri WHERE GRUPO_COMPRAS IS NOT NULL AND GRUPO_COMPRAS != '' AND GRUPO_COMPRAS != 'COMERCIAL' ORDER BY grupo"
    )]
    result['fornecedores'] = [r['fornecedor'] for r in query(
        "SELECT DISTINCT NOME_FORNECEDOR AS fornecedor FROM notas_ri WHERE NOME_FORNECEDOR IS NOT NULL AND NOME_FORNECEDOR != '' ORDER BY fornecedor"
    )]
    result['unidades'] = [r['unidade'] for r in query(
        "SELECT DISTINCT PLANTA AS unidade FROM notas_ri WHERE PLANTA IS NOT NULL AND PLANTA != '' ORDER BY unidade"
    )]
    return jsonify(result)


@app.route('/api/filters/ordens')
def filters_ordens():
    """Get distinct filter values from ordens_compra, respecting active empresa/ano filters."""
    result = {}
    # Build contextual WHERE for fornecedor dropdown
    ctx_parts = []
    empresa = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    ano = [a.strip() for a in request.args.getlist('ano') if a.strip()]
    if empresa:
        vals = ','.join([f"'{_esc(e)}'" for e in empresa])
        ctx_parts.append(f"org_desc IN ({vals})")
    if ano:
        vals = ','.join([f"'{_esc(a)}'" for a in ano])
        ctx_parts.append(f"SUBSTRING(DATA_OC, 1, 4) IN ({vals})")
    ctx_where = "WHERE " + " AND ".join(ctx_parts) if ctx_parts else ""

    result['anos'] = [r['ano'] for r in query(
        "SELECT DISTINCT SUBSTRING(DATA_OC, 1, 4) AS ano FROM ordens_compra WHERE DATA_OC IS NOT NULL ORDER BY ano DESC"
    )]
    result['meses'] = [r['mes'] for r in query(
        "SELECT DISTINCT CAST(SUBSTRING(DATA_OC, 6, 2) AS INT) AS mes FROM ordens_compra WHERE DATA_OC IS NOT NULL ORDER BY mes"
    )]
    result['empresas'] = [r['empresa'] for r in query(
        "SELECT DISTINCT org_desc AS empresa FROM ordens_compra WHERE org_desc IS NOT NULL AND org_desc != '' ORDER BY empresa"
    )]
    result['grupos'] = [r['grupo'] for r in query(
        "SELECT DISTINCT GRUPO_COMPRAS_OC AS grupo FROM ordens_compra WHERE GRUPO_COMPRAS_OC IS NOT NULL AND GRUPO_COMPRAS_OC != '' AND GRUPO_COMPRAS_OC != 'COMERCIAL' ORDER BY grupo"
    )]
    # Fornecedores filtered by active empresa+ano context
    result['fornecedores'] = [r['fornecedor'] for r in query(
        f"SELECT DISTINCT nome_fornecedor AS fornecedor FROM ordens_compra {ctx_where} AND nome_fornecedor IS NOT NULL AND nome_fornecedor != '' ORDER BY fornecedor" if ctx_where else
        "SELECT DISTINCT nome_fornecedor AS fornecedor FROM ordens_compra WHERE nome_fornecedor IS NOT NULL AND nome_fornecedor != '' ORDER BY fornecedor"
    )]
    result['status'] = [r['st'] for r in query(
        "SELECT DISTINCT STATUS_FECHAMENTO AS st FROM ordens_compra WHERE STATUS_FECHAMENTO IS NOT NULL ORDER BY st"
    )]
    return jsonify(result)


@app.route('/api/filters/advanced')
def filters_advanced():
    """Advanced filter options from notas_ri — only low-cardinality fields.
    High-cardinality fields (numero_ri, nota_fiscal, numero_oc, ds_item,
    codigo_item, descricao_item) use /api/filters/search endpoint."""
    result = {}
    result['macro_categoria'] = [r['v'] for r in query(
        "SELECT DISTINCT COALESCE(MACRO_CATEGORIA, 'Indiretos') AS v FROM notas_ri WHERE MACRO_CATEGORIA IS NOT NULL AND MACRO_CATEGORIA != '' ORDER BY v"
    )]
    result['dias'] = [r['v'] for r in query(
        "SELECT DISTINCT CAST(SUBSTRING(DATA_LANCAMENTO, 9, 2) AS INT) AS v FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL ORDER BY v"
    )]
    result['centralizado'] = [r['v'] for r in query(
        "SELECT DISTINCT CENTRALIZADO AS v FROM notas_ri WHERE CENTRALIZADO IS NOT NULL AND CENTRALIZADO != '' ORDER BY v"
    )]
    result['unidade'] = [r['v'] for r in query(
        "SELECT DISTINCT PLANTA AS v FROM notas_ri WHERE PLANTA IS NOT NULL AND PLANTA != '' ORDER BY v"
    )]
    result['status_pagamento'] = [r['v'] for r in query(
        "SELECT DISTINCT STATUS_PAGAMENTO AS v FROM notas_ri WHERE STATUS_PAGAMENTO IS NOT NULL AND STATUS_PAGAMENTO != '' ORDER BY v"
    )]
    result['tipo_nf'] = [r['v'] for r in query(
        "SELECT DISTINCT TIPO_NF AS v FROM notas_ri WHERE TIPO_NF IS NOT NULL AND TIPO_NF != '' ORDER BY v"
    )]
    # High-cardinality: return empty (use /api/filters/search?field=X&q=term)
    result['numero_ri'] = []
    result['nota_fiscal'] = []
    result['numero_oc'] = []
    result['ds_item'] = []
    result['cnpj_bimbo'] = []
    result['codigo_item'] = []
    result['descricao_item'] = []
    return jsonify(result)


@app.route('/api/filters/search')
def filters_search():
    """Server-side search for high-cardinality filter fields.
    Query params: field (column name), q (search term, min 2 chars).
    Returns up to 100 matching distinct values."""
    field = request.args.get('field', '')
    q = request.args.get('q', '').strip()
    allowed_notas = {
        'numero_ri': ('NUMERO_RI', 'notas_ri'),
        'nota_fiscal': ('NOTA_FISCAL', 'notas_ri'),
        'numero_oc': ('NUMERO_OC', 'notas_ri'),
        'ds_item': ('DS_ITEM', 'notas_ri'),
        'cnpj_bimbo': ('CNPJ_BIMBO', 'notas_ri'),
        'codigo_item': ('CODIGO_ITEM', 'notas_ri'),
        'descricao_item': ('DESCRICAO_ITEM', 'notas_ri'),
        'req_requisicao': ('REQUISICAO', 'requisicoes'),
        'req_descricao': ('DESCRICAO_REQ', 'requisicoes'),
        'req_numero_oc': ('NUMERO_OC', 'requisicoes'),
        'ord_numero_oc': ('NUMERO_OC', 'ordens_compra'),
        'ord_numero_acordo': ('numero_acordo', 'ordens_compra'),
        'ord_item_aquisicao': ('item_aquisicao', 'ordens_compra'),
        'ord_comprador': ('nome_usuario', 'ordens_compra'),
    }
    entry = allowed_notas.get(field)
    if not entry:
        return jsonify({'error': 'invalid field'}), 400
    col, table = entry
    if len(q) < 2:
        return jsonify([])
    safe_q = q.replace("'", "''")
    rows = query(f"SELECT DISTINCT {col} AS v FROM {table} WHERE {col} ILIKE '%{safe_q}%' ORDER BY v LIMIT 100")
    return jsonify([r['v'] for r in rows])


@app.route('/api/filters/requisicoes-adv')
def filters_requisicoes_adv():
    """Advanced filter options for requisicoes — dropdown values for status fields."""
    result = {}
    result['status'] = [r['v'] for r in query(
        "SELECT DISTINCT STATUS AS v FROM requisicoes WHERE STATUS IS NOT NULL AND STATUS != '' ORDER BY v"
    )]
    result['status_ordem'] = [r['v'] for r in query(
        "SELECT DISTINCT STATUS_ORDEM AS v FROM requisicoes WHERE STATUS_ORDEM IS NOT NULL AND STATUS_ORDEM != '' ORDER BY v"
    )]
    return jsonify(result)


@app.route('/api/filters/ordens-adv')
def filters_ordens_adv():
    """Advanced filter options for ordens_compra — dropdown values for low-cardinality fields."""
    result = {}
    result['macro_categoria'] = [r['v'] for r in query(
        "SELECT DISTINCT COALESCE(macro_categoria, 'Indiretos') AS v FROM ordens_compra WHERE macro_categoria IS NOT NULL AND macro_categoria != '' ORDER BY v"
    )]
    result['status_fechamento'] = [r['v'] for r in query(
        "SELECT DISTINCT STATUS_FECHAMENTO AS v FROM ordens_compra WHERE STATUS_FECHAMENTO IS NOT NULL AND STATUS_FECHAMENTO != '' ORDER BY v"
    )]
    result['centralizado'] = [r['v'] for r in query(
        "SELECT DISTINCT CENTRALIZADO AS v FROM ordens_compra WHERE CENTRALIZADO IS NOT NULL AND CENTRALIZADO != '' ORDER BY v"
    )]
    result['grupo_compras'] = [r['v'] for r in query(
        "SELECT DISTINCT GRUPO_COMPRAS_OC AS v FROM ordens_compra WHERE GRUPO_COMPRAS_OC IS NOT NULL AND GRUPO_COMPRAS_OC != '' AND GRUPO_COMPRAS_OC != 'COMERCIAL' ORDER BY v"
    )]
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════════════
# API: PAGE 01 — PROCUREMENT PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/performance/kpis')
def performance_kpis():
    """Net Spend, Savings, Centralization %, Payment Term."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)

    # Build comparison period clauses
    ano = request.args.getlist('ano')
    mes = request.args.getlist('mes')

    sql = f"""
    SELECT
        SUM(VALOR_LIQUIDO_BRL)::float AS net_spend,
        SUM(VALOR_NOTA_BRL)::float AS gross_spend,
        SUM(SAVING_TOTAL)::float AS savings_total,
        (SUM(CASE WHEN CENTRALIZADO = 'CENTRALIZADO' THEN VALOR_LIQUIDO_BRL ELSE 0 END) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0) * 100)::float AS centralization_pct,
        (SUM(PGTO_X_VALOR) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0))::float AS avg_payment_term,
        (SUM(SAVING_TOTAL) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0) * 100)::float AS savings_pct
    FROM notas_ri
    {w}
    """
    current = query(sql, params)

    # Previous period for comparison (same-day-range logic):
    # - If year+month filtered: compare to PREVIOUS MONTH limited to same day
    #   e.g. if today is Aug 21, compare Aug 1-21 vs Jul 1-21
    # - If year only: compare current year up to today vs prev year up to same date
    #   e.g. Jan 1 - Aug 21, 2026 vs Jan 1 - Aug 21, 2025
    comp_clauses = []
    today = date.today()
    today_day = today.day

    if ano and mes:
        # Compare to previous month
        cur_year = int(ano[0])
        cur_month = int(mes[0])
        is_current_period = (cur_year == today.year and cur_month == today.month)
        if cur_month == 1:
            prev_m = 12
            prev_y = cur_year - 1
        else:
            prev_m = cur_month - 1
            prev_y = cur_year
        comp_clauses.append(f"SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{prev_y}'")
        comp_clauses.append(f"CAST(SUBSTRING(DATA_LANCAMENTO, 6, 2) AS INT) = {prev_m}")
        # Only cap to today's day if viewing the CURRENT month (fair partial-month comparison)
        if is_current_period:
            comp_clauses.append(f"CAST(SUBSTRING(DATA_LANCAMENTO, 9, 2) AS INT) <= {today_day}")
            clauses.append(f"CAST(SUBSTRING(DATA_LANCAMENTO, 9, 2) AS INT) <= {today_day}")
        # Re-run current query with updated clauses
        w = _where(clauses)
        current = query(f"""
        SELECT
            SUM(VALOR_LIQUIDO_BRL)::float AS net_spend,
            SUM(VALOR_NOTA_BRL)::float AS gross_spend,
            SUM(SAVING_TOTAL)::float AS savings_total,
            (SUM(CASE WHEN CENTRALIZADO = 'CENTRALIZADO' THEN VALOR_LIQUIDO_BRL ELSE 0 END) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0) * 100)::float AS centralization_pct,
            (SUM(PGTO_X_VALOR) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0))::float AS avg_payment_term,
            (SUM(SAVING_TOTAL) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0) * 100)::float AS savings_pct
        FROM notas_ri
        {w}
        """)
        # Add entity filters (empresa, grupo, fornecedor, oc_type) but not date filters
        from werkzeug.datastructures import MultiDict
        entity_args = MultiDict([(k, v) for k, v in request.args.items(multi=True) if k not in ('ano', 'mes', 'dia', 'dt_ini', 'dt_fim')])
        entity_c, _ = _parse_filters(entity_args)
        # Remove any date-related clauses from entity filters
        comp_clauses.extend([c for c in entity_c if 'SUBSTRING' not in c and 'DATA_LANCAMENTO' not in c])
    elif ano:
        # Compare to previous year
        cur_year = int(ano[0])
        prev_year = str(cur_year - 1)
        comp_clauses.append(f"SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{prev_year}'")
        # Only cap to today's date when viewing the CURRENT year (fair partial-year comparison);
        # for past years both periods are complete — no cap needed.
        if cur_year == today.year:
            prev_cutoff = f"{prev_year}-{today.month:02d}-{today_day:02d}"
            comp_clauses.append(f"DATA_LANCAMENTO <= '{prev_cutoff}'")
            cur_cutoff = f"{cur_year}-{today.month:02d}-{today_day:02d}"
            clauses.append(f"DATA_LANCAMENTO <= '{cur_cutoff}'")
        # Re-run current query with date cap
        w = _where(clauses)
        current = query(f"""
        SELECT
            SUM(VALOR_LIQUIDO_BRL)::float AS net_spend,
            SUM(VALOR_NOTA_BRL)::float AS gross_spend,
            SUM(SAVING_TOTAL)::float AS savings_total,
            (SUM(CASE WHEN CENTRALIZADO = 'CENTRALIZADO' THEN VALOR_LIQUIDO_BRL ELSE 0 END) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0) * 100)::float AS centralization_pct,
            (SUM(PGTO_X_VALOR) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0))::float AS avg_payment_term,
            (SUM(SAVING_TOTAL) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0) * 100)::float AS savings_pct
        FROM notas_ri
        {w}
        """)
        from werkzeug.datastructures import MultiDict
        entity_args = MultiDict([(k, v) for k, v in request.args.items(multi=True) if k not in ('ano', 'mes', 'dia', 'dt_ini', 'dt_fim')])
        entity_c, _ = _parse_filters(entity_args)
        comp_clauses.extend([c for c in entity_c if 'SUBSTRING' not in c and 'DATA_LANCAMENTO' not in c])

    if comp_clauses:
        wc = _where(comp_clauses)
        prev = query(f"""
        SELECT
            SUM(VALOR_LIQUIDO_BRL)::float AS net_spend,
            SUM(SAVING_TOTAL)::float AS savings_total,
            (SUM(CASE WHEN CENTRALIZADO = 'CENTRALIZADO' THEN VALOR_LIQUIDO_BRL ELSE 0 END) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0) * 100)::float AS centralization_pct,
            (SUM(PGTO_X_VALOR) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0))::float AS avg_payment_term
        FROM notas_ri
        {wc}
        """)
    else:
        prev = [{}]

    return jsonify({'current': current[0] if current else {}, 'previous': prev[0] if prev else {}})


@app.route('/api/performance/spend-yoy')
def performance_spend_yoy():
    """Monthly Net Spend current year vs previous year.
    For the current month, caps previous year data to today's day number
    so both years compare the same date window (consistent with KPI card)."""
    from werkzeug.datastructures import MultiDict
    args_no_month_flat = MultiDict([(k, v) for k, v in request.args.items(multi=True) if k not in ('mes', 'dia')])
    clauses, params = _parse_filters(args_no_month_flat)
    ano = request.args.getlist('ano')
    current_year = ano[0] if ano else _default_year_filter()
    prev_year = str(int(current_year) - 1)

    today = date.today()
    today_day = today.day
    current_month = today.month

    # Always require year filter for the two comparison years
    year_clause = f"SUBSTRING(DATA_LANCAMENTO, 1, 4) IN ('{current_year}', '{prev_year}')"
    # Remove any year clause that _parse_filters added (we handle year ourselves)
    entity_clauses = [c for c in clauses if 'SUBSTRING' not in c or '1, 4' not in c]
    # Only cap previous year's current month to today's day when viewing the CURRENT year;
    # for past years both periods are complete — no day cap needed.
    if int(current_year) == today.year:
        day_cap = f"""NOT (
            SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{prev_year}'
            AND CAST(SUBSTRING(DATA_LANCAMENTO, 6, 2) AS INT) = {current_month}
            AND CAST(SUBSTRING(DATA_LANCAMENTO, 9, 2) AS INT) > {today_day}
        )"""
        all_clauses = [year_clause, day_cap] + entity_clauses
    else:
        all_clauses = [year_clause] + entity_clauses
    w = "WHERE " + " AND ".join(all_clauses)

    sql = f"""
    SELECT
        SUBSTRING(DATA_LANCAMENTO, 6, 2) AS mes,
        SUM(CASE WHEN SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{current_year}' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS current_spend,
        SUM(CASE WHEN SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{prev_year}' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS prev_spend
    FROM notas_ri
    {w}
    GROUP BY SUBSTRING(DATA_LANCAMENTO, 6, 2)
    ORDER BY mes
    """
    return jsonify(query(sql))


@app.route('/api/performance/savings-monthly')
def performance_savings_monthly():
    """Monthly savings current vs previous year."""
    # Apply entity filters but skip mes/dia (chart needs all months)
    from werkzeug.datastructures import MultiDict
    args_no_month_flat = MultiDict([(k, v) for k, v in request.args.items(multi=True) if k not in ('mes', 'dia')])
    clauses, params = _parse_filters(args_no_month_flat)
    ano = request.args.getlist('ano')
    current_year = ano[0] if ano else _default_year_filter()
    prev_year = str(int(current_year) - 1)

    year_clause = f"SUBSTRING(DATA_LANCAMENTO, 1, 4) IN ('{current_year}', '{prev_year}')"
    entity_clauses = [c for c in clauses if 'SUBSTRING' not in c or '1, 4' not in c]
    all_clauses = [year_clause] + entity_clauses
    w = "WHERE " + " AND ".join(all_clauses)

    sql = f"""
    SELECT
        SUBSTRING(DATA_LANCAMENTO, 6, 2) AS mes,
        SUM(CASE WHEN SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{current_year}' AND SAVING_PCT BETWEEN 0 AND 100
            THEN VALOR_LIQUIDO_BRL * SAVING_PCT / 100 ELSE 0 END)::float AS current_savings,
        SUM(CASE WHEN SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{prev_year}' AND SAVING_PCT BETWEEN 0 AND 100
            THEN VALOR_LIQUIDO_BRL * SAVING_PCT / 100 ELSE 0 END)::float AS prev_savings
    FROM notas_ri
    {w}
    GROUP BY SUBSTRING(DATA_LANCAMENTO, 6, 2)
    ORDER BY mes
    """
    return jsonify(query(sql))


@app.route('/api/performance/lead-time')
def performance_lead_time():
    """Process Funnel & Par-a-Par Lead Time:
    Scope: 'diretos' (default), 'indiretos', 'todos'
    Tracking: par-a-par cohort with First Delivery (MIN(data_lancamento)) for invoices.
    """
    scope = request.args.get('scope', 'diretos').strip().lower()
    if scope not in ('diretos', 'indiretos', 'todos'):
        scope = 'diretos'

    def _format_lead(val):
        """Convert avg_days to (value, unit). If 0 < val < 1, show hours."""
        if val is None:
            return None, 'dias'
        if val == 0:
            return 0, 'dias'
        if 0 < val < 1:
            h = round(val * 24, 1)
            return int(h) if h.is_integer() else h, 'horas'
        d = round(val, 1)
        return int(d) if d.is_integer() else d, 'dias'

    # Build clean args without 'grupo_compras' to avoid conflicting with the scope pills
    args_clean = request.args.copy()
    if 'grupo_compras' in args_clean:
        del args_clean['grupo_compras']

    oc_clauses, _ = _parse_filters(args_clean, date_col='DATA_OC', table_prefix='oc', empresa_col='ORG_DESC', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', fornecedor_col='nome_fornecedor')

    # Scope condition for ordens_compra
    if scope == 'diretos':
        oc_clauses.append("UPPER(TRIM(COALESCE(oc.grupo_compras_oc, ''))) = 'DIRETOS'")
    elif scope == 'indiretos':
        oc_clauses.append("UPPER(TRIM(COALESCE(oc.grupo_compras_oc, ''))) = 'INDIRETOS'")
    # scope == 'todos' does not filter by grupo_compras_oc

    oc_where = " AND ".join(oc_clauses) if oc_clauses else "1=1"

    if scope == 'indiretos':
        # Requisicoes filter conditions
        f_empresa = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
        f_ano = [a.strip() for a in request.args.getlist('ano') if a.strip()]
        f_mes = [m.strip() for m in request.args.getlist('mes') if m.strip()]
        f_dia = [d.strip() for d in request.args.getlist('dia') if d.strip()]
        f_dt_ini = request.args.get('dt_ini', '').strip()
        f_dt_fim = request.args.get('dt_fim', '').strip()

        req_date_expr = "COALESCE(NULLIF(TRIM(req.dt_aprovacao), ''), NULLIF(TRIM(req.dt_criacao), ''))"
        req_parts = [f"NULLIF(TRIM({req_date_expr}), '') IS NOT NULL"]
        if f_empresa:
            vals = ','.join([f"'{_esc(e)}'" for e in f_empresa])
            req_parts.append(f"req.empresa IN ({vals})")
        if f_ano:
            vals = ','.join([f"'{_esc(a)}'" for a in f_ano if a])
            if vals:
                req_parts.append(f"SUBSTRING({req_date_expr}, 1, 4) IN ({vals})")
        if f_mes:
            clean_months = [str(int(m)) for m in f_mes if m.isdigit()]
            if clean_months:
                vals = ','.join(clean_months)
                req_parts.append(f"(LENGTH(TRIM({req_date_expr})) >= 7 AND CAST(SUBSTRING(TRIM({req_date_expr}), 6, 2) AS INT) IN ({vals}))")
        if f_dia:
            clean_days = [str(int(d)) for d in f_dia if d.isdigit()]
            if clean_days:
                vals = ','.join(clean_days)
                req_parts.append(f"(LENGTH(TRIM({req_date_expr})) >= 10 AND CAST(SUBSTRING(TRIM({req_date_expr}), 9, 2) AS INT) IN ({vals}))")
        if f_dt_ini and not f_ano:
            req_parts.append(f"NULLIF(TRIM({req_date_expr}), '')::date >= '{_esc(f_dt_ini)}'::date")
        if f_dt_fim and not f_ano:
            req_parts.append(f"NULLIF(TRIM({req_date_expr}), '')::date <= '{_esc(f_dt_fim)}'::date")

        req_st = [v.strip() for v in request.args.getlist('req_status') if v.strip()]
        if req_st:
            vals = ','.join([f"'{_esc(v)}'" for v in req_st])
            req_parts.append(f"req.status IN ({vals})")

        req_where = " AND ".join(req_parts)

        # For the cohort of OCs generated from these requisitions:
        # Entity filters on OC (empresa, fornecedor, unidade, etc.) are kept, while the cohort timeline is anchored on the requisitions
        args_oc = args_clean.copy()
        for k in ('ano', 'mes', 'dia', 'dt_ini', 'dt_fim'):
            args_oc.pop(k, None)
        oc_clauses_cohort, _ = _parse_filters(args_oc, date_col='DATA_OC', table_prefix='oc', empresa_col='ORG_DESC', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', fornecedor_col='nome_fornecedor')
        oc_clauses_cohort.append("UPPER(TRIM(COALESCE(oc.grupo_compras_oc, ''))) = 'INDIRETOS'")
        oc_where_cohort = " AND ".join(oc_clauses_cohort) if oc_clauses_cohort else "1=1"

        sql = f"""
        WITH req_base AS (
            SELECT DISTINCT 
                req.requisicao, 
                NULLIF(TRIM(req.numero_oc), '') AS numero_oc,
                NULLIF(TRIM({req_date_expr}), '')::date AS req_dt
            FROM requisicoes req
            WHERE {req_where}
        ),
        req_items AS (
            SELECT 
                requisicao, 
                req_dt,
                TRIM(oc_num) AS po_num
            FROM req_base,
                 UNNEST(string_to_array(numero_oc, ',')) AS oc_num
            WHERE numero_oc IS NOT NULL 
              AND numero_oc != 'Requisicao sem OC'
              AND TRIM(oc_num) != '' 
              AND TRIM(oc_num) != 'Requisicao sem OC'
        ),
        req_nums AS (
            SELECT DISTINCT requisicao 
            FROM req_base 
            WHERE requisicao IS NOT NULL AND requisicao != ''
        ),
        req_ocs AS (
            SELECT DISTINCT po_num AS numero_oc 
            FROM req_items
        ),
        req_metrics AS (
            SELECT 
                COUNT(DISTINCT req.requisicao)::int AS qty_req,
                COALESCE(SUM(CASE WHEN req.valor_requisicao < 1000000000 THEN req.valor_requisicao ELSE 0 END), 0)::float AS spend_req
            FROM requisicoes req
            WHERE {req_where}
        ),
        oc_cohort AS (
            SELECT 
                oc.numero_oc,
                oc.chave_oc_linha,
                oc.valor_original_brl,
                NULLIF(TRIM(oc.data_oc), '')::date AS d_oc,
                NULLIF(TRIM(oc.dt_aprovacao), '')::date AS d_aprov,
                oc.status_aprovacao,
                oc.status_fechamento,
                oc.requisicao
            FROM ordens_compra oc
            WHERE {oc_where_cohort}
              AND (
                  (oc.requisicao IS NOT NULL AND oc.requisicao != '' AND oc.requisicao IN (SELECT requisicao FROM req_nums))
                  OR oc.numero_oc IN (SELECT numero_oc FROM req_ocs)
              )
              AND (
                  UPPER(TRIM(COALESCE(oc.status_aprovacao, ''))) IN ('APPROVED', 'APROVADO')
                  OR UPPER(TRIM(COALESCE(oc.status_fechamento, ''))) = 'PENDENTE APROVACAO'
                  OR UPPER(TRIM(COALESCE(oc.status_aprovacao, ''))) LIKE '%PENDING%'
                  OR UPPER(TRIM(COALESCE(oc.status_fechamento, ''))) LIKE '%PENDENTE%'
              )
        ),
        oc_aprov AS (
            SELECT * FROM oc_cohort 
            WHERE UPPER(TRIM(COALESCE(status_aprovacao, ''))) IN ('APPROVED', 'APROVADO')
        ),
        nf_agg AS (
            SELECT 
                nf.chave_oc_linha,
                SUM(nf.valor_liquido_brl) AS nf_line_spend,
                COUNT(DISTINCT nf.nota_fiscal) AS nf_line_count,
                MIN(NULLIF(TRIM(nf.data_lancamento), '')::date) AS min_nf_dt,
                MAX(NULLIF(TRIM(nf.data_lancamento), '')::date) AS max_nf_dt
            FROM oc_aprov a
            JOIN notas_ri nf ON nf.chave_oc_linha = a.chave_oc_linha
            WHERE NULLIF(TRIM(nf.data_lancamento), '') IS NOT NULL
            GROUP BY nf.chave_oc_linha
        ),
        oc_summary AS (
            SELECT 
                a.numero_oc,
                MIN(a.d_aprov) AS d_aprov,
                SUM(a.valor_original_brl) AS total_oc_vl,
                SUM(COALESCE(n.nf_line_spend, 0)) AS total_nf_vl,
                SUM(COALESCE(n.nf_line_count, 0)) AS total_nfs,
                MIN(n.min_nf_dt) AS first_nf_date,
                MAX(n.max_nf_dt) AS last_nf_date,
                BOOL_OR(UPPER(TRIM(COALESCE(a.status_fechamento, ''))) IN ('FECHADO', 'FECHADO P/ FATURAMENTO', 'FINALMENTE FECHADO')) AS is_closed
            FROM oc_aprov a
            LEFT JOIN nf_agg n ON n.chave_oc_linha = a.chave_oc_linha
            GROUP BY a.numero_oc
        ),
        oc_fat_metrics AS (
            SELECT 
                COUNT(CASE WHEN total_nf_vl > 0 OR total_nfs > 0 THEN 1 END)::int AS qty_fat_ini,
                COALESCE(SUM(CASE WHEN total_nf_vl > 0 OR total_nfs > 0 THEN total_nf_vl ELSE 0 END), 0)::float AS spend_fat_ini,
                COUNT(CASE WHEN (total_nf_vl > 0 OR total_nfs > 0) AND (is_closed = TRUE OR (total_oc_vl > 0 AND total_nf_vl >= total_oc_vl * 0.98) OR (total_oc_vl = 0 AND total_nf_vl > 0)) THEN 1 END)::int AS qty_fat_tot,
                COALESCE(SUM(CASE WHEN (total_nf_vl > 0 OR total_nfs > 0) AND (is_closed = TRUE OR (total_oc_vl > 0 AND total_nf_vl >= total_oc_vl * 0.98) OR (total_oc_vl = 0 AND total_nf_vl > 0)) THEN total_nf_vl ELSE 0 END), 0)::float AS spend_fat_tot,
                AVG(CASE WHEN first_nf_date IS NOT NULL AND d_aprov IS NOT NULL AND (first_nf_date - d_aprov) >= 0 THEN (first_nf_date - d_aprov) END)::float AS avg_days_aprov_to_first_nf,
                AVG(CASE WHEN last_nf_date IS NOT NULL AND first_nf_date IS NOT NULL AND (last_nf_date - first_nf_date) >= 0 THEN (last_nf_date - first_nf_date) END)::float AS avg_days_first_to_last_nf
            FROM oc_summary
        ),
        req_pairs AS (
            SELECT r.requisicao, r.req_dt, c.numero_oc, c.d_oc
            FROM req_base r
            JOIN (SELECT DISTINCT numero_oc, requisicao, d_oc FROM oc_cohort WHERE d_oc IS NOT NULL) c
              ON c.requisicao = r.requisicao AND c.requisicao IS NOT NULL AND c.requisicao != ''
            UNION
            SELECT ri.requisicao, ri.req_dt, c.numero_oc, c.d_oc
            FROM req_items ri
            JOIN (SELECT DISTINCT numero_oc, d_oc FROM oc_cohort WHERE d_oc IS NOT NULL) c
              ON c.numero_oc = ri.po_num
        ),
        req_to_oc_lead AS (
            SELECT AVG(d_oc - req_dt)::float AS avg_days_req_to_emit
            FROM req_pairs
            WHERE d_oc >= req_dt
        )
        SELECT 
            (SELECT spend_req FROM req_metrics) AS spend_req,
            (SELECT qty_req FROM req_metrics) AS qty_req,
            (SELECT COALESCE(SUM(valor_original_brl), 0)::float FROM oc_cohort) AS spend_emit,
            (SELECT COUNT(DISTINCT numero_oc)::int FROM oc_cohort) AS qty_emit,
            (SELECT avg_days_req_to_emit FROM req_to_oc_lead) AS avg_days_req_to_emit,
            (SELECT COALESCE(SUM(valor_original_brl), 0)::float FROM oc_aprov) AS spend_aprov,
            (SELECT COUNT(DISTINCT numero_oc)::int FROM oc_aprov) AS qty_aprov,
            (SELECT AVG(d_aprov - d_oc)::float FROM oc_aprov WHERE d_aprov IS NOT NULL AND d_oc IS NOT NULL AND (d_aprov - d_oc) >= 0) AS avg_days_emit_to_aprov,
            (SELECT qty_fat_ini FROM oc_fat_metrics) AS qty_fat_ini,
            (SELECT spend_fat_ini FROM oc_fat_metrics) AS spend_fat_ini,
            (SELECT qty_fat_tot FROM oc_fat_metrics) AS qty_fat_tot,
            (SELECT spend_fat_tot FROM oc_fat_metrics) AS spend_fat_tot,
            (SELECT avg_days_aprov_to_first_nf FROM oc_fat_metrics) AS avg_days_aprov_to_first_nf,
            (SELECT avg_days_first_to_last_nf FROM oc_fat_metrics) AS avg_days_first_to_last_nf
        """
        rows = query(sql)
        row = rows[0] if rows else {}

        spend_req = float(row.get('spend_req') or 0)
        qty_req = int(row.get('qty_req') or 0)
        spend_emit = float(row.get('spend_emit') or 0)
        qty_emit = int(row.get('qty_emit') or 0)
        spend_aprov = float(row.get('spend_aprov') or 0)
        qty_aprov = int(row.get('qty_aprov') or 0)
        spend_fat_ini = float(row.get('spend_fat_ini') or 0)
        qty_fat_ini = int(row.get('qty_fat_ini') or 0)
        spend_fat_tot = float(row.get('spend_fat_tot') or 0)
        qty_fat_tot = int(row.get('qty_fat_tot') or 0)

        v_req_emit, u_req_emit = _format_lead(row.get('avg_days_req_to_emit'))
        v_emit_aprov, u_emit_aprov = _format_lead(row.get('avg_days_emit_to_aprov'))
        v_aprov_nf, u_aprov_nf = _format_lead(row.get('avg_days_aprov_to_first_nf'))
        v_nf_fat, u_nf_fat = _format_lead(row.get('avg_days_first_to_last_nf'))

        qty_parcial = max(0, qty_fat_ini - qty_fat_tot)

        stages = [
            {
                'id': 'req',
                'name': 'Requisições',
                'sub': 'Aprovadas',
                'icon': 'req',
                'spend': spend_req,
                'qty': qty_req,
                'qty_label': 'requisições',
                'conv_pct': 100.0,
                'step_conv_pct': 100.0
            },
            {
                'id': 'emit',
                'name': 'Pedidos',
                'sub': 'Emitidos',
                'icon': 'cart',
                'spend': spend_emit,
                'qty': qty_emit,
                'qty_label': 'pedidos emitidos',
                'conv_pct': round(qty_emit / qty_req * 100, 1) if qty_req > 0 else 100.0,
                'step_conv_pct': round(qty_emit / qty_req * 100, 1) if qty_req > 0 else 100.0
            },
            {
                'id': 'aprov',
                'name': 'Pedidos',
                'sub': 'Aprovados',
                'icon': 'cart',
                'spend': spend_aprov,
                'qty': qty_aprov,
                'qty_label': 'pedidos aprovados',
                'conv_pct': round(qty_aprov / qty_req * 100, 1) if qty_req > 0 else 0,
                'step_conv_pct': round(qty_aprov / qty_emit * 100, 1) if qty_emit > 0 else 0
            },
            {
                'id': 'fat_ini',
                'name': 'Faturamento',
                'sub': 'Iniciado',
                'icon': 'fat_ini',
                'spend': spend_fat_ini,
                'qty': qty_fat_ini,
                'qty_label': 'pedidos faturados',
                'conv_pct': round(qty_fat_ini / qty_req * 100, 1) if qty_req > 0 else 0,
                'step_conv_pct': round(qty_fat_ini / qty_aprov * 100, 1) if qty_aprov > 0 else 0,
                'open_spend': max(0.0, spend_aprov - spend_fat_ini),
                'open_pct': round(max(0.0, spend_aprov - spend_fat_ini) / spend_aprov * 100, 1) if spend_aprov > 0 else 0
            },
            {
                'id': 'fat_tot',
                'name': 'Faturamento',
                'sub': 'Totalmente Concluído',
                'icon': 'fat_tot',
                'spend': spend_fat_tot,
                'qty': qty_fat_tot,
                'qty_label': 'pedidos concluídos',
                'conv_pct': round(qty_fat_tot / qty_req * 100, 1) if qty_req > 0 else 0,
                'step_conv_pct': round(qty_fat_tot / qty_fat_ini * 100, 1) if qty_fat_ini > 0 else 0,
                'open_spend': max(0.0, spend_fat_ini - spend_fat_tot),
                'open_pct': round(qty_parcial / qty_fat_ini * 100, 1) if qty_fat_ini > 0 else 0,
                'open_qty': qty_parcial,
                'open_label': f'Parciais: {qty_parcial:,}'.replace(',', '.')
            }
        ]
        connectors = [
            {'from': 'req', 'to': 'emit', 'val': v_req_emit, 'unit': u_req_emit, 'label': 'Requisição Aprovada e Pedido Emitido'},
            {'from': 'emit', 'to': 'aprov', 'val': v_emit_aprov, 'unit': u_emit_aprov, 'label': 'Pedido Emitido e Pedido Aprovado'},
            {'from': 'aprov', 'to': 'fat_ini', 'val': v_aprov_nf, 'unit': u_aprov_nf, 'label': 'Pedido Aprovado e 1ª NF'},
            {'from': 'fat_ini', 'to': 'fat_tot', 'val': v_nf_fat, 'unit': u_nf_fat, 'label': '1ª NF e Conclusão do Faturamento'}
        ]

    else:
        # Diretos or Todos
        sql = f"""
        WITH oc_cohort AS (
            SELECT 
                oc.numero_oc,
                oc.chave_oc_linha,
                oc.valor_original_brl,
                NULLIF(TRIM(oc.data_oc), '')::date AS d_oc,
                NULLIF(TRIM(oc.dt_aprovacao), '')::date AS d_aprov,
                oc.status_aprovacao,
                oc.status_fechamento
            FROM ordens_compra oc
            WHERE {oc_where}
              AND (
                  UPPER(TRIM(COALESCE(oc.status_aprovacao, ''))) IN ('APPROVED', 'APROVADO')
                  OR UPPER(TRIM(COALESCE(oc.status_fechamento, ''))) = 'PENDENTE APROVACAO'
                  OR UPPER(TRIM(COALESCE(oc.status_aprovacao, ''))) LIKE '%PENDING%'
                  OR UPPER(TRIM(COALESCE(oc.status_fechamento, ''))) LIKE '%PENDENTE%'
              )
        ),
        oc_aprov AS (
            SELECT * FROM oc_cohort 
            WHERE UPPER(TRIM(COALESCE(status_aprovacao, ''))) IN ('APPROVED', 'APROVADO')
        ),
        nf_agg AS (
            SELECT 
                nf.chave_oc_linha,
                SUM(nf.valor_liquido_brl) AS nf_line_spend,
                COUNT(DISTINCT nf.nota_fiscal) AS nf_line_count,
                MIN(NULLIF(TRIM(nf.data_lancamento), '')::date) AS min_nf_dt,
                MAX(NULLIF(TRIM(nf.data_lancamento), '')::date) AS max_nf_dt
            FROM oc_aprov a
            JOIN notas_ri nf ON nf.chave_oc_linha = a.chave_oc_linha
            WHERE NULLIF(TRIM(nf.data_lancamento), '') IS NOT NULL
            GROUP BY nf.chave_oc_linha
        ),
        oc_summary AS (
            SELECT 
                a.numero_oc,
                MIN(a.d_aprov) AS d_aprov,
                SUM(a.valor_original_brl) AS total_oc_vl,
                SUM(COALESCE(n.nf_line_spend, 0)) AS total_nf_vl,
                SUM(COALESCE(n.nf_line_count, 0)) AS total_nfs,
                MIN(n.min_nf_dt) AS first_nf_date,
                MAX(n.max_nf_dt) AS last_nf_date,
                BOOL_OR(UPPER(TRIM(COALESCE(a.status_fechamento, ''))) IN ('FECHADO', 'FECHADO P/ FATURAMENTO', 'FINALMENTE FECHADO')) AS is_closed
            FROM oc_aprov a
            LEFT JOIN nf_agg n ON n.chave_oc_linha = a.chave_oc_linha
            GROUP BY a.numero_oc
        ),
        oc_fat_metrics AS (
            SELECT 
                COUNT(CASE WHEN total_nf_vl > 0 OR total_nfs > 0 THEN 1 END)::int AS qty_fat_ini,
                COALESCE(SUM(CASE WHEN total_nf_vl > 0 OR total_nfs > 0 THEN total_nf_vl ELSE 0 END), 0)::float AS spend_fat_ini,
                COUNT(CASE WHEN (total_nf_vl > 0 OR total_nfs > 0) AND (is_closed = TRUE OR (total_oc_vl > 0 AND total_nf_vl >= total_oc_vl * 0.98) OR (total_oc_vl = 0 AND total_nf_vl > 0)) THEN 1 END)::int AS qty_fat_tot,
                COALESCE(SUM(CASE WHEN (total_nf_vl > 0 OR total_nfs > 0) AND (is_closed = TRUE OR (total_oc_vl > 0 AND total_nf_vl >= total_oc_vl * 0.98) OR (total_oc_vl = 0 AND total_nf_vl > 0)) THEN total_nf_vl ELSE 0 END), 0)::float AS spend_fat_tot,
                AVG(CASE WHEN first_nf_date IS NOT NULL AND d_aprov IS NOT NULL AND (first_nf_date - d_aprov) >= 0 THEN (first_nf_date - d_aprov) END)::float AS avg_days_aprov_to_first_nf,
                AVG(CASE WHEN last_nf_date IS NOT NULL AND first_nf_date IS NOT NULL AND (last_nf_date - first_nf_date) >= 0 THEN (last_nf_date - first_nf_date) END)::float AS avg_days_first_to_last_nf
            FROM oc_summary
        )
        SELECT 
            (SELECT COALESCE(SUM(valor_original_brl), 0)::float FROM oc_cohort) AS spend_emit,
            (SELECT COUNT(DISTINCT numero_oc)::int FROM oc_cohort) AS qty_emit,
            (SELECT COALESCE(SUM(valor_original_brl), 0)::float FROM oc_aprov) AS spend_aprov,
            (SELECT COUNT(DISTINCT numero_oc)::int FROM oc_aprov) AS qty_aprov,
            (SELECT AVG(d_aprov - d_oc)::float FROM oc_aprov WHERE d_aprov IS NOT NULL AND d_oc IS NOT NULL AND (d_aprov - d_oc) >= 0) AS avg_days_emit_to_aprov,
            (SELECT qty_fat_ini FROM oc_fat_metrics) AS qty_fat_ini,
            (SELECT spend_fat_ini FROM oc_fat_metrics) AS spend_fat_ini,
            (SELECT qty_fat_tot FROM oc_fat_metrics) AS qty_fat_tot,
            (SELECT spend_fat_tot FROM oc_fat_metrics) AS spend_fat_tot,
            (SELECT avg_days_aprov_to_first_nf FROM oc_fat_metrics) AS avg_days_aprov_to_first_nf,
            (SELECT avg_days_first_to_last_nf FROM oc_fat_metrics) AS avg_days_first_to_last_nf
        """
        rows = query(sql)
        row = rows[0] if rows else {}

        spend_emit = float(row.get('spend_emit') or 0)
        qty_emit = int(row.get('qty_emit') or 0)
        spend_aprov = float(row.get('spend_aprov') or 0)
        qty_aprov = int(row.get('qty_aprov') or 0)
        spend_fat_ini = float(row.get('spend_fat_ini') or 0)
        qty_fat_ini = int(row.get('qty_fat_ini') or 0)
        spend_fat_tot = float(row.get('spend_fat_tot') or 0)
        qty_fat_tot = int(row.get('qty_fat_tot') or 0)

        v_emit_aprov, u_emit_aprov = _format_lead(row.get('avg_days_emit_to_aprov'))
        v_aprov_nf, u_aprov_nf = _format_lead(row.get('avg_days_aprov_to_first_nf'))
        v_nf_fat, u_nf_fat = _format_lead(row.get('avg_days_first_to_last_nf'))
        v_req_emit, u_req_emit = None, 'dias'

        qty_parcial = max(0, qty_fat_ini - qty_fat_tot)

        stages = [
            {
                'id': 'emit',
                'name': 'Pedidos',
                'sub': 'Emitidos',
                'icon': 'cart',
                'spend': spend_emit,
                'qty': qty_emit,
                'qty_label': 'pedidos emitidos',
                'conv_pct': 100.0,
                'step_conv_pct': 100.0
            },
            {
                'id': 'aprov',
                'name': 'Pedidos',
                'sub': 'Aprovados',
                'icon': 'cart',
                'spend': spend_aprov,
                'qty': qty_aprov,
                'qty_label': 'pedidos aprovados',
                'conv_pct': round(qty_aprov / qty_emit * 100, 1) if qty_emit > 0 else 0,
                'step_conv_pct': round(qty_aprov / qty_emit * 100, 1) if qty_emit > 0 else 0
            },
            {
                'id': 'fat_ini',
                'name': 'Faturamento',
                'sub': 'Iniciado',
                'icon': 'fat_ini',
                'spend': spend_fat_ini,
                'qty': qty_fat_ini,
                'qty_label': 'pedidos faturados',
                'conv_pct': round(qty_fat_ini / qty_emit * 100, 1) if qty_emit > 0 else 0,
                'step_conv_pct': round(qty_fat_ini / qty_aprov * 100, 1) if qty_aprov > 0 else 0,
                'open_spend': max(0.0, spend_aprov - spend_fat_ini),
                'open_pct': round(max(0.0, spend_aprov - spend_fat_ini) / spend_aprov * 100, 1) if spend_aprov > 0 else 0
            },
            {
                'id': 'fat_tot',
                'name': 'Faturamento',
                'sub': 'Totalmente Concluído',
                'icon': 'fat_tot',
                'spend': spend_fat_tot,
                'qty': qty_fat_tot,
                'qty_label': 'pedidos concluídos',
                'conv_pct': round(qty_fat_tot / qty_emit * 100, 1) if qty_emit > 0 else 0,
                'step_conv_pct': round(qty_fat_tot / qty_fat_ini * 100, 1) if qty_fat_ini > 0 else 0,
                'open_spend': max(0.0, spend_fat_ini - spend_fat_tot),
                'open_pct': round(qty_parcial / qty_fat_ini * 100, 1) if qty_fat_ini > 0 else 0,
                'open_qty': qty_parcial,
                'open_label': f'Parciais: {qty_parcial:,}'.replace(',', '.')
            }
        ]
        connectors = [
            {'from': 'emit', 'to': 'aprov', 'val': v_emit_aprov, 'unit': u_emit_aprov, 'label': 'Pedido Emitido e Pedido Aprovado'},
            {'from': 'aprov', 'to': 'fat_ini', 'val': v_aprov_nf, 'unit': u_aprov_nf, 'label': 'Pedido Aprovado e 1ª NF'},
            {'from': 'fat_ini', 'to': 'fat_tot', 'val': v_nf_fat, 'unit': u_nf_fat, 'label': '1ª NF e Conclusão do Faturamento'}
        ]

    # Find longest lead time leg for summary
    legs_sorted = sorted([c for c in connectors if c['val'] is not None], key=lambda c: c['val'] * (24 if c['unit'] == 'dias' else 1), reverse=True)
    longest_leg_name = legs_sorted[0]['label'] if legs_sorted else 'Pedido Aprovado e 1ª NF'
    summary_title = f"O maior tempo do processo está entre {longest_leg_name}."

    result = [{
        'scope': scope,
        'stages': stages,
        'connectors': connectors,
        'longest_leg': longest_leg_name,
        'summary_title': summary_title,
        # Legacy compatibility fields
        'req_to_po_emit_days': v_req_emit,
        'req_to_po_emit_unit': u_req_emit,
        'po_emit_to_aprov_days': v_emit_aprov,
        'po_emit_to_aprov_unit': u_emit_aprov,
        'po_to_nf_days': v_aprov_nf,
        'po_to_nf_unit': u_aprov_nf,
        'qty_req': stages[0]['qty'] if scope == 'indiretos' and len(stages) > 0 else 0,
        'qty_emit': stages[1]['qty'] if scope == 'indiretos' and len(stages) > 1 else (stages[0]['qty'] if len(stages) > 0 else 0),
        'qty_aprov': stages[2]['qty'] if scope == 'indiretos' and len(stages) > 2 else (stages[1]['qty'] if len(stages) > 1 else 0),
        'qty_nf': stages[3]['qty'] if scope == 'indiretos' and len(stages) > 3 else (stages[2]['qty'] if len(stages) > 2 else 0)
    }]
    return jsonify(result)


@app.route('/api/performance/process-deviations')
def performance_process_deviations():
    """Process deviations: Regular, Post-Invoice PO, Invoice Without PO."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)

    sql = f"""
    SELECT
        SUM(CASE WHEN NUMERO_OC != 'Nota sem OC' AND OC_POS_FATURA = 'NÃO' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS regular,
        SUM(CASE WHEN OC_POS_FATURA = 'SIM' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS pos_fatura,
        SUM(CASE WHEN NUMERO_OC = 'Nota sem OC' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS sem_oc,
        SUM(VALOR_LIQUIDO_BRL) AS total
    FROM notas_ri
    {w}
    """
    return jsonify(query(sql, params))


@app.route('/api/performance/attention')
def performance_attention():
    """Action items requiring attention."""
    # Parse ALL filters for notas_ri
    clauses_nf, _ = _parse_filters(request.args)
    w_nf = _where(clauses_nf)
    and_nf = 'AND ' + ' AND '.join(clauses_nf) if clauses_nf else ''

    # Build empresa/grupo filter for ordens_compra (WITH date)
    oc_clauses, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade')
    oc_and = 'AND ' + ' AND '.join(oc_clauses) if oc_clauses else ''
    # Entity-only filter for OC queries that should ignore date (90d/180d alerts)
    oc_entity_clauses = []
    _oc_empresa = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    if _oc_empresa:
        _vals = ','.join([f"'{_esc(e)}'" for e in _oc_empresa])
        oc_entity_clauses.append(f"org_desc IN ({_vals})")
    _oc_grupo = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
    if _oc_grupo:
        _vals = ','.join([f"'{_esc(g)}'" for g in _oc_grupo])
        oc_entity_clauses.append(f"grupo_compras_oc IN ({_vals})")
    oc_entity_and = 'AND ' + ' AND '.join(oc_entity_clauses) if oc_entity_clauses else ''

    # Build empresa filter for requisicoes
    req_clauses, _ = _parse_filters(request.args, date_col='DT_CRIACAO')
    req_and = 'AND ' + ' AND '.join(req_clauses) if req_clauses else ''

    # Requisitions without PO for >5 days
    req_pending = query(f"""
    SELECT COUNT(*) AS qty, SUM(CASE WHEN VALOR_REQUISICAO < 1000000000 THEN VALOR_REQUISICAO ELSE 0 END) AS valor,
           COUNT(*)::float / NULLIF((SELECT COUNT(*) FROM requisicoes WHERE STATUS = 'Aprovado' {req_and}), 0)::float * 100 AS pct_qty,
           SUM(CASE WHEN VALOR_REQUISICAO < 1000000000 THEN VALOR_REQUISICAO ELSE 0 END)::float / NULLIF((SELECT SUM(CASE WHEN VALOR_REQUISICAO < 1000000000 THEN VALOR_REQUISICAO ELSE 0 END) FROM requisicoes WHERE STATUS = 'Aprovado' {req_and}), 0)::float * 100 AS pct_valor
    FROM requisicoes
    WHERE (NUMERO_OC IS NULL OR NUMERO_OC = '' OR NUMERO_OC = 'Requisicao sem OC')
      AND (CURRENT_DATE - DT_APROVACAO::date) > 5
      AND STATUS = 'Aprovado'
      {req_and}
    """)

    # Total distinct OCs faturadas (entity-only, for pct reference)
    _nf_ent_parts = []
    if _oc_empresa:
        _nf_ent_parts.append(f"EMPRESA IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _oc_empresa])})")
    if _oc_grupo:
        _nf_ent_parts.append(f"GRUPO_COMPRAS IN ({','.join([chr(39)+_esc(g)+chr(39) for g in _oc_grupo])})")
    _nf_ent_w = "WHERE NUMERO_OC != 'Nota sem OC' AND NUMERO_OC != ''" + (' AND ' + ' AND '.join(_nf_ent_parts) if _nf_ent_parts else '')
    _total_ocs_faturadas = f"SELECT COUNT(DISTINCT NUMERO_OC) FROM notas_ri {_nf_ent_w}"

    # Acordos OPEN >180 dias (mesma regra da aba Governança — referência: acordo_dt_criacao)
    _total_acordos_vl = f"SELECT SUM(acordo_valor_total) FROM (SELECT DISTINCT numero_acordo, acordo_valor_total FROM ordens_compra WHERE acordo_status = 'OPEN' {oc_entity_and}) a"
    blanket_old = query(f"""
    SELECT COUNT(*)::int AS qty,
           SUM(vl)::float AS valor,
           COUNT(*)::float / NULLIF(({_total_ocs_faturadas}), 0)::float * 100 AS pct_qty,
           SUM(vl)::float / NULLIF(({_total_acordos_vl}), 0)::float * 100 AS pct_valor
    FROM (
        SELECT numero_acordo, MAX(acordo_valor_total) AS vl
        FROM ordens_compra
        WHERE acordo_status = 'OPEN'
          AND numero_acordo IS NOT NULL AND numero_acordo != ''
          AND acordo_dt_criacao IS NOT NULL AND acordo_dt_criacao != ''
          AND (CURRENT_DATE - acordo_dt_criacao::date) > 180
          AND COALESCE(acordo_valor_liberado, 0) = 0
          {oc_entity_and}
        GROUP BY numero_acordo
    ) sub
    """)

    # Post-invoice POs — usa coluna oc_pos_fatura calculada no ETL
    # Regra: MIN(dt_nota) por NUMERO_OC < dt_aprovacao da OC
    pos_fatura = query(f"""
    SELECT COUNT(DISTINCT NUMERO_OC)::int AS qty, SUM(VALOR_LIQUIDO_BRL)::float AS valor,
           COUNT(DISTINCT NUMERO_OC)::float / NULLIF((SELECT COUNT(DISTINCT NUMERO_OC) FROM notas_ri {w_nf}), 0)::float * 100 AS pct_qty,
           SUM(VALOR_LIQUIDO_BRL)::float / NULLIF((SELECT SUM(VALOR_LIQUIDO_BRL) FROM notas_ri {w_nf}), 0)::float * 100 AS pct_valor
    FROM notas_ri
    WHERE OC_POS_FATURA = 'SIM'
      AND NUMERO_OC != 'Nota sem OC'
      {and_nf}
    """)

    # Decentralized POs > R$30k (excludes buyers from Compras area)
    # Source: ordens_compra — uses DATA_OC for date filter and valor_original_brl for value
    decentral = query(f"""
    SELECT COUNT(*)::int AS qty, SUM(valor_oc)::float AS valor,
           COUNT(*)::float / NULLIF((SELECT COUNT(DISTINCT NUMERO_OC) FROM ordens_compra WHERE CENTRALIZADO = 'DESCENTRALIZADO' {oc_and}), 0)::float * 100 AS pct_qty,
           SUM(valor_oc)::float / NULLIF((SELECT SUM(valor_original_brl) FROM ordens_compra WHERE CENTRALIZADO = 'DESCENTRALIZADO' {oc_and}), 0)::float * 100 AS pct_valor
    FROM (
        SELECT NUMERO_OC, SUM(valor_original_brl) AS valor_oc
        FROM ordens_compra
        WHERE CENTRALIZADO = 'DESCENTRALIZADO'
          AND (numero_acordo IS NULL OR numero_acordo = '')
          AND NUMERO_OC NOT IN ({_EXCL_COMPRAS_OCS})
          {oc_and}
        GROUP BY NUMERO_OC
        HAVING SUM(valor_original_brl) > 30000
    ) sub
    """)

    # OCs abertas > 90 dias — ignores date filters
    _total_valor_ocs = f"SELECT SUM(valor_original_brl) FROM ordens_compra WHERE 1=1 {oc_entity_and}"
    oc_90 = query(f"""
    SELECT COUNT(DISTINCT numero_oc)::int AS qty,
           SUM(valor_original_brl)::float AS valor,
           COUNT(DISTINCT numero_oc)::float / NULLIF(({_total_ocs_faturadas}), 0)::float * 100 AS pct_qty,
           SUM(valor_original_brl)::float / NULLIF(({_total_valor_ocs}), 0)::float * 100 AS pct_valor
    FROM ordens_compra
    WHERE status_fechamento = 'ABERTA' AND dias_aberto > 90
      {oc_entity_and}
    """)

    # Items with most negative saving_total (biggest cost increase)
    # Build entity-only filter (no date) so LAG() can look back across months
    entity_clauses = []
    _empresa = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    if _empresa:
        _vals = ','.join([f"'{_esc(e)}'" for e in _empresa])
        entity_clauses.append(f"EMPRESA IN ({_vals})")
    _grupo = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
    if _grupo:
        _vals = ','.join([f"'{_esc(g)}'" for g in _grupo])
        entity_clauses.append(f"GRUPO_COMPRAS IN ({_vals})")
    _forn = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
    if _forn:
        _vals = ','.join([f"'{_esc(f_)}'" for f_ in _forn])
        entity_clauses.append(f"NOME_FORNECEDOR IN ({_vals})")
    _oc_t = [t.strip() for t in request.args.getlist('oc_type') if t.strip()]
    if _oc_t and len(_oc_t) == 1:
        if _oc_t[0] == 'com_oc':
            entity_clauses.append("NUMERO_OC != 'Nota sem OC'")
        elif _oc_t[0] == 'sem_oc':
            entity_clauses.append("NUMERO_OC = 'Nota sem OC'")
    and_entity = 'AND ' + ' AND '.join(entity_clauses) if entity_clauses else ''

    price_alerts = query(f"""
    WITH ranked AS (
        SELECT *,
               LAG(data_lancamento) OVER (PARTITION BY codigo_item, nome_fornecedor ORDER BY data_lancamento) AS data_anterior,
               LAG(nota_fiscal) OVER (PARTITION BY codigo_item, nome_fornecedor ORDER BY data_lancamento) AS nf_anterior,
               LAG(preco_brl) OVER (PARTITION BY codigo_item, nome_fornecedor ORDER BY data_lancamento) AS preco_brl_anterior
        FROM notas_ri
        WHERE 1=1 {and_entity}
    )
    SELECT ds_item, codigo_item, nome_fornecedor,
           (preco_brl - preco_brl_anterior)::float AS saving_total,
           preco_brl::float AS preco_atual,
           preco_brl_anterior::float AS preco_anterior,
           ((preco_brl - preco_brl_anterior) / NULLIF(preco_brl_anterior, 0) * 100)::float AS pct_var,
           data_lancamento AS data_atual, nota_fiscal AS nf_atual,
           data_anterior, nf_anterior
    FROM ranked
    WHERE preco_brl_anterior IS NOT NULL AND preco_brl_anterior > 0
      AND preco_brl > preco_brl_anterior
      AND data_anterior IS NOT NULL
      AND nf_anterior IS NOT NULL AND nf_anterior != nota_fiscal
      AND GREATEST(preco_brl, preco_brl_anterior) / LEAST(preco_brl, preco_brl_anterior) <= 2
      AND (codigo_item IS NULL OR codigo_item NOT LIKE 'F-%%')
      AND (tipo_nf IS NULL OR UPPER(tipo_nf) != 'SERVICE')
      AND COALESCE(quantidade, 0) > 0
      {and_nf}
    ORDER BY (preco_brl - preco_brl_anterior) DESC
    LIMIT 50
    """)

    # Notas sem OC — ignores oc_type filter (would conflict), uses DATA_LANCAMENTO
    sem_oc_clauses = [c for c in clauses_nf if 'Nota sem OC' not in c]
    sem_oc_and = 'AND ' + ' AND '.join(sem_oc_clauses) if sem_oc_clauses else ''
    sem_oc = query(f"""
    SELECT COUNT(DISTINCT NOTA_FISCAL)::int AS qty,
           SUM(VALOR_LIQUIDO_BRL)::float AS valor,
           COUNT(DISTINCT NOTA_FISCAL)::float / NULLIF(
               (SELECT COUNT(DISTINCT NOTA_FISCAL) FROM notas_ri WHERE 1=1 {sem_oc_and}), 0
           )::float * 100 AS pct_qty,
           SUM(VALOR_LIQUIDO_BRL)::float / NULLIF(
               (SELECT SUM(VALOR_LIQUIDO_BRL) FROM notas_ri WHERE 1=1 {sem_oc_and}), 0
           )::float * 100 AS pct_valor
    FROM notas_ri
    WHERE NUMERO_OC = 'Nota sem OC'
      {sem_oc_and}
    """)

    def _fill_pct(d):
        if not d:
            return {}
        if 'pct' not in d or d['pct'] is None:
            d['pct'] = d.get('pct_valor') if d.get('pct_valor') is not None else d.get('pct_qty')
        return d

    return jsonify({
        'req_pending': _fill_pct(req_pending[0]) if req_pending else {},
        'blanket_old': _fill_pct(blanket_old[0]) if blanket_old else {},
        'pos_fatura': _fill_pct(pos_fatura[0]) if pos_fatura else {},
        'decentral': _fill_pct(decentral[0]) if decentral else {},
        'oc_90': _fill_pct(oc_90[0]) if oc_90 else {},
        'sem_oc': _fill_pct(sem_oc[0]) if sem_oc else {},
        'price_alerts': price_alerts or [],
    })


@app.route('/api/performance/req-pending-detail')
def req_pending_detail():
    """Drill-down: requisitions waiting for PO >5 days."""
    rows = query("""
    SELECT REQUISICAO, DESCRICAO_REQ, REQUISITANTE, EMPRESA,
           DT_APROVACAO, VALOR_REQUISICAO, STATUS,
           (CURRENT_DATE - DT_APROVACAO::date) AS dias_espera
    FROM requisicoes
    WHERE (NUMERO_OC IS NULL OR NUMERO_OC = '' OR NUMERO_OC = 'Requisicao sem OC')
      AND (CURRENT_DATE - DT_APROVACAO::date) > 5
      AND STATUS = 'Aprovado'
    ORDER BY dias_espera DESC
    LIMIT 100
    """)
    return jsonify(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# API: PAGE 02 — SPEND ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/spend/by-empresa')
def spend_by_empresa():
    """Spend by empresa (BB vs BQ). Ignores empresa filter, respects all others.
    Caps data to today's day when current month+year is selected (consistent with KPI)."""
    # Build filters WITHOUT empresa (exclude empresa from the clauses)
    clauses = []
    ano = [a.strip() for a in request.args.getlist('ano') if a.strip()]
    mes = [m.strip() for m in request.args.getlist('mes') if m.strip()]
    if ano:
        vals = ','.join([f"'{_esc(a)}'" for a in ano])
        clauses.append(f"SUBSTRING(DATA_LANCAMENTO, 1, 4) IN ({vals})")
    if mes:
        vals = ','.join([m for m in mes])
        clauses.append(f"CAST(SUBSTRING(DATA_LANCAMENTO, 6, 2) AS INT) IN ({vals})")
    # Cap to today's day if current month+year is in filters (fair comparison with KPI)
    today = date.today()
    if ano and mes and str(today.year) in ano and str(today.month) in mes:
        clauses.append(f"CAST(SUBSTRING(DATA_LANCAMENTO, 9, 2) AS INT) <= {today.day}")
    # Day filter
    dia = [d.strip() for d in request.args.getlist('dia') if d.strip()]
    if dia:
        vals = ','.join([d for d in dia])
        clauses.append(f"CAST(SUBSTRING(DATA_LANCAMENTO, 9, 2) AS INT) IN ({vals})")
    grupo = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
    if grupo:
        vals = ','.join([f"'{_esc(g)}'" for g in grupo])
        clauses.append(f"GRUPO_COMPRAS IN ({vals})")
    fornecedor = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
    if fornecedor:
        vals = ','.join([f"'{_esc(f_)}'" for f_ in fornecedor])
        clauses.append(f"NOME_FORNECEDOR IN ({vals})")
    unidade = [u.strip() for u in request.args.getlist('unidade') if u.strip()]
    if unidade:
        vals = ','.join([f"'{_esc(u)}'" for u in unidade])
        clauses.append(f"PLANTA IN ({vals})")
    # OC type filter (com_oc / sem_oc) - MUST match KPI logic
    oc_type = [t.strip() for t in request.args.getlist('oc_type') if t.strip()]
    if oc_type and len(oc_type) == 1:
        if oc_type[0] == 'com_oc':
            clauses.append("NUMERO_OC != 'Nota sem OC'")
        elif oc_type[0] == 'sem_oc':
            clauses.append("NUMERO_OC = 'Nota sem OC'")
    # Centralizado filter
    centralizado = [c.strip() for c in request.args.getlist('centralizado') if c.strip()]
    if centralizado:
        vals = ','.join([f"'{_esc(c)}'" for c in centralizado])
        clauses.append(f"CENTRALIZADO IN ({vals})")
    # Cross-filter parameters
    item_cross = [v.strip() for v in request.args.getlist('item_cross') if v.strip()]
    if item_cross:
        vals = ','.join([f"'{_esc(v)}'" for v in item_cross])
        clauses.append(f"COALESCE(DESCRICAO_ITEM, DS_ITEM, 'Sem descri\u00e7\u00e3o') IN ({vals})")
    categoria_cross = [v.strip() for v in request.args.getlist('categoria_cross') if v.strip()]
    if categoria_cross:
        vals = ','.join([f"'{_esc(v)}'" for v in categoria_cross])
        clauses.append(f"COALESCE(CATEGORIA_ITEM, 'Sem categoria') IN ({vals})")
    macro_categoria_cross = [v.strip() for v in request.args.getlist('macro_categoria_cross') if v.strip()]
    if macro_categoria_cross:
        vals = ','.join([f"'{_esc(v)}'" for v in macro_categoria_cross])
        clauses.append(f"COALESCE(MACRO_CATEGORIA, 'Indiretos') IN ({vals})")
    tipo_vendor_cross = [v.strip() for v in request.args.getlist('tipo_vendor_cross') if v.strip()]
    if tipo_vendor_cross:
        vals = ','.join([f"'{_esc(v)}'" for v in tipo_vendor_cross])
        clauses.append(f"COALESCE(TIPO_VENDOR, 'N\u00e3o classificado') IN ({vals})")
    w = _where(clauses)

    sql = f"""
    SELECT
        EMPRESA AS empresa,
        SUM(VALOR_LIQUIDO_BRL)::float AS net_spend
    FROM notas_ri
    {w}
    {'AND' if clauses else 'WHERE'} EMPRESA IN ('BB', 'BQ')
    GROUP BY EMPRESA
    ORDER BY net_spend DESC
    """
    return jsonify(query(sql))


@app.route('/api/spend/by-item')
def spend_by_item():
    """Top items by Net Spend."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)
    limit = request.args.get('limit', '15')

    sql = f"""
    SELECT
        COALESCE(DESCRICAO_ITEM, DS_ITEM, 'Sem descrição') AS item,
        SUM(VALOR_LIQUIDO_BRL) AS net_spend
    FROM notas_ri
    {w}
    GROUP BY COALESCE(DESCRICAO_ITEM, DS_ITEM, 'Sem descrição')
    ORDER BY net_spend DESC
    LIMIT {int(limit)}
    """
    total = query(f"SELECT SUM(VALOR_LIQUIDO_BRL) AS total FROM notas_ri {w}", params)
    rows = query(sql, params)
    return jsonify({'rows': rows, 'total': total[0]['total'] if total else 0})


@app.route('/api/spend/by-supplier')
def spend_by_supplier():
    """Top suppliers by Net Spend."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)
    limit = request.args.get('limit', '10')

    sql = f"""
    SELECT
        COALESCE(NOME_FORNECEDOR, 'Não identificado') AS fornecedor,
        SUM(VALOR_LIQUIDO_BRL) AS net_spend,
        COUNT(DISTINCT NOTA_FISCAL) AS qtd_notas
    FROM notas_ri
    {w}
    GROUP BY COALESCE(NOME_FORNECEDOR, 'Não identificado')
    ORDER BY net_spend DESC
    LIMIT {int(limit)}
    """
    total = query(f"SELECT SUM(VALOR_LIQUIDO_BRL) AS total FROM notas_ri {w}", params)
    rows = query(sql, params)
    return jsonify({'rows': rows, 'total': total[0]['total'] if total else 0})


@app.route('/api/spend/by-plant')
def spend_by_plant():
    """Spend by plant (receiving location). Uses LOCAL column which correctly
    associates plants with their company (BBR=BB, BQB=BQ)."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)

    sql = f"""
    SELECT
        COALESCE(PLANTA, 'Não identificada') AS unidade,
        SUM(VALOR_LIQUIDO_BRL) AS net_spend
    FROM notas_ri
    {w}
    GROUP BY COALESCE(PLANTA, 'Não identificada')
    HAVING SUM(VALOR_LIQUIDO_BRL) > 0
    ORDER BY net_spend DESC
    """
    total = query(f"SELECT SUM(VALOR_LIQUIDO_BRL) AS total FROM notas_ri {w}", params)
    rows = query(sql, params)
    return jsonify({'rows': rows, 'total': total[0]['total'] if total else 0})


@app.route('/api/spend/by-macro-category')
def spend_by_macro_category():
    """Spend by macro category (macro_categoria)."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)

    sql = f"""
    SELECT
        COALESCE(MACRO_CATEGORIA, 'Indiretos') AS macro_categoria,
        SUM(VALOR_LIQUIDO_BRL) AS net_spend
    FROM notas_ri
    {w}
    GROUP BY COALESCE(MACRO_CATEGORIA, 'Indiretos')
    HAVING SUM(VALOR_LIQUIDO_BRL) > 0
    ORDER BY net_spend DESC
    """
    return jsonify(query(sql, params))


@app.route('/api/spend/by-category')
def spend_by_category():
    """Spend by category."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)

    sql = f"""
    SELECT
        COALESCE(CATEGORIA_ITEM, 'Sem categoria') AS categoria,
        SUM(VALOR_LIQUIDO_BRL) AS net_spend
    FROM notas_ri
    {w}
    GROUP BY COALESCE(CATEGORIA_ITEM, 'Sem categoria')
    HAVING SUM(VALOR_LIQUIDO_BRL) > 0
    ORDER BY net_spend DESC
    LIMIT 15
    """
    return jsonify(query(sql, params))


@app.route('/api/spend/by-tipo-vendor')
def spend_by_tipo_vendor():
    """Spend by vendor type (tipo_vendor)."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)

    sql = f"""
    SELECT
        COALESCE(TIPO_VENDOR, 'Não classificado') AS tipo_vendor,
        SUM(VALOR_LIQUIDO_BRL) AS net_spend
    FROM notas_ri
    {w}
    GROUP BY COALESCE(TIPO_VENDOR, 'Não classificado')
    HAVING SUM(VALOR_LIQUIDO_BRL) > 0
    ORDER BY net_spend DESC
    LIMIT 15
    """
    return jsonify(query(sql, params))


@app.route('/api/spend/abc')
def spend_abc():
    """Dynamic ABC analysis."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)
    dimension = request.args.get('dimension', 'item')  # item, category, supplier

    col_map = {
        'item': "COALESCE(DESCRICAO_ITEM, DS_ITEM, 'Sem descrição')",
        'category': "COALESCE(CATEGORIA_ITEM, 'Sem categoria')",
        'supplier': "COALESCE(NOME_FORNECEDOR, 'Não identificado')",
    }
    col = col_map.get(dimension, col_map['item'])

    sql = f"""
    WITH ranked AS (
        SELECT
            {col} AS dimension_value,
            SUM(VALOR_LIQUIDO_BRL) AS net_spend
        FROM notas_ri
        {w}
        GROUP BY {col}
        HAVING SUM(VALOR_LIQUIDO_BRL) > 0
    ),
    total AS (
        SELECT SUM(net_spend) AS grand_total FROM ranked
    ),
    cumulative AS (
        SELECT
            dimension_value,
            net_spend,
            SUM(net_spend) OVER (ORDER BY net_spend DESC) / (SELECT grand_total FROM total) * 100 AS cum_pct
        FROM ranked
    )
    SELECT
        CASE
            WHEN cum_pct <= 80 THEN 'A'
            WHEN cum_pct <= 95 THEN 'B'
            ELSE 'C'
        END AS abc_class,
        COUNT(*) AS item_count,
        SUM(net_spend) AS class_spend
    FROM cumulative
    GROUP BY CASE
            WHEN cum_pct <= 80 THEN 'A'
            WHEN cum_pct <= 95 THEN 'B'
            ELSE 'C'
        END
    ORDER BY abc_class
    """
    return jsonify(query(sql, params))


@app.route('/api/spend/abc-detail')
def spend_abc_detail():
    """Detail items for a given ABC class."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)
    dimension = request.args.get('dimension', 'item')
    abc_class = request.args.get('abc_class', '').upper()
    class_filter = f"WHERE abc_class = '{_esc(abc_class)}'" if abc_class else ""

    col_map = {
        'item': "COALESCE(DESCRICAO_ITEM, DS_ITEM, 'Sem descrição')",
        'category': "COALESCE(CATEGORIA_ITEM, 'Sem categoria')",
        'supplier': "COALESCE(NOME_FORNECEDOR, 'Não identificado')",
    }
    col = col_map.get(dimension, col_map['item'])

    # Include codigo_item when dimension is 'item'
    extra_col = ", MIN(CODIGO_ITEM) AS codigo_item" if dimension == 'item' else ""
    extra_select = ", codigo_item" if dimension == 'item' else ""

    sql = f"""
    WITH ranked AS (
        SELECT
            {col} AS dimension_value,
            SUM(VALOR_LIQUIDO_BRL) AS net_spend
            {extra_col}
        FROM notas_ri
        {w}
        GROUP BY {col}
        HAVING SUM(VALOR_LIQUIDO_BRL) > 0
    ),
    total AS (
        SELECT SUM(net_spend) AS grand_total FROM ranked
    ),
    cumulative AS (
        SELECT
            dimension_value,
            net_spend,
            SUM(net_spend) OVER (ORDER BY net_spend DESC) / (SELECT grand_total FROM total) * 100 AS cum_pct,
            (net_spend / (SELECT grand_total FROM total) * 100) AS pct_of_total
            {extra_select}
        FROM ranked
    ),
    classified AS (
        SELECT *,
            CASE
                WHEN cum_pct <= 80 THEN 'A'
                WHEN cum_pct <= 95 THEN 'B'
                ELSE 'C'
            END AS abc_class
        FROM cumulative
    )
    SELECT dimension_value AS item, net_spend::float, pct_of_total::float AS pct, cum_pct::float {extra_select}
    FROM classified
    {class_filter}
    ORDER BY net_spend DESC
    """
    return jsonify(query(sql, params))


@app.route('/api/spend/centralization-table')
def spend_centralization_table():
    """Supplier centralization table."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)

    sql = f"""
    SELECT
        COALESCE(NOME_FORNECEDOR, 'Não identificado') AS fornecedor,
        SUM(VALOR_LIQUIDO_BRL) AS net_spend,
        SUM(CASE WHEN CENTRALIZADO = 'CENTRALIZADO' THEN VALOR_LIQUIDO_BRL ELSE 0 END) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0) * 100 AS centralization_pct
    FROM notas_ri
    {w}
    GROUP BY COALESCE(NOME_FORNECEDOR, 'Não identificado')
    HAVING SUM(VALOR_LIQUIDO_BRL) > 0
    ORDER BY net_spend DESC
    LIMIT 50
    """
    return jsonify(query(sql, params))


# ═══════════════════════════════════════════════════════════════════════════════
# API: PAGE 03 — PURCHASE ORDER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/orders/kpis')
def orders_kpis():
    """Open value, open POs, late POs, avg delay.
    - Valor em Aberto: uses dt_promessa as date reference (Jan through current month)
    - Uses valor_original_brl (converted to BRL via taxa_cambio)
    """
    # Build entity-only filters (empresa, grupo, fornecedor) — date is handled separately
    clauses = []
    empresa = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    if empresa:
        vals = ','.join([f"'{_esc(e)}'" for e in empresa])
        clauses.append(f"org_desc IN ({vals})")
    grupo = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
    if grupo:
        vals = ','.join([f"'{_esc(g)}'" for g in grupo])
        clauses.append(f"grupo_compras_oc IN ({vals})")
    fornecedor = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
    if fornecedor:
        vals = ','.join([f"'{_esc(f_)}'" for f_ in fornecedor])
        clauses.append(f"nome_fornecedor IN ({vals})")
    is_forn_esp = [v.strip() for v in request.args.getlist('is_fornecedor_especial') if v.strip()]
    if is_forn_esp:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_esp])
        clauses.append(f"is_fornecedor_especial IN ({vals})")
    is_forn_nn = [v.strip() for v in request.args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"is_fornecedor_nao_negociavel IN ({vals})")
    comprador = [c.strip() for c in request.args.getlist('comprador') if c.strip()]
    if comprador:
        vals = ','.join([f"'{_esc(c)}'" for c in comprador])
        clauses.append(f"nome_usuario IN ({vals})")
    # Advanced filters
    tipo_oc = [t.strip() for t in request.args.getlist('tipo_oc') if t.strip()]
    if tipo_oc:
        vals = ','.join([f"'{_esc(t)}'" for t in tipo_oc])
        clauses.append(f"tipo IN ({vals})")
    unidade = [u.strip() for u in request.args.getlist('unidade') if u.strip()]
    if unidade:
        vals = ','.join([f"'{_esc(u)}'" for u in unidade])
        clauses.append(f"unidade IN ({vals})")
    categoria_item = [c.strip() for c in request.args.getlist('categoria_item') if c.strip()]
    if categoria_item:
        vals = ','.join([f"'{_esc(c)}'" for c in categoria_item])
        clauses.append(f"categoria_item IN ({vals})")
    macro_categoria = [c.strip() for c in request.args.getlist('macro_categoria') if c.strip()]
    if macro_categoria:
        vals = ','.join([f"'{_esc(c)}'" for c in macro_categoria])
        clauses.append(f"COALESCE(macro_categoria, 'Indiretos') IN ({vals})")
    status_fech = [s.strip() for s in request.args.getlist('status_fechamento') if s.strip()]
    if status_fech:
        vals = ','.join([f"'{_esc(s)}'" for s in status_fech])
        clauses.append(f"STATUS_FECHAMENTO IN ({vals})")
    else:
        clauses.append("STATUS_FECHAMENTO = 'ABERTA'")

    # Date filter: dt_promessa — respects user's year and month selections
    ano = [a.strip() for a in request.args.getlist('ano') if a.strip()]
    if ano:
        vals = ','.join([f"'{_esc(a)}'" for a in ano])
        clauses.append(f"SUBSTRING(dt_promessa, 1, 4) IN ({vals})")
    mes = [m.strip() for m in request.args.getlist('mes') if m.strip()]
    if mes:
        vals = ','.join([m for m in mes])
        clauses.append(f"CAST(SUBSTRING(dt_promessa, 6, 2) AS INT) IN ({vals})")
    clauses.append("dt_promessa IS NOT NULL")

    w = _where(clauses)
    sql = f"""
    SELECT
        SUM(GREATEST(0, COALESCE(valor_original_brl, 0) - COALESCE(valor_utilizado_brl, 0))) AS open_value,
        COUNT(DISTINCT NUMERO_OC) AS open_pos,
        COUNT(DISTINCT CASE WHEN (CURRENT_DATE - dt_promessa::date) > 0 THEN NUMERO_OC END) AS late_pos,
        ROUND(AVG(CASE WHEN (CURRENT_DATE - dt_promessa::date) > 0 THEN (CURRENT_DATE - dt_promessa::date) END))::int AS avg_delay,
        SUM(CASE WHEN (CURRENT_DATE - dt_promessa::date) > 0 THEN GREATEST(0, COALESCE(valor_original_brl, 0) - COALESCE(valor_utilizado_brl, 0)) ELSE 0 END) AS late_value
    FROM ordens_compra
    {w}
    """
    return jsonify(query(sql))


@app.route('/api/orders/planned-vs-realized')
def orders_planned_vs_realized():
    """Planned vs realized by month.
    Uses dt_promessa as date reference (consistent with KPI card).
    Entity filters only — no data_oc filtering."""
    ano_raw = request.args.get('ano', str(date.today().year))
    try:
        ano = int(ano_raw)
    except (ValueError, TypeError):
        ano = date.today().year
    # Entity-only filters (same as KPI) — NO data_oc filter
    clauses = []
    empresa = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    if empresa:
        vals = ','.join([f"'{_esc(e)}'" for e in empresa])
        clauses.append(f"org_desc IN ({vals})")
    grupo = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
    if grupo:
        vals = ','.join([f"'{_esc(g)}'" for g in grupo])
        clauses.append(f"grupo_compras_oc IN ({vals})")
    fornecedor = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
    if fornecedor:
        vals = ','.join([f"'{_esc(f_)}'" for f_ in fornecedor])
        clauses.append(f"nome_fornecedor IN ({vals})")
    is_forn_esp = [v.strip() for v in request.args.getlist('is_fornecedor_especial') if v.strip()]
    if is_forn_esp:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_esp])
        clauses.append(f"is_fornecedor_especial IN ({vals})")
    is_forn_nn = [v.strip() for v in request.args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"is_fornecedor_nao_negociavel IN ({vals})")
    comprador = [c.strip() for c in request.args.getlist('comprador') if c.strip()]
    if comprador:
        vals = ','.join([f"'{_esc(c)}'" for c in comprador])
        clauses.append(f"nome_usuario IN ({vals})")
    tipo_oc = [t.strip() for t in request.args.getlist('tipo_oc') if t.strip()]
    if tipo_oc:
        vals = ','.join([f"'{_esc(t)}'" for t in tipo_oc])
        clauses.append(f"tipo IN ({vals})")
    unidade = [u.strip() for u in request.args.getlist('unidade') if u.strip()]
    if unidade:
        vals = ','.join([f"'{_esc(u)}'" for u in unidade])
        clauses.append(f"unidade IN ({vals})")
    categoria_item = [c.strip() for c in request.args.getlist('categoria_item') if c.strip()]
    if categoria_item:
        vals = ','.join([f"'{_esc(c)}'" for c in categoria_item])
        clauses.append(f"categoria_item IN ({vals})")
    macro_categoria = [c.strip() for c in request.args.getlist('macro_categoria') if c.strip()]
    if macro_categoria:
        vals = ','.join([f"'{_esc(c)}'" for c in macro_categoria])
        clauses.append(f"COALESCE(macro_categoria, 'Indiretos') IN ({vals})")
    status_fech = [s.strip() for s in request.args.getlist('status_fechamento') if s.strip()]
    if status_fech:
        vals = ','.join([f"'{_esc(s)}'" for s in status_fech])
        clauses.append(f"STATUS_FECHAMENTO IN ({vals})")
    and_f = (" AND " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
    SELECT
        TO_CHAR(dt_promessa::date, 'YYYY-MM') AS mes,
        SUM(COALESCE(valor_utilizado_brl, 0)) AS realized,
        SUM(CASE WHEN STATUS_FECHAMENTO = 'ABERTA'
            THEN GREATEST(0, COALESCE(valor_original_brl, 0) - COALESCE(valor_utilizado_brl, 0))
            ELSE 0 END) AS remaining
    FROM ordens_compra
    WHERE dt_promessa IS NOT NULL
      AND EXTRACT(YEAR FROM dt_promessa::date)::int = {ano}
      {and_f}
    GROUP BY TO_CHAR(dt_promessa::date, 'YYYY-MM')
    ORDER BY mes
    """
    return jsonify(query(sql))


@app.route('/api/orders/overdue-by-supplier')
def orders_overdue_by_supplier():
    """Overdue value by supplier. Uses dt_promessa for delay calculation."""
    clauses = []
    empresa = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    if empresa:
        vals = ','.join([f"'{_esc(e)}'" for e in empresa])
        clauses.append(f"org_desc IN ({vals})")
    grupo = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
    if grupo:
        vals = ','.join([f"'{_esc(g)}'" for g in grupo])
        clauses.append(f"grupo_compras_oc IN ({vals})")
    fornecedor = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
    if fornecedor:
        vals = ','.join([f"'{_esc(f_)}'" for f_ in fornecedor])
        clauses.append(f"nome_fornecedor IN ({vals})")
    is_forn_esp = [v.strip() for v in request.args.getlist('is_fornecedor_especial') if v.strip()]
    if is_forn_esp:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_esp])
        clauses.append(f"is_fornecedor_especial IN ({vals})")
    is_forn_nn = [v.strip() for v in request.args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"is_fornecedor_nao_negociavel IN ({vals})")
    comprador = [c.strip() for c in request.args.getlist('comprador') if c.strip()]
    if comprador:
        vals = ','.join([f"'{_esc(c)}'" for c in comprador])
        clauses.append(f"nome_usuario IN ({vals})")
    tipo_oc = [t.strip() for t in request.args.getlist('tipo_oc') if t.strip()]
    if tipo_oc:
        vals = ','.join([f"'{_esc(t)}'" for t in tipo_oc])
        clauses.append(f"tipo IN ({vals})")
    unidade = [u.strip() for u in request.args.getlist('unidade') if u.strip()]
    if unidade:
        vals = ','.join([f"'{_esc(u)}'" for u in unidade])
        clauses.append(f"unidade IN ({vals})")
    categoria_item = [ci.strip() for ci in request.args.getlist('categoria_item') if ci.strip()]
    if categoria_item:
        vals = ','.join([f"'{_esc(ci)}'" for ci in categoria_item])
        clauses.append(f"categoria_item IN ({vals})")
    macro_categoria = [c.strip() for c in request.args.getlist('macro_categoria') if c.strip()]
    if macro_categoria:
        vals = ','.join([f"'{_esc(c)}'" for c in macro_categoria])
        clauses.append(f"COALESCE(macro_categoria, 'Indiretos') IN ({vals})")
    status_fech = [s.strip() for s in request.args.getlist('status_fechamento') if s.strip()]
    if status_fech:
        vals = ','.join([f"'{_esc(s)}'" for s in status_fech])
        clauses.append(f"STATUS_FECHAMENTO IN ({vals})")
    else:
        clauses.append("STATUS_FECHAMENTO = 'ABERTA'")
    ano = [a.strip() for a in request.args.getlist('ano') if a.strip()]
    if ano:
        vals = ','.join([f"'{_esc(a)}'" for a in ano])
        clauses.append(f"SUBSTRING(dt_promessa, 1, 4) IN ({vals})")
    mes = [m.strip() for m in request.args.getlist('mes') if m.strip()]
    if mes:
        vals = ','.join([m for m in mes])
        clauses.append(f"CAST(SUBSTRING(dt_promessa, 6, 2) AS INT) IN ({vals})")
    clauses.append("dt_promessa IS NOT NULL")
    and_f = (" AND " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
    SELECT
        COALESCE(nome_fornecedor, 'Não identificado') AS fornecedor,
        SUM(GREATEST(0, COALESCE(valor_original_brl, 0) - COALESCE(valor_utilizado_brl, 0))) AS open_value,
        ROUND(AVG(CURRENT_DATE - dt_promessa::date))::int AS avg_days_late,
        COUNT(DISTINCT NUMERO_OC) AS qty
    FROM ordens_compra
    WHERE (CURRENT_DATE - dt_promessa::date) > 0
      {and_f}
    GROUP BY COALESCE(nome_fornecedor, 'Não identificado')
    ORDER BY open_value DESC
    LIMIT 10
    """
    return jsonify(query(sql))


@app.route('/api/orders/delay-buckets')
def orders_delay_buckets():
    """Open orders by delay bucket (deduplicated by OC, same logic as KPIs).
    Uses dt_promessa as date reference (consistent with KPI card)."""
    clauses = []
    empresa = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    if empresa:
        vals = ','.join([f"'{_esc(e)}'" for e in empresa])
        clauses.append(f"org_desc IN ({vals})")
    grupo = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
    if grupo:
        vals = ','.join([f"'{_esc(g)}'" for g in grupo])
        clauses.append(f"grupo_compras_oc IN ({vals})")
    fornecedor = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
    if fornecedor:
        vals = ','.join([f"'{_esc(f_)}'" for f_ in fornecedor])
        clauses.append(f"nome_fornecedor IN ({vals})")
    is_forn_esp = [v.strip() for v in request.args.getlist('is_fornecedor_especial') if v.strip()]
    if is_forn_esp:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_esp])
        clauses.append(f"is_fornecedor_especial IN ({vals})")
    is_forn_nn = [v.strip() for v in request.args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"is_fornecedor_nao_negociavel IN ({vals})")
    comprador = [c.strip() for c in request.args.getlist('comprador') if c.strip()]
    if comprador:
        vals = ','.join([f"'{_esc(c)}'" for c in comprador])
        clauses.append(f"nome_usuario IN ({vals})")
    tipo_oc = [t.strip() for t in request.args.getlist('tipo_oc') if t.strip()]
    if tipo_oc:
        vals = ','.join([f"'{_esc(t)}'" for t in tipo_oc])
        clauses.append(f"tipo IN ({vals})")
    unidade = [u.strip() for u in request.args.getlist('unidade') if u.strip()]
    if unidade:
        vals = ','.join([f"'{_esc(u)}'" for u in unidade])
        clauses.append(f"unidade IN ({vals})")
    categoria_item = [ci.strip() for ci in request.args.getlist('categoria_item') if ci.strip()]
    if categoria_item:
        vals = ','.join([f"'{_esc(ci)}'" for ci in categoria_item])
        clauses.append(f"categoria_item IN ({vals})")
    macro_categoria = [c.strip() for c in request.args.getlist('macro_categoria') if c.strip()]
    if macro_categoria:
        vals = ','.join([f"'{_esc(c)}'" for c in macro_categoria])
        clauses.append(f"COALESCE(macro_categoria, 'Indiretos') IN ({vals})")
    status_fech = [s.strip() for s in request.args.getlist('status_fechamento') if s.strip()]
    if status_fech:
        vals = ','.join([f"'{_esc(s)}'" for s in status_fech])
        clauses.append(f"STATUS_FECHAMENTO IN ({vals})")
    else:
        clauses.append("STATUS_FECHAMENTO = 'ABERTA'")
    ano = [a.strip() for a in request.args.getlist('ano') if a.strip()]
    if ano:
        vals = ','.join([f"'{_esc(a)}'" for a in ano])
        clauses.append(f"SUBSTRING(dt_promessa, 1, 4) IN ({vals})")
    mes = [m.strip() for m in request.args.getlist('mes') if m.strip()]
    if mes:
        vals = ','.join([m for m in mes])
        clauses.append(f"CAST(SUBSTRING(dt_promessa, 6, 2) AS INT) IN ({vals})")
    clauses.append("dt_promessa IS NOT NULL")
    w = _where(clauses)
    sql = f"""
    WITH oc_dedup AS (
        SELECT NUMERO_OC,
               MAX(STATUS_FECHAMENTO) AS status_fechamento,
               MAX(valor_original_brl) AS valor_original_brl,
               MIN(dt_promessa) AS dt_promessa
        FROM ordens_compra
        {w}
        GROUP BY NUMERO_OC
    ),
    oc_days AS (
        SELECT *,
               CASE WHEN dt_promessa IS NOT NULL
                    THEN GREATEST(0, CURRENT_DATE - dt_promessa::date)
                    ELSE 0 END AS dias_atraso
        FROM oc_dedup
    )
    SELECT
        CASE
            WHEN dias_atraso <= 0 THEN 'No prazo'
            WHEN dias_atraso BETWEEN 1 AND 30 THEN '1-30 dias'
            WHEN dias_atraso BETWEEN 31 AND 60 THEN '31-60 dias'
            WHEN dias_atraso BETWEEN 61 AND 90 THEN '61-90 dias'
            WHEN dias_atraso BETWEEN 91 AND 120 THEN '91-120 dias'
            ELSE '>120 dias'
        END AS bucket,
        SUM(valor_original_brl) AS valor,
        COUNT(*) AS qty
    FROM oc_days
    GROUP BY CASE
            WHEN dias_atraso <= 0 THEN 'No prazo'
            WHEN dias_atraso BETWEEN 1 AND 30 THEN '1-30 dias'
            WHEN dias_atraso BETWEEN 31 AND 60 THEN '31-60 dias'
            WHEN dias_atraso BETWEEN 61 AND 90 THEN '61-90 dias'
            WHEN dias_atraso BETWEEN 91 AND 120 THEN '91-120 dias'
            ELSE '>120 dias'
        END
    """
    return jsonify(query(sql))


@app.route('/api/orders/open-table')
def orders_open_table():
    """Open PO detail table — deduplicated by OC. Uses dt_promessa as date reference."""
    # Build filters using dt_promessa as date reference (same as KPIs)
    clauses = []
    empresa = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    if empresa:
        vals = ','.join([f"'{_esc(e)}'" for e in empresa])
        clauses.append(f"org_desc IN ({vals})")
    grupo = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
    if grupo:
        vals = ','.join([f"'{_esc(g)}'" for g in grupo])
        clauses.append(f"grupo_compras_oc IN ({vals})")
    fornecedor = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
    if fornecedor:
        vals = ','.join([f"'{_esc(f_)}'" for f_ in fornecedor])
        clauses.append(f"nome_fornecedor IN ({vals})")
    is_forn_esp = [v.strip() for v in request.args.getlist('is_fornecedor_especial') if v.strip()]
    if is_forn_esp:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_esp])
        clauses.append(f"is_fornecedor_especial IN ({vals})")
    is_forn_nn = [v.strip() for v in request.args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"is_fornecedor_nao_negociavel IN ({vals})")
    comprador = [c.strip() for c in request.args.getlist('comprador') if c.strip()]
    if comprador:
        vals = ','.join([f"'{_esc(c)}'" for c in comprador])
        clauses.append(f"nome_usuario IN ({vals})")
    tipo_oc = [t.strip() for t in request.args.getlist('tipo_oc') if t.strip()]
    if tipo_oc:
        vals = ','.join([f"'{_esc(t)}'" for t in tipo_oc])
        clauses.append(f"tipo IN ({vals})")
    unidade = [u.strip() for u in request.args.getlist('unidade') if u.strip()]
    if unidade:
        vals = ','.join([f"'{_esc(u)}'" for u in unidade])
        clauses.append(f"unidade IN ({vals})")
    categoria_item = [ci.strip() for ci in request.args.getlist('categoria_item') if ci.strip()]
    if categoria_item:
        vals = ','.join([f"'{_esc(ci)}'" for ci in categoria_item])
        clauses.append(f"categoria_item IN ({vals})")
    macro_categoria = [c.strip() for c in request.args.getlist('macro_categoria') if c.strip()]
    if macro_categoria:
        vals = ','.join([f"'{_esc(c)}'" for c in macro_categoria])
        clauses.append(f"COALESCE(macro_categoria, 'Indiretos') IN ({vals})")
    status_fech = [s.strip() for s in request.args.getlist('status_fechamento') if s.strip()]
    if status_fech:
        vals = ','.join([f"'{_esc(s)}'" for s in status_fech])
        clauses.append(f"STATUS_FECHAMENTO IN ({vals})")
    else:
        clauses.append("STATUS_FECHAMENTO = 'ABERTA'")
    # Date filter on dt_promessa
    ano = [a.strip() for a in request.args.getlist('ano') if a.strip()]
    if ano:
        vals = ','.join([f"'{_esc(a)}'" for a in ano])
        clauses.append(f"SUBSTRING(dt_promessa, 1, 4) IN ({vals})")
    mes = [m.strip() for m in request.args.getlist('mes') if m.strip()]
    if mes:
        vals = ','.join([m for m in mes])
        clauses.append(f"CAST(SUBSTRING(dt_promessa, 6, 2) AS INT) IN ({vals})")
    clauses.append("dt_promessa IS NOT NULL")

    and_f = (" AND " + " AND ".join(clauses)) if clauses else ""
    per_page = int(request.args.get('per_page', '50'))

    sql = f"""
    WITH oc_dedup AS (
        SELECT NUMERO_OC,
               MAX(nome_fornecedor) AS fornecedor,
               MAX(nome_usuario) AS comprador,
               SUM(GREATEST(0, COALESCE(valor_original_brl, 0) - COALESCE(valor_utilizado_brl, 0))) AS open_value,
               MIN(dt_promessa) AS promised_date,
               CASE WHEN MIN(dt_promessa) IS NOT NULL
                    THEN GREATEST(0, CURRENT_DATE - MIN(dt_promessa)::date)
                    ELSE 0 END AS days_late
        FROM ordens_compra
        WHERE 1=1 {and_f}
        GROUP BY NUMERO_OC
    )
    SELECT NUMERO_OC AS "NUMERO_OC", fornecedor AS "FORNECEDOR", comprador,
           open_value, promised_date, days_late
    FROM oc_dedup
    ORDER BY days_late DESC NULLS LAST
    LIMIT {per_page}
    """
    rows = query(sql)
    return jsonify({'rows': rows})


# ═══════════════════════════════════════════════════════════════════════════════
# API: PAGE 04 — COMMERCIAL CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/filters/comercial')
def filters_comercial():
    """Filter options for comercial page — suppliers with actual spend, ordered by spend desc."""
    result = {}
    result['anos'] = [r['ano'] for r in query(
        "SELECT DISTINCT SUBSTRING(DATA_LANCAMENTO, 1, 4) AS ano FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL ORDER BY ano DESC"
    )]
    result['meses'] = [r['mes'] for r in query(
        "SELECT DISTINCT CAST(SUBSTRING(DATA_LANCAMENTO, 6, 2) AS INT) AS mes FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL ORDER BY mes"
    )]
    result['empresas'] = [r['empresa'] for r in query(
        "SELECT DISTINCT EMPRESA AS empresa FROM notas_ri WHERE EMPRESA IS NOT NULL AND EMPRESA != '' ORDER BY empresa"
    )]
    result['grupos'] = [r['grupo'] for r in query(
        "SELECT DISTINCT GRUPO_COMPRAS AS grupo FROM notas_ri WHERE GRUPO_COMPRAS IS NOT NULL AND GRUPO_COMPRAS != '' AND GRUPO_COMPRAS != 'COMERCIAL' ORDER BY grupo"
    )]
    # Suppliers ordered by spend (descending) — only those with meaningful spend
    result['fornecedores'] = [r['fornecedor'] for r in query(
        "SELECT NOME_FORNECEDOR AS fornecedor, SUM(VALOR_LIQUIDO_BRL) AS spend FROM notas_ri WHERE NOME_FORNECEDOR IS NOT NULL AND NOME_FORNECEDOR != '' GROUP BY NOME_FORNECEDOR HAVING SUM(VALOR_LIQUIDO_BRL) > 0 ORDER BY spend DESC"
    )]
    return jsonify(result)


@app.route('/api/commercial/kpis')
def commercial_kpis():
    """Payment term, spend <60 days, savings."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)

    sql = f"""
    SELECT
        SUM(PGTO_X_VALOR) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0) AS avg_payment_term,
        SUM(CASE WHEN COND_PGTO_AP < 60 THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS spend_below_60,
        SUM(VALOR_LIQUIDO_BRL) AS total_spend,
        SUM(SAVING_TOTAL) AS savings_total,
        SUM(SAVING_TOTAL) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0) * 100 AS savings_pct,
        SUM(SAVING_TOTAL_ANO) / NULLIF(SUM(SAVING_TOTAL_ANO) + SUM(VALOR_LIQUIDO_BRL), 0) * 100 AS avg_saving_pct
    FROM notas_ri
    {w}
    """
    return jsonify(query(sql, params))


@app.route('/api/commercial/payment-evolution')
def commercial_payment_evolution():
    """Monthly weighted avg payment term."""
    clauses, params = _parse_filters(request.args)
    ano = request.args.getlist('ano')
    current_year = ano[0] if ano else _default_year_filter()

    # Always filter by year, plus any additional filters (empresa, grupo, fornecedor, oc_type)
    year_clause = f"SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{current_year}'"
    all_clauses = [year_clause] + [c for c in clauses if 'SUBSTRING(DATA_LANCAMENTO, 1, 4)' not in c]
    w = _where(all_clauses)

    sql = f"""
    SELECT
        SUBSTRING(DATA_LANCAMENTO, 6, 2) AS mes,
        SUM(PGTO_X_VALOR) / NULLIF(SUM(VALOR_LIQUIDO_BRL), 0) AS avg_term,
        SUM(SAVING_TOTAL) AS discount_monthly,
        SUM(PGTO_X_VALOR) AS sum_pgto,
        SUM(VALOR_LIQUIDO_BRL) AS sum_vlr
    FROM notas_ri
    {w}
    GROUP BY SUBSTRING(DATA_LANCAMENTO, 6, 2)
    ORDER BY mes
    """
    return jsonify(query(sql))


@app.route('/api/commercial/payment-distribution')
def commercial_payment_distribution():
    """Net Spend distribution by payment-term bucket."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)

    sql = f"""
    SELECT
        FAIXA_PRAZO_PAGAMENTO AS bucket,
        SUM(VALOR_LIQUIDO_BRL) AS net_spend
    FROM notas_ri
    {w}
    GROUP BY FAIXA_PRAZO_PAGAMENTO
    ORDER BY bucket
    """
    return jsonify(query(sql, params))


@app.route('/api/commercial/suppliers-below-60')
def commercial_suppliers_below_60():
    """Suppliers with largest spend below 60 days."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)
    extra = " AND COND_PGTO_AP < 60" if clauses else "WHERE COND_PGTO_AP < 60"

    sql = f"""
    SELECT
        COALESCE(NOME_FORNECEDOR, 'Não identificado') AS fornecedor,
        SUM(VALOR_LIQUIDO_BRL) AS net_spend
    FROM notas_ri
    {w}{extra}
    GROUP BY COALESCE(NOME_FORNECEDOR, 'Não identificado')
    ORDER BY net_spend DESC
    LIMIT 10
    """
    return jsonify(query(sql, params))


@app.route('/api/commercial/renegotiation-table')
def commercial_renegotiation_table():
    """Renegotiation opportunities at order (NUMERO_OC) level."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)

    sql = f"""
    SELECT
        NUMERO_OC AS numero_oc,
        MAX(NOME_FORNECEDOR) AS fornecedor,
        SUM(VALOR_LIQUIDO_BRL) AS net_spend,
        MAX(COND_PGTO_AP) AS prazo
    FROM notas_ri
    {w}
    GROUP BY NUMERO_OC
    HAVING SUM(VALOR_LIQUIDO_BRL) > 0 AND MAX(COND_PGTO_AP) < 60
    ORDER BY prazo ASC, net_spend DESC
    LIMIT 500
    """
    return jsonify(query(sql, params))


# ═══════════════════════════════════════════════════════════════════════════════
# API: PAGE 05 — GOVERNANCE
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/governance/kpis')
def governance_kpis():
    """Exception KPIs."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)
    year_clause = f"SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{date.today().year}'" if not clauses else clauses[0]

    sql = f"""
    SELECT
        COUNT(DISTINCT CASE WHEN NUMERO_OC != 'Nota sem OC' AND NUMERO_OC IS NOT NULL THEN NUMERO_OC END) AS total_oc_faturadas,
        COUNT(DISTINCT NOTA_FISCAL) AS total_notas,
        COUNT(DISTINCT CASE WHEN URGENTE = 'SIM' THEN NUMERO_OC END) AS urgente_qty,
        SUM(CASE WHEN URGENTE = 'SIM' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS urgente_val,
        COUNT(DISTINCT CASE WHEN NUMERO_OC = 'Nota sem OC' THEN NOTA_FISCAL END) AS sem_oc_qty,
        SUM(CASE WHEN NUMERO_OC = 'Nota sem OC' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS sem_oc_val
    FROM notas_ri
    {w}
    """
    result = query(sql, params)

    # OC Pós-Fatura: usa coluna oc_pos_fatura calculada no ETL
    pos_fatura_sql = f"""
    SELECT COUNT(DISTINCT NUMERO_OC) AS qty, COALESCE(SUM(VALOR_LIQUIDO_BRL), 0) AS val
    FROM notas_ri
    {w}
    {'AND' if clauses else 'WHERE'} OC_POS_FATURA = 'SIM' AND NUMERO_OC != 'Nota sem OC'
    """
    pos_result = query(pos_fatura_sql)

    # Decentralized >30k (source: ordens_compra, filter by DATA_OC)
    oc_clauses_gov, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade')
    w_oc_gov = _where(oc_clauses_gov)
    decentral_sql = f"""
    SELECT COUNT(*) AS qty, SUM(valor_oc) AS valor
    FROM (
        SELECT NUMERO_OC, SUM(valor_original_brl) AS valor_oc
        FROM ordens_compra
        {w_oc_gov}
        {'AND' if oc_clauses_gov else 'WHERE'} CENTRALIZADO = 'DESCENTRALIZADO'
        AND (numero_acordo IS NULL OR numero_acordo = '')
        AND NUMERO_OC NOT IN ({_EXCL_COMPRAS_OCS})
        GROUP BY NUMERO_OC
        HAVING SUM(valor_original_brl) > 30000
    ) sub
    """
    decentral = query(decentral_sql)

    # Blanket >180 dias (entity-only filters, no date — referência: acordo_dt_criacao)
    _bla_ent = []
    _bla_emp = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    if _bla_emp:
        _bla_ent.append(f"org_desc IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _bla_emp])})")
    _bla_grp = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
    if _bla_grp:
        _bla_ent.append(f"grupo_compras_oc IN ({','.join([chr(39)+_esc(g)+chr(39) for g in _bla_grp])})")
    _bla_ent_and = 'AND ' + ' AND '.join(_bla_ent) if _bla_ent else ''
    blanket_old = query(f"""
    SELECT COUNT(*)::int AS qty, SUM(vl)::float AS valor
    FROM (
        SELECT numero_acordo, MAX(acordo_valor_total) AS vl
        FROM ordens_compra
        WHERE acordo_status = 'OPEN'
          AND numero_acordo IS NOT NULL AND numero_acordo != ''
          AND acordo_dt_criacao IS NOT NULL AND acordo_dt_criacao != ''
          AND (CURRENT_DATE - acordo_dt_criacao::date) > 180
          AND COALESCE(acordo_valor_liberado, 0) = 0
          {_bla_ent_and}
        GROUP BY numero_acordo
    ) sub
    """)

    r = result[0] if result else {}
    r['pos_fatura_qty'] = pos_result[0]['qty'] if pos_result else 0
    r['pos_fatura_val'] = pos_result[0]['val'] if pos_result else 0
    r['decentral_qty'] = decentral[0]['qty'] if decentral else 0
    r['decentral_val'] = decentral[0]['valor'] if decentral else 0
    r['blanket_old_qty'] = blanket_old[0]['qty'] if blanket_old else 0
    r['blanket_old_val'] = blanket_old[0]['valor'] if blanket_old else 0
    return jsonify(r)


@app.route('/api/governance/deviation-impact')
def governance_deviation_impact():
    """Which deviation has largest impact."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)
    and_kw = 'AND' if clauses else 'WHERE'

    # Post-invoice: usa coluna oc_pos_fatura calculada no ETL
    pos_sql = f"""SELECT COALESCE(SUM(VALOR_LIQUIDO_BRL), 0) AS val, COUNT(DISTINCT NUMERO_OC)::int AS qty
    FROM notas_ri
    {w} {and_kw} OC_POS_FATURA = 'SIM' AND NUMERO_OC != 'Nota sem OC'"""
    # Emergency
    urg_sql = f"SELECT SUM(VALOR_LIQUIDO_BRL) AS val, COUNT(DISTINCT NUMERO_OC)::int AS qty FROM notas_ri {w} {and_kw} URGENTE = 'SIM'"
    # Without PO
    sem_sql = f"SELECT SUM(VALOR_LIQUIDO_BRL) AS val, COUNT(DISTINCT NOTA_FISCAL)::int AS qty FROM notas_ri {w} {and_kw} NUMERO_OC = 'Nota sem OC'"
    # Decentralized >30k (excludes buyers from Compras area)
    dec_sql = f"""
    SELECT SUM(valor_oc) AS val, COUNT(*)::int AS qty FROM (
        SELECT NUMERO_OC, SUM(VALOR_LIQUIDO_BRL) AS valor_oc
        FROM notas_ri {w} {and_kw} CENTRALIZADO = 'DESCENTRALIZADO'
          AND NUMERO_OC != 'Nota sem OC'
          AND NUMERO_OC NOT IN ({_EXCL_COMPRAS_OCS})
          AND NUMERO_OC NOT IN ({_EXCL_ACORDO_OCS})
        GROUP BY NUMERO_OC
        HAVING SUM(VALOR_LIQUIDO_BRL) > 30000
    ) sub
    """
    # Acordos OPEN >180 dias (mesma regra da aba Governança — referência: acordo_dt_criacao)
    bla_sql = """
    SELECT SUM(vl) AS val, COUNT(*)::int AS qty FROM (
        SELECT numero_acordo, MAX(acordo_valor_total) AS vl
        FROM ordens_compra
        WHERE acordo_status = 'OPEN'
          AND numero_acordo IS NOT NULL AND numero_acordo != ''
          AND acordo_dt_criacao IS NOT NULL AND acordo_dt_criacao != ''
          AND (CURRENT_DATE - acordo_dt_criacao::date) > 180
          AND COALESCE(acordo_valor_liberado, 0) = 0
        GROUP BY numero_acordo
    ) sub
    """
    # OCs abertas > 90 dias
    oc90_sql = """
    SELECT SUM(valor_original_brl) AS val, COUNT(DISTINCT numero_oc)::int AS qty
    FROM ordens_compra
    WHERE STATUS_FECHAMENTO = 'ABERTA' AND dias_aberto > 90
    """

    results = []
    for label, s, p in [
        ('OCs p\u00f3s-fatura', pos_sql, params),
        ('OC emergencial', urg_sql, params),
        ('Notas sem OCs', sem_sql, params),
        ('OCs Descentr. >30K', dec_sql, params),
        ('OCs abertas >90 dias', oc90_sql, []),
        ('Acordos de Compra >180 dias', bla_sql, []),
    ]:
        r = query(s, p)
        results.append({'label': label, 'value': r[0]['val'] if r and r[0]['val'] else 0, 'qty': r[0].get('qty', 0) if r else 0})

    return jsonify(sorted(results, key=lambda x: x['value'] or 0, reverse=True))


@app.route('/api/governance/by-buyer')
def governance_by_buyer():
    """Buyer exceptions table with type, qty, value, and % of buyer total."""
    clauses, params = _parse_filters(request.args)
    # Separate comprador filter: apply directly on oc.NOME_USUARIO (faster than IN subquery)
    comprador_clause = None
    base_clauses = []
    for c in clauses:
        if 'CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c:
            # Extract the IN values and build direct filter
            _comp_vals = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
            if _comp_vals:
                comprador_clause = f"oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals])})"
        else:
            base_clauses.append(c)
    w = _where(base_clauses)
    comp_and = f'AND {comprador_clause}' if comprador_clause else ''
    and_kw = 'AND' if base_clauses else 'WHERE'

    sql = f"""
    WITH oc_desc_30k AS (
        SELECT NUMERO_OC
        FROM notas_ri
        {w}
        {'AND' if base_clauses else 'WHERE'} CENTRALIZADO = 'DESCENTRALIZADO' AND NUMERO_OC != 'Nota sem OC'
          AND NUMERO_OC NOT IN ({_EXCL_COMPRAS_OCS})
          AND NUMERO_OC NOT IN ({_EXCL_ACORDO_OCS})
        GROUP BY NUMERO_OC
        HAVING SUM(VALOR_LIQUIDO_BRL) > 30000
    ),
    buyer_totals AS (
        SELECT
            COALESCE(oc.NOME_USUARIO, 'Não identificado') AS buyer,
            COUNT(DISTINCT nf.NOTA_FISCAL) AS total_transactions
        FROM notas_ri nf
        LEFT JOIN (
            SELECT DISTINCT CHAVE_OC_LINHA AS _jk, NOME_USUARIO
            FROM ordens_compra
        ) oc ON nf.CHAVE_OC_LINHA = oc._jk
        {w} {comp_and}
        GROUP BY COALESCE(oc.NOME_USUARIO, 'Não identificado')
    ),
    buyer_exceptions AS (
        SELECT
            COALESCE(oc.NOME_USUARIO, 'Não identificado') AS buyer,
            MAX(oc.USUARIO) AS usuario,
            CASE
                WHEN nf.OC_POS_FATURA = 'SIM' THEN 'OCs Pós-Fatura'
                WHEN nf.URGENTE = 'SIM' THEN 'Emergencial'
                WHEN nf.CENTRALIZADO = 'DESCENTRALIZADO' AND nf.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k) THEN 'OC Descentr. >30K'
                ELSE 'Outra'
            END AS tipo_excecao,
            COUNT(DISTINCT nf.NOTA_FISCAL) AS qty,
            SUM(nf.VALOR_LIQUIDO_BRL) AS valor
        FROM notas_ri nf
        LEFT JOIN (
            SELECT DISTINCT CHAVE_OC_LINHA AS _jk, NOME_USUARIO, USUARIO
            FROM ordens_compra
        ) oc ON nf.CHAVE_OC_LINHA = oc._jk
        {w} {comp_and}
        {'AND' if (base_clauses or comprador_clause) else 'WHERE'} nf.NUMERO_OC != 'Nota sem OC'
        AND (
            (nf.OC_POS_FATURA = 'SIM')
            OR nf.URGENTE = 'SIM'
            OR (nf.CENTRALIZADO = 'DESCENTRALIZADO' AND nf.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k))
        )
        GROUP BY COALESCE(oc.NOME_USUARIO, 'Não identificado'),
                 CASE
                    WHEN nf.OC_POS_FATURA = 'SIM' THEN 'OCs Pós-Fatura'
                    WHEN nf.URGENTE = 'SIM' THEN 'Emergencial'
                    WHEN nf.CENTRALIZADO = 'DESCENTRALIZADO' AND nf.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k) THEN 'OC Descentr. >30K'
                    ELSE 'Outra'
                 END
    )
    SELECT
        be.buyer,
        be.tipo_excecao,
        be.qty,
        be.valor,
        CASE WHEN bt.total_transactions > 0
             THEN ROUND((be.qty::float / bt.total_transactions * 100)::numeric, 1)
             ELSE 0 END AS pct_transacoes,
        COALESCE(cf.area, '') AS area
    FROM buyer_exceptions be
    JOIN buyer_totals bt ON be.buyer = bt.buyer
    LEFT JOIN (SELECT DISTINCT USUARIO_ORACLE, AREA FROM compradores_funcionais) cf ON cf.USUARIO_ORACLE = be.usuario
    ORDER BY be.valor DESC
    LIMIT 200
    """
    return jsonify(query(sql))


@app.route('/api/governance/exceptions-table')
def governance_exceptions_table():
    """Exceptions detail table."""
    exc_type = request.args.get('type', 'all')
    page = int(request.args.get('page', '1'))
    per_page = int(request.args.get('per_page', '50'))
    offset = (page - 1) * per_page

    type_filter = ""
    if exc_type == 'pos_fatura':
        # Build entity filters for notas_ri
        pf_entity = []
        _pf_empresa = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
        if _pf_empresa:
            pf_entity.append(f"nf.EMPRESA IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _pf_empresa])})")
        _pf_grupo = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
        if _pf_grupo:
            pf_entity.append(f"nf.GRUPO_COMPRAS IN ({','.join([chr(39)+_esc(g)+chr(39) for g in _pf_grupo])})")
        _pf_forn = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
        if _pf_forn:
            pf_entity.append(f"nf.NOME_FORNECEDOR IN ({','.join([chr(39)+_esc(f_)+chr(39) for f_ in _pf_forn])})")
        _pf_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _pf_comp:
            pf_entity.append(f"oc.nome_usuario IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _pf_comp])})")
        pf_entity_and = 'AND ' + ' AND '.join(pf_entity) if pf_entity else ''

        # Build date filter on dt_aprovacao (outer query)
        pf_date = []
        _pf_ano = [a.strip() for a in request.args.getlist('ano') if a.strip()]
        if _pf_ano:
            pf_date.append(f"SUBSTRING(dt_aprovacao, 1, 4) IN ({','.join([chr(39)+a+chr(39) for a in _pf_ano])})")
        _pf_mes = [m.strip() for m in request.args.getlist('mes') if m.strip()]
        if _pf_mes:
            pf_date.append(f"CAST(SUBSTRING(dt_aprovacao, 6, 2) AS INT) IN ({','.join(_pf_mes)})")
        pf_date_and = 'WHERE ' + ' AND '.join(pf_date) if pf_date else ''

        # Agrupado por OC: uma linha por NUMERO_OC, usa MIN(DATA_LANCAMENTO)
        sql = f"""
        WITH oc_pos AS (
            SELECT
                nf.NUMERO_OC,
                MIN(nf.DT_NOTA) AS primeira_nf,
                MAX(oc.DT_APROVACAO) AS dt_aprovacao,
                MAX(oc.NOME_USUARIO) AS comprador,
                MAX(nf.NOME_FORNECEDOR) AS fornecedor,
                SUM(nf.VALOR_LIQUIDO_BRL) AS net_spend,
                COUNT(DISTINCT nf.NOTA_FISCAL)::int AS qty_notas
            FROM notas_ri nf
            JOIN (SELECT DISTINCT chave_oc_linha, dt_aprovacao, nome_usuario FROM ordens_compra) oc
              ON nf.chave_oc_linha = oc.chave_oc_linha
            WHERE nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != '' AND nf.NUMERO_OC != 'Nota sem OC'
              AND nf.OC_POS_FATURA = 'SIM'
              AND nf.DT_NOTA IS NOT NULL AND oc.dt_aprovacao IS NOT NULL
              {pf_entity_and}
            GROUP BY nf.NUMERO_OC
        )
        SELECT
            'OCs pós-fatura' AS tipo_excecao,
            NUMERO_OC AS "NUMERO_OC",
            qty_notas,
            primeira_nf AS data_fatura,
            dt_aprovacao AS data_oc,
            (dt_aprovacao::date - primeira_nf::date) AS dias_pos_fatura,
            comprador,
            fornecedor,
            net_spend
        FROM oc_pos
        {pf_date_and}
        ORDER BY net_spend DESC
        LIMIT {per_page} OFFSET {offset}
        """
        return jsonify(query(sql))

    # ── OC abertas >90 dias (ignores date filters, queries ordens_compra) ──
    if exc_type == 'oc_90':
        oc90_parts = ["STATUS_FECHAMENTO = 'ABERTA'", "dias_aberto > 90"]
        _oc90_emp = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
        if _oc90_emp:
            oc90_parts.append(f"org_desc IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _oc90_emp])})")
        _oc90_grp = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
        if _oc90_grp:
            oc90_parts.append(f"grupo_compras_oc IN ({','.join([chr(39)+_esc(g)+chr(39) for g in _oc90_grp])})")
        _oc90_frn = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
        if _oc90_frn:
            oc90_parts.append(f"nome_fornecedor IN ({','.join([chr(39)+_esc(f_)+chr(39) for f_ in _oc90_frn])})")
        _oc90_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _oc90_comp:
            oc90_parts.append(f"nome_usuario IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _oc90_comp])})")
        oc90_where = ' AND '.join(oc90_parts)
        sql = f"""
        SELECT 'OC aberta >90 dias' AS tipo_excecao,
               NUMERO_OC AS "NUMERO_OC",
               nome_fornecedor AS fornecedor,
               nome_usuario AS comprador,
               valor_original_brl AS net_spend,
               DATA_OC AS data_oc,
               dias_aberto,
               STATUS_FECHAMENTO AS status
        FROM ordens_compra
        WHERE {oc90_where}
        ORDER BY dias_aberto DESC
        LIMIT {per_page} OFFSET {offset}
        """
        return jsonify(query(sql))

    # ── Acordos abertos >180 dias (acordo_status='OPEN', age from acordo_dt_criacao) ──
    if exc_type == 'blanket_old':
        bla_parts = [
            "acordo_status = 'OPEN'",
            "numero_acordo IS NOT NULL",
            "numero_acordo != ''",
            "acordo_dt_criacao IS NOT NULL",
            "acordo_dt_criacao != ''",
            "(CURRENT_DATE - acordo_dt_criacao::date) > 180",
            "COALESCE(acordo_valor_liberado, 0) = 0",
        ]
        _bla_emp = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
        if _bla_emp:
            bla_parts.append(f"org_desc IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _bla_emp])})")
        _bla_grp = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
        if _bla_grp:
            bla_parts.append(f"grupo_compras_oc IN ({','.join([chr(39)+_esc(g)+chr(39) for g in _bla_grp])})")
        _bla_frn = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
        if _bla_frn:
            bla_parts.append(f"nome_fornecedor IN ({','.join([chr(39)+_esc(f_)+chr(39) for f_ in _bla_frn])})")
        _bla_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _bla_comp:
            bla_parts.append(f"nome_usuario IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _bla_comp])})")
        bla_where = ' AND '.join(bla_parts)
        sql = f"""
        SELECT 'Acordo de Compra >180 dias' AS tipo_excecao,
               numero_acordo AS "NUMERO_OC",
               MAX(nome_fornecedor) AS fornecedor,
               MAX(nome_usuario) AS comprador,
               MAX(acordo_valor_total) AS net_spend,
               MAX(DATA_OC) AS data_oc,
               (CURRENT_DATE - MAX(acordo_dt_criacao)::date) AS dias_aberto,
               MAX(acordo_dt_criacao) AS acordo_dt_criacao,
               MAX(acordo_data_final) AS acordo_data_final,
               MAX(acordo_status) AS acordo_status,
               MAX(acordo_descricao) AS acordo_descricao
        FROM ordens_compra
        WHERE {bla_where}
        GROUP BY numero_acordo
        ORDER BY (CURRENT_DATE - MAX(acordo_dt_criacao)::date) DESC
        LIMIT {per_page} OFFSET {offset}
        """
        return jsonify(query(sql))

    # ── OC Descentralizada >30k (source: ordens_compra, filter by DATA_OC) ──
    if exc_type == 'decentral':
        dec_oc_clauses, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade')
        dec_oc_base = [c for c in dec_oc_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
        dec_oc_and = 'AND ' + ' AND '.join(dec_oc_base) if dec_oc_base else ''
        sql = f"""
        SELECT 'Descentralizada' AS tipo_excecao,
               numero_oc AS "NUMERO_OC",
               MAX(nome_usuario) AS comprador,
               MAX(nome_fornecedor) AS fornecedor,
               MAX(data_oc) AS data_oc,
               SUM(valor_original_brl)::float AS net_spend
        FROM ordens_compra
        WHERE CENTRALIZADO = 'DESCENTRALIZADO'
          AND numero_oc IS NOT NULL
          AND (numero_acordo IS NULL OR numero_acordo = '')
          AND numero_oc NOT IN ({_EXCL_COMPRAS_OCS})
          {dec_oc_and}
        GROUP BY numero_oc
        HAVING SUM(valor_original_brl) > 30000
        ORDER BY net_spend DESC
        LIMIT {per_page} OFFSET {offset}
        """
        return jsonify(query(sql))

    # Demais tipos: query por linha individual
    # Build date + entity filters (default: DATA_LANCAMENTO)
    exc_clauses, _ = _parse_filters(request.args)
    # Separate comprador for direct filter on oc.NOME_USUARIO (faster)
    exc_base = [c for c in exc_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    exc_and = 'AND ' + ' AND '.join(exc_base) if exc_base else ''
    _exc_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    exc_comp_and = f"AND oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _exc_comp])})" if _exc_comp else ''

    # For emergencial: override date filter to use oc.DATA_OC
    if exc_type == 'urgente':
        urg_parts = []
        _urg_ano = [a.strip() for a in request.args.getlist('ano') if a.strip()]
        if _urg_ano:
            urg_parts.append(f"SUBSTRING(oc.DATA_OC, 1, 4) IN ({','.join([chr(39)+a+chr(39) for a in _urg_ano])})")
        _urg_mes = [m.strip() for m in request.args.getlist('mes') if m.strip()]
        if _urg_mes:
            urg_parts.append(f"CAST(SUBSTRING(oc.DATA_OC, 6, 2) AS INT) IN ({','.join(_urg_mes)})")
        _urg_emp = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
        if _urg_emp:
            urg_parts.append(f"nf.EMPRESA IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _urg_emp])})")
        _urg_grp = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
        if _urg_grp:
            urg_parts.append(f"nf.GRUPO_COMPRAS IN ({','.join([chr(39)+_esc(g)+chr(39) for g in _urg_grp])})")
        _urg_frn = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
        if _urg_frn:
            urg_parts.append(f"nf.NOME_FORNECEDOR IN ({','.join([chr(39)+_esc(f_)+chr(39) for f_ in _urg_frn])})")
        _urg_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _urg_comp:
            urg_parts.append(f"oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _urg_comp])})")
        exc_and = 'AND ' + ' AND '.join(urg_parts) if urg_parts else ''
        exc_comp_and = ''  # already handled above in urg_parts

    # Build decentral CTE for type=all (same pattern as by-buyer endpoint)
    _exc_w = _where(exc_base)
    _exc_and_kw = 'AND' if exc_base else 'WHERE'
    oc_pos_cte = f"""WITH oc_desc_30k AS (
        SELECT NUMERO_OC
        FROM notas_ri
        {_exc_w}
        {_exc_and_kw} CENTRALIZADO = 'DESCENTRALIZADO' AND NUMERO_OC != 'Nota sem OC'
          AND NUMERO_OC NOT IN ({_EXCL_COMPRAS_OCS})
          AND NUMERO_OC NOT IN ({_EXCL_ACORDO_OCS})
        GROUP BY NUMERO_OC
        HAVING SUM(VALOR_LIQUIDO_BRL) > 30000
    )"""
    type_filter = ""
    if exc_type == 'urgente':
        type_filter = "AND nf.URGENTE = 'SIM'"
    elif exc_type == 'sem_oc':
        type_filter = "AND nf.NUMERO_OC = 'Nota sem OC'"
    elif exc_type == 'decentral':
        type_filter = "AND nf.CENTRALIZADO = 'DESCENTRALIZADO' AND nf.NUMERO_OC != 'Nota sem OC' AND nf.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k)"
    else:
        type_filter = "AND ((nf.OC_POS_FATURA = 'SIM' AND nf.NUMERO_OC != 'Nota sem OC') OR nf.URGENTE = 'SIM' OR nf.NUMERO_OC = 'Nota sem OC' OR (nf.CENTRALIZADO = 'DESCENTRALIZADO' AND nf.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k)))"

    # Fixed label per type (OC can belong to multiple types simultaneously)
    tipo_label_map = {
        'urgente': "'OC emergencial'",
        'sem_oc': "'Notas sem OCs'",
        'decentral': "'Descentralizada'",
    }
    tipo_expr = tipo_label_map.get(exc_type, """
        CASE
            WHEN nf.OC_POS_FATURA = 'SIM' AND nf.NUMERO_OC != 'Nota sem OC' THEN 'OCs p\u00f3s-fatura'
            WHEN nf.URGENTE = 'SIM' THEN 'OC emergencial'
            WHEN nf.NUMERO_OC = 'Nota sem OC' THEN 'Notas sem OCs'
            WHEN nf.CENTRALIZADO = 'DESCENTRALIZADO' THEN 'Descentralizada'
            ELSE 'Outro'
        END""")

    sql = f"""
    {oc_pos_cte}
    SELECT
        {tipo_expr} AS tipo_excecao,
        CASE
            WHEN nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != '' AND nf.NUMERO_OC != 'Nota sem OC'
            THEN nf.NUMERO_OC
            ELSE oc.NUMERO_OC
        END AS "NUMERO_OC",
        nf.NOTA_FISCAL AS "NOTA_FISCAL",
        oc.NOME_USUARIO AS comprador,
        oc.AREA AS area_comprador,
        nf.NOME_FORNECEDOR AS fornecedor,
        nf.VALOR_LIQUIDO_BRL AS net_spend,
        nf.DATA_LANCAMENTO AS data_fatura,
        oc.DATA_OC AS data_emissao_oc,
        oc.DT_APROVACAO AS data_oc,
        CASE
            WHEN nf.DATA_LANCAMENTO IS NOT NULL AND oc.DT_APROVACAO IS NOT NULL
            THEN (oc.DT_APROVACAO::date - nf.DATA_LANCAMENTO::date)
            ELSE NULL
        END AS dias_pos_fatura
    FROM notas_ri nf
    LEFT JOIN (
        SELECT DISTINCT CHAVE_OC_LINHA AS _jk, NOME_USUARIO, AREA, DATA_OC, DT_APROVACAO, NUMERO_OC
        FROM ordens_compra
    ) oc ON nf.CHAVE_OC_LINHA = oc._jk
    WHERE 1=1 {type_filter} {exc_and} {exc_comp_and}
    ORDER BY nf.VALOR_LIQUIDO_BRL DESC
    LIMIT {per_page} OFFSET {offset}
    """
    return jsonify(query(sql))


# ═══════════════════════════════════════════════════════════════════════════════
# API: PAGE 06 — REPORTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/reports/data')
def reports_data():
    """Report data with pagination and dynamic source."""
    source = request.args.get('source', 'notas')  # notas, ordens, requisicoes
    page = int(request.args.get('page', '1'))
    per_page = int(request.args.get('per_page', '50'))
    offset = (page - 1) * per_page
    search = request.args.get('search', '').strip()
    sort_col = request.args.get('sort', '')
    sort_dir = request.args.get('dir', 'DESC')

    table_map = {
        'notas': 'notas_ri',
        'ordens': 'ordens_compra',
        'requisicoes': 'requisicoes',
    }
    table = table_map.get(source, 'notas_ri')

    # Build where (filters + search)
    where_parts = []
    # Apply standard filters with correct column names per source
    if source == 'notas':
        filter_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO', empresa_col='EMPRESA', grupo_col='GRUPO_COMPRAS')
        # OC Pós-fatura filter
        oc_pf = [v.strip() for v in request.args.getlist('oc_pos_fatura') if v.strip()]
        if oc_pf and len(oc_pf) == 1:
            filter_clauses.append(f"OC_POS_FATURA = '{_esc(oc_pf[0])}'")
    elif source == 'ordens':
        filter_clauses, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', fornecedor_col='nome_fornecedor', unidade_col='unidade')
        filter_clauses.append("status_aprovacao = 'APPROVED'")
    else:
        filter_clauses, _ = _parse_filters(request.args, date_col='DT_CRIACAO', empresa_col='EMPRESA', grupo_col='GRUPO_COMPRAS')
    where_parts.extend(filter_clauses)

    if search:
        if source == 'notas':
            where_parts.append(f"(NOTA_FISCAL LIKE '%{search}%' OR NOME_FORNECEDOR LIKE '%{search}%' OR DS_ITEM LIKE '%{search}%')")
        elif source == 'ordens':
            where_parts.append(f"(NUMERO_OC LIKE '%{search}%' OR nome_fornecedor LIKE '%{search}%' OR nome_usuario LIKE '%{search}%')")
        elif source == 'requisicoes':
            where_parts.append(f"(REQUISICAO LIKE '%{search}%' OR REQUISITANTE LIKE '%{search}%' OR DESCRICAO_REQ LIKE '%{search}%')")

    w = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    order = f"ORDER BY {sort_col} {sort_dir}" if sort_col else ""

    # Column selection per source
    if source == 'notas':
        cols = "NOTA_FISCAL, NUMERO_RI, NUMERO_OC, OC_POS_FATURA, EMPRESA, NOME_FORNECEDOR, CNPJ_BIMBO, DS_ITEM, CODIGO_ITEM, COALESCE(MACRO_CATEGORIA, 'Indiretos') AS MACRO_CATEGORIA, CATEGORIA_ITEM, PLANTA AS UNIDADE, DT_NOTA, DATA_LANCAMENTO, VALOR_NOTA_BRL, VALOR_LIQUIDO_BRL, SAVING_TOTAL, PRECO AS PRECO_BRL, COND_PGTO_AP, CENTRALIZADO, GRUPO_COMPRAS, CENTRO_CUSTO, CONTA_CONTABIL, QUANTIDADE, TIPO_NF, STATUS_PAGAMENTO, IS_FORNECEDOR_ESPECIAL, IS_FORNECEDOR_NAO_NEGOCIAVEL, TIPO_VENDOR, CHAVE_OC_LINHA AS LINHA_OC, URGENTE"
        if not sort_col:
            order = "ORDER BY DATA_LANCAMENTO DESC"
    elif source == 'ordens':
        cols = """NUMERO_OC, numero_acordo AS NUMERO_ACORDO, tipo AS TIPO,
                  nome_fornecedor AS FORNECEDOR, descricao AS DESCRICAO,
                  item_aquisicao AS ITEM_AQUISICAO, descricao_item AS DESCRICAO_ITEM,
                  COALESCE(macro_categoria, 'Indiretos') AS MACRO_CATEGORIA,
                  categoria_item AS CATEGORIA_ITEM, nome_usuario AS NOME_USUARIO,
                  comprador_funcional AS COMPRADOR, aprovador AS APROVADOR,
                  org_desc AS EMPRESA, unidade AS UNIDADE, area AS AREA,
                  valor_original_brl AS VALOR_ORIGINAL, valor_utilizado_brl AS VALOR_UTILIZADO, qtd_faturada AS QTD_FATURADA,
                  moeda AS MOEDA, STATUS_FECHAMENTO, DATA_OC,
                  dt_aprovacao AS DT_APROVACAO, dt_promessa AS DT_PROMESSA,
                  CENTRALIZADO, GRUPO_COMPRAS_OC, categoria_oc AS CATEGORIA_OC,
                  requisicao AS REQUISICAO, oc_atrasada AS OC_ATRASADA,
                  dias_atraso_oc AS DIAS_ATRASO_OC, dias_aberto AS DIAS_ABERTO,
                  fornecedor_especial AS FORNECEDOR_ESPECIAL,
                  is_fornecedor_especial AS IS_FORNECEDOR_ESPECIAL,
                  is_fornecedor_nao_negociavel AS IS_FORNECEDOR_NAO_NEGOCIAVEL,
                  linha_oc AS LINHA_OC, dt_fechamento AS DT_FECHAMENTO,
                  usuario AS USUARIO, nome_requisitante AS NOME_REQUISITANTE,
                  acordo_status AS ACORDO_STATUS, acordo_dt_criacao AS ACORDO_DT_CRIACAO,
                  acordo_data_inicial AS ACORDO_DATA_INICIAL, acordo_data_final AS ACORDO_DATA_FINAL,
                  acordo_valor_total AS ACORDO_VALOR_TOTAL, acordo_valor_liberado AS ACORDO_VALOR_LIBERADO,
                  acordo_descricao AS ACORDO_DESCRICAO, acordo_condicao_frete AS ACORDO_CONDICAO_FRETE,
                  acordo_condicao_pgto AS ACORDO_CONDICAO_PGTO"""
        if not sort_col:
            order = "ORDER BY DATA_OC DESC"
    else:
        cols = "REQUISICAO, EMPRESA, REQUISITANTE, DESCRICAO_REQ, NUMERO_OC, DT_CRIACAO, DT_APROVACAO, VALOR_REQUISICAO, STATUS, STATUS_ORDEM, user_requisicao AS USER_REQUISICAO, email_requisitante AS EMAIL_REQUISITANTE, user_aprovador AS USER_APROVADOR, nome_aprovador AS NOME_APROVADOR, comprador_sugerido AS COMPRADOR_SUGERIDO"
        if not sort_col:
            order = "ORDER BY DT_CRIACAO DESC"

    sql = f"SELECT {cols} FROM {table} {w} {order} LIMIT {per_page} OFFSET {offset}"
    count_sql = f"SELECT COUNT(*) AS total FROM {table} {w}"

    _log.info("[REPORTS] source=%s | where_parts=%s | SQL_WHERE=%s", source, where_parts, w)
    rows = query(sql)
    total = query(count_sql)
    return jsonify({
        'rows': rows,
        'total': total[0]['total'] if total else 0,
        'page': page,
        'per_page': per_page,
        'source': source
    })


# ═══════════════════════════════════════════════════════════════════════════════
# API: GESTÃO DE CADASTROS / TABELAS DE APOIO (LOOKUPS)
# ═══════════════════════════════════════════════════════════════════════════════

LOOKUP_CONFIG = {
    "fornecedores_especiais": {
        "title": "Fornecedores Especiais",
        "description": "Fornecedores homologados e classificados como especiais",
        "table_name": "fornecedores_especiais",
        "csv_filename": "fornecedores_especiais.csv",
        "primary_key": "cod_fornecedor_oracle",
        "columns": [
            {"key": "cod_fornecedor_oracle", "label": "Cód. Fornecedor (Oracle)", "required": True, "type": "text"},
            {"key": "nome_fornecedor_oracle", "label": "Nome Fornecedor (Oracle)", "required": True, "type": "text"},
            {"key": "produto_servico", "label": "Produto / Serviço", "required": False, "type": "text"},
            {"key": "area", "label": "Área", "required": False, "type": "text"},
            {"key": "justificativa", "label": "Justificativa", "required": False, "type": "text"},
            {"key": "data_registro", "label": "Data Registro", "required": False, "type": "text"}
        ]
    },
    "fornecedores_nao_negociaveis": {
        "title": "Fornecedores Não Negociáveis",
        "description": "Fornecedores de contratações diretas ou não negociáveis",
        "table_name": "fornecedores_nao_negociaveis",
        "csv_filename": "fornecedores_nao_negociaiveis.csv",
        "primary_key": "cod_fornecedor_oracle",
        "columns": [
            {"key": "cod_fornecedor_oracle", "label": "Cód. Fornecedor (Oracle)", "required": True, "type": "text"},
            {"key": "nome_fornecedor_oracle", "label": "Nome Fornecedor (Oracle)", "required": True, "type": "text"},
            {"key": "produto_servico", "label": "Produto / Serviço", "required": False, "type": "text"},
            {"key": "area", "label": "Área", "required": False, "type": "text"},
            {"key": "justificativa", "label": "Justificativa", "required": False, "type": "text"},
            {"key": "data_registro", "label": "Data Registro", "required": False, "type": "text"}
        ]
    },
    "compradores_funcionais": {
        "title": "Compradores Funcionais",
        "description": "Mapeamento de usuários compradores por área e unidade",
        "table_name": "compradores_funcionais",
        "csv_filename": "COMPRADORES_FUNCIONAIS(BASE_COMPRAS).csv",
        "primary_key": "usuario_oracle",
        "columns": [
            {"key": "usuario_oracle", "label": "Usuário Oracle", "required": True, "type": "text"},
            {"key": "id", "label": "ID", "required": False, "type": "text"},
            {"key": "comprador_funcional", "label": "Comprador Funcional", "required": True, "type": "text"},
            {"key": "email", "label": "E-mail", "required": False, "type": "email"},
            {"key": "area", "label": "Área", "required": False, "type": "text"},
            {"key": "unidade", "label": "Unidade", "required": False, "type": "text"},
            {"key": "operacao", "label": "Operação", "required": False, "type": "text"},
            {"key": "obs", "label": "Observações", "required": False, "type": "text"}
        ]
    }
}

_LOOKUPS_VOLUME_PATH = os.getenv("LOOKUPS_VOLUME_PATH", "/Volumes/cat_dnabb_dv/grobbcompr_cz/compras_360")
_BASE_LOOKUPS_DIR = os.getenv("LOOKUPS_DIR", "/Workspace/Shared/Databricks_Apps/BQ-Apps/compras_360")


def _get_current_user_email():
    """Extract logged in user email from Databricks Apps proxy headers."""
    email = request.headers.get("X-Forwarded-Preferred-Username") or request.headers.get("X-Forwarded-Email") or request.headers.get("X-Databricks-User-Email")
    if not email:
        email = _PG_USER or "usuario_portal"
    return str(email).strip().lower()


_DEFAULT_CADASTROS_ADMINS = [
    "renan.ferreira@grupobimbo.com"
]

_DEFAULT_CADASTROS_AUTHORIZED = [
    "rafael.lobo@grupobimbo.com"
]


def _load_cadastros_access():
    """Load authorized admins and users from cadastros_access.json or environment."""
    admins = [a.lower() for a in _DEFAULT_CADASTROS_ADMINS]
    authorized = [u.lower() for u in _DEFAULT_CADASTROS_AUTHORIZED]

    env_emails = os.getenv("CADASTROS_AUTHORIZED_EMAILS", "")
    if env_emails:
        for em in env_emails.split(","):
            cleaned = em.strip().lower()
            if cleaned and cleaned not in authorized:
                authorized.append(cleaned)

    json_candidates = [
        os.path.join(os.path.dirname(__file__), "cadastros_access.json"),
        os.path.join("src", "app", "cadastros_access.json"),
        "cadastros_access.json"
    ]
    for p in json_candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    for a in cfg.get("admins", []):
                        clean_a = str(a).strip().lower()
                        if clean_a and clean_a not in admins:
                            admins.append(clean_a)
                    for u in cfg.get("authorized_users", []):
                        clean_u = str(u).strip().lower()
                        if clean_u and clean_u not in authorized:
                            authorized.append(clean_u)
                break
            except Exception as e:
                _log.warning("Could not read cadastros_access.json: %s", e)

    return {"admins": admins, "authorized_users": authorized}


def _get_current_user_groups():
    """Extract user groups from Databricks Apps proxy headers if present."""
    raw = (
        request.headers.get("X-Forwarded-Groups")
        or request.headers.get("X-Databricks-Groups")
        or request.headers.get("X-Databricks-User-Groups")
        or ""
    )
    if not raw:
        return []
    return [g.strip().lower() for g in raw.split(",") if g.strip()]


def _is_user_authorized_for_cadastros(email):
    """Check if the email or user groups have permission to view or manage Cadastros."""
    if not email:
        return False
    clean_email = str(email).strip().lower()
    # Allow local development and postgres user
    if clean_email in ("usuario_portal", "postgres", "bimbo_lakebase_dev"):
        return True

    cfg = _load_cadastros_access()
    admins = [a.lower() for a in cfg.get("admins", [])]
    authorized = [u.lower() for u in cfg.get("authorized_users", [])]

    if clean_email in admins or clean_email in authorized:
        return True

    user_groups = _get_current_user_groups()
    for g in user_groups:
        if g in admins or g in authorized:
            return True

    return False


def _read_local_csv_fallback(csv_filename):
    """Read local CSV with fallback encodings and legacy header handling (checks Volume first)."""
    candidates = [
        os.path.join(_LOOKUPS_VOLUME_PATH, csv_filename),
        os.path.join(os.path.dirname(__file__), "..", "dados", csv_filename),
        os.path.join(os.path.dirname(__file__), "dados", csv_filename),
        os.path.join("src", "dados", csv_filename),
        os.path.join(_BASE_LOOKUPS_DIR, csv_filename),
        csv_filename
    ]
    filepath = None
    for c in candidates:
        if os.path.exists(c):
            filepath = c
            break

    lines = []
    if filepath:
        for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
            try:
                with open(filepath, "r", encoding=enc) as f:
                    lines = f.readlines()
                if lines:
                    break
            except Exception:
                continue

    # Fallback to Databricks Files SDK from Volume if not directly mounted
    if not lines:
        try:
            vol_file = f"{_LOOKUPS_VOLUME_PATH.rstrip('/')}/{csv_filename}"
            res = _w.files.download(vol_file)
            if res and res.contents:
                raw_bytes = res.contents.read()
                for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
                    try:
                        lines = raw_bytes.decode(enc).splitlines(keepends=True)
                        if lines:
                            break
                    except Exception:
                        continue
        except Exception as e:
            _log.warning("Could not download %s from Volume: %s", csv_filename, e)

    if not lines:
        return []

    # Detect header line (handle files with title rows like fornecedores_nao_negociaveis)
    header_idx = 0
    for idx, l in enumerate(lines[:12]):
        l_upper = l.upper()
        if "COD_FORNECEDOR" in l_upper or "CÓD. FORNECEDOR" in l_upper or "CD. FORNECEDOR" in l_upper or "USUARIO_ORACLE" in l_upper:
            header_idx = idx
            break

    data_text = "".join(lines[header_idx:])
    sep = ";" if ";" in lines[header_idx] else ","
    reader = csv.reader(io.StringIO(data_text), delimiter=sep)
    try:
        raw_headers = next(reader)
    except StopIteration:
        return []

    # Normalize headers
    headers = []
    for h in raw_headers:
        norm = h.strip().lower().replace(" ", "_").replace(".", "").replace("á", "a").replace("ó", "o").replace("ç", "c").replace("ã", "a")
        if "fornecedor" in norm and "cod" in norm:
            norm = "cod_fornecedor_oracle"
        elif "fornecedor" in norm and "nome" in norm:
            norm = "nome_fornecedor_oracle"
        elif "produto" in norm or "servico" in norm:
            norm = "produto_servico"
        elif "justificativa" in norm:
            norm = "justificativa"
        elif "data" in norm and "registro" in norm:
            norm = "data_registro"
        elif "usuario" in norm:
            norm = "usuario_oracle"
        elif "comprador" in norm:
            norm = "comprador_funcional"
        elif "mail" in norm:
            norm = "email"
        elif "operac" in norm:
            norm = "operacao"
        headers.append(norm)

    rows = []
    for row in reader:
        if not row or not any(row):
            continue
        item = {}
        for idx, val in enumerate(row):
            if idx < len(headers) and headers[idx]:
                item[headers[idx]] = val.strip() if val else ""
        if any(item.values()):
            rows.append(item)
    return rows


def _read_lookup_rows(table_key):
    """Fetch lookup rows from Lakebase PostgreSQL, falling back to workspace/local CSV."""
    cfg = LOOKUP_CONFIG.get(table_key)
    if not cfg:
        return [], "Tabela não configurada"

    table_name = cfg["table_name"]
    col_keys = [c["key"] for c in cfg["columns"]]
    cols_sql = ", ".join([f'"{k}"' for k in col_keys])
    order_col = cfg["primary_key"]

    # 1. Try PostgreSQL Lakebase
    try:
        sql = f'SELECT {cols_sql} FROM "{_PG_SCHEMA}"."{table_name}" ORDER BY "{order_col}" ASC'
        pg_rows = query(sql)
        if pg_rows and len(pg_rows) > 0:
            cleaned = []
            for r in pg_rows:
                cleaned.append({c["key"]: str(r.get(c["key"], "") or "") for c in cfg["columns"]})
            return cleaned, None
    except Exception as e:
        _log.warning("Could not read lookup %s from Lakebase: %s", table_key, e)

    # 2. Fallback to local / workspace CSV
    fallback_rows = _read_local_csv_fallback(cfg["csv_filename"])
    if fallback_rows:
        return fallback_rows, None

    return [], None


def _save_csv_to_volume(filename, csv_text, is_backup=False):
    """Upload or overwrite CSV in Unity Catalog Volume (cat_dnabb_dv.grobbcompr_cz.compras_360)."""
    raw_bytes = csv_text.encode('utf-8-sig')
    vol_base = _LOOKUPS_VOLUME_PATH.rstrip('/')
    rel_path = f"backups/{filename}" if is_backup else filename
    full_vol_path = f"{vol_base}/{rel_path}"

    # 1. Try writing directly if filesystem path is mounted (FUSE or cluster POSIX)
    try:
        os.makedirs(os.path.dirname(full_vol_path), exist_ok=True)
        with open(full_vol_path, "wb") as f:
            f.write(raw_bytes)
        _log.info("Saved CSV to Volume via filesystem: %s (%d bytes)", full_vol_path, len(raw_bytes))
        return True
    except Exception:
        pass

    # 2. Upload via Databricks Files SDK
    try:
        stream = io.BytesIO(raw_bytes)
        _w.files.upload(full_vol_path, stream, overwrite=True)
        _log.info("Saved CSV to Volume via Databricks SDK: %s (%d bytes)", full_vol_path, len(raw_bytes))
        return True
    except Exception as e:
        _log.warning("Could not upload to Volume (%s): %s", full_vol_path, e)
        return False


def _save_csv_to_workspace(filepath, csv_text):
    """Upload or overwrite CSV in Databricks Workspace."""
    try:
        from databricks.sdk.service.workspace import ImportFormat
        raw_bytes = csv_text.encode('utf-8')
        b64_content = base64.b64encode(raw_bytes).decode('utf-8')
        parent_dir = os.path.dirname(filepath).replace('\\', '/')
        try:
            _w.workspace.mkdirs(parent_dir)
        except Exception:
            pass
        _w.workspace.import_(
            path=filepath,
            content=b64_content,
            format=ImportFormat.RAW,
            overwrite=True
        )
        _log.info("Saved CSV to Databricks Workspace: %s (%d bytes)", filepath, len(raw_bytes))
        return True
    except Exception as e:
        _log.warning("Could not upload to Databricks Workspace (%s): %s", filepath, e)
        return False


def _save_csv_to_local(filename, csv_text, is_backup=False):
    """Save CSV to local filesystem if directory exists (dev/local)."""
    base_dirs = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dados")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "dados")),
    ]
    saved = False
    for bdir in base_dirs:
        if os.path.exists(bdir):
            target_dir = os.path.join(bdir, "backups") if is_backup else bdir
            os.makedirs(target_dir, exist_ok=True)
            target_file = os.path.join(target_dir, filename)
            try:
                with open(target_file, "w", encoding="utf-8-sig") as f:
                    f.write(csv_text)
                saved = True
            except Exception as e:
                _log.warning("Failed saving local file %s: %s", target_file, e)
    return saved


def _update_lakebase_table(table_name, col_keys, rows):
    """Bulk replace rows in Lakebase PostgreSQL table."""
    conn = None
    cur = None
    try:
        conn = _get_conn()
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(f'TRUNCATE TABLE "{_PG_SCHEMA}"."{table_name}"')
        if rows:
            cols_str = ", ".join([f'"{c}"' for c in col_keys])
            placeholders = ", ".join(["%s"] * len(col_keys))
            insert_sql = f'INSERT INTO "{_PG_SCHEMA}"."{table_name}" ({cols_str}) VALUES ({placeholders})'
            values = [[str(r.get(c, "") or "").strip() for c in col_keys] for r in rows]
            psycopg2.extras.execute_batch(cur, insert_sql, values, page_size=200)
        conn.commit()
        _log.info("Successfully updated Lakebase table %s.%s with %d rows", _PG_SCHEMA, table_name, len(rows))
        return True, None
    except Exception as e:
        if conn:
            conn.rollback()
        _log.error("Failed to update Lakebase table %s.%s: %s", _PG_SCHEMA, table_name, e)
        return False, str(e)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _recalc_lakebase_flags(table_key):
    """Recalculate supplier classification flags in notas_ri and ordens_compra."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        if table_key == "fornecedores_especiais":
            _log.info("Recalculating is_fornecedor_especial in Lakebase...")
            cur.execute(f"""
                UPDATE "{_PG_SCHEMA}"."notas_ri"
                SET is_fornecedor_especial = CASE 
                    WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_especiais") THEN 'ESPECIAL'
                    ELSE 'NÃO ESPECIAL'
                END
                WHERE is_fornecedor_especial IS DISTINCT FROM (
                    CASE WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_especiais") THEN 'ESPECIAL' ELSE 'NÃO ESPECIAL' END
                )
            """)
            cur.execute(f"""
                UPDATE "{_PG_SCHEMA}"."ordens_compra"
                SET is_fornecedor_especial = CASE 
                    WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_especiais") THEN 'ESPECIAL'
                    ELSE 'NÃO ESPECIAL'
                END
                WHERE is_fornecedor_especial IS DISTINCT FROM (
                    CASE WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_especiais") THEN 'ESPECIAL' ELSE 'NÃO ESPECIAL' END
                )
            """)
        elif table_key == "fornecedores_nao_negociaveis":
            _log.info("Recalculating is_fornecedor_nao_negociavel in Lakebase...")
            cur.execute(f"""
                UPDATE "{_PG_SCHEMA}"."notas_ri"
                SET is_fornecedor_nao_negociavel = CASE 
                    WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_nao_negociaveis") THEN 'NÃO NEGOCIAVEL'
                    ELSE 'NEGOCIAVEL'
                END
                WHERE is_fornecedor_nao_negociavel IS DISTINCT FROM (
                    CASE WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_nao_negociaveis") THEN 'NÃO NEGOCIAVEL' ELSE 'NEGOCIAVEL' END
                )
            """)
            cur.execute(f"""
                UPDATE "{_PG_SCHEMA}"."ordens_compra"
                SET is_fornecedor_nao_negociavel = CASE 
                    WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_nao_negociaveis") THEN 'NÃO NEGOCIAVEL'
                    ELSE 'NEGOCIAVEL'
                END
                WHERE is_fornecedor_nao_negociavel IS DISTINCT FROM (
                    CASE WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_nao_negociaveis") THEN 'NÃO NEGOCIAVEL' ELSE 'NEGOCIAVEL' END
                )
            """)
        conn.commit()
        cur.close()
        conn.close()
        _log.info("Flag recalculation completed for %s", table_key)
    except Exception as e:
        _log.warning("Could not recalculate flags in Lakebase (%s): %s", table_key, e)


@app.route('/api/lookups/summary')
def lookups_summary():
    """Summary of all 3 lookup tables with counts and metadata."""
    summary = []
    for key, cfg in LOOKUP_CONFIG.items():
        rows, _ = _read_lookup_rows(key)
        summary.append({
            "key": key,
            "title": cfg["title"],
            "description": cfg["description"],
            "total": len(rows),
            "csv_filename": cfg["csv_filename"],
            "primary_key": cfg["primary_key"],
            "columns_count": len(cfg["columns"])
        })
    return jsonify({
        "success": True,
        "tables": summary,
        "user": _get_current_user_email()
    })


@app.route('/api/lookups/<table_key>', methods=['GET'])
def lookups_get(table_key):
    """Retrieve full lookup dataset with schema and columns definition."""
    cfg = LOOKUP_CONFIG.get(table_key)
    if not cfg:
        return jsonify({"success": False, "error": f"Tabela '{table_key}' não encontrada."}), 404

    rows, err = _read_lookup_rows(table_key)
    return jsonify({
        "success": True,
        "table_key": table_key,
        "title": cfg["title"],
        "description": cfg["description"],
        "primary_key": cfg["primary_key"],
        "columns": cfg["columns"],
        "rows": rows,
        "total": len(rows),
        "error": err
    })


@app.route('/api/lookups/<table_key>', methods=['POST'])
def lookups_save(table_key):
    """Save updated lookup dataset: saves backup, writes CSV and updates Lakebase."""
    cfg = LOOKUP_CONFIG.get(table_key)
    if not cfg:
        return jsonify({"success": False, "error": f"Tabela '{table_key}' não encontrada."}), 404

    data = request.get_json() or {}
    raw_rows = data.get("rows", [])
    if not isinstance(raw_rows, list):
        return jsonify({"success": False, "error": "Formato inválido: 'rows' deve ser uma lista."}), 400

    col_keys = [c["key"] for c in cfg["columns"]]
    pkey = cfg["primary_key"]
    user_email = _get_current_user_email()
    if not _is_user_authorized_for_cadastros(user_email):
        return jsonify({
            "success": False,
            "error": f"Acesso negado: o usuário '{user_email}' não possui permissão para atualizar cadastros."
        }), 403
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Clean and validate
    cleaned_rows = []
    seen_pkeys = set()
    duplicates = []
    empty_pkeys = 0

    for idx, r in enumerate(raw_rows):
        if not isinstance(r, dict):
            continue
        pk_val = str(r.get(pkey, "") or "").strip()
        if not pk_val:
            empty_pkeys += 1
            continue
        if pk_val in seen_pkeys:
            duplicates.append(pk_val)
            continue
        seen_pkeys.add(pk_val)

        row_dict = {}
        for k in col_keys:
            val = r.get(k, "")
            row_dict[k] = str(val).strip() if val is not None else ""
        cleaned_rows.append(row_dict)

    if not cleaned_rows and raw_rows:
        return jsonify({
            "success": False,
            "error": f"Nenhum registro válido para salvar. Verifique o campo obrigatório '{pkey}'."
        }), 400

    # 1. Build CSV string
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([c["label"] for c in cfg["columns"]])
    for r in cleaned_rows:
        writer.writerow([r.get(k, "") for k in col_keys])
    csv_text = output.getvalue()

    # 2. Save Backup (Volume + Local + Workspace)
    backup_filename = f"{cfg['table_name']}_backup_{ts}.csv"
    _save_csv_to_volume(backup_filename, csv_text, is_backup=True)
    _save_csv_to_local(backup_filename, csv_text, is_backup=True)
    _save_csv_to_workspace(f"{_BASE_LOOKUPS_DIR}/backups/{backup_filename}", csv_text)

    # 3. Update Official CSV (Volume + Workspace + Local)
    _save_csv_to_volume(cfg['csv_filename'], csv_text, is_backup=False)
    _save_csv_to_workspace(f"{_BASE_LOOKUPS_DIR}/{cfg['csv_filename']}", csv_text)
    _save_csv_to_local(cfg["csv_filename"], csv_text, is_backup=False)

    # 4. Update Lakebase PostgreSQL
    pg_ok, pg_err = _update_lakebase_table(cfg["table_name"], col_keys, cleaned_rows)

    # 5. Recalculate flags in background thread so HTTP response is fast
    if pg_ok and table_key in ["fornecedores_especiais", "fornecedores_nao_negociaveis"]:
        threading.Thread(target=_recalc_lakebase_flags, args=(table_key,), daemon=True).start()

    _log.info("[LOOKUP SAVE] table=%s | user=%s | total_saved=%d | duplicates_ignored=%d | empty_pkeys=%d",
              table_key, user_email, len(cleaned_rows), len(duplicates), empty_pkeys)

    msg = f"{len(cleaned_rows)} registros salvos com sucesso!"
    if duplicates:
        msg += f" ({len(duplicates)} linhas com chave duplicada ignoradas)"

    return jsonify({
        "success": True,
        "message": msg,
        "count": len(cleaned_rows),
        "lakebase_updated": pg_ok,
        "lakebase_error": pg_err,
        "backup": backup_filename,
        "timestamp": ts,
        "user": user_email
    })


@app.route('/api/lookups/<table_key>/export')
def lookups_export(table_key):
    """Download current lookup data as formatted CSV with UTF-8 BOM."""
    cfg = LOOKUP_CONFIG.get(table_key)
    if not cfg:
        return jsonify({"success": False, "error": "Tabela não encontrada."}), 404

    rows, _ = _read_lookup_rows(table_key)
    col_keys = [c["key"] for c in cfg["columns"]]

    output = io.StringIO()
    # Write UTF-8 BOM
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=";")
    writer.writerow([c["label"] for c in cfg["columns"]])
    for r in rows:
        writer.writerow([r.get(k, "") for k in col_keys])

    csv_bytes = output.getvalue().encode('utf-8-sig')
    filename = f"{cfg['table_name']}_atual_{datetime.now().strftime('%Y%m%d')}.csv"

    return Response(
        csv_bytes,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route('/api/auth/me', methods=['GET'])
def api_auth_me():
    """Return logged in user info and permissions."""
    email = _get_current_user_email()
    is_auth = _is_user_authorized_for_cadastros(email)
    cfg = _load_cadastros_access()
    admins = [a.lower() for a in cfg.get("admins", [])]
    user_groups = _get_current_user_groups()
    is_admin = (
        str(email).strip().lower() in admins
        or any(g in admins for g in user_groups)
        or email in ("usuario_portal", "postgres")
    )
    return jsonify({
        "authenticated": True,
        "email": email,
        "is_admin": is_admin,
        "can_access_cadastros": is_auth
    })


@app.route('/')
def route_index():
    return send_from_directory('.', 'index.html')


@app.route('/cadastros.html')
def route_cadastros():
    email = _get_current_user_email()
    if not _is_user_authorized_for_cadastros(email):
        html = f"""<!DOCTYPE html>
<html lang="pt-BR" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <title>Acesso Restrito | Portal Compras</title>
  <style>
    body {{ display:flex; align-items:center; justify-content:center; min-height:100vh; background:#0b132b; color:#f8fafc; font-family:system-ui,-apple-system,sans-serif; margin:0; padding:1.5rem; text-align:center; }}
    .card {{ background:rgba(30,41,59,0.9); border:1px solid rgba(239,68,68,0.35); border-radius:18px; padding:2.5rem 2rem; max-width:480px; box-shadow:0 25px 50px rgba(0,0,0,0.6); }}
    .icon-box {{ width:64px; height:64px; margin:0 auto 1.25rem; border-radius:50%; background:rgba(239,68,68,0.15); display:flex; align-items:center; justify-content:center; color:#ef4444; }}
    h1 {{ font-size:1.4rem; font-weight:700; margin:0 0 0.6rem; color:#f8fafc; }}
    p {{ font-size:0.88rem; color:#94a3b8; line-height:1.5; margin:0 0 1.2rem; }}
    .user-pill {{ display:inline-block; background:rgba(239,68,68,0.12); border:1px solid rgba(239,68,68,0.25); color:#fca5a5; padding:0.3rem 0.8rem; border-radius:50px; font-weight:600; font-size:0.8rem; margin-bottom:1.8rem; word-break:break-all; }}
    .back-btn {{ display:inline-flex; align-items:center; gap:6px; padding:0.6rem 1.4rem; background:#3b82f6; color:#fff; text-decoration:none; border-radius:8px; font-weight:600; font-size:0.85rem; transition:all 0.2s; }}
    .back-btn:hover {{ background:#2563eb; transform:translateY(-1px); }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon-box">
      <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
    </div>
    <h1>Módulo de Cadastros Restrito</h1>
    <p>A gestão de tabelas de apoio e cadastros é restrita aos administradores e usuários autorizados pelo setor de Compras.</p>
    <div class="user-pill">{email}</div>
    <div>
      <a href="index.html" class="back-btn">← Voltar para a Página Inicial</a>
    </div>
  </div>
</body>
</html>"""
        return html, 403
    return send_from_directory('.', 'cadastros.html')


# ═══════════════════════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8000'))
    _log.info("Starting PORTAL COMPRAS on port %d", port)
    from waitress import serve
    serve(app, host='0.0.0.0', port=port)

