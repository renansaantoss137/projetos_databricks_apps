/* ==========================================================================
   Portal Distribuidores Bimbo QSR — Novos Módulos Integrados
   Implementa US 116253 (Produtos), US 116251 (Campanhas),
   US 116257 (Suporte) e US 116252 (Academia Trade)
   ========================================================================== */
(function () {
  'use strict';

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  // ─── ESTADO GLOBAL DOS MÓDULOS ─────────────────────────────────────────────
  var modState = {
    produtos: [],
    produtosFiltro: { q: '', familia: '', tag: '' },
    campanhas: [],
    chamados: [],
    treinamentos: null,
    tradeSubTab: 'campanhas' // 'campanhas' | 'treinamentos'
  };

  // ─── 1. MÓDULO PRODUTOS & FICHAS TÉCNICAS (US 116253) ──────────────────────
  async function carregarProdutos() {
    var grid = $('#produtos-grid');
    if (!grid) return;
    try {
      var qp = new URLSearchParams();
      if (modState.produtosFiltro.q) qp.set('q', modState.produtosFiltro.q);
      if (modState.produtosFiltro.familia) qp.set('familia', modState.produtosFiltro.familia);
      if (modState.produtosFiltro.tag) qp.set('tag', modState.produtosFiltro.tag);

      var res = await fetch('/api/produtos?' + qp.toString());
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var data = await res.json();
      modState.produtos = data.produtos || [];
      renderProdutos();
    } catch (e) {
      grid.innerHTML = '<div class="v2-empty"><p>Falha ao carregar catálogo de produtos.</p></div>';
    }
  }

  function renderProdutos() {
    var grid = $('#produtos-grid');
    var countEl = $('#produtos-count');
    if (!grid) return;

    if (countEl) countEl.textContent = modState.produtos.length + ' produtos encontrados';

    if (!modState.produtos.length) {
      grid.innerHTML = '<div class="v2-empty" style="grid-column: 1/-1;"><p>Nenhum produto encontrado para os filtros selecionados.</p></div>';
      return;
    }

    grid.innerHTML = modState.produtos.map(function (p) {
      var tagHtml = p.tag ? '<span class="prod-badge ' + (p.tag_tipo || 'giro') + '">' + p.tag + '</span>' : '';
      return '<article class="card prod-card">' +
        '<div class="prod-card-top">' +
          '<div class="prod-thumb"><img src="' + p.imagem + '" alt="' + p.nome + '" loading="lazy" /></div>' +
          '<div class="prod-header-info">' +
            tagHtml +
            '<span class="prod-sku">SKU ' + p.sku + '</span>' +
            '<h3 class="prod-title">' + p.nome + '</h3>' +
            '<span class="prod-fam">' + p.familia + ' · ' + p.marca + '</span>' +
          '</div>' +
        '</div>' +
        '<p class="prod-desc">' + p.destaque_comercial + '</p>' +
        '<div class="prod-specs-mini">' +
          '<div><span>Unidade:</span> <strong>' + p.especificacoes.peso_unitario + '</strong></div>' +
          '<div><span>Caixa:</span> <strong>' + p.especificacoes.paes_caixa + ' pães</strong></div>' +
          '<div><span>Pallet:</span> <strong>' + p.especificacoes.caixas_pallet + ' cx (' + p.especificacoes.duzias_pallet + ' DZ)</strong></div>' +
          '<div><span>Validade:</span> <strong>' + p.especificacoes.shelf_life_ambiente + '</strong></div>' +
        '</div>' +
        '<div class="prod-actions">' +
          '<button type="button" class="btn btn-secondary btn-sm" onclick="window.abrirModalFicha(\'' + p.sku + '\')">Ficha Técnica &amp; ANVISA</button>' +
          '<a class="btn btn-primary btn-sm" href="' + p.arquivos.ficha_tecnica_pdf + '" download>Baixar Ficha</a>' +
        '</div>' +
      '</article>';
    }).join('');
  }

  window.abrirModalFicha = function (sku) {
    var p = modState.produtos.find(function (x) { return x.sku === sku; });
    if (!p) return;
    var modal = $('#modal-ficha-produto');
    var body = $('#modal-ficha-body');
    var title = $('#modal-ficha-title');
    if (!modal || !body) return;

    if (title) title.textContent = p.nome + ' (SKU ' + p.sku + ')';

    var argsHtml = (p.lancamento && p.lancamento.argumentos_venda)
      ? p.lancamento.argumentos_venda.map(function (a) { return '<li>' + a + '</li>'; }).join('')
      : '';

    body.innerHTML = '<div class="ficha-content-grid">' +
      '<div class="ficha-col">' +
        '<h4>Especificações Técnicas de Fábrica</h4>' +
        '<table class="tech-table">' +
          '<tr><td>Peso Unitário</td><td><strong>' + p.especificacoes.peso_unitario + '</strong></td></tr>' +
          '<tr><td>Pães por Pacote</td><td>' + p.especificacoes.paes_pacote + '</td></tr>' +
          '<tr><td>Pacotes por Caixa</td><td>' + p.especificacoes.pacotes_caixa + '</td></tr>' +
          '<tr><td>Pães por Caixa</td><td><strong>' + p.especificacoes.paes_caixa + ' pães</strong></td></tr>' +
          '<tr><td>Lastro / Caixas por Pallet</td><td>' + p.especificacoes.caixas_pallet + ' caixas</td></tr>' +
          '<tr><td>Volume em Dúzias</td><td>' + p.especificacoes.duzias_pallet + ' DZ / pallet</td></tr>' +
          '<tr><td>Dimensões Médias</td><td>' + p.especificacoes.dimensoes + '</td></tr>' +
          '<tr><td>Armazenamento Congelado</td><td>' + p.especificacoes.validade_congelado + '</td></tr>' +
          '<tr><td>Shelf Life Ambiente</td><td><strong>' + p.especificacoes.shelf_life_ambiente + '</strong></td></tr>' +
        '</table>' +
      '</div>' +
      '<div class="ficha-col">' +
        '<h4>Regulatório &amp; Comercial</h4>' +
        '<div class="ficha-box">' +
          '<strong>Registro ANVISA:</strong> ' + p.especificacoes.anvisa + '<br>' +
          '<strong>Alérgenos:</strong> ' + p.especificacoes.alergenicos +
        '</div>' +
        (argsHtml ? ('<h4 style="margin-top:1rem;">Argumentos de Venda para Hamburguerias</h4><ul class="ficha-args">' + argsHtml + '</ul>') : '') +
        '<div class="ficha-downloads">' +
          '<a class="btn btn-secondary btn-sm" href="' + p.arquivos.packshot_hd + '" download>Download Packshot HD</a>' +
          '<a class="btn btn-secondary btn-sm" href="' + p.arquivos.ficha_tecnica_pdf + '" download>Download Ficha PDF</a>' +
          '<a class="btn btn-secondary btn-sm" href="' + p.arquivos.kit_pdv + '" download>Kit Merchandising PDV</a>' +
        '</div>' +
      '</div>' +
    '</div>';

    modal.style.display = 'flex';
  };

  window.fecharModalFicha = function () {
    var modal = $('#modal-ficha-produto');
    if (modal) modal.style.display = 'none';
  };

  // ─── 2. MÓDULO TRADE & CAMPANHAS (US 116251 & 116252) ──────────────────────
  async function carregarCampanhas() {
    var cont = $('#campanhas-container');
    if (!cont) return;
    try {
      var res = await fetch('/api/campanhas');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var data = await res.json();
      modState.campanhas = data.campanhas || [];
      renderCampanhas(data);
    } catch (e) {
      cont.innerHTML = '<div class="v2-empty"><p>Falha ao carregar campanhas ativas.</p></div>';
    }
  }

  function renderCampanhas(data) {
    var cont = $('#campanhas-container');
    if (!cont) return;

    var campsHtml = (data.campanhas || []).map(function (c) {
      var rankRows = (c.ranking || []).map(function (r) {
        var elegPill = r.elegivel
          ? '<span class="status-pill status-good">Elegível à premiação</span>'
          : '<span class="status-pill status-warn">Abaixo da meta</span>';
        var pctCls = r.ating_pct >= 100 ? 'text-good' : (r.ating_pct >= 90 ? 'text-warn' : 'text-bad');
        var valTxt = c.tipo_meta === 'volume_dz'
          ? (r.realizado_dz.toLocaleString('pt-BR') + ' / ' + r.meta_dz.toLocaleString('pt-BR') + ' DZ')
          : (r.realizado_novos + ' / ' + r.meta_novos + ' clientes');

        return '<tr>' +
          '<td><strong>#' + r.posicao + '</strong></td>' +
          '<td><strong>' + r.nome + '</strong></td>' +
          '<td>' + valTxt + '</td>' +
          '<td><strong class="' + pctCls + '">' + r.ating_pct.toFixed(1).replace('.', ',') + '%</strong></td>' +
          '<td>' + elegPill + '</td>' +
        '</tr>';
      }).join('');

      return '<article class="card camp-card">' +
        '<div class="camp-card-head">' +
          '<div>' +
            '<span class="camp-tag">CAMPANHA VIGENTE · ' + c.dias_restantes + ' DIAS RESTANTES</span>' +
            '<h3 class="camp-title">' + c.nome + '</h3>' +
            '<p class="camp-desc">' + c.descricao + '</p>' +
          '</div>' +
          '<div class="camp-premio-box">' +
            '<span class="camp-premio-k">Premiação em Disputa</span>' +
            '<span class="camp-premio-v">' + c.premiacao + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="camp-table-wrap">' +
          '<table class="tech-table">' +
            '<thead>' +
              '<tr><th>Posição</th><th>Distribuidor</th><th>Realizado / Meta</th><th>% Atingimento</th><th>Status</th></tr>' +
            '</thead>' +
            '<tbody>' + rankRows + '</tbody>' +
          '</table>' +
        '</div>' +
        '<div class="camp-foot">' +
          '<span>Apuração automática diária via Databricks Delta Lake · Sem intervenção manual</span>' +
          '<span class="badge-neutral">Última atualização: ' + (data.ultima_apuracao || 'Hoje') + '</span>' +
        '</div>' +
      '</article>';
    }).join('');

    cont.innerHTML = '<div class="camp-audit-banner">' +
      '<div class="cab-left">' +
        '<strong>Apuração Automatizada de Campanhas Bimbo QSR</strong>' +
        '<p>Os resultados são consolidados em tempo real a partir das notas de Sell-out. Ganho operacional auditado: <strong>~4,5 horas economizadas por trimestre</strong> em relação ao processo manual.</p>' +
      '</div>' +
    '</div>' + campsHtml;
  }

  async function carregarTreinamentos() {
    var cont = $('#treinamentos-container');
    if (!cont) return;
    try {
      var res = await fetch('/api/treinamentos');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var data = await res.json();
      modState.treinamentos = data;
      renderTreinamentos(data);
    } catch (e) {
      cont.innerHTML = '<div class="v2-empty"><p>Falha ao carregar trilhas de capacitação.</p></div>';
    }
  }

  function renderTreinamentos(data) {
    var cont = $('#treinamentos-container');
    if (!cont) return;

    var trilhasHtml = (data.trilhas || []).map(function (t) {
      var stCls = t.progresso_usuario_pct === 100 ? 'status-good' : (t.progresso_usuario_pct > 0 ? 'status-warn' : 'status-neutral');
      var stTxt = t.progresso_usuario_pct === 100 ? 'Certificado Concluído' : (t.progresso_usuario_pct > 0 ? (t.progresso_usuario_pct + '% Concluído') : 'Não iniciado');

      var modulosHtml = (t.modulos || []).map(function (m) {
        var ico = m.tipo === 'video' ? '▶ Vídeo' : (m.tipo === 'pdf' ? '📄 Guia PDF' : '📝 Quiz');
        var btnTxt = m.concluido ? '✓ Concluído' : 'Iniciar';
        var btnCls = m.concluido ? 'btn-secondary' : 'btn-primary';
        return '<div class="trilha-mod-row">' +
          '<div class="tm-info">' +
            '<span class="tm-type">' + ico + ' · ' + m.duracao + '</span>' +
            '<strong>' + m.titulo + '</strong>' +
          '</div>' +
          '<button type="button" class="btn ' + btnCls + ' btn-sm" onclick="window.concluirModulo(\'' + m.id + '\')">' + btnTxt + '</button>' +
        '</div>';
      }).join('');

      return '<article class="card trilha-card">' +
        '<div class="trilha-head">' +
          '<div>' +
            '<span class="status-pill ' + stCls + '">' + stTxt + '</span>' +
            '<h3 class="trilha-title">' + t.titulo + '</h3>' +
            '<p class="trilha-desc">' + t.descricao + '</p>' +
          '</div>' +
          '<div class="trilha-prog-ring">' +
            '<span class="tpr-pct">' + t.progresso_usuario_pct + '%</span>' +
            '<span class="tpr-lbl">Progresso</span>' +
          '</div>' +
        '</div>' +
        '<div class="trilha-mod-list">' + modulosHtml + '</div>' +
      '</article>';
    }).join('');

    cont.innerHTML = trilhasHtml;
  }

  window.concluirModulo = async function (modId) {
    try {
      await fetch('/api/treinamentos/concluir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modulo_id: modId })
      });
      carregarTreinamentos();
    } catch (_) {}
  };

  window.switchTradeSubTab = function (sub) {
    modState.tradeSubTab = sub;
    var bCamp = $('#btn-trade-campanhas');
    var bTrein = $('#btn-trade-treinamentos');
    var cCamp = $('#campanhas-container');
    var cTrein = $('#treinamentos-container');

    if (bCamp && bTrein) {
      bCamp.classList.toggle('active', sub === 'campanhas');
      bTrein.classList.toggle('active', sub === 'treinamentos');
    }
    if (cCamp && cTrein) {
      cCamp.style.display = sub === 'campanhas' ? 'block' : 'none';
      cTrein.style.display = sub === 'treinamentos' ? 'block' : 'none';
    }
    if (sub === 'campanhas') carregarCampanhas();
    else carregarTreinamentos();
  };

  // ─── 3. MÓDULO SUPORTE & CHAMADOS (US 116257) ──────────────────────────────
  async function carregarChamados() {
    var cont = $('#chamados-list');
    if (!cont) return;
    try {
      var res = await fetch('/api/suporte');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var data = await res.json();
      modState.chamados = data.chamados || [];
      renderChamados(data);
    } catch (e) {
      cont.innerHTML = '<div class="v2-empty"><p>Falha ao carregar chamados de suporte.</p></div>';
    }
  }

  function renderChamados(data) {
    var cont = $('#chamados-list');
    if (!cont) return;

    if (!data.chamados || !data.chamados.length) {
      cont.innerHTML = '<div class="v2-empty"><p>Nenhum chamado aberto no momento.</p></div>';
      return;
    }

    cont.innerHTML = data.chamados.map(function (c) {
      var stCls = c.status === 'resolvido' ? 'status-good' : (c.status === 'em_analise' ? 'status-warn' : 'status-neutral');
      var stTxt = c.status === 'resolvido' ? 'Resolvido' : (c.status === 'em_analise' ? 'Em Análise' : 'Aberto');

      var msgsHtml = (c.mensagens || []).map(function (m) {
        var isBq = m.tipo === 'backoffice';
        return '<div class="msg-bubble ' + (isBq ? 'msg-bq' : 'msg-dist') + '">' +
          '<div class="msg-meta"><strong>' + m.autor + '</strong> · ' + m.data + '</div>' +
          '<p class="msg-body">' + m.texto + '</p>' +
        '</div>';
      }).join('');

      return '<article class="card chamado-card">' +
        '<div class="chamado-head">' +
          '<div>' +
            '<span class="chamado-prot">' + c.protocolo + ' · ' + c.categoria + '</span>' +
            '<h3 class="chamado-assunto">' + c.assunto + '</h3>' +
            (c.pedido_sap ? ('<span class="chamado-sap">Pedido SAP: <strong>#' + c.pedido_sap + '</strong></span>') : '') +
          '</div>' +
          '<div style="text-align:right;">' +
            '<span class="status-pill ' + stCls + '">' + stTxt + '</span>' +
            '<div class="chamado-sla">Limite SLA: ' + c.sla_limite + '</div>' +
          '</div>' +
        '</div>' +
        '<div class="chamado-thread">' + msgsHtml + '</div>' +
      '</article>';
    }).join('');
  }

  window.abrirModalNovoChamado = function () {
    var modal = $('#modal-novo-chamado');
    if (modal) modal.style.display = 'flex';
  };

  window.fecharModalNovoChamado = function () {
    var modal = $('#modal-novo-chamado');
    if (modal) modal.style.display = 'none';
  };

  window.enviarNovoChamado = async function () {
    var cat = $('#chamado-in-categoria') ? $('#chamado-in-categoria').value : '';
    var ass = $('#chamado-in-assunto') ? $('#chamado-in-assunto').value : '';
    var ped = $('#chamado-in-sap') ? $('#chamado-in-sap').value : '';
    var msg = $('#chamado-in-msg') ? $('#chamado-in-msg').value : '';

    if (!cat || !ass || !msg) {
      alert('Por favor, preencha categoria, assunto e descrição da solicitação.');
      return;
    }

    try {
      var res = await fetch('/api/suporte/novo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ categoria: cat, assunto: ass, pedido_sap: ped, mensagem: msg })
      });
      if (res.ok) {
        window.fecharModalNovoChamado();
        if ($('#chamado-in-assunto')) $('#chamado-in-assunto').value = '';
        if ($('#chamado-in-msg')) $('#chamado-in-msg').value = '';
        if ($('#chamado-in-sap')) $('#chamado-in-sap').value = '';
        carregarChamados();
      } else {
        alert('Falha ao enviar chamado.');
      }
    } catch (_) {
      alert('Erro de conexão ao enviar chamado.');
    }
  };

  // ─── 4. INTEGRAÇÃO WISE NA ABA FORECAST (US 116256) ────────────────────────
  window.abrirModalWise = function () {
    window.open('https://dashboard.wisesales.com.br/home', '_blank');
  };

  window.fecharModalWise = function () {
    var modal = $('#modal-wise-integration');
    if (modal) modal.style.display = 'none';
  };

  // ─── INICIALIZAÇÃO QUANDO ABA ATIVADA ──────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    // Escuta ativação de abas para carregar dados sob demanda
    document.addEventListener('v2-tabchange', function (e) {
      var tab = e.detail && e.detail.tab;
      if (tab === 'produtos') carregarProdutos();
      else if (tab === 'trade') window.switchTradeSubTab(modState.tradeSubTab);
      else if (tab === 'help') carregarChamados();
    });

    // Filtros de produtos
    var inpBusca = $('#produtos-search-input');
    if (inpBusca) {
      inpBusca.addEventListener('input', function () {
        modState.produtosFiltro.q = inpBusca.value.trim();
        carregarProdutos();
      });
    }

    $$('[data-prod-fam]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        $$('[data-prod-fam]').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        modState.produtosFiltro.familia = btn.getAttribute('data-prod-fam') || '';
        carregarProdutos();
      });
    });
  });

  // Exporta para escopo global
  window.V2ModulosNovos = {
    carregarProdutos: carregarProdutos,
    carregarCampanhas: carregarCampanhas,
    carregarTreinamentos: carregarTreinamentos,
    carregarChamados: carregarChamados
  };
})();

