/**
 * PORTAL COMPRAS — Navegação mobile inferior unificada (<= 640px)
 *
 * Reconstrói a <nav class="dna-mobile-nav"> de TODAS as telas a partir do trilho lateral (.sp-sidebar),
 * que é a fonte única de verdade dos módulos. Resolve:
 *  - itens diferentes em cada tela (Governança/Relatórios inacessíveis a partir de Performance/Ordens);
 *  - botão "Mais" sem função (toggleMobileMoreNav não existia);
 *  - grade fixa de 5 colunas com 6-7 itens (quebrava em 2 linhas no Guia/Cadastros);
 *  - módulos ocultos por CSS (ex.: Gastos) deixando buracos.
 * Regra: até 5 itens visíveis cabem direto; acima disso, 4 itens + "Mais" (folha com o restante).
 */
(function () {
  'use strict';
  var MAX_SLOTS = 5;

  function isHidden(el) {
    var cs = window.getComputedStyle(el);
    return cs.display === 'none' || cs.visibility === 'hidden';
  }

  function currentFile() {
    var p = (window.location.pathname || '').split('/').pop();
    return p || 'index.html';
  }

  // Clona o <span> do trilho preservando atributos do i18n (data-i18n, data-i18n-orig)
  function labelOf(a) {
    var span = a.querySelector('span');
    if (span) return span.cloneNode(true).outerHTML;
    var s = document.createElement('span');
    s.textContent = (a.getAttribute('title') || '').trim();
    return s.outerHTML;
  }

  function iconOf(a) {
    var svg = a.querySelector('svg');
    if (!svg) return '';
    var clone = svg.cloneNode(true);
    clone.removeAttribute('width');
    clone.removeAttribute('height');
    clone.setAttribute('aria-hidden', 'true');
    return clone.outerHTML;
  }

  function itemHtml(it, cls) {
    return '<a href="' + it.href + '" class="' + cls + (it.active ? ' active' : '') + '"' +
      (it.active ? ' aria-current="page"' : '') + '>' + it.icon + it.label + '</a>';
  }

  function build() {
    var nav = document.querySelector('nav.dna-mobile-nav');
    var side = document.querySelector('.sp-sidebar');
    if (!nav || !side || nav.getAttribute('data-built') === '1') return;

    var file = currentFile();
    var links = Array.prototype.filter.call(side.querySelectorAll('a.sp-nav-item'), function (a) { return !isHidden(a); });
    if (!links.length) return;

    var items = links.map(function (a) {
      var href = a.getAttribute('href');
      return { href: href, icon: iconOf(a), label: labelOf(a), active: a.classList.contains('active') || href === file };
    });

    var primary = items, extra = [];
    if (items.length > MAX_SLOTS) {
      primary = items.slice(0, MAX_SLOTS - 1);
      extra = items.slice(MAX_SLOTS - 1);
    }

    var html = primary.map(function (it) { return itemHtml(it, 'dna-mobile-nav-item'); }).join('');
    var extraActive = extra.some(function (it) { return it.active; });
    if (extra.length) {
      html += '<button type="button" class="dna-mobile-nav-item dna-more-btn' + (extraActive ? ' active' : '') + '" id="dnaMoreBtn" aria-haspopup="true" aria-expanded="false" aria-controls="dnaMoreSheet">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/></svg>' +
        '<span>' + (typeof window.t === 'function' ? window.t('Mais') : 'Mais') + '</span></button>';
    }

    nav.innerHTML = html;
    nav.style.gridTemplateColumns = 'repeat(' + (primary.length + (extra.length ? 1 : 0)) + ', minmax(0, 1fr))';
    nav.setAttribute('data-built', '1');

    if (!extra.length) return;

    var backdrop = document.createElement('div');
    backdrop.className = 'dna-more-backdrop';
    backdrop.hidden = true;

    var sheet = document.createElement('div');
    sheet.className = 'dna-more-sheet';
    sheet.id = 'dnaMoreSheet';
    sheet.setAttribute('role', 'menu');
    sheet.hidden = true;
    sheet.innerHTML = extra.map(function (it) { return itemHtml(it, 'dna-more-item'); }).join('');

    document.body.appendChild(backdrop);
    document.body.appendChild(sheet);

    var btn = document.getElementById('dnaMoreBtn');
    function setOpen(open) {
      sheet.hidden = !open;
      backdrop.hidden = !open;
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    btn.addEventListener('click', function (e) { e.stopPropagation(); setOpen(sheet.hidden); });
    backdrop.addEventListener('click', function () { setOpen(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setOpen(false); });
    window.addEventListener('resize', function () { if (window.innerWidth > 640) setOpen(false); });

  }

  // Relatórios: no celular o painel "Colunas" começa recolhido para a tabela aparecer primeiro
  function mobileDefaults() {
    if (!window.matchMedia || !window.matchMedia('(max-width: 768px)').matches) return;
    var colPanel = document.getElementById('colPanel');
    if (colPanel) colPanel.classList.add('collapsed');
  }

  /* ── Celular (≤640px) ─────────────────────────────────────────────────────
     1) dnaMonthWindow: seletor 6M/12M para gráficos mensais. Só a janela do gráfico muda;
        título e KPIs continuam com o período inteiro dos filtros.
     2) Tabelas viram cartões: cada célula recebe o nome da coluna (data-label);
        o CSS (visual-system.css) monta o cartão. Grades grandes (Relatórios, Cadastros)
        e as tabelas "Ver dados em tabela" ficam como estão. */
  var MQ = window.matchMedia ? window.matchMedia('(max-width: 640px)') : null;
  function isMobile() { return !!(MQ && MQ.matches); }
  function onBreakpoint(fn) {
    if (!MQ) return;
    if (MQ.addEventListener) MQ.addEventListener('change', fn); else if (MQ.addListener) MQ.addListener(fn);
  }

  var _mwCallbacks = [];
  function mwStored() {
    var v = 6;
    try { v = parseInt(localStorage.getItem('dna_mobile_months') || '6', 10); } catch (e) {}
    return v === 12 ? 12 : 6;
  }
  function mwSyncButtons() {
    var n = String(mwStored());
    var btns = document.querySelectorAll('.dna-mwin button');
    for (var i = 0; i < btns.length; i++) btns[i].setAttribute('aria-pressed', btns[i].getAttribute('data-n') === n ? 'true' : 'false');
  }
  function mwNotify() {
    for (var i = 0; i < _mwCallbacks.length; i++) {
      try { _mwCallbacks[i](); } catch (e) { if (window.console) console.error('dnaMonthWindow callback', e); }
    }
  }
  window.dnaMonthWindow = {
    /** Quantidade de meses a mostrar no gráfico: 0 = todos (desktop/tablet). */
    size: function () { return isMobile() ? mwStored() : 0; },
    /** Índice inicial da janela: termina o mais perto do fim possível, sempre contendo o mês em foco. */
    start: function (len, focus) {
      var n = this.size();
      if (!n || len <= n) return 0;
      var f = (focus == null || focus < 0 || focus >= len) ? len - 1 : focus;
      return Math.max(0, Math.min(len - n, f));
    },
    /** Insere o seletor 6M/12M (uma única vez por âncora). mode: 'append' (padrão) ou 'after'. */
    mount: function (anchor, onChange, mode) {
      if (!anchor) return;
      if (onChange && _mwCallbacks.indexOf(onChange) < 0) _mwCallbacks.push(onChange);
      if (anchor.getAttribute('data-dna-mwin') === '1') return;
      anchor.setAttribute('data-dna-mwin', '1');
      var box = document.createElement('div');
      box.className = 'dna-mwin';
      box.setAttribute('role', 'group');
      box.setAttribute('aria-label', 'Período do gráfico');
      box.innerHTML = '<button type="button" data-n="6" title="Últimos 6 meses">6M</button>' +
                      '<button type="button" data-n="12" title="Últimos 12 meses">12M</button>';
      box.addEventListener('click', function (e) {
        var b = e.target.closest ? e.target.closest('button[data-n]') : null;
        if (!b) return;
        try { localStorage.setItem('dna_mobile_months', b.getAttribute('data-n')); } catch (err) {}
        mwSyncButtons();
        mwNotify();
      });
      if (mode === 'after' && anchor.parentNode) anchor.parentNode.insertBefore(box, anchor.nextSibling);
      else anchor.appendChild(box);
      mwSyncButtons();
    }
  };
  onBreakpoint(mwNotify);

  var CARD_SKIP = '.det-table, #reportTable, #grTabela, [data-no-cards]';
  var CARD_MAX_FIELDS = 6;
  var _scanQueued = false;

  function labelTable(tbl) {
    if (!tbl.tHead || !tbl.tHead.rows.length || !tbl.tBodies.length) return;
    var ths = tbl.tHead.rows[tbl.tHead.rows.length - 1].cells;
    var names = [];
    for (var i = 0; i < ths.length; i++) {
      names.push((ths[i].textContent || '').replace(/[\u25B2\u25BC\u21C5\u2191\u2193\u2195\u24D8]/g, '').replace(/\s+/g, ' ').trim());
    }
    if (!tbl.classList.contains('dna-cards')) tbl.classList.add('dna-cards');
    if (tbl.parentElement && !tbl.parentElement.classList.contains('dna-cards-wrap')) tbl.parentElement.classList.add('dna-cards-wrap');
    var rows = tbl.tBodies[0].rows;
    for (var r = 0; r < rows.length; r++) {
      var tr = rows[r], cells = tr.cells, idx = 0, fields = 0;
      for (var c = 0; c < cells.length; c++) {
        var td = cells[c];
        if (td.classList.contains('dna-more-cell')) continue;
        var span = td.colSpan || 1;
        if (span > 1) { idx += span; continue; }
        var nm = names[idx] || '';
        if (td.getAttribute('data-label') !== nm) td.setAttribute('data-label', nm);
        fields++;
        var extra = fields > CARD_MAX_FIELDS;
        if (td.classList.contains('dna-extra') !== extra) td.classList.toggle('dna-extra', extra);
        idx += 1;
      }
      if (fields > CARD_MAX_FIELDS && !tr.querySelector('.dna-more-cell')) {
        var more = document.createElement('td');
        more.className = 'dna-more-cell';
        more.innerHTML = '<button type="button" class="dna-more-btn" data-extra="' + (fields - CARD_MAX_FIELDS) + '">Ver mais (' + (fields - CARD_MAX_FIELDS) + ')</button>';
        tr.appendChild(more);
      }
    }
  }

  function scanTables() {
    _scanQueued = false;
    if (!isMobile() || /cadastros|guia/.test(location.pathname)) return;
    var tables = document.querySelectorAll('table');
    for (var i = 0; i < tables.length; i++) {
      var t = tables[i];
      if (t.matches(CARD_SKIP) || t.closest('details, .chart-data-table, .chart-data-scroll')) continue;
      labelTable(t);
    }
  }
  function queueScan() {
    if (_scanQueued) return;
    _scanQueued = true;
    (window.requestAnimationFrame || setTimeout)(scanTables);
  }
  function initCards() {
    // Captura: o clique em "Ver mais" não aciona o clique da linha (que abre detalhes em algumas tabelas)
    document.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('.dna-more-btn') : null;
      if (!b) return;
      var tr = b.closest('tr');
      if (!tr) return;
      e.stopPropagation();
      e.preventDefault();
      var open = tr.classList.toggle('dna-open');
      b.textContent = open ? 'Ver menos' : 'Ver mais (' + b.getAttribute('data-extra') + ')';
    }, true);
    queueScan();
    if (window.MutationObserver) new MutationObserver(queueScan).observe(document.body, { childList: true, subtree: true });
    onBreakpoint(queueScan);
  }

  window.refreshMobileNavigation = function () {
    var nav = document.querySelector('nav.dna-mobile-nav');
    if (!nav || nav.getAttribute('data-built') !== '1') return;
    document.getElementById('dnaMoreSheet')?.remove();
    document.querySelector('.dna-more-backdrop')?.remove();
    nav.removeAttribute('data-built');
    build();
  };
  function init() { build(); mobileDefaults(); initCards(); }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
