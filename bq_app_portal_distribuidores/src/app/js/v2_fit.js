/* Zoom de tela desativado — mantém escala 100% nativa */
(function () {
  'use strict';
  try { localStorage.removeItem('v2-zoom'); } catch (e) {}
  var root = document.documentElement;
  root.classList.remove('v2-zoomed', 'v2-fit');
  root.style.removeProperty('--v2-zoom');
  window.v2Zoom = function () { return 1; };
})();
