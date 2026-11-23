








const API = '';
let MONTHS = typeof getMonths !== 'undefined' ? getMonths() : ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
let chartSpend, chartDisc;

function copyNF(btn, nfValue) {
  event.stopPropagation();
  navigator.clipboard.writeText(nfValue).then(function() {
    var original = btn.innerHTML;
    btn.innerHTML = '<span style="color:#22c55e;font-weight:700;">\u2713 Copiado!</span>';
    btn.style.borderColor = '#22c55e';
    setTimeout(function() { btn.innerHTML = original; btn.style.borderColor = ''; }, 1500);
  });
}

function fmt(v, type='currency') {
  if (v == null || isNaN(v)) return '--';
  const abs = Math.abs(v);
  if (type === 'currency') {
    if (abs >= 1e6) return 'R$ ' + (v/1e6).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1}) + ' Mi';
    if (abs >= 1e3) return 'R$ ' + (v/1e3).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1}) + ' mil';
    return 'R$ ' + v.toLocaleString('pt-BR',{minimumFractionDigits:0,maximumFractionDigits:0});
  }
  if (type === 'pct') return v.toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1}) + '%';
  if (type === 'days') return Math.round(v) + ' dias';
  return v.toLocaleString('pt-BR');
}

// MultiSelect and filters are provided by filters-shared.js
// i18n: override fmt with localized version
if (typeof fmtI18n !== 'undefined') fmt = fmtI18n;
document.addEventListener('langChange', function() { MONTHS = typeof getMonths !== 'undefined' ? getMonths() : MONTHS; if (typeof loadAll === 'function') loadAll(); });
// Set cascade endpoint for notas_ri-based modules
_cascadeEndpoint = '/api/filters/cascading';

async function loadKPIs() {
  try {
    const r = await fetch(`${API}/api/performance/kpis?${getFilters()}`).then(r=>r.json());
    const c = r.current || {};
    const p = r.previous || {};
    document.getElementById('vSpend').textContent = fmt(c.net_spend);
    document.getElementById('vCentral').textContent = fmt(c.centralization_pct, 'pct');
    document.getElementById('vPrazo').textContent = fmt(c.avg_payment_term, 'days');
    // Variations
    const hasMes = filters.fMes && filters.fMes.getSelected().length > 0;
    const vsLabel = hasMes ? t('vs mesmo período mês anterior') : t('vs mesmo período ano anterior');
    if (p.net_spend) {
      const pct = ((c.net_spend - p.net_spend) / p.net_spend * 100);
      const arrow = pct > 0 ? '↑' : '↓';
      const color = pct > 0 ? '#ef4444' : '#22c55e';
      document.getElementById('dSpend').innerHTML = `<span style="color:${color}">${arrow} ${Math.abs(pct).toFixed(1)}% ${vsLabel}</span>`;
    } else {
      document.getElementById('dSpend').innerHTML = '';
    }
    // Centralization semantic color (border stays neutral, only value color changes)
    const centralVal = c.centralization_pct || 0;
    const centralColor = centralVal >= 80 ? '#22c55e' : centralVal >= 70 ? '#fbbf24' : '#f87171';
    document.getElementById('vCentral').style.color = centralColor;
    // Delta vs meta for Centralização (meta = 80%)
    const centralDiff = centralVal - 80;
    const centralUp = centralDiff >= 0;
    document.getElementById('dCentral').innerHTML = `<span style="color:${centralUp?'#22c55e':'#ef4444'}">${centralUp?'\u2191':'\u2193'} ${centralUp?'+':''}${centralDiff.toFixed(1)} ${t('pp vs meta')}</span>`;
    // Payment term semantic (border stays amber, only value color changes)
    const prazoVal = c.avg_payment_term || 0;
    const prazoColor = prazoVal >= 60 ? '#22c55e' : prazoVal >= 50 ? '#fbbf24' : '#f87171';
    document.getElementById('vPrazo').style.color = prazoColor;
    // Delta vs meta for Prazo (meta = 60 dias)
    const prazoDiff = Math.round(prazoVal - 60);
    const prazoUp = prazoDiff >= 0;
    document.getElementById('dPrazo').innerHTML = `<span style="color:${prazoUp?'#22c55e':'#ef4444'}">${prazoUp?'\u2191':'\u2193'} ${prazoUp?'+':''}${prazoDiff} ${t('dias vs meta')}</span>`;
  } catch (err) {
    console.error('loadKPIs error:', err);
  }
}

function fmtPct(v) { return v != null ? Math.abs(Number(v)).toFixed(1) + '%' : '--'; }
function fmtPp(v) { return v != null ? (Number(v)>=0?'+':'') + Number(v).toFixed(1) : '--'; }

function getTickColor(isHighlight = false) {
  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  if (isHighlight) return isLight ? '#2563eb' : '#60a5fa';
  const cssTick = (getComputedStyle(document.documentElement).getPropertyValue('--fr-tick') || '').trim();
  if (cssTick && cssTick !== 'rgba(0,0,0,0.75)' && !isLight) return cssTick;
  return isLight ? '#64748b' : '#94a3b8';
}

let currentPerfYoYMetric = 'spend';
let _perfYoYRawData = null;

function setPerfYoYMetric(metric) {
  if (currentPerfYoYMetric === metric) return;
  currentPerfYoYMetric = metric;
  const btnS = document.getElementById('btnYoYSpend');
  const btnC = document.getElementById('btnYoYCentral');
  if (btnS) btnS.setAttribute('aria-selected', String(metric === 'spend'));
  if (btnC) btnC.setAttribute('aria-selected', String(metric === 'central'));
  renderPerfYoYChart();
}

async function loadSpendYoY() {
  try {
    const data = await fetch(`${API}/api/performance/spend-yoy?${getFilters()}`).then(r => r.json());
    _perfYoYRawData = Array.isArray(data) ? data : [];
    renderPerfYoYChart();
  } catch (err) {
    console.error('loadSpendYoY error:', err);
  }
}

const tok = n => (getComputedStyle(document.documentElement).getPropertyValue(n) || '').trim();

const pluginTracoYoY = {
  id: 'tracoComp',
  afterDatasetsDraw(chart) {
    const meta = chart.getDatasetMeta(0), y = chart.scales.y, c = chart.ctx;
    const v = chart._yoyData;
    if (!v || !v.comp) return;
    c.save();
    c.strokeStyle = tok('--gr-traco') || (document.documentElement.getAttribute('data-theme') === 'light' ? '#161A22' : '#F0F4F8');
    c.lineWidth = 2.5;
    meta.data.forEach((bar, i) => {
      if (v.comp[i] == null) return;
      const py = Math.round(y.getPixelForValue(v.comp[i])) + 0.5;
      const meia = bar.width * 0.62;
      c.beginPath();
      c.moveTo(bar.x - meia, py);
      c.lineTo(bar.x + meia, py);
      c.stroke();
    });
    c.restore();
  }
};

const pluginRotuloFoco = {
  id: 'rotuloFoco',
  afterDatasetsDraw(chart) {
    const v = chart._yoyData;
    if (!v || !v.realizado) return;
    const i = v.focoIndex;
    const bar = chart.getDatasetMeta(0).data[i];
    if (!bar || v.realizado[i] == null) return;
    const c = chart.ctx, yTraco = v.comp[i] != null ? chart.scales.y.getPixelForValue(v.comp[i]) : null;
    const encosta = yTraco != null && yTraco > bar.y - 24 && yTraco < bar.y + 4;
    const yTexto = (encosta ? Math.min(bar.y, yTraco) : bar.y) - 6;
    c.save();
    c.fillStyle = tok('--gr-titulo') || (document.documentElement.getAttribute('data-theme') === 'light' ? '#161A22' : '#F0F4F8');
    c.font = '700 12px Inter, "Segoe UI", system-ui, sans-serif';
    c.textAlign = 'center';
    c.textBaseline = 'bottom';
    const txt = v.isSpend ? fmt(v.realizado[i]) : fmtPct(v.realizado[i]);
    c.fillText(txt, bar.x, yTexto);
    c.restore();
  }
};

const pluginPilulasYoY = {
  id: 'pilulasYoY',
  afterDraw(chart) {
    const v = chart._yoyData;
    if (!v || !v.realizado) return;
    const c = chart.ctx, x = chart.scales.x, y0 = x.bottom + 6;
    c.save();
    c.font = '600 11px Inter, "Segoe UI", system-ui, sans-serif';
    c.textAlign = 'center';
    c.textBaseline = 'middle';
    v.realizado.forEach((r, i) => {
      const cp = v.comp[i];
      if (r == null || !cp) return;
      const pct = v.isSpend ? ((r - cp) / cp * 100) : (r - cp);
      let st = 'atencao';
      if (v.isSpend) {
        st = pct < -1 ? 'bom' : (pct > 5 ? 'ruim' : 'atencao');
      } else {
        st = r >= 80 ? 'bom' : (r >= 70 ? 'atencao' : 'ruim');
      }
      const sign = pct >= 0 ? '+' : '';
      const txt = v.isSpend ? `${sign}${pct.toFixed(1)}%` : `${sign}${pct.toFixed(1)} pp`;
      const w = c.measureText(txt).width + 14, h = 20, px = x.getPixelForValue(i);
      c.fillStyle = tok(`--gr-${st}-bg`) || (st === 'bom' ? 'rgba(74,222,128,.14)' : st === 'ruim' ? 'rgba(248,113,113,.14)' : 'rgba(251,191,36,.14)');
      c.beginPath();
      if (c.roundRect) c.roundRect(px - w / 2, y0, w, h, 10);
      else c.rect(px - w / 2, y0, w, h);
      c.fill();
      c.fillStyle = tok(`--gr-${st}-tx`) || (st === 'bom' ? '#4ADE80' : st === 'ruim' ? '#FCA5A5' : '#FBBF24');
      c.fillText(txt, px, y0 + h / 2 + 0.5);
    });
    c.restore();
  }
};

function tooltipExternoYoY({ chart, tooltip }) {
  const tip = document.getElementById('grTip');
  if (!tip) return;
  if (!tooltip || tooltip.opacity === 0 || !tooltip.dataPoints?.length) {
    tip.hidden = true;
    return;
  }
  const i = tooltip.dataPoints[0].dataIndex;
  const v = chart._yoyData;
  if (!v) return;
  const r = v.realizado[i], cp = v.comp[i];
  const pct = cp ? (v.isSpend ? (r - cp) / cp * 100 : r - cp) : null;
  let st = '';
  if (pct != null) {
    st = v.isSpend ? (pct < -1 ? 'bom' : pct > 5 ? 'ruim' : 'atencao') : (r >= 80 ? 'bom' : r >= 70 ? 'atencao' : 'ruim');
  }
  const sign = pct != null && pct >= 0 ? '+' : '';
  const pctFormatted = pct == null ? '—' : (v.isSpend ? `${sign}${pct.toFixed(1)}%` : `${sign}${pct.toFixed(1)} pp`);
  const difFormatted = (r != null && cp != null) ? fmt(r - cp) : '—';

  const mesesExt = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  const mesNome = mesesExt[parseInt(v.mesesRaw[i]) - 1] || v.labels[i];

  const linhas = [
    [v.serie, r == null ? '—' : (v.isSpend ? fmt(r) : fmtPct(r)), ''],
    [v.comparacao, cp == null ? '—' : (v.isSpend ? fmt(cp) : fmtPct(cp)), ''],
    [v.percentual, pctFormatted, st],
    ['Diferença', difFormatted, st]
  ];

  tip.innerHTML = `<h3>${mesNome}</h3><dl>${linhas.map(([label, val, cls]) => `<dt>${label}</dt><dd class="${cls}">${val}</dd>`).join('')}</dl>`;
  tip.hidden = false;

  const _z = window.dnaScale ? window.dnaScale() : 1;
  const _r = chart.canvas.getBoundingClientRect();
  const caixa = { left: _r.left / _z, top: _r.top / _z };
  const bar = chart.getDatasetMeta(0).data[i];
  if (!bar) return;
  const topoBarra = Math.min(bar.y, cp != null ? chart.scales.y.getPixelForValue(cp) : bar.y);
  let left = caixa.left + bar.x - tip.offsetWidth / 2;
  let top = caixa.top + topoBarra - tip.offsetHeight - 14;
  left = Math.max(8, Math.min(left, window.innerWidth / _z - tip.offsetWidth - 8));
  if (top < 8) top = caixa.top + bar.y + 14;
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
}

function renderPerfYoYChart() {
  if (!_perfYoYRawData) return;
  const isSpend = currentPerfYoYMetric === 'spend';

  const _selYears = filters.fAno ? filters.fAno.getSelected() : [];
  const _cy = String(new Date().getFullYear());
  const activeYear = (_selYears && _selYears.length === 1) ? _selYears[0] : _cy;
  const _includesCY = _selYears.length === 0 || _selYears.includes(_cy);
  const currentMonth = _includesCY ? new Date().getMonth() : 11;
  const filtered = _perfYoYRawData.filter(d => parseInt(d.mes) - 1 <= currentMonth);
  const labels = filtered.map(d => MONTHS[parseInt(d.mes) - 1]);
  const mesesRaw = filtered.map(d => d.mes);

  // Foco: se mês selecionado no filtro, usar ele; senão último mês
  const selMeses = filters.fMes ? filters.fMes.getSelected() : [];
  let focoIndex = filtered.length - 1;
  if (selMeses && selMeses.length > 0) {
    const idx = filtered.findIndex(d => String(d.mes) === String(selMeses[0]));
    if (idx >= 0) focoIndex = idx;
  }

  let realizado, comp, serie, comparacao, percentual;
  if (isSpend) {
    serie = t('Spend Líquido');
    comparacao = t('Ano Anterior');
    percentual = t('Variação');
    realizado = filtered.map(d => d.current_spend);
    comp = filtered.map(d => d.prev_spend);

    const totalCur = realizado.reduce((a, b) => a + (b || 0), 0);
    const totalPrev = comp.reduce((a, b) => a + (b || 0), 0);
    const pctVar = totalPrev ? ((totalCur - totalPrev) / totalPrev * 100).toFixed(1) : 0;
    const direction = pctVar > 0 ? t('acima') : t('abaixo');
    const signPct = parseFloat(pctVar) >= 0 ? '+' : '';

    const grEyebrow = document.getElementById('grEyebrow');
    if (grEyebrow) grEyebrow.textContent = `Performance Mensal · ${activeYear}`;
    const grTitulo = document.getElementById('grTitulo');
    if (grTitulo) grTitulo.textContent = `Em ${activeYear}, Spend Líquido em ${fmt(totalCur)} (${signPct}${pctVar}% ${direction} vs ano anterior)`;

    const selo = document.getElementById('grAcumSelo');
    if (selo) {
      selo.textContent = `${signPct}${pctVar}%`;
      selo.className = 'selo ' + (parseFloat(pctVar) <= 0 ? 'bom' : 'ruim');
    }
  } else {
    serie = t('% Centralização');
    comparacao = t('% Centraliz. Anterior');
    percentual = t('Diferença');
    realizado = filtered.map(d => d.current_central_pct != null ? d.current_central_pct : null);
    comp = filtered.map(d => d.prev_central_pct != null ? d.prev_central_pct : null);

    const totalCurCentralSpend = filtered.reduce((a, d) => a + (d.current_central_spend || 0), 0);
    const totalCurSpend = filtered.reduce((a, d) => a + (d.current_spend || 0), 0);
    const totalCurCentralPct = totalCurSpend ? (totalCurCentralSpend / totalCurSpend * 100) : 0;

    const totalPrevCentralSpend = filtered.reduce((a, d) => a + (d.prev_central_spend || 0), 0);
    const totalPrevSpend = filtered.reduce((a, d) => a + (d.prev_spend || 0), 0);
    const totalPrevCentralPct = totalPrevSpend ? (totalPrevCentralSpend / totalPrevSpend * 100) : 0;

    const diffPP = totalCurCentralPct - totalPrevCentralPct;
    const dirPP = diffPP >= 0 ? t('acima') : t('abaixo');
    const signPP = diffPP >= 0 ? '+' : '';

    const grEyebrow = document.getElementById('grEyebrow');
    if (grEyebrow) grEyebrow.textContent = `Centralização · ${activeYear}`;
    const grTitulo = document.getElementById('grTitulo');
    if (grTitulo) grTitulo.textContent = `Em ${activeYear}, Centralização em ${fmtPct(totalCurCentralPct)} (${signPP}${diffPP.toFixed(1)} pp ${dirPP} vs ano anterior)`;

    const selo = document.getElementById('grAcumSelo');
    if (selo) {
      selo.textContent = `${totalCurCentralPct.toFixed(1)}%`;
      selo.className = 'selo ' + (totalCurCentralPct >= 80 ? 'bom' : 'atencao');
    }
  }

  const grLegSerie = document.getElementById('grLegSerie');
  if (grLegSerie) grLegSerie.textContent = serie;
  const grLegComp = document.getElementById('grLegComp');
  if (grLegComp) grLegComp.textContent = comparacao;

  // Tabela acessível
  const grTabela = document.getElementById('grTabela');
  if (grTabela) {
    grTabela.innerHTML = `<thead><tr><th>Mês</th><th>${serie}</th><th>${comparacao}</th><th>${percentual}</th></tr></thead><tbody>${filtered.map((d, i) => {
      const r = realizado[i], c = comp[i];
      const p = (r != null && c) ? (isSpend ? ((r - c) / c * 100).toFixed(1) + '%' : (r - c).toFixed(1) + ' pp') : '—';
      return `<tr><td>${labels[i]}</td><td>${r == null ? '—' : (isSpend ? fmt(r) : fmtPct(r))}</td><td>${c == null ? '—' : (isSpend ? fmt(c) : fmtPct(c))}</td><td>${p}</td></tr>`;
    }).join('')}</tbody>`;
  }

  if (chartSpend) chartSpend.destroy();
  const canvasEl = document.getElementById('chartSpendYoY');
  if (!canvasEl) return;
  const ctx = canvasEl.getContext('2d');

  const maxVal = Math.max(...realizado.filter(x => x != null), ...comp.filter(x => x != null), 1);

  chartSpend = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: serie,
          data: realizado,
          backgroundColor: ctxItem => ctxItem.dataIndex === focoIndex ? tok('--gr-barra-foco') || '#3B82F6' : tok('--gr-barra') || '#2C3E63',
          hoverBackgroundColor: ctxItem => ctxItem.dataIndex === focoIndex ? tok('--gr-barra-foco') || '#60A5FA' : tok('--gr-barra-hover') || '#4B6AA5',
          borderRadius: 3,
          barPercentage: 0.9,
          categoryPercentage: 0.74
        }
      ]
    },
    plugins: [pluginTracoYoY, pluginRotuloFoco, pluginPilulasYoY],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 22, bottom: 32, left: 4, right: 4 } },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false, external: tooltipExternoYoY }
      },
      scales: {
        y: {
          display: false,
          beginAtZero: true,
          max: maxVal * 1.08
        },
        x: {
          grid: { display: false },
          border: { display: true, color: tok('--gr-base') || '#2A3242' },
          ticks: {
            color: ctxItem => ctxItem.index === focoIndex ? tok('--gr-eixo-foco') || '#F0F4F8' : tok('--gr-eixo') || '#94A2B8',
            font: ctxItem => ({
              size: 12,
              weight: ctxItem.index === focoIndex ? '700' : '400',
              family: 'Inter, "Segoe UI", system-ui, sans-serif'
            })
          }
        }
      }
    }
  });

  chartSpend._yoyData = {
    realizado,
    comp,
    labels,
    mesesRaw,
    focoIndex,
    isSpend,
    serie,
    comparacao,
    percentual
  };

  canvasEl.addEventListener('mouseleave', () => {
    const tip = document.getElementById('grTip');
    if (tip) tip.hidden = true;
  });
  window.addEventListener('scroll', () => {
    const tip = document.getElementById('grTip');
    if (tip) tip.hidden = true;
  }, { passive: true });

  syncFunnelRowHeight();
  scheduleSpendChartResize();
}

let currentPriceView = 'table';
let _discountData = null;

function updatePriceCardTitle() {
  const ttl = document.getElementById('txtPriceCardTitle');
  if (!ttl) return;
  if (!_discountData) {
    ttl.innerHTML = `${t('Alerta de Aumento de Preço')} — <span style="color:var(--fr-txt-soft);">${t('Oportunidade de Renegociação')}</span>`;
    return;
  }
  const { totalDisc, discColor, discLabel } = _discountData;
  const valSpan = `<span style="color:${discColor}">${fmt(totalDisc)}</span>`;
  if (currentPriceView === 'table') {
    ttl.innerHTML = `${discLabel}: ${valSpan} <span style="font-size:.60rem;color:var(--fr-txt-soft);font-weight:400;margin-left:4px;">(${t('Oportunidade de Renegociação')})</span>`;
  } else {
    ttl.innerHTML = `${discLabel}: ${valSpan}`;
  }
}

function setPriceView(view) {
  if (currentPriceView === view) return;
  currentPriceView = view;
  const isTable = view === 'table';
  const tableEl = document.getElementById('priceTableView');
  const chartEl = document.getElementById('priceChartView');
  const btnT = document.getElementById('btnViewTable');
  const btnC = document.getElementById('btnViewChart');
  const btnX = document.getElementById('btnExportAlerts');

  if (tableEl) tableEl.style.display = isTable ? 'block' : 'none';
  if (chartEl) chartEl.style.display = isTable ? 'none' : 'block';
  if (btnT) btnT.classList.toggle('active', isTable);
  if (btnC) btnC.classList.toggle('active', !isTable);
  if (btnX) btnX.style.display = isTable ? 'inline-flex' : 'none';

  updatePriceCardTitle();

  if (!isTable) {
    renderDiscountChart();
  }
}

function renderDiscountChart() {
  if (!_discountData) return;
  const { labels, monthly, totalDisc, barColors, discTickColors, lastIdxDisc, maxIdx, minIdx } = _discountData;
  const discLabelPlugin = {
    id:'discLabels',
    afterDatasetsDraw(chart){
      const meta = chart.getDatasetMeta(0);
      const ctxC = chart.ctx;
      ctxC.save();
      [maxIdx, minIdx].forEach(idx => {
        if(idx == null || idx < 0) return;
        const bar = meta.data[idx];
        if(!bar) return;
        const val = monthly[idx];
        const _loc = typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR';
        const label = (val/1e3).toLocaleString(_loc,{minimumFractionDigits:1,maximumFractionDigits:1}) + ' ' + t('mil');
        ctxC.font = 'bold 9px sans-serif';
        const isLight = document.documentElement.getAttribute('data-theme') === 'light';
        ctxC.fillStyle = val <= 0 ? 'rgba(22,163,74,.9)' : (isLight ? '#991b1b' : 'rgba(255,255,255,.9)');
        ctxC.textAlign = 'center';
        const yPos = val >= 0 ? Math.max(12, bar.y - 4) : bar.y + 12;
        ctxC.fillText(label, bar.x, yPos);
      });
      ctxC.restore();
    }
  };
  if (chartDisc) chartDisc.destroy();
  const canvas = document.getElementById('chartDiscount');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  chartDisc = new Chart(ctx, {
    type:'bar',
    data:{ labels, datasets:[{label: totalDisc <= 0 ? t('Desconto mensal') : t('Aumento mensal'), data:monthly, backgroundColor:barColors, borderRadius:3, barPercentage:.55}] },
    plugins:[discLabelPlugin],
    options:{
      responsive:true, maintainAspectRatio:false,
      layout:{padding:{top:12, bottom:4}},
      plugins:{legend:{display:false}, tooltip:{callbacks:{label:function(c){return fmt(c.raw)}}}},
      scales:{
        x:{
          grid:{display:false},
          border:{display:false},
          ticks:{
            color:function(ctx){return ctx.index===lastIdxDisc?getTickColor(true):getTickColor(false);},
            font:function(ctx){return ctx.index===lastIdxDisc?{size:9,weight:'800'}:{size:8.5,weight:'500'};}
          }
        },
        y:{
          title:{display:false},
          grid:{display:false},
          border:{display:false},
          ticks:{
            color:function(){return getTickColor(false);},
            font:{size:8},
            maxTicksLimit:4,
            callback:v=>fmt(v)
          }
        }
      }
    }
  });
}

async function loadDiscountChart() {
  // Build filters WITHOUT mes (we want all months for the year chart)
  const p = new URLSearchParams();
  Object.entries(filters).forEach(([id, ms]) => {
    if (ms.key === 'mes') return; // skip month filter for this chart
    if (ms.key === 'oc_type') { ms.getSelected().forEach(v => p.append('oc_type', v)); }
    else { ms.getSelected().forEach(v => p.append(ms.key, v)); }
  });
  const data = await fetch(`${API}/api/commercial/payment-evolution?${p.toString()}`).then(r=>r.json());
  // Only limit months to current month when current year is selected; past years show all 12
  const _selYearsD = filters.fAno ? filters.fAno.getSelected() : [];
  const _cyD = String(new Date().getFullYear());
  const _includesCYD = _selYearsD.length === 0 || _selYearsD.includes(_cyD);
  const currentMonth = _includesCYD ? new Date().getMonth() : 11;
  const filtered = data.filter(d => parseInt(d.mes) - 1 <= currentMonth);
  const labels = filtered.map(d => MONTHS[parseInt(d.mes)-1] || d.mes);
  const monthly = filtered.map(d => d.discount_monthly || 0);
  const totalDisc = monthly.reduce((a,b) => a + (b||0), 0);
  const discColor = totalDisc <= 0 ? '#22c55e' : '#ef4444';
  const discLabel = totalDisc <= 0 ? t('Desconto Financeiro Obtido Acumulado') : t('Aumento de Preço Acumulado');
  const maxVal = Math.max(...monthly);
  const minVal = Math.min(...monthly);
  const maxIdx = monthly.indexOf(maxVal);
  const minIdx = monthly.indexOf(minVal);
  const lastIdxDisc = monthly.length - 1;
  const barColors = monthly.map((v,i) => {
    if(i === lastIdxDisc) return v <= 0 ? 'rgba(22,163,74,1)' : 'rgba(220,38,38,1)'; // current month full
    if(i === minIdx && minVal < 0) return 'rgba(22,163,74,.7)';
    if(i === maxIdx && maxVal > 0) return 'rgba(220,38,38,.7)';
    return v <= 0 ? 'rgba(22,163,74,.35)' : 'rgba(220,38,38,.35)';
  });
  // X-axis tick colors: highlight current month
  const discTickColors = labels.map((_,i) => i === lastIdxDisc ? getTickColor(true) : getTickColor(false));

  _discountData = { labels, monthly, totalDisc, discColor, discLabel, barColors, discTickColors, lastIdxDisc, maxIdx, minIdx };
  updatePriceCardTitle();

  if (currentPriceView === 'chart') {
    renderDiscountChart();
  }
}

let currentFunnelScope = 'diretos';

function syncFunnelRowHeight() {
  const leftCard = document.getElementById('cardSpendYoY');
  const wrapChart = document.getElementById('wrapSpendYoY');
  // Altura agora é definida pelo CSS (linha em stretch: o cartão mais alto define, o outro acompanha)
  if (leftCard) leftCard.style.height = '';
  if (wrapChart) {
    wrapChart.style.height = '';
    wrapChart.style.maxHeight = '';
  }
  if (typeof chartSpend !== 'undefined' && chartSpend && typeof chartSpend.resize === 'function') {
    chartSpend.resize();
  }
}

// Auto-fit text content inside funnel bars dynamically
function autoFitFunnelBars() {
  document.querySelectorAll('.funnel-bar').forEach(bar => {
    const content = bar.querySelector('.funnel-bar-content');
    if (!content) return;
    if (bar.classList.contains('is-zero')) {
      content.style.transform = 'none';
      return;
    }
    content.style.transform = 'none';
    const barW = bar.clientWidth;
    const maxAvailable = barW - 12; // 0.5rem padding + safety margin
    const contentW = content.scrollWidth;
    if (maxAvailable > 30 && contentW > maxAvailable) {
      const scale = Math.max(0.65, maxAvailable / contentW);
      content.style.transform = `scale(${scale.toFixed(3)})`;
      content.style.transformOrigin = 'center center';
    } else {
      content.style.transform = 'none';
    }
  });
}

// Recalcula o canvas após o layout e o zoom do notebook estabilizarem.
// clientWidth/clientHeight usam as dimensões CSS internas, sem aplicar o zoom duas vezes.
let spendResizeFrame = 0;
function scheduleSpendChartResize() {
  cancelAnimationFrame(spendResizeFrame);
  spendResizeFrame = requestAnimationFrame(() => {
    const area = document.getElementById('wrapSpendYoY');
    if (!chartSpend || !area || !area.clientWidth || !area.clientHeight) return;
    chartSpend.resize(area.clientWidth, area.clientHeight);
  });
}
function observeSpendChartArea() {
  const area = document.getElementById('wrapSpendYoY');
  if (area && window.ResizeObserver) {
    new ResizeObserver(scheduleSpendChartResize).observe(area);
  }
  scheduleSpendChartResize();
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', observeSpendChartArea);
} else {
  observeSpendChartArea();
}
window.addEventListener('resize', scheduleSpendChartResize);

// Observe funnel card as the mandatory height master
function initFunnelResizeObserver() {
  const funnelCard = document.getElementById('cardFunnel');
  if (funnelCard && !window._funnelResizeObserver && window.ResizeObserver) {
    window._funnelResizeObserver = new ResizeObserver(() => {
      syncFunnelRowHeight();
      autoFitFunnelBars();
    });
    window._funnelResizeObserver.observe(funnelCard);
  }
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initFunnelResizeObserver);
} else {
  initFunnelResizeObserver();
}
window.addEventListener('resize', () => {
  syncFunnelRowHeight();
  autoFitFunnelBars();
});

function setFunnelScope(scope) {
  if (currentFunnelScope === scope) return;
  currentFunnelScope = scope;
  document.querySelectorAll('#funnelScopePills .funnel-pill').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-scope') === scope);
  });
  loadLeadTime();
}

function getStageIconSvg(icon, id) {
  if (id === 'fat_tot') {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" width="20" height="20">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <path d="M9 15l2 2 4-4" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
  }
  if (id === 'fat_ini') {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" width="20" height="20">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="16" y1="13" x2="8" y2="13"/>
    </svg>`;
  }
  if (id === 'aprov') {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" width="20" height="20">
      <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>
      <path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6"/>
      <path d="M12 9l2 2 4-4" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
  }
  if (icon === 'cart') {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" width="20" height="20">
      <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>
      <path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6"/>
    </svg>`;
  }
  if (id === 'req' || icon === 'req_doc') {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" width="20" height="20">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="16" y1="13" x2="8" y2="13"/>
      <line x1="16" y1="17" x2="8" y2="17"/>
    </svg>`;
  }
  return `<svg viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" width="20" height="20">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
  </svg>`;
}

async function loadLeadTime() {
  const container = document.getElementById('funnelFlow');
  if (!container) return;
  container.style.opacity = '0.6';
  try {
    const res = await fetch(`${API}/api/performance/lead-time?${getFilters()}&scope=${currentFunnelScope}`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    const data = await res.json();
    const d = data[0] || {};
    const stages = d.stages || [];
    const connectors = d.connectors || [];

    // Title / longest leg
    if (d.longest_leg) {
      document.getElementById('ttlLeadTime').textContent = tt('O maior tempo do processo está entre {leg}.', {leg: t(d.longest_leg)});
    } else if (d.summary_title) {
      document.getElementById('ttlLeadTime').textContent = t(d.summary_title);
    }

    if (!stages || stages.length === 0) {
      container.innerHTML = `<div style="padding:1.5rem;text-align:center;color:var(--text-muted, #94a3b8);font-size:0.85rem;">Nenhum dado encontrado para o escopo selecionado (${t(currentFunnelScope)}).</div>`;
      return;
    }

    // Identify which connector is the longest bottleneck
    let longestConnectorIdx = -1;
    let maxHours = -1;
    connectors.forEach((c, idx) => {
      if (c.val != null) {
        const hours = c.val * (c.unit === 'dias' ? 24 : 1);
        if (hours > maxHours) {
          maxHours = hours;
          longestConnectorIdx = idx;
        }
      }
    });

    const maxQty = stages.length > 0 ? Math.max(...stages.map(s => s.qty || 0), 1) : 1;

    let html = '<div class="funnel-container">';
    html += `
      <div class="funnel-header-row">
        <span class="funnel-col-th">${t('Etapa')}</span>
        <span class="funnel-col-th text-center">${t('Volume & Spend')}</span>
        <span class="funnel-col-th text-meta">${t('Avanço (Qtd)')}</span>
      </div>
    `;
    stages.forEach((stg, i) => {
      const spendStr = fmt(stg.spend, 'currency');
      const qtyStr = stg.qty != null ? stg.qty.toLocaleString('pt-BR') : '--';
      const qtyLbl = t(stg.qty_label || 'documentos');
      const iconSvg = getStageIconSvg(stg.icon, stg.id);

      // Width calculation for the funnel shape (tapering down based on quantity)
      const isZero = (stg.qty == null || stg.qty <= 0);
      const pctOfMax = maxQty > 0 ? ((stg.qty || 0) / maxQty * 100) : 100;
      const barWidth = isZero ? 0 : Math.max(48, Math.min(100, Math.round(pctOfMax)));
      const barCls = isZero ? 'funnel-bar is-zero' : 'funnel-bar';
      const barStyle = isZero ? '' : `style="width: ${barWidth}%;"`;

      let tip = `${t(stg.name)} ${stg.sub ? t(stg.sub) : ''}\nVolume: ${qtyStr} ${qtyLbl}\nSpend: R$ ${(stg.spend || 0).toLocaleString('pt-BR', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
      if (i > 0 && stg.conv_pct != null) {
        tip += `\n${t('Retenção da Base')}: ${stg.conv_pct}%`;
        if (stg.step_conv_pct != null) {
          tip += `\n${t('Avanço vs Anterior')}: ${stg.step_conv_pct}%`;
        }
      }
      if (stg.open_qty != null && stg.open_qty > 0) {
        tip += `\n${t('Pedidos Parciais')}: ${stg.open_qty.toLocaleString('pt-BR')} pedidos`;
      }
      if (stg.open_spend != null && stg.open_spend > 0) {
        tip += `\n${t('Saldo a Faturar')}: R$ ${stg.open_spend.toLocaleString('pt-BR', {minimumFractionDigits:2, maximumFractionDigits:2})} (${stg.open_pct}%)`;
      }

      let convBadge = '';
      if (i === 0) {
        convBadge = `<span class="funnel-conv-tag" title="${t('Base 100% de volume inicial')}"><span class="conv-dim">${t('base')}</span> 100%</span>`;
      } else if (stg.conv_pct != null) {
        const baseStg = stages[0];
        const prevStg = stages[i - 1];
        let badgeTitle = `${t('Retenção da base inicial')}: ${stg.conv_pct}%`;
        if (baseStg && baseStg.qty && stg.qty != null) {
          badgeTitle += ` (${stg.qty.toLocaleString('pt-BR')} / ${baseStg.qty.toLocaleString('pt-BR')} ${t(baseStg.qty_label || 'docs')})`;
        }
        if (stg.step_conv_pct != null && prevStg && prevStg.qty) {
          badgeTitle += `\n${t('Avanço vs etapa anterior')}: ${stg.step_conv_pct}% (${stg.qty.toLocaleString('pt-BR')} / ${prevStg.qty.toLocaleString('pt-BR')} ${t(prevStg.qty_label || 'docs')})`;
        }
        convBadge = `<span class="funnel-conv-tag" title="${badgeTitle}"><span class="conv-dim">${t('qtd')}</span> ${stg.conv_pct}%</span>`;
      }

      let openTag = '';
      if (stg.open_label && stg.id === 'fat_tot' && stg.open_qty != null && stg.open_qty > 0) {
        openTag = `<span class="funnel-open-tag" style="color:#f59e0b;" title="${t('Pedidos com faturamento parcial em andamento')}">${t(stg.open_label)}</span>`;
      } else if (stg.open_spend != null && stg.open_spend > 0) {
        openTag = `<span class="funnel-open-tag" title="${t('Saldo não faturado')}">${t('Aberto')}: ${fmt(stg.open_spend, 'currency')}</span>`;
      }

      // Funnel tier row
      html += `
        <div class="funnel-tier" title="${tip}">
          <div class="funnel-tier-label">
            <div class="funnel-tier-icon">${iconSvg}</div>
            <div class="funnel-tier-text">
              <span class="funnel-stage-name">${t(stg.name)}</span>
              <span class="funnel-stage-sub">${stg.sub ? t(stg.sub) : '&nbsp;'}</span>
            </div>
          </div>
          <div class="funnel-bar-track">
            <div class="${barCls}" ${barStyle}>
              <div class="funnel-bar-content">
                <span class="funnel-bar-qty">${qtyStr} ${qtyLbl}</span>
                <span class="funnel-bar-spend">${spendStr}</span>
              </div>
            </div>
          </div>
          <div class="funnel-tier-meta">
            ${convBadge}
            ${openTag}
          </div>
        </div>
      `;

      // Connector to next tier (if not the last stage)
      if (i < connectors.length) {
        const c = connectors[i];
        const durVal = c.val != null ? Math.round(c.val) : '--';
        const durUnit = t(c.unit || 'dias');

        html += `
          <div class="funnel-connector" title="${t(c.label || '')}">
            <div></div>
            <div class="funnel-connector-center">
              <div class="funnel-conn-badge">
                <span class="fc-arrow">↓</span>
                <span class="fc-val">${durVal}</span>
                <span class="fc-unit">${durUnit}</span>
              </div>
            </div>
            <div></div>
          </div>
        `;
      }
    });

    html += '</div>';
    container.innerHTML = html;
    autoFitFunnelBars();
    requestAnimationFrame(() => {
      autoFitFunnelBars();
      syncFunnelRowHeight();
    });
    setTimeout(() => {
      autoFitFunnelBars();
      syncFunnelRowHeight();
    }, 50);
  } catch (err) {
    console.error('Error loading lead time funnel:', err);
    container.innerHTML = `<div style="padding:1.5rem;text-align:center;color:var(--text-muted, #94a3b8);font-size:0.85rem;">
      <span style="display:inline-block;margin-bottom:0.5rem;color:#f87171;">⚠️ Falha ao carregar dados do funil (${currentFunnelScope})</span><br>
      <button type="button" class="funnel-pill" onclick="loadLeadTime()" style="margin-top:0.5rem;cursor:pointer;">Tentar novamente</button>
    </div>`;
  } finally {
    container.style.opacity = '1';
  }
}

async function loadDeviations() {
  try {
    const data = await fetch(`${API}/api/performance/process-deviations?${getFilters()}`).then(r=>r.json());
    const d = (Array.isArray(data) ? data[0] : data) || {};
    const total = d.total || 1;
    const regPct = ((d.regular||0)/total*100).toFixed(1);
    const posPct = ((d.pos_fatura||0)/total*100).toFixed(1);
    const semPct = ((d.sem_oc||0)/total*100).toFixed(1);
    const devPct = (parseFloat(posPct) + parseFloat(semPct)).toFixed(1);
    document.getElementById('ttlDeviations').textContent = tt('Desvios de processo representam {pct}% do Spend Líquido no período selecionado', {pct: devPct});
    document.getElementById('devBar').innerHTML = `
      <div class="dev-segment dev-regular" style="width:${regPct}%">${regPct}%</div>
      <div class="dev-segment dev-pos-fatura" style="width:${posPct}%">${posPct > 5 ? posPct+'%' : ''}</div>
      <div class="dev-segment dev-sem-oc" style="width:${semPct}%">${semPct > 5 ? semPct+'%' : ''}</div>
    `;
    document.getElementById('devLegend').innerHTML = `
      <div class="dev-legend-item"><div class="dev-legend-dot" style="background:#22c55e"></div>${t('Compra regular')} (${regPct}%)</div>
      <div class="dev-legend-item"><div class="dev-legend-dot" style="background:#f59e0b"></div>${t('OC pós-fatura')} (${posPct}%)</div>
      <div class="dev-legend-item"><div class="dev-legend-dot" style="background:#ef4444"></div>${t('Nota sem OC')} (${semPct}%)</div>
    `;
  } catch (err) {
    console.error('loadDeviations error:', err);
  }
}

async function loadAttention() {
  try {
    const data = await fetch(`${API}/api/performance/attention?${getFilters()}`).then(r=>r.json());
  const list = document.getElementById('attentionList');
  const items = [];
  if (data.req_pending && data.req_pending.qty > 0) {
    items.push({
      msg: t('Requisições aguardando OC há mais de 5 dias'),
      qty: data.req_pending.qty,
      pct_qty: data.req_pending.pct_qty,
      val: data.req_pending.valor,
      pct_val: data.req_pending.pct_valor,
      drill: 'req'
    });
  }
  if (data.pos_fatura && data.pos_fatura.qty > 0) {
    items.push({
      msg: t('OCs aprovadas após fatura'),
      qty: data.pos_fatura.qty,
      pct_qty: data.pos_fatura.pct_qty,
      val: data.pos_fatura.valor,
      pct_val: data.pos_fatura.pct_valor,
      govLink: 'pos_fatura'
    });
  }
  if (data.decentral && data.decentral.qty > 0) {
    items.push({
      msg: t('OCs descentralizadas acima de R$30.000'),
      qty: data.decentral.qty,
      pct_qty: data.decentral.pct_qty,
      val: data.decentral.valor,
      pct_val: data.decentral.pct_valor,
      govLink: 'decentral'
    });
  }
  if (data.oc_90 && data.oc_90.qty > 0) {
    items.push({
      msg: t('OCs abertas há mais de 90 dias'),
      qty: data.oc_90.qty,
      pct_qty: data.oc_90.pct_qty,
      val: data.oc_90.valor,
      pct_val: data.oc_90.pct_valor,
      govLink: 'oc_90'
    });
  }
  if (data.blanket_old && data.blanket_old.qty > 0) {
    items.push({
      msg: t('Acordos de Compra abertos há mais de 180 dias'),
      qty: data.blanket_old.qty,
      pct_qty: data.blanket_old.pct_qty,
      val: data.blanket_old.valor,
      pct_val: data.blanket_old.pct_valor,
      govLink: 'blanket_old'
    });
  }
  if (data.sem_oc && data.sem_oc.qty > 0) {
    items.push({
      msg: t('Notas sem OCs'),
      qty: data.sem_oc.qty,
      pct_qty: data.sem_oc.pct_qty,
      val: data.sem_oc.valor,
      pct_val: data.sem_oc.pct_valor,
      govLink: 'sem_oc'
    });
  }
  let html = `<table class="att-table">
    <thead><tr><th>${t('Alerta')}</th><th>${t('Qtd')}</th><th>${t('Valor')}</th><th></th></tr></thead>
    <tbody>`;
  html += items.map(i => {
    const drillAttr = i.drill ? `onclick="drillDown('${i.drill}')"` : (i.govLink ? `onclick="window.location.href='governanca.html?exc_type=${i.govLink}'"` : '');
    const _loc = typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR';
    const qtyStr = i.qty != null ? i.qty.toLocaleString(_loc) : '--';
    const pctQtyVal = i.pct_qty != null ? i.pct_qty : null;
    const pctQtyStr = pctQtyVal != null ? (pctQtyVal < 0.1 && pctQtyVal > 0 ? '<0.1%' : pctQtyVal.toFixed(1) + '%') : '';
    const valStr = i.val != null ? fmt(i.val) : '--';
    const pctValNum = i.pct_val != null ? i.pct_val : (i.pct_qty == null ? i.pct : null);
    const pctValStr = pctValNum != null ? (pctValNum < 0.1 && pctValNum > 0 ? '<0.1%' : pctValNum.toFixed(1) + '%') : '';

    const qtyCell = `
      <td class="att-qty">
        <div class="att-num">${qtyStr}</div>
        ${pctQtyStr ? `<div class="att-sub-pct">${pctQtyStr}</div>` : ''}
      </td>`;
    const valCell = `
      <td class="att-money">
        <div class="att-num">${valStr}</div>
        ${pctValStr ? `<div class="att-sub-pct">${pctValStr}</div>` : ''}
      </td>`;
    const drillIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;
    const linkBtn = i.govLink ? `<td><span class="att-drill" title="Ver detalhes em Governança">${drillIcon}</span></td>` : (i.drill ? `<td><span class="att-drill" title="Ver detalhes">${drillIcon}</span></td>` : '<td></td>');
    return `<tr ${drillAttr}><td>${i.msg}</td>${qtyCell}${valCell}${linkBtn}</tr>`;
  }).join('');
  html += '</tbody></table>';

  list.innerHTML = html;

  // Price increase alerts (table) - based on saving_total
  _priceAlertsData = (data && data.price_alerts) || [];
  renderPriceAlertsTable();
  } catch (err) {
    console.error('loadAttention error:', err);
  }
}

async function drillDown(type) {
  if (type === 'req') {
    document.getElementById('modalTitle').textContent = t('Requisições Aguardando OC (>5 dias)');
    const data = await fetch(`${API}/api/performance/req-pending-detail`).then(r=>r.json());
    let html = '<table class="orders-table"><thead><tr><th>Requisição</th><th>Descrição</th><th>Requisitante</th><th>Empresa</th><th>Dt. Aprovação</th><th>Valor</th><th>Dias Espera</th></tr></thead><tbody>';
    data.forEach(r => {
      html += `<tr><td>${r.REQUISICAO||''}</td><td>${r.DESCRICAO_REQ||''}</td><td>${r.REQUISITANTE||''}</td><td>${r.EMPRESA||''}</td><td>${r.DT_APROVACAO||''}</td><td>${fmt(r.VALOR_REQUISICAO)}</td><td style="color:#ef4444;font-weight:700">${r.dias_espera}</td></tr>`;
    });
    html += '</tbody></table>';
    document.getElementById('modalBody').innerHTML = html;
    document.getElementById('modalOverlay').classList.add('active');
  }
}

function closeModal() { document.getElementById('modalOverlay').classList.remove('active'); }
document.getElementById('modalOverlay').addEventListener('click', e => { if (e.target === e.currentTarget) closeModal(); });



function toggleAdvFilters(){const b=document.getElementById('advFiltersBar'),btn=document.getElementById('btnAdvFilters');if(b.style.display==='none'){b.style.display='flex';btn.style.borderColor='rgba(59,130,246,.45)';btn.style.color='#60a5fa';}else{b.style.display='none';btn.style.borderColor='rgba(100,116,139,.35)';btn.style.color='#94a3b8';}}
function loadAll() {
  return Promise.allSettled([loadKPIs(), loadSpendYoY(), loadDiscountChart(), loadLeadTime(), loadAttention()]);
}

function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  loadSpendYoY();
  loadDiscountChart();
}

/* ── Price Alerts Table ── */
let _priceAlertsData = [], _paSortCol = 'saving_total', _paSortDir = 'DESC';
let _paHeaderFilters = JSON.parse(localStorage.getItem('tbl_filter_perf_pa') || '{}');
const PA_COLS = [
  {key:'ds_item', label:'Ds Item', w:'140px'},
  {key:'nome_fornecedor', label:'Nome Fornecedor', w:'130px'},
  {key:'local_fornecedor', label:'Local Forn.', w:'120px'},
  {key:'preco_anterior', label:'Preço Ant', w:'90px'},
  {key:'preco_atual', label:'Preço Atual', w:'90px'},
  {key:'pct_var', label:'Var %', w:'70px'},
  {key:'saving_total', label:'Impacto', w:'95px'},
  {key:'data_anterior', label:'Dt Lanç. Ant', w:'95px'},
  {key:'data_atual', label:'Dt Lanç. Atual', w:'95px'},
  {key:'nf_anterior', label:'NF Ant', w:'100px'},
  {key:'nf_atual', label:'NF Atual', w:'100px'}
];

function getFilteredPriceAlerts() {
  return TableColumnFilter.filterData(_priceAlertsData, _paHeaderFilters, (r, k) => {
    if (k === 'local_fornecedor') return _fmtCNPJ(r.local_fornecedor);
    if (k === 'data_anterior') return _fmtDateBR(r.data_anterior);
    if (k === 'data_atual') return _fmtDateBR(r.data_atual);
    if (k === 'preco_anterior') return r.preco_anterior;
    if (k === 'preco_atual') return r.preco_atual;
    if (k === 'saving_total') return r.saving_total;
    if (k === 'pct_var') return r.pct_var;
    return r[k];
  });
}

function openPaFilter(e, colKey, colLabel) {
  TableColumnFilter.open(e, colKey, colLabel, _paHeaderFilters[colKey], (col, cfg) => {
    if (cfg && cfg.val) { _paHeaderFilters[col] = cfg; }
    else { delete _paHeaderFilters[col]; }
    try { localStorage.setItem('tbl_filter_perf_pa', JSON.stringify(_paHeaderFilters)); } catch(e){}
    renderPriceAlertsTable();
  });
}
window.openPaFilter = openPaFilter;

function _fmtCNPJ(v) {
  if (!v) return '\u2014';
  const s = String(v).replace(/\D/g, '');
  if (s.length === 14) return s.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
  if (s.length === 11) return s.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4');
  return String(v);
}

function _fmtDateBR(v) {
  if (!v) return '\u2014';
  const s = String(v).trim();
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : s;
}

function _fmtPreco(val, otherVal) {
  // Show more decimals when both prices round to the same at 2 decimals
  if (val == null) return '\u2014';
  const n = Number(val);
  const o = otherVal != null ? Number(otherVal) : null;
  let decimals = 2;
  if (o != null) {
    const r2v = n.toFixed(2), r2o = o.toFixed(2);
    if (r2v === r2o) {
      decimals = 4;
      const r4v = n.toFixed(4), r4o = o.toFixed(4);
      if (r4v === r4o) decimals = 6;
    }
  }
  return 'R$ ' + n.toLocaleString(typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR',{minimumFractionDigits:decimals,maximumFractionDigits:decimals});
}

function renderPriceAlertsTable() {
  const sortSvg = `<span class="pa-sort-icon"><svg class="arr-up" width="7" height="4" viewBox="0 0 8 5"><path d="M4 0L8 5H0z" fill="currentColor"/></svg><svg class="arr-down" width="7" height="4" viewBox="0 0 8 5"><path d="M4 5L0 0h8z" fill="currentColor"/></svg></span>`;
  const filtered = getFilteredPriceAlerts();
  // Sort data
  const sorted = [...filtered].sort((a,b) => {
    let va = a[_paSortCol], vb = b[_paSortCol];
    if (va == null) va = ''; if (vb == null) vb = '';
    if (typeof va === 'number' && typeof vb === 'number') return _paSortDir === 'ASC' ? va - vb : vb - va;
    return _paSortDir === 'ASC' ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
  });
  // Header
  document.getElementById('paHead').innerHTML = '<tr>' + PA_COLS.map(d => {
    let cls = '';
    if (_paSortCol === d.key) cls = _paSortDir === 'ASC' ? 'sort-asc' : 'sort-desc';
    const isFiltered = !!_paHeaderFilters[d.key];
    if (isFiltered) cls += ' th-filtered';
    const filterBtn = typeof TableColumnFilter !== 'undefined' ? TableColumnFilter.renderBtn(d.key, d.label, isFiltered, `openPaFilter(event, '${d.key}', '${d.label.replace(/'/g, "\\\\'")}')`) : '';
    return `<th class="${cls}" style="width:${d.w};min-width:50px;" onclick="_paSortClick('${d.key}')"><div class="th-content"><span>${t(d.label)}</span>${sortSvg}${filterBtn}</div><div class="pa-col-resizer" onmousedown="_paStartResize(event,this)" onclick="event.stopPropagation()"></div></th>`;
  }).join('') + '</tr>';
  // Body
  if (!sorted.length) {
    document.getElementById('paBody').innerHTML = `<tr><td colspan="11" style="text-align:center;color:var(--fr-txt-soft);padding:1.5rem;">${t('Nenhum alerta de preço no período')}</td></tr>`;
    return;
  }
  const copyBtnSvg = `<svg width='9' height='9' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><rect x='9' y='9' width='13' height='13' rx='2'/><path d='M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1'/></svg>`;
  document.getElementById('paBody').innerHTML = sorted.map(r => {
    const precoAnt = _fmtPreco(r.preco_anterior, r.preco_atual);
    const precoAtual = _fmtPreco(r.preco_atual, r.preco_anterior);
    const impacto = r.saving_total != null ? '+' + fmt(Math.abs(r.saving_total)) : '\u2014';
    const pctVar = r.pct_var != null ? '+' + Math.abs(r.pct_var).toFixed(Math.abs(r.pct_var) < 0.1 ? 2 : 1) + '%' : '\u2014';
    const nfAnt = r.nf_anterior || '\u2014';
    const nfAtual = r.nf_atual || '\u2014';
    const nfAntBtn = r.nf_anterior ? `<button data-nf="${r.nf_anterior}" onclick="copyNF(this,this.dataset.nf)" class="btn-copy-nf">${copyBtnSvg} ${r.nf_anterior}</button>` : '\u2014';
    const nfAtualBtn = r.nf_atual ? `<button data-nf="${r.nf_atual}" onclick="copyNF(this,this.dataset.nf)" class="btn-copy-nf">${copyBtnSvg} ${r.nf_atual}</button>` : '\u2014';
    const localForn = _fmtCNPJ(r.local_fornecedor);
    return `<tr>
      <td style="max-width:140px;overflow:hidden;text-overflow:ellipsis" title="${(r.ds_item||'')}${r.codigo_item ? ' (Cód: ' + r.codigo_item + ')' : ''}">${r.ds_item||'\u2014'}</td>
      <td style="max-width:130px;overflow:hidden;text-overflow:ellipsis" title="${(r.nome_fornecedor||'')}">${r.nome_fornecedor||'\u2014'}</td>
      <td style="max-width:120px;overflow:hidden;text-overflow:ellipsis" title="${r.local_fornecedor ? (typeof t !== 'undefined' ? t('Local Fornecedor') : 'Local Fornecedor') + ': ' + r.local_fornecedor : ''}">${localForn}</td>
      <td>${precoAnt}</td>
      <td>${precoAtual}</td>
      <td><span class="val-pct">${pctVar}</span></td>
      <td class="val-neg">${impacto}</td>
      <td>${_fmtDateBR(r.data_anterior)}</td>
      <td>${_fmtDateBR(r.data_atual)}</td>
      <td>${nfAntBtn}</td>
      <td>${nfAtualBtn}</td>
    </tr>`;
  }).join('');
}

function _paSortClick(col) {
  if (_paSortCol === col) _paSortDir = _paSortDir === 'ASC' ? 'DESC' : 'ASC';
  else { _paSortCol = col; _paSortDir = 'DESC'; }
  renderPriceAlertsTable();
}

// Column resize for price alerts table
let _paResizeTh = null, _paStartX = 0, _paStartW = 0;
function _paStartResize(e, handle) {
  e.stopPropagation(); e.preventDefault();
  _paResizeTh = handle.parentElement;
  _paStartX = e.pageX;
  _paStartW = _paResizeTh.offsetWidth;
  handle.classList.add('resizing');
  document.addEventListener('mousemove', _paDoResize);
  document.addEventListener('mouseup', _paStopResize);
}
function _paDoResize(e) {
  if (!_paResizeTh) return;
  const nw = Math.max(50, _paStartW + (e.pageX - _paStartX) / (window.dnaScale ? window.dnaScale() : 1));
  _paResizeTh.style.width = nw+'px'; _paResizeTh.style.minWidth = nw+'px'; _paResizeTh.style.maxWidth = nw+'px';
  const idx = Array.from(_paResizeTh.parentElement.children).indexOf(_paResizeTh);
  document.querySelectorAll('#paBody tr').forEach(tr => {
    const td = tr.children[idx];
    if(td){td.style.width=nw+'px';td.style.minWidth=nw+'px';td.style.maxWidth=nw+'px';}
  });
}
function _paStopResize() {
  if(_paResizeTh){const h=_paResizeTh.querySelector('.pa-col-resizer');if(h)h.classList.remove('resizing');}
  _paResizeTh=null; document.removeEventListener('mousemove',_paDoResize); document.removeEventListener('mouseup',_paStopResize);
}

// XLSX Export for price alerts
document.getElementById('btnExportAlerts').addEventListener('click', () => {
  const dataToExport = getFilteredPriceAlerts();
  if(!dataToExport.length) return;
  const header = PA_COLS.map(d=>t(d.label));
  const rows = dataToExport.map(r => [
    r.ds_item||'', r.nome_fornecedor||'', r.local_fornecedor||'',
    r.preco_anterior!=null?Number(r.preco_anterior):null,
    r.preco_atual!=null?Number(r.preco_atual):null,
    r.pct_var!=null?Number(r.pct_var).toFixed(1)+'%':null,
    r.saving_total!=null?Number(r.saving_total):null,
    _fmtDateBR(r.data_anterior), _fmtDateBR(r.data_atual),
    r.nf_anterior||'', r.nf_atual||''
  ]);
  const wsData = [header, ...rows];
  const ws = XLSX.utils.aoa_to_sheet(wsData);
  const hdrStyle = {font:{bold:true,color:{rgb:'FFFFFF'},sz:10},fill:{fgColor:{rgb:'1E40AF'}},alignment:{horizontal:'center'}};
  PA_COLS.forEach((_,i) => { const c=XLSX.utils.encode_cell({r:0,c:i}); if(ws[c]) ws[c].s=hdrStyle; });
  ws['!cols'] = PA_COLS.map((d,i)=>{let mx=d.label.length;rows.slice(0,100).forEach(r=>{const v=String(r[i]||'');if(v.length>mx)mx=v.length;});return{wch:Math.min(Math.max(mx+2,8),40)};});
  ws['!autofilter']={ref:XLSX.utils.encode_range({s:{r:0,c:0},e:{r:wsData.length-1,c:PA_COLS.length-1}})};
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, t('Alertas Preço'));
  XLSX.writeFile(wb, 'alertas_preco.xlsx');
});

// Init
const savedTheme = localStorage.getItem('theme');
if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);

let filtersPanel = null;
function initFilters() {
  const cy = String(new Date().getFullYear());
  const cm = String(new Date().getMonth() + 1);

  const MESES_OPCOES = [
    { v: '1', t: '01 - Jan' },
    { v: '2', t: '02 - Fev' },
    { v: '3', t: '03 - Mar' },
    { v: '4', t: '04 - Abr' },
    { v: '5', t: '05 - Mai' },
    { v: '6', t: '06 - Jun' },
    { v: '7', t: '07 - Jul' },
    { v: '8', t: '08 - Ago' },
    { v: '9', t: '09 - Set' },
    { v: '10', t: '10 - Out' },
    { v: '11', t: '11 - Nov' },
    { v: '12', t: '12 - Dez' }
  ];

  const defs = [
    { id: 'fEmpresa', key: 'empresa', rotulo: 'Empresa', tipo: 'multi', opcoes: ['BB','BQ'], padrao: ['BB','BQ'] },
    { id: 'fAno', key: 'ano', rotulo: 'Ano', tipo: 'unico', opcoes: [cy, String(Number(cy)-1)], padrao: cy },
    { id: 'fMes', key: 'mes', rotulo: 'Mês', tipo: 'multi', opcoes: MESES_OPCOES, padrao: [cm] },
    { id: 'fGrupo', key: 'grupo_compras', rotulo: 'Direto/Indireto', tipo: 'multi', opcoes: [] },
    { id: 'fFornecedor', key: 'fornecedor', rotulo: 'Fornecedor', tipo: 'multi', opcoes: [] },
    { id: 'fTipoNF', key: 'tipo_nf', rotulo: 'Tipo NF', tipo: 'multi', opcoes: ['com_oc','sem_oc'] },
    { id: 'fCentralizado', key: 'centralizado', rotulo: 'Centralizado', tipo: 'multi', opcoes: ['SIM','NÃO'] },
    { id: 'fFornNegociavel', key: 'is_fornecedor_nao_negociavel', rotulo: 'Forn. Negociável', tipo: 'multi', opcoes: ['NEGOCIAVEL', 'NÃO NEGOCIAVEL'], padrao: ['NEGOCIAVEL'] },
    { id: 'fFornSemOC', key: 'is_fornecedor_sem_oc', rotulo: 'Forn. sem OC', tipo: 'multi', opcoes: ['COM ATUAÇÃO', 'SEM OC'], padrao: ['COM ATUAÇÃO'] }
  ];

  filtersPanel = new DNAFiltersPanel({
    layoutId: 'appLayout',
    resumoId: 'fpResumo',
    chipsId: 'fpChips',
    limparTudoId: 'fpLimparTudo',
    abrirGavetaId: 'fpAbrirGaveta',
    lateralId: 'fpLateral',
    trilhoId: 'fpExpandir',
    trilhoContadorId: 'fpTrilhoContador',
    trilhoTextoId: 'fpTrilhoTexto',
    abertoId: 'fpAberto',
    tituloLateralId: 'fpTituloLateral',
    lateralContadorId: 'fpLateralContador',
    recolherId: 'fpRecolher',
    corpoLateralId: 'fpCorpoLateral',
    limparId: 'fpLimpar',
    aplicarId: 'fpAplicar',
    gavetaId: 'fpGaveta',
    tituloGavetaId: 'fpTituloGaveta',
    fecharGavetaId: 'fpFecharGaveta',
    corpoGavetaId: 'fpCorpoGaveta',
    gavetaLimparId: 'fpGavetaLimpar',
    gavetaAplicarId: 'fpGavetaAplicar',
    estadoInicial: 'recolhido',
    filtros: defs,
    onApply: () => aplicarFiltros(loadAll)
  });

  _filtersReady = true;

  // Carrega imediatamente os dados com paridade total a PROD
  aplicarFiltros(loadAll);

  // Carrega metadados de filtros da API em background (não-bloqueante)
  const fetchNotas = window.fetchCachedFilterData ? window.fetchCachedFilterData(`${API}/api/filters/notas`) : fetch(`${API}/api/filters/notas`).then(r=>r.json());
  fetchNotas.then(data => {
    if (!data || data.error) return;
    const updates = [];
    if (data.empresas && data.empresas.length) updates.push({ id: 'fEmpresa', opcoes: data.empresas });
    if (data.anos && data.anos.length) updates.push({ id: 'fAno', opcoes: data.anos.map(String) });
    if (data.grupos && data.grupos.length) updates.push({ id: 'fGrupo', opcoes: data.grupos });
    if (data.fornecedores && data.fornecedores.length) updates.push({ id: 'fFornecedor', opcoes: data.fornecedores });
    if (updates.length && filtersPanel) filtersPanel.updateDefinitions(updates);
  }).catch(e => console.warn('Erro ao atualizar filtros notas:', e));

  const fetchAdv = window.fetchCachedFilterData ? window.fetchCachedFilterData(`${API}/api/filters/advanced`) : fetch(`${API}/api/filters/advanced`).then(r=>r.json());
  fetchAdv.then(advData => {
    if (!advData || advData.error) return;
    const advDefs = [];
    if(advData.macro_categoria) advDefs.push({ id: 'fMacroCategoria', key: 'macro_categoria', rotulo: 'Categoria', tipo: 'multi', opcoes: advData.macro_categoria });
    if(advData.dias) advDefs.push({ id: 'fDia', key: 'dia', rotulo: 'Dia', tipo: 'multi', opcoes: advData.dias.map(String) });
    if(advData.descricao_item) advDefs.push({ id: 'fDescItem', key: 'descricao_item', rotulo: 'Descrição Item', tipo: 'multi', opcoes: advData.descricao_item });
    if(advData.unidade) advDefs.push({ id: 'fUnidade', key: 'unidade', rotulo: 'Unidade', tipo: 'multi', opcoes: advData.unidade });
    if(advData.status_pagamento) advDefs.push({ id: 'fStatusPgto', key: 'status_pagamento', rotulo: 'Status Pagamento', tipo: 'multi', opcoes: advData.status_pagamento });
    if(advData.tipo_nf) advDefs.push({ id: 'fTipoNFAdv', key: 'tipo_nf', rotulo: 'Tipo NF (Adv)', tipo: 'multi', opcoes: advData.tipo_nf });
    if(advData.tipo_linha) advDefs.push({ id: 'fTipoLinha', key: 'tipo_linha', rotulo: 'Tipo Linha', tipo: 'multi', opcoes: advData.tipo_linha });
    if(advData.numero_ri) advDefs.push({ id: 'fNumeroRI', key: 'numero_ri', rotulo: 'Número RI', tipo: 'multi', opcoes: advData.numero_ri });
    if(advData.nota_fiscal) advDefs.push({ id: 'fNotaFiscal', key: 'nota_fiscal', rotulo: 'Nota Fiscal', tipo: 'multi', opcoes: advData.nota_fiscal });
    if(advData.numero_oc) advDefs.push({ id: 'fNumeroOC', key: 'numero_oc', rotulo: 'Número OC', tipo: 'multi', opcoes: advData.numero_oc });
    if(advData.ds_item) advDefs.push({ id: 'fDsItem', key: 'ds_item', rotulo: 'DS Item', tipo: 'multi', opcoes: advData.ds_item });
    if(advData.codigo_item) advDefs.push({ id: 'fCodigoItem', key: 'codigo_item', rotulo: 'Código Item', tipo: 'multi', opcoes: advData.codigo_item });
    advDefs.push({ id: 'fFornEspecial', key: 'is_fornecedor_especial', rotulo: 'Forn. Especial', tipo: 'multi', opcoes: ['ESPECIAL', 'NÃO ESPECIAL'] });
    if (advDefs.length && filtersPanel) filtersPanel.updateDefinitions(advDefs);
  }).catch(()=>{});
}
window.addEventListener('themeChanged', () => {
  if (typeof renderPerfYoYChart === 'function') renderPerfYoYChart();
  if (typeof renderDiscountChart === 'function') renderDiscountChart();
});
initFilters();
