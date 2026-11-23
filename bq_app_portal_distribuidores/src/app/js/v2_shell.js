/* ==========================================================================
   Portal Distribuidores v2 — shell e interações (somente apresentação)
   Header, menu do usuário, tema, status de atualização, chips de filtro,
   bottom sheet de filtros, segmented controls, popover de regras, bottom nav,
   tabela de estoque (busca/ordenação/severidade), skeleton e estado de erro.
   Reaproveita as funções existentes (triggerDashboardRefresh, clear(), tabs).
   ========================================================================== */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var mqMobile = window.matchMedia('(max-width: 768px)');
  var FILTERS = [
    ['select-categoria', 'Categoria'], ['select-produto', 'Produto'], ['select-sku', 'SKU'],
    ['select-pedido', 'Nº pedido'], ['select-dia', 'Dia'], ['select-semana', 'Semana'],
    ['select-mes', 'Mês'], ['select-ano', 'Ano']
  ];

  /* ── Tema ── */
  function currentTheme() {
    var t = document.documentElement.getAttribute('data-theme');
    if (t) return t;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  // Escolha igual ao tema do sistema volta ao automático; diferente fica gravada
  function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    var sys = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    try {
      if (t === sys) localStorage.removeItem('v2-theme-override');
      else localStorage.setItem('v2-theme-override', t);
    } catch (e) {}
    syncThemeSwitch();
  }
  function syncThemeSwitch() {
    var sw = $('#v2-theme-toggle');
    if (sw) sw.setAttribute('aria-checked', String(currentTheme() === 'dark'));
  }
  document.addEventListener('v2-themechange', syncThemeSwitch);

  /* ── Menu do usuário ── */
  function initUserMenu() {
    var btn = $('#v2-user-btn'), menu = $('#v2-user-menu');
    if (!btn || !menu) return;
    function close() { menu.hidden = true; btn.setAttribute('aria-expanded', 'false'); }
    function open() {
      syncAdminItems();
      menu.hidden = false; btn.setAttribute('aria-expanded', 'true');
      var first = menu.querySelector('[role="menuitem"]:not([hidden]), [role="menuitemcheckbox"]');
      if (first) first.focus();
    }
    btn.addEventListener('click', function (e) { e.stopPropagation(); menu.hidden ? open() : close(); });
    document.addEventListener('click', function (e) { if (!menu.hidden && !menu.contains(e.target)) close(); });
    menu.addEventListener('keydown', function (e) {
      var items = $$('[role^="menuitem"]', menu).filter(function (x) { return !x.hidden && x.offsetParent !== null; });
      var i = items.indexOf(document.activeElement);
      if (e.key === 'Escape') { close(); btn.focus(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    });
    var tt = $('#v2-theme-toggle');
    if (tt) {
      tt.setAttribute('aria-checked', String(currentTheme() === 'dark'));
      tt.addEventListener('click', function () { setTheme(currentTheme() === 'dark' ? 'light' : 'dark'); });
    }
    var sim = $('#v2-menu-sim');
    if (sim) sim.addEventListener('click', function () {
      var b = $('#amb-btn-sim');
      close();
      if (b) b.click(); else { var p = $('#amb-btn-picker'); if (p) p.click(); }
    });
    var guia = $('#v2-menu-guia');
    if (guia) guia.addEventListener('click', function () {
      close();
      if (typeof window.activateTab === 'function') {
        window.activateTab('guia');
      }
    });
    var out = $('#v2-menu-logout');
    if (out) out.addEventListener('click', function () {
      try { sessionStorage.removeItem('logged_user'); } catch (e) {}
      fetch('/logout', { credentials: 'include' }).finally(function () { window.location.href = 'home.html'; });
    });
  }
  function syncAdminItems() {
    var isAdmin = !!$('#admin-mode-bar');
    var isSimulating = document.body.classList.contains('is-simulating');
    $$('.v2-admin-only').forEach(function (el) {
      if (el.classList.contains('v2-exec-tab')) {
        el.hidden = !(isAdmin && !isSimulating);
      } else {
        el.hidden = !isAdmin;
      }
    });
    var sim = $('#v2-menu-sim');
    if (sim && isAdmin) {
      var hasDist = !!$('#amb-btn-sim');
      sim.querySelector('.mi-sub').textContent = hasDist ? 'Abrir o portal exatamente como o distribuidor selecionado' : 'Escolha um distribuidor primeiro';
    }
    var cmd = $('#v2-cmd');
    if (cmd) cmd.hidden = !isAdmin;
  }

  /* ── Busca / comando (Ctrl K) ── */
  function initCommand() {
    var cmd = $('#v2-cmd');
    if (!cmd) return;
    cmd.addEventListener('click', function (e) {
      e.stopPropagation();
      var p = $('#amb-btn-picker');
      if (p) p.click();
    });
    var isMac = /Mac|iPhone|iPad/.test(navigator.platform || '');
    var k = cmd.querySelector('kbd');
    if (k) k.textContent = isMac ? '⌘ K' : 'Ctrl K';
  }

  /* ── "Atualizado há X min" ── */
  function initSync() {
    var src = $('#header-sync-timestamp'), rel = $('#v2-sync-rel'), pill = $('#header-sync-pill');
    if (!src || !rel) return;
    function paint() {
      var d = Fmt.parseBr(src.textContent);
      if (!d) { rel.textContent = 'Atualizado: ' + src.textContent; return; }
      rel.textContent = 'Atualizado ' + Fmt.relative(d);
      if (pill) { pill.setAttribute('data-tip', V2.tipHtml('Última sincronização', [['Data', Fmt.dateTime(d)]], 'Horário de Brasília')); pill.setAttribute('aria-label', 'Última atualização em ' + Fmt.dateTime(d)); }
    }
    new MutationObserver(paint).observe(src, { childList: true, characterData: true, subtree: true });
    paint();
    setInterval(paint, 60000);
  }

  /* ── Chips de filtros ativos ── */
  function chipLabel(id, v) {
    if (id === 'select-mes') { var m = parseInt(v, 10); return (m >= 1 && m <= 12) ? Fmt.MONTHS_SHORT[m - 1] : v; }
    if (id === 'select-semana') return 'S' + v;
    return v;
  }
  function activeFilters() {
    var out = [];
    FILTERS.forEach(function (f) {
      var el = document.getElementById(f[0]);
      if (!el || typeof el.getSelectedValues !== 'function') return;
      var vals = el.getSelectedValues();
      if (vals && vals.length) out.push({ id: f[0], name: f[1], vals: vals });
    });
    return out;
  }
  function renderChips() {
    var wrap = $('#v2-chips');
    if (!wrap) return;
    var act = activeFilters();
    var count = act.length;
    var btnCount = $('#v2-filter-count');
    if (btnCount) { btnCount.textContent = count ? String(count) : ''; btnCount.hidden = !count; }
    var fb = $('#v2-filter-btn');
    if (fb) fb.setAttribute('aria-label', 'Filtros' + (count ? ', ' + count + ' ativos' : ''));
    // V2: sem chips abaixo da barra (o valor já aparece no próprio filtro). Só o "Limpar filtros" na mesma faixa.
    var clr = $('#v2-clear-inline');
    if (clr) clr.hidden = !count;
    wrap.innerHTML = ''; wrap.hidden = true;
    return;
    var h = act.map(function (f) {
      var shown = f.vals.slice(0, 2).map(function (v) { return chipLabel(f.id, v); }).join(', ');
      if (f.vals.length > 2) shown += ' +' + (f.vals.length - 2);
      return '<span class="chip"><span class="chip-k">' + Fmt.esc(f.name) + ':</span> <span class="chip-v">' + Fmt.esc(shown) + '</span>' +
        '<button type="button" class="chip-x" data-clear="' + f.id + '" aria-label="Remover filtro ' + Fmt.esc(f.name) + '">' + V2.icon('x', 12) + '</button></span>';
    }).join('');
    h += '<button type="button" class="btn-link" id="v2-clear-all">Limpar filtros</button>';
    wrap.innerHTML = h;
  }
  function initChips() {
    var wrap = $('#v2-chips');
    var clr = $('#v2-clear-inline');
    if (clr) clr.addEventListener('click', function () {
      FILTERS.forEach(function (f) { var el = document.getElementById(f[0]); if (el && el.clear) el.clear(); });
      window.triggerDashboardRefresh(0);
    });
    if (wrap) wrap.addEventListener('click', function (e) {
      var x = e.target.closest('[data-clear]');
      if (x) { var el = document.getElementById(x.getAttribute('data-clear')); if (el && el.clear) el.clear(); window.triggerDashboardRefresh(0); return; }
      if (e.target.closest('#v2-clear-all')) {
        FILTERS.forEach(function (f) { var el = document.getElementById(f[0]); if (el && el.clear) el.clear(); });
        window.triggerDashboardRefresh(0);
      }
    });
    var orig = window.triggerDashboardRefresh;
    if (typeof orig === 'function') {
      window.triggerDashboardRefresh = function () { var r = orig.apply(this, arguments); setTimeout(renderChips, 0); return r; };
    }
    setTimeout(renderChips, 800);
  }

  /* ── Bottom sheet de filtros (mobile) ── */
  function initFilterSheet() {
    var bar = $('.portal-bar'), btn = $('#v2-filter-btn'), scrim = $('#v2-scrim');
    if (!bar || !btn) return;
    var lastFocus = null;
    function open() {
      lastFocus = document.activeElement;
      bar.classList.add('is-open'); if (scrim) scrim.hidden = false;
      bar.setAttribute('role', 'dialog'); bar.setAttribute('aria-modal', 'true');
      document.body.classList.add('no-scroll');
      var f = bar.querySelector('input, button'); if (f) setTimeout(function () { f.focus(); }, 50);
    }
    function close() {
      bar.classList.remove('is-open'); if (scrim) scrim.hidden = true;
      bar.removeAttribute('role'); bar.removeAttribute('aria-modal');
      document.body.classList.remove('no-scroll');
      if (lastFocus) lastFocus.focus();
    }
    btn.addEventListener('click', open);
    if (scrim) scrim.addEventListener('click', close);
    $$('[data-sheet-close]').forEach(function (b) { b.addEventListener('click', close); });
    var apply = $('#v2-sheet-apply');
    if (apply) apply.addEventListener('click', function () { window.triggerDashboardRefresh(0); close(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && bar.classList.contains('is-open')) close(); });
    mqMobile.addEventListener('change', function (e) { if (!e.matches) close(); });
  }

  /* ── Segmented controls (Valor/Volume, Sell-in/Sell-out) ── */
  function bindSegment(inputId, offId, onId) {
    var input = document.getElementById(inputId), off = document.getElementById(offId), on = document.getElementById(onId);
    if (!input || !off || !on) return;
    function sync() { off.setAttribute('aria-checked', String(!input.checked)); on.setAttribute('aria-checked', String(input.checked)); off.tabIndex = input.checked ? -1 : 0; on.tabIndex = input.checked ? 0 : -1; }
    function set(v) { if (input.checked !== v) { input.checked = v; input.dispatchEvent(new Event('change', { bubbles: true })); } sync(); }
    off.addEventListener('click', function () { set(false); });
    on.addEventListener('click', function () { set(true); });
    [off, on].forEach(function (b) {
      b.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); set(!input.checked); (input.checked ? on : off).focus(); }
      });
    });
    input.addEventListener('change', sync);
    sync();
  }

  /* ── Popover genérico (Regras de negócio) ── */
  function initPopovers() {
    $$('[data-popover]').forEach(function (btn) {
      var pop = document.getElementById(btn.getAttribute('data-popover'));
      if (!pop) return;
      function close() { pop.hidden = true; btn.setAttribute('aria-expanded', 'false'); }
      btn.addEventListener('click', function (e) { e.stopPropagation(); var o = pop.hidden; pop.hidden = !o; btn.setAttribute('aria-expanded', String(o)); });
      document.addEventListener('click', function (e) { if (!pop.hidden && !pop.contains(e.target)) close(); });
      document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !pop.hidden) { close(); btn.focus(); } });
    });
  }

  /* ── Navegação: indicador animado + bottom nav ── */
  function initNav() {
    var tabs = $$('.kpi-header .tab');
    var ind = $('#v2-tab-ind');
    var bottom = $('#v2-bottom-nav');
    function paint() {
      var act = tabs.filter(function (t) { return t.classList.contains('active'); })[0];
      tabs.forEach(function (t) { t.setAttribute('aria-selected', String(t === act)); t.tabIndex = t === act ? 0 : -1; });
      if (act) document.body.setAttribute('data-tab', act.getAttribute('data-tab'));
      if (ind && act && act.offsetParent) { ind.style.width = act.offsetWidth + 'px'; ind.style.transform = 'translateX(' + act.offsetLeft + 'px)'; ind.style.opacity = '1'; }
      if (bottom && act) $$('button', bottom).forEach(function (b) {
        var on = b.getAttribute('data-tab') === act.getAttribute('data-tab');
        b.classList.toggle('active', on); if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
      });
      if (act) {
        $$('.sp-sidebar .sp-nav-item.tab').forEach(function (sbBtn) {
          var on = sbBtn.getAttribute('data-tab') === act.getAttribute('data-tab');
          sbBtn.classList.toggle('active', on);
        });
      }
    }
    tabs.forEach(function (t) {
      new MutationObserver(paint).observe(t, { attributes: true, attributeFilter: ['class', 'style'] });
      t.addEventListener('keydown', function (e) {
        var vis = tabs.filter(function (x) { return x.offsetParent !== null; });
        var i = vis.indexOf(t);
        if (e.key === 'ArrowRight') { e.preventDefault(); vis[(i + 1) % vis.length].focus(); }
        if (e.key === 'ArrowLeft') { e.preventDefault(); vis[(i - 1 + vis.length) % vis.length].focus(); }
      });
    });
    window.addEventListener('resize', paint);
    setTimeout(paint, 50);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(paint);
  }

  /* ── Navegação inferior (celular): espelha o menu lateral, que é a navegação real do app ── */
  function initBottomNav() {
    var bottom = $('#v2-bottom-nav');
    if (!bottom) return;
    var side = $$('.sp-sidebar .sp-nav-item[data-tab]');
    function paint() {
      var cur = side.filter(function (x) { return x.classList.contains('active'); })[0];
      var t = cur ? cur.getAttribute('data-tab') : null;
      $$('button', bottom).forEach(function (b) {
        var on = b.getAttribute('data-tab') === t;
        b.classList.toggle('active', on);
        if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
      });
    }
    $$('button', bottom).forEach(function (b) {
      var src = side.filter(function (x) { return x.getAttribute('data-tab') === b.getAttribute('data-tab'); })[0];
      if (!src) { b.remove(); return; }
      b.addEventListener('click', function () { src.click(); window.scrollTo({ top: 0, behavior: 'smooth' }); });
    });
    side.forEach(function (x) { new MutationObserver(paint).observe(x, { attributes: true, attributeFilter: ['class'] }); });
    paint();
  }

  /* ── Faixa de período dos gráficos no celular (6 / 12 meses) ── */
  function initRange() {
    $$('[data-range-for]').forEach(function (grp) {
      var target = document.getElementById(grp.getAttribute('data-range-for'));
      if (!target) return;
      $$('button', grp).forEach(function (b) {
        b.addEventListener('click', function () {
          var all = b.getAttribute('data-range') === 'all';
          target.classList.toggle('show-all', all);
          $$('button', grp).forEach(function (x) { x.setAttribute('aria-checked', String(x === b)); });
        });
      });
    });
  }

  /* ── Estoque: severidade, busca, ordenação, alerta de dado ausente ── */
  var SEV = { vermelho: ['sev-danger', 'Crítico'], amarelo: ['sev-warning', 'Atenção'], verde: ['sev-success', 'Ideal'], negrito: ['sev-info', 'Excesso'] };
  var estSort = { key: 'dias', dir: 1 }, estQuery = '';
  var EST_PAGE = 10, estPage = 1;
  function decorateStock(tbody) {
    estPage = 1;
    var rows = $$('tr', tbody);
    var zeros = 0, total = 0;
    rows.forEach(function (tr) {
      var b = tr.querySelector('.dias-badge');
      if (!b) return;
      total++;
      var dias = parseInt(b.textContent, 10) || 0;
      if (dias === 0) zeros++;
      tr.setAttribute('data-dias', String(dias));
      var nm = tr.querySelector('.resumo-prod-name');
      tr.setAttribute('data-nome', nm ? nm.textContent.trim().toLowerCase() : '');
      if (!b.getAttribute('data-sev')) {
        var k = Object.keys(SEV).filter(function (c) { return b.classList.contains(c); })[0];
        if (k) {
          b.setAttribute('data-sev', k);
          b.classList.add(SEV[k][0]);
          b.innerHTML = '<span class="sev-dot" aria-hidden="true"></span><span class="sev-n">' + Fmt.int(dias) + ' dias</span><span class="sev-l">' + SEV[k][1] + '</span>';
        }
      }
      var sku = tr.querySelector('.resumo-sku-code');
      if (sku && !sku.getAttribute('data-v2')) { sku.setAttribute('data-v2', '1'); sku.textContent = sku.textContent.replace(/^SKU:\s*/, 'SKU '); }
    });
    var note = $('#v2-est-note'), head = $('#total-skus-count');
    var headDias = head ? parseInt(head.textContent, 10) || 0 : 0;
    if (note) note.hidden = !(total > 0 && zeros === total && headDias > 0);
    applyStock(tbody);
  }
  function applyStock(tbody) {
    var rows = $$('tr[data-dias]', tbody);
    rows.sort(function (a, b) {
      if (estSort.key === 'nome') return a.getAttribute('data-nome').localeCompare(b.getAttribute('data-nome'), 'pt-BR') * estSort.dir;
      return ((+a.getAttribute('data-dias')) - (+b.getAttribute('data-dias'))) * estSort.dir;
    });
    var matched = [];
    rows.forEach(function (r) {
      if (!estQuery || r.textContent.toLowerCase().indexOf(estQuery) >= 0) matched.push(r);
      r.hidden = true;
      tbody.appendChild(r);
    });
    var pages = Math.max(1, Math.ceil(matched.length / EST_PAGE));
    if (estPage > pages) estPage = pages;
    var from = (estPage - 1) * EST_PAGE;
    matched.slice(from, from + EST_PAGE).forEach(function (r) { r.hidden = false; });
    var empty = $('#v2-est-empty');
    if (empty) empty.hidden = !(rows.length && !matched.length);
    var pager = $('#v2-est-pager');
    if (pager) {
      pager.hidden = pages <= 1;
      $('.est-pager-info', pager).textContent = (from + 1) + '–' + Math.min(from + EST_PAGE, matched.length) + ' de ' + matched.length;
      $('.est-pager-pos', pager).textContent = estPage + ' / ' + pages;
      $('[data-pg="prev"]', pager).disabled = estPage <= 1;
      $('[data-pg="next"]', pager).disabled = estPage >= pages;
    }
  }
  function initStock() {
    var tbody = $('#tbody-estoque-resumo');
    if (!tbody) return;
    var mo = new MutationObserver(function () { mo.disconnect(); decorateStock(tbody); mo.observe(tbody, { childList: true }); });
    mo.observe(tbody, { childList: true });
    function rerun() { mo.disconnect(); applyStock(tbody); mo.observe(tbody, { childList: true }); }
    var wrap = tbody.closest('.estoque-resumo-wrap');
    if (wrap && !$('#v2-est-pager')) {
      wrap.insertAdjacentHTML('afterend',
        '<nav class="est-pager" id="v2-est-pager" aria-label="Páginas da tabela de estoque" hidden>' +
          '<span class="est-pager-info" aria-live="polite"></span>' +
          '<div class="est-pager-btns">' +
            '<button type="button" data-pg="prev" aria-label="Página anterior"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg></button>' +
            '<span class="est-pager-pos"></span>' +
            '<button type="button" data-pg="next" aria-label="Próxima página"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg></button>' +
          '</div>' +
        '</nav>');
      $('#v2-est-pager').addEventListener('click', function (e) {
        var b = e.target.closest('[data-pg]');
        if (!b || b.disabled) return;
        estPage += b.getAttribute('data-pg') === 'next' ? 1 : -1;
        rerun();
        if (wrap) wrap.scrollTop = 0;
      });
    }
    var s = $('#v2-est-search');
    if (s) s.addEventListener('input', function () { estQuery = s.value.trim().toLowerCase(); estPage = 1; rerun(); });
    $$('[data-sort]').forEach(function (th) {
      var btn = th.querySelector('button');
      (btn || th).addEventListener('click', function () {
        var k = th.getAttribute('data-sort');
        estSort.dir = estSort.key === k ? -estSort.dir : 1; estSort.key = k; estPage = 1;
        $$('[data-sort]').forEach(function (x) { x.setAttribute('aria-sort', x === th ? (estSort.dir === 1 ? 'ascending' : 'descending') : 'none'); });
        mo.disconnect(); applyStock(tbody); mo.observe(tbody, { childList: true });
      });
    });
  }

  /* ── Tabelas viram cards no celular: rótulos por coluna ── */
  function labelTable(table) {
    if (!table) return;
    // Cabeçalhos em CAIXA ALTA viram "Primeira maiúscula" (mantendo R$ e CX)
    function nice(t) {
      t = t.trim();
      if (t.length > 3 && t === t.toUpperCase() && /[A-ZÀ-Ú]/.test(t)) t = (t.charAt(0) + t.slice(1).toLowerCase()).replace('(r$)', '(R$)').replace('(cx)', '(CX)');
      return t;
    }
    function labelRows(tbl, skipDrill) {
      if (!tbl.tHead || !tbl.tBodies[0]) return;
      var heads = Array.prototype.map.call(tbl.tHead.rows[0].cells, function (th) { return nice(th.textContent); });
      Array.prototype.forEach.call(tbl.tBodies[0].rows, function (tr) {
        if (skipDrill && tr.classList.contains('grade-drilldown-row')) return;
        Array.prototype.forEach.call(tr.cells, function (td, i) { if (heads[i] && !td.hasAttribute('data-label')) td.setAttribute('data-label', heads[i]); });
      });
    }
    function apply() {
      labelRows(table, true);
      $$('.drilldown-subtable', table).forEach(function (st) { labelRows(st, false); });
    }
    var tb = table.querySelector('tbody');
    if (tb) new MutationObserver(apply).observe(tb, { childList: true });
    apply();
  }

  /* ── Skeleton na primeira carga + estado de erro com "Tentar novamente" ── */
  function initStates() {
    var origHide = window.hideGlobalLoader;
    if (typeof origHide === 'function') {
      window.hideGlobalLoader = function () { document.body.classList.remove('v2-loading'); return origHide.apply(this, arguments); };
    }
    setTimeout(function () { document.body.classList.remove('v2-loading'); }, 25000);
    var err = $('#v2-error');
    var origFetch = window.fetch;
    window.fetch = function (url) {
      var p = origFetch.apply(this, arguments);
      var u = typeof url === 'string' ? url : (url && url.url) || '';
      if (u.indexOf('/api/kpi') === -1) return p;
      return p.then(function (res) {
        if (err && res.ok) err.hidden = true;
        if (!res.ok) {
          if (err) err.hidden = false;
          document.body.classList.remove('v2-loading');
        }
        return res;
      }, function (e) {
        if (e && (e.name === 'AbortError' || e.message === 'Failed to fetch' && document.hidden)) {
          return Promise.reject(e);
        }
        if (err) err.hidden = false;
        document.body.classList.remove('v2-loading');
        throw e;
      });
    };
    var retry = $('#v2-retry');
    if (retry) retry.addEventListener('click', function () { if (err) err.hidden = true; window.triggerDashboardRefresh(0); });
  }

  /* ── Faixa de simulação / admin: ações no menu ── */
  function watchAdminBar() {
    var mo = new MutationObserver(function () {
      var bar = $('#admin-mode-bar');
      if (bar) { document.body.classList.add('is-admin'); syncAdminItems(); }
    });
    mo.observe(document.body, { childList: true });
    if ($('#admin-mode-bar')) { document.body.classList.add('is-admin'); syncAdminItems(); }
    if ($('#sim-banner')) document.body.classList.add('is-simulating');
  }

  /* ── Modo distribuidor: "Olá, <nome>" no cabeçalho (admin não vê; ele tem o seletor na faixa) ── */
  function initHello() {
    var src = $('#greeting-name'), box = $('#hdr-hello'), dst = $('#hdr-hello-name');
    if (!src || !box || !dst) return;
    function paint() {
      var admin = document.body.classList.contains('is-admin') && !document.body.classList.contains('is-simulating');
      var name = src.textContent.trim();
      var ok = !admin && name && !/^Carregando/.test(name);
      box.hidden = !ok;
      if (ok) { dst.textContent = name; box.title = src.title || name; }
    }
    new MutationObserver(paint).observe(src, { childList: true, characterData: true, subtree: true });
    new MutationObserver(paint).observe(document.body, { attributes: true, attributeFilter: ['class'] });
    paint();
  }

  /* ── Início: status ao vivo espelha o "Atualizado há…" do cabeçalho ── */
  function initInicioStatus() {
    var src = $('#v2-sync-rel'), dst = $('#inicio-sync');
    if (!src || !dst) return;
    function paint() { var t = src.textContent.trim(); if (/^Atualizado/.test(t)) dst.textContent = t.replace(/^Atualizado/, 'Dados atualizados'); }
    new MutationObserver(paint).observe(src, { childList: true, characterData: true, subtree: true });
    paint();
  }

  /* ── Página aberta pela raiz: começa na aba Início ── */
  function initStartTab() {
    var root = document.documentElement;
    if (root.getAttribute('data-start') !== 'inicio') return;
    if (typeof window.activateTab === 'function') window.activateTab('inicio');
    root.removeAttribute('data-start');
  }

  /* ── Sidebar Estilo DNA de Vendas ── */
  function initPortalSidebar() {
    var sidebar = $('#portal-sidebar');
    if (!sidebar) return;
    initNavExpand();

    var navItems = $$('.sp-nav-item', sidebar);
    navItems.forEach(function (item) {
      item.addEventListener('click', function (e) {
        var tabId = item.getAttribute('data-tab');
        if (tabId) {
          e.preventDefault();
          navItems.forEach(function (x) { x.classList.remove('active'); });
          item.classList.add('active');

          if (typeof window.activateTab === 'function') {
            window.activateTab(tabId);
          }
          var targetTabBtn = $('.kpi-header .tab[data-tab="' + tabId + '"]');
          if (targetTabBtn) targetTabBtn.click();
        }
      });
    });
  }

  /* ── Menu lateral: trilho compacto ou expandido com os nomes completos (mesmo modelo do Compras 360) ── */
  function initNavExpand() {
    var toggle = $('#nav-expand');
    if (!toggle) return;
    var expanded = false;
    try { expanded = localStorage.getItem('portal_nav_expanded') === '1'; } catch (e) {}
    function update() {
      var label = expanded ? 'Recolher menu' : 'Expandir menu';
      document.body.classList.toggle('nav-expanded', expanded);
      toggle.setAttribute('aria-expanded', String(expanded));
      toggle.setAttribute('aria-label', label);
      toggle.title = label;
    }
    toggle.addEventListener('click', function () {
      expanded = !expanded;
      try { localStorage.setItem('portal_nav_expanded', expanded ? '1' : '0'); } catch (e) {}
      update();
      // Gráficos e o ajuste à tela recalculam com a nova largura
      setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 220);
    });
    update();
  }

  /* ── Painel Retrátil de Filtros à Direita (Filter Drawer) ── */
  function initFilterDrawer() {
    var drawer = $('#portal-filter-drawer');
    var openBtn = $('#open-filter-drawer-btn');
    var closeBtn = $('#close-filter-drawer-btn');
    var closeFooterBtn = $('#pfd-close-footer-btn');
    var applyBtn = $('#pfd-apply-btn') || $('#v2-sheet-apply');
    var scrim = $('#v2-scrim');
    var periodChip = $('#afb-val-periodo');
    var modeChip = $('#afb-val-mode');
    if (!drawer) return;

    function openDrawer() {
      drawer.classList.add('is-open');
      if (scrim) {
        scrim.hidden = false;
        scrim.classList.add('is-visible');
      }
      document.body.classList.add('no-scroll');
      if (closeBtn) closeBtn.focus();
    }

    function closeDrawer() {
      drawer.classList.remove('is-open');
      if (scrim) {
        scrim.classList.remove('is-visible');
        setTimeout(function () { if (!drawer.classList.contains('is-open')) scrim.hidden = true; }, 250);
      }
      document.body.classList.remove('no-scroll');
    }

    function toggleDrawer() {
      if (drawer.classList.contains('is-open')) {
        closeDrawer();
      } else {
        openDrawer();
      }
    }

    if (openBtn) openBtn.addEventListener('click', toggleDrawer);
    if (periodChip) periodChip.addEventListener('click', openDrawer);
    if (modeChip) modeChip.addEventListener('click', openDrawer);
    if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
    if (closeFooterBtn) closeFooterBtn.addEventListener('click', closeDrawer);

    var allCloseButtons = document.querySelectorAll('#close-filter-drawer-btn, #pfd-close-footer-btn, [data-sheet-close]');
    allCloseButtons.forEach(function (btn) {
      btn.addEventListener('click', closeDrawer);
    });

    function handleApply() {
      if (typeof window.triggerDashboardRefresh === 'function') {
        window.triggerDashboardRefresh(0);
      }
      closeDrawer();
    }

    var sheetApplyBtn = $('#v2-sheet-apply');
    if (sheetApplyBtn) sheetApplyBtn.addEventListener('click', handleApply);
    var pfdApplyBtn = $('#pfd-apply-btn');
    if (pfdApplyBtn) pfdApplyBtn.addEventListener('click', handleApply);

    if (scrim) {
      scrim.addEventListener('click', function () {
        closeDrawer();
        var sidebar = $('#portal-sidebar');
        if (sidebar && sidebar.classList.contains('mobile-open')) {
          sidebar.classList.remove('mobile-open');
        }
      });
    }

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && drawer.classList.contains('is-open')) {
        closeDrawer();
      }
    });
  }

  /* ── Painel de filtros: lista aberta sempre inteira à vista (rola o painel até ela) ── */
  function offsetIn(el, anc) {
    var y = 0;
    while (el && el !== anc) { y += el.offsetTop; el = el.offsetParent; }
    return y;
  }
  function initDrawerDropdowns() {
    var drawer = $('#portal-filter-drawer');
    if (!drawer) return;
    drawer.addEventListener('click', function (e) {
      var cs = e.target.closest('.custom-select');
      if (!cs || e.target.closest('.options-container')) return;
      setTimeout(function () {
        var oc = cs.querySelector('.options-container'), body = drawer.querySelector('.pfd-body');
        if (!cs.classList.contains('active') || !oc || !body) return;
        // Medidas em px de layout (offsetTop), imunes ao zoom do ajuste de tela; scrollIntoView erra com zoom
        var top = offsetIn(oc, drawer) - offsetIn(body, drawer), bottom = top + oc.offsetHeight + 12;
        if (bottom > body.scrollTop + body.clientHeight) body.scrollTo({ top: bottom - body.clientHeight, behavior: 'smooth' });
      }, 60);
    }, true); // captura: o seletor interrompe a propagação do clique
  }

  /* ── Barra Resumo de Filtros Ativos (Active Filters Bar) ── */
  function syncActiveFiltersBar() {
    var chipPeriodo = $('#afb-val-periodo');
    var chipMode = $('#afb-val-mode');
    var badgeCount = $('#afb-count-badge') || $('#afb-count');
    var toggleValVol = $('#toggleValVol');

    function getSelected(id) {
      if (typeof window.getSafeSelectedValues === 'function') {
        var v = window.getSafeSelectedValues(id);
        if (Array.isArray(v) && v.length > 0) return v;
      }
      var el = document.getElementById(id);
      if (el && typeof el.getSelectedValues === 'function') {
        var v = el.getSelectedValues();
        if (Array.isArray(v) && v.length > 0) return v;
      }
      return [];
    }

    function getInputText(id) {
      var inp = document.querySelector('#' + id + ' .search-input');
      return (inp && inp.value) ? inp.value.trim() : '';
    }

    function update() {
      try {
        if (chipPeriodo) {
          var anos = getSelected('select-ano');
          var meses = getSelected('select-mes');

          var anoStr = '';
          if (anos.length > 0) {
            anoStr = anos.join(', ');
          } else {
            var rawAno = getInputText('select-ano');
            anoStr = (rawAno && rawAno !== 'Todos') ? rawAno : new Date().getFullYear().toString();
          }

          var mesStr = '';
          if (meses.length === 1) {
            var mNum = parseInt(meses[0], 10);
            var mNames = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
            mesStr = (mNum >= 1 && mNum <= 12) ? mNames[mNum - 1] : meses[0];
          } else if (meses.length > 1) {
            mesStr = meses.length + ' meses';
          } else {
            var rawMes = getInputText('select-mes');
            if (rawMes && rawMes !== 'Todos') {
              mesStr = rawMes;
            }
          }

          var periodoFinal = anoStr + (mesStr ? ' / ' + mesStr : '');
          chipPeriodo.innerHTML = '<span class="afb-k">Período: </span><strong>' + periodoFinal + '</strong>';
        }

        if (chipMode) {
          var isVol = toggleValVol ? toggleValVol.checked : false;
          chipMode.innerHTML = '<span class="afb-k">Exibição: </span><strong>' + (isVol ? 'Volume (Físico)' : 'Valor (R$)') + '</strong>';
        }

        if (badgeCount) {
          var count = 0;
          ['select-categoria', 'select-produto', 'select-sku', 'select-pedido', 'select-dia', 'select-semana'].forEach(function (id) {
            var vals = getSelected(id);
            if (vals && vals.length > 0) count += vals.length;
          });
          badgeCount.textContent = count;
          badgeCount.style.display = count > 0 ? 'inline-flex' : 'none';
        }
        renderFilterChips();
        syncQuick();
      } catch (err) {
        console.warn('Erro ao atualizar barra de filtros:', err);
      }
    }

    // Chips removíveis: um por filtro aplicado (período e exibição têm chip próprio)
    var CHIP_FILTERS = FILTERS.filter(function (f) { return f[0] !== 'select-mes' && f[0] !== 'select-ano'; });
    var X_ICON = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';
    function defaultPeriod() {
      var n = new Date();
      return { ano: [String(n.getFullYear())], mes: [String(n.getMonth() + 1).padStart(2, '0')] };
    }
    function sameSet(a, b) { return a.length === b.length && a.every(function (v) { return b.indexOf(String(v)) >= 0; }); }
    function periodIsDefault() {
      var p = defaultPeriod();
      return sameSet(getSelected('select-ano').map(String), p.ano) && sameSet(getSelected('select-mes').map(String), p.mes);
    }
    function renderFilterChips() {
      var box = $('#afb-chips-container');
      if (!box) return;
      $$('.afb-chip-filter', box).forEach(function (c) { c.remove(); });
      var any = false;
      CHIP_FILTERS.forEach(function (f) {
        var vals = getSelected(f[0]);
        if (!vals.length) return;
        any = true;
        var labels = vals.map(function (v) { return chipLabel(f[0], v); });
        var shown = labels.slice(0, 2).join(', ') + (labels.length > 2 ? ' +' + (labels.length - 2) : '');
        var chip = document.createElement('span');
        chip.className = 'afb-chip afb-chip-filter';
        chip.title = f[1] + ': ' + labels.join(', ');
        chip.innerHTML = Fmt.esc(f[1]) + ': <strong>' + Fmt.esc(shown) + '</strong>' +
          '<button type="button" class="afb-chip-x" data-clear="' + f[0] + '" aria-label="Remover filtro ' + Fmt.esc(f[1]) + '" title="Remover filtro">' + X_ICON + '</button>';
        box.appendChild(chip);
      });
      var pDef = periodIsDefault();
      var hasDist = getSelected('qf-dist').length > 0;
      var px = $('#afb-chip-periodo .afb-chip-x');
      if (px) px.hidden = pDef;
      var reset = $('#afb-reset');
      if (reset) reset.hidden = !any && pDef && !hasDist;
    }
    function resetPeriod() {
      var p = defaultPeriod(), a = $('#select-ano'), m = $('#select-mes');
      if (a && a.setSelected) a.setSelected(p.ano);
      if (m && m.setSelected) m.setSelected(p.mes);
    }
    function applyFilters() {
      update();
      if (typeof window.triggerDashboardRefresh === 'function') window.triggerDashboardRefresh(0);
    }
    var afb = $('#active-filters-bar');
    if (afb) afb.addEventListener('click', function (e) {
      var x = e.target.closest('[data-clear]');
      if (x) {
        var id = x.getAttribute('data-clear');
        if (id === 'periodo') resetPeriod();
        else { var el = document.getElementById(id); if (el && el.clear) el.clear(); }
        applyFilters();
        return;
      }
      if (e.target.closest('#afb-reset')) {
        CHIP_FILTERS.forEach(function (f) { var el = document.getElementById(f[0]); if (el && el.clear) el.clear(); });
        resetPeriod();
        if (window.AdminMode && typeof window.AdminMode.clear === 'function') window.AdminMode.clear();
        applyFilters();
      }
    });

    // Filtros rápidos (Ano / Mês) na faixa: o mesmo seletor do painel (makeCustomSelect), espelhado nos dois sentidos
    var QF = [['qf-ano', 'select-ano'], ['qf-mes', 'select-mes']];
    function optionsOf(id) {
      return $$('#' + id + ' .option-item:not(.select-all-item) input').map(function (i) {
        var lab = i.parentElement.querySelector('span');
        var l = lab ? lab.textContent.trim() : i.value;
        if (id === 'select-mes') l = Fmt.MONTHS_SHORT[parseInt(i.value, 10) - 1] || l;
        return { value: i.value, label: l };
      });
    }
    function syncQuick() {
      QF.forEach(function (q) {
        var qs = document.getElementById(q[0]);
        if (!qs || typeof qs.populate !== 'function') return;
        var opts = optionsOf(q[1]), key = JSON.stringify(opts), cur = getSelected(q[1]).map(String);
        if (qs.getAttribute('data-opts') !== key) { qs.setAttribute('data-opts', key); qs.populate(opts, cur); }
        else if (typeof qs.setSelected === 'function') qs.setSelected(cur);
      });
    }
    QF.forEach(function (q) {
      var qs = document.getElementById(q[0]);
      if (!qs || typeof window.makeCustomSelect !== 'function') return;
      window.makeCustomSelect(q[0], 'Todos');
      qs.addEventListener('change', function (e) {
        if (e.target !== qs) return;
        var el = document.getElementById(q[1]);
        if (!el) return;
        var v = qs.getSelectedValues();
        if (!v.length) el.clear(); else if (el.setSelected) el.setSelected(v);
        applyFilters();
      });
      var oc = document.querySelector('#' + q[1] + ' .options-container');
      if (oc) new MutationObserver(syncQuick).observe(oc, { childList: true });
    });
    syncQuick();

    // Escuta mudanças nos filtros e inputs
    document.querySelectorAll('.custom-select').forEach(function (cs) {
      cs.addEventListener('change', update);
      var inp = cs.querySelector('.search-input');
      if (inp) inp.addEventListener('input', update);
    });
    if (toggleValVol) toggleValVol.addEventListener('change', update);

    var chipP = $('#afb-chip-periodo');
    var chipM = $('#afb-chip-mode');
    var drawer = $('#portal-filter-drawer');
    if (chipP && drawer) chipP.addEventListener('click', function(e) { if (!e.target.closest('.afb-chip-x')) drawer.classList.add('is-open'); });
    if (chipM && drawer) chipM.addEventListener('click', function() { drawer.classList.add('is-open'); });

    window.updateActiveFiltersBar = update;

    update();
    setTimeout(update, 200);
    setTimeout(update, 600);
    setTimeout(update, 1500);
    setTimeout(update, 3000);
  }

  function init() {
    initUserMenu();
    initCommand();
    initSync();
    initChips();
    initFilterSheet();
    initPortalSidebar();
    initFilterDrawer();
    initDrawerDropdowns();
    syncActiveFiltersBar();
    bindSegment('toggleValVol', 'lbl-valor', 'lbl-volume');
    bindSegment('toggleChartMode', 'lbl-chart-sellin', 'lbl-chart-sellout');
    initPopovers();
    initNav();
    initBottomNav();
    initStartTab();
    initInicioStatus();
    initHello();
    initRange();
    initStock();
    labelTable($('.grade-table'));
    labelTable($('#modal-estoque-expand .modal-table'));
    labelTable($('#modal-positivacao-expand .modal-table'));
    initStates();
    watchAdminBar();
    syncAdminItems();
  }
  /* Script fica no fim do <body>: o DOM já existe. Inicializa já, antes do
     DOMContentLoaded, para envolver fetch/loader antes da primeira carga de dados. */
  init();
})();
