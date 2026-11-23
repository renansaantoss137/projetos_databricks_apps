
let cPlanned;
function fmt(v,t='currency'){if(v==null||isNaN(v))return'--';const a=Math.abs(v);if(t==='currency'){if(a>=1e9)return'R$ '+(v/1e9).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})+' Bi';if(a>=1e6)return'R$ '+(v/1e6).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})+' mi';if(a>=1e3)return'R$ '+(v/1e3).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})+' mil';return'R$ '+v.toLocaleString('pt-BR',{maximumFractionDigits:0});}return v.toLocaleString('pt-BR');}

// MultiSelect and filters provided by filters-shared.js
// Use ordens_compra cascading endpoint
_cascadeEndpoint = '/api/filters/cascading-ordens';
// i18n: override fmt with localized version
if (typeof fmtI18n !== 'undefined') fmt = fmtI18n;
document.addEventListener('langChange', function() { if (typeof loadAll === 'function') loadAll(); });

function _soft(){ return document.documentElement.getAttribute('data-theme')==='light' ? '#475569' : 'rgba(168,204,223,.55)'; }
async function loadKPIs(){
  const d=(await fetch('/api/orders/kpis?'+getFilters()).then(r=>r.json()))[0]||{};
  document.getElementById('vOpen').textContent = fmt(d.open_value);
  document.getElementById('vOpenQty').textContent = d.open_pos!=null ? d.open_pos.toLocaleString('pt-BR') : '--';
  document.getElementById('vLate').textContent = d.late_pos!=null ? d.late_pos.toLocaleString('pt-BR') : '--';
  document.getElementById('vAvgDelay').textContent = d.avg_delay!=null ? Math.round(d.avg_delay) : '--';
  const sc = _soft();
  // Late value + % in Valor em Aberto card
  if(d.late_value!=null && d.open_value) {
    const latePct = (d.late_value / d.open_value * 100).toFixed(0);
    document.getElementById('dOpen').innerHTML=`<span style="font-size:.56rem;font-weight:700;color:#f87171">${fmt(d.late_value)} ${t('em atraso')}</span><span style="font-size:.5rem;color:${sc}">(${latePct}% ${t('do valor em aberto')})</span>`;
  }
  // Late % of total open (pedidos)
  if(d.late_pos!=null && d.open_pos) { const latePct = (d.late_pos / d.open_pos * 100).toFixed(1); document.getElementById('dLate').innerHTML=`<span style="font-size:.6rem;font-weight:700;color:#f87171">${latePct}%</span> <span style="font-size:.5rem;color:${sc}">${t('do total em aberto')}</span>`; }
}

async function loadPlanned(){
  const data = await fetch(`/api/orders/planned-vs-realized?${getFilters()}`).then(r=>r.json());
  const labels = data.map(d => {
    if(!d.mes) return '';
    const parts = d.mes.split('-');
    const mNames = typeof getMonths !== 'undefined' ? getMonths() : ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
    return mNames[parseInt(parts[1]||parts[0])-1] || d.mes.substring(5);
  });
  if(cPlanned) cPlanned.destroy();
  const ctx = document.getElementById('chartPlanned').getContext('2d');
  const h = ctx.canvas.parentElement.offsetHeight || 220;
  const gPrev = ctx.createLinearGradient(0, 0, 0, h);
  gPrev.addColorStop(0, '#2563eb'); gPrev.addColorStop(1, '#1e40af');
  const gReal = ctx.createLinearGradient(0, 0, 0, h);
  gReal.addColorStop(0, '#93c5fd'); gReal.addColorStop(1, '#3b82f6');
  // Dados: Realizado (todas OCs) + A Realizar (OCs abertas: original - utilizado)
  const restanteData = data.map(d => d.remaining || 0);
  // % Realizado vs Total (Realizado + A Realizar)
  const pctData = data.map(d => {
    const total = (d.realized||0) + (d.remaining||0);
    return total > 0 ? Math.round((d.realized / total) * 1000) / 10 : null;
  });

  cPlanned = new Chart(ctx,{
    type:'bar',
    plugins:[ChartDataLabels],
    data:{ labels, datasets:[
      {label:t('Realizado (Recebido/Faturado)'), data:data.map(d=>d.realized), backgroundColor:gReal, borderRadius:{topLeft:0, topRight:0, bottomLeft:6, bottomRight:6}, borderSkipped:false, barPercentage:.7, categoryPercentage:.75,
        datalabels:{display:false}},
      {label:t('A Realizar (Restante)'), data:restanteData, backgroundColor:'rgba(30,64,175,0.45)', borderRadius:{topLeft:6, topRight:6, bottomLeft:0, bottomRight:0}, borderSkipped:false, barPercentage:.7, categoryPercentage:.75,
        datalabels:{
          display: (ctx2) => pctData[ctx2.dataIndex] != null && pctData[ctx2.dataIndex] > 0,
          formatter: (val, ctx2) => pctData[ctx2.dataIndex] != null ? pctData[ctx2.dataIndex] + '%' : '',
          color: '#fbbf24',
          anchor: 'end',
          align: 'end',
          offset: 2,
          font: {size: 10, weight: '800'}
        }},
    ]},
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{
        legend:{display:false},
        tooltip:{backgroundColor:'#1e2433', borderColor:'rgba(100,116,139,.3)', borderWidth:1, titleColor:'#E8F4FD', bodyColor:'#E8F4FD', padding:12, cornerRadius:8, titleFont:{size:12,weight:'700'}, bodyFont:{size:11,weight:'600'}, callbacks:{label:item=> `  ${item.dataset.label}: ${fmt(item.raw)}`}},
        datalabels:{}
      },
      scales:{
        x:{stacked:true, grid:{display:false}, border:{display:false}, ticks:{color:getComputedStyle(document.documentElement).getPropertyValue('--fr-tick')||'rgba(168,204,223,.85)', font:{size:12, weight:'700'}, padding:10}},
        y:{stacked:true, title:{display:false}, grid:{display:false}, border:{display:false}, ticks:{color:getComputedStyle(document.documentElement).getPropertyValue('--fr-tick')||'rgba(168,204,223,.7)', font:{size:9}, maxTicksLimit:5, callback:v=>fmt(v)}}
      },
      layout:{padding:{top:24, bottom:4, left:4, right:4}}
    }
  });
}

async function loadOverdue(){
  const data = await fetch('/api/orders/overdue-by-supplier?'+getFilters()).then(r=>r.json());
  const max = Math.max(...data.map(d=>d.open_value||0));
  const total = data.reduce((s,d)=>s+(d.open_value||0),0);
  const top5 = data.slice(0,5).reduce((s,d)=>s+(d.open_value||0),0);
  document.getElementById('ttlOverdue').textContent = tt('Os 5 maiores fornecedores concentram {pct}% do valor atrasado', {pct: total?((top5/total)*100).toFixed(0):0});
  document.getElementById('overdueNote').textContent = '';
  document.getElementById('overdueList').innerHTML = data.slice(0,10).map((d, i) => {
    const w = max ? ((d.open_value||0)/max*100) : 0;
    const isTop = i < 5;
    const barBg = isTop ? 'linear-gradient(90deg,#1e40af,#3b82f6)' : 'linear-gradient(90deg,rgba(100,116,139,.3),rgba(100,116,139,.2))';
    const lblStyle = isTop ? 'color:var(--fr-txt,#E8F4FD)' : 'color:var(--fr-txt-soft,rgba(168,204,223,.45))';
    const valStyle = isTop ? 'color:var(--fr-txt,#E8F4FD)' : 'color:var(--fr-txt-soft,rgba(168,204,223,.45))';
    const daysColor = isTop ? 'color:#f87171' : 'color:var(--fr-txt-soft,rgba(168,204,223,.4))';
    return `<div class="overdue-row"><span class="overdue-lbl" style="${lblStyle}">${(d.fornecedor||'').substring(0,18)}</span><div class="overdue-track"><div class="overdue-fill" style="width:${w}%;background:${barBg}"></div><span class="overdue-qty">${(d.qty||0).toLocaleString('pt-BR')}</span></div><span class="overdue-val" style="${valStyle}">${fmt(d.open_value)}</span><span class="overdue-days" style="${daysColor}">${d.avg_days_late||0}</span></div>`;
  }).join('');
}

async function loadBuckets(){
  const data = await fetch('/api/orders/delay-buckets?'+getFilters()).then(r=>r.json());
  const order = [{b:'No prazo',d:t('No prazo'),c:'green'},{b:'1-30 dias',d:t('1-30 dias'),c:'yellow'},{b:'31-60 dias',d:t('31-60 dias'),c:'orange'},{b:'61-90 dias',d:t('61-90 dias'),c:'red'},{b:'91-120 dias',d:t('91-120 dias'),c:'darkred'},{b:'>120 dias',d:t('>120 dias'),c:'crimson'}];
  const total = data.reduce((s,d)=>s+(d.valor||0),0);
  const max = Math.max(...data.map(d=>d.valor||0));
  let late90val = 0, late90qty = 0;
  document.getElementById('bucketList').innerHTML = order.map(({b,d:dl,c}) => {
    const row = data.find(d=>d.bucket===b) || {bucket:b, valor:0, qty:0};
    const pct = total ? ((row.valor/total)*100).toFixed(1) : 0;
    const w = max ? ((row.valor/max)*100) : 0;
    if(b==='91-120 dias' || b==='>120 dias') { late90val += (row.valor||0); late90qty += (row.qty||0); }
    return `<div class="bucket-row"><span class="bucket-label">${dl}</span><div class="bucket-track"><div class="bucket-fill ${c}" style="width:${w}%"></div><span class="bucket-qty">${(row.qty||0).toLocaleString(_getLocale())}</span></div><span class="bucket-val">${fmt(row.valor)}</span><span class="bucket-pct">${pct}%</span></div>`;
  }).join('');

  const attBox = document.getElementById('attentionBox');
  if (late90qty > 0) {
    if (attBox) {
      attBox.style.background = 'rgba(239,68,68,.06)';
      attBox.style.borderColor = 'rgba(239,68,68,.25)';
      const attTitle = attBox.querySelector('.attention-title');
      if (attTitle) { attTitle.textContent = 'ATENÇÃO'; attTitle.style.color = '#f87171'; }
    }
    document.getElementById('attVal').innerHTML = tt('Temos {qty} pedidos em aberto com mais de {days} dias de atraso, somando {val} entre eles.', {
      qty: `<span style="color:#f87171;font-size:1.2rem;font-weight:900">${late90qty.toLocaleString(_getLocale())}</span>`,
      days: `<span style="color:#fbbf24;font-weight:900">90</span>`,
      val: `<span style="color:#f87171;font-size:1.2rem;font-weight:900">${fmt(late90val)}</span>`
    });
  } else {
    if (attBox) {
      attBox.style.background = 'var(--surface-alt)';
      attBox.style.borderColor = 'var(--border)';
      const attTitle = attBox.querySelector('.attention-title');
      if (attTitle) { attTitle.textContent = 'STATUS REGULAR'; attTitle.style.color = 'var(--text-muted)'; }
    }
    document.getElementById('attVal').innerHTML = `<span style="color:var(--text-primary);font-size:0.85rem;font-weight:600">${t('Nenhum pedido em aberto com mais de 90 dias de atraso.')}</span>`;
  }
  document.getElementById('attDesc').textContent = '';
  document.getElementById('subtPlanned').textContent = `${fmt(total-((data.find(d=>d.bucket==='No prazo')||{}).valor||0))} previstos ainda não foram recebidos no prazo.`;
}

let _tableData = [];
let _sortedData = [];
let _sortCol = 'days_late';
let _sortDir = 'desc';
let _currentPage = 1;
const _pageSize = 20;
let _ordersHeaderFilters = JSON.parse(localStorage.getItem('tbl_filter_ord_orders') || '{}');

const _ORDERS_COLS = [
  { key: 'numero_oc', label: 'OC' },
  { key: 'fornecedor', label: 'Fornecedor' },
  { key: 'comprador', label: 'Comprador' },
  { key: 'open_value', label: 'R$ em Aberto' },
  { key: 'promised_date', label: 'Dt Prometida' },
  { key: 'days_late', label: 'Atraso (dias)' }
];

function getFilteredOrdersData() {
  return TableColumnFilter.filterData(_tableData, _ordersHeaderFilters, (item, k) => {
    if (k === 'numero_oc') return item.NUMERO_OC || item.numero_oc || '';
    if (k === 'fornecedor') return item.FORNECEDOR || item.fornecedor || '';
    if (k === 'open_value') return item.open_value;
    if (k === 'days_late') return item.days_late;
    return item[k];
  });
}

function _buildOrdersHead() {
  const thead = document.querySelector('#ordersTbl thead');
  if (!thead) return;
  thead.innerHTML = '<tr>' + _ORDERS_COLS.map(c => {
    const isFiltered = !!(_ordersHeaderFilters[c.key] && _ordersHeaderFilters[c.key].val);
    const thClass = (isFiltered ? 'th-filtered ' : '') + (_sortCol === c.key ? 'sorted' : '');
    const arrow = _sortCol === c.key ? (_sortDir === 'desc' ? '\u25BC' : '\u25B2') : '\u25B2\u25BC';
    const filterBtn = TableColumnFilter.renderBtn(c.key, c.label, isFiltered, `openOrdersFilter(event, '${c.key}', '${c.label.replace(/'/g, "\\'")}')`);
    return `<th class="${thClass}" data-col="${c.key}" style="user-select:none;white-space:nowrap;padding:.4rem .6rem;">
      <div style="display:flex;align-items:center;justify-content:space-between;width:100%;gap:4px;">
        <span style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;flex:1;overflow:hidden;text-overflow:ellipsis;" onclick="sortTable('${c.key}')" title="Clique para ordenar">
          <span>${t(c.label)}</span>
          <span class="sort-arrow">${arrow}</span>
        </span>
        ${filterBtn}
      </div>
      <div class="col-resizer"></div>
    </th>`;
  }).join('') + '</tr>';
}

function openOrdersFilter(e, colKey, colLabel) {
  TableColumnFilter.open(e, colKey, colLabel, _ordersHeaderFilters[colKey], (col, cfg) => {
    if (cfg && cfg.val) { _ordersHeaderFilters[col] = cfg; }
    else { delete _ordersHeaderFilters[col]; }
    try { localStorage.setItem('tbl_filter_ord_orders', JSON.stringify(_ordersHeaderFilters)); } catch(e){}
    _currentPage = 1;
    applyOrdersSortAndFilter();
  });
}
window.openOrdersFilter = openOrdersFilter;

function applyOrdersSortAndFilter() {
  const filtered = getFilteredOrdersData();
  _sortedData = [...filtered].sort((a, b) => {
    let va = a[_sortCol] || a[_sortCol.toUpperCase()] || '';
    let vb = b[_sortCol] || b[_sortCol.toUpperCase()] || '';
    if (_sortCol === 'numero_oc') { va = a.NUMERO_OC || a.numero_oc || ''; vb = b.NUMERO_OC || b.numero_oc || ''; }
    if (_sortCol === 'fornecedor') { va = a.FORNECEDOR || a.fornecedor || ''; vb = b.FORNECEDOR || b.fornecedor || ''; }
    if (typeof va === 'number' && typeof vb === 'number') return _sortDir === 'asc' ? va - vb : vb - va;
    return _sortDir === 'asc' ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
  });
  _buildOrdersHead();
  renderTablePage();
}

function _getTotalPages(){ return Math.max(1, Math.ceil(_sortedData.length / _pageSize)); }

function renderTablePage() {
  const start = (_currentPage - 1) * _pageSize;
  const pageData = _sortedData.slice(start, start + _pageSize);
  document.getElementById('tblBody').innerHTML = pageData.map(d => {
    const delay = d.days_late || 0;
    const color = delay <= 0 ? 'var(--text-muted)' : delay > 30 ? 'var(--danger)' : 'var(--warning)';
    return `<tr><td>${d.NUMERO_OC||d.numero_oc||''}</td><td>${(d.FORNECEDOR||d.fornecedor||'').substring(0,22)}</td><td>${d.comprador||''}</td><td>${fmt(d.open_value)}</td><td>${d.promised_date||''}</td><td><span class="days-badge" style="color:${color}">${delay}</span></td></tr>`;
  }).join('');
  const total = _sortedData.length;
  const totalPages = _getTotalPages();
  document.getElementById('tblPageInfo').textContent = tt('{total} registros \u2014 Página {page} de {pages}', {total: total.toLocaleString('pt-BR'), page: _currentPage, pages: totalPages});
  document.getElementById('btnPrev').disabled = _currentPage<=1;
  document.getElementById('btnPrev').style.opacity = _currentPage<=1?'.4':'1';
  document.getElementById('btnNext').disabled = _currentPage>=totalPages;
  document.getElementById('btnNext').style.opacity = _currentPage>=totalPages?'.4':'1';
}
function tblPrevPage(){ if(_currentPage>1){_currentPage--;renderTablePage();}}
function tblNextPage(){ if(_currentPage<_getTotalPages()){_currentPage++;renderTablePage();}}

function renderTableRows(data) {
  _tableData = data || [];
  _currentPage = 1;
  applyOrdersSortAndFilter();
}

function sortTable(col) {
  if (_sortCol === col) { _sortDir = _sortDir === 'asc' ? 'desc' : 'asc'; }
  else { _sortCol = col; _sortDir = (col === 'open_value' || col === 'days_late') ? 'desc' : 'asc'; }
  _currentPage = 1;
  applyOrdersSortAndFilter();
}

function exportTable() {
  if (!_sortedData.length) return;
  const wsData = [['OC', 'Fornecedor', 'Comprador', 'Valor em Aberto (R$)', 'Data Prometida', 'Dias de Atraso']];
  _sortedData.forEach(d => {
    wsData.push([
      d.NUMERO_OC || d.numero_oc || '',
      d.FORNECEDOR || d.fornecedor || '',
      d.comprador || '',
      d.open_value || 0,
      d.promised_date || '',
      d.days_late || 0
    ]);
  });
  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.aoa_to_sheet(wsData);
  ws['!cols'] = [{wch:16},{wch:28},{wch:22},{wch:20},{wch:14},{wch:14}];
  ws['!autofilter'] = {ref: XLSX.utils.encode_range({s:{r:0,c:0},e:{r:wsData.length-1,c:5}})};
  XLSX.utils.book_append_sheet(wb, ws, 'Pedidos em Atraso');
  XLSX.writeFile(wb, 'pedidos_em_atraso.xlsx');
}

async function loadTable(){
  const r = await fetch('/api/orders/open-table?per_page=10000&'+getFilters()).then(r=>r.json());
  _tableData = r.rows || [];
  _sortCol = 'days_late'; _sortDir = 'desc';
  _currentPage = 1;
  applyOrdersSortAndFilter();
}

function toggleAdvFilters(){const b=document.getElementById('advFiltersBar'),btn=document.getElementById('btnAdvFilters');if(b&&b.style.display==='none'){b.style.display='flex';btn.style.borderColor='rgba(59,130,246,.45)';btn.style.color='#60a5fa';}else if(b){b.style.display='none';btn.style.borderColor='rgba(100,116,139,.35)';btn.style.color='#94a3b8';}}
function loadAll(){ return Promise.allSettled([loadKPIs(), loadPlanned(), loadOverdue(), loadBuckets(), loadTable()]); }

// ─── Column Resize ───
(function(){
  const tbl = document.getElementById('ordersTbl');
  if(!tbl) return;
  const cols = tbl.querySelectorAll('colgroup col');
  tbl.querySelectorAll('.col-resizer').forEach((handle, idx) => {
    let startX, startW;
    handle.addEventListener('mousedown', e => {
      e.stopPropagation(); e.preventDefault();
      handle.classList.add('active');
      startX = e.pageX;
      startW = cols[idx].offsetWidth || handle.parentElement.offsetWidth;
      const onMove = ev => { const diff = ev.pageX - startX; cols[idx].style.width = Math.max(40, startW + diff) + 'px'; };
      const onUp = () => { handle.classList.remove('active'); document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  });
})();
function resetFilters(){
  _filtersReady=false;
  Object.values(filters).forEach(ms=>{
    if (ms.key === 'is_fornecedor_nao_negociavel' || (ms.container && ms.container.id === 'fFornNegociavel')) {
      ms.selected = new Set(['NEGOCIAVEL']);
    } else {
      ms.selected = new Set(ms.options);
    }
    ms.renderOptions();
    ms.updateLabel();
  });
  // Default: empresa = BB, BQ
  if(filters.fEmpresa){filters.fEmpresa.selected=new Set(['BB','BQ']);filters.fEmpresa.renderOptions();filters.fEmpresa.updateLabel();}
  // Default: current year
  const cy=String(new Date().getFullYear());if(filters.fAno&&filters.fAno.options.includes(cy)){filters.fAno.selected=new Set([cy]);filters.fAno.renderOptions();filters.fAno.updateLabel();}
  // Default: all months
  if(filters.fMes){filters.fMes.selected=new Set(filters.fMes.options);filters.fMes.renderOptions();filters.fMes.updateLabel();}
  if(filters.fFornNegociavel){filters.fFornNegociavel.selected=new Set(['NEGOCIAVEL']);filters.fFornNegociavel.renderOptions();filters.fFornNegociavel.updateLabel();}
  _filtersReady=true;
  loadAll();
}
function toggleTheme(){const h=document.documentElement;const n=h.getAttribute('data-theme')==='dark'?'light':'dark';h.setAttribute('data-theme',n);localStorage.setItem('theme',n);loadAll();}
const s=localStorage.getItem('theme');if(s)document.documentElement.setAttribute('data-theme',s);

async function initFilters(){
  // Fetch initial filter options from ordens_compra table exclusively (cached in sessionStorage)
  const data=await (window.fetchCachedFilterData ? window.fetchCachedFilterData('/api/filters/cascading-ordens') : fetch('/api/filters/cascading-ordens').then(r=>r.json()));
  filters.fEmpresa=new MultiSelect(document.getElementById('fEmpresa'),data.empresas||['BB','BQ']);
  filters.fEmpresa.selected=new Set(['BB','BQ']); filters.fEmpresa.renderOptions(); filters.fEmpresa.updateLabel();
  filters.fAno=new MultiSelect(document.getElementById('fAno'),(data.anos||[]).map(String));
  filters.fMes=new MultiSelect(document.getElementById('fMes'),(data.meses||[]).map(m=>String(m)));
  filters.fGrupo=new MultiSelect(document.getElementById('fGrupo'),data.grupos||[]);
  filters.fFornecedor=new MultiSelect(document.getElementById('fFornecedor'),data.fornecedores||[]);
  filters.fComprador=new MultiSelect(document.getElementById('fComprador'),data.compradores||[]);
  // Pre-select current year + month
  const cy=String(new Date().getFullYear()); if(filters.fAno.options.includes(cy)){filters.fAno.selected=new Set([cy]);filters.fAno.renderOptions();filters.fAno.updateLabel();}
  // Pre-select all months
  if(filters.fMes.options.length){filters.fMes.selected=new Set(filters.fMes.options);filters.fMes.renderOptions();filters.fMes.updateLabel();}
  // Advanced filters from ordens_compra
  if(document.getElementById('fMacroCategoria')) filters.fMacroCategoria=new MultiSelect(document.getElementById('fMacroCategoria'),data.macro_categorias||[]);
  if(document.getElementById('fUnidade')) filters.fUnidade=new MultiSelect(document.getElementById('fUnidade'),data.unidades||[]);
  if(document.getElementById('fCategoria')) filters.fCategoria=new MultiSelect(document.getElementById('fCategoria'),data.categorias||[]);
  if(document.getElementById('fTipoOC')) filters.fTipoOC=new MultiSelect(document.getElementById('fTipoOC'),data.tipo_oc||[]);
  if(document.getElementById('fStatusFech')) filters.fStatusFech=new MultiSelect(document.getElementById('fStatusFech'),data.status||[]);
  // Static supplier classification filters
  if(document.getElementById('fFornEspecial')) filters.fFornEspecial=new MultiSelect(document.getElementById('fFornEspecial'),['ESPECIAL','NÃO ESPECIAL']);
  if(document.getElementById('fFornNegociavel')) filters.fFornNegociavel=new MultiSelect(document.getElementById('fFornNegociavel'),['NEGOCIAVEL','NÃO NEGOCIAVEL']);
  if (typeof FilterStateStore !== 'undefined') FilterStateStore.restore();
  _filtersReady=true;
  aplicarFiltros(loadAll);
}
window.addEventListener('themeChanged', () => {
  if (typeof loadPlanned === 'function') loadPlanned();
});
initFilters();
