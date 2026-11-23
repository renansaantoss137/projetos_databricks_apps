/**
 * DNA DE VENDAS | Grupo Bimbo Brasil
 * Painel de Filtros Retrátil à Direita (F1 a F11 / identidade-da.md / filtros-referencia.html)
 */

(function () {
  'use strict';

  const STORAGE_KEY = 'dna_filtros_estado';
  const TXT = {
    pt: {
      todos: 'Todos',
      selecionados: n => `${n} selecionados`,
      pesquisar: 'Pesquisar',
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
      pesquisar: 'Search',
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
      pesquisar: 'Buscar',
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

      this.filtros = config.filtros || [];
      this.onApplyCallback = config.onApply || (() => {});
      this.seq = 0;

      this.init();
    }

    init() {
      // Normaliza opções
      this.filtros.forEach(f => {
        f.opcoes = (f.opcoes || []).map(o => typeof o === 'string' ? { v: o, t: o } : o);
      });

      this.aplicado = this.getPadrao();
      this.rascunho = this.clonar(this.aplicado);

      this.initTextos();
      this.initEstadoPainel();
      this.montarInterface();
      this.bindEvents();
      this.atualizarTudo();
    }

    updateDefinitions(newFiltros) {
      newFiltros.forEach(nf => {
        const existing = this.filtros.find(f => f.id === nf.id);
        if (existing) {
          existing.opcoes = (nf.opcoes || []).map(o => typeof o === 'string' ? { v: o, t: o } : o);
          if (nf.padrao !== undefined) existing.padrao = nf.padrao;
        } else {
          nf.opcoes = (nf.opcoes || []).map(o => typeof o === 'string' ? { v: o, t: o } : o);
          this.filtros.push(nf);
        }
      });
      this.aplicado = this.getPadrao();
      this.rascunho = this.clonar(this.aplicado);
      this.montarInterface();
      this.atualizarTudo();
    }

    getPadrao() {
      return Object.fromEntries(
        this.filtros.map(f => [
          f.id,
          f.tipo === 'unico' ? (f.padrao ?? (f.opcoes[0]?.v || '')) : new Set()
        ])
      );
    }

    clonar(e) {
      return Object.fromEntries(
        Object.entries(e).map(([k, v]) => [k, v instanceof Set ? new Set(v) : v])
      );
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
      if (f.tipo === 'multi' && this.rascunho[f.id].size === f.opcoes.length) {
        this.rascunho[f.id] = new Set();
      }
    }

    isAtivo(f, est = this.rascunho) {
      if (f.tipo === 'unico') {
        const def = f.padrao ?? (f.opcoes[0]?.v || '');
        return est[f.id] !== def;
      }
      return (est[f.id] && est[f.id].size > 0);
    }

    getResumo(f, est = this.rascunho) {
      const T = getTexts();
      if (f.tipo === 'unico') {
        return f.opcoes.find(o => o.v === est[f.id])?.t ?? '';
      }
      const s = est[f.id];
      if (!s || s.size === 0) return T.todos;
      if (s.size === 1) return f.opcoes.find(o => s.has(o.v))?.t || [...s][0];
      return T.selecionados(s.size);
    }

    isMarcado(f, v) {
      if (f.tipo === 'unico') return this.rascunho[f.id] === v;
      const s = this.rascunho[f.id];
      return (!s || s.size === 0 || s.has(v));
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
      if (this.limparTudoBtn) this.limparTudoBtn.textContent = T.limparTudo;
      if (this.recolherBtn) this.recolherBtn.setAttribute('aria-label', T.recolher);
      if (this.trilhoBtn) this.trilhoBtn.setAttribute('aria-label', T.expandir);
    }

    initEstadoPainel() {
      // Critério F3: salvo em localStorage por usuário; abre aberto a partir de 1440px e recolhido entre 1200 e 1439px
      let estado = null;
      try { estado = localStorage.getItem(STORAGE_KEY); } catch (e) {}

      if (!estado) {
        const w = window.innerWidth;
        estado = (w >= 1440) ? 'aberto' : 'recolhido';
      }
      this.setEstadoPainel(estado, false);
    }

    setEstadoPainel(estado, salvar = true) {
      if (!this.layoutEl) return;
      this.layoutEl.setAttribute('data-filtros', estado);
      const aberto = (estado === 'aberto');
      if (this.recolherBtn) this.recolherBtn.setAttribute('aria-expanded', String(aberto));
      if (this.trilhoBtn) this.trilhoBtn.setAttribute('aria-expanded', String(aberto));

      if (salvar) {
        try { localStorage.setItem(STORAGE_KEY, estado); } catch (e) {}
      }

      // Notifica redimensionamento de gráficos
      window.dispatchEvent(new Event('resize'));
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
        busca.setAttribute('aria-label', `${T.pesquisar}: ${f.rotulo}`);
        wrap.append(busca);
      }

      const ul = document.createElement('ul');
      ul.className = 'fp-lista';
      wrap.append(ul);

      const linha = (texto, checked, onToggle, comSomente, tipo, extraClasse) => {
        const li = document.createElement('li');
        li.className = 'fp-opcao' + (extraClasse ? ' ' + extraClasse : '');
        const id = `fp-${f.id}-${grupo}-${this.seq++}`;
        li.innerHTML = `<label for="${id}"><input id="${id}" type="${tipo}" name="fp-${f.id}-${grupo}"><span></span></label>`;
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
        const termo = (busca?.value || '').trim().toLowerCase();
        const visiveis = f.opcoes.filter(o => o.t.toLowerCase().includes(termo));
        ul.innerHTML = '';

        if (f.tipo === 'multi' && visiveis.length) {
          const s = this.rascunho[f.id] || new Set();
          if (termo) {
            const exato = (s.size === visiveis.length && visiveis.every(o => s.has(o.v)));
            linha(
              T.soResultados(visiveis.length),
              exato,
              () => {
                this.rascunho[f.id] = new Set(visiveis.map(o => o.v));
                this.normalizar(f);
                aoMudar();
                render();
              },
              null,
              'checkbox',
              'fp-todos'
            );
          } else {
            linha(
              T.selTodos,
              s.size === 0 ? true : 'misto',
              () => {
                this.rascunho[f.id] = new Set();
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
              const s = (this.rascunho[f.id].size === 0)
                ? new Set(f.opcoes.map(x => x.v))
                : this.rascunho[f.id];
              ev.target.checked ? s.add(o.v) : s.delete(o.v);
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

      wrap.addEventListener('keydown', ev => {
        if (!['ArrowDown', 'ArrowUp'].includes(ev.key)) return;
        const alvos = [busca, ...ul.querySelectorAll('input, button')].filter(Boolean);
        const i = alvos.indexOf(document.activeElement);
        if (i < 0) return;
        ev.preventDefault();
        const next = Math.max(0, Math.min(alvos.length - 1, i + (ev.key === 'ArrowDown' ? 1 : -1)));
        alvos[next]?.focus();
      });

      return { el: wrap, render, limparBusca: () => { if (busca) busca.value = ''; } };
    }

    montarSecoes(container, grupo) {
      if (!container) return [];
      container.innerHTML = '';
      const seta = '<svg class="fp-seta" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';

      return this.filtros.map(f => {
        const d = document.createElement('details');
        d.className = 'fp-secao';
        d.dataset.filtro = f.id;
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
      const atualizar = list => list.forEach(s => {
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

    atualizarChipsEResumo() {
      const T = getTexts();
      const n = this.totalAtivos(this.aplicado);

      if (this.abrirGavetaBtn) {
        this.abrirGavetaBtn.textContent = `${T.filtros}${n ? ` (${n})` : ''}`;
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

      if (this.chipsEl) {
        this.chipsEl.innerHTML = '';
        this.filtros.forEach(f => {
          if (!this.isAtivo(f, this.aplicado)) return;
          const chip = document.createElement('span');
          chip.className = 'chip';
          chip.innerHTML = `
            <span>${f.rotulo}: <strong>${this.getResumo(f, this.aplicado)}</strong></span>
            <button type="button" aria-label="${T.remover(f.rotulo)}">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
            </button>
          `;
          chip.querySelector('button').addEventListener('click', () => {
            if (f.tipo === 'unico') {
              this.aplicado[f.id] = f.padrao ?? (f.opcoes[0]?.v || '');
            } else {
              this.aplicado[f.id] = new Set();
            }
            this.rascunho = this.clonar(this.aplicado);
            this.aplicar();
          });
          this.chipsEl.append(chip);
        });
      }

      const temChips = (n > 0);
      if (this.limparTudoBtn) this.limparTudoBtn.hidden = !temChips;
      if (this.resumoEl) {
        const isDesktop = window.innerWidth >= 1200;
        this.resumoEl.hidden = isDesktop && !temChips;
      }
    }

    atualizarTudo() {
      this.sincronizarSecoes();
      this.atualizarBotoesEAvisos();
      this.atualizarChipsEResumo();
    }

    aplicar() {
      this.aplicado = this.clonar(this.rascunho);
      this.atualizarTudo();

      // Monta contrato com o backend
      const payload = {};
      this.filtros.forEach(f => {
        const val = this.aplicado[f.id];
        if (f.tipo === 'unico') {
          payload[f.id] = val;
        } else {
          if (!val || val.size === 0 || val.size === f.opcoes.length) {
            payload[f.id] = 'Todos';
          } else {
            payload[f.id] = [...val];
          }
        }
      });

      if (this.gavetaEl && this.gavetaEl.open) {
        this.gavetaEl.close();
      }

      this.onApplyCallback(payload);
    }

    limpar() {
      this.rascunho = this.getPadrao();
      this.aplicar();
    }

    bindEvents() {
      // Recolher e expandir painel lateral
      if (this.recolherBtn) {
        this.recolherBtn.addEventListener('click', () => {
          this.setEstadoPainel('recolhido');
          this.trilhoBtn?.focus();
        });
      }
      if (this.trilhoBtn) {
        this.trilhoBtn.addEventListener('click', () => {
          this.setEstadoPainel('aberto');
          this.recolherBtn?.focus();
        });
      }

      // Aplicar e Limpar do painel lateral
      if (this.aplicarBtn) {
        this.aplicarBtn.addEventListener('click', () => this.aplicar());
      }
      if (this.limparBtn) {
        this.limparBtn.addEventListener('click', () => this.limpar());
      }

      // Gaveta (tablet e celular)
      if (this.abrirGavetaBtn && this.gavetaEl) {
        this.abrirGavetaBtn.addEventListener('click', () => {
          this.rascunho = this.clonar(this.aplicado);
          this.atualizarTudo();
          this.gavetaEl.showModal();
        });
      }
      if (this.fecharGavetaBtn && this.gavetaEl) {
        this.fecharGavetaBtn.addEventListener('click', () => {
          this.rascunho = this.clonar(this.aplicado);
          this.gavetaEl.close();
          this.atualizarTudo();
          this.abrirGavetaBtn?.focus();
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

      // Esc na gaveta descarta rascunho
      if (this.gavetaEl) {
        this.gavetaEl.addEventListener('cancel', () => {
          this.rascunho = this.clonar(this.aplicado);
          this.atualizarTudo();
        });
      }

      // Redimensionamento de janela
      window.addEventListener('resize', () => {
        this.atualizarChipsEResumo();
      });

      // Mudança de idioma
      window.addEventListener('bimbo:langChange', () => {
        this.initTextos();
        this.atualizarTudo();
      });
    }
  }

  window.DNAFiltersPanel = DNAFiltersPanel;
})();
