"""
Motor de Resumo Executivo Cascateado (Semanal & Mensal) com IA via Databricks Foundation Models.
Gera síntese em 3 níveis (Macro -> Meso -> Micro Acionável) estritamente ancorada em fatos SQL,
com cache em memória por período e fallback determinístico em caso de indisponibilidade do LLM.
"""

import json
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

try:
    from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
    _HAS_SERVING_TYPES = True
except Exception:
    _HAS_SERVING_TYPES = False


_BRIEF_CACHE = {}
_BRIEF_LOCK = threading.Lock()
_BRIEF_TTL_SECONDS = 1800
_LLM_MODELS = ('databricks-claude-sonnet-4-6', 'databricks-claude-haiku-4-5')


_MESES_PT = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']


def _fmt_brl_compact(val):
    v = float(val or 0)
    sign = '-' if v < 0 else ''
    av = abs(v)
    if av >= 1_000_000:
        return f"{sign}R$ {av / 1_000_000:.1f} mi".replace('.', ',')
    if av >= 1_000:
        return f"{sign}R$ {av / 1_000:.1f} mil".replace('.', ',')
    return f"{sign}R$ {av:,.0f}".replace(',', '.')


def _fmt_pct(val, signed=False):
    if val is None:
        return 'N/D'
    v = float(val)
    prefix = '+' if (signed and v > 0) else ('-' if v < 0 else '')
    return f"{prefix}{abs(v):.1f}%".replace('.', ',')


def _fmt_pp(val):
    if val is None:
        return ''
    v = float(val)
    prefix = '+' if v >= 0 else '-'
    return f"{prefix}{abs(v):.1f} p.p.".replace('.', ',')


def _fmt_br_date(iso):
    if not iso or len(str(iso)) < 10:
        return '--'
    p = str(iso)[:10].split('-')
    return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 else str(iso)


def _fetch_weekly_and_mix_facts(execute_sql, catalog, schema, ano, mes, ref_dt, py_cutoff_dt, categoria='', modo='mensal'):
    """Busca comparativo semanal quando solicitado. Em modo mensal, retorna vazio instantaneamente."""
    if modo != 'semanal':
        return {
            'semana_cur': '',
            'semana_prv': '',
            'weekly_rows': [],
            'mix_rows': [],
            'open_orders': {},
        }

    cat_cond = ""
    base_params = {'ano_cur': ano, 'mes_cur': mes, 'ref_max': ref_dt.isoformat()}
    if categoria:
        cat_cond = " AND UPPER(COALESCE(f.CATEGORIA_PROD_BQ, f.GRUPO_PRODUTO_DESC_BQ, '')) = UPPER(:cat)"
        base_params['cat'] = categoria

    w_cur_end = ref_dt
    w_cur_ini = w_cur_end - timedelta(days=6)
    w_prv_end = w_cur_ini - timedelta(days=1)
    w_prv_ini = w_prv_end - timedelta(days=6)

    params = {
        'cur_ini': w_cur_ini.isoformat(),
        'cur_end': w_cur_end.isoformat(),
        'prv_ini': w_prv_ini.isoformat(),
        'prv_end': w_prv_end.isoformat(),
        'ano_cur': ano,
        'mes_cur': mes,
        'ano_py': ano - 1,
        'py_cut': py_cutoff_dt,
    }
    if categoria:
        params['cat'] = categoria

    q_weekly = f"""
        SELECT
            CAST(f.ID_DISTRIBUIDOR AS INT) AS dist_id,
            MAX(COALESCE(NULLIF(TRIM(f.DESC_DISTRIBUIDOR_DNA), ''), f.DESC_DISTRIBUIDOR)) AS nome,
            SUM(CASE WHEN f.DATA_SELL_OUT BETWEEN CAST(:cur_ini AS DATE) AND CAST(:cur_end AS DATE)
                     THEN COALESCE(f.VL_SELL_OUT, 0) ELSE 0 END) AS sem_cur_vl,
            SUM(CASE WHEN f.DATA_SELL_OUT BETWEEN CAST(:prv_ini AS DATE) AND CAST(:prv_end AS DATE)
                     THEN COALESCE(f.VL_SELL_OUT, 0) ELSE 0 END) AS sem_prv_vl,
            SUM(CASE WHEN f.DATA_SELL_OUT BETWEEN CAST(:cur_ini AS DATE) AND CAST(:cur_end AS DATE)
                     THEN COALESCE(f.QTDE_DUZIA_SELL_OUT, 0) ELSE 0 END) AS sem_cur_dz,
            SUM(CASE WHEN f.DATA_SELL_OUT BETWEEN CAST(:prv_ini AS DATE) AND CAST(:prv_end AS DATE)
                     THEN COALESCE(f.QTDE_DUZIA_SELL_OUT, 0) ELSE 0 END) AS sem_prv_dz
        FROM {catalog}.{schema}.tbl_factdy_sellout f
        WHERE f.DATA_SELL_OUT BETWEEN CAST(:prv_ini AS DATE) AND CAST(:cur_end AS DATE)
          AND (f.SKU_PROD_BQ NOT IN ('META','META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)
          {cat_cond}
        GROUP BY CAST(f.ID_DISTRIBUIDOR AS INT)
    """

    w_rows = execute_sql(q_weekly, params) or []

    return {
        'semana_cur': f"{_fmt_br_date(w_cur_ini.isoformat())[:5]} a {_fmt_br_date(w_cur_end.isoformat())[:5]}",
        'semana_prv': f"{_fmt_br_date(w_prv_ini.isoformat())[:5]} a {_fmt_br_date(w_prv_end.isoformat())[:5]}",
        'weekly_rows': w_rows,
        'mix_rows': [],
        'open_orders': {},
    }


def _fetch_dist_sku_detratores(execute_sql, catalog, schema, ano, mes, py_cutoff_dt, dist_ids):
    """Busca os SKUs detratores (maiores perdas em R$ vs ano anterior ou faturamento histórico) para os DTs do Pareto."""
    if not dist_ids:
        return {}

    dist_ids_str = ', '.join(str(int(x)) for x in dist_ids if str(x).isdigit())
    if not dist_ids_str:
        return {}

    q = f"""
        SELECT
            CAST(f.ID_DISTRIBUIDOR AS INT) AS dist_id,
            f.SKU_PROD_BQ AS sku,
            MAX(COALESCE(NULLIF(TRIM(f.DESC_PROD_BQ), ''), f.SKU_PROD_BQ)) AS nome,
            SUM(CASE WHEN YEAR(f.DATA_SELL_OUT) = :ano_cur THEN COALESCE(f.VL_SELL_OUT, 0) ELSE 0 END) AS vl_cur,
            SUM(CASE WHEN YEAR(f.DATA_SELL_OUT) = :ano_py THEN COALESCE(f.VL_SELL_OUT, 0) ELSE 0 END) AS vl_py
        FROM {catalog}.{schema}.tbl_factdy_sellout f
        WHERE (
            (YEAR(f.DATA_SELL_OUT) = :ano_cur AND MONTH(f.DATA_SELL_OUT) = :mes_cur)
            OR
            (YEAR(f.DATA_SELL_OUT) = :ano_py AND MONTH(f.DATA_SELL_OUT) = :mes_cur AND f.DATA_SELL_OUT <= CAST(:py_cut AS DATE))
        )
          AND CAST(f.ID_DISTRIBUIDOR AS INT) IN ({dist_ids_str})
          AND (f.SKU_PROD_BQ NOT IN ('META', 'META_POSITIVACAO') OR f.SKU_PROD_BQ IS NULL)
        GROUP BY CAST(f.ID_DISTRIBUIDOR AS INT), f.SKU_PROD_BQ
    """
    params = {
        'ano_cur': ano,
        'mes_cur': mes,
        'ano_py': ano - 1,
        'py_cut': py_cutoff_dt,
    }
    try:
        rows = execute_sql(q, params) or []
    except Exception:
        return {}

    by_dist = defaultdict(list)
    for r in rows:
        did = int(r['dist_id'])
        vc = float(r.get('vl_cur') or 0)
        vp = float(r.get('vl_py') or 0)
        diff = vc - vp
        pct = ((vc - vp) / vp * 100) if vp > 0 else (None if vc == 0 else 100.0)
        by_dist[did].append({
            'sku': str(r.get('sku') or '').strip(),
            'nome': str(r.get('nome') or '').strip(),
            'vl_cur': vc,
            'vl_py': vp,
            'delta': diff,
            'pct': pct,
        })

    result = {}
    for did in dist_ids:
        items = by_dist.get(did, [])
        # Detratores prioritários: SKUs com maior queda em R$ vs período anterior
        losers = sorted([x for x in items if x['delta'] < 0], key=lambda x: x['delta'])[:5]
        if not losers:
            py_sold = sorted([x for x in items if x['vl_py'] > 0 and x['vl_cur'] == 0], key=lambda x: x['vl_py'], reverse=True)[:5]
            if py_sold:
                losers = py_sold
            else:
                losers = sorted(items, key=lambda x: x['vl_cur'], reverse=True)[:5]

        result[did] = [
            {
                'sku': x['sku'],
                'nome': x['nome'],
                'realizado': _fmt_brl_compact(x['vl_cur']),
                'referencia': _fmt_brl_compact(x['vl_py']),
                'queda': _fmt_brl_compact(abs(x['delta'])),
                'delta_num': round(x['delta'], 2),
                'pct': _fmt_pct(x['pct'], signed=True) if x['pct'] is not None else ('Zerado' if x['vl_cur'] == 0 and x['vl_py'] > 0 else 'N/D'),
            }
            for x in losers
        ]
    return result


def _assemble_fact_packet(exec_payload, extra, modo):
    """Monta pacote compacto de fatos verificados (Macro, Meso, Micro) para o LLM e fallback."""
    c = exec_payload.get('consolidado') or {}
    py_meta = exec_payload.get('py_meta') or {}
    dists = exec_payload.get('distribuidores') or []
    ano = exec_payload.get('ano')
    mes = exec_payload.get('mes')

    so_real = float(c.get('so_real_vl') or 0)
    so_proj = float(c.get('so_proj_vl') or 0)
    so_meta = float(c.get('so_meta_vl') or 0)
    gap_meta = so_proj - so_meta
    att_pct = c.get('ating_proj_pct')
    yoy_pct = c.get('yoy_pct')
    preco_dz = c.get('preco_medio_dz')
    mix_brioche = c.get('mix_brioche_pct')
    si_real = float(c.get('si_real_vl') or 0)
    si_fcst = float(c.get('si_fcst_vl') or 0)
    carteira = float(c.get('carteira_vl') or 0)
    sem_envio = int(c.get('sem_envio_recente') or 0)

    # Semanal WoW agregado e destaques
    w_rows = extra.get('weekly_rows') or []
    w_cur_tot = sum(float(r.get('sem_cur_vl') or 0) for r in w_rows)
    w_prv_tot = sum(float(r.get('sem_prv_vl') or 0) for r in w_rows)
    wow_pct = round(((w_cur_tot - w_prv_tot) / w_prv_tot) * 100, 1) if w_prv_tot > 0 else None

    w_by_id = {}
    for r in w_rows:
        if r.get('dist_id') is None:
            continue
        did = int(r['dist_id'])
        cv = float(r.get('sem_cur_vl') or 0)
        pv = float(r.get('sem_prv_vl') or 0)
        w_by_id[did] = {
            'dist_id': did,
            'nome': str(r.get('nome') or f'ID {did}').strip(),
            'sem_cur_vl': cv,
            'sem_prv_vl': pv,
            'delta_vl': cv - pv,
            'wow_pct': round(((cv - pv) / pv) * 100, 1) if pv > 0 else None,
        }

    wow_gainers = sorted(
        [w for w in w_by_id.values() if w['delta_vl'] > 0 and w['sem_cur_vl'] >= 20000],
        key=lambda x: x['delta_vl'],
        reverse=True
    )[:5]
    wow_losers = sorted(
        [w for w in w_by_id.values() if w['delta_vl'] < 0],
        key=lambda x: x['delta_vl']
    )[:5]

    # Mix canal
    m_rows = extra.get('mix_rows') or []
    m_tot_cur = sum(float(r.get('vl_cur') or 0) for r in m_rows)
    m_tot_py = sum(float(r.get('vl_py') or 0) for r in m_rows)
    m_dz_py = sum(float(r.get('dz_py') or 0) for r in m_rows)
    preco_py_dz = round(m_tot_py / m_dz_py, 2) if m_dz_py > 0 else None
    mix_summary = []
    for r in sorted(m_rows, key=lambda x: float(x.get('vl_cur') or 0), reverse=True):
        vc = float(r.get('vl_cur') or 0)
        vp = float(r.get('vl_py') or 0)
        sh_c = (vc / m_tot_cur * 100) if m_tot_cur > 0 else 0.0
        sh_p = (vp / m_tot_py * 100) if m_tot_py > 0 else None
        mix_summary.append({
            'segmento': r.get('segmento'),
            'share_pct': round(sh_c, 1),
            'pp_vs_py': round(sh_c - sh_p, 1) if sh_p is not None else None,
            'valor': _fmt_brl_compact(vc),
        })

    # Rankings Meso & Pareto do Gap
    active_dists = [d for d in dists if float(d.get('so_meta_vl') or 0) > 0 or float(d.get('so_real_vl') or 0) > 0]
    for d in active_dists:
        d['_gap'] = float(d.get('so_proj_vl') or 0) - float(d.get('so_meta_vl') or 0)

    all_deficits = sorted([d for d in active_dists if d['_gap'] < 0], key=lambda x: x['_gap'])
    total_neg_gap = sum(abs(d['_gap']) for d in all_deficits)

    # Pareto: distribuidores que concentram até 75% do déficit total (máx 5)
    pareto_dts = []
    cum_gap = 0.0
    for d in all_deficits:
        pareto_dts.append(d)
        cum_gap += abs(d['_gap'])
        if len(pareto_dts) >= 5 or (total_neg_gap > 0 and (cum_gap / total_neg_gap) >= 0.72):
            break

    pareto_share_pct = round((cum_gap / total_neg_gap) * 100, 0) if total_neg_gap > 0 else 0
    pareto_qtd = len(pareto_dts)

    cur_bdays = int(py_meta.get('cur_bdays', 0) or 0)
    total_bdays = int(py_meta.get('total_bdays', 0) or 0)
    is_closed = (cur_bdays >= total_bdays and total_bdays > 0)
    mes_nome = _MESES_PT[mes] if (mes and 1 <= mes <= 12) else str(mes)
    base_yoy_label = f"{mes_nome}/{ano - 1}"

    deficits_data = []
    for d in pareto_dts:
        real_v = float(d.get('so_real_vl') or 0)
        meta_v = float(d.get('so_meta_vl') or 0)
        gap_v = float(d['_gap'] or 0)
        is_zero = real_v <= 0
        deficits_data.append({
            'dist_id': int(d['dist_id']),
            'nome': d['nome'],
            'faturamento_realizado': _fmt_brl_compact(real_v),
            'meta_mes': _fmt_brl_compact(meta_v),
            'gap_projetado': _fmt_brl_compact(abs(gap_v)),
            'gap_num': round(abs(gap_v), 2),
            'ating_pct': _fmt_pct(d.get('ating_proj_pct')),
            'faturamento_zerado': is_zero,
            'status_gap': f"{d['nome']} com meta de {_fmt_brl_compact(meta_v)} e faturamento zerado" if is_zero else f"{d['nome']} com déficit de {_fmt_brl_compact(abs(gap_v))}",
        })

    # Crescimento YoY mensal por distribuidor (com baseline explícito)
    gainers_yoy = sorted(
        [d for d in active_dists if (float(d.get('so_real_vl') or 0) - float(d.get('so_py_vl') or 0)) > 0 and float(d.get('so_real_vl') or 0) >= 30000],
        key=lambda x: (float(x.get('so_real_vl') or 0) - float(x.get('so_py_vl') or 0)),
        reverse=True
    )[:5]
    altas_mes_data = []
    for d in gainers_yoy:
        cur_v = float(d.get('so_real_vl') or 0)
        py_v = float(d.get('so_py_vl') or 0)
        diff_v = cur_v - py_v
        altas_mes_data.append({
            'dist_id': int(d['dist_id']),
            'nome': d['nome'],
            'realizado': _fmt_brl_compact(cur_v),
            'crescimento_vl': _fmt_brl_compact(diff_v),
            'crescimento_pct': _fmt_pct(d.get('yoy_pct'), signed=True),
            'base_comparacao': f"vs {base_yoy_label}",
        })

    # Maiores Quedas / Detratores YoY mensal por distribuidor
    losers_yoy = sorted(
        [d for d in dists if (float(d.get('so_real_vl') or 0) - float(d.get('so_py_vl') or 0)) < 0 and float(d.get('so_py_vl') or 0) > 0],
        key=lambda x: (float(x.get('so_real_vl') or 0) - float(x.get('so_py_vl') or 0)),
    )[:5]
    quedas_mes_data = []
    for d in losers_yoy:
        cur_v = float(d.get('so_real_vl') or 0)
        py_v = float(d.get('so_py_vl') or 0)
        diff_v = abs(cur_v - py_v)
        quedas_mes_data.append({
            'dist_id': int(d['dist_id']),
            'nome': d['nome'],
            'realizado': _fmt_brl_compact(cur_v),
            'zerado': cur_v <= 0,
            'queda_vl': _fmt_brl_compact(diff_v),
            'queda_pct': _fmt_pct(d.get('yoy_pct'), signed=True),
        })

    star_candidates = sorted(
        [d for d in active_dists if (d.get('ating_proj_pct') or 0) >= 80 and float(d.get('so_real_vl') or 0) >= 30000],
        key=lambda x: (float(x.get('ating_proj_pct') or 0) * 0.5 + float(x.get('yoy_pct') or 0)),
        reverse=True
    )[:3]

    late_dists = sorted(
        [d for d in dists if d.get('so_real_vl', 0) <= 0 or (d.get('atraso_envio_dias') is not None and d['atraso_envio_dias'] > 3)],
        key=lambda x: float(x.get('so_meta_vl') or 0),
        reverse=True
    )[:4]

    valid_dist_map = {str(d['nome']).strip().upper(): int(d['dist_id']) for d in dists if d.get('dist_id') and d.get('nome')}
    id_to_name = {int(d['dist_id']): str(d['nome']).strip() for d in dists if d.get('dist_id') and d.get('nome')}

    facts = {
        'modo': modo,
        'ano': ano,
        'mes': mes,
        'mes_nome': mes_nome,
        'is_mes_fechado': is_closed,
        'base_comparacao_anual': base_yoy_label,
        'dias_uteis': "" if is_closed else f"{cur_bdays} de {total_bdays} dias úteis",
        'janela_semanal': f"{extra.get('semana_cur')} vs {extra.get('semana_prv')}",
        'macro': {
            'total_distribuidores_ativos': len(dists),
            'sellout_realizado': _fmt_brl_compact(so_real),
            'sellout_projecao_mes': _fmt_brl_compact(so_proj),
            'sellout_meta_mes': _fmt_brl_compact(so_meta),
            'atingimento_projetado_pct': _fmt_pct(att_pct),
            'diferenca_projetada_meta': _fmt_brl_compact(gap_meta),
            'falta_meta': _fmt_brl_compact(abs(gap_meta)),
            'crescimento_yoy': _fmt_pct(yoy_pct, signed=True),
            'sellin_faturado': _fmt_brl_compact(si_real),
            'sellin_forecast_erp': _fmt_brl_compact(si_fcst),
            'carteira_aberta': _fmt_brl_compact(carteira),
            'preco_medio_dz': f"R$ {preco_dz:.2f}/DZ".replace('.', ',') if preco_dz else 'N/D',
            'preco_medio_ano_ant_dz': f"R$ {preco_py_dz:.2f}/DZ".replace('.', ',') if preco_py_dz else 'N/D',
            'mix_brioche_pct': _fmt_pct(mix_brioche),
            'dts_sem_envio_3d': sem_envio,
            'semanal_sellout_atual': _fmt_brl_compact(w_cur_tot),
            'semanal_sellout_anterior': _fmt_brl_compact(w_prv_tot),
            'semanal_variacao_wow': _fmt_pct(wow_pct, signed=True),
        },
        'mix_segmentos': mix_summary,
        'destaques_mes': [{'dist_id': int(d['dist_id']), 'nome': d['nome'], 'ating_pct': _fmt_pct(d.get('ating_proj_pct')), 'yoy': _fmt_pct(d.get('yoy_pct'), signed=True), 'sellout': _fmt_brl_compact(d.get('so_real_vl'))} for d in star_candidates],
        'maiores_gaps_meta': {
            'total_neg_gap': _fmt_brl_compact(total_neg_gap),
            'pareto_qtd': pareto_qtd,
            'pareto_share_pct': int(pareto_share_pct),
            'pareto_valor': _fmt_brl_compact(cum_gap),
            'dts': deficits_data,
        },
        'maiores_altas_mes': altas_mes_data,
        'maiores_quedas_mes': quedas_mes_data,
        'semana_alta': [{'dist_id': w['dist_id'], 'nome': w['nome'], 'realizado': _fmt_brl_compact(w['sem_cur_vl']), 'delta': _fmt_brl_compact(w['delta_vl']), 'wow': _fmt_pct(w['wow_pct'], signed=True)} for w in wow_gainers],
        'semana_queda': [{'dist_id': w['dist_id'], 'nome': w['nome'], 'realizado': _fmt_brl_compact(w['sem_cur_vl']), 'delta': _fmt_brl_compact(abs(w['delta_vl'])), 'wow': _fmt_pct(w['wow_pct'], signed=True)} for w in wow_losers],
        'sem_envio_recente_top': [{'dist_id': int(d['dist_id']), 'nome': d['nome'], 'atraso_dias': d.get('atraso_envio_dias'), 'meta': _fmt_brl_compact(d.get('so_meta_vl'))} for d in late_dists],
    }
    return facts, valid_dist_map, id_to_name, {
        'att_pct': att_pct, 'yoy_pct': yoy_pct, 'wow_pct': wow_pct, 'sem_envio': sem_envio,
        'gap_meta': gap_meta, 'top3_gap_share': int(pareto_share_pct), 'preco_dz': preco_dz, 'preco_py_dz': preco_py_dz,
    }


def _build_deterministic_brief(facts, raw_nums):
    """Gera o mesmo formato cascateado de forma determinística caso o endpoint LLM falhe."""
    m = facts['macro']
    is_sem = facts['modo'] == 'semanal'
    is_closed = facts.get('is_mes_fechado')
    mes_nome = facts.get('mes_nome') or ''
    ano = facts.get('ano') or ''
    base_yoy = facts.get('base_comparacao_anual') or 'ano anterior'
    att = raw_nums.get('att_pct')
    yoy = raw_nums.get('yoy_pct')
    wow = raw_nums.get('wow_pct')
    sem_envio = raw_nums.get('sem_envio') or 0

    if is_sem:
        manchete = (
            f"Sell-out da semana somou {m['semanal_sellout_atual']} ({m['semanal_variacao_wow']} vs semana anterior), "
            f"com projeção mensal em {m['atingimento_projetado_pct']} da meta."
        )
        macro = (
            f"Na semana {facts['janela_semanal']}, o faturamento somou {m['semanal_sellout_atual']} contra {m['semanal_sellout_anterior']} na anterior "
            f"({m['semanal_variacao_wow']}). No mês, Sell-out soma {m['sellout_realizado']} e Sell-in + carteira totaliza {m['sellin_faturado']} + {m['carteira_aberta']}."
        )
    elif not is_closed:
        manchete = (
            f"Sell-out de {m['sellout_realizado']} até hoje, ritmo de fechar {mes_nome} em {m['atingimento_projetado_pct']} da meta. "
            f"Previsão de {m['sellout_projecao_mes']} para {m['sellout_meta_mes']} de meta."
        )
        macro = (
            f"Com {facts['dias_uteis']}, o sell-out dos distribuidores soma {m['sellout_realizado']} "
            f"({m['crescimento_yoy']} vs {base_yoy}), com preço médio de {m['preco_medio_dz']} e {m['mix_brioche_pct']} em Brioche & Gourmet. "
            f"Em Sell-in, há {m['sellin_faturado']} faturado e {m['carteira_aberta']} em carteira aberta."
        )
    else:
        top_def = (facts['maiores_gaps_meta']['dts'] or [{}])[0]
        top_def_lead = f" ({top_def['nome']} com meta de {top_def['meta_mes']} e faturamento zerado)" if (top_def and top_def.get('faturamento_zerado')) else ""
        manchete = (
            f"{mes_nome} fechou em {m['atingimento_projetado_pct']} da meta. "
            f"Faltam {m['falta_meta']}{top_def_lead}."
        )
        macro = (
            f"No consolidado de {mes_nome}/{ano}, o sell-out dos distribuidores somou {m['sellout_realizado']} "
            f"({m['crescimento_yoy']} vs {base_yoy}), com preço médio de {m['preco_medio_dz']} e {m['mix_brioche_pct']} em Brioche & Gourmet. "
            f"Em Sell-in, há {m['sellin_faturado']} faturado e {m['carteira_aberta']} em carteira aberta."
        )

    movimentos = []
    # 1. Pareto do Gap da Meta
    pg = facts.get('maiores_gaps_meta') or {}
    if pg.get('dts'):
        top_items = ', '.join(d['status_gap'] for d in pg['dts'])
        movimentos.append({
            'nivel': 'Concentração do Gap',
            'texto': f"Pareto do déficit: {pg.get('pareto_qtd', len(pg['dts']))} distribuidores concentram {pg.get('pareto_share_pct', 0)}% do gap total ({pg.get('pareto_valor')} de {pg.get('total_neg_gap')}): {top_items}.",
            'tom': 'bad' if (att or 0) < 90 else 'warn',
        })

    # 2. Tração de Vendas
    if is_sem and (facts['semana_alta'] or facts['semana_queda']):
        altas = ', '.join(f"{x['nome']} ({x['delta']}, {x['wow']} vs semana ant.)" for x in facts['semana_alta'][:2])
        movimentos.append({
            'nivel': 'Tração Semanal',
            'texto': f"Maiores altas na semana ({facts['janela_semanal']}): {altas}.",
            'tom': 'good' if (wow or 0) >= 0 else 'warn',
        })
    elif not is_sem and facts.get('maiores_altas_mes'):
        altas = ', '.join(f"{x['nome']} cresceu {x['crescimento_vl']} ({x['crescimento_pct']} vs {base_yoy})" for x in facts['maiores_altas_mes'][:2])
        movimentos.append({
            'nivel': 'Tração de Vendas',
            'texto': f"Maiores crescimentos vs {base_yoy}: {altas}.",
            'tom': 'good',
        })

    # 3. Mix & Portfólio (Substitui Estoque Crítico para foco executivo comercial)
    brioche = next((s for s in facts['mix_segmentos'] if 'Brioche' in str(s.get('segmento'))), None)
    trad = next((s for s in facts['mix_segmentos'] if 'Tradicional' in str(s.get('segmento'))), None)
    if brioche:
        pp_txt = _fmt_pp(brioche.get('pp_vs_py')) if brioche.get('pp_vs_py') is not None else ''
        trad_txt = f"; Hambúrguer Tradicional representa {trad['share_pct']}% ({trad['valor']})" if trad else ""
        movimentos.append({
            'nivel': 'Mix & Portfólio',
            'texto': f"Brioche & Gourmet sustenta {brioche['share_pct']}% da receita ({m['preco_medio_dz']}"
                     + (f", ganho de {pp_txt} vs ano ant." if pp_txt else "") + f"){trad_txt}.",
            'tom': 'good' if (brioche.get('pp_vs_py') or 0) >= 0 else 'neutral',
        })

    acoes = []
    # Ação 1: Regularizar envios (sem apontar para um DT único)
    if sem_envio > 0:
        acoes.append({
            'titulo': f"{sem_envio} DTs sem envio >3d",
            'detalhe': "",
            'dist_id': None,
            'dist_nome': None,
            'filtro': 'late',
        })

    # Ação 2: Plano de recuperação do maior déficit
    if pg.get('dts'):
        d0 = pg['dts'][0]
        acoes.append({
            'titulo': f"{d0['nome']} — {('meta ' + d0['meta_mes'] + ' zerada') if d0.get('faturamento_zerado') else ('déficit de ' + d0['gap_projetado'])}",
            'detalhe': "",
            'dist_id': d0['dist_id'],
            'dist_nome': d0['nome'],
            'filtro': None,
        })

    # Ação 3: Destaque positivo / Benchmarking
    if facts['destaques_mes']:
        s0 = facts['destaques_mes'][0]
        acoes.append({
            'titulo': f"Destaque: {s0['nome']} ({s0['ating_pct']} meta · {s0['yoy']} YoY)",
            'detalhe': "",
            'dist_id': s0['dist_id'],
            'dist_nome': s0['nome'],
            'filtro': None,
        })

    return {
        'manchete': manchete,
        'macro': macro,
        'movimentos': movimentos[:3],
        'acoes': acoes[:3],
        'fonte': 'deterministico',
    }


def _call_databricks_llm(get_ws_client, facts, valid_dist_map, id_to_name):
    """Consulta Databricks Foundation Model Serving devolvendo JSON estruturado validado."""
    if not _HAS_SERVING_TYPES or not get_ws_client:
        return None
    client = get_ws_client()
    if not client:
        return None

    modo_lbl = 'BOLETIM SEMANAL (últimos 7 dias vs 7 dias anteriores + ritmo do mês)' if facts['modo'] == 'semanal' else 'RESUMO MENSAL (fechamento projetado, meta oficial, ano anterior e carteira)'

    sys_prompt = (
        "Você é o analista sênior de inteligência de vendas da Bimbo QSR Brasil preparando o briefing direto para o Diretor Comercial.\n"
        "O Diretor tem 30 segundos. Ele odeia enrolação, odeia papo corporativo vazio e quer ver apenas o que mexe no ponteiro.\n\n"
        "REGRAS DE OURO DE LINGUAGEM:\n"
        "1. NENHUM EMOJI. Zero símbolos decorativos, zero exclamações.\n"
        "2. NUNCA use clichês de IA ou jargão oco como: 'vale ressaltar', 'cenário desafiador', 'em constante evolução', 'alavancar', 'sinergia', 'ecossistema', 'crucial', 'jornada', 'ademais', 'outrossim', 'em suma', 'otimizar processos', 'movimento real existe'.\n"
        "3. Escreva como um executivo experiente: frases diretas, voz ativa, números reais. Exemplo: 'Sell-out de R$ 7,3 mi até hoje, ritmo de fechar Novembro em 51,3% da meta (previsão de R$ 14,1 mi para meta de R$ 24,4 mi)'.\n"
        "4. MÊS EM ANDAMENTO: Quando o mês não estiver fechado (is_mes_fechado=false), NUNCA diga 'fecha em X%' como se fosse fato consumado. Diga sempre 'ritmo de fechar [Mês] em X% da meta (previsão de R$ Y para R$ Z de meta)'.\n"
        "5. Formate valores monetários como R$ X,X mi ou R$ X mil. Nunca use 'M' ou 'K'. Nunca coloque sinal negativo após 'Faltam' ou 'déficit' (escreva 'Faltam R$ 10,3 mi', nunca 'Faltam -R$ 10,3 mi').\n"
        "6. CLAREZA CONTRA A META: NUNCA diga 'X zerada em R$ Y'. Se o distribuidor não vendeu nada, escreva: 'X com faturamento zerado contra meta de R$ Y' ou 'X com meta de R$ Y zerada'.\n"
        "7. COMPARATIVO ANUAL: NUNCA use a expressão 'em dias úteis' no texto corrido. Diga apenas 'YoY' ou 'vs [mês]/[ano anterior]' (ex: '+31,4% YoY vs Outubro/2025').\n"
        "8. ESCOPO TEMPORAL MENSAL: Quando o modo for RESUMO MENSAL, NUNCA mencione movimentações 'na semana'. Todos os crescimentos citados DEVEM ter a base temporal explícita informada no JSON (ex: 'vs Novembro/2025').\n"
        "9. PARETO DO GAP: No movimento de gap, apresente a visão Pareto informada no JSON: 'Pareto do déficit: X distribuidores concentram Y% do gap total (R$ A de R$ B): [Lista de DTs]'.\n"
        "10. MOVIMENTOS EXECUTIVOS PERMITIDOS: NUNCA use 'Estoque Crítico'. Os 3 movimentos devem ser OBRIGATORIAMENTE: 1) Pareto do Gap (ou Concentração do Gap), 2) Tração de Vendas (maiores crescimentos vs ano anterior), 3) Mix & Portfólio (share e preço médio de Brioche & Gourmet vs Tradicional).\n"
        "11. VOCABULÁRIO: NUNCA use o termo genérico 'canal'. Escreva 'distribuidores', 'operações' ou 'sell-out consolidado'.\n"
        "12. AÇÕES EXECUTIVAS: Na ação de atraso de envios de sell-out, nunca aponte para um único distribuidor ('dist_id' DEVE ser null e 'filtro' DEVE ser 'late'). Na ação de destaque positivo, o título DEVE ser 'Destaque de Tração: [Nome do DT]' explicando que é a operação referência do mês.\n"
        "13. Responda APENAS um JSON válido sem markdown ou blocos de código adicionais, neste schema exato:\n"
        '{"manchete":"frase direta de até 140 caracteres com o placar contra a meta","macro":"2 frases objetivas com realizado, projeção e carteira","movimentos":[{"nivel":"2 ou 3 palavras (ex: Pareto do Gap, Tração de Vendas, Mix & Portfólio)","texto":"1 frase com distribuidor e valor exato","tom":"good|warn|bad|neutral"}],"acoes":[{"titulo":"ordem executiva curta","detalhe":"motivo numérico direto","dist_id":null,"dist_nome":null,"filtro":"late|below|null"}]}'
    )
    user_prompt = f"Modo: {modo_lbl}\nDados verificados dos distribuidores Bimbo QSR:\n{json.dumps(facts, ensure_ascii=False)}"
    _strip_id = lambda s: re.sub(r'\s*\([^)]*dist_id[^)]*\)', '', str(s or ''), flags=re.IGNORECASE).strip()

    for model_name in _LLM_MODELS:
        try:
            resp = client.serving_endpoints.query(
                name=model_name,
                messages=[
                    ChatMessage(role=ChatMessageRole.SYSTEM, content=sys_prompt),
                    ChatMessage(role=ChatMessageRole.USER, content=user_prompt),
                ],
                temperature=0.15,
                max_tokens=950,
            )
            raw = resp.choices[0].message.content.strip() if resp and resp.choices else ''
            if not raw:
                continue
            m_json = re.search(r'\{[\s\S]*\}', raw)
            parsed = json.loads(m_json.group(0) if m_json else raw)
            if not isinstance(parsed, dict) or not parsed.get('manchete') or not parsed.get('macro'):
                continue

            # Sanitização estrita de IDs e enumerações
            movs = []
            for mv in (parsed.get('movimentos') or [])[:3]:
                if not isinstance(mv, dict) or not mv.get('texto'):
                    continue
                tom = str(mv.get('tom') or 'neutral').lower()
                if tom not in ('good', 'warn', 'bad', 'neutral'):
                    tom = 'neutral'
                movs.append({
                    'nivel': str(mv.get('nivel') or 'Destaque')[:40],
                    'texto': _strip_id(mv.get('texto'))[:320],
                    'tom': tom,
                })

            acts = []
            for ac in (parsed.get('acoes') or [])[:3]:
                if not isinstance(ac, dict) or not ac.get('titulo'):
                    continue
                did = ac.get('dist_id')
                dnm = str(ac.get('dist_nome') or '').strip()
                clean_id = None
                clean_nm = None
                if did is not None:
                    try:
                        di = int(did)
                        if di in id_to_name:
                            clean_id = di
                            clean_nm = id_to_name[di]
                    except (TypeError, ValueError):
                        pass
                if not clean_id and dnm and dnm.upper() in valid_dist_map:
                    clean_id = valid_dist_map[dnm.upper()]
                    clean_nm = id_to_name.get(clean_id, dnm)
                flt = ac.get('filtro')
                if flt not in ('late', 'below'):
                    flt = None
                acts.append({
                    'titulo': _strip_id(ac.get('titulo'))[:110],
                    'detalhe': _strip_id(ac.get('detalhe') or '')[:240],
                    'dist_id': clean_id,
                    'dist_nome': clean_nm,
                    'filtro': flt,
                })

            return {
                'manchete': _strip_id(parsed['manchete'])[:220],
                'macro': _strip_id(parsed['macro'])[:520],
                'movimentos': movs,
                'acoes': acts,
                'fonte': 'databricks-ai',
                'modelo': model_name,
            }
        except Exception:
            continue
    return None


def build_executivo_brief(execute_sql, get_ws_client, catalog, schema, exec_payload, ref_dt, py_cutoff_dt, modo='mensal', categoria='', force=False, use_llm=False):
    """Retorna o Resumo Executivo cascateado (Semanal ou Mensal) com cache TTL de 30 min.
    Ultra-rápido: cálculo determinístico em memória (<50ms). LLM apenas quando explicitamente solicitado."""
    modo_norm = 'semanal' if str(modo).lower().strip() == 'semanal' else 'mensal'
    ano = exec_payload.get('ano')
    mes = exec_payload.get('mes')
    cache_key = f"{ano}_{mes}_{modo_norm}_{categoria}_{ref_dt.isoformat()}_{use_llm}"

    if not force:
        with _BRIEF_LOCK:
            hit = _BRIEF_CACHE.get(cache_key)
            if hit and (time.time() - hit['ts'] < _BRIEF_TTL_SECONDS):
                return hit['data']

    extra = _fetch_weekly_and_mix_facts(execute_sql, catalog, schema, ano, mes, ref_dt, py_cutoff_dt, categoria, modo=modo_norm)
    facts, valid_dist_map, id_to_name, raw_nums = _assemble_fact_packet(exec_payload, extra, modo_norm)

    ai_res = None
    if use_llm:
        ai_res = _call_databricks_llm(get_ws_client, facts, valid_dist_map, id_to_name)
    if not ai_res:
        ai_res = _build_deterministic_brief(facts, raw_nums)

    pg = facts.get('maiores_gaps_meta') or {}
    pareto_list = pg.get('dts') or []
    pareto_dist_ids = [d['dist_id'] for d in pareto_list if d.get('dist_id')]
    sku_detratores_map = _fetch_dist_sku_detratores(execute_sql, catalog, schema, ano, mes, py_cutoff_dt, pareto_dist_ids)

    causa_raiz_map = {}
    for d in pareto_list:
        did = int(d['dist_id'])
        is_zero = bool(d.get('faturamento_zerado'))
        skus = sku_detratores_map.get(did, [])
        causa_raiz_map[str(did)] = {
            'dist_id': did,
            'nome': d['nome'],
            'realizado': d['faturamento_realizado'],
            'meta': d['meta_mes'],
            'gap': d['gap_projetado'],
            'zerado': is_zero,
            'skus': skus,
            'diagnostico': (
                f"Faturamento zerado no mês atual · ausência de transmissão de sell-out (>3 dias sem envio)."
                if is_zero
                else (
                    f"Faturamento de {d['faturamento_realizado']} abaixo do ritmo da meta de {d['meta_mes']}."
                )
            ),
        }

    visual = {
        'causa_raiz': causa_raiz_map,
        'pareto_dist_ids': pareto_dist_ids,
        'sellout': {
            'realizado': facts['macro']['sellout_realizado'],
            'yoy': facts['macro']['crescimento_yoy'],
            'base_yoy': facts['base_comparacao_anual'],
            'ating_pct': facts['macro']['atingimento_projetado_pct'],
            'projecao': facts['macro']['sellout_projecao_mes'],
            'meta': facts['macro']['sellout_meta_mes'],
            'is_closed': bool(facts.get('is_mes_fechado')),
            'mes_nome': facts.get('mes_nome'),
            'sem_atual': facts['macro'].get('semanal_sellout_atual'),
            'sem_ant': facts['macro'].get('semanal_sellout_anterior'),
            'wow': facts['macro'].get('semanal_variacao_wow'),
        },
        'sellin': {
            'faturado': facts['macro']['sellin_faturado'],
            'carteira': facts['macro']['carteira_aberta'],
            'forecast': facts['macro']['sellin_forecast_erp'],
        },
        'preco_mix': {
            'preco_dz': facts['macro']['preco_medio_dz'],
            'brioche_pct': facts['macro']['mix_brioche_pct'],
        },
        'pareto': {
            'qtd': pg.get('pareto_qtd', 0),
            'share_pct': pg.get('pareto_share_pct', 0),
            'pareto_valor': pg.get('pareto_valor'),
            'total_gap': pg.get('total_neg_gap'),
            'dts': [
                {
                    'dist_id': d['dist_id'],
                    'nome': d['nome'],
                    'realizado': d['faturamento_realizado'],
                    'meta': d['meta_mes'],
                    'gap': d['gap_projetado'],
                    'gap_num': d.get('gap_num', 0),
                    'zerado': bool(d.get('faturamento_zerado')),
                }
                for d in (pg.get('dts') or [])
            ],
        },
        'tracao': {
            'label': f"vs {facts['base_comparacao_anual']}" if modo_norm == 'mensal' else (facts.get('janela_semanal') or 'vs sem. ant.'),
            'dts': (
                [
                    {
                        'dist_id': x['dist_id'],
                        'nome': x['nome'],
                        'realizado': x['realizado'],
                        'delta': f"+{x['crescimento_vl']}",
                        'pct': x['crescimento_pct'],
                    }
                    for x in (facts.get('maiores_altas_mes') or [])[:5]
                ]
                if modo_norm == 'mensal'
                else [
                    {
                        'dist_id': w['dist_id'],
                        'nome': w['nome'],
                        'realizado': w.get('realizado'),
                        'delta': f"+{w['delta']}",
                        'pct': w['wow'],
                    }
                    for w in (facts.get('semana_alta') or [])[:5]
                ]
            ),
        },
        'detratores': {
            'label': f"vs {facts['base_comparacao_anual']}" if modo_norm == 'mensal' else (facts.get('janela_semanal') or 'vs sem. ant.'),
            'dts': (
                [
                    {
                        'dist_id': x['dist_id'],
                        'nome': x['nome'],
                        'realizado': x['realizado'],
                        'zerado': bool(x.get('zerado')),
                        'delta': f"-{x['queda_vl']}",
                        'pct': x['queda_pct'],
                    }
                    for x in (facts.get('maiores_quedas_mes') or [])[:5]
                ]
                if modo_norm == 'mensal'
                else [
                    {
                        'dist_id': w['dist_id'],
                        'nome': w['nome'],
                        'realizado': w.get('realizado'),
                        'zerado': False,
                        'delta': f"-{w['delta']}",
                        'pct': w['wow'],
                    }
                    for w in (facts.get('semana_queda') or [])[:5]
                ]
            ),
        },
        'mix': {
            'preco_dz': facts['macro']['preco_medio_dz'],
            'segmentos': [
                {
                    'nome': s['segmento'],
                    'share_pct': s['share_pct'],
                    'pp_vs_py': s.get('pp_vs_py'),
                    'valor': s['valor'],
                }
                for s in (facts.get('mix_segmentos') or [])[:2]
            ],
        },
    }

    result = {
        'ano': ano,
        'mes': mes,
        'modo': modo_norm,
        'janela_label': (
            f"Semana {extra.get('semana_cur', '')} vs {extra.get('semana_prv', '')}"
            if modo_norm == 'semanal' and extra.get('semana_cur')
            else ""
        ),
        'manchete': ai_res['manchete'],
        'macro': ai_res['macro'],
        'movimentos': ai_res['movimentos'],
        'acoes': ai_res['acoes'],
        'visual': visual,
        'fonte': ai_res.get('fonte', 'databricks-ai'),
        'modelo': ai_res.get('modelo'),
    }

    with _BRIEF_LOCK:
        _BRIEF_CACHE[cache_key] = {'ts': time.time(), 'data': result}

    return result
