/**
 * COMPRAS 360° — Shared Cascading Filters Module
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
  constructor(el, opts = [], onChange = null) {
    this.container = el;
    this.key = el.dataset.key;
    this.selected = new Set();
    this.options = [];
    this.isOpen = false;
    this.onChange = onChange;
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
    this.trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggle();
    });
    this.panel.addEventListener('click', (e) => {
      e.stopPropagation();
    });
    this.search.addEventListener('input', () => this.filter());
    this.container.querySelector('.ms-sel-all').addEventListener('click', () => this.selectAllVisible());
    this.container.querySelector('.ms-desel-all').addEventListener('click', () => this.deselectAllVisible());
    document.addEventListener('click', e => { if (!this.container.contains(e.target)) this.close(); });
  }
  setOptions(opts) {
    this.options = opts.map(String).filter(o => o.trim() && o.toLowerCase() !== 'todos');
    this.selected = new Set(this.options);
    this.renderOptions();
    this.updateLabel();
  }
  /** Update options while preserving current selections (cascading update). */
  updateOptions(newOpts) {
    const newSet = new Set(newOpts.map(String).filter(o => o.trim() && o.toLowerCase() !== 'todos'));
    // Keep only selections that still exist in new options
    const preserved = new Set([...this.selected].filter(v => newSet.has(v)));
    this.options = [...newSet];
    // If nothing is preserved, select all (meaning "no filter")
    this.selected = preserved.size > 0 ? preserved : new Set(this.options);
    this.renderOptions();
    this.updateLabel();
  }
  renderOptions() {
    this.optionsEl.innerHTML = this.options.map((o, idx) => `
      <div class="ms-option" data-idx="${idx}">
        <input type="checkbox" ${this.selected.has(o) ? 'checked' : ''}>
        <label>${o}</label>
      </div>`).join('');
    this.optionsEl.querySelectorAll('.ms-option').forEach(el => {
      el.addEventListener('click', (e) => {
        const idx = parseInt(el.dataset.idx, 10);
        const val = this.options[idx];
        if (e.target.tagName === 'INPUT') { this.toggleOption(val); return; }
        const cb = el.querySelector('input');
        if (cb) cb.checked = !cb.checked;
        this.toggleOption(val);
      });
    });
  }
  toggleOption(val) {
    if (this.selected.has(val)) this.selected.delete(val); else this.selected.add(val);
    this.updateLabel();
    if (typeof this.onChange === 'function') this.onChange(this);
    this.container.dispatchEvent(new CustomEvent('change', { detail: { selected: this.getSelected() } }));
  }
  selectAllVisible() {
    this.optionsEl.querySelectorAll('.ms-option:not(.hidden)').forEach(el => {
      const idx = parseInt(el.dataset.idx, 10);
      const val = this.options[idx];
      this.selected.add(val);
      const cb = el.querySelector('input');
      if (cb) cb.checked = true;
    });
    this.updateLabel();
    if (typeof this.onChange === 'function') this.onChange(this);
    this.container.dispatchEvent(new CustomEvent('change', { detail: { selected: this.getSelected() } }));
  }
  deselectAllVisible() {
    this.optionsEl.querySelectorAll('.ms-option:not(.hidden)').forEach(el => {
      const idx = parseInt(el.dataset.idx, 10);
      const val = this.options[idx];
      this.selected.delete(val);
      const cb = el.querySelector('input');
      if (cb) cb.checked = false;
    });
    this.updateLabel();
    if (typeof this.onChange === 'function') this.onChange(this);
    this.container.dispatchEvent(new CustomEvent('change', { detail: { selected: this.getSelected() } }));
  }
  filter() {
    const q = this.search.value.toLowerCase();
    this.optionsEl.querySelectorAll('.ms-option').forEach(el => {
      const idx = parseInt(el.dataset.idx, 10);
      const val = (this.options[idx] || '').toLowerCase();
      el.classList.toggle('hidden', !val.includes(q));
    });
  }
  toggle() { this.isOpen ? this.close() : this.open(); }
  open() {
    document.querySelectorAll('.ms-panel.open').forEach(p => {
      if (p !== this.panel) p.classList.remove('open');
    });
    this.panel.classList.add('open');
    this.isOpen = true;
    this.search.focus();
  }
  close() {
    this.panel.classList.remove('open');
    this.isOpen = false;
    this.search.value = '';
    this.filter();
  }
  updateLabel() {
    const t = this.options.length, s = this.selected.size;
    const textEl = this.trigger.querySelector('.ms-text');
    if (!textEl) return;
    if (s === 0) textEl.textContent = 'Nenhum';
    else if (s === t) textEl.textContent = 'Todos';
    else if (s <= 2) textEl.textContent = [...this.selected].join(', ');
    else textEl.innerHTML = `${s} selecionados <span class="ms-badge">${s}</span>`;
  }
  getSelected() {
    if (!this.options || this.options.length === 0) return [];
    if (this.selected.size === 0) return ['__NONE__'];
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
window.filters = window.filters || {};
var filters = window.filters;
let _cascadeEndpoint = '/api/filters/cascading'; // default for notas_ri modules
let _cascadeDebounce = null;
let _filtersReady = false;

/**
 * Build query string from current filter selections.
 * Used by data-loading functions.
 */
function getFilters() {
  const p = new URLSearchParams();
  Object.entries(filters).forEach(([id, ms]) => {
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
  Object.entries(filters).forEach(([id, ms]) => {
    if (excludeKeys.includes(ms.key)) return;
    if (ms.key === 'oc_type') { ms.getSelected().forEach(v => p.append('oc_type', v)); }
    else { ms.getSelected().forEach(v => p.append(ms.key, v)); }
  });
  return p.toString();
}

/**
 * Refresh cascading filter options based on current selections.
 * Calls the cascading endpoint and updates all dropdowns.
 */
async function refreshCascadingFilters() {
  if (!_filtersReady) return;
  try {
    const params = getFilters();
    const data = await fetch(`${_cascadeEndpoint}?${params}`).then(r => r.json());
    
    // Do NOT cascade date filters (ano/mes) — they must keep the full list
    // regardless of entity selections (empresa, fornecedor, grupo).
    // Only cascade entity filters if the API returns them.
    const mapping = {};
    
    Object.entries(mapping).forEach(([apiField, filterKey]) => {
      if (!data[apiField]) return;
      // Find the MultiSelect instance with this key
      const ms = Object.values(filters).find(f => f.key === filterKey);
      if (ms) {
        ms.updateOptions(data[apiField].map(String));
      }
    });
  } catch (e) {
    console.warn('Cascading filter refresh failed:', e);
  }
}

/**
 * Debounced version of refreshCascadingFilters.
 * Called automatically when user clicks "Aplicar".
 */
function triggerCascadeRefresh() {
  if (_cascadeDebounce) clearTimeout(_cascadeDebounce);
  _cascadeDebounce = setTimeout(refreshCascadingFilters, 100);
}

/**
 * Clear all filters to default state.
 */
function clearAllFilters(loadFn) {
  _filtersReady = false;
  Object.values(filters).forEach(ms => {
    ms.selected = new Set(ms.options);
    ms.renderOptions();
    ms.updateLabel();
  });
  // Default: empresa = BB
  if (filters.fEmpresa) {
    filters.fEmpresa.selected = new Set(['BB','BQ']);
    filters.fEmpresa.renderOptions();
    filters.fEmpresa.updateLabel();
  }
  // Default: current year
  const cy = String(new Date().getFullYear());
  if (filters.fAno && filters.fAno.options.includes(cy)) {
    filters.fAno.selected = new Set([cy]);
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
  _filtersReady = true;
  if (loadFn) loadFn();
}

/**
 * Standard "Aplicar" handler: refresh cascading + reload data.
 */
function aplicarFiltros(loadFn) {
  triggerCascadeRefresh();
  if (loadFn) loadFn();
}
