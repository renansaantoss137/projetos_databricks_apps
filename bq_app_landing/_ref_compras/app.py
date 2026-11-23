"""COMPRAS 360° — Procurement Intelligence
Flask backend using Lakebase PostgreSQL (direct connection).
"""
import logging
import os
import time
import json
import uuid
import threading
from datetime import date, timedelta
from decimal import Decimal
from flask import Flask, jsonify, request, send_from_directory
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
import psycopg2
import psycopg2.extras
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
    try:
        conn = _get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql_text)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        _log.error("Query exception: %s | Query: %s", str(e)[:300], sql_text[:200])
        return []


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

    # Unidades (planta OC)
    w = _cascading_where(request.args, exclude_field='unidade', table=base_table)
    wc = 'AND ' + ' AND '.join(w) if w else ''
    result['unidades'] = [r['v'] for r in query(
        f"SELECT DISTINCT UNIDADE AS v FROM ordens_compra WHERE UNIDADE IS NOT NULL AND UNIDADE != '' {wc} ORDER BY v"
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
    allowed = {
        'numero_ri': 'NUMERO_RI',
        'nota_fiscal': 'NOTA_FISCAL',
        'numero_oc': 'NUMERO_OC',
        'ds_item': 'DS_ITEM',
        'codigo_item': 'CODIGO_ITEM',
        'descricao_item': 'DESCRICAO_ITEM'
    }
    col = allowed.get(field)
    if not col:
        return jsonify({'error': 'invalid field'}), 400
    if len(q) < 2:
        return jsonify([])
    safe_q = q.replace("'", "''")
    rows = query(f"SELECT DISTINCT {col} AS v FROM notas_ri WHERE {col} ILIKE '%{safe_q}%' ORDER BY v LIMIT 100")
    return jsonify([r['v'] for r in rows])


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
        # Compare to previous year, limited to same date cutoff
        cur_year = int(ano[0])
        prev_year = str(cur_year - 1)
        # Prev year: up to same month+day as today
        prev_cutoff = f"{prev_year}-{today.month:02d}-{today_day:02d}"
        comp_clauses.append(f"SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{prev_year}'")
        comp_clauses.append(f"DATA_LANCAMENTO <= '{prev_cutoff}'")
        # Also limit current period to up to today
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
    # Cap previous year's current month to same day as today (fair YoY comparison)
    day_cap = f"""NOT (
        SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{prev_year}'
        AND CAST(SUBSTRING(DATA_LANCAMENTO, 6, 2) AS INT) = {current_month}
        AND CAST(SUBSTRING(DATA_LANCAMENTO, 9, 2) AS INT) > {today_day}
    )"""
    all_clauses = [year_clause, day_cap] + entity_clauses
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
    """Average lead time: Req Aprovada → Pedido Emitido → Pedido Aprovado → NF."""
    # Build filter clauses WITH table prefix to avoid ambiguity in JOINs
    nf_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO', table_prefix='nf')
    nf_where = " AND ".join(nf_clauses) if nf_clauses else "1=1"

    req_clauses, _ = _parse_filters(request.args, date_col='DT_APROVACAO', table_prefix='req')
    req_where = " AND ".join(req_clauses) if req_clauses else "1=1"

    # 1. Requisição Aprovada → Pedido Emitido (req.DT_APROVACAO → oc.DATA_OC)
    r1 = query(f"""
        SELECT AVG(oc.DATA_OC::date - req.DT_APROVACAO::date)::float AS avg_days
        FROM requisicoes req
        JOIN ordens_compra oc ON req.NUMERO_OC = oc.NUMERO_OC
        WHERE req.DT_APROVACAO IS NOT NULL AND oc.DATA_OC IS NOT NULL
          AND (oc.DATA_OC::date - req.DT_APROVACAO::date) >= 0
          AND {req_where}
    """)
    # 2. Pedido Emitido → Pedido Aprovado (oc.DATA_OC → oc.DT_APROVACAO)
    oc_clauses, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='ORG_DESC', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade')
    oc_where = " AND ".join(oc_clauses) if oc_clauses else "1=1"
    r2 = query(f"""
        SELECT AVG(DT_APROVACAO::date - DATA_OC::date)::float AS avg_days
        FROM ordens_compra
        WHERE DT_APROVACAO IS NOT NULL AND DATA_OC IS NOT NULL
          AND (DT_APROVACAO::date - DATA_OC::date) >= 0
          AND {oc_where}
    """)
    # 3. Pedido Aprovado → NF (oc.DT_APROVACAO → nf.DATA_LANCAMENTO)
    r3 = query(f"""
        SELECT AVG(nf.DATA_LANCAMENTO::date - oc.DT_APROVACAO::date)::float AS avg_days
        FROM notas_ri nf
        JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
        WHERE nf.DATA_LANCAMENTO IS NOT NULL AND oc.DT_APROVACAO IS NOT NULL
          AND nf.NUMERO_OC != 'Nota sem OC'
          AND (nf.DATA_LANCAMENTO::date - oc.DT_APROVACAO::date) >= 0
          AND {nf_where}
    """)
    # Counts per stage — filters mapped to each table's own columns
    f_empresa = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    f_ano = [a.strip() for a in request.args.getlist('ano') if a.strip()]
    f_mes = [m.strip() for m in request.args.getlist('mes') if m.strip()]
    f_dia = [d.strip() for d in request.args.getlist('dia') if d.strip()]
    f_grupo = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
    f_fornecedor = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]

    # ── c_req: requisicoes (date: DT_APROVACAO, empresa: EMPRESA, grupo: via JOIN ordens_compra)
    req_needs_join = bool(f_grupo or f_fornecedor)
    req_parts = []
    rp = "req." if req_needs_join else ""
    if f_empresa:
        vals = ','.join([f"'{_esc(e)}'" for e in f_empresa])
        req_parts.append(f"{rp}EMPRESA IN ({vals})")
    if f_ano:
        vals = ','.join([f"'{_esc(a)}'" for a in f_ano])
        req_parts.append(f"SUBSTRING({rp}DT_APROVACAO, 1, 4) IN ({vals})")
    if f_mes:
        vals = ','.join([m for m in f_mes])
        req_parts.append(f"CAST(SUBSTRING({rp}DT_APROVACAO, 6, 2) AS INT) IN ({vals})")
    if f_dia:
        vals = ','.join([d for d in f_dia])
        req_parts.append(f"CAST(SUBSTRING({rp}DT_APROVACAO, 9, 2) AS INT) IN ({vals})")
    if f_grupo:
        vals = ','.join([f"'{_esc(g)}'" for g in f_grupo])
        req_parts.append(f"oc.GRUPO_COMPRAS_OC IN ({vals})")
    if f_fornecedor:
        vals = ','.join([f"'{_esc(f_)}'" for f_ in f_fornecedor])
        req_parts.append(f"oc.NOME_FORNECEDOR IN ({vals})")
    req_count_where = " AND ".join(req_parts) if req_parts else "1=1"
    if req_needs_join:
        c_req = query(f"""
            SELECT COUNT(DISTINCT req.REQUISICAO)::int AS qty
            FROM requisicoes req
            JOIN ordens_compra oc ON req.REQUISICAO = oc.REQUISICAO
            WHERE {req_count_where}
        """)
    else:
        c_req = query(f"""
            SELECT COUNT(DISTINCT REQUISICAO)::int AS qty FROM requisicoes WHERE {req_count_where}
        """)

    # ── c_emit: ordens_compra (date: DATA_OC, empresa: ORG_DESC, grupo: GRUPO_COMPRAS_OC)
    emit_parts = []
    if f_empresa:
        vals = ','.join([f"'{_esc(e)}'" for e in f_empresa])
        emit_parts.append(f"ORG_DESC IN ({vals})")
    if f_ano:
        vals = ','.join([f"'{_esc(a)}'" for a in f_ano])
        emit_parts.append(f"SUBSTRING(DATA_OC, 1, 4) IN ({vals})")
    if f_mes:
        vals = ','.join([m for m in f_mes])
        emit_parts.append(f"CAST(SUBSTRING(DATA_OC, 6, 2) AS INT) IN ({vals})")
    if f_dia:
        vals = ','.join([d for d in f_dia])
        emit_parts.append(f"CAST(SUBSTRING(DATA_OC, 9, 2) AS INT) IN ({vals})")
    if f_grupo:
        vals = ','.join([f"'{_esc(g)}'" for g in f_grupo])
        emit_parts.append(f"GRUPO_COMPRAS_OC IN ({vals})")
    if f_fornecedor:
        vals = ','.join([f"'{_esc(f_)}'" for f_ in f_fornecedor])
        emit_parts.append(f"NOME_FORNECEDOR IN ({vals})")
    emit_where = " AND ".join(emit_parts) if emit_parts else "1=1"
    c_emit = query(f"""
        SELECT COUNT(DISTINCT NUMERO_OC)::int AS qty FROM ordens_compra WHERE {emit_where}
    """)

    # ── c_aprov: ordens_compra (date: DT_APROVACAO, empresa: ORG_DESC, grupo: GRUPO_COMPRAS_OC)
    aprov_parts = ["STATUS_APROVACAO = 'APPROVED'"]
    if f_empresa:
        vals = ','.join([f"'{_esc(e)}'" for e in f_empresa])
        aprov_parts.append(f"ORG_DESC IN ({vals})")
    if f_ano:
        vals = ','.join([f"'{_esc(a)}'" for a in f_ano])
        aprov_parts.append(f"SUBSTRING(DT_APROVACAO, 1, 4) IN ({vals})")
    if f_mes:
        vals = ','.join([m for m in f_mes])
        aprov_parts.append(f"CAST(SUBSTRING(DT_APROVACAO, 6, 2) AS INT) IN ({vals})")
    if f_dia:
        vals = ','.join([d for d in f_dia])
        aprov_parts.append(f"CAST(SUBSTRING(DT_APROVACAO, 9, 2) AS INT) IN ({vals})")
    if f_grupo:
        vals = ','.join([f"'{_esc(g)}'" for g in f_grupo])
        aprov_parts.append(f"GRUPO_COMPRAS_OC IN ({vals})")
    if f_fornecedor:
        vals = ','.join([f"'{_esc(f_)}'" for f_ in f_fornecedor])
        aprov_parts.append(f"NOME_FORNECEDOR IN ({vals})")
    aprov_where = " AND ".join(aprov_parts)
    c_aprov = query(f"""
        SELECT COUNT(DISTINCT NUMERO_OC)::int AS qty FROM ordens_compra WHERE {aprov_where}
    """)

    # ── c_nf: notas_ri (uses standard filters)
    nf_solo_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO')
    nf_solo_where = " AND ".join(nf_solo_clauses) if nf_solo_clauses else "1=1"
    c_nf = query(f"""
        SELECT COUNT(DISTINCT NOTA_FISCAL)::int AS qty FROM notas_ri WHERE {nf_solo_where}
    """)

    def _format_lead(val):
        """Convert avg_days to (value, unit). If 0 < val < 1, show hours."""
        if val is None:
            return None, 'dias'
        if val == 0:
            return 0, 'dias'
        if 0 < val < 1:
            return round(val * 24, 1), 'horas'
        return round(val, 1), 'dias'

    v1, u1 = _format_lead(r1[0]['avg_days'] if r1 else None)
    v2, u2 = _format_lead(r2[0]['avg_days'] if r2 else None)
    v3, u3 = _format_lead(r3[0]['avg_days'] if r3 else None)

    result = [{
        'req_to_po_emit_days': v1,
        'req_to_po_emit_unit': u1,
        'po_emit_to_aprov_days': v2,
        'po_emit_to_aprov_unit': u2,
        'po_to_nf_days': v3,
        'po_to_nf_unit': u3,
        'qty_req': c_req[0]['qty'] if c_req else 0,
        'qty_emit': c_emit[0]['qty'] if c_emit else 0,
        'qty_aprov': c_aprov[0]['qty'] if c_aprov else 0,
        'qty_nf': c_nf[0]['qty'] if c_nf else 0
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
    SELECT COUNT(*) AS qty, SUM(VALOR_REQUISICAO) AS valor
    FROM requisicoes
    WHERE (NUMERO_OC IS NULL OR NUMERO_OC = '')
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

    # Blanket POs open >180 days (tipo = BLANKET) — ignores date filters
    blanket_old = query(f"""
    SELECT COUNT(DISTINCT NUMERO_OC)::int AS qty,
           SUM(valor_original_brl)::float AS valor,
           COUNT(DISTINCT NUMERO_OC)::float / NULLIF(({_total_ocs_faturadas}), 0)::float * 100 AS pct
    FROM ordens_compra
    WHERE tipo = 'BLANKET'
      AND dias_aberto > 180
      {oc_entity_and}
    """)

    # Post-invoice POs — usa coluna oc_pos_fatura calculada no ETL
    # Regra: MIN(dt_nota) por NUMERO_OC < dt_aprovacao da OC
    pos_fatura = query(f"""
    SELECT COUNT(DISTINCT NUMERO_OC)::int AS qty, SUM(VALOR_LIQUIDO_BRL)::float AS valor,
           COUNT(DISTINCT NUMERO_OC)::float / NULLIF((SELECT COUNT(DISTINCT NUMERO_OC) FROM notas_ri {w_nf}), 0)::float * 100 AS pct
    FROM notas_ri
    WHERE OC_POS_FATURA = 'SIM'
      AND NUMERO_OC != 'Nota sem OC'
      {and_nf}
    """)

    # Decentralized POs > R$30k
    decentral = query(f"""
    SELECT COUNT(*)::int AS qty, SUM(valor_oc)::float AS valor,
           COUNT(*)::float / NULLIF((SELECT COUNT(DISTINCT NUMERO_OC) FROM notas_ri WHERE CENTRALIZADO = 'DESCENTRALIZADO' {and_nf}), 0)::float * 100 AS pct
    FROM (
        SELECT NUMERO_OC, SUM(VALOR_LIQUIDO_BRL) AS valor_oc
        FROM notas_ri
        WHERE CENTRALIZADO = 'DESCENTRALIZADO'
          {and_nf}
        GROUP BY NUMERO_OC
        HAVING SUM(VALOR_LIQUIDO_BRL) > 30000
    ) sub
    """)

    # OCs abertas > 90 dias — ignores date filters
    oc_90 = query(f"""
    SELECT COUNT(DISTINCT numero_oc)::int AS qty,
           SUM(valor_original_brl)::float AS valor,
           COUNT(DISTINCT numero_oc)::float / NULLIF(({_total_ocs_faturadas}), 0)::float * 100 AS pct
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

    return jsonify({
        'req_pending': req_pending[0] if req_pending else {},
        'blanket_old': blanket_old[0] if blanket_old else {},
        'pos_fatura': pos_fatura[0] if pos_fatura else {},
        'decentral': decentral[0] if decentral else {},
        'oc_90': oc_90[0] if oc_90 else {},
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
    WHERE (NUMERO_OC IS NULL OR NUMERO_OC = '')
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
    WITH oc_dedup AS (
        SELECT NUMERO_OC,
               MAX(STATUS_FECHAMENTO) AS status_fechamento,
               MAX(oc_atrasada) AS oc_atrasada,
               MAX(valor_original_brl) AS valor_original_brl,
               MAX(dias_atraso_oc) AS dias_atraso_oc
        FROM ordens_compra
        {w}
        GROUP BY NUMERO_OC
    )
    SELECT
        SUM(CASE WHEN status_fechamento = 'ABERTA' THEN valor_original_brl ELSE 0 END) AS open_value,
        COUNT(CASE WHEN status_fechamento = 'ABERTA' THEN 1 END) AS open_pos,
        COUNT(CASE WHEN oc_atrasada = 'SIM' THEN 1 END) AS late_pos,
        ROUND(AVG(CASE WHEN oc_atrasada = 'SIM' THEN dias_atraso_oc END))::int AS avg_delay
    FROM oc_dedup
    """
    return jsonify(query(sql))


@app.route('/api/orders/planned-vs-realized')
def orders_planned_vs_realized():
    """Planned vs realized by month."""
    ano_raw = request.args.get('ano', str(date.today().year))
    try:
        ano = int(ano_raw)
    except (ValueError, TypeError):
        ano = date.today().year
    clauses = _parse_order_filters(request.args, skip_mes=True)  # temporal chart: ignore month filter
    and_f = (" AND " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
    WITH oc_dedup AS (
        SELECT NUMERO_OC,
               MIN(dt_promessa) AS dt_promessa,
               MAX(valor_original_brl) AS valor_original_brl,
               MAX(VALOR_UTILIZADO) AS valor_utilizado
        FROM ordens_compra
        WHERE dt_promessa IS NOT NULL {and_f}
        GROUP BY NUMERO_OC
    )
    SELECT
        TO_CHAR(dt_promessa::date, 'YYYY-MM') AS mes,
        SUM(valor_original_brl) AS planned,
        SUM(CASE WHEN dt_promessa::date <= CURRENT_DATE THEN valor_utilizado ELSE 0 END) AS realized
    FROM oc_dedup
    WHERE EXTRACT(YEAR FROM dt_promessa::date)::int = {ano}
    GROUP BY TO_CHAR(dt_promessa::date, 'YYYY-MM')
    ORDER BY mes
    """
    return jsonify(query(sql))


@app.route('/api/orders/overdue-by-supplier')
def orders_overdue_by_supplier():
    """Overdue value by supplier."""
    clauses = _parse_order_filters(request.args)
    and_f = (" AND " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
    WITH oc_dedup AS (
        SELECT NUMERO_OC,
               MAX(nome_fornecedor) AS nome_fornecedor,
               MAX(valor_original_brl) AS valor_original_brl,
               MAX(dias_atraso_oc) AS dias_atraso_oc
        FROM ordens_compra
        WHERE oc_atrasada = 'SIM' {and_f}
        GROUP BY NUMERO_OC
    )
    SELECT
        COALESCE(nome_fornecedor, 'Não identificado') AS fornecedor,
        SUM(valor_original_brl) AS open_value,
        ROUND(AVG(dias_atraso_oc))::int AS avg_days_late,
        COUNT(*) AS qty
    FROM oc_dedup
    GROUP BY COALESCE(nome_fornecedor, 'Não identificado')
    ORDER BY open_value DESC
    LIMIT 10
    """
    return jsonify(query(sql))


@app.route('/api/orders/delay-buckets')
def orders_delay_buckets():
    """Open orders by delay bucket (deduplicated by OC, same logic as KPIs)."""
    clauses = _parse_order_filters(request.args)
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
        WHERE status_fechamento = 'ABERTA'
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
               MAX(valor_original_brl) AS open_value,
               MIN(dt_promessa) AS promised_date,
               CASE WHEN MIN(dt_promessa) IS NOT NULL
                    THEN GREATEST(0, CURRENT_DATE - MIN(dt_promessa)::date)
                    ELSE 0 END AS days_late
        FROM ordens_compra
        WHERE STATUS_FECHAMENTO = 'ABERTA' {and_f}
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

    # Decentralized >30k (aggregate at PO grain first)
    decentral_sql = f"""
    SELECT COUNT(*) AS qty, SUM(valor_oc) AS valor
    FROM (
        SELECT NUMERO_OC, SUM(VALOR_LIQUIDO_BRL) AS valor_oc
        FROM notas_ri
        {w}
        {'AND' if clauses else 'WHERE'} CENTRALIZADO = 'DESCENTRALIZADO'
        AND NUMERO_OC != 'Nota sem OC'
        GROUP BY NUMERO_OC
        HAVING SUM(VALOR_LIQUIDO_BRL) > 30000
    ) sub
    """
    decentral = query(decentral_sql, params)

    r = result[0] if result else {}
    r['pos_fatura_qty'] = pos_result[0]['qty'] if pos_result else 0
    r['pos_fatura_val'] = pos_result[0]['val'] if pos_result else 0
    r['decentral_qty'] = decentral[0]['qty'] if decentral else 0
    r['decentral_val'] = decentral[0]['valor'] if decentral else 0
    return jsonify(r)


@app.route('/api/governance/deviation-impact')
def governance_deviation_impact():
    """Which deviation has largest impact."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)
    and_kw = 'AND' if clauses else 'WHERE'

    # Post-invoice: usa coluna oc_pos_fatura calculada no ETL
    pos_sql = f"""SELECT COALESCE(SUM(VALOR_LIQUIDO_BRL), 0) AS val
    FROM notas_ri
    {w} {and_kw} OC_POS_FATURA = 'SIM' AND NUMERO_OC != 'Nota sem OC'"""
    # Emergency
    urg_sql = f"SELECT SUM(VALOR_LIQUIDO_BRL) AS val FROM notas_ri {w} {and_kw} URGENTE = 'SIM'"
    # Without PO
    sem_sql = f"SELECT SUM(VALOR_LIQUIDO_BRL) AS val FROM notas_ri {w} {and_kw} NUMERO_OC = 'Nota sem OC'"
    # Decentralized >30k
    dec_sql = f"""
    SELECT SUM(valor_oc) AS val FROM (
        SELECT NUMERO_OC, SUM(VALOR_LIQUIDO_BRL) AS valor_oc
        FROM notas_ri {w} {and_kw} CENTRALIZADO = 'DESCENTRALIZADO'
        GROUP BY NUMERO_OC
        HAVING SUM(VALOR_LIQUIDO_BRL) > 30000
    ) sub
    """
    # Blanket open >180 days (convertido para BRL)
    bla_sql = """
    SELECT SUM(VALOR_ORIGINAL * COALESCE(TAXA_CAMBIO, 1)) AS val
    FROM ordens_compra
    WHERE TIPO = 'BLANKET' AND STATUS_FECHAMENTO = 'ABERTA'
      AND (CURRENT_DATE - DATA_OC::date) > 180
    """

    results = []
    for label, s, p in [
        ('OC pós-fatura', pos_sql, params),
        ('OC emergencial', urg_sql, params),
        ('Nota sem OC', sem_sql, params),
        ('Descentralizada >R$30k', dec_sql, params),
        ('Contrato aberto >180 dias', bla_sql, []),
    ]:
        r = query(s, p)
        results.append({'label': label, 'value': r[0]['val'] if r and r[0]['val'] else 0})

    return jsonify(sorted(results, key=lambda x: x['value'] or 0, reverse=True))


@app.route('/api/governance/by-buyer')
def governance_by_buyer():
    """Buyer exceptions table with type, qty, value, and % of buyer total."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)
    and_kw = 'AND' if clauses else 'WHERE'

    sql = f"""
    WITH buyer_totals AS (
        SELECT
            COALESCE(oc.NOME_USUARIO, 'Não identificado') AS buyer,
            COUNT(DISTINCT nf.NOTA_FISCAL) AS total_transactions
        FROM notas_ri nf
        LEFT JOIN (
            SELECT DISTINCT CHAVE_OC_LINHA, NOME_USUARIO
            FROM ordens_compra
        ) oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
        {w}
        GROUP BY COALESCE(oc.NOME_USUARIO, 'Não identificado')
    ),
    buyer_exceptions AS (
        SELECT
            COALESCE(oc.NOME_USUARIO, 'Não identificado') AS buyer,
            CASE
                WHEN nf.OC_POS_FATURA = 'SIM' AND nf.NUMERO_OC != 'Nota sem OC' THEN 'OC Pós-Fatura'
                WHEN nf.URGENTE = 'SIM' THEN 'Emergencial'
                WHEN nf.NUMERO_OC = 'Nota sem OC' THEN 'Sem OC'
                ELSE 'Outra'
            END AS tipo_excecao,
            COUNT(DISTINCT nf.NOTA_FISCAL) AS qty,
            SUM(nf.VALOR_LIQUIDO_BRL) AS valor
        FROM notas_ri nf
        LEFT JOIN (
            SELECT DISTINCT CHAVE_OC_LINHA, NOME_USUARIO
            FROM ordens_compra
        ) oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
        {w}
        {'AND' if clauses else 'WHERE'} ((nf.OC_POS_FATURA = 'SIM' AND nf.NUMERO_OC != 'Nota sem OC') OR nf.URGENTE = 'SIM' OR nf.NUMERO_OC = 'Nota sem OC')
        GROUP BY COALESCE(oc.NOME_USUARIO, 'Não identificado'),
                 CASE
                    WHEN nf.OC_POS_FATURA = 'SIM' AND nf.NUMERO_OC != 'Nota sem OC' THEN 'OC Pós-Fatura'
                    WHEN nf.URGENTE = 'SIM' THEN 'Emergencial'
                    WHEN nf.NUMERO_OC = 'Nota sem OC' THEN 'Sem OC'
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
             ELSE 0 END AS pct_transacoes
    FROM buyer_exceptions be
    JOIN buyer_totals bt ON be.buyer = bt.buyer
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
            'OC pós-fatura' AS tipo_excecao,
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
        oc90_where = ' AND '.join(oc90_parts)
        sql = f"""
        SELECT 'OC aberta >90 dias' AS tipo_excecao,
               NUMERO_OC AS "NUMERO_OC",
               nome_fornecedor AS fornecedor,
               nome_usuario AS comprador,
               VALOR_ORIGINAL * COALESCE(TAXA_CAMBIO, 1) AS net_spend,
               DATA_OC AS data_oc,
               dias_aberto,
               STATUS_FECHAMENTO AS status
        FROM ordens_compra
        WHERE {oc90_where}
        ORDER BY dias_aberto DESC
        LIMIT {per_page} OFFSET {offset}
        """
        return jsonify(query(sql))

    # ── OC Blanket abertas >180 dias (ignores date filters, queries ordens_compra) ──
    if exc_type == 'blanket_old':
        bla_parts = ["tipo = 'BLANKET'", "dias_aberto > 180"]
        _bla_emp = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
        if _bla_emp:
            bla_parts.append(f"org_desc IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _bla_emp])})")
        _bla_grp = [g.strip() for g in request.args.getlist('grupo_compras') if g.strip()]
        if _bla_grp:
            bla_parts.append(f"grupo_compras_oc IN ({','.join([chr(39)+_esc(g)+chr(39) for g in _bla_grp])})")
        _bla_frn = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
        if _bla_frn:
            bla_parts.append(f"nome_fornecedor IN ({','.join([chr(39)+_esc(f_)+chr(39) for f_ in _bla_frn])})")
        bla_where = ' AND '.join(bla_parts)
        sql = f"""
        SELECT 'Blanket >180 dias' AS tipo_excecao,
               NUMERO_OC AS "NUMERO_OC",
               nome_fornecedor AS fornecedor,
               nome_usuario AS comprador,
               VALOR_ORIGINAL * COALESCE(TAXA_CAMBIO, 1) AS net_spend,
               DATA_OC AS data_oc,
               dias_aberto,
               STATUS_FECHAMENTO AS status
        FROM ordens_compra
        WHERE {bla_where}
        ORDER BY dias_aberto DESC
        LIMIT {per_page} OFFSET {offset}
        """
        return jsonify(query(sql))

    # Demais tipos: query por linha individual
    # Build date + entity filters (default: DATA_LANCAMENTO)
    exc_clauses, _ = _parse_filters(request.args)
    exc_and = 'AND ' + ' AND '.join(exc_clauses) if exc_clauses else ''

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
        exc_and = 'AND ' + ' AND '.join(urg_parts) if urg_parts else ''

    # Usa coluna oc_pos_fatura do ETL (sem CTE pesada)
    oc_pos_cte = """"""
    type_filter = ""
    if exc_type == 'urgente':
        type_filter = "AND nf.URGENTE = 'SIM'"
    elif exc_type == 'sem_oc':
        type_filter = "AND nf.NUMERO_OC = 'Nota sem OC'"
    elif exc_type == 'decentral':
        type_filter = "AND nf.CENTRALIZADO = 'DESCENTRALIZADO' AND nf.NUMERO_OC != 'Nota sem OC'"
    else:
        type_filter = "AND ((nf.OC_POS_FATURA = 'SIM' AND nf.NUMERO_OC != 'Nota sem OC') OR nf.URGENTE = 'SIM' OR nf.NUMERO_OC = 'Nota sem OC')"

    # Fixed label per type (OC can belong to multiple types simultaneously)
    tipo_label_map = {
        'urgente': "'OC emergencial'",
        'sem_oc': "'Nota sem OC'",
        'decentral': "'Descentralizada'",
    }
    tipo_expr = tipo_label_map.get(exc_type, """
        CASE
            WHEN nf.OC_POS_FATURA = 'SIM' AND nf.NUMERO_OC != 'Nota sem OC' THEN 'OC p\u00f3s-fatura'
            WHEN nf.URGENTE = 'SIM' THEN 'OC emergencial'
            WHEN nf.NUMERO_OC = 'Nota sem OC' THEN 'Nota sem OC'
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
        SELECT DISTINCT CHAVE_OC_LINHA, NOME_USUARIO, AREA, DATA_OC, DT_APROVACAO, NUMERO_OC
        FROM ordens_compra
    ) oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
    WHERE 1=1 {type_filter} {exc_and}
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
        cols = "NOTA_FISCAL, NUMERO_RI, NUMERO_OC, OC_POS_FATURA, EMPRESA, NOME_FORNECEDOR, DS_ITEM, CODIGO_ITEM, CATEGORIA_ITEM, PLANTA AS UNIDADE, DT_NOTA, DATA_LANCAMENTO, VALOR_NOTA_BRL, VALOR_LIQUIDO_BRL, SAVING_TOTAL, PRECO AS PRECO_BRL, COND_PGTO_AP, CENTRALIZADO, GRUPO_COMPRAS, CENTRO_CUSTO, CONTA_CONTABIL, QUANTIDADE, TIPO_NF, STATUS_PAGAMENTO, IS_FORNECEDOR_ESPECIAL, IS_FORNECEDOR_NAO_NEGOCIAVEL"
        if not sort_col:
            order = "ORDER BY DATA_LANCAMENTO DESC"
    elif source == 'ordens':
        cols = """NUMERO_OC, numero_acordo AS NUMERO_ACORDO, tipo AS TIPO,
                  nome_fornecedor AS FORNECEDOR, descricao AS DESCRICAO,
                  item_aquisicao AS ITEM_AQUISICAO, descricao_item AS DESCRICAO_ITEM,
                  categoria_item AS CATEGORIA_ITEM, nome_usuario AS NOME_USUARIO,
                  comprador_funcional AS COMPRADOR, aprovador AS APROVADOR,
                  org_desc AS EMPRESA, unidade AS UNIDADE, area AS AREA,
                  VALOR_ORIGINAL, VALOR_UTILIZADO, qtd_faturada AS QTD_FATURADA,
                  moeda AS MOEDA, STATUS_FECHAMENTO, DATA_OC,
                  dt_aprovacao AS DT_APROVACAO, dt_promessa AS DT_PROMESSA,
                  CENTRALIZADO, GRUPO_COMPRAS_OC, categoria_oc AS CATEGORIA_OC,
                  requisicao AS REQUISICAO, oc_atrasada AS OC_ATRASADA,
                  dias_atraso_oc AS DIAS_ATRASO_OC, dias_aberto AS DIAS_ABERTO,
                  fornecedor_especial AS FORNECEDOR_ESPECIAL,
                   is_fornecedor_especial AS IS_FORNECEDOR_ESPECIAL,
                   is_fornecedor_nao_negociavel AS IS_FORNECEDOR_NAO_NEGOCIAVEL"""
        if not sort_col:
            order = "ORDER BY DATA_OC DESC"
    else:
        cols = "REQUISICAO, EMPRESA, REQUISITANTE, DESCRICAO_REQ, NUMERO_OC, DT_CRIACAO, DT_APROVACAO, VALOR_REQUISICAO, STATUS, STATUS_ORDEM"
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
# STARTUP
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8000'))
    _log.info("Starting COMPRAS 360° on port %d", port)
    from waitress import serve
    serve(app, host='0.0.0.0', port=port)
