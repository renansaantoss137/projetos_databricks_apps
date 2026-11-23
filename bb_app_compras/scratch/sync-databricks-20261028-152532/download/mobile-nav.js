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

  function init() { build(); mobileDefaults(); }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
