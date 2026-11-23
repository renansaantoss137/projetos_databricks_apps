"""PORTAL COMPRAS — Procurement Intelligence
Flask backend using Lakebase PostgreSQL (direct connection).
"""
import base64
import csv
import io
import logging
import os
import re
import time
import json
import uuid
import threading
import urllib.parse
import concurrent.futures
from datetime import date, timedelta, datetime
from decimal import Decimal
from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context, g
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
try:
    from flask_compress import Compress
except ImportError:
    Compress = None
try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
except ImportError:
    psycopg2 = None
try:
    from openpyxl import Workbook
    from openpyxl.worksheet.table import Table, TableStyleInfo
    from openpyxl.utils import get_column_letter
except ImportError:
    Workbook = None
    Table = None
    TableStyleInfo = None
    get_column_letter = None
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
_PG_SCHEMA = os.getenv("PG_SCHEMA", "compras")

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


class _PooledConnection:
    """Wraps a psycopg2 pooled connection so close() returns to pool."""
    def __init__(self, conn, pool_ref):
        object.__setattr__(self, '_conn', conn)
        object.__setattr__(self, '_pool_ref', pool_ref)
    def close(self):
        pool_ref = object.__getattribute__(self, '_pool_ref')
        conn = object.__getattribute__(self, '_conn')
        if pool_ref and conn:
            try:
                if not conn.closed:
                    # Encerra a transação implícita aberta pelo SELECT (autocommit=False):
                    # evita conexão 'idle in transaction' (segura locks e bloqueia o swap do ETL)
                    # e conexão em estado abortado voltando ao pool (próximas consultas falhariam e viriam vazias).
                    conn.rollback()
                pool_ref.putconn(conn, close=bool(conn.closed))
            except Exception:
                # Rollback falhou (conexão quebrada): descarta a conexão e libera a vaga no pool
                try:
                    pool_ref.putconn(conn, close=True)
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
            object.__setattr__(self, '_conn', None)
    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_conn'), name)
    def __setattr__(self, name, value):
        if name in ('_conn', '_pool_ref'):
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, '_conn'), name, value)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


_pool = None
_pool_lock = threading.Lock()


def _create_pool():
    """Create or recreate the threaded connection pool with fresh token."""
    global _pool
    token = _refresh_token()
    old_pool = _pool
    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=8,
        maxconn=40,
        host=_PG_HOST,
        database=_PG_DATABASE,
        user=_PG_USER,
        password=token,
        port=_PG_PORT,
        sslmode="require",
        options=f"-c search_path={_PG_SCHEMA}"
    )
    if old_pool:
        try:
            old_pool.closeall()
        except Exception:
            pass
    _log.info("Connection pool created (min=8, max=40)")


def _get_conn():
    """Get a wrapped pooled connection. close() returns it to the pool."""
    global _pool
    with _pool_lock:
        if _pool is None:
            _create_pool()
    try:
        raw = _pool.getconn()
        return _PooledConnection(raw, _pool)
    except Exception as e:
        if 'exhausted' in str(e).lower():
            raise
        with _pool_lock:
            _create_pool()
        raw = _pool.getconn()
        return _PooledConnection(raw, _pool)


# Resolve PGUSER dynamically if not set (injected by platform when postgres resource is configured)
if not _PG_USER:
    try:
        me = _w.current_user.me()
        _PG_USER = me.user_name
        _log.info("Resolved PGUSER dynamically: %s", _PG_USER)
    except Exception as e:
        _log.warning("Could not resolve PGUSER: %s", e)

_log.info("Lakebase config: host=%s schema=%s user=%s", _PG_HOST, _PG_SCHEMA, _PG_USER)

def _init_colaboradores_table():
    """Ensure colaboradores table exists in Lakebase PostgreSQL."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS colaboradores (
            matricula TEXT PRIMARY KEY,
            id_colaborador TEXT,
            nome_completo TEXT,
            email TEXT,
            area TEXT,
            diretoria TEXT,
            nm_unidade TEXT,
            nm_cargo TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_colab_matricula ON colaboradores (matricula);
        CREATE INDEX IF NOT EXISTS idx_colab_id ON colaboradores (id_colaborador);
        CREATE INDEX IF NOT EXISTS idx_colab_email ON colaboradores (email);
        CREATE INDEX IF NOT EXISTS idx_colab_nome ON colaboradores (nome_completo);
        CREATE INDEX IF NOT EXISTS idx_colab_upper_nome ON colaboradores (UPPER(nome_completo));
        """)
        conn.commit()
        cur.close()
        conn.close()
        _log.info("colaboradores table ensured in Lakebase")
    except Exception as e:
        _log.warning("Could not ensure colaboradores table: %s", e)

def _sync_colaboradores_if_empty():
    """Sync colaboradores from Unity Catalog if table is empty."""
    def _do_sync():
        try:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM colaboradores")
            c = cur.fetchone()[0]
            if c > 0:
                cur.close()
                conn.close()
                return
            _log.info("Colaboradores table empty. Fetching from Unity Catalog...")
            wh_id = "f4a2e26b8410f1e3"
            stmt = _w.statement_execution.execute_statement(
                warehouse_id=wh_id,
                statement="""
                SELECT 
                    TRIM(CAST(matricula AS STRING)) AS matricula,
                    TRIM(CAST(id_colaborador AS STRING)) AS id_colaborador,
                    TRIM(nome_completo) AS nome_completo,
                    TRIM(email) AS email,
                    TRIM(area) AS area,
                    TRIM(diretoria) AS diretoria,
                    TRIM(nm_unidade) AS nm_unidade,
                    TRIM(nm_cargo) AS nm_cargo
                FROM cat_dnabb_dv.cmpbragp360_sz.vw_dim_colaborador_atual
                WHERE matricula IS NOT NULL
                """,
                wait_timeout="50s"
            )
            if stmt.status.state.value == "SUCCEEDED" and stmt.result and stmt.result.data_array:
                rows = stmt.result.data_array
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO colaboradores (matricula, id_colaborador, nome_completo, email, area, diretoria, nm_unidade, nm_cargo)
                    VALUES %s
                    ON CONFLICT (matricula) DO NOTHING
                    """,
                    rows
                )
                conn.commit()
                _log.info("Successfully synced %d colaboradores to Lakebase", len(rows))
            cur.close()
            conn.close()
        except Exception as e:
            _log.warning("Colaboradores background sync failed: %s", e)

    t = threading.Thread(target=_do_sync, daemon=True)
    t.start()

def _init_acordos_compra_table():
    """Ensure acordos_compra table and its indexes exist in Lakebase PostgreSQL."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS acordos_compra (
            numero_acordo TEXT,
            status TEXT,
            dt_criacao TEXT,
            dt_inicio TEXT,
            dt_fim TEXT,
            valor_total DOUBLE PRECISION,
            valor_liberado DOUBLE PRECISION,
            descricao TEXT,
            fornecedor TEXT,
            numero_fornecedor TEXT,
            comprador TEXT,
            usuario_comprador TEXT,
            departamento_comprador TEXT,
            empresa TEXT,
            dias_aberto DOUBLE PRECISION
        );
        CREATE INDEX IF NOT EXISTS idx_acordos_status ON acordos_compra (status, dt_criacao);
        CREATE INDEX IF NOT EXISTS idx_acordos_num ON acordos_compra (numero_acordo);
        CREATE INDEX IF NOT EXISTS idx_acordos_empresa ON acordos_compra (empresa);
        """)
        conn.commit()
        cur.close()
        conn.close()
        _log.info("acordos_compra table ensured in Lakebase")
    except Exception as e:
        _log.warning("Could not ensure acordos_compra table: %s", e)

def _sync_acordos_compra_if_empty():
    """Sync acordos_compra from Unity Catalog if table is empty."""
    def _do_sync():
        try:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM acordos_compra")
            c = cur.fetchone()[0]
            if c > 0:
                cur.close()
                conn.close()
                return
            _log.info("Acordos_compra table empty. Fetching from Unity Catalog...")
            wh_id = "f4a2e26b8410f1e3"
            stmt = _w.statement_execution.execute_statement(
                warehouse_id=wh_id,
                statement="""
                SELECT 
                    numero_acordo,
                    status,
                    dt_criacao,
                    dt_inicio,
                    dt_fim,
                    valor_total,
                    valor_liberado,
                    descricao,
                    fornecedor,
                    numero_fornecedor,
                    comprador,
                    usuario_comprador,
                    departamento_comprador,
                    empresa,
                    dias_aberto
                FROM cat_dnabb_dv.grobbcompr_cz.vw_acordos_bpa
                """,
                wait_timeout="50s"
            )
            if stmt.status.state.value == "SUCCEEDED" and stmt.result and stmt.result.data_array:
                all_rows = list(stmt.result.data_array)
                current_stmt = stmt
                while current_stmt.result and current_stmt.result.next_chunk_index:
                    chunk_idx = current_stmt.result.next_chunk_index
                    chunk = _w.statement_execution.get_statement_result_chunk_n(
                        statement_id=stmt.statement_id,
                        chunk_index=chunk_idx
                    )
                    if chunk and chunk.data_array:
                        all_rows.extend(chunk.data_array)
                    current_stmt = chunk
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO acordos_compra (
                        numero_acordo, status, dt_criacao, dt_inicio, dt_fim,
                        valor_total, valor_liberado, descricao, fornecedor, numero_fornecedor,
                        comprador, usuario_comprador, departamento_comprador, empresa, dias_aberto
                    )
                    VALUES %s
                    """,
                    all_rows
                )
                conn.commit()
                _log.info("Successfully synced %d acordos_compra to Lakebase", len(all_rows))
            cur.close()
            conn.close()
        except Exception as e:
            _log.warning("Acordos_compra background sync failed: %s", e)

    t = threading.Thread(target=_do_sync, daemon=True)
    t.start()

def _init_fornecedores_sem_oc_table():
    """Ensure fornecedores_sem_oc table exists and is populated from local CSV if empty."""
    def _do_init():
        try:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{_PG_SCHEMA}"."fornecedores_sem_oc" (
                cod_fornecedor_oracle TEXT PRIMARY KEY,
                nome_fornecedor_oracle TEXT,
                produto_servico TEXT,
                area TEXT,
                justificativa TEXT,
                data_registro TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_fsemoc_cod ON "{_PG_SCHEMA}"."fornecedores_sem_oc" (cod_fornecedor_oracle);
            """)
            try:
                cur.execute(f'ALTER TABLE "{_PG_SCHEMA}"."notas_ri" ADD COLUMN IF NOT EXISTS is_fornecedor_sem_oc TEXT;')
                cur.execute(f'ALTER TABLE "{_PG_SCHEMA}"."ordens_compra" ADD COLUMN IF NOT EXISTS is_fornecedor_sem_oc TEXT;')
            except Exception as e_col:
                _log.warning("Could not add column is_fornecedor_sem_oc to tables: %s", e_col)
            conn.commit()

            cur.execute(f'SELECT COUNT(*) FROM "{_PG_SCHEMA}"."fornecedores_sem_oc"')
            cnt = cur.fetchone()[0]
            if cnt == 0:
                csv_candidates = [
                    os.path.join(os.path.dirname(__file__), 'fornecedores_sem_oc.csv'),
                    os.path.join(os.path.dirname(__file__), '..', 'dados', 'fornecedores_sem_oc.csv'),
                    'src/dados/fornecedores_sem_oc.csv'
                ]
                csv_path = next((p for p in csv_candidates if os.path.exists(p)), None)
                if csv_path:
                    import csv
                    rows = []
                    with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                        reader = csv.reader(f, delimiter=';')
                        next(reader, None)
                        for r in reader:
                            if r and len(r) >= 2 and r[0].strip():
                                rows.append((
                                    r[0].strip(),
                                    r[1].strip(),
                                    r[2].strip() if len(r) > 2 else '',
                                    r[3].strip() if len(r) > 3 else '',
                                    r[4].strip() if len(r) > 4 else '',
                                    r[5].strip() if len(r) > 5 else ''
                                ))
                    if rows:
                        psycopg2.extras.execute_values(
                            cur,
                            f"""
                            INSERT INTO "{_PG_SCHEMA}"."fornecedores_sem_oc" 
                            (cod_fornecedor_oracle, nome_fornecedor_oracle, produto_servico, area, justificativa, data_registro)
                            VALUES %s
                            ON CONFLICT (cod_fornecedor_oracle) DO NOTHING
                            """,
                            rows
                        )
                        conn.commit()
                        _log.info("Populated %d rows into fornecedores_sem_oc in Lakebase", len(rows))
            cur.close()
            conn.close()
        except Exception as e:
            _log.warning("Could not initialize fornecedores_sem_oc in Lakebase: %s", e)

    t = threading.Thread(target=_do_init, daemon=True)
    t.start()

def _ensure_performance_indexes():
    """Ensure key performance indexes exist on ordens_compra and notas_ri."""
    def _run():
        time.sleep(3)
        try:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_oc_data_oc ON ordens_compra (data_oc);
            CREATE INDEX IF NOT EXISTS idx_oc_data_oc_yr ON ordens_compra (SUBSTRING(data_oc, 1, 4));
            CREATE INDEX IF NOT EXISTS idx_oc_org_data ON ordens_compra (org_desc, data_oc);
            CREATE INDEX IF NOT EXISTS idx_oc_forn_num ON ordens_compra (numero_fornecedor);
            CREATE INDEX IF NOT EXISTS idx_nr_data_pgto_yr ON notas_ri (SUBSTRING(data_pagamento, 1, 4));
            CREATE INDEX IF NOT EXISTS idx_nr_empresa_dt_pgto ON notas_ri (empresa, data_pagamento);
            CREATE INDEX IF NOT EXISTS idx_nr_data_lanc_yr ON notas_ri (SUBSTRING(data_lancamento, 1, 4));
            CREATE INDEX IF NOT EXISTS idx_nr_data_lanc ON notas_ri (data_lancamento);
            CREATE INDEX IF NOT EXISTS idx_nr_empresa_dt_lanc ON notas_ri (empresa, data_lancamento);
            CREATE INDEX IF NOT EXISTS idx_nr_chave_oc ON notas_ri (chave_oc_linha);
            CREATE INDEX IF NOT EXISTS idx_oc_chave_oc ON ordens_compra (chave_oc_linha);
            CREATE INDEX IF NOT EXISTS idx_nr_numero_oc ON notas_ri (numero_oc);
            CREATE INDEX IF NOT EXISTS idx_oc_numero_oc ON ordens_compra (numero_oc);
            CREATE INDEX IF NOT EXISTS idx_nr_cond_pgto ON notas_ri (cond_pgto_ap);
            CREATE INDEX IF NOT EXISTS idx_nr_fornecedor ON notas_ri (nome_fornecedor);
            CREATE INDEX IF NOT EXISTS idx_nr_grupo ON notas_ri (grupo_compras);
            CREATE INDEX IF NOT EXISTS idx_nr_faixa_prazo ON notas_ri (faixa_prazo_pagamento);
            """)
            conn.commit()
            cur.close()
            conn.close()
            _log.info("Performance indexes verified/ensured in Lakebase")
        except Exception as e:
            _log.warning("Could not ensure performance indexes: %s", e)
    t = threading.Thread(target=_run, daemon=True)
    t.start()

try:
    _init_colaboradores_table()
    _sync_colaboradores_if_empty()
    _init_acordos_compra_table()
    _sync_acordos_compra_if_empty()
    _init_fornecedores_sem_oc_table()
    _ensure_performance_indexes()
except Exception:
    pass

# static_folder=None: sem a rota automática /static/<arquivo> (exporia app.py, app.yaml, cadastros_access.json).
# Arquivos estáticos são servidos apenas pela rota static_files, com lista de extensões permitidas.
app = Flask(__name__, static_folder=None)
app.json_provider_class = CustomJSONProvider
app.json = CustomJSONProvider(app)
CORS(app)
if Compress:
    Compress(app)
    _log.info("GZIP compression enabled via Flask-Compress")

def _prewarm_cache():
    """Background cache pre-warming for default dashboard views."""
    def _run():
        time.sleep(5)
        _log.info("Starting background cache pre-warm...")
        try:
            with app.test_client() as client:
                client.get('/api/filters/notas')
                client.get('/api/filters/comercial')
                client.get('/api/filters/cascading-ordens')
                
                now = datetime.now()
                cy = str(now.year)
                cm = str(now.month)
                
                for p in [f"?empresa=BB&empresa=BQ&ano={cy}", f"?empresa=BB&empresa=BQ&ano={cy}&mes={cm}"]:
                    client.get(f'/api/performance/kpis{p}')
                    client.get(f'/api/commercial/kpis{p}')
                    client.get(f'/api/commercial/payment-evolution{p}')
                    client.get(f'/api/commercial/payment-distribution{p}')
                    client.get(f'/api/commercial/suppliers-below-60{p}')
                    client.get(f'/api/governance/kpis{p}')
                    client.get(f'/api/governance/deviation-impact{p}')
            _log.info("Background cache pre-warm completed successfully!")
        except Exception as e:
            _log.warning("Cache pre-warm notice: %s", e)
    t = threading.Thread(target=_run, daemon=True)
    t.start()

try:
    _prewarm_cache()
except Exception:
    pass

# ── In-Memory TTL Query Cache ─────────────────────────────────────────────────
_query_cache = {}
_CACHE_TTL = 1800  # 30 minutes
_CACHE_LOCK = threading.Lock()
# /api/auth/ é por usuário (e-mail/permissão) e /api/lookups/ é editado na tela de Cadastros: nunca cachear.
_CACHE_SKIP_PREFIXES = ('/api/admin/', '/api/auth/', '/api/lookups/', '/api/cadastros/')
# Contador global de falhas de consulta: se alguma consulta falhar durante a requisição,
# a resposta (provavelmente com zeros/listas vazias) não é guardada no cache.
_query_fail_seq = 0


def _mark_query_failure():
    global _query_fail_seq
    _query_fail_seq += 1


def _clear_query_cache(reason=''):
    with _CACHE_LOCK:
        count = len(_query_cache)
        _query_cache.clear()
    _log.info("Cache cleared (%s): %d entries purged", reason, count)
    return count
_CACHE_SKIP_EXACT = ('/api/health',)


def _cache_key():
    if request.args:
        items = []
        for k in sorted(request.args.keys()):
            for v in sorted(request.args.getlist(k)):
                items.append((k, v))
        return f"{request.path}?{urllib.parse.urlencode(items)}"
    return request.path


def _cache_get(key):
    with _CACHE_LOCK:
        entry = _query_cache.get(key)
        if entry and (time.time() - entry['ts']) < _CACHE_TTL:
            return entry['data']
        elif entry:
            del _query_cache[key]
    return None


def _cache_set(key, data):
    with _CACHE_LOCK:
        if len(_query_cache) > 500:
            now = time.time()
            expired = [k for k, v in _query_cache.items() if (now - v['ts']) >= _CACHE_TTL]
            for k in expired:
                del _query_cache[k]
        _query_cache[key] = {'data': data, 'ts': time.time()}


def _is_cacheable_path(path):
    if not path.startswith('/api/'):
        return False
    if path in _CACHE_SKIP_EXACT:
        return False
    for pfx in _CACHE_SKIP_PREFIXES:
        if path.startswith(pfx):
            return False
    if '/export' in path:
        return False
    return True


@app.before_request
def _check_cache():
    g._fail_seq_start = _query_fail_seq
    if request.method != 'GET':
        return None
    if not _is_cacheable_path(request.path):
        return None
    cached = _cache_get(_cache_key())
    if cached is not None:
        resp = app.make_response(cached)
        resp.headers['Content-Type'] = 'application/json'
        resp.headers['X-Cache'] = 'HIT'
        resp.headers['Cache-Control'] = 'public, max-age=300'
        return resp


@app.after_request
def _set_cache_and_headers(response):
    if request.method == 'GET' and _is_cacheable_path(request.path):
        if response.status_code == 200 and response.content_type and 'json' in response.content_type:
            body = response.get_data()
            # Do not cache empty/error responses ([] = 2 bytes, {} = 2 bytes)
            if _query_fail_seq != getattr(g, '_fail_seq_start', _query_fail_seq):
                response.headers['X-Cache'] = 'SKIP-QUERY-ERROR'
            elif len(body) > 10:
                _cache_set(_cache_key(), body)
                response.headers['X-Cache'] = 'MISS'
            else:
                response.headers['X-Cache'] = 'SKIP'
        if response.headers.get('X-Cache') == 'SKIP-QUERY-ERROR':
            response.headers['Cache-Control'] = 'no-store'
        elif response.status_code == 200:
            response.headers['Cache-Control'] = 'public, max-age=300'
    return response


@app.route('/api/admin/clear-cache', methods=['GET', 'POST'])
def admin_clear_cache():
    """Purge the in-memory query cache (somente administradores de Cadastros)."""
    email = _get_current_user_email()
    admins = [a.lower() for a in _load_cadastros_access().get("admins", [])]
    if email not in admins:
        return jsonify({"status": "forbidden"}), 403
    count = _clear_query_cache(f'admin {email}')
    return jsonify({"status": "ok", "entries_purged": count})


# ── Fallback seguro para a tabela colaboradores ──────────────────────────────
# Se a tabela ainda não existir no Lakebase (ex.: ETL ainda não rodou com a nova
# versão, ou o swap blue-green recriou o schema), as consultas NÃO podem quebrar.
# Nesse caso, substituímos "FROM colaboradores" por uma tabela vazia equivalente,
# e a cascata de departamento cai para compradores_funcionais / Oracle.
_colab_state = {"ok": None, "ts": 0.0}
_COLAB_EMPTY = (
    "FROM (SELECT NULL::text AS matricula, NULL::text AS id_colaborador, "
    "NULL::text AS nome_completo, NULL::text AS email, NULL::text AS area, "
    "NULL::text AS diretoria, NULL::text AS nm_unidade, NULL::text AS nm_cargo "
    "WHERE false) colaboradores"
)


def _colab_available():
    """Checa (com cache de 5 min) se a tabela colaboradores existe e tem dados."""
    now = time.time()
    if _colab_state["ok"] is not None and (now - _colab_state["ts"]) < 300:
        return _colab_state["ok"]
    ok = False
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('colaboradores') IS NOT NULL")
        ok = bool(cur.fetchone()[0])
        cur.close()
        conn.close()
    except Exception as e:
        _log.warning("colaboradores availability check failed: %s", e)
        ok = False
    if not ok and _colab_state["ok"] is not False:
        _log.warning("Tabela colaboradores indisponível no Lakebase — usando fallback (compradores_funcionais/Oracle).")
    _colab_state["ok"], _colab_state["ts"] = ok, now
    return ok


def _patch_sql(sql_text):
    if "colaboradores" in sql_text and not _colab_available():
        return sql_text.replace("FROM colaboradores", _COLAB_EMPTY)
    return sql_text


def query(sql_text, params=None):
    """Execute SQL on Lakebase PostgreSQL and return list of dicts."""
    global _pg_token
    sql_text = _patch_sql(sql_text)
    for attempt in range(2):
        conn = None
        try:
            conn = _get_conn()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql_text)
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            return rows
        except Exception as e:
            err_msg = str(e).lower()
            if attempt == 0 and ("authorization failed" in err_msg or "authentication failed" in err_msg or "password" in err_msg):
                _log.warning("Auth failure detected, recreating pool: %s", str(e)[:150])
                with _token_lock:
                    _pg_token = None
                with _pool_lock:
                    _create_pool()
                continue
            _mark_query_failure()
            _log.error("Query exception: %s | Query: %s", str(e)[:300], sql_text[:200])
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


def query_debug(sql_text):
    """Like query() but returns (rows, error_str). Never raises."""
    global _pg_token
    sql_text = _patch_sql(sql_text)
    for attempt in range(2):
        conn = None
        try:
            conn = _get_conn()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql_text)
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            return rows, None
        except Exception as e:
            err_msg = str(e).lower()
            if attempt == 0 and ("authorization failed" in err_msg or "authentication failed" in err_msg or "password" in err_msg):
                _log.warning("Auth failure in query_debug, recreating pool: %s", str(e)[:150])
                with _token_lock:
                    _pg_token = None
                with _pool_lock:
                    _create_pool()
                continue
            _mark_query_failure()
            _log.error("Query exception: %s | SQL: %s", str(e)[:300], sql_text[:200])
            return [], str(e)[:300]
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


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


# ── Excel-style DATE header filters (Relatórios) ──
_HF_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_HF_PERIODS = {
    'Q1': ['01', '02', '03'], 'Q2': ['04', '05', '06'],
    'Q3': ['07', '08', '09'], 'Q4': ['10', '11', '12'],
}


def _date_hf_clause(col_expr, op, val):
    """Build SQL clause for date header filters.
    Date columns are TEXT starting with YYYY-MM-DD (some with time).
    ops: date_eq, date_before, date_after, date_between ('a|b'),
         date_period ('Q1'..'Q4' or 'M01'..'M12'),
         date_tree (tokens 'Y:2026', 'M:2026-09', 'D:2026-09-28', 'EMPTY').
    """
    d = f"SUBSTRING(NULLIF(TRIM(({col_expr})::text), ''), 1, 10)"
    val = (val or '').strip()

    def _ok(x):
        return bool(_HF_DATE_RE.match(x or ''))

    if op == 'date_eq' and _ok(val):
        return f"({d} = '{val}')"
    if op == 'date_before' and _ok(val):
        return f"({d} < '{val}')"
    if op == 'date_after' and _ok(val):
        return f"({d} > '{val}')"
    if op == 'date_between':
        a, _, b = val.partition('|')
        parts = []
        if _ok(a.strip()):
            parts.append(f"{d} >= '{a.strip()}'")
        if _ok(b.strip()):
            parts.append(f"{d} <= '{b.strip()}'")
        return f"({' AND '.join(parts)})" if parts else None
    if op == 'date_period':
        if val in _HF_PERIODS:
            months = _HF_PERIODS[val]
        elif re.match(r'^M(0[1-9]|1[0-2])$', val):
            months = [val[1:]]
        else:
            return None
        mv = ','.join(f"'{m}'" for m in months)
        return f"(SUBSTRING({d}, 6, 2) IN ({mv}))"
    if op == 'date_tree':
        yrs, mos, dys, empty = [], [], [], False
        for tok in val.split(','):
            tok = tok.strip()
            if tok == 'EMPTY':
                empty = True
            elif re.match(r'^Y:\d{4}$', tok):
                yrs.append(tok[2:])
            elif re.match(r'^M:\d{4}-\d{2}$', tok):
                mos.append(tok[2:])
            elif tok.startswith('D:') and _ok(tok[2:]):
                dys.append(tok[2:])
        parts = []
        if yrs:
            parts.append(f"SUBSTRING({d}, 1, 4) IN ({','.join(repr(y) for y in yrs)})")
        if mos:
            parts.append(f"SUBSTRING({d}, 1, 7) IN ({','.join(repr(m) for m in mos)})")
        if dys:
            parts.append(f"{d} IN ({','.join(repr(x) for x in dys)})")
        if empty:
            parts.append(f"{d} IS NULL")
        return f"({' OR '.join(parts)})" if parts else "(1=0)"
    return None


_sem_oc_table_state = {"ok": None, "ts": 0.0}

def _sem_oc_table_available():
    """Checa (com cache de 5 min) se a tabela fornecedores_sem_oc existe no Lakebase."""
    now = time.time()
    if _sem_oc_table_state["ok"] is not None and (now - _sem_oc_table_state["ts"]) < 300:
        return _sem_oc_table_state["ok"]
    ok = False
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(f"SELECT to_regclass('\"{_PG_SCHEMA}\".\"fornecedores_sem_oc\"') IS NOT NULL")
        row = cur.fetchone()
        ok = bool(row and row[0])
        cur.close()
        conn.close()
    except Exception as e:
        _log.warning("fornecedores_sem_oc availability check failed: %s", e)
        ok = False
    _sem_oc_table_state["ok"], _sem_oc_table_state["ts"] = ok, now
    return ok


def _clause_forn_sem_oc(col_prefix, is_forn_sem_oc, num_forn_col="numero_fornecedor"):
    """
    Constrói a cláusula SQL segura para o filtro 'is_fornecedor_sem_oc'.
    - Se ambos 'COM ATUAÇÃO' e 'SEM OC' estiverem selecionados (ou nenhum): não filtra nada.
    - Se 'SEM OC' estiver selecionado: filtra os fornecedores da lista sem OC.
    - Se 'COM ATUAÇÃO' estiver selecionado: EXCLUI quem está na lista sem OC.
    - Se a tabela fornecedores_sem_oc ainda não estiver no Lakebase: retorna None para não quebrar as telas.
    """
    if not is_forn_sem_oc:
        return None
    has_com = any('ATUA' in str(v).upper() for v in is_forn_sem_oc)
    has_sem = any('SEM' in str(v).upper() for v in is_forn_sem_oc)
    if (has_com and has_sem) or (not has_com and not has_sem):
        return None
    if not _sem_oc_table_available():
        return None
    p = col_prefix or ""
    nf_col = f"{p}{num_forn_col}"
    if has_sem:
        return f"({nf_col} IN (SELECT cod_fornecedor_oracle FROM \"{_PG_SCHEMA}\".\"fornecedores_sem_oc\"))"
    elif has_com:
        return f"({nf_col} NOT IN (SELECT cod_fornecedor_oracle FROM \"{_PG_SCHEMA}\".\"fornecedores_sem_oc\"))"
    return None


def _sem_oc_flag_sql(nf_alias="nf", oc_alias="oc"):
    """Expressão SQL do rótulo 'Forn. sem OC / Atuação' calculada na hora a partir de fornecedores_sem_oc.
    Não usa a coluna is_fornecedor_sem_oc: o ETL diário recria notas_ri/ordens_compra (troca de schema)
    sem essa coluna, e o SELECT que a citava falhava em silêncio (Relatórios mostrava o total, mas 0 linhas).
    Mesma regra do filtro (_clause_forn_sem_oc) e do recálculo em _recalc_lakebase_flags."""
    if not _sem_oc_table_available():
        return "NULL::text"
    forn = f"COALESCE({nf_alias}.NUMERO_FORNECEDOR, {oc_alias}.numero_fornecedor)"
    return (f"CASE WHEN {forn} IN (SELECT cod_fornecedor_oracle FROM \"{_PG_SCHEMA}\".\"fornecedores_sem_oc\") "
            f"THEN 'SEM OC' ELSE 'COM ATUAÇÃO' END")


def _parse_filters(args, date_col="DATA_LANCAMENTO", table_prefix="", empresa_col="EMPRESA", grupo_col="GRUPO_COMPRAS", fornecedor_col="NOME_FORNECEDOR", unidade_col="PLANTA", is_notas=None):
    """Parse common filter parameters. Returns (clauses[], params=[]).
    All values are inlined directly in SQL (Statement Execution API has no params)."""
    clauses = []
    p = f"{table_prefix}." if table_prefix else ""

    # Regra de negócio: excluir faturas não comerciais (despesas/reembolso RGB/ADV, folha FOPAG, trade marketing ARKER, tributos/guias FISCAL)
    if is_notas is None:
        is_notas = (date_col in ("DATA_LANCAMENTO", "DATA_PAGAMENTO") and empresa_col == "EMPRESA" and unidade_col == "PLANTA")
    if is_notas:
        clauses.append(f"UPPER(COALESCE({p}NOTA_FISCAL, '')) NOT LIKE '%RGB%'")
        clauses.append(f"UPPER(COALESCE({p}NOTA_FISCAL, '')) NOT LIKE 'ADV%'")
        clauses.append(f"UPPER(COALESCE({p}NOTA_FISCAL, '')) NOT LIKE '%FOPAG%'")
        clauses.append(f"UPPER(COALESCE({p}NOTA_FISCAL, '')) NOT LIKE '%ARKER%'")
        clauses.append(f"UPPER(COALESCE({p}NOTA_FISCAL, '')) NOT LIKE '%FISCAL%'")

    # Date filters (only applied if date_col is specified)
    if date_col:
        ano = [a.strip() for a in args.getlist('ano') if a.strip()]
        mes = [m.strip() for m in args.getlist('mes') if m.strip()]
        dia = [d.strip() for d in args.getlist('dia') if d.strip()]
        dt_ini = args.get('dt_ini', '').strip()
        dt_fim = args.get('dt_fim', '').strip()

        if date_col == "DATA_PAGAMENTO" and (ano or mes or dia or dt_ini or dt_fim):
            clauses.append(f"{p}{date_col} IS NOT NULL AND {p}{date_col} != ''")

        if ano:
            vals = ','.join([f"'{_esc(a)}'" for a in ano])
            clauses.append(f"SUBSTRING({p}{date_col}, 1, 4) IN ({vals})")
        if mes:
            vals = ','.join([m for m in mes])
            clauses.append(f"CASE WHEN LENGTH(COALESCE({p}{date_col}, '')) >= 7 THEN CAST(SUBSTRING({p}{date_col}, 6, 2) AS INT) ELSE NULL END IN ({vals})")
        if dia:
            vals = ','.join([d for d in dia])
            clauses.append(f"CASE WHEN LENGTH(COALESCE({p}{date_col}, '')) >= 10 THEN CAST(SUBSTRING({p}{date_col}, 9, 2) AS INT) ELSE NULL END IN ({vals})")
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
        clauses.append(f"{p}{fornecedor_col} IN ({vals})")

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
    def _text_clause(col_expr, vals, op='contains'):
        if not vals:
            return None
        valid_vals = [v for v in vals if v]
        if not valid_vals:
            return None
        expr = f"({col_expr})::text"
        if op == 'equals':
            parts = [f"(TRIM({expr}) ILIKE '{_esc(v)}')" for v in valid_vals]
        elif op == 'startswith':
            parts = [f"({expr} ILIKE '{_esc(v)}%')" for v in valid_vals]
        elif op == 'endswith':
            parts = [f"({expr} ILIKE '%{_esc(v)}')" for v in valid_vals]
        else: # contains
            parts = [f"({expr} ILIKE '%{_esc(v)}%')" for v in valid_vals]
        return f"({' OR '.join(parts)})"

    numero_ri = [v.strip() for v in args.getlist('numero_ri') if v.strip()]
    if numero_ri:
        c = _text_clause(f"{p}NUMERO_RI", numero_ri, args.get('numero_ri_op', 'contains'))
        if c: clauses.append(c)
    nota_fiscal = [v.strip() for v in args.getlist('nota_fiscal') if v.strip()]
    if nota_fiscal:
        c = _text_clause(f"{p}NOTA_FISCAL", nota_fiscal, args.get('nota_fiscal_op', 'contains'))
        if c: clauses.append(c)
    numero_oc_f = [v.strip() for v in args.getlist('numero_oc') if v.strip()]
    if numero_oc_f:
        c = _text_clause(f"{p}NUMERO_OC", numero_oc_f, args.get('numero_oc_op', 'contains'))
        if c: clauses.append(c)
    ds_item = [v.strip() for v in args.getlist('ds_item') if v.strip()]
    if ds_item:
        c = _text_clause(f"{p}DS_ITEM", ds_item, args.get('ds_item_op', 'contains'))
        if c: clauses.append(c)
    cnpj_bimbo = [v.strip() for v in args.getlist('cnpj_bimbo') if v.strip()]
    if cnpj_bimbo:
        c = _text_clause(f"{p}CNPJ_BIMBO", cnpj_bimbo, args.get('cnpj_bimbo_op', 'contains'))
        if c: clauses.append(c)
    codigo_item = [v.strip() for v in args.getlist('codigo_item') if v.strip()]
    if codigo_item:
        c = _text_clause(f"{p}CODIGO_ITEM", codigo_item, args.get('codigo_item_op', 'contains'))
        if c: clauses.append(c)
    descricao_item = [v.strip() for v in args.getlist('descricao_item') if v.strip()]
    if descricao_item:
        c = _text_clause(f"{p}DESCRICAO_ITEM", descricao_item, args.get('descricao_item_op', 'contains'))
        if c: clauses.append(c)
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
    tipo_linha = [v.strip() for v in args.getlist('tipo_linha') if v.strip()]
    if tipo_linha:
        vals = ','.join([f"'{_esc(v)}'" for v in tipo_linha])
        clauses.append(f"{p}TIPO_LINHA IN ({vals})")
    is_forn_esp = [v.strip() for v in args.getlist('is_fornecedor_especial') if v.strip()]
    if is_forn_esp:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_esp])
        clauses.append(f"{p}IS_FORNECEDOR_ESPECIAL IN ({vals})")
    is_forn_nn = [v.strip() for v in args.getlist('is_fornecedor_nao_negociavel') if v.strip()]
    if is_forn_nn:
        vals = ','.join([f"'{_esc(v)}'" for v in is_forn_nn])
        clauses.append(f"{p}IS_FORNECEDOR_NAO_NEGOCIAVEL IN ({vals})")
    is_forn_sem_oc = [v.strip() for v in args.getlist('is_fornecedor_sem_oc') if v.strip()]
    c_sem_oc = _clause_forn_sem_oc(p, is_forn_sem_oc, num_forn_col="NUMERO_FORNECEDOR")
    if c_sem_oc:
        clauses.append(c_sem_oc)
    # Requisicoes-specific filters
    req_requisicao = [v.strip() for v in args.getlist('req_requisicao') if v.strip()]
    if req_requisicao:
        c = _text_clause(f"{p}REQUISICAO", req_requisicao, args.get('req_requisicao_op', 'contains'))
        if c: clauses.append(c)
    req_descricao = [v.strip() for v in args.getlist('req_descricao') if v.strip()]
    if req_descricao:
        c = _text_clause(f"{p}DESCRICAO_REQ", req_descricao, args.get('req_descricao_op', 'contains'))
        if c: clauses.append(c)
    req_numero_oc = [v.strip() for v in args.getlist('req_numero_oc') if v.strip()]
    if req_numero_oc:
        c = _text_clause(f"{p}NUMERO_OC", req_numero_oc, args.get('req_numero_oc_op', 'contains'))
        if c: clauses.append(c)
    req_status = [v.strip() for v in args.getlist('req_status') if v.strip()]
    if req_status:
        vals = ','.join([f"'{_esc(v)}'" for v in req_status])
        clauses.append(f"{p}STATUS IN ({vals})")
    req_status_ordem = [v.strip() for v in args.getlist('req_status_ordem') if v.strip()]
    if req_status_ordem:
        vals = ','.join([f"'{_esc(v)}'" for v in req_status_ordem])
        clauses.append(f"{p}STATUS_ORDEM IN ({vals})")
    req_comprador = [v.strip() for v in args.getlist('req_comprador_sugerido') if v.strip()]
    if req_comprador:
        vals = ','.join([f"'{_esc(v)}'" for v in req_comprador])
        clauses.append(f"NULLIF(TRIM({p}comprador_sugerido), '') IN ({vals})")
    # Ordens-specific advanced filters (routes to oc. when joined with nf)
    ord_numero_oc = [v.strip() for v in args.getlist('ord_numero_oc') if v.strip()]
    if ord_numero_oc:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_numero_oc])
        if p == 'nf.':
            clauses.append(f"(nf.NUMERO_OC IN ({vals}) OR oc.numero_oc IN ({vals}))")
        else:
            clauses.append(f"{p}NUMERO_OC IN ({vals})")
    ord_numero_acordo = [v.strip() for v in args.getlist('ord_numero_acordo') if v.strip()]
    if ord_numero_acordo:
        prefix_oc = 'oc.' if p == 'nf.' else p
        c = _text_clause(f"{prefix_oc}numero_acordo", ord_numero_acordo, args.get('ord_numero_acordo_op', 'contains'))
        if c: clauses.append(c)
    ord_item_aquisicao = [v.strip() for v in args.getlist('ord_item_aquisicao') if v.strip()]
    if ord_item_aquisicao:
        prefix_oc = 'oc.' if p == 'nf.' else p
        c = _text_clause(f"{prefix_oc}item_aquisicao", ord_item_aquisicao, args.get('ord_item_aquisicao_op', 'contains'))
        if c: clauses.append(c)

    # Header filters (Excel-style column filters: hf_COL=val & hf_COL_op=op)
    for k in args:
        if k.startswith('hf_') and not (k.endswith('_op') or k.endswith('_val')):
            col_key = k[3:]
            hf_val = args.get(k, '').strip()
            hf_op = args.get(f'{k}_op', 'contains').strip()
            if hf_val:
                upper_key = col_key.upper()
                if p == 'nf.':
                    oc_cols = {
                        'COMPRADOR': "COALESCE(NULLIF(oc.comprador, ''), oc.nome_usuario)",
                        'DEPARTAMENTO_COMPRADOR': "oc.area",
                        'STATUS_FECHAMENTO': "oc.status_fechamento",
                        'NUMERO_ACORDO': "oc.numero_acordo",
                        'ITEM_AQUISICAO': "oc.item_aquisicao",
                        'REQUISICAO': "oc.requisicao",
                        'NOME_REQUISITANTE': "oc.nome_requisitante",
                        'TIPO': "oc.tipo",
                        'DESCRICAO': "oc.descricao",
                        'FORNECEDOR': "COALESCE(nf.NOME_FORNECEDOR, oc.nome_fornecedor)",
                        'UNIDADE': "COALESCE(nf.PLANTA, oc.unidade)",
                        'DEPARTAMENTO_REQUISITANTE': "oc.area",
                        'DATA_OC': "oc.data_oc",
                        'DT_APROVACAO': "oc.dt_aprovacao",
                        'DT_PROMESSA': "oc.dt_promessa",
                        'DT_FECHAMENTO': "oc.dt_fechamento",
                        'ACORDO_DT_CRIACAO': "oc.acordo_dt_criacao",
                        'ACORDO_DATA_INICIAL': "oc.acordo_data_inicial",
                        'ACORDO_DATA_FINAL': "oc.acordo_data_final",
                    }
                    col_sql = oc_cols.get(upper_key, f"nf.{upper_key}")
                else:
                    col_sql = f"{p}{upper_key}"
                if hf_op.startswith('date_'):
                    c = _date_hf_clause(col_sql, hf_op, hf_val)
                else:
                    c = _text_clause(col_sql, [hf_val], hf_op)
                if c:
                    clauses.append(c)
    ord_comprador = [v.strip() for v in args.getlist('ord_comprador') if v.strip()]
    if ord_comprador:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_comprador])
        if p == 'nf.':
            clauses.append(f"COALESCE(NULLIF(oc.comprador, ''), oc.nome_usuario) IN ({vals})")
        else:
            clauses.append(f"{p}nome_usuario IN ({vals})")
    ord_status_fech = [v.strip() for v in args.getlist('ord_status_fechamento') if v.strip()]
    if ord_status_fech:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_status_fech])
        prefix_oc = 'oc.' if p == 'nf.' else p
        clauses.append(f"{prefix_oc}STATUS_FECHAMENTO IN ({vals})")
    ord_centralizado = [v.strip() for v in args.getlist('ord_centralizado') if v.strip()]
    if ord_centralizado:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_centralizado])
        clauses.append(f"{p}CENTRALIZADO IN ({vals})")
    ord_grupo_compras = [v.strip() for v in args.getlist('ord_grupo_compras') if v.strip()]
    if ord_grupo_compras:
        vals = ','.join([f"'{_esc(v)}'" for v in ord_grupo_compras])
        prefix_gc = 'oc.grupo_compras_oc' if p == 'nf.' else f"{p}GRUPO_COMPRAS_OC"
        clauses.append(f"{prefix_gc} IN ({vals})")
    comprador = [v.strip() for v in args.getlist('comprador') if v.strip()]
    if comprador:
        vals = ','.join([f"'{_esc(v)}'" for v in comprador])
        if p == 'nf.':
            clauses.append(f"COALESCE(NULLIF(oc.comprador, ''), oc.nome_usuario) IN ({vals})")
        else:
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
# Any purchase conducted by a buyer belonging to the Compras department (or functional
# purchasing team) is inherently CENTRALIZED and should NEVER appear as a
# "Descentralizada >30K" exception, regardless of value.
_EXCL_COMPRAS_OCS = """
    SELECT DISTINCT oc_x.numero_oc
    FROM ordens_compra oc_x
    WHERE oc_x.numero_oc IS NOT NULL AND oc_x.numero_oc != ''
      AND (
          UPPER(COALESCE(oc_x.nome_usuario, '')) LIKE '%ARKER%'
          OR UPPER(COALESCE(oc_x.usuario, '')) LIKE '%ARKER%'
          OR UPPER(COALESCE(oc_x.comprador, '')) LIKE '%ARKER%'
          OR UPPER(COALESCE(oc_x.usuario_comprador, '')) LIKE '%ARKER%'
          OR LOWER(oc_x.usuario) IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
          OR (oc_x.usuario IN (SELECT matricula FROM colaboradores WHERE UPPER(COALESCE(area, diretoria, '')) LIKE '%COMPRAS%'))
          OR (oc_x.usuario_comprador IS NOT NULL AND (
              LOWER(oc_x.usuario_comprador) IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
              OR oc_x.usuario_comprador IN (SELECT matricula FROM colaboradores WHERE UPPER(COALESCE(area, diretoria, '')) LIKE '%COMPRAS%')
          ))
          OR (oc_x.nome_usuario IS NOT NULL AND (
              UPPER(oc_x.nome_usuario) IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL)
              OR UPPER(oc_x.nome_usuario) IN (SELECT UPPER(nome_completo) FROM colaboradores WHERE UPPER(COALESCE(area, diretoria, '')) LIKE '%COMPRAS%')
          ))
          OR (oc_x.comprador IS NOT NULL AND (
              UPPER(oc_x.comprador) IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL)
              OR UPPER(oc_x.comprador) IN (SELECT UPPER(nome_completo) FROM colaboradores WHERE UPPER(COALESCE(area, diretoria, '')) LIKE '%COMPRAS%')
          ))
      )
      AND UPPER(COALESCE(oc_x.comprador, '')) NOT LIKE '%ABEL MOREIRA MARTINS FILHO%'
      AND UPPER(COALESCE(oc_x.nome_usuario, '')) NOT LIKE '%ABEL MOREIRA MARTINS FILHO%'
"""

# OCs with a purchase agreement (numero_acordo) are effectively centralized
# and should NOT appear as "OC Descentralizada >30K" exceptions — even if
# CENTRALIZADO is set to 'DESCENTRALIZADO' due to ETL inconsistency.
_EXCL_ACORDO_OCS = """
    SELECT DISTINCT numero_oc FROM ordens_compra
    WHERE numero_acordo IS NOT NULL AND TRIM(numero_acordo) != ''
      AND numero_oc IS NOT NULL
"""

# SQL clause to exclude Compras users from decentral OCs (checks both compradores_funcionais and colaboradores)
_EXCL_COMPRAS_DECENTRAL_OC = """
  AND UPPER(COALESCE(oc.nome_usuario, '')) NOT LIKE '%ARKER%'
  AND UPPER(COALESCE(oc.usuario, '')) NOT LIKE '%ARKER%'
  AND UPPER(COALESCE(oc.comprador, '')) NOT LIKE '%ARKER%'
  AND UPPER(COALESCE(oc.usuario_comprador, '')) NOT LIKE '%ARKER%'
  AND LOWER(oc.usuario) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
  AND (oc.usuario NOT IN (SELECT matricula FROM colaboradores WHERE UPPER(COALESCE(area, diretoria, '')) LIKE '%COMPRAS%'))
  AND (oc.usuario_comprador IS NULL OR (
      LOWER(oc.usuario_comprador) NOT IN (SELECT LOWER(usuario_oracle) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND usuario_oracle IS NOT NULL)
      AND oc.usuario_comprador NOT IN (SELECT matricula FROM colaboradores WHERE UPPER(COALESCE(area, diretoria, '')) LIKE '%COMPRAS%')
  ))
  AND (oc.nome_usuario IS NULL OR (
      UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL)
      AND UPPER(oc.nome_usuario) NOT IN (SELECT UPPER(nome_completo) FROM colaboradores WHERE UPPER(COALESCE(area, diretoria, '')) LIKE '%COMPRAS%')
  ))
  AND (oc.comprador IS NULL OR (
      UPPER(oc.comprador) NOT IN (SELECT UPPER(comprador_funcional) FROM compradores_funcionais WHERE UPPER(COALESCE(area, '')) LIKE '%COMPRAS%' AND comprador_funcional IS NOT NULL)
      AND UPPER(oc.comprador) NOT IN (SELECT UPPER(nome_completo) FROM colaboradores WHERE UPPER(COALESCE(area, diretoria, '')) LIKE '%COMPRAS%')
  ))
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
    is_forn_sem_oc = [v.strip() for v in args.getlist('is_fornecedor_sem_oc') if v.strip()]
    c_sem_oc = _clause_forn_sem_oc("", is_forn_sem_oc, num_forn_col="numero_fornecedor")
    if c_sem_oc:
        clauses.append(c_sem_oc)
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


_STATIC_ALLOWED_EXT = {'.html', '.js', '.css', '.png', '.jpg', '.jpeg', '.svg', '.ico', '.webp', '.gif',
                       '.woff', '.woff2', '.ttf', '.map'}


@app.route('/<path:filename>')
def static_files(filename):
    # Allowlist: nunca servir código (.py), config (.yaml/.json/.toml), backups (.bak*) ou arquivos ocultos.
    name = os.path.basename(filename).lower()
    ext = os.path.splitext(name)[1]
    if '.bak' in name or ext not in _STATIC_ALLOWED_EXT or name.startswith('.') or '/.' in filename:
        return jsonify({"error": "Not found"}), 404
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
        clauses.append("UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%RGB%'")
        clauses.append("UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE 'ADV%'")
        clauses.append("UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%FOPAG%'")
        clauses.append("UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%ARKER%'")
        clauses.append("UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%FISCAL%'")
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
    if exclude_field != 'is_fornecedor_sem_oc':
        is_forn_sem_oc = [v.strip() for v in args.getlist('is_fornecedor_sem_oc') if v.strip()]
        c_sem_oc = _clause_forn_sem_oc("", is_forn_sem_oc, num_forn_col="numero_fornecedor" if table == 'ordens_compra' else "NUMERO_FORNECEDOR")
        if c_sem_oc:
            clauses.append(c_sem_oc)
    if exclude_field != 'macro_categoria':
        macro_cat = [v.strip() for v in args.getlist('macro_categoria') if v.strip()]
        if macro_cat:
            vals = ','.join([f"'{_esc(v)}'" for v in macro_cat])
            clauses.append(f"COALESCE(macro_categoria, 'Indiretos') IN ({vals})")
    if exclude_field != 'tipo_linha' and table == 'notas_ri':
        tipo_linha = [v.strip() for v in args.getlist('tipo_linha') if v.strip()]
        if tipo_linha:
            vals = ','.join([f"'{_esc(v)}'" for v in tipo_linha])
            clauses.append(f"TIPO_LINHA IN ({vals})")
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


_filters_notas_cache = None
_filters_notas_cache_ts = 0

@app.route('/api/filters/notas')
def filters_notas():
    """Get distinct filter values from notas_ri (initial load, cached in memory with parallel fetch)."""
    global _filters_notas_cache, _filters_notas_cache_ts
    if _filters_notas_cache and (time.time() - _filters_notas_cache_ts) < 7200:
        resp = jsonify(_filters_notas_cache)
        resp.headers['Cache-Control'] = 'public, max-age=7200'
        return resp

    result = {}
    _nf_cond = "AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%RGB%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE 'ADV%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%FOPAG%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%ARKER%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%FISCAL%'"
    
    filter_queries = {
        'anos': f"SELECT DISTINCT SUBSTRING(DATA_LANCAMENTO, 1, 4) AS v FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL {_nf_cond} ORDER BY v DESC",
        'meses': f"SELECT DISTINCT CAST(SUBSTRING(DATA_LANCAMENTO, 6, 2) AS INT) AS v FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL {_nf_cond} ORDER BY v",
        'dias': f"SELECT DISTINCT CAST(SUBSTRING(DATA_LANCAMENTO, 9, 2) AS INT) AS v FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL {_nf_cond} ORDER BY v",
        'empresas': f"SELECT DISTINCT EMPRESA AS v FROM notas_ri WHERE EMPRESA IS NOT NULL AND EMPRESA != '' {_nf_cond} ORDER BY v",
        'grupos': f"SELECT DISTINCT GRUPO_COMPRAS AS v FROM notas_ri WHERE GRUPO_COMPRAS IS NOT NULL AND GRUPO_COMPRAS != '' AND GRUPO_COMPRAS != 'COMERCIAL' {_nf_cond} ORDER BY v",
        'fornecedores': f"SELECT DISTINCT NOME_FORNECEDOR AS v FROM notas_ri WHERE NOME_FORNECEDOR IS NOT NULL AND NOME_FORNECEDOR != '' {_nf_cond} ORDER BY v",
        'unidades': f"SELECT DISTINCT PLANTA AS v FROM notas_ri WHERE PLANTA IS NOT NULL AND PLANTA != '' {_nf_cond} ORDER BY v"
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futs = {k: executor.submit(query, q) for k, q in filter_queries.items()}
        for k, fut in futs.items():
            result[k] = [r['v'] for r in fut.result()]

    _filters_notas_cache = result
    _filters_notas_cache_ts = time.time()
    resp = jsonify(result)
    resp.headers['Cache-Control'] = 'public, max-age=7200'
    return resp


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
    _nf_cond = "AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%RGB%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE 'ADV%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%FOPAG%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%ARKER%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%FISCAL%'"
    result['macro_categoria'] = [r['v'] for r in query(
        f"SELECT DISTINCT COALESCE(MACRO_CATEGORIA, 'Indiretos') AS v FROM notas_ri WHERE MACRO_CATEGORIA IS NOT NULL AND MACRO_CATEGORIA != '' {_nf_cond} ORDER BY v"
    )]
    result['dias'] = [r['v'] for r in query(
        f"SELECT DISTINCT CAST(SUBSTRING(DATA_LANCAMENTO, 9, 2) AS INT) AS v FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL {_nf_cond} ORDER BY v"
    )]
    result['centralizado'] = [r['v'] for r in query(
        f"SELECT DISTINCT CENTRALIZADO AS v FROM notas_ri WHERE CENTRALIZADO IS NOT NULL AND CENTRALIZADO != '' {_nf_cond} ORDER BY v"
    )]
    result['unidade'] = [r['v'] for r in query(
        f"SELECT DISTINCT PLANTA AS v FROM notas_ri WHERE PLANTA IS NOT NULL AND PLANTA != '' {_nf_cond} ORDER BY v"
    )]
    result['status_pagamento'] = [r['v'] for r in query(
        f"SELECT DISTINCT STATUS_PAGAMENTO AS v FROM notas_ri WHERE STATUS_PAGAMENTO IS NOT NULL AND STATUS_PAGAMENTO != '' {_nf_cond} ORDER BY v"
    )]
    result['tipo_nf'] = [r['v'] for r in query(
        f"SELECT DISTINCT TIPO_NF AS v FROM notas_ri WHERE TIPO_NF IS NOT NULL AND TIPO_NF != '' {_nf_cond} ORDER BY v"
    )]
    result['tipo_linha'] = [r['v'] for r in query(
        f"SELECT DISTINCT TIPO_LINHA AS v FROM notas_ri WHERE TIPO_LINHA IS NOT NULL AND TIPO_LINHA != '' {_nf_cond} ORDER BY v"
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
        'req_comprador_sugerido': ('comprador_sugerido', 'requisicoes'),
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
    if table == 'notas_ri':
        rows = query(f"SELECT DISTINCT {col} AS v FROM {table} WHERE {col} ILIKE '%{safe_q}%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%RGB%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE 'ADV%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%FOPAG%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%ARKER%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%FISCAL%' ORDER BY v LIMIT 100")
    else:
        rows = query(f"SELECT DISTINCT {col} AS v FROM {table} WHERE {col} ILIKE '%{safe_q}%' ORDER BY v LIMIT 100")
    return jsonify([r['v'] for r in rows])


@app.route('/api/filters/requisicoes-adv')
def filters_requisicoes_adv():
    """Advanced filter options for requisicoes — dropdown values for status and buyer fields."""
    result = {}
    result['status'] = [r['v'] for r in query(
        "SELECT DISTINCT STATUS AS v FROM requisicoes WHERE STATUS IS NOT NULL AND STATUS != '' ORDER BY v"
    )]
    result['status_ordem'] = [r['v'] for r in query(
        "SELECT DISTINCT STATUS_ORDEM AS v FROM requisicoes WHERE STATUS_ORDEM IS NOT NULL AND STATUS_ORDEM != '' ORDER BY v"
    )]
    result['comprador_sugerido'] = [r['v'] for r in query(
        "SELECT DISTINCT NULLIF(TRIM(comprador_sugerido), '') AS v FROM requisicoes WHERE NULLIF(TRIM(comprador_sugerido), '') IS NOT NULL ORDER BY v"
    )]
    return jsonify(result)


@app.route('/api/filters/ordens-adv')
def filters_ordens_adv():
    """Advanced filter options for ordens_compra — dropdown values for low-cardinality fields."""
    result = {}
    result['comprador'] = [r['v'] for r in query(
        "SELECT DISTINCT COALESCE(NULLIF(TRIM(comprador), ''), NULLIF(TRIM(nome_usuario), '')) AS v FROM ordens_compra WHERE COALESCE(NULLIF(TRIM(comprador), ''), NULLIF(TRIM(nome_usuario), '')) IS NOT NULL ORDER BY v"
    )]
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
        SUM(CASE WHEN SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{prev_year}' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS prev_spend,
        SUM(CASE WHEN SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{current_year}' AND CENTRALIZADO = 'CENTRALIZADO' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS current_central_spend,
        SUM(CASE WHEN SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{prev_year}' AND CENTRALIZADO = 'CENTRALIZADO' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS prev_central_spend,
        ROUND((SUM(CASE WHEN SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{current_year}' AND CENTRALIZADO = 'CENTRALIZADO' THEN VALOR_LIQUIDO_BRL ELSE 0 END) / 
         NULLIF(SUM(CASE WHEN SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{current_year}' THEN VALOR_LIQUIDO_BRL ELSE 0 END), 0) * 100)::numeric, 1)::float AS current_central_pct,
        ROUND((SUM(CASE WHEN SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{prev_year}' AND CENTRALIZADO = 'CENTRALIZADO' THEN VALOR_LIQUIDO_BRL ELSE 0 END) / 
         NULLIF(SUM(CASE WHEN SUBSTRING(DATA_LANCAMENTO, 1, 4) = '{prev_year}' THEN VALOR_LIQUIDO_BRL ELSE 0 END), 0) * 100)::numeric, 1)::float AS prev_central_pct
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
    Temporal Anchor:
      - Diretos / Todos: ordens_compra.DATA_OC (order emission cohort)
      - Indiretos: requisicoes.dt_aprovacao / dt_criacao (requisition cohort, linking downstream to OCs)
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
                NULLIF(TRIM(SUBSTRING({req_date_expr}, 1, 10)), '')::date AS req_dt
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
                NULLIF(TRIM(SUBSTRING(oc.data_oc, 1, 10)), '')::date AS d_oc,
                NULLIF(TRIM(SUBSTRING(oc.dt_aprovacao, 1, 10)), '')::date AS d_aprov,
                oc.data_oc,
                oc.dt_aprovacao,
                oc.status_aprovacao,
                oc.status_fechamento,
                oc.requisicao
            FROM ordens_compra oc
            WHERE {oc_where_cohort}
              AND (
                  (oc.requisicao IS NOT NULL AND oc.requisicao != '' AND oc.requisicao IN (SELECT requisicao FROM req_nums))
                  OR oc.numero_oc IN (SELECT numero_oc FROM req_ocs)
              )
              AND UPPER(TRIM(COALESCE(oc.status_fechamento, ''))) NOT IN ('CANCELADA', 'CANCELADO', 'INCOMPLETA', 'RETIRADA', 'REJEITADA')
        ),
        oc_aprov AS (
            SELECT * FROM oc_cohort 
            WHERE UPPER(TRIM(COALESCE(status_aprovacao, ''))) IN ('APPROVED', 'APROVADO')
               OR (d_aprov IS NOT NULL AND UPPER(TRIM(COALESCE(status_fechamento, ''))) NOT IN ('PENDENTE APROVACAO', 'PENDING APPROVAL'))
        ),
        nf_agg AS (
            SELECT 
                nf.chave_oc_linha,
                SUM(nf.valor_liquido_brl) AS nf_line_spend,
                COUNT(DISTINCT nf.nota_fiscal) AS nf_line_count,
                MIN(NULLIF(TRIM(SUBSTRING(nf.data_lancamento, 1, 10)), '')::date) AS min_nf_dt,
                MAX(NULLIF(TRIM(SUBSTRING(nf.data_lancamento, 1, 10)), '')::date) AS max_nf_dt
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
        rows, err = query_debug(sql)
        if err:
            _log.error("Lead time query error (scope=indiretos): %s", err)
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
                NULLIF(TRIM(SUBSTRING(oc.data_oc, 1, 10)), '')::date AS d_oc,
                NULLIF(TRIM(SUBSTRING(oc.dt_aprovacao, 1, 10)), '')::date AS d_aprov,
                oc.data_oc,
                oc.dt_aprovacao,
                oc.status_aprovacao,
                oc.status_fechamento
            FROM ordens_compra oc
            WHERE {oc_where}
              AND UPPER(TRIM(COALESCE(oc.status_fechamento, ''))) NOT IN ('CANCELADA', 'CANCELADO', 'INCOMPLETA', 'RETIRADA', 'REJEITADA')
        ),
        oc_aprov AS (
            SELECT * FROM oc_cohort 
            WHERE UPPER(TRIM(COALESCE(status_aprovacao, ''))) IN ('APPROVED', 'APROVADO')
               OR (d_aprov IS NOT NULL AND UPPER(TRIM(COALESCE(status_fechamento, ''))) NOT IN ('PENDENTE APROVACAO', 'PENDING APPROVAL'))
        ),
        nf_agg AS (
            SELECT 
                nf.chave_oc_linha,
                SUM(nf.valor_liquido_brl) AS nf_line_spend,
                COUNT(DISTINCT nf.nota_fiscal) AS nf_line_count,
                MIN(NULLIF(TRIM(SUBSTRING(nf.data_lancamento, 1, 10)), '')::date) AS min_nf_dt,
                MAX(NULLIF(TRIM(SUBSTRING(nf.data_lancamento, 1, 10)), '')::date) AS max_nf_dt
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
        rows, err = query_debug(sql)
        if err:
            _log.error("Lead time query error (scope=%s): %s", scope, err)
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
        SUM(CASE WHEN NUMERO_OC != 'Nota sem OC' AND (OC_POS_FATURA = 'NÃO' OR COALESCE(IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'ESPECIAL') THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS regular,
        SUM(CASE WHEN OC_POS_FATURA = 'SIM' AND COALESCE(IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS pos_fatura,
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
    _nf_ent_w = (
        "WHERE NUMERO_OC != 'Nota sem OC' AND NUMERO_OC != '' "
        "AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%RGB%' "
        "AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE 'ADV%' "
        "AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%FOPAG%' "
        "AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%ARKER%' "
        "AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%FISCAL%' "
        + (' AND ' + ' AND '.join(_nf_ent_parts) if _nf_ent_parts else '')
    )
    _total_ocs_faturadas = f"SELECT COUNT(DISTINCT NUMERO_OC) FROM notas_ri {_nf_ent_w}"

    # Acordos OPEN >180 dias (tabela dedicada acordos_compra — referência: dt_criacao)
    _bla_emp_filter = f"AND empresa IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _oc_empresa])})" if _oc_empresa else ""
    _total_acordos_vl = f"SELECT SUM(valor_total) FROM acordos_compra WHERE status = 'OPEN' {_bla_emp_filter}"
    blanket_old = query(f"""
    SELECT COUNT(*)::int AS qty,
           COALESCE(SUM(valor_total), 0)::float AS valor,
           COUNT(*)::float / NULLIF(({_total_ocs_faturadas}), 0)::float * 100 AS pct_qty,
           COALESCE(SUM(valor_total), 0)::float / NULLIF(({_total_acordos_vl}), 0)::float * 100 AS pct_valor
    FROM acordos_compra
    WHERE status = 'OPEN'
      AND numero_acordo IS NOT NULL AND numero_acordo != ''
      AND dt_criacao IS NOT NULL AND dt_criacao != ''
      AND (CURRENT_DATE - dt_criacao::date) > 180
      AND COALESCE(valor_liberado, 0) = 0
      {_bla_emp_filter}
    """)

    # Post-invoice: análise por NF com âncora em DATA_PAGAMENTO (mesma regra e granularidade da Governança)
    pf_clauses, _ = _parse_filters(request.args, date_col='DATA_PAGAMENTO', table_prefix='nf')
    pf_base = [c for c in pf_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    _pf_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    if _pf_comp:
        pf_base.append(f"COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO) IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _pf_comp])})")
    w_pf = _where(pf_base)
    and_pf = 'AND' if pf_base else 'WHERE'

    pos_fatura = query(f"""
    WITH pf_sub AS (
        SELECT 
            COUNT(DISTINCT nf.NOTA_FISCAL)::int AS qty, 
            COALESCE(SUM(nf.VALOR_LIQUIDO_BRL), 0)::float AS valor
        FROM notas_ri nf
        LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
        {w_pf}
        {and_pf} nf.NUMERO_OC != 'Nota sem OC'
          AND nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != ''
          AND oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
          AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
          AND SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date < SUBSTRING(oc.DT_APROVACAO, 1, 10)::date
          AND COALESCE(nf.IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'
    ),
    tot_sub AS (
        SELECT 
            COUNT(DISTINCT nf.NOTA_FISCAL)::float AS tot_qty,
            COALESCE(SUM(nf.VALOR_LIQUIDO_BRL), 0)::float AS tot_valor
        FROM notas_ri nf
        LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
        {w_pf}
    )
    SELECT 
        pf.qty, 
        pf.valor,
        pf.qty::float / NULLIF(tot.tot_qty, 0) * 100 AS pct_qty,
        pf.valor::float / NULLIF(tot.tot_valor, 0) * 100 AS pct_valor
    FROM pf_sub pf, tot_sub tot
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
               LAG(data_lancamento) OVER (
                   PARTITION BY 
                       COALESCE(
                           NULLIF(NULLIF(NULLIF(TRIM(codigo_item), ''), '~NOVALUE~'), 'VAZIO'),
                           UPPER(TRIM(REGEXP_REPLACE(ds_item, '\s+', ' ', 'g')))
                       ),
                       nome_fornecedor, 
                       COALESCE(NULLIF(numero_fornecedor, ''), SUBSTRING(nota_fiscal FROM '-([0-9]+)$'))
                   ORDER BY data_lancamento, numero_ri
               ) AS data_anterior,
               LAG(nota_fiscal) OVER (
                   PARTITION BY 
                       COALESCE(
                           NULLIF(NULLIF(NULLIF(TRIM(codigo_item), ''), '~NOVALUE~'), 'VAZIO'),
                           UPPER(TRIM(REGEXP_REPLACE(ds_item, '\s+', ' ', 'g')))
                       ),
                       nome_fornecedor, 
                       COALESCE(NULLIF(numero_fornecedor, ''), SUBSTRING(nota_fiscal FROM '-([0-9]+)$'))
                   ORDER BY data_lancamento, numero_ri
               ) AS nf_anterior,
               LAG(ds_item) OVER (
                   PARTITION BY 
                       COALESCE(
                           NULLIF(NULLIF(NULLIF(TRIM(codigo_item), ''), '~NOVALUE~'), 'VAZIO'),
                           UPPER(TRIM(REGEXP_REPLACE(ds_item, '\s+', ' ', 'g')))
                       ),
                       nome_fornecedor, 
                       COALESCE(NULLIF(numero_fornecedor, ''), SUBSTRING(nota_fiscal FROM '-([0-9]+)$'))
                   ORDER BY data_lancamento, numero_ri
               ) AS ds_item_anterior,
               LAG(preco_brl) OVER (
                   PARTITION BY 
                       COALESCE(
                           NULLIF(NULLIF(NULLIF(TRIM(codigo_item), ''), '~NOVALUE~'), 'VAZIO'),
                           UPPER(TRIM(REGEXP_REPLACE(ds_item, '\s+', ' ', 'g')))
                       ),
                       nome_fornecedor, 
                       COALESCE(NULLIF(numero_fornecedor, ''), SUBSTRING(nota_fiscal FROM '-([0-9]+)$'))
                   ORDER BY data_lancamento, numero_ri
               ) AS preco_brl_anterior,
               LAG(numero_oc) OVER (
                   PARTITION BY 
                       COALESCE(
                           NULLIF(NULLIF(NULLIF(TRIM(codigo_item), ''), '~NOVALUE~'), 'VAZIO'),
                           UPPER(TRIM(REGEXP_REPLACE(ds_item, '\s+', ' ', 'g')))
                       ),
                       nome_fornecedor, 
                       COALESCE(NULLIF(numero_fornecedor, ''), SUBSTRING(nota_fiscal FROM '-([0-9]+)$'))
                   ORDER BY data_lancamento, numero_ri
               ) AS oc_anterior
        FROM notas_ri
        WHERE 1=1 {and_entity}
    )
    SELECT ds_item, codigo_item, nome_fornecedor,
           COALESCE(NULLIF(numero_fornecedor, ''), SUBSTRING(nota_fiscal FROM '-([0-9]+)$')) AS local_fornecedor,
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
      -- Não comparar NFs da mesma OC (ex.: entrada + pagamento restante na mesma OC)
      AND NOT (
          NULLIF(TRIM(numero_oc), '') IS NOT NULL AND numero_oc != 'Nota sem OC'
          AND TRIM(numero_oc) = TRIM(COALESCE(oc_anterior, ''))
      )
      AND GREATEST(preco_brl, preco_brl_anterior) / LEAST(preco_brl, preco_brl_anterior) <= 2
      AND (codigo_item IS NULL OR codigo_item NOT LIKE 'F-%%')
      AND (
          (codigo_item IS NOT NULL AND TRIM(codigo_item) NOT IN ('', '~NOVALUE~', 'VAZIO'))
          OR (ds_item_anterior IS NOT NULL AND UPPER(TRIM(ds_item)) = UPPER(TRIM(ds_item_anterior)))
      )
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
    is_forn_sem_oc = [v.strip() for v in request.args.getlist('is_fornecedor_sem_oc') if v.strip()]
    c_sem_oc = _clause_forn_sem_oc("", is_forn_sem_oc, num_forn_col="numero_fornecedor")
    if c_sem_oc:
        clauses.append(c_sem_oc)
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
    is_forn_sem_oc = [v.strip() for v in request.args.getlist('is_fornecedor_sem_oc') if v.strip()]
    c_sem_oc = _clause_forn_sem_oc("", is_forn_sem_oc, num_forn_col="numero_fornecedor")
    if c_sem_oc:
        clauses.append(c_sem_oc)
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
    is_forn_sem_oc = [v.strip() for v in request.args.getlist('is_fornecedor_sem_oc') if v.strip()]
    c_sem_oc = _clause_forn_sem_oc("", is_forn_sem_oc, num_forn_col="numero_fornecedor")
    if c_sem_oc:
        clauses.append(c_sem_oc)
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
    is_forn_sem_oc = [v.strip() for v in request.args.getlist('is_fornecedor_sem_oc') if v.strip()]
    c_sem_oc = _clause_forn_sem_oc("", is_forn_sem_oc, num_forn_col="numero_fornecedor")
    if c_sem_oc:
        clauses.append(c_sem_oc)
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
    is_forn_sem_oc = [v.strip() for v in request.args.getlist('is_fornecedor_sem_oc') if v.strip()]
    c_sem_oc = _clause_forn_sem_oc("", is_forn_sem_oc, num_forn_col="numero_fornecedor")
    if c_sem_oc:
        clauses.append(c_sem_oc)
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

_filters_comercial_cache = None
_filters_comercial_cache_ts = 0

@app.route('/api/filters/comercial')
def filters_comercial():
    """Filter options for comercial page — cached in memory with parallel query fetch."""
    global _filters_comercial_cache, _filters_comercial_cache_ts
    if _filters_comercial_cache and (time.time() - _filters_comercial_cache_ts) < 7200:
        resp = jsonify(_filters_comercial_cache)
        resp.headers['Cache-Control'] = 'public, max-age=7200'
        return resp

    result = {}
    _nf_cond = "AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%RGB%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE 'ADV%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%FOPAG%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%ARKER%' AND UPPER(COALESCE(NOTA_FISCAL, '')) NOT LIKE '%FISCAL%'"
    
    com_queries = {
        'anos': f"SELECT DISTINCT SUBSTRING(DATA_LANCAMENTO, 1, 4) AS v FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL {_nf_cond} ORDER BY v DESC",
        'meses': f"SELECT DISTINCT CAST(SUBSTRING(DATA_LANCAMENTO, 6, 2) AS INT) AS v FROM notas_ri WHERE DATA_LANCAMENTO IS NOT NULL {_nf_cond} ORDER BY v",
        'empresas': f"SELECT DISTINCT EMPRESA AS v FROM notas_ri WHERE EMPRESA IS NOT NULL AND EMPRESA != '' {_nf_cond} ORDER BY v",
        'grupos': f"SELECT DISTINCT GRUPO_COMPRAS AS v FROM notas_ri WHERE GRUPO_COMPRAS IS NOT NULL AND GRUPO_COMPRAS != '' AND GRUPO_COMPRAS != 'COMERCIAL' {_nf_cond} ORDER BY v",
        'fornecedores': f"SELECT NOME_FORNECEDOR AS v, SUM(VALOR_LIQUIDO_BRL) AS spend FROM notas_ri WHERE NOME_FORNECEDOR IS NOT NULL AND NOME_FORNECEDOR != '' {_nf_cond} GROUP BY NOME_FORNECEDOR HAVING SUM(VALOR_LIQUIDO_BRL) > 0 ORDER BY spend DESC"
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futs = {k: executor.submit(query, q) for k, q in com_queries.items()}
        for k, fut in futs.items():
            result[k] = [r['v'] for r in fut.result()]

    _filters_comercial_cache = result
    _filters_comercial_cache_ts = time.time()
    resp = jsonify(result)
    resp.headers['Cache-Control'] = 'public, max-age=7200'
    return resp


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

    sql = f"""
    SELECT
        COUNT(DISTINCT CASE WHEN NUMERO_OC != 'Nota sem OC' AND NUMERO_OC IS NOT NULL THEN NUMERO_OC END) AS total_oc_faturadas,
        COUNT(DISTINCT NOTA_FISCAL) AS total_notas,
        SUM(VALOR_LIQUIDO_BRL) AS total_spend,
        COUNT(DISTINCT CASE WHEN URGENTE = 'SIM' THEN NUMERO_OC END) AS urgente_qty,
        SUM(CASE WHEN URGENTE = 'SIM' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS urgente_val,
        COUNT(DISTINCT CASE WHEN NUMERO_OC = 'Nota sem OC' THEN NOTA_FISCAL END) AS sem_oc_qty,
        SUM(CASE WHEN NUMERO_OC = 'Nota sem OC' THEN VALOR_LIQUIDO_BRL ELSE 0 END) AS sem_oc_val
    FROM notas_ri
    {w}
    """
    result = query(sql, params)

    # OC Pós-Fatura: análise por NF com âncora em DATA_PAGAMENTO
    # Regra de negócio alinhada com o cliente:
    # - Denominador: total de NFs considerando os filtros da página (respeitando IS_FORNECEDOR_NAO_NEGOCIAVEL e IS_FORNECEDOR_ESPECIAL)
    # - Numerador: total de faturas pós-fatura sem fornecedores especiais (exclui fornecedores especiais)
    # Executado em 1 único aggregate pass para máxima performance (0 overhead / zero latência adicional)
    pf_clauses, _ = _parse_filters(request.args, date_col='DATA_PAGAMENTO', table_prefix='nf')
    pf_base = [c for c in pf_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    _pf_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    if _pf_comp:
        pf_base.append(f"COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO) IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _pf_comp])})")
    w_pf = _where(pf_base)

    pos_fatura_sql = f"""
    SELECT
        COUNT(DISTINCT CASE
            WHEN nf.NUMERO_OC != 'Nota sem OC'
             AND nf.NUMERO_OC IS NOT NULL
             AND nf.NUMERO_OC != ''
             AND oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
             AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
             AND SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date < SUBSTRING(oc.DT_APROVACAO, 1, 10)::date
             AND COALESCE(nf.IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'
            THEN nf.NOTA_FISCAL
        END) AS pos_fatura_qty,

        COALESCE(SUM(CASE
            WHEN nf.NUMERO_OC != 'Nota sem OC'
             AND nf.NUMERO_OC IS NOT NULL
             AND nf.NUMERO_OC != ''
             AND oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
             AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
             AND SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date < SUBSTRING(oc.DT_APROVACAO, 1, 10)::date
             AND COALESCE(nf.IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'
            THEN nf.VALOR_LIQUIDO_BRL
            ELSE 0
        END), 0) AS pos_fatura_val,

        COUNT(DISTINCT CASE
            WHEN nf.NUMERO_OC != 'Nota sem OC' AND nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != ''
            THEN nf.NUMERO_OC
        END) AS total_oc_faturadas_pgto,

        COUNT(DISTINCT CASE
            WHEN nf.NUMERO_OC != 'Nota sem OC' AND nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != ''
            THEN nf.NOTA_FISCAL
        END) AS total_nf_com_oc_pgto,

        COUNT(DISTINCT CASE
            WHEN nf.NOTA_FISCAL IS NOT NULL AND nf.NOTA_FISCAL != ''
            THEN nf.NOTA_FISCAL
        END) AS total_nfs_pgto,

        -- Notas sem OC: âncora DATA_PAGAMENTO (NFs sem data de pagamento ficam fora)
        COUNT(DISTINCT CASE
            WHEN nf.NUMERO_OC = 'Nota sem OC' AND NULLIF(TRIM(nf.DATA_PAGAMENTO), '') IS NOT NULL
            THEN nf.NOTA_FISCAL
        END) AS sem_oc_qty_pgto,
        COALESCE(SUM(CASE
            WHEN nf.NUMERO_OC = 'Nota sem OC' AND NULLIF(TRIM(nf.DATA_PAGAMENTO), '') IS NOT NULL
            THEN nf.VALOR_LIQUIDO_BRL ELSE 0
        END), 0) AS sem_oc_val_pgto,
        COALESCE(SUM(CASE
            WHEN NULLIF(TRIM(nf.DATA_PAGAMENTO), '') IS NOT NULL
            THEN nf.VALOR_LIQUIDO_BRL ELSE 0
        END), 0) AS total_spend_pgto
    FROM notas_ri nf
    LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
    {w_pf}
    """
    # Decentralized >30k (source: ordens_compra, filter by DATA_OC)
    oc_clauses_gov, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', table_prefix='oc')
    oc_gov_filtered = [c for c in oc_clauses_gov if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    _comp_vals = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    if _comp_vals:
        oc_gov_filtered.append(f"oc.nome_usuario IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals])})")
    w_oc_gov = _where(oc_gov_filtered)
    oc_and_kw = 'AND' if oc_gov_filtered else 'WHERE'

    decentral_sql = f"""
    SELECT COUNT(*) AS qty, COALESCE(SUM(valor_oc), 0) AS valor
    FROM (
        SELECT oc.NUMERO_OC, SUM(oc.valor_original_brl) AS valor_oc
        FROM ordens_compra oc
        {w_oc_gov}
        {oc_and_kw} oc.CENTRALIZADO = 'DESCENTRALIZADO'
        AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
        AND (
            UPPER(COALESCE(oc.status_aprovacao, '')) IN ('APPROVED', 'APROVADO')
            OR (UPPER(COALESCE(oc.status_fechamento, '')) = 'CANCELADA' AND (COALESCE(oc.qtd_faturada, 0) > 0 OR COALESCE(oc.valor_utilizado_brl, 0) > 0))
        )
        AND UPPER(COALESCE(oc.status_fechamento, '')) NOT IN ('PENDENTE APROVACAO', 'PENDING APPROVAL', 'INCOMPLETA', 'REJEITADA', 'RETIRADA')
        {_EXCL_COMPRAS_DECENTRAL_OC}
        GROUP BY oc.NUMERO_OC
        HAVING SUM(oc.valor_original_brl) > 30000
    ) sub
    """

    # Total OCs descentralizadas emitidas no período (para o percentual do card)
    total_dec_sql = f"""
    SELECT COUNT(DISTINCT oc.NUMERO_OC) AS total
    FROM ordens_compra oc
    {w_oc_gov}
    {oc_and_kw} oc.CENTRALIZADO = 'DESCENTRALIZADO'
      AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
      AND (
          UPPER(COALESCE(oc.status_aprovacao, '')) IN ('APPROVED', 'APROVADO')
          OR (UPPER(COALESCE(oc.status_fechamento, '')) = 'CANCELADA' AND (COALESCE(oc.qtd_faturada, 0) > 0 OR COALESCE(oc.valor_utilizado_brl, 0) > 0))
      )
      AND UPPER(COALESCE(oc.status_fechamento, '')) NOT IN ('PENDENTE APROVACAO', 'PENDING APPROVAL', 'INCOMPLETA', 'REJEITADA', 'RETIRADA')
      {_EXCL_COMPRAS_DECENTRAL_OC}
    """

    # Blanket >180 dias (tabela dedicada acordos_compra — referência: dt_criacao)
    _bla_parts = [
        "status = 'OPEN'",
        "numero_acordo IS NOT NULL AND numero_acordo != ''",
        "dt_criacao IS NOT NULL AND dt_criacao != ''",
        "(CURRENT_DATE - dt_criacao::date) > 180",
        "COALESCE(valor_liberado, 0) = 0",
    ]
    _bla_emp = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    if _bla_emp:
        _bla_parts.append(f"empresa IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _bla_emp])})")
    _bla_frn = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
    if _bla_frn:
        _bla_parts.append(f"fornecedor IN ({','.join([chr(39)+_esc(f_)+chr(39) for e in _bla_frn])})")
    _bla_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    if _bla_comp:
        _c_list = ','.join([chr(39)+_esc(v)+chr(39) for v in _bla_comp])
        _bla_parts.append(f"(comprador IN ({_c_list}) OR usuario_comprador IN ({_c_list}))")
    _bla_where = ' AND '.join(_bla_parts)

    blanket_old_sql = f"""
    SELECT COUNT(*)::int AS qty, COALESCE(SUM(valor_total), 0)::float AS valor
    FROM acordos_compra
    WHERE {_bla_where}
    """

    # OCs Sucessivas (source: ordens_compra, filter by DATA_OC)
    sucessivas_sql = f"""
    WITH oc_items AS (
        SELECT
            oc.numero_oc,
            COALESCE(NULLIF(TRIM(oc.numero_fornecedor), ''), '0') AS num_forn,
            COALESCE(NULLIF(TRIM(oc.nome_fornecedor), ''), 'Não informado') AS nome_forn,
            COALESCE(NULLIF(TRIM(oc.item_aquisicao), ''), NULLIF(TRIM(oc.descricao_item), '')) AS item,
            SUBSTRING(oc.data_oc, 1, 7) AS mes_oc,
            SUM(COALESCE(oc.valor_original_brl, 0)) AS valor_oc
        FROM ordens_compra oc
        {w_oc_gov}
          AND oc.numero_oc IS NOT NULL AND oc.numero_oc != ''
          AND oc.data_oc IS NOT NULL AND oc.data_oc != ''
          AND (
              (oc.item_aquisicao IS NOT NULL AND TRIM(oc.item_aquisicao) NOT IN ('', '~NOVALUE~'))
              OR (oc.descricao_item IS NOT NULL AND TRIM(oc.descricao_item) != '')
          )
          AND UPPER(COALESCE(oc.status_fechamento, '')) NOT IN ('INCOMPLETA', 'REJEITADA', 'RETIRADA')
        GROUP BY
            oc.numero_oc,
            COALESCE(NULLIF(TRIM(oc.numero_fornecedor), ''), '0'),
            COALESCE(NULLIF(TRIM(oc.nome_fornecedor), ''), 'Não informado'),
            COALESCE(NULLIF(TRIM(oc.item_aquisicao), ''), NULLIF(TRIM(oc.descricao_item), '')),
            SUBSTRING(oc.data_oc, 1, 7)
    ),
    oc_groups AS (
        SELECT
            numero_oc,
            valor_oc,
            num_forn,
            item,
            mes_oc,
            COUNT(*) OVER (PARTITION BY num_forn, nome_forn, item, mes_oc) AS qtd_ocs_grupo
        FROM oc_items
    )
    SELECT
        COUNT(DISTINCT CASE WHEN qtd_ocs_grupo >= 2 THEN num_forn || '|' || item || '|' || mes_oc END) AS total_grupos,
        COUNT(DISTINCT CASE WHEN qtd_ocs_grupo >= 2 THEN numero_oc END) AS total_ocs,
        COALESCE(SUM(CASE WHEN qtd_ocs_grupo >= 2 THEN valor_oc ELSE 0 END), 0)::float AS valor,
        COALESCE(SUM(valor_oc), 0)::float AS total_valor_ocs_periodo,
        COUNT(DISTINCT numero_oc) AS total_ocs_periodo
    FROM oc_groups
    """

    # OCs abertas > 90 dias (ignora filtros de data, respeita filtros de entidade)
    oc90_kpi_clauses, _ = _parse_filters(
        request.args,
        date_col=None,
        empresa_col='org_desc',
        grupo_col='grupo_compras_oc',
        fornecedor_col='nome_fornecedor',
        unidade_col='unidade',
        is_notas=False
    )
    _comp_vals_kpi90 = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    if _comp_vals_kpi90:
        _c_list = ','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals_kpi90])
        oc90_kpi_clauses.append(f"COALESCE(NULLIF(comprador, ''), usuario_comprador, nome_usuario) IN ({_c_list})")

    tot_open_clauses = list(oc90_kpi_clauses)
    tot_open_clauses.append("STATUS_FECHAMENTO = 'ABERTA'")
    w_tot_open = _where(tot_open_clauses)
    total_oc_abertas_sql = f"""
    SELECT COUNT(DISTINCT numero_oc)::int AS total
    FROM ordens_compra
    {w_tot_open}
    """

    oc90_kpi_clauses.append("STATUS_FECHAMENTO = 'ABERTA'")
    oc90_kpi_clauses.append("dias_aberto > 90")
    w_oc90_kpi = _where(oc90_kpi_clauses)
    oc90_kpi_sql = f"""
    SELECT COUNT(DISTINCT numero_oc)::int AS qty, COALESCE(SUM(valor_original_brl), 0)::float AS valor
    FROM ordens_compra
    {w_oc90_kpi}
    """

    # Parallel execution of all governance queries for ultra-fast response (<1s)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        f_main = executor.submit(query, sql, params)
        f_pf = executor.submit(query, pos_fatura_sql)
        f_dec = executor.submit(query, decentral_sql)
        f_tot_dec = executor.submit(query, total_dec_sql)
        f_bla = executor.submit(query, blanket_old_sql)
        f_suc = executor.submit(query, sucessivas_sql)
        f_oc90 = executor.submit(query, oc90_kpi_sql)
        f_tot_open = executor.submit(query, total_oc_abertas_sql)

        result = f_main.result()
        pf_agg = f_pf.result()
        decentral = f_dec.result()
        total_dec = f_tot_dec.result()
        blanket_old = f_bla.result()
        sucessivas = f_suc.result()
        oc90_res = f_oc90.result()
        tot_open_res = f_tot_open.result()

    pos_row = pf_agg[0] if pf_agg else {}

    r = result[0] if result else {}
    r['pos_fatura_qty'] = pos_row.get('pos_fatura_qty', 0)
    r['pos_fatura_val'] = pos_row.get('pos_fatura_val', 0)
    r['total_oc_faturadas_pgto'] = pos_row.get('total_oc_faturadas_pgto', 0)
    r['total_nf_com_oc_pgto'] = pos_row.get('total_nf_com_oc_pgto', 0)
    r['total_nfs_pgto'] = pos_row.get('total_nfs_pgto', 0)
    # Card "Nota sem OC": âncora DATA_PAGAMENTO (sobrescreve a versão por DATA_LANCAMENTO)
    r['sem_oc_qty'] = pos_row.get('sem_oc_qty_pgto', 0)
    r['sem_oc_val'] = pos_row.get('sem_oc_val_pgto', 0)
    r['total_spend_pgto'] = pos_row.get('total_spend_pgto', 0)
    r['decentral_qty'] = decentral[0]['qty'] if decentral else 0
    r['decentral_val'] = decentral[0]['valor'] if decentral else 0
    r['total_oc_decentral'] = total_dec[0]['total'] if total_dec else 0
    r['blanket_old_qty'] = blanket_old[0]['qty'] if blanket_old else 0
    r['blanket_old_val'] = blanket_old[0]['valor'] if blanket_old else 0
    r['sucessivas_groups_qty'] = sucessivas[0]['total_grupos'] if sucessivas else 0
    r['sucessivas_qty'] = sucessivas[0]['total_ocs'] if sucessivas else 0
    r['sucessivas_val'] = sucessivas[0]['valor'] if sucessivas else 0
    r['total_valor_ocs_periodo'] = sucessivas[0]['total_valor_ocs_periodo'] if sucessivas else 0
    r['total_ocs_periodo'] = sucessivas[0]['total_ocs_periodo'] if sucessivas else 0
    r['oc90_qty'] = oc90_res[0]['qty'] if oc90_res else 0
    r['oc90_val'] = oc90_res[0]['valor'] if oc90_res else 0
    r['total_oc_abertas'] = tot_open_res[0]['total'] if tot_open_res else 0
    return jsonify(r)


@app.route('/api/governance/deviation-impact')
def governance_deviation_impact():
    """Which deviation has largest impact."""
    clauses, params = _parse_filters(request.args)
    w = _where(clauses)
    and_kw = 'AND' if clauses else 'WHERE'

    # Post-invoice: análise por NF com âncora em DATA_PAGAMENTO (exclui fornecedores especiais)
    clauses_pf, _ = _parse_filters(request.args, date_col='DATA_PAGAMENTO', table_prefix='nf')
    pf_base = [c for c in clauses_pf if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    _comp_vals_pf = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    if _comp_vals_pf:
        pf_base.append(f"oc.nome_usuario IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals_pf])})")
    w_pf = _where(pf_base)
    and_pf = 'AND' if pf_base else 'WHERE'
    pos_sql = f"""SELECT COALESCE(SUM(nf.VALOR_LIQUIDO_BRL), 0) AS val, COUNT(DISTINCT nf.NOTA_FISCAL)::int AS qty
    FROM notas_ri nf
    LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
    {w_pf} {and_pf} nf.NUMERO_OC != 'Nota sem OC'
      AND nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != ''
      AND oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
      AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
      AND SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date < SUBSTRING(oc.DT_APROVACAO, 1, 10)::date
      AND COALESCE(nf.IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'"""
    # Emergency
    urg_sql = f"SELECT SUM(VALOR_LIQUIDO_BRL) AS val, COUNT(DISTINCT NUMERO_OC)::int AS qty FROM notas_ri {w} {and_kw} URGENTE = 'SIM'"
    # Without PO
    # Without PO — âncora DATA_PAGAMENTO (NFs sem data de pagamento ficam fora), alinhado ao Card e à Tabela
    sem_sql = f"""SELECT COALESCE(SUM(nf.VALOR_LIQUIDO_BRL), 0) AS val, COUNT(DISTINCT nf.NOTA_FISCAL)::int AS qty
    FROM notas_ri nf
    LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
    {w_pf} {and_pf} nf.NUMERO_OC = 'Nota sem OC'
      AND NULLIF(TRIM(nf.DATA_PAGAMENTO), '') IS NOT NULL"""
    # Decentralized >30k (source: ordens_compra, filter by DATA_OC — alinhado com o Card e com a Tabela)
    oc_clauses_gov, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', table_prefix='oc')
    oc_gov_filtered = [c for c in oc_clauses_gov if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    _comp_vals = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    if _comp_vals:
        oc_gov_filtered.append(f"oc.nome_usuario IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals])})")
    w_oc_gov = _where(oc_gov_filtered)
    oc_and_kw = 'AND' if oc_gov_filtered else 'WHERE'
    dec_sql = f"""
    SELECT COALESCE(SUM(valor_oc), 0)::float AS val, COUNT(*)::int AS qty FROM (
        SELECT oc.NUMERO_OC, SUM(oc.valor_original_brl) AS valor_oc
        FROM ordens_compra oc
        {w_oc_gov}
        {oc_and_kw} oc.CENTRALIZADO = 'DESCENTRALIZADO'
          AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
          AND (
              UPPER(COALESCE(oc.status_aprovacao, '')) IN ('APPROVED', 'APROVADO')
              OR (UPPER(COALESCE(oc.status_fechamento, '')) = 'CANCELADA' AND (COALESCE(oc.qtd_faturada, 0) > 0 OR COALESCE(oc.valor_utilizado_brl, 0) > 0))
          )
          AND UPPER(COALESCE(oc.status_fechamento, '')) NOT IN ('PENDENTE APROVACAO', 'PENDING APPROVAL', 'INCOMPLETA', 'REJEITADA', 'RETIRADA')
          {_EXCL_COMPRAS_DECENTRAL_OC}
        GROUP BY oc.NUMERO_OC
        HAVING SUM(oc.valor_original_brl) > 30000
    ) sub
    """
    # Acordos OPEN >180 dias (tabela dedicada acordos_compra — referência: dt_criacao)
    _bla_imp_parts = [
        "status = 'OPEN'",
        "numero_acordo IS NOT NULL AND numero_acordo != ''",
        "dt_criacao IS NOT NULL AND dt_criacao != ''",
        "(CURRENT_DATE - dt_criacao::date) > 180",
        "COALESCE(valor_liberado, 0) = 0",
    ]
    _bla_imp_emp = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
    if _bla_imp_emp:
        _bla_imp_parts.append(f"empresa IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _bla_imp_emp])})")
    _bla_imp_frn = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
    if _bla_imp_frn:
        _bla_imp_parts.append(f"fornecedor IN ({','.join([chr(39)+_esc(f_)+chr(39) for e in _bla_imp_frn])})")
    _bla_imp_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    if _bla_imp_comp:
        _c_list = ','.join([chr(39)+_esc(v)+chr(39) for v in _bla_imp_comp])
        _bla_imp_parts.append(f"(comprador IN ({_c_list}) OR usuario_comprador IN ({_c_list}))")
    _bla_imp_where = ' AND '.join(_bla_imp_parts)

    bla_sql = f"""
    SELECT COALESCE(SUM(valor_total), 0)::float AS val, COUNT(*)::int AS qty
    FROM acordos_compra
    WHERE {_bla_imp_where}
    """
    # OCs abertas > 90 dias — ignores date filters, respects all entity filters
    oc90_clauses, _ = _parse_filters(
        request.args,
        date_col=None,
        empresa_col='org_desc',
        grupo_col='grupo_compras_oc',
        fornecedor_col='nome_fornecedor',
        unidade_col='unidade',
        is_notas=False
    )
    _comp_vals_oc90 = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    if _comp_vals_oc90:
        _c_list = ','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals_oc90])
        oc90_clauses.append(f"COALESCE(NULLIF(comprador, ''), usuario_comprador, nome_usuario) IN ({_c_list})")
    oc90_clauses.append("STATUS_FECHAMENTO = 'ABERTA'")
    oc90_clauses.append("dias_aberto > 90")
    w_oc90 = _where(oc90_clauses)
    oc90_sql = f"""
    SELECT COALESCE(SUM(valor_original_brl), 0)::float AS val, COUNT(DISTINCT numero_oc)::int AS qty
    FROM ordens_compra
    {w_oc90}
    """

    # OCs Sucessivas
    sucessivas_imp_sql = f"""
    WITH oc_items AS (
        SELECT
            oc.numero_oc,
            COALESCE(NULLIF(TRIM(oc.numero_fornecedor), ''), '0') AS num_forn,
            COALESCE(NULLIF(TRIM(oc.nome_fornecedor), ''), 'Não informado') AS nome_forn,
            COALESCE(NULLIF(TRIM(oc.item_aquisicao), ''), NULLIF(TRIM(oc.descricao_item), '')) AS item,
            SUBSTRING(oc.data_oc, 1, 7) AS mes_oc,
            SUM(COALESCE(oc.valor_original_brl, 0)) AS valor_oc
        FROM ordens_compra oc
        {w_oc_gov}
          AND oc.numero_oc IS NOT NULL AND oc.numero_oc != ''
          AND oc.data_oc IS NOT NULL AND oc.data_oc != ''
          AND (
              (oc.item_aquisicao IS NOT NULL AND TRIM(oc.item_aquisicao) NOT IN ('', '~NOVALUE~'))
              OR (oc.descricao_item IS NOT NULL AND TRIM(oc.descricao_item) != '')
          )
          AND UPPER(COALESCE(oc.status_fechamento, '')) NOT IN ('INCOMPLETA', 'REJEITADA', 'RETIRADA')
        GROUP BY
            oc.numero_oc,
            COALESCE(NULLIF(TRIM(oc.numero_fornecedor), ''), '0'),
            COALESCE(NULLIF(TRIM(oc.nome_fornecedor), ''), 'Não informado'),
            COALESCE(NULLIF(TRIM(oc.item_aquisicao), ''), NULLIF(TRIM(oc.descricao_item), '')),
            SUBSTRING(oc.data_oc, 1, 7)
    ),
    oc_groups AS (
        SELECT
            numero_oc,
            valor_oc,
            num_forn,
            item,
            mes_oc,
            COUNT(*) OVER (PARTITION BY num_forn, nome_forn, item, mes_oc) AS qtd_ocs_grupo
        FROM oc_items
    )
    SELECT COALESCE(SUM(valor_oc), 0)::float AS val, COUNT(DISTINCT num_forn || '|' || item || '|' || mes_oc)::int AS qty
    FROM oc_groups
    WHERE qtd_ocs_grupo >= 2
    """

    targets = [
        ('OCs pós-fatura', pos_sql, []),
        ('OCs Descentr. >30K', dec_sql, []),
        ('OCs Sucessivas', sucessivas_imp_sql, []),
        ('OC emergencial', urg_sql, params),
        ('Notas sem OCs', sem_sql, []),
        ('OCs abertas >90 dias', oc90_sql, []),
        ('Acordos de Compra >180 dias', bla_sql, []),
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futs = [(label, executor.submit(query, s, p)) for label, s, p in targets]
        results = []
        for label, fut in futs:
            r = fut.result()
            results.append({'label': label, 'value': r[0]['val'] if r and r[0]['val'] else 0, 'qty': r[0].get('qty', 0) if r else 0})

    return jsonify(sorted(results, key=lambda x: (x.get('qty', 0) or 0, x.get('value', 0) or 0), reverse=True))


@app.route('/api/governance/by-buyer')
def governance_by_buyer():
    """Buyer exceptions table with type, qty, value, and % of buyer total."""
    # Build date + entity filters: LANÇAMENTO para emergencial, PAGAMENTO para pos_fatura, DATA_OC para descentral
    exc_lancto_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO', table_prefix='nf')
    exc_pgto_clauses, _ = _parse_filters(request.args, date_col='DATA_PAGAMENTO', table_prefix='nf')

    lancto_date = [c for c in exc_lancto_clauses if 'DATA_LANCAMENTO' in c]
    pgto_date = [c for c in exc_pgto_clauses if 'DATA_PAGAMENTO' in c]
    exc_base = [c for c in exc_lancto_clauses if 'DATA_LANCAMENTO' not in c and not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    exc_base_and = ('AND ' + ' AND '.join(exc_base)) if exc_base else ''

    lancto_d_and = (' AND ' + ' AND '.join(lancto_date)) if lancto_date else ''
    pgto_d_and = (' AND ' + ' AND '.join(pgto_date)) if pgto_date else ''

    _comp_vals = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    comp_and = f"AND oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals])})" if _comp_vals else ''

    # Filtros de ordens_compra para OCs descentralizadas
    oc_clauses_gov, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', table_prefix='oc')
    oc_gov_filtered = [c for c in oc_clauses_gov if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    if _comp_vals:
        oc_gov_filtered.append(f"oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals])})")
    w_oc_gov = _where(oc_gov_filtered)
    oc_and_kw = 'AND' if oc_gov_filtered else 'WHERE'

    sql = f"""
    WITH oc_desc_30k AS (
        SELECT oc.NUMERO_OC
        FROM ordens_compra oc
        {w_oc_gov}
        {oc_and_kw} oc.CENTRALIZADO = 'DESCENTRALIZADO'
          AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
          AND (
              UPPER(COALESCE(oc.status_aprovacao, '')) IN ('APPROVED', 'APROVADO')
              OR (UPPER(COALESCE(oc.status_fechamento, '')) = 'CANCELADA' AND (COALESCE(oc.qtd_faturada, 0) > 0 OR COALESCE(oc.valor_utilizado_brl, 0) > 0))
          )
          AND UPPER(COALESCE(oc.status_fechamento, '')) NOT IN ('PENDENTE APROVACAO', 'PENDING APPROVAL', 'INCOMPLETA', 'REJEITADA', 'RETIRADA')
          {_EXCL_COMPRAS_DECENTRAL_OC}
        GROUP BY oc.NUMERO_OC
        HAVING SUM(oc.valor_original_brl) > 30000
    ),
    buyer_totals AS (
        SELECT
            COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO, 'Não identificado') AS buyer,
            COUNT(DISTINCT nf.NOTA_FISCAL) AS total_transactions
        FROM notas_ri nf
        LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
        WHERE 1=1 {exc_base_and} {pgto_d_and} {comp_and}
        GROUP BY COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO, 'Não identificado')
    ),
    buyer_exceptions AS (
        SELECT
            COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO, 'Não identificado') AS buyer,
            MAX(COALESCE(NULLIF(oc.usuario_comprador, ''), oc.USUARIO)) AS usuario,
            MAX(oc.DEPARTAMENTO_COMPRADOR) AS area_oc,
            CASE
                WHEN nf.NUMERO_OC != 'Nota sem OC'
                     AND oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                     AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                     AND SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date < SUBSTRING(oc.DT_APROVACAO, 1, 10)::date
                     AND COALESCE(nf.IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'{pgto_d_and} THEN 'OCs Pós-Fatura'
                WHEN nf.URGENTE = 'SIM'{lancto_d_and} THEN 'Emergencial'
                ELSE 'Outra'
            END AS tipo_excecao,
            COUNT(DISTINCT nf.NOTA_FISCAL) AS qty,
            SUM(nf.VALOR_LIQUIDO_BRL) AS valor
        FROM notas_ri nf
        LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
        WHERE 1=1 {exc_base_and} {comp_and}
          AND nf.NUMERO_OC != 'Nota sem OC'
          AND (
              (nf.NUMERO_OC != 'Nota sem OC'
               AND oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
               AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
               AND SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date < SUBSTRING(oc.DT_APROVACAO, 1, 10)::date
               AND COALESCE(nf.IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'{pgto_d_and})
              OR (nf.URGENTE = 'SIM'{lancto_d_and})
          )
        GROUP BY COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO, 'Não identificado'),
                 CASE
                    WHEN nf.NUMERO_OC != 'Nota sem OC'
                         AND oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                         AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                         AND SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date < SUBSTRING(oc.DT_APROVACAO, 1, 10)::date
                         AND COALESCE(nf.IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'{pgto_d_and} THEN 'OCs Pós-Fatura'
                    WHEN nf.URGENTE = 'SIM'{lancto_d_and} THEN 'Emergencial'
                    ELSE 'Outra'
                 END

        UNION ALL

        SELECT
            COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO, 'Não identificado') AS buyer,
            MAX(COALESCE(NULLIF(oc.usuario_comprador, ''), oc.USUARIO)) AS usuario,
            MAX(oc.DEPARTAMENTO_COMPRADOR) AS area_oc,
            'OC Descentr. >30K' AS tipo_excecao,
            COUNT(DISTINCT oc.NUMERO_OC) AS qty,
            SUM(oc.valor_original_brl) AS valor
        FROM ordens_compra oc
        {w_oc_gov}
        {oc_and_kw} oc.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k)
        GROUP BY COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO, 'Não identificado')
    )
    SELECT
        be.buyer,
        be.tipo_excecao,
        be.qty,
        be.valor,
        CASE WHEN COALESCE(bt.total_transactions, 0) > 0
             THEN LEAST(100.0, ROUND((be.qty::float / bt.total_transactions * 100)::numeric, 1))
             ELSE 100.0 END AS pct_transacoes,
        REGEXP_REPLACE(
            COALESCE(
                CASE 
                    WHEN colab.area IS NOT NULL AND colab.nm_unidade IS NOT NULL AND colab.nm_unidade != '' 
                    THEN colab.area || ' - ' || colab.nm_unidade
                    ELSE colab.area 
                END,
                CASE 
                    WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                    THEN cf.area || ' - ' || cf.unidade
                    ELSE cf.area 
                END,
                NULLIF(be.area_oc, ''),
                'Não informado'
            ),
            '^[0-9]+\\s*-\\s*',
            ''
        ) AS depart,
        REGEXP_REPLACE(
            COALESCE(
                CASE 
                    WHEN colab.area IS NOT NULL AND colab.nm_unidade IS NOT NULL AND colab.nm_unidade != '' 
                    THEN colab.area || ' - ' || colab.nm_unidade
                    ELSE colab.area 
                END,
                CASE 
                    WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                    THEN cf.area || ' - ' || cf.unidade
                    ELSE cf.area 
                END,
                NULLIF(be.area_oc, ''),
                'Não informado'
            ),
            '^[0-9]+\\s*-\\s*',
            ''
        ) AS area
    FROM buyer_exceptions be
    LEFT JOIN buyer_totals bt ON be.buyer = bt.buyer
    LEFT JOIN LATERAL (
        SELECT area, nm_unidade
        FROM colaboradores
        WHERE (matricula IS NOT NULL AND matricula = be.usuario)
           OR (id_colaborador IS NOT NULL AND id_colaborador = be.usuario)
           OR (nome_completo IS NOT NULL AND UPPER(nome_completo) = UPPER(be.buyer))
           OR (UPPER(nome_completo) LIKE UPPER(be.buyer) || '%')
        LIMIT 1
    ) colab ON true
    LEFT JOIN LATERAL (
        SELECT area, unidade
        FROM compradores_funcionais
        WHERE (usuario_oracle IS NOT NULL AND LOWER(usuario_oracle) = LOWER(be.usuario))
           OR (comprador_funcional IS NOT NULL AND UPPER(comprador_funcional) = UPPER(be.buyer))
        LIMIT 1
    ) cf ON true
    ORDER BY be.valor DESC
    LIMIT 200
    """
    rows, err = query_debug(sql)
    if err:
        _log.error("BY-BUYER ERROR: %s", err)
    return jsonify(rows)


@app.route('/api/governance/exceptions-table')
def governance_exceptions_table():
    """Exceptions detail table with native Oracle Buyer and Requester information."""
    exc_type = request.args.get('type', 'all')
    page = int(request.args.get('page', '1'))
    per_page_str = str(request.args.get('per_page', '50')).strip()
    try:
        per_page = int(per_page_str)
    except (ValueError, TypeError):
        per_page = 50

    if per_page <= 0 or per_page_str.lower() in ('0', 'all', 'none', '-1'):
        limit_clause = ""
        offset = 0
    else:
        offset = (page - 1) * per_page
        limit_clause = f"LIMIT {per_page} OFFSET {offset}"

    type_filter = ""
    if exc_type == 'pos_fatura':
        # Filtros de entidade e data ancorada em DATA_PAGAMENTO
        pf_clauses, _ = _parse_filters(request.args, date_col='DATA_PAGAMENTO', table_prefix='nf')
        pf_base = [c for c in pf_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
        _pf_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _pf_comp:
            pf_base.append(f"COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO) IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _pf_comp])})")
        pf_where_and = 'AND ' + ' AND '.join(pf_base) if pf_base else ''

        # --- Step 1: aggregate base data (fast, ~1s) ---
        base_sql = f"""
        SELECT
            'OCs pós-fatura' AS tipo_excecao,
            nf.NUMERO_OC AS "NUMERO_OC",
            nf.NOTA_FISCAL AS "NOTA_FISCAL",
            COALESCE(MAX(NULLIF(TRIM(oc.numero_acordo), '')), '-') AS numero_acordo,
            MAX(SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)) AS data_fatura,
            MAX(SUBSTRING(oc.DATA_OC, 1, 10)) AS data_criacao_oc,
            MAX(SUBSTRING(oc.DATA_OC, 1, 10)) AS data_oc,
            MAX(SUBSTRING(oc.DT_APROVACAO, 1, 10)) AS data_aprov_oc,
            MAX(CASE
                WHEN oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                     AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                THEN (SUBSTRING(oc.DT_APROVACAO, 1, 10)::date - SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date)
                ELSE NULL
            END) AS dias_pos_fatura,
            MAX(COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO, 'Não informado')) AS comprador,
            MAX(COALESCE(NULLIF(oc.usuario_comprador, ''), oc.usuario)) AS usuario,
            MAX(oc.DEPARTAMENTO_COMPRADOR) AS dept_oc,
            MAX(COALESCE(oc.NOME_REQUISITANTE, 'Não informado')) AS solicitante,
            REGEXP_REPLACE(
                COALESCE(MAX(oc.DEPARTAMENTO_REQUISITANTE), ''),
                '^[0-9]+\\s*-\\s*',
                ''
            ) AS depart_solicitante,
            MAX(oc.AREA) AS area_oc,
            MAX(nf.NOME_FORNECEDOR) AS fornecedor,
            SUM(nf.VALOR_LIQUIDO_BRL) AS net_spend
        FROM notas_ri nf
        LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
        WHERE nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != '' AND nf.NUMERO_OC != 'Nota sem OC'
          AND oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
          AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
          AND SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date < SUBSTRING(oc.DT_APROVACAO, 1, 10)::date
          AND COALESCE(nf.IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'
          {pf_where_and}
        GROUP BY nf.NUMERO_OC, nf.NOTA_FISCAL
        ORDER BY net_spend DESC
        {limit_clause}
        """
        rows, err = query_debug(base_sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [pos_fatura] base ERROR: %s", err)
            return jsonify(rows)

        # --- Step 2: resolve departments via batch lookup (avoids slow LATERAL) ---
        def _get_name_variants(n):
            if not n or n in ('Não informado', '--', 'Vazio'):
                return []
            n = n.strip()
            variants = [n]
            if ',' in n:
                parts = [p.strip() for p in n.split(',', 1)]
                if len(parts) == 2 and parts[0] and parts[1]:
                    # Oracle format "LastName, FirstName" -> "FirstName LastName"
                    variants.append(f"{parts[1]} {parts[0]}")
                    variants.append(f"{parts[0]} {parts[1]}")
            return list(dict.fromkeys(variants))

        if rows and _colab_available():
            try:
                names_set = set()
                users_set = set()
                for r in rows:
                    for v in _get_name_variants(r.get('comprador')):
                        names_set.add(v)
                    for v in _get_name_variants(r.get('solicitante')):
                        names_set.add(v)
                    u = r.get('usuario')
                    if u:
                        users_set.add(u)

                names_list = list(names_set)
                users_list = list(users_set)

                where_parts = []
                if names_list:
                    esc_names = ','.join([chr(39) + _esc(n.upper()) + chr(39) for n in names_list if n])
                    if esc_names:
                        where_parts.append(f"UPPER(c.nome_completo) IN ({esc_names})")
                        where_parts.append(f"UPPER(cf.comprador_funcional) IN ({esc_names})")
                if users_list:
                    esc_users = ','.join([chr(39) + _esc(u) + chr(39) for u in users_list if u])
                    esc_users_l = ','.join([chr(39) + _esc(u.lower()) + chr(39) for u in users_list if u])
                    if esc_users:
                        where_parts.append(f"c.matricula IN ({esc_users})")
                        where_parts.append(f"c.id_colaborador IN ({esc_users})")
                        where_parts.append(f"LOWER(cf.usuario_oracle) IN ({esc_users_l})")

                dept_rows = []
                if where_parts:
                    dept_sql = (
                        "SELECT DISTINCT ON (UPPER(COALESCE(c.nome_completo, cf.comprador_funcional, '')), COALESCE(c.matricula, cf.usuario_oracle, '')) "
                        "UPPER(COALESCE(c.nome_completo, cf.comprador_funcional, '')) AS nome_key, "
                        "COALESCE(c.matricula, c.id_colaborador, cf.usuario_oracle, '') AS user_key, "
                        "COALESCE(CASE WHEN c.area IS NOT NULL AND c.nm_unidade IS NOT NULL AND c.nm_unidade != '' THEN c.area || ' - ' || c.nm_unidade ELSE c.area END, "
                        "CASE WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' THEN cf.area || ' - ' || cf.unidade ELSE cf.area END) AS dept "
                        "FROM colaboradores c "
                        "FULL OUTER JOIN compradores_funcionais cf ON UPPER(cf.comprador_funcional) = UPPER(c.nome_completo) "
                        f"WHERE {' OR '.join(where_parts)} "
                        "ORDER BY UPPER(COALESCE(c.nome_completo, cf.comprador_funcional, '')), COALESCE(c.matricula, cf.usuario_oracle, '')"
                    )
                    dept_rows = query(dept_sql)

                # Build lookup maps: by name and by user
                _dept_by_name = {}
                _dept_by_user = {}
                for dr in (dept_rows or []):
                    d = dr.get('dept')
                    if not d:
                        continue
                    d = re.sub(r'^[0-9]+\s*-\s*', '', d)
                    nk = (dr.get('nome_key') or '').strip().upper()
                    uk = (dr.get('user_key') or '').strip()
                    if nk and nk not in _dept_by_name:
                        _dept_by_name[nk] = d
                    if uk and uk not in _dept_by_user:
                        _dept_by_user[uk] = d

                # Enrich rows
                for r in rows:
                    # Comprador
                    resolved_comp = None
                    for v in _get_name_variants(r.get('comprador')):
                        if v.upper() in _dept_by_name:
                            resolved_comp = _dept_by_name[v.upper()]
                            break
                    if not resolved_comp and r.get('usuario'):
                        resolved_comp = _dept_by_user.get(r.get('usuario'))
                    fallback_comp = re.sub(r'^[0-9]+\s*-\s*', '', r.get('dept_oc') or '') if r.get('dept_oc') else ''
                    fallback_comp = fallback_comp or (re.sub(r'^[0-9]+\s*-\s*', '', r.get('area_oc') or '') if r.get('area_oc') else '')
                    r['depart_comprador'] = resolved_comp or fallback_comp or 'Não informado'

                    # Solicitante
                    resolved_solic = None
                    for v in _get_name_variants(r.get('solicitante')):
                        if v.upper() in _dept_by_name:
                            resolved_solic = _dept_by_name[v.upper()]
                            break
                    if not resolved_solic and r.get('solicitante') and ',' in r.get('solicitante', ''):
                        sp = [x.strip() for x in r['solicitante'].split(',', 1)]
                        if len(sp) == 2 and sp[0] and sp[1]:
                            first_part = sp[1].split()[0].upper()
                            last_part = sp[0].split()[-1].upper()
                            for nk, dval in _dept_by_name.items():
                                if first_part in nk and last_part in nk:
                                    resolved_solic = dval
                                    break
                    fallback_solic = r.get('depart_solicitante') or ''
                    if not fallback_solic or fallback_solic == '--':
                        fallback_solic = re.sub(r'^[0-9]+\s*-\s*', '', r.get('area_oc') or '') if r.get('area_oc') else ''
                    r['depart_solicitante'] = resolved_solic or fallback_solic or '--'

                    r.pop('dept_oc', None)
                    r.pop('area_oc', None)
                    r.pop('usuario', None)
            except Exception as e:
                _log.warning("EXCEPTIONS-TABLE [pos_fatura] dept-resolve warn: %s", e)
                for r in rows:
                    r['depart_comprador'] = re.sub(r'^[0-9]+\s*-\s*', '', r.get('dept_oc') or '') or 'Não informado'
                    if not r.get('depart_solicitante') or r.get('depart_solicitante') == '--':
                        r['depart_solicitante'] = re.sub(r'^[0-9]+\s*-\s*', '', r.get('area_oc') or '') if r.get('area_oc') else '' or '--'
                    r.pop('dept_oc', None)
                    r.pop('area_oc', None)
                    r.pop('usuario', None)

        sql = None  # signal to skip query_debug below
        if sql is not None:
            rows, err = query_debug(sql)
            if err:
                _log.error("EXCEPTIONS-TABLE [pos_fatura] ERROR: %s", err)
        return jsonify(rows)

    # ── OC abertas >90 dias (ignores date filters, queries ordens_compra) ──
    if exc_type == 'oc_90':
        oc90_parts, _ = _parse_filters(
            request.args,
            date_col=None,
            empresa_col='org_desc',
            grupo_col='grupo_compras_oc',
            fornecedor_col='nome_fornecedor',
            unidade_col='unidade',
            table_prefix='oc',
            is_notas=False
        )
        _oc90_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _oc90_comp:
            oc90_parts.append(f"COALESCE(NULLIF(oc.comprador, ''), oc.usuario_comprador, oc.nome_usuario) IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _oc90_comp])})")
        oc90_parts.append("oc.STATUS_FECHAMENTO = 'ABERTA'")
        oc90_parts.append("oc.dias_aberto > 90")
        oc90_where = ' AND '.join(oc90_parts)
        sql = f"""
        WITH oc90_agg AS (
            SELECT 'OC aberta >90 dias' AS tipo_excecao,
                   oc.NUMERO_OC AS "NUMERO_OC",
                   MAX(oc.nome_fornecedor) AS fornecedor,
                   MAX(COALESCE(NULLIF(oc.comprador, ''), oc.nome_usuario, 'Não informado')) AS comprador,
                   MAX(COALESCE(NULLIF(oc.usuario_comprador, ''), oc.usuario)) AS usuario,
                   MAX(oc.departamento_comprador) AS dept_oc,
                   MAX(COALESCE(oc.nome_requisitante, 'Não informado')) AS solicitante,
                   REGEXP_REPLACE(COALESCE(NULLIF(MAX(oc.departamento_requisitante), ''), NULLIF(MAX(oc.area), ''), '--'), '^[0-9]+\\s*-\\s*', '') AS depart_solicitante,
                   SUM(oc.valor_original_brl) AS net_spend,
                   MAX(oc.DATA_OC) AS data_oc,
                   MAX(oc.dias_aberto) AS dias_aberto,
                   MAX(oc.STATUS_FECHAMENTO) AS status
            FROM ordens_compra oc
            WHERE {oc90_where}
            GROUP BY oc.NUMERO_OC
        ),
        buyers_map AS (
            SELECT
                db.comprador,
                db.usuario,
                COALESCE(
                    CASE 
                        WHEN colab.area IS NOT NULL AND colab.nm_unidade IS NOT NULL AND colab.nm_unidade != '' 
                        THEN colab.area || ' - ' || colab.nm_unidade
                        ELSE colab.area 
                    END,
                    CASE 
                        WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                        THEN cf.area || ' - ' || cf.unidade
                        ELSE cf.area 
                    END
                ) AS dept_resolved
            FROM (SELECT DISTINCT comprador, usuario FROM oc90_agg) db
            LEFT JOIN LATERAL (
                SELECT area, nm_unidade
                FROM colaboradores
                WHERE (matricula IS NOT NULL AND matricula = db.usuario)
                   OR (id_colaborador IS NOT NULL AND id_colaborador = db.usuario)
                   OR (nome_completo IS NOT NULL AND UPPER(nome_completo) = UPPER(db.comprador))
                   OR (UPPER(nome_completo) LIKE UPPER(db.comprador) || '%')
                LIMIT 1
            ) colab ON true
            LEFT JOIN LATERAL (
                SELECT area, unidade
                FROM compradores_funcionais
                WHERE (usuario_oracle IS NOT NULL AND LOWER(usuario_oracle) = LOWER(db.usuario))
                   OR (comprador_funcional IS NOT NULL AND UPPER(comprador_funcional) = UPPER(db.comprador))
                LIMIT 1
            ) cf ON true
        )
        SELECT
            oc.tipo_excecao,
            oc."NUMERO_OC",
            oc.fornecedor,
            oc.comprador,
            REGEXP_REPLACE(
                COALESCE(bm.dept_resolved, NULLIF(oc.dept_oc, ''), 'Não informado'),
                '^[0-9]+\\s*-\\s*',
                ''
            ) AS depart_comprador,
            oc.solicitante,
            oc.depart_solicitante,
            oc.net_spend,
            oc.data_oc,
            oc.dias_aberto,
            oc.status
        FROM oc90_agg oc
        LEFT JOIN buyers_map bm 
          ON oc.comprador = bm.comprador 
         AND (oc.usuario = bm.usuario OR (oc.usuario IS NULL AND bm.usuario IS NULL))
        ORDER BY oc.dias_aberto DESC
        {limit_clause}
        """
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [oc_90] ERROR: %s", err)
        return jsonify(rows)

    # ── Acordos abertos >180 dias (tabela dedicada acordos_compra, status='OPEN', age from dt_criacao) ──
    if exc_type == 'blanket_old':
        bla_parts = [
            "oc.status = 'OPEN'",
            "oc.numero_acordo IS NOT NULL AND oc.numero_acordo != ''",
            "oc.dt_criacao IS NOT NULL AND oc.dt_criacao != ''",
            "(CURRENT_DATE - oc.dt_criacao::date) > 180",
            "COALESCE(oc.valor_liberado, 0) = 0",
        ]
        _bla_emp = [e.strip() for e in request.args.getlist('empresa') if e.strip()]
        if _bla_emp:
            bla_parts.append(f"oc.empresa IN ({','.join([chr(39)+_esc(e)+chr(39) for e in _bla_emp])})")
        _bla_frn = [f_.strip() for f_ in request.args.getlist('fornecedor') if f_.strip()]
        if _bla_frn:
            bla_parts.append(f"oc.fornecedor IN ({','.join([chr(39)+_esc(f_)+chr(39) for e in _bla_frn])})")
        _bla_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _bla_comp:
            _c_list = ','.join([chr(39)+_esc(v)+chr(39) for v in _bla_comp])
            bla_parts.append(f"(oc.comprador IN ({_c_list}) OR oc.usuario_comprador IN ({_c_list}))")
        bla_where = ' AND '.join(bla_parts)
        sql = f"""
        WITH bla_agg AS (
            SELECT 'Acordo de Compra >180 dias' AS tipo_excecao,
                   oc.numero_acordo AS "NUMERO_OC",
                   oc.fornecedor AS fornecedor,
                   COALESCE(NULLIF(oc.comprador, ''), oc.usuario_comprador, 'Não informado') AS comprador,
                   oc.usuario_comprador AS usuario,
                   oc.departamento_comprador AS dept_oc,
                   oc.valor_total AS net_spend,
                   COALESCE(oc.valor_liberado, 0) AS valor_liberado,
                   oc.dt_criacao AS data_oc,
                   (CURRENT_DATE - oc.dt_criacao::date) AS dias_aberto,
                   oc.dt_criacao AS acordo_dt_criacao,
                   oc.dt_fim AS acordo_data_final,
                   oc.status AS acordo_status,
                   oc.descricao AS acordo_descricao
            FROM acordos_compra oc
            WHERE {bla_where}
        ),
        buyers_map AS (
            SELECT
                db.comprador,
                db.usuario,
                COALESCE(
                    CASE 
                        WHEN colab.area IS NOT NULL AND colab.nm_unidade IS NOT NULL AND colab.nm_unidade != '' 
                        THEN colab.area || ' - ' || colab.nm_unidade
                        ELSE colab.area 
                    END,
                    CASE 
                        WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                        THEN cf.area || ' - ' || cf.unidade
                        ELSE cf.area 
                    END
                ) AS dept_resolved
            FROM (SELECT DISTINCT comprador, usuario FROM bla_agg) db
            LEFT JOIN LATERAL (
                SELECT area, nm_unidade
                FROM colaboradores
                WHERE (matricula IS NOT NULL AND matricula = db.usuario)
                   OR (id_colaborador IS NOT NULL AND id_colaborador = db.usuario)
                   OR (nome_completo IS NOT NULL AND UPPER(nome_completo) = UPPER(db.comprador))
                   OR (UPPER(nome_completo) LIKE UPPER(db.comprador) || '%')
                LIMIT 1
            ) colab ON true
            LEFT JOIN LATERAL (
                SELECT area, unidade
                FROM compradores_funcionais
                WHERE (usuario_oracle IS NOT NULL AND LOWER(usuario_oracle) = LOWER(db.usuario))
                   OR (comprador_funcional IS NOT NULL AND UPPER(comprador_funcional) = UPPER(db.comprador))
                LIMIT 1
            ) cf ON true
        )
        SELECT
            oc.tipo_excecao,
            oc."NUMERO_OC",
            oc.fornecedor,
            oc.comprador,
            REGEXP_REPLACE(
                COALESCE(bm.dept_resolved, NULLIF(oc.dept_oc, ''), 'Não informado'),
                '^[0-9]+\\s*-\\s*',
                ''
            ) AS depart_comprador,
            oc.net_spend,
            oc.valor_liberado,
            oc.data_oc,
            oc.dias_aberto,
            oc.acordo_dt_criacao,
            oc.acordo_data_final,
            oc.acordo_status,
            oc.acordo_descricao
        FROM bla_agg oc
        LEFT JOIN buyers_map bm 
          ON oc.comprador = bm.comprador 
         AND (oc.usuario = bm.usuario OR (oc.usuario IS NULL AND bm.usuario IS NULL))
        ORDER BY oc.dias_aberto DESC
        {limit_clause}
        """
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [blanket_old] ERROR: %s", err)
        return jsonify(rows)

    # ── OC Descentralizada >30k (source: ordens_compra, filter by DATA_OC) ──
    if exc_type == 'decentral':
        dec_oc_clauses, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', table_prefix='oc')
        dec_oc_base = [c for c in dec_oc_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
        _dec_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _dec_comp:
            dec_oc_base.append(f"COALESCE(NULLIF(oc.comprador, ''), oc.nome_usuario) IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _dec_comp])})")
        dec_oc_and = ('AND ' + ' AND '.join(dec_oc_base)) if dec_oc_base else ''
        sql = f"""
        WITH dec_agg AS (
            SELECT 'Descentralizada' AS tipo_excecao,
                   oc.numero_oc AS "NUMERO_OC",
                   MAX(COALESCE(NULLIF(oc.comprador, ''), oc.nome_usuario, 'Não informado')) AS comprador,
                   MAX(COALESCE(NULLIF(oc.usuario_comprador, ''), oc.usuario)) AS usuario,
                   MAX(oc.departamento_comprador) AS dept_oc,
                   MAX(COALESCE(oc.nome_requisitante, 'Não informado')) AS solicitante,
                   REGEXP_REPLACE(COALESCE(NULLIF(MAX(oc.departamento_requisitante), ''), NULLIF(MAX(oc.area), ''), '--'), '^[0-9]+\\s*-\\s*', '') AS depart_solicitante,
                   MAX(oc.nome_fornecedor) AS fornecedor,
                   MAX(oc.data_oc) AS data_oc,
                   SUM(oc.valor_original_brl)::float AS net_spend
            FROM ordens_compra oc
            WHERE oc.CENTRALIZADO = 'DESCENTRALIZADO'
              AND oc.numero_oc IS NOT NULL AND oc.numero_oc != ''
              AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
              AND (
                  UPPER(COALESCE(oc.status_aprovacao, '')) IN ('APPROVED', 'APROVADO')
                  OR (UPPER(COALESCE(oc.status_fechamento, '')) = 'CANCELADA' AND (COALESCE(oc.qtd_faturada, 0) > 0 OR COALESCE(oc.valor_utilizado_brl, 0) > 0))
              )
              AND UPPER(COALESCE(oc.status_fechamento, '')) NOT IN ('PENDENTE APROVACAO', 'PENDING APPROVAL', 'INCOMPLETA', 'REJEITADA', 'RETIRADA')
              {_EXCL_COMPRAS_DECENTRAL_OC}
              {dec_oc_and}
            GROUP BY oc.numero_oc
            HAVING SUM(oc.valor_original_brl) > 30000
        ),
        buyers_map AS (
            SELECT
                db.comprador,
                db.usuario,
                COALESCE(
                    CASE 
                        WHEN colab.area IS NOT NULL AND colab.nm_unidade IS NOT NULL AND colab.nm_unidade != '' 
                        THEN colab.area || ' - ' || colab.nm_unidade
                        ELSE colab.area 
                    END,
                    CASE 
                        WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                        THEN cf.area || ' - ' || cf.unidade
                        ELSE cf.area 
                    END
                ) AS dept_resolved
            FROM (SELECT DISTINCT comprador, usuario FROM dec_agg) db
            LEFT JOIN LATERAL (
                SELECT area, nm_unidade
                FROM colaboradores
                WHERE (matricula IS NOT NULL AND matricula = db.usuario)
                   OR (id_colaborador IS NOT NULL AND id_colaborador = db.usuario)
                   OR (nome_completo IS NOT NULL AND UPPER(nome_completo) = UPPER(db.comprador))
                   OR (UPPER(nome_completo) LIKE UPPER(db.comprador) || '%')
                LIMIT 1
            ) colab ON true
            LEFT JOIN LATERAL (
                SELECT area, unidade
                FROM compradores_funcionais
                WHERE (usuario_oracle IS NOT NULL AND LOWER(usuario_oracle) = LOWER(db.usuario))
                   OR (comprador_funcional IS NOT NULL AND UPPER(comprador_funcional) = UPPER(db.comprador))
                LIMIT 1
            ) cf ON true
        )
        SELECT
            dec.tipo_excecao,
            dec."NUMERO_OC",
            dec.comprador,
            REGEXP_REPLACE(
                COALESCE(bm.dept_resolved, NULLIF(dec.dept_oc, ''), 'Não informado'),
                '^[0-9]+\\s*-\\s*',
                ''
            ) AS depart_comprador,
            dec.solicitante,
            dec.depart_solicitante,
            dec.fornecedor,
            dec.data_oc,
            dec.net_spend
        FROM dec_agg dec
        LEFT JOIN buyers_map bm 
          ON dec.comprador = bm.comprador 
         AND (dec.usuario = bm.usuario OR (dec.usuario IS NULL AND bm.usuario IS NULL))
        ORDER BY dec.net_spend DESC
        {limit_clause}
        """
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [decentral] ERROR: %s", err)
        return jsonify(rows)

    # ── OCs Sucessivas / Fracionadas (source: ordens_compra, filter by DATA_OC) ──
    if exc_type == 'sucessivas':
        suc_clauses_gov, _ = _parse_filters(request.args, date_col='DATA_OC', empresa_col='org_desc', grupo_col='GRUPO_COMPRAS_OC', unidade_col='unidade', table_prefix='oc')
        suc_gov_filtered = [c for c in suc_clauses_gov if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
        _comp_vals = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _comp_vals:
            suc_gov_filtered.append(f"oc.nome_usuario IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _comp_vals])})")
        w_suc_gov = _where(suc_gov_filtered)

        sql = f"""
        WITH oc_items AS (
            SELECT
                oc.numero_oc AS "NUMERO_OC",
                COALESCE(NULLIF(TRIM(oc.numero_fornecedor), ''), '0') AS num_forn,
                COALESCE(NULLIF(TRIM(oc.nome_fornecedor), ''), 'Não informado') AS fornecedor,
                COALESCE(NULLIF(TRIM(oc.item_aquisicao), ''), NULLIF(TRIM(oc.descricao_item), '')) AS item,
                SUBSTRING(oc.data_oc, 1, 7) AS mes_oc,
                MAX(oc.data_oc) AS data_oc,
                MAX(COALESCE(NULLIF(oc.comprador, ''), oc.nome_usuario, 'Não informado')) AS comprador,
                MAX(COALESCE(NULLIF(oc.usuario_comprador, ''), oc.usuario)) AS usuario,
                MAX(oc.departamento_comprador) AS dept_oc,
                MAX(COALESCE(oc.nome_requisitante, 'Não informado')) AS solicitante,
                REGEXP_REPLACE(
                    COALESCE(NULLIF(MAX(oc.departamento_requisitante), ''), NULLIF(MAX(oc.area), ''), '--'),
                    '^[0-9]+\\s*-\\s*',
                    ''
                ) AS depart_solicitante,
                MAX(oc.area) AS area_oc,
                SUM(COALESCE(oc.valor_original_brl, 0))::float AS net_spend
            FROM ordens_compra oc
            {w_suc_gov}
              AND oc.numero_oc IS NOT NULL AND oc.numero_oc != ''
              AND oc.data_oc IS NOT NULL AND oc.data_oc != ''
              AND (
                  (oc.item_aquisicao IS NOT NULL AND TRIM(oc.item_aquisicao) NOT IN ('', '~NOVALUE~'))
                  OR (oc.descricao_item IS NOT NULL AND TRIM(oc.descricao_item) != '')
              )
              AND UPPER(COALESCE(oc.status_fechamento, '')) NOT IN ('INCOMPLETA', 'REJEITADA', 'RETIRADA')
            GROUP BY
                oc.numero_oc,
                COALESCE(NULLIF(TRIM(oc.numero_fornecedor), ''), '0'),
                COALESCE(NULLIF(TRIM(oc.nome_fornecedor), ''), 'Não informado'),
                COALESCE(NULLIF(TRIM(oc.item_aquisicao), ''), NULLIF(TRIM(oc.descricao_item), '')),
                SUBSTRING(oc.data_oc, 1, 7)
        ),
        oc_groups AS (
            SELECT
                'OCs sucessivas' AS tipo_excecao,
                *,
                COUNT(*) OVER (PARTITION BY num_forn, fornecedor, item, mes_oc) AS qtd_ocs_grupo,
                SUM(net_spend) OVER (PARTITION BY num_forn, fornecedor, item, mes_oc)::float AS valor_total_grupo,
                MIN(net_spend) OVER (PARTITION BY num_forn, fornecedor, item, mes_oc)::float AS min_val_grupo,
                MAX(net_spend) OVER (PARTITION BY num_forn, fornecedor, item, mes_oc)::float AS max_val_grupo,
                AVG(net_spend) OVER (PARTITION BY num_forn, fornecedor, item, mes_oc)::float AS avg_val_grupo
            FROM oc_items
        ),
        oc_filtered AS (
            SELECT
                tipo_excecao,
                "NUMERO_OC",
                num_forn,
                fornecedor,
                item,
                mes_oc,
                data_oc,
                comprador,
                usuario,
                dept_oc,
                solicitante,
                depart_solicitante,
                area_oc,
                net_spend,
                qtd_ocs_grupo,
                valor_total_grupo,
                CASE WHEN max_val_grupo = min_val_grupo THEN 1 ELSE 0 END AS is_identical,
                CASE 
                    WHEN avg_val_grupo > 0 AND ((max_val_grupo - min_val_grupo) / avg_val_grupo) <= 0.20 THEN 1 
                    ELSE 0 
                END AS is_similar,
                CASE 
                    WHEN avg_val_grupo > 0 THEN ROUND((((max_val_grupo - min_val_grupo) / avg_val_grupo) * 100)::numeric, 1)
                    ELSE 0 
                END AS diff_pct,
                DENSE_RANK() OVER (ORDER BY valor_total_grupo DESC, num_forn, item, mes_oc) AS grupo_rank
            FROM oc_groups
            WHERE qtd_ocs_grupo >= 2
        ),
        buyers_map AS (
            SELECT
                db.comprador,
                db.usuario,
                COALESCE(
                    CASE 
                        WHEN colab.area IS NOT NULL AND colab.nm_unidade IS NOT NULL AND colab.nm_unidade != '' 
                        THEN colab.area || ' - ' || colab.nm_unidade
                        ELSE colab.area 
                    END,
                    CASE 
                        WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                        THEN cf.area || ' - ' || cf.unidade
                        ELSE cf.area 
                    END
                ) AS dept_resolved
            FROM (SELECT DISTINCT comprador, usuario FROM oc_filtered) db
            LEFT JOIN LATERAL (
                SELECT area, nm_unidade
                FROM colaboradores
                WHERE (matricula IS NOT NULL AND matricula = db.usuario)
                   OR (id_colaborador IS NOT NULL AND id_colaborador = db.usuario)
                   OR (nome_completo IS NOT NULL AND UPPER(nome_completo) = UPPER(db.comprador))
                   OR (UPPER(nome_completo) LIKE UPPER(db.comprador) || '%')
                LIMIT 1
            ) colab ON true
            LEFT JOIN LATERAL (
                SELECT area, unidade
                FROM compradores_funcionais
                WHERE (usuario_oracle IS NOT NULL AND LOWER(usuario_oracle) = LOWER(db.usuario))
                   OR (comprador_funcional IS NOT NULL AND UPPER(comprador_funcional) = UPPER(db.comprador))
                LIMIT 1
            ) cf ON true
        )
        SELECT
            f.tipo_excecao,
            '#GRP-' || LPAD(f.grupo_rank::text, 3, '0') AS id_grupo,
            f.grupo_rank,
            f."NUMERO_OC",
            f.num_forn,
            f.fornecedor,
            f.item,
            f.mes_oc,
            f.data_oc,
            f.comprador,
            REGEXP_REPLACE(
                COALESCE(bm.dept_resolved, NULLIF(f.dept_oc, ''), 'Não informado'),
                '^[0-9]+\\s*-\\s*',
                ''
            ) AS depart_comprador,
            f.solicitante,
            f.depart_solicitante,
            f.net_spend,
            f.qtd_ocs_grupo,
            f.valor_total_grupo,
            f.is_identical,
            f.is_similar,
            f.diff_pct
        FROM oc_filtered f
        LEFT JOIN buyers_map bm 
          ON f.comprador = bm.comprador 
         AND (f.usuario = bm.usuario OR (f.usuario IS NULL AND bm.usuario IS NULL))
        ORDER BY f.grupo_rank ASC, f.data_oc ASC, f.net_spend DESC
        {limit_clause}
        """
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [sucessivas] ERROR: %s", err)
        return jsonify(rows)

    # ── Notas sem OCs (source: notas_ri, âncora DATA_PAGAMENTO — sem data de pagamento fica fora) ──
    if exc_type == 'sem_oc':
        sem_clauses, _ = _parse_filters(request.args, date_col='DATA_PAGAMENTO', table_prefix='nf')
        sem_base = [c for c in sem_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
        sem_w = _where(sem_base)
        and_kw = 'AND' if sem_base else 'WHERE'

        sql = f"""
        SELECT
            'Notas sem OCs' AS tipo_excecao,
            NULL AS "NUMERO_OC",
            nf.NOTA_FISCAL AS "NOTA_FISCAL",
            NULL AS comprador,
            NULL AS depart_comprador,
            NULL AS solicitante,
            NULL AS depart_solicitante,
            MAX(nf.NOME_FORNECEDOR) AS fornecedor,
            SUM(nf.VALOR_LIQUIDO_BRL) AS net_spend,
            SUM(nf.VALOR_NOTA_BRL) AS gross_spend,
            MAX(nf.DATA_PAGAMENTO) AS data_pagamento,
            MAX(nf.DATA_LANCAMENTO) AS data_fatura,
            NULL AS data_emissao_oc,
            NULL AS data_oc,
            NULL AS dias_pos_fatura
        FROM notas_ri nf
        {sem_w} {and_kw} nf.NUMERO_OC = 'Nota sem OC'
                  AND NULLIF(TRIM(nf.DATA_PAGAMENTO), '') IS NOT NULL
GROUP BY nf.NOTA_FISCAL
        ORDER BY net_spend DESC
        {limit_clause}
        """
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [sem_oc] ERROR: %s", err)
        return jsonify(rows)

    # ── OC Emergencial (source: notas_ri, filter by DATA_LANCAMENTO alinhado ao KPI) ──
    if exc_type == 'urgente':
        urg_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO', table_prefix='nf')
        urg_base = [c for c in urg_clauses if not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
        _urg_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
        if _urg_comp:
            _c_list = ','.join([chr(39)+_esc(v)+chr(39) for v in _urg_comp])
            urg_base.append(f"COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO) IN ({_c_list})")
        urg_w = _where(urg_base)
        and_kw = 'AND' if urg_base else 'WHERE'

        sql = f"""
        WITH urg_raw AS (
            SELECT
                'OC emergencial' AS tipo_excecao,
                nf.NUMERO_OC AS "NUMERO_OC",
                MAX(COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO, 'Não informado')) AS comprador,
                MAX(COALESCE(NULLIF(oc.usuario_comprador, ''), oc.usuario)) AS usuario,
                MAX(oc.DEPARTAMENTO_COMPRADOR) AS dept_oc,
                MAX(COALESCE(oc.NOME_REQUISITANTE, 'Não informado')) AS solicitante,
                REGEXP_REPLACE(
                    COALESCE(MAX(NULLIF(oc.DEPARTAMENTO_REQUISITANTE, '')), MAX(NULLIF(oc.area, '')), '--'),
                    '^[0-9]+\\s*-\\s*',
                    ''
                ) AS depart_solicitante,
                MAX(nf.NOME_FORNECEDOR) AS fornecedor,
                SUM(nf.VALOR_LIQUIDO_BRL)::float AS net_spend,
                MAX(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO)) AS data_fatura,
                MAX(COALESCE(oc.DATA_OC, oc.DT_APROVACAO)) AS data_emissao_oc,
                MAX(oc.DT_APROVACAO) AS data_oc
            FROM notas_ri nf
            LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
            {urg_w} {and_kw} nf.URGENTE = 'SIM'
              AND nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != '' AND nf.NUMERO_OC != 'Nota sem OC'
            GROUP BY nf.NUMERO_OC
        ),
        buyers_map AS (
            SELECT
                db.comprador,
                db.usuario,
                COALESCE(
                    CASE 
                        WHEN colab.area IS NOT NULL AND colab.nm_unidade IS NOT NULL AND colab.nm_unidade != '' 
                        THEN colab.area || ' - ' || colab.nm_unidade
                        ELSE colab.area 
                    END,
                    CASE 
                        WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                        THEN cf.area || ' - ' || cf.unidade
                        ELSE cf.area 
                    END
                ) AS dept_resolved
            FROM (SELECT DISTINCT comprador, usuario FROM urg_raw) db
            LEFT JOIN LATERAL (
                SELECT area, nm_unidade
                FROM colaboradores
                WHERE (matricula IS NOT NULL AND matricula = db.usuario)
                   OR (id_colaborador IS NOT NULL AND id_colaborador = db.usuario)
                   OR (nome_completo IS NOT NULL AND UPPER(nome_completo) = UPPER(db.comprador))
                   OR (UPPER(nome_completo) LIKE UPPER(db.comprador) || '%')
                LIMIT 1
            ) colab ON true
            LEFT JOIN LATERAL (
                SELECT area, unidade
                FROM compradores_funcionais
                WHERE (usuario_oracle IS NOT NULL AND LOWER(usuario_oracle) = LOWER(db.usuario))
                   OR (comprador_funcional IS NOT NULL AND UPPER(comprador_funcional) = UPPER(db.comprador))
                LIMIT 1
            ) cf ON true
        )
        SELECT
            ur.tipo_excecao,
            ur."NUMERO_OC",
            ur.comprador,
            REGEXP_REPLACE(
                COALESCE(bm.dept_resolved, NULLIF(ur.dept_oc, ''), 'Não informado'),
                '^[0-9]+\\s*-\\s*',
                ''
            ) AS depart_comprador,
            ur.solicitante,
            ur.depart_solicitante,
            ur.fornecedor,
            ur.net_spend,
            ur.data_fatura,
            ur.data_emissao_oc,
            ur.data_oc
        FROM urg_raw ur
        LEFT JOIN buyers_map bm 
          ON ur.comprador = bm.comprador 
         AND (ur.usuario = bm.usuario OR (ur.usuario IS NULL AND bm.usuario IS NULL))
        ORDER BY ur.net_spend DESC
        {limit_clause}
        """
        rows, err = query_debug(sql)
        if err:
            _log.error("EXCEPTIONS-TABLE [urgente] ERROR: %s", err)
        return jsonify(rows)


    # Demais tipos: query por linha individual
    # Build date + entity filters: LANÇAMENTO para sem_oc/decentral, PAGAMENTO para pos_fatura
    exc_lancto_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO', table_prefix='nf')
    exc_pgto_clauses, _ = _parse_filters(request.args, date_col='DATA_PAGAMENTO', table_prefix='nf')

    lancto_date = [c for c in exc_lancto_clauses if 'DATA_LANCAMENTO' in c]
    pgto_date = [c for c in exc_pgto_clauses if 'DATA_PAGAMENTO' in c]
    exc_base = [c for c in exc_lancto_clauses if 'DATA_LANCAMENTO' not in c and not ('CHAVE_OC_LINHA IN' in c and 'nome_usuario' in c)]
    exc_and = ('AND ' + ' AND '.join(exc_base)) if exc_base else ''
    _exc_comp = [v.strip() for v in request.args.getlist('comprador') if v.strip()]
    exc_comp_and = f"AND oc.NOME_USUARIO IN ({','.join([chr(39)+_esc(v)+chr(39) for v in _exc_comp])})" if _exc_comp else ''

    lancto_d_and = (' AND ' + ' AND '.join(lancto_date)) if lancto_date else ''
    pgto_d_and = (' AND ' + ' AND '.join(pgto_date)) if pgto_date else ''

    # Date and entity filters for type=all

    # Build decentral CTE for type=all
    oc_pos_cte = f"""WITH oc_desc_30k AS (
        SELECT oc.NUMERO_OC
        FROM ordens_compra oc
        WHERE oc.CENTRALIZADO = 'DESCENTRALIZADO' AND oc.NUMERO_OC IS NOT NULL AND oc.NUMERO_OC != ''
          AND (oc.numero_acordo IS NULL OR TRIM(oc.numero_acordo) = '')
          AND (
              UPPER(COALESCE(oc.status_aprovacao, '')) IN ('APPROVED', 'APROVADO')
              OR (UPPER(COALESCE(oc.status_fechamento, '')) = 'CANCELADA' AND (COALESCE(oc.qtd_faturada, 0) > 0 OR COALESCE(oc.valor_utilizado_brl, 0) > 0))
          )
          AND UPPER(COALESCE(oc.status_fechamento, '')) NOT IN ('PENDENTE APROVACAO', 'PENDING APPROVAL', 'INCOMPLETA', 'REJEITADA', 'RETIRADA')
          {_EXCL_COMPRAS_DECENTRAL_OC}
        GROUP BY oc.NUMERO_OC
        HAVING SUM(oc.valor_original_brl) > 30000
    )"""

    if exc_type == 'urgente':
        type_filter = "AND nf.URGENTE = 'SIM'"
        tipo_expr = "'OC emergencial'"
    else:
        # type == 'all'
        type_filter = f"AND ((nf.NUMERO_OC != 'Nota sem OC' AND oc.DT_APROVACAO ~ '^[0-9]{{{{4}}}}-[0-9]{{{{2}}}}-[0-9]{{{{2}}}}' AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{{{4}}}}-[0-9]{{{{2}}}}-[0-9]{{{{2}}}}' AND SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date < SUBSTRING(oc.DT_APROVACAO, 1, 10)::date AND COALESCE(nf.IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'{pgto_d_and}) OR (nf.URGENTE = 'SIM'{lancto_d_and}) OR (nf.NUMERO_OC = 'Nota sem OC' AND NULLIF(TRIM(nf.DATA_PAGAMENTO), '') IS NOT NULL{pgto_d_and}) OR (nf.CENTRALIZADO = 'DESCENTRALIZADO' AND nf.NUMERO_OC IN (SELECT NUMERO_OC FROM oc_desc_30k){lancto_d_and}))"
        tipo_expr = """
        CASE
            WHEN nf.NUMERO_OC != 'Nota sem OC'
                 AND oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                 AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                 AND SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date < SUBSTRING(oc.DT_APROVACAO, 1, 10)::date
                 AND COALESCE(nf.IS_FORNECEDOR_ESPECIAL, 'NÃO ESPECIAL') = 'NÃO ESPECIAL'
            THEN 'OCs pós-fatura'
            WHEN nf.URGENTE = 'SIM' THEN 'OC emergencial'
            WHEN nf.NUMERO_OC = 'Nota sem OC' THEN 'Notas sem OCs'
            WHEN nf.CENTRALIZADO = 'DESCENTRALIZADO' THEN 'Descentralizada'
            ELSE 'Outro'
        END"""

    sql = f"""
    {oc_pos_cte},
    all_raw AS (
        SELECT
            {tipo_expr} AS tipo_excecao,
            CASE
                WHEN nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != '' AND nf.NUMERO_OC != 'Nota sem OC'
                THEN nf.NUMERO_OC
                ELSE oc.NUMERO_OC
            END AS "NUMERO_OC",
            nf.NOTA_FISCAL AS "NOTA_FISCAL",
            COALESCE(NULLIF(oc.comprador, ''), oc.NOME_USUARIO, 'Não informado') AS comprador,
            COALESCE(NULLIF(oc.usuario_comprador, ''), oc.usuario) AS usuario,
            oc.DEPARTAMENTO_COMPRADOR AS dept_oc,
            COALESCE(oc.NOME_REQUISITANTE, 'Não informado') AS solicitante,
            REGEXP_REPLACE(
                COALESCE(NULLIF(oc.DEPARTAMENTO_REQUISITANTE, ''), NULLIF(oc.area, ''), '--'),
                '^[0-9]+\\s*-\\s*',
                ''
            ) AS depart_solicitante,
            nf.NOME_FORNECEDOR AS fornecedor,
            nf.VALOR_LIQUIDO_BRL AS net_spend,
            COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) AS data_fatura,
            oc.DATA_OC AS data_criacao_oc,
            oc.DATA_OC AS data_emissao_oc,
            oc.DT_APROVACAO AS data_oc,
            oc.DT_APROVACAO AS data_aprov_oc,
            CASE
                WHEN oc.DT_APROVACAO ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}' 
                     AND COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                THEN (SUBSTRING(oc.DT_APROVACAO, 1, 10)::date 
                      - SUBSTRING(COALESCE(nf.DT_NOTA, nf.DATA_LANCAMENTO), 1, 10)::date)
                ELSE NULL
            END AS dias_pos_fatura
        FROM notas_ri nf
        LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA
        WHERE 1=1 {type_filter} {exc_and} {exc_comp_and}
    ),
    buyers_map AS (
        SELECT
            db.comprador,
            db.usuario,
            COALESCE(
                CASE 
                    WHEN colab.area IS NOT NULL AND colab.nm_unidade IS NOT NULL AND colab.nm_unidade != '' 
                    THEN colab.area || ' - ' || colab.nm_unidade
                    ELSE colab.area 
                END,
                CASE 
                    WHEN cf.area IS NOT NULL AND cf.unidade IS NOT NULL AND cf.unidade != '' 
                    THEN cf.area || ' - ' || cf.unidade
                    ELSE cf.area 
                END
            ) AS dept_resolved
        FROM (SELECT DISTINCT comprador, usuario FROM all_raw) db
        LEFT JOIN LATERAL (
            SELECT area, nm_unidade
            FROM colaboradores
            WHERE (matricula IS NOT NULL AND matricula = db.usuario)
               OR (id_colaborador IS NOT NULL AND id_colaborador = db.usuario)
               OR (nome_completo IS NOT NULL AND UPPER(nome_completo) = UPPER(db.comprador))
               OR (UPPER(nome_completo) LIKE UPPER(db.comprador) || '%')
            LIMIT 1
        ) colab ON true
        LEFT JOIN LATERAL (
            SELECT area, unidade
            FROM compradores_funcionais
            WHERE (usuario_oracle IS NOT NULL AND LOWER(usuario_oracle) = LOWER(db.usuario))
               OR (comprador_funcional IS NOT NULL AND UPPER(comprador_funcional) = UPPER(db.comprador))
            LIMIT 1
        ) cf ON true
    )
    SELECT
        ar.tipo_excecao,
        ar."NUMERO_OC",
        ar."NOTA_FISCAL",
        ar.comprador,
        REGEXP_REPLACE(
            COALESCE(bm.dept_resolved, NULLIF(ar.dept_oc, ''), 'Não informado'),
            '^[0-9]+\\s*-\\s*',
            ''
        ) AS depart_comprador,
        ar.solicitante,
        ar.depart_solicitante,
        ar.fornecedor,
        ar.net_spend,
        ar.data_fatura,
        ar.data_emissao_oc,
        ar.data_oc,
        ar.dias_pos_fatura
    FROM all_raw ar
    LEFT JOIN buyers_map bm 
      ON ar.comprador = bm.comprador 
     AND (ar.usuario = bm.usuario OR (ar.usuario IS NULL AND bm.usuario IS NULL))
    ORDER BY ar.net_spend DESC
    {limit_clause}
    """
    rows, err = query_debug(sql)
    if err:
        _log.error("EXCEPTIONS-TABLE [%s] ERROR: %s", exc_type, err)
    return jsonify(rows)


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
        'notas': 'notas_ri nf LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA',
        'ordens': 'notas_ri nf LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA',
        'notas_ordens': 'notas_ri nf LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA',
        'requisicoes': 'requisicoes',
    }
    table = table_map.get(source, table_map['notas'])

    # Build where (filters + search)
    where_parts = []
    # Apply standard filters with correct column names per source
    if source in ('notas', 'ordens', 'notas_ordens'):
        filter_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO', empresa_col='EMPRESA', grupo_col='GRUPO_COMPRAS', table_prefix='nf')
        # OC Pós-fatura filter
        oc_pf = [v.strip() for v in request.args.getlist('oc_pos_fatura') if v.strip()]
        if oc_pf and len(oc_pf) == 1:
            filter_clauses.append(f"nf.OC_POS_FATURA = '{_esc(oc_pf[0])}'")
        # Tipo NF filter (com_oc / sem_oc)
        oc_type = request.args.getlist('oc_type')
        if oc_type and len(oc_type) == 1:
            if oc_type[0] == 'com_oc':
                filter_clauses.append("nf.NUMERO_OC != 'Nota sem OC' AND nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != ''")
            elif oc_type[0] == 'sem_oc':
                filter_clauses.append("nf.NUMERO_OC = 'Nota sem OC'")
    else:
        filter_clauses, _ = _parse_filters(request.args, date_col='DT_CRIACAO', empresa_col='EMPRESA', grupo_col='GRUPO_COMPRAS')
    where_parts.extend(filter_clauses)

    if search:
        s_esc = _esc(search)
        if source in ('notas', 'ordens', 'notas_ordens'):
            where_parts.append(
                f"(nf.NOTA_FISCAL ILIKE '%{s_esc}%' "
                f"OR nf.NOME_FORNECEDOR ILIKE '%{s_esc}%' "
                f"OR COALESCE(nf.DS_ITEM, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(nf.NUMERO_OC, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(nf.CODIGO_ITEM, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(nf.NUMERO_RI, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(oc.numero_oc, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(oc.nome_usuario, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(oc.numero_acordo, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(oc.item_aquisicao, '') ILIKE '%{s_esc}%')"
            )
        elif source == 'requisicoes':
            where_parts.append(
                f"(COALESCE(REQUISICAO::text, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(REQUISITANTE, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(DESCRICAO_REQ, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(NUMERO_OC::text, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(COMPRADOR_SUGERIDO, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(FORNECEDOR, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(STATUS, '') ILIKE '%{s_esc}%')"
            )

    w = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    if source in ('notas', 'ordens', 'notas_ordens'):
        cols = """
            nf.NOTA_FISCAL AS "NOTA_FISCAL",
            COALESCE(nf.NUMERO_OC, oc.numero_oc) AS "NUMERO_OC",
            COALESCE(nf.CHAVE_OC_LINHA, oc.linha_oc::text) AS "LINHA_OC",
            nf.OC_POS_FATURA AS "OC_POS_FATURA",
            nf.CNPJ_BIMBO AS "CNPJ_BIMBO",
            COALESCE(nf.NOME_FORNECEDOR, oc.nome_fornecedor) AS "FORNECEDOR",
            COALESCE(nf.DS_ITEM, oc.descricao_item) AS "DS_ITEM",
            nf.CODIGO_ITEM AS "CODIGO_ITEM",
            COALESCE(nf.MACRO_CATEGORIA, oc.categoria_oc, 'Indiretos') AS "MACRO_CATEGORIA",
            COALESCE(nf.CATEGORIA_ITEM, oc.categoria_item) AS "CATEGORIA_ITEM",
            COALESCE(nf.EMPRESA, oc.org_desc) AS "EMPRESA",
            COALESCE(nf.PLANTA, oc.unidade) AS "UNIDADE",
            COALESCE(nf.CENTRALIZADO, oc.centralizado) AS "CENTRALIZADO",
            COALESCE(nf.GRUPO_COMPRAS, oc.grupo_compras_oc) AS "GRUPO_COMPRAS",
            nf.STATUS_PAGAMENTO AS "STATUS_PAGAMENTO",
            nf.NUMERO_RI AS "NUMERO_RI",
            nf.CENTRO_CUSTO AS "CENTRO_CUSTO",
            nf.CONTA_CONTABIL AS "CONTA_CONTABIL",
            nf.TIPO_NF AS "TIPO_NF",
            nf.TIPO_LINHA AS "TIPO_LINHA",
            nf.DT_NOTA AS "DT_NOTA",
            nf.DATA_LANCAMENTO AS "DATA_LANCAMENTO",
            nf.DATA_VENCIMENTO AS "DATA_VENCIMENTO",
            nf.DATA_PAGAMENTO AS "DATA_PAGAMENTO",
            nf.VALOR_LIQUIDO_BRL AS "VALOR_LIQUIDO_BRL",
            nf.VALOR_NOTA_BRL AS "VALOR_NOTA_BRL",
            nf.SAVING_TOTAL AS "SAVING_TOTAL",
            nf.PRECO AS "PRECO_BRL",
            nf.QUANTIDADE AS "QUANTIDADE",
            nf.COND_PGTO_AP AS "COND_PGTO_AP",
            COALESCE(nf.IS_FORNECEDOR_ESPECIAL, oc.is_fornecedor_especial) AS "IS_FORNECEDOR_ESPECIAL",
            COALESCE(nf.IS_FORNECEDOR_NAO_NEGOCIAVEL, oc.is_fornecedor_nao_negociavel) AS "IS_FORNECEDOR_NAO_NEGOCIAVEL",
            __SEM_OC_EXPR__ AS "IS_FORNECEDOR_SEM_OC",
            nf.TIPO_VENDOR AS "TIPO_VENDOR",
            nf.URGENTE AS "URGENTE",
            COALESCE(NULLIF(oc.comprador, ''), oc.nome_usuario) AS "COMPRADOR",
            oc.area AS "DEPARTAMENTO_COMPRADOR",
            oc.status_fechamento AS "STATUS_FECHAMENTO",
            oc.data_oc AS "DATA_OC",
            oc.dt_aprovacao AS "DT_APROVACAO",
            oc.dt_promessa AS "DT_PROMESSA",
            oc.dt_fechamento AS "DT_FECHAMENTO",
            oc.valor_original_brl AS "VALOR_ORIGINAL",
            oc.valor_utilizado_brl AS "VALOR_UTILIZADO",
            oc.qtd_faturada AS "QTD_FATURADA",
            oc.moeda AS "MOEDA",
            oc.aprovador AS "APROVADOR",
            oc.requisicao AS "REQUISICAO",
            oc.nome_requisitante AS "NOME_REQUISITANTE",
            oc.area AS "DEPARTAMENTO_REQUISITANTE",
            oc.tipo AS "TIPO",
            oc.descricao AS "DESCRICAO",
            oc.item_aquisicao AS "ITEM_AQUISICAO",
            oc.oc_atrasada AS "OC_ATRASADA",
            oc.dias_atraso_oc AS "DIAS_ATRASO_OC",
            oc.dias_aberto AS "DIAS_ABERTO",
            oc.numero_acordo AS "NUMERO_ACORDO",
            oc.acordo_status AS "ACORDO_STATUS",
            oc.acordo_dt_criacao AS "ACORDO_DT_CRIACAO",
            oc.acordo_data_inicial AS "ACORDO_DATA_INICIAL",
            oc.acordo_data_final AS "ACORDO_DATA_FINAL",
            oc.acordo_valor_total AS "ACORDO_VALOR_TOTAL",
            oc.acordo_valor_liberado AS "ACORDO_VALOR_LIBERADO",
            oc.acordo_descricao AS "ACORDO_DESCRICAO",
            oc.acordo_condicao_frete AS "ACORDO_CONDICAO_FRETE",
            oc.acordo_condicao_pgto AS "ACORDO_CONDICAO_PGTO"
        """
        tie_breaker = "nf.DATA_LANCAMENTO DESC, nf.NUMERO_RI DESC, nf.CHAVE_OC_LINHA ASC, nf.NOTA_FISCAL ASC"
        order = f'ORDER BY "{sort_col}" {sort_dir} NULLS LAST, {tie_breaker}' if sort_col else f'ORDER BY {tie_breaker}'
    else:
        cols = """
            REQUISICAO AS "REQUISICAO",
            EMPRESA AS "EMPRESA",
            REQUISITANTE AS "REQUISITANTE",
            departamento_requisitante AS "DEPARTAMENTO_REQUISITANTE",
            DESCRICAO_REQ AS "DESCRICAO_REQ",
            NUMERO_OC AS "NUMERO_OC",
            DT_CRIACAO AS "DT_CRIACAO",
            DT_APROVACAO AS "DT_APROVACAO",
            VALOR_REQUISICAO AS "VALOR_REQUISICAO",
            STATUS AS "STATUS",
            STATUS_ORDEM AS "STATUS_ORDEM",
            user_requisicao AS "USER_REQUISICAO",
            email_requisitante AS "EMAIL_REQUISITANTE",
            user_aprovador AS "USER_APROVADOR",
            NULLIF(TRIM(comprador_sugerido), '') AS "COMPRADOR_SUGERIDO",
            NULLIF(TRIM(departamento_comprador), '') AS "DEPARTAMENTO_COMPRADOR"
        """
        tie_breaker = 'DT_CRIACAO DESC, REQUISICAO DESC'
        order = f'ORDER BY "{sort_col}" {sort_dir} NULLS LAST, {tie_breaker}' if sort_col else f'ORDER BY {tie_breaker}'

    # Distinct date values for Excel-style date header filter tree
    dv_col = request.args.get('date_values_col', '').strip().upper()
    if dv_col:
        if source in ('notas', 'ordens', 'notas_ordens'):
            dv_map = {
                'DT_NOTA': 'nf.DT_NOTA', 'DATA_LANCAMENTO': 'nf.DATA_LANCAMENTO',
                'DATA_VENCIMENTO': 'nf.DATA_VENCIMENTO', 'DATA_PAGAMENTO': 'nf.DATA_PAGAMENTO',
                'DATA_OC': 'oc.data_oc', 'DT_APROVACAO': 'oc.dt_aprovacao',
                'DT_PROMESSA': 'oc.dt_promessa', 'DT_FECHAMENTO': 'oc.dt_fechamento',
                'ACORDO_DT_CRIACAO': 'oc.acordo_dt_criacao',
                'ACORDO_DATA_INICIAL': 'oc.acordo_data_inicial',
                'ACORDO_DATA_FINAL': 'oc.acordo_data_final',
            }
        else:
            dv_map = {'DT_CRIACAO': 'DT_CRIACAO', 'DT_APROVACAO': 'DT_APROVACAO'}
        dv_sql = dv_map.get(dv_col)
        if not dv_sql:
            return jsonify({'error': 'Coluna de data inválida'}), 400
        dexpr = f"SUBSTRING(NULLIF(TRIM(({dv_sql})::text), ''), 1, 10)"
        dv_rows = query(f"SELECT {dexpr} AS d, COUNT(*) AS n FROM {table} {w} GROUP BY 1 ORDER BY 1 DESC NULLS LAST")
        values = [r['d'] for r in dv_rows if r.get('d')]
        has_empty = any(not r.get('d') for r in dv_rows)
        return jsonify({'col': dv_col, 'values': values, 'has_empty': has_empty})

    if '__SEM_OC_EXPR__' in cols:
        cols = cols.replace('__SEM_OC_EXPR__', _sem_oc_flag_sql())
    sql = f"SELECT {cols} FROM {table} {w} {order} LIMIT {per_page} OFFSET {offset}"
    count_sql = f"SELECT COUNT(*) AS total FROM {table} {w}"

    _log.info("[REPORTS] source=%s | where_parts=%s | SQL_WHERE=%s", source, where_parts, w)
    rows, rows_err = query_debug(sql) or ([], 'sem resposta do banco')
    if rows_err:
        # Não devolver total com 0 linhas: a tela mostraria "Nenhum registro" em vez de erro
        _mark_query_failure()
        _log.error("[REPORTS] rows query failed: %s", rows_err[:300])
        return jsonify({'error': 'Falha ao consultar os dados do relatório', 'rows': [], 'total': 0}), 500
    total = query(count_sql)
    return jsonify({
        'rows': rows,
        'total': total[0]['total'] if total else 0,
        'page': page,
        'per_page': per_page,
        'source': source
    })


@app.route('/api/export/table-xlsx', methods=['POST'])
def export_table_xlsx():
    """Gera XLSX formatado como Tabela nativa 'Clara 1' a partir de linhas já carregadas no front.
    Payload: {filename, sheet, columns:[{label, type}], rows:[[...], ...]}
    type: 'text' | 'currency' | 'integer' | 'date'
    """
    if Workbook is None:
        return jsonify({'error': 'openpyxl indisponível'}), 500
    payload = request.get_json(silent=True) or {}
    columns = payload.get('columns') or []
    rows = payload.get('rows') or []
    if not columns:
        return jsonify({'error': 'Sem colunas'}), 400
    sheet = str(payload.get('sheet') or 'Dados')[:31]
    filename = str(payload.get('filename') or 'export').replace('"', '')

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    headers = [str(c.get('label', '')) for c in columns]
    ws.append(headers)
    types = [c.get('type', 'text') for c in columns]

    for r in rows:
        out = []
        for idx, val in enumerate(r[:len(types)]):
            ct = types[idx]
            if val is None or val == '':
                out.append(None)
            elif ct == 'currency':
                try:
                    out.append(float(val))
                except (TypeError, ValueError):
                    out.append(val)
            elif ct == 'integer':
                try:
                    out.append(int(round(float(val))))
                except (TypeError, ValueError):
                    out.append(val)
            elif ct == 'date':
                s = str(val).strip()
                out.append(f'{s[8:10]}/{s[5:7]}/{s[0:4]}' if len(s) >= 10 and s[4] == '-' and s[7] == '-' else s)
            else:
                out.append(str(val))
        ws.append(out)

    n = len(rows)
    last_col = get_column_letter(len(headers))
    if n > 0:
        tab = Table(displayName=f"Tabela_{uuid.uuid4().hex[:8]}", ref=f"A1:{last_col}{n + 1}")
        tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showFirstColumn=False,
                                            showLastColumn=False, showRowStripes=True, showColumnStripes=False)
        ws.add_table(tab)
        for idx, ct in enumerate(types, start=1):
            if ct == 'currency':
                cl = get_column_letter(idx)
                for ri in range(2, n + 2):
                    ws[f'{cl}{ri}'].number_format = 'R$ #,##0.00;[Red]-R$ #,##0.00'
    for idx, h in enumerate(headers, start=1):
        cl = get_column_letter(idx)
        max_len = len(h)
        for ri in range(2, min(n + 2, 202)):
            v = ws[f'{cl}{ri}'].value
            if v is not None and len(str(v)) > max_len:
                max_len = len(str(v))
        ws.column_dimensions[cl].width = min(max(max_len + 3, 10), 45)
    ws.freeze_panes = 'A2'

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        buf.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
        }
    )


@app.route('/api/reports/export')
def reports_export():
    """Streamlined report export (CSV formatted for Brazilian Excel with UTF-8 BOM and ';' delimiter).
    Streams natively from database cursor directly to the client browser without freezing memory.
    """
    source = request.args.get('source', 'notas')
    search = request.args.get('search', '').strip()
    sort_col = request.args.get('sort', '')
    sort_dir = request.args.get('dir', 'DESC')
    requested_cols_raw = request.args.get('cols', '').strip()

    table_map = {
        'notas': 'notas_ri nf LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA',
        'ordens': 'notas_ri nf LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA',
        'notas_ordens': 'notas_ri nf LEFT JOIN ordens_compra oc ON nf.CHAVE_OC_LINHA = oc.CHAVE_OC_LINHA',
        'requisicoes': 'requisicoes',
    }
    table = table_map.get(source, table_map['notas'])

    where_parts = []
    if source in ('notas', 'ordens', 'notas_ordens'):
        filter_clauses, _ = _parse_filters(request.args, date_col='DATA_LANCAMENTO', empresa_col='EMPRESA', grupo_col='GRUPO_COMPRAS', table_prefix='nf')
        oc_pf = [v.strip() for v in request.args.getlist('oc_pos_fatura') if v.strip()]
        if oc_pf and len(oc_pf) == 1:
            filter_clauses.append(f"nf.OC_POS_FATURA = '{_esc(oc_pf[0])}'")
        oc_type = request.args.getlist('oc_type')
        if oc_type and len(oc_type) == 1:
            if oc_type[0] == 'com_oc':
                filter_clauses.append("nf.NUMERO_OC != 'Nota sem OC' AND nf.NUMERO_OC IS NOT NULL AND nf.NUMERO_OC != ''")
            elif oc_type[0] == 'sem_oc':
                filter_clauses.append("nf.NUMERO_OC = 'Nota sem OC'")
    else:
        filter_clauses, _ = _parse_filters(request.args, date_col='DT_CRIACAO', empresa_col='EMPRESA', grupo_col='GRUPO_COMPRAS')
    where_parts.extend(filter_clauses)

    if search:
        s_esc = _esc(search)
        if source in ('notas', 'ordens', 'notas_ordens'):
            where_parts.append(
                f"(nf.NOTA_FISCAL ILIKE '%{s_esc}%' "
                f"OR nf.NOME_FORNECEDOR ILIKE '%{s_esc}%' "
                f"OR COALESCE(nf.DS_ITEM, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(nf.NUMERO_OC, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(nf.CODIGO_ITEM, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(nf.NUMERO_RI, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(oc.numero_oc, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(oc.nome_usuario, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(oc.numero_acordo, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(oc.item_aquisicao, '') ILIKE '%{s_esc}%')"
            )
        elif source == 'requisicoes':
            where_parts.append(
                f"(COALESCE(REQUISICAO::text, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(REQUISITANTE, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(DESCRICAO_REQ, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(NUMERO_OC::text, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(COMPRADOR_SUGERIDO, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(FORNECEDOR, '') ILIKE '%{s_esc}%' "
                f"OR COALESCE(STATUS, '') ILIKE '%{s_esc}%')"
            )

    w = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    export_definitions = {
        'notas': [
            # Nativas NF
            ('nf.NOTA_FISCAL', 'Nota Fiscal', 'text', 'NOTA_FISCAL'),
            ('COALESCE(nf.NUMERO_OC, oc.numero_oc)', 'Nº OC', 'text', 'NUMERO_OC'),
            ('COALESCE(nf.CHAVE_OC_LINHA, oc.linha_oc::text)', 'Linha OC', 'text', 'LINHA_OC'),
            ('nf.OC_POS_FATURA', 'OC Pós-fatura', 'text', 'OC_POS_FATURA'),
            ('nf.CNPJ_BIMBO', 'CNPJ Bimbo', 'text', 'CNPJ_BIMBO'),
            ('COALESCE(nf.NOME_FORNECEDOR, oc.nome_fornecedor)', 'Fornecedor', 'text', 'FORNECEDOR'),
            ('COALESCE(nf.DS_ITEM, oc.descricao_item)', 'Ds Item', 'text', 'DS_ITEM'),
            ('nf.CODIGO_ITEM', 'Código Item', 'text', 'CODIGO_ITEM'),
            ("COALESCE(nf.MACRO_CATEGORIA, oc.categoria_oc, 'Indiretos')", 'Categoria', 'text', 'MACRO_CATEGORIA'),
            ('COALESCE(nf.CATEGORIA_ITEM, oc.categoria_item)', 'Sub-categoria', 'text', 'CATEGORIA_ITEM'),
            ('COALESCE(nf.EMPRESA, oc.org_desc)', 'Empresa', 'text', 'EMPRESA'),
            ('COALESCE(nf.PLANTA, oc.unidade)', 'Unidade', 'text', 'UNIDADE'),
            ('COALESCE(nf.CENTRALIZADO, oc.centralizado)', 'Centralizado', 'text', 'CENTRALIZADO'),
            ('COALESCE(nf.GRUPO_COMPRAS, oc.grupo_compras_oc)', 'Grupo Compras', 'text', 'GRUPO_COMPRAS'),
            ('nf.STATUS_PAGAMENTO', 'Status Pagamento', 'text', 'STATUS_PAGAMENTO'),
            ('nf.NUMERO_RI', 'Número RI', 'text', 'NUMERO_RI'),
            ('nf.CENTRO_CUSTO', 'Centro de Custo', 'text', 'CENTRO_CUSTO'),
            ('nf.CONTA_CONTABIL', 'Conta Contábil', 'text', 'CONTA_CONTABIL'),
            ('nf.TIPO_NF', 'Tipo NF', 'text', 'TIPO_NF'),
            ('nf.TIPO_LINHA', 'Tipo Linha', 'text', 'TIPO_LINHA'),
            ('nf.DT_NOTA', 'Dt Emissão NF', 'date', 'DT_NOTA'),
            ('nf.DATA_LANCAMENTO', 'Data Lançamento', 'date', 'DATA_LANCAMENTO'),
            ('nf.DATA_VENCIMENTO', 'Data Vencimento', 'date', 'DATA_VENCIMENTO'),
            ('nf.DATA_PAGAMENTO', 'Data Pagamento', 'date', 'DATA_PAGAMENTO'),
            ('nf.VALOR_NOTA_BRL', 'Valor Bruto BRL', 'currency', 'VALOR_NOTA_BRL'),
            ('nf.VALOR_LIQUIDO_BRL', 'Valor Líquido BRL', 'currency', 'VALOR_LIQUIDO_BRL'),
            ('nf.SAVING_TOTAL', 'Desconto(-)/Aumento(+)', 'currency', 'SAVING_TOTAL'),
            ('nf.PRECO', 'Preço BRL', 'currency', 'PRECO_BRL'),
            ('nf.COND_PGTO_AP', 'Prazo', 'integer', 'COND_PGTO_AP'),
            ('nf.QUANTIDADE', 'Quantidade', 'integer', 'QUANTIDADE'),
            ('COALESCE(nf.IS_FORNECEDOR_ESPECIAL, oc.is_fornecedor_especial)', 'Forn. Especial', 'text', 'IS_FORNECEDOR_ESPECIAL'),
            ('COALESCE(nf.IS_FORNECEDOR_NAO_NEGOCIAVEL, oc.is_fornecedor_nao_negociavel)', 'Negociabilidade', 'text', 'IS_FORNECEDOR_NAO_NEGOCIAVEL'),
            (_sem_oc_flag_sql(), 'Forn. sem OC / Atuação', 'text', 'IS_FORNECEDOR_SEM_OC'),
            ('nf.TIPO_VENDOR', 'Tipo Vendor', 'text', 'TIPO_VENDOR'),
            ('nf.URGENTE', 'Urgente', 'text', 'URGENTE'),
            # Dados Enriquecidos OC
            ("COALESCE(NULLIF(oc.comprador, ''), oc.nome_usuario)", 'Comprador', 'text', 'COMPRADOR'),
            ('oc.area', 'Departamento Comprador', 'text', 'DEPARTAMENTO_COMPRADOR'),
            ('oc.status_fechamento', 'Status Fechamento', 'text', 'STATUS_FECHAMENTO'),
            ('oc.data_oc', 'Data OC', 'date', 'DATA_OC'),
            ('oc.dt_aprovacao', 'Dt Aprovação', 'date', 'DT_APROVACAO'),
            ('oc.dt_promessa', 'Dt Promessa', 'date', 'DT_PROMESSA'),
            ('oc.dt_fechamento', 'Dt Fechamento', 'date', 'DT_FECHAMENTO'),
            ('oc.valor_original_brl', 'Valor Original BRL', 'currency', 'VALOR_ORIGINAL'),
            ('oc.valor_utilizado_brl', 'Valor Utilizado BRL', 'currency', 'VALOR_UTILIZADO'),
            ('oc.qtd_faturada', 'Qtd Faturada', 'integer', 'QTD_FATURADA'),
            ('oc.moeda', 'Moeda', 'text', 'MOEDA'),
            ('oc.aprovador', 'Aprovador', 'text', 'APROVADOR'),
            ('oc.requisicao', 'Requisição', 'text', 'REQUISICAO'),
            ('oc.nome_requisitante', 'Nome Requisitante', 'text', 'NOME_REQUISITANTE'),
            ('oc.area', 'Departamento Requisitante', 'text', 'DEPARTAMENTO_REQUISITANTE'),
            ('oc.tipo', 'Tipo', 'text', 'TIPO'),
            ('oc.descricao', 'Descrição', 'text', 'DESCRICAO'),
            ('oc.item_aquisicao', 'Item Aquisição', 'text', 'ITEM_AQUISICAO'),
            ('oc.oc_atrasada', 'OC Atrasada', 'text', 'OC_ATRASADA'),
            ('oc.dias_atraso_oc', 'Dias Atraso OC', 'integer', 'DIAS_ATRASO_OC'),
            ('oc.dias_aberto', 'Dias Aberto', 'integer', 'DIAS_ABERTO'),
            # Dados Acordo
            ('oc.numero_acordo', 'Número Acordo', 'text', 'NUMERO_ACORDO'),
            ('oc.acordo_status', 'Acordo Status', 'text', 'ACORDO_STATUS'),
            ('oc.acordo_dt_criacao', 'Acordo Dt Criação', 'date', 'ACORDO_DT_CRIACAO'),
            ('oc.acordo_data_inicial', 'Acordo Data Inicial', 'date', 'ACORDO_DATA_INICIAL'),
            ('oc.acordo_data_final', 'Acordo Data Final', 'date', 'ACORDO_DATA_FINAL'),
            ('oc.acordo_valor_total', 'Acordo Valor Total', 'currency', 'ACORDO_VALOR_TOTAL'),
            ('oc.acordo_valor_liberado', 'Acordo Valor Liberado', 'currency', 'ACORDO_VALOR_LIBERADO'),
            ('oc.acordo_descricao', 'Acordo Descrição', 'text', 'ACORDO_DESCRICAO'),
            ('oc.acordo_condicao_frete', 'Acordo Condição Frete', 'text', 'ACORDO_CONDICAO_FRETE'),
            ('oc.acordo_condicao_pgto', 'Acordo Prazo Pgto', 'text', 'ACORDO_CONDICAO_PGTO')
        ],
        'ordens': [],  # alias pointing to notas
        'requisicoes': [
            ('REQUISICAO', 'Requisição', 'text', 'REQUISICAO'),
            ('EMPRESA', 'Empresa', 'text', 'EMPRESA'),
            ('REQUISITANTE', 'Requisitante', 'text', 'REQUISITANTE'),
            ('departamento_requisitante', 'Departamento Requisitante', 'text', 'DEPARTAMENTO_REQUISITANTE'),
            ('DESCRICAO_REQ', 'Descrição Req', 'text', 'DESCRICAO_REQ'),
            ('NUMERO_OC', 'Número OC', 'text', 'NUMERO_OC'),
            ('DT_CRIACAO', 'Dt Criação', 'date', 'DT_CRIACAO'),
            ('DT_APROVACAO', 'Dt Aprovação', 'date', 'DT_APROVACAO'),
            ('VALOR_REQUISICAO', 'Valor Requisição', 'currency', 'VALOR_REQUISICAO'),
            ('STATUS', 'Status', 'text', 'STATUS'),
            ('STATUS_ORDEM', 'Status Ordem', 'text', 'STATUS_ORDEM'),
            ('user_requisicao', 'Usuário do Requisitante', 'text', 'USER_REQUISICAO'),
            ('email_requisitante', 'Email Requisitante', 'text', 'EMAIL_REQUISITANTE'),
            ('user_aprovador', 'User Aprovador', 'text', 'USER_APROVADOR'),
            ("NULLIF(TRIM(comprador_sugerido), '')", 'Comprador Sugerido', 'text', 'COMPRADOR_SUGERIDO'),
            ("NULLIF(TRIM(departamento_comprador), '')", 'Departamento Comprador', 'text', 'DEPARTAMENTO_COMPRADOR'),
        ]
    }
    export_definitions['ordens'] = export_definitions['notas']
    export_definitions['notas_ordens'] = export_definitions['notas']

    all_defs = export_definitions.get(source, export_definitions['notas'])
    if requested_cols_raw:
        req_set = set(c.strip().upper() for c in requested_cols_raw.split(',') if c.strip())
        active_defs = [
            d for d in all_defs
            if (len(d) > 3 and d[3].upper() in req_set) or d[0].upper() in req_set or d[1].upper() in req_set
        ]
        if not active_defs:
            active_defs = all_defs
    else:
        active_defs = all_defs

    select_expr = ", ".join([f"{d[0]} AS \"{d[3] if len(d) > 3 else d[1]}\"" for d in active_defs])

    if source in ('notas', 'ordens', 'notas_ordens'):
        tie_breaker = "nf.DATA_LANCAMENTO DESC, nf.NUMERO_RI DESC, nf.CHAVE_OC_LINHA ASC, nf.NOTA_FISCAL ASC"
        order = f'ORDER BY "{sort_col}" {sort_dir} NULLS LAST, {tie_breaker}' if sort_col else f'ORDER BY {tie_breaker}'
    else:
        tie_breaker = "DT_CRIACAO DESC, REQUISICAO DESC"
        order = f'ORDER BY "{sort_col}" {sort_dir} NULLS LAST, {tie_breaker}' if sort_col else f'ORDER BY {tie_breaker}'

    sql = f"SELECT {select_expr} FROM {table} {w} {order}"
    _log.info("[EXPORT] Streaming %s export: %s", source, sql[:250])

    fmt = request.args.get('format', 'xlsx').lower()

    if fmt == 'xlsx' and Workbook is not None:
        wb = Workbook()
        ws = wb.active
        titles_map = {'notas': 'Notas & OCs', 'ordens': 'Notas & OCs', 'notas_ordens': 'Notas & OCs', 'requisicoes': 'Requisições'}
        ws.title = (titles_map.get(source, 'Dados'))[:31]

        headers = [d[1] for d in active_defs]
        ws.append(headers)

        conn = _get_conn()
        row_count = 0
        try:
            cur = conn.cursor(name=f'exp_{uuid.uuid4().hex}')
            cur.itersize = 5000
            cur.execute(sql)
            for row in cur:
                row_count += 1
                row_vals = []
                for idx, val in enumerate(row):
                    c_type = active_defs[idx][2]
                    if val is None or val == '':
                        row_vals.append(None)
                    elif c_type == 'date':
                        s = str(val).strip()
                        if len(s) >= 10 and s[4] == '-' and s[7] == '-':
                            row_vals.append(f'{s[8:10]}/{s[5:7]}/{s[0:4]}')
                        else:
                            row_vals.append(s)
                    elif c_type == 'currency':
                        try:
                            row_vals.append(float(val))
                        except:
                            row_vals.append(val)
                    elif c_type == 'integer':
                        try:
                            row_vals.append(int(round(float(val))))
                        except:
                            row_vals.append(val)
                    else:
                        row_vals.append(str(val))
                ws.append(row_vals)
            cur.close()
        finally:
            conn.close()

        # Format as Excel Table Style Light 1 ("Clara 1" matching Excel screenshot)
        if row_count > 0:
            last_col = get_column_letter(len(headers))
            last_row = row_count + 1
            tab = Table(displayName=f"Tabela_{source}_{uuid.uuid4().hex[:6]}", ref=f"A1:{last_col}{last_row}")
            tab_style = TableStyleInfo(
                name="TableStyleLight1",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False
            )
            tab.tableStyleInfo = tab_style
            ws.add_table(tab)

        # Apply currency format
        for idx, d in enumerate(active_defs):
            if d[2] == 'currency':
                col_letter = get_column_letter(idx + 1)
                for r_idx in range(2, min(row_count + 2, 50000)):
                    ws[f'{col_letter}{r_idx}'].number_format = 'R$ #,##0.00;[Red]-R$ #,##0.00;"R$ 0,00"'

        # Auto-adjust column widths (sampled from first 200 rows)
        for col_idx, d in enumerate(active_defs, start=1):
            col_letter = get_column_letter(col_idx)
            max_len = len(d[1])
            for r in range(2, min(row_count + 2, 202)):
                val_str = str(ws[f'{col_letter}{r}'].value or '')
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 45)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename = f"compras_{source}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return Response(
            buf.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )

    # Fallback to CSV streaming
    @stream_with_context
    def generate_csv():
        yield '\ufeff'
        yield ';'.join([f'"{d[1]}"' for d in active_defs]) + '\r\n'

        conn = _get_conn()
        try:
            cur = conn.cursor(name=f'exp_{uuid.uuid4().hex}')
            cur.itersize = 2000
            cur.execute(sql)
            for row in cur:
                line_parts = []
                for idx, val in enumerate(row):
                    c_type = active_defs[idx][2]
                    if val is None or val == '':
                        line_parts.append('')
                    elif c_type == 'date':
                        s = str(val).strip()
                        if len(s) >= 10 and s[4] == '-' and s[7] == '-':
                            line_parts.append(f'{s[8:10]}/{s[5:7]}/{s[0:4]}')
                        else:
                            line_parts.append(s)
                    elif c_type == 'currency':
                        try:
                            line_parts.append(f'{float(val):.2f}'.replace('.', ','))
                        except:
                            line_parts.append(str(val))
                    elif c_type == 'integer':
                        try:
                            line_parts.append(str(int(round(float(val)))))
                        except:
                            line_parts.append(str(val))
                    else:
                        s = str(val).replace('"', '""')
                        line_parts.append(f'"{s}"')
                yield ';'.join(line_parts) + '\r\n'
            cur.close()
        except Exception as e:
            _log.error("Error streaming CSV: %s", e)
            yield f"\r\nERRO AO EXPORTAR DADOS: {str(e)}\r\n"
        finally:
            conn.close()

    filename = f"compras_{source}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        generate_csv(),
        mimetype='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )


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
        "fornecedores_sem_oc": {
        "title": "Fornecedores sem OC",
        "description": "Fornecedores permitidos faturar sem PO (sem atuação de Compras)",
        "table_name": "fornecedores_sem_oc",
        "csv_filename": "fornecedores_sem_oc.csv",
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
        if "fornecedor" in norm and ("cod" in norm or "num" in norm or "codigo" in norm):
            norm = "cod_fornecedor_oracle"
        elif "fornecedor" in norm and ("nome" in norm or "razao" in norm or norm == "fornecedor"):
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
                UPDATE "{_PG_SCHEMA}"."notas_ri"
                SET oc_pos_fatura = 'NÃO'
                WHERE is_fornecedor_especial = 'ESPECIAL' AND oc_pos_fatura = 'SIM'
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
        elif table_key == "fornecedores_sem_oc":
            _log.info("Recalculating is_fornecedor_sem_oc in Lakebase...")
            cur.execute(f"""
                UPDATE "{_PG_SCHEMA}"."notas_ri"
                SET is_fornecedor_sem_oc = CASE 
                    WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_sem_oc") THEN 'SEM OC'
                    ELSE 'COM ATUAÇÃO'
                END
                WHERE is_fornecedor_sem_oc IS DISTINCT FROM (
                    CASE WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_sem_oc") THEN 'SEM OC' ELSE 'COM ATUAÇÃO' END
                )
            """)
            cur.execute(f"""
                UPDATE "{_PG_SCHEMA}"."ordens_compra"
                SET is_fornecedor_sem_oc = CASE 
                    WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_sem_oc") THEN 'SEM OC'
                    ELSE 'COM ATUAÇÃO'
                END
                WHERE is_fornecedor_sem_oc IS DISTINCT FROM (
                    CASE WHEN numero_fornecedor IN (SELECT cod_fornecedor_oracle FROM "{_PG_SCHEMA}"."fornecedores_sem_oc") THEN 'SEM OC' ELSE 'COM ATUAÇÃO' END
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
        _clear_query_cache(f'flags recalculated {table_key}')
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

    # 4b. Dados de cadastro mudaram: limpa o cache para as telas refletirem a alteração
    if pg_ok:
        _clear_query_cache(f'lookup save {table_key}')

    # 5. Recalculate flags in background thread so HTTP response is fast
    if pg_ok and table_key in ["fornecedores_especiais", "fornecedores_nao_negociaveis", "fornecedores_sem_oc"]:
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


@app.route('/api/lookups/parse-file', methods=['POST'])
def lookups_parse_file():
    """Robust endpoint to parse uploaded spreadsheets (Excel/CSV), with fallback for RMS-protected files."""
    user_email = _get_current_user_email()
    if not _is_user_authorized_for_cadastros(user_email):
        return jsonify({"success": False, "error": "Acesso negado para o módulo de cadastros."}), 403

    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename:
        return jsonify({"success": False, "error": "Nenhum arquivo enviado."}), 400

    filename = uploaded.filename
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    file_bytes = uploaded.read()
    if not file_bytes:
        return jsonify({"success": False, "error": "Arquivo vazio."}), 400

    parsed_rows = []
    
    # 1. Try Pandas (openpyxl / xlrd / csv)
    try:
        import pandas as pd
        if ext == 'csv':
            for enc in ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']:
                try:
                    df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, sep=None, engine='python')
                    if not df.empty:
                        break
                except Exception:
                    continue
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))
        
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                item = {}
                for col in df.columns:
                    val = row[col]
                    val_str = "" if pd.isna(val) else str(val).strip()
                    if val_str.endswith(".0") and val_str[:-2].isdigit():
                        val_str = val_str[:-2]
                    item[str(col).strip()] = val_str
                if any(item.values()):
                    parsed_rows.append(item)
    except Exception as e:
        _log.warning("Pandas failed to read uploaded file %s: %s", filename, e)

    # 2. If failed and on Windows, attempt Excel COM (handles RMS/MIP encrypted files)
    if not parsed_rows and os.name == 'nt' and ext in ['xlsx', 'xls']:
        try:
            import tempfile, subprocess
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}").replace('/', '\\')
            with open(temp_path, "wb") as f:
                f.write(file_bytes)
            
            ps_script = f"""
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {{
    $wb = $excel.Workbooks.Open('{temp_path}')
    $sh = $wb.Sheets.Item(1)
    $used = $sh.UsedRange
    $rows = $used.Rows.Count
    $cols = $used.Columns.Count
    $headers = @()
    for ($c = 1; $c -le $cols; $c++) {{
        $h = [string]$sh.Cells.Item(1, $c).Text
        $headers += ($h -replace '[\r\n]+', ' ').Trim()
    }}
    $data = @()
    for ($r = 2; $r -le $rows; $r++) {{
        $rowObj = [ordered]@{{}}
        $hasVal = $false
        for ($c = 1; $c -le $cols; $c++) {{
            $val = [string]$sh.Cells.Item($r, $c).Text
            $val = ($val -replace '[\r\n]+', ' ').Trim()
            $key = $headers[$c - 1]
            if ($key) {{
                $rowObj[$key] = $val
                if ($val) {{ $hasVal = $true }}
            }}
        }}
        if ($hasVal) {{
            $data += [PSCustomObject]$rowObj
        }}
    }}
    $wb.Close($false)
    $data | ConvertTo-Json -Compress
}} finally {{
    $excel.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
}}
"""
            ps_res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                                   capture_output=True, text=True, timeout=45)
            if ps_res.returncode == 0 and ps_res.stdout.strip():
                raw_json = json.loads(ps_res.stdout.strip())
                if isinstance(raw_json, dict):
                    parsed_rows = [raw_json]
                elif isinstance(raw_json, list):
                    parsed_rows = raw_json
            try:
                os.remove(temp_path)
            except Exception:
                pass
        except Exception as e:
            _log.warning("Windows COM fallback failed for %s: %s", filename, e)

    if not parsed_rows:
        return jsonify({
            "success": False,
            "error": "Não foi possível extrair dados da planilha. Verifique se o arquivo está corrompido ou sem linhas de dados."
        }), 400

    return jsonify({
        "success": True,
        "filename": filename,
        "rows": parsed_rows,
        "count": len(parsed_rows),
        "columns": list(parsed_rows[0].keys()) if parsed_rows else []
    })


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
    _log.info("Starting PORTAL COMPRAS on port %d with 16 threads", port)
    from waitress import serve
    serve(app, host='0.0.0.0', port=port, threads=16, connection_limit=100, channel_timeout=60)

