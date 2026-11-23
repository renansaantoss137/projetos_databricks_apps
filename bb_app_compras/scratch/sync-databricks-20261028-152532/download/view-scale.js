/**
 * PORTAL COMPRAS — Padrão D&A: Auto-Fit de Tela e Seletor de Escala
 *
 * - Desktop (>= 1025px com mouse/trackpad): aplica zoom no <body> para caber em notebooks 13"/14"
 *   mantendo 100% em monitores grandes. Seletor "Ajuste de Visualização" no cabeçalho (antes do menu do usuário).
 * - Tablet / celular: escala SEMPRE 100% (o layout responsivo cuida da adaptação) e o seletor fica oculto.
 * - Carregar no <head> (antes do body) para evitar flicker.
 * - API: window.dnaScale() -> escala numérica atual (1 quando sem zoom). Use para corrigir coordenadas
 *   de getBoundingClientRect/pageX ao posicionar popovers e redimensionar colunas.
 */
(function () {
  'use strict';
  var STORAGE_KEY = 'bimbo_dna_scale';
  var BASE_HEIGHT = 885;            // Altura ideal do dashboard em desktop
  var MIN_SCALE = 0.58;
  var VALID = ['auto', '100', '85', '75', '67'];
  var DESKTOP_MQ = '(min-width: 1025px) and (any-pointer: fine)';
  var root = document.documentElement;
  var current = 1;

  // Regra base injetada imediatamente (antes do <body> existir) para evitar flicker
  (function injectBase() {
    if (document.getElementById('dna-scale-base')) return;
    var s = document.createElement('style');
    s.id = 'dna-scale-base';
    s.textContent = 'html.dna-scaled body{zoom:var(--dna-scale,1);min-height:var(--dna-vh,100vh);}';
    (document.head || root).appendChild(s);
  })();

  function getSavedScale() {
    var v = null;
    try { v = localStorage.getItem(STORAGE_KEY); } catch (e) {}
    return VALID.indexOf(v) >= 0 ? v : 'auto';
  }
  function setSavedScale(val) { try { localStorage.setItem(STORAGE_KEY, val); } catch (e) {} }

  function isDesktop() {
    return !window.matchMedia || window.matchMedia(DESKTOP_MQ).matches;
  }

  function winHeight() {
    return window.innerHeight || root.clientHeight || 800;
  }

  function calculateAutoScale() {
    var winH = winHeight();
    if (winH >= BASE_HEIGHT) return 1.0;
    return Math.min(1.0, Math.max(MIN_SCALE, Math.round(((winH - 10) / BASE_HEIGHT) * 100) / 100));
  }

  function resolveScale(setting) {
    if (!isDesktop()) return 1.0;
    if (setting === 'auto') return calculateAutoScale();
    return parseFloat(setting) / 100 || 1.0;
  }

  function applyScale(scaleSetting) {
    var desktop = isDesktop();
    var numericScale = resolveScale(scaleSetting);
    var changed = numericScale !== current;
    current = numericScale;

    root.classList.toggle('dna-scale-desktop', desktop);
    root.classList.toggle('dna-scaled', numericScale !== 1);
    root.style.setProperty('--dna-scale', String(numericScale));
    // Altura útil em px "internos" do body com zoom (px são escalados pelo zoom; vh pode não ser)
    root.style.setProperty('--dna-vh', Math.ceil(winHeight() / numericScale) + 'px');

    var label = document.getElementById('v2-scale-label');
    if (label) {
      label.textContent = scaleSetting === 'auto'
        ? 'Auto (' + Math.round(numericScale * 100) + '%)'
        : scaleSetting + '%';
    }
    var opts = document.querySelectorAll('.scale-option');
    for (var i = 0; i < opts.length; i++) {
      var on = opts[i].getAttribute('data-scale') === scaleSetting;
      opts[i].classList.toggle('active', on);
      opts[i].setAttribute('aria-checked', on ? 'true' : 'false');
    }

    if (changed) {
      try { window.dispatchEvent(new CustomEvent('dnaScaleChange', { detail: { scale: numericScale, setting: scaleSetting } })); } catch (e) {}
    }
  }

  function initScaleUI() {
    var menuContainer = document.getElementById('app-menu-container');
    if (!menuContainer || document.getElementById('dna-scale-picker')) { applyScale(getSavedScale()); return; }

    var picker = document.createElement('div');
    picker.className = 'dna-scale-picker';
    picker.id = 'dna-scale-picker';
    picker.innerHTML =
      '<button type="button" class="dna-scale-btn" id="v2-scale-btn" aria-haspopup="true" aria-expanded="false" aria-controls="v2-scale-dropdown" title="Ajuste de Visualização">' +
        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>' +
        '<span id="v2-scale-label">Auto</span>' +
        '<svg class="dna-scale-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>' +
      '</button>' +
      '<div class="dna-scale-dropdown" id="v2-scale-dropdown" role="menu" hidden>' +
        '<div class="scale-dd-title">Ajuste de Visualização</div>' +
        '<button type="button" role="menuitemradio" class="scale-option" data-scale="auto"><div class="scale-opt-info"><span class="scale-opt-title">Automático (Ajustar à Tela)</span><span class="scale-opt-desc">Calcula a escala ideal para a altura da janela</span></div><span class="scale-badge">Recomendado</span></button>' +
        '<div class="scale-sep" role="separator"></div>' +
        '<button type="button" role="menuitemradio" class="scale-option" data-scale="100"><div class="scale-opt-info"><span class="scale-opt-title">100% · Padrão</span><span class="scale-opt-desc">Monitores de 24"+</span></div></button>' +
        '<button type="button" role="menuitemradio" class="scale-option" data-scale="85"><div class="scale-opt-info"><span class="scale-opt-title">85% · Compacto</span><span class="scale-opt-desc">Telas médias ou divididas</span></div></button>' +
        '<button type="button" role="menuitemradio" class="scale-option" data-scale="75"><div class="scale-opt-info"><span class="scale-opt-title">75% · Notebook 14"</span><span class="scale-opt-desc">Visualização equilibrada</span></div></button>' +
        '<button type="button" role="menuitemradio" class="scale-option" data-scale="67"><div class="scale-opt-info"><span class="scale-opt-title">67% · Notebook 13"</span><span class="scale-opt-desc">Cockpit total em telas pequenas</span></div></button>' +
      '</div>';

    menuContainer.parentNode.insertBefore(picker, menuContainer);

    var btn = document.getElementById('v2-scale-btn');
    var dd = document.getElementById('v2-scale-dropdown');

    function setOpen(open) {
      dd.hidden = !open;
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    btn.addEventListener('click', function (e) { e.stopPropagation(); setOpen(dd.hidden); });
    document.addEventListener('click', function (e) { if (!picker.contains(e.target)) setOpen(false); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !dd.hidden) { setOpen(false); btn.focus(); }
    });

    var opts = dd.querySelectorAll('.scale-option');
    for (var i = 0; i < opts.length; i++) {
      opts[i].addEventListener('click', function () {
        var val = this.getAttribute('data-scale');
        setSavedScale(val);
        applyScale(val);
        setOpen(false);
      });
    }

    applyScale(getSavedScale());
  }

  // Reaplica em qualquer resize (auto recalcula; manual precisa respeitar a troca desktop <-> mobile)
  var resizeTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { applyScale(getSavedScale()); }, 100);
  });

  // Sincroniza entre abas
  window.addEventListener('storage', function (e) {
    if (e.key === STORAGE_KEY) applyScale(getSavedScale());
  });

  window.dnaScale = function () { return current || 1; };
  window.DnaScale = { apply: applyScale, get: window.dnaScale, saved: getSavedScale };

  // Execução imediata (no <head>) para evitar flicker
  applyScale(getSavedScale());

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initScaleUI);
  } else {
    initScaleUI();
  }
})();
