
    let MONTHS = typeof getMonths !== 'undefined' ? getMonths() : ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    let cEvol, cDisc;
    let viewMode = 'valor';
    function setMode(m) { viewMode = m; document.getElementById('btnValor').classList.toggle('active', m === 'valor'); document.getElementById('btnVolume').classList.toggle('active', m === 'volume'); loadAll(); }
    function fmt(v, t = 'currency') { if (v == null || isNaN(v)) return '--'; const a = Math.abs(v); if (t === 'currency') { if (a >= 1e9) return 'R$ ' + (v / 1e9).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' Bi'; if (a >= 1e6) return 'R$ ' + (v / 1e6).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' Mi'; if (a >= 1e3) return 'R$ ' + (v / 1e3).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' mil'; return 'R$ ' + v.toLocaleString('pt-BR', { maximumFractionDigits: 0 }); } if (t === 'pct') return v.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + '%'; if (t === 'days') return Math.round(v) + ' dias'; return v.toLocaleString('pt-BR'); }


    // MultiSelect and filters provided by filters-shared.js
    _cascadeEndpoint = '/api/filters/cascading';
    // i18n: override fmt with localized version
    if (typeof fmtI18n !== 'undefined') fmt = fmtI18n;
    document.addEventListener('langChange', function () { MONTHS = typeof getMonths !== 'undefined' ? getMonths() : MONTHS; if (typeof loadAll === 'function') loadAll(); });
    function _tc() { return document.documentElement.getAttribute('data-theme') === 'light' ? '#374151' : 'rgba(168,204,223,.7)'; }
    function _tcs() { return document.documentElement.getAttribute('data-theme') === 'light' ? '#64748b' : 'rgba(168,204,223,.6)'; }

    async function loadKPIs() {
      const d = (await fetch(`/api/commercial/kpis?${getFilters()}`).then(r => r.json()))[0] || {};
      const term = d.avg_payment_term || 0;
      const termEl = document.getElementById('vTerm');
      termEl.textContent = Math.round(term) + ' ' + t('dias');
      termEl.style.color = term >= 60 ? '#22c55e' : '#f87171';
      const diff = Math.round(term - 60);
      document.getElementById('dTerm').innerHTML = `<span style="color:${diff >= 0 ? '#22c55e' : '#ef4444'}">${diff >= 0 ? '↑ +' : '↓ '}${Math.abs(diff)} ${t('dias vs meta')}</span>`;
      const pctBelow = d.total_spend ? ((d.spend_below_60 / d.total_spend) * 100) : 0;
      document.getElementById('vBelow60').textContent = pctBelow.toFixed(0) + '%';
      document.getElementById('vBelow60Val').textContent = fmt(d.spend_below_60);
    }

    async function loadEvolution() {
      // Ignore month filter — always show full year evolution
      let data = [];
      try {
        const url = `/api/commercial/payment-evolution?${getFiltersExcluding('mes', 'dia')}`;
        const resp = await fetch(url);
        if (!resp.ok) { console.error('payment-evolution HTTP', resp.status); data = []; }
        else { data = await resp.json(); }
      } catch (e) { console.error('payment-evolution fetch error', e); data = []; }
      if (!Array.isArray(data)) data = [];
      const currentMonth = new Date().getMonth();
      const filtered = data.filter(d => d && d.mes && parseInt(d.mes) - 1 <= currentMonth);
      const labels = filtered.map(d => MONTHS[parseInt(d.mes) - 1] || d.mes);
      const monthly = filtered.map(d => d.avg_term || 0);
      // Compute accumulated weighted average (matches KPI)
      let accPgto = 0, accVlr = 0;
      const accumulated = filtered.map(d => { accPgto += (d.sum_pgto || 0); accVlr += (d.sum_vlr || 0); return accVlr ? accPgto / accVlr : 0; });
      const overallAvg = accumulated.length ? accumulated[accumulated.length - 1] : 0;
      if (cEvol) cEvol.destroy();
      if (!filtered.length) { console.warn('loadEvolution: 0 rows returned from API. data=', data); document.getElementById('chartEvol').parentElement.setAttribute('data-empty', 'Sem dados para este filtro'); return; }
      document.getElementById('chartEvol').parentElement.removeAttribute('data-empty');
      // Point only on last month for accumulated
      const evolPtRadius = accumulated.map((_, i) => i === accumulated.length - 1 ? 5 : 0);
      cEvol = new Chart(document.getElementById('chartEvol'), {
        type: 'line',
        data: {
          labels, datasets: [
            { label: t('Prazo m\u00e9dio acumulado (dias)'), data: accumulated, borderColor: '#1e40af', borderWidth: 2.5, fill: false, tension: .3, pointRadius: evolPtRadius, pointBackgroundColor: '#1e40af', pointHoverRadius: 6, order: 1 },
            { label: t('Prazo mensal (dias)'), data: monthly, borderColor: 'rgba(148,163,184,.5)', borderWidth: 1.5, borderDash: [4, 2], fill: false, tension: .3, pointRadius: 3, pointBackgroundColor: 'rgba(148,163,184,.6)', pointHoverRadius: 5, order: 2 },
          ]
        },
        plugins: [{
          id: 'evolLabels',
          afterDatasetsDraw(chart) {
            const ctx = chart.ctx;
            ctx.save();
            // Label on last point of accumulated line
            const dsAcc = chart.data.datasets[0];
            if (dsAcc && dsAcc.data.length) {
              const metaAcc = chart.getDatasetMeta(0);
              const lastIdx = dsAcc.data.length - 1;
              const pt = metaAcc.data[lastIdx];
              if (pt) {
                const rounded = Math.round(dsAcc.data[lastIdx]);
                const labelColor = rounded >= 60 ? '#22c55e' : rounded >= 50 ? '#f59e0b' : '#f87171';
                ctx.font = 'bold 12px sans-serif';
                ctx.fillStyle = labelColor;
                ctx.textAlign = 'center';
                ctx.fillText(rounded + ' ' + t('dias'), pt.x, pt.y - 14);
              }
            }
            // Labels on ALL points of monthly line (gray)
            const dsMonth = chart.data.datasets[1];
            if (dsMonth && dsMonth.data.length) {
              const metaMonth = chart.getDatasetMeta(1);
              ctx.font = '600 9px sans-serif';
              ctx.fillStyle = 'rgba(148,163,184,.8)';
              ctx.textAlign = 'center';
              metaMonth.data.forEach((pt, i) => {
                if (pt && dsMonth.data[i] != null) {
                  ctx.fillText(Math.round(dsMonth.data[i]), pt.x, pt.y - 10);
                }
              });
            }
            ctx.restore();
          }
        }],
        options: (() => { const allVals = [...accumulated, ...monthly].filter(v => v != null && v > 0); const dMin = Math.min(...allVals); const dMax = Math.max(...allVals); const yMin = Math.max(0, Math.floor((dMin - 10) / 5) * 5); const yMax = Math.ceil((dMax + 5) / 5) * 5; return { responsive: true, maintainAspectRatio: false, layout: { padding: { right: 30, top: 10 } }, interaction: { mode: 'index', intersect: false }, plugins: { tooltip: { enabled: true, callbacks: { label: function (ctx) { return ctx.dataset.label + ': ' + Math.round(ctx.parsed.y) + ' dias'; } } }, legend: { display: true, position: 'top', align: 'start', labels: { color: _tc(), boxWidth: 10, padding: 10, font: { size: 9 } } } }, scales: { x: { grid: { display: false }, border: { display: false }, ticks: { color: _tc(), font: { size: 10, weight: '600' } } }, y: { grid: { display: false }, border: { display: false }, min: yMin, max: yMax, ticks: { color: _tcs(), font: { size: 9 }, maxTicksLimit: 5 } } } }; })()
      });
    }

    async function loadDistribution() {
      const rawData = await fetch(`/api/commercial/payment-distribution?${getFilters()}`).then(r => r.json());
      // Merge 31-45 and 46-59 buckets into 31-59
      const merged = [];
      let merge31 = { bucket: '31 a 59 dias', net_spend: 0 };
      rawData.forEach(d => {
        if ((d.bucket || '').includes('31') || (d.bucket || '').includes('45') || (d.bucket || '').includes('46') || (d.bucket || '').includes('59')) {
          if (!(d.bucket || '').includes('Acima')) merge31.net_spend += (d.net_spend || 0);
          else merged.push(d);
        } else { merged.push(d); }
      });
      // Insert merged bucket after '16 a 30'
      const idx30 = merged.findIndex(d => (d.bucket || '').includes('30'));
      merged.splice(idx30 + 1, 0, merge31);
      const data = merged;
      const total = data.reduce((a, d) => a + (d.net_spend || 0), 0);
      const max = Math.max(...data.map(d => d.net_spend || 0));
      const above60 = data.filter(d => (d.bucket || '').toLowerCase().includes('60') || (d.bucket || '').toLowerCase().includes('acima')).reduce((a, d) => a + (d.net_spend || 0), 0);
      const pct60 = total ? ((above60 / total) * 100).toFixed(0) : 0;
      document.getElementById('ttlDist').textContent = tt('{pct}% do spend est\u00e1 em prazos superiores a 60 dias', { pct: pct60 });
      document.getElementById('distList').innerHTML = data.map(d => {
        const pct = total ? ((d.net_spend / total) * 100).toFixed(0) : 0;
        const w = max ? ((d.net_spend / max) * 100) : 0;
        // Remove leading numbers like "00. ", "01. ", etc. (only XX. pattern)
        const label = (d.bucket || '').replace(/^\d+\.\s*/, '');
        // Pre-attentive: highlight buckets >= 60 dias (blue), À vista (amber), mute the rest
        const isHighlight = (d.bucket || '').toLowerCase().includes('60') || (d.bucket || '').toLowerCase().includes('acima');
        const isVista = (d.bucket || '').toLowerCase().includes('vista');
        const barBg = isVista ? 'background:linear-gradient(90deg,#d97706,#f59e0b)!important' : isHighlight ? 'background:linear-gradient(90deg,#1d4ed8,#3b82f6)!important' : 'background:#64748b!important';
        const lblStyle = (isHighlight || isVista) ? '' : 'color:#64748b';
        const valStyle = (isHighlight || isVista) ? '' : 'color:#64748b';
        return `<div class="hbar-row"><span class="hbar-label" style="${lblStyle}">${t(label)}</span><div class="hbar-track"><div class="hbar-fill" style="width:${w}%;${barBg}"></div></div><span class="hbar-val" style="${valStyle}">${fmt(d.net_spend)} · ${pct}%</span></div>`;
      }).join('');
    }

    async function loadDiscountChart() {
      const data = await fetch(`/api/commercial/payment-evolution?${getFilters()}`).then(r => r.json());
      const labels = data.map(d => MONTHS[parseInt(d.mes) - 1] || d.mes);
      const monthly = data.map(d => d.discount_monthly || 0);
      let acc = 0; const cumulative = monthly.map(v => { acc += v; return acc; });
      if (cDisc) cDisc.destroy();
      // Bar colors: only the MAX positive and MIN negative get full contrast
      const maxVal = Math.max(...monthly);
      const minVal = Math.min(...monthly);
      const maxIdx = monthly.indexOf(maxVal);
      const minIdx = monthly.indexOf(minVal);
      const barColors = monthly.map((v, i) => {
        if (i === maxIdx && maxVal > 0) return 'rgba(22,163,74,1)';
        if (i === minIdx && minVal < 0) return 'rgba(220,38,38,1)';
        return v >= 0 ? 'rgba(22,163,74,.4)' : 'rgba(220,38,38,.4)';
      });
      // Point radius: only last point visible (smaller)
      const ptRadius = cumulative.map((_, i) => i === cumulative.length - 1 ? 4 : 0);
      cDisc = new Chart(document.getElementById('chartDiscount'), {
        type: 'bar',
        data: {
          labels, datasets: [
            { type: 'bar', label: t('Mensal'), data: monthly, backgroundColor: barColors, borderRadius: 3, barPercentage: .6, yAxisID: 'y' },
            { type: 'line', label: t('Acumulado'), data: cumulative, borderColor: 'rgba(148,163,184,.55)', borderWidth: 1.5, pointRadius: ptRadius, pointBackgroundColor: 'rgba(148,163,184,.7)', pointHoverRadius: 4, tension: .3, fill: false, yAxisID: 'y2' }
          ]
        },
        plugins: [{
          id: 'lastPointLabel',
          afterDatasetsDraw(chart) {
            const ds = chart.data.datasets[1];
            if (!ds || !ds.data.length) return;
            const meta = chart.getDatasetMeta(1);
            const lastIdx = ds.data.length - 1;
            const pt = meta.data[lastIdx];
            if (!pt) return;
            const ctx = chart.ctx;
            const val = ds.data[lastIdx];
            ctx.save();
            ctx.font = 'bold 11px sans-serif';
            ctx.fillStyle = 'rgba(148,163,184,.8)';
            ctx.textAlign = 'center';
            ctx.fillText(fmt(val), pt.x, pt.y - 12);
            ctx.restore();
          }
        }],
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, border: { display: false }, ticks: { color: _tc(), font: { size: 10, weight: '600' } } }, y: { grid: { display: false }, border: { display: false }, ticks: { color: _tcs(), font: { size: 9 }, maxTicksLimit: 5, callback: v => fmt(v) } }, y2: { position: 'right', grid: { display: false }, border: { display: false }, ticks: { color: _tcs(), font: { size: 9 }, maxTicksLimit: 5, callback: v => fmt(v) } } } }
      });
    }

    async function loadBelow60() {
      const data = await fetch(`/api/commercial/suppliers-below-60?${getFilters()}`).then(r => r.json());
      const max = Math.max(...data.map(d => d.net_spend || 0));
      const total = data.reduce((s, d) => s + (d.net_spend || 0), 0);
      // Knee detection: find natural cutoff for pre-attentive highlight
      let highlightN = 3;
      if (data.length >= 4) {
        for (let i = 1; i < Math.min(data.length, 6); i++) {
          const curr = data[i].net_spend || 0;
          const prev = data[i - 1].net_spend || 0;
          if (curr < prev * 0.4) { highlightN = i; break; }
        }
      }
      highlightN = Math.max(1, Math.min(highlightN, 5));
      // Dynamic title: top N highlighted suppliers % of total
      const topNSpend = data.slice(0, highlightN).reduce((s, d) => s + (d.net_spend || 0), 0);
      const topNPct = total ? ((topNSpend / total) * 100).toFixed(1) : 0;
      document.getElementById('ttlBelow60').textContent = tt('Os {n} principais fornecedores representam {pct}% do spend pago em menos de 60 dias', { n: highlightN, pct: topNPct });
      document.getElementById('barBelow60').innerHTML = data.slice(0, 10).map((d, i) => {
        const w = max ? ((d.net_spend / max) * 100) : 0;
        const pct = total ? ((d.net_spend / total) * 100).toFixed(1) : 0;
        const muted = i >= highlightN;
        const barBg = muted ? 'background:#64748b!important' : 'background:linear-gradient(90deg,#1d4ed8,#3b82f6)!important';
        const lblStyle = muted ? 'color:#64748b' : '';
        const valStyle = muted ? 'color:#64748b' : '';
        return `<div class="hbar-row"><span class="hbar-label" style="${lblStyle}">${(d.fornecedor || '').substring(0, 24)}</span><div class="hbar-track"><div class="hbar-fill" style="width:${w}%;${barBg}"></div></div><span class="hbar-val" style="${valStyle}">${fmt(d.net_spend)} \u00b7 ${pct}%</span></div>`;
      }).join('');

    }

    let _renegoData = [];
    let _renPage = 1;
    const _REN_PAGE_SIZE = 50;
    let _renSortCol = 'prazo';
    let _renSortDir = 'asc';
    let _renHeaderFilters = JSON.parse(localStorage.getItem('tbl_filter_com_ren') || '{}');

    const _RENEGO_COLS = [
      { key: 'numero_oc', label: 'N° Pedido' },
      { key: 'fornecedor', label: 'Fornecedor' },
      { key: 'net_spend', label: 'Spend líquido' },
      { key: 'prazo', label: 'Prazo (dias)' }
    ];

    function getFilteredRenegoData() {
      return TableColumnFilter.filterData(_renegoData, _renHeaderFilters, (item, k) => {
        if (k === 'net_spend') return item.net_spend;
        if (k === 'prazo') return item.prazo;
        return item[k];
      });
    }

    function _buildRenegoHead() {
      const el = document.getElementById('renegoHead');
      if (!el) return;
      el.innerHTML = '<tr>' + _RENEGO_COLS.map(c => {
        const isFiltered = !!(_renHeaderFilters[c.key] && _renHeaderFilters[c.key].val);
        const thClass = isFiltered ? 'th-filtered' : '';
        const arrow = c.key === _renSortCol ? (_renSortDir === 'desc' ? '\u25BC' : '\u25B2') : '';
        const filterBtn = TableColumnFilter.renderBtn(c.key, c.label, isFiltered, `openRenegoFilter(event, '${c.key}', '${c.label.replace(/'/g, "\\'")}')`);
        return `<th class="${thClass}" style="user-select:none;white-space:nowrap;padding:.4rem .6rem;">
          <div style="display:flex;align-items:center;justify-content:space-between;width:100%;gap:4px;">
            <span style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;flex:1;overflow:hidden;text-overflow:ellipsis;" onclick="sortRenego('${c.key}')" title="Clique para ordenar (crescente/decrescente)">
              <span>${t(c.label)}</span>
              <span id="srt_${c.key}">${arrow}</span>
            </span>
            ${filterBtn}
          </div>
        </th>`;
      }).join('') + '</tr>';
    }

    function openRenegoFilter(e, colKey, colLabel) {
      TableColumnFilter.open(e, colKey, colLabel, _renHeaderFilters[colKey], (col, cfg) => {
        if (cfg && cfg.val) { _renHeaderFilters[col] = cfg; }
        else { delete _renHeaderFilters[col]; }
        try { localStorage.setItem('tbl_filter_com_ren', JSON.stringify(_renHeaderFilters)); } catch(e){}
        _renPage = 1;
        _buildRenegoHead();
        renderRenegoPage();
      });
    }
    window.openRenegoFilter = openRenegoFilter;

    function sortRenego(col) {
      if (_renSortCol === col) _renSortDir = _renSortDir === 'desc' ? 'asc' : 'desc';
      else { _renSortCol = col; _renSortDir = col === 'net_spend' ? 'desc' : 'asc'; }
      _renegoData.sort((a, b) => {
        let va = a[col], vb = b[col];
        if (typeof va === 'string') return _renSortDir === 'asc' ? (va || '').localeCompare(vb || '') : (vb || '').localeCompare(va || '');
        return _renSortDir === 'asc' ? (va || 0) - (vb || 0) : (vb || 0) - (va || 0);
      });
      _renPage = 1;
      _buildRenegoHead();
      renderRenegoPage();
    }

    function renderRenegoPage() {
      const data = getFilteredRenegoData();
      const totalPages = Math.max(1, Math.ceil(data.length / _REN_PAGE_SIZE));
      if (_renPage > totalPages) _renPage = totalPages;
      const start = (_renPage - 1) * _REN_PAGE_SIZE;
      const slice = data.slice(start, start + _REN_PAGE_SIZE);
      document.getElementById('tblRenego').innerHTML = slice.map(d => `<tr><td>${d.numero_oc || '--'}</td><td>${d.fornecedor || '--'}</td><td>${fmt(d.net_spend)}</td><td>${d.prazo != null ? Math.round(d.prazo) : '--'}</td></tr>`).join('');
      document.getElementById('renPageInfo').textContent = tt('Página {page} de {pages}', { page: _renPage, pages: totalPages });
      document.getElementById('renPrev').disabled = _renPage <= 1;
      document.getElementById('renNext').disabled = _renPage >= totalPages;
    }
    function renegoPage(dir) { _renPage += dir; renderRenegoPage(); }

    async function loadRenegoTable() {
      _renegoData = await fetch(`/api/commercial/renegotiation-table?${getFilters()}`).then(r => r.json());
      // Default sort: maior spend, depois menor prazo
      _renegoData.sort((a, b) => (b.net_spend || 0) - (a.net_spend || 0) || (a.prazo || 0) - (b.prazo || 0));
      _renSortCol = 'net_spend'; _renSortDir = 'desc';
      _renPage = 1;
      _buildRenegoHead();
      renderRenegoPage();
    }
    function exportRenego() {
      const data = getFilteredRenegoData();
      if (!data.length) return;
      const rows = data.map(d => ({
        [t('N° Pedido')]: d.numero_oc || '',
        [t('Fornecedor')]: d.fornecedor || '',
        [t('Spend líquido') + ' (R$)']: d.net_spend || 0,
        [t('Prazo (dias)')]: d.prazo != null ? Math.round(d.prazo) : ''
      }));
      const ws = XLSX.utils.json_to_sheet(rows);
      ws['!cols'] = [{ wch: 18 }, { wch: 35 }, { wch: 18 }, { wch: 12 }];
      ws['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: rows.length, c: 3 } }) };
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, t('Renegociação'));
      XLSX.writeFile(wb, 'renegociacao_pedidos.xlsx');
    }

    function toggleAdvFilters() { const b = document.getElementById('advFiltersBar'), btn = document.getElementById('btnAdvFilters'); if (b.style.display === 'none') { b.style.display = 'flex'; btn.style.borderColor = 'rgba(59,130,246,.45)'; btn.style.color = '#60a5fa'; } else { b.style.display = 'none'; btn.style.borderColor = 'rgba(100,116,139,.35)'; btn.style.color = '#94a3b8'; } }
    function loadAll() { return Promise.allSettled([loadKPIs(), loadEvolution(), loadDistribution(), loadDiscountChart(), loadBelow60(), loadRenegoTable()]); }
    function toggleTheme() { const h = document.documentElement; const n = h.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'; h.setAttribute('data-theme', n); localStorage.setItem('theme', n); loadAll(); }
    const s = localStorage.getItem('theme'); if (s) document.documentElement.setAttribute('data-theme', s);

    async function initFilters() {
      const data = await (window.fetchCachedFilterData ? window.fetchCachedFilterData('/api/filters/comercial') : fetch('/api/filters/comercial').then(r => r.json()));
      filters.fEmpresa = new MultiSelect(document.getElementById('fEmpresa'), data.empresas || ['BB', 'BQ']);
      filters.fEmpresa.selected = new Set(['BB', 'BQ']); filters.fEmpresa.renderOptions(); filters.fEmpresa.updateLabel();
      filters.fAno = new MultiSelect(document.getElementById('fAno'), data.anos || []);
      const cy = String(new Date().getFullYear()); if (filters.fAno.options.includes(cy)) { filters.fAno.selected = new Set([cy]); filters.fAno.renderOptions(); filters.fAno.updateLabel(); }
      filters.fMes = new MultiSelect(document.getElementById('fMes'), (data.meses || []).map(m => String(m)));
      filters.fGrupo = new MultiSelect(document.getElementById('fGrupo'), data.grupos || []);
      filters.fFornecedor = new MultiSelect(document.getElementById('fFornecedor'), data.fornecedores || []);
      filters.fTipoNF = new MultiSelect(document.getElementById('fTipoNF'), ['com_oc', 'sem_oc']);
      filters.fTipoNF.selected = new Set(['com_oc', 'sem_oc']); filters.fTipoNF.renderOptions(); filters.fTipoNF.updateLabel();
      const cm = String(new Date().getMonth() + 1); if (filters.fMes.options.includes(cm)) { filters.fMes.selected = new Set([cm]); filters.fMes.renderOptions(); filters.fMes.updateLabel(); }
      if (document.getElementById('fFornNegociavel')) {
        filters.fFornNegociavel = new MultiSelect(document.getElementById('fFornNegociavel'), ['NEGOCIAVEL', 'NÃO NEGOCIAVEL']);
      }
      if (typeof FilterStateStore !== 'undefined') FilterStateStore.restore();
      _filtersReady = true;
      aplicarFiltros(loadAll);
      // Advanced filters (non-blocking, cached)
      (window.fetchCachedFilterData ? window.fetchCachedFilterData('/api/filters/advanced') : fetch('/api/filters/advanced').then(r => r.json())).then(advData => {
        if (document.getElementById('fMacroCategoria')) filters.fMacroCategoria = new MultiSelect(document.getElementById('fMacroCategoria'), advData.macro_categoria || []);
        if (document.getElementById('fDia')) filters.fDia = new MultiSelect(document.getElementById('fDia'), (advData.dias || []).map(d => String(d)));
        if (document.getElementById('fNumeroRI')) filters.fNumeroRI = new MultiSelect(document.getElementById('fNumeroRI'), advData.numero_ri || []);
        if (document.getElementById('fNotaFiscal')) filters.fNotaFiscal = new MultiSelect(document.getElementById('fNotaFiscal'), advData.nota_fiscal || []);
        if (document.getElementById('fNumeroOC')) filters.fNumeroOC = new MultiSelect(document.getElementById('fNumeroOC'), advData.numero_oc || []);
        if (document.getElementById('fDsItem')) filters.fDsItem = new MultiSelect(document.getElementById('fDsItem'), advData.ds_item || []);
        if (document.getElementById('fCodigoItem')) filters.fCodigoItem = new MultiSelect(document.getElementById('fCodigoItem'), advData.codigo_item || []);
        if (document.getElementById('fDescItem')) filters.fDescItem = new MultiSelect(document.getElementById('fDescItem'), advData.descricao_item || []);
        if (document.getElementById('fCentralizado')) filters.fCentralizado = new MultiSelect(document.getElementById('fCentralizado'), advData.centralizado || []);
        if (document.getElementById('fUnidade')) filters.fUnidade = new MultiSelect(document.getElementById('fUnidade'), advData.unidade || []);
        if (document.getElementById('fStatusPgto')) filters.fStatusPgto = new MultiSelect(document.getElementById('fStatusPgto'), advData.status_pagamento || []);
        if (document.getElementById('fTipoNFAdv')) filters.fTipoNFAdv = new MultiSelect(document.getElementById('fTipoNFAdv'), advData.tipo_nf || []);
        if (document.getElementById('fTipoLinha')) filters.fTipoLinha = new MultiSelect(document.getElementById('fTipoLinha'), advData.tipo_linha || []);
        if (document.getElementById('fFornEspecial')) filters.fFornEspecial = new MultiSelect(document.getElementById('fFornEspecial'), ['ESPECIAL', 'NÃO ESPECIAL']);
        if (document.getElementById('fFornNegociavel') && !filters.fFornNegociavel) filters.fFornNegociavel = new MultiSelect(document.getElementById('fFornNegociavel'), ['NEGOCIAVEL', 'NÃO NEGOCIAVEL']);
        if (typeof FilterStateStore !== 'undefined') FilterStateStore.restore();
      }).catch(() => { });
    }
    window.addEventListener('themeChanged', () => {
      if (typeof loadEvolution === 'function') loadEvolution();
      if (typeof loadDiscountChart === 'function') loadDiscountChart();
    });
    initFilters();
  