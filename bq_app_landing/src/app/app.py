import os
import io
import re
import csv
import json
import logging
import unicodedata
from datetime import datetime
from flask import Flask, jsonify, request, Response, send_from_directory, redirect
from flask_cors import CORS
import pandas as pd
import numpy as np
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo, TableColumn
from openpyxl.worksheet.filters import AutoFilter
from openpyxl.utils import get_column_letter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bq_landing")

# No padrão compras-360: static_folder='.' serve todos os arquivos estáticos diretamente da raiz do app
app = Flask(__name__, static_folder=".")
CORS(app)

def get_volume_path():
    """
    Retorna dinamicamente o caminho do Volume Unity Catalog de acordo com o ambiente.
    Identifica automaticamente se a aplicação está rodando em DEV ou PROD através do Databricks Apps runtime.
    """
    catalog = os.environ.get("CATALOG", "cat_dnabb_dv")
    schema = os.environ.get("SCHEMA", "grobbbqb_sz")
    app_name = (os.environ.get("DATABRICKS_APP_NAME") or "").lower()
    app_url = (os.environ.get("DATABRICKS_APP_URL") or "").lower()
    is_prod = "prod" in app_name or "prod" in app_url

    env_vol = os.environ.get("VOLUME_PATH", "").strip()
    if env_vol:
        if is_prod and "dev_bq_landing" in env_vol:
            return env_vol.replace("dev_bq_landing", "prod_bq_landing")
        if not is_prod and "prod_bq_landing" in env_vol:
            return env_vol.replace("prod_bq_landing", "dev_bq_landing")
        return env_vol

    target_volume = "prod_bq_landing" if is_prod else "dev_bq_landing"
    return f"/Volumes/{catalog}/{schema}/{target_volume}/base_landing.xlsx"


PORT = int(os.environ.get("PORT", 8000))
CATALOG = os.environ.get("CATALOG", "cat_dnabb_dv")
SCHEMA = os.environ.get("SCHEMA", "grobbbqb_sz")
TABLE = os.environ.get("TABLE", "tbl_bq_landing")
VOLUME_PATH = get_volume_path()

# ── Cache em memória da Base de Dados Real ─────────────────────────────────────
_cached_df = None
_cached_mtime = 0
_cached_path = None


def _normalize_col(c):
    """Normaliza nomes de coluna removendo acentuação e pontuações para chave maiúscula."""
    nfd = unicodedata.normalize('NFD', str(c))
    no_accents = ''.join(ch for ch in nfd if unicodedata.category(ch) != 'Mn')
    return re.sub(r'[^A-Z0-9]+', '_', no_accents.strip().upper()).strip('_')


def _get_field_val(row_dict, key, label=None):
    """Obtém o valor de um campo de forma insensível a maiúsculas/minúsculas e aceitando label ou key."""
    if not isinstance(row_dict, dict):
        return ""
    if key in row_dict and row_dict[key] is not None:
        return row_dict[key]
    if label and label in row_dict and row_dict[label] is not None:
        return row_dict[label]
    for k, v in row_dict.items():
        if k.lower() == key.lower() or (label and k.lower() == label.lower()):
            if v is not None:
                return v
    return ""


def _infer_unidade_de_medida(r):
    """
    Infere a Unidade de Medida oficial com base na categorização do produto:
    - Buns -> 'Dúzias'
    - Baguetes -> 'Caixas'
    - No Buns / Tortas -> 'Unidades'
    - No Buns / Cookies -> 'Unidades' (independente do cliente)
    """
    if isinstance(r, dict):
        cat = str(_get_field_val(r, "categoria", "Categoria") or "").strip().lower()
        subcat = str(_get_field_val(r, "sub_categoria", "Sub_Categoria") or "").strip().lower()
    else:
        cat = str(getattr(r, "categoria", "") or "").strip().lower()
        subcat = str(getattr(r, "sub_categoria", "") or "").strip().lower()

    if cat == "no buns":
        if subcat in ("tortas", "cookies"):
            return "Unidades"
    elif "baguet" in cat or "baguet" in subcat:
        return "Caixas"
    elif "bun" in cat or "bun" in subcat:
        return "Dúzias"
    return "Dúzias"


def _processar_dataframe_base(df):
    """
    Sanitiza, tipa e normaliza as colunas da aba 'Base de Landing' / 'Base de Dados'.
    Suporta tanto o modelo oficial novo (Ano e Mês separados) quanto o modelo legado (Data unificada).
    """
    df.columns = [_normalize_col(c) for c in df.columns]

    # Descarte de linhas 'Total' ou rodapés
    if "ANO" in df.columns:
        df = df[df["ANO"].astype(str).str.strip().str.upper() != "TOTAL"].copy()

    # Composição robusta de DATA a partir de ANO e MES se necessário
    col_mes = next((c for c in df.columns if c in ("MES", "MESES") or ("MES" in c and "ANO" not in c)), None)
    if "ANO" in df.columns and col_mes:
        def _montar_data(r):
            try:
                a_val = str(r["ANO"]).split(".")[0].strip()
                m_val = str(r[col_mes]).split(".")[0].strip()
                if a_val.isdigit() and m_val.isdigit():
                    return f"{int(a_val):04d}-{int(m_val):02d}-01"
            except Exception:
                pass
            return None

        data_montada = df.apply(_montar_data, axis=1)
        if "DATA" not in df.columns:
            df["DATA"] = data_montada
        else:
            df["DATA"] = df["DATA"].fillna(data_montada)

    # Descarte de linhas vazias sem Data válida
    if "DATA" in df.columns:
        df["DATA"] = pd.to_datetime(df["DATA"], errors="coerce")
        df = df.dropna(subset=["DATA"]).copy()
        df["ANO"] = df["DATA"].dt.year.dropna().astype(int).astype(str)
        df["MES"] = df["DATA"].dt.month.dropna().astype(int).astype(str)
    elif "ANO" in df.columns and col_mes:
        df["ANO"] = df["ANO"].astype(str).str.split(".").str[0].str.strip()
        df["MES"] = df[col_mes].astype(str).str.split(".").str[0].str.strip()
    else:
        df["ANO"] = "2026"
        df["MES"] = "9"

    # Normalização de Grupo de Clientes / Cliente
    col_grupo = next((c for c in df.columns if "GRUPO" in c), None)
    if col_grupo:
        df["GRUPO_CLIENTE"] = df[col_grupo].fillna("").astype(str).str.strip()
        df["CLIENTE"] = df["GRUPO_CLIENTE"]
    else:
        col_sub = next((c for c in ["SUB_CANAL", "CLIENTE"] if c in df.columns), df.columns[0])
        df["GRUPO_CLIENTE"] = df[col_sub].fillna("").astype(str).str.strip()
        df["CLIENTE"] = df["GRUPO_CLIENTE"]

    # Diretor / Gerente combinado
    df["DIRETOR"] = df.get("DIRETOR", "").fillna("").astype(str).str.strip()
    df["GERENTE"] = df.get("GERENTE", "").fillna("").astype(str).str.strip()
    df["DIRETOR_GERENTE"] = df.apply(
        lambda r: f"{r['DIRETOR']} / {r['GERENTE']}" if r["DIRETOR"] and r["GERENTE"] else (r["DIRETOR"] or r["GERENTE"] or "-"),
        axis=1
    )

    # Limpeza e preenchimento de campos textuais
    for c in ["CANAL", "SUB_CANAL", "SETOR", "CATEGORIA", "SUB_CATEGORIA", "UNIDADE_DE_MEDIDA"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()
    if "UNIDADE_DE_MEDIDA" not in df.columns:
        df["UNIDADE_DE_MEDIDA"] = ""

    def _infer_um_row(r):
        cat = str(r.get("CATEGORIA", "") or "").strip().lower()
        subcat = str(r.get("SUB_CATEGORIA", "") or "").strip().lower()
        # Cookies são sempre Unidades independente do cliente ou canal
        if subcat == "cookies":
            return "Unidades"
        um = str(r.get("UNIDADE_DE_MEDIDA", "") or "").strip()
        if um and um.lower() not in ("none", "nan", "", "-"):
            return um
        if cat == "no buns":
            if subcat in ("tortas", "cookies"):
                return "Unidades"
        elif "baguet" in cat or "baguet" in subcat:
            return "Caixas"
        elif "bun" in cat or "bun" in subcat:
            return "Dúzias"
        return "Dúzias"

    df["UNIDADE_DE_MEDIDA"] = df.apply(_infer_um_row, axis=1)

    # Normalização das colunas de variação (DIF. BGT e DIF. FCST)
    col_dif_bgt = next((c for c in df.columns if "DIF" in c and "BGT" in c), None)
    col_dif_fcst = next((c for c in df.columns if "DIF" in c and "FCST" in c), None)

    landing_num = pd.to_numeric(df.get("LANDING", 0), errors="coerce").fillna(0.0)
    bgt_num = pd.to_numeric(df.get("BGT", 0), errors="coerce").fillna(0.0)
    fcst_num = pd.to_numeric(df.get("FCST", 0), errors="coerce").fillna(0.0)

    if col_dif_bgt:
        num_dif_bgt = pd.to_numeric(df[col_dif_bgt], errors="coerce")
        df["DIF_BGT"] = num_dif_bgt.fillna(landing_num - bgt_num)
    else:
        df["DIF_BGT"] = landing_num - bgt_num

    if col_dif_fcst:
        num_dif_fcst = pd.to_numeric(df[col_dif_fcst], errors="coerce")
        df["DIF_FCST"] = num_dif_fcst.fillna(landing_num - fcst_num)
    else:
        df["DIF_FCST"] = landing_num - fcst_num

    # Conversão numérica segura dos campos de valor
    for col in ["BGT", "FCST", "LANDING", "DIF_BGT", "DIF_FCST"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Coluna unificada de comentários
    col_coment = next((c for c in df.columns if "COMENT" in c or "JUSTIF" in c), None)
    if col_coment:
        df["COMENTARIOS"] = df[col_coment].fillna("-").astype(str).str.strip()
        df["COMENTARIOS"] = df["COMENTARIOS"].replace({"": "-", "nan": "-", "NaN": "-"})
    else:
        df["COMENTARIOS"] = "-"

    # Deduplicação defensiva caso a base tenha registros duplicados (ex: importação anterior com duas unidades)
    subset_cols = [c for c in ["ANO", "MES", "GRUPO_CLIENTE", "CANAL", "SUB_CANAL", "SETOR", "CATEGORIA", "SUB_CATEGORIA", "RECEITA_VOLUME"] if c in df.columns]
    if subset_cols:
        df = df.drop_duplicates(subset=subset_cols, keep="last").copy()

    return df


def _read_excel_safe(source):
    """
    Lê o arquivo Excel suportando com segurança as abas 'Base de Landing', 
    'Base de Dados' ou a primeira aba disponível.
    """
    try:
        xl = pd.ExcelFile(source)
        if "Base de Landing" in xl.sheet_names:
            return xl.parse("Base de Landing")
        elif "Base de Dados" in xl.sheet_names:
            return xl.parse("Base de Dados")
        return xl.parse(xl.sheet_names[0])
    except Exception:
        return pd.read_excel(source)


def obter_dados_base():
    """
    Carrega a base de dados real:
    1. Diretamente do Volume do Unity Catalog via Databricks SDK (automático na nuvem)
    2. Da pasta local do app (src/app/base_landing.xlsx) como fallback
    3. Da pasta fixtures (fixtures/base_landing.xlsx)
    Aplica cache em memória via mtime / last_modified para tempo de resposta em milissegundos.
    """
    global _cached_df, _cached_mtime, _cached_path

    # 1. Tenta carregar diretamente do Volume do Unity Catalog via Databricks SDK
    vol_path = get_volume_path()
    if vol_path:
        try:
            from databricks.sdk import WorkspaceClient
            w = WorkspaceClient()
            meta = w.files.get_metadata(vol_path)
            vol_mtime = str(meta.last_modified or meta.content_length)
            if _cached_df is not None and _cached_path == vol_path and _cached_mtime == vol_mtime:
                return _cached_df.copy()

            logger.info(f"Baixando base de dados atualizada do Unity Catalog Volume: {vol_path}")
            resp = w.files.download(vol_path)
            excel_bytes = io.BytesIO(resp.contents.read())
            df = _read_excel_safe(excel_bytes)

            df = _processar_dataframe_base(df)
            _cached_df = df
            _cached_mtime = vol_mtime
            _cached_path = vol_path
            logger.info(f"Base carregada do Volume com sucesso: {len(df)} registros.")
            return df.copy()
        except Exception as e:
            logger.warning(f"Não foi possível carregar do Volume via SDK ({e}). Usando fallback local...")

    # 2. Fallback para arquivos locais no sistema de arquivos
    caminhos = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "base_landing.xlsx")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "base_landing.xlsx")),
        os.path.abspath("base_landing.xlsx")
    ]

    for caminho in caminhos:
        if caminho and os.path.exists(caminho):
            try:
                mtime = os.path.getmtime(caminho)
                if _cached_df is not None and _cached_path == caminho and _cached_mtime == mtime:
                    return _cached_df.copy()

                logger.info(f"Carregando base de dados a partir de arquivo local: {caminho}")
                df = _read_excel_safe(caminho)

                df = _processar_dataframe_base(df)
                _cached_df = df
                _cached_mtime = mtime
                _cached_path = caminho
                logger.info(f"Base carregada com sucesso do arquivo local: {len(df)} registros.")
                return df.copy()

            except Exception as e:
                logger.error(f"Erro ao processar arquivo {caminho}: {e}")

    logger.warning("Nenhum arquivo de dados encontrado nos caminhos configurados.")
    return pd.DataFrame()


@app.route("/")
def home():
    return redirect("/performance.html")


@app.route("/api/refresh", methods=["GET", "POST"])
def refresh_cache():
    """Força o re-carregamento imediato da base do Volume, limpando o cache em memória."""
    global _cached_df, _cached_mtime, _cached_path
    _cached_df = None
    _cached_mtime = 0
    _cached_path = None
    try:
        df = obter_dados_base()
        logger.info(f"Cache atualizado via /api/refresh: {len(df)} registros.")
        return jsonify({"sucesso": True, "registros": len(df), "mensagem": "Cache atualizado com sucesso."})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


APP_DIR = os.path.dirname(os.path.abspath(__file__))


@app.route("/cadastros")
def cadastros_redirect():
    return redirect("/cadastros.html")


@app.route("/<path:filename>")
def serve_static(filename):
    for base in [APP_DIR, "."]:
        target = os.path.join(base, filename)
        if os.path.exists(target):
            return send_from_directory(base, filename)
    return send_from_directory(APP_DIR, filename)


def aplicar_filtros_df(df, args):
    """
    Aplica filtros dinâmicos recebidos via query params (suportando seleção múltipla)
    sobre o DataFrame.
    """
    if df.empty:
        return df

    df_filtrado = df.copy()
    mapeamento = [
        ("ano", "ANO"),
        ("mes", "MES"),
        ("canal", "CANAL"),
        ("grupo_cliente", "GRUPO_CLIENTE"),
        ("diretor", "DIRETOR"),
        ("gerente", "GERENTE"),
        ("diretor_gerente", "DIRETOR_GERENTE"),
        ("sub_canal", "SUB_CANAL"),
        ("setor", "SETOR"),
        ("categoria", "CATEGORIA"),
        ("sub_categoria", "SUB_CATEGORIA"),
        ("unidade_de_medida", "UNIDADE_DE_MEDIDA")
    ]

    for param_key, col_target in mapeamento:
        vals = args.getlist(param_key)
        all_vals = []
        for v in vals:
            all_vals.extend([x.strip() for x in v.split(",") if x.strip()])
        if not all_vals:
            continue
        if "__NONE__" in all_vals:
            return df_filtrado.iloc[0:0]

        if col_target in df_filtrado.columns:
            mask = df_filtrado[col_target].astype(str).str.strip().isin(all_vals)
            df_filtrado = df_filtrado[mask]

    return df_filtrado


@app.route("/api/filtros")
def get_filtros():
    df = obter_dados_base()
    if df.empty:
        return jsonify({
            "sucesso": True,
            "anos": ["2026", "2025"],
            "meses": [str(m) for m in range(1, 13)],
            "canais": ["QSR", "INDÚSTRIA", "EXPORTAÇÃO"],
            "grupos_clientes": ["Corporativo", "Franquias"],
            "diretores": ["Ronaldo Pernambuco / Thais Gnoatto"],
            "sub_canais": ["Mc Donald's", "Zamp", "Subway", "KFC", "Outback"],
            "setores": ["I", "II", "III"],
            "categorias": ["Buns", "No Buns"],
            "sub_categorias": ["Buns", "Tortas"]
        })

    def get_unicos(col_name):
        if col_name in df.columns:
            vals = df[col_name].dropna().astype(str).unique().tolist()
            return sorted([v.strip() for v in vals if v.strip() and v != "nan" and v != "-" and v.lower() != "todos"])
        return []

    meses_padrao = [str(m) for m in range(1, 13)]
    meses_unicos = get_unicos("MES")
    if meses_unicos:
        meses_set = set(meses_padrao).union(meses_unicos)
        try:
            meses_ordenados = sorted(list(meses_set), key=lambda m: int(m))
        except Exception:
            meses_ordenados = sorted(list(meses_set))
    else:
        meses_ordenados = meses_padrao

    anos_padrao = ["2026", "2025"]
    anos_unicos = get_unicos("ANO")
    if anos_unicos:
        anos_set = set(anos_padrao).union(anos_unicos)
        try:
            anos_ordenados = sorted(list(anos_set), key=lambda a: int(a), reverse=True)
        except Exception:
            anos_ordenados = sorted(list(anos_set), reverse=True)
    else:
        anos_ordenados = anos_padrao

    return jsonify({
        "sucesso": True,
        "anos": anos_ordenados,
        "meses": meses_ordenados,
        "canais": get_unicos("CANAL") or ["QSR"],
        "grupos_clientes": get_unicos("GRUPO_CLIENTE"),
        "diretores": get_unicos("DIRETOR") or ["Ronaldo Pernambuco"],
        "gerentes": get_unicos("GERENTE"),
        "diretores_gerentes": get_unicos("DIRETOR_GERENTE"),
        "sub_canais": get_unicos("SUB_CANAL"),
        "setores": get_unicos("SETOR"),
        "categorias": get_unicos("CATEGORIA"),
        "sub_categorias": get_unicos("SUB_CATEGORIA"),
        "unidades_medida": get_unicos("UNIDADE_DE_MEDIDA")
    })


@app.route("/api/waterfall")
def get_waterfall():
    """
    Retorna os dados estruturados para os dois gráficos de cascata (Waterfall):
    1. BGT x LANDING: Barra inicial BGT -> intermediários DIF. BGT por Sub_Canal -> barra final LANDING
    2. FCST x LANDING: Barra inicial FCST -> intermediários DIF. FCST por Sub_Canal -> barra final LANDING
    """
    metrica = request.args.get("metrica", "RECEITA").upper()
    df_raw = obter_dados_base()

    if df_raw.empty:
        return jsonify({
            "sucesso": True,
            "metrica": metrica,
            "waterfall_bgt": [],
            "waterfall_fcst": [],
            "waterfall": [],
            "totais": {"bgt": 0.0, "fcst": 0.0, "landing": 0.0, "dif_bgt": 0.0, "dif_fcst": 0.0},
            "detalhes": []
        })

    # 1. Filtra pela Métrica Selecionada (Receita ou Volume)
    col_metrica = next((c for c in df_raw.columns if "RECEITA" in c or "VOLUME" in c), None)
    if col_metrica:
        if metrica == "VOLUME":
            df_metric = df_raw[df_raw[col_metrica].astype(str).str.upper().str.contains("VOLUME")].copy()
        else:
            df_metric = df_raw[df_raw[col_metrica].astype(str).str.upper().str.contains("RECEITA")].copy()
    else:
        df_metric = df_raw.copy()

    # 2. Aplica filtros dinâmicos de múltiplos valores
    df = aplicar_filtros_df(df_metric, request.args).copy()

    if df.empty:
        return jsonify({
            "sucesso": True,
            "metrica": metrica,
            "waterfall_bgt": [],
            "waterfall_fcst": [],
            "waterfall": [],
            "totais": {"bgt": 0.0, "fcst": 0.0, "landing": 0.0, "dif_bgt": 0.0, "dif_fcst": 0.0},
            "detalhes": []
        })

    # Colunas analíticas normalizadas
    col_bgt = "BGT"
    col_fcst = "FCST"
    col_landing = "LANDING"
    col_dif_bgt = "DIF_BGT"
    col_dif_fcst = "DIF_FCST"
    col_agrup = "SUB_CANAL" if "SUB_CANAL" in df.columns else df.columns[0]
    col_canal = "CANAL" if "CANAL" in df.columns else col_agrup
    col_cliente = "CLIENTE" if "CLIENTE" in df.columns else col_agrup

    # Agrupa por Sub-Canal para as cascatas da Bridge
    agrupado = df.groupby(col_agrup, as_index=False).agg({
        col_bgt: "sum",
        col_fcst: "sum",
        col_landing: "sum",
        col_dif_bgt: "sum",
        col_dif_fcst: "sum"
    })

    total_bgt = float(df[col_bgt].sum())
    total_fcst = float(df[col_fcst].sum())
    total_landing = float(df[col_landing].sum())

    # 1. Monta Cascata BGT x LANDING
    waterfall_bgt = []
    waterfall_bgt.append({
        "categoria": "Budget (BGT)",
        "inicio": 0,
        "fim": total_bgt,
        "variacao": total_bgt,
        "tipo": "total"
    })
    acum_bgt = total_bgt
    for _, row in agrupado.iterrows():
        delta = float(row[col_dif_bgt])
        inicio = acum_bgt
        fim = acum_bgt + delta
        acum_bgt = fim
        waterfall_bgt.append({
            "categoria": str(row[col_agrup]),
            "inicio": inicio,
            "fim": fim,
            "variacao": delta,
            "tipo": "delta"
        })
    waterfall_bgt.append({
        "categoria": "Landing",
        "inicio": 0,
        "fim": total_landing,
        "variacao": total_landing,
        "tipo": "total"
    })

    # 2. Monta Cascata FCST x LANDING
    waterfall_fcst = []
    waterfall_fcst.append({
        "categoria": "Forecast (FCST)",
        "inicio": 0,
        "fim": total_fcst,
        "variacao": total_fcst,
        "tipo": "total"
    })
    acum_fcst = total_fcst
    for _, row in agrupado.iterrows():
        delta = float(row[col_dif_fcst])
        inicio = acum_fcst
        fim = acum_fcst + delta
        acum_fcst = fim
        waterfall_fcst.append({
            "categoria": str(row[col_agrup]),
            "inicio": inicio,
            "fim": fim,
            "variacao": delta,
            "tipo": "delta"
        })
    waterfall_fcst.append({
        "categoria": "Landing",
        "inicio": 0,
        "fim": total_landing,
        "variacao": total_landing,
        "tipo": "total"
    })

    # Prepara lista detalhada para a tabela de justificativas
    detalhes = []
    for _, row in df.iterrows():
        bgt_val = float(row[col_bgt])
        fcst_val = float(row[col_fcst])
        dif_bgt_val = float(row[col_dif_bgt])
        dif_fcst_val = float(row[col_dif_fcst])

        dif_bgt_pct = (dif_bgt_val / bgt_val * 100) if bgt_val != 0 else 0.0
        dif_fcst_pct = (dif_fcst_val / fcst_val * 100) if fcst_val != 0 else 0.0

        # Formatação de data mes/ano (ex: set/2026)
        meses_nomes = {
            1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
            7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez"
        }
        try:
            m_idx = int(row.get("MES", 9))
            ano_val = str(row.get("ANO", "2026"))
            data_fmt = f"{meses_nomes.get(m_idx, str(m_idx))}/{ano_val}"
        except Exception:
            data_fmt = "set/2026"

        ano_val_clean = str(row.get("ANO", "2026")).split(".")[0].strip()
        mes_val_clean = str(row.get("MES", "9")).split(".")[0].strip()
        rv_val = str(row.get("RECEITA_VOLUME", metrica)).strip()
        um_val = str(row.get("UNIDADE_DE_MEDIDA", "")).strip()
        sub_c_val = str(row.get(col_agrup, "-")).strip()
        grp_c_val = str(row.get("GRUPO_CLIENTE", row.get("CLIENTE", "-"))).strip()
        cat_val = str(row.get("CATEGORIA", "-")).strip()
        sub_cat_val = str(row.get("SUB_CATEGORIA", "-")).strip()
        setor_val = str(row.get("SETOR", "-")).strip()
        gerente_val = str(row.get("GERENTE", "-")).strip()
        diretor_val = str(row.get("DIRETOR", "-")).strip()
        canal_val = str(row.get(col_canal, "-")).strip()
        cod_gr_val = str(row.get("COD_GR_CLIENTE", "")).split(".")[0].strip()

        row_key = f"{ano_val_clean}_{mes_val_clean}_{rv_val}_{sub_c_val}_{grp_c_val}_{cat_val}_{sub_cat_val}_{setor_val}"

        detalhes.append({
            "id": row_key,
            "ano": ano_val_clean,
            "mes": mes_val_clean,
            "receita_volume": rv_val,
            "unidade_de_medida": um_val,
            "data": data_fmt,
            "canal": canal_val,
            "sub_canal": sub_c_val,
            "cliente": str(row.get(col_cliente, grp_c_val)),
            "grupo_cliente": grp_c_val,
            "cod_gr_cliente": cod_gr_val,
            "diretor": diretor_val,
            "gerente": gerente_val,
            "setor": setor_val,
            "categoria": cat_val,
            "sub_categoria": sub_cat_val,
            "bgt": bgt_val,
            "fcst": fcst_val,
            "landing": float(row[col_landing]),
            "dif_bgt": dif_bgt_val,
            "dif_bgt_pct": dif_bgt_pct,
            "dif_fcst": dif_fcst_val,
            "dif_fcst_pct": dif_fcst_pct,
            "comentario": str(row.get("COMENTARIOS", "-"))
        })

    detalhes = sorted(detalhes, key=lambda x: abs(x["dif_bgt"]), reverse=True)

    return jsonify({
        "sucesso": True,
        "metrica": metrica,
        "waterfall_bgt": waterfall_bgt,
        "waterfall_fcst": waterfall_fcst,
        "waterfall": waterfall_bgt,
        "totais": {
            "bgt": total_bgt,
            "fcst": total_fcst,
            "landing": total_landing,
            "dif_bgt": total_landing - total_bgt,
            "dif_fcst": total_landing - total_fcst
        },
        "detalhes": detalhes
    })


@app.route("/api/exportar")
def exportar():
    metrica = request.args.get("metrica", "RECEITA").upper()
    df_raw = obter_dados_base()

    if df_raw.empty:
        return Response("", mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=export_bq_landing.csv"})

    col_metrica = next((c for c in df_raw.columns if "RECEITA" in c or "VOLUME" in c), None)
    if col_metrica:
        if metrica == "VOLUME":
            df_metric = df_raw[df_raw[col_metrica].astype(str).str.upper().str.contains("VOLUME")].copy()
        else:
            df_metric = df_raw[df_raw[col_metrica].astype(str).str.upper().str.contains("RECEITA")].copy()
    else:
        df_metric = df_raw.copy()

    df = aplicar_filtros_df(df_metric, request.args)
    csv = df.to_csv(index=False, sep=";", encoding="utf-8-sig")
    return Response(
        csv,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=export_bq_landing.csv"}
    )


@app.route("/api/performance/salvar_edicoes", methods=["POST"])
def salvar_edicoes_performance():
    """
    Salva alterações feitas diretamente na tabela de comentários/landing da aba Performance.
    Atualiza LANDING e COMENTÁRIOS na base de dados oficial (base_landing.xlsx),
    recalcula DIF. BGT e DIF. FCST, grava backup no Volume e atualiza o arquivo oficial.
    """
    data = request.get_json() or {}
    modificacoes = data.get("modificacoes", [])
    if not modificacoes:
        return jsonify({"success": False, "error": "Nenhuma alteração informada."}), 400

    user_email = _get_current_user_email()
    app_name = (os.environ.get("DATABRICKS_APP_NAME") or "").lower()
    app_url = (os.environ.get("DATABRICKS_APP_URL") or "").lower()
    is_prod = "prod" in app_name or "prod" in app_url

    if is_prod and not _is_user_authorized_for_cadastros(user_email):
        return jsonify({
            "success": False,
            "error": f"Acesso negado: o usuário '{user_email}' não possui permissão para atualizar a base de produção."
        }), 403

    current_rows, err = _read_lookup_rows("base_landing")
    if err or not current_rows:
        return jsonify({"success": False, "error": f"Erro ao acessar base de dados: {err or 'Base vazia'}"}), 500

    # Cria mapa de busca normalizado sobre as linhas da base
    def _make_lookup_key(r):
        ano = _norm_str_key(_get_field_val(r, "ano", "Ano"), is_numeric_key=True)
        mes = _norm_str_key(_get_field_val(r, "mes", "Mês"), is_numeric_key=True)
        rv = _norm_str_key(_get_field_val(r, "receita_volume", "RECEITA | VOLUME"))
        rv_norm = "VOLUME" if "VOLUME" in rv else "RECEITA"
        sub_c = _norm_str_key(_get_field_val(r, "sub_canal", "Sub_Canal"))
        grp_c = _norm_str_key(_get_field_val(r, "grupo_de_clientes", "Grupo de Clientes") or _get_field_val(r, "grupo_cliente", "CLIENTE"))
        cat = _norm_str_key(_get_field_val(r, "categoria", "Categoria"))
        sub_cat = _norm_str_key(_get_field_val(r, "sub_categoria", "Sub_Categoria"))
        setor = _norm_str_key(_get_field_val(r, "setor", "Setor"))
        return (ano, mes, rv_norm, sub_c, grp_c, cat, sub_cat, setor)

    lookup_map = {}
    for idx, r in enumerate(current_rows):
        k = _make_lookup_key(r)
        lookup_map[k] = idx

    updated_count = 0
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    for mod in modificacoes:
        ano = _norm_str_key(mod.get("ano", ""), is_numeric_key=True)
        mes = _norm_str_key(mod.get("mes", ""), is_numeric_key=True)
        rv_raw = _norm_str_key(mod.get("receita_volume", ""))
        rv_norm = "VOLUME" if "VOLUME" in rv_raw else "RECEITA"
        sub_c = _norm_str_key(mod.get("sub_canal", ""))
        grp_c = _norm_str_key(mod.get("grupo_cliente") or mod.get("grupo_de_clientes") or "")
        cat = _norm_str_key(mod.get("categoria", ""))
        sub_cat = _norm_str_key(mod.get("sub_categoria", ""))
        setor = _norm_str_key(mod.get("setor", ""))

        target_k = (ano, mes, rv_norm, sub_c, grp_c, cat, sub_cat, setor)
        row_idx = lookup_map.get(target_k)

        # Se não encontrar com setor exato, tenta chave sem setor
        if row_idx is None:
            for k, idx in lookup_map.items():
                if k[:7] == target_k[:7]:
                    row_idx = idx
                    break

        if row_idx is not None:
            target_row = current_rows[row_idx]

            # Atualiza landing se fornecido
            if "landing" in mod and mod["landing"] is not None:
                try:
                    raw_landing = str(mod["landing"]).strip()
                    clean_landing = re.sub(r"[^\d,.-]", "", raw_landing).strip()
                    if "," in clean_landing and "." in clean_landing:
                        clean_landing = clean_landing.replace(".", "").replace(",", ".")
                    elif "," in clean_landing:
                        clean_landing = clean_landing.replace(",", ".")
                    num_val = float(clean_landing) if clean_landing else 0.0

                    target_row["landing"] = num_val
                    # Recalcula dif_bgt e dif_fcst
                    bgt_val = float(_get_field_val(target_row, "bgt", "BGT") or 0)
                    fcst_val = float(_get_field_val(target_row, "fcst", "FCST") or 0)
                    target_row["dif_bgt"] = num_val - bgt_val
                    target_row["dif_fcst"] = num_val - fcst_val
                except Exception as e:
                    logger.warning(f"Erro ao converter landing: {e}")

            # Atualiza comentário se fornecido
            if "comentario" in mod:
                coment_txt = str(mod["comentario"]).strip()
                target_row["comentarios"] = coment_txt if coment_txt else "-"

            updated_count += 1

    if updated_count == 0:
        return jsonify({
            "success": False,
            "error": "Nenhum registro correspondente foi encontrado para atualizar."
        }), 404

    # Gera o workbook oficial com estilos, fórmulas e metadados
    try:
        excel_bytes = _gerar_workbook_oficial_bytes(current_rows)
    except Exception as e:
        logger.error(f"Erro ao gerar workbook oficial: {e}")
        return jsonify({"success": False, "error": f"Erro ao gerar planilha Excel: {e}"}), 500

    # Grava backups de segurança
    backup_filename = f"base_landing_backup_edicao_{ts}.xlsx"
    _save_excel_to_volume(excel_bytes, backup_filename, is_backup=True)
    _save_excel_to_local(excel_bytes, backup_filename, is_backup=True)

    # Grava arquivo oficial no Volume Unity Catalog e localmente
    vol_ok, vol_err = _save_excel_to_volume(excel_bytes, "base_landing.xlsx", is_backup=False)
    loc_ok = _save_excel_to_local(excel_bytes, "base_landing.xlsx", is_backup=False)

    if not vol_ok and not loc_ok:
        logger.error(f"[PERFORMANCE SAVE] Falha crítica de gravação: {vol_err}")
        return jsonify({
            "success": False,
            "error": f"Falha ao persistir no Volume Unity Catalog: {vol_err or 'Erro desconhecido'}"
        }), 500

    # Limpa cache em memória e recarrega imediatamente
    global _cached_df, _cached_mtime, _cached_path
    _cached_df = None
    _cached_mtime = 0
    _cached_path = None
    try:
        obter_dados_base()
    except Exception as e:
        logger.warning(f"Aviso ao recarregar cache após edição: {e}")

    logger.info(f"[PERFORMANCE EDIT SAVE] user={user_email} | updated={updated_count} | vol_ok={vol_ok}")

    return jsonify({
        "success": True,
        "updated_count": updated_count,
        "mensagem": f"{updated_count} registro(s) salvo(s) com sucesso na Base de Landing!"
    })


# ═══════════════════════════════════════════════════════════════════════════════
# API: GESTÃO DE CADASTROS / BASE LANDING (LOOKUPS)
# ═══════════════════════════════════════════════════════════════════════════════

LOOKUP_CONFIG = {
    "base_landing": {
        "title": "Base de Landing",
        "description": "Base analítica de planejamento, projeção (Landing), Forecast e Budget de BQ",
        "table_name": "base_landing",
        "excel_filename": "base_landing.xlsx",
        "primary_key": "sub_canal",
        "composite_keys": [
            "ano",
            "mes",
            "grupo_de_clientes",
            "cod_gr_cliente",
            "diretor",
            "gerente",
            "canal",
            "sub_canal",
            "setor",
            "categoria",
            "sub_categoria",
            "receita_volume"
        ],
        "columns": [
            {"key": "ano", "label": "Ano", "required": True, "type": "number"},
            {"key": "mes", "label": "Mês", "required": True, "type": "number"},
            {"key": "grupo_de_clientes", "label": "Grupo de Clientes", "required": True, "type": "text"},
            {"key": "cod_gr_cliente", "label": "Cod_GR_Cliente", "required": False, "type": "text"},
            {"key": "diretor", "label": "Diretor", "required": False, "type": "text"},
            {"key": "gerente", "label": "Gerente", "required": False, "type": "text"},
            {"key": "canal", "label": "Canal", "required": False, "type": "text"},
            {"key": "sub_canal", "label": "Sub_Canal", "required": True, "type": "text"},
            {"key": "setor", "label": "Setor", "required": False, "type": "text"},
            {"key": "categoria", "label": "Categoria", "required": False, "type": "text"},
            {"key": "sub_categoria", "label": "Sub_Categoria", "required": False, "type": "text"},
            {"key": "unidade_de_medida", "label": "Unidade de Medida", "required": True, "type": "text"},
            {"key": "receita_volume", "label": "RECEITA | VOLUME", "required": True, "type": "text"},
            {"key": "bgt", "label": "BGT", "required": False, "type": "number"},
            {"key": "fcst", "label": "FCST", "required": False, "type": "number"},
            {"key": "landing", "label": "LANDING", "required": False, "type": "number"},
            {"key": "dif_bgt", "label": "DIF. BGT", "required": False, "type": "number"},
            {"key": "dif_fcst", "label": "DIF. FCST", "required": False, "type": "number"},
            {"key": "realizado", "label": "REALIZADO", "required": False, "type": "text"},
            {"key": "comentarios", "label": "COMENTÁRIOS", "required": False, "type": "text"}
        ]
    }
}

_DEFAULT_CADASTROS_ADMINS = [
    "renan.ferreira@grupobimbo.com",
    "DNA - GB Brasil Leaders"
]

_DEFAULT_CADASTROS_AUTHORIZED = [
    "rafael.lobo@grupobimbo.com",
    "veronica.hirschhorn@grupobimbo.com",
    "sucena.luque@grupobimbo.com"
]


def _get_current_user_email():
    """Extrai o e-mail do usuário autenticado a partir dos cabeçalhos Databricks Apps proxy."""
    email = (
        request.headers.get("X-Forwarded-Preferred-Username")
        or request.headers.get("X-Forwarded-Email")
        or request.headers.get("X-Databricks-User-Email")
    )
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


def _load_cadastros_access():
    """Carrega lista de administradores e usuários autorizados do arquivo cadastros_access.json."""
    admins = [a.lower() for a in _DEFAULT_CADASTROS_ADMINS]
    authorized = [u.lower() for u in _DEFAULT_CADASTROS_AUTHORIZED]

    candidates = [
        os.path.join(os.path.dirname(__file__), "cadastros_access.json"),
        os.path.join("src", "app", "cadastros_access.json"),
        "cadastros_access.json"
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    for a in cfg.get("admins", []):
                        ca = str(a).strip().lower()
                        if ca and ca not in admins:
                            admins.append(ca)
                    for u in cfg.get("authorized_users", []):
                        cu = str(u).strip().lower()
                        if cu and cu not in authorized:
                            authorized.append(cu)
                break
            except Exception as e:
                logger.warning(f"Não foi possível ler {p}: {e}")

    return {"admins": admins, "authorized_users": authorized}


def _is_user_authorized_for_cadastros(email):
    """Verifica se o usuário tem permissão para gerenciar a base landing."""
    if not email:
        return False
    clean_email = str(email).strip().lower()
    if clean_email in ("usuario_portal", "postgres", "admin", "renan.ferreira@grupobimbo.com"):
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


def _read_lookup_rows(table_key):
    """Lê as linhas da base da planilha do Volume ou do fallback local."""
    cfg = LOOKUP_CONFIG.get(table_key)
    if not cfg:
        return [], "Tabela não configurada"

    raw_df = None
    vol_path = get_volume_path()
    if vol_path:
        try:
            from databricks.sdk import WorkspaceClient
            w = WorkspaceClient()
            resp = w.files.download(vol_path)
            raw_df = _read_excel_safe(io.BytesIO(resp.contents.read()))
        except Exception as e:
            logger.warning(f"Não foi possível ler do Volume via SDK ({e}). Tentando fallback local...")

    if raw_df is None or raw_df.empty:
        caminhos = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "base_landing.xlsx")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "base_landing.xlsx")),
            os.path.abspath("base_landing.xlsx")
        ]
        for c in caminhos:
            if c and os.path.exists(c):
                try:
                    raw_df = _read_excel_safe(c)
                    if not raw_df.empty:
                        break
                except Exception as e:
                    logger.warning(f"Falha ao ler {c}: {e}")

    if raw_df is None or raw_df.empty:
        return [], None

    col_mapping = {}
    for col in raw_df.columns:
        norm = _normalize_col(col).lower().replace("_", "")
        for c_def in cfg["columns"]:
            key_norm = _normalize_col(c_def["key"]).lower().replace("_", "")
            label_norm = _normalize_col(c_def["label"]).lower().replace("_", "")
            if norm == key_norm or norm == label_norm:
                col_mapping[col] = c_def["key"]
                break

    rows = []
    for _, r in raw_df.iterrows():
        row_dict = {}
        for orig_col, target_key in col_mapping.items():
            val = r.get(orig_col)
            if pd.isna(val):
                row_dict[target_key] = ""
            elif isinstance(val, (datetime, pd.Timestamp)):
                row_dict[target_key] = val.strftime("%Y-%m-%d")
            else:
                row_dict[target_key] = str(val).strip()

        # Suporte para extrair Ano e Mês se o arquivo continha apenas a coluna Data
        if not row_dict.get("ano") and not row_dict.get("mes"):
            col_data = next((c for c in raw_df.columns if _normalize_col(c) == "DATA"), None)
            if col_data and pd.notna(r.get(col_data)):
                try:
                    dt = pd.to_datetime(r[col_data])
                    row_dict["ano"] = str(dt.year)
                    row_dict["mes"] = str(dt.month)
                except Exception:
                    pass

        # Limpeza de números flutuantes (ex: 2026.0 -> 2026, 1.0 -> 1)
        for k in ("ano", "mes", "cod_gr_cliente"):
            if k in row_dict and row_dict[k]:
                row_dict[k] = row_dict[k].split(".")[0].strip()

        # Ignora linhas de total
        if str(row_dict.get("ano", "")).strip().lower() == "total":
            continue

        for c_def in cfg["columns"]:
            if c_def["key"] not in row_dict:
                row_dict[c_def["key"]] = ""

        # Garante Unidade de Medida preenchida se vazia ou normalizada para Cookies
        subcat_val = str(row_dict.get("sub_categoria", "")).strip().lower()
        if subcat_val == "cookies":
            row_dict["unidade_de_medida"] = "Unidades"
        elif not row_dict.get("unidade_de_medida") or str(row_dict.get("unidade_de_medida")).strip() in ("", "None", "nan", "-"):
            row_dict["unidade_de_medida"] = _infer_unidade_de_medida(row_dict)

        if any(v for k, v in row_dict.items() if k != "cod_gr_cliente"):
            rows.append(row_dict)

    return rows, None


def _get_field_val(row_dict, key, label=None):
    """Obtém o valor de um campo de forma insensível a maiúsculas/minúsculas e aceitando label ou key."""
    if not isinstance(row_dict, dict):
        return ""
    if key in row_dict and row_dict[key] is not None:
        return row_dict[key]
    if label and label in row_dict and row_dict[label] is not None:
        return row_dict[label]
    for k, v in row_dict.items():
        if k.lower() == key.lower() or (label and k.lower() == label.lower()):
            if v is not None:
                return v
    return ""


def _norm_str_key(val, is_numeric_key=False):
    """Normaliza strings de chave composta para comparação sem falso-positivos de formato."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if is_numeric_key:
        try:
            return str(int(float(s)))
        except Exception:
            pass
    return " ".join(s.split()).upper()


def _build_row_composite_key(row_dict, composite_keys, columns_cfg=None):
    """
    Gera o 'endereço' (chave composta normalizada) da linha para comparação inequívoca.
    """
    key_parts = []
    numeric_keys = {"ano", "mes", "cod_gr_cliente"}
    for k in composite_keys:
        label = None
        if columns_cfg:
            col_def = next((c for c in columns_cfg if c["key"] == k), None)
            if col_def:
                label = col_def.get("label")
        val = _get_field_val(row_dict, k, label)
        # Suporte para derivar ano/mês de 'data' se não vierem explícitos
        if k in ("ano", "mes") and not str(val).strip():
            dt_val = _get_field_val(row_dict, "data", "Data")
            if dt_val:
                try:
                    dt = pd.to_datetime(dt_val)
                    val = str(dt.year) if k == "ano" else str(dt.month)
                except Exception:
                    pass
        key_parts.append(_norm_str_key(val, is_numeric_key=(k in numeric_keys)))
    return tuple(key_parts)


# Colunas calculadas automaticamente por fórmula no Excel ou derived metrics
# Não devem disparar "modificação" durante a mesclagem inteligente / upsert
CALCULATED_FORMULA_COLUMNS = {"dif_bgt", "dif_fcst"}


def _normalize_row_value(val, col_type):
    """Normaliza valor de métrica ou texto para verificar se houve alteração real."""
    if val is None or pd.isna(val):
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
    # Em colunas de texto (ex: comentarios, realizado), "-" e nulos são equivalentes a vazio
    if not s or s in ("-", "None", "nan", "NaN"):
        return ""
    if s.endswith(".0") and col_type == "text":
        try:
            return str(int(float(s)))
        except Exception:
            pass
    return s


def _are_rows_identical(row_a, row_b, columns_cfg):
    """
    Retorna True apenas se todos os campos manuais/reais (chaves e métricas) forem idênticos.
    Ignora colunas calculadas por fórmula (DIF. BGT, DIF. FCST).
    """
    for col in columns_cfg:
        k = col["key"]
        if k in CALCULATED_FORMULA_COLUMNS:
            continue
        t = col.get("type", "text")
        v_a = _normalize_row_value(_get_field_val(row_a, k, col.get("label")), t)
        v_b = _normalize_row_value(_get_field_val(row_b, k, col.get("label")), t)
        if v_a != v_b:
            return False
    return True


def _smart_merge_rows(current_rows, imported_rows, composite_keys, columns_cfg, mode="merge"):
    """
    Algoritmo de Mesclagem Inteligente (Upsert) da Base Landing.
    - Se a linha for idêntica: não duplica, mantém a existente intacta.
    - Se a linha for modificada (mesma chave, valores diferentes): atualiza os valores.
    - Se a linha for inexistente na base: adiciona nova linha.
    - Linhas existentes que não vieram no arquivo: preservadas intactas (no modo merge).
    - Se a base atual já possuir linhas duplicadas (bug anterior), consolida automaticamente.
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

    if mode == "replace":
        dedup_map = {}
        for r in imported_rows:
            key = _build_row_composite_key(r, composite_keys, columns_cfg)
            dedup_map[key] = r
        final_rows = list(dedup_map.values())
        stats["novos"] = len(final_rows)
        stats["total_final"] = len(final_rows)
        return final_rows, stats

    # 1. Mapeia a base atual por chave composta eliminando eventuais duplicidades antigas
    existing_map = {}
    existing_order = []
    seen_existing_keys = set()

    for r in current_rows:
        key = _build_row_composite_key(r, composite_keys, columns_cfg)
        if key in seen_existing_keys:
            stats["duplicatas_removidas_base"] += 1
            # Se a linha já mapeada tinha Caixas e a duplicata tem Unidades, prefere Unidades
            um_val = str(_get_field_val(r, "unidade_de_medida", "Unidade de Medida") or "").strip().lower()
            if um_val in ("unidades", "un"):
                existing_map[key] = dict(r)
            continue
        seen_existing_keys.add(key)
        existing_map[key] = dict(r)
        existing_order.append(key)

    matched_keys_in_import = set()
    new_rows = []

    # 2. Processa cada linha importada contra a base
    for imp_r in imported_rows:
        key = _build_row_composite_key(imp_r, composite_keys, columns_cfg)
        if key in existing_map:
            matched_keys_in_import.add(key)
            curr_r = existing_map[key]
            if _are_rows_identical(curr_r, imp_r, columns_cfg):
                stats["inalterados"] += 1
            else:
                stats["atualizados"] += 1
                # Atualiza mantendo campos
                updated = dict(curr_r)
                for col in columns_cfg:
                    k = col["key"]
                    if k in CALCULATED_FORMULA_COLUMNS:
                        continue
                    v = _get_field_val(imp_r, k, col.get("label"))
                    if v != "":
                        updated[k] = v
                    elif k in ("comentarios", "realizado"):
                        updated[k] = "-"
                existing_map[key] = updated
        else:
            if key not in [k for k, _ in new_rows]:
                stats["novos"] += 1
                new_rows.append((key, dict(imp_r)))

    # 3. Conta quantas linhas da base foram preservadas sem sofrer toque
    for k in existing_order:
        if k not in matched_keys_in_import:
            stats["preservados"] += 1

    # 4. Concatena na ordem: existentes preservadas/atualizadas + novas inseridas ao fim
    final_rows = [existing_map[k] for k in existing_order]
    for _, nr in new_rows:
        final_rows.append(nr)

    stats["total_final"] = len(final_rows)
    return final_rows, stats


def _save_excel_to_volume(excel_bytes, filename, is_backup=False):
    """
    Grava o arquivo Excel no Volume do Databricks Unity Catalog.
    Utiliza primariamente o Databricks Files SDK (API oficial do Unity Catalog),
    garantindo que o arquivo seja persistido no storage da nuvem e visível no Catálogo.
    Retorna (sucesso: bool, erro_msg: str | None).
    """
    vol_path = get_volume_path()
    if not vol_path:
        logger.error("VOLUME_PATH não configurado.")
        return False, "VOLUME_PATH não configurado no ambiente."
    vol_dir = os.path.dirname(vol_path).replace("\\", "/")
    rel_path = f"backups/{filename}" if is_backup else filename
    full_vol_path = f"{vol_dir}/{rel_path}"

    last_error = None
    # 1. Upload DIRETO e PRIORITÁRIO via Databricks Files SDK (API oficial do Unity Catalog)
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        stream = io.BytesIO(excel_bytes)
        w.files.upload(full_vol_path, stream, overwrite=True)
        logger.info(f"Excel gravado com sucesso no Volume Unity Catalog via SDK: {full_vol_path} ({len(excel_bytes)} bytes)")
        return True, None
    except Exception as e:
        last_error = str(e)
        logger.error(f"Erro ao gravar no Volume via Databricks SDK ({full_vol_path}): {e}")

    # 2. Fallback apenas se for cluster tradicional onde /Volumes é mount FUSE real
    if os.name != "nt" and os.path.ismount("/Volumes"):
        try:
            os.makedirs(os.path.dirname(full_vol_path), exist_ok=True)
            with open(full_vol_path, "wb") as f:
                f.write(excel_bytes)
            logger.info(f"Excel gravado no Volume via FUSE mount: {full_vol_path} ({len(excel_bytes)} bytes)")
            return True, None
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Fallback FUSE falhou: {e}")

    return False, last_error


def _save_excel_to_local(excel_bytes, filename, is_backup=False):
    """Grava cópia local no disco do Databricks App para contingência imediata."""
    app_dir = os.path.abspath(os.path.dirname(__file__))
    target_dir = os.path.join(app_dir, "backups") if is_backup else app_dir
    os.makedirs(target_dir, exist_ok=True)
    target_file = os.path.join(target_dir, filename)
    try:
        with open(target_file, "wb") as f:
            f.write(excel_bytes)
        logger.info(f"Excel gravado localmente: {target_file} ({len(excel_bytes)} bytes)")
        return True
    except Exception as e:
        logger.warning(f"Falha ao salvar arquivo local {target_file}: {e}")
        return False


# ── ROTAS DE CADASTROS / BASE LANDING ─────────────────────────────────────────

@app.route('/api/auth/me', methods=['GET'])
def api_auth_me():
    """Retorna dados e permissões do usuário logado."""
    email = _get_current_user_email()
    is_auth = _is_user_authorized_for_cadastros(email)
    cfg = _load_cadastros_access()
    admins = [a.lower() for a in cfg.get("admins", [])]
    user_groups = _get_current_user_groups()
    is_admin = (
        str(email).strip().lower() in admins
        or any(g in admins for g in user_groups)
        or email in ("usuario_portal", "postgres", "renan.ferreira@grupobimbo.com")
    )
    return jsonify({
        "authenticated": True,
        "email": email,
        "is_admin": is_admin,
        "can_access_cadastros": is_auth
    })


@app.route('/api/lookups/summary', methods=['GET'])
def lookups_summary():
    """Resumo das tabelas e estatísticas da Base Landing."""
    summary = []
    total_linhas = 0
    linhas_receita = 0
    linhas_volume = 0

    for key, cfg in LOOKUP_CONFIG.items():
        rows, _ = _read_lookup_rows(key)
        total_linhas = len(rows)
        for r in rows:
            rv = str(r.get("receita_volume", "")).upper()
            if "RECEITA" in rv:
                linhas_receita += 1
            elif "VOLUME" in rv:
                linhas_volume += 1

        summary.append({
            "key": key,
            "title": cfg["title"],
            "description": cfg["description"],
            "total": total_linhas,
            "linhas_receita": linhas_receita,
            "linhas_volume": linhas_volume,
            "excel_filename": cfg["excel_filename"],
            "primary_key": cfg["primary_key"],
            "columns_count": len(cfg["columns"])
        })

    return jsonify({
        "success": True,
        "tables": summary,
        "stats": {
            "total": total_linhas,
            "receita": linhas_receita,
            "volume": linhas_volume
        },
        "user": _get_current_user_email()
    })


@app.route('/api/lookups/<table_key>', methods=['GET'])
def lookups_get(table_key):
    """Recupera os registros completos e o esquema da tabela."""
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


OFFICIAL_EXCEL_COLUMNS = [
    {"idx": 1, "header": "Ano", "key": "ano", "label": "Ano", "align": "center", "width": 8.5, "fmt": "General"},
    {"idx": 2, "header": "Mês", "key": "mes", "label": "Mês", "align": "center", "width": 8.5, "fmt": "General"},
    {"idx": 3, "header": "Grupo de Clientes", "key": "grupo_de_clientes", "label": "Grupo de Clientes", "align": "left", "width": 18.0, "fmt": "General"},
    {"idx": 4, "header": "Cod_GR_Cliente", "key": "cod_gr_cliente", "label": "Cod_GR_Cliente", "align": "center", "width": 18.0, "fmt": "General"},
    {"idx": 5, "header": "Diretor", "key": "diretor", "label": "Diretor", "align": "left", "width": 15.0, "fmt": "General"},
    {"idx": 6, "header": "Gerente", "key": "gerente", "label": "Gerente", "align": "left", "width": 12.0, "fmt": "General"},
    {"idx": 7, "header": "Canal", "key": "canal", "label": "Canal", "align": "center", "width": 10.0, "fmt": "General"},
    {"idx": 8, "header": "Sub_Canal", "key": "sub_canal", "label": "Sub_Canal", "align": "left", "width": 13.0, "fmt": "General"},
    {"idx": 9, "header": "Setor", "key": "setor", "label": "Setor", "align": "center", "width": 10.0, "fmt": "General"},
    {"idx": 10, "header": "Categoria", "key": "categoria", "label": "Categoria", "align": "center", "width": 13.0, "fmt": "General"},
    {"idx": 11, "header": "Sub_Categoria", "key": "sub_categoria", "label": "Sub_Categoria", "align": "center", "width": 16.0, "fmt": "General"},
    {"idx": 12, "header": "Unidade de Medida", "key": "unidade_de_medida", "label": "Unidade de Medida", "align": "center", "width": 16.0, "fmt": "General"},
    {"idx": 13, "header": "RECEITA | VOLUME", "key": "receita_volume", "label": "RECEITA | VOLUME", "align": "center", "width": 20.0, "fmt": "General"},
    {"idx": 14, "header": "BGT", "key": "bgt", "label": "BGT", "align": "center", "width": 12.0, "fmt": "#,##0"},
    {"idx": 15, "header": "FCST", "key": "fcst", "label": "FCST", "align": "center", "width": 12.0, "fmt": "#,##0"},
    {"idx": 16, "header": "LANDING", "key": "landing", "label": "LANDING", "align": "center", "width": 13.0, "fmt": "#,##0"},
    {"idx": 17, "header": "DIF. BGT", "key": "dif_bgt", "label": "DIF. BGT", "align": "center", "width": 13.0, "fmt": "#,##0"},
    {"idx": 18, "header": "DIF. FCST", "key": "dif_fcst", "label": "DIF. FCST", "align": "center", "width": 14.0, "fmt": "#,##0"},
    {"idx": 19, "header": "REALIZADO", "key": "realizado", "label": "REALIZADO", "align": "center", "width": 14.0, "fmt": '_-"R$"\\ * #,##0_-;\\-"R$"\\ * #,##0_-;_-"R$"\\ * "-"_-;_-@_-'},
    {"idx": 20, "header": "COMENTÁRIOS", "key": "comentarios", "label": "COMENTÁRIOS", "align": "center", "width": 17.0, "fmt": '_-"R$"\\ * #,##0_-;\\-"R$"\\ * #,##0_-;_-"R$"\\ * "-"_-;_-@_-'}
]

FONT_EXCEL_CELL = Font(name="Aptos Narrow", size=9)
FONT_EXCEL_HEADER = Font(name="Aptos Narrow", size=9, bold=True, color="FFFFFF")
ALIGN_EXCEL_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_EXCEL_LEFT = Alignment(horizontal="left", vertical="center")
FILL_EXCEL_HEADER = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")


def _get_official_template_path():
    """Busca o modelo oficial BQ LANDING.xlsx no app, templates, fixtures ou caminhos padrão."""
    candidates = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "modelo_bq_landing.xlsx")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "templates", "modelo_bq_landing.xlsx")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "base_landing.xlsx")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "modelo_bq_landing.xlsx")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "base_landing.xlsx")),
        os.path.abspath("modelo_bq_landing.xlsx"),
        os.path.abspath("base_landing.xlsx"),
        r"C:\Users\renan.ferreira\Downloads\BQ LANDING.xlsx"
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _gerar_workbook_oficial_bytes(rows_data):
    """
    Gera a planilha oficial idêntica ao modelo BQ LANDING.xlsx:
    - Todas as abas oficiais: 'De_Para', 'Base de Landing', 'Total QSR', 'Total Categoria', 'Resumo'
    - Tabela formatada 'Tabela2' no estilo 'TableStyleLight2' com linhas zebradas e autofiltro
    - 19 colunas com cabeçalhos oficiais padronizados e larguras ajustadas
    - Fórmulas dinâmicas de variação (=O{row}-M{row} para DIF. BGT e =O{row}-N{row} para DIF. FCST)
    - Formatação numérica #,##0 para colunas métricas e monetária para Realizado/Comentários
    - Tipografia Aptos Narrow tamanho 9 e alinhamentos conforme modelo oficial
    """
    total_rows = len(rows_data)
    template_path = _get_official_template_path()

    wb = None
    if template_path and os.path.exists(template_path):
        try:
            wb = openpyxl.load_workbook(template_path)
            ws = wb["Base de Landing"] if "Base de Landing" in wb.sheetnames else wb.active
            prev_max = ws.max_row
            if prev_max > total_rows + 1:
                ws.delete_rows(total_rows + 2, prev_max - (total_rows + 1))
        except Exception as e:
            logger.warning(f"Erro ao carregar template ({e}). Gerando workbook oficial do zero...")
            wb = None

    if wb is None:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Base de Landing"
        for s_name in ["De_Para", "Total QSR", "Total Categoria", "Resumo"]:
            wb.create_sheet(title=s_name)

    # Garante cabeçalhos padronizados na linha 1
    for c_def in OFFICIAL_EXCEL_COLUMNS:
        cell_h = ws.cell(1, c_def["idx"], c_def["header"])
        cell_h.font = FONT_EXCEL_HEADER
        cell_h.alignment = ALIGN_EXCEL_CENTER
        if not template_path:
            cell_h.fill = FILL_EXCEL_HEADER

    def _parse_num_val(v):
        if v is None:
            return 0.0
        s = str(v).strip()
        if not s or s in ("-", "None", "nan", "NaN"):
            return 0.0
        try:
            if "," in s:
                s = s.replace(".", "").replace(",", ".")
            return float(s)
        except Exception:
            return 0.0

    # Preenche linhas de dados com valores, fórmulas e formatações
    for r_idx, r in enumerate(rows_data, start=2):
        ano_raw = _get_field_val(r, "ano", "Ano") or 2026
        try:
            ano_val = int(float(str(ano_raw).split(".")[0].strip()))
        except Exception:
            ano_val = 2026

        mes_raw = _get_field_val(r, "mes", "Mês") or 1
        try:
            mes_val = int(float(str(mes_raw).split(".")[0].strip()))
        except Exception:
            mes_val = 1

        cod_raw = str(_get_field_val(r, "cod_gr_cliente", "Cod_GR_Cliente") or "").split(".")[0].strip()
        try:
            cod_val = int(cod_raw) if cod_raw else ""
        except Exception:
            cod_val = cod_raw

        bgt_val = _parse_num_val(_get_field_val(r, "bgt", "BGT"))
        fcst_val = _parse_num_val(_get_field_val(r, "fcst", "FCST"))
        landing_val = _parse_num_val(_get_field_val(r, "landing", "LANDING"))

        realizado_raw = _get_field_val(r, "realizado", "REALIZADO")
        if realizado_raw is None or str(realizado_raw).strip() in ("", "None", "nan", "NaN"):
            realizado_val = "-"
        else:
            realizado_val = realizado_raw

        coment_raw = _get_field_val(r, "comentarios", "COMENTÁRIOS")
        if coment_raw is None or str(coment_raw).strip() in ("", "None", "nan", "NaN"):
            coment_val = "-"
        else:
            coment_val = str(coment_raw).strip()

        row_map = {
            1: ano_val,
            2: mes_val,
            3: str(_get_field_val(r, "grupo_de_clientes", "Grupo de Clientes") or "").strip(),
            4: cod_val,
            5: str(_get_field_val(r, "diretor", "Diretor") or "").strip(),
            6: str(_get_field_val(r, "gerente", "Gerente") or "").strip(),
            7: str(_get_field_val(r, "canal", "Canal") or "").strip(),
            8: str(_get_field_val(r, "sub_canal", "Sub_Canal") or "").strip(),
            9: str(_get_field_val(r, "setor", "Setor") or "").strip(),
            10: str(_get_field_val(r, "categoria", "Categoria") or "").strip(),
            11: str(_get_field_val(r, "sub_categoria", "Sub_Categoria") or "").strip(),
            12: str(_get_field_val(r, "unidade_de_medida", "Unidade de Medida") or "").strip(),
            13: str(_get_field_val(r, "receita_volume", "RECEITA | VOLUME") or "").strip(),
            14: bgt_val,
            15: fcst_val,
            16: landing_val,
            17: f"=P{r_idx}-N{r_idx}",
            18: f"=P{r_idx}-O{r_idx}",
            19: realizado_val,
            20: coment_val
        }

        for c_def in OFFICIAL_EXCEL_COLUMNS:
            col_i = c_def["idx"]
            cell = ws.cell(r_idx, col_i, row_map[col_i])
            cell.font = FONT_EXCEL_CELL
            cell.alignment = ALIGN_EXCEL_LEFT if c_def["align"] == "left" else ALIGN_EXCEL_CENTER
            if c_def["fmt"] != "General":
                cell.number_format = c_def["fmt"]

    # Ajusta largura de cada coluna
    for c_def in OFFICIAL_EXCEL_COLUMNS:
        col_letter = get_column_letter(c_def["idx"])
        ws.column_dimensions[col_letter].width = c_def["width"]

    # Garante a Tabela oficial 'Tabela2' com estilo TableStyleLight2 e AutoFilter único (ECMA-376)
    # Remove qualquer tabela residual do template para reconstrução perfeita
    for t_name in list(ws.tables.keys()):
        del ws.tables[t_name]

    # Crucial: Em planilhas com Tabela oficial, o AutoFilter pertence exclusivamente à Table.
    # O autoFilter da planilha (ws.auto_filter) deve ser desativado para evitar erro de XML duplicado no Excel.
    ws.auto_filter.ref = None

    table_ref = f"A1:T{total_rows + 1}"
    tab = Table(displayName="Tabela2", ref=table_ref)
    tab.tableStyleInfo = TableStyleInfo(
        name="TableStyleLight2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False
    )
    # Define as 20 colunas com correspondência exata aos cabeçalhos oficiais
    tab.tableColumns = [TableColumn(id=c["idx"], name=c["header"]) for c in OFFICIAL_EXCEL_COLUMNS]
    tab.autoFilter = AutoFilter(ref=table_ref)
    ws.add_table(tab)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@app.route('/api/lookups/<table_key>/preview_merge', methods=['POST'])
def lookups_preview_merge(table_key):
    """
    Simula a mesclagem inteligente e retorna as estatísticas de auditoria
    (inalterados, atualizados, novos, total_final, duplicatas_removidas_base) antes de gravar.
    """
    cfg = LOOKUP_CONFIG.get(table_key)
    if not cfg:
        return jsonify({"success": False, "error": f"Tabela '{table_key}' não encontrada."}), 404

    data = request.get_json() or {}
    raw_rows = data.get("rows", [])
    mode = data.get("mode", "merge")
    if not isinstance(raw_rows, list):
        return jsonify({"success": False, "error": "Formato inválido: 'rows' deve ser uma lista."}), 400

    col_defs = cfg["columns"]
    composite_keys = cfg.get("composite_keys", [c["key"] for c in col_defs])

    # Validação e auto-preenchimento inteligente da Unidade de Medida na importação
    if table_key == "base_landing":
        for r in raw_rows:
            if isinstance(r, dict):
                subcat_val = str(_get_field_val(r, "sub_categoria", "Sub_Categoria") or "").strip().lower()
                if subcat_val == "cookies":
                    r["unidade_de_medida"] = "Unidades"
                else:
                    cur_um = str(_get_field_val(r, "unidade_de_medida", "Unidade de Medida") or "").strip()
                    if not cur_um or cur_um.lower() in ("none", "nan", "-"):
                        r["unidade_de_medida"] = _infer_unidade_de_medida(r)

        has_um = any(bool(str(_get_field_val(r, "unidade_de_medida", "Unidade de Medida") or "").strip()) for r in raw_rows)
        if not has_um and raw_rows:
            return jsonify({
                "success": False,
                "error": "A coluna obrigatória 'Unidade de Medida' não foi encontrada na planilha importada. Por favor, utilize o novo modelo oficial com as 20 colunas."
            }), 400

    current_rows, _ = _read_lookup_rows(table_key)

    _, stats = _smart_merge_rows(current_rows, raw_rows, composite_keys, col_defs, mode=mode)

    return jsonify({
        "success": True,
        "mode": mode,
        "stats": stats
    })


@app.route('/api/lookups/<table_key>', methods=['POST'])
def lookups_save(table_key):
    """Salva a nova versão da planilha aplicando Mesclagem Inteligente (Upsert), grava backup, atualiza no Volume e invalida cache."""
    cfg = LOOKUP_CONFIG.get(table_key)
    if not cfg:
        return jsonify({"success": False, "error": f"Tabela '{table_key}' não encontrada."}), 404

    data = request.get_json() or {}
    raw_rows = data.get("rows", [])
    mode = data.get("mode", "merge")
    if not isinstance(raw_rows, list):
        return jsonify({"success": False, "error": "Formato inválido: 'rows' deve ser uma lista."}), 400

    user_email = _get_current_user_email()
    if not _is_user_authorized_for_cadastros(user_email):
        return jsonify({
            "success": False,
            "error": f"Acesso negado: o usuário '{user_email}' não possui permissão para atualizar cadastros."
        }), 403

    col_defs = cfg["columns"]
    composite_keys = cfg.get("composite_keys", [c["key"] for c in col_defs])

    # Validação e auto-preenchimento inteligente da Unidade de Medida na importação
    if table_key == "base_landing":
        for r in raw_rows:
            if isinstance(r, dict):
                subcat_val = str(_get_field_val(r, "sub_categoria", "Sub_Categoria") or "").strip().lower()
                if subcat_val == "cookies":
                    r["unidade_de_medida"] = "Unidades"
                else:
                    cur_um = str(_get_field_val(r, "unidade_de_medida", "Unidade de Medida") or "").strip()
                    if not cur_um or cur_um.lower() in ("none", "nan", "-"):
                        r["unidade_de_medida"] = _infer_unidade_de_medida(r)

        has_um = any(bool(str(_get_field_val(r, "unidade_de_medida", "Unidade de Medida") or "").strip()) for r in raw_rows)
        if not has_um and raw_rows:
            return jsonify({
                "success": False,
                "error": "A coluna obrigatória 'Unidade de Medida' não foi encontrada na planilha importada. Por favor, utilize o novo modelo oficial com as 20 colunas."
            }), 400

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Lê a base atual do Volume / fallback
    current_rows, _ = _read_lookup_rows(table_key)

    # Executa a Mesclagem Inteligente (Upsert)
    merged_rows, stats = _smart_merge_rows(current_rows, raw_rows, composite_keys, col_defs, mode=mode)

    data_for_df = []
    for r in merged_rows:
        if not isinstance(r, dict):
            continue
        item = {}
        for c in col_defs:
            val = _get_field_val(r, c["key"], c.get("label"))
            if val is None or val == "None" or val == "nan" or val == "NaN":
                val = ""

            if c["type"] == "number" and str(val).strip() != "":
                try:
                    num_str = str(val).replace(".", "").replace(",", ".") if "," in str(val) else str(val)
                    item[c["label"]] = float(num_str)
                except Exception:
                    item[c["label"]] = str(val).strip()
            elif c["type"] == "date" and str(val).strip() != "":
                try:
                    dt = pd.to_datetime(val)
                    item[c["label"]] = dt.strftime("%Y-%m-%d")
                except Exception:
                    item[c["label"]] = str(val).strip()
            else:
                item[c["label"]] = str(val).strip()

        if any(v for k, v in item.items() if k != "Cód. GR Cliente"):
            data_for_df.append(item)

    if not data_for_df and raw_rows:
        return jsonify({"success": False, "error": "Nenhum registro com dados válidos encontrado para salvar."}), 400

    df_to_save = pd.DataFrame(data_for_df)

    try:
        if "LANDING" in df_to_save.columns and "BGT" in df_to_save.columns:
            df_to_save["DIF. BGT"] = pd.to_numeric(df_to_save["LANDING"], errors="coerce").fillna(0) - pd.to_numeric(df_to_save["BGT"], errors="coerce").fillna(0)
        if "LANDING" in df_to_save.columns and "FCST" in df_to_save.columns:
            df_to_save["DIF. FCST"] = pd.to_numeric(df_to_save["LANDING"], errors="coerce").fillna(0) - pd.to_numeric(df_to_save["FCST"], errors="coerce").fillna(0)
    except Exception as e:
        logger.warning(f"Aviso ao recalcular diferenças: {e}")

    excel_bytes = _gerar_workbook_oficial_bytes(data_for_df)
    backup_filename = f"base_landing_backup_{ts}.xlsx"
    _save_excel_to_volume(excel_bytes, backup_filename, is_backup=True)
    _save_excel_to_local(excel_bytes, backup_filename, is_backup=True)

    vol_ok, vol_err = _save_excel_to_volume(excel_bytes, cfg["excel_filename"], is_backup=False)
    loc_ok = _save_excel_to_local(excel_bytes, cfg["excel_filename"], is_backup=False)

    if not vol_ok:
        logger.error(f"[CADASTRO SAVE] Falha crítica ao persistir no Volume Unity Catalog: {cfg['excel_filename']} | {vol_err}")
        return jsonify({
            "success": False,
            "error": f"Falha ao gravar arquivo no Volume do Databricks Unity Catalog: {vol_err or 'Verifique as permissões de acesso ao Volume.'}"
        }), 500

    global _cached_df, _cached_mtime, _cached_path
    _cached_df = None
    _cached_mtime = 0
    _cached_path = None
    try:
        obter_dados_base()
    except Exception as e:
        logger.warning(f"Aviso ao recarregar cache: {e}")

    logger.info(
        f"[CADASTRO SAVE] table={table_key} | user={user_email} | mode={mode} | "
        f"final={len(data_for_df)} | inalterados={stats['inalterados']} | "
        f"atualizados={stats['atualizados']} | novos={stats['novos']} | "
        f"duplicatas_removidas={stats['duplicatas_removidas_base']}"
    )

    return jsonify({
        "success": True,
        "message": f"{len(data_for_df)} registros salvos com sucesso na planilha base do Databricks!",
        "count": len(data_for_df),
        "stats": stats,
        "mode": mode,
        "volume_updated": vol_ok,
        "local_updated": loc_ok,
        "backup": backup_filename,
        "timestamp": ts,
        "user": user_email
    })


@app.route('/api/lookups/<table_key>/export', methods=['GET'])
def lookups_export_csv(table_key):
    """Exporta os dados atuais como arquivo CSV com separador ponto-e-vírgula e UTF-8 BOM."""
    cfg = LOOKUP_CONFIG.get(table_key)
    if not cfg:
        return jsonify({"success": False, "error": "Tabela não encontrada."}), 404

    rows, _ = _read_lookup_rows(table_key)
    col_defs = cfg["columns"]

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    writer.writerow([c["label"] for c in col_defs])

    for r in rows:
        writer.writerow([r.get(c["key"], "") for c in col_defs])

    csv_bytes = output.getvalue().encode('utf-8-sig')
    filename = f"base_landing_atual_{datetime.now().strftime('%Y%m%d')}.csv"

    return Response(
        csv_bytes,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route('/api/lookups/<table_key>/export_excel', methods=['GET'])
def lookups_export_excel(table_key):
    """Exporta a planilha oficial com o modelo BQ LANDING.xlsx completo (todas as abas)."""
    cfg = LOOKUP_CONFIG.get(table_key)
    if not cfg:
        return jsonify({"success": False, "error": "Tabela não encontrada."}), 404

    rows, _ = _read_lookup_rows(table_key)
    excel_bytes = _gerar_workbook_oficial_bytes(rows)
    filename = f"BQ_LANDING_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return Response(
        excel_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route('/api/lookups/<table_key>/template', methods=['GET'])
def lookups_template_excel(table_key):
    """Gera ou fornece o modelo oficial BQ LANDING.xlsx com todas as abas."""
    cfg = LOOKUP_CONFIG.get(table_key)
    if not cfg:
        return jsonify({"success": False, "error": "Tabela não encontrada."}), 404

    template_path = _get_official_template_path()
    if template_path and os.path.exists(template_path):
        with open(template_path, "rb") as f:
            excel_bytes = f.read()
    else:
        rows, _ = _read_lookup_rows(table_key)
        excel_bytes = _gerar_workbook_oficial_bytes(rows[:10] if rows else [])

    filename = "modelo_exemplo_BQ_LANDING.xlsx"
    return Response(
        excel_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == "__main__":
    from waitress import serve
    logger.info(f"🚀 Iniciando servidor BQ Landing na porta {PORT}...")
    serve(app, host="0.0.0.0", port=PORT)
