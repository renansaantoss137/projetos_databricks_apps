/**
 * DNA DE VENDAS | Grupo Bimbo Brasil
 * Sistema de Filtros & Custom Selects idêntico ao Portal Distribuidores (v2)
 */

(function () {
  'use strict';

  const STORAGE_KEY = 'dna_filtros_estado';
  const BOOKMARKS_STORAGE_PREFIX = 'dna_bookmarks_';

  class DNAFiltersPanel {
    constructor(config) {
      this.filtros = config.filtros || [];
      this.onApplyCallback = config.onApply || (() => {});
      this.selectInstances = new Map();
      this.quickInstances = new Map();
      this.currentUserEmail = null;

      // Normaliza opções
      this.filtros.forEach(f => {
        f.opcoes = (f.opcoes || []).map(o => typeof o === 'string' ? { v: o, t: o } : o);
      });

      this.aplicado = this.getPadrao();
      this.rascunho = this.clonar(this.aplicado);

      this.initDOM();
      this.initIndicadoresPessoais();
      this.montarDrawer();
      this.montarQuickFilters();
      this.montarChips();
      this.bindGlobalEvents();
      this.atualizarTudo();
    }

    getPadrao() {
      return Object.fromEntries(
        this.filtros.map(f => [
          f.id,
          f.tipo === 'unico'
            ? (f.padrao ?? (f.opcoes[0]?.v || ''))
            : (f.padrao ? new Set(Array.isArray(f.padrao) ? f.padrao : [f.padrao]) : new Set())
        ])
      );
    }

    clonar(est) {
      return Object.fromEntries(
        Object.entries(est).map(([k, v]) => [k, v instanceof Set ? new Set(v) : v])
      );
    }

    async getIdentidadeUsuario() {
      if (this.currentUserEmail) return this.currentUserEmail;
      try {
        const res = await fetch('/api/user/me');
        if (res.ok) {
          const u = await res.json();
          this.currentUserEmail = u.email || 'usuario_local';
          return this.currentUserEmail;
        }
      } catch (e) {}
      this.currentUserEmail = 'usuario_local';
      return this.currentUserEmail;
    }

    getStorageKeyBookmarks() {
      return BOOKMARKS_STORAGE_PREFIX + (this.currentUserEmail || 'usuario_local');
    }

    initDOM() {
      // Assegura existência da Barra Superior de Filtros Ativos
      let bar = document.getElementById('active-filters-bar');
      if (!bar) {
        const oldResumo = document.getElementById('fpResumo');
        if (oldResumo) {
          oldResumo.id = 'active-filters-bar';
          oldResumo.className = 'active-filters-bar';
          bar = oldResumo;
        }
      }

      if (bar) {
        const hasTargetMode = (typeof window.setComparisonMode === 'function');
        const isFcst = window.comparisonMode === 'Forecast';
        const targetSwitchHtml = hasTargetMode ? `
            <div class="segmented sm" id="global-target-seg" role="radiogroup" aria-label="Meta de comparação da página">
              <button type="button" class="toggle-label ${!isFcst ? 'active-label' : ''}" data-target="Budget" aria-checked="${!isFcst}">Budget</button>
              <button type="button" class="toggle-label ${isFcst ? 'active-label' : ''}" data-target="Forecast" aria-checked="${isFcst}">Forecast</button>
            </div>` : '';
        bar.innerHTML = `
          <div class="afb-left">
            <div class="qf-group" id="fpQuickFilters"></div>
            <div class="afb-chips" id="afb-chips-container"></div>
          </div>
          <div class="afb-right">
            ${targetSwitchHtml}
            <div class="fp-bookmarks-wrap" id="fpBookmarksWrap"></div>
            <span class="afb-sep" aria-hidden="true" style="width:1px; height:18px; background:var(--border); margin:0 4px; display:inline-block;"></span>
            <button type="button" class="afb-reset-btn" id="afb-reset" hidden title="Voltar aos filtros padrão" aria-label="Limpar todos os filtros">
              <svg class="ico" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                <path d="M3 3v5h5"/>
              </svg>
              <span>Limpar filtros</span>
            </button>
            <button type="button" class="btn btn-secondary afb-drawer-btn" id="open-filter-drawer-btn" aria-label="Abrir painel de filtros retrátil à direita">
              <svg class="ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 20a1 1 0 0 0 .55.89l2 1A1 1 0 0 0 14 21v-7a2 2 0 0 1 .52-1.34L21.74 4.67A1 1 0 0 0 21 3H3a1 1 0 0 0-.74 1.67l7.22 7.99A2 2 0 0 1 10 14z"/></svg>
              <span>Filtros</span>
              <span class="afb-count" id="afb-count-badge" hidden style="display:none;">0</span>
            </button>
          </div>
        `;

        bar.querySelectorAll('#global-target-seg button[data-target]').forEach(btn => {
          btn.addEventListener('click', () => {
            if (typeof window.setComparisonMode === 'function') {
              window.setComparisonMode(btn.dataset.target);
            }
          });
        });
      }

      // Assegura existência do Painel Retrátil à Direita e Scrim
      let drawer = document.getElementById('portal-filter-drawer');
      if (!drawer) {
        const oldLateral = document.getElementById('fpLateral');
        if (oldLateral) oldLateral.remove();
        const oldGaveta = document.getElementById('fpGaveta');
        if (oldGaveta) oldGaveta.remove();

        drawer = document.createElement('aside');
        drawer.className = 'portal-filter-drawer';
        drawer.id = 'portal-filter-drawer';
        drawer.setAttribute('aria-label', 'Painel de filtros retrátil à direita');
        document.body.appendChild(drawer);
      }

      drawer.innerHTML = `
        <div class="pfd-header">
          <div class="pfd-title-group">
            <svg class="ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 20a1 1 0 0 0 .55.89l2 1A1 1 0 0 0 14 21v-7a2 2 0 0 1 .52-1.34L21.74 4.67A1 1 0 0 0 21 3H3a1 1 0 0 0-.74 1.67l7.22 7.99A2 2 0 0 1 10 14z"/></svg>
            <span class="pfd-title">Filtros &amp; Parâmetros</span>
          </div>
          <button type="button" class="pfd-close-btn" id="close-filter-drawer-btn" aria-label="Fechar painel de filtros (Esc)" title="Fechar / Minimizar painel">
            <svg class="ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
          </button>
        </div>
        <div class="pfd-body drawer-body" id="pfd-body"></div>
        <div class="pfd-footer drawer-foot">
          <button type="button" class="btn btn-secondary" id="pfd-clear-btn">Limpar</button>
          <button type="button" class="btn btn-primary" id="pfd-apply-btn" style="flex:1;">Aplicar Filtros</button>
          <button type="button" class="btn btn-secondary" id="pfd-close-footer-btn">Fechar</button>
        </div>
      `;

      let scrim = document.getElementById('v2-scrim');
      if (!scrim) {
        scrim = document.createElement('div');
        scrim.className = 'v2-scrim';
        scrim.id = 'v2-scrim';
        scrim.hidden = true;
        document.body.appendChild(scrim);
      }
    }

    openDrawer() {
      const drawer = document.getElementById('portal-filter-drawer');
      const scrim = document.getElementById('v2-scrim');
      if (drawer) drawer.classList.add('is-open');
      if (scrim) scrim.hidden = false;
      this.rascunho = this.clonar(this.aplicado);
      this.sincronizarDrawerComRascunho();
    }

    closeDrawer() {
      const drawer = document.getElementById('portal-filter-drawer');
      const scrim = document.getElementById('v2-scrim');
      if (drawer) drawer.classList.remove('is-open');
      if (scrim) scrim.hidden = true;
      // Fecha todos os dropdowns abertos
      document.querySelectorAll('.custom-select').forEach(cs => {
        cs.classList.remove('active');
        const opt = cs.querySelector('.options-container');
        if (opt) opt.style.display = 'none';
      });
    }

    bindGlobalEvents() {
      const openBtn = document.getElementById('open-filter-drawer-btn');
      if (openBtn) openBtn.addEventListener('click', () => this.openDrawer());

      const closeBtn = document.getElementById('close-filter-drawer-btn');
      if (closeBtn) closeBtn.addEventListener('click', () => this.closeDrawer());

      const closeFooterBtn = document.getElementById('pfd-close-footer-btn');
      if (closeFooterBtn) closeFooterBtn.addEventListener('click', () => this.closeDrawer());

      const scrim = document.getElementById('v2-scrim');
      if (scrim) scrim.addEventListener('click', () => this.closeDrawer());

      const applyBtn = document.getElementById('pfd-apply-btn');
      if (applyBtn) {
        applyBtn.addEventListener('click', () => {
          this.aplicado = this.clonar(this.rascunho);
          this.closeDrawer();
          this.aplicar();
        });
      }

      const clearBtn = document.getElementById('pfd-clear-btn');
      if (clearBtn) {
        clearBtn.addEventListener('click', () => {
          this.filtros.forEach(f => {
            if (f.tipo === 'unico') {
              this.rascunho[f.id] = f.padrao ?? (f.opcoes[0]?.v || '');
            } else {
              this.rascunho[f.id] = new Set();
            }
          });
          this.sincronizarDrawerComRascunho();
        });
      }

      const resetTopBtn = document.getElementById('afb-reset');
      if (resetTopBtn) {
        resetTopBtn.addEventListener('click', () => {
          this.aplicado = this.getPadrao();
          this.rascunho = this.clonar(this.aplicado);
          this.sincronizarDrawerComRascunho();
          this.aplicar();
        });
      }

      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          const drawer = document.getElementById('portal-filter-drawer');
          if (drawer && drawer.classList.contains('is-open')) {
            this.closeDrawer();
          }
        }
      });
    }

    montarDrawer() {
      const body = document.getElementById('pfd-body');
      if (!body) return;
      body.innerHTML = '';

      // 1. Barra de Pesquisa Geral com Resultados Instantâneos e Destaque
      const searchBox = document.createElement('div');
      searchBox.className = 'drawer-global-search';
      searchBox.innerHTML = `
        <div class="select-trigger global-search-trigger">
          <svg class="search-ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--text-muted); flex:none;"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          <input type="text" id="pfd-global-search" class="search-input" placeholder="Pesquisar em todos os filtros..." autocomplete="off" />
          <button type="button" class="search-clear-btn" id="pfd-search-clear" style="display:none;" aria-label="Limpar busca">✕</button>
        </div>
        <div class="drawer-search-results" id="pfd-search-results" style="display:none;"></div>
      `;
      body.appendChild(searchBox);

      const globalSearchInput = searchBox.querySelector('#pfd-global-search');
      const searchClearBtn = searchBox.querySelector('#pfd-search-clear');
      const searchResultsEl = searchBox.querySelector('#pfd-search-results');

      const performGlobalSearch = () => {
        const rawQ = globalSearchInput.value.trim();
        const normQ = rawQ.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        const normQNoSpace = normQ.replace(/[^a-z0-9]/g, '');

        if (!normQ) {
          searchClearBtn.style.display = 'none';
          searchResultsEl.style.display = 'none';
          searchResultsEl.innerHTML = '';
          this.selectInstances.forEach((inst, fid) => {
            inst.filterOptions('');
            const wrapper = inst.container.closest('.filter-wrapper');
            if (wrapper) {
              wrapper.classList.remove('filter-has-match', 'filter-no-match');
              wrapper.style.opacity = '1';
              const badge = wrapper.querySelector('.filter-match-badge');
              if (badge) badge.remove();
            }
          });
          return;
        }

        searchClearBtn.style.display = 'inline-flex';

        // 1. Coleta correspondências em todas as opções de todos os filtros
        const matches = [];
        this.filtros.forEach(f => {
          if (!f.opcoes || f.opcoes.length === 0) return;
          const inst = this.selectInstances.get(f.id);
          const fMatches = [];
          f.opcoes.forEach(opt => {
            const rawOpt = String(opt.t || opt.v || '');
            const normOpt = rawOpt.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
            const normOptNoSpace = normOpt.replace(/[^a-z0-9]/g, '');
            if (normOpt.includes(normQ) || (normQNoSpace && normOptNoSpace.includes(normQNoSpace))) {
              fMatches.push(opt);
              matches.push({
                filterId: f.id,
                filterRotulo: f.rotulo,
                filterTipo: f.tipo,
                val: opt.v,
                txt: opt.t || opt.v
              });
            }
          });

          // Atualiza o select individual e seu wrapper
          if (inst) {
            inst.filterOptions(rawQ);
            const wrapper = inst.container.closest('.filter-wrapper');
            if (wrapper) {
              const label = wrapper.querySelector('.group-label');
              let badge = wrapper.querySelector('.filter-match-badge');
              if (fMatches.length > 0) {
                wrapper.classList.add('filter-has-match');
                wrapper.classList.remove('filter-no-match');
                wrapper.style.opacity = '1';
                if (!badge && label) {
                  badge = document.createElement('span');
                  badge.className = 'filter-match-badge';
                  label.appendChild(badge);
                }
                if (badge) badge.textContent = `${fMatches.length} ${fMatches.length === 1 ? 'opção' : 'opções'}`;
              } else {
                wrapper.classList.remove('filter-has-match');
                wrapper.classList.add('filter-no-match');
                wrapper.style.opacity = '0.35';
                if (badge) badge.remove();
              }
            }
          }
        });

        // 2. Renderiza lista de resultados rápidos sob a barra de busca
        searchResultsEl.innerHTML = '';
        if (matches.length === 0) {
          searchResultsEl.innerHTML = `<div class="dsr-empty">Nenhum valor correspondente a "${rawQ}"</div>`;
          searchResultsEl.style.display = 'block';
          return;
        }

        const hdr = document.createElement('div');
        hdr.className = 'dsr-header';
        hdr.textContent = `${matches.length} ${matches.length === 1 ? 'resultado encontrado' : 'resultados encontrados'}:`;
        searchResultsEl.appendChild(hdr);

        // Renderiza até 15 itens principais
        matches.slice(0, 15).forEach(m => {
          const item = document.createElement('div');
          item.className = 'dsr-item';
          const curVal = this.rascunho[m.filterId];
          const isSelected = m.filterTipo === 'unico'
            ? String(curVal) === String(m.val)
            : (curVal instanceof Set && curVal.has(m.val));

          item.innerHTML = `
            <div style="display:flex; align-items:center; gap:8px; overflow:hidden; flex:1;">
              <span class="dsr-tag">${m.filterRotulo}</span>
              <span class="dsr-val" title="${m.txt}">${m.txt}</span>
            </div>
            <button type="button" class="dsr-btn ${isSelected ? 'is-selected' : ''}">
              ${isSelected ? '✓ Selecionado' : '+ Selecionar'}
            </button>
          `;

          const btn = item.querySelector('.dsr-btn');
          const toggleSelection = (e) => {
            if (e) e.stopPropagation();
            const inst = this.selectInstances.get(m.filterId);
            if (!inst) return;

            if (m.filterTipo === 'unico') {
              this.rascunho[m.filterId] = m.val;
              inst.setSelected([m.val]);
            } else {
              if (!this.rascunho[m.filterId] || !(this.rascunho[m.filterId] instanceof Set)) {
                this.rascunho[m.filterId] = new Set();
              }
              const set = this.rascunho[m.filterId];
              if (set.has(m.val)) {
                set.delete(m.val);
              } else {
                set.add(m.val);
              }
              inst.setSelected(Array.from(set));
            }

            // Atualiza o botão no resultado
            const nowSelected = m.filterTipo === 'unico'
              ? String(this.rascunho[m.filterId]) === String(m.val)
              : (this.rascunho[m.filterId] instanceof Set && this.rascunho[m.filterId].has(m.val));
            btn.className = `dsr-btn ${nowSelected ? 'is-selected' : ''}`;
            btn.textContent = nowSelected ? '✓ Selecionado' : '+ Selecionar';

            // Abre / foca o dropdown correspondente suavemente para o usuário ver
            const targetSelect = inst.container;
            if (targetSelect) {
              targetSelect.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
          };

          item.addEventListener('click', toggleSelection);
          searchResultsEl.appendChild(item);
        });

        if (matches.length > 15) {
          const more = document.createElement('div');
          more.style.cssText = 'padding:6px 8px; font-size:11px; color:var(--text-muted); text-align:center; font-style:italic;';
          more.textContent = `+ mais ${matches.length - 15} opções disponíveis nos filtros destacados abaixo`;
          searchResultsEl.appendChild(more);
        }

        searchResultsEl.style.display = 'block';
      };

      globalSearchInput.addEventListener('input', performGlobalSearch);
      globalSearchInput.addEventListener('focus', () => {
        if (globalSearchInput.value.trim()) {
          searchResultsEl.style.display = 'block';
        }
      });
      searchClearBtn.addEventListener('click', () => {
        globalSearchInput.value = '';
        performGlobalSearch();
        globalSearchInput.focus();
      });
      document.addEventListener('click', (e) => {
        if (!searchBox.contains(e.target)) {
          searchResultsEl.style.display = 'none';
        }
      });

      // 2. Modo de Exibição (Valor / Volume)
      const secModo = document.createElement('div');
      secModo.className = 'drawer-section-title';
      secModo.style.display = 'flex';
      secModo.style.alignItems = 'center';
      secModo.style.justifyContent = 'space-between';
      secModo.innerHTML = `<span>Modo de Exibição</span><kbd style="font-size:10px; padding:1px 5px; border-radius:4px; background:var(--surface-sunken); border:1px solid var(--border); color:var(--text-muted); font-family:inherit; text-transform:none; letter-spacing:0;">Atalho: V</kbd>`;
      body.appendChild(secModo);

      const visControls = document.createElement('div');
      visControls.className = 'visualization-controls';
      visControls.style.marginBottom = '6px';
      const isVol = window.currentMetric === 'Volume';
      visControls.innerHTML = `
        <div class="segmented toggle-group" role="radiogroup" aria-label="Exibir valores em" style="width:100%; display:flex;">
          <button type="button" class="toggle-label ${!isVol ? 'active-label' : ''}" id="pfd-btn-val" role="radio" aria-checked="${!isVol}" style="flex:1;">Valor (R$)</button>
          <button type="button" class="toggle-label ${isVol ? 'active-label' : ''}" id="pfd-btn-vol" role="radio" aria-checked="${isVol}" style="flex:1;">Volume (Kg)</button>
        </div>
      `;
      body.appendChild(visControls);

      visControls.querySelector('#pfd-btn-val').addEventListener('click', () => {
        if (typeof window.setMetric === 'function') window.setMetric('Valor');
        const bVal = visControls.querySelector('#pfd-btn-val');
        const bVol = visControls.querySelector('#pfd-btn-vol');
        bVal.classList.add('active-label');
        bVal.setAttribute('aria-checked', 'true');
        bVol.classList.remove('active-label');
        bVol.setAttribute('aria-checked', 'false');
      });
      visControls.querySelector('#pfd-btn-vol').addEventListener('click', () => {
        if (typeof window.setMetric === 'function') window.setMetric('Volume');
        const bVal = visControls.querySelector('#pfd-btn-val');
        const bVol = visControls.querySelector('#pfd-btn-vol');
        bVol.classList.add('active-label');
        bVol.setAttribute('aria-checked', 'true');
        bVal.classList.remove('active-label');
        bVal.setAttribute('aria-checked', 'false');
      });

      // 3. Filtros de Período (Grid 2: Ano e Mês)
      const secPeriodo = document.createElement('div');
      secPeriodo.className = 'drawer-section-title';
      secPeriodo.textContent = 'Período de Análise';
      body.appendChild(secPeriodo);

      const gridPeriodo = document.createElement('div');
      gridPeriodo.className = 'drawer-grid-2';
      body.appendChild(gridPeriodo);

      const periodoFilters = this.filtros.filter(f => ['ano', 'mes'].includes(f.id));
      periodoFilters.forEach(f => {
        const wrap = this.criarCustomSelectWrapper(f);
        gridPeriodo.appendChild(wrap);
      });

      // 4. Gestão Comercial & Canais
      const comercialIds = ['gerente', 'canal', 'grupo_cliente', 'cluster', 'cluster_detalhe'];
      const comercialFilters = this.filtros.filter(f => comercialIds.includes(f.id));
      comercialFilters.sort((a, b) => comercialIds.indexOf(a.id) - comercialIds.indexOf(b.id));
      if (comercialFilters.length > 0) {
        const secCom = document.createElement('div');
        secCom.className = 'drawer-section-title';
        secCom.textContent = 'Gestão Comercial & Canais';
        body.appendChild(secCom);

        const stackCom = document.createElement('div');
        stackCom.className = 'drawer-stack';
        body.appendChild(stackCom);

        comercialFilters.forEach(f => {
          const wrap = this.criarCustomSelectWrapper(f);
          stackCom.appendChild(wrap);
        });
      }

      // 5. Portfólio & Unidades Fabris
      const prodIds = ['categoria', 'tipo_produto', 'filial'];
      const prodFilters = this.filtros.filter(f => prodIds.includes(f.id));
      prodFilters.sort((a, b) => prodIds.indexOf(a.id) - prodIds.indexOf(b.id));
      if (prodFilters.length > 0) {
        const secProd = document.createElement('div');
        secProd.className = 'drawer-section-title';
        secProd.textContent = 'Portfólio & Unidades Fabris';
        body.appendChild(secProd);

        const stackProd = document.createElement('div');
        stackProd.className = 'drawer-stack';
        body.appendChild(stackProd);

        prodFilters.forEach(f => {
          const wrap = this.criarCustomSelectWrapper(f);
          stackProd.appendChild(wrap);
        });
      }
    }

    criarCustomSelectWrapper(f) {
      const wrap = document.createElement('div');
      wrap.className = 'filter-group filter-wrapper';
      wrap.dataset.filterId = f.id;

      const label = document.createElement('label');
      label.className = 'group-label';
      label.setAttribute('for', `filter-input-${f.id}`);
      label.textContent = f.rotulo;
      wrap.appendChild(label);

      const cs = document.createElement('div');
      cs.className = 'custom-select';
      cs.id = `select-${f.id}`;
      cs.innerHTML = `
        <div class="select-trigger">
          <input type="text" class="search-input" id="filter-input-${f.id}" placeholder="Todos" autocomplete="off" />
          <span class="arrow" aria-hidden="true"></span>
        </div>
        <div class="options-container" style="display:none;"></div>
      `;
      wrap.appendChild(cs);

      const inst = this.setupCustomSelect(cs, f, (selectedVals) => {
        if (f.tipo === 'unico') {
          this.rascunho[f.id] = selectedVals[0] || '';
        } else {
          this.rascunho[f.id] = new Set(selectedVals);
        }
      });

      this.selectInstances.set(f.id, inst);
      return wrap;
    }

    setupCustomSelect(container, f, onChange) {
      const input = container.querySelector('.search-input');
      const optionsContainer = container.querySelector('.options-container');
      let allOptions = f.opcoes || [];
      let selectedValues = new Set();
      let matchingCount = allOptions.length;

      const showDropdown = () => {
        document.querySelectorAll('.custom-select').forEach(other => {
          if (other !== container) {
            other.classList.remove('active');
            const opt = other.querySelector('.options-container');
            if (opt) opt.style.display = 'none';
          }
        });
        optionsContainer.style.display = 'block';
        container.classList.add('active');
        input.focus();
        try { input.select(); } catch (e) {}
      };

      const closeDropdown = () => {
        optionsContainer.style.display = 'none';
        container.classList.remove('active');
        updateTriggerText();
      };

      const trigger = container.querySelector('.select-trigger');
      trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        if (e.target === input && optionsContainer.style.display === 'block') {
          return;
        }
        optionsContainer.style.display === 'block' ? closeDropdown() : showDropdown();
      });

      input.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeDropdown();
        else if ((e.key === 'ArrowDown' || e.key === 'Enter') && optionsContainer.style.display !== 'block') {
          showDropdown();
        }
      });

      document.addEventListener('click', (e) => {
        if (!container.contains(e.target)) closeDropdown();
      });

      function updateTriggerText() {
        if (selectedValues.size === 0) {
          input.value = '';
          input.placeholder = 'Todos';
        } else if (selectedValues.size === 1) {
          const val = Array.from(selectedValues)[0];
          const opt = allOptions.find(o => String(o.v) === String(val));
          input.value = opt ? opt.t : val;
        } else {
          input.value = `${selectedValues.size} sel.`;
        }
      }

      function renderOptions() {
        optionsContainer.innerHTML = '';
        if (allOptions.length === 0) {
          optionsContainer.innerHTML = `<div class="option-item" style="color:var(--text-muted); font-style:italic; justify-content:center; padding:10px;">Nenhum valor</div>`;
          return;
        }

        const frag = document.createDocumentFragment();

        if (f.tipo === 'multi') {
          const selectAllItem = document.createElement('div');
          selectAllItem.className = 'option-item select-all-item';
          const isAllChecked = (selectedValues.size === allOptions.length && allOptions.length > 0);
          selectAllItem.innerHTML = `
            <input type="checkbox" ${isAllChecked ? 'checked' : ''} />
            <span style="font-weight:700;">Selecionar Todos</span>
          `;
          frag.appendChild(selectAllItem);
        }

        allOptions.forEach(opt => {
          const item = document.createElement('div');
          item.className = 'option-item';
          const isChecked = selectedValues.has(opt.v);
          item.innerHTML = `
            <input type="${f.tipo === 'unico' ? 'radio' : 'checkbox'}" name="opt-${f.id}" value="${opt.v}" ${isChecked ? 'checked' : ''} />
            <span title="${opt.t}">${opt.t}</span>
          `;
          frag.appendChild(item);
        });

        optionsContainer.appendChild(frag);
      }

      optionsContainer.addEventListener('click', (e) => {
        const item = e.target.closest('.option-item');
        if (!item) return;
        const cb = item.querySelector('input');
        if (!cb) return;
        e.stopPropagation();

        if (e.target !== cb) {
          cb.checked = !cb.checked;
        }

        if (item.classList.contains('select-all-item')) {
          const isChecked = cb.checked;
          const checkboxes = optionsContainer.querySelectorAll('.option-item:not(.select-all-item) input');
          checkboxes.forEach(c => {
            c.checked = isChecked;
            if (isChecked) selectedValues.add(c.value);
            else selectedValues.delete(c.value);
          });
        } else {
          if (f.tipo === 'unico') {
            selectedValues.clear();
            selectedValues.add(cb.value);
            closeDropdown();
          } else {
            if (cb.checked) selectedValues.add(cb.value);
            else selectedValues.delete(cb.value);

            const allCb = optionsContainer.querySelector('.select-all-item input');
            if (allCb) allCb.checked = (selectedValues.size === allOptions.length && allOptions.length > 0);
          }
        }

        updateTriggerText();
        onChange(Array.from(selectedValues));
      });

      input.addEventListener('input', () => {
        if (optionsContainer.style.display !== 'block') {
          showDropdown();
        }
        const q = input.value.trim().toLowerCase();
        filterOptions(q);
      });

      function filterOptions(q) {
        let count = 0;
        const normQ = (q || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();
        const normQNoSpace = normQ.replace(/[^a-z0-9]/g, '');

        const selectAll = optionsContainer.querySelector('.select-all-item');
        if (selectAll) {
          if (normQ) {
            selectAll.style.setProperty('display', 'none', 'important');
            selectAll.classList.add('is-hidden');
            selectAll.hidden = true;
          } else {
            selectAll.style.removeProperty('display');
            selectAll.classList.remove('is-hidden');
            selectAll.hidden = false;
          }
        }

        const items = optionsContainer.querySelectorAll('.option-item:not(.select-all-item)');
        items.forEach(it => {
          const rawTxt = it.textContent || '';
          const normTxt = rawTxt.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
          const normTxtNoSpace = normTxt.replace(/[^a-z0-9]/g, '');
          const match = !normQ || normTxt.includes(normQ) || (normQNoSpace && normTxtNoSpace.includes(normQNoSpace));
          if (match) {
            it.style.removeProperty('display');
            it.classList.remove('is-hidden');
            it.hidden = false;
            count++;
          } else {
            it.style.setProperty('display', 'none', 'important');
            it.classList.add('is-hidden');
            it.hidden = true;
          }
        });
        matchingCount = count;
      }

      function setSelected(values) {
        selectedValues.clear();
        (values || []).forEach(v => selectedValues.add(String(v)));
        renderOptions();
        updateTriggerText();
      }

      renderOptions();
      updateTriggerText();

      return {
        container,
        setSelected,
        filterOptions,
        get matchingCount() { return matchingCount; }
      };
    }

    sincronizarDrawerComRascunho() {
      this.filtros.forEach(f => {
        const inst = this.selectInstances.get(f.id);
        if (!inst) return;
        const cur = this.rascunho[f.id];
        if (f.tipo === 'unico') {
          inst.setSelected(cur ? [cur] : []);
        } else {
          inst.setSelected(cur ? Array.from(cur) : []);
        }
      });
    }

    montarQuickFilters() {
      const qfContainer = document.getElementById('fpQuickFilters');
      if (!qfContainer) return;
      qfContainer.innerHTML = '';

      const quickIds = ['ano', 'mes', 'gerente'];
      quickIds.forEach(id => {
        const f = this.filtros.find(filter => filter.id === id);
        if (!f) return;

        const qf = document.createElement('div');
        qf.className = 'custom-select qf-select';
        qf.id = `qf-${f.id}`;
        qf.innerHTML = `
          <div class="select-trigger">
            <span class="qf-k">${f.rotulo}</span>
            <input type="text" class="search-input" id="qf-input-${f.id}" placeholder="Todos" autocomplete="off" />
            <span class="arrow" aria-hidden="true"></span>
          </div>
          <div class="options-container" style="display:none;"></div>
        `;
        qfContainer.appendChild(qf);

        const inst = this.setupCustomSelect(qf, f, (selectedVals) => {
          if (f.tipo === 'unico') {
            this.aplicado[f.id] = selectedVals[0] || '';
          } else {
            this.aplicado[f.id] = new Set(selectedVals);
          }
          this.rascunho = this.clonar(this.aplicado);
          this.aplicar();
        });

        this.quickInstances.set(f.id, inst);
      });
    }

    sincronizarQuickFilters() {
      this.quickInstances.forEach((inst, fid) => {
        const cur = this.aplicado[fid];
        const f = this.filtros.find(x => x.id === fid);
        if (f && f.tipo === 'unico') {
          inst.setSelected(cur ? [cur] : []);
        } else {
          inst.setSelected(cur ? Array.from(cur) : []);
        }
      });
    }

    montarChips() {
      const container = document.getElementById('afb-chips-container');
      if (!container) return;
      container.innerHTML = '';

      let drawerAtivosCount = 0;
      let totalModificados = 0;
      const quickFilterIds = new Set(['ano', 'mes', 'gerente']);

      this.filtros.forEach(f => {
        const cur = this.aplicado[f.id];
        let hasValue = false;
        let textVal = '';

        if (f.tipo === 'unico') {
          const def = f.padrao ?? (f.opcoes[0]?.v || '');
          if (cur && cur !== def) {
            hasValue = true;
            totalModificados++;
            const opt = f.opcoes.find(o => String(o.v) === String(cur));
            textVal = opt ? opt.t : cur;
          }
        } else {
          // Se for filtro de mês (ou outro com padrão), verifica se difere do padrão
          const defSet = f.padrao ? (f.padrao instanceof Set ? f.padrao : new Set(Array.isArray(f.padrao) ? f.padrao : [f.padrao])) : new Set();
          const curSet = cur || new Set();
          const isDefault = (curSet.size === defSet.size && [...curSet].every(x => defSet.has(x)));

          if (curSet.size > 0 && curSet.size < f.opcoes.length && !isDefault) {
            hasValue = true;
            totalModificados++;
            if (curSet.size === 1) {
              const val = [...curSet][0];
              const opt = f.opcoes.find(o => String(o.v) === String(val));
              textVal = opt ? opt.t : val;
            } else {
              textVal = `${curSet.size} sel.`;
            }
          }
        }

        // Não gera chip duplicado para filtros que já estão visíveis na barra rápida (ano, mês, gerente)
        if (hasValue && !quickFilterIds.has(f.id)) {
          drawerAtivosCount++;
          const chip = document.createElement('span');
          chip.className = 'afb-chip';
          chip.innerHTML = `
            <span>${f.rotulo}: <strong>${textVal}</strong></span>
            <button type="button" class="afb-chip-x" aria-label="Remover filtro ${f.rotulo}" title="Remover filtro">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
            </button>
          `;
          chip.querySelector('.afb-chip-x').addEventListener('click', (e) => {
            e.stopPropagation();
            if (f.tipo === 'unico') {
              this.aplicado[f.id] = f.padrao ?? (f.opcoes[0]?.v || '');
            } else {
              this.aplicado[f.id] = new Set();
            }
            this.rascunho = this.clonar(this.aplicado);
            this.aplicar();
          });
          container.appendChild(chip);
        } else if (hasValue && quickFilterIds.has(f.id)) {
          // Filtro rápido modificado fora do padrão
          drawerAtivosCount++;
        }
      });

      // Atualiza badge no botão Filtros
      const badge = document.getElementById('afb-count-badge');
      if (badge) {
        if (drawerAtivosCount > 0) {
          badge.textContent = String(drawerAtivosCount);
          badge.hidden = false;
          badge.style.display = 'inline-grid';
        } else {
          badge.hidden = true;
          badge.style.display = 'none';
        }
      }

      // Atualiza botão Limpar tudo no topo
      const resetTop = document.getElementById('afb-reset');
      if (resetTop) {
        resetTop.hidden = (totalModificados === 0);
      }
    }

    initIndicadoresPessoais() {
      const wrap = document.getElementById('fpBookmarksWrap');
      if (!wrap) return;

      wrap.innerHTML = `
        <button type="button" class="fp-bookmark-btn" id="btnPersonalBookmarks" aria-haspopup="true" aria-expanded="false" title="Indicadores pessoais (Segmentações salvas)">
          <svg class="ico-bm" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
          </svg>
          <span>Indicadores</span>
          <svg class="ico-chev" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
        </button>
        <div class="fp-bookmarks-dropdown" id="ddPersonalBookmarks" hidden>
          <div class="bm-dd-header">
            <div class="bm-dd-title">
              <span>Indicadores salvos</span>
            </div>
          </div>
          <button type="button" class="bm-save-action" id="btnSaveBookmarkAction">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            <span>Salvar filtros atuais</span>
          </button>
          <div class="bm-create-form" id="bmCreateForm" hidden>
            <input type="text" class="bm-input" id="bmNameInput" placeholder="Nome do indicador..." autocomplete="off" />
            <div class="bm-form-actions">
              <button type="button" class="btn btn-secondary btn-sm" id="bmCancelBtn">Cancelar</button>
              <button type="button" class="btn btn-primary btn-sm" id="bmConfirmSaveBtn">Salvar</button>
            </div>
          </div>
          <div class="bm-list" id="bmBookmarksList"></div>
        </div>
      `;

      const btn = wrap.querySelector('#btnPersonalBookmarks');
      const dd = wrap.querySelector('#ddPersonalBookmarks');
      const btnSave = wrap.querySelector('#btnSaveBookmarkAction');
      const createForm = wrap.querySelector('#bmCreateForm');
      const nameInput = wrap.querySelector('#bmNameInput');
      const btnCancel = wrap.querySelector('#bmCancelBtn');
      const btnConfirm = wrap.querySelector('#bmConfirmSaveBtn');
      const listEl = wrap.querySelector('#bmBookmarksList');

      this.getIdentidadeUsuario().then(() => {
        this.renderBookmarksList(listEl, dd, btn);
      });

      const showCreateForm = () => {
        btnSave.hidden = true;
        createForm.hidden = false;
        nameInput.value = '';
        nameInput.focus();
      };

      const hideCreateForm = () => {
        createForm.hidden = true;
        btnSave.hidden = false;
        nameInput.value = '';
      };

      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = !dd.hidden;
        dd.hidden = isOpen;
        btn.setAttribute('aria-expanded', String(!isOpen));
        if (!isOpen) {
          hideCreateForm();
          this.renderBookmarksList(listEl, dd, btn);
        }
      });

      document.addEventListener('click', (e) => {
        if (!dd.hidden && !wrap.contains(e.target)) {
          dd.hidden = true;
          btn.setAttribute('aria-expanded', 'false');
          hideCreateForm();
        }
      });

      btnSave.addEventListener('click', (e) => {
        e.stopPropagation();
        showCreateForm();
      });

      btnCancel.addEventListener('click', (e) => {
        e.stopPropagation();
        hideCreateForm();
      });

      const executeSave = () => {
        const nome = (nameInput.value || '').trim();
        if (!nome) {
          nameInput.focus();
          return;
        }

        const serializado = {};
        this.filtros.forEach(f => {
          const v = this.aplicado[f.id];
          serializado[f.id] = (v instanceof Set) ? Array.from(v) : v;
        });

        const key = this.getStorageKeyBookmarks();
        let bookmarks = [];
        try { bookmarks = JSON.parse(localStorage.getItem(key)) || []; } catch (err) {}
        bookmarks.unshift({
          id: 'bm_' + Date.now(),
          name: nome,
          filters: serializado,
          metric: window.currentMetric || 'Valor',
          created: new Date().toISOString()
        });
        try { localStorage.setItem(key, JSON.stringify(bookmarks)); } catch (err) {}

        hideCreateForm();
        this.renderBookmarksList(listEl, dd, btn);
      };

      btnConfirm.addEventListener('click', (e) => {
        e.stopPropagation();
        executeSave();
      });

      nameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          executeSave();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          hideCreateForm();
        }
      });
    }

    renderBookmarksList(listEl, dd, btn) {
      if (!listEl) return;
      listEl.innerHTML = '';
      const key = this.getStorageKeyBookmarks();
      let bookmarks = [];
      try { bookmarks = JSON.parse(localStorage.getItem(key)) || []; } catch (err) {}

      if (bookmarks.length === 0) {
        listEl.innerHTML = '<div style="padding:10px; font-size:11.5px; color:var(--text-muted); text-align:center; font-style:italic;">Nenhum indicador salvo</div>';
        return;
      }

      bookmarks.forEach(bm => {
        const row = document.createElement('div');
        row.className = 'bm-item';
        row.innerHTML = `
          <div class="bm-item-left">
            <svg class="bm-item-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/></svg>
            <span class="bm-item-name" title="${bm.name}">${bm.name}</span>
          </div>
          <button type="button" class="bm-item-delete" title="Excluir indicador" aria-label="Excluir ${bm.name}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        `;

        row.querySelector('.bm-item-left').addEventListener('click', (e) => {
          e.stopPropagation();
          if (bm.filters) {
            this.filtros.forEach(f => {
              const val = bm.filters[f.id];
              if (val !== undefined) {
                this.aplicado[f.id] = (f.tipo === 'unico') ? val : new Set(Array.isArray(val) ? val : [val]);
              }
            });
            this.rascunho = this.clonar(this.aplicado);
            if (bm.metric && typeof window.setMetric === 'function') {
              window.setMetric(bm.metric);
            }
            this.aplicar();
          }
          dd.hidden = true;
          btn.setAttribute('aria-expanded', 'false');
        });

        row.querySelector('.bm-item-delete').addEventListener('click', (e) => {
          e.stopPropagation();
          let bms = [];
          try { bms = JSON.parse(localStorage.getItem(key)) || []; } catch (err) {}
          bms = bms.filter(x => x.id !== bm.id);
          try { localStorage.setItem(key, JSON.stringify(bms)); } catch (err) {}
          this.renderBookmarksList(listEl, dd, btn);
        });

        listEl.appendChild(row);
      });
    }

    syncMetricButtons(metric) {
      const isVol = metric === 'Volume';
      ['#afb-btn-val', '#pfd-btn-val'].forEach(sel => {
        const b = document.querySelector(sel);
        if (b) {
          b.classList.toggle('active-label', !isVol);
          b.setAttribute('aria-checked', String(!isVol));
        }
      });
      ['#afb-btn-vol', '#pfd-btn-vol'].forEach(sel => {
        const b = document.querySelector(sel);
        if (b) {
          b.classList.toggle('active-label', isVol);
          b.setAttribute('aria-checked', String(isVol));
        }
      });
    }

    atualizarTudo() {
      this.sincronizarDrawerComRascunho();
      this.sincronizarQuickFilters();
      this.montarChips();
      this.syncMetricButtons(window.currentMetric || 'Valor');
    }

    aplicar() {
      this.atualizarTudo();
      const payload = this.getPayload();
      this.onApplyCallback(payload);
    }

    getPayload() {
      const res = {};
      this.filtros.forEach(f => {
        const val = this.aplicado[f.id];
        if (f.tipo === 'unico') {
          res[f.id] = val || 'Todos';
        } else {
          if (!val || val.size === 0 || val.size === f.opcoes.length) {
            res[f.id] = 'Todos';
          } else {
            res[f.id] = Array.from(val);
          }
        }
      });
      return res;
    }
  }

  window.showFilterUpdatingIndicator = function (msg) {
  let t = document.getElementById('v2-loading-toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'v2-loading-toast';
    t.className = 'v2-loading-toast';
    t.setAttribute('role', 'status');
    t.setAttribute('aria-live', 'polite');
    t.innerHTML = '<span class="v2-spin" aria-hidden="true"></span><span class="v2-loading-txt">Atualizando indicadores…</span><span class="v2-loading-track" aria-hidden="true"><span></span></span>';
    document.body.appendChild(t);
  }
  const txtEl = t.querySelector('.v2-loading-txt');
  if (txtEl) txtEl.textContent = msg || 'Atualizando indicadores…';
  clearTimeout(window.__v2LoadHideT);
  t.hidden = false;
  requestAnimationFrame(() => t.classList.add('is-on'));
  document.body.classList.add('v2-refreshing');
};

window.hideFilterUpdatingIndicator = function () {
  const t = document.getElementById('v2-loading-toast');
  if (t) {
    t.classList.remove('is-on');
    window.__v2LoadHideT = setTimeout(() => { t.hidden = true; }, 220);
  }
  document.body.classList.remove('v2-refreshing');
};

window.DNACache = {
  getMetadata: async function () {
    const KEY = 'dna_meta_v1';
    const TTL = 15 * 60 * 1000;
    try {
      const raw = sessionStorage.getItem(KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && parsed.ts && (Date.now() - parsed.ts < TTL) && parsed.data) {
          return parsed.data;
        }
      }
    } catch (_) {}
    const res = await fetch('/api/metadata');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    try { sessionStorage.setItem(KEY, JSON.stringify({ ts: Date.now(), data })); } catch (_) {}
    return data;
  },
  postJson: async function (url, payload, signal, ttlMs = 5 * 60 * 1000) {
    const key = 'dna_post_v1:' + url + ':' + JSON.stringify(payload);
    try {
      const raw = sessionStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && parsed.ts && (Date.now() - parsed.ts < ttlMs) && parsed.data) {
          return parsed.data;
        }
      }
    } catch (_) {}
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    try { sessionStorage.setItem(key, JSON.stringify({ ts: Date.now(), data })); } catch (_) {}
    return data;
  }
};

window.DNAFiltersPanel = DNAFiltersPanel;
})();
