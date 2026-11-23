css_addition = """/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   MENU DO USUÁRIO — PADRÃO PORTAL DISTRIBUIDORES V2 (A3, A4, identidade-da.md)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
.da-app-menu {
  position: relative;
  display: inline-flex;
  align-items: center;
  margin-left: auto;
  flex-shrink: 0;
  z-index: 1000;
}

.da-menu-trigger {
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
  border-radius: var(--r-pill, 999px);
  min-width: 44px;
  min-height: 44px;
  color: var(--text-primary);
  transition: all .15s ease;
}

.da-menu-trigger:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

.da-avatar-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--surface-hover);
  border: 1px solid var(--border);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color .15s ease, background-color .15s ease;
}

.da-menu-trigger:hover .da-avatar-circle {
  border-color: var(--primary);
  background: var(--primary-soft);
  color: var(--primary);
}

.da-chevron {
  color: var(--text-muted);
  transition: transform .2s ease;
}

.da-menu-trigger[aria-expanded="true"] .da-chevron {
  transform: rotate(180deg);
}

/* Dropdown Panel Desktop */
.da-menu-panel {
  display: none;
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 340px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow-menu);
  z-index: 1001;
  padding: 8px 0;
  color: var(--text-primary);
  font-family: inherit;
  box-sizing: border-box;
}

.da-menu-panel.da-open {
  display: flex;
  flex-direction: column;
  animation: daFadeSlideDown .18s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes daFadeSlideDown {
  from { opacity: 0; transform: translateY(-6px); }
  to { opacity: 1; transform: translateY(0); }
}

.da-sheet-handle { display: none; }
.da-menu-backdrop { display: none; }

.da-menu-row {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  height: 52px;
  padding: 0 20px;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  box-sizing: border-box;
  text-align: left;
  transition: background .12s ease;
}

.da-menu-row:hover,
.da-menu-row:focus-visible {
  background: var(--surface-hover);
  outline: none;
}

.da-row-interactive {
  cursor: default;
}
.da-row-interactive:hover {
  background: transparent;
}

.da-row-icon {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  flex-shrink: 0;
}

.da-row-label {
  flex: 1;
  font-size: 15px;
  font-weight: 500;
  color: var(--text-primary);
}

.da-menu-divider {
  height: 1px;
  background: var(--border);
  margin: 6px 0;
  flex-shrink: 0;
}

/* Seletor Compacto de Idioma PT | EN | ES */
.da-lang-pills {
  display: inline-flex;
  align-items: center;
  padding: 2px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  border-radius: 8px;
  gap: 2px;
}

.da-lang-pill {
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 700;
  border: none;
  background: transparent;
  color: var(--text-muted);
  border-radius: 6px;
  cursor: pointer;
  transition: all .15s ease;
}

.da-lang-pill:hover {
  color: var(--text-primary);
}

.da-lang-pill.active {
  background: var(--primary);
  color: #ffffff;
  box-shadow: 0 1px 2px rgba(0,0,0,.15);
}

/* Switch de Tema Escuro */
.da-switch {
  width: 44px;
  height: 24px;
  border-radius: 999px;
  background: var(--border-input);
  border: none;
  position: relative;
  cursor: pointer;
  transition: background-color .2s ease;
  padding: 0;
  flex-shrink: 0;
}

.da-switch.da-switch-on {
  background: var(--primary);
}

.da-switch-thumb {
  display: block;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #ffffff;
  position: absolute;
  top: 3px;
  left: 3px;
  transition: transform .2s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 1px 3px rgba(0,0,0,.3);
}

.da-switch.da-switch-on .da-switch-thumb {
  transform: translateX(20px);
}

.da-menu-logout {
  color: var(--danger, #ef4444);
}
.da-menu-logout .da-row-icon,
.da-menu-logout .da-row-label {
  color: var(--danger, #ef4444);
}
.da-menu-logout:hover {
  background: var(--danger-soft, rgba(239,68,68,.1));
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   TRILHO DE NAVEGAÇÃO VERTICAL (DNA DE VENDAS — A2)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
.sp-app-layout {
  display: flex;
  min-height: 100vh;
  min-height: 100dvh;
  width: 100%;
  background: var(--bg-page);
  position: relative;
}

.sp-sidebar {
  width: 80px;
  background: var(--bg-header);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 1.25rem 0;
  gap: 0.75rem;
  flex-shrink: 0;
  z-index: 40;
  position: sticky;
  top: 0;
  height: 100vh;
  height: 100dvh;
  box-sizing: border-box;
}

.sp-nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 68px;
  min-height: 56px;
  padding: 6px 2px;
  border-radius: 10px;
  color: var(--text-muted);
  text-decoration: none;
  font-size: 11px;
  font-weight: 600;
  transition: all .15s ease;
  box-sizing: border-box;
}

.sp-nav-item svg {
  width: 22px !important;
  height: 22px !important;
  max-width: 22px !important;
  max-height: 22px !important;
  display: block;
}

.sp-nav-item span {
  text-align: center;
  line-height: 1.15;
  max-width: 64px;
  word-break: break-word;
  white-space: normal;
}

.sp-nav-item:hover {
  color: var(--primary);
  background: var(--surface-hover);
}

.sp-nav-item.active {
  color: var(--primary-strong);
  background: var(--primary-soft);
  border: 1px solid rgba(37, 99, 235, 0.25);
}

[data-theme="dark"] .sp-nav-item.active {
  color: var(--link);
  border-color: rgba(96, 165, 250, 0.35);
}

.sp-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-page);
}

/* Cabeçalho Unificado (DNA Header — A8) */
.dna-header {
  height: 64px;
  background: var(--bg-header);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  overflow: visible !important;
  box-sizing: border-box;
}

.dna-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dna-logo-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 44px;
  text-decoration: none;
  border-radius: var(--r-control, 8px);
}

.dna-logo-link:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

.dna-logo-img {
  height: 32px;
  max-height: 32px;
  width: auto;
  object-fit: contain;
  display: block;
}

.sp-header-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dna-brand-badge {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--primary);
  background: var(--primary-soft);
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid rgba(59, 130, 246, 0.25);
}

.sp-mod-crumb {
  font-size: 13px;
  font-weight: 800;
  color: var(--primary);
  opacity: .9;
}

.sp-page-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* Navegação Mobile Inferior */
.dna-mobile-nav {
  display: none;
}

/* ── Mobile & Tablet Responsividade ── */
@media (max-width: 640px) {
  .sp-sidebar {
    display: none !important;
  }
  
  .sp-main {
    padding-bottom: calc(60px + env(safe-area-inset-bottom, 0px));
  }

  .dna-mobile-nav {
    display: grid !important;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: calc(56px + env(safe-area-inset-bottom, 0px));
    padding-bottom: env(safe-area-inset-bottom, 0px);
    background: var(--bg-header);
    border-top: 1px solid var(--border);
    z-index: 45;
    grid-template-columns: repeat(5, 1fr);
    align-items: center;
    box-sizing: border-box;
  }

  .dna-mobile-nav-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    height: 48px;
    color: var(--text-muted);
    text-decoration: none;
    font-size: 10px;
    font-weight: 600;
  }

  .dna-mobile-nav-item svg {
    width: 20px;
    height: 20px;
  }

  .dna-mobile-nav-item.active {
    color: var(--primary);
  }

  .da-menu-backdrop.da-open {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
    z-index: 9998;
  }

  .da-menu-panel {
    position: fixed !important;
    top: auto !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    width: 100% !important;
    max-height: 85dvh;
    overflow-y: auto;
    border-radius: 16px 16px 0 0 !important;
    padding: 12px 16px calc(16px + env(safe-area-inset-bottom, 16px)) !important;
    z-index: 9999 !important;
    animation: daSlideUp .22s cubic-bezier(0.16, 1, 0.3, 1) !important;
  }

  @keyframes daSlideUp {
    from { transform: translateY(100%); }
    to { transform: translateY(0); }
  }

  .da-sheet-handle {
    display: block;
    width: 40px;
    height: 4px;
    background: var(--border-input);
    border-radius: 999px;
    margin: 0 auto 12px;
  }

  .da-menu-row {
    height: 56px;
    padding: 0 16px;
  }
}
"""

with open('src/app/styles.css', 'r', encoding='utf-8') as f:
    content = f.read()

target_str = '/* ── Menu do App (Canto Superior Direito) ── */'
idx = content.find(target_str)
if idx != -1:
    new_content = content[:idx] + css_addition
    with open('src/app/styles.css', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('styles.css atualizado com sucesso!')
else:
    print('Erro: target string não encontrada')
