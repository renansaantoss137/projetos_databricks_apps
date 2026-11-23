/**
 * PORTAL COMPRAS — Menu do Usuário no padrão Portal Distribuidores v2 (A3, A4, identidade-da.md)
 * 
 * Funcionalidades:
 * - Idioma (PT | EN | ES)
 * - Alternância Direta de Tema (Claro / Escuro)
 * - Governança de Acessos (Módulo Administrativo para Cadastros de Apoio - Exibido apenas para Admins)
 */

(function () {
  'use strict';

  var _userInfo = null;
  var THEME_KEY = 'bimbo_theme_choice';
  var _themeChoice = localStorage.getItem(THEME_KEY) || 'dark';

  function _resolveSystemTheme() {
    try {
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    } catch (e) { return 'dark'; }
  }

  function applyAppTheme(choice) {
    _themeChoice = (choice === 'light' || choice === 'dark') ? choice : 'dark';
    try {
      localStorage.setItem(THEME_KEY, _themeChoice);
      localStorage.setItem('theme', _themeChoice);
      localStorage.setItem('bimbo_theme', _themeChoice);
    } catch (e) {}

    document.documentElement.setAttribute('data-theme', _themeChoice);
    document.documentElement.setAttribute('data-theme-mode', _themeChoice);
    if (document.body) {
      document.body.setAttribute('data-theme', _themeChoice);
    }

    _updateThemeSwitchUI(_themeChoice === 'dark');

    // Atualizar logos DNA para contraste perfeito com o tema
    var logoImgs = document.querySelectorAll('.dna-logo-img');
    logoImgs.forEach(function (img) {
      img.src = _themeChoice === 'light' ? 'logo-dna-blue.png' : 'logo-dna.png';
    });

    // Disparar evento para recriar gráficos
    var evt = new CustomEvent('themeChanged', { detail: { theme: _themeChoice, mode: _themeChoice } });
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

  // Inicializar tema padrão
  var initialChoice = localStorage.getItem(THEME_KEY) || localStorage.getItem('theme') || 'dark';
  applyAppTheme(initialChoice);

  // ── Renderização do Menu ──
  function renderAppMenuContainer(targetEl) {
    if (!targetEl) return;

    var currentLang = (typeof _currentLang !== 'undefined' ? _currentLang : (localStorage.getItem('portalCompras_lang') || 'pt')).toLowerCase();
    var isDark = (document.documentElement.getAttribute('data-theme') || 'dark') === 'dark';

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
      '    <!-- 1. Identidade -->' +
      '    <div class="da-menu-row" id="daMenuIdentity" style="display:none;overflow-wrap:anywhere;"></div>' +
      '    <!-- 2. Governança de Acessos (Admin) -->' +
      '    <button class="da-menu-row" id="daRowAccessGov" type="button" style="display:none;">' +
      '      <div class="da-row-icon" aria-hidden="true">' +
      '        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#3b82f6" stroke-width="2">' +
      '          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>' +
      '          <path d="M12 8v4"></path>' +
      '          <path d="M12 16h.01"></path>' +
      '        </svg>' +
      '      </div>' +
      '      <span class="da-row-label">Governança de Acessos</span>' +
      '      <span style="font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;background:rgba(59,130,246,0.15);color:#3b82f6;border:1px solid rgba(59,130,246,0.3);">ADMIN</span>' +
      '    </button>' +
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

        // Se for admin, habilita a opção de Governança de Acessos no menu
        if (data && data.is_admin) {
          var govRow = document.getElementById('daRowAccessGov');
          if (govRow) govRow.style.display = 'flex';
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
      }
    });

    // Idioma
    panel.querySelectorAll('.da-lang-pill').forEach(function (pill) {
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

    // Governança de Acessos (Admin)
    var govRow = document.getElementById('daRowAccessGov');
    if (govRow) {
      govRow.addEventListener('click', function (e) {
        e.stopPropagation();
        closeMenu(false);
        openAccessGovModal();
      });
    }

    // Evento de Switch de Tema (Claro / Escuro direto)
    var themeRow = document.getElementById('daRowTheme');
    var themeSwitch = document.getElementById('daMenuThemeSwitch');
    if (themeRow && themeSwitch) {
      function toggleTheme() {
        var currentEffective = document.documentElement.getAttribute('data-theme') || 'dark';
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

  // ══════════════════════════════════════════════════════════
  // MÓDULO DE GOVERNANÇA DE ACESSOS (IMPECCABLE D&A MODAL)
  // ══════════════════════════════════════════════════════════
  function _injectGovModalStyles() {
    if (document.getElementById('da-gov-styles')) return;
    var style = document.createElement('style');
    style.id = 'da-gov-styles';
    style.textContent = `
      .da-gov-overlay {
        position: fixed; inset: 0; z-index: 99999;
        display: flex; align-items: center; justify-content: center;
        padding: 1rem; box-sizing: border-box;
      }
      .da-gov-backdrop {
        position: absolute; inset: 0;
        background: rgba(11, 19, 43, 0.75);
        backdrop-filter: blur(6px);
        -webkit-backdrop-filter: blur(6px);
      }
      .da-gov-dialog {
        position: relative; z-index: 1;
        width: 100%; max-width: 560px; max-height: 90vh;
        background: var(--surface, #1e293b);
        border: 1px solid var(--border, rgba(255,255,255,0.12));
        border-radius: 18px;
        box-shadow: 0 25px 60px rgba(0,0,0,0.6);
        display: flex; flex-direction: column;
        color: var(--text-primary, #f8fafc);
        font-family: inherit;
        animation: daGovPop 0.22s cubic-bezier(0.16, 1, 0.3, 1);
        overflow: hidden;
      }
      @keyframes daGovPop {
        from { opacity: 0; transform: scale(0.96) translateY(8px); }
        to { opacity: 1; transform: scale(1) translateY(0); }
      }
      .da-gov-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 1.25rem 1.5rem;
        border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
        background: var(--surface-alt, #0f172a);
      }
      .da-gov-title-wrap {
        display: flex; align-items: center; gap: 12px;
      }
      .da-gov-icon {
        width: 40px; height: 40px; border-radius: 10px;
        background: rgba(59, 130, 246, 0.15);
        border: 1px solid rgba(59, 130, 246, 0.3);
        display: flex; align-items: center; justify-content: center;
        color: #3b82f6; flex-shrink: 0;
      }
      .da-gov-title {
        margin: 0; font-size: 1.15rem; font-weight: 700;
        color: var(--text-primary, #f8fafc);
      }
      .da-gov-subtitle {
        margin: 2px 0 0; font-size: 0.8rem; color: var(--text-muted, #94a3b8);
      }
      .da-gov-close-btn {
        background: transparent; border: none; cursor: pointer;
        color: var(--text-muted, #94a3b8);
        width: 32px; height: 32px; border-radius: 8px;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.25rem; line-height: 1; transition: background .15s, color .15s;
      }
      .da-gov-close-btn:hover {
        background: var(--surface-hover, rgba(255,255,255,0.08));
        color: var(--text-primary, #ffffff);
      }
      .da-gov-body {
        padding: 1.25rem 1.5rem; overflow-y: auto; display: flex; flex-direction: column; gap: 1.25rem;
      }
      .da-gov-alert {
        padding: 0.65rem 1rem; border-radius: 8px; font-size: 0.85rem; font-weight: 500;
        display: flex; align-items: center; gap: 8px;
      }
      .da-gov-alert-success {
        background: rgba(16, 185, 129, 0.12); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);
      }
      .da-gov-alert-error {
        background: rgba(239, 68, 68, 0.12); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3);
      }
      .da-gov-card {
        background: var(--surface-alt, #0f172a);
        border: 1px solid var(--border, rgba(255,255,255,0.08));
        border-radius: 12px; padding: 1rem 1.25rem;
      }
      .da-gov-card-head {
        display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;
      }
      .da-gov-card-title {
        font-size: 0.88rem; font-weight: 700; color: var(--text-primary, #f8fafc);
        text-transform: uppercase; letter-spacing: 0.04em;
      }
      .da-gov-pill {
        font-size: 0.72rem; font-weight: 600; padding: 2px 8px; border-radius: 999px;
      }
      .da-gov-pill-blue {
        background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3);
      }
      .da-gov-pill-gray {
        background: rgba(148, 163, 184, 0.12); color: var(--text-muted, #94a3b8); border: 1px solid rgba(148, 163, 184, 0.2);
      }
      .da-gov-card-desc {
        font-size: 0.82rem; color: var(--text-muted, #94a3b8); margin-bottom: 0.85rem; line-height: 1.4;
      }
      .da-gov-list {
        display: flex; flex-direction: column; gap: 6px;
      }
      .da-gov-item {
        display: flex; align-items: center; justify-content: space-between;
        padding: 0.5rem 0.75rem; border-radius: 8px;
        background: var(--surface, #1e293b);
        border: 1px solid var(--border, rgba(255,255,255,0.05));
      }
      .da-gov-item-left {
        display: flex; align-items: center; gap: 10px; overflow: hidden;
      }
      .da-gov-avatar {
        width: 28px; height: 28px; border-radius: 50%;
        background: rgba(59, 130, 246, 0.2); color: #60a5fa;
        font-weight: 700; font-size: 0.75rem;
        display: flex; align-items: center; justify-content: center; flex-shrink: 0;
      }
      .da-gov-email {
        font-size: 0.85rem; font-weight: 500; color: var(--text-primary, #f8fafc);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .da-gov-btn-rm {
        background: transparent; border: 1px solid transparent; cursor: pointer;
        color: #f87171; padding: 4px 10px; border-radius: 6px; font-size: 0.78rem; font-weight: 600;
        transition: all .15s;
      }
      .da-gov-btn-rm:hover {
        background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.3);
      }
      .da-gov-add-form {
        display: flex; gap: 8px; margin-bottom: 0.85rem;
      }
      .da-gov-input {
        flex: 1; height: 38px; padding: 0 12px; border-radius: 8px;
        background: var(--surface, #1e293b);
        border: 1px solid var(--border-input, rgba(255,255,255,0.15));
        color: var(--text-primary, #f8fafc); font-size: 0.85rem; outline: none;
        transition: border-color .15s, box-shadow .15s;
      }
      .da-gov-input:focus {
        border-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
      }
      .da-gov-btn-add {
        height: 38px; padding: 0 16px; border-radius: 8px;
        background: #2563eb; color: #ffffff; border: none; font-size: 0.85rem; font-weight: 600;
        cursor: pointer; display: flex; align-items: center; gap: 6px; transition: background .15s;
        white-space: nowrap;
      }
      .da-gov-btn-add:hover { background: #1d4ed8; }
      .da-gov-btn-add:disabled { opacity: 0.6; cursor: not-allowed; }
      .da-gov-empty {
        padding: 0.85rem; text-align: center; color: var(--text-muted, #94a3b8);
        font-size: 0.82rem; font-style: italic;
      }
    `;
    document.head.appendChild(style);
  }

  function openAccessGovModal() {
    _injectGovModalStyles();

    var existing = document.getElementById('daGovModalOverlay');
    if (existing) existing.remove();

    var overlay = document.createElement('div');
    overlay.className = 'da-gov-overlay';
    overlay.id = 'daGovModalOverlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'daGovTitle');

    overlay.innerHTML = `
      <div class="da-gov-backdrop" id="daGovBackdrop"></div>
      <div class="da-gov-dialog">
        <div class="da-gov-header">
          <div class="da-gov-title-wrap">
            <div class="da-gov-icon">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                <path d="M12 8v4"/>
                <path d="M12 16h.01"/>
              </svg>
            </div>
            <div>
              <h2 class="da-gov-title" id="daGovTitle">Governança de Acessos</h2>
              <p class="da-gov-subtitle">Gestão de permissões corporativas para a aba Cadastros de Apoio</p>
            </div>
          </div>
          <button class="da-gov-close-btn" id="daGovCloseBtn" type="button" aria-label="Fechar">&times;</button>
        </div>

        <div class="da-gov-body">
          <div id="daGovAlert" class="da-gov-alert" style="display:none;"></div>

          <!-- Administradores -->
          <div class="da-gov-card">
            <div class="da-gov-card-head">
              <span class="da-gov-card-title">Administradores Globais</span>
              <span class="da-gov-pill da-gov-pill-blue">Acesso Irrevogável</span>
            </div>
            <p class="da-gov-card-desc">Contas com permissão de gestão de acessos e parametrização geral.</p>
            <div id="daGovAdminsList" class="da-gov-list">
              <div class="da-gov-empty">Carregando administradores...</div>
            </div>
          </div>

          <!-- Usuários Autorizados -->
          <div class="da-gov-card">
            <div class="da-gov-card-head">
              <span class="da-gov-card-title">Usuários Autorizados</span>
              <span class="da-gov-pill da-gov-pill-gray" id="daGovUserCountBadge">0 autorizados</span>
            </div>
            <p class="da-gov-card-desc">Colaboradores com autorização para acessar, visualizar e salvar novos cadastros de apoio.</p>

            <form id="daGovAddForm" class="da-gov-add-form" onsubmit="return false;">
              <input type="email" id="daGovEmailInput" class="da-gov-input" placeholder="colaborador@grupobimbo.com" required autocomplete="off">
              <button type="submit" id="daGovAddBtn" class="da-gov-btn-add">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                <span>Autorizar</span>
              </button>
            </form>

            <div id="daGovUsersList" class="da-gov-list">
              <div class="da-gov-empty">Carregando permissões...</div>
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    function closeModal() {
      overlay.remove();
      document.removeEventListener('keydown', onKeyDown);
    }

    function onKeyDown(e) {
      if (e.key === 'Escape') closeModal();
    }

    document.getElementById('daGovCloseBtn').addEventListener('click', closeModal);
    document.getElementById('daGovBackdrop').addEventListener('click', closeModal);
    document.addEventListener('keydown', onKeyDown);

    var alertBox = document.getElementById('daGovAlert');
    function showAlert(msg, isError) {
      alertBox.textContent = msg;
      alertBox.className = 'da-gov-alert ' + (isError ? 'da-gov-alert-error' : 'da-gov-alert-success');
      alertBox.style.display = 'flex';
      setTimeout(function () {
        alertBox.style.display = 'none';
      }, 4500);
    }

    function loadAccessData() {
      fetch('/api/admin/cadastros-access')
        .then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.json();
        })
        .then(function (data) {
          renderAdmins(data.admins || []);
          renderUsers(data.authorized_users || []);
        })
        .catch(function (err) {
          showAlert('Não foi possível carregar a lista de permissões: ' + err.message, true);
        });
    }

    function renderAdmins(admins) {
      var list = document.getElementById('daGovAdminsList');
      if (!list) return;
      if (!admins.length) {
        list.innerHTML = '<div class="da-gov-empty">Nenhum administrador listado.</div>';
        return;
      }
      var html = '';
      admins.forEach(function (adm) {
        var initial = (adm.charAt(0) || 'A').toUpperCase();
        html += `
          <div class="da-gov-item">
            <div class="da-gov-item-left">
              <div class="da-gov-avatar">${initial}</div>
              <span class="da-gov-email">${adm}</span>
            </div>
            <span style="font-size:0.75rem; color:#60a5fa; font-weight:600;">Admin</span>
          </div>
        `;
      });
      list.innerHTML = html;
    }

    function renderUsers(users) {
      var list = document.getElementById('daGovUsersList');
      var badge = document.getElementById('daGovUserCountBadge');
      if (badge) badge.textContent = users.length + (users.length === 1 ? ' autorizado' : ' autorizados');
      if (!list) return;

      if (!users.length) {
        list.innerHTML = '<div class="da-gov-empty">Nenhum usuário adicional autorizado. Apenas administradores possuem acesso.</div>';
        return;
      }

      var html = '';
      users.forEach(function (user) {
        var initial = (user.charAt(0) || 'U').toUpperCase();
        html += `
          <div class="da-gov-item" data-email="${user}">
            <div class="da-gov-item-left">
              <div class="da-gov-avatar" style="background:rgba(16,185,129,0.15); color:#34d399;">${initial}</div>
              <span class="da-gov-email">${user}</span>
            </div>
            <button class="da-gov-btn-rm" type="button" data-action="remove" data-email="${user}">Revogar</button>
          </div>
        `;
      });
      list.innerHTML = html;

      // Eventos de revogação
      list.querySelectorAll('button[data-action="remove"]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var emailToRemove = btn.getAttribute('data-email');
          if (confirm('Deseja realmente revogar o acesso de ' + emailToRemove + '?')) {
            btn.disabled = true;
            btn.textContent = 'Removendo...';
            fetch('/api/admin/cadastros-access', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ action: 'remove', email: emailToRemove })
            })
              .then(function (res) { return res.json(); })
              .then(function (resData) {
                if (resData.error) throw new Error(resData.error);
                showAlert(resData.message || 'Acesso revogado com sucesso.', false);
                loadAccessData();
              })
              .catch(function (err) {
                showAlert('Erro ao revogar acesso: ' + err.message, true);
                btn.disabled = false;
                btn.textContent = 'Revogar';
              });
          }
        });
      });
    }

    // Formulário de adição
    var addForm = document.getElementById('daGovAddForm');
    var addInput = document.getElementById('daGovEmailInput');
    var addBtn = document.getElementById('daGovAddBtn');

    addForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var emailVal = (addInput.value || '').trim().toLowerCase();
      if (!emailVal || emailVal.indexOf('@') === -1) {
        showAlert('Por favor, informe um endereço de e-mail corporativo válido.', true);
        return;
      }

      addBtn.disabled = true;
      addBtn.textContent = 'Salvando...';

      fetch('/api/admin/cadastros-access', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'add', email: emailVal })
      })
        .then(function (res) { return res.json(); })
        .then(function (resData) {
          if (resData.error) throw new Error(resData.error);
          showAlert(resData.message || 'Usuário autorizado com sucesso.', false);
          addInput.value = '';
          loadAccessData();
        })
        .catch(function (err) {
          showAlert('Erro ao autorizar usuário: ' + err.message, true);
        })
        .finally(function () {
          addBtn.disabled = false;
          addBtn.innerHTML = `
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            <span>Autorizar</span>
          `;
        });
    });

    loadAccessData();
  }

  // Auto-inicializar no container se já existir no DOM
  function autoInit() {
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
    openAccessGov: openAccessGovModal,
    getUserInfo: function () { return _userInfo; }
  };
})();
