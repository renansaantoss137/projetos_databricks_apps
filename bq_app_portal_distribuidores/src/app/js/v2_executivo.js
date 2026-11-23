/* ==========================================================================
   Portal Distribuidores v2 — Visão Executiva (Apenas Admin)
   Consolidado 30.000 pés de todo o canal com ranking por distribuidor
   e 1 clique para abrir a operação detalhada.
   ========================================================================== */
(function () {
  'use strict';

  var state = {
    payload: null,
    loading: false,
    lastQuery: null,
    abortCtrl: null,
    reqSeq: 0,
    isVolume: false,
    filter: 'all', // 'all' | 'below' | 'late'
    search: '',
    sortKey: 'so_real',
    sortDir: -1,
    aiMode: 'mensal',
    aiCache: {},
    aiReqSeq: 0,
    aiAbort: null,
    aiCollapsed: false
  };

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function fmtVal(v, compact) {
    var n = Number(v) || 0;
    if (!window.Fmt) return String(Math.round(n));
    if (state.isVolume) return (compact ? Fmt.compact(n) : Fmt.int(n)) + ' DZ';
    return compact ? Fmt.moneyCompact(n) : Fmt.money(n);
  }

  function fmtBrDate(iso) {
    if (!iso || String(iso).length < 10) return '—';
    var p = String(iso).slice(0, 10).split('-');
    return p.length === 3 ? (p[2] + '/' + p[1] + '/' + p[0]) : iso;
  }

  function buildQuery() {
    var qp = new URLSearchParams();
    var anoVals = typeof window.getSafeSelectedValues === 'function' ? window.getSafeSelectedValues('select-ano') : [];
    var mesVals = typeof window.getSafeSelectedValues === 'function' ? window.getSafeSelectedValues('select-mes') : [];
    var catVals = typeof window.getSafeSelectedValues === 'function' ? window.getSafeSelectedValues('select-categoria') : [];
    if (anoVals && anoVals.length) qp.append('ano', anoVals[0]);
    if (mesVals && mesVals.length) qp.append('mes', mesVals[0]);
    if (catVals && catVals.length) qp.append('categoria', catVals.join(','));
    return qp.toString();
  }

  function syncUnitButtons() {
    var bVal = $('#ex-unit-valor');
    var bVol = $('#ex-unit-volume');
    if (!bVal || !bVol) return;
    bVal.classList.toggle('active-label', !state.isVolume);
    bVol.classList.toggle('active-label', state.isVolume);
    bVal.setAttribute('aria-checked', String(!state.isVolume));
    bVol.setAttribute('aria-checked', String(state.isVolume));
    bVal.tabIndex = state.isVolume ? -1 : 0;
    bVol.tabIndex = state.isVolume ? 0 : -1;
  }

  async function fetchExecutivo(force) {
    if (!document.body.classList.contains('is-admin') || document.body.classList.contains('is-simulating')) return;
    var q = buildQuery();
    fetchAiBrief(force, q);
    if (!force && state.payload && state.lastQuery === q) {
      renderAll();
      return;
    }
    if (state.abortCtrl) {
      try { state.abortCtrl.abort(); } catch (_) {}
    }
    var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    state.abortCtrl = ctrl;
    state.lastQuery = q;
    state.loading = true;
    var seq = ++state.reqSeq;

    try {
      var opts = { credentials: 'include' };
      if (ctrl) opts.signal = ctrl.signal;
      var res = await fetch('/api/executivo' + (q ? '?' + q : ''), opts);
      if (seq !== state.reqSeq) return;
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var data = await res.json();
      if (seq !== state.reqSeq) return;
      state.payload = data;
      state.loading = false;
      renderAll();
    } catch (err) {
      if (err && err.name === 'AbortError') return;
      state.loading = false;
      console.warn('[V2Executivo] Erro ao carregar /api/executivo:', err);
      var tbody = $('#ex-tbody');
      var empty = $('#ex-empty');
      var emptyMsg = $('#ex-empty-msg');
      var retryBtn = $('#ex-retry-btn');
      if (tbody) tbody.innerHTML = '';
      if (empty) empty.hidden = false;
      if (emptyMsg) emptyMsg.textContent = 'Não foi possível carregar a visão executiva do canal.';
      if (retryBtn) retryBtn.hidden = false;
    }
  }

  function renderAll() {
    syncUnitButtons();
    if (!state.payload || !state.payload.consolidado) return;
    var c = state.payload.consolidado;
    var pyMeta = state.payload.py_meta || {};
    var mName = (window.Fmt && Fmt.MONTHS_LONG && Fmt.MONTHS_LONG[(state.payload.mes || 1) - 1]) || '';

    var pBadge = $('#ex-period-badge');
    if (pBadge) pBadge.textContent = 'Consolidado Distribuidores · ' + (mName ? mName + ' ' + state.payload.ano : state.payload.ano) + ' (' + (c.total_dists || 0) + ' DTs)';

    var yoyBadge = $('#ex-yoy-badge');
    if (yoyBadge) {
      var isClosed = !pyMeta.rem_bdays || pyMeta.rem_bdays <= 0 || (pyMeta.cur_bdays >= pyMeta.total_bdays && pyMeta.total_bdays > 0);
      if (isClosed) {
        yoyBadge.textContent = 'YoY vs ' + (mName ? mName + '/' : '') + (state.payload.ano - 1);
      } else {
        yoyBadge.textContent = 'YoY até ' + fmtBrDate(pyMeta.py_cutoff_dt);
      }
    }

    var lateBadge = $('#ex-late-badge');
    if (lateBadge) {
      if (c.sem_envio_recente > 0) {
        lateBadge.hidden = false;
        lateBadge.textContent = c.sem_envio_recente + ' DT(s) sem envio >3d';
      } else {
        lateBadge.hidden = true;
      }
    }

    // Card 1: Sell-out do canal
    var c1Val = $('#ex-c1-val');
    var c1Badge = $('#ex-c1-badge');
    var c1Foot = $('#ex-c1-foot');
    var soReal = state.isVolume ? c.so_real_dz : c.so_real_vl;
    if (c1Val) c1Val.textContent = fmtVal(soReal, true);
    if (c1Badge) {
      if (c.yoy_pct !== null && c.yoy_pct !== undefined) {
        var up = c.yoy_pct >= 0;
        c1Badge.className = up ? 'badge-up' : 'badge-down';
        c1Badge.innerHTML = V2.icon(up ? 'arrow-up' : 'arrow-down', 11) + Fmt.esc((up ? '+' : '−') + Fmt.pct(Math.abs(c.yoy_pct), 1) + ' YoY');
        c1Badge.setAttribute('tabindex', '0');
        c1Badge.setAttribute('data-tip', V2.tipHtml('YoY ajustado por dias úteis', [
          ['Realizado atual (R$)', Fmt.money(c.so_real_vl)],
          ['Ano anterior (' + (pyMeta.cur_bdays || 0) + ' DU até ' + fmtBrDate(pyMeta.py_cutoff_dt) + ')', Fmt.money(c.so_py_vl)],
          ['Variação', (up ? '+' : '−') + Fmt.pct(Math.abs(c.yoy_pct), 1), up ? 'att-good' : 'att-bad']
        ]));
      } else {
        c1Badge.className = 'badge-neutral';
        c1Badge.textContent = 'Sem base YoY';
      }
    }
    if (c1Foot) {
      c1Foot.textContent = c.so_py_vl > 0
        ? ('Mesmo corte ano anterior: ' + Fmt.moneyCompact(c.so_py_vl))
        : (c.total_dists + ' distribuidores com movimentação');
    }

    // Card 2: Projeção fechamento
    var c2Val = $('#ex-c2-val');
    var c2Badge = $('#ex-c2-badge');
    var c2Foot = $('#ex-c2-foot');
    var soProj = state.isVolume ? c.so_proj_dz : c.so_proj_vl;
    var soMeta = state.isVolume ? c.si_fcst_dz : c.so_meta_vl;
    var attCanal = soMeta > 0 ? Math.round((soProj / soMeta) * 1000) / 10 : null;
    if (c2Val) c2Val.textContent = fmtVal(soProj, true);
    if (c2Badge) {
      if (attCanal !== null) {
        c2Badge.className = attCanal >= 100 ? 'badge-up' : (attCanal >= 90 ? 'badge-warn' : 'badge-down');
        c2Badge.textContent = Fmt.pct(attCanal, 1) + (state.isVolume ? ' do forecast' : ' da meta');
      } else {
        c2Badge.className = 'badge-neutral';
        c2Badge.textContent = 'Sem meta';
      }
    }
    if (c2Foot) {
      c2Foot.textContent = soMeta > 0
        ? ((state.isVolume ? 'Referência Forecast (DZ): ' : 'Meta oficial: ') + fmtVal(soMeta, true))
        : 'Projeção linear por dias úteis';
    }

    // Card 3: Sell-in + Carteira
    var c3Val = $('#ex-c3-val');
    var c3Badge = $('#ex-c3-badge');
    var c3Foot = $('#ex-c3-foot');
    var siReal = state.isVolume ? c.si_real_dz : c.si_real_vl;
    var cart = state.isVolume ? c.carteira_dz : c.carteira_vl;
    var siFcst = state.isVolume ? c.si_fcst_dz : c.si_fcst_vl;
    var siGar = siReal + cart;
    var siAtt = siFcst > 0 ? Math.round((siGar / siFcst) * 1000) / 10 : null;
    if (c3Val) c3Val.textContent = fmtVal(siGar, true);
    if (c3Badge) c3Badge.textContent = siAtt !== null ? (Fmt.pct(siAtt, 0) + ' do forecast') : 'Sem forecast';
    if (c3Foot) c3Foot.textContent = 'Faturado: ' + fmtVal(siReal, true) + ' · Carteira: ' + fmtVal(cart, true);

    // Card 4: Mix & Preço Médio
    var c4Val = $('#ex-c4-val');
    var c4Badge = $('#ex-c4-badge');
    var c4Foot = $('#ex-c4-foot');
    if (c4Val) c4Val.textContent = c.preco_medio_dz ? (Fmt.money(c.preco_medio_dz) + '/DZ') : '--';
    if (c4Badge) c4Badge.textContent = Fmt.pct(c.mix_brioche_pct || 0, 1) + ' Brioche';
    if (c4Foot) {
      c4Foot.textContent = 'Receita Brioche & Gourmet: ' + Fmt.moneyCompact(c.so_brioche_vl || 0) + ' de ' + Fmt.moneyCompact(c.so_real_vl || 0);
    }

    renderTable();
  }

  function getFilteredList() {
    var list = (state.payload && state.payload.distribuidores) || [];
    var belowCnt = 0, lateCnt = 0;
    list.forEach(function (d) {
      if (d.ating_proj_pct !== null && d.ating_proj_pct < 90) belowCnt++;
      if (d.so_real_vl <= 0 || (d.atraso_envio_dias !== null && d.atraso_envio_dias > 3)) lateCnt++;
    });
    var cAll = $('#ex-cnt-all'), cBel = $('#ex-cnt-below'), cLat = $('#ex-cnt-late');
    if (cAll) cAll.textContent = String(list.length);
    if (cBel) cBel.textContent = String(belowCnt);
    if (cLat) cLat.textContent = String(lateCnt);

    var q = state.search.trim().toLowerCase();
    var filtered = list.filter(function (d) {
      if (state.filter === 'below' && !(d.ating_proj_pct !== null && d.ating_proj_pct < 90)) return false;
      if (state.filter === 'late' && !(d.so_real_vl <= 0 || (d.atraso_envio_dias !== null && d.atraso_envio_dias > 3))) return false;
      if (q && (String(d.nome || '').toLowerCase().indexOf(q) < 0 && String(d.cnpj || '').indexOf(q) < 0)) return false;
      return true;
    });

    var k = state.sortKey, dir = state.sortDir;
    filtered.sort(function (a, b) {
      if (k === 'nome') return String(a.nome || '').localeCompare(String(b.nome || ''), 'pt-BR') * dir;
      var va, vb;
      if (k === 'so_real') { va = state.isVolume ? a.so_real_dz : a.so_real_vl; vb = state.isVolume ? b.so_real_dz : b.so_real_vl; }
      else if (k === 'so_proj') { va = state.isVolume ? a.so_proj_dz : a.so_proj_vl; vb = state.isVolume ? b.so_proj_dz : b.so_proj_vl; }
      else if (k === 'att') { va = a.ating_proj_pct == null ? -1 : a.ating_proj_pct; vb = b.ating_proj_pct == null ? -1 : b.ating_proj_pct; }
      else if (k === 'yoy') { va = a.yoy_pct == null ? -9999 : a.yoy_pct; vb = b.yoy_pct == null ? -9999 : b.yoy_pct; }
      else if (k === 'preco') { va = a.preco_medio_dz || 0; vb = b.preco_medio_dz || 0; }
      else if (k === 'mix') { va = a.mix_brioche_pct || 0; vb = b.mix_brioche_pct || 0; }
      else if (k === 'si') { va = state.isVolume ? (a.si_real_dz + a.carteira_dz) : (a.si_real_vl + a.carteira_vl); vb = state.isVolume ? (b.si_real_dz + b.carteira_dz) : (b.si_real_vl + b.carteira_vl); }
      else if (k === 'envio') { va = a.atraso_envio_dias == null ? 999 : a.atraso_envio_dias; vb = b.atraso_envio_dias == null ? 999 : b.atraso_envio_dias; }
      else { va = 0; vb = 0; }
      return ((Number(va) || 0) - (Number(vb) || 0)) * dir;
    });
    return filtered;
  }

  function renderTable() {
    var tbody = $('#ex-tbody');
    var empty = $('#ex-empty');
    if (!tbody) return;
    var rows = getFilteredList();
    var emptyMsg = $('#ex-empty-msg');
    var retryBtn = $('#ex-retry-btn');
    if (retryBtn) retryBtn.hidden = true;
    if (!rows.length) {
      tbody.innerHTML = '';
      if (emptyMsg) emptyMsg.textContent = 'Nenhum distribuidor encontrado para o filtro aplicado.';
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    tbody.innerHTML = rows.map(function (d) {
      var soR = state.isVolume ? d.so_real_dz : d.so_real_vl;
      var soP = state.isVolume ? d.so_proj_dz : d.so_proj_vl;
      var siG = state.isVolume ? (d.si_real_dz + d.carteira_dz) : (d.si_real_vl + d.carteira_vl);
      var attCls = d.ating_proj_pct == null ? 'att-none' : (d.ating_proj_pct >= 100 ? 'att-good' : (d.ating_proj_pct >= 90 ? 'att-warn' : 'att-bad'));
      var yoyTxt = d.yoy_pct == null ? '—' : ((d.yoy_pct >= 0 ? '+' : '−') + Fmt.pct(Math.abs(d.yoy_pct), 1));
      var yoyCls = d.yoy_pct == null ? 'muted' : (d.yoy_pct >= 0 ? 'att-good' : 'att-bad');

      var envioTip = d.ultimo_envio ? ('Última venda recebida em ' + fmtBrDate(d.ultimo_envio)) : 'Nenhuma venda recebida no mês';
      var envioHtml;
      if (d.so_real_vl <= 0) {
        envioHtml = '<span class="fc-status-badge fc-st-danger" tabindex="0" data-tip="' + Fmt.esc(envioTip) + '">Sem envio</span>';
      } else if (d.atraso_envio_dias !== null && d.atraso_envio_dias > 3) {
        envioHtml = '<span class="fc-status-badge fc-st-warn" tabindex="0" data-tip="' + Fmt.esc(envioTip) + '">Atrasado ' + d.atraso_envio_dias + 'd</span>';
      } else {
        envioHtml = '<span class="fc-status-badge fc-st-good" tabindex="0" data-tip="' + Fmt.esc(envioTip) + '">Em dia</span>';
      }

      return '<tr>' +
        '<td data-label="Distribuidor" class="ex-td-dt">' +
          '<div class="fc-prod-name">' + Fmt.esc(d.nome) + '</div>' +
          '<div class="fc-prod-meta">' + (d.dias_estoque > 0 ? ('Estoque ' + d.dias_estoque + 'd · ') : '') + (d.cnpj ? Fmt.cnpj(d.cnpj) : '') + '</div>' +
        '</td>' +
        '<td data-label="Sell-out real" class="num">' + Fmt.esc(fmtVal(soR, true)) + '</td>' +
        '<td data-label="Projeção mês" class="num"><strong>' + Fmt.esc(fmtVal(soP, true)) + '</strong></td>' +
        '<td data-label="% Meta" class="num"><span class="fc-att-pill ' + attCls + '">' + (d.ating_proj_pct != null ? Fmt.pct(d.ating_proj_pct, 0) : '—') + '</span></td>' +
        '<td data-label="Var. ano ant." class="num"><span class="' + yoyCls + '">' + Fmt.esc(yoyTxt) + '</span></td>' +
        '<td data-label="R$/DZ" class="num">' + (d.preco_medio_dz ? Fmt.esc(Fmt.money(d.preco_medio_dz)) : '—') + '</td>' +
        '<td data-label="% Mix Brioche" class="num">' + Fmt.esc(Fmt.pct(d.mix_brioche_pct || 0, 0)) + '</td>' +
        '<td data-label="Sell-in + Cart." class="num">' + Fmt.esc(fmtVal(siG, true)) + '</td>' +
        '<td data-label="Envio SO" class="num">' + envioHtml + '</td>' +
        '<td data-label="Ação" class="num"><button type="button" class="btn btn-secondary btn-sm ex-btn-open" data-open-dt="' + d.dist_id + '">Abrir</button></td>' +
      '</tr>';
    }).join('');
  }

  function exportCsv() {
    var rows = getFilteredList();
    if (!rows.length) return;
    var esc = function (v) { return '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"'; };
    var hdr = ['Distribuidor', 'CNPJ', 'Sell-out Real (R$)', 'Projecao Mes (R$)', 'Meta SO (R$)', '% Meta', 'YoY % (DU)', 'Preco Medio R$/DZ', '% Mix Brioche', 'Sell-in Real (R$)', 'Carteira (R$)', 'Dias Estoque', 'Ultimo Envio SO'];
    var body = rows.map(function (d) {
      return [d.nome, d.cnpj, d.so_real_vl, d.so_proj_vl, d.so_meta_vl, d.ating_proj_pct, d.yoy_pct, d.preco_medio_dz, d.mix_brioche_pct, d.si_real_vl, d.carteira_vl, d.dias_estoque, d.ultimo_envio || ''];
    });
    var csv = '\uFEFF' + [hdr].concat(body).map(function (r) { return r.map(esc).join(';'); }).join('\r\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'visao_executiva_distribuidores.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function syncAiButtons() {
    var bM = $('#ex-ai-mensal');
    var bS = $('#ex-ai-semanal');
    var isSem = state.aiMode === 'semanal';
    if (bM && bS) {
      bM.classList.toggle('active-label', !isSem);
      bS.classList.toggle('active-label', isSem);
      bM.setAttribute('aria-checked', String(!isSem));
      bS.setAttribute('aria-checked', String(isSem));
      bM.tabIndex = isSem ? -1 : 0;
      bS.tabIndex = isSem ? 0 : -1;
    }
  }

  function renderAiState(loading, errMsg, data) {
    var loadEl = $('#ex-ai-loading');
    var contEl = $('#ex-ai-content');
    var errEl = $('#ex-ai-error');
    var winEl = $('#ex-ai-window');
    var refBtn = $('#ex-ai-refresh');
    if (refBtn) refBtn.disabled = Boolean(loading);
    if (loading) {
      if (loadEl) loadEl.hidden = false;
      if (contEl) contEl.hidden = true;
      if (errEl) errEl.hidden = true;
      return;
    }
    if (loadEl) loadEl.hidden = true;
    if (errMsg || !data) {
      if (contEl) contEl.hidden = true;
      if (errEl) errEl.hidden = false;
      var emEl = $('#ex-ai-err-msg');
      if (emEl && errMsg) emEl.textContent = errMsg;
      return;
    }
    if (errEl) errEl.hidden = true;
    if (contEl) contEl.hidden = false;
    if (winEl) {
      var jl = String(data.janela_label || '').trim();
      var isBdaysNoise = jl.indexOf('dias úteis') !== -1 || /^\d+\s*de\s*\d+/i.test(jl);
      winEl.textContent = isBdaysNoise ? '' : jl;
      winEl.hidden = !winEl.textContent;
    }

    var hEl = $('#ex-ai-manchete');
    var mEl = $('#ex-ai-macro');
    var v = data.visual;

    if (v && v.sellout) {
      var so = v.sellout;
      var si = v.sellin || {};
      var pm = v.preco_mix || {};
      if (hEl) {
        var mNome = so.mes_nome || 'o mês';
        if (data.modo === 'semanal' && so.sem_atual) {
          hEl.textContent = 'Na última semana, o sell-out somou ' + so.sem_atual + ' (' + (so.wow || '—') + ' vs semana anterior), mantendo ' + mNome + ' em ritmo de ' + so.ating_pct + ' da meta.';
        } else if (so.is_closed) {
          hEl.textContent = mNome + ' fechou com ' + so.realizado + ' de sell-out (' + (so.yoy || '—') + ' vs ' + so.base_yoy + '), atingindo ' + so.ating_pct + ' da meta de ' + so.meta + '.';
        } else {
          hEl.textContent = 'Até hoje, o sell-out soma ' + so.realizado + ' (' + (so.yoy || '—') + ' vs ' + so.base_yoy + '), em ritmo de fechar ' + mNome + ' em ' + so.ating_pct + ' da meta — previsão de ' + so.projecao + ' contra meta de ' + so.meta + '.';
        }
      }
      if (mEl) {
        mEl.hidden = true;
        mEl.innerHTML = '';
      }
    } else {
      if (hEl) hEl.textContent = data.manchete || '';
      if (mEl) {
        mEl.hidden = false;
        mEl.textContent = data.macro || '';
      }
    }

    var movWrap = $('#ex-ai-movimentos');
    if (movWrap) {
      if (v && v.pareto) {
        state.lastAiData = data;
        movWrap.hidden = false;
        movWrap.classList.add('is-2col');
        var p = v.pareto;
        var causaMap = v.causa_raiz || {};
        var paretoDts = p.dts || [];

        // Determina distribuidor ativo: selecionado ou primeiro com vendas ou primeiro da lista
        var activeDid = state.selectedDetratorId;
        if (!activeDid || !causaMap[String(activeDid)]) {
          activeDid = paretoDts[0] ? String(paretoDts[0].dist_id) : null;
          state.selectedDetratorId = activeDid;
        }

        var paretoRows = paretoDts.map(function (d) {
          var did = String(d.dist_id);
          var isSel = did === String(activeDid);
          var realTxt = d.zerado ? '<span class="ex-mini-zero">Zerado</span>' : Fmt.esc(d.realizado || '—');
          return '<tr class="ex-mini-click ex-detrator-row' + (isSel ? ' is-selected' : '') + '" data-detrator-id="' + did + '" title="Clique para detalhar causa raiz por SKU">' +
            '<td class="ex-mini-name">' + Fmt.esc(d.nome) + '</td>' +
            '<td class="ex-mini-num ex-mini-muted">' + realTxt + '</td>' +
            '<td class="ex-mini-num ex-mini-muted">' + Fmt.esc(d.meta || '—') + '</td>' +
            '<td class="ex-mini-num is-bad">-' + Fmt.esc(d.gap) + '</td>' +
          '</tr>';
        }).join('');

        var paretoHtml = '<div class="ex-ai-panel">' +
          '<div class="ex-inf-head"><span class="ex-ai-mov-k"><span class="ex-ai-dot is-bad" aria-hidden="true"></span>1. Distribuidores Detratores</span>' +
          (p.qtd ? '<span class="ex-inf-sub">' + p.qtd + ' DTs = ' + p.share_pct + '% do gap (' + Fmt.esc(p.pareto_valor) + ' / ' + Fmt.esc(p.total_gap) + ')</span>' : '') +
          '</div>' +
          (paretoRows
            ? '<table class="ex-mini-tbl"><thead><tr><th>Distribuidor</th><th class="num">Realizado</th><th class="num">Meta</th><th class="num">Déficit</th></tr></thead><tbody>' + paretoRows + '</tbody></table>'
            : '<span class="ex-inf-empty">Sem déficit relevante</span>') +
        '</div>';

        // Detalhe Causa Raiz do Distribuidor Ativo
        var curDiag = causaMap[String(activeDid)] || {};
        var skus = Array.isArray(curDiag.skus) ? curDiag.skus : [];
        var skuRows = '';
        if (curDiag.zerado) {
          if (skus.length) {
            skuRows = skus.map(function (s) {
              return '<tr>' +
                '<td class="ex-mini-name" title="' + Fmt.esc(s.nome) + '">' + Fmt.esc(s.nome) + '</td>' +
                '<td class="ex-mini-num ex-mini-muted">' + Fmt.esc(s.referencia) + '</td>' +
                '<td class="ex-mini-num is-bad">Zerado</td>' +
              '</tr>';
            }).join('');
          }
        } else {
          skuRows = skus.map(function (s) {
            return '<tr>' +
              '<td class="ex-mini-name" title="' + Fmt.esc(s.nome) + '">' + Fmt.esc(s.nome) + '</td>' +
              '<td class="ex-mini-num ex-mini-muted">' + Fmt.esc(s.realizado) + '</td>' +
              '<td class="ex-mini-num ex-mini-muted">' + Fmt.esc(s.referencia) + '</td>' +
              '<td class="ex-mini-num is-bad">-' + Fmt.esc(s.queda) + '</td>' +
              '<td class="ex-mini-num is-bad">' + Fmt.esc(s.pct) + '</td>' +
            '</tr>';
          }).join('');
        }

        var rightPanelContent = '';
        if (curDiag.zerado) {
          rightPanelContent = '<div class="ex-root-diag">' +
            '<div class="ex-root-diag-title">' + V2.icon('alert-triangle', 14) + '<span>Faturamento Zerado no Mês</span></div>' +
            '<div class="ex-root-diag-msg">Meta de <strong>' + Fmt.esc(curDiag.meta || '') + '</strong> sem nenhum envio registrado. Ausência de transmissão de sell-out (>3d) ou faturamento pendente.</div>' +
          '</div>' +
          (skuRows
            ? '<div style="margin:4px 0 6px;font-size:11px;font-weight:600;color:var(--text-subtle)">Produtos que costumava vender no ano anterior (represados):</div>' +
              '<table class="ex-mini-tbl"><thead><tr><th>SKU / Produto</th><th class="num">Ref. Histórica</th><th class="num">Status</th></tr></thead><tbody>' + skuRows + '</tbody></table>'
            : '<span class="ex-inf-empty">Sem histórico de vendas no ano anterior</span>') +
          '<div class="ex-root-footer">' +
            '<span>Ação recomendada: Cobrar equipe de TI/EDI para retransmissão de arquivos</span>' +
            (curDiag.dist_id ? '<button type="button" class="ex-ai-act-link" data-open-dt="' + curDiag.dist_id + '">Abrir ' + Fmt.esc(curDiag.nome || '') + ' →</button>' : '') +
          '</div>';
        } else {
          rightPanelContent = (skuRows
            ? '<table class="ex-mini-tbl"><thead><tr><th>SKU / Produto Detrator</th><th class="num">Realizado</th><th class="num">Ref. YoY</th><th class="num">Queda</th><th class="num">Var.</th></tr></thead><tbody>' + skuRows + '</tbody></table>'
            : '<span class="ex-inf-empty">Nenhum SKU individual com queda expressiva vs ano anterior.</span>') +
          '<div class="ex-root-footer">' +
            '<span>Produtos com maior perda de faturamento vs ano anterior</span>' +
            (curDiag.dist_id ? '<button type="button" class="ex-ai-act-link" data-open-dt="' + curDiag.dist_id + '">Abrir ' + Fmt.esc(curDiag.nome || '') + ' →</button>' : '') +
          '</div>';
        }

        var causaRaizHtml = '<div class="ex-ai-panel">' +
          '<div class="ex-inf-head"><span class="ex-ai-mov-k"><span class="ex-ai-dot is-bad" aria-hidden="true"></span>2. Causa Raiz & SKUs Detratores</span>' +
          '<span class="ex-inf-sub">' + Fmt.esc(curDiag.nome || 'Distribuidor') + ' · Déficit -' + Fmt.esc(curDiag.gap || '') + ' vs meta</span></div>' +
          rightPanelContent +
        '</div>';

        movWrap.innerHTML = paretoHtml + causaRaizHtml;
      } else {
        movWrap.classList.remove('is-2col');
        var movs = Array.isArray(data.movimentos) ? data.movimentos : [];
        movWrap.hidden = !movs.length;
        movWrap.innerHTML = movs.map(function (mv) {
          var tom = mv.tom === 'good' || mv.tom === 'warn' || mv.tom === 'bad' ? (' is-' + mv.tom) : '';
          return '<div class="ex-ai-mov">' +
            '<span class="ex-ai-mov-k"><span class="ex-ai-dot' + tom + '" aria-hidden="true"></span>' + Fmt.esc(mv.nivel || '') + '</span>' +
            '<p class="ex-ai-mov-v">' + Fmt.esc(mv.texto || '') + '</p>' +
          '</div>';
        }).join('');
      }
    }

    var actWrap = $('#ex-ai-acoes');
    if (actWrap) {
      if (v) {
        actWrap.hidden = true;
        actWrap.innerHTML = '';
      } else {
        var acts = Array.isArray(data.acoes) ? data.acoes : [];
        actWrap.hidden = !acts.length;
        actWrap.innerHTML = acts.map(function (ac) {
          var btnHtml = '';
          if (ac.dist_id) {
            btnHtml = '<button type="button" class="ex-ai-act-link" data-open-dt="' + ac.dist_id + '">Abrir ' + Fmt.esc(ac.dist_nome || ('DT ' + ac.dist_id)) + ' →</button>';
          } else if (ac.filtro) {
            var fLbl = ac.filtro === 'late' ? 'Filtrar distribuidores sem envio →' : 'Ver abaixo da meta →';
            btnHtml = '<button type="button" class="ex-ai-act-link" data-ex-apply-filter="' + Fmt.esc(ac.filtro) + '">' + fLbl + '</button>';
          }
          return '<div class="ex-ai-act-item">' +
            '<div class="ex-ai-act-txt"><strong>' + Fmt.esc(ac.titulo || '') + '</strong>' +
              (ac.detalhe ? '<span>' + Fmt.esc(ac.detalhe) + '</span>' : '') +
            '</div>' + btnHtml +
          '</div>';
        }).join('');
      }
    }

    var metaEl = $('#ex-ai-meta');
    if (metaEl) {
      metaEl.hidden = Boolean(v);
      if (!v) {
        metaEl.textContent = data.fonte === 'databricks-ai'
          ? 'Síntese gerada automaticamente por IA sobre os indicadores oficiais dos distribuidores.'
          : 'Síntese gerada automaticamente a partir dos indicadores oficiais dos distribuidores.';
      }
    }
  }

  async function fetchAiBrief(force, queryOverride) {
    if (!document.body.classList.contains('is-admin') || document.body.classList.contains('is-simulating')) return;
    syncAiButtons();
    var q = typeof queryOverride === 'string' ? queryOverride : buildQuery();
    var key = q + '|' + state.aiMode;
    if (!force && state.aiCache[key]) {
      renderAiState(false, null, state.aiCache[key]);
      return;
    }
    if (state.aiAbort) {
      try { state.aiAbort.abort(); } catch (_) {}
    }
    var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    state.aiAbort = ctrl;
    var seq = ++state.aiReqSeq;
    renderAiState(true, null, null);

    var qp = new URLSearchParams(q);
    qp.set('modo', state.aiMode);
    if (force) qp.set('force', '1');
    try {
      var opts = { credentials: 'include' };
      if (ctrl) opts.signal = ctrl.signal;
      var res = await fetch('/api/executivo/resumo-ia?' + qp.toString(), opts);
      if (seq !== state.aiReqSeq) return;
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var data = await res.json();
      if (seq !== state.aiReqSeq) return;
      state.aiCache[key] = data;
      renderAiState(false, null, data);
    } catch (err) {
      if (err && err.name === 'AbortError') return;
      console.warn('[V2Executivo] Erro ao gerar resumo IA:', err);
      renderAiState(false, 'Não foi possível gerar o resumo executivo agora.', null);
    }
  }

  function openDistributorById(did) {
    var dObj = (state.payload && Array.isArray(state.payload.distribuidores))
      ? state.payload.distribuidores.find(function (d) { return String(d.dist_id) === String(did); })
      : null;
    var nome = dObj ? dObj.nome : undefined;
    if (window.AdminMode && typeof window.AdminMode.selectById === 'function' && window.AdminMode.selectById(did, nome)) {
      if (typeof window.activateTab === 'function') window.activateTab('kpis');
    } else {
      window.location.href = '/dashboard.html?dist_id=' + encodeURIComponent(did);
    }
  }

  function bindEvents() {
    var drawerToggle = $('#toggleValVol');
    if (drawerToggle) {
      state.isVolume = Boolean(drawerToggle.checked);
      drawerToggle.addEventListener('change', function () {
        state.isVolume = Boolean(drawerToggle.checked);
        renderAll();
      });
    }
    ['#lbl-valor', '#lbl-volume'].forEach(function (sel) {
      var b = $(sel);
      if (!b) return;
      b.addEventListener('click', function () {
        setTimeout(function () {
          var t = $('#toggleValVol');
          var nextVol = t ? Boolean(t.checked) : (sel === '#lbl-volume');
          if (state.isVolume !== nextVol) {
            state.isVolume = nextVol;
            renderAll();
          }
        }, 0);
      });
    });

    var lateBadge = $('#ex-late-badge');
    if (lateBadge) {
      lateBadge.addEventListener('click', function () {
        var btn = $('[data-ex-filter="late"]');
        if (btn) btn.click();
      });
    }

    var retryBtn = $('#ex-retry-btn');
    if (retryBtn) {
      retryBtn.addEventListener('click', function () { fetchExecutivo(true); });
    }

    $$('[data-ex-filter]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        state.filter = btn.getAttribute('data-ex-filter') || 'all';
        $$('[data-ex-filter]').forEach(function (x) {
          var on = x === btn;
          x.classList.toggle('active', on);
          x.setAttribute('aria-selected', String(on));
        });
        renderTable();
      });
    });

    var inp = $('#ex-search-input');
    if (inp) {
      inp.addEventListener('input', function () {
        state.search = inp.value || '';
        renderTable();
      });
    }

    $$('[data-ex-sort]').forEach(function (th) {
      var btn = th.querySelector('button') || th;
      btn.addEventListener('click', function () {
        var k = th.getAttribute('data-ex-sort');
        if (state.sortKey === k) state.sortDir = -state.sortDir;
        else {
          state.sortKey = k;
          state.sortDir = (k === 'nome' || k === 'envio') ? 1 : -1;
        }
        $$('[data-ex-sort]').forEach(function (x) {
          x.setAttribute('aria-sort', x === th ? (state.sortDir === 1 ? 'ascending' : 'descending') : 'none');
        });
        renderTable();
      });
    });

    var tbody = $('#ex-tbody');
    if (tbody) {
      tbody.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-open-dt]');
        if (btn) openDistributorById(btn.getAttribute('data-open-dt'));
      });
    }

    var aiCard = $('#ex-ai-brief');
    if (aiCard) {
      aiCard.addEventListener('click', function (e) {
        var openBtn = e.target.closest('[data-open-dt]');
        if (openBtn) {
          openDistributorById(openBtn.getAttribute('data-open-dt'));
          return;
        }
        var detRow = e.target.closest('.ex-detrator-row');
        if (detRow) {
          var did = detRow.getAttribute('data-detrator-id');
          if (did && state.lastAiData) {
            state.selectedDetratorId = did;
            renderAiState(false, null, state.lastAiData);
            return;
          }
        }
        var fltBtn = e.target.closest('[data-ex-apply-filter]');
        if (fltBtn) {
          var targetF = fltBtn.getAttribute('data-ex-apply-filter');
          var pill = $('[data-ex-filter="' + targetF + '"]');
          if (pill) pill.click();
          var tblCard = $('.ex-table-card');
          if (tblCard && tblCard.scrollIntoView) tblCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    }

    $$('[data-ai-mode]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var m = btn.getAttribute('data-ai-mode') || 'mensal';
        if (state.aiMode === m) return;
        state.aiMode = m;
        fetchAiBrief(false);
      });
    });

    var aiRg = $('.ex-ai-switch');
    if (aiRg) {
      aiRg.addEventListener('keydown', function (e) {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
        e.preventDefault();
        var next = state.aiMode === 'mensal' ? $('#ex-ai-semanal') : $('#ex-ai-mensal');
        if (next) { next.focus(); next.click(); }
      });
    }

    var aiRef = $('#ex-ai-refresh');
    if (aiRef) aiRef.addEventListener('click', function () { fetchAiBrief(true); });
    var aiRetry = $('#ex-ai-retry');
    if (aiRetry) aiRetry.addEventListener('click', function () { fetchAiBrief(true); });
    var aiToggle = $('#ex-ai-toggle');
    if (aiToggle) {
      aiToggle.addEventListener('click', function () {
        state.aiCollapsed = !state.aiCollapsed;
        var body = $('#ex-ai-body');
        if (body) body.hidden = state.aiCollapsed;
        aiToggle.setAttribute('aria-expanded', String(!state.aiCollapsed));
        aiToggle.textContent = state.aiCollapsed ? 'Expandir' : 'Recolher';
      });
    }

    var btnCsv = $('#ex-btn-export');
    if (btnCsv) btnCsv.addEventListener('click', exportCsv);
  }

  document.addEventListener('DOMContentLoaded', bindEvents);

  window.V2Executivo = {
    refresh: function () { fetchExecutivo(true); },
    onTabActivated: function () { fetchExecutivo(false); }
  };
})();

