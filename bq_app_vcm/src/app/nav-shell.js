/**
 * BQ VCM — Navigation Shell, V2 Header, Sidebar Rail, Filter Drawer & Governance
 * Aligned with Portal Distribuidores V2 Design System
 */
(function () {
  const SIDEBAR_COLLAPSED_KEY = "vcm_sidebar_collapsed";
  const NAV_EXPANDED_KEY = "vcm_nav_expanded";
  let _authUser = null;

  function escHtml(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function getActiveTheme() {
    return document.documentElement.getAttribute("data-theme") || "dark";
  }

  function syncThemeSwitches() {
    const isDark = getActiveTheme() === "dark";
    const oldSw = document.getElementById("daMenuThemeSwitch");
    if (oldSw) {
      oldSw.classList.toggle("da-switch-on", isDark);
      oldSw.setAttribute("aria-checked", String(isDark));
    }
    const v2Sw = document.getElementById("v2-theme-switch");
    if (v2Sw) {
      v2Sw.classList.toggle("da-switch-on", isDark);
    }
    const v2Toggle = document.getElementById("v2-theme-toggle");
    if (v2Toggle) {
      v2Toggle.setAttribute("aria-checked", String(isDark));
    }
  }

  function flipTheme() {
    const next = getActiveTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme_preference", next);
      localStorage.setItem("portal_theme", next);
    } catch (e) {}
    syncThemeSwitches();
  }
  window.flipTheme = flipTheme;

  window.updateTopbarBaseDate = function (dtStr) {
    if (!dtStr) return;
    const cleanDt = escHtml(dtStr);
    const oldEl = document.getElementById("topbarBaseUpdated");
    if (oldEl) {
      oldEl.innerHTML = `Base atualizada: <strong>${cleanDt}</strong>`;
      oldEl.style.display = "inline-block";
    }
    const v2Sync = document.getElementById("v2-sync-rel");
    if (v2Sync) {
      v2Sync.textContent = `Atualizado: ${cleanDt}`;
    }
  };

  /* ── Sidebar Expansion / Rail ── */
  function applySavedSidebarState() {
    try {
      const expanded = localStorage.getItem(NAV_EXPANDED_KEY) === "1";
      if (expanded && window.innerWidth >= 900) {
        document.body.classList.add("nav-expanded");
        const btn = document.getElementById("nav-expand");
        if (btn) btn.setAttribute("aria-expanded", "true");
      }
    } catch (e) {}
  }

  window.toggleNavExpand = function () {
    const isMobile = window.innerWidth < 900;
    const sidebar = document.getElementById("portal-sidebar") || document.getElementById("appSidebar");
    const scrim = document.getElementById("v2-scrim") || document.getElementById("sidebarBackdrop");
    const btn = document.getElementById("nav-expand");

    if (isMobile) {
      if (sidebar) {
        const isOpen = sidebar.classList.toggle("mobile-open");
        if (btn) btn.setAttribute("aria-expanded", String(isOpen));
        if (scrim) {
          scrim.hidden = !isOpen;
          scrim.classList.toggle("is-visible", isOpen);
        }
      }
    } else {
      const isExpanded = document.body.classList.toggle("nav-expanded");
      if (btn) btn.setAttribute("aria-expanded", String(isExpanded));
      try {
        localStorage.setItem(NAV_EXPANDED_KEY, isExpanded ? "1" : "0");
      } catch (e) {}
    }
  };

  /* ── Filter Drawer (Painel Retrátil à Direita) ── */
  window.openFilterDrawer = function () {
    const drawer = document.getElementById("portal-filter-drawer");
    const scrim = document.getElementById("v2-scrim");
    const btn = document.getElementById("btnAdvFilters") || document.getElementById("open-filter-drawer-btn");
    if (!drawer) return;
    drawer.classList.add("is-open");
    if (scrim) {
      scrim.hidden = false;
      scrim.classList.add("is-visible");
    }
    if (btn) {
      btn.setAttribute("aria-expanded", "true");
      btn.classList.add("filter-btn-active");
    }
    document.body.style.overflow = "hidden";
    const closeBtn = document.getElementById("close-filter-drawer-btn");
    if (closeBtn) closeBtn.focus();
  };

  window.closeFilterDrawer = function () {
    const drawer = document.getElementById("portal-filter-drawer");
    const scrim = document.getElementById("v2-scrim");
    const btn = document.getElementById("btnAdvFilters") || document.getElementById("open-filter-drawer-btn");
    if (!drawer) return;
    drawer.classList.remove("is-open");
    if (scrim) {
      scrim.classList.remove("is-visible");
      setTimeout(() => {
        if (!drawer.classList.contains("is-open")) scrim.hidden = true;
      }, 250);
    }
    if (btn) {
      btn.setAttribute("aria-expanded", "false");
      btn.classList.remove("filter-btn-active");
    }
    document.body.style.overflow = "";
  };

  window.toggleFilterDrawer = function (e) {
    if (e && typeof e.preventDefault === "function") e.preventDefault();
    const drawer = document.getElementById("portal-filter-drawer");
    if (!drawer) return;
    if (drawer.classList.contains("is-open")) {
      window.closeFilterDrawer();
    } else {
      window.openFilterDrawer();
    }
  };

  function initFilterDrawerEvents() {
    const drawer = document.getElementById("portal-filter-drawer");
    const scrim = document.getElementById("v2-scrim");
    const openBtn = document.getElementById("open-filter-drawer-btn");
    const advBtn = document.getElementById("btnAdvFilters");
    const closeBtn = document.getElementById("close-filter-drawer-btn");
    const footerCloseBtn = document.getElementById("pfd-close-footer-btn");
    const applyBtn = document.getElementById("pfd-apply-btn");

    if (openBtn) openBtn.addEventListener("click", window.toggleFilterDrawer);
    if (advBtn) advBtn.addEventListener("click", window.toggleFilterDrawer);
    if (closeBtn) closeBtn.addEventListener("click", window.closeFilterDrawer);
    if (footerCloseBtn) footerCloseBtn.addEventListener("click", window.closeFilterDrawer);

    if (applyBtn) {
      applyBtn.addEventListener("click", function () {
        if (typeof window.aplicarFiltros === "function") {
          window.aplicarFiltros();
        }
        window.closeFilterDrawer();
      });
    }

    if (scrim) {
      scrim.addEventListener("click", function () {
        window.closeFilterDrawer();
        const sidebar = document.getElementById("portal-sidebar");
        if (sidebar && sidebar.classList.contains("mobile-open")) {
          sidebar.classList.remove("mobile-open");
          scrim.classList.remove("is-visible");
          setTimeout(() => { scrim.hidden = true; }, 200);
        }
      });
    }

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        if (drawer && drawer.classList.contains("is-open")) {
          window.closeFilterDrawer();
        }
      }
    });
  }

  /* ── Header V2 Interactions ── */
  function initV2Header() {
    const navBtn = document.getElementById("nav-expand");
    if (navBtn) {
      navBtn.addEventListener("click", window.toggleNavExpand);
    }

    const userBtn = document.getElementById("v2-user-btn");
    const userMenu = document.getElementById("v2-user-menu");
    const govBtn = document.getElementById("v2-menu-access-gov");
    const themeBtn = document.getElementById("v2-theme-toggle");

    if (userBtn && userMenu) {
      userBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        const isOpen = !userMenu.hidden;
        userMenu.hidden = isOpen;
        userBtn.setAttribute("aria-expanded", String(!isOpen));
      });

      document.addEventListener("click", function (e) {
        if (!userBtn.contains(e.target) && !userMenu.contains(e.target)) {
          userMenu.hidden = true;
          userBtn.setAttribute("aria-expanded", "false");
        }
      });
    }

    if (govBtn) {
      govBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        if (userMenu) userMenu.hidden = true;
        if (userBtn) userBtn.setAttribute("aria-expanded", "false");
        openAccessGovModal();
      });
    }

    if (themeBtn) {
      themeBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        flipTheme();
      });
    }

    syncThemeSwitches();
  }

  function loadAuth() {
    fetch("/api/auth/me")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data) return;
        _authUser = data;
        const email = data.email || "Usuário";

        // V2 elements
        const v2Email = document.getElementById("v2-menu-user-email");
        const v2GovBtn = document.getElementById("v2-menu-access-gov");
        if (v2Email) v2Email.textContent = email;
        if (v2GovBtn && (data.is_admin || data.is_manager || data.can_manage_access)) {
          v2GovBtn.style.display = "flex";
        }

        // V1 fallback elements
        const triggerEmail = document.getElementById("daTriggerEmail");
        const menuEmail = document.getElementById("daMenuIdentityEmail");
        const menuRole = document.getElementById("daMenuIdentityRole");
        const govBtn = document.getElementById("daRowAccessGov");
        if (triggerEmail) triggerEmail.textContent = email;
        if (menuEmail) menuEmail.textContent = email;
        if (menuRole) {
          menuRole.textContent = data.role_label || (data.is_admin
            ? "Administrador"
            : (data.is_manager ? "Gestor de Acessos" : (data.can_access_cadastros ? "Edição de Base autorizada" : "Visualização")));
        }
        if (govBtn && (data.is_admin || data.is_manager || data.can_manage_access)) {
          govBtn.style.display = "flex";
        }

        if (data.base_atualizada_em) {
          window.updateTopbarBaseDate(data.base_atualizada_em);
        }
      })
      .catch(() => {});
  }

  function openAccessGovModal() {
    const existing = document.getElementById("daGovOverlay");
    if (existing) existing.remove();

    const overlay = document.createElement("div");
    overlay.id = "daGovOverlay";
    overlay.className = "da-gov-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "daGovTitle");

    overlay.innerHTML = `
      <div class="da-gov-backdrop" id="daGovBackdrop"></div>
      <div class="da-gov-dialog">
        <div class="da-gov-header">
          <div>
            <h2 class="da-gov-title" id="daGovTitle">Governança de Acessos — Base VCM</h2>
            <p class="da-gov-subtitle">Gerencie quem pode atualizar e baixar a Base VCM no módulo Cadastros.</p>
          </div>
          <button type="button" class="da-gov-close-btn" id="daGovCloseBtn" aria-label="Fechar">&times;</button>
        </div>
        <div class="da-gov-body">
          <div id="daGovAlertBox" style="display:none;"></div>
          <form class="da-gov-form" id="daGovAddForm">
            <input type="email" id="daGovEmailInput" placeholder="nome.sobrenome@grupobimbo.com" required autocomplete="off" aria-label="E-mail corporativo para autorizar" style="flex:1;">
            <select id="daGovRoleSelect" class="da-gov-role-select" style="display:none;" aria-label="Nível de Acesso">
              <option value="authorized">Usuário Autorizado</option>
              <option value="manager">Gestor de Acessos</option>
            </select>
            <button type="submit" class="da-gov-btn-primary" id="daGovAddBtn">Autorizar</button>
          </form>
          <div>
            <div class="da-gov-section-title">Usuários Autorizados (Operação Base VCM)</div>
            <ul class="da-gov-list" id="daGovUsersList">
              <li class="da-gov-list-item">Carregando lista...</li>
            </ul>
          </div>
          <div style="margin-top: 14px;">
            <div class="da-gov-section-title">Gestores de Acesso (Concedem e Revogam Acessos)</div>
            <ul class="da-gov-list" id="daGovManagersList">
              <li class="da-gov-list-item">Carregando lista...</li>
            </ul>
          </div>
          <div style="margin-top: 14px;">
            <div class="da-gov-section-title">Administradores Gerais</div>
            <ul class="da-gov-list" id="daGovAdminsList"></ul>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const closeModal = () => overlay.remove();
    document.getElementById("daGovBackdrop").addEventListener("click", closeModal);
    document.getElementById("daGovCloseBtn").addEventListener("click", closeModal);

    const escHandler = (e) => {
      if (e.key === "Escape") {
        closeModal();
        document.removeEventListener("keydown", escHandler);
      }
    };
    document.addEventListener("keydown", escHandler);

    function showGovAlert(msg, isError) {
      const box = document.getElementById("daGovAlertBox");
      if (!box) return;
      box.className = `da-gov-alert ${isError ? "da-gov-alert-error" : "da-gov-alert-success"}`;
      box.textContent = msg;
      box.style.display = "block";
    }

    function loadAccessLists() {
      fetch("/api/admin/cadastros-access")
        .then((res) => res.json().then((d) => ({ ok: res.ok, d })))
        .then(({ ok, d }) => {
          if (!ok) throw new Error(d.error || "Falha ao carregar acessos.");
          const usersList = document.getElementById("daGovUsersList");
          const managersList = document.getElementById("daGovManagersList");
          const adminsList = document.getElementById("daGovAdminsList");
          const roleSelect = document.getElementById("daGovRoleSelect");

          const users = d.authorized_users || [];
          const managers = d.managers || [];
          const admins = d.admins || [];
          const isAdmin = !!d.current_user_is_admin;

          if (roleSelect && isAdmin) {
            roleSelect.style.display = "inline-block";
          }

          // 1. Usuários autorizados
          if (users.length === 0) {
            usersList.innerHTML = `<li class="da-gov-list-item" style="color:var(--da-txt-muted);">Nenhum usuário autorizado cadastrado.</li>`;
          } else {
            usersList.innerHTML = users.map((u) => `
              <li class="da-gov-list-item">
                <span>${escHtml(u)}</span>
                <button type="button" class="da-gov-revoke-btn" data-revoke-email="${escHtml(u)}">Revogar</button>
              </li>
            `).join("");
          }

          // 2. Gestores de Acesso (ex: Jessica)
          if (managers.length === 0) {
            managersList.innerHTML = `<li class="da-gov-list-item" style="color:var(--da-txt-muted);">Nenhum gestor cadastrado.</li>`;
          } else {
            managersList.innerHTML = managers.map((m) => `
              <li class="da-gov-list-item">
                <div style="display:flex;align-items:center;gap:8px;">
                  <span>${escHtml(m)}</span>
                  <span class="da-gov-badge-manager">Gestor de Acessos</span>
                </div>
                ${isAdmin ? `<button type="button" class="da-gov-revoke-btn" data-revoke-email="${escHtml(m)}">Revogar</button>` : `<span style="font-size:0.75rem;color:var(--da-txt-muted);">Gestor</span>`}
              </li>
            `).join("");
          }

          // Eventos de revogação
          overlay.querySelectorAll("[data-revoke-email]").forEach((btn) => {
            btn.addEventListener("click", function () {
              const target = btn.getAttribute("data-revoke-email");
              btn.disabled = true;
              btn.textContent = "Revogando...";
              fetch("/api/admin/cadastros-access", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "remove", email: target })
              })
                .then((r) => r.json().then((res) => ({ ok: r.ok, res })))
                .then(({ ok, res }) => {
                  if (!ok) throw new Error(res.error || "Falha ao revogar.");
                  showGovAlert(res.message || "Acesso revogado.", false);
                  loadAccessLists();
                })
                .catch((err) => {
                  showGovAlert(err.message, true);
                  btn.disabled = false;
                  btn.textContent = "Revogar";
                });
            });
          });

          // 3. Administradores
          adminsList.innerHTML = admins.map((a) => `
            <li class="da-gov-list-item">
              <span>${escHtml(a)}</span>
              <span style="font-size:0.75rem;font-weight:700;color:var(--da-primary-txt);">Admin</span>
            </li>
          `).join("");
        })
        .catch((err) => showGovAlert(err.message, true));
    }

    document.getElementById("daGovAddForm").addEventListener("submit", function (e) {
      e.preventDefault();
      const input = document.getElementById("daGovEmailInput");
      const roleSel = document.getElementById("daGovRoleSelect");
      const btn = document.getElementById("daGovAddBtn");
      const emailVal = (input.value || "").trim().toLowerCase();
      const roleVal = roleSel && roleSel.value === "manager" ? "manager" : "authorized";

      if (!emailVal || emailVal.indexOf("@") === -1) {
        showGovAlert("Informe um e-mail corporativo válido.", true);
        return;
      }
      btn.disabled = true;
      btn.textContent = "Salvando...";
      fetch("/api/admin/cadastros-access", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "add", email: emailVal, role: roleVal })
      })
        .then((r) => r.json().then((res) => ({ ok: r.ok, res })))
        .then(({ ok, res }) => {
          if (!ok) throw new Error(res.error || "Falha ao autorizar.");
          showGovAlert(res.message || "Acesso concedido com sucesso.", false);
          input.value = "";
          loadAccessLists();
        })
        .catch((err) => showGovAlert(err.message, true))
        .finally(() => {
          btn.disabled = false;
          btn.textContent = "Autorizar";
        });
    });

    loadAccessLists();
    document.getElementById("daGovEmailInput").focus();
  }
  window.openAccessGovModal = openAccessGovModal;

  document.addEventListener("DOMContentLoaded", function () {
    applySavedSidebarState();
    initV2Header();
    initFilterDrawerEvents();
    loadAuth();
  });
})();
