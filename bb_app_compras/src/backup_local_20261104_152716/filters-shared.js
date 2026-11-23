/**
 * PORTAL COMPRAS — Shared Cascading Filters Module
 * Implements Power BI-style cross-filtering for all modules.
 * 
 * Usage:
 *   Include this script BEFORE module-specific scripts.
 *   Call initCascadingFilters(config) from each module's init.
 */

// ══════════════════════════════════════════════════════════════════════════════
// MultiSelect Component
// ══════════════════════════════════════════════════════════════════════════════
class MultiSelect {
  constructor(el, opts = []) {
    this.container = el;
    this.key = el.dataset.key;
    this.selected = new Set();
    this.options = [];
    this.isOpen = false;
    this.render();
    if (opts.length) this.setOptions(opts);
  }
  render() {
    this.container.innerHTML = `
      <div class="ms-trigger" tabindex="0"><span class="ms-text">Todos</span><span class="ms-arrow">▼</span></div>
      <div class="ms-panel">
        <input type="text" class="ms-search" placeholder="Pesquisar...">
        <div class="ms-actions"><a class="ms-sel-all">Selecionar tudo</a> <a class="ms-desel-all">Limpar</a></div>
        <div class="ms-options"></div>
      </div>`;
    this.trigger = this.container.querySelector('.ms-trigger');
    this.panel = this.container.querySelector('.ms-panel');
    this.search = this.container.querySelector('.ms-search');
    this.optionsEl = this.container.querySelector('.ms-options');
    this.trigger.addEventListener('click', () => this.toggle());
    this.search.addEventListener('input', () => this.filter());
    this.container.querySelector('.ms-sel-all').addEventListener('click', () => this.selectAllVisible());
    this.container.querySelector('.ms-desel-all').addEventListener('click', () => this.deselectAllVisible());
    document.addEventListener('click', e => { if (!this.container.contains(e.target)) this.close(); });
  }
  setOptions(opts) {
    this.options = opts.map(String);
    if (this.key === 'is_fornecedor_nao_negociavel' || (this.container && this.container.id === 'fFornNegociavel')) {
      this.selected = new Set(['NEGOCIAVEL']);
    } else if (this.key === 'is_fornecedor_sem_oc' || (this.container && this.container.id === 'fFornSemOC')) {
      this.selected = new Set(['COM ATUAÇÃO']);
    } else {
      this.selected = new Set(this.options);
    }
    this.renderOptions();
    this.updateLabel();
  }
  /** Update options while preserving current selections (cascading update). */
  updateOptions(newOpts) {
    const newSet = new Set(newOpts.map(String));
    // Keep only selections that still exist in new options
    const preserved = new Set([...this.selected].filter(v => newSet.has(v)));
    this.options = [...newSet];
    // If nothing is preserved, select all (or default to NEGOCIAVEL for fFornNegociavel)
    if (preserved.size > 0) {
      this.selected = preserved;
    } else if (this.key === 'is_fornecedor_nao_negociavel' || (this.container && this.container.id === 'fFornNegociavel')) {
      this.selected = this.options.includes('NEGOCIAVEL') ? new Set(['NEGOCIAVEL']) : new Set(this.options);
    } else if (this.key === 'is_fornecedor_sem_oc' || (this.container && this.container.id === 'fFornSemOC')) {
      this.selected = this.options.includes('COM ATUAÇÃO') ? new Set(['COM ATUAÇÃO']) : new Set(this.options);
    } else {
      this.selected = new Set(this.options);
    }
    this.renderOptions();
    this.updateLabel();
  }
  renderOptions() {
    this.optionsEl.innerHTML = this.options.map(o => `
      <div class="ms-option" data-val="${o}">
        <input type="checkbox" ${this.selected.has(o) ? 'checked' : ''}>
        <span>${o}</span>
      </div>`).join('');
    this.optionsEl.querySelectorAll('.ms-option').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.tagName === 'INPUT') { this.toggleOption(el.dataset.val); return; }
        const cb = el.querySelector('input');
        cb.checked = !cb.checked;
        this.toggleOption(el.dataset.val);
      });
    });
  }
  toggleOption(val) {
    if (this.selected.has(val)) this.selected.delete(val); else this.selected.add(val);
    this.updateLabel();
    if (typeof FilterStateStore !== 'undefined') FilterStateStore.save();
  }
  selectAllVisible() {
    this.optionsEl.querySelectorAll('.ms-option:not(.hidden)').forEach(el => {
      this.selected.add(el.dataset.val); el.querySelector('input').checked = true;
    });
    this.updateLabel();
    if (typeof FilterStateStore !== 'undefined') FilterStateStore.save();
  }
  deselectAllVisible() {
    this.optionsEl.querySelectorAll('.ms-option:not(.hidden)').forEach(el => {
      this.selected.delete(el.dataset.val); el.querySelector('input').checked = false;
    });
    this.updateLabel();
    if (typeof FilterStateStore !== 'undefined') FilterStateStore.save();
  }
  filter() {
    const q = this.search.value.toLowerCase();
    this.optionsEl.querySelectorAll('.ms-option').forEach(el => {
      el.classList.toggle('hidden', !el.dataset.val.toLowerCase().includes(q));
    });
  }
  toggle() { this.isOpen ? this.close() : this.open(); }
  open() { this.panel.classList.add('open'); this.isOpen = true; this.search.focus(); }
  close() { this.panel.classList.remove('open'); this.isOpen = false; this.search.value = ''; this.filter(); }
  updateLabel() {
    const t = this.options.length, s = this.selected.size;
    var _t = typeof window.t !== 'undefined' ? window.t : function(x){return x;};
    if (s === 0) this.trigger.querySelector('.ms-text').textContent = _t('Nenhum');
    else if (s === t) this.trigger.querySelector('.ms-text').textContent = _t('Todos');
    else if (s <= 2) this.trigger.querySelector('.ms-text').textContent = [...this.selected].join(', ');
    else { var _tFn = typeof window.t !== 'undefined' ? window.t : function(x){return x;}; this.trigger.querySelector('.ms-text').innerHTML = `${s} ${_tFn('selecionados')} <span class="ms-badge">${s}</span>`; }
  }
  getSelected() {
    if (this.selected.size === this.options.length) return [];
    return [...this.selected];
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Cascading Filter Logic
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Global filter registry and cascading configuration.
 * Each module calls initCascadingFilters() with its config.
 */
var filters = (typeof window !== 'undefined' && window.filters) ? window.filters : {};
if (typeof window !== 'undefined') window.filters = filters;
let _cascadeEndpoint = '/api/filters/cascading'; // default for notas_ri modules
let _cascadeDebounce = null;
let _filtersReady = false;

/**
 * Build query string from current filter selections.
 * Used by data-loading functions.
 */
function getFilters() {
  const p = new URLSearchParams();
  const target = (typeof filters !== 'undefined' && Object.keys(filters).length > 0) ? filters : ((typeof window !== 'undefined' && window.filters) ? window.filters : {});
  Object.entries(target).forEach(([id, ms]) => {
    if (!ms || typeof ms.getSelected !== 'function') return;
    if (ms.key === 'oc_type') { ms.getSelected().forEach(v => p.append('oc_type', v)); }
    else { ms.getSelected().forEach(v => p.append(ms.key, v)); }
  });
  return p.toString();
}

/**
 * Build query string excluding a specific key (for temporal charts).
 */
function getFiltersExcluding(...excludeKeys) {
  const p = new URLSearchParams();
  const target = (typeof filters !== 'undefined' && Object.keys(filters).length > 0) ? filters : ((typeof window !== 'undefined' && window.filters) ? window.filters : {});
  Object.entries(target).forEach(([id, ms]) => {
    if (!ms || typeof ms.getSelected !== 'function') return;
    if (excludeKeys.includes(ms.key)) return;
    if (ms.key === 'oc_type') { ms.getSelected().forEach(v => p.append('oc_type', v)); }
    else { ms.getSelected().forEach(v => p.append(ms.key, v)); }
  });
  return p.toString();
}

/**
 * Cache helper for initial filter payloads (stored in sessionStorage for instant tab switching).
 */
async function fetchCachedFilterData(url) {
  try {
    const key = 'pc_filter_cache_' + url.replace(/[^a-zA-Z0-9]/g, '_');
    const raw = sessionStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw);
      // Valid for 2 hours (7200000 ms) and must be a valid payload (not an error)
      if (parsed && parsed.ts && (Date.now() - parsed.ts < 7200000) && parsed.data && !parsed.data.error && (parsed.data.anos || parsed.data.empresas || parsed.data.compradores || parsed.data.macro_categoria)) {
        return parsed.data;
      }
    }
    const data = await fetch(url).then(r => r.json());
    if (data && typeof data === 'object' && Object.keys(data).length > 0 && !data.error && (data.anos || data.empresas || data.compradores || data.macro_categoria)) {
      try {
        sessionStorage.setItem(key, JSON.stringify({ ts: Date.now(), data }));
      } catch (e) {}
    }
    return data;
  } catch (err) {
    return fetch(url).then(r => r.json());
  }
}
window.fetchCachedFilterData = fetchCachedFilterData;

/**
 * Refresh cascading filter options (no-op since backend does not require cascading).
 */
async function refreshCascadingFilters() {
  // Cascading disabled: options are static per ETL cycle
  return;
}

/**
 * Debounced version of refreshCascadingFilters.
 */
function triggerCascadeRefresh() {
  // no-op
}

/**
 * Filter State Persistence (Cross-tab Synchronization)
 */
const FilterStateStore = {
  STORAGE_KEY: 'portal_compras_shared_filters',

  save(filtersMap) {
    try {
      // Keep selections for filters that do not exist on the current page.
      const state = JSON.parse(localStorage.getItem(this.STORAGE_KEY) || '{}');
      const target = filtersMap || (typeof filters !== 'undefined' ? filters : {});
      Object.entries(target).forEach(([id, ms]) => {
        if (!ms || !ms.options || !ms.options.length || !ms.selected) return;
        const key = ms.key || id;
        if (ms.selected.size === ms.options.length) {
          state[key] = '__ALL__';
        } else {
          state[key] = Array.from(ms.selected);
        }
      });
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      console.warn('FilterStateStore save error:', e);
    }
  },

  restore(filtersMap) {
    try {
      const raw = localStorage.getItem(this.STORAGE_KEY);
      if (!raw) return false;
      const state = JSON.parse(raw);
      if (!state || typeof state !== 'object') return false;

      const target = filtersMap || (typeof filters !== 'undefined' ? filters : {});
      let anyRestored = false;

      Object.entries(target).forEach(([id, ms]) => {
        if (!ms || !ms.options || !ms.options.length) return;
        const key = ms.key || id;
        const savedVal = state[key] !== undefined ? state[key] : state[id];
        if (savedVal === undefined) return;

        if (savedVal === '__ALL__') {
          ms.selected = new Set(ms.options.map(String));
          anyRestored = true;
        } else if (Array.isArray(savedVal)) {
          const optsSet = new Set(ms.options.map(String));
          const valid = savedVal.filter(v => optsSet.has(String(v)));
          if (valid.length > 0) {
            ms.selected = new Set(valid.map(String));
            anyRestored = true;
          }
        }
        if (typeof ms.renderOptions === 'function') ms.renderOptions();
        if (typeof ms.updateLabel === 'function') ms.updateLabel();
      });

      return anyRestored;
    } catch (e) {
      console.warn('FilterStateStore restore error:', e);
      return false;
    }
  },

  clear() {
    try {
      localStorage.removeItem(this.STORAGE_KEY);
    } catch (e) {}
  }
};
window.FilterStateStore = FilterStateStore;

/**
 * Clear all filters to default state.
 */
function clearAllFilters(loadFn) {
  _filtersReady = false;
  if (typeof FilterStateStore !== 'undefined') {
    FilterStateStore.clear();
  }
  Object.values(filters).forEach(ms => {
    if (ms.key === 'is_fornecedor_nao_negociavel' || (ms.container && ms.container.id === 'fFornNegociavel')) {
      ms.selected = new Set(['NEGOCIAVEL']);
    } else if (ms.key === 'is_fornecedor_sem_oc' || (ms.container && ms.container.id === 'fFornSemOC')) {
      ms.selected = new Set(['COM ATUAÇÃO']);
    } else {
      ms.selected = new Set(ms.options);
    }
    ms.renderOptions();
    ms.updateLabel();
  });
  // Default: empresa = BB
  if (filters.fEmpresa) {
    filters.fEmpresa.selected = new Set(['BB','BQ']);
    filters.fEmpresa.renderOptions();
    filters.fEmpresa.updateLabel();
  }
  // Default: current year (or latest available year)
  const cy = String(new Date().getFullYear());
  if (filters.fAno && filters.fAno.options && filters.fAno.options.length > 0) {
    const defaultAno = filters.fAno.options.includes(cy) ? cy : filters.fAno.options[0];
    filters.fAno.selected = new Set([defaultAno]);
    filters.fAno.renderOptions();
    filters.fAno.updateLabel();
  }
  // Default: current month
  const cm = String(new Date().getMonth() + 1);
  if (filters.fMes && filters.fMes.options.includes(cm)) {
    filters.fMes.selected = new Set([cm]);
    filters.fMes.renderOptions();
    filters.fMes.updateLabel();
  }
  // Default: fornecedor negociável = NEGOCIAVEL
  if (filters.fFornNegociavel) {
    filters.fFornNegociavel.selected = new Set(['NEGOCIAVEL']);
    filters.fFornNegociavel.renderOptions();
    filters.fFornNegociavel.updateLabel();
  }
  // Default: fornecedor sem OC = COM ATUAÇÃO
  if (filters.fFornSemOC) {
    filters.fFornSemOC.selected = new Set(['COM ATUAÇÃO']);
    filters.fFornSemOC.renderOptions();
    filters.fFornSemOC.updateLabel();
  }
  if (typeof FilterStateStore !== 'undefined') {
    FilterStateStore.save();
  }
  _filtersReady = true;
  if (loadFn) {
    aplicarFiltros(loadFn);
  }
}

let _filterLoadSequence = 0;

/** Show one indicator at the bottom of the visible header, including embedded modules. */
let _filterDimTimeout = null;
const FILTER_DIM_SELECTOR = '.fr-kpi-row, .fr-kpi-row-center, .fr-grid-row, .fr-split-row, .kpi-row, .grid, .chart-card, .table-card, .card, .det-wrap, .report-top, .report-bottom, .section-card, .table-section, #empresaChart, #barCategories, #leadTimeFunnel';
function setFilterLoadingState(isLoading) {
  // Barra de carregamento do topo desativada (pedido do usuário): ficava presa e parecia app travado.
  try {
    const old = (window.parent !== window ? window.parent.document : document).getElementById('filterGlowBar');
    if (old) old.remove();
  } catch (_) {}
  // Visuais ficam acinzentados enquanto carregam / reaplicam filtros (estado anterior restaurado).
  clearTimeout(_filterDimTimeout);
  const cards = document.querySelectorAll(FILTER_DIM_SELECTOR);
  cards.forEach(el => el.classList.toggle('is-filter-loading', !!isLoading));
  if (isLoading) {
    // Failsafe: nunca deixa o visual cinza preso
    _filterDimTimeout = setTimeout(() => {
      document.querySelectorAll('.is-filter-loading').forEach(el => el.classList.remove('is-filter-loading'));
    }, 18000);
  }
  return;
  let hostWindow = window;
  try { if (window.parent !== window && window.parent.document.querySelector('.home-header')) hostWindow = window.parent; } catch (_) {}
  const hostDocument = hostWindow.document;
  const header = hostDocument.querySelector('.home-header, .dna-header');
  if (!header) return;
  const pending = hostWindow.__filterLoadingFrames || (hostWindow.__filterLoadingFrames = new Set());
  if (isLoading) pending.add(window); else pending.delete(window);
  let bar = hostDocument.getElementById('filterGlowBar');
  if (!bar) {
    bar = hostDocument.createElement('div');
    bar.id = 'filterGlowBar';
    bar.className = 'filter-glow-bar';
    bar.setAttribute('role', 'status');
    bar.setAttribute('aria-label', 'Atualizando dados dos filtros');
    header.appendChild(bar);
  }
  bar.classList.toggle('active', pending.size > 0);
  bar.setAttribute('aria-hidden', pending.size ? 'false' : 'true');
}

/**
 * Standard "Aplicar" handler: refresh cascading + reload data with visual feedback.
 */
async function aplicarFiltros(loadFn) {
  triggerCascadeRefresh();
  const sequence = ++_filterLoadSequence;
  setFilterLoadingState(true);
  try {
    if (loadFn) {
      const res = loadFn();
      if (res && typeof res.then === 'function') {
        await res;
      }
    }
  } catch (err) {
    console.error('Erro ao aplicar filtros:', err);
  } finally {
    if (sequence === _filterLoadSequence) setFilterLoadingState(false);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Table Column Filter Engine (Excel-style Header Filters)
// ══════════════════════════════════════════════════════════════════════════════
const TableColumnFilter = {
  _activeCallback: null,
  _activeCol: null,
  _activeType: 'text',
  
  ensurePopover() {
    let pop = document.getElementById('tableHeaderFilterPopover');
    if (!pop) {
      pop = document.createElement('div');
      pop.id = 'tableHeaderFilterPopover';
      pop.className = 'hfp-popover';
      pop.style.display = 'none';
      pop.onclick = e => e.stopPropagation();
      pop.innerHTML = `
        <div class="hfp-hdr">
          <span class="hfp-title" id="thfColTitle">Filtrar Coluna</span>
          <button type="button" class="hfp-close" onclick="TableColumnFilter.close()">&times;</button>
        </div>
        <div class="hfp-body">
          <div class="hfp-field">
            <label>${typeof t === 'function' ? t('Condição:') : 'Condição:'}</label>
            <select id="thfOpSelect" class="hfp-select">
              <option value="contains" selected>${typeof t === 'function' ? t('Contém') : 'Contém'}</option>
              <option value="equals">${typeof t === 'function' ? t('É igual a') : 'É igual a'}</option>
              <option value="neq">É diferente de</option>
              <option value="startswith">${typeof t === 'function' ? t('Começa com') : 'Começa com'}</option>
              <option value="endswith">${typeof t === 'function' ? t('Termina com') : 'Termina com'}</option>
              <option value="notcontains">Não contém</option>
              <option value="gt">${typeof t === 'function' ? t('Maior que (>)') : 'Maior que (>)'}</option>
              <option value="lt">${typeof t === 'function' ? t('Menor que (<)') : 'Menor que (<)'}</option>
              <option value="gte">Maior ou igual a</option><option value="lte">Menor ou igual a</option><option value="between">Está entre</option>
            </select>
          </div>
          <div class="hfp-field">
            <label>${typeof t === 'function' ? t('Valor:') : 'Valor:'}</label>
            <input type="text" id="thfValInput" class="hfp-input" placeholder="${typeof t === 'function' ? t('Digite para filtrar...') : 'Digite para filtrar...'}" onkeydown="if(event.key==='Enter') TableColumnFilter.apply()">
            <input type="text" id="thfValEnd" class="hfp-input" aria-label="Valor final" placeholder="Valor final" style="display:none;margin-top:.4rem">
          </div>
          <div class="hfp-btns">
            <button type="button" class="hfp-btn-apply" onclick="TableColumnFilter.apply()">${typeof t === 'function' ? t('Aplicar') : 'Aplicar'}</button>
            <button type="button" class="hfp-btn-clear" onclick="TableColumnFilter.clear()">${typeof t === 'function' ? t('Limpar') : 'Limpar'}</button>
          </div>
        </div>
      `;
      document.body.appendChild(pop);
      document.addEventListener('click', e => {
        if (pop && pop.style.display !== 'none' && !pop.contains(e.target) && !e.target.closest('.th-filter-btn')) {
          TableColumnFilter.close();
        }
      });
      document.addEventListener('keydown', e => {
        if (e.key === 'Escape') TableColumnFilter.close();
      });
    }
    return pop;
  },

  open(e, colKey, colLabel, currentFilter, onApply, type = 'text') {
    if (e) {
      if (typeof e.stopPropagation === 'function') e.stopPropagation();
      if (typeof e.preventDefault === 'function') e.preventDefault();
    }
    const pop = this.ensurePopover();
    this._activeCol = colKey;
    this._activeCallback = onApply;
    this._activeType = type;

    const titleEl = document.getElementById('thfColTitle');
    if (titleEl) titleEl.textContent = (typeof t === 'function' ? t('Filtrar:') : 'Filtrar:') + ' ' + (colLabel || colKey);

    const opSelect = document.getElementById('thfOpSelect');
    const valInput = document.getElementById('thfValInput');
    const allowed = type === 'text' ? ['contains','equals','neq','startswith','endswith','notcontains'] : ['equals','neq','gt','gte','lt','lte','between'];
    Array.from(opSelect.options).forEach(o => { o.hidden = !allowed.includes(o.value); });
    opSelect.value = allowed.includes(currentFilter?.op) ? currentFilter.op : (type === 'text' ? 'contains' : 'equals');
    const parts = String(currentFilter?.val || '').split('|');
    valInput.type = type === 'date' ? 'date' : 'text';
    valInput.value = parts[0];
    const endInput = document.getElementById('thfValEnd');
    endInput.type = type === 'date' ? 'date' : 'text';
    endInput.value = parts[1] || '';
    const updateEnd = () => { endInput.style.display = opSelect.value === 'between' ? '' : 'none'; };
    opSelect.onchange = updateEnd; updateEnd();

    pop.style.display = 'block';
    const triggerEl = (e && e.currentTarget) || (e && e.target && e.target.closest && e.target.closest('.th-filter-btn')) || (e && e.target) || document.body;
    const rect = triggerEl.getBoundingClientRect ? triggerEl.getBoundingClientRect() : { left: 100, bottom: 100 };
    const popW = 220;
    // Coordenadas da tela -> px internos do body (zoom do seletor de escala)
    const _z = window.dnaScale ? window.dnaScale() : 1;
    const _sx = window.scrollX / _z;
    const _vw = window.innerWidth / _z;
    let left = rect.left / _z + _sx;
    if (left + popW > _sx + _vw - 15) {
      left = _sx + _vw - popW - 15;
    }
    pop.style.left = `${Math.max(10, left)}px`;
    pop.style.top = `${(rect.bottom + window.scrollY) / _z + 6}px`;

    setTimeout(() => { if (valInput) valInput.focus(); }, 60);
  },

  close() {
    const pop = document.getElementById('tableHeaderFilterPopover');
    if (pop) pop.style.display = 'none';
    this._activeCol = null;
    this._activeCallback = null;
  },

  apply() {
    if (!this._activeCallback || !this._activeCol) return;
    let val = (document.getElementById('thfValInput')?.value || '').trim();
    const op = document.getElementById('thfOpSelect')?.value || 'contains';
    if (op === 'between') {
      const end = (document.getElementById('thfValEnd')?.value || '').trim();
      if (!val || !end) return;
      val += '|' + end;
    }
    const callback = this._activeCallback;
    const col = this._activeCol;
    this.close();
    callback(col, val ? { op, val, type: this._activeType } : null);
  },

  clear() {
    if (!this._activeCallback || !this._activeCol) return;
    const callback = this._activeCallback;
    const col = this._activeCol;
    this.close();
    callback(col, null);
  },

  matches(cellValue, filterObj) {
    if (!filterObj || !filterObj.val) return true;
    const { op, val, type } = filterObj;
    if (cellValue == null) return false;
    
    // Check if numeric comparison (gt or lt)
    if (type === 'number' || type === 'date' || op === 'gt' || op === 'lt') {
      const cleanNum = v => {
        if (typeof v === 'number') return v;
        const s = String(v).replace(/[R$\s%]/g, '').replace(/\./g, '').replace(',', '.');
        return parseFloat(s);
      };
      const asDate = v => { const s = String(v).trim(); const m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})/); return m ? `${m[3]}-${m[2]}-${m[1]}` : s.slice(0, 10); };
      const parse = type === 'date' ? asDate : cleanNum;
      const nCell = parse(cellValue);
      const [first, last] = String(val).split('|');
      const nTarget = parse(first);
      if (type !== 'date' && (isNaN(nCell) || isNaN(nTarget))) return false;
      if (type === 'date' && (!/^\d{4}-\d{2}-\d{2}$/.test(nCell) || !/^\d{4}-\d{2}-\d{2}$/.test(nTarget))) return false;
      if (op === 'equals') return nCell === nTarget;
      if (op === 'neq') return nCell !== nTarget;
      if (op === 'gt') return nCell > nTarget;
      if (op === 'gte') return nCell >= nTarget;
      if (op === 'lt') return nCell < nTarget;
      if (op === 'lte') return nCell <= nTarget;
      if (op === 'between') return nCell >= nTarget && nCell <= parse(last);
      return false;
    }

    const sCell = String(cellValue).trim().toLowerCase();
    const sVal = String(val).trim().toLowerCase();
    if (op === 'equals') return sCell === sVal;
    if (op === 'neq') return sCell !== sVal;
    if (op === 'notcontains') return !sCell.includes(sVal);
    if (op === 'startswith') return sCell.startsWith(sVal);
    if (op === 'endswith') return sCell.endsWith(sVal);
    return sCell.includes(sVal); // default: contains
  },

  filterData(dataArray, filtersMap, getValFn) {
    const activeKeys = Object.keys(filtersMap).filter(k => filtersMap[k] && filtersMap[k].val);
    if (!activeKeys.length) return dataArray;
    return dataArray.filter(item => {
      return activeKeys.every(k => {
        const cellVal = getValFn ? getValFn(item, k) : item[k];
        return TableColumnFilter.matches(cellVal, filtersMap[k]);
      });
    });
  },

  renderBtn(colKey, colLabel, isFiltered, onClickFnCall) {
    const safeLabel = (colLabel || '').replace(/'/g, "\\'");
    const activeClass = isFiltered ? ' active' : '';
    const fill = isFiltered ? '#3b82f6' : 'none';
    const titleText = isFiltered ? `${typeof t === 'function' ? t('Filtrado por') : 'Filtrado por'}: ${safeLabel}` : `${typeof t === 'function' ? t('Filtrar coluna') : 'Filtrar coluna'} ${safeLabel}`;
    let callExpr = (onClickFnCall || '').trim();
    if (callExpr && !callExpr.includes('(')) {
      callExpr = `${callExpr}(event, '${colKey}', '${safeLabel}')`;
    }
    return `<button type="button" class="th-filter-btn${activeClass}" onclick="event.stopPropagation(); ${callExpr}" title="${titleText}">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="${fill}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon>
      </svg>
    </button>`;
  }
};

if (typeof window !== 'undefined') {
  window.MultiSelect = MultiSelect;
  window.filters = filters;
  window.getFilters = getFilters;
  window.getFiltersExcluding = getFiltersExcluding;
  window.aplicarFiltros = aplicarFiltros;
  window.TableColumnFilter = TableColumnFilter;
}
