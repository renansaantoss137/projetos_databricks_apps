/**
 * DNA DE VENDAS | Grupo Bimbo Brasil
 * Menu de Usuário & Gestão de Tema idêntico ao Portal Distribuidores (v2)
 */

(function () {
  'use strict';

  var THEME_KEY = 'bimbo_theme';

  function currentTheme() {
    var saved = localStorage.getItem(THEME_KEY);
    if (saved) return saved;
    var t = document.documentElement.getAttribute('data-theme');
    if (t) return t;
    return 'light';
  }

  function syncLogos(t) {
    var dnas = document.querySelectorAll('.home-dna, .brand-dna');
    dnas.forEach(function (img) {
      if (t === 'light') {
        img.src = 'logo-dna-dark.png';
      } else {
        img.src = 'logo-dna.png';
      }
    });
  }

  function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    if (document.body) document.body.setAttribute('data-theme', t);
    try { localStorage.setItem(THEME_KEY, t); } catch (e) {}
    var sw = document.getElementById('v2-theme-toggle');
    if (sw) sw.setAttribute('aria-checked', String(t === 'dark'));
    syncLogos(t);
    window.dispatchEvent(new CustomEvent('bimbo:themeChange', { detail: { theme: t, effective: t } }));
  }

  // Inicializa tema imediatamente
  var initTheme = currentTheme();
  document.documentElement.setAttribute('data-theme', initTheme);
  if (document.body) document.body.setAttribute('data-theme', initTheme);
  syncLogos(initTheme);

  function initUserMenu() {
    syncLogos(currentTheme());

    var container = document.getElementById('app-menu-container');
    if (!container) return;

    container.innerHTML = 
      '<div class="user-menu-wrapper" style="display:inline-flex; align-items:center; gap:12px;">' +
        '<div class="user-menu" style="position:relative;">' +
          '<button type="button" class="avatar-btn" id="v2-user-btn" aria-haspopup="menu" aria-expanded="false" aria-controls="v2-user-menu" aria-label="Menu do usuário">' +
            '<span class="avatar" aria-hidden="true">' +
              '<svg class="ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>' +
                '<circle cx="12" cy="7" r="4"/>' +
              '</svg>' +
            '</span>' +
            '<svg class="ico chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
              '<path d="m6 9 6 6 6-6"/>' +
            '</svg>' +
          '</button>' +
          '<div class="menu" id="v2-user-menu" role="menu" aria-label="Menu do usuário" hidden>' +
            '<a href="guia.html" class="mi" id="v2-menu-guia" role="menuitem" style="text-decoration:none;">' +
              '<svg class="ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/>' +
                '<path d="M6 6h10M6 10h10"/>' +
              '</svg>' +
              '<span class="mi-t">Guia do Usuário & Dicionário</span>' +
            '</a>' +
            '<div class="mi-sep" role="separator"></div>' +
            '<button type="button" class="mi" id="v2-theme-toggle" role="menuitemcheckbox" aria-checked="' + String(currentTheme() === 'dark') + '">' +
              '<svg class="ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>' +
              '</svg>' +
              '<span class="mi-t">Tema escuro</span>' +
              '<span class="switch" aria-hidden="true"></span>' +
            '</button>' +
          '</div>' +
        '</div>' +
      '</div>';

    var btn = document.getElementById('v2-user-btn');
    var menu = document.getElementById('v2-user-menu');
    if (!btn || !menu) return;

    function close() {
      menu.hidden = true;
      btn.setAttribute('aria-expanded', 'false');
    }

    function open() {
      menu.hidden = false;
      btn.setAttribute('aria-expanded', 'true');
    }

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      menu.hidden ? open() : close();
    });

    document.addEventListener('click', function (e) {
      if (!menu.hidden && !menu.contains(e.target) && !btn.contains(e.target)) {
        close();
      }
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !menu.hidden) {
        close();
        btn.focus();
      }
    });

    var tt = document.getElementById('v2-theme-toggle');
    if (tt) {
      tt.addEventListener('click', function (e) {
        e.stopPropagation();
        var isDark = currentTheme() === 'dark';
        setTheme(isDark ? 'light' : 'dark');
      });
    }

    // Toggle da Sidebar Vertical (Minimizar / Maximizar)
    var SIDEBAR_STATE_KEY = 'bimbo_sidebar_state';
    var sidebar = document.getElementById('spSidebar');
    var toggleBtn = document.getElementById('btnToggleSidebar');

    function applySidebarState(isExpanded) {
      if (!sidebar) return;
      if (isExpanded) {
        sidebar.classList.add('expanded');
        if (toggleBtn) {
          toggleBtn.setAttribute('aria-expanded', 'true');
          toggleBtn.title = 'Recolher menu';
        }
      } else {
        sidebar.classList.remove('expanded');
        if (toggleBtn) {
          toggleBtn.setAttribute('aria-expanded', 'false');
          toggleBtn.title = 'Expandir menu';
        }
      }
      try { localStorage.setItem(SIDEBAR_STATE_KEY, isExpanded ? 'expanded' : 'collapsed'); } catch(e){}
      window.dispatchEvent(new Event('resize'));
    }

    if (sidebar && toggleBtn) {
      var savedSidebar = localStorage.getItem(SIDEBAR_STATE_KEY);
      applySidebarState(savedSidebar === 'expanded');

      toggleBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        var willExpand = !sidebar.classList.contains('expanded');
        applySidebarState(willExpand);
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUserMenu);
  } else {
    initUserMenu();
  }
})();
