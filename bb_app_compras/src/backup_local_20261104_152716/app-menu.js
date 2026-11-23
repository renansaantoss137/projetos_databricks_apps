/**
 * PORTAL COMPRAS — Menu do Usuário no padrão Portal Distribuidores v2 (A3, A4, identidade-da.md)
 * 
 * Especificação:
 * - Gatilho: ícone de pessoa em contorno num círculo de 36px com chevron ao lado, sem iniciais.
 * - Linhas com ícone (20px), texto de 16px, altura 52-56px, padding lateral 20px.
 * - Sem cabeçalho com nome/e-mail, sem títulos de seção, sem selos ADMIN, sem rodapé de versão.
 * - Ordem:
 *   1. Guia do Usuário e Cadastro de Planilhas (visível por permissão via /api/auth/me)
 *   2. Divisória e Idioma (seletor compacto PT | EN | ES à direita)
 *   3. Tema escuro (switch liga/desliga role="switch")
 *   4. Divisória e Sair (logout real)
 * - Funciona e fecha nas 7 telas (desktop 360px, mobile <= 640px bottom sheet).
 */

(function () {
  'use strict';

  var _userInfo = null;
  var THEME_KEY = 'bimbo_theme_choice';
  var _themeChoice = localStorage.getItem(THEME_KEY) || 'system';

  function _resolveSystemTheme() {
    try {
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    } catch (e) { return 'light'; }
  }

  function applyAppTheme(choice) {
    _themeChoice = choice || 'system';
    try {
      localStorage.setItem(THEME_KEY, _themeChoice);
    } catch (e) {}

    var effectiveTheme = _themeChoice === 'system' ? _resolveSystemTheme() : _themeChoice;
    document.documentElement.setAttribute('data-theme', effectiveTheme);
    document.documentElement.setAttribute('data-theme-mode', _themeChoice);
    if (document.body) {
      document.body.setAttribute('data-theme', effectiveTheme);
    }
    try {
      localStorage.setItem('theme', effectiveTheme);
      localStorage.setItem('bimbo_theme', effectiveTheme);
    } catch (e) {}

    _updateThemeSwitchUI(effectiveTheme === 'dark');
    var systemButton = document.getElementById('daThemeSystem');
    if (systemButton) systemButton.setAttribute('aria-pressed', String(_themeChoice === 'system'));

    // Atualizar logos DNA para contraste perfeito com o tema
    var logoImgs = document.querySelectorAll('.dna-logo-img');
    logoImgs.forEach(function (img) {
      img.src = effectiveTheme === 'light' ? 'logo-dna-blue.png' : 'logo-dna.png';
    });

    // Disparar evento para recriar gráficos
    var evt = new CustomEvent('themeChanged', { detail: { theme: effectiveTheme, mode: _themeChoice } });
    window.dispatchEvent(evt);
    document.dispatchEvent(evt);
  }

  function _updateThemeSwitchUI(isDark) {
    var sw = document.getElementById('daMenuThemeSwitch');
    if (sw) {
      sw.setAttribute('aria-checked', isDark ? 'true' : 'false');
      if (isDark) {
        sw.classList.add('da-switch-on');
      } else {
        sw.classList.remove('da-switch-on');
      }
    }
  }

  try {
    var systemTheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
    var onSystemThemeChange = function () {
      if (_themeChoice === 'system') {
        applyAppTheme('system');
      }
    };
    if (systemTheme && systemTheme.addEventListener) systemTheme.addEventListener('change', onSystemThemeChange);
    else if (systemTheme && systemTheme.addListener) systemTheme.addListener(onSystemThemeChange);
  } catch (e) {}

  // Inicializar tema
  var initialChoice = localStorage.getItem(THEME_KEY);
  if (!initialChoice) initialChoice = 'system';
  applyAppTheme(initialChoice);

  // ── Renderização do Menu ──
  function renderAppMenuContainer(targetEl) {
    if (!targetEl) return;

    var currentLang = (typeof _currentLang !== 'undefined' ? _currentLang : (localStorage.getItem('portalCompras_lang') || 'pt')).toLowerCase();
    var isDark = (document.documentElement.getAttribute('data-theme') || _resolveSystemTheme()) === 'dark';

    var html = '' +
      '<div class="da-app-menu" id="daAppMenuWrapper">' +
      '  <button class="da-menu-trigger" id="daAppMenuTrigger" type="button" ' +
      '          aria-haspopup="menu" aria-expanded="false" aria-controls="daAppMenuPanel" aria-label="Menu do usuário">' +
      '    <div class="da-avatar-circle" aria-hidden="true">' +
      '      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">' +
      '        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>' +
      '        <circle cx="12" cy="7" r="4"></circle>' +
      '      </svg>' +
      '    </div>' +
      '    <svg class="da-chevron" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">' +
      '      <polyline points="6 9 12 15 18 9"></polyline>' +
      '    </svg>' +
      '  </button>' +
      '  <div class="da-menu-backdrop" id="daMenuBackdrop"></div>' +
      '  <div class="da-menu-panel" id="daAppMenuPanel" role="menu" aria-labelledby="daAppMenuTrigger" tabindex="-1">' +
      '    <div class="da-sheet-handle" aria-hidden="true"></div>' +
      '    <!-- 1. Ferramentas -->' +
      '    <div class="da-menu-row" id="daMenuIdentity" style="display:none;overflow-wrap:anywhere;"></div>' +
      '    <!-- 3. Idioma -->' +
      '    <div class="da-menu-row da-row-interactive" id="daRowLang">' +
      '      <div class="da-row-icon" aria-hidden="true">' +
      '        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">' +
      '          <circle cx="12" cy="12" r="10"></circle>' +
      '          <line x1="2" y1="12" x2="22" y2="12"></line>' +
      '          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>' +
      '        </svg>' +
      '      </div>' +
      '      <span class="da-row-label" data-i18n="Idioma">Idioma</span>' +
      '      <div class="da-lang-pills" role="radiogroup" aria-label="Seleção de idioma">' +
      '        <button type="button" class="da-lang-pill' + (currentLang === 'pt' ? ' active' : '') + '" data-lang="pt" role="radio" aria-checked="' + (currentLang === 'pt' ? 'true' : 'false') + '">PT</button>' +
      '        <button type="button" class="da-lang-pill' + (currentLang === 'en' ? ' active' : '') + '" data-lang="en" role="radio" aria-checked="' + (currentLang === 'en' ? 'true' : 'false') + '">EN</button>' +
      '        <button type="button" class="da-lang-pill' + (currentLang === 'es' ? ' active' : '') + '" data-lang="es" role="radio" aria-checked="' + (currentLang === 'es' ? 'true' : 'false') + '">ES</button>' +
      '      </div>' +
      '    </div>' +
      '    <!-- 4. Tema escuro -->' +
      '    <div class="da-menu-row da-row-interactive" id="daRowTheme">' +
      '      <div class="da-row-icon" aria-hidden="true">' +
      '        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">' +
      '          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>' +
      '        </svg>' +
      '      </div>' +
      '      <span class="da-row-label" data-i18n="Tema escuro">Tema escuro</span>' +
      '      <button type="button" class="da-switch' + (isDark ? ' da-switch-on' : '') + '" id="daMenuThemeSwitch" role="switch" aria-checked="' + (isDark ? 'true' : 'false') + '" aria-label="Alternar tema escuro">' +
      '        <span class="da-switch-thumb"></span>' +
      '      </button>' +
      '    </div>' +
      '    <button class="da-menu-row" id="daThemeSystem" type="button" aria-pressed="' + (_themeChoice === 'system' ? 'true' : 'false') + '">Usar tema do sistema</button>' +
      '  </div>' +
      '</div>';

    targetEl.innerHTML = html;
    _bindAppMenuEvents();
    _fetchUserInfo();
  }

  function _updateLangPills(lang) {
    document.querySelectorAll('.da-lang-pill').forEach(function (pill) {
      var isCurrent = pill.getAttribute('data-lang') === lang;
      pill.classList.toggle('active', isCurrent);
      pill.setAttribute('aria-checked', isCurrent ? 'true' : 'false');
    });
  }

  function _fetchUserInfo() {
    fetch('/api/auth/me')
      .then(function (res) {
        if (!res.ok) throw new Error('Auth HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        _userInfo = data;
        var identity = document.getElementById('daMenuIdentity');
        if (identity && data.email && data.email.indexOf('@') !== -1 && !data.email.endsWith('.invalid')) {
          identity.textContent = data.email;
          identity.style.display = 'flex';
          var avatar = document.querySelector('#daAppMenuTrigger .da-avatar-circle');
          if (avatar) avatar.textContent = data.email.charAt(0).toUpperCase();
        }
      })
      .catch(function (err) {
        console.warn('Auth info indisponível (offline/local):', err);
      });
  }

  function _bindAppMenuEvents() {
    var trigger = document.getElementById('daAppMenuTrigger');
    var panel = document.getElementById('daAppMenuPanel');
    var backdrop = document.getElementById('daMenuBackdrop');
    if (!trigger || !panel) return;

    function openMenu() {
      panel.classList.add('da-open');
      if (backdrop) backdrop.classList.add('da-open');
      trigger.setAttribute('aria-expanded', 'true');
      var firstItem = panel.querySelector('a, button');
      if (firstItem) firstItem.focus();
    }

    function closeMenu(restoreFocus) {
      panel.classList.remove('da-open');
      if (backdrop) backdrop.classList.remove('da-open');
      trigger.setAttribute('aria-expanded', 'false');
      if (restoreFocus !== false) {
        trigger.focus();
      }
    }

    trigger.addEventListener('click', function (e) {
      e.stopPropagation();
      if (panel.classList.contains('da-open')) {
        closeMenu(false);
      } else {
        openMenu();
      }
    });

    if (backdrop) {
      backdrop.addEventListener('click', function () {
        closeMenu(true);
      });
    }

    document.addEventListener('click', function (e) {
      if (!panel.contains(e.target) && !trigger.contains(e.target)) {
        if (panel.classList.contains('da-open')) {
          closeMenu(false);
        }
      }
    });

    panel.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeMenu(true);
      } else if (e.key === 'Tab') {
        // Fechar ao navegar para fora
        closeMenu(false);
      }
    });

    // Eventos de Idioma
    document.querySelectorAll('.da-lang-pill').forEach(function (pill) {
      pill.addEventListener('click', function (e) {
        e.stopPropagation();
        var lang = pill.getAttribute('data-lang');
        _updateLangPills(lang);
        if (typeof setLang === 'function') {
          setLang(lang);
        } else {
          localStorage.setItem('portalCompras_lang', lang);
          document.documentElement.lang = lang === 'pt' ? 'pt-BR' : lang;
          if (typeof _translateStaticContent === 'function') {
            _translateStaticContent();
          }
        }
      });
    });

    // Evento de Switch de Tema
    var themeRow = document.getElementById('daRowTheme');
    var themeSwitch = document.getElementById('daMenuThemeSwitch');
    var systemButton = document.getElementById('daThemeSystem');
    if (systemButton) systemButton.addEventListener('click', function () { applyAppTheme('system'); });
    if (themeRow && themeSwitch) {
      function toggleTheme() {
        var currentEffective = document.documentElement.getAttribute('data-theme') || _resolveSystemTheme();
        var newTheme = currentEffective === 'dark' ? 'light' : 'dark';
        applyAppTheme(newTheme);
      }
      themeSwitch.addEventListener('click', function (e) {
        e.stopPropagation();
        toggleTheme();
      });
      themeRow.addEventListener('click', function (e) {
        if (e.target !== themeSwitch && !themeSwitch.contains(e.target)) {
          toggleTheme();
        }
      });
    }
  }

  // Auto-inicializar no container se já existir no DOM
  function autoInit() {
    applyAppTheme(_themeChoice);
    var container = document.getElementById('app-menu-container');
    if (container) {
      renderAppMenuContainer(container);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }

  // API Global
  window.AppMenu = {
    render: renderAppMenuContainer,
    applyTheme: applyAppTheme,
    getUserInfo: function () { return _userInfo; }
  };
})();
