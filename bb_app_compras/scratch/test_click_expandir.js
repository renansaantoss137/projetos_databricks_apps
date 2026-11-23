const fs = require('fs');

function createElement(tag, id = '') {
  const el = {
    id: id,
    tagName: (tag || 'DIV').toUpperCase(),
    innerHTML: '',
    textContent: '',
    style: {},
    classList: {
      _classes: new Set(),
      add: function(...c) { c.forEach(x => this._classes.add(x)); },
      remove: function(...c) { c.forEach(x => this._classes.delete(x)); },
      toggle: function(c, force) {
        if (force === undefined) {
          if (this._classes.has(c)) this._classes.delete(c);
          else this._classes.add(c);
        } else if (force) this._classes.add(c);
        else this._classes.delete(c);
      },
      contains: function(c) { return this._classes.has(c); }
    },
    children: [],
    childNodes: [],
    dataset: {},
    _listeners: {},
    addEventListener: function(event, cb) {
      if (!this._listeners[event]) this._listeners[event] = [];
      this._listeners[event].push(cb);
    },
    removeEventListener: function(event, cb) {
      if (this._listeners[event]) {
        this._listeners[event] = this._listeners[event].filter(x => x !== cb);
      }
    },
    dispatchEvent: function(e) {
      const type = e.type || e;
      if (this._listeners[type]) {
        this._listeners[type].forEach(cb => cb(e));
      }
      return true;
    },
    click: function() {
      console.log(`[CLICK]: Element #${this.id || this.tagName} clicked! Listeners:`, (this._listeners['click'] || []).length);
      if (this._listeners['click']) {
        this._listeners['click'].forEach(cb => cb({ target: this, currentTarget: this }));
      }
    },
    querySelector: function(sel) {
      if (sel === 'input') return createElement('input');
      if (sel === 'span') return createElement('span');
      if (sel === 'button') return createElement('button');
      if (sel === '.fp-valor') return createElement('span');
      return null;
    },
    querySelectorAll: function(sel) { return []; },
    appendChild: function(c) { this.children.push(c); return c; },
    append: function(...c) { this.children.push(...c); },
    prepend: function(...c) { this.children.unshift(...c); },
    insertBefore: function(n, r) { this.children.push(n); return n; },
    setAttribute: function(k, v) {
      this[k] = v;
      console.log(`[SET ATTRIBUTE]: #${this.id || this.tagName} setAttribute(${k}, ${v})`);
    },
    getAttribute: function(k) { return this[k] || null; },
    removeAttribute: function(k) { delete this[k]; },
    getContext: () => ({
      save: () => {},
      restore: () => {},
      fillRect: () => {},
      clearRect: () => {},
      measureText: () => ({ width: 50 })
    })
  };
  return el;
}

const elements = {};
function getOrCreateElement(id) {
  if (!elements[id]) {
    elements[id] = createElement('div', id);
  }
  return elements[id];
}

global.window = global;
global.window.addEventListener = () => {};
global.window.removeEventListener = () => {};
global.dispatchEvent = () => true;
global.CustomEvent = function(n) { this.type = n; };
global.getComputedStyle = () => ({ getPropertyValue: () => '' });
global.Chart = function() {
  return {
    destroy: () => {},
    update: () => {},
    resize: () => {},
    getDatasetMeta: () => ({ data: [] }),
    ctx: { save: () => {}, restore: () => {}, fillText: () => {} }
  };
};

const headEl = createElement('head', 'head');
const bodyEl = createElement('body', 'body');

global.document = {
  documentElement: createElement('html', 'html'),
  head: headEl,
  body: bodyEl,
  getElementById: (id) => getOrCreateElement(id),
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: (tag) => createElement(tag),
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => true
};
global.localStorage = {
  _store: {},
  getItem: (k) => global.localStorage._store[k] || null,
  setItem: (k, v) => { global.localStorage._store[k] = String(v); },
  removeItem: (k) => { delete global.localStorage._store[k]; }
};
global.sessionStorage = {
  _store: {},
  getItem: (k) => global.sessionStorage._store[k] || null,
  setItem: (k, v) => { global.sessionStorage._store[k] = String(v); },
  removeItem: (k) => { delete global.sessionStorage._store[k]; }
};
global.location = { pathname: '/performance.html', href: 'https://test/performance.html' };
global.requestAnimationFrame = (cb) => setTimeout(cb, 0);

global.fetch = async (url) => {
  return {
    ok: true,
    json: async () => ({
      empresas: ['BB', 'BQ'],
      anos: [2026, 2025],
      meses: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
      grupos: ['Direto', 'Indireto'],
      fornecedores: ['F1', null, 'F2'], // note null here!
      current: { net_spend: 100 },
      previous: { net_spend: 90 }
    })
  };
};

(async () => {
  try {
    eval(fs.readFileSync('src/app/i18n.js', 'utf8'));
    eval(fs.readFileSync('src/app/filters-shared.js', 'utf8'));
    eval(fs.readFileSync('src/app/filters-component.js', 'utf8'));
    eval(fs.readFileSync('src/app/app-menu.js', 'utf8'));

    const html = fs.readFileSync('src/app/performance.html', 'utf8');
    const scripts = [...html.matchAll(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m => m[1]);
    const inlineScript = scripts.find(s => s.includes('initFilters') || s.includes('DNAFiltersPanel'));
    eval(inlineScript);

    // Wait for initFilters to finish
    await new Promise(r => setTimeout(r, 500));

    console.log('\n--- SIMULATING USER CLICK ON fpExpandir (FILTROS RAIL) ---');
    const trilho = elements['fpExpandir'];
    console.log('trilho button exists:', !!trilho);
    trilho.click();

    console.log('appLayout data-filtros after click:', elements['appLayout'].data_filtros || elements['appLayout']['data-filtros']);
  } catch (err) {
    console.error('ERROR IN TEST:', err);
  }
})();
