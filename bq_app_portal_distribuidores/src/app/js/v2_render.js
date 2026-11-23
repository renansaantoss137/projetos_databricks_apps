/* ==========================================================================
   Portal Distribuidores v2 — camada de renderização (somente apresentação)
   Carregado DEPOIS de kpi_distribuidores.js e substitui as funções globais de
   desenho abaixo. Recebem exatamente os mesmos dados/argumentos; os cálculos de
   negócio (somas, % de atingimento, regularidade, média diária) são idênticos.
   Mudanças de apresentação deliberadas (aprovadas no brief):
     - meta = 0/nula -> estado neutro "Sem meta cadastrada" (antes: "+100%" / "100%")
     - escala de atingimento: >=100% sucesso, 90–99% alerta, <90% perigo
   ========================================================================== */
'use strict';

var V2 = window.V2 || (window.V2 = {});
V2.ATT_GOOD = 100;
V2.ATT_WARN = 90;

V2.attClass = function (pct, hasMeta) {
  if (!hasMeta) return 'att-none';
  if (pct >= V2.ATT_GOOD) return 'att-good';
  if (pct >= V2.ATT_WARN) return 'att-warn';
  return 'att-bad';
};

V2.icon = function (name, size) {
  var s = size || 16;
  var p = {
    'arrow-up': '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
    'arrow-down': '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    'minus': '<path d="M5 12h14"/>',
    'check': '<path d="M20 6 9 17l-5-5"/>',
    'info': '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    'x': '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    'moon': '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    'calendar': '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    'alert': '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
    'refresh': '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    'inbox': '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>'
  }[name] || '';
  return '<svg class="ico" width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + p + '</svg>';
};

/* Tooltip rico compartilhado (hover, foco e toque) */
V2.tipHtml = function (title, rows, foot) {
  var h = '<div class="tip-h">' + Fmt.esc(title) + '</div>';
  rows.forEach(function (r) {
    h += '<div class="tip-r"><span>' + Fmt.esc(r[0]) + '</span><strong' + (r[2] ? ' class="' + r[2] + '"' : '') + '>' + Fmt.esc(r[1]) + '</strong></div>';
  });
  if (foot) h += '<div class="tip-f">' + Fmt.esc(foot) + '</div>';
  return h;
};

(function initTooltip() {
  var tip = null, owner = null, shownAt = 0;
  function ensure() {
    if (tip) return tip;
    tip = document.createElement('div');
    tip.id = 'v2-tip';
    tip.className = 'v2-tip';
    tip.setAttribute('role', 'tooltip');
    tip.hidden = true;
    document.body.appendChild(tip);
    return tip;
  }
  function show(el) {
    var html = el.getAttribute('data-tip');
    if (!html) return;
    ensure();
    if (owner !== el || tip.hidden) shownAt = Date.now();
    owner = el;
    tip.innerHTML = html;
    tip.hidden = false;
    // Coordenadas em px da janela; com ajuste à tela (zoom no body) converte para px do layout
    var z = window.v2Zoom ? window.v2Zoom() : 1;
    var r = el.getBoundingClientRect();
    var tw = tip.offsetWidth * z, th = tip.offsetHeight * z;
    var x = r.left + r.width / 2 - tw / 2;
    x = Math.max(8, Math.min(x, window.innerWidth - tw - 8));
    var y = r.top - th - 10;
    if (y < 8) y = r.bottom + 10;
    tip.style.transform = 'translate(' + Math.round(x / z) + 'px,' + Math.round((y + window.scrollY) / z) + 'px)';
    el.setAttribute('aria-describedby', 'v2-tip');
  }
  function hide() {
    if (tip) tip.hidden = true;
    if (owner) owner.removeAttribute('aria-describedby');
    owner = null;
  }
  document.addEventListener('mouseover', function (e) {
    var el = e.target.closest && e.target.closest('[data-tip]');
    if (el) show(el); else if (owner && !(e.target.closest && e.target.closest('#v2-tip'))) hide();
  });
  document.addEventListener('focusin', function (e) {
    var el = e.target.closest && e.target.closest('[data-tip]');
    if (el) show(el); else hide();
  });
  document.addEventListener('click', function (e) {
    var el = e.target.closest && e.target.closest('[data-tip]');
    // No toque, o navegador dispara mouseover (abre) e logo depois click: esse click não pode fechar.
    if (el) { if (owner === el && tip && !tip.hidden && Date.now() - shownAt > 500) hide(); else show(el); }
    else hide();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') hide(); });
  window.addEventListener('scroll', hide, { passive: true });
  window.addEventListener('resize', hide);
})();

function v2SelectedMonthIdx() {
  var m = getSafeSelectedValues('select-mes');
  if (m.length === 1) { var x = parseInt(m[0], 10); if (x >= 1 && x <= 12) return x - 1; }
  return -1;
}

function v2MaxMonthIdx(a, b) {
  var now = new Date();
  var anoFilter = getSafeSelectedValues('select-ano');
  var selectedYear = (anoFilter.length === 1 && !isNaN(parseInt(anoFilter[0]))) ? parseInt(anoFilter[0]) : null;
  if (!selectedYear || selectedYear >= now.getFullYear()) return now.getMonth();
  for (var m = 11; m >= 0; m--) { if ((a[m] && a[m] > 0) || (b[m] && b[m] > 0)) return m; }
  return 11;
}

/* Componente: barras de realizado + marcador de meta (IBCS) + linha de atingimento */
function v2TargetBars(opts) {
  var vals = opts.values, tgts = opts.targets, maxIdx = opts.maxIdx;
  var visV = vals.slice(0, maxIdx + 1), visT = tgts.slice(0, maxIdx + 1);
  var maxVal = Math.max.apply(null, visV.concat(visT).concat([1]));
  var top = maxVal * 1.15;
  var sel = v2SelectedMonthIdx();
  var hi = (sel >= 0 && sel <= maxIdx) ? sel : maxIdx;
  var cols = '';
  var summary = [];
  for (var i = 0; i <= maxIdx; i++) {
    var v = vals[i] || 0, t = tgts[i] || 0;
    var hasMeta = t > 0;
    var pct = hasMeta ? Math.round((v / t) * 100) : null;
    var cls = V2.attClass(pct, hasMeta);
    var h = Math.min(100, (v / top) * 100);
    var ht = Math.min(100, (t / top) * 100);
    var mName = Fmt.MONTHS_SHORT[i], mLong = Fmt.MONTHS_LONG[i];
    var vStr = opts.fmt(v), tStr = hasMeta ? opts.fmt(t) : 'Sem meta cadastrada';
    var rows = [[opts.realLabel, vStr], ['Meta', tStr]];
    if (hasMeta) {
      rows.push(['Atingimento', Fmt.pct(pct), cls]);
      rows.push(['Diferença', (v - t >= 0 ? '+' : '−') + opts.fmt(Math.abs(v - t)), v >= t ? 'att-good' : 'att-bad']);
    }
    var aria = mLong + ': ' + opts.realLabel.toLowerCase() + ' ' + vStr + ', meta ' + tStr + (hasMeta ? ', ' + pct + '% de atingimento' : '');
    summary.push(aria);
    cols += '<button type="button" class="tc-col' + (i === hi ? ' is-current' : '') + (i < maxIdx - 5 ? ' is-older' : '') + '" aria-label="' + Fmt.esc(aria) + '" data-tip="' + Fmt.esc(V2.tipHtml(mLong, rows)) + '">' +
      '<span class="tc-plot">' +
        (i === hi && v > 0 ? '<span class="tc-val" style="bottom:calc(' + h.toFixed(1) + '% + 6px)">' + Fmt.esc(opts.fmt(v)) + '</span>' : '') +
        '<span class="tc-bar" style="height:' + h.toFixed(1) + '%"></span>' +
        (hasMeta ? '<span class="tc-target" style="bottom:' + ht.toFixed(1) + '%"></span>' : '') +
      '</span>' +
      '<span class="tc-month">' + mName + '</span>' +
      '<span class="tc-att ' + cls + '">' + (hasMeta ? Fmt.pct(pct) : '—') + '</span>' +
    '</button>';
  }
  return '<div class="tc" style="--cols:' + (maxIdx + 1) + '">' + cols + '</div>' +
    '<p class="sr-only">' + Fmt.esc(opts.title + '. ' + summary.join('; ') + '.') + '</p>';
}

function v2SetBadge(el, sumReal, sumMeta, tipPrefix, fmt) {
  if (!el) return;
  var pill = el.parentElement && el.parentElement.classList.contains('chart-kpi-pill') ? el.parentElement : null;
  var tip;
  if (sumMeta > 0) {
    var diffPct = ((sumReal - sumMeta) / sumMeta) * 100;
    var up = diffPct >= 0;
    el.className = up ? 'badge-up' : 'badge-down';
    el.innerHTML = V2.icon(up ? 'arrow-up' : 'arrow-down', 12) + '<span>' + (up ? '+' : '−') + Fmt.pct(Math.abs(diffPct), 1) + '</span>';
    tip = tipPrefix + ': realizado ' + fmt(sumReal) + ' vs meta ' + fmt(sumMeta) + ' (' + (up ? '+' : '−') + Fmt.pct(Math.abs(diffPct), 1) + ')';
  } else {
    el.className = 'badge-neutral';
    el.innerHTML = '<span>Sem meta</span>';
    tip = sumReal > 0 ? tipPrefix + ': realizado ' + fmt(sumReal) + ' (sem meta cadastrada)' : tipPrefix + ': sem movimentação no período';
  }
  el.title = tip;
  if (pill) { pill.title = tip; pill.setAttribute('aria-label', tip); }
}

/* ── Realizado vs Meta (Sell-in / Sell-out) ── */
function buildBarChart(monthlyIn, monthlyOut, isVolume, monthlyMetaOut, monthlyMetaIn) {
  var container = document.getElementById('barChart');
  if (!container) return;
  if (monthlyIn && monthlyIn.length === 12) lastMonthlyIn = monthlyIn;
  if (monthlyOut && monthlyOut.length === 12) lastMonthlyOut = monthlyOut;
  if (monthlyMetaIn && monthlyMetaIn.length === 12) lastMonthlyMetaIn = monthlyMetaIn;
  if (monthlyMetaOut && monthlyMetaOut.length === 12) lastMonthlyMetaOut = monthlyMetaOut;
  if (typeof isVolume === 'boolean') lastIsVolume = isVolume;

  var chartToggle = document.getElementById('toggleChartMode');
  var isOut = chartToggle ? chartToggle.checked : (lastChartMode === 'sellout');
  lastChartMode = isOut ? 'sellout' : 'sellin';
  var lblIn = document.getElementById('lbl-chart-sellin'), lblOut = document.getElementById('lbl-chart-sellout');
  if (lblIn && lblOut) {
    lblIn.classList.toggle('active-label', !isOut); lblOut.classList.toggle('active-label', isOut);
    lblIn.setAttribute('aria-checked', String(!isOut)); lblOut.setAttribute('aria-checked', String(isOut));
  }
  var metric = isOut ? 'Sell-out' : 'Sell-in';
  var titleEl = document.getElementById('chart-title-text');
  if (titleEl) titleEl.textContent = metric + ' vs meta';
  var legR = document.getElementById('chart-leg-lbl-realized');
  if (legR) legR.textContent = metric + ' realizado';

  var real = isOut ? (lastMonthlyOut && lastMonthlyOut.length === 12 ? lastMonthlyOut : Array(12).fill(0))
                   : (lastMonthlyIn && lastMonthlyIn.length === 12 ? lastMonthlyIn : Array(12).fill(0));
  var meta = isOut ? (lastMonthlyMetaOut && lastMonthlyMetaOut.length === 12 ? lastMonthlyMetaOut : Array(12).fill(0))
                   : (lastMonthlyMetaIn && lastMonthlyMetaIn.length === 12 ? lastMonthlyMetaIn : Array(12).fill(0));
  var useVol = lastIsVolume;
  var fmt = function (v) { return useVol ? Fmt.compact(v) : Fmt.moneyCompact(v); };
  var maxIdx = v2MaxMonthIdx(real, meta);

  var sumR = real.slice(0, maxIdx + 1).reduce(function (a, b) { return a + b; }, 0);
  var sumM = meta.slice(0, maxIdx + 1).reduce(function (a, b) { return a + b; }, 0);
  v2SetBadge(document.getElementById('chart-diff-badge'), sumR, sumM, metric + ' acumulado vs meta', fmt);

  container.innerHTML = v2TargetBars({
    values: real, targets: meta, maxIdx: maxIdx, fmt: fmt, realLabel: 'Realizado',
    title: 'Gráfico ' + metric + ' realizado versus meta por mês'
  });
  container.setAttribute('aria-busy', 'false');
}

/* ── Positivação: positivados vs meta + ticket médio (small multiple) ── */
function buildPositivChart(monthlyPositiv, monthlyPositivPct, totalBaseClientes, monthlyPositivMeta, monthlyTicketMedio) {
  var container = document.getElementById('positivChart');
  if (!container) return;
  if (monthlyPositiv && monthlyPositiv.length === 12) lastMonthlyPositiv = monthlyPositiv;
  if (monthlyPositivPct && monthlyPositivPct.length === 12) lastMonthlyPositivPct = monthlyPositivPct;
  if (monthlyPositivMeta && monthlyPositivMeta.length === 12) lastMonthlyPositivMeta = monthlyPositivMeta;
  if (monthlyTicketMedio && monthlyTicketMedio.length === 12) lastMonthlyTicketMedio = monthlyTicketMedio;
  if (typeof totalBaseClientes === 'number' && totalBaseClientes > 0) lastTotalBaseClientes = totalBaseClientes;

  var arr = lastMonthlyPositiv && lastMonthlyPositiv.length === 12 ? lastMonthlyPositiv : Array(12).fill(0);
  var arrMeta = lastMonthlyPositivMeta && lastMonthlyPositivMeta.length === 12 ? lastMonthlyPositivMeta : Array(12).fill(0);
  var arrTicket = lastMonthlyTicketMedio && lastMonthlyTicketMedio.length === 12 ? lastMonthlyTicketMedio : Array(12).fill(0);
  var maxIdx = v2MaxMonthIdx(arr, arrMeta);
  var fmtCli = function (v) { return Fmt.int(v) + ' clientes'; };

  var sumR = arr.slice(0, maxIdx + 1).reduce(function (a, b) { return a + b; }, 0);
  var sumM = arrMeta.slice(0, maxIdx + 1).reduce(function (a, b) { return a + b; }, 0);
  v2SetBadge(document.getElementById('positiv-chart-badge'), sumR, sumM, 'Acumulado no ano', fmtCli);

  var bars = v2TargetBars({
    values: arr, targets: arrMeta, maxIdx: maxIdx, fmt: function (v) { return Fmt.int(v); }, realLabel: 'Positivados',
    title: 'Gráfico de clientes positivados versus meta por mês'
  });

  /* Ticket médio (Valor) ou venda média em DZ (Volume): linha compacta alinhada aos mesmos meses */
  var tVol = !!window.__v2TicketVolume;
  var tName = tVol ? 'Venda média' : 'Ticket médio';
  var tFull = function (t) { return tVol ? Fmt.compact(t) + ' DZ' : Fmt.moneyCompact(t); };
  var tLong = function (t) { return tVol ? Fmt.int(t) + ' DZ' : Fmt.money(t); };
  var legLine = document.querySelector('#positivChart') && document.querySelector('#positivChart').closest('section');
  legLine = legLine ? legLine.querySelector('.lg-line') : null;
  if (legLine && legLine.parentElement) legLine.parentElement.lastChild.textContent = tName;
  var vis = arrTicket.slice(0, maxIdx + 1);
  var valid = vis.filter(function (t) { return typeof t === 'number' && t > 0; });
  var tline = '';
  if (valid.length) {
    var mn = Math.min.apply(null, valid), mx = Math.max.apply(null, valid);
    var span = mx > mn ? mx - mn : (mx * 0.4 || 1);
    var lo = Math.max(0, mn - span * 0.2), hiV = mx + span * 0.2;
    var y = function (t) { return t > 0 ? 34 - ((t - lo) / (hiV - lo)) * 26 : null; };
    var sel = v2SelectedMonthIdx();
    var cur = (sel >= 0 && sel <= maxIdx) ? sel : maxIdx;
    // Curva suave monotônica (Fritsch–Carlson): passa pelos valores sem criar picos falsos.
    // Cada mês ocupa 100 unidades com o ponto no centro (x=50); cada trecho entre dois meses é uma
    // Bézier cúbica dividida ao meio, e cada célula desenha a metade que lhe cabe.
    var ys = [];
    for (var k = 0; k <= maxIdx; k++) ys.push(y(arrTicket[k] || 0));
    var dk = [], mk = [];
    for (k = 0; k < maxIdx; k++) dk.push(ys[k] !== null && ys[k + 1] !== null ? (ys[k + 1] - ys[k]) / 100 : null);
    for (k = 0; k <= maxIdx; k++) {
      var a = k > 0 ? dk[k - 1] : null, b = k < maxIdx ? dk[k] : null;
      mk.push(a === null ? (b === null ? 0 : b) : b === null ? a : (a * b <= 0 ? 0 : (a + b) / 2));
    }
    function halves(k) { // trecho k → k+1 dividido em t=0,5: [metade esquerda, metade direita], y apenas (x é linear)
      var b0 = ys[k], b3 = ys[k + 1], b1 = b0 + mk[k] * 100 / 3, b2 = b3 - mk[k + 1] * 100 / 3;
      var mid = (b0 + 3 * b1 + 3 * b2 + b3) / 8;
      return [[b0, (b0 + b1) / 2, (b0 + 2 * b1 + b2) / 4, mid], [mid, (b1 + 2 * b2 + b3) / 4, (b2 + b3) / 2, b3]];
    }
    // Celular: rótulo só com o número; a unidade vai para o título (R$ mil quando o ticket passa de mil)
    var tDiv = mx >= 1000 ? 1000 : 1, tUnit = tVol ? (tDiv === 1000 ? 'mil DZ' : 'DZ') : (tDiv === 1000 ? 'R$ mil' : 'R$');
    var cells = '', sum = [];
    for (var i = 0; i <= maxIdx; i++) {
      var t = arrTicket[i] || 0, yc = ys[i];
      var path = '';
      if (yc !== null) {
        if (i > 0 && dk[i - 1] !== null) { var r = halves(i - 1)[1]; path += '<path d="M0 ' + r[0].toFixed(1) + ' C16.7 ' + r[1].toFixed(1) + ' 33.3 ' + r[2].toFixed(1) + ' 50 ' + r[3].toFixed(1) + '"/>'; }
        if (i < maxIdx && dk[i] !== null) { var l = halves(i)[0]; path += '<path d="M50 ' + l[0].toFixed(1) + ' C66.7 ' + l[1].toFixed(1) + ' 83.3 ' + l[2].toFixed(1) + ' 100 ' + l[3].toFixed(1) + '"/>'; }
      }
      var lbl = t > 0 ? Fmt.esc(tFull(t)) : '—';
      var lblShort = t > 0 ? (t / tDiv).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) : '—';
      if (t > 0) sum.push(Fmt.MONTHS_LONG[i] + ' ' + tLong(t));
      cells += '<div class="tl-cell' + (i === cur ? ' is-current' : '') + (i < maxIdx - 5 ? ' is-older' : '') + '" data-tip="' + Fmt.esc(V2.tipHtml(Fmt.MONTHS_LONG[i], [[tName, t > 0 ? tLong(t) : 'Sem dado']], tVol ? 'Volume (DZ) por cliente positivado' : 'Por cliente positivado')) + '" tabindex="0">' +
        '<svg viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true">' + path + '</svg>' +
        '<span class="tl-lbl"><span class="tl-full">' + lbl + '</span><span class="tl-short">' + lblShort + '</span></span></div>';
    }
    tline = '<div class="tl"><div class="tl-title">' + tName + ' por cliente positivado<span class="tl-unit"> (' + tUnit + ')</span></div>' +
      '<div class="tl-row" style="--cols:' + (maxIdx + 1) + '">' + cells + '</div>' +
      '<p class="sr-only">' + tName + ' mensal: ' + Fmt.esc(sum.join('; ')) + '.</p></div>';
  }
  container.innerHTML = bars + tline;
  container.setAttribute('aria-busy', 'false');
}

/* Valor completo dos indicadores, sem abreviação de milhar. */
V2.fullNumber = function (value, isVolume) {
  var n = Number(value);
  if (!Number.isFinite(n)) return 'Sem dado';
  return isVolume
    ? new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n) + ' DZ'
    : Fmt.money(n);
};
V2.metricTip = function (el, label, value, isVolume) {
  if (!el) return;
  el.setAttribute('data-tip', V2.tipHtml(label, [['Valor completo', V2.fullNumber(value, isVolume)]]));
  el.setAttribute('tabindex', '0');
};

/* ── Cards de meta (Sell-in / Sell-out) ── */
function updateCardGaugeAndDiff(cardClass, diffElemId, vlRealized, vlTarget, formatNumber, isVolume) {
  var card = document.querySelector('.' + cardClass);
  if (!card) return;
  var valEl = card.querySelector('.card-kpi-val');
  var tgtEl = card.querySelector('.kpi-target-line');
  var fill = card.querySelector('.kpi-progress-fill');
  var bar = card.querySelector('.kpi-progress');
  var pctTxt = card.querySelector('.gauge-pct-txt');
  var diffEl = document.getElementById(diffElemId);
  if (valEl) valEl.textContent = formatNumber(vlRealized);
  V2.metricTip(valEl, cardClass === 'card-sellin' ? 'Sell-in' : 'Sell-out', vlRealized, isVolume);

  if (!(vlTarget > 0)) {
    card.classList.add('is-no-meta');
    if (tgtEl) { tgtEl.textContent = 'Sem meta cadastrada'; tgtEl.removeAttribute('data-tip'); tgtEl.removeAttribute('tabindex'); }
    if (fill) { fill.style.width = '0%'; fill.className = 'kpi-progress-fill att-none'; }
    if (bar) { bar.setAttribute('aria-valuenow', '0'); bar.setAttribute('aria-valuetext', 'Sem meta cadastrada'); }
    if (pctTxt) { pctTxt.textContent = ''; pctTxt.className = 'gauge-pct-txt'; }
    card.style.setProperty('--att', '0%');
    if (diffEl) { diffEl.removeAttribute('data-tip'); diffEl.removeAttribute('tabindex'); diffEl.className = 'kpi-diff-box delta delta-neutral'; diffEl.innerHTML = V2.icon('minus', 14) + '<span>Sem meta para comparar</span>'; }
    return;
  }
  card.classList.remove('is-no-meta');
  var pctInt = Math.round((vlRealized / vlTarget) * 100);
  var above = vlRealized >= vlTarget;
  var absDiff = Math.abs(vlRealized - vlTarget);
  var diffPct = above ? pctInt - 100 : 100 - pctInt;
  var cls = V2.attClass(pctInt, true);
  if (tgtEl) tgtEl.innerHTML = '<span class="kpi-target-k">Meta</span> de ' + Fmt.esc(formatNumber(vlTarget));
  V2.metricTip(tgtEl, 'Meta', vlTarget, isVolume);
  if (fill) { fill.style.width = Math.min(100, Math.max(0, pctInt)) + '%'; fill.className = 'kpi-progress-fill ' + cls; }
  if (bar) { bar.setAttribute('aria-valuenow', String(pctInt)); bar.setAttribute('aria-valuetext', pctInt + '% da meta atingido'); }
  card.style.setProperty('--att', Math.min(100, Math.max(0, pctInt)) + '%');
  if (pctTxt) {
    pctTxt.className = 'gauge-pct-txt ' + cls;
    pctTxt.innerHTML = '<strong>' + Fmt.esc(Fmt.pct(pctInt)) + '</strong><span class="sr-only"> da meta atingido</span>';
  }
  if (diffEl) {
    V2.metricTip(diffEl, 'Diferença para a meta', vlRealized - vlTarget, isVolume);
    diffEl.className = 'kpi-diff-box delta ' + (above ? 'delta-pos' : 'delta-neg');
    diffEl.innerHTML = V2.icon(above ? 'arrow-up' : 'arrow-down', 14) +
      '<span class="sr-only">' + (above ? 'Acima da meta em' : 'Abaixo da meta em') + '</span>' +
      '<span>' + (above ? '+' : '−') + formatNumber(absDiff) + '</span>' +
      '<span class="delta-pct">(' + (above ? '+' : '−') + diffPct + '%)</span>';
  }
}

/* ── Vs. ano anterior (Sell-in / Sell-out) ──
   Compara o realizado do período filtrado com os mesmos meses do ano anterior, limitado à mesma
   data de um ano atrás (mês corrente compara parcial com parcial). */
function _fmtBrDate(iso) {
  if (!iso || String(iso).length < 10) return '';
  var p = String(iso).slice(0, 10).split('-');
  return p.length === 3 ? (p[2] + '/' + p[1] + '/' + p[0]) : iso;
}

function updateCardYoY(cardClass, vlCur, vlPy, hasPy, formatNumber, isVolume, pyMeta) {
  var card = document.querySelector('.' + cardClass);
  if (!card) return;
  var el = card.querySelector('.kpi-yoy');
  if (!el) {
    el = document.createElement('div');
    el.className = 'kpi-yoy';
    var tgt = card.querySelector('.kpi-target-line');
    if (tgt) tgt.insertAdjacentElement('afterend', el); else card.appendChild(el);
  }
  var anoSel = getSafeSelectedValues('select-ano');
  var pyLbl = anoSel.length === 1 && !isNaN(parseInt(anoSel[0], 10)) ? String(parseInt(anoSel[0], 10) - 1) : 'ano anterior';
  var hasBdays = pyMeta && pyMeta.cur_bdays > 0 && pyMeta.py_cutoff_dt;
  var tipNote = hasBdays
    ? ('Mesmos ' + pyMeta.cur_bdays + ' dias úteis do ano anterior (até ' + _fmtBrDate(pyMeta.py_cutoff_dt) + ').')
    : 'Mesmos meses do ano anterior, ajustado por dias úteis.';
  if (!hasPy) {
    el.className = 'kpi-yoy is-empty';
    el.innerHTML = '<span class="kpi-yoy-k">Vs. ano anterior</span><span class="kpi-yoy-v">selecione um ano</span>';
    el.removeAttribute('data-tip');
    return;
  }
  if (!(vlPy > 0)) {
    el.className = 'kpi-yoy is-empty';
    el.innerHTML = '<span class="kpi-yoy-k">Vs. ' + Fmt.esc(pyLbl) + '</span><span class="kpi-yoy-v">sem dado no ano anterior</span>';
    el.setAttribute('data-tip', V2.tipHtml('Vs. ano anterior', [['Realizado atual', V2.fullNumber(vlCur, isVolume)], [pyLbl, 'Sem dado na base']], tipNote));
    el.setAttribute('tabindex', '0');
    return;
  }
  var pct = ((vlCur - vlPy) / vlPy) * 100;
  var up = pct >= 0;
  el.className = 'kpi-yoy ' + (up ? 'is-up' : 'is-down');
  el.innerHTML = '<span class="kpi-yoy-k">Vs. ' + Fmt.esc(pyLbl) + '</span>' +
    '<strong class="kpi-yoy-v">' + V2.icon(up ? 'arrow-up' : 'arrow-down', 12) + (up ? '+' : '−') + Fmt.esc(Fmt.pct(Math.abs(pct), 1)) + '</strong>' +
    '<span class="kpi-yoy-b">' + Fmt.esc(formatNumber(vlPy)) + '</span>';
  el.setAttribute('tabindex', '0');
  el.setAttribute('data-tip', V2.tipHtml('Vs. ano anterior (dias úteis)', [
    ['Base ' + pyLbl, V2.fullNumber(vlPy, isVolume)]
  ], tipNote));
}

/* ── Qualidade da Receita: Mix por Linha & Preço Médio (R$/DZ) ── */
function renderMixQualityCard(mixRows) {
  var titleEl = document.getElementById('mix-insight-title');
  var priceEl = document.getElementById('mix-avg-price-val');
  var badgeEl = document.getElementById('mix-avg-price-badge');
  var wrapEl = document.getElementById('mix-bars-wrap');
  if (!wrapEl) return;

  var rows = Array.isArray(mixRows) ? mixRows.filter(function (r) {
    return (parseFloat(r.vl_atual) || 0) > 0 || (parseFloat(r.vl_py) || 0) > 0;
  }) : [];
  if (!rows.length) {
    if (titleEl) titleEl.textContent = 'Qualidade da receita — Mix & Preço Médio';
    if (priceEl) priceEl.textContent = '--';
    if (badgeEl) { badgeEl.className = 'badge-neutral'; badgeEl.textContent = '—'; }
    wrapEl.innerHTML = '<div class="v2-empty sm"><p>Sem dados de mix no período selecionado.</p></div>';
    return;
  }

  var totVl = 0, totDz = 0, totVlPy = 0, totDzPy = 0;
  rows.forEach(function (r) {
    totVl += parseFloat(r.vl_atual) || 0;
    totDz += parseFloat(r.dz_atual) || 0;
    totVlPy += parseFloat(r.vl_py) || 0;
    totDzPy += parseFloat(r.dz_py) || 0;
  });

  var avgPrice = totDz > 0 ? (totVl / totDz) : 0;
  var avgPricePy = totDzPy > 0 ? (totVlPy / totDzPy) : 0;
  var priceDiffPct = (avgPrice > 0 && avgPricePy > 0) ? ((avgPrice - avgPricePy) / avgPricePy) * 100 : null;

  if (priceEl) priceEl.textContent = avgPrice > 0 ? (Fmt.money(avgPrice) + '/DZ') : '--';
  if (badgeEl) {
    if (priceDiffPct === null) {
      badgeEl.className = 'badge-neutral';
      badgeEl.textContent = 'sem base ant.';
    } else {
      var up = priceDiffPct >= 0;
      badgeEl.className = up ? 'badge-up' : 'badge-down';
      badgeEl.innerHTML = V2.icon(up ? 'arrow-up' : 'arrow-down', 11) + Fmt.esc((up ? '+' : '−') + Fmt.pct(Math.abs(priceDiffPct), 1));
    }
  }

  var fmtPp = function (val) {
    return new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(val) + ' p.p.';
  };
  var briocheRow = rows.filter(function (r) { return String(r.segmento || '').indexOf('Brioche') >= 0; })[0];
  var briocheShare = (briocheRow && totVl > 0) ? ((parseFloat(briocheRow.vl_atual) || 0) / totVl) * 100 : 0;
  var briocheSharePy = (briocheRow && totVlPy > 0) ? ((parseFloat(briocheRow.vl_py) || 0) / totVlPy) * 100 : null;
  if (titleEl) {
    if (briocheShare > 0 && priceDiffPct !== null) {
      var pp = briocheSharePy !== null ? (briocheShare - briocheSharePy) : null;
      var ppTxt = pp !== null ? (' (' + (pp >= 0 ? '+' : '−') + fmtPp(Math.abs(pp)) + ' vs ano ant.)') : '';
      titleEl.textContent = 'Brioche & Gourmet representa ' + Fmt.pct(briocheShare, 0) + ' da receita' + ppTxt;
    } else if (briocheShare > 0) {
      titleEl.textContent = 'Brioche & Gourmet responde por ' + Fmt.pct(briocheShare, 0) + ' da receita de Sell-out';
    } else {
      titleEl.textContent = 'Qualidade da receita — Mix & Preço Médio';
    }
  }

  rows.sort(function (a, b) { return (parseFloat(b.vl_atual) || 0) - (parseFloat(a.vl_atual) || 0); });
  wrapEl.innerHTML = rows.map(function (r) {
    var vl = parseFloat(r.vl_atual) || 0;
    var dz = parseFloat(r.dz_atual) || 0;
    var vlPy = parseFloat(r.vl_py) || 0;
    var dzPy = parseFloat(r.dz_py) || 0;
    var sh = totVl > 0 ? (vl / totVl) * 100 : 0;
    var shPy = totVlPy > 0 ? (vlPy / totVlPy) * 100 : null;
    var ppDiff = shPy !== null ? (sh - shPy) : null;
    var pr = dz > 0 ? (vl / dz) : 0;
    var prPy = dzPy > 0 ? (vlPy / dzPy) : 0;
    var isFocus = String(r.segmento || '').indexOf('Brioche') >= 0;
    var ppHtml = ppDiff === null ? '' : (
      '<span class="mix-pp ' + (ppDiff >= 0 ? 'att-good' : 'att-bad') + '">' +
        (ppDiff >= 0 ? '+' : '−') + fmtPp(Math.abs(ppDiff)) +
      '</span>'
    );
    var tip = V2.tipHtml(r.segmento || 'Linha', [
      ['Volume', Fmt.int(Math.round(dz)) + ' DZ'],
      ['Preço médio atual', pr > 0 ? Fmt.money(pr) + '/DZ' : '—'],
      ['Preço médio ano ant.', prPy > 0 ? Fmt.money(prPy) + '/DZ' : '—']
    ], '% Receita = linha ÷ total · p.p. compara mesma base de dias úteis do ano anterior.');

    return '<div class="mix-row' + (isFocus ? ' is-focus' : '') + '" tabindex="0" data-tip="' + Fmt.esc(tip) + '">' +
      '<div class="mix-row-label">' +
        '<span class="mix-seg-name">' + Fmt.esc(r.segmento || '-') + '</span>' +
        '<span class="mix-seg-price">' + (pr > 0 ? Fmt.esc(Fmt.money(pr)) + '/DZ' : '—') + '</span>' +
      '</div>' +
      '<div class="mix-bar-track" aria-hidden="true">' +
        '<span class="mix-bar-fill' + (isFocus ? ' is-focus' : '') + '" style="width:' + Math.max(2, Math.round(sh)) + '%"></span>' +
      '</div>' +
      '<div class="mix-row-nums">' +
        '<strong class="mix-share">' + Fmt.esc(Fmt.pct(sh, 1)) + '</strong>' +
        '<span class="mix-vl">' + Fmt.esc(Fmt.moneyCompact(vl)) + '</span>' +
        ppHtml +
      '</div>' +
    '</div>';
  }).join('');
}

/* ── Indicador de carregamento visível ao filtrar ──
   Além da barra fina no topo: aviso flutuante centralizado com spinner e barra animada no topo de cada card. */
function showFilterUpdatingIndicator() {
  var bar = document.getElementById('filter-loading-bar');
  if (!bar) { bar = document.createElement('div'); bar.id = 'filter-loading-bar'; bar.className = 'filter-loading-bar'; document.body.appendChild(bar); }
  bar.classList.add('active');
  var t = document.getElementById('v2-loading-toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'v2-loading-toast';
    t.className = 'v2-loading-toast';
    t.setAttribute('role', 'status');
    t.setAttribute('aria-live', 'polite');
    t.innerHTML = '<span class="v2-spin" aria-hidden="true"></span><span class="v2-loading-txt">Atualizando indicadores…</span><span class="v2-loading-track" aria-hidden="true"><span></span></span>';
    document.body.appendChild(t);
  }
  clearTimeout(window.__v2LoadHideT);
  t.hidden = false;
  requestAnimationFrame(function () { t.classList.add('is-on'); });
  document.body.classList.add('v2-refreshing');
  var grid = document.querySelector('.kpi-grid');
  if (grid) grid.classList.add('is-refreshing');
}
function hideFilterUpdatingIndicator() {
  var bar = document.getElementById('filter-loading-bar');
  if (bar) bar.classList.remove('active');
  var t = document.getElementById('v2-loading-toast');
  if (t) { t.classList.remove('is-on'); window.__v2LoadHideT = setTimeout(function () { t.hidden = true; }, 220); }
  document.body.classList.remove('v2-refreshing');
  var grid = document.querySelector('.kpi-grid');
  if (grid) grid.classList.remove('is-refreshing');
}

/* ── Ritmo vs meta ──
   Meta do mês distribuída igualmente pelos dias úteis (seg a sex; sábado e domingo não contam).
   Meta proporcional = Σ meta do mês × (dias úteis até ontem ÷ dias úteis do mês). A base é carregada
   com as vendas até o dia anterior (D-1), por isso o corte é ontem. Mês passado entra inteiro; futuro, zero. */
function v2BizDays(y, m, upto) {
  var n = 0;
  for (var day = 1; day <= upto; day++) { var w = new Date(y, m, day).getDay(); if (w !== 0 && w !== 6) n++; }
  return n;
}
function v2RowNum(row, key) {
  for (var k in row) { if (k.toLowerCase() === key) { var v = parseFloat(row[k]); return isNaN(v) ? 0 : v; } }
  return 0;
}
function v2PaceTarget(rows, metaKey) {
  var cut = new Date(); cut.setHours(0, 0, 0, 0); cut.setDate(cut.getDate() - 1);
  var cy = cut.getFullYear(), cm = cut.getMonth();
  var out = { meta: 0, pace: 0, open: false, done: 0, total: 0, cut: cut };
  (rows || []).forEach(function (r) {
    var meta = v2RowNum(r, metaKey);
    var y = parseInt(r.ANO || r.ano, 10), m = parseInt(r.MES || r.mes, 10) - 1;
    if (!(meta > 0) || isNaN(y) || isNaN(m)) return;
    var last = new Date(y, m + 1, 0).getDate();
    var total = v2BizDays(y, m, last), frac;
    if (y < cy || (y === cy && m < cm)) frac = 1;
    else if (y > cy || m > cm) frac = 0;
    else {
      var done = v2BizDays(y, m, cut.getDate());
      frac = total ? done / total : 0;
      if (frac > 0 && frac < 1) { out.open = true; out.done += done; out.total += total; }
    }
    out.meta += meta; out.pace += meta * frac;
  });
  return out;
}
function updateCardPace(cardClass, vlRealized, rows, metaKey, formatNumber) {
  var card = document.querySelector('.' + cardClass);
  if (!card) return;
  var row = card.querySelector('.kpi-pace'), mark = card.querySelector('.kpi-pace-mark'), lbl = card.querySelector('.kpi-pace-lbl');
  var bar = card.querySelector('.kpi-progress');
  var t = v2PaceTarget(rows, metaKey);
  if (!t.open || !(t.pace > 0)) {
    if (row) { row.hidden = true; row.removeAttribute('data-tip'); }
    if (mark) mark.hidden = true;
    if (lbl) lbl.hidden = true;
    card.classList.remove('has-pace');
    return;
  }
  var pct = Math.round((vlRealized / t.pace) * 100);
  var cls = V2.attClass(pct, true);
  var expected = Math.min(100, (t.pace / t.meta) * 100);
  var cutLbl = t.cut.getDate() + '/' + Fmt.MONTHS_SHORT[t.cut.getMonth()].toLowerCase();
  card.classList.add('has-pace');
  if (mark) { mark.hidden = false; mark.style.left = expected.toFixed(1) + '%'; }
  // Rótulo ancorado no marcador: termina nele na metade direita da barra, começa nele na esquerda
  if (lbl) {
    lbl.hidden = false; lbl.textContent = 'Esperado até ' + cutLbl;
    lbl.style.left = expected.toFixed(1) + '%';
    lbl.classList.toggle('is-left', expected < 50);
  }
  if (bar) bar.setAttribute('aria-valuetext', bar.getAttribute('aria-valuetext') + '; esperado até ' + cutLbl + ': ' + Math.round(expected) + '%');
  if (row) {
    row.hidden = false;
    row.innerHTML = '<span class="kpi-pace-k">Ritmo</span><strong class="kpi-pace-v ' + cls + '">' + Fmt.esc(Fmt.pct(pct)) + '</strong>' +
      '<span class="kpi-pace-t">do esperado · ' + Fmt.esc(formatNumber(t.pace)) + ' até ' + cutLbl + '</span>' +
      '<span class="kpi-pace-i" aria-hidden="true">' + V2.icon('info', 15) + '</span>';
    row.setAttribute('aria-label', 'Ritmo ' + pct + '% da meta proporcional até ' + cutLbl + '. Toque ou passe o mouse para ver como é calculado');
    row.setAttribute('role', 'button');
    row.setAttribute('data-tip', V2.tipHtml('Ritmo vs meta', [
      ['Dias úteis transcorridos', t.done + ' de ' + t.total],
      ['Meta por dia útil', formatNumber(t.meta / t.total)]
    ], 'Meta do mês dividida igualmente pelos dias úteis (seg a sex). Sábado e domingo não contam.'));
  }
}

/* ── Faturado / Carteira / Faturado + Carteira ── */
function updateOrderPipelineCards(orderMetrics, isVolume, formatNumber, vlSellIn) {
  if (vlSellIn === undefined) vlSellIn = null;
  var invEl = document.getElementById('kpi-invoiced-val');
  var openEl = document.getElementById('kpi-open-val');
  var totEl = document.getElementById('kpi-total-order-val');
  var descEl = document.getElementById('kpi-total-order-desc');
  function num(v) { var x = parseFloat(v); return isNaN(x) ? 0 : x; }
  var row = (orderMetrics && Array.isArray(orderMetrics) && orderMetrics.length > 0) ? orderMetrics[0]
          : (orderMetrics && !Array.isArray(orderMetrics) ? orderMetrics : {});
  var inv, open, tot, unit = isVolume ? ' DZ' : '';
  if (isVolume) {
    inv = (vlSellIn !== null && vlSellIn !== undefined) ? num(vlSellIn) : num(row.total_qty_invoiced_dz || row.TOTAL_QTY_INVOICED_DZ);
    open = num(row.total_qty_open_dz || row.TOTAL_QTY_OPEN_DZ);
  } else {
    inv = (vlSellIn !== null && vlSellIn !== undefined) ? num(vlSellIn) : num(row.total_vl_invoiced || row.TOTAL_VL_INVOICED);
    open = num(row.total_vl_open || row.TOTAL_VL_OPEN);
  }
  tot = inv + open;
  if (invEl) invEl.textContent = formatNumber(inv) + unit;
  if (openEl) openEl.textContent = open === 0 ? '—' : formatNumber(open) + unit;
  if (openEl) openEl.classList.toggle('is-empty', open === 0);
  if (totEl) totEl.textContent = formatNumber(tot) + unit;
  V2.metricTip(invEl, 'Faturado', inv, isVolume);
  V2.metricTip(openEl, 'Carteira em aberto', open, isVolume);
  V2.metricTip(totEl, 'Faturado + carteira', tot, isVolume);

  var segInv = document.getElementById('kpi-stack-inv'), segOpen = document.getElementById('kpi-stack-open');
  var stack = document.getElementById('kpi-stack');
  if (tot > 0) {
    var pInv = Math.round((inv / tot) * 100), pOpen = 100 - pInv;
    if (descEl) descEl.innerHTML = '<span class="lg lg-inv"></span>Faturado ' + pInv + '% <span class="lg lg-open"></span>Carteira ' + pOpen + '%';
    if (segInv) segInv.style.width = pInv + '%';
    if (segOpen) segOpen.style.width = pOpen + '%';
    if (stack) { stack.hidden = false; stack.setAttribute('aria-label', pInv + '% faturado e ' + pOpen + '% em carteira'); }
  } else {
    if (descEl) descEl.textContent = 'Sem pedidos registrados';
    if (segInv) segInv.style.width = '0%';
    if (segOpen) segOpen.style.width = '0%';
    if (stack) stack.hidden = true;
  }
}

/* ── Tracking de envio & sell-out: calendário ── */
function renderTrackingRibbon(trackingRows, selectedYear, selectedMonth, isVolume, formatNumber) {
  var container = document.getElementById('tracking-days-track');
  var monthPill = document.getElementById('tracking-month-pill');
  var activeDaysEl = document.getElementById('tracking-active-days');
  var regEl = document.getElementById('tracking-regularity-pct');
  var avgEl = document.getElementById('tracking-avg-daily');
  if (!container) return;
  var now = new Date();
  var year = (selectedYear && !isNaN(selectedYear)) ? parseInt(selectedYear, 10) : now.getFullYear();
  var month = (selectedMonth && !isNaN(selectedMonth) && selectedMonth >= 1 && selectedMonth <= 12) ? parseInt(selectedMonth, 10) : (now.getMonth() + 1);
  if (monthPill) monthPill.textContent = Fmt.MONTHS_LONG[month - 1] + ' ' + year;
  var daysInMonth = new Date(year, month, 0).getDate();
  var isCurYear = year === now.getFullYear();
  var isCurMonth = isCurYear && month === now.getMonth() + 1;
  var isFuture = year > now.getFullYear() || (isCurYear && month > now.getMonth() + 1);
  var maxDay = isFuture ? 0 : (isCurMonth ? Math.min(daysInMonth, now.getDate()) : daysInMonth);

  if (maxDay === 0) {
    container.innerHTML = '<div class="v2-empty">' + V2.icon('calendar', 20) + '<p>Mês futuro selecionado. Os dias aparecem aqui quando o período começar.</p></div>';
    if (activeDaysEl) activeDaysEl.textContent = '0 de 0 úteis';
    if (regEl) regEl.textContent = '0%';
    if (avgEl) avgEl.textContent = formatNumber(0) + (isVolume ? ' DZ' : '');
    return;
  }

  // Vários DTs ("Todos"): dia útil só fica verde se TODOS os DTs esperados enviaram; senão, vermelho.
  var expected = Array.isArray(window.__v2TrackExpected) && window.__v2TrackExpected.length > 1 ? window.__v2TrackExpected : null;
  var expNames = {};
  if (expected) expected.forEach(function (e) { expNames[String(e.cnpj)] = e.nome || String(e.cnpj); });
  var sales = new Map();
  if (Array.isArray(trackingRows)) {
    trackingRows.forEach(function (r) {
      var rm = parseInt(r.mes || r.MES || 0, 10), ry = parseInt(r.ano || r.ANO || 0, 10);
      if ((rm && rm !== month) || (ry && ry !== year)) return;
      var d = parseInt(r.dia || r.DIA || 0, 10);
      if (!d && r.data_sell_out) { var p = String(r.data_sell_out).split('-'); if (p.length === 3) d = parseInt(p[2], 10); }
      if (d > 0) {
        var sent = String(r.dists_envio || r.DISTS_ENVIO || '').split(',').filter(Boolean);
        sales.set(d, {
          valor: parseFloat(r.total_vl_sell_out || r.TOTAL_VL_SELL_OUT || 0) || 0,
          volume: parseFloat(r.total_qty_dz_sell_out || r.TOTAL_QTY_DZ_SELL_OUT || 0) || 0,
          clientes: parseInt(r.total_clientes || r.TOTAL_CLIENTES || 0, 10) || 0,
          sent: sent
        });
      }
    });
  }
  function missingFor(s) {
    if (!expected) return [];
    var got = {};
    (s && s.sent || []).forEach(function (c) { got[c] = 1; });
    return expected.filter(function (e) { return !got[String(e.cnpj)]; }).map(function (e) { return expNames[String(e.cnpj)]; });
  }
  var legInactive = document.querySelector('#card-tracking-ribbon .cal-legend .cal-sw.state-inactive');
  if (legInactive && legInactive.parentElement) legInactive.parentElement.lastChild.textContent = expected ? 'Sem venda ou envio incompleto' : 'Sem venda';

  var totalActive = 0, totalBiz = 0, activeBiz = 0, activeWeekends = 0, totalSO = 0;
  var mStr = String(month).padStart(2, '0');
  var html = '<div class="cal-head" aria-hidden="true">' + Fmt.WEEKDAYS_SHORT.map(function (w, i) {
    return '<span class="' + (i === 0 || i === 6 ? 'is-we' : '') + '">' + w + '</span>';
  }).join('') + '</div><div class="cal-grid" role="list">';
  var lead = new Date(year, month - 1, 1).getDay();
  for (var b = 0; b < lead; b++) html += '<span class="cal-blank" aria-hidden="true"></span>';

  for (var d = 1; d <= daysInMonth; d++) {
    var dt = new Date(year, month - 1, d), dow = dt.getDay();
    var we = dow === 0 || dow === 6;
    var dStr = String(d).padStart(2, '0');
    var dateLbl = dStr + '/' + mStr + '/' + year;
    var today = isCurMonth && d === now.getDate();
    if (d > maxDay) {
      html += '<span class="cal-day state-future' + (we ? ' is-we' : '') + '" role="listitem" aria-label="' + dateLbl + ': período futuro"><span class="cal-n">' + d + '</span></span>';
      continue;
    }
    if (!we) totalBiz++;
    var s = sales.get(d);
    var has = !!(s && (s.valor > 0 || s.volume > 0));
    var miss = (expected && !we) ? missingFor(s) : [];
    var state, label, icon, rows;
    if (has && miss.length) {
      totalActive++;
      totalSO += isVolume ? (s.volume || 0) : (s.valor || 0);
      state = 'state-inactive'; label = 'Envio incompleto'; icon = 'x';
      rows = [['Status', 'Envio incompleto (dia útil)', 'att-bad'],
        ['DTs que enviaram', Fmt.int(expected.length - miss.length) + ' de ' + Fmt.int(expected.length)],
        ['Sem envio', miss.slice(0, 6).join(', ') + (miss.length > 6 ? ' +' + (miss.length - 6) : '')],
        ['Faturamento', Fmt.money(s.valor || 0)]];
    } else if (has) {
      totalActive++; if (!we) activeBiz++;
      if (we) activeWeekends++;
      totalSO += isVolume ? (s.volume || 0) : (s.valor || 0);
      state = 'state-active'; label = 'Venda ativa' + (we ? ' (fim de semana)' : ''); icon = 'check';
      rows = [['Status', label, 'att-good'], ['Faturamento', Fmt.money(s.valor || 0)], ['Volume', Fmt.int(s.volume || 0) + ' DZ'], ['Clientes atendidos', Fmt.int(s.clientes || 0)]];
      if (expected && !we) rows.splice(1, 0, ['DTs que enviaram', 'Todos (' + Fmt.int(expected.length) + ')']);
    } else if (we) {
      state = 'state-weekend'; label = 'Fim de semana'; icon = '';
      rows = [['Status', 'Fim de semana, sem movimentação']];
    } else {
      state = 'state-inactive'; label = 'Sem venda'; icon = 'x';
      rows = [['Status', 'Sem venda (dia útil)', 'att-bad'], ['Envio', 'Nenhum envio registrado']];
      if (expected) rows.push(['DTs que enviaram', '0 de ' + Fmt.int(expected.length)]);
    }
    var aria = Fmt.WEEKDAYS_LONG[dow] + ', ' + dateLbl + ': ' + label + (has ? ', faturamento ' + Fmt.money(s.valor || 0) : '') + (today ? ' (hoje)' : '');
    html += '<button type="button" role="listitem" class="cal-day ' + state + (we ? ' is-we' : '') + (today ? ' is-today' : '') + '" aria-label="' + Fmt.esc(aria) + '" data-tip="' + Fmt.esc(V2.tipHtml(Fmt.WEEKDAYS_LONG[dow] + ', ' + dateLbl, rows)) + '">' +
      '<span class="cal-n">' + d + '</span>' + (icon ? '<span class="cal-ic">' + V2.icon(icon, 12) + '</span>' : '') + '</button>';
  }
  html += '</div>';
  container.innerHTML = html;

  var regPct = totalBiz > 0 ? Math.round((activeBiz / totalBiz) * 100) : 0;
  var avg = totalActive > 0 ? (totalSO / totalActive) : 0;
  if (activeDaysEl) {
    activeDaysEl.textContent = activeBiz + ' de ' + totalBiz + ' úteis';
    if (activeDaysEl.parentElement) activeDaysEl.parentElement.title = activeBiz + ' de ' + totalBiz + ' dias úteis com venda (' + regPct + '% de regularidade)' + (activeWeekends ? ' + ' + activeWeekends + ' em fins de semana (total: ' + totalActive + ' dias com venda)' : '');
  }
  if (regEl) {
    regEl.textContent = regPct + '%';
    var chip = regEl.closest('.tracking-kpi-chip');
    if (chip) { chip.classList.remove('att-good', 'att-warn', 'att-bad'); chip.classList.add(V2.attClass(regPct, true)); }
  }
  if (avgEl) avgEl.textContent = formatNumber(avg) + (isVolume ? ' DZ' : '');
}
