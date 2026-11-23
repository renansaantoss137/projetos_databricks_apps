/**
 * PORTAL COMPRAS — Padrão D&A: Auto-Fit de Tela e Seletor de Escala
 *
 * - Desktop (>= 1025px com mouse/trackpad): aplica zoom no <body> para caber em notebooks 13"/14"
 *   mantendo 100% em monitores grandes. Seletor "Ajuste de Visualização" dentro do menu do usuário.
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

    var select = document.getElementById('dna-scale-select');
    if (select) select.value = scaleSetting;
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
    var panel = document.getElementById('daAppMenuPanel');
    if (!panel || document.getElementById('dna-scale-picker')) { applyScale(getSavedScale()); return; }
    var picker = document.createElement('div');
    picker.id = 'dna-scale-picker';
    picker.className = 'dna-scale-picker da-menu-row';
    var label = document.createElement('label');
    label.htmlFor = 'dna-scale-select';
    label.textContent = 'Ajuste de visualização';
    var select = document.createElement('select');
    select.id = 'dna-scale-select';
    select.setAttribute('aria-label', 'Ajuste de visualização');
    [['auto','Automático'],['100','100% · Padrão'],['85','85% · Compacto'],['75','75% · Notebook'],['67','67% · Compacto']].forEach(function (entry) {
      var option = document.createElement('option'); option.value = entry[0]; option.textContent = entry[1]; select.appendChild(option);
    });
    select.value = getSavedScale();
    select.addEventListener('change', function () { setSavedScale(this.value); applyScale(this.value); });
    picker.appendChild(label); picker.appendChild(select);
    panel.insertBefore(picker, document.getElementById('daBtnLogout'));
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
