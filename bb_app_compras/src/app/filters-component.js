/**
 * PORTAL COMPRAS | Grupo Bimbo Brasil
 * Painel de Filtros Retrátil à Direita (F1 a F11 / identidade-da.md / filtros-referencia.html)
 */

(function () {
  'use strict';

  const STORAGE_KEY = 'portal_compras_filtros_estado';
  const TXT = {
    pt: {
      todos: 'Todos',
      selecionados: n => `${n} selecionados`,
      pesquisar: 'Pesquisar...',
      selTodos: 'Selecionar todos',
      soResultados: n => `Somente os resultados (${n})`,
      somente: 'Somente',
      somenteDe: t => `Selecionar somente ${t}`,
      vazio: 'Nenhum resultado',
      aplicar: 'Aplicar',
      limpar: 'Limpar',
      limparTudo: 'Limpar tudo',
      filtros: 'Filtros',
      fechar: 'Fechar',
      recolher: 'Recolher filtros',
      expandir: 'Expandir filtros',
      remover: t => `Remover filtro ${t}`
    },
    en: {
      todos: 'All',
      selecionados: n => `${n} selected`,
      pesquisar: 'Search...',
      selTodos: 'Select all',
      soResultados: n => `Only search results (${n})`,
      somente: 'Only',
      somenteDe: t => `Select only ${t}`,
      vazio: 'No results',
      aplicar: 'Apply',
      limpar: 'Clear',
      limparTudo: 'Clear all',
      filtros: 'Filters',
      fechar: 'Close',
      recolher: 'Collapse filters',
      expandir: 'Expand filters',
      remover: t => `Remove filter ${t}`
    },
    es: {
      todos: 'Todos',
      selecionados: n => `${n} seleccionados`,
      pesquisar: 'Buscar...',
      selTodos: 'Seleccionar todo',
      soResultados: n => `Solo los resultados (${n})`,
      somente: 'Solo',
      somenteDe: t => `Seleccionar solo ${t}`,
      vazio: 'Sin resultados',
      aplicar: 'Aplicar',
      limpar: 'Limpiar',
      limparTudo: 'Limpiar todo',
      filtros: 'Filtros',
      fechar: 'Cerrar',
      recolher: 'Contraer filtros',
      expandir: 'Expandir filtros',
      remover: t => `Quitar filtro ${t}`
    }
  };

  function getTexts() {
    const lang = (document.documentElement.lang || 'pt').slice(0, 2);
    return TXT[lang] || TXT.pt;
  }

  class DNAFiltersPanel {
    constructor(config) {
      this.layoutEl = document.getElementById(config.layoutId || 'appLayout');
      this.resumoEl = document.getElementById(config.resumoId || 'fpResumo');
      this.chipsEl = document.getElementById(config.chipsId || 'fpChips');
      this.limparTudoBtn = document.getElementById(config.limparTudoId || 'fpLimparTudo');
      this.abrirGavetaBtn = document.getElementById(config.abrirGavetaId || 'fpAbrirGaveta');

      this.lateralEl = document.getElementById(config.lateralId || 'fpLateral');
      this.trilhoBtn = document.getElementById(config.trilhoId || 'fpExpandir');
      this.trilhoContador = document.getElementById(config.trilhoContadorId || 'fpTrilhoContador');
      this.trilhoTexto = document.getElementById(config.trilhoTextoId || 'fpTrilhoTexto');

      this.abertoEl = document.getElementById(config.abertoId || 'fpAberto');
      this.tituloLateral = document.getElementById(config.tituloLateralId || 'fpTituloLateral');
      this.lateralContador = document.getElementById(config.lateralContadorId || 'fpLateralContador');
      this.recolherBtn = document.getElementById(config.recolherId || 'fpRecolher');
      this.corpoLateral = document.getElementById(config.corpoLateralId || 'fpCorpoLateral');
      this.limparBtn = document.getElementById(config.limparId || 'fpLimpar');
      this.aplicarBtn = document.getElementById(config.aplicarId || 'fpAplicar');

      this.gavetaEl = document.getElementById(config.gavetaId || 'fpGaveta');
      this.tituloGaveta = document.getElementById(config.tituloGavetaId || 'fpTituloGaveta');
      this.fecharGavetaBtn = document.getElementById(config.fecharGavetaId || 'fpFecharGaveta');
      this.corpoGaveta = document.getElementById(config.corpoGavetaId || 'fpCorpoGaveta');
      this.gavetaLimparBtn = document.getElementById(config.gavetaLimparId || 'fpGavetaLimpar');
      this.gavetaAplicarBtn = document.getElementById(config.gavetaAplicarId || 'fpGavetaAplicar');

      this.config = config || {};
      this.filtros = config.filtros || [];
      this.onApplyCallback = config.onApply || (() => {});
      this.seq = 0;

      this.init();
    }

    _normalizarOpcao(o) {
      if (o === null || o === undefined) return null;
      if (typeof o === 'object') {
        if ('v' in o) {
          const val = String(o.v ?? '').trim();
          if (!val) return null;
          return { v: val, t: String(o.t !== undefined ? o.t : val) };
        }
        return null;
      }
      const str = String(o).trim();
      if (!str) return null;
      return { v: str, t: str };
    }

    _normalizarListaOpcoes(lista) {
      return (lista || [])
        .map(o => this._normalizarOpcao(o))
        .filter(Boolean);
    }

    init() {
      // Normaliza opções com total segurança contra nulos e tipos mistos
      this.filtros.forEach(f => {
        f.opcoes = this._normalizarListaOpcoes(f.opcoes);
        // Padrões nativos corporativos GB Brasil Compras:
        if ((f.key === 'is_fornecedor_nao_negociavel' || f.id === 'fFornNegociavel') && (!f.padrao || !f.padrao.length)) {
          f.padrao = ['NEGOCIAVEL'];
        }
        if ((f.key === 'is_fornecedor_sem_oc' || f.id === 'fFornSemOC') && (!f.padrao || !f.padrao.length)) {
          f.padrao = ['COM ATUAÇÃO'];
        }
      });

      this.aplicado = this.getPadrao();
      // Restore by API key, since pages can use different IDs for the same filter.
      try {
        const key = window.FilterStateStore ? window.FilterStateStore.STORAGE_KEY : 'portal_compras_shared_filters';
        const shared = JSON.parse(localStorage.getItem(key) || '{}');
        this.filtros.forEach(f => {
          const saved = shared[f.key] !== undefined ? shared[f.key] : shared[f.id];
          if (saved === '__ALL__' && f.tipo !== 'unico') {
            this.aplicado[f.id] = new Set();
          } else if (Array.isArray(saved)) {
            this.aplicado[f.id] = f.tipo === 'unico'
              ? (saved.length ? String(saved[0]) : this.aplicado[f.id])
              : new Set(saved.map(String));
          }
        });
      } catch (err) {
        console.warn('Não foi possível restaurar os filtros compartilhados:', err);
      }
      this.rascunho = this.clonar(this.aplicado);

      this.initTextos();
      this.initEstadoPainel();
      this.bindEvents();
      try {
        this.montarInterface();
      } catch (err) {
        console.error('Erro ao montar interface dos filtros:', err);
      }
      this.syncWithGlobalFilters();
      this.atualizarTudo();
    }

    syncWithGlobalFilters() {
      if (typeof window.filters === 'undefined') window.filters = {};
      this.filtros.forEach(f => {
        const item = {
          id: f.id,
          key: f.key,
          options: f.opcoes.map(o => o.v),
          selected: f.tipo === 'unico' 
            ? new Set(this.aplicado[f.id] ? [String(this.aplicado[f.id])] : [])
            : (this.aplicado[f.id] instanceof Set ? this.aplicado[f.id] : new Set()),
          getSelected: () => {
            const val = this.aplicado[f.id];
            if (f.tipo === 'unico') {
              return val ? [String(val)] : [];
            }
            if (val && val instanceof Set && val.has('__NONE__')) {
              return ['__NONE__'];
            }
            if (!val || !(val instanceof Set) || val.size === 0 || this.todosSelecionados(f, val)) {
              return [];
            }
            return [...val].filter(x => x !== '__NONE__').map(String);
          },
          setOptions: (opts) => {
            f.opcoes = this._normalizarListaOpcoes(opts);
            this.syncWithGlobalFilters();
            this.montarInterface();
            this.atualizarTudo();
          },
          renderOptions: () => {},
          updateLabel: () => {}
        };
        window.filters[f.id] = item;
        if (typeof filters !== 'undefined') {
          try { filters[f.id] = item; } catch (e) {}
        }
      });
    }

    updateDefinitions(newFiltros) {
      newFiltros.forEach(nf => {
        const existing = this.filtros.find(f => f.id === nf.id);
        if (existing) {
          existing.opcoes = this._normalizarListaOpcoes(nf.opcoes);
          if (nf.padrao !== undefined) existing.padrao = nf.padrao;
        } else {
          nf.opcoes = this._normalizarListaOpcoes(nf.opcoes);
          this.filtros.push(nf);
          try {
            const state = JSON.parse(localStorage.getItem('portal_compras_shared_filters') || '{}');
            const saved = state[nf.key || nf.id];
            if (saved === '__ALL__' && nf.tipo !== 'unico') this.aplicado[nf.id] = new Set();
            else if (Array.isArray(saved)) this.aplicado[nf.id] = nf.tipo === 'unico' ? String(saved[0] || '') : new Set(saved.map(String));
          } catch (_) {}
        }
      });
      this.filtros.forEach(f => {
        if (f.tipo === 'unico') {
          const val = this.aplicado[f.id];
          if (!val && f.opcoes.length > 0) {
            this.aplicado[f.id] = (f.padrao !== undefined && f.padrao !== null) ? String(f.padrao) : f.opcoes[0].v;
          }
        } else {
          if (!(this.aplicado[f.id] instanceof Set)) {
            this.aplicado[f.id] = f.padrao ? new Set(f.padrao) : new Set();
          }
        }
      });
      this.rascunho = this.clonar(this.aplicado);
      this.syncWithGlobalFilters();
      this.montarInterface();
      this.atualizarTudo();
    }

    getPadrao() {
      return Object.fromEntries(
        this.filtros.map(f => {
          if (f.tipo === 'unico') {
            const validVals = (f.opcoes || []).map(o => String(o.v !== undefined ? o.v : o));
            let val = f.padrao !== undefined && f.padrao !== null ? String(f.padrao) : '';
            if ((!val || !validVals.includes(val)) && validVals.length > 0) {
              val = validVals[0];
            }
            return [f.id, val];
          }
          if ((f.key === 'is_fornecedor_nao_negociavel' || f.id === 'fFornNegociavel') && (!f.padrao || !f.padrao.length)) {
            return [f.id, new Set(['NEGOCIAVEL'])];
          }
          if ((f.key === 'is_fornecedor_sem_oc' || f.id === 'fFornSemOC') && (!f.padrao || !f.padrao.length)) {
            return [f.id, new Set(['COM ATUAÇÃO'])];
          }
          return [f.id, f.padrao ? new Set(f.padrao) : new Set()];
        })
      );
    }

    clonar(e) {
      return Object.fromEntries(
        Object.entries(e).map(([k, v]) => [k, v instanceof Set ? new Set(v) : v])
      );
    }

    todosSelecionados(f, valores) {
      return f.opcoes.length > 0 && valores.size === f.opcoes.length && f.opcoes.every(o => valores.has(String(o.v)));
    }

    saoIguais(a, b) {
      return this.filtros.every(f => {
        if (f.tipo === 'unico') return a[f.id] === b[f.id];
        const sa = a[f.id] || new Set();
        const sb = b[f.id] || new Set();
        if (sa.size !== sb.size) return false;
        for (let x of sa) {
          if (!sb.has(x)) return false;
        }
        return true;
      });
    }

    normalizar(f) {
      if (f.tipo === 'multi') {
        const s = this.rascunho[f.id];
        if (s && s instanceof Set && !s.has('__NONE__') && this.todosSelecionados(f, s)) {
          this.rascunho[f.id] = new Set();
        }
      }
    }

    isAtivo(f, est = this.rascunho) {
      if (f.tipo === 'unico') {
        const def = f.padrao ?? (f.opcoes[0]?.v || '');
        return est[f.id] !== def;
      }
      const s = est[f.id];
      if (!s || !(s instanceof Set)) return false;
      if (s.has('__NONE__')) return true;

      // Se filtro tem padrão definido (ex: Fornecedor Negociável ['NEGOCIAVEL'])
      if (f.padrao && Array.isArray(f.padrao)) {
        const padraoSet = new Set(f.padrao.map(String));
        if (s.size === padraoSet.size && [...s].every(x => padraoSet.has(String(x)))) {
          return false;
        }
      }

      if (s.size === 0 || this.todosSelecionados(f, s)) return false;
      return s.size > 0;
    }

    getResumo(f, est = this.rascunho) {
      const T = getTexts();
      if (f.tipo === 'unico') {
        return f.opcoes.find(o => o.v === est[f.id])?.t ?? est[f.id] ?? '';
      }
      const s = est[f.id];
      if (s && s instanceof Set && s.has('__NONE__')) {
        return typeof window.t === 'function' ? window.t('Nenhum') : 'Nenhum';
      }
      if (!s || !(s instanceof Set) || s.size === 0 || this.todosSelecionados(f, s)) {
        if (f.key === 'mes' || f.id === 'fMes') return 'Ano Fechado (Todos)';
        return T.todos;
      }
      if (s.size === 1) {
        const v = [...s][0];
        return f.opcoes.find(o => String(o.v) === String(v))?.t || v;
      }

      // Tratamento especial intuitivo para Mês (Ano Acumulado / Intervalo de Meses)
      if (f.key === 'mes' || f.id === 'fMes') {
        const nums = [...s].map(Number).filter(n => !isNaN(n)).sort((a, b) => a - b);
        const isSequential = nums.length > 0 && nums.every((n, i) => i === 0 || n === nums[i - 1] + 1);
        if (isSequential && nums[0] === 1) {
          const ultimoNome = f.opcoes.find(o => Number(o.v) === nums[nums.length - 1])?.t?.split('-')[1]?.trim() || nums[nums.length - 1];
          return `Acumulado (Jan a ${ultimoNome})`;
        }
        if (isSequential) {
          const mIni = f.opcoes.find(o => Number(o.v) === nums[0])?.t?.split('-')[1]?.trim() || nums[0];
          const mFim = f.opcoes.find(o => Number(o.v) === nums[nums.length - 1])?.t?.split('-')[1]?.trim() || nums[nums.length - 1];
          return `${mIni} a ${mFim}`;
        }
        return `${s.size} meses`;
      }

      return T.selecionados(s.size);
    }

    isMarcado(f, v) {
      if (f.tipo === 'unico') return this.rascunho[f.id] === v;
      const s = this.rascunho[f.id];
      if (s && s instanceof Set && s.has('__NONE__')) return false;
      return (!s || !(s instanceof Set) || s.size === 0 || s.has(v));
    }

    totalAtivos(est = this.aplicado) {
      return this.filtros.filter(f => this.isAtivo(f, est)).length;
    }

    initTextos() {
      const T = getTexts();
      if (this.trilhoTexto) this.trilhoTexto.textContent = T.filtros;
      if (this.tituloLateral) this.tituloLateral.textContent = T.filtros;
      if (this.tituloGaveta) this.tituloGaveta.textContent = T.filtros;
      if (this.limparBtn) this.limparBtn.textContent = T.limpar;
      if (this.aplicarBtn) this.aplicarBtn.textContent = T.aplicar;
      if (this.gavetaLimparBtn) this.gavetaLimparBtn.textContent = T.limpar;
      if (this.gavetaAplicarBtn) this.gavetaAplicarBtn.textContent = T.aplicar;
      if (this.limparTudoBtn) {
        const span = this.limparTudoBtn.querySelector('span');
        if (span) span.textContent = T.limparTudo;
        else this.limparTudoBtn.textContent = T.limparTudo;
      }
      if (this.recolherBtn) this.recolherBtn.setAttribute('aria-label', T.recolher);
      if (this.trilhoBtn) this.trilhoBtn.setAttribute('aria-label', T.expandir);
    }

    initEstadoPainel() {
      // Padrão nativo do app: sempre minimizado ('recolhido' no trilho de 48px)
      const estado = (this.config && this.config.estadoInicial) || 'recolhido';
      this.setEstadoPainel(estado, false);
    }

    setEstadoPainel(estado, salvar = true) {
      const layout = this.layoutEl || document.getElementById('appLayout') || document.querySelector('.layout') || document.body;
      if (layout) {
        layout.setAttribute('data-filtros', estado);
      }
      const aberto = (estado === 'aberto');
      if (this.recolherBtn) this.recolherBtn.setAttribute('aria-expanded', String(aberto));
      if (this.trilhoBtn) this.trilhoBtn.setAttribute('aria-expanded', String(aberto));

      if (salvar) {
        try { localStorage.setItem(STORAGE_KEY, estado); } catch (e) {}
      }

      try { window.dispatchEvent(new Event('resize')); } catch (e) {}
    }

    criarLista(f, aoMudar, grupo) {
      const T = getTexts();
      const wrap = document.createElement('div');
      wrap.className = 'fp-lista-wrap';
      let busca = null;

      if (f.opcoes.length >= 8) {
        busca = document.createElement('input');
        busca.type = 'search';
        busca.className = 'fp-busca';
        busca.placeholder = T.pesquisar;
        busca.setAttribute('aria-label', `${T.pesquisar} ${f.rotulo}`);
        wrap.append(busca);
      }

      const ul = document.createElement('ul');
      ul.className = 'fp-lista';
      wrap.append(ul);

      const linha = (texto, checked, onToggle, comSomente, tipo, extraClasse) => {
        const li = document.createElement('li');
        li.className = 'fp-opcao' + (extraClasse ? ' ' + extraClasse : '');
        const id = `fp-${f.id}-${grupo}-${this.seq++}`;
        li.innerHTML = `<label><input id="${id}" type="${tipo}" name="fp-${f.id}-${grupo}"><span></span></label>`;
        const input = li.querySelector('input');
        li.querySelector('span').textContent = texto;
        input.checked = (checked === true);
        input.indeterminate = (checked === 'misto');
        input.addEventListener('change', onToggle);

        if (comSomente) {
          const b = document.createElement('button');
          b.type = 'button';
          b.className = 'fp-somente';
          b.textContent = T.somente;
          b.setAttribute('aria-label', T.somenteDe(texto));
          b.addEventListener('click', (e) => {
            e.stopPropagation();
            comSomente();
          });
          li.append(b);
        }
        ul.append(li);
      };

      const render = () => {
        const normalize = v => String(v || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
        const termo = normalize((busca?.value || '').trim());
        const visiveis = f.opcoes.filter(o => normalize(o.t).includes(termo));
        ul.innerHTML = '';

        if (f.tipo === 'multi' && visiveis.length) {
          if (termo) {
            const todosVisiveisMarcados = visiveis.length > 0 && visiveis.every(o => this.isMarcado(f, o.v));
            const nenhumVisivelMarcado = visiveis.length > 0 && visiveis.every(o => !this.isMarcado(f, o.v));
            const estadoChecked = todosVisiveisMarcados ? true : (nenhumVisivelMarcado ? false : 'misto');
            linha(
              T.soResultados(visiveis.length),
              estadoChecked,
              () => {
                const sAtual = this.rascunho[f.id] || new Set();
                let novo;
                if (sAtual.has('__NONE__')) {
                  novo = new Set();
                } else if (sAtual.size === 0) {
                  novo = new Set(f.opcoes.map(x => x.v));
                } else {
                  novo = new Set(sAtual);
                }
                novo.delete('__NONE__');

                const todosVisiveisEstavamMarcados = visiveis.length > 0 && visiveis.every(o => this.isMarcado(f, o.v));
                if (todosVisiveisEstavamMarcados) {
                  visiveis.forEach(o => novo.delete(o.v));
                  if (novo.size === 0) novo.add('__NONE__');
                } else {
                  visiveis.forEach(o => novo.add(o.v));
                }
                this.rascunho[f.id] = novo;
                this.normalizar(f);
                aoMudar();
                render();
              },
              null,
              'checkbox',
              'fp-todos'
            );
          } else {
            const todosMarcados = visiveis.length > 0 && visiveis.every(o => this.isMarcado(f, o.v));
            const nenhumMarcado = visiveis.length > 0 && visiveis.every(o => !this.isMarcado(f, o.v));
            const estadoChecked = todosMarcados ? true : (nenhumMarcado ? false : 'misto');
            linha(
              T.selTodos,
              estadoChecked,
              () => {
                const todosEstavamMarcados = visiveis.length > 0 && visiveis.every(o => this.isMarcado(f, o.v));
                if (todosEstavamMarcados) {
                  // Ao clicar em selecionar todos, caso todos já estejam selecionados, deseleciona todos!
                  this.rascunho[f.id] = new Set(['__NONE__']);
                } else {
                  // Caso contrário, seleciona todos!
                  this.rascunho[f.id] = new Set(f.opcoes.map(o => o.v));
                }
                this.normalizar(f);
                aoMudar();
                render();
              },
              null,
              'checkbox',
              'fp-todos'
            );
          }
        }

        visiveis.forEach(o => {
          linha(
            o.t,
            this.isMarcado(f, o.v),
            (ev) => {
              if (f.tipo === 'unico') {
                this.rascunho[f.id] = o.v;
                aoMudar();
                render();
                return;
              }
              const sAtual = this.rascunho[f.id];
              let s;
              if (sAtual && sAtual.has('__NONE__')) {
                s = new Set();
              } else if (!sAtual || sAtual.size === 0) {
                s = new Set(f.opcoes.map(x => x.v));
              } else {
                s = new Set(sAtual);
              }
              s.delete('__NONE__');

              if (ev.target.checked) {
                s.add(o.v);
              } else {
                s.delete(o.v);
              }

              if (s.size === 0) {
                s.add('__NONE__');
              }
              this.rascunho[f.id] = s;
              this.normalizar(f);
              aoMudar();
              render();
            },
            f.tipo === 'multi' ? () => {
              this.rascunho[f.id] = new Set([o.v]);
              this.normalizar(f);
              aoMudar();
              render();
            } : null,
            f.tipo === 'unico' ? 'radio' : 'checkbox'
          );
        });

        if (!visiveis.length) {
          const li = document.createElement('li');
          li.className = 'fp-vazio';
          li.textContent = T.vazio;
          ul.append(li);
        }
      };

      if (busca) {
        busca.addEventListener('input', render);
      }

      return { el: wrap, render, limparBusca: () => { if (busca) busca.value = ''; } };
    }

    montarSecoes(container, grupo) {
      if (!container) return [];
      container.innerHTML = '';
      const seta = '<svg class="fp-seta" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
      const search = document.createElement('input');
      search.type = 'search';
      search.className = 'fp-busca fp-busca-central';
      const lang = (document.documentElement.lang || 'pt').slice(0, 2);
      const label = {pt: 'Pesquisar filtros e opções', en: 'Search filters and options', es: 'Buscar filtros y opciones'}[lang] || 'Pesquisar filtros e opções';
      search.placeholder = label;
      search.setAttribute('aria-label', label);
      container.append(search);
      const empty = document.createElement('p');
      empty.className = 'fp-busca-vazia';
      empty.textContent = 'Nenhum filtro encontrado.';
      empty.hidden = true;

      const secoes = this.filtros.map(f => {
        const d = document.createElement('details');
        d.className = 'fp-secao';
        d.setAttribute('data-filtro', f.id);
        d.innerHTML = `
          <summary>
            <span class="fp-nome">${f.rotulo}</span>
            <span class="fp-valor"></span>
            ${seta}
          </summary>
        `;
        const ctrl = this.criarLista(f, () => this.aoMudarRascunho(), grupo);
        d.append(ctrl.el);

        d.addEventListener('toggle', () => {
          if (d.open) ctrl.render();
          else ctrl.limparBusca();
        });

        container.append(d);
        return { el: d, filtro: f, renderLista: ctrl.render };
      });
      container.append(empty);
      const normalizar = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
      search.addEventListener('input', () => {
        const termo = normalizar(search.value.trim());
        let encontrados = 0;
        secoes.forEach(({el, filtro, renderLista}) => {
          const nomeCorresponde = normalizar(filtro.rotulo).includes(termo);
          const opcaoCorresponde = termo && filtro.opcoes.some(o => normalizar(o.t).includes(termo));
          const visivel = !termo || nomeCorresponde || opcaoCorresponde;
          el.hidden = !visivel;
          if (visivel) encontrados++;
          if (termo && opcaoCorresponde && !nomeCorresponde) {
            el.open = true;
            const buscaOpcao = el.querySelector('.fp-lista-wrap .fp-busca');
            if (buscaOpcao) { buscaOpcao.value = search.value.trim(); renderLista(); }
          } else if (!termo) {
            const buscaOpcao = el.querySelector('.fp-lista-wrap .fp-busca');
            if (buscaOpcao && buscaOpcao.value) { buscaOpcao.value = ''; if (el.open) renderLista(); }
          }
        });
        empty.hidden = encontrados > 0;
      });
      return secoes;
    }

    montarInterface() {
      this.secoesLateral = this.montarSecoes(this.corpoLateral, 'lat');
      this.secoesGaveta = this.montarSecoes(this.corpoGaveta, 'gav');
    }

    aoMudarRascunho() {
      this.atualizarBotoesEAvisos();
      this.sincronizarSecoes();
    }

    sincronizarSecoes() {
      const atualizar = list => (list || []).forEach(s => {
        const valEl = s.el.querySelector('.fp-valor');
        if (valEl) valEl.textContent = this.getResumo(s.filtro);
        s.el.classList.toggle('ativo', this.isAtivo(s.filtro));
        if (s.el.open) s.renderLista();
      });
      atualizar(this.secoesLateral);
      atualizar(this.secoesGaveta);
    }

    atualizarBotoesEAvisos() {
      const mudou = !this.saoIguais(this.rascunho, this.aplicado);
      if (this.aplicarBtn) this.aplicarBtn.disabled = !mudou;
      if (this.gavetaAplicarBtn) this.gavetaAplicarBtn.disabled = !mudou;
    }

    getChipsAtivos(est = this.aplicado) {
      const chips = [];

      this.filtros.forEach(f => {
        // 1. Filtro de Ano (Sempre visível para contextualização temporal imediata)
        if (f.key === 'ano' || f.id === 'fAno') {
          const val = est[f.id];
          if (val) {
            chips.push({
              filtro: f,
              label: 'Ano',
              val: String(val),
              podeRemover: true
            });
          }
          return;
        }

        // 2. Filtro de Mês (Exibe mês ativo, ex: 'Out' ou 'Jan a Out')
        if (f.key === 'mes' || f.id === 'fMes') {
          const s = est[f.id];
          if (s && s instanceof Set && s.size > 0 && s.size < f.opcoes.length) {
            let textVal = '';
            if (s.size === 1) {
              const v = [...s][0];
              const opt = f.opcoes.find(o => String(o.v) === String(v));
              const raw = opt ? (opt.t || opt.v) : v;
              textVal = raw.includes('-') ? raw.split('-')[1].trim() : raw;
            } else {
              textVal = this.getResumo(f, est);
            }
            chips.push({
              filtro: f,
              label: 'Mês',
              val: textVal,
              podeRemover: true
            });
          }
          return;
        }

        // 3. Fornecedores sem OC
        if (f.key === 'is_fornecedor_sem_oc' || f.id === 'fFornSemOC') {
          const s = est[f.id];
          if (s && s instanceof Set && s.size > 0 && s.size < f.opcoes.length) {
            chips.push({
              filtro: f,
              label: 'Forn. sem OC',
              val: [...s].join(', '),
              podeRemover: true
            });
          }
          return;
        }

        // 4. Fornecedores Não Negociáveis
        if (f.key === 'is_fornecedor_nao_negociavel' || f.id === 'fFornNegociavel') {
          const s = est[f.id];
          if (s && s instanceof Set && s.size > 0 && s.size < f.opcoes.length) {
            const val = [...s].join(', ');
            chips.push({
              filtro: f,
              label: 'Negociável',
              val: val === 'NEGOCIAVEL' ? 'SIM' : val,
              podeRemover: true
            });
          }
          return;
        }

        // 5. Empresa (BB / BQ)
        if (f.key === 'empresa' || f.id === 'fEmpresa') {
          const s = est[f.id];
          if (s && s instanceof Set && s.size > 0 && s.size < f.opcoes.length) {
            chips.push({
              filtro: f,
              label: 'Empresa',
              val: [...s].join(', '),
              podeRemover: true
            });
          }
          return;
        }

        // 6. Demais filtros Multi-seleção
        if (f.tipo === 'multi') {
          const s = est[f.id];
          if (s && s instanceof Set && s.size > 0 && s.size < f.opcoes.length) {
            let textVal = '';
            if (s.size === 1) {
              const v = [...s][0];
              const opt = f.opcoes.find(o => String(o.v) === String(v));
              textVal = opt ? (opt.t || opt.v) : v;
            } else {
              textVal = `${s.size} sel.`;
            }
            chips.push({
              filtro: f,
              label: f.rotulo || f.key,
              val: textVal,
              podeRemover: true
            });
          }
          return;
        }

        // 7. Demais filtros Únicos
        if (f.tipo === 'unico') {
          const cur = est[f.id];
          const def = f.padrao ?? (f.opcoes[0]?.v || '');
          if (cur && cur !== def) {
            const opt = f.opcoes.find(o => o.v === cur);
            const textVal = opt ? (opt.t || opt.v) : cur;
            chips.push({
              filtro: f,
              label: f.rotulo || f.key,
              val: textVal,
              podeRemover: true
            });
          }
        }
      });

      return chips;
    }

    posicionarGavetaEmbutida(anchor) {
      if (!this.gavetaEl) return;
      try {
        if (window !== window.parent && window.frameElement && this.gavetaEl.ownerDocument === document) {
        this.gavetaOrigem = { parent: this.gavetaEl.parentNode, next: this.gavetaEl.nextSibling };
        window.parent.document.body.appendChild(this.gavetaEl);
        }
        const host = this.gavetaEl.ownerDocument.defaultView;
        this.gavetaAnchor = anchor || window.__filterPortalAnchor || this.abrirGavetaBtn;
        if (!this.gavetaAnchor.isConnected && this.gavetaOrigem) this.gavetaAnchor = host.document.querySelector('.header-filter-action[aria-haspopup="dialog"]') || this.gavetaAnchor;
        window.__filterPortalAnchor = null;
        this.gavetaEl.classList.add('fp-gaveta-popover');
        const rect = this.gavetaAnchor.getBoundingClientRect();
        const scale = host.dnaScale ? host.dnaScale() : 1;
        const margin = 8;
        const width = Math.min(400 * scale, host.innerWidth - margin * 2);
        const below = host.innerHeight - rect.bottom - margin * 2;
        const above = rect.top - margin * 2;
        const useAbove = below < 280 && above > below;
        const height = Math.max(0, Math.min(760 * scale, useAbove ? above : below));
        this.gavetaEl.style.left = Math.max(margin, Math.min(rect.left, host.innerWidth - width - margin)) / scale + 'px';
        this.gavetaEl.style.top = (useAbove ? rect.top - margin - height : rect.bottom + margin) / scale + 'px';
        this.gavetaEl.style.width = width / scale + 'px';
        this.gavetaEl.style.height = height / scale + 'px';
      } catch (_) {}
    }

    abrirGaveta(anchor) {
      this.posicionarGavetaEmbutida(anchor);
      if (this.gavetaEl.open) return;
      const hostDoc = this.gavetaEl.ownerDocument;
      this.fecharAoClicarFora = event => {
        if (!this.gavetaEl.contains(event.target) && !this.gavetaAnchor?.contains(event.target)) {
          this.rascunho = this.clonar(this.aplicado);
          this.gavetaEl.close();
          this.atualizarTudo();
        }
      };
      this.fecharComEscape = event => {
        if (event.key !== 'Escape') return;
        event.preventDefault();
        this.rascunho = this.clonar(this.aplicado);
        this.retornarFocoGaveta = true;
        this.gavetaEl.close();
        this.atualizarTudo();
      };
      this.reposicionarGaveta = () => this.posicionarGavetaEmbutida(this.gavetaAnchor);
      hostDoc.addEventListener('pointerdown', this.fecharAoClicarFora, true);
      hostDoc.addEventListener('keydown', this.fecharComEscape, true);
      this.gavetaFrameDocs = Array.from(hostDoc.querySelectorAll('iframe')).map(frame => {
        try { return frame.contentDocument; } catch (_) { return null; }
      }).filter(Boolean);
      this.gavetaFrameDocs.forEach(doc => {
        doc.addEventListener('pointerdown', this.fecharAoClicarFora, true);
        doc.addEventListener('keydown', this.fecharComEscape, true);
      });
      hostDoc.defaultView.addEventListener('resize', this.reposicionarGaveta);
      hostDoc.defaultView.addEventListener('scroll', this.reposicionarGaveta, true);
      this.gavetaEl.show();
    }

    abrirGavetaEFocar(filtroId) {
      if (this.gavetaEl) {
        this.rascunho = this.clonar(this.aplicado);
        this.atualizarTudo();
        try { this.abrirGaveta(); } catch (e) {}
        const sec = this.gavetaEl.querySelector(`[data-filtro="${filtroId}"]`);
        if (sec) {
          sec.open = true;
          sec.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      } else {
        this.setEstadoPainel('aberto');
        const sec = this.corpoLateral ? this.corpoLateral.querySelector(`[data-filtro="${filtroId}"]`) : null;
        if (sec) {
          sec.open = true;
          sec.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      }
    }

    atualizarChipsEResumo() {
      const T = getTexts();
      const chipsAtivos = this.getChipsAtivos();
      const n = chipsAtivos.length;

      if (this.abrirGavetaBtn) {
        this.abrirGavetaBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 5h16l-6 7v5l-4 2v-7z"/></svg><span>${T.filtros}</span>`;
        this.abrirGavetaBtn.setAttribute('aria-label', `${T.filtros}: ${n} ativos`);
      }
      if (this.trilhoContador) {
        this.trilhoContador.textContent = String(n);
        this.trilhoContador.hidden = (n === 0);
      }
      if (this.lateralContador) {
        this.lateralContador.textContent = String(n);
        this.lateralContador.hidden = (n === 0);
      }

      if (!this.chipsEl || !this.resumoEl) return;
      this.chipsEl.innerHTML = '';

      // Barra sempre visível quando houver contexto filtrado
      this.resumoEl.hidden = false;

      chipsAtivos.forEach(c => {
        const chip = document.createElement('span');
        chip.className = 'chip';
        chip.setAttribute('data-filtro', c.filtro.id);
        chip.title = `Clique para ajustar ${c.label}`;

        chip.innerHTML = `
          <span class="chip-label">${c.label}:</span>
          <strong class="chip-val">${c.val}</strong>
          ${c.podeRemover ? `<button type="button" class="chip-remove" aria-label="${T.remover(c.label)}" title="${T.remover(c.label)}">&times;</button>` : ''}
        `;

        if (c.podeRemover) {
          const btn = chip.querySelector('.chip-remove');
          if (btn) {
            btn.addEventListener('click', (ev) => {
              ev.stopPropagation();
              this.removerFiltro(c.filtro);
            });
          }
        }

        chip.addEventListener('click', () => {
          this.abrirGavetaEFocar(c.filtro.id);
        });

        this.chipsEl.append(chip);
      });

      if (this.limparTudoBtn) {
        const temRemovivel = chipsAtivos.some(c => c.podeRemover && c.filtro.id !== 'fAno');
        this.limparTudoBtn.hidden = !temRemovivel;
      }
    }

    removerFiltro(f) {
      if (f.key === 'mes' || f.id === 'fMes') {
        // Ao remover mês, seleciona todos os meses (Ano Fechado)
        this.aplicado[f.id] = new Set(f.opcoes.map(o => o.v));
      } else if (f.key === 'is_fornecedor_sem_oc' || f.id === 'fFornSemOC') {
        // Ao remover, inclui ambos (COM ATUAÇÃO + SEM OC)
        this.aplicado[f.id] = new Set(f.opcoes.map(o => o.v));
      } else if (f.key === 'is_fornecedor_nao_negociavel' || f.id === 'fFornNegociavel') {
        // Ao remover, inclui ambos (NEGOCIAVEL + NÃO NEGOCIAVEL)
        this.aplicado[f.id] = new Set(f.opcoes.map(o => o.v));
      } else if (f.key === 'ano' || f.id === 'fAno') {
        this.abrirGavetaEFocar(f.id);
        return;
      } else if (f.tipo === 'unico') {
        this.aplicado[f.id] = f.padrao ?? (f.opcoes[0]?.v || '');
      } else {
        this.aplicado[f.id] = new Set(f.opcoes.map(o => o.v));
      }
      this.rascunho = this.clonar(this.aplicado);
      this.aplicar();
    }

    atualizarTudo() {
      this.sincronizarSecoes();
      this.atualizarBotoesEAvisos();
      this.atualizarChipsEResumo();
    }

    aplicar() {
      this.aplicado = this.clonar(this.rascunho);
      this.syncWithGlobalFilters();
      this.atualizarTudo();

      try {
        const key = 'portal_compras_shared_filters';
        const state = JSON.parse(localStorage.getItem(key) || '{}');
        this.filtros.forEach(f => {
          const val = this.aplicado[f.id];
          state[f.key || f.id] = f.tipo === 'unico' ? [String(val || '')] :
            (!val || val.size === 0 || this.todosSelecionados(f, val) ? '__ALL__' : [...val]);
        });
        localStorage.setItem(key, JSON.stringify(state));
      } catch (err) { console.warn('Não foi possível compartilhar os filtros:', err); }

      if (this.gavetaEl && this.gavetaEl.open) {
        this.gavetaEl.close();
      }

      const payload = {};
      this.filtros.forEach(f => {
        const val = this.aplicado[f.id];
        if (f.tipo === 'unico') {
          payload[f.id] = val;
        } else {
          if (!val || !(val instanceof Set) || val.size === 0 || this.todosSelecionados(f, val)) {
            payload[f.id] = 'Todos';
          } else {
            payload[f.id] = [...val];
          }
        }
      });

      this.onApplyCallback(payload);
    }

    getValores() {
      const vals = {};
      this.filtros.forEach(f => {
        const val = this.aplicado[f.id];
        let res;
        if (f.tipo === 'unico') {
          res = (val !== undefined && val !== null) ? String(val) : '';
        } else if (val instanceof Set) {
          if (val.has('__NONE__')) {
            res = [];
          } else if (val.size === 0 || this.todosSelecionados(f, val)) {
            res = f.opcoes.map(o => o.v);
          } else {
            res = [...val];
          }
        } else if (Array.isArray(val)) {
          res = val;
        } else {
          res = f.opcoes.map(o => o.v);
        }
        vals[f.id] = res;
        if (f.key) vals[f.key] = res;
      });
      return vals;
    }

    limpar() {
      this.rascunho = this.getPadrao();
      this.aplicar();
    }

    bindEvents() {
      window.addEventListener('storage', event => {
        if (event.key !== 'portal_compras_shared_filters' || !event.newValue) return;
        try {
          const state = JSON.parse(event.newValue);
          const updated = this.clonar(this.aplicado);
          this.filtros.forEach(f => {
            const saved = state[f.key || f.id];
            if (saved === '__ALL__' && f.tipo !== 'unico') updated[f.id] = new Set();
            else if (Array.isArray(saved)) updated[f.id] = f.tipo === 'unico' ? String(saved[0] || '') : new Set(saved.map(String));
          });
          if (this.saoIguais(updated, this.aplicado)) return;
          this.aplicado = updated;
          this.rascunho = this.clonar(updated);
          this.syncWithGlobalFilters();
          this.atualizarTudo();
          this.onApplyCallback();
        } catch (err) { console.warn('Não foi possível sincronizar os filtros:', err); }
      });
      if (this.recolherBtn) {
        this.recolherBtn.addEventListener('click', (e) => {
          if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
          this.setEstadoPainel('recolhido');
          try { this.trilhoBtn?.focus(); } catch (err) {}
        });
      }
      if (this.trilhoBtn) {
        this.trilhoBtn.addEventListener('click', (e) => {
          if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
          this.setEstadoPainel('aberto');
          try { this.recolherBtn?.focus(); } catch (err) {}
        });
      }
      if (this.lateralEl) {
        this.lateralEl.addEventListener('click', (e) => {
          const layout = this.layoutEl || document.getElementById('appLayout') || document.querySelector('.layout');
          const estado = layout ? layout.getAttribute('data-filtros') : 'recolhido';
          if (estado === 'recolhido') {
            this.setEstadoPainel('aberto');
            try { this.recolherBtn?.focus(); } catch (err) {}
          }
        });
      }
      if (this.aplicarBtn) {
        this.aplicarBtn.addEventListener('click', () => this.aplicar());
      }
      if (this.limparBtn) {
        this.limparBtn.addEventListener('click', () => this.limpar());
      }
      if (this.abrirGavetaBtn && this.gavetaEl) {
        this.abrirGavetaBtn.addEventListener('click', () => {
          this.rascunho = this.clonar(this.aplicado);
          this.atualizarTudo();
          this.abrirGaveta();
        });
      }
      if (this.fecharGavetaBtn && this.gavetaEl) {
        this.fecharGavetaBtn.addEventListener('click', () => {
          this.rascunho = this.clonar(this.aplicado);
          this.retornarFocoGaveta = true;
          this.gavetaEl.close();
          this.atualizarTudo();
        });
      }
      if (this.gavetaAplicarBtn) {
        this.gavetaAplicarBtn.addEventListener('click', () => this.aplicar());
      }
      if (this.gavetaLimparBtn) {
        this.gavetaLimparBtn.addEventListener('click', () => this.limpar());
      }
      if (this.limparTudoBtn) {
        this.limparTudoBtn.addEventListener('click', () => this.limpar());
      }
      if (this.gavetaEl) {
        this.gavetaEl.addEventListener('close', () => {
          const hostDoc = this.gavetaEl.ownerDocument;
          hostDoc.removeEventListener('pointerdown', this.fecharAoClicarFora, true);
          hostDoc.removeEventListener('keydown', this.fecharComEscape, true);
          (this.gavetaFrameDocs || []).forEach(doc => {
            doc.removeEventListener('pointerdown', this.fecharAoClicarFora, true);
            doc.removeEventListener('keydown', this.fecharComEscape, true);
          });
          this.gavetaFrameDocs = null;
          hostDoc.defaultView.removeEventListener('resize', this.reposicionarGaveta);
          hostDoc.defaultView.removeEventListener('scroll', this.reposicionarGaveta, true);
          if (this.gavetaOrigem) {
            const { parent, next } = this.gavetaOrigem;
            parent.insertBefore(this.gavetaEl, next && next.parentNode === parent ? next : null);
            this.gavetaOrigem = null;
          }
          this.gavetaEl.classList.remove('fp-gaveta-popover');
          ['left', 'top', 'width', 'height'].forEach(prop => this.gavetaEl.style.removeProperty(prop));
          if (this.retornarFocoGaveta) (this.gavetaAnchor?.isConnected ? this.gavetaAnchor : hostDoc.querySelector('.header-filter-action[aria-haspopup="dialog"]'))?.focus();
          this.retornarFocoGaveta = false;
        });
        this.gavetaEl.addEventListener('cancel', () => {
          this.rascunho = this.clonar(this.aplicado);
          this.atualizarTudo();
        });
      }
      window.addEventListener('resize', () => {
        this.atualizarChipsEResumo();
      });
      window.addEventListener('bimbo:langChange', () => {
        this.initTextos();
        this.atualizarTudo();
      });
    }
  }

  window.DNAFiltersPanel = DNAFiltersPanel;
})();
