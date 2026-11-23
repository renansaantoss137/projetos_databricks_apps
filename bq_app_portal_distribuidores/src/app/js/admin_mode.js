/* ── Modo Administrador (faixa âmbar, seletor multi-distribuidor padrão .custom-select e simulação) ──
 * Carregado e executado somente quando /api/me confirma admin=true.
 * Na simulação ("Ver como distribuidor"), /api/me devolve admin=false e este
 * módulo não roda: o portal fica idêntico à visão do distribuidor.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'admin_dist_ids';
  var filterSyncTimer = null;
  var state = {
    role: null,
    email: null,
    list: [],
    selected: [], // [{id, cnpj, nome}, ...] aplicados atualmente
    current: null // preenchido somente quando selected.length === 1
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function normDigits(s) { return String(s || '').replace(/\D/g, ''); }

  function readSelectedIdsFromUrl() {
    var u = new URLSearchParams(window.location.search);
    var rawId = (u.get('dist_id') || '').trim();
    if (rawId) {
      var ids = rawId.split(',').map(function (x) { return x.trim(); }).filter(function (x) { return /^\d+$/.test(x) && Number(x) > 0; });
      if (ids.length) return Array.from(new Set(ids));
    }
    var d = normDigits(u.get('dist'));
    if (d.length === 14) return ['cnpj:' + d];
    try {
      var saved = (sessionStorage.getItem(STORAGE_KEY) || '').trim();
      if (saved) {
        var sIds = saved.split(',').map(function (x) { return x.trim(); }).filter(function (x) { return /^\d+$/.test(x) && Number(x) > 0; });
        if (sIds.length) return Array.from(new Set(sIds));
      }
    } catch (e) {}
    return [];
  }

  function writeSelectedToUrl(selectedItems) {
    var url = new URL(window.location.href);
    url.searchParams.delete('dist');
    var ids = (selectedItems || []).map(function (d) { return String(d.id || ''); }).filter(Boolean);
    if (ids.length && ids.length < state.list.length) {
      var val = ids.join(',');
      url.searchParams.set('dist_id', val);
      try { sessionStorage.setItem(STORAGE_KEY, val); } catch (e) {}
    } else {
      url.searchParams.delete('dist_id');
      try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) {}
    }
    window.history.replaceState({}, '', url.toString());
  }

  /* ── Faixa de controle admin (oculta na tela, usada pelo menu de usuário para simulação) ── */
  function renderTopBar() {
    var bar = document.getElementById('admin-mode-bar');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'admin-mode-bar';
      bar.setAttribute('role', 'region');
      bar.setAttribute('aria-label', 'Modo administrador');
      document.body.insertBefore(bar, document.body.firstChild);
    }
    var isViewer = state.role === 'VISUALIZADOR';
    var badgeCls = state.role === 'MASTER' ? 'amb-badge amb-badge-master' : 'amb-badge amb-badge-admin';
    var count = state.selected.length;
    var namesList = state.selected.map(function (d) { return d.nome; }).join(', ');

    var viewTxt;
    if (count === 0 || count === state.list.length) {
      viewTxt = 'Visão: <b>Todos os distribuidores</b>';
    } else if (count === 1) {
      viewTxt = 'Visão: <b>' + esc(state.selected[0].nome) + '</b>';
    } else {
      viewTxt = 'Visão: <b title="' + esc(namesList) + '">' + count + ' distribuidores selecionados</b>';
    }

    var simBtn = (count === 1)
      ? '<button type="button" class="amb-btn" id="amb-btn-sim" title="Recarregar o portal exatamente como este distribuidor o vê">Ver como distribuidor</button>'
      : '';
    var allBtn = (count > 0 && count < state.list.length)
      ? '<button type="button" class="amb-btn" id="amb-btn-all" title="Voltar para Todos os distribuidores">Todos</button>'
      : '';
    var govLink = isViewer ? '' : '<a class="amb-link" href="/gestao-acessos">Gestão de Acessos</a>';

    bar.innerHTML =
      '<div class="amb-left">' +
        '<span class="' + badgeCls + '">' + esc(state.role) + '</span>' +
        '<span class="amb-title">' + (isViewer ? 'MODO VISUALIZADOR' : 'MODO ADMINISTRADOR') + '</span>' +
        '<span class="amb-sep">·</span>' +
        '<span class="amb-view">' + viewTxt + '</span>' +
      '</div>' +
      '<div class="amb-right">' +
        allBtn +
        simBtn +
        '<button type="button" class="amb-kbd" id="amb-btn-picker" title="Trocar distribuidor (Ctrl+K)">Trocar <kbd>Ctrl K</kbd></button>' +
        govLink +
      '</div>';

    var bAll = document.getElementById('amb-btn-all');
    if (bAll) bAll.onclick = function () { applySelection([]); };
    var bSim = document.getElementById('amb-btn-sim');
    if (bSim) bSim.onclick = confirmSimulation;
    var bPick = document.getElementById('amb-btn-picker');
    if (bPick) bPick.onclick = function (e) { e.stopPropagation(); openPicker(); };
  }

  /* ── Inicializa e sincroniza o filtro padrão .custom-select (#qf-dist) ── */
  function setupDistributorSelect() {
    var ug = document.getElementById('user-greeting');
    var qfDist = document.getElementById('qf-dist');
    if (!qfDist) return;

    if (ug) ug.style.display = 'none';
    qfDist.hidden = false;

    if (typeof window.makeCustomSelect === 'function' && !qfDist._initialized) {
      window.makeCustomSelect('qf-dist', 'Todos');
    }

    var opts = state.list.map(function (d) {
      return { value: String(d.id), label: d.nome };
    });
    var selIds = state.selected.map(function (d) { return String(d.id); });
    if (typeof qfDist.populate === 'function') {
      qfDist.populate(opts, selIds, 'Nenhum distribuidor');
    }

    if (!qfDist._adminBound) {
      qfDist._adminBound = true;
      qfDist.addEventListener('change', function (e) {
        if (e.target !== qfDist) return;
        var rawIds = typeof qfDist.getSelectedValues === 'function' ? qfDist.getSelectedValues() : [];
        var picked = state.list.filter(function (d) { return rawIds.indexOf(String(d.id)) !== -1; });
        applySelection(picked, true);
      });
    }
  }

  function openPicker() {
    var qfDist = document.getElementById('qf-dist');
    if (!qfDist) return;
    var trig = qfDist.querySelector('.select-trigger');
    if (trig && !qfDist.classList.contains('active')) {
      trig.click();
    } else {
      var inp = document.getElementById('qf-dist-input');
      if (inp) inp.focus();
    }
  }

  function applySelection(items, fromSelectEvent) {
    var arr = Array.isArray(items) ? items.filter(function (d) { return d && d.id; }) : [];
    state.selected = arr;
    state.current = arr.length === 1 ? arr[0] : null;
    writeSelectedToUrl(arr);
    renderTopBar();

    if (!fromSelectEvent) {
      var qfDist = document.getElementById('qf-dist');
      if (qfDist && typeof qfDist.setSelected === 'function') {
        qfDist.setSelected(arr.map(function (d) { return String(d.id); }));
      }
    }

    clearTimeout(filterSyncTimer);
    filterSyncTimer = setTimeout(function () {
      if (typeof window.loadFilters === 'function') window.loadFilters();
      else if (typeof window.loadDynamicFilters === 'function') window.loadDynamicFilters();
      if (typeof window.triggerDashboardRefresh === 'function') window.triggerDashboardRefresh(50);
    }, 180);
  }

  /* ── Modal de confirmação da simulação ── */
  function confirmSimulation() {
    if (!state.current) return;
    var old = document.getElementById('amb-modal');
    if (old) old.remove();
    var d = state.current;
    var wrap = document.createElement('div');
    wrap.id = 'amb-modal';
    wrap.className = 'amb-modal-overlay';
    wrap.innerHTML =
      '<div class="amb-modal" role="dialog" aria-modal="true" aria-labelledby="amb-m-title">' +
        '<h3 id="amb-m-title">Ver como distribuidor</h3>' +
        '<div class="amb-modal-body">' +
          '<p>O portal será recarregado exatamente como <b>' + esc(d.nome) + '</b> o vê:</p>' +
          '<p>• Sem a barra de administrador e sem o botão Guia<br>' +
             '• Dados restritos a este distribuidor<br>' +
             '• A simulação vale apenas nesta sessão e não altera nenhum cadastro</p>' +
        '</div>' +
        '<div class="amb-modal-actions">' +
          '<button type="button" class="amb-modal-cancel" id="amb-m-cancel">Cancelar</button>' +
          '<button type="button" class="amb-modal-ok" id="amb-m-ok">Entrar na simulação</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(wrap);
    document.getElementById('amb-m-cancel').onclick = function () { wrap.remove(); };
    wrap.addEventListener('click', function (e) { if (e.target === wrap) wrap.remove(); });
    document.getElementById('amb-m-ok').onclick = startSimulation;
  }

  function startSimulation() {
    var btn = document.getElementById('amb-m-ok');
    if (btn) { btn.disabled = true; btn.textContent = 'Ativando…'; }
    fetch('/api/admin/simulacao', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: state.current.id, cnpj: state.current.cnpj })
    }).then(function (r) {
      if (!r.ok) throw new Error('Falha ao iniciar simulação');
      window.location.href = '/dashboard.html';
    }).catch(function (err) {
      alert(err.message);
      if (btn) { btn.disabled = false; btn.textContent = 'Entrar na simulação'; }
    });
  }

  /* ── Inicialização ── */
  async function init(meData) {
    if (!meData || !meData.admin) return;
    window.__ADMIN_MODE__ = true;
    state.role = meData.role || 'ADMIN';
    state.email = meData.email;

    renderTopBar();
    setupDistributorSelect();

    try {
      var r = await fetch('/api/admin/distribuidores/grupos', { credentials: 'include' });
      if (r.ok) {
        var j = await r.json();
        state.list = (j.items || []).filter(function (d) { return d && d.id; });
      }
    } catch (e) { console.warn('[admin_mode] catálogo indisponível:', e); }

    var hadUrlDist = new URLSearchParams(window.location.search).has('dist_id') || new URLSearchParams(window.location.search).has('dist');
    var wanted = readSelectedIdsFromUrl();
    if (wanted.length) {
      var found = [];
      wanted.forEach(function (w) {
        var match = null;
        if (w.indexOf('cnpj:') === 0) {
          var cj = w.slice(5);
          match = state.list.find(function (d) { return d.cnpj === cj || (d.cnpjs || []).indexOf(cj) !== -1; });
        } else {
          match = state.list.find(function (d) { return String(d.id) === String(w); });
        }
        if (match && !found.some(function (x) { return String(x.id) === String(match.id); })) {
          found.push(match);
        }
      });
      state.selected = found;
      state.current = found.length === 1 ? found[0] : null;
      writeSelectedToUrl(found);
      if (!hadUrlDist && found.length) {
        applySelection(found, true);
      }
    }

    renderTopBar();
    setupDistributorSelect();

    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        openPicker();
      }
    });
  }

  window.AdminMode = {
    init: init,
    openPicker: openPicker,
    clear: function () { applySelection([]); },
    selectById: function (id, nome) {
      var match = state.list.find(function (d) { return String(d.id) === String(id); });
      if (match) {
        applySelection([match], false);
        return true;
      }
      if (id && /^\d+$/.test(String(id).trim())) {
        applySelection([{ id: String(id).trim(), nome: nome || ('DT ' + id), cnpj: '', cnpjs: [] }], false);
        return true;
      }
      return false;
    }
  };
})();
