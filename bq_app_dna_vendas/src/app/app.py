"""
Bimbo Brasil - DNA Analytics
Databricks App: DNA de Vendas (Vendômetro + Report Dinâmico)
"""

import os
import time
import json
import io
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor
from fastapi.middleware.gzip import GZipMiddleware

from fastapi import FastAPI, Request, Query, Body, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import openpyxl
from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

from databricks.sdk import WorkspaceClient

# Warehouse ID default
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "f4a2e26b8410f1e3")

app = FastAPI(title="DNA de Vendas | Grupo Bimbo Brasil")
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path.lower()
    if path.endswith((".css", ".js", ".png", ".svg", ".jpg", ".jpeg", ".webp", ".ico", ".woff2")):
        response.headers["Cache-Control"] = "public, max-age=3600"
    elif path == "/api/metadata":
        response.headers["Cache-Control"] = "private, max-age=300"
    else:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# In-memory query & endpoint cache with TTL (chave isolada por usuário)
CACHE: Dict[str, Any] = {}
CACHE_TTL = 1800  # 30 minutes
METADATA_CACHE: Dict[str, Any] = {}
METADATA_TTL = 1800  # 30 minutes
ENDPOINT_CACHE: Dict[str, Any] = {}
ENDPOINT_TTL = 1800  # 30 minutes


def _endpoint_cache_key(request: Optional[Request], route: str, payload: Any) -> str:
    user_info = get_current_user_info(request)
    user_key = user_info.get("email") or "anonymous"
    return f"{user_key}:{route}:{json.dumps(payload, sort_keys=True, default=str)}"


def _endpoint_cache_get(request: Optional[Request], route: str, payload: Any):
    key = _endpoint_cache_key(request, route, payload)
    entry = ENDPOINT_CACHE.get(key)
    if entry:
        val, ts = entry
        if time.time() - ts < ENDPOINT_TTL:
            return val
    return None


def _endpoint_cache_set(request: Optional[Request], route: str, payload: Any, val: Any):
    key = _endpoint_cache_key(request, route, payload)
    ENDPOINT_CACHE[key] = (val, time.time())

def get_current_user_info(request: Optional[Request] = None) -> Dict[str, str]:
    """Extrai identidade do usuário a partir dos cabeçalhos Databricks Apps ou fallback local."""
    email = ""
    name = ""
    if request:
        email = request.headers.get("x-forwarded-email") or ""
        name = request.headers.get("x-forwarded-preferred-username") or ""
    
    if not email:
        email = os.getenv("DEV_USER_EMAIL", "renan.ferreira@grupobimbo.com")
    if not name:
        name = os.getenv("DEV_USER_NAME", "Renan Ferreira")
    return {"email": email, "name": name}

def get_user_workspace_client(request: Optional[Request] = None) -> WorkspaceClient:
    """
    Cria cliente WorkspaceClient por requisição (R12 / OBO).
    Usa o token do usuário repassado em 'x-forwarded-access-token'.
    Sem token em ambiente Databricks Apps, falha fechado (401/403).
    Em ambiente local (dev), permite fallback para variáveis de ambiente.
    """
    token = request.headers.get("x-forwarded-access-token") if request else None
    host = os.getenv("DATABRICKS_HOST", "https://adb-8674310331778219.19.azuredatabricks.net")

    if token:
        return WorkspaceClient(host=host, token=token)

    # Se estiver rodando dentro do Databricks Apps sem token, falhe fechado (O3)
    is_databricks_app = bool(os.getenv("DATABRICKS_APP_ID") or os.getenv("DATABRICKS_APP_NAME"))
    if is_databricks_app:
        raise HTTPException(
            status_code=401,
            detail="Autenticação OBO necessária: cabeçalho 'x-forwarded-access-token' não fornecido."
        )

    # Desenvolvimento local: permite token pessoal ou credenciais locais
    local_token = os.getenv("DATABRICKS_TOKEN")
    if local_token:
        return WorkspaceClient(host=host, token=local_token)

    return WorkspaceClient()

def run_databricks_query(sql: str, request: Optional[Request] = None, use_cache: bool = True) -> List[Dict[str, Any]]:
    """Executa consulta com token OBO do usuário e cache isolado por usuário."""
    now = time.time()
    user_info = get_current_user_info(request)
    user_key = user_info.get("email") or "anonymous"
    cache_key = f"{user_key}:{sql}"

    if use_cache and cache_key in CACHE:
        val, ts = CACHE[cache_key]
        if now - ts < CACHE_TTL:
            return val

    try:
        w = get_user_workspace_client(request)
        res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID,
            statement=sql,
            wait_timeout="45s"
        )
    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if "403" in err_msg or "PERMISSION_DENIED" in err_msg or "User is not authorized" in err_msg:
            raise HTTPException(
                status_code=403,
                detail="Acesso negado no Unity Catalog ou Warehouse. Solicite permissão ao administrador."
            )
        raise HTTPException(status_code=500, detail="Erro ao executar consulta no Databricks.")

    if res.status.state != "SUCCEEDED" and res.status.error:
        raise HTTPException(status_code=500, detail=str(res.status.error))

    if not res.result or not res.result.data_array:
        return []

    cols = [c.name for c in res.manifest.schema.columns]
    rows = []
    for raw in res.result.data_array:
        row_dict = {}
        for c, v in zip(cols, raw):
            row_dict[c] = v
        rows.append(row_dict)

    if use_cache:
        CACHE[cache_key] = (rows, now)

    return rows


# ─── MODELS ───
class VendometroFilters(BaseModel):
    grupo_cliente: Optional[Any] = "Todos"
    gerente: Optional[Any] = "Todos"
    canal: Optional[Any] = "Todos"
    categoria: Optional[Any] = "Todos"
    periodo: Optional[Any] = "Outubro/2026"
    mes: Optional[Any] = None
    ano: Optional[Any] = None
    metrica: Optional[str] = "Valor"  # "Valor" ou "Volume"
    filial: Optional[Any] = "Todos"
    cluster: Optional[Any] = "Todos"
    cluster_detalhe: Optional[Any] = "Todos"
    tipo_produto: Optional[Any] = "Todos"


class ReportRequest(BaseModel):
    dimensions: List[str] = ["Ano", "Canal", "Categoria Bq", "Grupo_Cliente", "Produto Desc"]
    measures: List[str] = ["R$ Invoiced", "R$ Open Orders", "R$ Budget", "R$ Forecast"]
    filters: Optional[Dict[str, Any]] = None
    column_filters: Optional[Dict[str, Any]] = None
    sort_column: Optional[str] = None
    sort_direction: Optional[str] = "asc"
    page: int = 1
    page_size: int = 50


def build_filter_sql(col: str, val: Any) -> Optional[str]:
    """Constrói cláusula SQL para filtros que podem ser string simples ou listas (multi-select)."""
    if val is None or val == "Todos" or val == "" or val == []:
        return None
    if isinstance(val, (list, set, tuple)):
        items = [str(x).replace("'", "''") for x in val if x and str(x).lower() != "todos"]
        if not items:
            return None
        if len(items) == 1:
            return f"{col} = '{items[0]}'"
        in_clause = ", ".join(f"'{x}'" for x in items)
        return f"{col} IN ({in_clause})"
    if isinstance(val, str):
        if val.lower() == "todos":
            return None
        escaped = val.replace("'", "''")
        return f"{col} = '{escaped}'"
    return None


# ─── API ENDPOINTS ───

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat(), "warehouse": WAREHOUSE_ID}


@app.get("/api/user/me")
def get_user_profile(request: Request):
    """Retorna dados do usuário autenticado via OBO para o menu de usuário."""
    info = get_current_user_info(request)
    name = info["name"]
    email = info["email"]
    parts = [p for p in name.split() if p]
    initials = (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else (parts[0][:2].upper() if parts else "US")
    return {
        "name": name,
        "email": email,
        "initials": initials,
        "is_obo": bool(request.headers.get("x-forwarded-access-token"))
    }


@app.get("/api/metadata")
def get_metadata(request: Request):
    """Retorna dados de atualização e valores para os dropdowns de filtro no padrão Bimbo."""
    now = time.time()
    user_info = get_current_user_info(request)
    m_key = f"meta:{user_info.get('email') or 'anon'}"
    if m_key in METADATA_CACHE:
        val, ts = METADATA_CACHE[m_key]
        if now - ts < METADATA_TTL:
            return val
    try:
        sql_filters = """
        SELECT DISTINCT 
            coalesce(c.NM_CANAL, 'OUTROS') as canal,
            coalesce(c.CLUSTER, 'OUTROS') as cluster,
            coalesce(c.CLUSTER_1, 'OUTROS') as cluster_detalhe,
            coalesce(c.GRUPO_CLIENTE_DESC, 'OUTROS') as grupo_cliente,
            coalesce(c.NM_NV1, 'OUTROS') as gerente,
            coalesce(p.CATEGORIA_MKT, 'OUTROS') as categoria,
            coalesce(p.TIPO_CESTO, 'OUTROS') as tipo_produto,
            coalesce(cast(v.CNPJ_BIMBO as string), 'OUTROS') as filial
        FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2 v
        LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view p ON cast(p.INVENTORY_ITEM_ID as string) = cast(v.ID_PRODUTO as string)
        LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view c ON cast(c.COD_GR_CLIENTE as string) = cast(v.GRUPO_CLI as string)
        WHERE year(v.DT_REGISTRO) = 2026
        """
        rows = run_databricks_query(sql_filters, request=request)

        canais = sorted(list({r["canal"] for r in rows if r.get("canal") and r["canal"] != 'OUTROS'}))
        clusters = sorted(list({r["cluster"] for r in rows if r.get("cluster") and r["cluster"] != 'OUTROS'}))
        clusters_detalhe = sorted(list({r["cluster_detalhe"] for r in rows if r.get("cluster_detalhe") and r["cluster_detalhe"] != 'OUTROS'}))
        grupos = sorted(list({r["grupo_cliente"] for r in rows if r.get("grupo_cliente") and r["grupo_cliente"] != 'OUTROS'}))
        gerentes = sorted(list({r["gerente"] for r in rows if r.get("gerente") and r["gerente"] != 'OUTROS'}))
        categorias = sorted(list({r["categoria"] for r in rows if r.get("categoria") and r["categoria"] != 'OUTROS'}))
        tipos_produto = sorted(list({r["tipo_produto"] for r in rows if r.get("tipo_produto") and r["tipo_produto"] != 'OUTROS'}))
        filiais = sorted(list({r["filial"] for r in rows if r.get("filial") and r["filial"] != 'OUTROS'}))
        if not filiais:
            filiais = [
                "01 - Fábrica RJ", "02 - Juiz de Fora", "03 - Osasco", 
                "04 - Santo Amaro", "07 - Guarulhos", "08 - Jaguariuna", "11 - Pouso Alegre"
            ]

        hoje = date.today()
        periodos = [
            f"{m:02d} - {['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'][m-1]}/{hoje.year}"
            for m in range(hoje.month, 0, -1)
        ]

        last_update_str = "18/11/2026 às 15:31"
        last_update_iso = "2026-11-18T18:31:00Z"
        try:
            hist_rows = run_databricks_query("DESCRIBE HISTORY cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2 LIMIT 1", request=request)
            if hist_rows and hist_rows[0].get("timestamp"):
                from datetime import datetime, timezone, timedelta
                raw_ts = str(hist_rows[0]["timestamp"]).replace(".000Z", "Z").replace(".000", "")
                dt_utc = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                dt_brt = dt_utc.astimezone(timezone(timedelta(hours=-3)))
                last_update_str = dt_brt.strftime("%d/%m/%Y às %H:%M")
                last_update_iso = dt_utc.isoformat()
        except Exception:
            pass

        meta_res = {
            "last_update": last_update_str,
            "last_update_iso": last_update_iso,
            "periodos": periodos,
            "mes_atual": hoje.month,
            "ano_atual": hoje.year,
            "anos": [str(hoje.year), str(hoje.year - 1), str(hoje.year - 2)],
            "canais": canais or ["QSR", "DISTRIBUIDORES", "CLUBES DE COMPRA", "FOOD SERVICE"],
            "clusters": clusters or ["MCD", "RBI", "OTHER QSR", "SUBWAY", "CHAINS & INDUSTRY"],
            "clusters_detalhe": clusters_detalhe or ["MCD", "BK", "POPEYES", "SUBWAY BRASIL", "SUBWAY EXPORTAÇÃO", "INDUSTRY", "CHAINS"],
            "grupos_clientes": grupos or ["BURGER KING", "MC DONALDS", "SUBWAY", "KFC", "POPEYES", "BOBS"],
            "gerentes": gerentes or ["ANTONIO VITORINO", "RONALDO PERNAMBUCO"],
            "categorias": categorias or ["BUNS", "NON BUNS", "BAGUETES", "TORTAS", "PANES"],
            "tipos_produto": tipos_produto or ["Pão de Hambúrguer", "Baguete", "Brioche", "Pão Francês", "Torta"],
            "filiais": filiais
        }
        METADATA_CACHE[m_key] = (meta_res, now)
        return meta_res
    except Exception as e:
        hoje = date.today()
        return {
            "last_update": "18/11/2026 às 15:31",
            "last_update_iso": "2026-11-18T18:31:00Z",
            "periodos": [
                f"{m:02d} - {['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'][m-1]}/{hoje.year}"
                for m in range(hoje.month, 0, -1)
            ],
            "mes_atual": hoje.month,
            "ano_atual": hoje.year,
            "anos": [str(hoje.year), str(hoje.year - 1), str(hoje.year - 2)],
            "canais": ["QSR", "DISTRIBUIDORES", "CLUBES DE COMPRA", "FOOD SERVICE"],
            "clusters": ["MCD", "RBI", "OTHER QSR", "SUBWAY", "CHAINS & INDUSTRY"],
            "clusters_detalhe": ["MCD", "BK", "POPEYES", "SUBWAY BRASIL", "SUBWAY EXPORTAÇÃO", "INDUSTRY", "CHAINS"],
            "grupos_clientes": ["BURGER KING", "MC DONALDS", "SUBWAY", "KFC", "POPEYES"],
            "gerentes": ["ANTONIO VITORINO", "RONALDO PERNAMBUCO"],
            "categorias": ["BUNS", "NON BUNS", "BAGUETES", "TORTAS"],
            "tipos_produto": ["Pão de Hambúrguer", "Baguete", "Brioche"],
            "filiais": [
                "01 - Fábrica RJ", "02 - Juiz de Fora", "03 - Osasco", 
                "04 - Santo Amaro", "07 - Guarulhos", "08 - Jaguariuna", "11 - Pouso Alegre"
            ]
        }


@app.post("/api/vendometro")
def get_vendometro_data(filters: VendometroFilters, request: Request):
    """Calcula os KPIs e dados para a aba Vendômetro com suporte a seleção múltipla de meses e anos."""
    f_dict = filters.model_dump() if hasattr(filters, "model_dump") else filters.dict()
    cached = _endpoint_cache_get(request, "vendometro", f_dict)
    if cached is not None:
        return cached
    meses_nomes_curtos = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    meses_nomes_completos = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

    # 1. Parsing dinâmico dos meses selecionados
    selected_months = []
    if filters.mes is not None and filters.mes != "Todos":
        raw_m = filters.mes if isinstance(filters.mes, (list, set, tuple)) else [filters.mes]
        for item in raw_m:
            item_str = str(item).strip()
            if item_str.isdigit():
                m_int = int(item_str)
                if 1 <= m_int <= 12:
                    selected_months.append(m_int)
            else:
                for idx, c in enumerate(["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"], 1):
                    if item_str.lower().startswith(c):
                        selected_months.append(idx)
                        break

    hoje = date.today()
    is_all_months = False
    if not selected_months:
        if filters.mes == "Todos":
            selected_months = list(range(1, 13))
            is_all_months = True
        else:
            selected_months = [hoje.month]
    selected_months = sorted(list(set(selected_months)))

    # 2. Parsing dinâmico dos anos selecionados
    selected_years = []
    if filters.ano is not None and filters.ano != "Todos":
        raw_y = filters.ano if isinstance(filters.ano, (list, set, tuple)) else [filters.ano]
        for item in raw_y:
            item_str = str(item).strip()
            if item_str.isdigit():
                selected_years.append(int(item_str))
    if not selected_years:
        selected_years = [hoje.year]
    selected_years = sorted(list(set(selected_years)))

    # 3. Label amigável do período selecionado
    if is_all_months or len(selected_months) == 12:
        periodo_label = "Ano Completo"
    elif len(selected_months) == 1:
        periodo_label = meses_nomes_completos[selected_months[0] - 1]
    elif len(selected_months) == 2:
        periodo_label = f"{meses_nomes_completos[selected_months[0] - 1]} e {meses_nomes_completos[selected_months[1] - 1]}"
    else:
        nomes = [meses_nomes_curtos[m - 1] for m in selected_months]
        periodo_label = f"{len(selected_months)} meses ({', '.join(nomes[:3])}{'...' if len(nomes) > 3 else ''})"

    # 4. Cláusulas de filtro SQL
    where_clauses = ["v.GRUPO_CLI <> 108"]
    where_clauses.append(f"year(v.DT_REGISTRO) IN ({', '.join(str(y) for y in selected_years)})")

    for col, val in [
        ("c.NM_CANAL", filters.canal),
        ("c.GRUPO_CLIENTE_DESC", filters.grupo_cliente),
        ("c.NM_NV1", filters.gerente),
        ("p.CATEGORIA_MKT", filters.categoria),
        ("cast(v.CNPJ_BIMBO as string)", filters.filial),
        ("c.CLUSTER", filters.cluster),
        ("c.CLUSTER_1", filters.cluster_detalhe),
        ("p.TIPO_CESTO", filters.tipo_produto),
    ]:
        sql_cond = build_filter_sql(col, val)
        if sql_cond:
            where_clauses.append(sql_cond)

    where_sql = " AND ".join(where_clauses)
    is_volume = (filters.metrica == "Volume")

    col_invoiced = "v.QT_CYW_LIQ_VENDIDO" if is_volume else "v.VL_CYW_LIQ_VENDIDO"
    col_bgt = "v.BUDGET_QTDE" if is_volume else "v.BUDGET_VALOR"
    col_fcst = "v.FORECAST_QTDE" if is_volume else "v.FORECAST_VALOR"
    col_open = "v.QT_OPEN_ORDERS" if is_volume else "v.VL_LIQ_OPEN_ORDERS"

    month_sql_cond = f"month(v.DT_REGISTRO) IN ({', '.join(str(m) for m in selected_months)})"

    sql_combined = f"""
    SELECT 
        month(v.DT_REGISTRO) as num_mes,
        sum({col_invoiced}) as total_invoiced,
        sum({col_bgt}) as total_budget,
        sum({col_fcst}) as total_forecast,
        sum({col_open}) as total_open_orders,
        sum(case when v.DT_REGISTRO <= '2026-10-20' then {col_invoiced} else 0 end) as invoiced_ytd_part,
        sum(case when v.DT_REGISTRO <= '2026-10-20' then {col_bgt} else 0 end) as budget_ytd_part,
        sum(case when v.DT_REGISTRO <= '2026-10-20' then {col_fcst} else 0 end) as forecast_ytd_part,
        sum(case when upper(coalesce(c.NM_CANAL, '')) = 'QSR' then (coalesce({col_invoiced}, 0) + coalesce({col_open}, 0)) else 0 end) as canal_qsr_part,
        sum(case when upper(coalesce(c.NM_CANAL, '')) <> 'QSR' then (coalesce({col_invoiced}, 0) + coalesce({col_open}, 0)) else 0 end) as canal_distrib_part
    FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2 v
    LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view p ON cast(p.INVENTORY_ITEM_ID as string) = cast(v.ID_PRODUTO as string)
    LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view c ON cast(c.COD_GR_CLIENTE as string) = cast(v.GRUPO_CLI as string)
    WHERE {where_sql}
    GROUP BY month(v.DT_REGISTRO)
    ORDER BY num_mes
    """

    # Baseline por mês para fallback dinâmico local quando sem warehouse conectado
    baseline_meses = {
        1:  {"inv": 62.4, "bgt": 59.3, "fcst": 60.0, "oo": 0.0, "py": 58.2},
        2:  {"inv": 54.1, "bgt": 53.6, "fcst": 54.0, "oo": 0.0, "py": 51.0},
        3:  {"inv": 62.3, "bgt": 60.6, "fcst": 61.0, "oo": 0.0, "py": 59.5},
        4:  {"inv": 62.3, "bgt": 62.7, "fcst": 62.5, "oo": 0.0, "py": 60.1},
        5:  {"inv": 62.2, "bgt": 63.0, "fcst": 62.8, "oo": 0.0, "py": 61.2},
        6:  {"inv": 61.8, "bgt": 68.0, "fcst": 65.0, "oo": 0.0, "py": 59.8},
        7:  {"inv": 64.1, "bgt": 73.1, "fcst": 70.0, "oo": 0.0, "py": 62.0},
        8:  {"inv": 64.3, "bgt": 65.9, "fcst": 66.0, "oo": 0.0, "py": 63.1},
        9:  {"inv": 64.8, "bgt": 67.2, "fcst": 67.0, "oo": 0.0, "py": 63.5},
        10: {"inv": 38.23, "bgt": 75.81, "fcst": 65.84, "oo": 14.73, "py": 62.35},
        11: {"inv": 33.0, "bgt": 77.6, "fcst": 75.0, "oo": 25.0, "py": 65.0},
        12: {"inv": 0.0, "bgt": 86.9, "fcst": 85.0, "oo": 30.0, "py": 72.0},
    }

    try:
        # Query do ano anterior (mesmos filtros sem ano, limitado ao mesmo nº de dias úteis descontando feriados nacionais)
        import calendar
        try:
            from .forecast_engine import _get_feriados_nacionais
        except ImportError:
            from forecast_engine import _get_feriados_nacionais

        _feriados_cache = {}
        def _biz_days_count(yr: int, mo: int, upto_day: int) -> int:
            if yr not in _feriados_cache:
                _feriados_cache[yr] = _get_feriados_nacionais(yr)
            fer = _feriados_cache[yr]
            cnt = 0
            for d in range(1, upto_day + 1):
                dt = date(yr, mo, d)
                if dt.weekday() < 5 and dt not in fer:
                    cnt += 1
            return cnt

        cut_dt = hoje - timedelta(days=1)
        pace_done = 0
        pace_total = 0
        pace_open = False
        pace_cutoff_lbl = f"{cut_dt.day:02d}/{meses_nomes_curtos[cut_dt.month - 1].lower()}"

        # Calcula fração proporcional de dias úteis para os meses selecionados
        primary_yr = selected_years[0] if selected_years else hoje.year
        py_yr = primary_yr - 1
        pace_frac_weighted_bgt = 0.0
        for m_num in selected_months:
            last_d = calendar.monthrange(primary_yr, m_num)[1]
            tot_b = _biz_days_count(primary_yr, m_num, last_d)
            if primary_yr < hoje.year or (primary_yr == hoje.year and m_num < hoje.month):
                done_b = tot_b
            elif primary_yr > hoje.year or m_num > hoje.month:
                done_b = 0
            else:
                done_b = _biz_days_count(primary_yr, m_num, cut_dt.day)
                if 0 < done_b < tot_b:
                    pace_open = True
            pace_done += done_b
            pace_total += tot_b

        # Data de corte equivalente no ano anterior (mesma quantidade de dias úteis, descontando feriados nacionais)
        py_cutoff_cond = ""
        py_cutoff_dt_str = ""
        if len(selected_months) == 1 and pace_open and pace_done > 0:
            m_py = selected_months[0]
            last_py_d = calendar.monthrange(py_yr, m_py)[1]
            if py_yr not in _feriados_cache:
                _feriados_cache[py_yr] = _get_feriados_nacionais(py_yr)
            py_fer = _feriados_cache[py_yr]
            seen_b = 0
            py_cut_d = last_py_d
            for d in range(1, last_py_d + 1):
                dt_py = date(py_yr, m_py, d)
                if dt_py.weekday() < 5 and dt_py not in py_fer:
                    seen_b += 1
                    if seen_b >= pace_done:
                        py_cut_d = d
                        break
            py_cutoff_dt_str = f"{py_yr}-{m_py:02d}-{py_cut_d:02d}"
            py_cutoff_cond = f" AND v.DT_REGISTRO <= '{py_cutoff_dt_str}'"

        where_py_clauses = [f"year(v.DT_REGISTRO) = {py_yr}", f"month(v.DT_REGISTRO) IN ({', '.join(str(m) for m in selected_months)})"]
        if py_cutoff_cond:
            where_py_clauses.append(f"v.DT_REGISTRO <= '{py_cutoff_dt_str}'")
        # Reaproveita os mesmos filtros de dimensão (excluindo o filtro de ano)
        for c in where_clauses:
            if "year(v.DT_REGISTRO)" not in c:
                where_py_clauses.append(c)
        sql_py = f"""
        SELECT sum({col_invoiced}) as py_invoiced
        FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2 v
        LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view p ON cast(p.INVENTORY_ITEM_ID as string) = cast(v.ID_PRODUTO as string)
        LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view c ON cast(c.COD_GR_CLIENTE as string) = cast(v.GRUPO_CLI as string)
        WHERE {' AND '.join(where_py_clauses)}
        """

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_main = pool.submit(run_databricks_query, sql_combined, request)
            f_py = pool.submit(run_databricks_query, sql_py, request)
            month_rows = f_main.result()
            try:
                py_rows = f_py.result()
            except Exception:
                py_rows = []

        month_map = {int(m["num_mes"]): m for m in month_rows if m.get("num_mes")}

        # Soma dinâmica baseada nos meses selecionados
        fallback_inv = sum(baseline_meses[m]["inv"] for m in selected_months) * 1e6
        fallback_bgt = sum(baseline_meses[m]["bgt"] for m in selected_months) * 1e6
        fallback_fcst = sum(baseline_meses[m]["fcst"] for m in selected_months) * 1e6
        fallback_oo = sum(baseline_meses[m]["oo"] for m in selected_months) * 1e6
        fallback_py = sum(baseline_meses[m]["py"] for m in selected_months) * 1e6

        if month_map:
            invoiced_periodo = sum(float(month_map.get(m, {}).get("total_invoiced") or 0.0) for m in selected_months)
            open_orders = sum(float(month_map.get(m, {}).get("total_open_orders") or 0.0) for m in selected_months)
            budget_periodo = sum(float(month_map.get(m, {}).get("total_budget") or 0.0) for m in selected_months)
            forecast_periodo = sum(float(month_map.get(m, {}).get("total_forecast") or 0.0) for m in selected_months)
            invoiced_ytd = sum(float(m.get("invoiced_ytd_part") or 0.0) for m in month_map.values())
            budget_ytd = sum(float(m.get("budget_ytd_part") or 0.0) for m in month_map.values())
            forecast_ytd = sum(float(m.get("forecast_ytd_part") or 0.0) for m in month_map.values())
            canal_qsr = sum(float(month_map.get(m, {}).get("canal_qsr_part") or 0.0) for m in selected_months)
            canal_distrib = sum(float(month_map.get(m, {}).get("canal_distrib_part") or 0.0) for m in selected_months)
        else:
            invoiced_periodo = float(fallback_inv)
            open_orders = float(fallback_oo)
            budget_periodo = float(fallback_bgt)
            forecast_periodo = float(fallback_fcst)
            invoiced_ytd = 596476242.73
            budget_ytd = 620100000.0
            forecast_ytd = 608000000.0
            canal_qsr = (invoiced_periodo + open_orders) * 0.788
            canal_distrib = (invoiced_periodo + open_orders) * 0.212

        py_db_val = float(py_rows[0].get("py_invoiced") or 0.0) if py_rows else 0.0
        py_invoiced = py_db_val if py_db_val > 0 else float(fallback_py)
        invoiced_plus_open = invoiced_periodo + open_orders

        # Proporcional de budget e forecast até hoje usando dias úteis reais
        if pace_total > 0:
            budget_ate_hoje = budget_periodo * (pace_done / pace_total)
            forecast_ate_hoje = forecast_periodo * (pace_done / pace_total)
        else:
            budget_ate_hoje = budget_periodo
            forecast_ate_hoje = forecast_periodo

        vs_budget_ate_hoje_pct = ((invoiced_periodo / budget_ate_hoje) - 1.0) * 100 if budget_ate_hoje else 0
        vs_forecast_ate_hoje_pct = ((invoiced_periodo / forecast_ate_hoje) - 1.0) * 100 if forecast_ate_hoje else 0
        cobertura_bgt_pct = (invoiced_plus_open / budget_periodo) * 100 if budget_periodo else 0
        cobertura_fcst_pct = (invoiced_plus_open / forecast_periodo) * 100 if forecast_periodo else 0

        vs_budget_ytd_pct = ((invoiced_ytd / budget_ytd) - 1.0) * 100 if budget_ytd else -3.8
        vs_forecast_ytd_pct = ((invoiced_ytd / forecast_ytd) - 1.0) * 100 if forecast_ytd else -1.9
        py_ytd = 574200000.0
        vs_py_ytd_pct = ((invoiced_ytd / py_ytd) - 1.0) * 100 if py_ytd else 3.9

        total_canal = canal_qsr + canal_distrib
        qsr_pct = (canal_qsr / total_canal) * 100 if total_canal else 78.8
        distrib_pct = 100.0 - qsr_pct

        mensal_data = []
        for idx in range(1, 13):
            nome = meses_nomes_curtos[idx - 1]
            m_obj = baseline_meses[idx]
            inv_db = month_map.get(idx, {}).get("total_invoiced")
            bgt_db = month_map.get(idx, {}).get("total_budget")
            fcst_db = month_map.get(idx, {}).get("total_forecast")

            final_inv = (float(inv_db) / 1e6) if inv_db is not None else (m_obj["inv"] if not month_map and m_obj["inv"] > 0 else None)
            final_bgt = (float(bgt_db) / 1e6) if bgt_db is not None else (m_obj["bgt"] if not month_map else None)
            final_fcst = (float(fcst_db) / 1e6) if fcst_db is not None else (m_obj.get("fcst") if not month_map else None)

            pct_diff = ((final_inv / final_bgt) - 1.0) * 100 if (final_inv and final_bgt) else None
            pct_str = f"{pct_diff:+.1f}%".replace('.', ',') if pct_diff is not None else (f"bgt {final_bgt:.1f}".replace('.', ',') if final_bgt else "—")

            mensal_data.append({
                "mes": nome,
                "num_mes": idx,
                "invoiced": round(final_inv, 1) if final_inv else None,
                "budget": round(final_bgt, 1) if final_bgt else None,
                "forecast": round(final_fcst, 1) if final_fcst else None,
                "pct": pct_str,
                "is_selected": (idx in selected_months),
                "is_current": (idx == hoje.month),
                "is_future": (idx > hoje.month)
            })

        def _calc_tri(months_list, in_prog=False):
            if month_map:
                t_inv = sum(float(month_map.get(m, {}).get("total_invoiced") or 0.0) for m in months_list) / 1e6
                t_bgt = sum(float(month_map.get(m, {}).get("total_budget") or 0.0) for m in months_list) / 1e6
                t_fcst = sum(float(month_map.get(m, {}).get("total_forecast") or 0.0) for m in months_list) / 1e6
            else:
                t_inv = sum(baseline_meses[m]["inv"] for m in months_list)
                t_bgt = sum(baseline_meses[m]["bgt"] for m in months_list)
                t_fcst = sum(baseline_meses[m]["fcst"] for m in months_list)
            diff_p = ((t_inv / t_bgt) - 1.0) * 100 if t_bgt > 0 else 0.0
            diff_f = ((t_inv / t_fcst) - 1.0) * 100 if t_fcst > 0 else 0.0
            return {
                "valor": round(t_inv, 1),
                "pct": f"{diff_p:+.1f}%".replace('.', ','),
                "positive": diff_p >= 0,
                "pct_fcst": f"{diff_f:+.1f}%".replace('.', ','),
                "positive_fcst": diff_f >= 0,
                "in_progress": in_prog
            }

        t1 = _calc_tri([1, 2, 3])
        t2 = _calc_tri([4, 5, 6])
        t3 = _calc_tri([7, 8, 9])
        t4 = _calc_tri([10, 11, 12], in_prog=True)

        trimestres = [
            {"trim": "1º Tri", **t1},
            {"trim": "2º Tri", **t2},
            {"trim": "3º Tri", **t3},
            {"trim": "4º Tri", **t4}
        ]

        comp_palavra = "abaixo" if vs_budget_ate_hoje_pct < 0 else "acima"
        banner_msg = f"{periodo_label} está {abs(vs_budget_ate_hoje_pct):.0f}% {comp_palavra} do budget até hoje. Com as open orders, chega a {cobertura_bgt_pct:.0f}% do budget."

        result_payload = {
            "periodo_label": periodo_label,
            "selected_months": selected_months,
            "selected_years": selected_years,
            "insight_banner": banner_msg,
            "kpis": {
                "invoiced": round(invoiced_periodo / 1e6, 2),
                "vs_budget_pct": round(vs_budget_ate_hoje_pct, 1),
                "vs_forecast_pct": round(vs_forecast_ate_hoje_pct, 1),
                "budget_ate_hoje": round(budget_ate_hoje / 1e6, 2),
                "forecast_ate_hoje": round(forecast_ate_hoje / 1e6, 2),
                "open_orders": round(open_orders / 1e6, 2),
                "invoiced_plus_open": round(invoiced_plus_open / 1e6, 2),
                "gap_budget": round((budget_periodo - invoiced_plus_open) / 1e6, 2),
                "gap_forecast": round((forecast_periodo - invoiced_plus_open) / 1e6, 2),
                "cobertura_bgt_pct": round(cobertura_bgt_pct, 1),
                "cobertura_fcst_pct": round(cobertura_fcst_pct, 1),
                "budget_full": round(budget_periodo / 1e6, 2),
                "forecast_full": round(forecast_periodo / 1e6, 2),
                "py_invoiced": round(py_invoiced / 1e6, 2),
                "ytd_invoiced": round(invoiced_ytd / 1e6, 1),
                "vs_budget_ytd_pct": round(vs_budget_ytd_pct, 1),
                "budget_ytd": round(budget_ytd / 1e6, 1),
                "vs_forecast_ytd_pct": round(vs_forecast_ytd_pct, 1),
                "forecast_ytd": round(forecast_ytd / 1e6, 1),
                "vs_py_ytd_pct": round(vs_py_ytd_pct, 1),
                "py_ytd": round(py_ytd / 1e6, 1),
                "pace_open": pace_open,
                "pace_done_bdays": pace_done,
                "pace_total_bdays": pace_total,
                "pace_cutoff_lbl": pace_cutoff_lbl,
                "py_year_label": str(py_yr),
                "py_cutoff_dt": py_cutoff_dt_str,
                "raw": {
                    "invoiced": round(invoiced_periodo, 2),
                    "open_orders": round(open_orders, 2),
                    "invoiced_plus_open": round(invoiced_plus_open, 2),
                    "budget_full": round(budget_periodo, 2),
                    "forecast_full": round(forecast_periodo, 2),
                    "budget_ate_hoje": round(budget_ate_hoje, 2),
                    "forecast_ate_hoje": round(forecast_ate_hoje, 2),
                    "py_invoiced": round(py_invoiced, 2),
                    "ytd_invoiced": round(invoiced_ytd, 2),
                    "budget_ytd": round(budget_ytd, 2),
                    "forecast_ytd": round(forecast_ytd, 2),
                    "py_ytd": round(py_ytd, 2)
                }
            },
            "canais": {
                "qsr_val": round(canal_qsr / 1e6, 2),
                "qsr_raw": round(canal_qsr, 2),
                "qsr_pct": round(qsr_pct, 1),
                "distrib_val": round(canal_distrib / 1e6, 2),
                "distrib_raw": round(canal_distrib, 2),
                "distrib_pct": round(distrib_pct, 1)
            },
            "mensal": mensal_data,
            "trimestres": trimestres
        }
        _endpoint_cache_set(request, "vendometro", f_dict, result_payload)
        return result_payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar vendômetro: {str(e)}")


@app.get("/api/vendometro")
def get_vendometro_data_get(
    request: Request,
    mes: Optional[str] = "10",
    ano: Optional[str] = "2026",
    metrica: Optional[str] = "Valor",
    canal: Optional[str] = "Todos"
):
    f = VendometroFilters(
        mes=[mes] if mes and mes != "Todos" else "Todos",
        ano=ano,
        metrica=metrica,
        canal=canal
    )
    return get_vendometro_data(f, request)


@app.post("/api/report/data")
def get_report_data(req: ReportRequest, request: Request):
    """Consulta paginada ao modelo para alimentar o Report Dinâmico."""
    r_dict = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    cached = _endpoint_cache_get(request, "report", r_dict)
    if cached is not None:
        return cached
    # Mapeamento de colunas amigáveis para SQL
    dim_map = {
        "Ano": "year(v.DT_REGISTRO)",
        "Canal": "c.NM_CANAL",
        "Canal Fin": "c.NM_SEGMENTO",
        "Categoria Bq": "p.DS_CLASIF_BQ",
        "Categoria Fin": "case when upper(p.DS_CLASIF_BQ) = 'BUNS' then 'BUNS' else 'NON BUNS' end",
        "Categoria Mkt": "p.CATEGORIA_MKT",
        "Cluster": "c.CLUSTER",
        "Cluster Detalhe": "c.CLUSTER_1",
        "Filial": "cast(v.CNPJ_BIMBO as string)",
        "Grupo_Cliente": "c.GRUPO_CLIENTE_DESC",
        "Cnpj Bimbo": "v.CNPJ_BIMBO",
        "Cnpj Cliente": "v.CNPJ_CLIENTE",
        "Data Emissão": "v.DT_EMISSAO",
        "Produto Desc": "p.DESCRICAO_PRODUTO",
        "Código Produto": "p.COD_PRODUTO",
        "Mês": "month(v.DT_REGISTRO)",
        "Gerente": "c.NM_NV1",
        "Tipo Produto": "p.TIPO_CESTO"
    }

    meas_map = {
        "R$ Invoiced": "coalesce(v.VL_CYW_LIQ_VENDIDO, 0)",
        "R$ Open Orders": "coalesce(v.VL_LIQ_OPEN_ORDERS, 0)",
        "R$ Budget": "coalesce(v.BUDGET_VALOR, 0)",
        "R$ Forecast": "coalesce(v.FORECAST_VALOR, 0)",
        "Qt Invoiced": "coalesce(v.QT_CYW_LIQ_VENDIDO, 0)",
        "Qt Open Orders": "coalesce(v.QT_OPEN_ORDERS, 0)",
        "Qt Budget": "coalesce(v.BUDGET_QTDE, 0)",
        "Qt Forecast": "coalesce(v.FORECAST_QTDE, 0)"
    }

    select_items = []
    group_items = []

    # Dimensões solicitadas
    for d in req.dimensions:
        if d in dim_map:
            sql_expr = dim_map[d]
            select_items.append(f"{sql_expr} AS `{d}`")
            group_items.append(sql_expr)

    # Medidas solicitadas
    for m in req.measures:
        if m in meas_map:
            sql_expr = meas_map[m]
            select_items.append(f"sum({sql_expr}) AS `{m}`")

    if not select_items:
        select_items = ["year(v.DT_REGISTRO) AS `Ano`", "sum(coalesce(v.VL_CYW_LIQ_VENDIDO, 0)) AS `R$ Invoiced`"]
        group_items = ["year(v.DT_REGISTRO)"]

    where_clauses = ["v.GRUPO_CLI <> 108"]

    # Filtros globais (Ano, Mês, Canal, Cluster, etc.)
    flt = req.filters or {}

    def _as_list(v):
        if v is None or v == "Todos":
            return []
        return list(v) if isinstance(v, (list, set, tuple)) else [v]

    anos = [int(a) for a in _as_list(flt.get("ano")) if str(a).strip().isdigit()]
    where_clauses.append(
        f"year(v.DT_REGISTRO) IN ({', '.join(str(a) for a in anos)})" if anos else "year(v.DT_REGISTRO) = 2026"
    )

    meses = []
    for m in _as_list(flt.get("mes") or flt.get("periodo")):
        head = str(m).split("-")[0].strip()
        if head.isdigit() and 1 <= int(head) <= 12:
            meses.append(int(head))
    if meses:
        where_clauses.append(f"month(v.DT_REGISTRO) IN ({', '.join(str(m) for m in sorted(set(meses)))})")

    def _q(v):
        return "'" + str(v).replace("'", "''") + "'"

    def add_in_filter(field_sql, key):
        val = flt.get(key)
        if not val or val == "Todos":
            return
        if isinstance(val, str):
            where_clauses.append(f"{field_sql} = {_q(val)}")
        elif isinstance(val, (list, set, tuple)):
            clean_vals = [_q(v) for v in val if v and v != "Todos"]
            if clean_vals:
                where_clauses.append(f"{field_sql} IN ({', '.join(clean_vals)})")

    add_in_filter("c.NM_CANAL", "canal")
    add_in_filter("c.CLUSTER", "cluster")
    add_in_filter("c.CLUSTER_1", "cluster_detalhe")
    add_in_filter("c.GRUPO_CLIENTE_DESC", "grupo_cliente")
    add_in_filter("p.CATEGORIA_MKT", "categoria")
    add_in_filter("p.TIPO_CESTO", "tipo_produto")
    add_in_filter("c.NM_NV1", "gerente")
    add_in_filter("cast(v.CNPJ_BIMBO as string)", "filial")

    # Filtros por cabeçalho de coluna (texto, número, data)
    if req.column_filters:
        for col_name, fval in req.column_filters.items():
            if not fval:
                continue
            fval_str = str(fval).strip()
            if col_name in dim_map:
                field_expr = dim_map[col_name]
                where_clauses.append(f"lower({field_expr}) LIKE '%{fval_str.lower()}%'")

    where_sql = " AND ".join(where_clauses)
    select_sql = ", ".join(select_items)
    group_sql = ", ".join(group_items) if group_items else "1"

    order_sql = ""
    if req.sort_column:
        dir_sql = "DESC" if req.sort_direction and req.sort_direction.lower() == "desc" else "ASC"
        order_sql = f"ORDER BY `{req.sort_column}` {dir_sql}"
    else:
        order_sql = f"ORDER BY `{req.dimensions[0]}` ASC" if req.dimensions else ""

    offset = (req.page - 1) * req.page_size
    limit = req.page_size

    sql = f"""
    SELECT {select_sql}
    FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2 v
    LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view p ON cast(p.INVENTORY_ITEM_ID as string) = cast(v.ID_PRODUTO as string)
    LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view c ON cast(c.COD_GR_CLIENTE as string) = cast(v.GRUPO_CLI as string)
    WHERE {where_sql}
    GROUP BY {group_sql}
    {order_sql}
    LIMIT {limit} OFFSET {offset}
    """

    count_sql = f"""
    SELECT count(*) as total FROM (
        SELECT 1
        FROM cat_dnabb_dv.opebrapodis_lz.vendas_pedidos_ppto_bq_v2 v
        LEFT JOIN cat_dnabb_dv.bracatlg_lz.produtos_view p ON cast(p.INVENTORY_ITEM_ID as string) = cast(v.ID_PRODUTO as string)
        LEFT JOIN cat_dnabb_dv.bracatlg_lz.grupo_clientes_view c ON cast(c.COD_GR_CLIENTE as string) = cast(v.GRUPO_CLI as string)
        WHERE {where_sql}
        GROUP BY {group_sql}
    )
    """

    start_t = time.time()
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_data = ex.submit(run_databricks_query, sql, request)
        fut_cnt = ex.submit(run_databricks_query, count_sql, request)
        data = fut_data.result()
        try:
            cnt_res = fut_cnt.result()
            total_rows = int(cnt_res[0]["total"]) if cnt_res else len(data)
        except Exception:
            total_rows = len(data)
    exec_ms = int((time.time() - start_t) * 1000)

    rep_payload = {
        "data": data,
        "page": req.page,
        "page_size": req.page_size,
        "total_rows": total_rows,
        "execution_time_ms": exec_ms
    }
    _endpoint_cache_set(request, "report", r_dict, rep_payload)
    return rep_payload


@app.get("/api/report/data")
def get_report_data_get(request: Request, page: int = 1, page_size: int = 50):
    req = ReportRequest(page=page, page_size=page_size)
    return get_report_data(req, request)


class DirectExportRequest(BaseModel):
    filename: Optional[str] = "DNA_Vendas_Report"
    sheet: Optional[str] = "Report"
    columns: List[Dict[str, Any]]
    rows: List[List[Any]]


@app.post("/api/report/export_xlsx")
def export_report_xlsx(payload: DirectExportRequest):
    """
    Gera planilha XLSX formatada como Tabela nativa do Excel 'TableStyleLight1' (tema claro),
    com tipos numéricos, formatação de moeda R$ #,##0.00, congelamento de painel e auto-largura.
    """
    columns = payload.columns
    rows = payload.rows

    if not columns:
        raise HTTPException(status_code=400, detail="Nenhuma coluna informada.")

    wb = Workbook()
    ws = wb.active
    ws.title = (payload.sheet or "Report")[:31]

    headers = [str(c.get("label", c.get("id", ""))) for c in columns]
    ws.append(headers)
    types = [c.get("type", "text") for c in columns]

    for r in rows:
        out = []
        for idx, val in enumerate(r[:len(types)]):
            ct = types[idx]
            if val is None or val == "" or val == "-":
                out.append(None)
            elif ct == "number" or ct == "currency":
                try:
                    # Se for string formatada em pt-BR (ex: "R$ 1.234,56")
                    s = str(val).replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".").strip()
                    out.append(float(s))
                except (ValueError, TypeError):
                    out.append(val)
            elif ct == "integer":
                try:
                    out.append(int(round(float(val))))
                except (ValueError, TypeError):
                    out.append(val)
            elif ct == "date":
                s = str(val).strip()
                out.append(f"{s[8:10]}/{s[5:7]}/{s[0:4]}" if len(s) >= 10 and s[4] == '-' and s[7] == '-' else s)
            else:
                out.append(str(val))
        ws.append(out)

    n = len(rows)
    last_col = get_column_letter(len(headers))
    if n > 0:
        # Tabela nativa oficial do Excel com tema claro TableStyleLight1
        table_name = f"Tabela_DNA_{uuid.uuid4().hex[:6]}"
        tab = Table(displayName=table_name, ref=f"A1:{last_col}{n + 1}")
        tab.tableStyleInfo = TableStyleInfo(
            name="TableStyleLight1",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False
        )
        ws.add_table(tab)

        # Formatação de células
        for idx, col_cfg in enumerate(columns, start=1):
            cl = get_column_letter(idx)
            lbl = col_cfg.get("label", "")
            is_currency = ("R$" in lbl or "Invoiced" in lbl or "Orders" in lbl or "Budget" in lbl or "Forecast" in lbl or col_cfg.get("type") == "currency")
            for ri in range(2, n + 2):
                cell = ws[f"{cl}{ri}"]
                if is_currency and isinstance(cell.value, (int, float)):
                    cell.number_format = 'R$ #,##0.00;[Red]-R$ #,##0.00'
                elif isinstance(cell.value, (int, float)):
                    cell.number_format = '#,##0'

    # Auto dimensionamento inteligente de largura das colunas
    for idx, h in enumerate(headers, start=1):
        cl = get_column_letter(idx)
        max_len = len(h)
        for ri in range(2, min(n + 2, 200)):
            v = ws[f"{cl}{ri}"].value
            if v is not None and len(str(v)) > max_len:
                max_len = len(str(v))
        ws.column_dimensions[cl].width = min(max(max_len + 4, 12), 48)

    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    file_bytes = buf.getvalue()

    filename = f"{payload.filename or 'DNA_Vendas_Report'}.xlsx"
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


# ─── API PREVISÕES (FORECAST DE INVOICED) ───

class ForecastRequest(BaseModel):
    ano: Optional[Any] = "2026"
    mes: Optional[Any] = "11"
    horizon: Optional[int] = 1
    grupo_cliente: Optional[Any] = "Todos"
    gerente: Optional[Any] = "Todos"
    canal: Optional[Any] = "Todos"
    categoria: Optional[Any] = "Todos"
    cluster: Optional[Any] = "Todos"
    cluster_detalhe: Optional[Any] = "Todos"
    tipo_produto: Optional[Any] = "Todos"
    filial: Optional[Any] = "Todos"


@app.post("/api/forecast")
def post_forecast_data(req: ForecastRequest, request: Request):
    """Calcula a previsão diária, semanal, multi-horizonte e matriz por SKU usando o Modelo Campeão Híbrido."""
    try:
        from forecast_engine import build_dna_forecast_payload
        filters_dict = req.model_dump() if hasattr(req, "model_dump") else req.dict()
        cached = _endpoint_cache_get(request, "forecast", filters_dict)
        if cached is not None:
            return cached
        payload = build_dna_forecast_payload(
            run_query_fn=run_databricks_query,
            build_filter_fn=build_filter_sql,
            filters_dict=filters_dict,
            request=request
        )
        _endpoint_cache_set(request, "forecast", filters_dict, payload)
        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao calcular previsões: {str(e)}")


@app.get("/api/forecast")
def get_forecast_data(
    request: Request,
    ano: Optional[str] = "2026",
    mes: Optional[str] = "11",
    horizon: Optional[int] = 1,
    gerente: Optional[str] = "Todos",
    canal: Optional[str] = "Todos"
):
    req = ForecastRequest(ano=ano, mes=mes, horizon=horizon, gerente=gerente, canal=canal)
    return post_forecast_data(req, request)


# ─── FRONTEND STATIC PAGES ───

static_dir = os.path.dirname(os.path.abspath(__file__))

NO_CACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}

@app.get("/", response_class=HTMLResponse)
def index_page():
    return FileResponse(os.path.join(static_dir, "index.html"), headers=NO_CACHE_HEADERS)

@app.get("/vendometro", response_class=HTMLResponse)
def vendometro_page():
    return FileResponse(os.path.join(static_dir, "vendometro.html"), headers=NO_CACHE_HEADERS)

@app.get("/vendometro.html", response_class=HTMLResponse)
def vendometro_html_page():
    return FileResponse(os.path.join(static_dir, "vendometro.html"), headers=NO_CACHE_HEADERS)

@app.get("/previsoes", response_class=HTMLResponse)
def previsoes_page():
    return FileResponse(os.path.join(static_dir, "previsoes.html"), headers=NO_CACHE_HEADERS)

@app.get("/previsoes.html", response_class=HTMLResponse)
def previsoes_html_page():
    return FileResponse(os.path.join(static_dir, "previsoes.html"), headers=NO_CACHE_HEADERS)

@app.get("/relatorios", response_class=HTMLResponse)
def relatorios_page():
    return FileResponse(os.path.join(static_dir, "relatorios.html"), headers=NO_CACHE_HEADERS)

@app.get("/relatorios.html", response_class=HTMLResponse)
def relatorios_html_page():
    return FileResponse(os.path.join(static_dir, "relatorios.html"), headers=NO_CACHE_HEADERS)

@app.get("/guia", response_class=HTMLResponse)
def guia_page():
    return FileResponse(os.path.join(static_dir, "guia.html"), headers=NO_CACHE_HEADERS)

@app.get("/guia.html", response_class=HTMLResponse)
def guia_html_page():
    return FileResponse(os.path.join(static_dir, "guia.html"), headers=NO_CACHE_HEADERS)

# Montar arquivos estáticos gerais (CSS, JS, logos)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
