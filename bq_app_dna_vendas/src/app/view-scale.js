/**
 * DNA DE VENDAS | Grupo Bimbo Brasil
 * Gerenciador de Escala e Adaptação Automática de Tela (Auto-Fit)
 * Permite exibição completa do dashboard sem barra de rolagem em telas de 13", 14" e 24"+
 */

(function () {
  'use strict';

  var STORAGE_KEY = 'bimbo_dna_scale';
  var BASE_HEIGHT = 885; // Altura de referência do dashboard completo em desktop
  var MIN_SCALE = 0.60;
  var MAX_SCALE = 1.0;

  function isHomePage() {
    return document.body && document.body.classList.contains('home');
  }

  function getBaseHeight() {
    return isHomePage() ? 740 : BASE_HEIGHT;
  }

  function getSavedScale() {
    if (isHomePage()) return 'auto';
    return localStorage.getItem(STORAGE_KEY) || 'auto';
  }

  function setSavedScale(val) {
    if (isHomePage()) return;
    try {
      localStorage.setItem(STORAGE_KEY, val);
    } catch (e) {}
  }

  function calculateAutoScale() {
    var winH = window.innerHeight || document.documentElement.clientHeight;
    var baseH = getBaseHeight();
    // Se a tela tem altura suficiente, mantém 100%
    if (winH >= baseH) {
      return 1.0;
    }
    // Para telas menores, calcula o percentual para caber sem barra de rolagem
    var availableH = winH - 10;
    var scale = availableH / baseH;
    return Math.min(MAX_SCALE, Math.max(MIN_SCALE, Math.round(scale * 100) / 100));
  }

  function applyScale(scaleSetting) {
    var numericScale = 1.0;
    if (scaleSetting === 'auto') {
      numericScale = calculateAutoScale();
    } else {
      var parsed = parseFloat(scaleSetting);
      numericScale = isNaN(parsed) ? 1.0 : (parsed / 100);
    }

    // Aplica no body via CSS zoom
    document.body.style.zoom = numericScale;
    document.documentElement.style.setProperty('--dna-scale', String(numericScale));
    document.body.style.setProperty('--dna-scale', String(numericScale));
    document.documentElement.style.minHeight = '';
    document.body.style.minHeight = '';

    // Se a escala for reduzida, ativa classe auxiliar para ajustes finos de layout
    if (numericScale < 0.85) {
      document.body.classList.add('dna-compact-view');
    } else {
      document.body.classList.remove('dna-compact-view');
    }

    updateButtonLabel(scaleSetting, numericScale);

    window.dispatchEvent(new CustomEvent('bimbo:scaleChange', { 
      detail: { setting: scaleSetting, effectiveScale: numericScale } 
    }));
  }

  function updateButtonLabel(setting, effectiveScale) {
    var labelEl = document.getElementById('v2-scale-label');
    if (labelEl) {
      if (setting === 'auto') {
        labelEl.textContent = 'Auto (' + Math.round(effectiveScale * 100) + '%)';
      } else {
        labelEl.textContent = setting + '%';
      }
    }

    // Atualiza marcação ativa nas opções
    var options = document.querySelectorAll('.scale-option');
    options.forEach(function (opt) {
      var optVal = opt.getAttribute('data-scale');
      if (optVal === setting) {
        opt.classList.add('active');
        opt.setAttribute('aria-selected', 'true');
      } else {
        opt.classList.remove('active');
        opt.setAttribute('aria-selected', 'false');
      }
    });
  }

  function initScaleUI() {
    // Modo automático sempre ativo em segundo plano, sem poluir o menu do usuário
    applyScale('auto');
  }

  // Redimensionamento de janela (sempre recalcula a escala ideal)
  var resizeTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      applyScale('auto');
    }, 100);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initScaleUI);
  } else {
    initScaleUI();
  }

  // Executa cálculo imediato para evitar pulo de layout
  var initialNum = calculateAutoScale();
  if (isNaN(initialNum)) initialNum = 1.0;
  document.body.style.zoom = initialNum;
  document.documentElement.style.setProperty('--dna-scale', String(initialNum));
  document.body.style.setProperty('--dna-scale', String(initialNum));
})();
