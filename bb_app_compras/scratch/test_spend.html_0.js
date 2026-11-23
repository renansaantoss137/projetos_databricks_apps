
let spendType = 'liquido';
function setSpendType(t) {
  spendType = t;
  document.getElementById('btnLiq').classList.toggle('active', t==='liquido');
  document.getElementById('btnBruto').classList.toggle('active', t==='bruto');
  loadAll();
}

function fmt(v,t='currency'){if(v==null||isNaN(v))return'--';const a=Math.abs(v);if(t==='currency'){if(a>=1e9)return'R$ '+(v/1e9).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})+'Bi';if(a>=1e6)return'R$ '+(v/1e6).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})+'M';if(a>=1e3)return'R$ '+(v/1e3).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})+'mil';return'R$ '+v.toLocaleString('pt-BR',{maximumFractionDigits:0});}if(t==='pct')return v.toFixed(1)+'%';return v.toLocaleString('pt-BR');}



// MultiSelect and filters provided by filters-shared.js
_cascadeEndpoint = '/api/filters/cascading';
// i18n: override fmt with localized version
if (typeof fmtI18n !== 'undefined') fmt = fmtI18n;
document.addEventListener('langChange', function() { if (typeof loadAll === 'function') loadAll(); });

// ═══ Cross-Filter State ═══
let _crossFilter = null; // {type:'fornecedor', value:'X', source:'suppliers'}

function setCrossFilter(type, value, source) {
  if (_crossFilter && _crossFilter.type === type && _crossFilter.value === value) {
    clearCrossFilter(); return;
  }
  _crossFilter = { type, value, source };
  const labels = {fornecedor:'Fornecedor', item_cross:'Item', unidade:'Planta', macro_categoria_cross:'Categoria', categoria_cross:'Sub-categoria', tipo_vendor_cross:'Tipo Vendor'};
  document.getElementById('cfLabel').textContent = labels[type] || type;
  document.getElementById('cfValue').textContent = value;
  document.getElementById('crossFilterBar').classList.add('active');
  loadAllCrossFiltered();
}

function clearCrossFilter() {
  _crossFilter = null;
  document.getElementById('crossFilterBar').classList.remove('active');
  loadAll();
}

function getFiltersWithCross() {
  let base = getFilters();
  if (_crossFilter) {
    const p = new URLSearchParams(base);
    p.append(_crossFilter.type, _crossFilter.value);
    return p.toString();
  }
  return base;
}

function loadAllCrossFiltered() {
  const src = _crossFilter ? _crossFilter.source : null;
  if (src !== 'items') loadItems();
  if (src !== 'suppliers') loadSuppliers();
  if (src !== 'plants') loadPlants();
  if (src !== 'categories') loadCatOrTipo();
  loadABC();
  loadSpendByEmpresa();
  // Re-render source chart to show selection state
  if (src === 'items') loadItems();
  if (src === 'suppliers') loadSuppliers();
  if (src === 'plants') loadPlants();
  if (src === 'categories') loadCatOrTipo();
}

function renderBars(containerId, data, labelKey, valueKey, maxVal, highlightCount=999, overrideTotal=null, crossType=null, crossSource=null) {
  const sumData = data.reduce((s,d)=>s+(d[valueKey]||0),0);
  const total = overrideTotal || sumData;
  const max = maxVal || Math.max(...data.map(d=>d[valueKey]||0));
  const isSourceChart = _crossFilter && _crossFilter.source === crossSource;
  document.getElementById(containerId).innerHTML = data.slice(0,8).map((d,i) => {
    const val = d[valueKey]||0;
    const pct = total ? ((val/total)*100).toFixed(0) : 0;
    const barW = max ? Math.max(2, (val/max)*100) : 0;
    const label = (d[labelKey]||'Outros').substring(0,20);
    const fullLabel = d[labelKey]||'Outros';
    const muted = i >= highlightCount;
    const barBg = muted ? 'background:#64748b !important' : 'background:linear-gradient(90deg,#1d4ed8,#3b82f6) !important';
    const lblStyle = muted ? 'color:#64748b' : '';
    const valStyle = muted ? 'color:#64748b' : '';
    // Cross-filter highlight
    const isSelected = isSourceChart && _crossFilter.value === fullLabel;
    const rowClass = isSelected ? 'hbar-row cf-selected' : 'hbar-row';
    const clickAttr = crossType ? `onclick="setCrossFilter('${crossType}','${fullLabel.replace(/'/g,"\\'").replace(/"/g,'&quot;')}','${crossSource}')"` : '';
    return `<div class="${rowClass}" ${clickAttr} title="${fullLabel}"><span class="hbar-label" style="${lblStyle}">${label}</span><div class="hbar-track"><div class="hbar-fill" style="width:${barW}%;${barBg}"></div></div><span class="hbar-val" style="${valStyle}">${fmt(val)}</span><span class="hbar-pct" style="${valStyle}">${pct}%</span></div>`;
  }).join('');
  return { total: sumData, topPct: sumData ? ((data.slice(0,6).reduce((s,d)=>s+(d[valueKey]||0),0)/sumData)*100).toFixed(0) : 0 };
}

async function loadItems(){
  const r = await fetch(`/api/spend/by-item?${getFiltersWithCross()}`).then(res=>res.json());
  const data = r.rows || (Array.isArray(r) ? r : []);
  const total = r.total || data.reduce((s,d)=>s+(d.net_spend||0),0);
  const topSum = data.slice(0,3).reduce((s,d)=>s+(d.net_spend||0),0);
  const topPct = total ? (topSum/total*100).toFixed(0) : 0;
  renderBars('barItems', data, 'item', 'net_spend', null, 3, total, 'item_cross', 'items');
  document.getElementById('ttlItems').textContent = typeof tt !== 'undefined' ? tt('Os {n} maiores itens representam {pct}% do Spend', {n: 3, pct: topPct}) : `Os 3 maiores itens representam ${topPct}% do Spend`;
}

async function loadSuppliers(){
  const r = await fetch(`/api/spend/by-supplier?${getFiltersWithCross()}`).then(r=>r.json());
  const data = r.rows||[];
  const total = r.total||1;

  // Find the "knee": where the gap between consecutive values is significant
  let highlightN = 3; // default
  if (data.length >= 4) {
    for (let i = 1; i < Math.min(data.length, 6); i++) {
      const curr = data[i].net_spend || 0;
      const prev = data[i-1].net_spend || 0;
      if (curr < prev * 0.4) { highlightN = i; break; } // big drop = natural cutoff
    }
  }
  highlightN = Math.max(2, Math.min(highlightN, 5));

  const topNSum = data.slice(0, highlightN).reduce((s,d) => s + (d.net_spend||0), 0);
  const topNPct = total ? (topNSum / total * 100).toFixed(0) : 0;

  renderBars('barSuppliers', data, 'fornecedor', 'net_spend', null, highlightN, total, 'fornecedor', 'suppliers');
  document.getElementById('ttlSuppliers').textContent = typeof tt !== 'undefined' ? tt('Os {n} maiores fornecedores representam {pct}% do Spend', {n: highlightN, pct: topNPct}) : `Os ${highlightN} maiores fornecedores representam ${topNPct}% do Spend`;
}

async function loadABC(){
  const data = await fetch(`/api/spend/abc?dimension=item&${getFiltersWithCross()}`).then(r=>r.json());
  const total = data.reduce((s,d)=>s+(d.class_spend||0),0);
  const body = document.getElementById('abcBody');
  body.innerHTML = data.map(d => {
    const pct = total ? ((d.class_spend/total)*100).toFixed(0) : 0;
    const cls = d.abc_class==='A'?'abc-a':d.abc_class==='B'?'abc-b':'abc-c';
    return `<tr class="abc-row-clickable" onclick="drillABC('${d.abc_class}')"><td><span class="abc-badge ${cls}">${d.abc_class}</span></td><td>${fmt(d.class_spend)}</td><td>${pct}%</td></tr>`;
  }).join('') + `<tr class="abc-total"><td>${t('Total')}</td><td>${fmt(total)}</td><td>100%</td></tr>`;
  // Title is now fixed: "Análise ABC do Spend Líquido"
}

let _abcDimension = 'item';
let _abcCurrentClass = 'A';

function setAbcDim(dim) {
  _abcDimension = dim;
  document.getElementById('abcBtnItem').classList.toggle('active', dim==='item');
  document.getElementById('abcBtnCat').classList.toggle('active', dim==='category');
  document.getElementById('abcBtnSup').classList.toggle('active', dim==='supplier');
  drillABC(_abcCurrentClass);
}

async function drillABC(cls) {
  _abcCurrentClass = cls;
  const modal = document.getElementById('abcModal');
  const classLabels = {A:t('Classe A (80% do Spend)'), B:t('Classe B (80-95%)'), C:t('Classe C (cauda, 95-100%)')};
  const dimLabels = {item:t('Itens'), category:t('Categorias'), supplier:t('Fornecedores')};
  document.getElementById('abcModalTitle').textContent = `${dimLabels[_abcDimension]||'Itens'} ${classLabels[cls] || cls}`;
  document.getElementById('abcModalBody').innerHTML = '<div style="text-align:center;padding:2rem;color:var(--fr-txt-soft)">Carregando...</div>';
  modal.classList.add('active');

  // When cross-filter is active + dimension is category/supplier, skip ABC class filter (shows all)
  const filterStr = getFiltersWithCross();
  const skipClass = _crossFilter && _abcDimension !== 'item';
  const classParam = skipClass ? '' : `&abc_class=${cls}`;
  const data = await fetch(`/api/spend/abc-detail?dimension=${_abcDimension}${classParam}&${filterStr}`).then(r=>r.json());
  _abcExportData = data;
  _abcExportClass = cls;
  if (!data.length) {
    document.getElementById('abcModalBody').innerHTML = '<div style="text-align:center;padding:2rem;color:var(--fr-txt-soft)">Nenhum registro encontrado</div>';
    return;
  }
  const headerMap = {
    item: `<th>#</th><th>${t('Código')}</th><th>${t('Item')}</th><th>Spend</th><th>% Total</th><th>${t('% Acum')}</th>`,
    category: `<th>#</th><th>${t('Categoria')}</th><th>Spend</th><th>% Total</th><th>${t('% Acum')}</th>`,
    supplier: `<th>#</th><th>${t('Fornecedor')}</th><th>Spend</th><th>% Total</th><th>${t('% Acum')}</th>`
  };
  let html = `<table class="abc-detail-table"><thead><tr>${headerMap[_abcDimension]}</tr></thead><tbody>`;
  data.forEach((d, i) => {
    const crossType = _abcDimension === 'item' ? 'item_cross' : _abcDimension === 'category' ? 'categoria_cross' : 'fornecedor';
    const crossSource = _abcDimension === 'item' ? 'items' : _abcDimension === 'category' ? 'categories' : 'suppliers';
    const clickAttr = `onclick="setCrossFilter('${crossType}','${(d.item||'').replace(/'/g,"\\'").replace(/"/g,'&quot;')}','${crossSource}');closeAbcModal();"`;
    if (_abcDimension === 'item') {
      html += `<tr class="abc-row-clickable" ${clickAttr}><td style="color:var(--fr-txt-soft)">${i+1}</td><td style="font-size:.65rem;color:var(--fr-txt-soft);white-space:nowrap">${d.codigo_item||'--'}</td><td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${d.item}">${d.item}</td><td>${fmt(d.net_spend)}</td><td>${d.pct!=null?d.pct.toFixed(1)+'%':'--'}</td><td style="color:var(--fr-txt-soft)">${d.cum_pct!=null?d.cum_pct.toFixed(1)+'%':'--'}</td></tr>`;
    } else {
      html += `<tr class="abc-row-clickable" ${clickAttr}><td style="color:var(--fr-txt-soft)">${i+1}</td><td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${d.item}">${d.item}</td><td>${fmt(d.net_spend)}</td><td>${d.pct!=null?d.pct.toFixed(1)+'%':'--'}</td><td style="color:var(--fr-txt-soft)">${d.cum_pct!=null?d.cum_pct.toFixed(1)+'%':'--'}</td></tr>`;
    }
  });
  html += '</tbody></table>';
  document.getElementById('abcModalBody').innerHTML = html;
}

let _abcExportData = [];
let _abcExportClass = '';

function exportAbcXlsx() {
  if (!_abcExportData.length) return;
  const dimNames = {item:'Item', category:'Categoria', supplier:'Fornecedor'};
  const dimName = dimNames[_abcDimension] || 'Item';
  let rows;
  if (_abcDimension === 'item') {
    rows = _abcExportData.map((d, i) => ({
      '#': i + 1,
      'C\u00f3digo': d.codigo_item || '--',
      'Item': d.item,
      'Spend (R$)': d.net_spend ? Math.round(d.net_spend * 100) / 100 : 0,
      '% Total': d.pct != null ? Math.round(d.pct * 10) / 10 : null,
      '% Acumulado': d.cum_pct != null ? Math.round(d.cum_pct * 10) / 10 : null
    }));
  } else {
    rows = _abcExportData.map((d, i) => ({
      '#': i + 1,
      [dimName]: d.item,
      'Spend (R$)': d.net_spend ? Math.round(d.net_spend * 100) / 100 : 0,
      '% Total': d.pct != null ? Math.round(d.pct * 10) / 10 : null,
      '% Acumulado': d.cum_pct != null ? Math.round(d.cum_pct * 10) / 10 : null
    }));
  }
  const ws = XLSX.utils.json_to_sheet(rows);
  ws['!cols'] = _abcDimension === 'item' ? [{wch:5},{wch:15},{wch:50},{wch:15},{wch:10},{wch:12}] : [{wch:5},{wch:50},{wch:15},{wch:10},{wch:12}];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, `${dimName} Classe ${_abcExportClass}`);
  XLSX.writeFile(wb, `ABC_${dimName}_Classe_${_abcExportClass}_${new Date().toISOString().slice(0,10)}.xlsx`);
}

function closeAbcModal() { document.getElementById('abcModal').classList.remove('active'); }
document.getElementById('abcModal').addEventListener('click', e => { if(e.target===e.currentTarget) closeAbcModal(); });

async function loadPlants(){
  const r = await fetch(`/api/spend/by-plant?${getFiltersWithCross()}`).then(res=>res.json());
  const data = r.rows || (Array.isArray(r) ? r : []);
  const total = r.total || data.reduce((s,d)=>s+(d.net_spend||0),0);

  // Knee detection: find natural cutoff (pre-attentive)
  let highlightN = 3;
  if (data.length >= 4) {
    for (let i = 1; i < Math.min(data.length, 6); i++) {
      const curr = data[i].net_spend || 0;
      const prev = data[i-1].net_spend || 0;
      if (curr < prev * 0.4) { highlightN = i; break; }
    }
  }
  highlightN = Math.max(2, Math.min(highlightN, 5));

  const topNSum = data.slice(0, highlightN).reduce((s,d) => s + (d.net_spend||0), 0);
  const topNPct = total ? (topNSum / total * 100).toFixed(0) : 0;

  renderBars('barPlants', data, 'unidade', 'net_spend', null, highlightN, total, 'unidade', 'plants');
  document.getElementById('ttlPlants').textContent = tt('As {n} maiores plantas representam {pct}% do Spend', {n: highlightN, pct: topNPct});
}

let _catTipoMode = 'macro';

function setCatTipo(mode) {
  _catTipoMode = mode;
  document.getElementById('btnMacro').classList.toggle('active', mode==='macro');
  document.getElementById('btnCat').classList.toggle('active', mode==='categoria');
  document.getElementById('btnTipo').classList.toggle('active', mode==='tipo');
  loadCatOrTipo();
}

function loadCatOrTipo() {
  if (_catTipoMode === 'macro') {
    loadMacroCategories();
  } else if (_catTipoMode === 'tipo') {
    loadTipoVendor();
  } else {
    loadCategories();
  }
}

async function loadMacroCategories(){
  const r = await fetch(`/api/spend/by-macro-category?${getFiltersWithCross()}`).then(res=>res.json());
  const data = Array.isArray(r) ? r : (r.rows || []);
  const total = r.total || data.reduce((s,d)=>s+(d.net_spend||0),0);

  let highlightN = 2;
  if (data.length >= 4) {
    for (let i = 1; i < Math.min(data.length, 6); i++) {
      if ((data[i].net_spend||0) < (data[i-1].net_spend||0) * 0.4) { highlightN = i; break; }
    }
  }
  highlightN = Math.max(1, Math.min(highlightN, data.length || 1));

  const topNSum = data.slice(0, highlightN).reduce((s,d) => s + (d.net_spend||0), 0);
  const topNPct = total ? (topNSum / total * 100).toFixed(0) : 0;

  renderBars('barCategories', data, 'macro_categoria', 'net_spend', null, highlightN, total, 'macro_categoria_cross', 'categories');
  document.getElementById('ttlCategories').textContent = tt('As {n} maiores categorias representam {pct}% do Spend', {n: highlightN, pct: topNPct});
  document.getElementById('subtCategories').textContent = t('Quais categorias concentram o gasto?');
}

async function loadCategories(){
  const r = await fetch(`/api/spend/by-category?${getFiltersWithCross()}`).then(res=>res.json());
  const data = Array.isArray(r) ? r : (r.rows || []);
  const total = r.total || data.reduce((s,d)=>s+(d.net_spend||0),0);

  let highlightN = 3;
  if (data.length >= 4) {
    for (let i = 1; i < Math.min(data.length, 6); i++) {
      if ((data[i].net_spend||0) < (data[i-1].net_spend||0) * 0.4) { highlightN = i; break; }
    }
  }
  highlightN = Math.max(2, Math.min(highlightN, 5));

  const topNSum = data.slice(0, highlightN).reduce((s,d) => s + (d.net_spend||0), 0);
  const topNPct = total ? (topNSum / total * 100).toFixed(0) : 0;

  renderBars('barCategories', data, 'categoria', 'net_spend', null, highlightN, total, 'categoria_cross', 'categories');
  document.getElementById('ttlCategories').textContent = tt('As {n} maiores sub-categorias representam {pct}% do Spend', {n: highlightN, pct: topNPct});
  document.getElementById('subtCategories').textContent = t('Quais sub-categorias concentram o gasto?');
}

async function loadTipoVendor(){
  const r = await fetch(`/api/spend/by-tipo-vendor?${getFiltersWithCross()}`).then(res=>res.json());
  const data = Array.isArray(r) ? r : (r.rows || []);
  const total = data.reduce((s,d)=>s+(d.net_spend||0),0);

  let highlightN = 3;
  if (data.length >= 4) {
    for (let i = 1; i < Math.min(data.length, 6); i++) {
      if ((data[i].net_spend||0) < (data[i-1].net_spend||0) * 0.4) { highlightN = i; break; }
    }
  }
  highlightN = Math.max(2, Math.min(highlightN, 5));

  const topNSum = data.slice(0, highlightN).reduce((s,d) => s + (d.net_spend||0), 0);
  const topNPct = total ? (topNSum / total * 100).toFixed(0) : 0;

  renderBars('barCategories', data, 'tipo_vendor', 'net_spend', null, highlightN, total, 'tipo_vendor_cross', 'categories');
  document.getElementById('ttlCategories').textContent = tt('Os {n} maiores tipos representam {pct}% do Spend', {n: highlightN, pct: topNPct});
  document.getElementById('subtCategories').textContent = t('Spend l\u00edquido por tipo de fornecedor');
}

async function loadSpendByEmpresa(){
  const data = await fetch(`/api/spend/by-empresa?${getFiltersWithCross()}`).then(res=>res.json());
  const container = document.getElementById('empresaChart');
  if (!data || !data.length) { container.innerHTML = '<div style="text-align:center;color:var(--fr-txt-soft);font-size:.8rem">Sem dados</div>'; return; }

  const rows = data.map(row => { const n = {}; Object.keys(row).forEach(k => n[k.toUpperCase()] = row[k]); return n; });
  const total = rows.reduce((s,row) => s + (row.NET_SPEND || 0), 0);
  const colors = { 'BB': '#3b82f6', 'BQ': '#f59e0b' };
  const gradients = { 'BB': 'linear-gradient(90deg,#1d4ed8,#3b82f6)', 'BQ': 'linear-gradient(90deg,#d97706,#f59e0b)' };
  const maxVal = Math.max(...rows.map(row => row.NET_SPEND || 0));

  container.innerHTML = rows.map(row => {
    const val = row.NET_SPEND || 0;
    const pct = total > 0 ? (val / total * 100).toFixed(1) : '0.0';
    const barW = maxVal > 0 ? Math.max(3, val / maxVal * 100) : 0;
    const color = colors[row.EMPRESA] || '#6366f1';
    return `
      <div style="display:flex;flex-direction:column;gap:4px">
        <div style="display:flex;justify-content:space-between;align-items:baseline">
          <span style="font-size:.85rem;font-weight:800;color:${color}">${row.EMPRESA}</span>
          <span style="font-size:.7rem;font-weight:700;color:var(--fr-txt)">${fmt(val)} <span style="color:var(--fr-txt-soft);font-weight:600">(${pct}%)</span></span>
        </div>
        <div style="height:28px;background:rgba(100,116,139,.1);border-radius:6px;overflow:hidden">
          <div style="height:100%;width:${barW}%;background:${gradients[row.EMPRESA] || color};border-radius:6px;transition:width .5s"></div>
        </div>
      </div>`;
  }).join('');

  const bb = rows.find(row=>row.EMPRESA==='BB');
  document.getElementById('ttlEmpresa').textContent = bb ? tt('{emp} representa {pct}% do Spend L\u00edquido', {emp: 'BB', pct: (bb.NET_SPEND/total*100).toFixed(0)}) : t('Spend L\u00edquido por Empresa');
}

function toggleAdvFilters(){const b=document.getElementById('advFiltersBar'),btn=document.getElementById('btnAdvFilters');if(b.style.display==='none'){b.style.display='flex';btn.style.borderColor='rgba(59,130,246,.45)';btn.style.color='#60a5fa';}else{b.style.display='none';btn.style.borderColor='rgba(100,116,139,.35)';btn.style.color='#94a3b8';}}
function resetFilters(){_crossFilter=null;document.getElementById('crossFilterBar').classList.remove('active');Object.values(filters).forEach(ms=>{if(ms.key==='is_fornecedor_nao_negociavel'||(ms.container&&ms.container.id==='fFornNegociavel')){ms.selected=new Set(['NEGOCIAVEL']);}else{ms.selected=new Set(ms.options);}ms.renderOptions();ms.updateLabel();});const cy=String(new Date().getFullYear()),cm=String(new Date().getMonth()+1);if(filters.fEmpresa){filters.fEmpresa.selected=new Set(['BB','BQ']);filters.fEmpresa.renderOptions();filters.fEmpresa.updateLabel();}if(filters.fAno&&filters.fAno.options.includes(cy)){filters.fAno.selected=new Set([cy]);filters.fAno.renderOptions();filters.fAno.updateLabel();}if(filters.fMes&&filters.fMes.options.includes(cm)){filters.fMes.selected=new Set([cm]);filters.fMes.renderOptions();filters.fMes.updateLabel();}if(filters.fTipoNF){filters.fTipoNF.selected=new Set(['com_oc','sem_oc']);filters.fTipoNF.renderOptions();filters.fTipoNF.updateLabel();}if(filters.fFornNegociavel){filters.fFornNegociavel.selected=new Set(['NEGOCIAVEL']);filters.fFornNegociavel.renderOptions();filters.fFornNegociavel.updateLabel();}loadAll();}
function loadAll(){ return Promise.allSettled([loadItems(), loadSuppliers(), loadABC(), loadPlants(), loadCatOrTipo(), loadSpendByEmpresa()]); }
function toggleTheme(){const h=document.documentElement;const n=h.getAttribute('data-theme')==='dark'?'light':'dark';h.setAttribute('data-theme',n);localStorage.setItem('theme',n);loadAll();}
const s=localStorage.getItem('theme');if(s)document.documentElement.setAttribute('data-theme',s);

async function initFilters(){
  const data=await (window.fetchCachedFilterData ? window.fetchCachedFilterData('/api/filters/notas') : fetch('/api/filters/notas').then(r=>r.json()));
  filters.fEmpresa=new MultiSelect(document.getElementById('fEmpresa'),data.empresas||['BB','BQ']);
  filters.fEmpresa.selected=new Set(['BB','BQ']); filters.fEmpresa.renderOptions(); filters.fEmpresa.updateLabel();
  filters.fAno=new MultiSelect(document.getElementById('fAno'),data.anos||[]);
  const cy=String(new Date().getFullYear()); if(filters.fAno.options.includes(cy)){filters.fAno.selected=new Set([cy]);filters.fAno.renderOptions();filters.fAno.updateLabel();}
  filters.fMes=new MultiSelect(document.getElementById('fMes'),(data.meses||[]).map(m=>String(m)));
  filters.fGrupo=new MultiSelect(document.getElementById('fGrupo'),data.grupos||[]);
  filters.fFornecedor=new MultiSelect(document.getElementById('fFornecedor'),data.fornecedores||[]);
  filters.fTipoNF=new MultiSelect(document.getElementById('fTipoNF'),['com_oc','sem_oc']);
  filters.fTipoNF.selected=new Set(['com_oc','sem_oc']); filters.fTipoNF.renderOptions(); filters.fTipoNF.updateLabel();
  // Pre-select current month
  const cm=String(new Date().getMonth()+1);if(filters.fMes.options.includes(cm)){filters.fMes.selected=new Set([cm]);filters.fMes.renderOptions();filters.fMes.updateLabel();}
  if(document.getElementById('fFornNegociavel')) {
    filters.fFornNegociavel = new MultiSelect(document.getElementById('fFornNegociavel'), ['NEGOCIAVEL', 'NÃO NEGOCIAVEL']);
  }
  if (typeof FilterStateStore !== 'undefined') FilterStateStore.restore();
  loadAll();
  window._filtersReady=true;
  // Advanced filters (non-blocking, cached)
  (window.fetchCachedFilterData ? window.fetchCachedFilterData('/api/filters/advanced') : fetch('/api/filters/advanced').then(r=>r.json())).then(advData=>{
    const safeMS = (id, opts) => { const el = document.getElementById(id); if (el) return new MultiSelect(el, opts); return null; };
    filters.fMacroCategoria = safeMS('fMacroCategoria', advData.macro_categoria||[]);
    filters.fDia = safeMS('fDia', (advData.dias||[]).map(d=>String(d)));
    filters.fDescItem = safeMS('fDescItem', advData.descricao_item||[]);
    filters.fCentralizado = safeMS('fCentralizado', advData.centralizado||[]);
    filters.fUnidade = safeMS('fUnidade', advData.unidade||[]);
    filters.fStatusPgto = safeMS('fStatusPgto', advData.status_pagamento||[]);
    filters.fTipoNFAdv = safeMS('fTipoNFAdv', advData.tipo_nf||[]);
    filters.fTipoLinha = safeMS('fTipoLinha', advData.tipo_linha||[]);
    filters.fFornEspecial = safeMS('fFornEspecial', ['ESPECIAL', 'NÃO ESPECIAL']);
    if (!filters.fFornNegociavel) filters.fFornNegociavel = safeMS('fFornNegociavel', ['NEGOCIAVEL', 'NÃO NEGOCIAVEL']);
    if (typeof FilterStateStore !== 'undefined') FilterStateStore.restore();
  }).catch(()=>{});
}
initFilters();
