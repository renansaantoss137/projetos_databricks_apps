/* ==========================================================================
   Portal Distribuidores v2 — Módulo Forecast & Planejamento (v2_forecast.js)
   Focado na tomada de decisão isolada do distribuidor:
     1. Projeção de fechamento mensal (Sell-out e Sell-in) + Túnel de Confiança
     2. Gap projetado contra a Meta Oficial e Ritmo Diário Necessário
     3. Plano de Pedidos (Faturado + Carteira Aberta vs Pedido Sugerido Restante)
     4. Curva Diária e Trajetória Acumulada interativas com tooltips por dia
     5. Ritmo Semanal (Semanas 1 a 5) e Matriz de Decisão/Estoque por SKU
   ========================================================================== */
(function () {
  'use strict';

  var state = {
    payload: null,
    loading: false,
    lastQuery: null,
    pendingQuery: null,
    abortCtrl: null,
    prefetchTimer: null,
    reqSeq: 0,
    lens: 'sellout',       // 'sellout' | 'sellin'
    isVolume: false,       // false = Valor (R$), true = Volume (DZ)
    horizon: 1,            // 1 | 2 | 3 meses
    chartView: 'daily',    // 'daily' | 'cumulative'
    skuFilter: 'all',      // 'all' | 'ruptura' | 'pedir' | 'acelerar' | 'no_ritmo'
    skuSearch: '',
    skuSortKey: 'proj',
    skuSortDir: -1,
    skuPage: 1,
    skuPageSize: 12
  };

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function fmtVal(v, compact, categoria) {
    var n = Number(v) || 0;
    if (!window.Fmt) return String(Math.round(n));
    if (state.isVolume) {
      var isEspecialidade = categoria && /especialidade|doce|bolo|lamus/i.test(categoria);
      var unit = isEspecialidade ? 'Und' : 'DZ';
      return (compact ? Fmt.compact(n) : Fmt.int(n)) + ' ' + unit;
    }
    return compact ? Fmt.moneyCompact(n) : Fmt.money(n);
  }

  function fmtDateBr(iso) {
    if (!iso) return '--';
    var p = String(iso).slice(0, 10).split('-');
    return p.length === 3 ? (p[2] + '/' + p[1] + '/' + p[0]) : iso;
  }

  function buildCurrentQuery() {
    var ids = [
      ['categoria', 'select-categoria'],
      ['produto', 'select-produto'],
      ['sku', 'select-sku'],
      ['pedido', 'select-pedido'],
      ['dia', 'select-dia'],
      ['semana', 'select-semana'],
      ['mes', 'select-mes'],
      ['ano', 'select-ano']
    ];
    var qp = new URLSearchParams();
    ids.forEach(function (pair) {
      if (typeof window.getSafeSelectedValues === 'function') {
        var vals = window.getSafeSelectedValues(pair[1]);
        if (vals && vals.length) qp.append(pair[0], vals.join(','));
      }
    });
    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('dist')) qp.append('dist', urlParams.get('dist'));
    if (urlParams.get('dist_id')) qp.append('dist_id', urlParams.get('dist_id'));
    if (state.horizon > 1) qp.append('horizon', String(state.horizon));
    return qp.toString();
  }

  function syncHorizonButtons() {
    [1, 2, 3].forEach(function (h) {
      var btn = $('#fc-horizon-' + h);
      if (!btn) return;
      var on = state.horizon === h;
      btn.classList.toggle('active-label', on);
      btn.setAttribute('aria-checked', String(on));
      btn.tabIndex = on ? 0 : -1;
    });
  }

  function syncUnitButtons() {
    var bVal = $('#fc-unit-valor');
    var bVol = $('#fc-unit-volume');
    if (bVal && bVol) {
      bVal.classList.toggle('active-label', !state.isVolume);
      bVol.classList.toggle('active-label', state.isVolume);
      bVal.setAttribute('aria-checked', String(!state.isVolume));
      bVol.setAttribute('aria-checked', String(state.isVolume));
      bVal.tabIndex = state.isVolume ? -1 : 0;
      bVol.tabIndex = state.isVolume ? 0 : -1;
    }
  }

  function syncLensButtons() {
    var bSo = $('#fc-btn-sellout');
    var bSi = $('#fc-btn-sellin');
    var isSo = state.lens === 'sellout';
    if (bSo && bSi) {
      bSo.classList.toggle('active-label', isSo);
      bSi.classList.toggle('active-label', !isSo);
      bSo.setAttribute('aria-checked', String(isSo));
      bSi.setAttribute('aria-checked', String(!isSo));
      bSo.tabIndex = isSo ? 0 : -1;
      bSi.tabIndex = isSo ? -1 : 0;
    }
  }

  function syncViewButtons() {
    var bDay = $('#fc-view-daily');
    var bCum = $('#fc-view-cum');
    var isDay = state.chartView === 'daily';
    if (bDay && bCum) {
      bDay.classList.toggle('active-label', isDay);
      bCum.classList.toggle('active-label', !isDay);
      bDay.setAttribute('aria-checked', String(isDay));
      bCum.setAttribute('aria-checked', String(!isDay));
      bDay.tabIndex = isDay ? 0 : -1;
      bCum.tabIndex = isDay ? -1 : 0;
    }
  }

  function isForecastTabVisible() {
    var tab = $('#tab-forecast');
    if (!tab) return false;
    return tab.style.display !== 'none' && tab.offsetParent !== null;
  }

  async function fetchForecast(queryString, force) {
    var q = typeof queryString === 'string' ? queryString : buildCurrentQuery();
    if (!force && state.payload && state.lastQuery === q) {
      state.pendingQuery = null;
      renderAll();
      return;
    }
    if (state.loading && state.lastQuery === q && !force) {
      return;
    }
    if (state.abortCtrl) {
      try { state.abortCtrl.abort(); } catch (_) {}
    }
    var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    state.abortCtrl = ctrl;
    state.lastQuery = q;
    state.pendingQuery = null;
    state.loading = true;
    var seq = ++state.reqSeq;

    var stage = $('#fc-chart-stage');
    if (stage) stage.setAttribute('aria-busy', 'true');

    try {
      var base = typeof window.API_BASE === 'string' ? window.API_BASE : '';
      var fetchOpts = { credentials: 'include' };
      if (ctrl) fetchOpts.signal = ctrl.signal;
      var res = await fetch(base + '/api/forecast' + (q ? '?' + q : ''), fetchOpts);
      if (seq !== state.reqSeq) return;
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var data = await res.json();
      if (seq !== state.reqSeq) return;
      state.payload = data;
      state.loading = false;
      var globalErr = $('#v2-error');
      if (globalErr) globalErr.hidden = true;
      renderAll();
    } catch (err) {
      if (err && err.name === 'AbortError') return;
      if (seq !== state.reqSeq) return;
      state.loading = false;
      console.warn('[V2Forecast] Erro ao carregar /api/forecast:', err);
      if (stage) {
        stage.setAttribute('aria-busy', 'false');
        stage.innerHTML = '<div class="v2-empty"><p>Não foi possível calcular a previsão para o filtro atual.</p><button type="button" class="btn btn-secondary btn-sm" id="fc-retry-btn">Tentar novamente</button></div>';
        var retryBtn = $('#fc-retry-btn');
        if (retryBtn) retryBtn.addEventListener('click', function () { fetchForecast(state.lastQuery, true); });
      }
    }
  }

  function activeDataBlock() {
    if (!state.payload) return null;
    var unitBlock = state.isVolume ? state.payload.volume : state.payload.valor;
    if (!unitBlock) return null;
    return state.lens === 'sellout' ? unitBlock.sellout : unitBlock.sellin;
  }

  function renderHorizonOverlay() {
    if (!(state.horizon > 1 && state.payload && state.payload.horizonte)) return;
    var hz = state.payload.horizonte;
    var unitKey = state.isVolume ? 'volume' : 'valor';
    var lensKey = state.lens === 'sellout' ? 'sellout' : 'sellin';
    var cons = hz.consolidado && hz.consolidado[unitKey] && hz.consolidado[unitKey][lensKey];
    if (!cons) return;

    var c1Title = $('#fc-c1-title');
    if (c1Title) c1Title.textContent = 'Projeção ' + hz.meses + ' meses (' + hz.periodo_label + ')';
    var c1Val = $('#fc-c1-val');
    if (c1Val) {
      c1Val.textContent = fmtVal(cons.projecao, true);
      c1Val.setAttribute('data-tip', V2.tipHtml('Projeção acumulada (' + hz.meses + ' meses)', [
        ['Central esperada', fmtVal(cons.projecao, false)],
        ['Cenário conservador (IC 85%)', fmtVal(cons.int_min, false)],
        ['Cenário otimista (IC 85%)', fmtVal(cons.int_max, false)],
        ['Já realizado no mês atual', fmtVal(cons.realizado, false)]
      ], 'Horizonte ' + hz.periodo_label + '.'));
    }
    var c1Range = $('#fc-c1-range');
    if (c1Range) c1Range.textContent = fmtVal(cons.int_min, true) + ' a ' + fmtVal(cons.int_max, true);
    var c1Tunnel = $('#fc-c1-tunnel');
    if (c1Tunnel) {
      c1Tunnel.setAttribute('tabindex', '0');
      c1Tunnel.setAttribute('data-tip', V2.tipHtml(
        'Faixa esperada (' + hz.meses + ' meses · IC 85%)',
        [
          ['Piso conservador', fmtVal(cons.int_min, false)],
          ['Projeção central', fmtVal(cons.projecao, false)],
          ['Teto otimista', fmtVal(cons.int_max, false)]
        ]
      ));
    }
    var c1Prog = $('#fc-c1-progress');
    var c1Fill = $('#fc-c1-prog-fill');
    if (c1Prog && c1Fill) {
      var hasAllPub = cons.meta > 0 && cons.metas_publicadas === cons.total_meses;
      var pctBarHz = hasAllPub ? Math.min(100, Math.max(0, Math.round(cons.ating_pct || 0))) : 100;
      c1Prog.setAttribute('aria-valuenow', String(pctBarHz));
      c1Fill.style.width = pctBarHz + '%';
      c1Fill.className = 'kpi-progress-fill ' + V2.attClass(cons.ating_pct || 0, hasAllPub);
    }
    var c1Badge = $('#fc-c1-badge');
    if (c1Badge) {
      if (cons.ating_pct !== null) {
        var up = cons.ating_pct >= 100;
        c1Badge.className = up ? 'badge-up' : (cons.ating_pct >= 90 ? 'badge-warn' : 'badge-down');
        c1Badge.innerHTML = '<span>Atinge ' + Fmt.pct(cons.ating_pct, 1) + ' da meta</span>';
      } else {
        c1Badge.className = 'badge-neutral';
        c1Badge.textContent = cons.metas_publicadas + '/' + cons.total_meses + ' metas';
      }
    }
    var c1Foot = $('#fc-c1-foot');
    if (c1Foot) {
      c1Foot.innerHTML = 'Acumulado real no mês atual: <strong>' + Fmt.esc(fmtVal(cons.realizado, true)) + '</strong> · Horizonte de ' + hz.meses + ' meses.';
    }

    var c2Title = $('#fc-c2-title');
    if (c2Title) c2Title.textContent = 'Realizado & metas (' + hz.meses + 'm)';
    var c2Tag = $('#fc-c2-tag');
    if (c2Tag) c2Tag.textContent = cons.metas_publicadas + ' de ' + cons.total_meses + ' metas';
    var c2MetaK = $('#fc-c2-meta-k');
    if (c2MetaK) c2MetaK.textContent = 'Metas publicadas (' + hz.periodo_label + ')';
    var c2MetaV = $('#fc-c2-meta-v');
    if (c2MetaV) c2MetaV.textContent = cons.meta > 0 ? fmtVal(cons.meta, true) : 'Sem meta';
    var c2GapK = $('#fc-c2-gap-k');
    if (c2GapK) c2GapK.textContent = 'Balanço projetado (' + hz.meses + 'm) vs metas';
    var c2GapV = $('#fc-c2-gap-v');
    if (c2GapV) {
      if (cons.meta > 0) {
        var gHz = cons.projecao - cons.meta;
        c2GapV.textContent = (gHz >= 0 ? '+' : '−') + fmtVal(Math.abs(gHz), true);
        c2GapV.className = gHz >= 0 ? 'att-good' : 'att-bad';
      } else {
        c2GapV.textContent = '—';
        c2GapV.className = '';
      }
    }
    var c2Foot = $('#fc-c2-foot');
    if (c2Foot) {
      if (cons.metas_publicadas < cons.total_meses) {
        c2Foot.textContent = 'Meses futuros sem meta oficial no ERP usam somente projeção estatística.';
      } else if (cons.meta > 0) {
        var faltaHz = Math.max(0, cons.meta - cons.realizado);
        c2Foot.innerHTML = 'Faltam <strong>' + Fmt.esc(fmtVal(faltaHz, true)) + '</strong> sobre o realizado atual para 100% das metas do período.';
      } else {
        c2Foot.textContent = 'Projeção estatística consolidada para ' + hz.periodo_label + '.';
      }
    }

    // Sinaliza claramente que decisão diária e SKUs tratam o mês corrente
    var c3Tag = $('#fc-c3-tag');
    if (c3Tag) c3Tag.textContent = 'Operação mês atual';

    // Ajusta controles e legenda do gráfico para visão mensal multi-mês (sem Dia a dia / Acumulado)
    var viewSwitch = $('.fc-chart-head .segmented');
    if (viewSwitch) viewSwitch.hidden = true;
    var chartLeg = $('.fc-chart-legend');
    if (chartLeg) {
      chartLeg.setAttribute('data-hz-leg', '1');
      chartLeg.innerHTML =
        '<span class="leg-item"><span class="fc-lg-solid" style="background:var(--action);height:8px;border-radius:4px;" aria-hidden="true"></span>Projeção mensal do modelo</span>' +
        '<span class="leg-item"><span style="display:inline-block;width:2px;height:12px;background:var(--text-strong);margin-right:6px;vertical-align:middle;" aria-hidden="true"></span>Meta oficial publicada</span>';
    }

    // Renderiza gráfico mensal comparativo no palco principal
    var stage = $('#fc-chart-stage');
    var chartTitle = $('#fc-chart-title');
    var chartSub = $('#fc-chart-sub');
    if (chartTitle) chartTitle.textContent = 'Projeção dos próximos ' + hz.meses + ' meses (' + hz.periodo_label + ')';
    if (chartSub) chartSub.textContent = 'Comparativo mensal entre projeção estatística do modelo e meta oficial publicada.';
    if (!stage || !Array.isArray(hz.meses_detalhe)) return;

    var months = hz.meses_detalhe;
    var maxV = 1;
    months.forEach(function (m) {
      var b = m[unitKey][lensKey];
      maxV = Math.max(maxV, Number(b.projecao) || 0, Number(b.meta) || 0, Number(b.int_max) || 0);
    });
    var html = '<div class="fc-hz-bars">' + months.map(function (m) {
      var b = m[unitKey][lensKey];
      var pctProj = Math.round(((Number(b.projecao) || 0) / maxV) * 100);
      var pctMeta = (Number(b.meta) || 0) > 0 ? Math.round((Number(b.meta) / maxV) * 100) : 0;
      var tipRows = [
        ['Projeção central', fmtVal(b.projecao, false)],
        ['Faixa esperada (IC 85%)', fmtVal(b.int_min, true) + ' a ' + fmtVal(b.int_max, true)],
        ['Meta oficial', b.meta_publicada ? fmtVal(b.meta, false) : 'Não publicada no ERP']
      ];
      if (b.realizado > 0) tipRows.unshift(['Realizado até corte', fmtVal(b.realizado, false)]);
      var attBadge = b.meta_publicada && b.ating_pct !== null
        ? '<span class="' + (b.ating_pct >= 100 ? 'att-good' : (b.ating_pct >= 90 ? 'att-warn' : 'att-bad')) + '">' + Fmt.esc(Fmt.pct(b.ating_pct, 1)) + ' da meta</span>'
        : '<span class="muted">Meta futura não publicada</span>';

      return '<div class="fc-hz-col" tabindex="0" data-tip="' + Fmt.esc(V2.tipHtml(m.mes_nome + ' ' + m.ano, tipRows)) + '">' +
        '<div class="fc-hz-head"><strong>' + Fmt.esc(m.label) + '</strong>' + attBadge + '</div>' +
        '<div class="fc-hz-track">' +
          '<div class="fc-hz-bar" style="width:' + Math.max(4, pctProj) + '%"></div>' +
          (pctMeta > 0 ? '<div class="fc-hz-meta-mark" style="left:' + Math.min(98, pctMeta) + '%" title="Meta oficial"></div>' : '') +
        '</div>' +
        '<div class="fc-hz-foot"><span>Proj.: <strong>' + Fmt.esc(fmtVal(b.projecao, true)) + '</strong></span>' +
          '<span>' + (b.meta_publicada ? ('Meta: ' + Fmt.esc(fmtVal(b.meta, true))) : 'Estimado s/ meta') + '</span></div>' +
      '</div>';
    }).join('') + '</div>';
    stage.innerHTML = html;
  }

  function renderAll() {
    syncUnitButtons();
    syncLensButtons();
    syncViewButtons();
    syncHorizonButtons();

    if (!state.payload || !state.payload.periodo) return;
    var d = activeDataBlock();
    if (!d) return;

    var per = state.payload.periodo;
    var isSo = state.lens === 'sellout';

    // 1. Cutoff e nota do modelo exclusivo do distribuidor
    var cPill = $('#fc-cutoff-pill');
    if (cPill) {
      var cutTxt = per.is_closed_month
        ? 'Mês encerrado (' + per.last_day + ' dias)'
        : ('Corte realizado até ' + fmtDateBr(per.cutoff_dt) + ' (dia ' + per.cutoff_day + ' de ' + per.last_day + ')');
      cPill.textContent = cutTxt;
    }

    var mNote = $('#fc-model-note');
    if (mNote) {
      var distRaw = ($('#qf-dist-input') && $('#qf-dist-input').value) ? $('#qf-dist-input').value.trim() : '';
      if (!distRaw || /^todos/i.test(distRaw) || /^\d+\s+sel\.$/i.test(distRaw)) {
        var hdrNm = ($('#hdr-hello-name') && $('#hdr-hello-name').textContent) ? $('#hdr-hello-name').textContent.trim() : '';
        if (hdrNm && !/administrador|distribuidor|todos/i.test(hdrNm)) distRaw = hdrNm;
        else distRaw = '';
      }
      var fmtDistName = distRaw
        ? distRaw.toLowerCase().replace(/\b([a-zà-ú])/g, function (m) { return m.toUpperCase(); })
        : '';
      var sparkIco = '<svg class="ico" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/></svg>';
      if (fmtDistName) {
        mNote.innerHTML = sparkIco + '<span><strong>Previsão sob medida para ' + Fmt.esc(fmtDistName) + '</strong> — calculada com o histórico e ritmo próprios da sua operação</span>';
      } else {
        mNote.innerHTML = sparkIco + '<span><strong>Previsão individual por distribuidor</strong> — cada operação usa histórico e ritmo próprios</span>';
      }
      if (window.V2 && typeof V2.tipHtml === 'function') {
        mNote.setAttribute('data-tip', V2.tipHtml('Previsão feita sob medida', [
          ['Base própria', 'Só histórico desta operação'],
          ['Calendário', 'Ritmo por dia da semana'],
          ['Reposição', 'Cruza vendas + pedidos abertos']
        ], 'Sem médias genéricas: cada distribuidor conta com projeção exclusiva, calibrada para a própria rota.'));
      }
    }

    var alertBanner = $('#fc-alert-banner');
    var alertText = $('#fc-alert-text');
    if (alertBanner && alertText) {
      var aviso = isSo ? d.aviso_envio : null;
      if (aviso) {
        alertBanner.hidden = false;
        alertText.textContent = aviso;
      } else {
        alertBanner.hidden = true;
        alertText.textContent = '';
      }
    }

    var chartTitleEl = $('#fc-chart-title');
    var chartSubEl = $('#fc-chart-sub');
    var viewSwitch = $('.fc-chart-head .segmented');
    var chartLeg = $('.fc-chart-legend');
    if (state.horizon === 1) {
      if (chartTitleEl) chartTitleEl.textContent = 'Curva de evolução e tendência até o fim do mês';
      if (chartSubEl) chartSubEl.textContent = 'Toque ou passe o mouse sobre qualquer dia para inspecionar realizado, projeção e média histórica do dia da semana.';
      if (viewSwitch) viewSwitch.hidden = false;
      if (chartLeg && chartLeg.getAttribute('data-hz-leg') === '1') {
        chartLeg.removeAttribute('data-hz-leg');
        chartLeg.innerHTML =
          '<span class="leg-item"><span class="fc-lg-solid" aria-hidden="true"></span>Realizado</span>' +
          '<span class="leg-item"><span class="fc-lg-proj" aria-hidden="true"></span>Projeção futura</span>' +
          '<span class="leg-item" id="fc-leg-ref-wrap"><span class="fc-lg-hist" aria-hidden="true"></span><span id="fc-leg-ref-lbl">Média histórica do dia da semana</span></span>';
      }
      var c2MetaK = $('#fc-c2-meta-k');
      if (c2MetaK) c2MetaK.textContent = 'Meta oficial do mês';
      var c2GapK = $('#fc-c2-gap-k');
      if (c2GapK) c2GapK.textContent = 'Balanço projetado vs meta';
    }

    // 2. Cards Executivos (1 a 4)
    renderKpiCards(d, per, isSo);

    // 3. Curva Diária / Acumulada SVG ou Horizonte 2–3 meses
    if (state.horizon > 1 && state.payload.horizonte) {
      renderHorizonOverlay();
    } else {
      renderForecastChart(d, per, isSo);
    }

    // 4. Semanas do Mês
    renderWeeksGrid(d, per, isSo);

    // 5. Tabela de Decisão por SKU
    renderSkuTable();
  }

  function renderKpiCards(d, per, isSo) {
    var proj = Number(d.projecao_fechamento || 0);
    var real = Number(d.realizado || 0);
    var meta = Number(d.meta || 0);
    var intMin = Number(d.int_min || 0);
    var intMax = Number(d.int_max || 0);
    var hasMeta = meta > 0;
    var attProj = hasMeta ? Number(d.atingimento_proj_pct || ((proj / meta) * 100)) : null;
    var attReal = hasMeta ? Number(d.atingimento_real_pct || ((real / meta) * 100)) : null;

    // Card 1: Projeção de Fechamento
    var c1Title = $('#fc-c1-title');
    if (c1Title) c1Title.textContent = isSo ? 'Projeção de fechamento (Sell-out)' : 'Projeção de fechamento (Sell-in)';

    var c1Val = $('#fc-c1-val');
    if (c1Val) {
      c1Val.textContent = fmtVal(proj, true);
      c1Val.setAttribute('data-tip', V2.tipHtml(
        'Projeção de fechamento',
        [
          ['Valor exato projetado', fmtVal(proj, false)],
          ['Piso esperado (IC mín.)', fmtVal(intMin, false)],
          ['Teto esperado (IC máx.)', fmtVal(intMax, false)]
        ],
        per.label
      ));
    }

    var c1Badge = $('#fc-c1-badge');
    if (c1Badge) {
      if (hasMeta && attProj !== null) {
        var up = attProj >= 100;
        c1Badge.className = up ? 'badge-up' : (attProj >= 90 ? 'badge-warn' : 'badge-down');
        var gapPct = Math.abs(100 - attProj);
        var tipText = up
          ? ('Projeção supera a meta em +' + Fmt.pct(attProj - 100, 1))
          : ('Projeção atinge ' + Fmt.pct(attProj, 1) + ' da meta (gap de -' + Fmt.pct(gapPct, 1) + ')');
        c1Badge.setAttribute('title', tipText);
        c1Badge.innerHTML = '<span>Atinge ' + Fmt.pct(attProj, 1) + ' da meta</span>';
      } else {
        c1Badge.className = 'badge-neutral';
        c1Badge.textContent = 'Sem meta oficial';
      }
    }

    var c1Range = $('#fc-c1-range');
    if (c1Range) c1Range.textContent = fmtVal(intMin, true) + ' a ' + fmtVal(intMax, true);

    var c1Tunnel = $('#fc-c1-tunnel');
    if (c1Tunnel) {
      c1Tunnel.setAttribute('tabindex', '0');
      c1Tunnel.setAttribute('data-tip', V2.tipHtml(
        'Faixa esperada de fechamento (IC 85%)',
        [
          ['Cenário conservador (piso)', fmtVal(intMin, false)],
          ['Projeção central esperada', fmtVal(proj, false)],
          ['Cenário otimista (teto)', fmtVal(intMax, false)]
        ],
        'IC = Intervalo de Confiança: 85% de probabilidade do faturamento fechar nesta faixa, calculada pela volatilidade histórica da sua operação.'
      ));
    }

    var c1Prog = $('#fc-c1-progress');
    var c1Fill = $('#fc-c1-prog-fill');
    if (c1Prog && c1Fill) {
      var pctBar = hasMeta ? Math.min(100, Math.max(0, Math.round(attProj || 0))) : 100;
      c1Prog.setAttribute('aria-valuenow', String(pctBar));
      c1Fill.style.width = pctBar + '%';
      c1Fill.className = 'kpi-progress-fill ' + V2.attClass(attProj || 0, hasMeta);
    }

    var c1Foot = $('#fc-c1-foot');
    if (c1Foot) {
      if (per.is_closed_month) {
        c1Foot.textContent = 'Período encerrado — comparativo entre projeção do modelo e fechamento.';
      } else {
        var remVal = Math.max(0, proj - real);
        c1Foot.innerHTML = 'Já realizado: <strong>' + Fmt.esc(fmtVal(real, true)) + '</strong> · Mais <strong>' + Fmt.esc(fmtVal(remVal, true)) + '</strong> previstos até o dia ' + per.last_day;
      }
    }

    // Card 2: Realizado & Gap vs Meta
    var c2Title = $('#fc-c2-title');
    if (c2Title) c2Title.textContent = isSo ? 'Realizado & meta de vendas' : 'Faturado & meta de compras';

    var c2Tag = $('#fc-c2-tag');
    if (c2Tag) c2Tag.textContent = hasMeta && attReal !== null ? (Fmt.pct(attReal, 1) + ' realizado') : 'Acumulado no mês';

    var c2Val = $('#fc-c2-val');
    if (c2Val) {
      c2Val.textContent = fmtVal(real, true);
      c2Val.setAttribute('data-tip', V2.tipHtml(
        'Acumulado realizado no mês',
        [
          ['Realizado exato', fmtVal(real, false)],
          ['Meta oficial do mês', hasMeta ? fmtVal(meta, false) : 'Sem meta cadastrada']
        ]
      ));
    }

    var c2MetaV = $('#fc-c2-meta-v');
    if (c2MetaV) c2MetaV.textContent = hasMeta ? fmtVal(meta, true) : 'Sem meta';

    var c2GapV = $('#fc-c2-gap-v');
    if (c2GapV) {
      if (hasMeta) {
        var gap = proj - meta;
        var sign = gap >= 0 ? '+' : '−';
        c2GapV.textContent = sign + fmtVal(Math.abs(gap), true);
        c2GapV.className = gap >= 0 ? 'att-good' : 'att-bad';
      } else {
        c2GapV.textContent = '—';
        c2GapV.className = '';
      }
    }

    var c2Foot = $('#fc-c2-foot');
    if (c2Foot) {
      if (hasMeta) {
        var faltamHoje = Math.max(0, meta - real);
        c2Foot.innerHTML = faltamHoje > 0
          ? ('Faltam <strong>' + Fmt.esc(fmtVal(faltamHoje, true)) + '</strong> sobre o realizado atual para 100% da meta.')
          : '<strong class="att-good">Meta oficial já superada pelo realizado acumulado!</strong>';
      } else {
        c2Foot.textContent = 'Acompanhe a evolução diária na curva abaixo.';
      }
    }

    // Card 3: Plano Operacional (Adapta entre Sell-out e Sell-in)
    var c3Title = $('#fc-c3-title');
    var c3Tag = $('#fc-c3-tag');
    var c3Val = $('#fc-c3-val');
    var c3R1K = $('#fc-c3-r1-k'), c3R1V = $('#fc-c3-r1-v');
    var c3R2K = $('#fc-c3-r2-k'), c3R2V = $('#fc-c3-r2-v');
    var c3Foot = $('#fc-c3-foot');

    if (isSo) {
      var ritmoNec = Number(d.ritmo_necessario_dia || d.ritmo_necessario_meta || 0);
      var ritmoProj = Number(d.media_projetada_dia || d.ritmo_projetado || 0);
      var diasRest = Number(d.dias_uteis_restantes || 0);
      var diasCorr = Number(d.dias_uteis_corridos || 0);
      var diasTot = Number(d.dias_uteis_total || 26);

      if (c3Title) c3Title.textContent = 'Ritmo diário necessário';
      if (c3Tag) c3Tag.textContent = diasRest > 0 ? (diasRest + ' dias úteis restantes') : 'Mês concluído';
      if (c3Val) {
        c3Val.textContent = hasMeta && diasRest > 0 ? (fmtVal(ritmoNec, true) + '/dia') : (fmtVal(ritmoProj, true) + '/dia');
      }
      if (c3R1K) c3R1K.textContent = 'Seu ritmo projetado até o fim';
      if (c3R1V) {
        c3R1V.textContent = fmtVal(ritmoProj, true) + '/dia';
        c3R1V.className = (hasMeta && ritmoProj >= ritmoNec) ? 'att-good' : '';
      }
      if (c3R2K) c3R2K.textContent = 'Dias úteis transcorridos';
      if (c3R2V) c3R2V.textContent = diasCorr + ' de ' + diasTot + ' dias';

      if (c3Foot) {
        if (per.is_closed_month) {
          c3Foot.textContent = 'Média diária realizada nos ' + (d.dias_ativos_mes || diasTot) + ' dias com venda ativa.';
        } else if (hasMeta && ritmoNec > 0) {
          var diffRitmo = ritmoProj - ritmoNec;
          if (diffRitmo >= 0) {
            c3Foot.innerHTML = '<span class="att-good">Ritmo atual suficiente</span> para atingir a meta mantendo a cadência da rota.';
          } else {
            c3Foot.innerHTML = 'Acelere <strong>+' + Fmt.esc(fmtVal(Math.abs(diffRitmo), true)) + '/dia útil</strong> nas rotas para buscar 100% da meta.';
          }
        } else {
          c3Foot.textContent = 'Projeção baseada nas últimas 8 semanas e positivação ativa.';
        }
      }
    } else {
      // Lente Sell-in: foco em Faturado + Carteira Aberta e Sugestão de Novo Pedido
      var cart = Number(d.carteira_aberta || 0);
      var gar = Number(d.garantido_total || (real + cart));
      var sug = Number(d.pedido_sugerido_restante || 0);

      if (c3Title) c3Title.textContent = 'Plano de compras & carteira';
      if (c3Tag) c3Tag.textContent = cart > 0 ? 'Com carteira aberta' : 'Carteira zerada';
      if (c3Val) {
        c3Val.textContent = sug > 0 ? fmtVal(sug, true) : 'Cobertura completa';
        c3Val.setAttribute('data-tip', V2.tipHtml(
          'Cálculo de reposição do mês',
          [
            ['Faturado no mês', fmtVal(real, false)],
            ['Carteira de pedidos em aberto', fmtVal(cart, false)],
            ['Total já garantido (Faturado + Carteira)', fmtVal(gar, false)],
            ['Novos pedidos sugeridos até o fim do mês', fmtVal(sug, false)]
          ]
        ));
      }
      if (c3R1K) c3R1K.textContent = 'Carteira de pedidos em aberto';
      if (c3R1V) {
        c3R1V.textContent = fmtVal(cart, true);
        c3R1V.className = '';
      }
      if (c3R2K) c3R2K.textContent = 'Total garantido (Faturado + Carteira)';
      if (c3R2V) {
        c3R2V.textContent = fmtVal(gar, true) + (hasMeta && d.atingimento_garantido_pct ? ' (' + Fmt.pct(d.atingimento_garantido_pct, 0) + ')' : '');
      }
      if (c3Foot) {
        if (sug > 0) {
          c3Foot.innerHTML = 'Sugestão de novos pedidos para atingir a meta/giro. <button type="button" class="btn-link fc-inline-link" id="fc-goto-grade">Ver carteira em Pedidos</button>';
        } else {
          c3Foot.innerHTML = 'Faturado + carteira cobrem a projeção do mês. <button type="button" class="btn-link fc-inline-link" id="fc-goto-grade">Consultar entregas em Pedidos</button>';
        }
        var btnGoto = $('#fc-goto-grade');
        if (btnGoto) {
          btnGoto.addEventListener('click', function () {
            if (typeof window.activateTab === 'function') window.activateTab('grade');
          });
        }
      }
    }

    // Card 4: Assertividade de Predição Sell-out / Sell-in
    var acc = Number(d.acuracia_modelo_pct || 0);
    var canalCurto = isSo ? 'Sell-out' : 'Sell-in';
    var c4Title = $('#fc-c4-title');
    if (c4Title) c4Title.textContent = 'Assertividade de Predição ' + canalCurto;

    var c4Val = $('#fc-c4-val');
    if (c4Val) {
      c4Val.textContent = Fmt.pct(acc, 1) + ' de precisão';
      c4Val.title = 'O modelo acertou ' + Fmt.pct(acc, 1) + ' do fechamento real nos meses anteriores. Projeção auditada por backtest com dados históricos da sua operação.';
    }

    var c4Badge = $('#fc-c4-badge');
    if (c4Badge) {
      c4Badge.className = acc >= 90 ? 'badge-up' : 'badge-warn';
      c4Badge.textContent = acc >= 90 ? 'Alta fidelidade' : 'Calibrado';
      c4Badge.title = 'Auditado por backtest nos meses anteriores da sua operação';
    }

    var c4Diag = $('#fc-c4-diag');
    if (c4Diag) {
      var canalNome = isSo ? 'vendas (Sell-out)' : 'compras (Sell-in)';
      var metricNome = state.isVolume ? 'em volume (DZ)' : 'em faturamento (R$)';
      var tooltipDet = 'O modelo acertou ' + Fmt.pct(acc, 1) + ' do fechamento real de ' + canalNome + ' ' + metricNome + ' nos meses anteriores. Projeção auditada com dados próprios da sua operação.';
      c4Diag.title = tooltipDet;
      c4Diag.style.cursor = 'help';
      if (acc > 0) {
        c4Diag.textContent = 'Confiança comprovada na predição do ' + canalCurto + '.';
      } else {
        c4Diag.textContent = 'Predição calibrada com o histórico dos últimos 60 dias.';
      }
    }

    var resSkus = state.payload.resumo_skus || { risco_ruptura: 0, sugestao_pedido: 0 };
    var nRup = $('#fc-qp-ruptura-num');
    var nPed = $('#fc-qp-pedir-num');
    if (nRup) nRup.textContent = String(resSkus.risco_ruptura || 0);
    if (nPed) nPed.textContent = String(resSkus.sugestao_pedido || 0);
  }

  function renderForecastChart(d, per, isSo) {
    var stage = $('#fc-chart-stage');
    if (!stage) return;
    stage.setAttribute('aria-busy', 'false');

    var series = d.daily_series || [];
    if (!series.length) {
      stage.innerHTML = '<div class="v2-empty"><p>Sem dados diários suficientes para traçar a curva neste período.</p></div>';
      return;
    }

    var isCum = state.chartView === 'cumulative';
    var refLbl = $('#fc-leg-ref-lbl');
    if (refLbl) {
      refLbl.textContent = isCum ? 'Trajetória ideal da meta (dias úteis)' : 'Média histórica do mesmo dia da semana';
    }

    // Usa a largura real do container para manter proporção 1:1 (sem deformar texto ou curvas)
    var rawW = stage.clientWidth || 960;
    var W = Math.max(560, Math.round(rawW));
    var H = W < 640 ? 220 : 250;
    var padL = 68, padR = 20, padT = 18, padB = 42;
    var plotW = W - padL - padR;
    var plotH = H - padT - padB;
    var n = series.length;

    function xOf(idx) {
      if (n <= 1) return padL + plotW / 2;
      return padL + (idx / (n - 1)) * plotW;
    }

    // Coleta valores para escala vertical (sem faixa esperada)
    var allVals = [1];
    series.forEach(function (r) {
      if (isCum) {
        if (r.acum_real !== null) allVals.push(r.acum_real);
        allVals.push(r.acum_proj || 0);
        if (r.acum_meta > 0) allVals.push(r.acum_meta);
      } else {
        if (r.real !== null) allVals.push(r.real);
        allVals.push(r.projecao || 0);
        allVals.push(r.media_hist || 0);
      }
    });

    var maxVal = Math.max.apply(null, allVals) * 1.12;
    var baseY = padT + plotH;
    function yOf(v) {
      var clamped = Math.max(0, Math.min(maxVal, Number(v) || 0));
      return padT + plotH - (clamped / maxVal) * plotH;
    }

    // Rótulos do eixo Y (sem linhas de grade)
    var axisSvg = '';
    for (var g = 0; g <= 4; g++) {
      var frac = g / 4;
      var gy = padT + plotH - frac * plotH;
      var gVal = maxVal * frac;
      axisSvg += '<text x="' + (padL - 10) + '" y="' + (gy + 4).toFixed(1) + '" text-anchor="end" class="fc-svg-axis">' + Fmt.esc(fmtVal(gVal, true)) + '</text>';
    }

    // Pontos das curvas
    var realPts = [];
    var projPts = [];
    var refPts = [];
    var cutoffIdx = -1;

    series.forEach(function (r, idx) {
      var x = xOf(idx);
      var vReal = isCum ? r.acum_real : r.real;
      var vProj = isCum ? r.acum_proj : r.projecao;
      var vRef = isCum ? r.acum_meta : r.media_hist;

      refPts.push([x, yOf(vRef)]);

      if (r.is_past && vReal !== null) {
        realPts.push([x, yOf(vReal)]);
        cutoffIdx = idx;
      }
      if (!r.is_past) {
        // Conecta a linha projetada a partir do último ponto realizado
        if (projPts.length === 0 && cutoffIdx >= 0) {
          var prevR = series[cutoffIdx];
          var prevVal = isCum ? prevR.acum_real : prevR.real;
          projPts.push([xOf(cutoffIdx), yOf(prevVal)]);
        }
        projPts.push([x, yOf(vProj)]);
      }
    });

    // Curva suave monotônica (sem overshoot abaixo de zero)
    function toSmoothPath(pts) {
      if (!pts.length) return '';
      if (pts.length === 1) return 'M' + pts[0][0].toFixed(1) + ',' + pts[0][1].toFixed(1);
      if (pts.length === 2) {
        return 'M' + pts[0][0].toFixed(1) + ',' + pts[0][1].toFixed(1) + ' L' + pts[1][0].toFixed(1) + ',' + pts[1][1].toFixed(1);
      }
      var m = pts.length;
      var dx = [], dy = [], slopes = [], tangents = [];
      for (var i = 0; i < m - 1; i++) {
        dx[i] = pts[i + 1][0] - pts[i][0];
        dy[i] = pts[i + 1][1] - pts[i][1];
        slopes[i] = dx[i] !== 0 ? (dy[i] / dx[i]) : 0;
      }
      tangents[0] = slopes[0];
      for (var j = 1; j < m - 1; j++) {
        if (slopes[j - 1] * slopes[j] <= 0) {
          tangents[j] = 0;
        } else {
          tangents[j] = (slopes[j - 1] + slopes[j]) / 2;
        }
      }
      tangents[m - 1] = slopes[m - 2];

      for (var k = 0; k < m - 1; k++) {
        if (slopes[k] === 0) {
          tangents[k] = 0;
          tangents[k + 1] = 0;
        } else {
          var alpha = tangents[k] / slopes[k];
          var beta = tangents[k + 1] / slopes[k];
          var s2 = alpha * alpha + beta * beta;
          if (s2 > 9) {
            var tau = 3 / Math.sqrt(s2);
            tangents[k] = tau * alpha * slopes[k];
            tangents[k + 1] = tau * beta * slopes[k];
          }
        }
      }

      var dStr = 'M' + pts[0][0].toFixed(1) + ',' + pts[0][1].toFixed(1);
      for (var s = 0; s < m - 1; s++) {
        var h = dx[s] / 3;
        var cp1x = pts[s][0] + h;
        var cp1y = Math.min(baseY, Math.max(padT, pts[s][1] + tangents[s] * h));
        var cp2x = pts[s + 1][0] - h;
        var cp2y = Math.min(baseY, Math.max(padT, pts[s + 1][1] - tangents[s + 1] * h));
        dStr += ' C' + cp1x.toFixed(1) + ',' + cp1y.toFixed(1) + ' ' + cp2x.toFixed(1) + ',' + cp2y.toFixed(1) + ' ' + pts[s + 1][0].toFixed(1) + ',' + pts[s + 1][1].toFixed(1);
      }
      return dStr;
    }

    function toAreaPath(pts) {
      if (pts.length < 2) return '';
      var bY = baseY.toFixed(1);
      return toSmoothPath(pts) + ' L' + pts[pts.length - 1][0].toFixed(1) + ',' + bY + ' L' + pts[0][0].toFixed(1) + ',' + bY + ' Z';
    }

    var realArea = realPts.length >= 2 ? '<path d="' + toAreaPath(realPts) + '" class="fc-svg-real-area" />' : '';
    var refPath = refPts.length >= 2 ? '<path d="' + toSmoothPath(refPts) + '" class="fc-svg-ref-line" />' : '';
    var realPath = realPts.length >= 2 ? '<path d="' + toSmoothPath(realPts) + '" class="fc-svg-real-line" />' : '';
    var projPath = projPts.length >= 2 ? '<path d="' + toSmoothPath(projPts) + '" class="fc-svg-proj-line" />' : '';

    // Colunas interativas para tooltip ao passar o mouse (sem marcadores fixos)
    var hitCols = '';
    var colW = plotW / Math.max(1, n);

    series.forEach(function (r, idx) {
      var x = xOf(idx);
      var vMain = isCum ? (r.is_past ? r.acum_real : r.acum_proj) : (r.is_past ? r.real : r.projecao);
      var y = yOf(vMain);

      if (idx === 0 || idx === n - 1 || r.day % 3 === 1) {
        axisSvg += '<text x="' + x.toFixed(1) + '" y="' + (H - 18) + '" text-anchor="middle" class="fc-svg-xlab">' + String(r.day).padStart(2, '0') + '</text>';
        axisSvg += '<text x="' + x.toFixed(1) + '" y="' + (H - 5) + '" text-anchor="middle" class="fc-svg-xdow">' + Fmt.esc(r.dow_name) + '</text>';
      }

      var tipTitle = 'Dia ' + String(r.day).padStart(2, '0') + ' (' + r.dow_name + ') · ' + fmtDateBr(r.dt);
      var tipRows = [];
      if (r.is_past) {
        tipRows.push(['Realizado no dia', fmtVal(r.real, false)]);
        tipRows.push(['Média histórica (' + r.dow_name + ')', fmtVal(r.media_hist, false)]);
        tipRows.push(['Acumulado no mês', fmtVal(r.acum_real, false)]);
        if (r.acum_meta > 0 && r.acum_real !== null) {
          tipRows.push(['Meta proporcional acumulada', fmtVal(r.acum_meta, false)]);
          var attAcum = (r.acum_real / r.acum_meta) * 100;
          var attCls = attAcum >= 100 ? 'att-good' : (attAcum >= 85 ? 'att-warn' : 'att-bad');
          tipRows.push(['Atingimento vs meta acumulada', Fmt.pct(attAcum, 1), attCls]);
        }
      } else {
        tipRows.push(['Projeção do dia', fmtVal(r.projecao, false)]);
        tipRows.push(['Média histórica (' + r.dow_name + ')', fmtVal(r.media_hist, false)]);
        tipRows.push(['Acumulado projetado', fmtVal(r.acum_proj, false)]);
        if (r.acum_meta > 0) {
          tipRows.push(['Meta proporcional acumulada', fmtVal(r.acum_meta, false)]);
          var attAcum = (r.acum_proj / r.acum_meta) * 100;
          var attCls = attAcum >= 100 ? 'att-good' : (attAcum >= 85 ? 'att-warn' : 'att-bad');
          tipRows.push(['Projetado vs meta acumulada', Fmt.pct(attAcum, 1), attCls]);
        }
      }
      var metaTot = Number(d.meta || 0);
      if (metaTot > 0) {
        var vCurAcum = r.is_past ? (r.acum_real || 0) : (r.acum_proj || 0);
        var pctMesTot = (vCurAcum / metaTot) * 100;
        tipRows.push(['Progresso da meta do mês', Fmt.pct(pctMesTot, 1)]);
      }
      var tipFoot = r.is_past ? 'Dado consolidado no Lakehouse' : 'Previsão estatística para dia futuro';

      var rx = (x - colW / 2).toFixed(1);
      var aria = tipTitle + ': ' + (r.is_past ? 'realizado ' : 'projetado ') + fmtVal(vMain, true);
      hitCols += '<g class="fc-hit-col" tabindex="0" role="button" aria-label="' + Fmt.esc(aria) + '" data-tip="' + Fmt.esc(V2.tipHtml(tipTitle, tipRows, tipFoot)) + '">' +
        '<line x1="' + x.toFixed(1) + '" y1="' + padT + '" x2="' + x.toFixed(1) + '" y2="' + baseY + '" class="fc-hit-guide" />' +
        '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="4.5" class="fc-hit-ring" />' +
        '<rect x="' + rx + '" y="' + padT + '" width="' + colW.toFixed(1) + '" height="' + plotH + '" fill="transparent" />' +
      '</g>';
    });

    stage.innerHTML =
      '<div class="fc-svg-wrap">' +
        '<svg class="fc-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Curva de previsão mensal">' +
          axisSvg +
          realArea +
          refPath +
          realPath +
          projPath +
          hitCols +
        '</svg>' +
      '</div>';
  }

  function renderWeeksGrid(d, per, isSo) {
    var grid = $('#fc-weeks-grid');
    if (!grid) return;
    var weeks = d.weekly_breakdown || [];
    if (!weeks.length) {
      grid.innerHTML = '<div class="v2-empty sm"><p>Sem detalhamento semanal.</p></div>';
      return;
    }

    var stateLabels = {
      'concluida': ['Concluída', 'fc-wk-done'],
      'em_andamento': ['Semana atual', 'fc-wk-active'],
      'futura': ['Projetada', 'fc-wk-future']
    };

    grid.innerHTML = weeks.map(function (w) {
      var st = stateLabels[w.estado] || ['Projetada', 'fc-wk-future'];
      var hasMeta = w.meta > 0;
      var att = w.atingimento_pct;
      var attCls = V2.attClass(att || 0, hasMeta);
      var mainVal = w.estado === 'concluida' ? w.real : w.projecao;
      var mainLbl = w.estado === 'concluida' ? 'Realizado' : (w.estado === 'em_andamento' ? 'Real + Projeção' : 'Projeção da semana');
      var pctBar = hasMeta && att !== null ? Math.min(100, Math.max(0, Math.round(att))) : 100;

      var tip = V2.tipHtml(
        w.label + ' (' + w.range_str + ')',
        [
          ['Realizado na semana', fmtVal(w.real, false)],
          ['Fechamento esperado da semana', fmtVal(w.projecao, false)],
          ['Meta proporcional da semana', hasMeta ? fmtVal(w.meta, false) : 'Sem meta'],
          ['Atingimento esperado', hasMeta && att !== null ? Fmt.pct(att, 1) : '—', attCls]
        ]
      );

      return '<article class="fc-week-item ' + st[1] + '" tabindex="0" data-tip="' + Fmt.esc(tip) + '">' +
        '<div class="fc-wk-head">' +
          '<div>' +
            '<h3 class="fc-wk-title">' + Fmt.esc(w.label) + '</h3>' +
            '<span class="fc-wk-range">' + Fmt.esc(w.range_str) + '</span>' +
          '</div>' +
          '<span class="fc-wk-badge">' + Fmt.esc(st[0]) + '</span>' +
        '</div>' +
        '<div class="fc-wk-val-row">' +
          '<div>' +
            '<span class="fc-wk-k">' + Fmt.esc(mainLbl) + '</span>' +
            '<strong class="fc-wk-v">' + Fmt.esc(fmtVal(mainVal, true)) + '</strong>' +
          '</div>' +
          '<div class="fc-wk-meta-col">' +
            '<span class="fc-wk-k">Meta semana</span>' +
            '<span class="fc-wk-m">' + (hasMeta ? Fmt.esc(fmtVal(w.meta, true)) : '—') + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="kpi-progress fc-wk-prog"><span class="kpi-progress-fill ' + attCls + '" style="width:' + pctBar + '%"></span></div>' +
        '<div class="fc-wk-foot">' +
          '<span>' + (w.estado === 'em_andamento' ? ('Já realizado: ' + Fmt.esc(fmtVal(w.real, true))) : (w.estado === 'concluida' ? 'Semana fechada' : 'Tendência futura')) + '</span>' +
          '<strong class="' + attCls + '">' + (hasMeta && att !== null ? Fmt.pct(att, 0) : '—') + '</strong>' +
        '</div>' +
      '</article>';
    }).join('');
  }

  function getFilteredSortedSkus() {
    if (!state.payload || !Array.isArray(state.payload.skus)) return [];
    var all = state.payload.skus;
    var isSo = state.lens === 'sellout';

    // Atualiza contadores nas pílulas de filtro
    var counts = { all: all.length, ruptura: 0, pedir: 0, acelerar: 0, no_ritmo: 0 };
    all.forEach(function (s) {
      if (counts[s.status_code] !== undefined) counts[s.status_code]++;
    });
    var cAll = $('#fc-cnt-all'), cRup = $('#fc-cnt-ruptura'), cPed = $('#fc-cnt-pedir'), cAce = $('#fc-cnt-acelerar'), cOk = $('#fc-cnt-noritmo');
    if (cAll) cAll.textContent = String(counts.all);
    if (cRup) cRup.textContent = String(counts.ruptura);
    if (cPed) cPed.textContent = String(counts.pedir);
    if (cAce) cAce.textContent = String(counts.acelerar);
    if (cOk) cOk.textContent = String(counts.no_ritmo);

    var q = state.skuSearch.trim().toLowerCase();
    var filtered = all.filter(function (s) {
      if (state.skuFilter !== 'all' && s.status_code !== state.skuFilter) return false;
      if (q) {
        var hay = (s.sku + ' ' + s.produto + ' ' + s.categoria + ' ' + s.status_label).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });

    var statusOrder = { ruptura: 1, pedir: 2, acelerar: 3, no_ritmo: 4 };
    filtered.sort(function (a, b) {
      var ua = state.isVolume ? a.volume : a.valor;
      var ub = state.isVolume ? b.volume : b.valor;
      var k = state.skuSortKey;
      var dir = state.skuSortDir;

      if (k === 'produto') return a.produto.localeCompare(b.produto, 'pt-BR') * dir;
      if (k === 'status') return ((statusOrder[a.status_code] || 9) - (statusOrder[b.status_code] || 9)) * dir;
      if (k === 'dias') return ((a.dias_estoque || 0) - (b.dias_estoque || 0)) * dir;
      if (k === 'carteira') return ((ua.carteira_aberta || 0) - (ub.carteira_aberta || 0)) * dir;
      if (k === 'sugestao') return ((ua.pedido_sugerido || 0) - (ub.pedido_sugerido || 0)) * dir;
      if (k === 'meta') return ((ua.meta || 0) - (ub.meta || 0)) * dir;
      if (k === 'real') {
        var ra = isSo ? ua.so_real : ua.si_real;
        var rb = isSo ? ub.so_real : ub.si_real;
        return (ra - rb) * dir;
      }
      if (k === 'ating') {
        var aa = (isSo ? ua.ating_so_pct : ua.ating_si_pct) || 0;
        var ab = (isSo ? ub.ating_so_pct : ub.ating_si_pct) || 0;
        return (aa - ab) * dir;
      }
      // default: proj
      var pa = isSo ? ua.so_proj : ua.si_proj;
      var pb = isSo ? ub.so_proj : ub.si_proj;
      return (pa - pb) * dir;
    });

    return filtered;
  }

  function renderSkuTable() {
    var tbody = $('#fc-sku-tbody');
    var empty = $('#fc-sku-empty');
    var countTxt = $('#fc-sku-count-txt');
    var pager = $('#fc-sku-pagination');
    if (!tbody) return;

    var isSo = state.lens === 'sellout';
    var thReal = $('#fc-th-real');
    var thProj = $('#fc-th-proj');
    if (thReal) thReal.textContent = isSo ? 'Sell-out realizado' : 'Sell-in faturado';
    if (thProj) thProj.textContent = isSo ? 'Projeção Sell-out' : 'Projeção Sell-in';

    var list = getFilteredSortedSkus();
    var total = list.length;

    if (total === 0) {
      tbody.innerHTML = '';
      if (empty) empty.hidden = false;
      if (countTxt) countTxt.textContent = 'Mostrando 0 itens';
      if (pager) pager.innerHTML = '';
      return;
    }
    if (empty) empty.hidden = true;

    var totalPages = Math.max(1, Math.ceil(total / state.skuPageSize));
    if (state.skuPage > totalPages) state.skuPage = totalPages;
    var start = (state.skuPage - 1) * state.skuPageSize;
    var pageItems = list.slice(start, start + state.skuPageSize);

    var statusClsMap = {
      ruptura: 'fc-st-danger',
      pedir: 'fc-st-warn',
      acelerar: 'fc-st-info',
      no_ritmo: 'fc-st-good'
    };

    // Atualiza CTA do Mercanet com o total sugerido de reposição nos SKUs
    var ctaMercanet = $('#fc-mercanet-cta');
    if (ctaMercanet && state.payload && Array.isArray(state.payload.skus)) {
      var totalSugSkus = state.payload.skus.reduce(function (acc, item) {
        var uItem = state.isVolume ? item.volume : item.valor;
        return acc + Number((uItem && uItem.pedido_sugerido) || 0);
      }, 0);
      var ctaSpan = ctaMercanet.querySelector('span');
      if (ctaSpan) {
        ctaSpan.textContent = totalSugSkus > 0
          ? ('Emitir pedido no Mercanet (+' + fmtVal(totalSugSkus, true) + ')')
          : 'Emitir pedido no Mercanet';
      }
    }

    tbody.innerHTML = pageItems.map(function (s) {
      var u = state.isVolume ? s.volume : s.valor;
      var vReal = isSo ? u.so_real : u.si_real;
      var vProj = isSo ? u.so_proj : u.si_proj;
      var vMeta = u.meta;
      var vAtt = isSo ? u.ating_so_pct : u.ating_si_pct;
      var hasMeta = vMeta > 0 && vAtt !== null;
      var attCls = V2.attClass(vAtt || 0, hasMeta);

      var dias = s.dias_estoque || 0;
      var hasOpenOrder = Number(u.carteira_aberta || 0) > 0;
      var diasCls = dias <= 7
        ? (hasOpenOrder ? 'sev-warning' : 'sev-danger')
        : (dias <= 18 ? 'sev-warning' : (dias <= 30 ? 'sev-success' : 'sev-info'));
      var diasTxt = Fmt.int(dias) + ' dias' + (dias <= 7 && hasOpenOrder ? ' · c/ ped.' : '');
      var stCls = statusClsMap[s.status_code] || 'fc-st-good';

      var isEsp = /especialidade|doce|bolo|lamus/i.test(s.categoria || '');
      var pal = s.pallet || {};
      var sugVal = Number(u.pedido_sugerido) || 0;
      var palMin = Number(pal.pallets_min) || (sugVal > 0 ? 1 : 0);
      var titleTooltip = '';
      if (sugVal > 0 || palMin > 0) {
        if (palMin > 0) {
          var palLbl = palMin === 1 ? '1 pallet' : palMin + ' pallets';
          var necUnitStr = isEsp
            ? (Number(pal.pedido_nec_un || 0).toLocaleString('pt-BR') + ' un')
            : (Number(pal.pedido_nec_dz || 0).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' DZ');
          var fechadoUnitStr = isEsp
            ? (Number(pal.pedido_fechado_un || 0).toLocaleString('pt-BR') + ' un')
            : (Number(pal.pedido_fechado_dz || 0).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' DZ');

          var excNum = isEsp ? Number(pal.excedente_un || 0) : Number(pal.excedente_dz || 0);
          var excUnitStr = isEsp
            ? (Number(pal.excedente_un || 0).toLocaleString('pt-BR') + ' un')
            : (Number(pal.excedente_dz || 0).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' DZ');

          var vlAproxNum = pal.vl_aprox_fechado || sugVal;
          var vlAproxFormatted = Fmt.moneyCompact ? Fmt.moneyCompact(vlAproxNum) : ('R$ ' + Math.round(vlAproxNum).toLocaleString('pt-BR'));

          titleTooltip = 'Lote mínimo: ' + palLbl + ' (' + fechadoUnitStr + ')' +
            (excNum > 0.05 ? ('\nExcedente de pallet: +' + excUnitStr) : '') +
            (pal.caixas_pallet ? ('\nPallet padrão: ' + pal.caixas_pallet + ' caixas') : '') +
            '\nValor estimado fechado: ~' + vlAproxFormatted;
        }
      }

      return '<tr>' +
        '<td data-label="Produto / SKU" class="fc-td-prod">' +
          '<div class="fc-prod-name">' + Fmt.esc(s.produto) + '</div>' +
          '<div class="fc-prod-meta"><span class="fc-sku-code">SKU ' + Fmt.esc(s.sku) + '</span> · <span>' + Fmt.esc(s.categoria) + '</span>' + (pal.caixas_pallet ? (' · <span>' + pal.caixas_pallet + ' cx/pal</span>') : '') + '</div>' +
        '</td>' +
        '<td data-label="Realizado no mês" class="num">' + Fmt.esc(fmtVal(vReal, true, s.categoria)) + '</td>' +
        '<td data-label="Projeção fechamento" class="num"><strong class="fc-proj-strong">' + Fmt.esc(fmtVal(vProj, true, s.categoria)) + '</strong></td>' +
        '<td data-label="Referência / Meta" class="num">' + (vMeta > 0 ? Fmt.esc(fmtVal(vMeta, true, s.categoria)) : '—') + '</td>' +
        '<td data-label="% Ating. proj." class="num"><span class="fc-att-pill ' + attCls + '">' + (hasMeta ? Fmt.pct(vAtt, 0) : '—') + '</span></td>' +
        '<td data-label="Carteira aberta" class="num">' + (u.carteira_aberta > 0 ? Fmt.esc(fmtVal(u.carteira_aberta, true, s.categoria)) : '—') + '</td>' +
        '<td data-label="Cobertura estoque" class="num"><span class="dias-badge ' + diasCls + '">' + Fmt.esc(diasTxt) + '</span></td>' +
        '<td data-label="Status &amp; recomendação" class="fc-td-status"' + (titleTooltip ? (' title="' + Fmt.esc(titleTooltip) + '"') : '') + '>' +
          '<span class="fc-status-badge ' + stCls + '">' + Fmt.esc(s.status_label) + '</span>' +
          '<span class="fc-status-rec">' + Fmt.esc(s.acao_recomendada) + '</span>' +
        '</td>' +
      '</tr>';
    }).join('');

    if (countTxt) {
      countTxt.textContent = 'Mostrando ' + (start + 1) + '–' + Math.min(start + state.skuPageSize, total) + ' de ' + total + ' produtos';
    }

    if (pager) {
      if (totalPages <= 1) {
        pager.innerHTML = '';
      } else {
        var btns = '';
        btns += '<button type="button" class="page-btn" data-fc-page="' + (state.skuPage - 1) + '" ' + (state.skuPage <= 1 ? 'disabled' : '') + ' aria-label="Página anterior">&lsaquo;</button>';
        for (var p = 1; p <= totalPages; p++) {
          if (p === 1 || p === totalPages || Math.abs(p - state.skuPage) <= 1) {
            btns += '<button type="button" class="page-btn' + (p === state.skuPage ? ' active' : '') + '" data-fc-page="' + p + '">' + p + '</button>';
          }
        }
        btns += '<button type="button" class="page-btn" data-fc-page="' + (state.skuPage + 1) + '" ' + (state.skuPage >= totalPages ? 'disabled' : '') + ' aria-label="Próxima página">&rsaquo;</button>';
        pager.innerHTML = btns;
      }
    }
  }

  function exportSkusCsv() {
    var list = getFilteredSortedSkus();
    if (!list.length) return;
    var unitLbl = state.isVolume ? 'DZ' : 'R$';
    var headers = [
      'SKU', 'Produto', 'Categoria', 'Unidade',
      'Sell-out Realizado (' + unitLbl + ')', 'Sell-out Projetado (' + unitLbl + ')',
      'Sell-in Faturado (' + unitLbl + ')', 'Carteira Aberta (' + unitLbl + ')',
      'Sell-in Projetado (' + unitLbl + ')', 'Meta / Referencia (' + unitLbl + ')',
      'Pedido Sugerido (' + unitLbl + ')',
      'Pallets Mínimos', 'Necessidade Calculada', 'Pedido Fechado Lote',
      'Excedente Lote', 'Valor Aprox Fechado (R$)',
      'Dias de Estoque', 'Status', 'Recomendacao'
    ];
    var rows = list.map(function (s) {
      var u = state.isVolume ? s.volume : s.valor;
      var pal = s.pallet || {};
      var isEspItem = /especialidade|doce|bolo|lamus/i.test(s.categoria || '');
      var itemUnit = isEspItem ? 'un' : 'DZ';
      var necVal = isEspItem ? (pal.pedido_nec_un || 0) : (pal.pedido_nec_dz || 0);
      var fecVal = isEspItem ? (pal.pedido_fechado_un || 0) : (pal.pedido_fechado_dz || 0);
      var excVal = isEspItem ? (pal.excedente_un || 0) : (pal.excedente_dz || 0);
      return [
        s.sku,
        '"' + String(s.produto || '').replace(/"/g, '""') + '"',
        '"' + String(s.categoria || '').replace(/"/g, '""') + '"',
        itemUnit,
        String(u.so_real || 0).replace('.', ','),
        String(u.so_proj || 0).replace('.', ','),
        String(u.si_real || 0).replace('.', ','),
        String(u.carteira_aberta || 0).replace('.', ','),
        String(u.si_proj || 0).replace('.', ','),
        String(u.meta || 0).replace('.', ','),
        String(u.pedido_sugerido || 0).replace('.', ','),
        String(pal.pallets_min || 0),
        String(necVal).replace('.', ','),
        String(fecVal).replace('.', ','),
        String(excVal).replace('.', ','),
        String(pal.vl_aprox_fechado || 0).replace('.', ','),
        String(s.dias_estoque || 0),
        '"' + String(s.status_label || '').replace(/"/g, '""') + '"',
        '"' + String(s.acao_recomendada || '').replace(/"/g, '""') + '"'
      ].join(';');
    });
    var csv = '\uFEFF' + headers.join(';') + '\r\n' + rows.join('\r\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    var per = (state.payload && state.payload.periodo) || {};
    a.href = url;
    a.download = 'forecast_reposicao_skus_' + (per.ano || '2026') + '_' + String(per.mes || '11').padStart(2, '0') + '.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function setSkuFilterPill(filterKey, scrollIntoView) {
    state.skuFilter = filterKey;
    state.skuPage = 1;
    $$('.fc-filter-pills .fc-pill').forEach(function (btn) {
      var on = btn.getAttribute('data-filter') === filterKey;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-selected', String(on));
    });
    renderSkuTable();
    if (scrollIntoView) {
      var sec = $('#fc-sku-section');
      if (sec && sec.scrollIntoView) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  function bindEvents() {
    // Alternância Sell-out / Sell-in
    ['#fc-btn-sellout', '#fc-btn-sellin'].forEach(function (sel) {
      var btn = $(sel);
      if (!btn) return;
      btn.addEventListener('click', function () {
        state.lens = btn.getAttribute('data-lens') || 'sellout';
        renderAll();
      });
    });

    // Alternância Valor (R$) / Volume (DZ) sincronizada com o portal
    ['#fc-unit-valor', '#fc-unit-volume'].forEach(function (sel) {
      var btn = $(sel);
      if (!btn) return;
      btn.addEventListener('click', function () {
        var wantVol = btn.getAttribute('data-unit') === 'volume';
        state.isVolume = wantVol;
        var globalToggle = $('#toggleValVol');
        if (globalToggle && globalToggle.checked !== wantVol) {
          globalToggle.checked = wantVol;
          globalToggle.dispatchEvent(new Event('change', { bubbles: true }));
        }
        renderAll();
      });
    });

    var globalToggle = $('#toggleValVol');
    if (globalToggle) {
      globalToggle.addEventListener('change', function () {
        state.isVolume = !!globalToggle.checked;
        renderAll();
      });
    }

    // Alternância Dia a Dia / Acumulado
    ['#fc-view-daily', '#fc-view-cum'].forEach(function (sel) {
      var btn = $(sel);
      if (!btn) return;
      btn.addEventListener('click', function () {
        state.chartView = btn.getAttribute('data-view') || 'daily';
        renderAll();
      });
    });

    // Alternância Horizonte (1 mês / 2 meses / 3 meses)
    [1, 2, 3].forEach(function (h) {
      var btn = $('#fc-horizon-' + h);
      if (!btn) return;
      btn.addEventListener('click', function () {
        if (state.horizon === h) return;
        state.horizon = h;
        syncHorizonButtons();
        fetchForecast(buildCurrentQuery(), false);
      });
    });

    // Atalhos rápidos do Card 4 para filtrar SKUs
    $$('[data-sku-filter]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        setSkuFilterPill(btn.getAttribute('data-sku-filter') || 'all', true);
      });
    });

    // Pílulas de filtro da tabela de SKUs
    $$('.fc-filter-pills .fc-pill').forEach(function (btn) {
      btn.addEventListener('click', function () {
        setSkuFilterPill(btn.getAttribute('data-filter') || 'all', false);
      });
    });

    // Busca de SKU
    var searchInp = $('#fc-sku-search-input');
    if (searchInp) {
      searchInp.addEventListener('input', function () {
        state.skuSearch = searchInp.value || '';
        state.skuPage = 1;
        renderSkuTable();
      });
    }

    // Ordenação de colunas da tabela de SKUs
    $$('[data-fc-sort]').forEach(function (th) {
      var btn = th.querySelector('button') || th;
      btn.addEventListener('click', function () {
        var k = th.getAttribute('data-fc-sort');
        if (state.skuSortKey === k) {
          state.skuSortDir = -state.skuSortDir;
        } else {
          state.skuSortKey = k;
          state.skuSortDir = (k === 'produto' || k === 'dias' || k === 'status') ? 1 : -1;
        }
        $$('[data-fc-sort]').forEach(function (x) {
          x.setAttribute('aria-sort', x === th ? (state.skuSortDir === 1 ? 'ascending' : 'descending') : 'none');
        });
        state.skuPage = 1;
        renderSkuTable();
      });
    });

    // Paginação da tabela de SKUs
    var pager = $('#fc-sku-pagination');
    if (pager) {
      pager.addEventListener('click', function (e) {
        var b = e.target.closest('[data-fc-page]');
        if (!b || b.disabled) return;
        var pg = parseInt(b.getAttribute('data-fc-page'), 10);
        if (!isNaN(pg) && pg >= 1) {
          state.skuPage = pg;
          renderSkuTable();
        }
      });
    }

    // Exportar CSV
    var btnCsv = $('#fc-export-csv');
    if (btnCsv) btnCsv.addEventListener('click', exportSkusCsv);

    // Minimizar / expandir módulo de previsão por semana (nativamente minimizado)
    var weeksCard = $('#fc-weeks-card');
    var weeksHead = $('#fc-weeks-head');
    var weeksToggle = $('#fc-weeks-toggle');
    var weeksToggleTxt = $('#fc-weeks-toggle-txt');
    var weeksGrid = $('#fc-weeks-grid');
    function toggleWeeksCard() {
      if (!weeksCard || !weeksGrid) return;
      var collapsed = weeksCard.classList.toggle('is-collapsed');
      weeksGrid.hidden = collapsed;
      if (weeksToggle) weeksToggle.setAttribute('aria-expanded', String(!collapsed));
      if (weeksToggleTxt) weeksToggleTxt.textContent = collapsed ? 'Mostrar semanas' : 'Minimizar';
    }
    if (weeksToggle) {
      weeksToggle.addEventListener('click', function (e) {
        e.stopPropagation();
        toggleWeeksCard();
      });
    }
    if (weeksHead) {
      weeksHead.addEventListener('click', function (e) {
        if (e.target.closest('button')) return;
        toggleWeeksCard();
      });
    }

    // Navegação por teclado (ArrowLeft / ArrowRight) em todos os radiogroups do Forecast
    $$('#tab-forecast [role="radiogroup"]').forEach(function (rg) {
      rg.addEventListener('keydown', function (e) {
        if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
        var btns = $$('[role="radio"]', rg).filter(function (x) { return x.offsetParent !== null; });
        if (!btns.length) return;
        var idx = btns.indexOf(document.activeElement);
        if (idx < 0) return;
        e.preventDefault();
        var next = btns[(idx + (e.key === 'ArrowRight' ? 1 : -1) + btns.length) % btns.length];
        next.focus();
        next.click();
      });
    });

    // Re-renderiza ao redimensionar mantendo o horizonte ativo (1m vs 2–3m)
    var resizeTimer = null;
    window.addEventListener('resize', function () {
      if (!state.payload || !state.payload.periodo) return;
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        if (state.horizon > 1 && state.payload.horizonte) {
          renderHorizonOverlay();
        } else {
          var d = activeDataBlock();
          if (d) renderForecastChart(d, state.payload.periodo, state.lens === 'sellout');
        }
      }, 120);
    });
  }

  window.V2Forecast = {
    refresh: function (queryString, isVolume) {
      if (typeof isVolume === 'boolean') state.isVolume = isVolume;
      var q = typeof queryString === 'string' ? queryString : buildCurrentQuery();
      clearTimeout(state.prefetchTimer);
      if (isForecastTabVisible()) {
        fetchForecast(q, false);
      } else {
        state.pendingQuery = q;
      }
    },
    prefetchAfterKpi: function (queryString) {
      var q = typeof queryString === 'string' ? queryString : (state.pendingQuery !== null ? state.pendingQuery : buildCurrentQuery());
      if (state.payload && state.lastQuery === q) return;
      clearTimeout(state.prefetchTimer);
      state.prefetchTimer = setTimeout(function () {
        fetchForecast(q, false);
      }, 1500);
    },
    onTabActivated: function () {
      var gt = $('#toggleValVol');
      if (gt) state.isVolume = !!gt.checked;
      clearTimeout(state.prefetchTimer);
      var q = state.pendingQuery !== null ? state.pendingQuery : buildCurrentQuery();
      if (!state.payload || state.lastQuery !== q) {
        fetchForecast(q, false);
      } else {
        renderAll();
      }
    }
  };

  bindEvents();
})();
