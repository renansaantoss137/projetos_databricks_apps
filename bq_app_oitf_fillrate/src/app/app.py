import inspect
import hashlib
import json as _json
import logging
import os
import threading
import time
import calendar as _calendar
from datetime import date, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
_log = logging.getLogger("app.db")

pyodbc = None
pymssql = None
try:
    import pyodbc
except Exception:
    pass

try:
    import pymssql
    _log.info("Driver pymssql %s disponível", getattr(pymssql, '__version__', '?'))
except Exception as _e:
    _log.warning("pymssql indisponível: %s", _e)

# ── Credenciais: Databricks Secrets (produção) com fallback para .env (dev local) ──
try:
    from databricks.sdk.runtime import dbutils
    _DB_USER     = dbutils.secrets.get(scope="kvsecret-DnABrazil", key="kvsecret-AzSQL-cz-BB-sql-Usr")
    _DB_PASSWORD = dbutils.secrets.get(scope="kvsecret-DnABrazil", key="kvsecret-AzSQL-cz-BB-sql-psw")
    _CRED_SOURCE = "databricks-secrets"
except Exception:
    from dotenv import load_dotenv
    load_dotenv()
    _DB_USER     = os.getenv("DB_USER", "")
    _DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    _CRED_SOURCE = "dotenv"

_DB_SERVER = os.getenv("DB_SERVER", "bbraclbbsqlcp02.database.windows.net")
_DB_NAME   = os.getenv("DB_NAME",   "ACL-DNA-BRPROD")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR)
CORS(app)


_thread_local = threading.local()
_CONN_TTL_SECONDS = 300  # 5 minutes

_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={_DB_SERVER};"
    f"DATABASE={_DB_NAME};"
    f"UID={_DB_USER};"
    f"PWD={_DB_PASSWORD};"
    "Authentication=ActiveDirectoryPassword;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
    "Connection Timeout=30;"
)

# ── Wrapper de compatibilidade pymssql (‘?’ → ‘%s’) ─────────────────────────────
# pymssql segue DB-API 2.0 com %s, enquanto pyodbc usa ?.  Este wrapper
# converte automaticamente os placeholders e escapa % literais no SQL.

class _MssqlCursor:
    def __init__(self, cur):
        self._cur = cur

    @staticmethod
    def _fix(sql):
        """Escapa % literais como %% e converte ? em %s."""
        return sql.replace('%', '%%').replace('?', '%s')

    def execute(self, sql, params=()):
        if params:
            sql = self._fix(sql)
            self._cur.execute(sql, tuple(params))
        else:
            self._cur.execute(sql)

    def fetchone(self):  return self._cur.fetchone()
    def fetchall(self):  return self._cur.fetchall()

    @property
    def description(self): return self._cur.description

    @property
    def rowcount(self):    return self._cur.rowcount

    def __getattr__(self, name): return getattr(self._cur, name)


class _MssqlConn:
    def __init__(self, conn):
        self._c = conn

    def cursor(self):
        return _MssqlCursor(self._c.cursor())

    def execute(self, sql, params=()):
        """Atalho keep-alive: cria cursor e executa."""
        return self.cursor().execute(sql, params)

    def close(self):
        return self._c.close()

    def __getattr__(self, name): return getattr(self._c, name)


def get_connection():
    conn = getattr(_thread_local, 'conn', None)
    conn_ts = getattr(_thread_local, 'conn_ts', 0)

    # Force reconnect if TTL exceeded
    if conn is not None and (time.time() - conn_ts) > _CONN_TTL_SECONDS:
        _log.info("Conexão expirou (TTL %ds) — reconectando", _CONN_TTL_SECONDS)
        try:
            conn.close()
        except Exception:
            pass
        conn = None
        _thread_local.conn = None

    # Health check on existing connection
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            _thread_local.conn = None

    if pyodbc is not None:
        try:
            conn = pyodbc.connect(_CONN_STR)
            _thread_local.conn = conn
            _thread_local.conn_ts = time.time()
            _log.info("Conexão pyodbc OK")
            return conn
        except Exception as _e:
            _log.warning("pyodbc falhou (%s) — tentando pymssql", _e)

    if pymssql is not None:
        _log.info("Conectando via pymssql: server=%s db=%s", _DB_SERVER, _DB_NAME)
        _raw = pymssql.connect(
            server=_DB_SERVER,
            database=_DB_NAME,
            user=_DB_USER,
            password=_DB_PASSWORD,
            autocommit=True,
            login_timeout=30,
        )
        conn = _MssqlConn(_raw)
        _thread_local.conn = conn
        _thread_local.conn_ts = time.time()
        _log.info("Conexão pymssql OK (TLS via FreeTDS)")
        return conn

    raise RuntimeError(
        "Nenhum driver disponível. Adicione pymssql ao requirements.txt."
    )


# ── SQL helpers ───────────────────────────────────────────────────────────────

_GROUP_BY = """
    GROUP BY
        NUMERO_PEDIDO, CNPJ_CLIENTE, GRUPO_CLI, NOME_GRP_CLIENTE,
        CNPJ_BIMBO, EMPRESA, PLANTA,
        DT_EMISSAO_PEDIDO, DT_PLANEJADA_FATURAMENTO, DT_ENVIO,
        ID_STATUS_PEDIDO, STATUS_PEDIDO
"""

_PLANTA_CASE = (
    "CASE P.DB_PED_EMPRESA"
    " WHEN 'QRA' THEN 'JAG'"
    " WHEN 'QRC' THEN 'JDF'"
    " WHEN 'QRB' THEN 'OSA'"
    " WHEN 'QRE' THEN 'QRE'"
    " WHEN 'QRJ' THEN 'GUA'"
    " WHEN 'QRD' THEN 'POU'"
    " WHEN 'QRF' THEN 'OSA'"
    " ELSE P.DB_PED_EMPRESA END"
)


def _parse_filters(args):
    """Lê os filtros do request e devolve os componentes da query.
    Aceita múltiplos valores para empresa e status (ex: ?empresa=QRA&empresa=QRB).
    Aceita ano/mes/dia/semana OU dt_ini/dt_fim para datas."""
    dt_ini   = args.get('dt_ini', '').strip()
    dt_fim   = args.get('dt_fim', '').strip()
    anos     = [a.strip() for a in args.getlist('ano')    if a.strip()]
    meses    = [m.strip() for m in args.getlist('mes')    if m.strip()]
    dias     = [d.strip() for d in args.getlist('dia')    if d.strip()]
    semanas  = [s.strip() for s in args.getlist('semana') if s.strip()]
    plantas         = [p.strip() for p in args.getlist('planta')        if p.strip()]
    grupos_cliente  = [g.strip() for g in args.getlist('grupo_cliente') if g.strip()]
    canais          = [c.strip() for c in args.getlist('canal')         if c.strip()]
    responsaveis    = [r.strip() for r in args.getlist('responsavel')   if r.strip()]
    statuses = [s.strip() for s in args.getlist('status') if s.strip()]
    busca    = args.get('busca', '').strip()

    cte_filters = [
        "I.DB_PEDI_PRODUTO <> '999999917'",
        "I.db_pedi_situacao IN (0, 1, 2, 9)",
        "I.status_registro = 'ATIVO'",
    ]
    cte_params = []

    # Date filtering: prefer ano/mes/dia if provided, else dt_ini/dt_fim
    if anos or meses or dias or semanas:
        if semanas:
            # Semana ranges: "YYYY-MM-DD|YYYY-MM-DD"
            sem_clauses = []
            for s in semanas:
                parts = s.split('|')
                if len(parts) == 2:
                    sem_clauses.append("(CAST(P.DB_PED_DT_PREVENT AS DATE) >= CAST(? AS DATE) AND CAST(P.DB_PED_DT_PREVENT AS DATE) <= CAST(? AS DATE))")
                    cte_params.extend(parts)
            if sem_clauses:
                cte_filters.append("(" + " OR ".join(sem_clauses) + ")")
        else:
            if anos:
                ph = ','.join('?' * len(anos))
                cte_filters.append(f"YEAR(P.DB_PED_DT_PREVENT) IN ({ph})")
                cte_params.extend(anos)
            if meses:
                ph = ','.join('?' * len(meses))
                cte_filters.append(f"MONTH(P.DB_PED_DT_PREVENT) IN ({ph})")
                cte_params.extend(meses)
            if dias:
                ph = ','.join('?' * len(dias))
                cte_filters.append(f"DAY(P.DB_PED_DT_PREVENT) IN ({ph})")
                cte_params.extend(dias)
    else:
        default_ini = (date.today() - timedelta(days=90)).isoformat()
        default_fim = date.today().isoformat()
        cte_filters.append("CAST(P.DB_PED_DT_PREVENT AS DATE) >= CAST(? AS DATE)")
        cte_filters.append("CAST(P.DB_PED_DT_PREVENT AS DATE) <= CAST(? AS DATE)")
        cte_params = [dt_ini or default_ini, dt_fim or default_fim]

    if plantas:
        ph = ','.join('?' * len(plantas))
        cte_filters.append(f"{_PLANTA_CASE} IN ({ph})")
        cte_params.extend(plantas)

    outer_filters = ["CANAL <> 'N\u00c3O DEFINIDO'"]
    outer_params  = []

    if grupos_cliente:
        ph = ','.join('?' * len(grupos_cliente))
        outer_filters.append(f"NOME_GRP_CLIENTE IN ({ph})")
        outer_params.extend(grupos_cliente)
    if canais:
        ph = ','.join('?' * len(canais))
        outer_filters.append(f"CANAL IN ({ph})")
        outer_params.extend(canais)
    if responsaveis:
        ph = ','.join('?' * len(responsaveis))
        outer_filters.append(f"RESPONSAVEL IN ({ph})")
        outer_params.extend(responsaveis)

    if statuses:
        _st_clauses = []
        _vencido = "CAST(DT_PLANEJADA_FATURAMENTO AS DATE) < CAST(GETDATE() AS DATE)"
        _no_prazo = "CAST(DT_PLANEJADA_FATURAMENTO AS DATE) >= CAST(GETDATE() AS DATE)"
        _liquido = "(PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO)"
        for sv in statuses:
            if sv == 'no_prazo':
                _st_clauses.append(f"({_no_prazo})")
            elif sv == 'nao_faturado':
                _st_clauses.append(f"({_vencido} AND PEDIDO_QTDE_ATENDIDO = 0 AND ID_STATUS_PEDIDO <> '9')")
            elif sv == 'parcial':
                _st_clauses.append(f"({_vencido} AND PEDIDO_QTDE_ATENDIDO > 0 AND PEDIDO_QTDE_ATENDIDO < {_liquido})")
            elif sv == 'conforme':
                _st_clauses.append(f"(PEDIDO_QTDE_ATENDIDO >= {_liquido} AND {_liquido} > 0)")
        if _st_clauses:
            outer_filters.append("(" + " OR ".join(_st_clauses) + ")")
    if busca:
        like = f'%{busca}%'
        outer_filters.append(
            "(CAST(NUMERO_PEDIDO AS NVARCHAR(50)) LIKE ? OR CNPJ_CLIENTE LIKE ?)"
        )
        outer_params.extend([like, like])

    cte_where   = "WHERE " + " AND ".join(cte_filters)
    outer_where = ("WHERE " + " AND ".join(outer_filters)) if outer_filters else ""

    return cte_where, cte_params, outer_where, outer_params


def _build_cte_sql(cte_where):
    return f"""
        WITH BASE AS (
            SELECT
                I.DB_PEDI_PEDIDO AS NUMERO_PEDIDO,
                CASE
                    WHEN dc.DB_CLI_CGCMF = '099999999999999' THEN '0'
                    WHEN dc.DB_CLI_CGCMF = '99999999999999'  THEN '0'
                    ELSE dc.DB_CLI_CGCMF
                END AS CNPJ_CLIENTE,
                R.DB_TBATV_CODIGO                                     AS GRUPO_CLI,
                G.GRUPO_CLIENTE_DESC                                  AS NOME_GRP_CLIENTE,
                ISNULL(G.CLUSTER_FILL_RATE_OTIF, 'Sem Canal')         AS CANAL,
                ISNULL(G.NM_NV1, 'Sem Responsável')                   AS RESPONSAVEL,
                CASE P.DB_PED_EMPRESA
                    WHEN 'QRA' THEN '35402759011110'
                    WHEN 'QRC' THEN '35402759011209'
                    WHEN 'QRB' THEN '35402759011381'
                    WHEN 'QRE' THEN '35402759011462'
                    WHEN 'QRD' THEN '35402759011543'
                    WHEN 'QRF' THEN '35402759011624'
                    ELSE ''
                END AS CNPJ_BIMBO,
                P.DB_PED_EMPRESA                                      AS EMPRESA,
                CASE P.DB_PED_EMPRESA
                    WHEN 'QRA' THEN 'JAG'
                    WHEN 'QRC' THEN 'JDF'
                    WHEN 'QRB' THEN 'OSA'
                    WHEN 'QRE' THEN 'QRE'
                    WHEN 'QRJ' THEN 'GUA'
                    WHEN 'QRD' THEN 'POU'
                    WHEN 'QRF' THEN 'OSA'
                    ELSE P.DB_PED_EMPRESA
                END AS PLANTA,
                CAST(P.DB_PED_DT_EMISSAO  AS DATE)                   AS DT_EMISSAO_PEDIDO,
                CAST(P.DB_PED_DT_PREVENT  AS DATE)                   AS DT_PLANEJADA_FATURAMENTO,
                CAST(P.DB_PED_DATA_ENVIO  AS DATE)                   AS DT_ENVIO,
                CAST(I.DB_PEDI_ATD_DATA   AS DATE)                   AS DT_REAL_FATURAMENTO,
                I.db_pedi_situacao                                    AS ID_STATUS_PEDIDO,
                CASE I.db_pedi_situacao
                    WHEN '0' THEN 'Aberto'
                    WHEN '1' THEN 'Faturado Parcial'
                    WHEN '2' THEN 'Faturado'
                    WHEN '9' THEN 'Cancelado'
                    ELSE 'Verificar'
                END AS STATUS_PEDIDO,
                I.db_pedi_qtde_solic                                  AS PEDIDO_QTDE,
                I.db_pedi_qtde_atend                                  AS PEDIDO_QTDE_ATENDIDO,
                I.db_pedi_qtde_canc                                   AS PEDIDO_QTDE_CANCELADO,
                I.db_pedi_preco_liq                                   AS PRECO_UNIT,
                I.DB_PEDI_PRECO_UNIT * I.DB_PEDI_QTDE_ATEND          AS PEDIDO_ATENDIDO_VLR,
                I.db_pedi_qtde_solic * I.db_pedi_preco_liq           AS PEDIDO_VLR,
                I.db_pedi_qtde_solic * I.db_pedi_preco_liq
                    - (I.DB_PEDI_PRECO_UNIT * I.db_pedi_qtde_canc)   AS PEDIDO_VLR_LIQ,
                (I.db_pedi_qtde_solic   * I.db_pedi_preco_liq)
                    - (I.DB_PEDI_PRECO_UNIT * I.DB_PEDI_QTDE_ATEND)
                    - (I.DB_PEDI_PRECO_UNIT * I.db_pedi_qtde_canc)   AS VL_BRUTO_OPEN_ORDERS,
                COALESCE(I.DB_PEDI_VU_ICMS, 0)                       AS VL_ICMS_BRUTO,
                (
                    (I.db_pedi_qtde_solic   * I.db_pedi_preco_liq)
                    - (I.DB_PEDI_PRECO_UNIT * I.DB_PEDI_QTDE_ATEND)
                    - (I.DB_PEDI_PRECO_UNIT * I.db_pedi_qtde_canc)
                ) * I.DB_PEDI_ICMSDEST / 100                         AS VL_ICMS_SALDO_OPEN_ORDERS,
                (
                    (I.db_pedi_qtde_solic   * I.db_pedi_preco_liq)
                    - (I.DB_PEDI_PRECO_UNIT * I.DB_PEDI_QTDE_ATEND)
                    - (I.DB_PEDI_PRECO_UNIT * I.db_pedi_qtde_canc)
                ) * (1 - I.DB_PEDI_ICMSDEST / 100) * 0.0925         AS VL_PIS_COFINS_OPEN_ORDERS,
                COALESCE(I.DB_PEDI_VU_ICMS, 0)
                    + (I.DB_PEDI_PRECO_UNIT * I.DB_PEDI_QTDE_ATEND * 0.0925) AS IMPOSTO_VENDA
            FROM BQB.MCANET_DB_PEDIDO_PROD I WITH (NOLOCK)
            INNER JOIN BQB.MCANET_DB_PEDIDO P WITH (NOLOCK)
                ON I.DB_PEDI_PEDIDO = P.DB_PED_NRO
            LEFT JOIN BQB.MCANET_DB_CLIENTE dc WITH (NOLOCK)
                ON P.DB_PED_CLIENTE = dc.DB_CLI_CODIGO
            LEFT JOIN BQB.MCANET_DB_TB_RAMO_ATIV R WITH (NOLOCK)
                ON dc.DB_CLI_RAMATIV = R.DB_TBATV_CODIGO
            LEFT JOIN BQB.GRUPO_CLIENTES_VIEW G WITH (NOLOCK)
                ON TRY_CAST(R.DB_TBATV_CODIGO AS INT) = G.COD_GR_CLIENTE
            {cte_where}
        )
    """


# ── Diagnóstico de conexão ─────────────────────────────────────────────────────

@app.route('/api/diag')
def diag():
    """Endpoint de diagnóstico: informa drivers, fonte de credenciais e testa a conexão."""
    import sys
    info = {
        "python": sys.version,
        "drivers": {
            "pyodbc": getattr(pyodbc, 'version', None) if pyodbc else None,
            "pymssql": getattr(pymssql, '__version__', None) if pymssql else None,
        },
        "credentials_source": _CRED_SOURCE,
        "db_server": _DB_SERVER,
        "db_name":   _DB_NAME,
        "db_user_hint": (_DB_USER[:3] + "***") if _DB_USER else "(vazio)",
    }

    # Testar conexão real
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT GETDATE() AS now, @@VERSION AS version")
        row = cur.fetchone()
        info["connection"] = {
            "status": "OK",
            "server_time": str(row[0]),
            "server_version": str(row[1])[:80],
        }
        _log.info("/api/diag: conexão OK — server_time=%s", row[0])
    except Exception as _e:
        info["connection"] = {"status": "ERRO", "detail": str(_e)}
        _log.error("/api/diag: falha na conexão — %s", _e)

    return jsonify(info)


# ── Pedidos ───────────────────────────────────────────────────────────────────

@app.route('/api/pedidos')
def get_pedidos():
    page      = max(1, int(request.args.get('page',      1)))
    page_size = min(500, max(1, int(request.args.get('page_size', 50))))

    cte_where, cte_params, outer_where, outer_params = _parse_filters(request.args)

    # Column-specific filters (cf_EMPRESA[]=..., cf_STATUS_PEDIDO[]=..., etc.)
    _CF_COLS = {
        'EMPRESA': 'EMPRESA', 'STATUS_PEDIDO': 'STATUS_PEDIDO',
        'GRUPO_CLI': 'GRUPO_CLI', 'CNPJ_CLIENTE': 'CNPJ_CLIENTE',
        'NUMERO_PEDIDO': 'CAST(NUMERO_PEDIDO AS VARCHAR(50))',
    }
    cf_extra = []
    cf_params = []
    for col_key, col_expr in _CF_COLS.items():
        vals = request.args.getlist(f'cf_{col_key}')
        if vals:
            ph = ','.join('?' * len(vals))
            cf_extra.append(f"ISNULL({col_expr},'') IN ({ph})")
            cf_params.extend(vals)
    if cf_extra:
        sep = ' AND ' if outer_where else 'WHERE '
        if outer_where:
            outer_where += ' AND ' + ' AND '.join(cf_extra)
        else:
            outer_where = 'WHERE ' + ' AND '.join(cf_extra)
    outer_params = outer_params + cf_params

    cte_sql    = _build_cte_sql(cte_where)
    all_params = cte_params + outer_params
    offset     = (page - 1) * page_size

    # Sort support — whitelist allowed column names to prevent SQL injection
    _SORT_COLS = {
        'NUMERO_PEDIDO': 'NUMERO_PEDIDO', 'PLANTA': 'PLANTA',
        'DT_PLANEJADA_FATURAMENTO': 'DT_PLANEJADA_FATURAMENTO',
        'DT_REAL_FATURAMENTO': 'MAX(DT_REAL_FATURAMENTO)',
        'STATUS_PEDIDO': 'STATUS_PEDIDO', 'NOME_GRP_CLIENTE': 'NOME_GRP_CLIENTE',
        'CNPJ_CLIENTE': 'CNPJ_CLIENTE',
        'DT_EMISSAO_PEDIDO': 'DT_EMISSAO_PEDIDO', 'DT_ENVIO': 'DT_ENVIO',
        'PEDIDO_QTDE': 'SUM(PEDIDO_QTDE)', 'PEDIDO_QTDE_ATENDIDO': 'SUM(PEDIDO_QTDE_ATENDIDO)',
        'PEDIDO_QTDE_CANCELADO': 'SUM(PEDIDO_QTDE_CANCELADO)',
        'PEDIDO_VLR': 'SUM(PEDIDO_VLR)', 'PEDIDO_ATENDIDO_VLR': 'SUM(PEDIDO_ATENDIDO_VLR)',
        'VL_BRUTO_OPEN_ORDERS': 'SUM(VL_BRUTO_OPEN_ORDERS)',
        '_fill_rate': 'CASE WHEN (SUM(PEDIDO_QTDE)-SUM(PEDIDO_QTDE_CANCELADO))<=0 THEN 100.0 ELSE CAST(SUM(PEDIDO_QTDE_ATENDIDO) AS FLOAT)*100.0/(SUM(PEDIDO_QTDE)-SUM(PEDIDO_QTDE_CANCELADO)) END',
    }
    sort_field = request.args.get('sort_field', 'DT_EMISSAO_PEDIDO')
    sort_dir   = 'ASC' if request.args.get('sort_dir', 'desc').lower() == 'asc' else 'DESC'
    order_expr = _SORT_COLS.get(sort_field, 'DT_EMISSAO_PEDIDO')
    order_by   = f'ORDER BY {order_expr} {sort_dir}'
    if sort_field != 'NUMERO_PEDIDO':
        order_by += ', NUMERO_PEDIDO'

    query = cte_sql + f"""
        SELECT
            CAST(NUMERO_PEDIDO AS NVARCHAR(50))                      AS NUMERO_PEDIDO,
            ISNULL(CNPJ_CLIENTE, '')                                 AS CNPJ_CLIENTE,
            ISNULL(CAST(GRUPO_CLI AS NVARCHAR(50)), '')              AS GRUPO_CLI,
            ISNULL(NOME_GRP_CLIENTE, '')                             AS NOME_GRP_CLIENTE,
            ISNULL(CNPJ_BIMBO, '')                                   AS CNPJ_BIMBO,
            ISNULL(EMPRESA, '')                                      AS EMPRESA,
            ISNULL(PLANTA, '')                                       AS PLANTA,
            CONVERT(VARCHAR(10), DT_EMISSAO_PEDIDO,         103)    AS DT_EMISSAO_PEDIDO,
            CONVERT(VARCHAR(10), DT_PLANEJADA_FATURAMENTO,  103)    AS DT_PLANEJADA_FATURAMENTO,
            CONVERT(VARCHAR(10), DT_ENVIO,                  103)    AS DT_ENVIO,
            CONVERT(VARCHAR(10), MAX(DT_REAL_FATURAMENTO),  103)    AS DT_REAL_FATURAMENTO,
            CAST(ID_STATUS_PEDIDO AS NVARCHAR(10))                   AS ID_STATUS_PEDIDO,
            ISNULL(STATUS_PEDIDO, '')                                AS STATUS_PEDIDO,
            ISNULL(SUM(PEDIDO_QTDE), 0)                             AS PEDIDO_QTDE,
            ISNULL(SUM(PEDIDO_QTDE_ATENDIDO), 0)                    AS PEDIDO_QTDE_ATENDIDO,
            ISNULL(SUM(PEDIDO_QTDE_CANCELADO), 0)                   AS PEDIDO_QTDE_CANCELADO,
            ISNULL(SUM(PRECO_UNIT), 0)                              AS PRECO_UNIT,
            ISNULL(SUM(PEDIDO_ATENDIDO_VLR), 0)                     AS PEDIDO_ATENDIDO_VLR,
            ISNULL(SUM(PEDIDO_VLR), 0)                              AS PEDIDO_VLR,
            ISNULL(SUM(VL_BRUTO_OPEN_ORDERS), 0)                   AS VL_BRUTO_OPEN_ORDERS,
            ISNULL(SUM(VL_ICMS_BRUTO), 0)                          AS VL_ICMS_BRUTO,
            ISNULL(SUM(VL_ICMS_SALDO_OPEN_ORDERS), 0)             AS VL_ICMS_SALDO_OPEN_ORDERS,
            ISNULL(SUM(VL_PIS_COFINS_OPEN_ORDERS), 0)             AS VL_PIS_COFINS_OPEN_ORDERS,
            ISNULL(SUM(IMPOSTO_VENDA), 0)                           AS IMPOSTO_VENDA
        FROM BASE
        {outer_where}
        {_GROUP_BY}
        {order_by}
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    """

    count_query = cte_sql + f"""
        SELECT COUNT(*) FROM (
            SELECT NUMERO_PEDIDO FROM BASE
            {outer_where}
            {_GROUP_BY}
        ) AS T
    """

    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(count_query, all_params)
        total = cursor.fetchone()[0]

        cursor.execute(query, all_params + [offset, page_size])
        cols = [col[0] for col in cursor.description]
        rows = []
        for row in cursor.fetchall():
            d = {}
            for col, val in zip(cols, row):
                d[col] = str(val) if val is not None else None
            rows.append(d)

        return jsonify({
            'rows':        rows,
            'total':       total,
            'page':        page,
            'page_size':   page_size,
            'total_pages': max(1, -(-total // page_size)),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pedidos/distinct')
def get_pedidos_distinct():
    """Distinct values for a column (for Excel-like column filters)."""
    col_key = request.args.get('column', '')
    _CF_COLS = {
        'EMPRESA': 'EMPRESA', 'STATUS_PEDIDO': 'STATUS_PEDIDO',
        'GRUPO_CLI': 'GRUPO_CLI', 'CNPJ_CLIENTE': 'CNPJ_CLIENTE',
    }
    if col_key not in _CF_COLS:
        return jsonify([]), 200
    col_expr = _CF_COLS[col_key]
    cte_where, cte_params, _, _ = _parse_filters(request.args)
    cte_sql = _build_cte_sql(cte_where)
    query = cte_sql + f"""
        SELECT DISTINCT ISNULL({col_expr}, '') AS VAL
        FROM BASE
        WHERE ISNULL({col_expr}, '') <> ''
        ORDER BY VAL
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, cte_params)
        rows = [row[0] for row in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pedidos/resumo')
def get_pedidos_resumo():
    """Totais agregados para os KPI cards (sem paginação).
    Separa pedidos vencidos (DT_PLANEJADA < hoje) dos dentro do prazo (>= hoje).
    Fill Rate e Corte são calculados apenas sobre os vencidos.
    """
    cte_where, cte_params, outer_where, outer_params = _parse_filters(request.args)
    cte_sql    = _build_cte_sql(cte_where)
    all_params = cte_params + outer_params

    # Usa agregação condicional: vencidos vs dentro do prazo
    vencido_cond = "DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)"
    prazo_cond   = "DT_PLANEJADA_FATURAMENTO >= CAST(GETDATE() AS DATE)"

    resumo_query = cte_sql + f"""
        SELECT
            COUNT(DISTINCT CASE WHEN {vencido_cond} AND ID_STATUS_PEDIDO <> '9' THEN NUMERO_PEDIDO END) AS TOTAL_PEDIDOS,
            COUNT(DISTINCT CASE WHEN {vencido_cond} AND ID_STATUS_PEDIDO = '9' THEN NUMERO_PEDIDO END) AS PEDIDOS_CANCELADOS,
            ISNULL(SUM(CASE WHEN {vencido_cond} THEN PEDIDO_QTDE END), 0)             AS TOTAL_QTDE_PEDIDO,
            ISNULL(SUM(CASE WHEN {vencido_cond} THEN PEDIDO_QTDE_ATENDIDO END), 0)    AS TOTAL_QTDE_ATENDIDO,
            ISNULL(SUM(CASE WHEN {vencido_cond} THEN PEDIDO_QTDE_CANCELADO END), 0)   AS TOTAL_QTDE_CANCELADO,
            ISNULL(SUM(CASE WHEN {vencido_cond} THEN PEDIDO_VLR END), 0)              AS TOTAL_VLR_PEDIDO,
            ISNULL(SUM(CASE WHEN {vencido_cond} THEN PEDIDO_VLR_LIQ END), 0)          AS TOTAL_VLR_LIQ,
            ISNULL(SUM(CASE WHEN {vencido_cond} THEN PEDIDO_ATENDIDO_VLR END), 0)     AS TOTAL_VLR_ATENDIDO,
            ISNULL(SUM(CASE WHEN {prazo_cond} THEN PEDIDO_QTDE END), 0)               AS QTDE_DENTRO_PRAZO,
            ISNULL(SUM(CASE WHEN {prazo_cond} THEN PEDIDO_VLR END), 0)                AS VLR_DENTRO_PRAZO,
            COUNT(DISTINCT CASE WHEN {prazo_cond} THEN NUMERO_PEDIDO END)             AS PEDIDOS_DENTRO_PRAZO,
            COUNT(DISTINCT NUMERO_PEDIDO)                                              AS TOTAL_PEDIDOS_GERAL,
            COUNT(DISTINCT CASE WHEN ID_STATUS_PEDIDO = '9' THEN NUMERO_PEDIDO END)    AS PEDIDOS_CANCELADOS_GERAL
        FROM BASE
        {outer_where}
    """

    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(resumo_query, all_params)
        row  = cursor.fetchone()
        cols = [c[0] for c in cursor.description]
        return jsonify(dict(zip(cols, [str(v) if v is not None else '0' for v in row])))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Fill Rate agregado ───────────────────────────────────────────────────────

@app.route('/api/fillrate/por-empresa')
def get_fillrate_por_empresa():
    """Qtdes agregadas por EMPRESA ou GRUPO CLIENTE para o gráfico e tabela de Fill Rate."""
    cte_where, cte_params, outer_where, outer_params = _parse_filters(request.args)
    cte_sql    = _build_cte_sql(cte_where)
    all_params = cte_params + outer_params

    agrupar = request.args.get('agrupar', 'grupo_cliente')

    vencido_filter = "DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)"
    if outer_where:
        fr_where = outer_where + f" AND {vencido_filter}"
    else:
        fr_where = f"WHERE {vencido_filter}"

    if agrupar == 'grupo_cliente':
        col_select = "ISNULL(NOME_GRP_CLIENTE, 'Sem Grupo')  AS EMPRESA"
        group_col  = "NOME_GRP_CLIENTE"
    else:
        col_select = "ISNULL(PLANTA, 'Sem Planta')           AS EMPRESA"
        group_col  = "PLANTA"

    query = cte_sql + f"""
        SELECT
            {col_select},
            ISNULL(SUM(PEDIDO_QTDE), 0)              AS QTDE_PEDIDA,
            ISNULL(SUM(PEDIDO_QTDE_ATENDIDO), 0)     AS QTDE_ATENDIDA,
            ISNULL(SUM(PEDIDO_QTDE_CANCELADO), 0)    AS QTDE_CANCELADA
        FROM BASE
        {fr_where}
        GROUP BY {group_col}
        HAVING (SUM(PEDIDO_QTDE) - SUM(PEDIDO_QTDE_CANCELADO)) > 0
        ORDER BY CASE WHEN (SUM(PEDIDO_QTDE) - SUM(PEDIDO_QTDE_CANCELADO)) > 0 THEN CAST(SUM(PEDIDO_QTDE_ATENDIDO) AS FLOAT) / (SUM(PEDIDO_QTDE) - SUM(PEDIDO_QTDE_CANCELADO)) ELSE 0 END DESC
    """

    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, all_params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, [str(v) if v is not None else '0' for v in row]))
                for row in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500




@app.route('/api/fillrate/por-canal')
def get_fillrate_por_canal():
    cte_where, cte_params, outer_where, outer_params = _parse_filters(request.args)
    cte_sql = _build_cte_sql(cte_where)
    all_params = cte_params + outer_params
    vencido_filter = "DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)"
    fr_where = (outer_where + f" AND {vencido_filter}") if outer_where else f"WHERE {vencido_filter}"
    query = cte_sql + f"""
        SELECT CANAL, ISNULL(SUM(PEDIDO_QTDE),0) AS QTDE_PEDIDA,
               ISNULL(SUM(PEDIDO_QTDE_ATENDIDO),0) AS QTDE_ATENDIDA,
               ISNULL(SUM(PEDIDO_QTDE_CANCELADO),0) AS QTDE_CANCELADA
        FROM BASE {fr_where}
        GROUP BY CANAL
        ORDER BY CASE WHEN ISNULL(SUM(PEDIDO_QTDE),0)-ISNULL(SUM(PEDIDO_QTDE_CANCELADO),0)=0 THEN 0
                 ELSE CAST(ISNULL(SUM(PEDIDO_QTDE_ATENDIDO),0) AS FLOAT)/(ISNULL(SUM(PEDIDO_QTDE),0)-ISNULL(SUM(PEDIDO_QTDE_CANCELADO),0)) END DESC
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, all_params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, [str(v) if v is not None else '0' for v in row])) for row in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/fillrate/mensal')
def get_fillrate_mensal():
    """Qtdes agregadas por ano/mês para o gráfico de evolução mensal."""
    cte_where, cte_params, outer_where, outer_params = _parse_filters(request.args)
    cte_sql    = _build_cte_sql(cte_where)
    all_params = cte_params + outer_params

    vencido_filter = "DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)"
    if outer_where:
        fr_where = outer_where + f" AND {vencido_filter}"
    else:
        fr_where = f"WHERE {vencido_filter}"

    query = cte_sql + f"""
        SELECT
            YEAR(DT_PLANEJADA_FATURAMENTO)           AS ANO,
            MONTH(DT_PLANEJADA_FATURAMENTO)          AS MES,
            ISNULL(SUM(PEDIDO_QTDE), 0)              AS QTDE_PEDIDA,
            ISNULL(SUM(PEDIDO_QTDE_ATENDIDO), 0)     AS QTDE_ATENDIDA,
            ISNULL(SUM(PEDIDO_QTDE_CANCELADO), 0)    AS QTDE_CANCELADA
        FROM BASE
        {fr_where}
        GROUP BY YEAR(DT_PLANEJADA_FATURAMENTO), MONTH(DT_PLANEJADA_FATURAMENTO)
        ORDER BY ANO, MES
    """

    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, all_params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, [str(v) if v is not None else '0' for v in row]))
                for row in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/fillrate/semanal')
def get_fillrate_semanal():
    """Qtdes agregadas por semana (segunda a domingo) para o gráfico semanal de Fill Rate."""
    cte_where, cte_params, outer_where, outer_params = _parse_filters(request.args)
    cte_sql    = _build_cte_sql(cte_where)
    all_params = cte_params + outer_params

    # Calculate Monday of each week without using % (conflicts with pymssql)
    _wd = "(DATEPART(weekday, DT_PLANEJADA_FATURAMENTO) - 2 + 7)"
    _mod7 = f"({_wd} - ({_wd} / 7) * 7)"
    dt_segunda = f"CAST(DATEADD(day, -({_mod7}), DT_PLANEJADA_FATURAMENTO) AS DATE)"

    vencido_filter = "DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)"
    if outer_where:
        fr_where = outer_where + f" AND {vencido_filter}"
    else:
        fr_where = f"WHERE {vencido_filter}"

    query = cte_sql + f"""
        SELECT
            {dt_segunda}                             AS DT_SEGUNDA,
            DATEPART(ISO_WEEK, DT_PLANEJADA_FATURAMENTO) AS SEMANA_NUM,
            ISNULL(SUM(PEDIDO_QTDE), 0)              AS QTDE_PEDIDA,
            ISNULL(SUM(PEDIDO_QTDE_ATENDIDO), 0)     AS QTDE_ATENDIDA,
            ISNULL(SUM(PEDIDO_QTDE_CANCELADO), 0)    AS QTDE_CANCELADA
        FROM BASE
        {fr_where}
        GROUP BY {dt_segunda}, DATEPART(ISO_WEEK, DT_PLANEJADA_FATURAMENTO)
        ORDER BY DT_SEGUNDA
    """

    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, all_params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, [str(v) if v is not None else '0' for v in row]))
                for row in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── OTIF ─────────────────────────────────────────────────────────────────────

def _build_otif_cte(cte_where):
    """Extende o CTE BASE com ORDER_LEVEL (status 1/2 apenas) e OTIF_CALC."""
    base = _build_cte_sql(cte_where).rstrip()
    return base + """
        , ORDER_LEVEL AS (
            SELECT
                NUMERO_PEDIDO,
                PLANTA,
                MAX(DT_REAL_FATURAMENTO)        AS DT_FAT,
                MAX(DT_PLANEJADA_FATURAMENTO)   AS DT_PLAN,
                SUM(PEDIDO_QTDE)                AS QTDE_PED,
                SUM(PEDIDO_QTDE_ATENDIDO)       AS QTDE_ATD,
                SUM(PEDIDO_QTDE_CANCELADO)      AS QTDE_CAN
            FROM BASE
            WHERE ID_STATUS_PEDIDO IN (1, 2)
            GROUP BY NUMERO_PEDIDO, PLANTA
        )
        , OTIF_CALC AS (
            SELECT
                NUMERO_PEDIDO,
                PLANTA,
                DT_PLAN,
                CASE WHEN DT_FAT IS NOT NULL AND DT_FAT <= DT_PLAN
                     THEN 1 ELSE 0 END AS ON_TIME_OK,
                CASE WHEN QTDE_PED - QTDE_CAN > 0
                          AND QTDE_ATD >= QTDE_PED - QTDE_CAN
                     THEN 1 ELSE 0 END AS IN_FULL_OK
            FROM ORDER_LEVEL
        )
    """


# ── Painel Executivo ──────────────────────────────────────────────────────────

def _exec_month_cte_where(ano, mes):
    """cte_where + params para um mês/ano específico (todos os status)."""
    yr, mo = int(ano), int(mes)
    last = _calendar.monthrange(yr, mo)[1]
    cte_filters = [
        "I.DB_PEDI_PRODUTO <> '999999917'",
        "I.db_pedi_situacao IN (0, 1, 2, 9)",
        "I.status_registro = 'ATIVO'",
        "CAST(P.DB_PED_DT_PREVENT AS DATE) >= CAST(? AS DATE)",
        "CAST(P.DB_PED_DT_PREVENT AS DATE) <= CAST(? AS DATE)",
    ]
    cte_where = "WHERE " + " AND ".join(cte_filters)
    params = [f"{yr}-{mo:02d}-01", f"{yr}-{mo:02d}-{last:02d}"]
    return cte_where, params


def _exec_months_cte_where(anos, meses, plantas=None, dias=None, grupos_cliente=None, responsaveis=None):
    """cte_where + params para múltiplos anos e múltiplos meses (+ filtro de planta, dia, grupo_cliente opcionais)."""
    if not isinstance(anos, list):
        anos = [anos]
    anos  = [int(a) for a in anos if a]
    meses = [int(m) for m in meses if m]
    if not anos:
        anos = [date.today().year]
    if not meses:
        meses = [date.today().month]
    yr_ph = ','.join('?' * len(anos))
    mo_ph = ','.join('?' * len(meses))
    cte_filters = [
        "I.DB_PEDI_PRODUTO <> '999999917'",
        "I.db_pedi_situacao IN (0, 1, 2, 9)",
        "I.status_registro = 'ATIVO'",
        f"YEAR(CAST(P.DB_PED_DT_PREVENT AS DATE)) IN ({yr_ph})",
        f"MONTH(CAST(P.DB_PED_DT_PREVENT AS DATE)) IN ({mo_ph})",
    ]
    params = anos + meses
    if plantas:
        ph = ','.join('?' * len(plantas))
        cte_filters.append(f"{_PLANTA_CASE} IN ({ph})")
        params += plantas
    if dias:
        dias_int = [int(d) for d in dias]
        d_ph = ','.join('?' * len(dias_int))
        cte_filters.append(f"DAY(CAST(P.DB_PED_DT_PREVENT AS DATE)) IN ({d_ph})")
        params += dias_int
    if grupos_cliente:
        ph = ','.join('?' * len(grupos_cliente))
        cte_filters.append(
            f"CAST(G.COD_GR_CLIENTE AS VARCHAR) + '-' + G.GRUPO_CLIENTE_DESC IN ({ph})"
        )
        params += grupos_cliente
    if responsaveis:
        ph = ','.join('?' * len(responsaveis))
        cte_filters.append(f"G.NM_NV1 IN ({ph})")
        params += responsaveis
    cte_where = "WHERE " + " AND ".join(cte_filters)
    return cte_where, params


def _exec_range_cte_where(dt_ini, dt_fim, plantas=None, grupos_cliente=None, responsaveis=None):
    """cte_where + params para um intervalo de datas livre (ex: semana) + filtro de planta/grupo_cliente opcional."""
    cte_filters = [
        "I.DB_PEDI_PRODUTO <> '999999917'",
        "I.db_pedi_situacao IN (0, 1, 2, 9)",
        "I.status_registro = 'ATIVO'",
        "CAST(P.DB_PED_DT_PREVENT AS DATE) >= CAST(? AS DATE)",
        "CAST(P.DB_PED_DT_PREVENT AS DATE) <= CAST(? AS DATE)",
    ]
    params = [dt_ini, dt_fim]
    if plantas:
        ph = ','.join('?' * len(plantas))
        cte_filters.append(f"{_PLANTA_CASE} IN ({ph})")
        params += plantas
    if grupos_cliente:
        ph = ','.join('?' * len(grupos_cliente))
        cte_filters.append(
            f"CAST(G.COD_GR_CLIENTE AS VARCHAR) + '-' + G.GRUPO_CLIENTE_DESC IN ({ph})"
        )
        params += grupos_cliente
    if responsaveis:
        ph = ','.join('?' * len(responsaveis))
        cte_filters.append(f"G.NM_NV1 IN ({ph})")
        params += responsaveis
    cte_where = "WHERE " + " AND ".join(cte_filters)
    return cte_where, params


_FR_TARGET = 96.0
_OTIF_TARGET = 85.0


def _get_exec_filters(args=None):
    args = args or request.args
    today = date.today()
    dt_ini = args.get('dt_ini', '').strip()
    dt_fim = args.get('dt_fim', '').strip()
    anos = args.getlist('ano') or [str(today.year)]
    meses = args.getlist('mes') or [str(today.month)]
    dias = [d.strip() for d in args.getlist('dia') if d.strip()] or None
    plantas = [p.strip() for p in args.getlist('planta') if p.strip()] or None
    grupos_cliente = [g.strip() for g in args.getlist('grupo_cliente') if g.strip()] or None
    responsaveis = [r.strip() for r in args.getlist('responsavel') if r.strip()] or None
    return {
        'dt_ini': dt_ini,
        'dt_fim': dt_fim,
        'anos': [str(a) for a in anos if str(a).strip()],
        'meses': [str(m) for m in meses if str(m).strip()],
        'dias': dias,
        'plantas': plantas,
        'grupos_cliente': grupos_cliente,
        'responsaveis': responsaveis,
    }


def _build_exec_fr_source(filters):
    if filters['dt_ini'] and filters['dt_fim']:
        cte_where, params = _exec_range_cte_where(
            filters['dt_ini'], filters['dt_fim'], filters['plantas'], filters['grupos_cliente'], filters.get('responsaveis')
        )
    else:
        cte_where, params = _exec_months_cte_where(
            filters['anos'], filters['meses'], filters['plantas'], filters['dias'], filters['grupos_cliente'], filters.get('responsaveis')
        )
    return _build_cte_sql(cte_where), params


def _build_exec_otif_diag_where(filters):
    where_parts = ["GRUPO_CLIENTE <> 'ARMAZÉM EXTERNO'", "CLUSTER_FILL_RATE_OTIF <> 'NÃO DEFINIDO'"]
    params = []
    if filters['dt_ini'] and filters['dt_fim']:
        where_parts.append("CAST(DATA_GRADE AS DATE) >= CAST(? AS DATE)")
        where_parts.append("CAST(DATA_GRADE AS DATE) <= CAST(? AS DATE)")
        params += [filters['dt_ini'], filters['dt_fim']]
    else:
        anos = [int(a) for a in filters['anos'] if a]
        meses = [int(m) for m in filters['meses'] if m]
        where_parts.append(f"YEAR(CAST(DATA_GRADE AS DATE)) IN ({','.join('?' * len(anos))})")
        params += anos
        where_parts.append(f"MONTH(CAST(DATA_GRADE AS DATE)) IN ({','.join('?' * len(meses))})")
        params += meses
        if filters['dias']:
            dias = [int(d) for d in filters['dias']]
            where_parts.append(f"DAY(CAST(DATA_GRADE AS DATE)) IN ({','.join('?' * len(dias))})")
            params += dias
    if filters['plantas']:
        where_parts.append(f"PLANTA IN ({','.join('?' * len(filters['plantas']))})")
        params += filters['plantas']
    if filters['grupos_cliente']:
        where_parts.append(f"NOME_GRUPO_ID_CLIENTE IN ({','.join('?' * len(filters['grupos_cliente']))})")
        params += filters['grupos_cliente']
    if filters.get('responsaveis'):
        where_parts.append(f"RESPONSAVEL IN ({','.join('?' * len(filters['responsaveis']))})")
        params += filters['responsaveis']
    return "WHERE " + " AND ".join(where_parts), params


def _fr_dimension_expr(dimension):
    if dimension == 'grupo_cliente':
        return "ISNULL(CAST(GRUPO_CLI AS VARCHAR(50)) + '-' + NOME_GRP_CLIENTE, 'Sem Grupo')"
    return "ISNULL(PLANTA, 'Sem Planta')"


def _otif_dimension_expr(dimension):
    if dimension == 'grupo_cliente':
        return "ISNULL(NOME_GRUPO_ID_CLIENTE, 'Sem Grupo')"
    return "ISNULL(PLANTA, 'Sem Planta')"


def _metric_label(kpi, otif_view='geral'):
    if kpi == 'fillrate':
        return 'Fill Rate'
    if otif_view == 'cif':
        return 'OTIF CIF'
    if otif_view == 'fob':
        return 'OTIF FOB'
    return 'OTIF Geral'


def _action_label(kpi, otif_view='geral', dimension='planta'):
    if kpi == 'fillrate':
        return 'Priorizar cliente/grupo crítico' if dimension == 'grupo_cliente' else 'Atuar pedidos vencidos'
    if otif_view == 'cif':
        return 'Revisar remessas CIF'
    if otif_view == 'fob':
        return 'Verificar atraso FOB'
    return 'Priorizar cliente/grupo crítico' if dimension == 'grupo_cliente' else 'Revisar remessas OTIF'


def _pct(numerator, denominator):
    return min(100.0, float(numerator) / float(denominator) * 100.0) if float(denominator or 0) > 0 else 0.0


def _exec_diag_pareto_rows(filters, kpi='fillrate', dimension='planta', otif_view='geral', cursor=None):
    own_cursor = False
    if cursor is None:
        conn = get_connection()
        cursor = conn.cursor()
        own_cursor = True
    try:
        if kpi == 'fillrate':
            cte_sql, params = _build_exec_fr_source(filters)
            dim_expr = _fr_dimension_expr(dimension)
            query = cte_sql + f"""
                SELECT
                    {dim_expr} AS DIMENSION_NAME,
                    ISNULL(SUM(PEDIDO_QTDE) - SUM(PEDIDO_QTDE_CANCELADO), 0) AS DENOMINATOR,
                    ISNULL(SUM(PEDIDO_QTDE_ATENDIDO), 0) AS NUMERATOR
                FROM BASE
                WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)
                  AND CANAL <> 'NÃO DEFINIDO'
                GROUP BY {dim_expr}
                HAVING ISNULL(SUM(PEDIDO_QTDE) - SUM(PEDIDO_QTDE_CANCELADO), 0) > 0
            """
            cursor.execute(query, params)
        else:
            where, params = _build_exec_otif_diag_where(filters)
            dim_expr = _otif_dimension_expr(dimension)
            if otif_view == 'cif':
                denominator_expr = "SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END)"
                numerator_expr = "SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN OTIF_CIF ELSE 0 END)"
            elif otif_view == 'fob':
                denominator_expr = "SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END)"
                numerator_expr = "SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN OTIF_FOB ELSE 0 END)"
            else:
                denominator_expr = "COUNT(*)"
                numerator_expr = "SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN OTIF_FOB ELSE OTIF_CIF END)"
            query = _OTIF2_BASE_CTE + f"""
                SELECT
                    {dim_expr} AS DIMENSION_NAME,
                    ISNULL({denominator_expr}, 0) AS DENOMINATOR,
                    ISNULL({numerator_expr}, 0) AS NUMERATOR
                FROM base
                {where}
                GROUP BY {dim_expr}
                HAVING ISNULL({denominator_expr}, 0) > 0
            """
            cursor.execute(query, params)

        raw_rows = []
        for row in cursor.fetchall():
            dimension_name = str(row[0] or 'Sem dimensão')
            denominator = float(row[1] or 0)
            numerator = float(row[2] or 0)
            if denominator <= 0:
                continue
            raw_rows.append({
                'dimension_name': dimension_name,
                'denominator': denominator,
                'numerator': numerator,
                'kpi_value': _pct(numerator, denominator),
            })

        _target = _FR_TARGET if kpi == 'fillrate' else _OTIF_TARGET
        total_denominator = sum(r['denominator'] for r in raw_rows)
        for r in raw_rows:
            r['target'] = _target
            r['loss_value'] = max(0.0, r['denominator'] * (_target / 100.0) - r['numerator'])
            r['gap_vs_target'] = r['kpi_value'] - _target
            r['impact_pp'] = (r['loss_value'] / total_denominator * 100.0) if total_denominator > 0 else 0.0
            r['selected_kpi'] = kpi
            r['selected_dimension'] = dimension
            r['otif_view'] = otif_view if kpi == 'otif' else None
            r['metric_label'] = _metric_label(kpi, otif_view)
            r['action_label'] = _action_label(kpi, otif_view, dimension)

        ranked = sorted(raw_rows, key=lambda r: (r['loss_value'], r['impact_pp'], r['denominator']), reverse=True)
        total_loss = sum(r['loss_value'] for r in ranked)
        cumulative = 0.0
        for idx, r in enumerate(ranked, start=1):
            share = (r['loss_value'] / total_loss * 100.0) if total_loss > 0 else 0.0
            cumulative += share
            r['loss_share_pct'] = round(share, 2)
            r['cumulative_loss_pct'] = round(cumulative, 2)
            r['rank'] = idx
            r['kpi_value'] = round(r['kpi_value'], 2)
            r['target'] = round(r['target'], 2)
            r['gap_vs_target'] = round(r['gap_vs_target'], 2)
            r['denominator'] = round(r['denominator'], 2)
            r['numerator'] = round(r['numerator'], 2)
            r['loss_value'] = round(r['loss_value'], 2)
            r['impact_pp'] = round(r['impact_pp'], 2)
        return ranked
    finally:
        if own_cursor:
            try:
                cursor.close()
            except Exception:
                pass


def _build_exec_priority_rows(filters, cursor=None):
    own_cursor = False
    if cursor is None:
        conn = get_connection()
        cursor = conn.cursor()
        own_cursor = True
    try:
        candidates = []

        # Fill Rate por planta + grupo cliente — with monetary loss and volume
        fr_cte_sql, fr_params = _build_exec_fr_source(filters)
        cursor.execute(fr_cte_sql + """
            SELECT
                ISNULL(PLANTA, 'Sem Planta') AS PLANTA,
                ISNULL(CAST(GRUPO_CLI AS VARCHAR(50)) + '-' + NOME_GRP_CLIENTE, 'Sem Grupo') AS GRUPO_CLIENTE,
                ISNULL(SUM(PEDIDO_QTDE) - SUM(PEDIDO_QTDE_CANCELADO), 0) AS DENOMINATOR,
                ISNULL(SUM(PEDIDO_QTDE_ATENDIDO), 0) AS NUMERATOR,
                ISNULL(SUM(CASE WHEN (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO) > PEDIDO_QTDE_ATENDIDO
                    THEN PRECO_UNIT * ((PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO) - PEDIDO_QTDE_ATENDIDO)
                    ELSE 0 END), 0) AS PERDA_MONETARIA,
                ISNULL(SUM(CASE WHEN (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO) > PEDIDO_QTDE_ATENDIDO
                    THEN (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO) - PEDIDO_QTDE_ATENDIDO
                    ELSE 0 END), 0) AS VOL_NAO_ATENDIDO
            FROM BASE
            WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)
              AND CANAL <> 'NÃO DEFINIDO'
            GROUP BY PLANTA, CAST(GRUPO_CLI AS VARCHAR(50)) + '-' + NOME_GRP_CLIENTE
            HAVING ISNULL(SUM(PEDIDO_QTDE) - SUM(PEDIDO_QTDE_CANCELADO), 0) > 0
        """, fr_params)
        fr_rows = cursor.fetchall()
        fr_total_den = sum(float(r[2] or 0) for r in fr_rows)
        for row in fr_rows:
            planta = str(row[0] or 'Sem Planta')
            grupo = str(row[1] or 'Sem Grupo')
            denominator = float(row[2] or 0)
            numerator = float(row[3] or 0)
            perda_monetaria = float(row[4] or 0)
            vol_nao_atendido = float(row[5] or 0)
            if denominator <= 0:
                continue
            pp_gap = max(0.0, _FR_TARGET - _pct(numerator, denominator))
            loss_value = max(0.0, denominator * (_FR_TARGET / 100.0) - numerator)
            if loss_value <= 0:
                continue
            # Score weighted by monetary value (fallback to volume)
            weight = perda_monetaria if perda_monetaria > 0 else vol_nao_atendido
            score = pp_gap * weight
            candidates.append({
                'planta': planta,
                'grupo_cliente': grupo,
                'indicador': 'Fill Rate',
                'valor_atual': round(_pct(numerator, denominator), 2),
                'meta': _FR_TARGET,
                'gap_pp': round(pp_gap, 2),
                'impact_pp': round((loss_value / fr_total_den * 100.0) if fr_total_den > 0 else 0.0, 2),
                'loss_value': round(loss_value, 2),
                'denominator': round(denominator, 2),
                'numerator': round(numerator, 2),
                'perda_monetaria': round(perda_monetaria, 2),
                'vol_nao_atendido': round(vol_nao_atendido, 0),
                'score': round(score, 2),
                'acao_sugerida': _action_label('fillrate', 'geral', 'grupo_cliente'),
            })

        # OTIF por planta + grupo cliente (geral/cif/fob) — with volume weighting
        otif_where, otif_params = _build_exec_otif_diag_where(filters)
        cursor.execute(_OTIF2_BASE_CTE + f"""
            SELECT
                ISNULL(PLANTA, 'Sem Planta') AS PLANTA,
                ISNULL(NOME_GRUPO_ID_CLIENTE, 'Sem Grupo') AS GRUPO_CLIENTE,
                COUNT(*) AS DEN_GERAL,
                ISNULL(SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN OTIF_FOB ELSE OTIF_CIF END), 0) AS NUM_GERAL,
                SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END) AS DEN_CIF,
                ISNULL(SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN OTIF_CIF ELSE 0 END), 0) AS NUM_CIF,
                SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END) AS DEN_FOB,
                ISNULL(SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN OTIF_FOB ELSE 0 END), 0) AS NUM_FOB,
                ISNULL(SUM(CASE WHEN (CASE WHEN TIPO_FRETE='FOB' THEN OTIF_FOB ELSE OTIF_CIF END)=0
                    THEN VOL_LIQUIDO ELSE 0 END), 0) AS VOL_AFETADO_GERAL,
                ISNULL(SUM(CASE WHEN TIPO_FRETE='CIF' AND OTIF_CIF=0
                    THEN VOL_LIQUIDO ELSE 0 END), 0) AS VOL_AFETADO_CIF,
                ISNULL(SUM(CASE WHEN TIPO_FRETE='FOB' AND OTIF_FOB=0
                    THEN VOL_LIQUIDO ELSE 0 END), 0) AS VOL_AFETADO_FOB,
                -- OT/IF breakdown for action suggestion
                ISNULL(SUM(CASE WHEN TIPO_FRETE='CIF' THEN OT_CIF ELSE 0 END), 0) AS OT_OK_CIF,
                ISNULL(SUM(CASE WHEN TIPO_FRETE='FOB' THEN OT_FOB ELSE 0 END), 0) AS OT_OK_FOB,
                ISNULL(SUM(INFULL), 0) AS IF_OK_TOTAL
            FROM base
            {otif_where}
              AND (
                  (TIPO_FRETE = 'FOB' AND CAST(DATA_GRADE AS DATE) < CAST(GETDATE() AS DATE))
                  OR
                  (TIPO_FRETE = 'CIF' AND CAST(DATA_AGENDA_ENTREGA AS DATE) < CAST(GETDATE() AS DATE))
              )
            GROUP BY PLANTA, NOME_GRUPO_ID_CLIENTE
        """, otif_params)
        otif_rows = cursor.fetchall()
        total_den_geral = sum(float(r[2] or 0) for r in otif_rows)
        total_den_cif = sum(float(r[4] or 0) for r in otif_rows)
        total_den_fob = sum(float(r[6] or 0) for r in otif_rows)
        for row in otif_rows:
            planta = str(row[0] or 'Sem Planta')
            grupo = str(row[1] or 'Sem Grupo')
            # OT/IF breakdown for smart action suggestion
            den_cif_r = float(row[4] or 0)
            den_fob_r = float(row[6] or 0)
            ot_ok_cif = float(row[11] or 0)
            ot_ok_fob = float(row[12] or 0)
            if_ok_total = float(row[13] or 0)
            den_total_r = den_cif_r + den_fob_r
            ot_pct = _pct(ot_ok_cif + ot_ok_fob, den_total_r) if den_total_r > 0 else 100.0
            if_pct = _pct(if_ok_total, den_total_r) if den_total_r > 0 else 100.0
            # Determine offender: OT or IF
            if ot_pct < if_pct:
                acao = 'Corrigir pontualidade'
            elif if_pct < ot_pct:
                acao = 'Completar volume'
            else:
                acao = 'Revisar prazo e volume'

            metrics = [
                ('OTIF CIF', 'cif', den_cif_r, float(row[5] or 0), total_den_cif, float(row[9] or 0)),
                ('OTIF FOB', 'fob', den_fob_r, float(row[7] or 0), total_den_fob, float(row[10] or 0)),
            ]
            for label, view_name, denominator, numerator, total_den, vol_afetado in metrics:
                if denominator <= 0:
                    continue
                pp_gap = max(0.0, _OTIF_TARGET - _pct(numerator, denominator))
                loss_value = max(0.0, denominator * (_OTIF_TARGET / 100.0) - numerator)
                if loss_value <= 0:
                    continue
                # Score weighted by affected volume
                score = pp_gap * vol_afetado if vol_afetado > 0 else pp_gap * loss_value
                candidates.append({
                    'planta': planta,
                    'grupo_cliente': grupo,
                    'indicador': label,
                    'valor_atual': round(_pct(numerator, denominator), 2),
                    'meta': _OTIF_TARGET,
                    'gap_pp': round(pp_gap, 2),
                    'impact_pp': round((loss_value / total_den * 100.0) if total_den > 0 else 0.0, 2),
                    'loss_value': round(loss_value, 2),
                    'denominator': round(denominator, 2),
                    'numerator': round(numerator, 2),
                    'vol_afetado': round(vol_afetado, 0),
                    'perda_monetaria': None,
                    'vol_nao_atendido': None,
                    'score': round(score, 2),
                    'acao_sugerida': acao,
                })

        # Normalize scores within each indicator for fair cross-KPI ranking
        # (FR uses monetary R$ values, OTIF uses volume — scales differ by 100x+)
        from collections import defaultdict
        by_ind = defaultdict(list)
        for c in candidates:
            by_ind[c['indicador']].append(c)
        for ind, items in by_ind.items():
            max_s = max((i['score'] for i in items), default=1.0) or 1.0
            for i in items:
                i['_norm_score'] = i['score'] / max_s

        # Rank by normalized score (primary), gap_pp (secondary), impact_pp (tertiary)
        ranked = sorted(candidates, key=lambda r: (r.get('_norm_score', 0), r['gap_pp'], r['impact_pp']), reverse=True)
        for idx, row in enumerate(ranked, start=1):
            row['prioridade'] = idx

        # ── Trend indicator: compare current period vs 4 weeks ago ──
        _enrich_priority_trends(ranked[:10], filters, cursor)

        return ranked
    finally:
        if own_cursor:
            try:
                cursor.close()
            except Exception:
                pass


def _enrich_priority_trends(rows, filters, cursor):
    """Add trend_delta_pp and trend_direction to each priority row.
    Compares the metric for the last 4 weeks vs the previous 4 weeks."""
    if not rows:
        return
    today = date.today()
    # Current window: last 4 weeks
    cur_end = today
    cur_start = today - timedelta(days=28)
    # Previous window: 4 weeks before that
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=27)

    for row in rows:
        try:
            planta = row['planta']
            grupo = row['grupo_cliente']
            indicador = row['indicador']

            if indicador == 'Fill Rate':
                # Build FR CTE with wide date range covering both windows
                trend_fr_filters = {'anos': [], 'meses': [], 'dt_ini': prev_start.isoformat(), 'dt_fim': cur_end.isoformat(), 'dias': None, 'plantas': None, 'grupos_cliente': None}
                fr_trend_cte, fr_trend_params = _build_exec_fr_source(trend_fr_filters)
                q = fr_trend_cte + """
                    SELECT
                        SUM(CASE WHEN DT_PLANEJADA_FATURAMENTO >= CAST(? AS DATE) AND DT_PLANEJADA_FATURAMENTO < CAST(? AS DATE) THEN PEDIDO_QTDE_ATENDIDO ELSE 0 END) AS NUM_CUR,
                        SUM(CASE WHEN DT_PLANEJADA_FATURAMENTO >= CAST(? AS DATE) AND DT_PLANEJADA_FATURAMENTO < CAST(? AS DATE) THEN (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO) ELSE 0 END) AS DEN_CUR,
                        SUM(CASE WHEN DT_PLANEJADA_FATURAMENTO >= CAST(? AS DATE) AND DT_PLANEJADA_FATURAMENTO < CAST(? AS DATE) THEN PEDIDO_QTDE_ATENDIDO ELSE 0 END) AS NUM_PREV,
                        SUM(CASE WHEN DT_PLANEJADA_FATURAMENTO >= CAST(? AS DATE) AND DT_PLANEJADA_FATURAMENTO < CAST(? AS DATE) THEN (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO) ELSE 0 END) AS DEN_PREV
                    FROM BASE
                    WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)
                      AND CANAL <> 'NÃO DEFINIDO'
                      AND ISNULL(PLANTA, '') = ?
                      AND ISNULL(CAST(GRUPO_CLI AS VARCHAR(50)) + '-' + NOME_GRP_CLIENTE, '') = ?
                """
                extra_params = [
                    cur_start.isoformat(), cur_end.isoformat(),
                    cur_start.isoformat(), cur_end.isoformat(),
                    prev_start.isoformat(), (prev_end + timedelta(days=1)).isoformat(),
                    prev_start.isoformat(), (prev_end + timedelta(days=1)).isoformat(),
                    planta, grupo,
                ]
                cursor.execute(q, fr_trend_params + extra_params)
            else:
                # OTIF trend
                frete_filter = ""
                ot_col = "CASE WHEN TIPO_FRETE='FOB' THEN OTIF_FOB ELSE OTIF_CIF END"
                if 'FOB' in indicador:
                    frete_filter = "AND TIPO_FRETE = 'FOB'"
                    ot_col = "OTIF_FOB"
                elif 'CIF' in indicador:
                    frete_filter = "AND TIPO_FRETE = 'CIF'"
                    ot_col = "OTIF_CIF"

                q = _OTIF2_BASE_CTE + f"""
                    SELECT
                        SUM(CASE WHEN DATA_GRADE >= ? AND DATA_GRADE < ? THEN {ot_col} ELSE 0 END) AS NUM_CUR,
                        SUM(CASE WHEN DATA_GRADE >= ? AND DATA_GRADE < ? THEN 1 ELSE 0 END) AS DEN_CUR,
                        SUM(CASE WHEN DATA_GRADE >= ? AND DATA_GRADE < ? THEN {ot_col} ELSE 0 END) AS NUM_PREV,
                        SUM(CASE WHEN DATA_GRADE >= ? AND DATA_GRADE < ? THEN 1 ELSE 0 END) AS DEN_PREV
                    FROM base
                    WHERE ISNULL(PLANTA, '') = ?
                      AND ISNULL(NOME_GRUPO_ID_CLIENTE, '') = ?
                      AND GRUPO_CLIENTE <> 'ARMAZÉM EXTERNO'
                      AND CLUSTER_FILL_RATE_OTIF <> 'NÃO DEFINIDO'
                      {frete_filter}
                """
                params = [
                    cur_start.isoformat(), cur_end.isoformat(),
                    cur_start.isoformat(), cur_end.isoformat(),
                    prev_start.isoformat(), prev_end.isoformat(),
                    prev_start.isoformat(), prev_end.isoformat(),
                    planta, grupo,
                ]
                cursor.execute(q, params)

            r = cursor.fetchone()
            if r:
                num_cur, den_cur = float(r[0] or 0), float(r[1] or 0)
                num_prev, den_prev = float(r[2] or 0), float(r[3] or 0)
                pct_cur = _pct(num_cur, den_cur) if den_cur > 0 else None
                pct_prev = _pct(num_prev, den_prev) if den_prev > 0 else None
                if pct_cur is not None and pct_prev is not None and den_prev >= 5:
                    delta = round(pct_cur - pct_prev, 1)
                    row['trend_delta_pp'] = delta
                    row['trend_direction'] = 'up' if delta > 0.5 else ('down' if delta < -0.5 else 'flat')
                else:
                    row['trend_delta_pp'] = None
                    row['trend_direction'] = None
            else:
                row['trend_delta_pp'] = None
                row['trend_direction'] = None
        except Exception:
            row['trend_delta_pp'] = None
            row['trend_direction'] = None


@app.route('/api/executivo/resumo')
def get_executivo_resumo():
    """KPIs globais para o(s) mês(es) selecionado(s), ou para um intervalo de datas (ex: semana): FR (qtdes) + OTIF."""
    today   = date.today()
    dt_ini  = request.args.get('dt_ini', '').strip()
    dt_fim  = request.args.get('dt_fim', '').strip()
    plantas = [p.strip() for p in request.args.getlist('planta') if p.strip()]
    dias    = [d.strip() for d in request.args.getlist('dia') if d.strip()]
    grupos_cliente = [g.strip() for g in request.args.getlist('grupo_cliente') if g.strip()] or None

    if dt_ini and dt_fim:
        cte_where, params = _exec_range_cte_where(dt_ini, dt_fim, plantas, grupos_cliente)
    else:
        anos  = request.args.getlist('ano') or [today.year]
        meses = request.args.getlist('mes') or [today.month]
        cte_where, params = _exec_months_cte_where(anos, meses, plantas, dias or None, grupos_cliente)
    full_cte = _build_otif_cte(cte_where).rstrip()

    query = full_cte + """
        SELECT
            (SELECT ISNULL(SUM(PEDIDO_QTDE),           0) FROM BASE
             WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE) AND CANAL <> 'N\u00c3O DEFINIDO')      AS QTDE_PEDIDA,
            (SELECT ISNULL(SUM(PEDIDO_QTDE_ATENDIDO),  0) FROM BASE
             WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE) AND CANAL <> 'N\u00c3O DEFINIDO')      AS QTDE_ATENDIDA,
            (SELECT ISNULL(SUM(PEDIDO_QTDE_CANCELADO), 0) FROM BASE
             WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE) AND CANAL <> 'N\u00c3O DEFINIDO')      AS QTDE_CANCELADA,
            (SELECT COUNT(DISTINCT NUMERO_PEDIDO)          FROM BASE
             WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE) AND CANAL <> 'N\u00c3O DEFINIDO'
             AND ID_STATUS_PEDIDO <> '9')                                                               AS TOTAL_PEDIDOS,
            (SELECT COUNT(*)                               FROM OTIF_CALC) AS OTIF_AVALIADOS,
            (SELECT ISNULL(SUM(ON_TIME_OK), 0)             FROM OTIF_CALC) AS ON_TIME,
            (SELECT ISNULL(SUM(IN_FULL_OK), 0)             FROM OTIF_CALC) AS IN_FULL,
            (SELECT ISNULL(SUM(CASE WHEN ON_TIME_OK = 1 AND IN_FULL_OK = 1
                                    THEN 1 ELSE 0 END), 0) FROM OTIF_CALC) AS OTIF
    """

    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        row  = cursor.fetchone()
        cols = [c[0] for c in cursor.description]
        return jsonify(dict(zip(cols, [str(v) if v is not None else '0' for v in row])))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/executivo/scorecard')
def get_executivo_scorecard():
    """FR + OTIF por empresa para o(s) mês(es) selecionado(s), ou para um intervalo de datas (ex: semana)."""
    today   = date.today()
    dt_ini  = request.args.get('dt_ini', '').strip()
    dt_fim  = request.args.get('dt_fim', '').strip()
    plantas = [p.strip() for p in request.args.getlist('planta') if p.strip()]

    if dt_ini and dt_fim:
        cte_where, params = _exec_range_cte_where(dt_ini, dt_fim, plantas)
    else:
        anos  = request.args.getlist('ano') or [today.year]
        meses = request.args.getlist('mes') or [today.month]
        cte_where, params = _exec_months_cte_where(anos, meses, plantas)
    full_cte = _build_otif_cte(cte_where).rstrip()

    query = full_cte + """
        , FR_BY_EMP AS (
            SELECT
                ISNULL(PLANTA, 'Sem Planta')            AS PLANTA,
                ISNULL(SUM(PEDIDO_QTDE), 0)             AS QTDE_PED,
                ISNULL(SUM(PEDIDO_QTDE_ATENDIDO), 0)    AS QTDE_ATD,
                ISNULL(SUM(PEDIDO_QTDE_CANCELADO), 0)   AS QTDE_CAN
            FROM BASE
            WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)
            GROUP BY PLANTA
        )
        , OTIF_BY_EMP AS (
            SELECT
                ISNULL(PLANTA, 'Sem Planta')            AS PLANTA,
                COUNT(*)                                AS AVALIADOS,
                ISNULL(SUM(ON_TIME_OK), 0)              AS ON_TIME,
                ISNULL(SUM(IN_FULL_OK), 0)              AS IN_FULL,
                ISNULL(SUM(CASE WHEN ON_TIME_OK = 1 AND IN_FULL_OK = 1
                                THEN 1 ELSE 0 END), 0)  AS OTIF
            FROM OTIF_CALC GROUP BY PLANTA
        )
        SELECT
            COALESCE(f.PLANTA, o.PLANTA)               AS EMPRESA,
            ISNULL(f.QTDE_PED, 0)                      AS QTDE_PEDIDA,
            ISNULL(f.QTDE_ATD, 0)                      AS QTDE_ATENDIDA,
            ISNULL(f.QTDE_CAN, 0)                      AS QTDE_CANCELADA,
            ISNULL(o.AVALIADOS, 0)                     AS OTIF_AVALIADOS,
            ISNULL(o.ON_TIME, 0)                       AS ON_TIME,
            ISNULL(o.IN_FULL, 0)                       AS IN_FULL,
            ISNULL(o.OTIF, 0)                          AS OTIF
        FROM FR_BY_EMP f
        FULL OUTER JOIN OTIF_BY_EMP o ON f.PLANTA = o.PLANTA
        ORDER BY COALESCE(f.PLANTA, o.PLANTA)
    """

    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, [str(v) if v is not None else '0' for v in row]))
                for row in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/executivo/diagnostico/pareto')
def get_executivo_pareto():
    filters = _get_exec_filters(request.args)
    kpi = request.args.get('kpi', 'fillrate').strip().lower()
    dimension = request.args.get('dimension', 'planta').strip().lower()
    otif_view = request.args.get('otif_view', 'geral').strip().lower()
    if kpi not in ('fillrate', 'otif'):
        return jsonify({'error': 'kpi inválido'}), 400
    if dimension not in ('planta', 'grupo_cliente'):
        return jsonify({'error': 'dimension inválida'}), 400
    if otif_view not in ('geral', 'cif', 'fob'):
        return jsonify({'error': 'otif_view inválido'}), 400
    try:
        rows = _exec_diag_pareto_rows(filters, kpi, dimension, otif_view)
        return jsonify(rows)
    except Exception as e:
        _log.error("[PARETO] %s", e, exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/executivo/diagnostico/acao-prioritaria')
def get_executivo_acao_prioritaria():
    filters = _get_exec_filters(request.args)
    configs = [
        ('fillrate', 'planta', 'geral'),
        ('fillrate', 'grupo_cliente', 'geral'),
        ('otif', 'planta', 'geral'),
        ('otif', 'grupo_cliente', 'geral'),
        ('otif', 'planta', 'cif'),
        ('otif', 'grupo_cliente', 'cif'),
        ('otif', 'planta', 'fob'),
        ('otif', 'grupo_cliente', 'fob'),
    ]
    try:
        conn = get_connection()
        cursor = conn.cursor()
        best = None
        for kpi, dimension, otif_view in configs:
            rows = _exec_diag_pareto_rows(filters, kpi, dimension, otif_view, cursor=cursor)
            if not rows:
                continue
            top = rows[0]
            if top['loss_value'] <= 0:
                continue
            candidate = dict(top)
            candidate['scope_label'] = 'Grupo Cliente' if dimension == 'grupo_cliente' else 'Planta'
            if best is None or candidate['impact_pp'] > best['impact_pp'] or (
                candidate['impact_pp'] == best['impact_pp'] and candidate['loss_value'] > best['loss_value']
            ):
                best = candidate
        if not best:
            return jsonify({
                'dimension_name': 'Sem ofensores relevantes',
                'scope_label': 'Planta',
                'metric_label': 'Fill Rate',
                'kpi_value': 100.0,
                'impact_pp': 0.0,
                'action_label': 'Monitorar operação',
                'loss_value': 0.0,
                'gap_vs_target': 4.0,
            })
        return jsonify(best)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/executivo/diagnostico/prioridades')
def get_executivo_prioridades():
    filters = _get_exec_filters(request.args)
    limit = max(5, min(10, int(request.args.get('limit', 8))))
    try:
        rows = _build_exec_priority_rows(filters)[:limit]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/executivo/diagnostico/export')
def get_executivo_export():
    """Export overdue problematic shipments/orders as formatted Excel (.xlsx)."""
    from flask import Response
    import io
    from openpyxl import Workbook
    from openpyxl.worksheet.table import Table, TableStyleInfo
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Font, Alignment, PatternFill

    filters = _get_exec_filters(request.args)
    planta = request.args.get('planta', '').strip()
    grupo_cliente = request.args.get('grupo_cliente', '').strip()
    indicador = request.args.get('indicador', '').strip().lower()
    if not planta or not grupo_cliente:
        return jsonify({'error': 'planta e grupo_cliente obrigat\u00f3rios'}), 400
    try:
        conn = get_connection()
        cur = conn.cursor()
        if 'fill' in indicador:
            cte_sql, params = _build_exec_fr_source(filters)
            # Somente pedidos vencidos (DT_PLANEJADA < hoje) e com falta
            query = cte_sql + """
                SELECT
                    NUMERO_PEDIDO, PLANTA, NOME_GRP_CLIENTE,
                    DT_PLANEJADA_FATURAMENTO, DT_REAL_FATURAMENTO, STATUS_PEDIDO,
                    PEDIDO_QTDE, PEDIDO_QTDE_ATENDIDO, PEDIDO_QTDE_CANCELADO,
                    (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO - PEDIDO_QTDE_ATENDIDO) AS QTDE_FALTANTE,
                    CANAL, RESPONSAVEL
                FROM BASE
                WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)
                  AND CANAL <> 'N\u00c3O DEFINIDO'
                  AND PLANTA = ?
                  AND (PEDIDO_QTDE_ATENDIDO < (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO))
                ORDER BY (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO - PEDIDO_QTDE_ATENDIDO) DESC
            """
            params.append(planta)
            cur.execute(query, params)
            cols = ['Pedido', 'Planta', 'Grupo Cliente', 'Dt. Planejada', 'Dt. Faturamento',
                    'Status', 'Qtde Pedida', 'Qtde Atendida', 'Qtde Cancelada', 'Qtde Faltante',
                    'Canal', 'Responsavel']
        else:
            # OTIF export — somente remessas j\u00e1 vencidas
            # FOB: DATA_GRADE < hoje | CIF: DATA_AGENDA_ENTREGA < hoje
            where, params = _build_exec_otif_diag_where(filters)
            query = _OTIF2_BASE_CTE + f"""
                SELECT
                    REMESSA, PEDIDO_MERCANET, PLANTA, NOME_GRUPO_ID_CLIENTE,
                    DATA_GRADE, DATA_AGENDA_ENTREGA,
                    CASE WHEN TIPO_FRETE='FOB' THEN DATA_CHEGADA_PLANTA
                         ELSE DATA_CHEGADA_DESTINO END AS DATA_CHEGADA,
                    TIPO_FRETE, TRANSPORTADORA,
                    CASE WHEN TIPO_FRETE='FOB' THEN OT_FOB ELSE OT_CIF END AS ON_TIME,
                    INFULL AS IN_FULL,
                    CASE WHEN TIPO_FRETE='FOB' THEN OTIF_FOB ELSE OTIF_CIF END AS OTIF_OK,
                    CLUSTER_FILL_RATE_OTIF
                FROM base
                {where}
                  AND PLANTA = ?
                  AND (CASE WHEN TIPO_FRETE='FOB' THEN OTIF_FOB ELSE OTIF_CIF END) = 0
                  AND (
                      (TIPO_FRETE = 'FOB' AND CAST(DATA_GRADE AS DATE) < CAST(GETDATE() AS DATE))
                      OR
                      (TIPO_FRETE = 'CIF' AND CAST(DATA_AGENDA_ENTREGA AS DATE) < CAST(GETDATE() AS DATE))
                  )
                ORDER BY DATA_GRADE DESC
            """
            params.append(planta)
            cur.execute(query, params)
            cols = ['Remessa', 'Pedido', 'Planta', 'Grupo Cliente',
                    'Dt. Grade', 'Dt. Agenda Entrega', 'Dt. Chegada',
                    'Tipo Frete', 'Transportadora',
                    'On Time', 'In Full', 'OTIF', 'Canal']

        rows = cur.fetchall()

        # --- Build formatted Excel ---
        wb = Workbook()
        ws = wb.active
        ws.title = 'Export'

        hdr_font = Font(bold=True, color='FFFFFF', size=10)
        hdr_fill = PatternFill(start_color='2E3B4E', end_color='2E3B4E', fill_type='solid')
        hdr_align = Alignment(horizontal='center', vertical='center', wrap_text=True)

        # Header row
        for col_idx, col_name in enumerate(cols, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = hdr_font
            cell.fill = hdr_fill
            cell.alignment = hdr_align

        # Data rows
        for row_idx, row in enumerate(rows, 2):
            for col_idx, val in enumerate(row, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.alignment = Alignment(horizontal='center', vertical='center')

        # Auto-fit column widths
        for col_idx, col_name in enumerate(cols, 1):
            max_len = len(str(col_name))
            for row_idx in range(2, min(len(rows) + 2, 102)):
                cell_val = ws.cell(row=row_idx, column=col_idx).value
                if cell_val is not None:
                    max_len = max(max_len, len(str(cell_val)))
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 3, 30)

        # Add Excel Table with auto-filter and striped rows
        if rows:
            table_ref = f"A1:{get_column_letter(len(cols))}{len(rows) + 1}"
            tab = Table(displayName='DadosExport', ref=table_ref)
            tab.tableStyleInfo = TableStyleInfo(
                name='TableStyleMedium2', showFirstColumn=False,
                showLastColumn=False, showRowStripes=True, showColumnStripes=False
            )
            ws.add_table(tab)
        else:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}1"

        # Freeze header
        ws.freeze_panes = 'A2'

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f'export_{planta}_{indicador}.xlsx'
        return Response(
            output.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        _log.error("[EXPORT] %s", e, exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/executivo/diagnostico/drill-down')
def get_executivo_drill_down():
    """Drill-down for a specific planta x grupo_cliente x indicador."""
    filters = _get_exec_filters(request.args)
    planta = request.args.get('planta', '').strip()
    grupo_cliente = request.args.get('grupo_cliente', '').strip()
    indicador = request.args.get('indicador', '').strip()
    if not planta or not grupo_cliente or not indicador:
        return jsonify({'error': 'planta, grupo_cliente e indicador obrigatórios'}), 400
    try:
        conn = get_connection()
        cur = conn.cursor()
        result = {'indicador': indicador, 'planta': planta, 'grupo_cliente': grupo_cliente}

        if indicador == 'Fill Rate':
            # FR drill-down: breakdown by canal
            fr_cte, fr_params = _build_exec_fr_source(filters)
            cur.execute(fr_cte + """
                SELECT
                    ISNULL(CANAL, 'Sem Canal') AS CANAL,
                    ISNULL(SUM(PEDIDO_QTDE) - SUM(PEDIDO_QTDE_CANCELADO), 0) AS DEN,
                    ISNULL(SUM(PEDIDO_QTDE_ATENDIDO), 0) AS NUM
                FROM BASE
                WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)
                  AND CANAL <> 'NÃO DEFINIDO'
                  AND ISNULL(PLANTA, '') = ?
                  AND ISNULL(CAST(GRUPO_CLI AS VARCHAR(50)) + '-' + NOME_GRP_CLIENTE, '') = ?
                GROUP BY CANAL
                HAVING ISNULL(SUM(PEDIDO_QTDE) - SUM(PEDIDO_QTDE_CANCELADO), 0) > 0
            """, fr_params + [planta, grupo_cliente])
            canais = []
            for row in cur.fetchall():
                den = float(row[1] or 0)
                num = float(row[2] or 0)
                falhas = max(0, den - num)
                canais.append({
                    'nome': str(row[0]),
                    'valor_pct': round(_pct(num, den), 1),
                    'falhas': int(round(falhas)),
                    'denominador': int(round(den)),
                })
            result['por_canal'] = sorted(canais, key=lambda x: x['valor_pct'])
            result['componentes'] = None
            result['por_transportadora'] = None

            # Detail records (individual failed orders - overdue with gap)
            cte_sql2, fr_params2 = _build_exec_fr_source(filters)
            cur.execute(cte_sql2 + """
                SELECT TOP 30
                    NUMERO_PEDIDO,
                    (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO) AS VOL_PED,
                    PEDIDO_QTDE_ATENDIDO AS VOL_FAT,
                    (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO - PEDIDO_QTDE_ATENDIDO) AS GAP_VOL,
                    (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO - PEDIDO_QTDE_ATENDIDO) * ISNULL(PRECO_UNIT, 0) AS PERDA_VLR,
                    CANAL,
                    PLANTA,
                    NOME_GRP_CLIENTE,
                    CONVERT(VARCHAR(10), DT_PLANEJADA_FATURAMENTO, 120) AS DT_PLAN,
                    STATUS_PEDIDO,
                    RESPONSAVEL
                FROM BASE
                WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)
                  AND CANAL <> 'N\u00c3O DEFINIDO'
                  AND ISNULL(PLANTA, '') = ?
                  AND ISNULL(CAST(GRUPO_CLI AS VARCHAR(50)) + '-' + NOME_GRP_CLIENTE, '') = ?
                  AND (PEDIDO_QTDE_ATENDIDO < (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO))
                ORDER BY (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO - PEDIDO_QTDE_ATENDIDO) DESC
            """, fr_params2 + [planta, grupo_cliente])
            detalhe = []
            for row in cur.fetchall():
                detalhe.append({
                    'pedido': str(row[0] or ''),
                    'vol_ped': int(row[1] or 0),
                    'vol_fat': int(row[2] or 0),
                    'gap_vol': int(row[3] or 0),
                    'perda_vlr': round(float(row[4] or 0), 2),
                    'canal': str(row[5] or ''),
                    'planta': str(row[6] or ''),
                    'grupo_cliente': str(row[7] or ''),
                    'dt_planejada': str(row[8] or ''),
                    'status': str(row[9] or ''),
                    'responsavel': str(row[10] or ''),
                })
            result['remessas_detalhe'] = detalhe

            # Count: pedidos com falta vs total de pedidos vencidos
            cur.execute(cte_sql2 + """
                SELECT
                    SUM(CASE WHEN PEDIDO_QTDE_ATENDIDO < (PEDIDO_QTDE - PEDIDO_QTDE_CANCELADO) THEN 1 ELSE 0 END) AS COM_FALTA,
                    COUNT(*) AS TOTAL_VENCIDOS
                FROM BASE
                WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)
                  AND CANAL <> 'N\u00c3O DEFINIDO'
                  AND ISNULL(PLANTA, '') = ?
                  AND ISNULL(CAST(GRUPO_CLI AS VARCHAR(50)) + '-' + NOME_GRP_CLIENTE, '') = ?
            """, fr_params2 + [planta, grupo_cliente])
            cnt_row = cur.fetchone()
            result['total_com_falta'] = int(cnt_row[0] or 0)
            result['total_registros'] = int(cnt_row[1] or 0)
        else:
            # OTIF drill-down
            otif_where, otif_params = _build_exec_otif_diag_where(filters)
            frete_cond = ""
            ot_col = "CASE WHEN TIPO_FRETE='FOB' THEN OT_FOB ELSE OT_CIF END"
            otif_col = "CASE WHEN TIPO_FRETE='FOB' THEN OTIF_FOB ELSE OTIF_CIF END"
            if 'FOB' in indicador:
                frete_cond = "AND TIPO_FRETE = 'FOB'"
                ot_col = "OT_FOB"
                otif_col = "OTIF_FOB"
            elif 'CIF' in indicador:
                frete_cond = "AND TIPO_FRETE = 'CIF'"
                ot_col = "OT_CIF"
                otif_col = "OTIF_CIF"

            _vencido_filter = """AND (
                    (TIPO_FRETE = 'FOB' AND CAST(DATA_GRADE AS DATE) < CAST(GETDATE() AS DATE))
                    OR
                    (TIPO_FRETE = 'CIF' AND CAST(DATA_AGENDA_ENTREGA AS DATE) < CAST(GETDATE() AS DATE))
                )"""
            base_where = f"{otif_where} AND ISNULL(PLANTA, '') = ? AND ISNULL(NOME_GRUPO_ID_CLIENTE, '') = ? {frete_cond} {_vencido_filter}"
            base_params = otif_params + [planta, grupo_cliente]

            # Components: OT vs IF
            cur.execute(_OTIF2_BASE_CTE + f"""
                SELECT
                    COUNT(*) AS TOTAL,
                    ISNULL(SUM({ot_col}), 0) AS OT_OK,
                    ISNULL(SUM(INFULL), 0) AS IF_OK,
                    ISNULL(SUM({otif_col}), 0) AS OTIF_OK
                FROM base
                {base_where}
            """, base_params)
            r = cur.fetchone()
            total = int(r[0] or 0)
            ot_ok = int(r[1] or 0)
            if_ok = int(r[2] or 0)
            ot_pct = round(_pct(ot_ok, total), 1) if total > 0 else 0
            if_pct = round(_pct(if_ok, total), 1) if total > 0 else 0
            ot_falhas = total - ot_ok
            if_falhas = total - if_ok
            principal = 'On Time' if ot_falhas >= if_falhas else 'In Full'
            result['componentes'] = {
                'ot_pct': ot_pct, 'if_pct': if_pct,
                'ot_falhas': ot_falhas, 'if_falhas': if_falhas,
                'total_remessas': total, 'principal_ofensor': principal,
            }

            # By canal
            cur.execute(_OTIF2_BASE_CTE + f"""
                SELECT
                    CLUSTER_FILL_RATE_OTIF AS CANAL,
                    COUNT(*) AS DEN,
                    ISNULL(SUM({ot_col}), 0) AS OT_OK,
                    ISNULL(SUM(INFULL), 0) AS IF_OK,
                    ISNULL(SUM({otif_col}), 0) AS OTIF_OK
                FROM base
                {base_where}
                GROUP BY CLUSTER_FILL_RATE_OTIF
                HAVING COUNT(*) > 0
            """, base_params)
            canais = []
            for row in cur.fetchall():
                den = int(row[1] or 0)
                canais.append({
                    'nome': str(row[0] or 'Sem Canal'),
                    'valor_pct': round(_pct(int(row[4] or 0), den), 1),
                    'ot_pct': round(_pct(int(row[2] or 0), den), 1),
                    'if_pct': round(_pct(int(row[3] or 0), den), 1),
                    'falhas': den - int(row[4] or 0),
                    'denominador': den,
                })
            result['por_canal'] = sorted(canais, key=lambda x: x['valor_pct'])

            # By transportadora
            cur.execute(_OTIF2_BASE_CTE + f"""
                SELECT
                    TRANSPORTADORA,
                    COUNT(*) AS DEN,
                    ISNULL(SUM({ot_col}), 0) AS OT_OK,
                    ISNULL(SUM(INFULL), 0) AS IF_OK,
                    ISNULL(SUM({otif_col}), 0) AS OTIF_OK
                FROM base
                {base_where}
                GROUP BY TRANSPORTADORA
                HAVING COUNT(*) > 0
            """, base_params)
            transp = []
            for row in cur.fetchall():
                nome = str(row[0] or 'Não Definido')
                if nome == 'Não Definido':
                    continue
                den = int(row[1] or 0)
                transp.append({
                    'nome': nome,
                    'valor_pct': round(_pct(int(row[4] or 0), den), 1),
                    'ot_pct': round(_pct(int(row[2] or 0), den), 1),
                    'if_pct': round(_pct(int(row[3] or 0), den), 1),
                    'falhas': den - int(row[4] or 0),
                    'denominador': den,
                })
            result['por_transportadora'] = sorted(transp, key=lambda x: x['valor_pct'])

            # Detail records (individual failed shipments)
            cur.execute(_OTIF2_BASE_CTE + f"""
                SELECT TOP 30
                    REMESSA, PEDIDO_MERCANET, PLANTA, NOME_GRUPO_ID_CLIENTE,
                    CONVERT(VARCHAR(19), DATA_GRADE, 120) AS DT_GRADE,
                    CONVERT(VARCHAR(19), DATA_AGENDA_ENTREGA, 120) AS DT_AGENDA,
                    CONVERT(VARCHAR(19), CASE WHEN TIPO_FRETE='FOB' THEN DATA_CHEGADA_PLANTA
                         ELSE DATA_CHEGADA_DESTINO END, 120) AS DT_CHEGADA,
                    TIPO_FRETE, TRANSPORTADORA,
                    VOL_LIQUIDO,
                    VOL_FATURADO,
                    CASE WHEN TIPO_FRETE='FOB' THEN TEMPO_ATRASO_FOB
                         ELSE TEMPO_ATRASO_CIF END AS ATRASO_MIN,
                    {ot_col} AS ON_TIME,
                    INFULL AS IN_FULL,
                    {otif_col} AS OTIF_OK,
                    CLUSTER_FILL_RATE_OTIF
                FROM base
                {base_where}
                  AND ({otif_col}) = 0
                ORDER BY DATA_GRADE DESC
            """, base_params)
            detalhe = []
            for row in cur.fetchall():
                detalhe.append({
                    'remessa': str(row[0] or ''),
                    'pedido': str(row[1] or ''),
                    'planta': str(row[2] or ''),
                    'grupo_cliente': str(row[3] or ''),
                    'dt_grade': str(row[4] or ''),
                    'dt_agenda': str(row[5] or ''),
                    'dt_chegada': str(row[6] or ''),
                    'tipo_frete': str(row[7] or ''),
                    'transportadora': str(row[8] or ''),
                    'volume': int(row[9] or 0),
                    'vol_faturado': int(row[10] or 0),
                    'atraso_min': int(row[11] or 0),
                    'on_time': int(row[12] or 0),
                    'in_full': int(row[13] or 0),
                    'otif': int(row[14] or 0),
                    'canal': str(row[15] or ''),
                })
            result['remessas_detalhe'] = detalhe
            result['total_registros'] = sum(c['falhas'] for c in canais)

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/api/executivo/evolucao')
def get_executivo_evolucao():
    """FR + OTIF mensais – janela de 12 meses terminando em dt_fim (ou mês atual)."""
    today = date.today()

    # Determina mês final da janela
    raw_fim = request.args.get('dt_fim', '').strip()
    if raw_fim:
        try:
            end_date = date.fromisoformat(raw_fim)
            yr_end, mo_end = end_date.year, end_date.month
        except ValueError:
            yr_end, mo_end = today.year, today.month
    else:
        yr_end, mo_end = today.year, today.month

    last_day = _calendar.monthrange(yr_end, mo_end)[1]
    dt_fim   = f"{yr_end}-{mo_end:02d}-{last_day:02d}"

    dt_ini = '2025-01-01'

    plantas = [p.strip() for p in request.args.getlist('planta') if p.strip()]
    grupos_cliente = [g.strip() for g in request.args.getlist('grupo_cliente') if g.strip()]

    cte_filters = [
        "I.DB_PEDI_PRODUTO <> '999999917'",
        "I.db_pedi_situacao IN (0, 1, 2, 9)",
        "I.status_registro = 'ATIVO'",
        "CAST(P.DB_PED_DT_PREVENT AS DATE) >= CAST(? AS DATE)",
        "CAST(P.DB_PED_DT_PREVENT AS DATE) <= CAST(? AS DATE)",
    ]
    params = [dt_ini, dt_fim]
    if plantas:
        ph = ','.join('?' * len(plantas))
        cte_filters.append(f"{_PLANTA_CASE} IN ({ph})")
        params += plantas
    if grupos_cliente:
        ph = ','.join('?' * len(grupos_cliente))
        cte_filters.append(
            f"CAST(G.COD_GR_CLIENTE AS VARCHAR) + '-' + G.GRUPO_CLIENTE_DESC IN ({ph})"
        )
        params += grupos_cliente
    cte_where = "WHERE " + " AND ".join(cte_filters)

    full_cte = _build_otif_cte(cte_where).rstrip()

    query = full_cte + """
        , MENSAL_FR AS (
            SELECT
                YEAR(DT_PLANEJADA_FATURAMENTO)          AS ANO,
                MONTH(DT_PLANEJADA_FATURAMENTO)         AS MES,
                ISNULL(SUM(PEDIDO_QTDE), 0)             AS QTDE_PED,
                ISNULL(SUM(PEDIDO_QTDE_ATENDIDO), 0)    AS QTDE_ATD,
                ISNULL(SUM(PEDIDO_QTDE_CANCELADO), 0)   AS QTDE_CAN
            FROM BASE
            WHERE DT_PLANEJADA_FATURAMENTO < CAST(GETDATE() AS DATE)
              AND CANAL <> 'NÃO DEFINIDO'
            GROUP BY YEAR(DT_PLANEJADA_FATURAMENTO), MONTH(DT_PLANEJADA_FATURAMENTO)
        )
        , MENSAL_OTIF AS (
            SELECT
                YEAR(DT_PLAN)                           AS ANO,
                MONTH(DT_PLAN)                          AS MES,
                COUNT(*)                                AS AVALIADOS,
                ISNULL(SUM(ON_TIME_OK), 0)              AS ON_TIME,
                ISNULL(SUM(IN_FULL_OK), 0)              AS IN_FULL,
                ISNULL(SUM(CASE WHEN ON_TIME_OK = 1 AND IN_FULL_OK = 1
                                THEN 1 ELSE 0 END), 0)  AS OTIF
            FROM OTIF_CALC
            GROUP BY YEAR(DT_PLAN), MONTH(DT_PLAN)
        )
        SELECT
            COALESCE(f.ANO,  o.ANO)                     AS ANO,
            COALESCE(f.MES,  o.MES)                     AS MES,
            ISNULL(f.QTDE_PED, 0)                       AS QTDE_PEDIDA,
            ISNULL(f.QTDE_ATD, 0)                       AS QTDE_ATENDIDA,
            ISNULL(f.QTDE_CAN, 0)                       AS QTDE_CANCELADA,
            ISNULL(o.AVALIADOS, 0)                      AS OTIF_AVALIADOS,
            ISNULL(o.ON_TIME, 0)                        AS ON_TIME,
            ISNULL(o.IN_FULL, 0)                        AS IN_FULL,
            ISNULL(o.OTIF, 0)                           AS OTIF
        FROM MENSAL_FR f
        FULL OUTER JOIN MENSAL_OTIF o ON f.ANO = o.ANO AND f.MES = o.MES
        ORDER BY ANO, MES
    """

    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, [str(v) if v is not None else '0' for v in row]))
                for row in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── OTIF (base: bqb.base_otm_otif_bq) ──────────────────────────────────────

_INSIGHTS_CACHE = {}
_INSIGHTS_TTL = 300


def _fmt_num(n):
    return f"{int(round(float(n or 0))):,}".replace(',', '.')


def _build_exec_insight_text(data):
    bullets = []
    fr_pct = data.get('fr_pct')
    otif_pct = data.get('otif_pct')
    fr_prev = data.get('fr_prev')
    otif_prev = data.get('otif_prev')
    action = data.get('action') or {}
    pareto = data.get('pareto') or []
    priorities = data.get('priorities') or []

    if fr_pct is not None or otif_pct is not None:
        fr_txt = f"Fill Rate {fr_pct:.1f}%" if fr_pct is not None else "Fill Rate sem base"
        otif_txt = f"OTIF {otif_pct:.1f}%" if otif_pct is not None else "OTIF sem base"
        bullets.append(f"• {fr_txt} (meta {_FR_TARGET:.0f}%) | {otif_txt} (meta {_OTIF_TARGET:.0f}%).")

    if fr_prev is not None and fr_pct is not None:
        delta_fr = fr_pct - fr_prev
        if abs(delta_fr) >= 0.1:
            bullets.append(f"• Fill Rate {'melhorou' if delta_fr > 0 else 'recuou'} {delta_fr:+.1f}pp vs. mês anterior.")
    elif otif_prev is not None and otif_pct is not None:
        delta_otif = otif_pct - otif_prev
        if abs(delta_otif) >= 0.1:
            bullets.append(f"• OTIF {'melhorou' if delta_otif > 0 else 'recuou'} {delta_otif:+.1f}pp vs. mês anterior.")

    if action and action.get('loss_value', 0) > 0:
        bullets.append(
            f"• Maior perda concentrada em {action.get('dimension_name')} ({action.get('metric_label')}) "
            f"com {action.get('kpi_value', 0):.1f}% e impacto estimado de {action.get('impact_pp', 0):.2f}pp."
        )

    if pareto:
        top3 = pareto[:3]
        cum_pct = top3[-1].get('cumulative_loss_pct', 0)
        bullets.append(
            f"• Os 3 maiores ofensores concentram {cum_pct:.1f}% do gap no Pareto atual."
        )

    if priorities:
        top = priorities[0]
        bullets.append(
            f"• Priorize {top.get('acao_sugerida')} em {top.get('planta')} / {top.get('grupo_cliente')} "
            f"({top.get('indicador')} em {top.get('valor_atual', 0):.1f}%)."
        )

    if not bullets:
        bullets.append("• Indicadores próximos da meta. Monitorar a dispersão do gap nas maiores bases.")

    return '\n'.join(bullets[:5])


@app.route('/api/executivo/insights')
def get_executivo_insights():
    filters = _get_exec_filters(request.args)
    cache_key = hashlib.md5(_json.dumps(filters, sort_keys=True).encode()).hexdigest()
    cached = _INSIGHTS_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _INSIGHTS_TTL:
        return jsonify({'text': cached[1], 'cached': True})

    try:
        conn = get_connection()
        cur = conn.cursor()

        fr_rows = _exec_diag_pareto_rows(filters, 'fillrate', 'planta', 'geral', cursor=cur)
        otif_rows = _exec_diag_pareto_rows(filters, 'otif', 'planta', 'geral', cursor=cur)
        action_candidates = []
        for cfg in [
            ('fillrate', 'planta', 'geral'),
            ('fillrate', 'grupo_cliente', 'geral'),
            ('otif', 'planta', 'geral'),
            ('otif', 'grupo_cliente', 'geral'),
            ('otif', 'planta', 'cif'),
            ('otif', 'grupo_cliente', 'cif'),
            ('otif', 'planta', 'fob'),
            ('otif', 'grupo_cliente', 'fob'),
        ]:
            rows = _exec_diag_pareto_rows(filters, cfg[0], cfg[1], cfg[2], cursor=cur)
            if rows and rows[0].get('loss_value', 0) > 0:
                action_candidates.append(rows[0])
        action = max(action_candidates, key=lambda r: (r['impact_pp'], r['loss_value'])) if action_candidates else None
        priorities = _build_exec_priority_rows(filters, cursor=cur)[:5]

        fr_den = sum(float(r['denominator']) for r in fr_rows)
        fr_num = sum(float(r['numerator']) for r in fr_rows)
        otif_den = sum(float(r['denominator']) for r in otif_rows)
        otif_num = sum(float(r['numerator']) for r in otif_rows)
        fr_pct = _pct(fr_num, fr_den) if fr_den > 0 else None
        otif_pct = _pct(otif_num, otif_den) if otif_den > 0 else None

        fr_prev = None
        otif_prev = None
        if not filters['dt_ini'] and not filters['dt_fim'] and len(filters['anos']) == 1 and len(filters['meses']) == 1:
            pa = int(filters['anos'][0])
            pm = int(filters['meses'][0]) - 1
            if pm < 1:
                pm = 12
                pa -= 1
            prev_filters = dict(filters)
            prev_filters['anos'] = [str(pa)]
            prev_filters['meses'] = [str(pm)]
            prev_filters['dt_ini'] = ''
            prev_filters['dt_fim'] = ''
            prev_fr_rows = _exec_diag_pareto_rows(prev_filters, 'fillrate', 'planta', 'geral', cursor=cur)
            prev_otif_rows = _exec_diag_pareto_rows(prev_filters, 'otif', 'planta', 'geral', cursor=cur)
            prev_fr_den = sum(float(r['denominator']) for r in prev_fr_rows)
            prev_fr_num = sum(float(r['numerator']) for r in prev_fr_rows)
            prev_otif_den = sum(float(r['denominator']) for r in prev_otif_rows)
            prev_otif_num = sum(float(r['numerator']) for r in prev_otif_rows)
            fr_prev = _pct(prev_fr_num, prev_fr_den) if prev_fr_den > 0 else None
            otif_prev = _pct(prev_otif_num, prev_otif_den) if prev_otif_den > 0 else None

        focus_pareto = []
        if action:
            focus_pareto = _exec_diag_pareto_rows(
                filters,
                action['selected_kpi'],
                action['selected_dimension'],
                action.get('otif_view') or 'geral',
                cursor=cur,
            )

        text = _build_exec_insight_text({
            'fr_pct': round(fr_pct, 1) if fr_pct is not None else None,
            'otif_pct': round(otif_pct, 1) if otif_pct is not None else None,
            'fr_prev': round(fr_prev, 1) if fr_prev is not None else None,
            'otif_prev': round(otif_prev, 1) if otif_prev is not None else None,
            'action': action,
            'pareto': focus_pareto,
            'priorities': priorities,
        })
    except Exception as e:
        _log.error("Insights data error: %s", e)
        return jsonify({'text': '• Não foi possível consolidar a leitura executiva no momento.', 'cached': False})

    _INSIGHTS_CACHE[cache_key] = (time.time(), text)
    return jsonify({'text': text, 'cached': False})


def _parse_otif2_filters():
    semanas        = [s.strip() for s in request.args.getlist('semana')        if s.strip()] or None
    anos           = [a.strip() for a in request.args.getlist('ano')           if a.strip()] or None
    meses          = [m.strip() for m in request.args.getlist('mes')           if m.strip()] or None
    dias           = [d.strip() for d in request.args.getlist('dia')           if d.strip()] or None
    plantas        = [p.strip() for p in request.args.getlist('planta')        if p.strip()] or None
    clientes       = [c.strip() for c in request.args.getlist('cliente')       if c.strip()] or None
    grupos_cliente = [g.strip() for g in request.args.getlist('grupo_cliente') if g.strip()] or None
    pedidos        = [p.strip() for p in request.args.getlist('pedido')        if p.strip()] or None
    canais         = [c.strip() for c in request.args.getlist('canal')         if c.strip()] or None
    remessas          = [r.strip() for r in request.args.getlist('remessa')          if r.strip()] or None
    transportadoras   = [t.strip() for t in request.args.getlist('transportadora')   if t.strip()] or None
    return semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras


def _build_otif2_filters(semanas=None, anos=None, meses=None, dias=None,
                          plantas=None, clientes=None, grupos_cliente=None,
                          canais=None, pedidos=None, remessas=None, tipos_frete=None,
                          transportadoras=None):
    filters = ["GRUPO_CLIENTE <> 'ARMAZÉM EXTERNO'", "CLUSTER_FILL_RATE_OTIF <> 'NÃO DEFINIDO'"]
    params  = []

    if semanas:
        clauses = []
        for sem in semanas:
            parts = sem.split('|')
            if len(parts) == 2:
                clauses.append(
                    "(CAST(DATA_GRADE AS DATE)"
                    " BETWEEN CAST(? AS DATE) AND CAST(? AS DATE))"
                )
                params.extend(parts)
        if clauses:
            filters.append("(" + " OR ".join(clauses) + ")")

    if anos:
        ph = ','.join('?' * len(anos))
        filters.append(f"YEAR(CAST(DATA_GRADE AS DATE)) IN ({ph})")
        params.extend(anos)
    if meses:
        ph = ','.join('?' * len(meses))
        filters.append(f"MONTH(CAST(DATA_GRADE AS DATE)) IN ({ph})")
        params.extend(meses)
    if dias:
        ph = ','.join('?' * len(dias))
        filters.append(f"DAY(CAST(DATA_GRADE AS DATE)) IN ({ph})")
        params.extend(dias)

    if plantas:
        ph = ','.join('?' * len(plantas))
        filters.append(f"PLANTA IN ({ph})")
        params.extend(plantas)
    if clientes:
        ph = ','.join('?' * len(clientes))
        filters.append(f"CLIENTE IN ({ph})")
        params.extend(clientes)
    if grupos_cliente:
        ph = ','.join('?' * len(grupos_cliente))
        filters.append(f"NOME_GRUPO_ID_CLIENTE IN ({ph})")
        params.extend(grupos_cliente)
    if canais:
        ph = ','.join('?' * len(canais))
        filters.append(f"CLUSTER_FILL_RATE_OTIF IN ({ph})")
        params.extend(canais)
    if pedidos:
        ph = ','.join('?' * len(pedidos))
        filters.append(f"CAST(PEDIDO_MERCANET AS VARCHAR) IN ({ph})")
        params.extend(pedidos)
    if remessas:
        ph = ','.join('?' * len(remessas))
        filters.append(f"CAST(REMESSA AS VARCHAR) IN ({ph})")
        params.extend(remessas)
    if tipos_frete:
        ph = ','.join('?' * len(tipos_frete))
        filters.append(f"TIPO_FRETE IN ({ph})")
        params.extend(tipos_frete)
    if transportadoras:
        ph = ','.join('?' * len(transportadoras))
        filters.append(f"TRANSPORTADORA IN ({ph})")
        params.extend(transportadoras)

    # Responsavel filter (via GRUPO_CLIENTES_VIEW.NM_NV1)
    responsaveis = [r.strip() for r in request.args.getlist('responsavel') if r.strip()] if hasattr(request, 'args') else None
    if responsaveis:
        ph = ','.join('?' * len(responsaveis))
        filters.append(f"RESPONSAVEL IN ({ph})")
        params.extend(responsaveis)

    # Status filter (no_prazo, atraso_ot, incompleto_if, conforme)
    status_vals = [s.strip() for s in request.args.getlist('status') if s.strip()] if hasattr(request, 'args') else None
    if status_vals:
        _vencido_fob = "(TIPO_FRETE='FOB' AND CAST(DATA_GRADE AS DATE) < CAST(GETDATE() AS DATE))"
        _vencido_cif = "(TIPO_FRETE='CIF' AND CAST(DATA_AGENDA_ENTREGA AS DATE) < CAST(GETDATE() AS DATE))"
        _no_prazo_fob = "(TIPO_FRETE='FOB' AND CAST(DATA_GRADE AS DATE) >= CAST(GETDATE() AS DATE))"
        _no_prazo_cif = "(TIPO_FRETE='CIF' AND CAST(DATA_AGENDA_ENTREGA AS DATE) >= CAST(GETDATE() AS DATE))"
        status_clauses = []
        for sv in status_vals:
            if sv == 'no_prazo':
                status_clauses.append(f"({_no_prazo_fob} OR {_no_prazo_cif})")
            elif sv == 'atraso_ot':
                status_clauses.append(
                    f"(({_vencido_fob} AND OT_FOB = 0) OR ({_vencido_cif} AND OT_CIF = 0))"
                )
            elif sv == 'incompleto_if':
                status_clauses.append(
                    f"(({_vencido_fob} OR {_vencido_cif}) AND INFULL = 0)"
                )
            elif sv == 'conforme':
                status_clauses.append(
                    "(CASE WHEN TIPO_FRETE='FOB' THEN OTIF_FOB ELSE OTIF_CIF END) = 1"
                )
        if status_clauses:
            filters.append("(" + " OR ".join(status_clauses) + ")")

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    return where, params


_OTIF2_BASE_CTE = """
    WITH raw AS (
        SELECT
            CASE WHEN TIPO_FRETE = 'FOB'
                 AND DATA_CHEGADA_PLANTA <= DATEADD(MINUTE, 30, DATA_GRADE)
                 THEN 1 ELSE 0 END AS OT_FOB,
            CASE WHEN TIPO_FRETE = 'CIF'
                 AND DATA_CHEGADA_DESTINO <= DATA_AGENDA_ENTREGA
                 THEN 1 ELSE 0 END AS OT_CIF,
            CASE WHEN QT_ATEND_MERCANET >= (QT_SOLIC_MERCANET - QT_CANC_MERCANET)
                  AND (QT_SOLIC_MERCANET - QT_CANC_MERCANET) > 0
                 THEN 1 ELSE 0 END AS INFULL,
            CASE
                WHEN TIPO_FRETE = 'FOB'
                 AND DATEDIFF(MINUTE, DATA_GRADE, DATA_CHEGADA_PLANTA) > 0
                    THEN DATEDIFF(MINUTE, DATA_GRADE, DATA_CHEGADA_PLANTA)
                WHEN TIPO_FRETE = 'FOB' THEN 0
                ELSE NULL
            END AS TEMPO_ATRASO_FOB,
            CASE
                WHEN TIPO_FRETE = 'CIF'
                 AND DATEDIFF(MINUTE, DATA_AGENDA_ENTREGA, DATA_CHEGADA_DESTINO) > 0
                    THEN DATEDIFF(MINUTE, DATA_AGENDA_ENTREGA, DATA_CHEGADA_DESTINO)
                WHEN TIPO_FRETE = 'CIF' THEN 0
                ELSE NULL
            END AS TEMPO_ATRASO_CIF,
            o.DATA_GRADE,
            ISNULL(o.QT_SOLIC_MERCANET, 0) - ISNULL(o.QT_CANC_MERCANET, 0) AS VOL_LIQUIDO,
            ISNULL(o.QT_ATEND_MERCANET, 0) AS VOL_FATURADO,
            o.PEDIDO_MERCANET,
            o.REMESSA,
            UPPER(CASE WHEN UPPER(o.CLIENTE) LIKE 'BQ[_]%'
                       THEN STUFF(o.CLIENTE, 1, 3, '')
                       ELSE o.CLIENTE END) AS CLIENTE,
            o.DESC_GRUPO_CLIENTE                                              AS GRUPO_CLIENTE,
            CAST(o.ID_GRUPO_CLIENTE AS VARCHAR) + '-' + o.DESC_GRUPO_CLIENTE AS NOME_GRUPO_ID_CLIENTE,
            o.TIPO_FRETE,
            ISNULL(o.TRANSPORTADORA, 'Não Definido') AS TRANSPORTADORA,
            CASE UPPER(o.ORIGEM)
                WHEN 'GUARULHOS'    THEN 'GUA'
                WHEN 'JAGUARIUNA'   THEN 'JAG'
                WHEN 'JUIZ DE FORA' THEN 'JDF'
                WHEN 'POUSO ALEGRE' THEN 'POU'
                WHEN 'OSASCO'       THEN 'OSA'
                ELSE o.ORIGEM
            END                     AS PLANTA,
            ISNULL(gc.CLUSTER_FILL_RATE_OTIF, 'Sem Canal') AS CLUSTER_FILL_RATE_OTIF,
            ISNULL(gc.NM_NV1, 'Sem Responsável') AS RESPONSAVEL,
            o.DATA_AGENDA_ENTREGA,
            o.DATA_CHEGADA_PLANTA,
            o.DATA_CHEGADA_DESTINO
        FROM bqb.base_otm_otif_bq o
        LEFT JOIN BQB.GRUPO_CLIENTES_VIEW gc WITH (NOLOCK)
            ON o.ID_GRUPO_CLIENTE = gc.COD_GR_CLIENTE
    ),
    base AS (
        SELECT
            r.OT_FOB * r.INFULL AS OTIF_FOB,
            r.OT_CIF * r.INFULL AS OTIF_CIF,
            r.OT_FOB,
            r.OT_CIF,
            r.INFULL,
            r.VOL_LIQUIDO,
            r.VOL_FATURADO,
            r.TEMPO_ATRASO_FOB,
            r.TEMPO_ATRASO_CIF,
            r.TIPO_FRETE,
            r.TRANSPORTADORA,
            r.PLANTA,
            r.PEDIDO_MERCANET,
            r.REMESSA,
            r.CLIENTE,
            r.GRUPO_CLIENTE,
            r.NOME_GRUPO_ID_CLIENTE,
            r.CLUSTER_FILL_RATE_OTIF,
            r.RESPONSAVEL,
            r.DATA_GRADE,
            r.DATA_AGENDA_ENTREGA,
            r.DATA_CHEGADA_PLANTA,
            r.DATA_CHEGADA_DESTINO
        FROM raw r
    )
"""


@app.route('/api/otif2/plantas')
def get_otif2_plantas():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT ORIGEM FROM bqb.base_otm_otif_bq"
            " WHERE ORIGEM IS NOT NULL ORDER BY ORIGEM"
        )
        return jsonify([row[0] for row in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/clientes')
def get_otif2_clientes():
    grupos = [g.strip() for g in request.args.getlist('grupo_cliente') if g.strip()]
    try:
        conn = get_connection()
        cur  = conn.cursor()
        if grupos:
            ph = ','.join('?' * len(grupos))
            cur.execute(
                "SELECT DISTINCT UPPER(CASE WHEN UPPER(CLIENTE) LIKE 'BQ[_]%'"
                "  THEN STUFF(CLIENTE, 1, 3, '') ELSE CLIENTE END) AS CLIENTE"
                " FROM bqb.base_otm_otif_bq"
                f" WHERE CLIENTE IS NOT NULL"
                f"   AND CAST(ID_GRUPO_CLIENTE AS VARCHAR) + '-' + DESC_GRUPO_CLIENTE IN ({ph})"
                " ORDER BY 1",
                grupos
            )
        else:
            cur.execute(
                "SELECT DISTINCT UPPER(CASE WHEN UPPER(CLIENTE) LIKE 'BQ[_]%'"
                "  THEN STUFF(CLIENTE, 1, 3, '') ELSE CLIENTE END) AS CLIENTE"
                " FROM bqb.base_otm_otif_bq"
                " WHERE CLIENTE IS NOT NULL ORDER BY 1"
            )
        return jsonify([row[0] for row in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/grupos-cliente')
def get_otif2_grupos_cliente():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT CAST(ID_GRUPO_CLIENTE AS VARCHAR) + '-' + DESC_GRUPO_CLIENTE"
            " FROM bqb.base_otm_otif_bq"
            " WHERE ID_GRUPO_CLIENTE IS NOT NULL AND DESC_GRUPO_CLIENTE IS NOT NULL"
            " ORDER BY 1"
        )
        return jsonify([row[0] for row in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/responsaveis')
def get_otif2_responsaveis():
    """Distinct RESPONSAVEL values from GRUPO_CLIENTES_VIEW."""
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT NM_NV1"
            " FROM BQB.GRUPO_CLIENTES_VIEW"
            " WHERE NM_NV1 IS NOT NULL AND NM_NV1 <> ''"
            " ORDER BY 1"
        )
        return jsonify([row[0] for row in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/canais')
def get_otif2_canais():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT CLUSTER_FILL_RATE_OTIF"
            " FROM bqb.base_otm_otif_bq"
            " WHERE CLUSTER_FILL_RATE_OTIF IS NOT NULL AND CLUSTER_FILL_RATE_OTIF <> '' AND CLUSTER_FILL_RATE_OTIF <> 'NÃO DEFINIDO'"
            " ORDER BY 1"
        )
        return jsonify([row[0] for row in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/pedidos')
def get_otif2_pedidos():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT CAST(PEDIDO_MERCANET AS VARCHAR)"
            " FROM bqb.base_otm_otif_bq"
            " WHERE PEDIDO_MERCANET IS NOT NULL"
            " ORDER BY 1"
        )
        return jsonify([row[0] for row in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/remessas')
def get_otif2_remessas():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT CAST(REMESSA AS VARCHAR)"
            " FROM bqb.base_otm_otif_bq"
            " WHERE REMESSA IS NOT NULL"
            " ORDER BY 1"
        )
        return jsonify([row[0] for row in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/resumo')
def get_otif2_resumo():
    semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras = _parse_otif2_filters()
    tipos_frete = [t.strip() for t in request.args.getlist('tipo_frete') if t.strip()] or None
    where, params = _build_otif2_filters(semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, tipos_frete=tipos_frete, transportadoras=transportadoras)
    query = _OTIF2_BASE_CTE + f"""
        SELECT
            COUNT(*)                                             AS TOTAL_LINHAS,
            SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END) AS FOB_LINHAS,
            SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END) AS CIF_LINHAS,
            SUM(OT_FOB * INFULL)                                             AS OTIF_FOB,
            SUM(OT_FOB)                                                      AS OT_FOB,
            SUM(OT_CIF)                                                      AS OT_CIF,
            SUM(OT_CIF * INFULL)                                             AS OTIF_CIF,
            SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN INFULL ELSE 0 END)        AS INFULL_FOB,
            SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN INFULL ELSE 0 END)        AS INFULL_CIF,
            AVG(CASE WHEN TEMPO_ATRASO_FOB > 0 THEN TEMPO_ATRASO_FOB END)   AS AVG_ATRASO_FOB,
            AVG(CASE WHEN TEMPO_ATRASO_CIF > 0 THEN TEMPO_ATRASO_CIF END)   AS AVG_ATRASO_CIF
        FROM base
        {where}
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        row  = cursor.fetchone()
        cols = [c[0] for c in cursor.description]
        return jsonify(dict(zip(cols, [str(v) if v is not None else '0' for v in row])))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/por-planta')
def get_otif2_por_planta():
    semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras = _parse_otif2_filters()
    where, params = _build_otif2_filters(semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras=transportadoras)
    query = _OTIF2_BASE_CTE + f"""
        SELECT
            ISNULL(PLANTA, 'Sem Planta')                         AS GRUPO,
            COUNT(*)                                             AS TOTAL_LINHAS,
            SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END) AS FOB_LINHAS,
            SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END) AS CIF_LINHAS,
            SUM(OT_FOB * INFULL)                                             AS OTIF_FOB,
            SUM(OT_FOB)                                                      AS OT_FOB,
            SUM(OT_CIF)                                                      AS OT_CIF,
            SUM(OT_CIF * INFULL)                                             AS OTIF_CIF,
            SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN INFULL ELSE 0 END)        AS INFULL_FOB,
            SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN INFULL ELSE 0 END)        AS INFULL_CIF,
            AVG(CASE WHEN TEMPO_ATRASO_FOB > 0 THEN TEMPO_ATRASO_FOB END)   AS AVG_ATRASO_FOB,
            AVG(CASE WHEN TEMPO_ATRASO_CIF > 0 THEN TEMPO_ATRASO_CIF END)   AS AVG_ATRASO_CIF
        FROM base
        {where}
        GROUP BY PLANTA
        HAVING SUM(OT_FOB * INFULL) > 0 OR SUM(OT_CIF * INFULL) > 0
        ORDER BY (
            CASE WHEN SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END) > 0
                 THEN CAST(SUM(OT_FOB * INFULL) AS FLOAT) / SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END) * 100
                 ELSE 0 END
          + CASE WHEN SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END) > 0
                 THEN CAST(SUM(OT_CIF * INFULL) AS FLOAT) / SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END) * 100
                 ELSE 0 END
        ) / 2.0 DESC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, [str(v) if v is not None else '0' for v in row]))
                for row in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/por-cliente')
def get_otif2_por_cliente():
    semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras = _parse_otif2_filters()
    where, params = _build_otif2_filters(semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras=transportadoras)
    mode = request.args.get('mode', 'grupo')
    dim_col   = 'CLIENTE'       if mode == 'cliente' else 'GRUPO_CLIENTE'
    dim_label = "'Sem Cliente'" if mode == 'cliente' else "'Sem Grupo'"
    query = _OTIF2_BASE_CTE + f"""
        SELECT
            ISNULL({dim_col}, {dim_label})                       AS GRUPO,
            COUNT(*)                                             AS TOTAL_LINHAS,
            SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END) AS FOB_LINHAS,
            SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END) AS CIF_LINHAS,
            SUM(OT_FOB * INFULL)                                             AS OTIF_FOB,
            SUM(OT_FOB)                                                      AS OT_FOB,
            SUM(OT_CIF)                                                      AS OT_CIF,
            SUM(OT_CIF * INFULL)                                             AS OTIF_CIF,
            SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN INFULL ELSE 0 END)        AS INFULL_FOB,
            SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN INFULL ELSE 0 END)        AS INFULL_CIF,
            AVG(CASE WHEN TEMPO_ATRASO_FOB > 0 THEN TEMPO_ATRASO_FOB END)   AS AVG_ATRASO_FOB,
            AVG(CASE WHEN TEMPO_ATRASO_CIF > 0 THEN TEMPO_ATRASO_CIF END)   AS AVG_ATRASO_CIF
        FROM base
        {where}
        GROUP BY {dim_col}
        HAVING SUM(OT_FOB * INFULL) > 0 OR SUM(OT_CIF * INFULL) > 0
        ORDER BY (
            CASE WHEN SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END) > 0
                 THEN CAST(SUM(OT_FOB * INFULL) AS FLOAT) / SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END) * 100
                 ELSE 0 END
          + CASE WHEN SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END) > 0
                 THEN CAST(SUM(OT_CIF * INFULL) AS FLOAT) / SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END) * 100
                 ELSE 0 END
        ) / 2.0 DESC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, [str(v) if v is not None else '0' for v in row]))
                for row in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/mensal')
def get_otif2_mensal():
    semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras = _parse_otif2_filters()
    where, params = _build_otif2_filters(semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras=transportadoras)
    query = _OTIF2_BASE_CTE + f"""
        SELECT
            YEAR(CAST(DATA_GRADE  AS DATE)) AS ANO,
            MONTH(CAST(DATA_GRADE AS DATE)) AS MES,
            COUNT(*)                                             AS TOTAL_LINHAS,
            SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END) AS FOB_LINHAS,
            SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END) AS CIF_LINHAS,
            SUM(OT_FOB * INFULL)                                             AS OTIF_FOB,
            SUM(OT_FOB)                                                      AS OT_FOB,
            SUM(OT_CIF)                                                      AS OT_CIF,
            SUM(OT_CIF * INFULL)                                             AS OTIF_CIF,
            SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN INFULL ELSE 0 END)        AS INFULL_FOB,
            SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN INFULL ELSE 0 END)        AS INFULL_CIF,
            AVG(CASE WHEN TEMPO_ATRASO_FOB > 0 THEN TEMPO_ATRASO_FOB END)   AS AVG_ATRASO_FOB,
            AVG(CASE WHEN TEMPO_ATRASO_CIF > 0 THEN TEMPO_ATRASO_CIF END)   AS AVG_ATRASO_CIF
        FROM base
        {where}
        GROUP BY YEAR(CAST(DATA_GRADE AS DATE)),
                 MONTH(CAST(DATA_GRADE AS DATE))
        HAVING SUM(OT_FOB * INFULL) > 0 OR SUM(OT_CIF * INFULL) > 0
        ORDER BY ANO, MES
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, [str(v) if v is not None else '0' for v in row]))
                for row in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/semanal')
def get_otif2_semanal():
    semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras = _parse_otif2_filters()
    where, params = _build_otif2_filters(semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras=transportadoras)
    # Modulo sem usar '%' (conflita com pymssql format): x%7 = x - (x/7)*7
    _wd = "(DATEPART(weekday, CAST(DATA_GRADE AS DATE)) - 2 + 7)"
    _mod7 = f"({_wd} - ({_wd} / 7) * 7)"
    dt_segunda = (
        f"CAST(DATEADD(day, -({_mod7}), "
        f"CAST(DATA_GRADE AS DATE)) AS DATE)"
    )
    query = _OTIF2_BASE_CTE + f"""
        SELECT
            {dt_segunda}                                             AS DT_SEGUNDA,
            DATEPART(ISO_WEEK, {dt_segunda})                         AS SEMANA_NUM,
            COUNT(*)                                                 AS TOTAL_LINHAS,
            SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END)     AS FOB_LINHAS,
            SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END)     AS CIF_LINHAS,
            SUM(OT_FOB * INFULL)                                     AS OTIF_FOB,
            SUM(OT_FOB)                                              AS OT_FOB,
            SUM(OT_CIF)                                              AS OT_CIF,
            SUM(OT_CIF * INFULL)                                     AS OTIF_CIF,
            SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN INFULL ELSE 0 END) AS INFULL_FOB,
            SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN INFULL ELSE 0 END) AS INFULL_CIF,
            AVG(CASE WHEN TEMPO_ATRASO_FOB > 0 THEN TEMPO_ATRASO_FOB END)   AS AVG_ATRASO_FOB,
            AVG(CASE WHEN TEMPO_ATRASO_CIF > 0 THEN TEMPO_ATRASO_CIF END)   AS AVG_ATRASO_CIF
        FROM base
        {where}
        GROUP BY {dt_segunda}
        ORDER BY DT_SEGUNDA
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        cols = [c[0] for c in cursor.description]
        def fmt(v):
            if v is None: return ''
            if hasattr(v, 'strftime'): return v.strftime('%Y-%m-%d')
            return str(v)
        rows = [dict(zip(cols, [fmt(v) for v in row])) for row in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/detalhe')
def get_otif2_detalhe():
    semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras = _parse_otif2_filters()
    tipos_frete = [t.strip() for t in request.args.getlist('tipo_frete') if t.strip()] or None
    where, params = _build_otif2_filters(semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, tipos_frete=tipos_frete, transportadoras=transportadoras)
    download = request.args.get('download', '0') == '1'
    page      = max(1, int(request.args.get('page', 1)))
    page_size = 500
    offset    = (page - 1) * page_size
    pagination = '' if download else f'OFFSET {offset} ROWS FETCH NEXT {page_size} ROWS ONLY'

    count_query = _OTIF2_BASE_CTE + f"SELECT COUNT(*) AS TOTAL FROM base {where}"
    data_query  = _OTIF2_BASE_CTE + f"""
        SELECT
            DATA_GRADE,
            DATA_AGENDA_ENTREGA,
            DATA_CHEGADA_PLANTA,
            DATA_CHEGADA_DESTINO,
            PEDIDO_MERCANET, REMESSA, CLIENTE, GRUPO_CLIENTE,
            TIPO_FRETE, PLANTA, TRANSPORTADORA,
            OT_FOB, OT_CIF, INFULL,
            OTIF_FOB, OTIF_CIF,
            ISNULL(TEMPO_ATRASO_FOB, 0) AS TEMPO_ATRASO_FOB,
            ISNULL(TEMPO_ATRASO_CIF, 0) AS TEMPO_ATRASO_CIF
        FROM base
        {where}
        ORDER BY DATA_GRADE DESC
        {pagination}
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        cursor.execute(data_query, params * (1 if download else 1))
        cols = [c[0] for c in cursor.description]
        def fmt(v):
            if v is None: return ''
            if hasattr(v, 'strftime'): return v.strftime('%d/%m/%Y %H:%M')
            return str(v)
        rows = [dict(zip(cols, [fmt(v) for v in row])) for row in cursor.fetchall()]
        return jsonify({'total': total, 'page': page, 'page_size': page_size, 'rows': rows})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/transportadoras')
def get_otif2_transportadoras():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT ISNULL(TRANSPORTADORA,'Não Definido') AS T"
            " FROM bqb.base_otm_otif_bq"
            " WHERE TRANSPORTADORA IS NOT NULL AND LTRIM(RTRIM(TRANSPORTADORA)) <> ''"
            " ORDER BY 1"
        )
        return jsonify([row[0] for row in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/por-transportadora')
def get_otif2_por_transportadora():
    semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras = _parse_otif2_filters()
    where, params = _build_otif2_filters(semanas, anos, meses, dias, plantas, clientes, grupos_cliente, canais, pedidos, remessas, transportadoras=transportadoras)
    query = _OTIF2_BASE_CTE + f"""
        SELECT
            ISNULL(TRANSPORTADORA, 'Não Definido')               AS GRUPO,
            COUNT(*)                                             AS TOTAL_LINHAS,
            SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END) AS FOB_LINHAS,
            SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END) AS CIF_LINHAS,
            SUM(OT_FOB * INFULL)                                             AS OTIF_FOB,
            SUM(OT_FOB)                                                      AS OT_FOB,
            SUM(OT_CIF)                                                      AS OT_CIF,
            SUM(OT_CIF * INFULL)                                             AS OTIF_CIF,
            SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN INFULL ELSE 0 END)        AS INFULL_FOB,
            SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN INFULL ELSE 0 END)        AS INFULL_CIF,
            AVG(CASE WHEN TEMPO_ATRASO_FOB > 0 THEN TEMPO_ATRASO_FOB END)   AS AVG_ATRASO_FOB,
            AVG(CASE WHEN TEMPO_ATRASO_CIF > 0 THEN TEMPO_ATRASO_CIF END)   AS AVG_ATRASO_CIF
        FROM base
        {{where}}
        GROUP BY TRANSPORTADORA
        HAVING COUNT(*) > 0
        ORDER BY (
            CASE WHEN SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END) > 0
                 THEN CAST(SUM(OT_FOB * INFULL) AS FLOAT) / SUM(CASE WHEN TIPO_FRETE = 'FOB' THEN 1 ELSE 0 END) * 100
                 ELSE 0 END
          + CASE WHEN SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END) > 0
                 THEN CAST(SUM(OT_CIF * INFULL) AS FLOAT) / SUM(CASE WHEN TIPO_FRETE = 'CIF' THEN 1 ELSE 0 END) * 100
                 ELSE 0 END
        ) / 2.0 DESC
    """.format(where=where)
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, [str(v) if v is not None else '0' for v in row]))
                for row in cursor.fetchall()]
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/otif2/debug-tipo-frete')
def debug_tipo_frete():
    """Retorna os valores distintos de TIPO_FRETE e suas contagens."""
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT TIPO_FRETE, COUNT(*) AS QTD"
            " FROM bqb.base_otm_otif_bq"
            " GROUP BY TIPO_FRETE"
            " ORDER BY QTD DESC"
        )
        return jsonify([{'TIPO_FRETE': row[0], 'QTD': row[1]} for row in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Filtros dinâmicos ─────────────────────────────────────────────────────────

@app.route('/api/empresas')
def get_empresas():
    """Retorna os códigos de planta (QRA, QRB…) disponíveis."""
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT DB_PED_EMPRESA"
            " FROM BQB.MCANET_DB_PEDIDO"
            " WHERE DB_PED_EMPRESA IS NOT NULL"
            " ORDER BY DB_PED_EMPRESA"
        )
        result = [row[0] for row in cur.fetchall()]
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/plantas')
def get_plantas():
    """Retorna os nomes de planta (lista estática derivada do mapeamento fixo de empresa)."""
    return jsonify(['GUA', 'JAG', 'JDF', 'OSA', 'POU', 'QRE'])


@app.route('/api/fillrate/grupos-cliente')
def get_fillrate_grupos_cliente():
    """Lista distinct de GRUPO_CLIENTE_DESC da view."""
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT GRUPO_CLIENTE_DESC"
            " FROM BQB.GRUPO_CLIENTES_VIEW"
            " WHERE GRUPO_CLIENTE_DESC IS NOT NULL AND GRUPO_CLIENTE_DESC <> ''"
            " ORDER BY 1"
        )
        return jsonify([row[0] for row in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/fillrate/canais')
def get_fillrate_canais():
    """Lista distinct de CLUSTER_FILL_RATE_OTIF da view."""
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT CLUSTER_FILL_RATE_OTIF"
            " FROM BQB.GRUPO_CLIENTES_VIEW"
            " WHERE CLUSTER_FILL_RATE_OTIF IS NOT NULL AND CLUSTER_FILL_RATE_OTIF <> '' AND CLUSTER_FILL_RATE_OTIF <> 'NÃO DEFINIDO'"
            " ORDER BY 1"
        )
        return jsonify([row[0] for row in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/fillrate/responsaveis')
def get_fillrate_responsaveis():
    """Lista distinct de NM_NV1 da view GRUPO_CLIENTES_VIEW."""
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT NM_NV1"
            " FROM BQB.GRUPO_CLIENTES_VIEW"
            " WHERE NM_NV1 IS NOT NULL AND NM_NV1 <> ''"
            " ORDER BY 1"
        )
        return jsonify([row[0] for row in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/status')
def get_status():
    """Retorna os status de pedido válidos."""
    return jsonify([
        {'id': '0', 'descricao': 'Aberto'},
        {'id': '1', 'descricao': 'Faturado Parcial'},
        {'id': '2', 'descricao': 'Faturado'},
        {'id': '9', 'descricao': 'Cancelado'},
    ])


# ── Servir arquivos estáticos ─────────────────────────────────────────────────

@app.route('/')
def serve_index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(BASE_DIR, filename)


@app.route('/src/app/<path:filename>')
def serve_src_app_static(filename):
    return send_from_directory(BASE_DIR, filename)


# ── Inicialização ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port  = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV', 'production') == 'development'
    if debug:
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        from waitress import serve
        print(f'Servidor rodando em http://0.0.0.0:{port}')
        serve(app, host='0.0.0.0', port=port)
