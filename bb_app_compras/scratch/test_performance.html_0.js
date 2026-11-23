
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
    document.getElementById('dSpend').innerHTML = `<span style="color:${color}">${arrow} ${fmtPct(Math.abs(pct))} ${vsLabel}</span>`;
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
  document.getElementById('dCentral').innerHTML = `<span style="color:${centralUp?'#22c55e':'#ef4444'}">${centralUp?'\u2191':'\u2193'} ${fmtPp(centralDiff)} ${t('vs meta')}</span>`;
  // Payment term semantic (border stays amber, only value color changes)
  const prazoVal = c.avg_payment_term || 0;
  const prazoColor = prazoVal >= 60 ? '#22c55e' : prazoVal >= 50 ? '#fbbf24' : '#f87171';
  document.getElementById('vPrazo').style.color = prazoColor;
  // Delta vs meta for Prazo (meta = 60 dias)
  const prazoDiff = Math.round(prazoVal - 60);
  const prazoUp = prazoDiff >= 0;
  document.getElementById('dPrazo').innerHTML = `<span style="color:${prazoUp?'#22c55e':'#ef4444'}">${prazoUp?'\u2191':'\u2193'} ${prazoUp?'+':''}${prazoDiff} ${t('dias vs meta')}</span>`;
}

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
  if (btnS) {
    btnS.classList.toggle('active', metric === 'spend');
  }
  if (btnC) {
    btnC.classList.toggle('active', metric === 'central');
  }
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

function renderPerfYoYChart() {
  if (!_perfYoYRawData) return;
  const isSpend = currentPerfYoYMetric === 'spend';

  // Only limit months to current month when current year is selected; past years show all 12
  const _selYears = filters.fAno ? filters.fAno.getSelected() : [];
  const _cy = String(new Date().getFullYear());
  const activeYear = (_selYears && _selYears.length === 1) ? _selYears[0] : (_selYears && _selYears.length > 1 ? _selYears.join('/') : _cy);
  const _includesCY = _selYears.length === 0 || _selYears.includes(_cy);
  const currentMonth = _includesCY ? new Date().getMonth() : 11; // 0=Jan
  const filtered = _perfYoYRawData.filter(d => parseInt(d.mes) - 1 <= currentMonth);
  const labels = filtered.map(d => MONTHS[parseInt(d.mes) - 1]);
  const lastIdx = filtered.length - 1;

  // Legend elements
  const legCurColor = document.getElementById('legYoYColorCur');
  const legCurLbl = document.getElementById('legYoYLblCur');
  const legPrevLbl = document.getElementById('legYoYLblPrev');
  const legMeta = document.getElementById('legYoYMeta');

  let currentData, prevData, yoyPcts, bgCur, currentDatasetLabel, prevDatasetLabel;

  if (isSpend) {
    if (legCurColor) legCurColor.style.background = '#3b82f6';
    if (legCurLbl) legCurLbl.textContent = t('Spend Líquido');
    if (legPrevLbl) legPrevLbl.textContent = t('Spend Líq. Ano Anterior');
    if (legMeta) legMeta.style.display = 'none';

    currentData = filtered.map(d => d.current_spend);
    prevData = filtered.map(d => d.prev_spend);
    currentDatasetLabel = t('Spend Líquido');
    prevDatasetLabel = t('Spend Líq. Ano Anterior');

    const totalCur = currentData.reduce((a, b) => a + (b || 0), 0);
    const totalPrev = prevData.reduce((a, b) => a + (b || 0), 0);
    const pctVar = totalPrev ? ((totalCur - totalPrev) / totalPrev * 100).toFixed(1) : 0;
    const direction = pctVar > 0 ? t('acima') : t('abaixo');
    const signPct = parseFloat(pctVar) >= 0 ? '+' : '';
    document.getElementById('ttlSpendYoY').textContent = typeof tt !== 'undefined'
      ? tt('Em {ano}, o Spend Líquido está em {val} ({pct}% {dir} do mesmo período do ano anterior)', {ano: activeYear, val: fmt(totalCur), pct: `${signPct}${pctVar}`, dir: direction})
      : `Em ${activeYear}, o Spend Líquido está em ${fmt(totalCur)} (${signPct}${pctVar}% ${direction} do mesmo período do ano anterior)`;

    bgCur = currentData.map((_, i) => i === lastIdx ? '#3b82f6' : 'rgba(59,130,246,0.4)');
    yoyPcts = currentData.map((c, i) => {
      const p = prevData[i] || 0;
      if (!p) return null;
      return ((c - p) / p * 100);
    });
  } else {
    // Centralização
    if (legCurColor) legCurColor.style.background = 'linear-gradient(135deg, #22c55e, #ef4444)';
    if (legCurLbl) legCurLbl.textContent = t('% Centralização');
    if (legPrevLbl) legPrevLbl.textContent = t('% Centraliz. Ano Anterior');
    if (legMeta) legMeta.style.display = 'inline-flex';

    currentData = filtered.map(d => d.current_central_pct != null ? d.current_central_pct : null);
    prevData = filtered.map(d => d.prev_central_pct != null ? d.prev_central_pct : null);
    currentDatasetLabel = t('% Centralização');
    prevDatasetLabel = t('% Centraliz. Ano Anterior');

    const totalCurCentralSpend = filtered.reduce((a, d) => a + (d.current_central_spend || 0), 0);
    const totalCurSpend = filtered.reduce((a, d) => a + (d.current_spend || 0), 0);
    const totalCurCentralPct = totalCurSpend ? (totalCurCentralSpend / totalCurSpend * 100) : 0;

    const totalPrevCentralSpend = filtered.reduce((a, d) => a + (d.prev_central_spend || 0), 0);
    const totalPrevSpend = filtered.reduce((a, d) => a + (d.prev_spend || 0), 0);
    const totalPrevCentralPct = totalPrevSpend ? (totalPrevCentralSpend / totalPrevSpend * 100) : 0;

    const diffPP = totalCurCentralPct - totalPrevCentralPct;
    const dirPP = diffPP >= 0 ? t('acima') : t('abaixo');

    document.getElementById('ttlSpendYoY').textContent = typeof tt !== 'undefined'
      ? tt('Em {ano}, a Centralização está em {val} ({diff} {dir} do mesmo período do ano anterior)', {ano: activeYear, val: fmtPct(totalCurCentralPct), diff: fmtPp(diffPP), dir: dirPP})
      : `Em ${activeYear}, a Centralização está em ${fmtPct(totalCurCentralPct)} (${fmtPp(diffPP)} ${dirPP} do mesmo período do ano anterior)`;

    // Conditional colors based on meta >= 80% (palette aligned with chartDiscount)
    bgCur = currentData.map((val, i) => {
      if (val == null) return 'rgba(100,116,139,0.2)';
      const meetsMeta = val >= 80;
      const isCurMonth = (i === lastIdx);
      if (meetsMeta) {
        return isCurMonth ? 'rgba(22,163,74,1)' : 'rgba(22,163,74,0.65)';
      } else {
        return isCurMonth ? 'rgba(220,38,38,1)' : 'rgba(220,38,38,0.55)';
      }
    });

    yoyPcts = currentData.map((c, i) => {
      const p = prevData[i];
      if (c == null || p == null) return null;
      return (c - p);
    });
  }

  if (chartSpend) chartSpend.destroy();
  const ctx = document.getElementById('chartSpendYoY').getContext('2d');

  // Custom plugin to draw labels:
  // - Current year value on top of bar (formatted currency for Spend, % for Centralization)
  // - Difference vs previous year at base of column inside high-contrast badge (% for Spend, pp for Centralization)
  const yoyLabelPlugin = {
    id: 'yoyLabels',
    afterDatasetsDraw(chart) {
      const meta = chart.getDatasetMeta(0);
      const ctxC = chart.ctx;
      const isLight = document.documentElement.getAttribute('data-theme') === 'light';
      ctxC.save();

      meta.data.forEach((bar, i) => {
        const cVal = currentData[i];
        if (cVal != null && cVal > 0) {
          // 1. Top label: Current year value (bold on current month, clean neutral text)
          ctxC.font = i === lastIdx ? '800 10.5px system-ui, -apple-system, sans-serif' : '600 9.5px system-ui, -apple-system, sans-serif';
          ctxC.textAlign = 'center';
          ctxC.textBaseline = 'bottom';
          ctxC.fillStyle = isLight ? '#1e293b' : '#f1f5f9';
          const topLabel = isSpend ? fmt(cVal) : fmtPct(cVal);
          ctxC.fillText(topLabel, bar.x, bar.y - 2);
        }

        // 2. Base label: Difference vs previous year (contrast background badge at base of column)
        const diffVal = yoyPcts[i];
        if (diffVal != null && isFinite(diffVal) && (bar.base - bar.y > 24)) {
          const arrow = diffVal >= 0 ? '\u2191' : '\u2193';
          const text = isSpend ? `${arrow}${fmtPct(Math.abs(diffVal))}` : `${arrow}${fmtPp(diffVal)}`;

          ctxC.font = '700 8.5px system-ui, -apple-system, sans-serif';
          const textWidth = ctxC.measureText(text).width;
          const badgeW = textWidth + 8;
          const badgeH = 13;
          const badgeX = bar.x - badgeW / 2;
          const badgeY = bar.base - badgeH - 3;

          // Background pill for contrast
          ctxC.beginPath();
          if (ctxC.roundRect) {
            ctxC.roundRect(badgeX, badgeY, badgeW, badgeH, 3);
          } else {
            ctxC.rect(badgeX, badgeY, badgeW, badgeH);
          }
          ctxC.fillStyle = isLight ? 'rgba(255, 255, 255, 0.92)' : 'rgba(15, 23, 42, 0.88)';
          ctxC.fill();
          ctxC.strokeStyle = isLight ? 'rgba(148, 163, 184, 0.35)' : 'rgba(148, 163, 184, 0.25)';
          ctxC.lineWidth = 0.8;
          ctxC.stroke();

          // Text inside badge
          let textColor;
          if (isSpend) {
            // For Spend: spending less (negative diff) is green (savings), spending more is red
            if (diffVal > 0.5) textColor = isLight ? '#dc2626' : '#f87171';
            else if (diffVal < -0.5) textColor = isLight ? '#16a34a' : '#4ade80';
            else textColor = isLight ? '#64748b' : '#94a3b8';
          } else {
            // For Centralization: higher centralization is green, lower is red
            if (diffVal > 0.5) textColor = isLight ? '#16a34a' : '#4ade80';
            else if (diffVal < -0.5) textColor = isLight ? '#dc2626' : '#f87171';
            else textColor = isLight ? '#64748b' : '#94a3b8';
          }

          ctxC.fillStyle = textColor;
          ctxC.textAlign = 'center';
          ctxC.textBaseline = 'middle';
          ctxC.fillText(text, bar.x, badgeY + badgeH / 2);
        }
      });
      ctxC.restore();
    }
  };

  // Target 80% line plugin for Centralization (subtle neutral dashed line without text label)
  const metaLinePlugin = {
    id: 'metaLineCentral',
    afterDraw(chart) {
      if (isSpend) return;
      const yScale = chart.scales.y;
      if (!yScale) return;
      const yPos = yScale.getPixelForValue(80);
      if (yPos == null || isNaN(yPos)) return;
      const ctxC = chart.ctx;
      const isLight = document.documentElement.getAttribute('data-theme') === 'light';
      ctxC.save();
      ctxC.beginPath();
      ctxC.setLineDash([4, 4]);
      ctxC.strokeStyle = isLight ? 'rgba(100, 116, 139, 0.45)' : 'rgba(148, 163, 184, 0.4)';
      ctxC.lineWidth = 1.2;
      ctxC.moveTo(chart.chartArea.left, yPos);
      ctxC.lineTo(chart.chartArea.right, yPos);
      ctxC.stroke();
      ctxC.restore();
    }
  };

  chartSpend = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: currentDatasetLabel,
          data: currentData,
          backgroundColor: bgCur,
          borderColor: 'transparent',
          borderWidth: 0,
          borderRadius: 3,
          barPercentage: 0.65
        },
        {
          label: prevDatasetLabel,
          data: prevData,
          backgroundColor: 'rgba(200,200,200,0.25)',
          borderRadius: 3,
          barPercentage: 0.65
        }
      ]
    },
    plugins: [yoyLabelPlugin, metaLinePlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 20, bottom: 4 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(c) {
              if (isSpend) return c.dataset.label + ': ' + fmt(c.raw);
              return c.dataset.label + ': ' + (c.raw != null ? c.raw.toFixed(1) + '%' : '--');
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          border: { display: false },
          ticks: {
            color: function(ctx) { return ctx.index === lastIdx ? getTickColor(true) : getTickColor(false); },
            font: function(ctx) { return ctx.index === lastIdx ? { size: 9, weight: '800' } : { size: 8.5, weight: '500' }; }
          }
        },
        y: {
          display: false,
          grace: isSpend ? '18%' : undefined,
          min: 0,
          max: isSpend ? undefined : 108
        }
      }
    }
  });
  syncFunnelRowHeight();
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
  const rightCard = document.getElementById('cardFunnel');
  const leftCard = document.getElementById('cardSpendYoY');
  const wrapChart = document.getElementById('wrapSpendYoY');
  if (!rightCard || !leftCard || !wrapChart) return;

  const targetH = rightCard.offsetHeight;
  if (!targetH || targetH < 60) return;

  leftCard.style.height = targetH + 'px';

  const header = leftCard.querySelector('.fr-chart-header-wrap');
  const headerH = header ? header.offsetHeight : 45;
  const pad = 24; // padding: 0.75rem top + 0.75rem bottom
  const chartH = Math.max(90, targetH - headerH - pad - 6);

  wrapChart.style.height = chartH + 'px';
  wrapChart.style.maxHeight = chartH + 'px';

  if (typeof chartSpend !== 'undefined' && chartSpend) {
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
  const data = await fetch(`${API}/api/performance/process-deviations?${getFilters()}`).then(r=>r.json());
  const d = data[0] || {};
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
}

async function loadAttention() {
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
  _priceAlertsData = data.price_alerts || [];
  renderPriceAlertsTable();
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
  const nw = Math.max(50, _paStartW + (e.pageX - _paStartX));
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

async function initFilters() {
  const data = await (window.fetchCachedFilterData ? window.fetchCachedFilterData(`${API}/api/filters/notas`) : fetch(`${API}/api/filters/notas`).then(r=>r.json()));
  filters.fEmpresa = new MultiSelect(document.getElementById('fEmpresa'), data.empresas || ['BB','BQ']);
  filters.fEmpresa.selected = new Set(['BB','BQ']); filters.fEmpresa.renderOptions(); filters.fEmpresa.updateLabel();
  filters.fAno = new MultiSelect(document.getElementById('fAno'), data.anos || []);
  filters.fMes = new MultiSelect(document.getElementById('fMes'), (data.meses || []).map(m => String(m)));
  filters.fGrupo = new MultiSelect(document.getElementById('fGrupo'), data.grupos || []);
  filters.fFornecedor = new MultiSelect(document.getElementById('fFornecedor'), data.fornecedores || []);
  filters.fTipoNF = new MultiSelect(document.getElementById('fTipoNF'), ['com_oc','sem_oc']);
  filters.fTipoNF.selected = new Set(['com_oc', 'sem_oc']); filters.fTipoNF.renderOptions(); filters.fTipoNF.updateLabel();
  if (document.getElementById('fFornNegociavel')) {
    filters.fFornNegociavel = new MultiSelect(document.getElementById('fFornNegociavel'), ['NEGOCIAVEL', 'NÃO NEGOCIAVEL']);
  }
  // Advanced filters (non-blocking, cached)
  (window.fetchCachedFilterData ? window.fetchCachedFilterData(`${API}/api/filters/advanced`) : fetch(`${API}/api/filters/advanced`).then(r=>r.json())).then(advData=>{
    if(document.getElementById('fMacroCategoria')) filters.fMacroCategoria = new MultiSelect(document.getElementById('fMacroCategoria'), advData.macro_categoria || []);
    if(document.getElementById('fDia')) filters.fDia = new MultiSelect(document.getElementById('fDia'), (advData.dias || []).map(d=>String(d)));
    if(document.getElementById('fNumeroRI')) filters.fNumeroRI = new MultiSelect(document.getElementById('fNumeroRI'), advData.numero_ri || []);
    if(document.getElementById('fNotaFiscal')) filters.fNotaFiscal = new MultiSelect(document.getElementById('fNotaFiscal'), advData.nota_fiscal || []);
    if(document.getElementById('fNumeroOC')) filters.fNumeroOC = new MultiSelect(document.getElementById('fNumeroOC'), advData.numero_oc || []);
    if(document.getElementById('fDsItem')) filters.fDsItem = new MultiSelect(document.getElementById('fDsItem'), advData.ds_item || []);
    if(document.getElementById('fCodigoItem')) filters.fCodigoItem = new MultiSelect(document.getElementById('fCodigoItem'), advData.codigo_item || []);
    if(document.getElementById('fDescItem')) filters.fDescItem = new MultiSelect(document.getElementById('fDescItem'), advData.descricao_item || []);
    if(document.getElementById('fCentralizado')) filters.fCentralizado = new MultiSelect(document.getElementById('fCentralizado'), advData.centralizado || []);
    if(document.getElementById('fUnidade')) filters.fUnidade = new MultiSelect(document.getElementById('fUnidade'), advData.unidade || []);
    if(document.getElementById('fStatusPgto')) filters.fStatusPgto = new MultiSelect(document.getElementById('fStatusPgto'), advData.status_pagamento || []);
    if(document.getElementById('fTipoNFAdv')) filters.fTipoNFAdv = new MultiSelect(document.getElementById('fTipoNFAdv'), advData.tipo_nf || []);
    if(document.getElementById('fTipoLinha')) filters.fTipoLinha = new MultiSelect(document.getElementById('fTipoLinha'), advData.tipo_linha || []);
    if(document.getElementById('fFornEspecial')) filters.fFornEspecial = new MultiSelect(document.getElementById('fFornEspecial'), ['ESPECIAL', 'NÃO ESPECIAL']);
    if(document.getElementById('fFornNegociavel') && !filters.fFornNegociavel) filters.fFornNegociavel = new MultiSelect(document.getElementById('fFornNegociavel'), ['NEGOCIAVEL', 'NÃO NEGOCIAVEL']);
    if (typeof FilterStateStore !== 'undefined') FilterStateStore.restore();
  }).catch(()=>{});
  // Pre-select current year + month
  const cy = String(new Date().getFullYear());
  if (filters.fAno.options.includes(cy)) { filters.fAno.selected = new Set([cy]); filters.fAno.renderOptions(); filters.fAno.updateLabel(); }
  const cm = String(new Date().getMonth() + 1);
  if (filters.fMes.options.includes(cm)) { filters.fMes.selected = new Set([cm]); filters.fMes.renderOptions(); filters.fMes.updateLabel(); }
  if (typeof FilterStateStore !== 'undefined') FilterStateStore.restore();
  _filtersReady = true;
  // Initial cascade + data load
  aplicarFiltros(loadAll);
}
window.addEventListener('themeChanged', () => {
  if (typeof renderPerfYoYChart === 'function') renderPerfYoYChart();
  if (typeof renderDiscountChart === 'function') renderDiscountChart();
});
initFilters();
