const fs = require('fs');

// Create a DOM mocking engine that faithfully reproduces DOM querying
function createDOMNode(tag, id = '', className = '') {
  return {
    id,
    tagName: tag.toUpperCase(),
    className,
    classList: {
      _set: new Set(className.split(' ').filter(Boolean)),
      add(...cls) { cls.forEach(c => this._set.add(c)); },
      remove(...cls) { cls.forEach(c => this._set.delete(c)); },
      toggle(c, f) {
        if (f === undefined) {
          if (this._set.has(c)) this._set.delete(c);
          else this._set.add(c);
        } else if (f) this._set.add(c);
        else this._set.delete(c);
      },
      contains(c) { return this._set.has(c); }
    },
    style: {},
    children: [],
    childNodes: [],
    _listeners: {},
    addEventListener(evt, fn) {
      if (!this._listeners[evt]) this._listeners[evt] = [];
      this._listeners[evt].push(fn);
    },
    removeEventListener(evt, fn) {
      if (this._listeners[evt]) this._listeners[evt] = this._listeners[evt].filter(f => f !== fn);
    },
    dispatchEvent(e) {
      const type = e.type || e;
      if (this._listeners[type]) this._listeners[type].forEach(fn => fn(e));
      return true;
    },
    click() {
      if (this._listeners['click']) {
        this._listeners['click'].forEach(fn => fn({ target: this, currentTarget: this }));
      }
    },
    setAttribute(k, v) { this[k] = String(v); },
    getAttribute(k) { return this[k] || null; },
    removeAttribute(k) { delete this[k]; },
    querySelector(sel) {
      if (sel === 'input') return createDOMNode('input');
      if (sel === 'span') return createDOMNode('span');
      if (sel === 'button') return createDOMNode('button');
      if (sel === '.fp-valor') return createDOMNode('span');
      return null;
    },
    querySelectorAll(sel) { return []; },
    appendChild(c) { this.children.push(c); return c; },
    append(...c) { this.children.push(...c); },
    prepend(...c) { this.children.unshift(...c); },
    insertBefore(n, r) { this.children.push(n); return n; },
    getContext() {
      return {
        save() {}, restore() {}, fillRect() {}, clearRect() {},
        measureText() { return { width: 50 }; },
        beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fill() {}
      };
    }
  };
}

const domNodes = {};
function getNode(id, tag = 'div') {
  if (!domNodes[id]) {
    domNodes[id] = createDOMNode(tag, id);
  }
  return domNodes[id];
}

global.window = global;
global.window.innerWidth = 1440;
global.window.addEventListener = () => {};
global.window.removeEventListener = () => {};
global.window.dispatchEvent = () => {};
global.document = {
  documentElement: createDOMNode('html', 'html'),
  head: createDOMNode('head'),
  body: createDOMNode('body'),
  getElementById(id) { return getNode(id); },
  querySelector(sel) {
    if (sel.startsWith('#')) return getNode(sel.slice(1));
    return createDOMNode('div');
  },
  querySelectorAll() { return []; },
  createElement(tag) { return createDOMNode(tag); },
  addEventListener() {},
  removeEventListener() {},
  dispatchEvent() {}
};

global.localStorage = {
  _store: {},
  getItem(k) { return this._store[k] || null; },
  setItem(k, v) { this._store[k] = String(v); },
  removeItem(k) { delete this._store[k]; }
};

global.sessionStorage = {
  _store: {},
  getItem(k) { return this._store[k] || null; },
  setItem(k, v) { this._store[k] = String(v); },
  removeItem(k) { delete this._store[k]; }
};

global.location = { pathname: '/performance.html', href: 'https://test/performance.html' };
global.requestAnimationFrame = (cb) => setTimeout(cb, 0);

// Mock Chart.js
global.Chart = function(ctx, config) {
  return {
    destroy() {},
    update() {},
    resize() {},
    data: config.data || {},
    options: config.options || {},
    getDatasetMeta() { return { data: [] }; },
    ctx: { save() {}, restore() {}, fillText() {} }
  };
};

global.XLSX = {
  utils: {
    aoa_to_sheet() { return {}; },
    encode_cell() { return 'A1'; },
    encode_range() { return 'A1:B2'; },
    book_new() { return {}; },
    book_append_sheet() {}
  },
  writeFile() {}
};

const capturedFetchUrls = [];
global.fetch = async (url) => {
  capturedFetchUrls.push(url);
  console.log('[FETCH]:', url);
  if (url.includes('/api/filters/notas')) {
    return {
      ok: true,
      json: async () => ({
        empresas: ['BB', 'BQ'],
        anos: [2026, 2025, 2024],
        meses: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        grupos: ['Direto', 'Indireto', null],
        fornecedores: ['Fornecedor A', 'Fornecedor B', null]
      })
    };
  }
  if (url.includes('/api/filters/advanced')) {
    return {
      ok: true,
      json: async () => ({
        macro_categoria: ['Embalagens', 'Ingredientes'],
        dias: [1, 2, 3, 4, 5]
      })
    };
  }
  // Data endpoints
  return {
    ok: true,
    json: async () => ({
      current: { net_spend: 1000000, total_nfs: 500, lead_time_medio: 12.5 },
      previous: { net_spend: 950000, total_nfs: 480, lead_time_medio: 14.0 },
      top_suppliers: [],
      price_alerts: [],
      monthly_trend: []
    })
  };
};

(async () => {
  try {
    console.log('1. Loading i18n.js...');
    eval(fs.readFileSync('src/app/i18n.js', 'utf8'));

    console.log('2. Loading filters-shared.js...');
    eval(fs.readFileSync('src/app/filters-shared.js', 'utf8'));

    console.log('3. Loading filters-component.js...');
    eval(fs.readFileSync('src/app/filters-component.js', 'utf8'));

    console.log('4. Loading app-menu.js...');
    eval(fs.readFileSync('src/app/app-menu.js', 'utf8'));

    console.log('5. Extracting and running performance.html inline script...');
    const html = fs.readFileSync('src/app/performance.html', 'utf8');
    const scripts = [...html.matchAll(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m => m[1]);
    const mainScript = scripts.find(s => s.includes('initFilters'));
    eval(mainScript);

    // Wait 1 second for async operations
    await new Promise(r => setTimeout(r, 1000));

    console.log('\n=== STATUS AFTER INIT ===');
    console.log('Total Fetch Calls Made:', capturedFetchUrls.length);
    console.log('appLayout data-filtros:', domNodes['appLayout']?.['data-filtros']);

    console.log('\n--- SIMULATING USER CLICK ON fpExpandir ---');
    const trilhoBtn = domNodes['fpExpandir'];
    console.log('Has click listener on fpExpandir?', (trilhoBtn?._listeners['click'] || []).length);
    trilhoBtn.click();
    console.log('appLayout data-filtros after click:', domNodes['appLayout']?.['data-filtros']);

    console.log('\n--- SIMULATING USER CLICK ON fpRecolher ---');
    const recolherBtn = domNodes['fpRecolher'];
    console.log('Has click listener on fpRecolher?', (recolherBtn?._listeners['click'] || []).length);
    recolherBtn.click();
    console.log('appLayout data-filtros after click:', domNodes['appLayout']?.['data-filtros']);

    console.log('\n--- SIMULATING USER CLICK ON fpLateral (ANYWHERE ON RAIL) ---');
    const lateralEl = domNodes['fpLateral'];
    console.log('Has click listener on fpLateral?', (lateralEl?._listeners['click'] || []).length);
    lateralEl.click();
    console.log('appLayout data-filtros after clicking anywhere on rail:', domNodes['appLayout']?.['data-filtros']);

    console.log('\n--- CHECKING GETFILTERS OUTPUT ---');
    const qs = global.getFilters ? global.getFilters() : (global.filters ? new URLSearchParams().toString() : 'NO FILTERS');
    console.log('Query String generated for API:', qs);

  } catch (err) {
    console.error('FATAL ERROR DURING EXECUTION:', err);
  }
})();
