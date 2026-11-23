
    let MONTHS = typeof getMonths !== 'undefined' ? getMonths() : ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    let currentExcType = 'pos_fatura';
    function fmt(v, t = 'currency') { if (v == null || isNaN(v)) return '--'; const a = Math.abs(v); if (t === 'currency') { if (a >= 1e9) return 'R$ ' + (v / 1e9).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' Bi'; if (a >= 1e6) return 'R$ ' + (v / 1e6).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' Mi'; if (a >= 1e3) return 'R$ ' + (v / 1e3).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' mil'; return 'R$ ' + v.toLocaleString('pt-BR', { maximumFractionDigits: 0 }); } return v.toLocaleString('pt-BR'); }

    // MultiSelect and filters provided by filters-shared.js
    _cascadeEndpoint = '/api/filters/cascading';
    // i18n: override fmt with localized version
    if (typeof fmtI18n !== 'undefined') fmt = fmtI18n;
    document.addEventListener('langChange', function () { MONTHS = typeof getMonths !== 'undefined' ? getMonths() : MONTHS; if (typeof loadAll === 'function') loadAll(); });

    async function loadKPIs() {
      const d = await fetch(`/api/governance/kpis?${getFilters()}`).then(r => r.json());
      const totalNfs = (d.total_nfs_pgto != null && d.total_nfs_pgto > 0) ? d.total_nfs_pgto : (d.total_nf_com_oc_pgto || d.total_notas || 1);
      const posPct = totalNfs ? ((d.pos_fatura_qty || 0) / totalNfs * 100).toFixed(1) : 0;
      document.getElementById('vPosFatura').textContent = (d.pos_fatura_qty || 0).toLocaleString(typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR');
      document.getElementById('dPosFatura').innerHTML = `${fmt(d.pos_fatura_val)} &nbsp;·&nbsp; <span style="color:rgba(248,113,113,.85)">${posPct}%</span> ${t('(qtd) do total de NFs')}`;
      document.getElementById('vUrgente').textContent = (d.urgente_qty || 0).toLocaleString(typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR');
      document.getElementById('dUrgente').textContent = fmt(d.urgente_val);
      // Âncora DATA_PAGAMENTO: numerador e denominador consideram só NFs com data de pagamento
      const _semOcDen = d.total_spend_pgto != null ? d.total_spend_pgto : d.total_spend;
      const semOcPct = _semOcDen ? ((d.sem_oc_val || 0) / (_semOcDen) * 100).toFixed(1) : 0;
      document.getElementById('vSemOC').textContent = (d.sem_oc_qty || 0).toLocaleString(typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR');
      document.getElementById('dSemOC').innerHTML = `${fmt(d.sem_oc_val)} &nbsp;·&nbsp; <span style="color:rgba(96,165,250,.85)">${semOcPct}%</span> ${t('(R$) do Spend Líquido Total')}`;
      const totalDec = d.total_oc_decentral != null && d.total_oc_decentral > 0 ? d.total_oc_decentral : (d.total_oc_faturadas_pgto || d.total_oc_faturadas);
      const decPct = totalDec ? ((d.decentral_qty || 0) / totalDec * 100).toFixed(1) : 0;
      document.getElementById('vDecentral').textContent = (d.decentral_qty || 0).toLocaleString(typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR');
      document.getElementById('dDecentral').innerHTML = `${fmt(d.decentral_val)} &nbsp;·&nbsp; <span style="color:rgba(167,139,250,.85)">${decPct}%</span> ${t('(qtd) das OCs descentralizadas')}`;
      const sucGroups = d.sucessivas_groups_qty != null ? d.sucessivas_groups_qty : (d.sucessivas_qty || 0);
      const sucOcs = d.sucessivas_qty || 0;
      const totalValOcs = d.total_valor_ocs_periodo || 0;
      const sucValPct = totalValOcs > 0 ? ((d.sucessivas_val || 0) / totalValOcs * 100).toFixed(1) : 0;
      document.getElementById('vSucessivas').textContent = sucGroups.toLocaleString(typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR');
      document.getElementById('vSucessivas').title = `${sucGroups} ${t('grupos/casos de OCs sucessivas')} (${sucOcs} ${t('OCs envolvidas')})`;
      document.getElementById('dSucessivas').innerHTML = `${fmt(d.sucessivas_val)} &nbsp;·&nbsp; <span style="color:rgba(251,146,60,.85)">${sucValPct}%</span> ${t('(R$) das OCs do Período')} &nbsp;·&nbsp; <span style="color:var(--fr-txt-soft);font-size:.62rem">${sucOcs} ${t('OCs')}</span>`;
      const totalBla = d.total_oc_faturadas_pgto || d.total_oc_faturadas;
      const blaPct = totalBla ? ((d.blanket_old_qty || 0) / totalBla * 100).toFixed(1) : 0;
      document.getElementById('vBlanket').textContent = (d.blanket_old_qty || 0).toLocaleString(typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR');
      document.getElementById('dBlanket').innerHTML = `${fmt(d.blanket_old_val)} &nbsp;·&nbsp; <span style="color:rgba(52,211,153,.85)">${blaPct}%</span> ${t('(qtd) das OCs faturadas')}`;
      const totalOcAbertas = d.total_oc_abertas || 0;
      const oc90Pct = totalOcAbertas ? ((d.oc90_qty || 0) / totalOcAbertas * 100).toFixed(1) : 0;
      document.getElementById('vOc90').textContent = (d.oc90_qty || 0).toLocaleString(typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR');
      document.getElementById('dOc90').innerHTML = `${fmt(d.oc90_val)} &nbsp;·&nbsp; <span style="color:rgba(34,211,238,.85)">${oc90Pct}%</span> ${t('(qtd) das OCs abertas')}`;
    }

    async function loadImpact() {
      const rawData = await fetch(`/api/governance/deviation-impact?${getFilters()}`).then(r => r.json());
      const data = rawData.filter(d => !(d.label || '').toLowerCase().includes('emergencial'));
      data.sort((a, b) => (b.qty || 0) - (a.qty || 0) || (b.value || 0) - (a.value || 0));
      const total = data.reduce((a, d) => a + (d.value || 0), 0);
      const maxQty = Math.max(...data.map(d => d.qty || 0));
      document.getElementById('ttlImpact').textContent = t('Qual Desvio Tem Maior Impacto?');
      document.getElementById('impactList').innerHTML = data.map(d => {
        const qty = d.qty || 0;
        const rawW = maxQty && qty > 0 ? (qty / maxQty * 100) : 0;
        const w = qty > 0 ? Math.max(rawW, 1.2) : 0;
        const isOut = w < 14;
        const qtyStr = qty.toLocaleString(typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR');
        const posStyle = isOut ? `left:calc(${w}% + 8px);` : 'left:10px;';
        return `<div class="impact-row"><span class="impact-lbl">${t(d.label || '')}</span><div class="impact-track"><div class="impact-fill" style="width:${w}%"></div><span class="impact-qty ${isOut ? 'out-bar' : 'in-bar'}" style="${posStyle}">${qtyStr}</span></div><span class="impact-val">${fmt(d.value)}</span></div>`;
      }).join('');
    }

    let _buyerData = [];
    let _buyerPage = 1;
    let _buyerSortCol = 'valor';
    let _buyerSortDir = 'desc';
    let _buyerHeaderFilters = JSON.parse(localStorage.getItem('tbl_filter_gov_buyer') || '{}');
    const _BUYER_COLS = [
      { key: 'buyer', label: 'Criador OC' },
      { key: 'depart', label: 'Depart.' },
      { key: 'tipo_excecao', label: 'Tipo' },
      { key: 'qty', label: 'Qtd' },
      { key: 'valor', label: 'Valor' },
      { key: 'pct_transacoes', label: '% Exceções' }
    ];

    const _BUYER_PAGE_SIZE = 8;

    function getFilteredBuyerData() {
      return TableColumnFilter.filterData(_buyerData, _buyerHeaderFilters, (item, k) => {
        if (k === 'depart') return _cleanDept(item.depart || item.area);
        if (k === 'qty') return item.qty;
        if (k === 'valor') return item.valor;
        if (k === 'pct_transacoes') return item.pct_transacoes;
        return item[k];
      });
    }

    function _buildBuyerHead() {
      const el = document.getElementById('buyerHead');
      if (!el) return;
      el.innerHTML = '<tr>' + _BUYER_COLS.map(c => {
        const isFiltered = !!(_buyerHeaderFilters[c.key] && _buyerHeaderFilters[c.key].val);
        const thClass = isFiltered ? 'th-filtered' : '';
        const arrow = c.key === _buyerSortCol ? (_buyerSortDir === 'desc' ? '\u25BC' : '\u25B2') : '';
        const filterBtn = TableColumnFilter.renderBtn(c.key, c.label, isFiltered, `openBuyerFilter(event, '${c.key}', '${c.label.replace(/'/g, "\\'")}')`);
        return `<th class="${thClass}" style="user-select:none;white-space:nowrap;padding:.4rem .6rem;">
          <div style="display:flex;align-items:center;justify-content:space-between;width:100%;gap:4px;">
            <span style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;flex:1;overflow:hidden;text-overflow:ellipsis;" onclick="sortBuyer('${c.key}')" title="Clique para ordenar">
              <span>${t(c.label)}</span>
              <span id="srtB_${c.key}">${arrow}</span>
            </span>
            ${filterBtn}
          </div>
        </th>`;
      }).join('') + '</tr>';
    }

    function openBuyerFilter(e, colKey, colLabel) {
      TableColumnFilter.open(e, colKey, colLabel, _buyerHeaderFilters[colKey], (col, cfg) => {
        if (cfg && cfg.val) { _buyerHeaderFilters[col] = cfg; }
        else { delete _buyerHeaderFilters[col]; }
        try { localStorage.setItem('tbl_filter_gov_buyer', JSON.stringify(_buyerHeaderFilters)); } catch(e){}
        _buyerPage = 1;
        _buildBuyerHead();
        renderBuyerPage();
      });
    }
    window.openBuyerFilter = openBuyerFilter;

    function sortBuyer(col) {
      if (_buyerSortCol === col) _buyerSortDir = _buyerSortDir === 'desc' ? 'asc' : 'desc';
      else { _buyerSortCol = col; _buyerSortDir = 'desc'; }
      _buyerData.sort((a, b) => {
        let va = a[col], vb = b[col];
        if (typeof va === 'string') return _buyerSortDir === 'asc' ? (va || '').localeCompare(vb || '') : (vb || '').localeCompare(va || '');
        return _buyerSortDir === 'asc' ? (va || 0) - (vb || 0) : (vb || 0) - (va || 0);
      });
      _buyerPage = 1;
      _buildBuyerHead();
      renderBuyerPage();
    }

    function _cleanDept(d) {
      if (!d || d === '--') return '--';
      return String(d).replace(/^\d+\s*-\s*/, '').trim() || '--';
    }

    function renderBuyerPage() {
      const loc = typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR';
      const data = getFilteredBuyerData();
      const totalPages = Math.max(1, Math.ceil(data.length / _BUYER_PAGE_SIZE));
      if (_buyerPage > totalPages) _buyerPage = totalPages;
      if (_buyerPage < 1) _buyerPage = 1;
      const start = (_buyerPage - 1) * _BUYER_PAGE_SIZE;
      const slice = data.slice(start, start + _BUYER_PAGE_SIZE);
      document.getElementById('buyerBody').innerHTML = slice.map(d => {
        const dep = _cleanDept(d.depart || d.area);
        return `<tr><td>${(d.buyer || '').substring(0, 24)}</td><td title="${dep.replace(/"/g, '&quot;')}" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${dep}</td><td>${t(d.tipo_excecao || '')}</td><td>${(d.qty || 0).toLocaleString(loc)}</td><td>${fmt(d.valor)}</td><td>${d.pct_transacoes || 0}%</td></tr>`;
      }).join('');
      document.getElementById('buyerPageInfo').textContent = tt('Página {page} de {pages}', { page: _buyerPage.toLocaleString(loc), pages: totalPages.toLocaleString(loc) });
      document.getElementById('buyerPrev').disabled = _buyerPage <= 1;
      document.getElementById('buyerNext').disabled = _buyerPage >= totalPages;
    }
    function buyerPage(dir) { _buyerPage += dir; renderBuyerPage(); }

    async function loadBuyer() {
      const rawBuyer = await fetch(`/api/governance/by-buyer?${getFilters()}`).then(r => r.json());
      _buyerData = rawBuyer.filter(d => { const t = (d.tipo_excecao || '').toLowerCase(); return !t.includes('emergencial') && !t.includes('nf sem oc'); });
      _buyerData.sort((a, b) => (b.valor || 0) - (a.valor || 0));
      _buyerSortCol = 'valor'; _buyerSortDir = 'desc';
      _buyerPage = 1;
      // Update title with top 3 concentration
      const total = _buyerData.reduce((a, d) => a + (d.valor || 0), 0);
      const buyers = new Set(_buyerData.map(d => d.buyer));
      const topBuyers = [...buyers].slice(0, 3);
      const top3Sum = _buyerData.filter(d => topBuyers.includes(d.buyer)).reduce((a, d) => a + (d.valor || 0), 0);
      const pct = total ? ((top3Sum / total) * 100).toFixed(1) : 0;
      document.getElementById('ttlBuyer').textContent = tt('Três criadores OC concentram {pct}% do valor de exceções', { pct: pct });
      _buildBuyerHead();
      renderBuyerPage();
    }

    function exportBuyer() {
      const data = getFilteredBuyerData();
      if (!data.length) return;
      const rows = data.map(d => ({
        [t('Criador OC')]: d.buyer || '',
        [t('Depart.')]: _cleanDept(d.depart || d.area),
        [t('Tipo Exceção')]: d.tipo_excecao || '',
        [t('Quantidade')]: d.qty || 0,
        [t('Valor (R$)')]: d.valor || 0,
        [t('% Exceções')]: d.pct_transacoes || 0
      }));
      const ws = XLSX.utils.json_to_sheet(rows);
      ws['!cols'] = [{ wch: 25 }, { wch: 20 }, { wch: 16 }, { wch: 12 }, { wch: 18 }, { wch: 14 }];
      ws['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: rows.length, c: 5 } }) };
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, t('Criadores OC'));
      XLSX.writeFile(wb, 'criadores_oc_excecoes.xlsx');
    }

    let _excData = [];
    let _excPage = 1;
    const _EXC_PAGE_SIZE = 10;
    let _excSortCol = 'net_spend';
    let _excSortDir = 'desc';

    function _isPosFatura() { return currentExcType === 'pos_fatura'; }
    function _isUrgente() { return currentExcType === 'urgente'; }
    function _isSemOC() { return currentExcType === 'sem_oc'; }
    function _isOC90() { return currentExcType === 'oc_90'; }
    function _isBlanketOld() { return currentExcType === 'blanket_old'; }
    function _isDecentral() { return currentExcType === 'decentral'; }
    function _isSucessivas() { return currentExcType === 'sucessivas'; }

    let _sucessivasFilter = 'all'; // 'all', 'similar', 'identical'
    function setSucessivasFilter(mode) {
      _sucessivasFilter = mode;
      document.querySelectorAll('#sucessivasPills .view-toggle-pill').forEach(b => b.classList.remove('active'));
      if (mode === 'all') document.getElementById('btnSucAll').classList.add('active');
      if (mode === 'similar') document.getElementById('btnSucSimilar').classList.add('active');
      if (mode === 'identical') document.getElementById('btnSucIdentical').classList.add('active');
      _excPage = 1;
      renderExcPage();
    }

    function _excCols() {
      if (_isBlanketOld()) {
        return [
          { key: 'tipo_excecao', label: 'Tipo' },
          { key: 'NUMERO_OC', label: 'Nº Acordo' },
          { key: 'comprador', label: 'Criador OC' },
          { key: 'depart_comprador', label: 'Depart. Criador OC' },
          { key: 'fornecedor', label: 'Fornecedor' },
          { key: 'data_oc', label: 'Data OC' },
          { key: 'dias_aberto', label: 'Dias Aberto' },
          { key: 'acordo_dt_criacao', label: 'Criação Acordo' },
          { key: 'acordo_data_final', label: 'Fim Acordo' },
          { key: 'acordo_status', label: 'Status' },
          { key: 'acordo_descricao', label: 'Descrição' },
          { key: 'net_spend', label: 'Valor do Acordo (R$)' },
          { key: 'valor_liberado', label: 'Valor Liberado (R$)' }
        ];
      }
      if (_isOC90()) {
        return [
          { key: 'tipo_excecao', label: 'Tipo' },
          { key: 'NUMERO_OC', label: 'Nº OC' },
          { key: 'comprador', label: 'Criador OC' },
          { key: 'depart_comprador', label: 'Depart. Criador OC' },
          { key: 'solicitante', label: 'Solicitante' },
          { key: 'depart_solicitante', label: 'Depart. Solicitante' },
          { key: 'fornecedor', label: 'Fornecedor' },
          { key: 'data_oc', label: 'Data OC' },
          { key: 'dias_aberto', label: 'Dias Aberto' },
          { key: 'net_spend', label: 'Valor (R$)' }
        ];
      }
      if (_isSucessivas()) {
        return [
          { key: 'tipo_excecao', label: 'Tipo Exceção' },
          { key: 'id_grupo', label: 'ID Grupo' },
          { key: 'NUMERO_OC', label: 'Nº OC' },
          { key: 'num_forn', label: 'Cód. Fornecedor' },
          { key: 'fornecedor', label: 'Fornecedor' },
          { key: 'item', label: 'Item Aquisição' },
          { key: 'data_oc', label: 'Data OC' },
          { key: 'qtd_ocs_grupo', label: 'OCs no Mês' },
          { key: 'diff_pct', label: 'Dispersão de Valor' },
          { key: 'net_spend', label: 'Valor OC' },
          { key: 'valor_total_grupo', label: 'Total Mês (Grupo)' },
          { key: 'comprador', label: 'Criador OC' },
          { key: 'depart_comprador', label: 'Depart. Criador OC' },
          { key: 'solicitante', label: 'Solicitante' },
          { key: 'depart_solicitante', label: 'Depart. Solicitante' }
        ];
      }
      const cols = [{ key: 'tipo_excecao', label: 'Tipo Exceção' }];
      if (!_isSemOC()) cols.push({ key: 'NUMERO_OC', label: 'Nº OC' });
      if (!_isUrgente() && !_isSemOC() && !_isDecentral()) cols.push({ key: 'NOTA_FISCAL', label: 'Nota Fiscal' });
      if (_isPosFatura()) cols.push({ key: 'numero_acordo', label: 'Acordo Compra' });
      if (_isDecentral()) cols.push({ key: 'data_oc', label: 'Data OC' });
      if (_isSemOC()) cols.push({ key: 'NOTA_FISCAL', label: 'Nota Fiscal' }, { key: 'data_fatura', label: 'Data Lançamento' }, { key: 'data_pagamento', label: 'Data Pagamento' });
      if (_isUrgente()) cols.push({ key: 'data_emissao_oc', label: 'Data OC' });
      if (_isPosFatura()) cols.push(
        { key: 'data_fatura', label: 'DT Criação NF' },
        { key: 'data_criacao_oc', label: 'DT Criação OC' },
        { key: 'data_aprov_oc', label: 'DT Aprov OC' },
        { key: 'dias_pos_fatura', label: 'Dias Pós-Fat' }
      );
      if (!_isSemOC()) {
        cols.push(
          { key: 'comprador', label: 'Criador OC' },
          { key: 'depart_comprador', label: 'Depart. Criador OC' },
          { key: 'solicitante', label: 'Solicitante' },
          { key: 'depart_solicitante', label: 'Depart. Solicitante' }
        );
      }
      cols.push(
        { key: 'fornecedor', label: 'Fornecedor' },
        { key: 'net_spend', label: 'Spend Líquido' }
      );
      if (_isSemOC()) cols.push({ key: 'gross_spend', label: 'Spend Bruto' });
      return cols;
    }

    let _excHeaderFilters = JSON.parse(localStorage.getItem('tbl_filter_gov_exc') || '{}');

    function getFilteredExcData() {
      let data = _excData;
      if (_isSucessivas()) {
        if (_sucessivasFilter === 'similar') {
          data = data.filter(d => d.is_similar === 1);
        } else if (_sucessivasFilter === 'identical') {
          data = data.filter(d => d.is_identical === 1);
        }
      }
      return TableColumnFilter.filterData(data, _excHeaderFilters, (item, k) => {
        if (k === 'depart_comprador' || k === 'depart_solicitante') return _cleanDept(item[k]);
        if (k === 'id_grupo') return item.id_grupo;
        if (k === 'net_spend') return item.net_spend;
        if (k === 'gross_spend') return item.gross_spend;
        if (k === 'valor_total_grupo') return item.valor_total_grupo;
        if (k === 'qtd_ocs_grupo') return item.qtd_ocs_grupo;
        if (k === 'diff_pct') return item.diff_pct;
        if (k === 'dias_pos_fatura') return item.dias_pos_fatura;
        if (k === 'dias_aberto') return item.dias_aberto;
        return item[k];
      });
    }

    function _buildExcHead() {
      const cols = _excCols();
      const indicator = c => c.key === _excSortCol ? (_excSortDir === 'desc' ? '\u25BC' : '\u25B2') : '';
      document.getElementById('excHead').innerHTML = '<tr>' + cols.map(c => {
        const isFiltered = !!(_excHeaderFilters[c.key] && _excHeaderFilters[c.key].val);
        const thClass = isFiltered ? 'th-filtered' : '';
        const filterBtn = TableColumnFilter.renderBtn(c.key, c.label, isFiltered, `openExcFilter(event, '${c.key}', '${c.label.replace(/'/g, "\\'")}')`);
        const infoIcon = c.key === 'diff_pct'
          ? `<span title="${t('Dispersão de Valor no Grupo:\nMede a variação entre as OCs do mesmo fornecedor e item no mês civil.\n\nFórmula:\n((Maior OC - Menor OC) ÷ Média do Grupo) × 100\n\n• 0% (Idênticas): Todas as OCs têm o mesmo valor exato (forte indício de fracionamento de alçada).\n• Até 20% (±10%): Valores muito próximos da média.\n• Valores altos: Pedidos com valores bem heterogêneos.')}" style="cursor:help;display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;border-radius:50%;background:rgba(59,130,246,0.18);color:#60a5fa;font-size:10px;font-weight:700;margin-left:4px;" onclick="event.stopPropagation()">ⓘ</span>`
          : '';
        return `<th class="${thClass}" style="user-select:none;white-space:nowrap;padding:.4rem .6rem;">
          <div style="display:flex;align-items:center;justify-content:space-between;width:100%;gap:4px;">
            <span style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;flex:1;overflow:hidden;text-overflow:ellipsis;" onclick="sortExc('${c.key}')" title="Clique para ordenar">
              <span>${t(c.label)}</span>
              ${infoIcon}
              <span id="srt_${c.key}">${indicator(c)}</span>
            </span>
            ${filterBtn}
          </div>
        </th>`;
      }).join('') + '</tr>';
    }

    function openExcFilter(e, colKey, colLabel) {
      TableColumnFilter.open(e, colKey, colLabel, _excHeaderFilters[colKey], (col, cfg) => {
        if (cfg && cfg.val) { _excHeaderFilters[col] = cfg; }
        else { delete _excHeaderFilters[col]; }
        try { localStorage.setItem('tbl_filter_gov_exc', JSON.stringify(_excHeaderFilters)); } catch(e){}
        _excPage = 1;
        _buildExcHead();
        renderExcPage();
      });
    }
    window.openExcFilter = openExcFilter;

    function sortExc(col) {
      if (_excSortCol === col) _excSortDir = _excSortDir === 'desc' ? 'asc' : 'desc';
      else { _excSortCol = col; _excSortDir = col === 'dias_pos_fatura' || col === 'net_spend' || col === 'gross_spend' || col === 'valor_total_grupo' ? 'desc' : 'asc'; }
      _excData.sort((a, b) => {
        if (_isSucessivas() && (col === 'id_grupo' || col === 'valor_total_grupo')) {
          let va = a.grupo_rank || 0, vb = b.grupo_rank || 0;
          if (col === 'valor_total_grupo') {
            va = a.valor_total_grupo || 0;
            vb = b.valor_total_grupo || 0;
          }
          let diff = _excSortDir === 'asc' ? va - vb : vb - va;
          if (diff !== 0) return diff;
          return (b.net_spend || 0) - (a.net_spend || 0);
        }
        let va = a[col], vb = b[col];
        if (va == null) va = typeof vb === 'string' ? '' : 0;
        if (vb == null) vb = typeof va === 'string' ? '' : 0;
        if (typeof va === 'string') return _excSortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
        return _excSortDir === 'asc' ? va - vb : vb - va;
      });
      _excPage = 1;
      _buildExcHead();
      renderExcPage();
    }

    function _fmtDate(d) { if (!d) return '--'; return d.substring(0, 10).split('-').reverse().join('/'); }

    function _cellVal(d, key) {
      if (key === 'id_grupo') return `<td style="white-space:nowrap;"><span style="display:inline-block;padding:2px 7px;border-radius:5px;font-size:.65rem;font-weight:700;letter-spacing:0.02em;background:rgba(59,130,246,0.12);color:#60a5fa;border:1px solid rgba(59,130,246,0.28);font-family:monospace;">${d.id_grupo || '--'}</span></td>`;
      if (key === 'net_spend' || key === 'valor_liberado') return `<td style="font-weight:700">${fmt(d[key])}</td>`;
      if (key === 'gross_spend') return `<td style="font-weight:700">${d.gross_spend != null ? fmt(d.gross_spend) : '--'}</td>`;
      if (key === 'data_pagamento') return `<td>${_fmtDate(d.data_pagamento)}</td>`;
      if (key === 'valor_total_grupo') return `<td style="font-weight:700;color:var(--fr-txt,#E8F4FD)">${fmt(d.valor_total_grupo)}</td>`;
      if (key === 'data_fatura' || key === 'data_oc' || key === 'data_emissao_oc' || key === 'data_criacao_oc' || key === 'data_aprov_oc' || key === 'acordo_dt_criacao' || key === 'acordo_data_final') return `<td>${_fmtDate(d[key])}</td>`;
      if (key === 'dias_pos_fatura') return `<td style="font-weight:700;color:#f59e0b">${d.dias_pos_fatura != null ? d.dias_pos_fatura + ' ' + t('dias') : '--'}</td>`;
      if (key === 'dias_aberto') return `<td style="font-weight:700;color:#f87171">${d.dias_aberto != null ? d.dias_aberto + ' ' + t('dias') : '--'}</td>`;
      if (key === 'acordo_descricao') return `<td title="${(d[key] || '').replace(/"/g, '&quot;')}" style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${(d[key] || '').substring(0, 30)}</td>`;
      if (key === 'acordo_status') return `<td>${d[key] || '--'}</td>`;
      if (key === 'numero_acordo') return `<td>${d.numero_acordo && d.numero_acordo !== '-' ? d.numero_acordo : '--'}</td>`;
      if (key === 'num_forn') return `<td>${d.num_forn || '--'}</td>`;
      if (key === 'item') return `<td title="${(d.item || '').replace(/"/g, '&quot;')}" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${(d.item || '').substring(0, 32)}</td>`;
      if (key === 'qtd_ocs_grupo') return `<td style="font-weight:700;text-align:center">${d.qtd_ocs_grupo || 0}</td>`;
      if (key === 'diff_pct') {
        const tooltip = `Dispersão do Grupo ${d.id_grupo || ''}:\nFórmula: ((Maior OC - Menor OC) ÷ Média do Grupo) × 100\nMede o grau de variação entre os pedidos do mesmo item e fornecedor no mês.\n${d.is_identical === 1 ? '• Todas as OCs deste grupo têm valor idêntico (0%).' : d.is_similar === 1 ? '• Valores dentro de ±10% da média do grupo.' : '• Grupo com pedidos de valores heterogêneos.'}`;
        if (d.is_identical === 1) {
          return `<td style="white-space:nowrap;"><span title="${tooltip}" style="background:rgba(239,68,68,0.18);color:#f87171;padding:2px 6px;border-radius:4px;border:1px solid rgba(239,68,68,0.35);font-size:.65rem;font-weight:800;cursor:help;">0% (Idênticas)</span></td>`;
        }
        if (d.is_similar === 1) {
          return `<td style="white-space:nowrap;"><span title="${tooltip}" style="background:rgba(245,158,11,0.18);color:#fbbf24;padding:2px 6px;border-radius:4px;border:1px solid rgba(245,158,11,0.35);font-size:.65rem;font-weight:700;cursor:help;">${d.diff_pct}% (±10%)</span></td>`;
        }
        return `<td title="${tooltip}" style="cursor:help;">${d.diff_pct != null ? d.diff_pct + '%' : '--'}</td>`;
      }
      if (key === 'comprador') return `<td title="${(d.comprador || '').replace(/"/g, '&quot;')}">${(d.comprador || '').substring(0, 24)}</td>`;
      if (key === 'depart_comprador') {
        const dep = _cleanDept(d.depart_comprador);
        return `<td title="${dep.replace(/"/g, '&quot;')}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${dep}</td>`;
      }
      if (key === 'solicitante') return `<td title="${(d.solicitante || '').replace(/"/g, '&quot;')}">${(d.solicitante || '').substring(0, 24)}</td>`;
      if (key === 'depart_solicitante') {
        const dep = _cleanDept(d.depart_solicitante);
        return `<td title="${dep.replace(/"/g, '&quot;')}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${dep}</td>`;
      }
      if (key === 'fornecedor') return `<td title="${(d.fornecedor || '').replace(/"/g, '&quot;')}">${(d.fornecedor || '').substring(0, 25)}</td>`;
      return `<td>${d[key] || ''}</td>`;
    }

    function renderExcPage() {
      const loc = typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR';
      const data = getFilteredExcData();
      const totalPages = Math.max(1, Math.ceil(data.length / _EXC_PAGE_SIZE));
      if (_excPage > totalPages) _excPage = totalPages;
      const start = (_excPage - 1) * _EXC_PAGE_SIZE;
      const slice = data.slice(start, start + _EXC_PAGE_SIZE);
      const cols = _excCols();
      document.getElementById('excBody').innerHTML = slice.map((d, idx) => {
        const prev = idx > 0 ? slice[idx - 1] : null;
        const isNewGroup = _isSucessivas() && prev && prev.id_grupo !== d.id_grupo;
        const trStyle = isNewGroup ? 'border-top: 2px solid rgba(148, 163, 184, 0.28);' : '';
        return `<tr style="${trStyle}">` + cols.map(c => _cellVal(d, c.key)).join('') + '</tr>';
      }).join('');
      document.getElementById('excPageInfo').textContent = tt('Página {page} de {pages}', {
        page: _excPage.toLocaleString(loc),
        pages: totalPages.toLocaleString(loc)
      });
      document.getElementById('excPrev').disabled = _excPage <= 1;
      document.getElementById('excNext').disabled = _excPage >= totalPages;
    }
    function excPage(dir) { _excPage += dir; renderExcPage(); }
    function jumpExcPage() {
      const loc = typeof _getLocale !== 'undefined' ? _getLocale() : 'pt-BR';
      const data = getFilteredExcData();
      const totalPages = Math.max(1, Math.ceil(data.length / _EXC_PAGE_SIZE));
      const p = prompt(`Ir para página (1 a ${totalPages.toLocaleString(loc)}):`, _excPage);
      if (p) {
        const num = parseInt(p.replace(/\D/g, ''), 10);
        if (!isNaN(num) && num >= 1 && num <= totalPages) {
          _excPage = num;
          renderExcPage();
        }
      }
    }

    async function loadExcTable() {
      try {
        const res = await fetch(`/api/governance/exceptions-table?type=${currentExcType}&per_page=0&${getFilters()}`).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
        _excData = Array.isArray(res) ? res : [];
        if (_isSucessivas()) {
          _excData.sort((a, b) => {
            const grpDiff = (a.grupo_rank || 0) - (b.grupo_rank || 0);
            if (grpDiff !== 0) return grpDiff;
            return (b.net_spend || 0) - (a.net_spend || 0);
          });
          _excSortCol = 'id_grupo';
          _excSortDir = 'asc';
        } else {
          _excData.sort((a, b) => (b.net_spend || 0) - (a.net_spend || 0));
          _excSortCol = 'net_spend';
          _excSortDir = 'desc';
        }
        _excPage = 1;
      } catch (e) { console.error('loadExcTable error:', e); _excData = []; _excPage = 1; }
      _buildExcHead();
      renderExcPage();
    }
    function setExcType(t, btn) {
      currentExcType = t;
      _excHeaderFilters = {};
      const p = document.getElementById('sucessivasPills');
      if (p) p.style.display = (t === 'sucessivas' ? 'inline-flex' : 'none');
      document.querySelectorAll('.exc-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadExcTable();
    }

    async function exportExc() {
      const btn = document.querySelector('button[onclick="exportExc()"]');
      const data = getFilteredExcData();
      if (!data.length) { alert(t('Sem dados')); return; }
      const origHtml = btn ? btn.innerHTML : '';
      if (btn) { btn.disabled = true; btn.innerHTML = t('Carregando...'); }
      try {
        // Mesmas colunas e mesma ordenação exibidas na tela (sem nova consulta ao banco)
        const cols = _excCols();
        const typeOf = k => (k === 'net_spend' || k === 'gross_spend' || k === 'valor_total_grupo' || k === 'valor_liberado') ? 'currency'
          : (['qty_notas', 'dias_pos_fatura', 'dias_aberto', 'qtd_ocs_grupo'].includes(k) ? 'integer'
          : (/^data_|^acordo_dt_|^acordo_data_/.test(k) ? 'date' : 'text'));
        const valOf = (d, k) => {
          if (k === 'depart_comprador' || k === 'depart_solicitante') return _cleanDept(d[k]);
          if (k === 'tipo_excecao') return t(d[k] || '');
          if (k === 'diff_pct') return d.is_identical === 1 ? '0% (Idênticas)' : (d.is_similar === 1 ? d.diff_pct + '% (±10%)' : (d.diff_pct != null ? d.diff_pct + '%' : '--'));
          return d[k] == null ? '' : d[k];
        };
        const payload = {
          filename: 'excecoes_' + currentExcType,
          sheet: t('Exceções'),
          columns: cols.map(c => ({ label: t(c.label) + (c.key === 'net_spend' || c.key === 'gross_spend' ? ' (R$)' : ''), type: typeOf(c.key) })),
          rows: data.map(d => cols.map(c => valOf(d, c.key)))
        };
        const resp = await fetch('/api/export/table-xlsx', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const blob = await resp.blob();
        const cd = resp.headers.get('Content-Disposition') || '';
        const m = cd.match(/filename="([^"]+)"/);
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = m ? m[1] : 'excecoes_governanca.xlsx';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      } catch (e) {
        console.error('exportExc error:', e);
        alert('Erro ao exportar: ' + e.message);
      } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = origHtml; }
      }
    }

    function toggleAdvFilters() { const b = document.getElementById('advFiltersBar'), btn = document.getElementById('btnAdvFilters'); if (b.style.display === 'none') { b.style.display = 'flex'; btn.style.borderColor = 'rgba(59,130,246,.45)'; btn.style.color = '#60a5fa'; } else { b.style.display = 'none'; btn.style.borderColor = 'rgba(100,116,139,.35)'; btn.style.color = '#94a3b8'; } }
    function loadAll() { return Promise.allSettled([loadKPIs(), loadImpact(), loadBuyer(), loadExcTable()]); }
    function toggleTheme() { const h = document.documentElement; const n = h.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'; h.setAttribute('data-theme', n); localStorage.setItem('theme', n); loadAll(); }
    const s = localStorage.getItem('theme'); if (s) document.documentElement.setAttribute('data-theme', s);

    async function initFilters() {
      const data = await (window.fetchCachedFilterData ? window.fetchCachedFilterData('/api/filters/notas') : fetch('/api/filters/notas').then(r => r.json()));
      filters.fEmpresa = new MultiSelect(document.getElementById('fEmpresa'), data.empresas || ['BB', 'BQ']);
      filters.fEmpresa.selected = new Set(['BB', 'BQ']); filters.fEmpresa.renderOptions(); filters.fEmpresa.updateLabel();
      filters.fAno = new MultiSelect(document.getElementById('fAno'), data.anos || []);
      const cy = String(new Date().getFullYear()); if (filters.fAno.options.includes(cy)) { filters.fAno.selected = new Set([cy]); filters.fAno.renderOptions(); filters.fAno.updateLabel(); }
      filters.fMes = new MultiSelect(document.getElementById('fMes'), (data.meses || []).map(m => String(m)));
      filters.fGrupo = new MultiSelect(document.getElementById('fGrupo'), data.grupos || []);
      filters.fFornecedor = new MultiSelect(document.getElementById('fFornecedor'), data.fornecedores || []);
      const cm = String(new Date().getMonth() + 1); if (filters.fMes.options.includes(cm)) { filters.fMes.selected = new Set([cm]); filters.fMes.renderOptions(); filters.fMes.updateLabel(); }
      if (document.getElementById('fFornNegociavel')) {
        filters.fFornNegociavel = new MultiSelect(document.getElementById('fFornNegociavel'), ['NEGOCIAVEL', 'NÃO NEGOCIAVEL']);
      }
      if (typeof FilterStateStore !== 'undefined') FilterStateStore.restore();
      _filtersReady = true;
      // Check URL for pre-selected exception type (linked from performance tab)
      const urlExcType = new URLSearchParams(window.location.search).get('exc_type');
      if (urlExcType) {
        currentExcType = urlExcType;
        const targetBtn = document.querySelector(`.exc-btn[data-type="${urlExcType}"]`);
        if (targetBtn) {
          document.querySelectorAll('.exc-btn').forEach(b => b.classList.remove('active'));
          targetBtn.classList.add('active');
          // Scroll to the exceptions table
          setTimeout(() => { targetBtn.closest('.card').scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 500);
        }
      }
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
      // Compradores (from ordens_compra)
      if (document.getElementById('fComprador')) {
        fetch('/api/filters/cascading-ordens').then(r => r.json()).then(d => {
          filters.fComprador = new MultiSelect(document.getElementById('fComprador'), d.compradores || []);
        }).catch(() => { });
      }
    }
    initFilters();
  