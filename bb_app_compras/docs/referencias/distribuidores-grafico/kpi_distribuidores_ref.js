'use strict';

/* RLS STRICT MODE: Nenhum dado simulado ou hardcoded.
   Todos os dados vêm exclusivamente da API /api/kpi com filtro RLS do Unity Catalog. */

let lastMonthlyIn = Array(12).fill(0);
let lastMonthlyMetaIn = Array(12).fill(0);
let lastMonthlyOut = Array(12).fill(0);
let lastMonthlyMetaOut = Array(12).fill(0);
let lastChartMode = 'sellin';
let lastMonthlyPositiv = Array(12).fill(0);
let lastMonthlyPositivPct = Array(12).fill(0);
let lastMonthlyPositivMeta = Array(12).fill(0);
let lastMonthlyTicketMedio = Array(12).fill(0);
let lastTotalBaseClientes = 0;
let lastDnaData = null;
let lastIsVolume = false;
const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

// Funcao auxiliar segura para obter valores selecionados de dropdowns sem quebrar caso ainda nao inicializados
function getSafeSelectedValues(id) {
  const el = document.getElementById(id);
  if (el && typeof el.getSelectedValues === 'function') {
    return el.getSelectedValues();
  }
  return [];
}

/* ── Renderiza cards do DNA de Vendas ── */
function renderDnaCards(dnaData) {
  if (!dnaData) return;
  lastDnaData = dnaData;
  const isVolume = document.getElementById('toggleValVol')?.checked || false;
  const el = (id) => document.getElementById(id);
  const fmtDna = (val) => {
    if (isVolume) {
      if (val >= 1000000) return `${(val/1000000).toFixed(1)}M DZ`;
      if (val >= 1000) return `${(val/1000).toFixed(1)}K DZ`;
      return `${Math.round(val)} DZ`;
    }
    if (val >= 1000000) return `R$ ${(val/1000000).toFixed(1)}M`;
    if (val >= 1000) return `R$ ${(val/1000).toFixed(1)}K`;
    return `R$ ${Math.round(val)}`;
  };
  function setDna(prefix, realized, target, metaLabel) {
    const pct = target > 0 ? ((realized / target) * 100) : 0;
    const diff = realized - target;
    const above = diff >= 0;
    const arrow = above ? '↑' : '↓';
    const sign = above ? '+' : '';
    if (el(prefix+'-val'))  el(prefix+'-val').textContent = fmtDna(realized);
    if (el(prefix+'-cmp')) {
      el(prefix+'-cmp').textContent = target > 0 ? `${arrow} vs ${metaLabel} ${sign}${(pct-100).toFixed(1)}%` : `vs ${metaLabel} --`;
      el(prefix+'-cmp').className = 'dna-compare ' + (target > 0 ? (above ? 'positive' : 'negative') : 'neutral');
    }
    if (el(prefix+'-meta')) el(prefix+'-meta').textContent = fmtDna(target);
    if (el(prefix+'-diff')) {
      el(prefix+'-diff').textContent = `${sign}${fmtDna(Math.abs(diff))}`;
      el(prefix+'-diff').className = 'dna-ft-value ' + (above ? 'positive' : 'negative');
    }
  }
  setDna('dna-si', dnaData.vlSellIn, dnaData.vlForecast, 'Forecast');
  setDna('dna-so', dnaData.vlSellOut, dnaData.vlMetaSellOut, 'Meta');
  setDna('dna-sia', dnaData.siAcum, dnaData.fcAcum, 'Forecast');
  setDna('dna-soa', dnaData.soAcum, dnaData.moAcum, 'Meta');
}
window.renderDnaCards = renderDnaCards;

/* ── Renderiza gráfico de barras de Positivação (REALIZADO vs META) & Linha de Ticket Médio ── */
function buildPositivChart(monthlyPositiv, monthlyPositivPct, totalBaseClientes, monthlyPositivMeta, monthlyTicketMedio) {
  const container = document.getElementById('positivChart');
  if (!container) return;

  if (monthlyPositiv && monthlyPositiv.length === 12) {
    lastMonthlyPositiv = monthlyPositiv;
  }
  if (monthlyPositivPct && monthlyPositivPct.length === 12) {
    lastMonthlyPositivPct = monthlyPositivPct;
  }
  if (monthlyPositivMeta && monthlyPositivMeta.length === 12) {
    lastMonthlyPositivMeta = monthlyPositivMeta;
  }
  if (monthlyTicketMedio && monthlyTicketMedio.length === 12) {
    lastMonthlyTicketMedio = monthlyTicketMedio;
  }
  if (typeof totalBaseClientes === 'number' && totalBaseClientes > 0) {
    lastTotalBaseClientes = totalBaseClientes;
  }

  const arr = (lastMonthlyPositiv && lastMonthlyPositiv.length === 12) ? lastMonthlyPositiv : Array(12).fill(0);
  const arrMeta = (lastMonthlyPositivMeta && lastMonthlyPositivMeta.length === 12) ? lastMonthlyPositivMeta : Array(12).fill(0);
  const arrTicket = (lastMonthlyTicketMedio && lastMonthlyTicketMedio.length === 12) ? lastMonthlyTicketMedio : Array(12).fill(0);

  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonthIdx = now.getMonth();

  const anoFilter = getSafeSelectedValues('select-ano');
  const selectedYear = (anoFilter.length === 1 && !isNaN(parseInt(anoFilter[0]))) ? parseInt(anoFilter[0]) : null;

  let maxMonthIdx = 11;
  if (!selectedYear || selectedYear >= currentYear) {
    maxMonthIdx = currentMonthIdx;
  } else {
    let lastWithData = -1;
    for (let m = 11; m >= 0; m--) {
      if ((arr[m] && arr[m] > 0) || (arrMeta[m] && arrMeta[m] > 0)) {
        lastWithData = m;
        break;
      }
    }
    maxMonthIdx = lastWithData >= 0 ? lastWithData : 11;
  }

  const visible = arr.slice(0, maxMonthIdx + 1);
  const visibleMeta = arrMeta.slice(0, maxMonthIdx + 1);
  const maxVal = Math.max(...visible, ...visibleMeta, 1);
  const suggestedMax = maxVal * 1.28;
  const totalPositiv = visible.reduce((a, b) => a + b, 0);
  const totalMeta = visibleMeta.reduce((a, b) => a + b, 0);

  const badgeEl = document.getElementById('positiv-chart-badge');
  if (badgeEl) {
    if (totalMeta > 0) {
      const diffPct = ((totalPositiv - totalMeta) / totalMeta) * 100;
      const isPositive = diffPct >= 0;
      badgeEl.className = isPositive ? 'badge-up' : 'badge-down';
      badgeEl.textContent = `${isPositive ? '↑ +' : '↓ -'}${Math.abs(diffPct).toFixed(1)}%`;
      const tipText = `Acumulado no Ano: Realizado ${totalPositiv.toLocaleString('pt-BR')} vs Meta ${totalMeta.toLocaleString('pt-BR')} clientes (${isPositive ? '+' : '-'}${Math.abs(diffPct).toFixed(1)}%)`;
      badgeEl.title = tipText;
      if (badgeEl.parentElement && badgeEl.parentElement.classList.contains('chart-kpi-pill')) {
        badgeEl.parentElement.title = tipText;
      }
    } else if (totalPositiv > 0) {
      badgeEl.className = 'badge-up';
      badgeEl.textContent = '↑ +100%';
      const tipText = `Acumulado no Ano: ${totalPositiv.toLocaleString('pt-BR')} clientes positivados (sem meta cadastrada)`;
      badgeEl.title = tipText;
      if (badgeEl.parentElement && badgeEl.parentElement.classList.contains('chart-kpi-pill')) {
        badgeEl.parentElement.title = tipText;
      }
    } else {
      badgeEl.className = 'badge-up';
      badgeEl.textContent = '0%';
      const tipText = 'Acumulado no Ano: Sem movimentação no período';
      badgeEl.title = tipText;
      if (badgeEl.parentElement && badgeEl.parentElement.classList.contains('chart-kpi-pill')) {
        badgeEl.parentElement.title = tipText;
      }
    }
  }

  let html = '';
  for (let i = 0; i <= maxMonthIdx; i++) {
    const v = arr[i] || 0;
    const vMeta = arrMeta[i] || 0;
    const h = Math.min(100, (v / suggestedMax) * 100).toFixed(1);
    const hMeta = Math.min(100, (vMeta / suggestedMax) * 100).toFixed(1);
    const tooltipRealizado = `Positivados (${MONTHS[i]}): ${v} clientes`;
    const tooltipMeta = `Meta Positivação (${MONTHS[i]}): ${vMeta} clientes`;

    // Cálculo do % de atingimento mês a mês (Positivados vs Meta)
    let pctPerfVal = 0;
    let pctPerfStr = '0%';
    let perfClass = 'perf-neutral';
    let tooltipPerf = `Atingimento (${MONTHS[i]}): Sem movimentação`;

    if (vMeta > 0 && v > 0) {
      pctPerfVal = Math.round((v / vMeta) * 100);
      pctPerfStr = `${pctPerfVal}%`;
      const isAbove = v >= vMeta;
      perfClass = isAbove ? 'perf-positive' : 'perf-negative';
      const diffPct = (((v - vMeta) / vMeta) * 100).toFixed(1);
      const sign = isAbove ? '+' : '';
      tooltipPerf = `Atingimento (${MONTHS[i]}): ${pctPerfVal}% (${sign}${diffPct}% vs meta) | Realizado: ${v} / Meta: ${vMeta} clientes`;
    } else if (v > 0 && vMeta === 0) {
      pctPerfVal = 100;
      pctPerfStr = '100%';
      perfClass = 'perf-positive';
      tooltipPerf = `Atingimento (${MONTHS[i]}): 100% | Realizado: ${v} clientes (Sem meta cadastrada)`;
    } else {
      pctPerfVal = 0;
      pctPerfStr = '0%';
      perfClass = 'perf-neutral';
      tooltipPerf = `Atingimento (${MONTHS[i]}): 0% | Realizado: ${v} / Meta: ${vMeta} clientes`;
    }

    // Badge de Ticket Médio mensal em HTML puro (clean e neutro)
    const tVal = arrTicket[i] || 0;
    const labelTicket = tVal >= 1000 ? `R$ ${(tVal / 1000).toFixed(1).replace('.', ',')}k` : (tVal > 0 ? `R$ ${Math.round(tVal)}` : '');
    const fullTicketVal = tVal > 0 ? `Ticket Médio (${MONTHS[i]}): R$ ${tVal.toLocaleString('pt-BR')} por cliente positivado` : '';

    html += `
      <div class="bar-group">
        ${tVal > 0 ? `<div class="bar-ticket-badge" title="${fullTicketVal}">${labelTicket}</div>` : `<div class="bar-ticket-badge is-empty"></div>`}
        <div class="bar-pair">
          <div class="bar b-sellin b-realizado" style="height:${h}%" data-tooltip="${tooltipRealizado}" title="${tooltipRealizado}">
            <span class="bar-val">
              ${v > 0 ? `<span class="bar-qty">${v}</span>` : ''}
            </span>
          </div>
          <div class="bar b-sellout b-meta" style="height:${hMeta}%" data-tooltip="${tooltipMeta}" title="${tooltipMeta}">
            <span class="bar-val">
              ${vMeta > 0 ? `<span class="bar-qty">${vMeta}</span>` : ''}
            </span>
          </div>
        </div>
        <span class="bar-month">${MONTHS[i]}</span>
        <span class="bar-perf-badge ${perfClass}" data-tooltip="${tooltipPerf}" title="${tooltipPerf}">${pctPerfStr}</span>
      </div>
    `;
  }

  // ── Overlay SVG do Gráfico de Linha: Ticket Médio Mensal (Visual Clean e Neutro) ──
  let svgTicketHtml = '';
  const visibleTickets = arrTicket.slice(0, maxMonthIdx + 1);
  const validTickets = visibleTickets.filter(t => typeof t === 'number' && t > 0);

  if (validTickets.length > 0) {
    const minT = Math.min(...validTickets);
    const maxT = Math.max(...validTickets);
    const spanT = (maxT > minT) ? (maxT - minT) : (maxT * 0.4 || 1000);
    const baseMin = Math.max(0, minT - spanT * 0.15);
    const baseMax = maxT + spanT * 0.25;

    const numCols = maxMonthIdx + 1;
    const ticketPoints = [];
    for (let i = 0; i <= maxMonthIdx; i++) {
      const tVal = arrTicket[i] || 0;
      if (tVal > 0) {
        const x = ((i + 0.5) / numCols) * 1000;
        const norm = (baseMax > baseMin) ? ((tVal - baseMin) / (baseMax - baseMin)) : 0.5;
        const y = 52 - (norm * 24); // Linha suave e harmônica logo abaixo dos badges
        ticketPoints.push({ i, x, y, val: tVal });
      }
    }

    let pathD = '';
    ticketPoints.forEach((pt, idx) => {
      if (idx === 0) pathD += `M ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`;
      else pathD += ` L ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`;
    });

    svgTicketHtml = `
      <svg class="positiv-ticket-svg" viewBox="0 0 1000 200" preserveAspectRatio="none">
        ${pathD ? `<path d="${pathD}" fill="none" stroke="#64748B" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" opacity="0.85"/>` : ''}
      </svg>
    `;
  }

  container.innerHTML = html + svgTicketHtml;
}

/* ── Renderiza gráfico de barras (REALIZADO vs META: Sell-in ou Sell-out) ── */
function buildBarChart(monthlyIn, monthlyOut, isVolume, monthlyMetaOut, monthlyMetaIn) {
  const container = document.getElementById('barChart');
  if (!container) return;

  if (monthlyIn && monthlyIn.length === 12) lastMonthlyIn = monthlyIn;
  if (monthlyOut && monthlyOut.length === 12) lastMonthlyOut = monthlyOut;
  if (monthlyMetaIn && monthlyMetaIn.length === 12) lastMonthlyMetaIn = monthlyMetaIn;
  if (monthlyMetaOut && monthlyMetaOut.length === 12) lastMonthlyMetaOut = monthlyMetaOut;
  if (typeof isVolume === 'boolean') lastIsVolume = isVolume;

  const MONTHS = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];

  // Modo do gráfico selecionado pelo toggle (Sell-in vs Sell-out)
  const chartToggle = document.getElementById('toggleChartMode');
  const isSellOutMode = chartToggle ? chartToggle.checked : (lastChartMode === 'sellout');
  lastChartMode = isSellOutMode ? 'sellout' : 'sellin';

  // Sincroniza labels do toggle
  const lblSellin = document.getElementById('lbl-chart-sellin');
  const lblSellout = document.getElementById('lbl-chart-sellout');
  if (lblSellin && lblSellout) {
    if (isSellOutMode) {
      lblSellin.classList.remove('active-label');
      lblSellout.classList.add('active-label');
    } else {
      lblSellout.classList.remove('active-label');
      lblSellin.classList.add('active-label');
    }
  }

  // Título e Legenda dinâmicos
  const titleEl = document.getElementById('chart-title-text');
  if (titleEl) {
    titleEl.textContent = isSellOutMode ? 'Sell-out vs Meta' : 'Sell-in vs Meta';
  }

  const legRealized = document.getElementById('chart-leg-lbl-realized');
  const legMeta = document.getElementById('chart-leg-lbl-meta');
  if (legRealized) legRealized.textContent = isSellOutMode ? 'Sell-out' : 'Sell-in';
  if (legMeta) legMeta.textContent = 'Meta';

  // Arrays de Realizado e Meta de acordo com o modo
  const arrRealized = isSellOutMode 
    ? ((lastMonthlyOut && lastMonthlyOut.length === 12) ? lastMonthlyOut : Array(12).fill(0))
    : ((lastMonthlyIn && lastMonthlyIn.length === 12) ? lastMonthlyIn : Array(12).fill(0));

  const arrMeta = isSellOutMode
    ? ((lastMonthlyMetaOut && lastMonthlyMetaOut.length === 12) ? lastMonthlyMetaOut : Array(12).fill(0))
    : ((lastMonthlyMetaIn && lastMonthlyMetaIn.length === 12) ? lastMonthlyMetaIn : Array(12).fill(0));

  const metricName = isSellOutMode ? 'Sell-out' : 'Sell-in';
  const useVol = lastIsVolume;

  // Determina até qual mês exibir:
  // Se for o ano atual (ou nenhum ano específico filtrado), limita estritamente ao mês atual
  // evitando que meses futuros zerados poluam o gráfico.
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonthIdx = now.getMonth(); // 0-based: 0=JAN, 8=SEP, 9=OCT...

  const anoFilter = getSafeSelectedValues('select-ano');
  const selectedYear = (anoFilter.length === 1 && !isNaN(parseInt(anoFilter[0]))) ? parseInt(anoFilter[0]) : null;

  let maxMonthIdx = 11;
  if (!selectedYear || selectedYear >= currentYear) {
    maxMonthIdx = currentMonthIdx;
  } else {
    // Para anos passados, exibe até o último mês com dados reais (ou 11 se houver dados até dezembro)
    let lastWithData = -1;
    for (let m = 11; m >= 0; m--) {
      if ((arrRealized[m] && arrRealized[m] > 0) || (arrMeta[m] && arrMeta[m] > 0)) {
        lastWithData = m;
        break;
      }
    }
    maxMonthIdx = lastWithData >= 0 ? lastWithData : 11;
  }

  const visibleRealized = arrRealized.slice(0, maxMonthIdx + 1);
  const visibleMeta = arrMeta.slice(0, maxMonthIdx + 1);

  const maxVal = Math.max(...visibleRealized, ...visibleMeta, 1);
  const suggestedMax = maxVal * 1.25;

  const formatBarVal = (val) => {
    if (val <= 0) return '';
    if (useVol) {
      if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`;
      if (val >= 1000) return `${Math.round(val / 1000)}K`;
      return Math.round(val).toString();
    } else {
      if (val >= 1000000) return `R$ ${(val / 1000000).toFixed(1)}M`;
      if (val >= 1000) return `R$ ${Math.round(val / 1000)}K`;
      return `R$ ${Math.round(val)}`;
    }
  };

  // Atualiza a badge do título com a diferença percentual entre Realizado e Meta dos meses visíveis
  const badgeEl = document.getElementById('chart-diff-badge');
  if (badgeEl) {
    const sumRealized = visibleRealized.reduce((a, b) => a + b, 0);
    const sumMeta = visibleMeta.reduce((a, b) => a + b, 0);
    if (sumMeta > 0) {
      const diffPct = ((sumRealized - sumMeta) / sumMeta) * 100;
      const isPositive = diffPct >= 0;
      badgeEl.className = isPositive ? 'badge-up' : 'badge-down';
      badgeEl.textContent = `${isPositive ? '↑ +' : '↓ -'}${Math.abs(diffPct).toFixed(1)}%`;
      badgeEl.title = `${metricName} vs Meta: ${isPositive ? '+' : '-'}${Math.abs(diffPct).toFixed(1)}% | Realizado: ${formatBarVal(sumRealized) || (useVol ? '0' : 'R$ 0')} / Meta: ${formatBarVal(sumMeta) || (useVol ? '0' : 'R$ 0')}`;
    } else if (sumRealized > 0) {
      badgeEl.className = 'badge-up';
      badgeEl.textContent = '↑ +100%';
      badgeEl.title = `${metricName} Realizado sem meta estipulada`;
    } else {
      badgeEl.className = 'badge-up';
      badgeEl.textContent = '0%';
      badgeEl.title = 'Sem movimentação no período';
    }
  }

  let html = '';
  for (let i = 0; i <= maxMonthIdx; i++) {
    const vRealized = arrRealized[i] || 0;
    const vMeta = arrMeta[i] || 0;
    const hRealized = Math.min(100, (vRealized / suggestedMax) * 100).toFixed(1);
    const hMeta = Math.min(100, (vMeta / suggestedMax) * 100).toFixed(1);

    const strRealized = formatBarVal(vRealized) || (useVol ? '0' : 'R$ 0');
    const strMeta = formatBarVal(vMeta) || (useVol ? '0' : 'R$ 0');

    const titleRealized = `data-tooltip="${metricName} (${MONTHS[i]}): ${strRealized}" title="${metricName} Realizado (${MONTHS[i]}): ${strRealized}"`;
    const titleMeta = `data-tooltip="Meta (${MONTHS[i]}): ${strMeta}" title="Meta ${metricName} (${MONTHS[i]}): ${strMeta}"`;

    // Cálculo do % de atingimento mês a mês (Realizado vs Meta)
    let pctVal = 0;
    let pctStr = '0%';
    let perfClass = 'perf-neutral';
    let tooltipPerf = `Atingimento (${MONTHS[i]}): Sem movimentação`;

    if (vMeta > 0 && vRealized > 0) {
      pctVal = Math.round((vRealized / vMeta) * 100);
      pctStr = `${pctVal}%`;
      const isAbove = vRealized >= vMeta;
      perfClass = isAbove ? 'perf-positive' : 'perf-negative';
      const diffPct = (((vRealized - vMeta) / vMeta) * 100).toFixed(1);
      const sign = isAbove ? '+' : '';
      tooltipPerf = `Atingimento ${metricName} (${MONTHS[i]}): ${pctVal}% (${sign}${diffPct}% vs meta) | Realizado: ${strRealized} / Meta: ${strMeta}`;
    } else if (vRealized > 0 && vMeta === 0) {
      pctVal = 100;
      pctStr = '100%';
      perfClass = 'perf-positive';
      tooltipPerf = `Atingimento ${metricName} (${MONTHS[i]}): 100% | Realizado: ${strRealized} (Sem meta cadastrada)`;
    } else {
      pctVal = 0;
      pctStr = '0%';
      perfClass = 'perf-neutral';
      tooltipPerf = `Atingimento ${metricName} (${MONTHS[i]}): 0% | Realizado: ${strRealized} / Meta: ${strMeta}`;
    }

    html += `
      <div class="bar-group">
        <div class="bar-pair">
          <div class="bar b-sellin b-realizado" style="height:${hRealized}%" ${titleRealized}><span class="bar-val">${formatBarVal(vRealized)}</span></div>
          <div class="bar b-sellout b-meta" style="height:${hMeta}%" ${titleMeta}><span class="bar-val">${formatBarVal(vMeta)}</span></div>
        </div>
        <span class="bar-month">${MONTHS[i]}</span>
        <span class="bar-perf-badge ${perfClass}" data-tooltip="${tooltipPerf}" title="${tooltipPerf}">${pctStr}</span>
      </div>
    `;
  }
  container.innerHTML = html;
}

/* ── Anima os gauges ── */
function animateGauges() {
  var CIRC = 2 * Math.PI * 46; // r=46 → 289.0
  document.querySelectorAll('.gauge-arc').forEach(function (arc) {
    var pct = parseFloat(arc.getAttribute('data-pct') || '0');
    var offset = CIRC * (1 - pct);
    arc.style.strokeDasharray = CIRC;
    arc.style.strokeDashoffset = offset;
  });
}

/* ── Drill-down accordion ── */
function toggleDrill(id, group) {
  var content = document.getElementById(id);
  if (!content) return;

  var isOpen = content.classList.contains('open');

  // fecha todos do mesmo grupo
  document.querySelectorAll('[id^="' + group + '-"]').forEach(function (el) {
    el.classList.remove('open');
    var row = el.closest('.drill-row');
    if (row) row.classList.remove('open');
  });

  // abre o clicado se estava fechado
  if (!isOpen) {
    content.classList.add('open');
    var row = content.closest('.drill-row');
    if (row) row.classList.add('open');
  }
}

/* ── Forecast chart (Combo: Sell-out Realizado vs FCST Meta com Eixo Y e Gridlines) ── */
function buildForecastChart(monthlyIn, monthlyOut, isVolume, monthlyMetaOut) {
  const container = document.getElementById('fcChart');
  if (!container) return;

  if (monthlyIn && monthlyIn.length === 12) lastMonthlyIn = monthlyIn;
  if (monthlyOut && monthlyOut.length === 12) lastMonthlyOut = monthlyOut;
  if (monthlyMetaOut && monthlyMetaOut.length === 12) lastMonthlyMetaOut = monthlyMetaOut;
  if (typeof isVolume === 'boolean') lastIsVolume = isVolume;

  const MONTHS = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];

  const arrOut = lastMonthlyOut;
  const arrMetaOut = lastMonthlyMetaOut;
  const useVol = lastIsVolume;

  const maxVal = Math.max(...arrOut, ...arrMetaOut, 1);
  const suggestedMax = maxVal * 1.15;

  const formatBarVal = (val) => {
    if (val <= 0) return '';
    if (useVol) {
      if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`;
      if (val >= 1000) return `${Math.round(val / 1000)}K`;
      return Math.round(val).toString();
    } else {
      if (val >= 1000000) return `R$ ${(val / 1000000).toFixed(1)}M`;
      if (val >= 1000) return `R$ ${Math.round(val / 1000)}K`;
      return `R$ ${Math.round(val)}`;
    }
  };

  const formatTickVal = (val) => {
    if (val <= 0) return '0';
    if (useVol) {
      if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`;
      if (val >= 1000) return `${Math.round(val / 1000)}K`;
      return Math.round(val).toString();
    } else {
      if (val >= 1000000) return `R$ ${(val / 1000000).toFixed(1)}M`;
      if (val >= 1000) return `R$ ${Math.round(val / 1000)}K`;
      return `R$ ${Math.round(val)}`;
    }
  };

  // Eixo Y: 5 Ticks (0, 25%, 50%, 75%, 100%)
  const yTicks = [1.0, 0.75, 0.5, 0.25, 0];
  let yAxisHtml = '<div class="fc-y-axis">';
  yTicks.forEach(pct => {
    const val = suggestedMax * pct;
    yAxisHtml += `<span class="fc-y-tick">${formatTickVal(val)}</span>`;
  });
  yAxisHtml += '</div>';

  // Gridlines de Fundo
  let gridlinesHtml = '<div class="fc-gridlines">';
  yTicks.forEach(() => {
    gridlinesHtml += '<div class="fc-gridline"></div>';
  });
  gridlinesHtml += '</div>';

  let barsHtml = '<div class="fc-bars-wrapper">';
  for (let i = 0; i < 12; i++) {
    const vOut  = arrOut[i] || 0;
    const vMeta = arrMetaOut[i] || 0;
    const hOut  = Math.min(100, (vOut / suggestedMax) * 100).toFixed(1);
    const hMeta = Math.min(100, (vMeta / suggestedMax) * 100).toFixed(1);

    const titleOut  = `data-tooltip="Sell-out (${MONTHS[i]}): ${formatBarVal(vOut)}" title="Sell-out Realizado (${MONTHS[i]}): ${formatBarVal(vOut)}"`;
    const titleMeta = `data-tooltip="FCST Meta (${MONTHS[i]}): ${formatBarVal(vMeta)}" title="FCST Meta (${MONTHS[i]}): ${formatBarVal(vMeta)}"`;

    barsHtml += `
      <div class="bar-group">
        <div class="bar-pair">
          <div class="bar b-sellout" style="height:${hOut}%" ${titleOut}>
            <span class="bar-val">${formatBarVal(vOut)}</span>
          </div>
          <div class="bar b-sellin" style="height:${hMeta}%" ${titleMeta}>
            <span class="bar-val">${formatBarVal(vMeta)}</span>
          </div>
        </div>
        <span class="bar-month">${MONTHS[i]}</span>
      </div>
    `;
  }
  barsHtml += '</div>';

  container.innerHTML = yAxisHtml + gridlinesHtml + barsHtml;
}

/* ── Tabs ── */
var TAB_LABELS = {
  kpis:     'Portal Distribuidores — KPI',
  grade:    'Portal Distribuidores — Pedidos de Compra',
  guia:     'Portal Distribuidores — Guia do Usuário & Técnico'
};

function updateToggleVisibility(tabId) {
  var toggleGroup = document.querySelector('.toggle-group');
  if (toggleGroup) {
    if (tabId === 'grade') {
      toggleGroup.style.display = 'none';
    } else {
      toggleGroup.style.display = 'flex';
    }
  }
}

function activateTab(tabId) {
  // 1. Atualiza botões da barra de abas
  document.querySelectorAll('.tab').forEach(function (b) { 
    b.classList.remove('active');
    if (b.getAttribute('data-tab') === tabId) {
      b.classList.add('active');
    }
  });

  // 2. Esconde todos os painéis de abas
  document.querySelectorAll('.tab-panel').forEach(function (panel) {
    panel.style.display = 'none';
    panel.classList.remove('active');
  });

  // 3. Exibe o painel de destino
  var panel = document.getElementById('tab-' + tabId);
  if (panel) {
    panel.style.display = 'flex';
    panel.classList.add('active');
  }

  // 4. Controles de cabeçalho e visibilidade da barra de filtros
  var portalBar = document.querySelector('.portal-bar');
  var headerTitle = document.querySelector('.header-title');
  var btnAdminGuide = document.getElementById('btn-admin-guide');
  var btnAdminGuideText = document.getElementById('btn-admin-guide-text');

  if (tabId === 'guia') {
    if (userSessionData && userSessionData.admin !== true && userSessionData.perfil !== 'admin') {
      activateTab('kpis');
      return;
    }
    if (portalBar) portalBar.style.display = 'none';
    if (headerTitle) headerTitle.textContent = 'GUIA DO USUÁRIO & TÉCNICO';
    if (btnAdminGuide) btnAdminGuide.classList.add('active');
    if (btnAdminGuideText) btnAdminGuideText.textContent = 'Dashboard';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else {
    if (portalBar) portalBar.style.display = 'block';
    if (headerTitle) headerTitle.textContent = 'DASHBOARD';
    if (btnAdminGuide) btnAdminGuide.classList.remove('active');
    if (btnAdminGuideText) btnAdminGuideText.textContent = 'Guia';
  }

  var lbl = document.getElementById('portalLabel');
  if (lbl && TAB_LABELS && TAB_LABELS[tabId]) lbl.textContent = TAB_LABELS[tabId];

  updateToggleVisibility(tabId);

  if (tabId === 'kpis') {
    requestAnimationFrame(function() {
      animateGauges();
      if (typeof lastMonthlyIn !== 'undefined' && lastMonthlyOut) {
        buildBarChart(lastMonthlyIn, lastMonthlyOut, lastIsVolume, lastMonthlyMetaOut, lastMonthlyMetaIn);
      }
      if (typeof lastMonthlyPositiv !== 'undefined' && typeof buildPositivChart === 'function') {
        buildPositivChart(lastMonthlyPositiv, lastMonthlyPositivPct, lastTotalBaseClientes, lastMonthlyPositivMeta);
      }
      if (lastDnaData && typeof renderDnaCards === 'function') {
        renderDnaCards(lastDnaData);
      }
    });
  } else if (tabId === 'grade') {
    requestAnimationFrame(function() {
      if (typeof currentGradeRowsData !== 'undefined' && currentGradeRowsData.length > 0) {
        updateGradeLogistica(currentGradeRowsData, null, typeof currentGradePage !== 'undefined' ? currentGradePage : 1);
      }
    });
  }
}

function toggleAdminGuide() {
  var tabGuia = document.getElementById('tab-guia');
  if (!tabGuia) return;
  var isGuiaActive = tabGuia.classList.contains('active') && tabGuia.style.display !== 'none';
  if (isGuiaActive) {
    activateTab('kpis');
  } else {
    activateTab('guia');
  }
}

function switchGuiaSubTab(subTabId) {
  document.querySelectorAll('.guia-tab-content').forEach(function (el) { el.classList.remove('active'); });
  document.querySelectorAll('.guia-tab-btn').forEach(function (btn) { btn.classList.remove('active'); });

  var targetContent = document.getElementById(subTabId);
  if (targetContent) targetContent.classList.add('active');

  var btnMap = {
    'guia-sub-negocio': 'btn-sub-negocio',
    'guia-sub-arquitetura': 'btn-sub-arquitetura',
    'guia-sub-metricas': 'btn-sub-metricas',
    'guia-sub-schema': 'btn-sub-schema',
    'guia-sub-rls': 'btn-sub-rls',
    'guia-sub-runbook': 'btn-sub-runbook'
  };

  var targetBtnId = btnMap[subTabId];
  if (targetBtnId) {
    var targetBtn = document.getElementById(targetBtnId);
    if (targetBtn) targetBtn.classList.add('active');
  }

  var tabGuia = document.getElementById('tab-guia');
  if (tabGuia) {
    tabGuia.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

window.activateTab = activateTab;
window.toggleAdminGuide = toggleAdminGuide;
window.switchGuiaSubTab = switchGuiaSubTab;

function initTabs() {
  document.querySelectorAll('.tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var tabId = btn.getAttribute('data-tab');
      activateTab(tabId);
    });
  });

  var activeTab = document.querySelector('.tab.active');
  if (activeTab) {
    updateToggleVisibility(activeTab.getAttribute('data-tab'));
  }
}

/* ── Toggle Valor / Volume ── */
function initToggle() {
  var toggle  = document.getElementById('toggleValVol');
  var lblValor  = document.getElementById('lbl-valor');
  var lblVolume = document.getElementById('lbl-volume');
  if (!toggle) return;
  toggle.addEventListener('change', function () {
    if (toggle.checked) {
      lblValor.classList.remove('active-label');
      lblVolume.classList.add('active-label');
    } else {
      lblVolume.classList.remove('active-label');
      lblValor.classList.add('active-label');
    }
    triggerDashboardRefresh(150);
  });
  if (lblValor) {
    lblValor.addEventListener('click', function () {
      if (toggle.checked) {
        toggle.checked = false;
        toggle.dispatchEvent(new Event('change'));
      }
    });
  }
  if (lblVolume) {
    lblVolume.addEventListener('click', function () {
      if (!toggle.checked) {
        toggle.checked = true;
        toggle.dispatchEvent(new Event('change'));
      }
    });
  }
}

/* ── Toggle Sell-in / Sell-out no Gráfico de Barras (Realizado vs Meta) ── */
function initChartToggle() {
  var toggle = document.getElementById('toggleChartMode');
  var lblSellin = document.getElementById('lbl-chart-sellin');
  var lblSellout = document.getElementById('lbl-chart-sellout');

  if (toggle) {
    toggle.addEventListener('change', function () {
      lastChartMode = toggle.checked ? 'sellout' : 'sellin';
      if (lblSellin && lblSellout) {
        if (toggle.checked) {
          lblSellin.classList.remove('active-label');
          lblSellout.classList.add('active-label');
        } else {
          lblSellout.classList.remove('active-label');
          lblSellin.classList.add('active-label');
        }
      }
      buildBarChart();
    });
  }

  if (lblSellin && toggle) {
    lblSellin.addEventListener('click', function () {
      if (toggle.checked) {
        toggle.checked = false;
        toggle.dispatchEvent(new Event('change'));
      }
    });
  }

  if (lblSellout && toggle) {
    lblSellout.addEventListener('click', function () {
      if (!toggle.checked) {
        toggle.checked = true;
        toggle.dispatchEvent(new Event('change'));
      }
    });
  }
}

/* ── Custom Searchable Multi-Select Helper ── */
function makeCustomSelect(containerId, placeholderName) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Evita re-inicialização duplicada do mesmo elemento
  if (container._initialized) return;
  container._initialized = true;

  const input = container.querySelector('.search-input');
  const optionsContainer = container.querySelector('.options-container');
  
  let allOptions = [];
  let selectedValues = new Set();

  const showDropdown = () => {
    // Fecha todos os outros dropdowns
    document.querySelectorAll('.custom-select').forEach(cs => {
      if (cs !== container) {
        cs.classList.remove('active');
        const opt = cs.querySelector('.options-container');
        if (opt) opt.style.display = 'none';
        cs.closest('.filter-wrapper')?.classList.remove('active-wrapper');
        cs.closest('.filter-group')?.classList.remove('active-group');
      }
    });

    optionsContainer.style.display = 'block';
    container.classList.add('active');
    container.closest('.filter-wrapper')?.classList.add('active-wrapper');
    container.closest('.filter-group')?.classList.add('active-group');

    // Restaura exibição de todos os itens ao reabrir
    const items = optionsContainer.querySelectorAll('.option-item');
    items.forEach(item => item.style.display = 'flex');

    if (document.activeElement !== input) {
      input.focus();
    }
    try { input.select(); } catch (_) {}
  };

  const closeDropdown = () => {
    optionsContainer.style.display = 'none';
    container.classList.remove('active');
    container.closest('.filter-wrapper')?.classList.remove('active-wrapper');
    container.closest('.filter-group')?.classList.remove('active-group');
    updateTriggerText();
  };

  const trigger = container.querySelector('.select-trigger');
  if (trigger) {
    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      const isVisible = optionsContainer.style.display === 'block';
      if (e.target === input) {
        // Clicar no input abre o dropdown se fechado; se aberto, mantém aberto para digitação
        if (!isVisible) showDropdown();
      } else {
        // Clicar na setinha ou no fundo do container alterna abre/fecha
        if (isVisible) closeDropdown();
        else showDropdown();
      }
    });
  }

  // Foco no input abre o dropdown
  input.addEventListener('focus', () => {
    if (optionsContainer.style.display !== 'block') {
      showDropdown();
    }
  });

  // Navegação por teclado: fechar no Escape e abrir na seta para baixo
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeDropdown();
    } else if (e.key === 'ArrowDown' && optionsContainer.style.display !== 'block') {
      showDropdown();
    }
  });

  document.addEventListener('click', (e) => {
    if (!container.contains(e.target)) {
      closeDropdown();
    }
  });

  function updateTriggerText() {
    if (selectedValues.size === 0) {
      input.value = '';
      input.placeholder = placeholderName;
    } else if (selectedValues.size === 1) {
      const val = Array.from(selectedValues)[0];
      const opt = allOptions.find(o => String(o.value) === String(val));
      input.value = opt ? opt.label : val;
    } else {
      input.value = `${selectedValues.size} sel.`;
    }
  }

  container.populate = function(options, initialSelected = [], emptyPlaceholder = 'Nenhum valor') {
    allOptions = options || [];
    optionsContainer.innerHTML = '';
    selectedValues.clear();

    if (initialSelected && initialSelected.length > 0) {
      initialSelected.forEach(val => selectedValues.add(val));
    }
    
    if (allOptions.length === 0) {
      optionsContainer.innerHTML = `<div class="option-item" style="color: #94A3B8; font-style: italic; cursor: default; justify-content: center; padding: 10px;">${emptyPlaceholder}</div>`;
      updateTriggerText();
      return;
    }

    const selectAllItem = document.createElement('div');
    selectAllItem.className = 'option-item select-all-item';
    selectAllItem.innerHTML = `
      <input type="checkbox" />
      <span style="font-weight: 700;">Selecionar Todos</span>
    `;
    const selectAllCheckbox = selectAllItem.querySelector('input');
    
    selectAllItem.addEventListener('click', (e) => {
      e.stopPropagation();
      if (e.target !== selectAllCheckbox) {
        selectAllCheckbox.checked = !selectAllCheckbox.checked;
      }
      const isChecked = selectAllCheckbox.checked;
      const checkboxes = optionsContainer.querySelectorAll('.option-item:not(.select-all-item) input');
      checkboxes.forEach(cb => {
        cb.checked = isChecked;
        if (isChecked) {
          selectedValues.add(cb.value);
        } else {
          selectedValues.delete(cb.value);
        }
      });
      updateTriggerText();
      container.dispatchEvent(new Event('change', { bubbles: true }));
    });
    optionsContainer.appendChild(selectAllItem);

    allOptions.forEach(opt => {
      const item = document.createElement('div');
      item.className = 'option-item';
      item.innerHTML = `
        <input type="checkbox" value="${opt.value}" />
        <span title="${opt.label}">${opt.label}</span>
      `;
      const checkbox = item.querySelector('input');

      if (selectedValues.has(opt.value)) {
        checkbox.checked = true;
      }

      item.addEventListener('click', (e) => {
        e.stopPropagation();
        if (e.target !== checkbox) {
          checkbox.checked = !checkbox.checked;
        }
        if (checkbox.checked) {
          selectedValues.add(checkbox.value);
        } else {
          selectedValues.delete(checkbox.value);
        }

        const allChecked = Array.from(optionsContainer.querySelectorAll('.option-item:not(.select-all-item) input')).every(cb => cb.checked);
        selectAllCheckbox.checked = allChecked;

        updateTriggerText();
        container.dispatchEvent(new Event('change', { bubbles: true }));
      });
      optionsContainer.appendChild(item);
    });

    updateTriggerText();
  };

  input.addEventListener('input', () => {
    const filter = input.value.toLowerCase();
    const items = optionsContainer.querySelectorAll('.option-item:not(.select-all-item)');
    items.forEach(item => {
      const text = item.textContent.toLowerCase();
      item.style.display = text.includes(filter) ? 'flex' : 'none';
    });
  });

  container.getSelectedValues = function() {
    return Array.from(selectedValues);
  };

  container.clear = function() {
    selectedValues.clear();
    const checkboxes = optionsContainer.querySelectorAll('input');
    checkboxes.forEach(cb => cb.checked = false);
    updateTriggerText();
  };
}

/* ── Dynamic Filters & Databricks Integration ── */
// Resolve o endpoint da API: se houver backend Node rodando na 8000, usa-o.
// Funciona tanto no Live Server (5500, 5501, 5502...) quanto rodando diretamente pelo Node.
function getApiBase() {
  // Sempre usa rotas relativas '', garantindo funcionamento no servidor Local e em Databricks Apps (porta 8080/8115/qualquer porta)
  return '';
}
const API_BASE = getApiBase();

let _categoriasMapping = {};

function initAllCustomSelects() {
  makeCustomSelect('select-categoria', 'Todos');
  makeCustomSelect('select-produto', 'Todos');
  makeCustomSelect('select-sku', 'Todos');
  makeCustomSelect('select-pedido', 'Todos');
  makeCustomSelect('select-dia', 'Todos');
  makeCustomSelect('select-semana', 'Todos');
  makeCustomSelect('select-mes', 'Todos');
  makeCustomSelect('select-ano', 'Todos');

  const now = new Date();
  const currentYear = now.getFullYear().toString(); // e.g. "2026"
  const currentMonthNum = now.getMonth() + 1;
  const currentMonthStr = String(currentMonthNum).padStart(2, '0');
  const defaultMonth = currentMonthStr; // Sempre o mês atual corrente

  // 1. ANO: Seleção nativa automática do ANO ATUAL
  let yearsArray = ['2025', '2026'];
  if (!yearsArray.includes(currentYear)) {
    yearsArray.push(currentYear);
  }
  yearsArray.sort();
  const defaultAnos = yearsArray.map(a => ({ value: String(a), label: String(a) }));
  const existingAnos = getSafeSelectedValues('select-ano');
  const selAno = existingAnos.length > 0 ? existingAnos : [currentYear];
  document.getElementById('select-ano')?.populate(defaultAnos, selAno);

  // 2. MÊS: Seleção nativa automática do MÊS ATUAL
  const defaultMeses = [
    { value: '01', label: '01 - Jan' },
    { value: '02', label: '02 - Fev' },
    { value: '03', label: '03 - Mar' },
    { value: '04', label: '04 - Abr' },
    { value: '05', label: '05 - Mai' },
    { value: '06', label: '06 - Jun' },
    { value: '07', label: '07 - Jul' },
    { value: '08', label: '08 - Ago' },
    { value: '09', label: '09 - Set' },
    { value: '10', label: '10 - Out' },
    { value: '11', label: '11 - Nov' },
    { value: '12', label: '12 - Dez' }
  ];
  const existingMeses = getSafeSelectedValues('select-mes');
  const selMes = existingMeses.length > 0 ? existingMeses : [defaultMonth];
  document.getElementById('select-mes')?.populate(defaultMeses, selMes);

  // 3. SEMANAS (S1, S2... para caber perfeitamente em 1 linha)
  const defaultSemanas = Array.from({length: 52}, (_, i) => ({ value: String(i + 1), label: `S${i + 1}` }));
  document.getElementById('select-semana')?.populate(defaultSemanas);

  // 4. DIAS (01, 02... compacto e nítido)
  const defaultDias = Array.from({length: 31}, (_, i) => {
    const d = String(i + 1).padStart(2, '0');
    return { value: d, label: d };
  });
  document.getElementById('select-dia')?.populate(defaultDias);

  document.getElementById('select-categoria')?.populate([], [], 'Carregando categorias...');
  document.getElementById('select-produto')?.populate([], [], 'Carregando produtos...');
  document.getElementById('select-sku')?.populate([], [], 'Carregando SKUs...');
  document.getElementById('select-pedido')?.populate([], [], 'Carregando pedidos...');
}

async function loadFilters() {
  initAllCustomSelects();

  const now = new Date();
  const currentYear = now.getFullYear().toString();
  const currentMonthNum = now.getMonth() + 1;
  const currentMonthStr = String(currentMonthNum).padStart(2, '0');

  const monthLabels = {
    '01': '01 - Jan', '02': '02 - Fev', '03': '03 - Mar', '04': '04 - Abr',
    '05': '05 - Mai', '06': '06 - Jun', '07': '07 - Jul', '08': '08 - Ago',
    '09': '09 - Set', '10': '10 - Out', '11': '11 - Nov', '12': '12 - Dez'
  };

  try {
    const res = await fetch(`${API_BASE}/api/filtros`, { credentials: 'include' });
    const data = await res.json();

    if (data.erro) {
      console.warn('Aviso filtros dinâmicos:', data.erro);
    }

    // Anos: preserva ano selecionado pelo usuário ou ano atual
    let anoList = (data.anos && data.anos.length > 0) ? data.anos.map(String) : ['2025', '2026'];
    if (!anoList.includes(currentYear)) {
      anoList.push(currentYear);
    }
    anoList.sort();
    const curAnoSelected = getSafeSelectedValues('select-ano');
    const anosToKeep = curAnoSelected.length > 0 ? curAnoSelected : [currentYear];
    document.getElementById('select-ano')?.populate(anoList.map(a => ({ value: String(a), label: String(a) })), anosToKeep);

    // Meses: preserva mês selecionado pelo usuário ou o mês mais recente com dados (ex: '09 - Set')
    const mesList = (data.meses && data.meses.length > 0)
      ? data.meses.map(m => String(m).padStart(2, '0'))
      : ['01','02','03','04','05','06','07','08','09','10','11','12'];
    // Sempre usa o mês atual corrente por padrão (ex: '10' para Outubro)
    const defaultMonth = currentMonthStr;
    const curMesSelected = getSafeSelectedValues('select-mes');
    const mesesToKeep = curMesSelected.length > 0 ? curMesSelected : [defaultMonth];
    document.getElementById('select-mes')?.populate(uniqueMeses.map(m => ({
      value: m,
      label: monthLabels[m] || m
    })), mesesToKeep);

    // Semanas (S1, S2... para caber perfeitamente em 1 linha)
    const semList = (data.semanas && data.semanas.length > 0) ? data.semanas : Array.from({length: 52}, (_, i) => String(i + 1));
    const curSemSelected = getSafeSelectedValues('select-semana');
    document.getElementById('select-semana')?.populate(semList.map(s => ({ value: String(s), label: `S${s}` })), curSemSelected);

    // Dias (01, 02... compacto e nítido)
    const diaList = (data.dias && data.dias.length > 0) ? data.dias : Array.from({length: 31}, (_, i) => String(i + 1).padStart(2, '0'));
    const curDiaSelected = getSafeSelectedValues('select-dia');
    document.getElementById('select-dia')?.populate(diaList.map(d => ({ value: String(d), label: String(d) })), curDiaSelected);

    // Produto
    const prodList = (data.produtos && data.produtos.length > 0) ? data.produtos : [];
    const curProdSelected = getSafeSelectedValues('select-produto');
    document.getElementById('select-produto')?.populate(prodList.map(p => ({ value: p, label: p })), curProdSelected, 'Nenhum produto');

    // SKU
    const skuCodes = (data.skus || []).map(s => {
      return s.includes(' - ') ? s.split(' - ')[0].trim() : s.trim();
    }).filter(Boolean);
    const uniqueSkuCodes = Array.from(new Set(skuCodes));
    const curSkuSelected = getSafeSelectedValues('select-sku');
    document.getElementById('select-sku')?.populate(uniqueSkuCodes.map(s => ({ value: s, label: s })), curSkuSelected, 'Nenhum SKU');

    // Pedidos
    const pedOpts = (data.pedidos || []).map(p => ({ value: String(p), label: String(p) }));
    window._pedidosFromApi = pedOpts;
    const curPedSelected = getSafeSelectedValues('select-pedido');
    document.getElementById('select-pedido')?.populate(pedOpts, curPedSelected, 'Nenhum pedido');

    // Categorias de Produto (Pães / Especialidades)
    _categoriasMapping = data.categorias || {};
    const catNames = Object.keys(_categoriasMapping).sort();
    const catOpts = catNames.map(c => ({ value: c, label: c }));
    const curCatSelected = getSafeSelectedValues('select-categoria');
    document.getElementById('select-categoria')?.populate(catOpts, curCatSelected, 'Nenhuma categoria');

    // Listener: quando Categoria muda, filtra o dropdown de Produto
    const catEl = document.getElementById('select-categoria');
    if (catEl && !catEl._catListenerAdded) {
      catEl._catListenerAdded = true;
      catEl.addEventListener('change', () => {
        const selCats = getSafeSelectedValues('select-categoria');
        const prodSelect = document.getElementById('select-produto');
        if (!prodSelect || !prodSelect.populate) return;
        if (selCats.length === 0) {
          // Sem categoria selecionada: mostra todos os produtos
          prodSelect.populate(prodList.map(p => ({ value: p, label: p })), [], 'Nenhum produto');
        } else {
          // Filtra produtos pelas categorias selecionadas
          const allowedProds = new Set();
          selCats.forEach(c => {
            (_categoriasMapping[c] || []).forEach(p => allowedProds.add(p));
          });
          const filteredProdOpts = prodList.filter(p => allowedProds.has(p)).map(p => ({ value: p, label: p }));
          prodSelect.populate(filteredProdOpts, [], 'Nenhum produto na categoria');
        }
      });
    }

  } catch (err) {
    console.warn('Erro ao carregar dados dinâmicos de filtros:', err);
  }
}


function updateCardGaugeAndDiff(cardClass, diffElemId, vlRealized, vlTarget, formatNumber) {
  const card = document.querySelector('.' + cardClass);
  if (!card) return;

  const kpiValEl = card.querySelector('.card-kpi-val');
  if (kpiValEl) {
    kpiValEl.innerHTML = `${formatNumber(vlRealized)} <span class="kpi-target">/ ${formatNumber(vlTarget)}</span>`;
  }

  const pctRatio = vlTarget > 0 ? (vlRealized / vlTarget) : 0;
  const pctInt = Math.round(pctRatio * 100);

  // Animação do arco do Gauge SVG (r=46 → CIRC ~289.0)
  const arc = card.querySelector('.gauge-arc');
  const pctTxt = card.querySelector('.gauge-pct-txt');
  if (arc) {
    arc.setAttribute('data-pct', pctRatio.toFixed(2));
    const CIRC = 2 * Math.PI * 46;
    const clampedPct = Math.min(1, Math.max(0, pctRatio));
    arc.style.strokeDashoffset = CIRC * (1 - clampedPct);
  }
  if (pctTxt) {
    pctTxt.textContent = `${pctInt}%`;
  }

  // Valor absoluto da Diferença entre Realizado e Meta
  const absDiff = Math.abs(vlRealized - vlTarget);
  const isAbove = vlRealized >= vlTarget;

  // Percentual da diferença: quando abaixo da meta, garante que pctInt + missingPct = 100%
  let diffPctText = '';
  if (vlTarget > 0) {
    if (isAbove) {
      const surplusPct = pctInt - 100;
      diffPctText = ` (+${surplusPct}%)`;
    } else {
      const missingPct = 100 - pctInt;
      diffPctText = ` (-${missingPct}%)`;
    }
  } else {
    diffPctText = vlRealized > 0 ? ' (+100%)' : ' (0%)';
  }

  const diffEl = document.getElementById(diffElemId);
  if (diffEl) {
    const arrow = isAbove ? '↑' : '↓';
    const color = isAbove ? '#22c55e' : '#ef4444';
    const sign = isAbove ? '+' : '-';
    diffEl.style.color = color;
    diffEl.innerHTML = `<span style="font-size: 15px; font-weight: 800; line-height: 1;">${arrow}</span> <span>Diferença:</span> <span style="font-weight: 850;">${sign}${formatNumber(absDiff)}${diffPctText}</span>`;
  }
}

function updateOrderPipelineCards(orderMetrics, isVolume, formatNumber, vlSellIn = null) {
  const invoicedValEl = document.getElementById('kpi-invoiced-val');
  const openValEl = document.getElementById('kpi-open-val');
  const totalValEl = document.getElementById('kpi-total-order-val');
  const totalDescEl = document.getElementById('kpi-total-order-desc');

  function num(val) {
    const n = parseFloat(val);
    return isNaN(n) ? 0 : n;
  }

  const row = (orderMetrics && Array.isArray(orderMetrics) && orderMetrics.length > 0)
    ? orderMetrics[0]
    : (orderMetrics && !Array.isArray(orderMetrics) ? orderMetrics : {});

  let invoicedVal = 0;
  let openVal = 0;
  let totalVal = 0;

  if (isVolume) {
    // Volume: utiliza o volume consolidado de Sell-In em DZ para paridade com o card de Sell-In
    invoicedVal = (vlSellIn !== null && vlSellIn !== undefined)
      ? num(vlSellIn)
      : num(row.total_qty_invoiced_dz || row.TOTAL_QTY_INVOICED_DZ);
    openVal = num(row.total_qty_open_dz || row.TOTAL_QTY_OPEN_DZ);
    totalVal = invoicedVal + openVal;

    if (invoicedValEl) invoicedValEl.textContent = `${formatNumber(invoicedVal)} DZ`;
    if (openValEl) openValEl.textContent = openVal === 0 ? '--' : `${formatNumber(openVal)} DZ`;
    if (totalValEl) totalValEl.textContent = `${formatNumber(totalVal)} DZ`;
  } else {
    // Valor: alinhamento oficial com o Sell-In contábil (DNA de Vendas) da Bimbo
    invoicedVal = (vlSellIn !== null && vlSellIn !== undefined)
      ? num(vlSellIn)
      : num(row.total_vl_invoiced || row.TOTAL_VL_INVOICED);
    openVal = num(row.total_vl_open || row.TOTAL_VL_OPEN);
    totalVal = invoicedVal + openVal;

    if (invoicedValEl) invoicedValEl.textContent = formatNumber(invoicedVal);
    if (openValEl) openValEl.textContent = openVal === 0 ? '--' : formatNumber(openVal);
    if (totalValEl) totalValEl.textContent = formatNumber(totalVal);
  }

  if (totalDescEl) {
    if (totalVal > 0) {
      const pctInvoiced = Math.round((invoicedVal / totalVal) * 100);
      totalDescEl.textContent = `${pctInvoiced}% faturado • ${100 - pctInvoiced}% em carteira`;
    } else {
      totalDescEl.textContent = 'Sem pedidos registrados';
    }
  }
}

/* ── Renderiza o Tracker Ribbon Horizontal de Sell-Out (Tracking Diário de Envio) ── */
function renderTrackingRibbon(trackingRows, selectedYear, selectedMonth, isVolume, formatNumber) {
  const container = document.getElementById('tracking-days-track');
  const monthPill = document.getElementById('tracking-month-pill');
  const activeDaysEl = document.getElementById('tracking-active-days');
  const regularityPctEl = document.getElementById('tracking-regularity-pct');
  const avgDailyEl = document.getElementById('tracking-avg-daily');

  if (!container) return;

  const MONTH_NAMES = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
  ];
  const WEEKDAYS_SHORT = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
  const WEEKDAYS_FULL = ['Domingo', 'Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado'];

  const now = new Date();
  const year = (selectedYear && !isNaN(selectedYear)) ? parseInt(selectedYear, 10) : now.getFullYear();
  const month = (selectedMonth && !isNaN(selectedMonth) && selectedMonth >= 1 && selectedMonth <= 12) ? parseInt(selectedMonth, 10) : (now.getMonth() + 1);

  if (monthPill) {
    monthPill.textContent = `${MONTH_NAMES[month - 1]} ${year}`;
  }

  // Quantidade de dias no mês (ex: 30 para Setembro, 31 para Agosto, 28/29 para Fevereiro)
  const daysInMonth = new Date(year, month, 0).getDate();

  // Determina o limite de dias a exibir: apenas dias atuais para trás se for o mês corrente
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;
  const currentDay = now.getDate();

  const isCurrentYear = (year === currentYear);
  const isCurrentMonth = isCurrentYear && (month === currentMonth);
  const isFutureMonth = (year > currentYear) || (isCurrentYear && month > currentMonth);

  let maxDay = daysInMonth;
  if (isFutureMonth) {
    maxDay = 0;
  } else if (isCurrentMonth) {
    maxDay = Math.min(daysInMonth, currentDay);
  }

  if (maxDay === 0) {
    container.innerHTML = '<div class="tracking-loading-state" style="color:#94A3B8;">Mês futuro selecionado — aguardando início do período.</div>';
    if (activeDaysEl) activeDaysEl.textContent = '0 de 0 úteis';
    if (regularityPctEl) regularityPctEl.textContent = '0%';
    if (avgDailyEl) avgDailyEl.textContent = `${formatNumber(0)}${isVolume ? ' DZ' : ''}`;
    return;
  }

  // Mapeia vendas registradas por dia
  const salesMap = new Map();
  if (Array.isArray(trackingRows)) {
    trackingRows.forEach(r => {
      let d = parseInt(r.dia || r.DIA || 0, 10);
      if (!d && r.data_sell_out) {
        const parts = String(r.data_sell_out).split('-');
        if (parts.length === 3) d = parseInt(parts[2], 10);
      }
      if (d > 0) {
        const val = parseFloat(r.total_vl_sell_out || r.TOTAL_VL_SELL_OUT || 0) || 0;
        const vol = parseFloat(r.total_qty_dz_sell_out || r.TOTAL_QTY_DZ_SELL_OUT || 0) || 0;
        const cli = parseInt(r.total_clientes || r.TOTAL_CLIENTES || 0, 10) || 0;
        salesMap.set(d, { valor: val, volume: vol, clientes: cli });
      }
    });
  }

  let totalActiveDays = 0;
  let totalBusinessDays = 0;
  let activeBusinessDays = 0;
  let totalSellOut = 0;
  let capsulesHtml = '';

  for (let d = 1; d <= maxDay; d++) {
    const dateObj = new Date(year, month - 1, d);
    const dayOfWeek = dateObj.getDay(); // 0 = Domingo, 6 = Sábado
    const isWeekend = (dayOfWeek === 0 || dayOfWeek === 6);
    const weekdayShort = WEEKDAYS_SHORT[dayOfWeek];
    const weekdayFull = WEEKDAYS_FULL[dayOfWeek];
    const dStr = String(d).padStart(2, '0');
    const mStr = String(month).padStart(2, '0');

    if (!isWeekend) {
      totalBusinessDays++;
    }

    const saleInfo = salesMap.get(d);
    const hasSale = !!(saleInfo && (saleInfo.valor > 0 || saleInfo.volume > 0));

    if (hasSale) {
      totalActiveDays++;
      if (!isWeekend) activeBusinessDays++;
      totalSellOut += isVolume ? (saleInfo.volume || 0) : (saleInfo.valor || 0);

      const valFmt = `R$ ${(saleInfo.valor || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
      const volFmt = `${Math.round(saleInfo.volume || 0).toLocaleString('pt-BR')} DZ`;
      const cliCount = saleInfo.clientes || 0;

      capsulesHtml += `
        <div class="day-capsule status-active ${isWeekend ? 'is-weekend' : ''}" data-day="${d}">
          <span class="capsule-weekday ${isWeekend ? 'weekday-weekend' : ''}">${weekdayShort}</span>
          <span class="capsule-day">${dStr}</span>
          <span class="capsule-icon-wrap">✓</span>
          <div class="capsule-tooltip">
            <div class="tip-status-pill pill-green">🟢 Venda Registrada ${isWeekend ? '(Fim de Semana)' : ''}</div>
            <div class="tip-title">${dStr}/${mStr}/${year} (${weekdayFull})</div>
            <div class="tip-row"><span>Faturamento:</span> <span class="tip-val">${valFmt}</span></div>
            <div class="tip-row"><span>Volume:</span> <span class="tip-val">${volFmt}</span></div>
            <div class="tip-row"><span>Clientes Atendidos:</span> <span class="tip-val">${cliCount}</span></div>
          </div>
        </div>
      `;
    } else if (isWeekend) {
      // Fim de semana sem movimentação: cinzinha neutro, sem ícone, apenas nome e dia
      capsulesHtml += `
        <div class="day-capsule status-weekend" data-day="${d}">
          <span class="capsule-weekday">${weekdayShort}</span>
          <span class="capsule-day">${dStr}</span>
          <div class="capsule-tooltip">
            <div class="tip-status-pill pill-gray">⚪ Fim de Semana</div>
            <div class="tip-title">${dStr}/${mStr}/${year} (${weekdayFull})</div>
            <div class="tip-row"><span>Status:</span> <span class="tip-val" style="color:#94A3B8">Sem movimentação</span></div>
          </div>
        </div>
      `;
    } else {
      // Dia útil sem envio: demarcação em vermelho com ✕
      capsulesHtml += `
        <div class="day-capsule status-inactive" data-day="${d}">
          <span class="capsule-weekday">${weekdayShort}</span>
          <span class="capsule-day">${dStr}</span>
          <span class="capsule-icon-wrap">✕</span>
          <div class="capsule-tooltip">
            <div class="tip-status-pill pill-red">🔴 Sem Venda (Dia Útil)</div>
            <div class="tip-title">${dStr}/${mStr}/${year} (${weekdayFull})</div>
            <div class="tip-row"><span>Status:</span> <span class="tip-val" style="color:#F87171">Nenhum envio registrado</span></div>
          </div>
        </div>
      `;
    }
  }

  container.innerHTML = capsulesHtml;

  const regularityPct = totalBusinessDays > 0 ? Math.round((activeBusinessDays / totalBusinessDays) * 100) : 0;
  const avgDaily = totalActiveDays > 0 ? (totalSellOut / totalActiveDays) : 0;

  if (activeDaysEl) {
    activeDaysEl.textContent = `${activeBusinessDays} de ${totalBusinessDays} úteis`;
    if (activeDaysEl.parentElement) {
      activeDaysEl.parentElement.title = `${activeBusinessDays} de ${totalBusinessDays} dias úteis com venda (${regularityPct}% de regularidade)${totalActiveDays > activeBusinessDays ? ` + ${totalActiveDays - activeBusinessDays} em fins de semana (Total: ${totalActiveDays} dias)` : ''}`;
    }
  }
  if (regularityPctEl) {
    regularityPctEl.textContent = `${regularityPct}%`;
  }
  if (avgDailyEl) {
    avgDailyEl.textContent = `${formatNumber(avgDaily)}${isVolume ? ' DZ' : ''}`;
  }
}

let currentStockRowsData = [];

function openEstoqueModal(mode) {
  const modal = document.getElementById('modal-estoque-expand');
  const tagEl = document.getElementById('modal-block-tag') || document.getElementById('modal-estoque-tag');
  const titleEl = document.getElementById('modal-block-title') || document.getElementById('modal-estoque-title');
  const tbody = document.getElementById('modal-tbody-estoque');

  if (!modal || !tbody) return;

  function getProdDesc(r) {
    if (!r) return 'Produto';
    if (r.produto && String(r.produto).trim() !== '') return String(r.produto).trim();
    if (r.DESC_PROD_BQ && String(r.DESC_PROD_BQ).trim() !== '') return String(r.DESC_PROD_BQ).trim();
    if (r.desc_prod_bq && String(r.desc_prod_bq).trim() !== '') return String(r.desc_prod_bq).trim();
    for (const key of Object.keys(r)) {
      if (key.toUpperCase().includes('DESC_PROD_BQ') || key.toUpperCase().includes('DESC_PROD_ARQUIVO_DIST') || key.toUpperCase().includes('DESC_PRODUTO_ARQUIVO') || key.toUpperCase().includes('DESC_PROD_DIST')) {
        if (r[key] && String(r[key]).trim() !== '') return String(r[key]).trim();
      }
    }
    return r.DESC_PROD_ARQUIVO_DIST || r.desc_prod_arquivo_dist || r.DESC_PRODUTO_ARQUIVO_DIST || r.DESCRICAO_PRODUTO || r.SKU_PROD_BQ || r.sku_prod_bq || r.SKU_PROD_DIST || r.sku_prod_dist || 'Produto';
  }

  function getClienteName(r) {
    if (!r) return 'Cliente';
    if (r.razao_social_cliente && String(r.razao_social_cliente).trim() !== '' && String(r.razao_social_cliente).trim() !== 'Cliente') return String(r.razao_social_cliente).trim();
    if (r.DESC_CLIENTE && String(r.DESC_CLIENTE).trim() !== '' && String(r.DESC_CLIENTE).trim() !== 'Cliente') return String(r.DESC_CLIENTE).trim();
    if (r.desc_cliente && String(r.desc_cliente).trim() !== '' && String(r.desc_cliente).trim() !== 'Cliente') return String(r.desc_cliente).trim();
    if (r.desc_distribuidor && String(r.desc_distribuidor).trim() !== '' && String(r.desc_distribuidor).trim() !== 'Cliente') return String(r.desc_distribuidor).trim();
    if (r.DESC_DISTRIBUIDOR && String(r.DESC_DISTRIBUIDOR).trim() !== '' && String(r.DESC_DISTRIBUIDOR).trim() !== 'Cliente') return String(r.DESC_DISTRIBUIDOR).trim();
    if (r.RAZAO_SOCIAL && String(r.RAZAO_SOCIAL).trim() !== '' && String(r.RAZAO_SOCIAL).trim() !== 'Cliente') return String(r.RAZAO_SOCIAL).trim();
    for (const key of Object.keys(r)) {
      if (key.toUpperCase().includes('CLIENTE') || key.toUpperCase().includes('RAZAO') || key.toUpperCase().includes('DISTRIBUIDOR')) {
        if (r[key] && String(r[key]).trim() !== '' && String(r[key]).trim() !== 'Cliente') return String(r[key]).trim();
      }
    }
    return r.desc_distribuidor || r.DESC_DISTRIBUIDOR || 'Cliente';
  }

  // RLS STRICT: sem fallback simulado. Se não há dados, mostra cards vazios.

  // Inicializar seletores se existirem
  if (typeof makeCustomSelect === 'function') {
    makeCustomSelect('select-modal-est-cliente', 'Todos os Clientes');
    makeCustomSelect('select-modal-est-produto', 'Todos os Produtos');
  }

  const uniqueClientes = Array.from(new Set(currentStockRowsData.map(getClienteName))).filter(Boolean).sort();
  const uniqueProdutos = Array.from(new Set(currentStockRowsData.map(getProdDesc))).filter(Boolean).sort();

  const selEstCliente = document.getElementById('select-modal-est-cliente');
  const selEstProduto = document.getElementById('select-modal-est-produto');

  if (selEstCliente && typeof selEstCliente.populate === 'function') {
    selEstCliente.populate(uniqueClientes.map(c => ({ value: c, label: c })));
  }
  if (selEstProduto && typeof selEstProduto.populate === 'function') {
    selEstProduto.populate(uniqueProdutos.map(p => ({ value: p, label: p })));
  }

  document.getElementById('filter-modal-est-cliente')?.removeEventListener('input', filterModalEstoqueTable);
  document.getElementById('filter-modal-est-cliente')?.addEventListener('input', filterModalEstoqueTable);
  document.getElementById('filter-modal-est-produto')?.removeEventListener('input', filterModalEstoqueTable);
  document.getElementById('filter-modal-est-produto')?.addEventListener('input', filterModalEstoqueTable);

  let filteredItems = [];
  let blockTitleText = '';

  const allItems = currentStockRowsData.map(row => ({
    dias: parseInt(row.dias_estoque || row.DIAS_ESTOQUE || '0', 10),
    cliente: getClienteName(row),
    produto: getProdDesc(row),
    skuCode: row.sku_prod_dist || row.SKU_PROD_DIST || row.SKU_PROD_BQ || 'SKU'
  }));

  // Ordena itens de forma crescente por dias de estoque
  allItems.sort((a, b) => a.dias - b.dias);

  if (mode === 'range1') {
    blockTitleText = 'Bloco: Abaixo de 20 dias de Estoque (Atenção Crítica)';
    filteredItems = allItems.filter(item => item.dias < 20);
  } else if (mode === 'range2') {
    blockTitleText = 'Bloco: Entre 20 e 24 dias de Estoque (Atenção)';
    filteredItems = allItems.filter(item => item.dias >= 20 && item.dias <= 24);
  } else if (mode === 'range3') {
    blockTitleText = 'Bloco: Entre 25 e 29 dias de Estoque (Target)';
    filteredItems = allItems.filter(item => item.dias >= 25 && item.dias <= 29);
  } else if (mode === 'range4') {
    blockTitleText = 'Bloco: Acima de 30 dias de Estoque (Excesso)';
    filteredItems = allItems.filter(item => item.dias >= 30);
  } else {
    blockTitleText = 'Visão Completa — Todos os Blocos de Dias de Estoque';
    filteredItems = allItems;
  }

  const modeUpper = (mode || 'ALL').toUpperCase();
  if (tagEl) tagEl.textContent = `ESTOQUE POR SKU • VISÃO AMPLIADA (${modeUpper})`;
  if (titleEl) titleEl.textContent = blockTitleText;

  renderModalRows(filteredItems);

  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function renderModalRows(items) {
  const tbody = document.getElementById('modal-tbody-estoque');
  const countEl = document.getElementById('modal-records-count');
  if (!tbody) return;

  function getBadgeClass(dias) {
    if (dias >= 30) return 'negrito';              // acima de 30 dias: Negrito
    if (dias >= 25 && dias <= 29) return 'verde';   // Target - Entre 25 a 29 dias: Verde
    if (dias >= 20 && dias <= 24) return 'amarelo'; // Entre 20 e 24 dias: Amarelo
    return 'vermelho';                             // Abaixo de 20 dias: Vermelho
  }

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; padding: 24px; color: #94A3B8;">Nenhum registro de estoque encontrado neste bloco.</td></tr>`;
  } else {
    tbody.innerHTML = items.map(item => `
      <tr>
        <td style="font-weight: 700; color: #0C2167;">${item.cliente}</td>
        <td style="font-weight: 600; color: #0F172A;">${item.produto}</td>
        <td style="text-align: center;"><span class="dias-badge ${getBadgeClass(item.dias)}">${item.dias} dias</span></td>
      </tr>
    `).join('');
  }

  if (countEl) countEl.textContent = `Exibindo ${items ? items.length : 0} registro(s)`;
}

function filterModalEstoqueTable() {
  const containerCliente = document.getElementById('select-modal-est-cliente');
  const containerProduto = document.getElementById('select-modal-est-produto');
  
  const selClientes = containerCliente && typeof containerCliente.getSelectedValues === 'function' ? containerCliente.getSelectedValues() : [];
  const typedCliente = document.getElementById('filter-modal-est-cliente')?.value.toLowerCase().trim() || '';
  
  const selProdutos = containerProduto && typeof containerProduto.getSelectedValues === 'function' ? containerProduto.getSelectedValues() : [];
  const typedProduto = document.getElementById('filter-modal-est-produto')?.value.toLowerCase().trim() || '';

  function getProdDesc(r) {
    if (!r) return 'Produto';
    if (r.produto && String(r.produto).trim() !== '') return String(r.produto).trim();
    if (r.DESC_PROD_BQ && String(r.DESC_PROD_BQ).trim() !== '') return String(r.DESC_PROD_BQ).trim();
    if (r.desc_prod_bq && String(r.desc_prod_bq).trim() !== '') return String(r.desc_prod_bq).trim();
    for (const key of Object.keys(r)) {
      if (key.toUpperCase().includes('DESC_PROD_BQ') || key.toUpperCase().includes('DESC_PROD_ARQUIVO_DIST') || key.toUpperCase().includes('DESC_PRODUTO_ARQUIVO') || key.toUpperCase().includes('DESC_PROD_DIST')) {
        if (r[key] && String(r[key]).trim() !== '') return String(r[key]).trim();
      }
    }
    return r.DESC_PROD_ARQUIVO_DIST || r.desc_prod_arquivo_dist || r.DESC_PRODUTO_ARQUIVO_DIST || r.DESCRICAO_PRODUTO || r.SKU_PROD_BQ || r.sku_prod_bq || r.SKU_PROD_DIST || r.sku_prod_dist || 'Produto';
  }

  function getClienteName(r) {
    if (!r) return 'Cliente';
    if (r.razao_social_cliente && String(r.razao_social_cliente).trim() !== '' && String(r.razao_social_cliente).trim() !== 'Cliente') return String(r.razao_social_cliente).trim();
    if (r.DESC_CLIENTE && String(r.DESC_CLIENTE).trim() !== '' && String(r.DESC_CLIENTE).trim() !== 'Cliente') return String(r.DESC_CLIENTE).trim();
    if (r.desc_cliente && String(r.desc_cliente).trim() !== '' && String(r.desc_cliente).trim() !== 'Cliente') return String(r.desc_cliente).trim();
    if (r.desc_distribuidor && String(r.desc_distribuidor).trim() !== '' && String(r.desc_distribuidor).trim() !== 'Cliente') return String(r.desc_distribuidor).trim();
    if (r.DESC_DISTRIBUIDOR && String(r.DESC_DISTRIBUIDOR).trim() !== '' && String(r.DESC_DISTRIBUIDOR).trim() !== 'Cliente') return String(r.DESC_DISTRIBUIDOR).trim();
    if (r.RAZAO_SOCIAL && String(r.RAZAO_SOCIAL).trim() !== '' && String(r.RAZAO_SOCIAL).trim() !== 'Cliente') return String(r.RAZAO_SOCIAL).trim();
    for (const key of Object.keys(r)) {
      if (key.toUpperCase().includes('CLIENTE') || key.toUpperCase().includes('RAZAO') || key.toUpperCase().includes('DISTRIBUIDOR')) {
        if (r[key] && String(r[key]).trim() !== '' && String(r[key]).trim() !== 'Cliente') return String(r[key]).trim();
      }
    }
    return r.desc_distribuidor || r.DESC_DISTRIBUIDOR || 'Cliente';
  }

  const allItems = currentStockRowsData.map(row => ({
    dias: parseInt(row.dias_estoque || row.DIAS_ESTOQUE || '0', 10),
    cliente: getClienteName(row),
    produto: getProdDesc(row)
  }));

  const filtered = allItems.filter(item => {
    const itemCliente = item.cliente.toLowerCase();
    const itemProduto = item.produto.toLowerCase();

    const matchClienteSel = selClientes.length === 0 || selClientes.some(sc => itemCliente.includes(sc.toLowerCase()));
    const matchClienteText = !typedCliente || itemCliente.includes(typedCliente);
    
    const matchProdutoSel = selProdutos.length === 0 || selProdutos.some(sp => itemProduto.includes(sp.toLowerCase()));
    const matchProdutoText = !typedProduto || itemProduto.includes(typedProduto);

    return matchClienteSel && matchClienteText && matchProdutoSel && matchProdutoText;
  });

  renderModalRows(filtered);
}

function closeEstoqueModal() {
  const modal = document.getElementById('modal-estoque-expand');
  if (modal) modal.style.display = 'none';
  document.body.style.overflow = '';
}

/* ── Modal & Card de Positivação por Grupo de Produtos (GRUPO_PRODUTO_DESC_BQ) ── */
let currentPositivRowsData = [];

function openPositivacaoModal(mode) {
  const modal = document.getElementById('modal-positivacao-expand');
  if (!modal) return;

  // RLS STRICT: sem positivação simulada. Mostra apenas dados reais da API.

  if (typeof makeCustomSelect === 'function') {
    makeCustomSelect('select-modal-pos-cliente', 'Todos os Clientes');
    makeCustomSelect('select-modal-pos-grupo', 'Todos os Grupos');
  }

  const uniqueClientes = Array.from(new Set(currentPositivRowsData.map(item => item.cliente || item.razao_social_cliente))).filter(Boolean).sort();
  const uniqueGrupos = Array.from(new Set(currentPositivRowsData.map(item => item.grupo || item.grupo_produto_desc_bq))).filter(Boolean).sort();

  const selPosCliente = document.getElementById('select-modal-pos-cliente');
  const selPosGrupo = document.getElementById('select-modal-pos-grupo');

  if (selPosCliente && typeof selPosCliente.populate === 'function') {
    selPosCliente.populate(uniqueClientes.map(c => ({ value: c, label: c })));
  }
  if (selPosGrupo && typeof selPosGrupo.populate === 'function') {
    selPosGrupo.populate(uniqueGrupos.map(g => ({ value: g, label: g })));
  }

  document.getElementById('filter-modal-pos-cliente')?.removeEventListener('input', filterModalPositivacaoTable);
  document.getElementById('filter-modal-pos-cliente')?.addEventListener('input', filterModalPositivacaoTable);
  document.getElementById('filter-modal-pos-grupo')?.removeEventListener('input', filterModalPositivacaoTable);
  document.getElementById('filter-modal-pos-grupo')?.addEventListener('input', filterModalPositivacaoTable);

  if (mode && mode !== 'all') {
    let searchStr = decodeURIComponent(mode).toLowerCase().trim();
    const filteredByMode = currentPositivRowsData.filter(item => {
      const g = (item.grupo || item.grupo_produto_desc_bq || '').toLowerCase();
      return g.includes(searchStr);
    });
    renderPositivacaoModalRows(filteredByMode.length > 0 ? filteredByMode : currentPositivRowsData);
  } else {
    renderPositivacaoModalRows(currentPositivRowsData);
  }

  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function renderPositivacaoModalRows(items) {
  const tbody = document.getElementById('modal-tbody-positivacao');
  const countEl = document.getElementById('modal-positiv-records-count');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding: 24px; color: #94A3B8;">Nenhum registro de Positivação encontrado.</td></tr>`;
    if (countEl) countEl.textContent = `Exibindo 0 registros`;
    return;
  }

  tbody.innerHTML = items.map(item => {
    const cliente = item.cliente || item.razao_social_cliente || 'Cliente';
    const grupo = item.grupo || item.grupo_produto_desc_bq || 'Grupo';
    const isPositivado = item.isPositivado !== undefined 
      ? (item.isPositivado === true || item.isPositivado === 'true' || item.isPositivado === 1) 
      : (item.status === 'POSITIVADO' || item.compras_mes_atual > 0);
    const isNovoCliente = item.isNovoCliente !== undefined 
      ? (item.isNovoCliente === true || item.isNovoCliente === 'true' || item.isNovoCliente === 1) 
      : (item.is_novo_cliente === true || item.compras_3m_anteriores === 0);

    return `
      <tr>
        <td style="font-weight: 700; color: #0C2167;">${cliente}</td>
        <td style="font-weight: 600; color: #0F172A;">${grupo}</td>
        <td style="text-align: center;">
          ${isPositivado 
            ? '<span class="status-badge positiv">POSITIVADO</span>' 
            : '<span class="status-badge nao-positiv">NÃO POSITIVADO</span>'}
        </td>
        <td style="text-align: center;">
          ${isNovoCliente 
            ? '<span class="badge-novo-cliente">⭐ NOVO CLIENTE</span>' 
            : '<span class="badge-recorrente">CLIENTE RECORRENTE</span>'}
        </td>
      </tr>
    `;
  }).join('');

  if (countEl) countEl.textContent = `Exibindo ${items.length} registro(s)`;
}

function filterModalPositivacaoTable() {
  const containerCliente = document.getElementById('select-modal-pos-cliente');
  const containerGrupo = document.getElementById('select-modal-pos-grupo');

  const selClientes = containerCliente && typeof containerCliente.getSelectedValues === 'function' ? containerCliente.getSelectedValues() : [];
  const typedCliente = document.getElementById('filter-modal-pos-cliente')?.value.toLowerCase().trim() || '';

  const selGrupos = containerGrupo && typeof containerGrupo.getSelectedValues === 'function' ? containerGrupo.getSelectedValues() : [];
  const typedGrupo = document.getElementById('filter-modal-pos-grupo')?.value.toLowerCase().trim() || '';

  const filtered = currentPositivRowsData.filter(item => {
    const itemCliente = (item.cliente || item.razao_social_cliente || '').toLowerCase();
    const itemGrupo = (item.grupo || item.grupo_produto_desc_bq || '').toLowerCase();

    const matchClienteSel = selClientes.length === 0 || selClientes.some(sc => itemCliente.includes(sc.toLowerCase()));
    const matchClienteText = !typedCliente || itemCliente.includes(typedCliente);
    
    const matchGrupoSel = selGrupos.length === 0 || selGrupos.some(sg => itemGrupo.includes(sg.toLowerCase()));
    const matchGrupoText = !typedGrupo || itemGrupo.includes(typedGrupo);

    return matchClienteSel && matchClienteText && matchGrupoSel && matchGrupoText;
  });

  renderPositivacaoModalRows(filtered);
}

function closePositivacaoModal() {
  const modal = document.getElementById('modal-positivacao-expand');
  if (modal) modal.style.display = 'none';
  document.body.style.overflow = '';
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeEstoqueModal();
    closePositivacaoModal();
  }
});



function updatePositivacaoCard(positivRows, metaVal) {
  const drillList = document.getElementById('positiv-drill-list');
  const totalCountEl = document.getElementById('total-positiv-count');
  const metaEl = document.getElementById('positiv-meta-val');
  const realizadoEl = document.getElementById('positiv-realizado-val');
  const coverageEl = document.getElementById('positiv-coverage-text');
  const subMetaEl = document.getElementById('positiv-meta-sub') || document.querySelector('.positiv-metric-box.box-meta .positiv-box-sub');
  const subRealizadoEl = document.getElementById('positiv-realizado-sub');
  const diffBadge = document.getElementById('positiv-diff-badge');
  const boxRealizadoWrap = document.getElementById('box-realizado-wrap');
  const progressContainer = document.getElementById('positiv-progress-container');
  const progressFill = document.getElementById('positiv-progress-fill');
  const statusDot = document.getElementById('positiv-status-dot');

  const meta = (typeof metaVal === 'number' && metaVal > 0) ? metaVal : 0;

  if (metaEl) {
    if (meta > 0) {
      metaEl.textContent = meta.toString();
      if (subMetaEl) subMetaEl.textContent = 'Meta estipulada';
    } else {
      metaEl.textContent = '--';
      if (subMetaEl) subMetaEl.textContent = 'Aguardando meta';
    }
  }

  if (!positivRows || positivRows.length === 0) {
    if (drillList) drillList.innerHTML = '<div style="text-align:center; padding: 24px; color: #94A3B8; font-size: 13px;">Nenhum cliente positivado no período selecionado.</div>';
    if (totalCountEl) totalCountEl.innerHTML = '0 <span>Clientes</span>';
    if (realizadoEl) realizadoEl.textContent = '0';
    if (coverageEl) coverageEl.textContent = meta > 0 ? `0 de ${meta} clientes (0%)` : 'Base ativa no período';
    if (diffBadge) diffBadge.style.display = 'none';
    if (progressContainer) progressContainer.style.display = 'none';
    if (statusDot) statusDot.className = 'status-indicator-dot dot-neutral';
    if (boxRealizadoWrap) boxRealizadoWrap.className = 'positiv-metric-box box-realizado';
    if (subRealizadoEl) subRealizadoEl.innerHTML = '<span class="diff-tag neutral">Clientes atendidos</span>';
    currentPositivRowsData = [];
    return;
  }

  currentPositivRowsData = positivRows || [];

  // Agrupa por GRUPO_PRODUTO_DESC_BQ
  const gruposMap = new Map();
  const allClientsSet = new Set();
  const positivadosSet = new Set();

  positivRows.forEach(row => {
    const grupo = row.grupo || row.grupo_produto_desc_bq || row.GRUPO_PRODUTO_DESC_BQ || row.GRUPO_PRODUTO || row.grupo_produto || 'Pães Tradicionais & Especialidades';
    const cliente = row.cliente || row.razao_social_cliente || row.RAZAO_SOCIAL || 'Cliente Distribuidor';
    const cnpj = row.cnpj || row.cnpj_cliente || row.CNPJ || 'CNPJ';
    
    const comprasMes = parseInt(row.compras_mes_atual || row.COMPRAS_MES_ATUAL || (row.status === 'POSITIVADO' ? 1 : 0), 10);
    const compras3M = parseInt(row.compras_3m_anteriores || row.COMPRAS_3M_ANTERIORES || (row.isNovoCliente ? 0 : 1), 10);
    
    const isPositivado = row.isPositivado !== undefined 
      ? (row.isPositivado === true || row.isPositivado === 'true' || row.isPositivado === 1) 
      : (comprasMes > 0 || row.status === 'POSITIVADO');
    const isNovoCliente = row.isNovoCliente !== undefined 
      ? (row.isNovoCliente === true || row.isNovoCliente === 'true' || row.isNovoCliente === 1) 
      : (isPositivado && compras3M === 0);

    allClientsSet.add(cliente);
    if (isPositivado) {
      positivadosSet.add(cliente);
    }

    if (!gruposMap.has(grupo)) {
      gruposMap.set(grupo, []);
    }

    gruposMap.get(grupo).push({
      cliente,
      cnpj,
      grupo,
      isPositivado,
      isNovoCliente
    });
  });

  const realVal = positivadosSet.size;

  if (totalCountEl) {
    totalCountEl.innerHTML = `${realVal} <span>Clientes</span>`;
  }
  if (realizadoEl) {
    realizadoEl.textContent = realVal.toString();
  }

  // ── Balanço Meta vs Realizado com Condicionais (Cores, Setas, Progresso) ──
  if (meta > 0) {
    const pct = Math.round((realVal / meta) * 100);
    const diff = realVal - meta;

    let status = 'positive';
    let statusColor = '#059669';
    let badgeClass = 'badge-up';
    let arrow = '↑';
    let dotClass = 'dot-positive';
    let barClass = 'bar-positive';
    let boxClass = 'is-positive';

    if (realVal >= meta) {
      status = 'positive';
      statusColor = '#059669';
      badgeClass = 'badge-up';
      arrow = '↑';
      dotClass = 'dot-positive';
      barClass = 'bar-positive';
      boxClass = 'is-positive';
    } else if (pct >= 70) {
      status = 'warning';
      statusColor = '#D97706';
      badgeClass = 'badge-warning';
      arrow = '↓';
      dotClass = 'dot-warning';
      barClass = 'bar-warning';
      boxClass = 'is-warning';
    } else {
      status = 'negative';
      statusColor = '#DC2626';
      badgeClass = 'badge-down';
      arrow = '↓';
      dotClass = 'dot-negative';
      barClass = 'bar-negative';
      boxClass = 'is-negative';
    }

    // 1. Badge no topo (ao lado da contagem total)
    if (diffBadge) {
      diffBadge.style.display = 'inline-block';
      diffBadge.className = badgeClass;
      diffBadge.textContent = `${arrow} ${pct}% ating.`;
      diffBadge.title = realVal >= meta
        ? `Meta superada! (${pct}% do objetivo)`
        : `Atingimento de ${pct}% da meta estipulada`;
    }

    // 2. Subtítulo dinâmico do bloco Realizado
    if (subRealizadoEl) {
      if (realVal >= meta) {
        subRealizadoEl.innerHTML = `<span class="diff-tag positive">↑ +${diff} clientes (superou)</span>`;
      } else {
        const faltam = Math.abs(diff);
        subRealizadoEl.innerHTML = `<span class="diff-tag ${status}">${arrow} Faltam ${faltam} (${pct}%)</span>`;
      }
    }

    // 3. Estilização sutil de destaque no box Realizado
    if (boxRealizadoWrap) {
      boxRealizadoWrap.className = `positiv-metric-box box-realizado ${boxClass}`;
    }

    // 4. Barra de progresso sutil (Atingimento da Meta)
    if (progressContainer && progressFill) {
      progressContainer.style.display = 'block';
      progressFill.className = `positiv-progress-bar ${barClass}`;
      progressFill.style.width = `${Math.min(100, Math.max(0, pct))}%`;
      progressContainer.title = `Progresso da Meta: ${pct}% (${realVal} de ${meta} clientes)`;
    }

    // 5. Rodapé com comparação Realizado vs Meta
    if (statusDot) {
      statusDot.className = `status-indicator-dot ${dotClass}`;
    }
    if (coverageEl) {
      if (realVal >= meta) {
        const surplus = diff > 0 ? ` (+${diff})` : '';
        coverageEl.innerHTML = `<strong>${realVal} de ${meta} clientes</strong> (${pct}%) &bull; <span style="color:#059669; font-weight:750;">Meta superada!${surplus}</span>`;
      } else {
        const faltam = Math.abs(diff);
        coverageEl.innerHTML = `<strong>${realVal} de ${meta} clientes</strong> (${pct}%) &bull; <span style="color:${statusColor}; font-weight:750;">Faltam ${faltam}</span>`;
      }
    }
  } else {
    // Caso sem meta definida
    if (diffBadge) diffBadge.style.display = 'none';
    if (subRealizadoEl) subRealizadoEl.innerHTML = `<span class="diff-tag neutral">Clientes atendidos</span>`;
    if (boxRealizadoWrap) boxRealizadoWrap.className = 'positiv-metric-box box-realizado';
    if (progressContainer) progressContainer.style.display = 'none';
    if (statusDot) statusDot.className = 'status-indicator-dot dot-neutral';
    if (coverageEl) coverageEl.textContent = `${realVal} clientes atendidos no período`;
  }

  if (drillList) {
    const barClasses = ['bar-cyan', 'bar-navy', 'bar-amber', 'bar-purple', 'bar-emerald'];
    let groupIndex = 0;
    let html = '';

    gruposMap.forEach((clientesArr, grupoNome) => {
      groupIndex++;
      const totalClientesNoGrupo = clientesArr.length;
      const positivadosNoGrupo = clientesArr.filter(c => c.isPositivado).length;
      const pctPositivacao = allClientsSet.size > 0 
        ? Math.round((positivadosNoGrupo / allClientsSet.size) * 100) 
        : (totalClientesNoGrupo > 0 ? Math.round((positivadosNoGrupo / totalClientesNoGrupo) * 100) : 0);
      
      const barClass = barClasses[(groupIndex - 1) % barClasses.length];
      const rowId = `pos-${groupIndex}`;
      const grupoEscaped = String(grupoNome || 'Grupo').replace(/'/g, "\\'");

      const tableRows = clientesArr.map(c => `
        <tr>
          <td style="font-weight: 700; color: #0C2167;">${c.cliente}</td>
          <td>
            ${c.isPositivado 
              ? '<span class="status-badge positiv">POSITIVADO</span>' 
              : '<span class="status-badge nao-positiv">NÃO POSITIVADO</span>'}
          </td>
          <td>
            ${c.isNovoCliente 
              ? '<span class="badge-novo-cliente">⭐ NOVO CLIENTE</span>' 
              : '<span class="badge-recorrente">CLIENTE RECORRENTE</span>'}
          </td>
        </tr>
      `).join('');

      html += `
        <div class="drill-row" id="row-${rowId}">
          <div class="drill-row-head" onclick="toggleDrill('${rowId}','pos')">
            <div class="drill-row-bar ${barClass}"></div>
            <div class="drill-row-info">
              <span class="drill-row-tag">${grupoNome.toUpperCase()}</span>
              <span class="drill-row-label">${positivadosNoGrupo} cliente(s) • ${pctPositivacao}% de positivação</span>
            </div>
            <div class="drill-row-right">
              <span class="drill-count">${pctPositivacao}%</span>
              <button class="btn-expand-block" onclick="event.stopPropagation(); openPositivacaoModal('${grupoEscaped}')" title="Ampliar grupo ${grupoNome}">
                <svg viewBox="0 0 16 16" fill="none" width="12" height="12"><path d="M2 6V2h4M14 6V2h-4M2 10v4h4M14 10v4h-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
              <svg class="drill-chevron" viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
          </div>
          <div class="drill-content" id="${rowId}">
            <table class="drill-table">
              <thead><tr><th>Cliente (Razão Social)</th><th>Status</th><th>Classificação</th></tr></thead>
              <tbody>
                ${tableRows}
              </tbody>
            </table>
          </div>
        </div>
      `;
    });

    drillList.innerHTML = html;
  }
}

function updateStockCard(stockRows) {
  currentStockRowsData = stockRows || [];
  const tbodyResumo = document.getElementById('tbody-estoque-resumo');
  const totalSkusEl = document.getElementById('total-skus-count');

  if (!stockRows || stockRows.length === 0) {
    if (tbodyResumo) tbodyResumo.innerHTML = '<tr><td colspan="2" style="text-align:center; padding: 20px; color:#94A3B8;">Nenhum produto em estoque</td></tr>';
    if (totalSkusEl) totalSkusEl.innerHTML = '0 <span>SKUs</span>';
    return;
  }

  function getProdDesc(r) {
    if (!r) return 'Produto';
    if (r.produto && String(r.produto).trim() !== '') return String(r.produto).trim();
    if (r.DESC_PROD_BQ && String(r.DESC_PROD_BQ).trim() !== '') return String(r.DESC_PROD_BQ).trim();
    if (r.desc_prod_bq && String(r.desc_prod_bq).trim() !== '') return String(r.desc_prod_bq).trim();
    for (const key of Object.keys(r)) {
      if (key.toUpperCase().includes('DESC_PROD_BQ') || key.toUpperCase().includes('DESC_PROD_ARQUIVO_DIST') || key.toUpperCase().includes('DESC_PRODUTO_ARQUIVO') || key.toUpperCase().includes('DESC_PROD_DIST')) {
        if (r[key] && String(r[key]).trim() !== '') return String(r[key]).trim();
      }
    }
    return r.DESC_PROD_ARQUIVO_DIST || r.desc_prod_arquivo_dist || r.DESC_PRODUTO_ARQUIVO_DIST || r.DESCRICAO_PRODUTO || r.SKU_PROD_BQ || r.sku_prod_bq || r.SKU_PROD_DIST || r.sku_prod_dist || 'Produto';
  }

  const distinctSkusMap = new Map();

  stockRows.forEach(row => {
    const dias = parseInt(row.dias_estoque || row.DIAS_ESTOQUE || '0', 10);
    const mediaVenda = parseFloat(row.media_venda || row.MEDIA_VENDA || '0') || 0;
    const qtdeEstoque = parseFloat(row.total_qty_stock || row.QTDE_ESTOQUE || '0') || 0;
    const produto = getProdDesc(row);
    const skuCode = String(row.sku_prod_dist || row.SKU_PROD_DIST || row.SKU_PROD_BQ || row.COD_PROD_DIST || '').trim();
    const key = skuCode || produto;

    if (!distinctSkusMap.has(key)) {
      distinctSkusMap.set(key, {
        produto,
        skuCode,
        dias,
        mediaVenda,
        qtdeEstoque
      });
    }
  });

  const uniqueItems = Array.from(distinctSkusMap.values());

  // 1. Ordenação crescente de dias de estoque (menor para maior)
  uniqueItems.sort((a, b) => a.dias - b.dias);

  // 2. Média ponderada de dias de estoque de acordo com o consumo (media_venda no mês)
  let sumPonderado = 0;
  let sumPesos = 0;
  uniqueItems.forEach(item => {
    if (item.mediaVenda > 0) {
      sumPonderado += (item.dias * item.mediaVenda);
      sumPesos += item.mediaVenda;
    }
  });

  let mediaPonderada = 0;
  if (sumPesos > 0) {
    mediaPonderada = Math.round(sumPonderado / sumPesos);
  } else if (uniqueItems.length > 0) {
    const sumDias = uniqueItems.reduce((acc, curr) => acc + curr.dias, 0);
    mediaPonderada = Math.round(sumDias / uniqueItems.length);
  }

  // Regra de Farol Condicional
  // acima de 30 dias: Negrito
  // Target - Entre 25 a 29 dias: Verde
  // Entre 20 e 24 dias: Amarelo
  // Abaixo de 20 dias: Vermelho
  function getBadgeClass(dias) {
    if (dias >= 30) return 'negrito';
    if (dias >= 25 && dias <= 29) return 'verde';
    if (dias >= 20 && dias <= 24) return 'amarelo';
    return 'vermelho';
  }

  if (totalSkusEl) {
    totalSkusEl.innerHTML = `${mediaPonderada} <span>dias</span>`;
    totalSkusEl.title = `Média ponderada pelo consumo mensal de cada item (${uniqueItems.length} SKUs): ${mediaPonderada} dias`;
  }

  if (tbodyResumo) {
    if (uniqueItems.length === 0) {
      tbodyResumo.innerHTML = '<tr><td colspan="2" style="text-align:center; padding: 20px; color:#94A3B8;">Nenhum produto em estoque</td></tr>';
    } else {
      tbodyResumo.innerHTML = uniqueItems.map(item => `
        <tr>
          <td class="resumo-item-cell">
            <div class="resumo-prod-name" title="${item.produto}">${item.produto}</div>
            ${item.skuCode ? `<div class="resumo-sku-code">SKU: ${item.skuCode}</div>` : ''}
          </td>
          <td class="resumo-dias-cell">
            <span class="dias-badge ${getBadgeClass(item.dias)}">${item.dias} dias</span>
          </td>
        </tr>
      `).join('');
    }
  }
}

let isInitialDashboardLoad = true;
let filterDebounceTimer = null;

function showGlobalLoader(msg) {
  const overlay = document.getElementById('global-loading-overlay');
  if (!overlay) return;
  if (msg) {
    const subtitle = overlay.querySelector('.loading-subtitle');
    if (subtitle) subtitle.textContent = msg;
  }
  overlay.classList.remove('hidden');
}

function hideGlobalLoader() {
  const overlay = document.getElementById('global-loading-overlay');
  if (!overlay) return;
  overlay.classList.add('hidden');
}

function showFilterUpdatingIndicator() {
  let bar = document.getElementById('filter-loading-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'filter-loading-bar';
    bar.className = 'filter-loading-bar';
    document.body.appendChild(bar);
  }
  bar.classList.add('active');
  const grid = document.querySelector('.kpi-grid');
  if (grid) grid.classList.add('is-refreshing');
}

function hideFilterUpdatingIndicator() {
  const bar = document.getElementById('filter-loading-bar');
  if (bar) bar.classList.remove('active');
  const grid = document.querySelector('.kpi-grid');
  if (grid) grid.classList.remove('is-refreshing');
}

function triggerDashboardRefresh(delay = 200) {
  clearTimeout(filterDebounceTimer);
  showFilterUpdatingIndicator();
  filterDebounceTimer = setTimeout(() => {
    updateDashboardData();
  }, delay);
}

async function updateDashboardData() {
  // O popup invasivo de tela cheia só aparece na PRIMEIRA carga da página.
  // Filtros posteriores atualizam suavemente em background sem bloquear o usuário!
  if (isInitialDashboardLoad) {
    showGlobalLoader('Buscando indicadores no Databricks e processando regras...');
  } else {
    showFilterUpdatingIndicator();
  }

  const produto = getSafeSelectedValues('select-produto').join(',');
  const sku = getSafeSelectedValues('select-sku').join(',');
  const pedido = getSafeSelectedValues('select-pedido').join(',');
  const dia = getSafeSelectedValues('select-dia').join(',');
  const semana = getSafeSelectedValues('select-semana').join(',');
  const mes = getSafeSelectedValues('select-mes').join(',');
  const ano = getSafeSelectedValues('select-ano').join(',');

  const queryParams = new URLSearchParams();
  if (produto) queryParams.append('produto', produto);
  if (sku) queryParams.append('sku', sku);
  if (pedido) queryParams.append('pedido', pedido);
  if (dia) queryParams.append('dia', dia);
  if (semana) queryParams.append('semana', semana);
  if (mes) queryParams.append('mes', mes);
  if (ano) queryParams.append('ano', ano);

  const urlParams = new URLSearchParams(window.location.search);
  const perfilParam = urlParams.get('perfil');
  if (perfilParam) queryParams.append('perfil', perfilParam);

  const isVolume = document.getElementById('toggleValVol')?.checked || false;

  const formatNumber = (val) => {
    if (isVolume) {
      if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`;
      if (val >= 1000) return `${(val / 1000).toFixed(1)}K`;
      return Math.round(val).toString();
    } else {
      if (val >= 1000000) return `R$ ${(val / 1000000).toFixed(1)}M`;
      if (val >= 1000) return `R$ ${(val / 1000).toFixed(1)}K`;
      return `R$ ${Math.round(val)}`;
    }
  };

  function getVal(obj, key) {
    if (!obj) return 0;
    const targetKey = key.toLowerCase();
    for (const k of Object.keys(obj)) {
      if (k.toLowerCase() === targetKey) {
        const val = parseFloat(obj[k]);
        return isNaN(val) ? 0 : val;
      }
    }
    return 0;
  }

  const filterState = { produto, sku, pedido, dia, semana, mes, ano };

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 20000);

    const res = await fetch(`${API_BASE}/api/kpi?${queryParams.toString()}`, { 
      credentials: 'include',
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    const result = await res.json();
    
    if (result.dados && (result.dados.sellin.length > 0 || result.dados.sellout.length > 0 || result.dados.stock.length > 0 || (result.dados.orders && result.dados.orders.length > 0))) {
      console.log('Dados atualizados do Databricks:', result.dados);

      // Puxa o nome real do distribuidor: prioriza o mapeamento RLS da sessão, depois dados dos pedidos
      let fullDistName = (userSessionData && userSessionData.distribuidores && userSessionData.distribuidores[0] && userSessionData.distribuidores[0].nome)
        ? userSessionData.distribuidores[0].nome
        : (userSessionData && userSessionData.desc_distribuidor && userSessionData.desc_distribuidor !== 'Distribuidor Bimbo QSR' && userSessionData.desc_distribuidor !== 'Administrador')
          ? userSessionData.desc_distribuidor
          : null;

      if (!fullDistName) {
        const _greetOrd = result.dados.orders || [];
        const _greetStk = result.dados.stock || [];
        const _greetSin = result.dados.sellin || [];
        const sampleRow = _greetOrd[0] || _greetStk[0] || _greetSin[0];
        if (sampleRow) {
          const distNameFromData = sampleRow.desc_distribuidor || sampleRow.DESC_DISTRIBUIDOR || sampleRow.NOME_DISTRIBUIDOR;
          if (distNameFromData && String(distNameFromData).trim() !== '' && String(distNameFromData).trim() !== 'null') {
            fullDistName = String(distNameFromData).trim();
          }
        }
      }

      if (fullDistName) {
        const greetingNameEl = document.getElementById('greeting-name');
        if (greetingNameEl) {
          greetingNameEl.textContent = formatGreetingDistName(fullDistName);
          greetingNameEl.title = fullDistName;
          greetingNameEl.style.color = '#38BDF8';
        }
        if (userSessionData) {
          userSessionData.desc_distribuidor = fullDistName;
        }
      }
      
      // Sell-In e Sell-Out para os Cards de KPI:
      // Se houver mês filtrado, soma apenas aquele mês; se for 'Todos', soma o ano todo.
      let rowsSellIn = result.dados.sellin || [];
      let rowsSellOut = result.dados.sellout || [];
      if (filterState.mes && filterState.mes !== '' && filterState.mes !== 'Todos') {
        const selectedMonths = filterState.mes.split(',').map(m => parseInt(m.trim(), 10)).filter(m => !isNaN(m));
        if (selectedMonths.length > 0) {
          rowsSellIn = rowsSellIn.filter(r => selectedMonths.includes(parseInt(r.MES || r.mes, 10)));
          rowsSellOut = rowsSellOut.filter(r => selectedMonths.includes(parseInt(r.MES || r.mes, 10)));
        }
      }

      let vlSellIn = 0;
      let vlForecast = 0;
      if (rowsSellIn.length > 0) {
        if (isVolume) {
          vlSellIn = rowsSellIn.reduce((acc, curr) => acc + getVal(curr, 'total_qty_sell_in'), 0);
          vlForecast = rowsSellIn.reduce((acc, curr) => acc + getVal(curr, 'total_qty_forecast'), 0);
        } else {
          vlSellIn = rowsSellIn.reduce((acc, curr) => acc + getVal(curr, 'total_vl_sell_in'), 0);
          vlForecast = rowsSellIn.reduce((acc, curr) => acc + getVal(curr, 'total_vl_forecast'), 0);
        }
      }
      
      let vlSellOut = 0;
      let vlMetaSellOut = isVolume ? vlForecast : 0;
      if (rowsSellOut.length > 0) {
        if (isVolume) {
          vlSellOut = rowsSellOut.reduce((acc, curr) => acc + getVal(curr, 'total_qty_dz_sell_out'), 0);
          vlMetaSellOut = vlForecast; // Meta de volume de Sell-Out é igual à meta de volume de Sell-In (Forecast em DZ)
        } else {
          vlSellOut = rowsSellOut.reduce((acc, curr) => acc + getVal(curr, 'total_vl_sell_out'), 0);
          vlMetaSellOut = rowsSellOut.reduce((acc, curr) => acc + getVal(curr, 'total_vl_meta'), 0);
        }
      }

      updateCardGaugeAndDiff('card-sellin', 'sellin-diff-info', vlSellIn, vlForecast, formatNumber);
      updateCardGaugeAndDiff('card-sellout', 'sellout-diff-info', vlSellOut, vlMetaSellOut, formatNumber);
      updateOrderPipelineCards(result.dados.order_metrics, isVolume, formatNumber, vlSellIn);

      // Renderiza Fita Horizontal de Tracking Diário de Sell-Out
      const selYearTracking = (filterState.ano && !isNaN(parseInt(filterState.ano, 10))) ? parseInt(filterState.ano, 10) : (new Date().getFullYear());
      let selMonthTracking = (new Date().getMonth() + 1);
      if (filterState.mes && filterState.mes !== '' && filterState.mes !== 'Todos') {
        const mNum = parseInt(filterState.mes.split(',')[0].trim(), 10);
        if (!isNaN(mNum) && mNum >= 1 && mNum <= 12) selMonthTracking = mNum;
      }
      renderTrackingRibbon(result.dados.tracking || [], selYearTracking, selMonthTracking, isVolume, formatNumber);

      let currentStock = result.dados.stock || [];
      let currentOrders = result.dados.orders || [];
      let currentPositiv = result.dados.positiv || [];

      // ── Captura o dataset RLS completo (sem filtros de SKU/Pedido) para popular os dropdowns ──
      const allOrdersRLS = currentOrders.slice();
      const allStockRLS = currentStock.slice();

      // Filtro por Produto (DESC_PROD_BQ)
      if (filterState.produto && filterState.produto !== '') {
        const prodSel = filterState.produto.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);

        const filterByProd = (item) => {
          const prodName = (item.produto || item.PRODUTO || item.DESC_PROD_BQ || item.desc_prod_bq || item.DESC_PROD_ARQUIVO_DIST || item.desc_prod_arquivo_dist || '').toLowerCase();
          return prodSel.some(p => prodName.includes(p) || p.includes(prodName));
        };
        const fStock = currentStock.filter(filterByProd);
        if (fStock.length > 0) currentStock = fStock;
        const fOrders = currentOrders.filter(filterByProd);
        if (fOrders.length > 0) currentOrders = fOrders;
      }

      if (filterState.sku && filterState.sku !== '') {
        const skusSel = filterState.sku.split(',').map(s => {
          let val = s.trim().toLowerCase();
          if (val.includes(' - ')) val = val.split(' - ')[0].trim().toLowerCase();
          return val;
        }).filter(Boolean);

        const filterBySku = (item) => {
          const prodName = (item.DESC_PROD_ARQUIVO_DIST || item.desc_prod_arquivo_dist || item.DESCRICAO_PRODUTO || '').toLowerCase();
          const prodSku = (item.SKU_PROD_DIST || item.sku_prod_dist || item.SKU_DISTRIB || item.sku_distrib || item.COD_PRODUTO || '').toLowerCase();
          return skusSel.some(filterSku => prodSku.includes(filterSku) || prodName.includes(filterSku));
        };

        const fStock = currentStock.filter(filterBySku);
        if (fStock.length > 0) currentStock = fStock;

        const fOrders = currentOrders.filter(filterBySku);
        if (fOrders.length > 0) currentOrders = fOrders;
      }

      if (filterState.pedido && filterState.pedido !== '') {
        const pedsSel = filterState.pedido.split(',').map(p => p.trim().toLowerCase()).filter(Boolean);
        const fOrders = currentOrders.filter(item => {
          const pedNum = String(item.numero_pedido || item.NUMERO_PEDIDO || item.NUM_PEDIDO || '').toLowerCase();
          return pedsSel.some(filterPed => pedNum.includes(filterPed));
        });
        if (fOrders.length > 0) currentOrders = fOrders;
      }

      // Sem fallback simulado: se estoque ou orders estão vazios, mostra vazio
      if (!currentStock) currentStock = [];
      if (!currentOrders) currentOrders = [];

      updateStockCard(currentStock);
      updateGradeLogistica(currentOrders, formatNumber);

      // ── Sincroniza os dropdowns de Pedido e SKU usando o dataset RLS COMPLETO
      const allOrd = (typeof allOrdersRLS !== 'undefined' && allOrdersRLS.length > 0) ? allOrdersRLS : currentOrders;
      const allStk = (typeof allStockRLS !== 'undefined' && allStockRLS.length > 0) ? allStockRLS : currentStock;

      let uniqueOrders = Array.from(new Set(allOrd.map(r => String(r.numero_pedido || r.NUMERO_PEDIDO || r.NUM_PEDIDO || '')).filter(Boolean))).sort();
      
      if (window._pedidosFromApi && window._pedidosFromApi.length > 0) {
        const apiOrderVals = window._pedidosFromApi.map(p => p.value);
        uniqueOrders = Array.from(new Set([...apiOrderVals, ...uniqueOrders])).sort();
      }

      if (uniqueOrders.length > 0) {
        const pedSelect = document.getElementById('select-pedido');
        if (pedSelect && pedSelect.populate) {
          const currentSelected = pedSelect.getSelectedValues ? pedSelect.getSelectedValues() : [];
          const orderOpts = uniqueOrders.map(p => ({ value: p, label: p }));
          pedSelect.populate(orderOpts, currentSelected);
        }
      }

      const uniqueSkus = Array.from(new Set(allStk.map(r => String(r.SKU_PROD_DIST || r.sku_prod_dist || r.SKU_DISTRIB || r.sku_distrib || r.COD_PRODUTO || '')).filter(Boolean))).sort();
      if (uniqueSkus.length > 0) {
        const skuSelect = document.getElementById('select-sku');
        if (skuSelect && skuSelect.populate) {
          const currentSelected = skuSelect.getSelectedValues ? skuSelect.getSelectedValues() : [];
          const skuOpts = uniqueSkus.map(s => ({ value: s, label: s }));
          skuSelect.populate(skuOpts, currentSelected);
        }
      }

      // ── Gráfico de Positivação e Metas (histórico mensal, ignora filtro de mês) ──
      const monthlyPositiv = Array(12).fill(0);
      const monthlyPositivPct = Array(12).fill(0);
      const monthlyPositivMeta = Array(12).fill(0);
      let totalBaseClientes = 0;
      (result.dados.positiv_monthly || []).forEach(row => {
        const m = parseInt(row.MES || row.mes, 10);
        if (m >= 1 && m <= 12) {
          monthlyPositiv[m - 1] += parseInt(row.clientes_positivados || row.CLIENTES_POSITIVADOS || 0, 10);
          monthlyPositivMeta[m - 1] += parseInt(row.meta_positivacao || row.META_POSITIVACAO || 0, 10);
          monthlyPositivPct[m - 1] = parseFloat(row.pct_positivacao || row.PCT_POSITIVACAO || 0);
          const baseCl = parseInt(row.total_base_clientes || row.TOTAL_BASE_CLIENTES || 0, 10);
          if (baseCl > totalBaseClientes) totalBaseClientes = baseCl;
        }
      });
      if (totalBaseClientes > 0) {
        for (let i = 0; i < 12; i++) {
          if (monthlyPositiv[i] > 0 && (!monthlyPositivPct[i] || monthlyPositivPct[i] === 0)) {
            monthlyPositivPct[i] = parseFloat(((monthlyPositiv[i] / totalBaseClientes) * 100).toFixed(1));
          }
        }
      }

      // Identifica a meta do período filtrado para o card de resumo de positivação
      // Como a Positivação mede clientes únicos distintos (COUNT DISTINCT), a meta representa a base de clientes a ser atingida no período
      const mesFilterVals = getSafeSelectedValues('select-mes');
      let currentPeriodPositivMeta = 0;

      const selectedMonths = mesFilterVals
        .map(v => parseInt(v, 10))
        .filter(m => !isNaN(m) && m >= 1 && m <= 12);

      if (selectedMonths.length > 0) {
        // Se há meses filtrados (único ou múltiplos), usa a meta da base de clientes do período selecionado
        const metasSelected = selectedMonths
          .map(m => monthlyPositivMeta[m - 1])
          .filter(val => typeof val === 'number' && val > 0);

        if (metasSelected.length > 0) {
          currentPeriodPositivMeta = Math.max(...metasSelected);
        } else if (totalBaseClientes > 0) {
          currentPeriodPositivMeta = totalBaseClientes;
        }
      } else {
        // Se nenhum mês está filtrado ("Todos"), a meta é a base ativa de clientes ou a maior meta mensal
        const allMetas = monthlyPositivMeta.filter(val => typeof val === 'number' && val > 0);
        if (allMetas.length > 0) {
          currentPeriodPositivMeta = Math.max(...allMetas);
        } else if (totalBaseClientes > 0) {
          currentPeriodPositivMeta = totalBaseClientes;
        }
      }

      if (currentPositiv && currentPositiv.length > 0) {
        updatePositivacaoCard(currentPositiv, currentPeriodPositivMeta);
      } else {
        updatePositivacaoCard([], currentPeriodPositivMeta);
      }

      const gapEl = document.getElementById('sellout-gap');
      if (gapEl) {
        if (vlMetaSellOut > 0) {
          const isAbove = vlSellOut >= vlMetaSellOut;
          const absDiff = Math.abs(vlSellOut - vlMetaSellOut);
          gapEl.className = isAbove ? 'foot-val positive' : 'foot-val negative';
          gapEl.textContent = `${isAbove ? '+' : '-'}${formatNumber(absDiff)}`;
        } else {
          gapEl.className = 'foot-val';
          gapEl.textContent = formatNumber(vlSellOut);
        }
      }

      // Group monthly data for the bar chart (Exibe o histórico completo de 12 meses independente do mês selecionado)
      const monthlyIn = Array(12).fill(0);
      const monthlyMetaIn = Array(12).fill(0);
      const monthlyOut = Array(12).fill(0);
      const monthlyMetaOut = Array(12).fill(0);

      result.dados.sellin.forEach(row => {
        const m = parseInt(row.MES || row.mes, 10);
        if (m >= 1 && m <= 12) {
          monthlyIn[m - 1] += isVolume ? getVal(row, 'total_qty_sell_in') : getVal(row, 'total_vl_sell_in');
          monthlyMetaIn[m - 1] += isVolume ? getVal(row, 'total_qty_forecast') : getVal(row, 'total_vl_forecast');
        }
      });

      const monthlySelloutVal = Array(12).fill(0);

      result.dados.sellout.forEach(row => {
        const m = parseInt(row.MES || row.mes, 10);
        if (m >= 1 && m <= 12) {
          monthlyOut[m - 1] += isVolume ? getVal(row, 'total_qty_dz_sell_out') : getVal(row, 'total_vl_sell_out');
          monthlySelloutVal[m - 1] += getVal(row, 'total_vl_sell_out');
          if (!isVolume) {
            monthlyMetaOut[m - 1] += getVal(row, 'total_vl_meta');
          }
        }
      });

      if (isVolume) {
        // Meta de volume de Sell-Out é igual à meta de volume de Sell-In (Forecast em DZ),
        // conforme definido na regra de negócio do portal (linha 1733: vlMetaSellOut = vlForecast)
        for (let i = 0; i < 12; i++) {
          monthlyMetaOut[i] = monthlyMetaIn[i];
        }
      }

      // Cálculo do Ticket Médio mensal (Sell-out em R$ / # Clientes Positivados)
      const monthlyTicketMedio = Array(12).fill(0);
      for (let i = 0; i < 12; i++) {
        if (monthlyPositiv[i] > 0 && monthlySelloutVal[i] > 0) {
          monthlyTicketMedio[i] = Math.round(monthlySelloutVal[i] / monthlyPositiv[i]);
        }
      }

      buildBarChart(monthlyIn, monthlyOut, isVolume, monthlyMetaOut, monthlyMetaIn);
      buildPositivChart(monthlyPositiv, monthlyPositivPct, totalBaseClientes, monthlyPositivMeta, monthlyTicketMedio);

      // ── DNA de Vendas Cards ──
      let siAcum = 0, fcAcum = 0, soAcum = 0, moAcum = 0;
      (result.dados.sellin || []).forEach(r => {
        siAcum += isVolume ? getVal(r, 'total_qty_sell_in') : getVal(r, 'total_vl_sell_in');
        fcAcum += isVolume ? getVal(r, 'total_qty_forecast') : getVal(r, 'total_vl_forecast');
      });
      (result.dados.sellout || []).forEach(r => {
        soAcum += isVolume ? getVal(r, 'total_qty_dz_sell_out') : getVal(r, 'total_vl_sell_out');
        moAcum += isVolume ? 0 : getVal(r, 'total_vl_meta');
      });
      if (isVolume) moAcum = fcAcum;

      renderDnaCards({
        vlSellIn, vlForecast,
        vlSellOut, vlMetaSellOut,
        siAcum, fcAcum,
        soAcum, moAcum
      });

    } else {
      console.log('Sem dados no período selecionado para o distribuidor.');
      updateCardGaugeAndDiff('card-sellin', 'sellin-diff-info', 0, 0, formatNumber);
      updateCardGaugeAndDiff('card-sellout', 'sellout-diff-info', 0, 0, formatNumber);
      updateOrderPipelineCards(null, isVolume, formatNumber, 0);
      renderTrackingRibbon([], new Date().getFullYear(), new Date().getMonth() + 1, isVolume, formatNumber);
      updateStockCard([]);
      updateGradeLogistica([], formatNumber);
      updatePositivacaoCard([], 0);
      buildBarChart(Array(12).fill(0), Array(12).fill(0), isVolume, Array(12).fill(0), Array(12).fill(0));
      buildPositivChart(Array(12).fill(0), Array(12).fill(0), 0, Array(12).fill(0), Array(12).fill(0));
      renderDnaCards({ vlSellIn: 0, vlForecast: 0, vlSellOut: 0, vlMetaSellOut: 0, siAcum: 0, fcAcum: 0, soAcum: 0, moAcum: 0 });
    }
  } catch (err) {
    console.warn('Erro ou timeout ao buscar dados do Databricks:', err.message);
  } finally {
    if (isInitialDashboardLoad) {
      hideGlobalLoader();
      isInitialDashboardLoad = false;
    }
    hideFilterUpdatingIndicator();
  }
}

/* ── RLS STRICT: Todas as funções de dados simulados foram removidas ──
   getSimulatedStockForUser, generateSimulatedPositivacao, applyFallbackUI
   foram eliminadas para garantir que APENAS dados reais do Databricks
   (filtrados pela RLS do Unity Catalog) sejam exibidos no portal. ──── */
function getSimulatedStockForUser() { return []; }
function generateSimulatedPositivacao() { }
function applyFallbackUI() { }

let currentGradeRowsData = [];
let currentGradePage = 1;
const GRADE_PAGE_SIZE = 15;
const expandedOrderIds = new Set();

window.toggleOrderDrilldown = function(orderId) {
  const rowId = `drilldown-${orderId}`;
  const btnId = `btn-toggle-${orderId}`;
  const orderRowId = `order-row-${orderId}`;

  const drillRow = document.getElementById(rowId);
  const btn = document.getElementById(btnId);
  const orderRow = document.getElementById(orderRowId);

  if (!drillRow) return;

  if (expandedOrderIds.has(orderId)) {
    expandedOrderIds.delete(orderId);
    drillRow.style.display = 'none';
    if (btn) {
      btn.textContent = '+';
      btn.title = 'Ver itens do pedido';
    }
    if (orderRow) orderRow.classList.remove('is-expanded');
  } else {
    expandedOrderIds.add(orderId);
    drillRow.style.display = 'table-row';
    if (btn) {
      btn.textContent = '−';
      btn.title = 'Recolher itens';
    }
    if (orderRow) orderRow.classList.add('is-expanded');
  }
};

function updateGradeLogistica(stockRows, formatNumber, targetPage = 1) {
  const tbody = document.getElementById('tbody-grade-logistica');
  const countEl = document.getElementById('grade-count-txt') || document.querySelector('.grade-count');
  const paginationWrap = document.getElementById('grade-pagination-wrap') || document.querySelector('.grade-pagination');

  if (!tbody) return;

  if (stockRows) currentGradeRowsData = stockRows;
  currentGradePage = targetPage || 1;

  if (!currentGradeRowsData || currentGradeRowsData.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 28px; color: #94A3B8;">Nenhum pedido encontrado.</td></tr>`;
    if (countEl) countEl.textContent = `Mostrando 0 de 0 pedidos`;
    if (paginationWrap) paginationWrap.innerHTML = '';
    return;
  }

  function getProdDesc(r) {
    if (!r) return 'Produto';
    if (r.produto && String(r.produto).trim() !== '') return String(r.produto).trim();
    if (r.DESC_PROD_BQ && String(r.DESC_PROD_BQ).trim() !== '') return String(r.DESC_PROD_BQ).trim();
    if (r.desc_prod_bq && String(r.desc_prod_bq).trim() !== '') return String(r.desc_prod_bq).trim();
    if (r.DESC_SKU_DIST && String(r.DESC_SKU_DIST).trim() !== '') return String(r.DESC_SKU_DIST).trim();
    if (r.desc_sku_dist && String(r.desc_sku_dist).trim() !== '') return String(r.desc_sku_dist).trim();
    for (const key of Object.keys(r)) {
      if (key.toUpperCase().includes('DESC_PROD_ARQUIVO_DIST') || key.toUpperCase().includes('DESC_PRODUTO_ARQUIVO') || key.toUpperCase().includes('DESC_PROD_DIST') || key.toUpperCase().includes('DESCRICAO_PRODUTO') || key.toUpperCase().includes('DESC_PROD')) {
        if (r[key] && String(r[key]).trim() !== '') return String(r[key]).trim();
      }
    }
    return r.DESC_PROD_ARQUIVO_DIST || r.desc_prod_arquivo_dist || r.DESC_PRODUTO_ARQUIVO_DIST || r.DESCRICAO_PRODUTO || r.SKU_PROD_BQ || r.sku_prod_bq || 'Produto';
  }

  function getStatusBadgeClass(status) {
    const st = String(status || '').toUpperCase();
    if (st.includes('ENTREGUE')) return 'status-badge order-entregue';
    if (st.includes('FATURADO')) return 'status-badge order-faturado';
    if (st.includes('TRÂNSITO') || st.includes('TRANSITO')) return 'status-badge order-transito';
    return 'status-badge order-processando';
  }

  function formatDate(dStr) {
    if (!dStr) return '-';
    if (typeof dStr === 'string' && dStr.includes('T')) dStr = dStr.split('T')[0];
    const parts = String(dStr).split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
    return dStr;
  }

  const fmtInt = (n) => {
    const num = parseFloat(n);
    return isNaN(num) ? '0' : Math.round(num).toLocaleString('pt-BR');
  };

  const fmtBRL = (val) => {
    const num = parseFloat(val);
    if (isNaN(num)) return 'R$ 0,00';
    return num.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  };

  // Agrupamento por NUMERO_PEDIDO
  const ordersMap = new Map();
  for (const row of currentGradeRowsData) {
    const numPedido = String(row.numero_pedido || row.NUMERO_PEDIDO || row.NUM_PEDIDO || 'SEM-NUMERO').trim();
    if (!ordersMap.has(numPedido)) {
      ordersMap.set(numPedido, {
        numero_pedido: numPedido,
        data_emissao_pedido: row.data_emissao_pedido || row.DATA_EMISSAO_PEDIDO || row.DATA_EMISSAO,
        data_previsao_entrega: row.data_previsao_entrega || row.DATA_PREVISAO_ENTREGA,
        data_entrega: row.data_entrega || row.DATA_ENTREGA,
        desc_status_pedido: row.desc_status_pedido || row.DESC_STATUS_PEDIDO || row.STATUS_PEDIDOS || 'ENTREGUE',
        total_vl_bruto: 0,
        total_vl_atendido: 0,
        total_qtde_un: 0,
        total_qtde_atendida_un: 0,
        total_qtde_cx: 0,
        total_qtde_atendida_cx: 0,
        itens: []
      });
    }

    const order = ordersMap.get(numPedido);
    const vlBruto = parseFloat(row.vl_pedido_bruto || row.VL_PEDIDO_BRUTO || row.valor_bruto || 0);
    const vlAtendido = parseFloat(row.vl_pedido_atendido_bruto || row.VL_PEDIDO_ATENDIDO_BRUTO || row.valor_atendido || 0);
    const qtdUn = parseFloat(row.qtde_pedido_un || row.QTDE_PEDIDO_UN || row.qtde_pedido_dz || row.QTDE_PEDIDO || '0');
    const qtdAtendidaUn = parseFloat(row.qtde_pedido_atendido_un || row.QTDE_PEDIDO_ATENDIDO_UN || row.qtde_pedido_atendido_dz || row.QTDE_ATENDIDA || '0');
    const qtdCx = parseFloat(row.qtde_pedido_cx || row.QTDE_PEDIDO_CX || '0');
    const qtdAtendidaCx = parseFloat(row.qtde_pedido_atendido_cx || row.QTDE_PEDIDO_ATENDIDO_CX || '0');

    order.total_vl_bruto += isNaN(vlBruto) ? 0 : vlBruto;
    order.total_vl_atendido += isNaN(vlAtendido) ? 0 : vlAtendido;
    order.total_qtde_un += isNaN(qtdUn) ? 0 : qtdUn;
    order.total_qtde_atendida_un += isNaN(qtdAtendidaUn) ? 0 : qtdAtendidaUn;
    order.total_qtde_cx += isNaN(qtdCx) ? 0 : qtdCx;
    order.total_qtde_atendida_cx += isNaN(qtdAtendidaCx) ? 0 : qtdAtendidaCx;

    order.itens.push({
      sku: row.sku || row.SKU || row.SKU_PROD_BQ || row.sku_prod_bq || row.SKU_PROD_DIST || '-',
      produto: row.produto || row.PRODUTO || row.DESC_PROD_BQ || row.desc_prod_bq || getProdDesc(row),
      qtde_pedido_un: qtdUn,
      qtde_pedido_atendido_un: qtdAtendidaUn,
      qtde_pedido_cx: qtdCx,
      qtde_pedido_atendido_cx: qtdAtendidaCx,
      vl_pedido_bruto: isNaN(vlBruto) ? 0 : vlBruto,
      vl_pedido_atendido_bruto: isNaN(vlAtendido) ? 0 : vlAtendido
    });
  }

  const groupedOrders = Array.from(ordersMap.values());
  const totalOrders = groupedOrders.length;
  const totalSkus = currentGradeRowsData.length;

  const totalPages = Math.ceil(totalOrders / GRADE_PAGE_SIZE);
  if (currentGradePage > totalPages) currentGradePage = totalPages;
  if (currentGradePage < 1) currentGradePage = 1;

  const startIndex = (currentGradePage - 1) * GRADE_PAGE_SIZE;
  const endIndex = Math.min(startIndex + GRADE_PAGE_SIZE, totalOrders);
  const pageOrders = groupedOrders.slice(startIndex, endIndex);

  tbody.innerHTML = pageOrders.map(order => {
    const numPedido = order.numero_pedido;
    const safeOrderId = String(numPedido).replace(/[^a-zA-Z0-9_-]/g, '_');
    const dtEmissao = formatDate(order.data_emissao_pedido);
    const dtPrevEntrega = formatDate(order.data_previsao_entrega);
    const dtEntregaReal = formatDate(order.data_entrega);
    const statusPedido = order.desc_status_pedido;
    const isExpanded = expandedOrderIds.has(safeOrderId);

    // Linhas dos itens do pedido (drill down)
    const itemsRowsHtml = order.itens.map(item => `
      <tr>
        <td style="text-align: center; font-weight: 700; color: #2563EB; font-family: monospace;">${item.sku}</td>
        <td style="font-weight: 600; color: #0F172A;">${item.produto}</td>
        <td class="td-qty" style="text-align: center;">${fmtInt(item.qtde_pedido_un)}</td>
        <td class="td-qty" style="text-align: center; font-weight: 800; color: #0C2167;">${fmtInt(item.qtde_pedido_atendido_un)}</td>
        <td class="td-qty" style="text-align: center;">${fmtInt(item.qtde_pedido_cx)}</td>
        <td class="td-qty" style="text-align: center; font-weight: 800; color: #0C2167;">${fmtInt(item.qtde_pedido_atendido_cx)}</td>
        <td style="text-align: right; font-weight: 750; color: #0C2167; padding-right: 14px;">${fmtBRL(item.vl_pedido_bruto)}</td>
      </tr>
    `).join('');

    return `
      <tr class="grade-order-row ${isExpanded ? 'is-expanded' : ''}" id="order-row-${safeOrderId}" onclick="toggleOrderDrilldown('${safeOrderId}')" title="Clique para expandir/recolher os itens deste pedido">
        <td style="text-align: center; width: 46px;">
          <button class="btn-expand-order" id="btn-toggle-${safeOrderId}" onclick="event.stopPropagation(); toggleOrderDrilldown('${safeOrderId}')" title="${isExpanded ? 'Recolher itens' : 'Ver itens do pedido'}" aria-label="Expandir itens">
            ${isExpanded ? '−' : '+'}
          </button>
        </td>
        <td style="text-align: center; font-weight: 800; color: #0F172A;">${numPedido}</td>
        <td style="text-align: center; color: #475569; font-weight: 500;">${dtEmissao}</td>
        <td style="text-align: center; color: #475569; font-weight: 500;">${dtPrevEntrega}</td>
        <td style="text-align: center; color: #475569; font-weight: 500;">${dtEntregaReal}</td>
        <td style="text-align: center;"><span class="${getStatusBadgeClass(statusPedido)}">${statusPedido}</span></td>
        <td style="text-align: right; font-weight: 800; color: #0C2167; font-size: 13px; padding-right: 20px;">${fmtBRL(order.total_vl_bruto)}</td>
      </tr>
      <tr class="grade-drilldown-row" id="drilldown-${safeOrderId}" style="${isExpanded ? '' : 'display: none;'}">
        <td colspan="7">
          <div class="drilldown-container">
            <div class="drilldown-header-bar">
              <span class="drilldown-badge">
                <span class="drilldown-badge-count">${order.itens.length} SKUs</span>
                Itens do Pedido nº ${numPedido}
              </span>
              <span class="drilldown-total-txt">Total Itens: <strong style="color: #0C2167;">${fmtBRL(order.total_vl_bruto)}</strong></span>
            </div>
            <table class="drilldown-subtable">
              <thead>
                <tr>
                  <th style="text-align: center; width: 90px;">SKU</th>
                  <th>PRODUTO</th>
                  <th style="text-align: center; width: 110px;">QTD PEDIDO</th>
                  <th style="text-align: center; width: 110px;">QTD ATENDIDA</th>
                  <th style="text-align: center; width: 120px;">QTD PEDIDO (CX)</th>
                  <th style="text-align: center; width: 120px;">QTD ATENDIDA (CX)</th>
                  <th style="text-align: right; width: 140px; padding-right: 14px;">VALOR DO ITEM (R$)</th>
                </tr>
              </thead>
              <tbody>
                ${itemsRowsHtml}
              </tbody>
            </table>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  if (countEl) {
    countEl.textContent = `Mostrando ${startIndex + 1}-${endIndex} de ${totalOrders} pedidos (${totalSkus} itens)`;
  }

  if (paginationWrap) {
    let paginationHTML = `
      <button class="page-btn" ${currentGradePage === 1 ? 'disabled style="opacity:0.4;cursor:default;"' : `onclick="changeGradePage(${currentGradePage - 1})"`} aria-label="anterior">&#8249;</button>
    `;

    // Limita os botões visíveis para no máximo 3 páginas (ex: 1, 2, 3)
    let startPage = 1;
    if (currentGradePage > 2) {
      startPage = Math.min(currentGradePage - 1, totalPages - 2);
    }
    if (startPage < 1) startPage = 1;
    const endPage = Math.min(startPage + 2, totalPages);

    for (let p = startPage; p <= endPage; p++) {
      paginationHTML += `
        <button class="page-btn ${p === currentGradePage ? 'active' : ''}" onclick="changeGradePage(${p})">${p}</button>
      `;
    }

    paginationHTML += `
      <button class="page-btn" ${currentGradePage === totalPages ? 'disabled style="opacity:0.4;cursor:default;"' : `onclick="changeGradePage(${currentGradePage + 1})"`} aria-label="próximo">&#8250;</button>
    `;

    paginationWrap.innerHTML = paginationHTML;
  }
}

function changeGradePage(newPage) {
  updateGradeLogistica(null, null, newPage);
}

function initFilterListeners() {
  ['select-categoria', 'select-produto', 'select-sku', 'select-pedido', 'select-dia', 'select-semana', 'select-mes', 'select-ano'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', () => triggerDashboardRefresh(200));
    }
  });
}

let userSessionData = null;

function formatGreetingDistName(name) {
  if (!name) return 'Distribuidor';
  return String(name).trim();
}

// Todos os dados de usuário/distribuidor vêm exclusivamente da tabela
// cat_dnabb_dv.opebrapodis_sz.tbl_dim_distributor_user_mapping via /api/me.
// Nenhum fallback local é permitido (Falha Fechada).

async function loadUserGreeting() {
  const greetingNameEl = document.getElementById('greeting-name');

  try {
    const currentParams = window.location.search;
    const res = await fetch(`${API_BASE}/api/me${currentParams}`, { credentials: 'include' });
    if (res.status === 403 || res.status === 401) {
      const errData = await res.json().catch(() => ({}));
      if (greetingNameEl) {
        greetingNameEl.textContent = 'Acesso Restrito';
        greetingNameEl.style.color = '#F43F5E';
      }
      showUnlinkedUserNotice(errData.email || '');
      return false;
    }

    if (res.ok) {
      const data = await res.json();
      userSessionData = data;

      let primaryDistName = 'Distribuidor Bimbo QSR';
      if (data.admin === true || data.perfil === 'admin') {
        primaryDistName = data.desc_distribuidor || 'Administrador Bimbo QSR';
      } else if (data.distribuidores && data.distribuidores.length > 0 && data.distribuidores[0].nome) {
        primaryDistName = data.distribuidores[0].nome;
      } else if (data.desc_distribuidor) {
        primaryDistName = data.desc_distribuidor;
      }

      userSessionData.desc_distribuidor = primaryDistName;

      if (greetingNameEl) {
        greetingNameEl.textContent = formatGreetingDistName(primaryDistName);
        greetingNameEl.title = primaryDistName;
        greetingNameEl.style.color = '#38BDF8';
      }

      // Atualização do Indicador de Sincronização do Portal via Databricks Job
      const syncTimestampEl = document.getElementById('header-sync-timestamp');
      const syncPillEl = document.getElementById('header-sync-pill');
      if (syncTimestampEl && data.ultima_atualizacao) {
        syncTimestampEl.textContent = data.ultima_atualizacao;
        if (syncPillEl) {
          syncPillEl.title = `Última sincronização do banco de dados via Databricks Workflow (Horário de Brasília): ${data.ultima_atualizacao}`;
        }
      }

      // Controle de visibilidade estrita do Botão de Guia (Apenas Administradores Ativos)
      const isUserAdmin = Boolean(data.admin === true || data.perfil === 'admin');

      const btnAdminGuide = document.getElementById('btn-admin-guide');
      const btnAdminGuideDivider = document.getElementById('btn-admin-guide-divider');
      const tabBtnGuia = document.getElementById('tab-btn-guia');
      if (isUserAdmin) {
        if (btnAdminGuide) btnAdminGuide.style.display = 'inline-flex';
        if (btnAdminGuideDivider) btnAdminGuideDivider.style.display = 'block';
        if (tabBtnGuia) tabBtnGuia.style.display = 'inline-flex';
      } else {
        if (btnAdminGuide) btnAdminGuide.style.display = 'none';
        if (btnAdminGuideDivider) btnAdminGuideDivider.style.display = 'none';
        if (tabBtnGuia) tabBtnGuia.style.display = 'none';
      }
      return true;
    } else {
      if (greetingNameEl) {
        greetingNameEl.textContent = 'Acesso Restrito';
        greetingNameEl.style.color = '#F43F5E';
      }
      return false;
    }
  } catch (err) {
    console.error('Erro ao carregar perfil via /api/me:', err);
  }
  return true;
}

function showUnlinkedUserNotice(email) {
  const noticeHTML = `
    <div style="max-width: 750px; margin: 50px auto; padding: 40px; background: #FFFFFF; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); text-align: center; font-family: sans-serif; border: 1px solid #F1F5F9;">
      <div style="font-size: 56px; margin-bottom: 16px;">⚠️</div>
      <h2 style="color: #0F172A; font-size: 22px; font-weight: 700; margin-bottom: 12px;">Acesso Restrito</h2>
      <p style="color: #475569; font-size: 16px; line-height: 1.6; margin-bottom: 24px;">
        Usuário sem distribuidor vinculado. Contate o administrador.
      </p>
      ${email ? `<div style="font-size: 13px; color: #64748B; background: #F8FAFC; padding: 10px 16px; border-radius: 8px; display: inline-block; font-weight: 600;">E-mail SSO: ${email}</div>` : ''}
    </div>
  `;
  
  const targetEl = document.querySelector('.kpi-cards-grid') || document.querySelector('.dashboard-grid') || document.querySelector('.main-content');
  if (targetEl) {
    targetEl.innerHTML = noticeHTML;
  }
}

function animateGauges() {
  document.querySelectorAll('.gauge-arc').forEach(arc => {
    const pct = parseFloat(arc.getAttribute('data-pct')) || 0;
    const CIRC = 2 * Math.PI * 46;
    const clamped = Math.min(1, Math.max(0, pct));
    arc.style.strokeDasharray = `${CIRC}`;
    arc.style.strokeDashoffset = `${CIRC * (1 - clamped)}`;
  });
}

function initTabs() {
  const tabs = document.querySelectorAll('.tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const target = tab.getAttribute('data-tab');

      const portalLabel = document.getElementById('portalLabel');
      if (portalLabel && typeof TAB_LABELS !== 'undefined' && TAB_LABELS[target]) {
        portalLabel.textContent = TAB_LABELS[target];
      }

      if (typeof updateToggleVisibility === 'function') {
        updateToggleVisibility(target);
      }

      document.querySelectorAll('.tab-panel').forEach(p => {
        if (p.id === `tab-${target}`) {
          p.classList.add('active');
          p.style.display = 'flex';
        } else {
          p.classList.remove('active');
          p.style.display = 'none';
        }
      });

      if (target === 'kpis') {
        requestAnimationFrame(() => {
          if (typeof lastMonthlyIn !== 'undefined' && lastMonthlyOut) {
            buildBarChart(lastMonthlyIn, lastMonthlyOut, lastIsVolume, lastMonthlyMetaOut, lastMonthlyMetaIn);
          } else {
            buildBarChart();
          }
          animateGauges();
        });
      } else if (target === 'grade') {
        requestAnimationFrame(() => {
          if (currentGradeRowsData && currentGradeRowsData.length > 0) {
            updateGradeLogistica(currentGradeRowsData, null, currentGradePage);
          }
        });
      }
    });
  });
}

/* ── Init ── */
document.addEventListener('DOMContentLoaded', async function () {
  initAllCustomSelects();
  initFilterListeners();
  initToggle();
  initChartToggle();
  buildBarChart();
  buildForecastChart();
  animateGauges();
  initTabs();
  // Watchdog de seguranca: fecha o loader preventivamente apos 8s para nunca travar a tela
  const safetyWatchdog = setTimeout(() => {
    console.warn('[SafetyWatchdog] Fechando overlay de carregamento preventivamente apos 8s.');
    hideGlobalLoader();
  }, 8000);

  try {
    // Carregamento Concorrente Paralelo: elimina o waterfall sequencial, cortando o tempo de abertura pela metade!
    await Promise.all([
      loadUserGreeting(),
      loadFilters(),
      updateDashboardData()
    ]);
  } catch (err) {
    console.error('Erro na inicializacao da pagina:', err);
  } finally {
    clearTimeout(safetyWatchdog);
    hideGlobalLoader();
  }

  if (typeof ResizeObserver !== 'undefined') {
    let resizeTimer;
    const ro = new ResizeObserver(() => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        if (typeof buildBarChart === 'function' && lastMonthlyIn) {
          buildBarChart(lastMonthlyIn, lastMonthlyOut, lastIsVolume, lastMonthlyMetaOut, lastMonthlyMetaIn);
        }
        if (typeof buildPositivChart === 'function' && lastMonthlyPositiv) {
          buildPositivChart(lastMonthlyPositiv, lastMonthlyPositivPct, lastTotalBaseClientes, lastMonthlyPositivMeta, lastMonthlyTicketMedio);
        }
      }, 100);
    });
    const bc = document.getElementById('barChart');
    const pc = document.getElementById('positivChart');
    if (bc) ro.observe(bc);
    if (pc) ro.observe(pc);
  }
});
