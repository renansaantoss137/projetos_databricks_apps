/* ── Gestão de Acessos – Portal Distribuidores ──
   VISUALIZADOR não entra nesta tela: só vê os dados de todos os distribuidores.
   MASTER: tudo. ADMIN: concede/revoga/reativa ADMIN e acessos de distribuidores; não mexe em MASTER
   (não concede MASTER, não promove/rebaixa, não revoga MASTER).
   As regras (domínio @grupobimbo.com, último MASTER, auto-rebaixamento) são validadas no servidor;
   aqui elas apenas orientam a interface. Toda mudança é gravada em tbl_log_admin_audit (source=APP).
*/
(function () {
  'use strict';

  var EMAIL_RE = /^[a-z0-9._%+\-]+@grupobimbo\.com$/;
  var ACTION_LABELS = {
    GRANT: 'Acesso concedido', REACTIVATE: 'Acesso reativado', PROMOTE: 'Promovido', DEMOTE: 'Rebaixado',
    REVOKE: 'Acesso revogado', SEED: 'Carga inicial', RLS_UPDATE: 'Atualização de RLS',
    SIMULATE_START: 'Simulação iniciada', SIMULATE_END: 'Simulação encerrada',
    DIST_GRANT: 'Distribuidor: acesso concedido', DIST_REACTIVATE: 'Distribuidor: acesso reativado',
    DIST_CHANGE: 'Distribuidor: vínculo alterado', DIST_REVOKE: 'Distribuidor: acesso revogado',
    PORTAL_DIST_ENABLE: 'Portal: distribuidor liberado', PORTAL_DIST_DISABLE: 'Portal: distribuidor desativado',
    PORTAL_DIST_NOTES: 'Portal: observação atualizada'
  };
  var ANY_EMAIL_RE = /^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$/;
  var state = { me: null, canEdit: false, canManageMasters: false, items: [], audit: [], auditLoaded: false,
                dists: [], distsLoaded: false, catalog: [],
                portalDists: [], portalCandidates: [], portalDistsLoaded: false, pdSelected: [],
                uso: null, usoLoaded: false };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fmtMs(ms) {
    var n = parseInt(ms, 10);
    if (!n) return '<span class="ga-muted">—</span>';
    return esc(new Date(n).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }));
  }
  function dash(v) { return v ? esc(v) : '<span class="ga-muted">—</span>'; }
  function roleBadge(role) {
    if (!role) return '<span class="ga-muted">—</span>';
    return '<span class="amb-badge amb-badge-' + esc(String(role).toLowerCase()) + '">' + esc(role) + '</span>';
  }

  /* ── Paginação padrão das tabelas (15 linhas por página) ── */
  var PAGE_SIZE = 15;
  var tablePages = {};
  var tableFilterKeys = {};

  function buildPageNumbers(current, total) {
    if (total <= 7) {
      var all = [];
      for (var i = 1; i <= total; i++) all.push(i);
      return all;
    }
    var out = [1];
    var start = Math.max(2, current - 1);
    var end = Math.min(total - 1, current + 1);
    if (current <= 3) end = 4;
    if (current >= total - 2) start = total - 3;
    if (start > 2) out.push('…');
    for (var p = start; p <= end; p++) out.push(p);
    if (end < total - 1) out.push('…');
    out.push(total);
    return out;
  }

  function renderPagedTable(tbodyId, rows, mapRowFn, emptyHtml, filterKey, onRerender) {
    var tbody = $(tbodyId);
    if (!tbody) return;
    var wrap = tbody.closest('.ga-table-wrap');
    var pagerId = tbodyId + '-pager';
    var pager = $(pagerId);
    if (!pager && wrap && wrap.parentNode) {
      pager = document.createElement('div');
      pager.id = pagerId;
      pager.className = 'ga-pager';
      pager.hidden = true;
      wrap.parentNode.insertBefore(pager, wrap.nextSibling);
      pager.addEventListener('click', function (e) {
        var btn = e.target.closest('button[data-page]');
        if (!btn || btn.disabled) return;
        var nextP = parseInt(btn.getAttribute('data-page'), 10);
        if (nextP > 0 && nextP !== tablePages[tbodyId]) {
          tablePages[tbodyId] = nextP;
          if (pager._rerender) pager._rerender();
        }
      });
    }
    if (pager && onRerender) pager._rerender = onRerender;

    var fk = String(filterKey || '');
    if (tableFilterKeys[tbodyId] !== fk) {
      tableFilterKeys[tbodyId] = fk;
      tablePages[tbodyId] = 1;
    }

    var list = rows || [];
    if (!list.length) {
      tbody.innerHTML = emptyHtml;
      if (pager) pager.hidden = true;
      return;
    }

    var total = list.length;
    var totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    var page = Math.min(Math.max(1, tablePages[tbodyId] || 1), totalPages);
    tablePages[tbodyId] = page;
    var start = (page - 1) * PAGE_SIZE;
    var end = Math.min(start + PAGE_SIZE, total);
    tbody.innerHTML = list.slice(start, end).map(mapRowFn).join('');

    if (!pager) return;
    if (total <= PAGE_SIZE) {
      pager.hidden = true;
      return;
    }
    pager.hidden = false;
    var nums = buildPageNumbers(page, totalPages);
    var navHtml = '<button type="button" class="ga-page-btn" data-page="' + (page - 1) + '"' + (page <= 1 ? ' disabled' : '') + ' aria-label="Página anterior">‹ Anterior</button>';
    nums.forEach(function (n) {
      if (n === '…') {
        navHtml += '<span class="ga-page-dots">…</span>';
      } else {
        navHtml += '<button type="button" class="ga-page-btn' + (n === page ? ' active' : '') + '" data-page="' + n + '">' + n + '</button>';
      }
    });
    navHtml += '<button type="button" class="ga-page-btn" data-page="' + (page + 1) + '"' + (page >= totalPages ? ' disabled' : '') + ' aria-label="Próxima página">Próxima ›</button>';

    pager.innerHTML =
      '<span class="ga-pager-info">Mostrando <b>' + (start + 1) + '–' + end + '</b> de <b>' + total + '</b></span>' +
      '<div class="ga-pager-nav">' + navHtml + '</div>';
  }

  var toastTimer = null;
  function toast(msg, ok) {
    var t = $('ga-toast');
    t.innerHTML = esc(msg);
    t.className = 'ga-toast ' + (ok ? 'ok' : 'err');
    t.style.display = 'block';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.style.display = 'none'; }, ok ? 3500 : 6000);
  }

  function showLoadingToast(msg) {
    var t = $('ga-toast');
    t.innerHTML = '<span class="amb-spinner"></span> <span>' + esc(msg || 'Processando...') + '</span>';
    t.className = 'ga-toast loading';
    t.style.display = 'flex';
    clearTimeout(toastTimer);
  }

  function api(method, url, body) {
    var opts = { method: method, credentials: 'include', headers: {} };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.error || ('Erro ' + r.status));
        return j;
      });
    });
  }

  /* ── Modal de confirmação ── */
  function confirmDialog(opts) {
    var ov = document.createElement('div');
    ov.className = 'amb-modal-overlay';
    ov.innerHTML =
      '<div class="amb-modal" role="dialog" aria-modal="true" aria-labelledby="ga-modal-title">' +
        '<h3 id="ga-modal-title">' + esc(opts.title) + '</h3>' +
        '<div class="amb-modal-body">' + opts.body + '</div>' +
        '<div class="amb-modal-status" id="ga-modal-status">' +
          '<span class="amb-spinner"></span>' +
          '<span>Gravando alteração no Databricks... Aguarde um momento.</span>' +
        '</div>' +
        '<div class="amb-modal-actions">' +
          '<button type="button" class="amb-modal-cancel">Cancelar</button>' +
          '<button type="button" class="amb-modal-ok' + (opts.danger ? ' danger' : '') + '">' + esc(opts.ok) + '</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(ov);
    var isSubmitting = false;
    function close() { if (isSubmitting) return; ov.remove(); document.removeEventListener('keydown', onKey, true); }
    function onKey(e) { if (e.key === 'Escape' && !isSubmitting) { e.stopPropagation(); close(); } }
    document.addEventListener('keydown', onKey, true);
    var cancelBtn = ov.querySelector('.amb-modal-cancel');
    cancelBtn.addEventListener('click', close);
    ov.addEventListener('mousedown', function (e) { if (e.target === ov && !isSubmitting) close(); });
    var okBtn = ov.querySelector('.amb-modal-ok');
    var statusEl = ov.querySelector('#ga-modal-status');
    var originalOkText = okBtn.textContent;

    okBtn.addEventListener('click', function () {
      if (isSubmitting) return;
      if (opts.background) {
        var task;
        try { task = opts.onOk(ov); } catch (err) { toast(err.message || 'Falha na operação', false); return; }
        close();
        Promise.resolve(task).catch(function (e) {
          toast(e.message || 'Falha na operação', false);
        });
        return;
      }
      isSubmitting = true;
      okBtn.disabled = true;
      cancelBtn.disabled = true;
      okBtn.innerHTML = '<span class="amb-spinner"></span> Processando...';
      if (statusEl) statusEl.style.display = 'flex';
      showLoadingToast('Gravando alteração no Databricks...');

      Promise.resolve(opts.onOk(ov))
        .then(function () {
          isSubmitting = false;
          close();
        })
        .catch(function (e) {
          isSubmitting = false;
          okBtn.disabled = false;
          cancelBtn.disabled = false;
          okBtn.textContent = originalOkText;
          if (statusEl) statusEl.style.display = 'none';
          toast(e.message || 'Falha na operação', false);
        });
    });
    var first = ov.querySelector('input, select');
    (first || okBtn).focus();
  }

  /* ── Administradores ── */
  function activeMasters() {
    return state.items.filter(function (r) { return r.is_active && r.role === 'MASTER'; }).length;
  }

  function actionsHtml(r) {
    if (!state.canEdit) return '<span class="ga-muted">—</span>';
    var isSelf = state.me && r.user_email === state.me.email;
    if (isSelf) return '<span class="ga-muted" title="Não é permitido alterar o próprio acesso">—</span>';
    var e = esc(r.user_email);
    if (!r.is_active) {
      return '<div class="ga-actions"><button type="button" class="ga-btn ga-btn-outline ga-btn-sm" data-act="reactivate" data-email="' + e + '">Reativar</button></div>';
    }
    if (!state.canManageMasters) {
      if (r.role === 'MASTER') return '<span class="ga-muted" title="Somente um MASTER pode alterar o acesso de outro MASTER">Somente MASTER</span>';
      return '<div class="ga-actions"><button type="button" class="ga-btn ga-btn-danger ga-btn-sm" data-act="revoke" data-email="' + e + '">Revogar</button></div>';
    }
    var lastMaster = r.role === 'MASTER' && activeMasters() <= 1;
    var lockTitle = lastMaster ? ' title="Não é permitido remover ou rebaixar o último MASTER" disabled' : '';
    var roleBtn = r.role !== 'MASTER'
      ? '<button type="button" class="ga-btn ga-btn-outline ga-btn-sm" data-act="promote" data-email="' + e + '">Promover a ' + (r.role === 'VISUALIZADOR' ? 'ADMIN' : 'MASTER') + '</button>'
      : '<button type="button" class="ga-btn ga-btn-outline ga-btn-sm" data-act="demote" data-email="' + e + '"' + lockTitle + '>Rebaixar a ADMIN</button>';
    return '<div class="ga-actions">' + roleBtn +
      '<button type="button" class="ga-btn ga-btn-danger ga-btn-sm" data-act="revoke" data-email="' + e + '"' + lockTitle + '>Revogar</button></div>';
  }

  function renderAdmins() {
    var rows = state.items.filter(function (r) { return r.is_active; });
    $('ga-admins-title').textContent = 'Administradores (' + rows.length + ')';
    renderPagedTable('ga-admins-body', rows, function (r) {
      var isSelf = state.me && r.user_email === state.me.email;
      return '<tr>' +
        '<td><b>' + esc(r.user_email) + '</b>' + (isSelf ? '<span class="ga-you">você</span>' : '') + '</td>' +
        '<td>' + roleBadge(r.role) + '</td>' +
        '<td>' + dash(r.notes) + '</td>' +
        '<td>' + actionsHtml(r) + '</td>' +
      '</tr>';
    }, '<tr><td colspan="4" class="ga-empty">Nenhum registro</td></tr>', 'active', renderAdmins);
  }

  function loadAdmins() {
    return api('GET', '/api/admin/acessos').then(function (j) {
      state.me = j.me;
      state.canEdit = !!j.can_edit;
      state.canManageMasters = !!j.can_manage_masters;
      state.items = j.items || [];
      var mOpt = $('ga-role-master-opt');
      if (mOpt) { mOpt.disabled = !state.canManageMasters; mOpt.hidden = !state.canManageMasters; }
      var badge = $('ga-role-badge');
      badge.textContent = j.me.role;
      badge.className = 'amb-badge amb-badge-' + String(j.me.role).toLowerCase();
      $('ga-add-form').style.display = state.canEdit ? 'grid' : 'none';
      $('ga-add-hint').style.display = state.canEdit ? 'block' : 'none';
      $('ga-readonly').style.display = (state.canManageMasters || state.isUsoPage) ? 'none' : 'block';
      renderAdmins();
    }).catch(function (e) {
      $('ga-admins-body').innerHTML = '<tr><td colspan="4" class="ga-empty">' + esc(e.message) + '</td></tr>';
    });
  }

  function afterChange(j, okMsg) {
    if (j && j.audit_error) toast(okMsg + ' (atenção: falha ao gravar o histórico)', false);
    else toast(okMsg, true);
    state.auditLoaded = false;
    return loadAdmins();
  }

  function findItem(email) {
    return state.items.filter(function (r) { return r.user_email === email; })[0];
  }

  function onAction(act, email) {
    var r = findItem(email);
    if (!r) return;
    var e = '<b>' + esc(email) + '</b>';
    if (act === 'promote' || act === 'demote') {
      var newRole = act === 'promote' && r.role === 'ADMIN' ? 'MASTER' : 'ADMIN';
      confirmDialog({
        title: (act === 'promote' ? 'Promover a ' : 'Rebaixar a ') + newRole,
        body: '<p>Alterar o papel de ' + e + ' de <b>' + esc(r.role) + '</b> para <b>' + newRole + '</b>?</p>' +
          (newRole === 'MASTER' ? '<p>MASTER pode conceder, alterar e revogar acessos de outros administradores.</p>'
                                : '<p>Como ADMIN, o usuário vê todos os distribuidores e pode conceder acessos ADMIN e de distribuidores (não altera MASTER).</p>'),
        ok: act === 'promote' ? 'Promover' : 'Rebaixar',
        danger: act === 'demote',
        onOk: function () {
          return api('PATCH', '/api/admin/acessos/' + encodeURIComponent(email), { role: newRole })
            .then(function (j) { return afterChange(j, 'Papel atualizado para ' + newRole); });
        }
      });
    } else if (act === 'revoke') {
      confirmDialog({
        title: 'Revogar acesso',
        body: '<p>Revogar o acesso de administrador de ' + e + ' (' + esc(r.role) + ')?</p>' +
          '<p>O usuário deixa de ver todos os distribuidores imediatamente (em até 1 minuto). O registro fica no histórico e pode ser reativado.</p>' +
          '<label for="ga-motivo">Motivo (opcional)</label><input type="text" id="ga-motivo" maxlength="500">',
        ok: 'Revogar',
        danger: true,
        onOk: function (ov) {
          var motivo = ov.querySelector('#ga-motivo').value.trim();
          return api('DELETE', '/api/admin/acessos/' + encodeURIComponent(email), { motivo: motivo })
            .then(function (j) { return afterChange(j, 'Acesso de ' + email + ' revogado'); });
        }
      });
    } else if (act === 'reactivate') {
      var prev = r.role === 'VISUALIZADOR' ? 'VISUALIZADOR' : (r.role === 'MASTER' && state.canManageMasters) ? 'MASTER' : 'ADMIN';
      confirmDialog({
        title: 'Reativar acesso',
        body: '<p>Reativar o acesso de administrador de ' + e + '?</p>' +
          '<label for="ga-react-role">Papel</label><select id="ga-react-role">' +
            '<option value="VISUALIZADOR"' + (prev === 'VISUALIZADOR' ? ' selected' : '') + '>VISUALIZADOR</option>' +
            '<option value="ADMIN"' + (prev === 'ADMIN' ? ' selected' : '') + '>ADMIN</option>' +
            (state.canManageMasters ? '<option value="MASTER"' + (prev === 'MASTER' ? ' selected' : '') + '>MASTER</option>' : '') + '</select>' +
          '<label for="ga-react-notes">Observação (opcional)</label><input type="text" id="ga-react-notes" maxlength="500">',
        ok: 'Reativar',
        onOk: function (ov) {
          var role = ov.querySelector('#ga-react-role').value;
          var notes = ov.querySelector('#ga-react-notes').value.trim();
          return api('POST', '/api/admin/acessos', { email: email, role: role, notes: notes })
            .then(function (j) { return afterChange(j, 'Acesso de ' + email + ' reativado como ' + role); });
        }
      });
    }
  }

  function onAddSubmit(ev) {
    ev.preventDefault();
    var email = $('ga-email').value.trim().toLowerCase();
    var role = $('ga-role').value;
    var notes = $('ga-notes').value.trim();
    if (!EMAIL_RE.test(email)) { toast('Informe um e-mail válido @grupobimbo.com', false); $('ga-email').focus(); return; }
    if (role === 'MASTER' && !state.canManageMasters) { toast('Somente um MASTER pode conceder acesso MASTER', false); return; }
    var existing = findItem(email);
    if (existing && existing.is_active) { toast(email + ' já possui acesso ativo como ' + existing.role, false); return; }
    confirmDialog({
      title: existing ? 'Reativar acesso' : 'Conceder acesso',
      body: '<p>' + (existing ? 'Reativar' : 'Conceder') + ' acesso <b>' + esc(role) + '</b> para <b>' + esc(email) + '</b>?</p>' +
        (role === 'MASTER' ? '<p>MASTER vê todos os distribuidores e gerencia todos os acessos.</p>'
         : role === 'VISUALIZADOR' ? '<p>VISUALIZADOR vê os dados de todos os distribuidores, sem acesso à Gestão de Acessos.</p>'
                           : '<p>ADMIN vê todos os distribuidores e pode conceder acessos ADMIN e de distribuidores (não altera MASTER).</p>'),
      ok: existing ? 'Reativar' : 'Conceder',
      onOk: function () {
        return api('POST', '/api/admin/acessos', { email: email, role: role, notes: notes }).then(function (j) {
          $('ga-email').value = ''; $('ga-notes').value = ''; $('ga-role').value = 'ADMIN';
          return afterChange(j, 'Acesso ' + role + ' concedido para ' + email);
        });
      }
    });
  }

  /* ── Autocomplete de e-mail (usuários Databricks) ──
     Leve: só busca a partir de 3 caracteres, espera 300 ms sem digitar, cancela a busca anterior
     e reaproveita resultados já buscados (cache local + cache de 10 min no servidor). */
  var userCache = {};
  function attachUserSuggest(input, opts) {
    opts = opts || {};
    var wrap = input.parentNode;
    wrap.classList.add('ga-suggest-wrap');
    var box = document.createElement('div');
    box.className = 'ga-suggest';
    box.setAttribute('role', 'listbox');
    wrap.appendChild(box);
    input.setAttribute('autocomplete', 'off');
    var timer = null, ctrl = null, items = [], idx = -1, lastTerm = '';

    function hide() { box.style.display = 'none'; idx = -1; }
    function render(list, term, note) {
      items = list; idx = -1;
      if (!list.length) {
        box.innerHTML = '<div class="ga-suggest-note">' + esc(note || 'Nenhum usuário encontrado — você pode digitar o e-mail completo') + '</div>';
      } else {
        box.innerHTML = list.map(function (u, i) {
          return '<div class="ga-suggest-item" role="option" data-i="' + i + '">' +
            '<b>' + esc(u.email) + '</b>' + (u.nome ? '<span>' + esc(u.nome) + '</span>' : '') + '</div>';
        }).join('');
      }
      box.style.display = 'block';
    }
    function pick(i) {
      var u = items[i];
      if (!u) return;
      input.value = u.email;
      hide();
      if (opts.onPick) opts.onPick(u);
    }
    function highlight() {
      Array.prototype.forEach.call(box.querySelectorAll('.ga-suggest-item'), function (el, i) {
        el.classList.toggle('active', i === idx);
        if (i === idx) el.scrollIntoView({ block: 'nearest' });
      });
    }
    function apply(list, term) {
      if (opts.filter) list = list.filter(opts.filter);
      render(list, term);
    }
    function search() {
      var term = input.value.trim().toLowerCase();
      if (term.length < 3 || !/^[a-z0-9._@\-]+$/.test(term)) { hide(); return; }
      if (term === lastTerm && box.style.display === 'block') return;
      lastTerm = term;
      if (userCache[term]) { apply(userCache[term], term); return; }
      if (ctrl) ctrl.abort();
      ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
      box.innerHTML = '<div class="ga-suggest-note">Buscando…</div>';
      box.style.display = 'block';
      fetch('/api/admin/usuarios?q=' + encodeURIComponent(term), { credentials: 'include', signal: ctrl ? ctrl.signal : undefined })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (input.value.trim().toLowerCase() !== term) return;   // resposta antiga
          if (j.unavailable) { render([], term, 'Busca de usuários indisponível — digite o e-mail completo'); return; }
          userCache[term] = j.items || [];
          apply(userCache[term], term);
        })
        .catch(function (e) { if (e && e.name !== 'AbortError') hide(); });
    }

    input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(search, 300); });
    input.addEventListener('keydown', function (e) {
      if (box.style.display !== 'block' || !items.length) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); highlight(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); idx = Math.max(idx - 1, 0); highlight(); }
      else if (e.key === 'Enter' && idx >= 0) { e.preventDefault(); pick(idx); }
      else if (e.key === 'Escape') { hide(); }
    });
    input.addEventListener('blur', function () { setTimeout(hide, 150); });
    box.addEventListener('mousedown', function (e) {
      var el = e.target.closest('.ga-suggest-item');
      if (el) { e.preventDefault(); pick(parseInt(el.getAttribute('data-i'), 10)); }
    });
  }

  /* ── Distribuidores (tbl_dim_distributor_user_mapping) ──
     Cada linha da tabela é um vínculo (e-mail, CNPJ); um e-mail pode somar vários distribuidores. */
  function fmtCnpj(c) {
    c = String(c || '').replace(/\D/g, '');
    return c.length === 14 ? c.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5') : c;
  }
  function distLabel(d) { return (d.nome || '(sem nome)') + (d.id ? ' (ID ' + d.id + ')' : '') + ' — ' + (d.cnpjs || [d.cnpj]).map(fmtCnpj).join(' / '); }
  function fmtDate(s) {
    if (!s) return '<span class="ga-muted">—</span>';
    var p = String(s).slice(0, 10).split('-');
    return p.length === 3 ? esc(p[2] + '/' + p[1] + '/' + p[0]) : esc(s);
  }
  // Aceita o rótulo do datalist ("NOME — 00.000.000/0000-00") ou só o CNPJ digitado.
  function resolveDist(value) {
    var v = String(value || '').trim();
    if (!v) return null;
    var exact = state.catalog.filter(function (d) { return distLabel(d) === v; })[0];
    if (exact) return exact;
    var digits = v.replace(/\D/g, '');
    if (digits.length === 14) {
      var matches = state.catalog.filter(function (d) { return (d.cnpjs || [d.cnpj]).indexOf(digits) !== -1; });
      return matches.length === 1 ? matches[0] : null;
    }
    var byId = state.catalog.filter(function (d) { return d.id && String(d.id) === v; });
    if (byId.length === 1) return byId[0];
    var byName = state.catalog.filter(function (d) { return (d.nome || '').toLowerCase() === v.toLowerCase(); });
    return byName.length === 1 ? byName[0] : null;
  }

  function loadCatalog() {
    if (state.catalog.length) return Promise.resolve();
    return api('GET', '/api/admin/distribuidores/grupos').then(function (j) {
      state.catalog = (j.items || []).map(function (d) {
        d.cnpjs = (d.cnpjs || [d.cnpj]).filter(function (c) { return c && !/^0+$/.test(c); });
        d.cnpj = d.cnpjs[0] || ''; 
        return d;
      }).filter(function (d) { return d.id || d.cnpjs.length; });
      var owners = {};
      state.catalog.forEach(function (d) { d.cnpjs.forEach(function (c) { (owners[c] || (owners[c] = [])).push(d); }); });
      state.catalog.forEach(function (d) { d.ambiguous = d.cnpjs.filter(function (c) { return owners[c].length > 1; }); });
      $('ga-dist-options').innerHTML = state.catalog.map(function (d) {
        return '<option value="' + esc(distLabel(d)) + '"></option>';
      }).join('');
    });
  }

  function activeLinksOf(email) {
    return state.dists.filter(function (r) { return r.user_email === email && r.is_active; });
  }

  function distActionsHtml(r) {
    var key = ' data-email="' + esc(r.user_email) + '" data-cnpj="' + esc(r.cnpj) + '"';
    if (!r.is_active) {
      return '<div class="ga-actions"><button type="button" class="ga-btn ga-btn-outline ga-btn-sm" data-dact="reactivate"' + key + '>Reativar</button></div>';
    }
    return '<div class="ga-actions">' +
      '<button type="button" class="ga-btn ga-btn-outline ga-btn-sm" data-dact="change"' + key + '>Trocar</button>' +
      '<button type="button" class="ga-btn ga-btn-danger ga-btn-sm" data-dact="revoke"' + key + '>Revogar</button></div>';
  }

  /* Revogação em massa: vínculos por ID marcados na tabela; a seleção sobrevive aos filtros */
  var revokeSel = {};
  function selKey(r) { return r.user_email + '|' + r.id; }
  function selectedLinks() { return state.dists.filter(function (r) { return revokeSel[selKey(r)]; }); }
  function isSelectable(r) { return r.is_active && !r.legacy && r.id; }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }

  function syncRevokeBar() {
    var sel = selectedLinks();
    var users = new Set(sel.map(function (r) { return r.user_email; })).size;
    $('ga-revoke-bar').hidden = !sel.length;
    $('ga-revoke-count').textContent = plural(sel.length, 'vínculo selecionado', 'vínculos selecionados') + ' · ' + plural(users, 'usuário', 'usuários');
    $('ga-revoke-submit').textContent = 'Revogar ' + plural(sel.length, 'acesso', 'acessos');
    var boxes = [].slice.call($('ga-dist-body').querySelectorAll('input[data-sel]'));
    var on = boxes.filter(function (b) { return b.checked; }).length;
    var all = $('ga-dist-sel-all');
    all.disabled = !boxes.length;
    all.checked = boxes.length > 0 && on === boxes.length;
    all.indeterminate = on > 0 && on < boxes.length;
  }
  function onRevokeToggle(e) {
    var b = e.target;
    if (!b.matches('input[data-sel]')) return;
    if (b.checked) revokeSel[b.getAttribute('data-sel')] = true;
    else delete revokeSel[b.getAttribute('data-sel')];
    b.closest('tr').classList.toggle('is-selected', b.checked);
    syncRevokeBar();
  }
  function onRevokeAll(e) {
    [].forEach.call($('ga-dist-body').querySelectorAll('input[data-sel]'), function (b) {
      b.checked = e.target.checked;
      if (b.checked) revokeSel[b.getAttribute('data-sel')] = true;
      else delete revokeSel[b.getAttribute('data-sel')];
      b.closest('tr').classList.toggle('is-selected', b.checked);
    });
    syncRevokeBar();
  }
  function onRevokeClear() { revokeSel = {}; renderDists(); }
  function onRevokeSubmit() {
    var sel = selectedLinks();
    if (!sel.length) return;
    var byEmail = {};
    sel.forEach(function (r) { (byEmail[r.user_email] || (byEmail[r.user_email] = [])).push(r); });
    var emails = Object.keys(byEmail).sort();
    // Quem fica sem nenhum vínculo ativo deixa de ver os dados do portal
    var lost = emails.filter(function (e) { return activeLinksOf(e).length === byEmail[e].length; });
    confirmDialog({
      title: 'Revogar ' + plural(sel.length, 'acesso', 'acessos'),
      body: '<ul class="ga-revoke-list">' + emails.map(function (e) {
        return '<li><b>' + esc(e) + '</b><span>' + esc(byEmail[e].map(function (r) { return r.nome || 'ID ' + r.id; }).join(', ')) + '</span></li>';
      }).join('') + '</ul>' +
        (lost.length ? '<p class="ga-revoke-warn">' + (lost.length === 1 ? '1 usuário perde' : lost.length + ' usuários perdem') + ' todo o acesso ao portal: ' + esc(lost.join(', ')) + '.</p>' : '') +
        '<p>Os registros ficam no histórico e podem ser reativados.</p>' +
        '<label for="ga-bulk-motivo">Motivo (opcional)</label><input type="text" id="ga-bulk-motivo" maxlength="500">',
      ok: 'Revogar ' + plural(sel.length, 'acesso', 'acessos'),
      danger: true,
      onOk: function (ov) {
        var motivo = ov.querySelector('#ga-bulk-motivo').value.trim();
        return api('POST', '/api/admin/distribuidores-ids/revogar', { motivo: motivo, items: sel.map(function (r) { return { email: r.user_email, id: r.id }; }) })
          .then(function (j) {
            revokeSel = {};
            return afterDistChange(j, plural(j.revoked, 'acesso revogado', 'acessos revogados'));
          });
      }
    });
  }

  function renderDists() {
    var q = $('ga-dist-filter').value.trim().toLowerCase();
    var qd = q.replace(/\D/g, '');
    var rows = state.dists.filter(function (r) {
      if (!r.is_active) return false;
      var d = state.catalog.find(function (x) { return r.id && String(x.id) === String(r.id); });
      r.cnpjs = d ? d.cnpjs : (r.cnpj ? [r.cnpj] : []);
      r.nome = d ? d.nome : r.distributor_name;
      return !q || [r.user_email, r.nome, r.id, r.cnpjs.map(fmtCnpj).join(' ')].join(' ').toLowerCase().indexOf(q) !== -1 ||
        (qd.length >= 3 && r.cnpjs.some(function (c) { return c.indexOf(qd) !== -1; }));
    });
    var active = state.dists.filter(function (r) { return r.is_active; });
    $('ga-dist-title').textContent = 'Acessos de distribuidores (' + new Set(active.map(function (r) { return r.user_email; })).size + ' usuários, ' + active.length + ' vínculos)';
    renderPagedTable('ga-dist-body', rows, function (r) {
      var label = r.legacy ? 'Legado por CNPJ' : 'ID ' + r.id;
      var buttons = r.legacy ? '<button type="button" class="ga-btn ga-btn-danger ga-btn-sm" data-legacy-revoke="' + esc(r.cnpj) + '" data-email="' + esc(r.user_email) + '">Revogar</button>' :
        '<button type="button" class="ga-btn ga-btn-danger ga-btn-sm" data-id-action="revoke" data-id="' + esc(r.id) + '" data-email="' + esc(r.user_email) + '">Revogar</button>';
      var picked = isSelectable(r) && revokeSel[selKey(r)];
      var box = isSelectable(r) ? '<input type="checkbox" data-sel="' + esc(selKey(r)) + '"' + (picked ? ' checked' : '') + ' aria-label="Selecionar ' + esc(r.user_email) + ', ' + esc(r.nome || 'ID ' + r.id) + '">' : '';
      return '<tr' + (picked ? ' class="is-selected"' : '') + '><td class="ga-sel">' + box + '</td><td><b>' + esc(r.user_email) + '</b></td>' +
        '<td>' + esc(r.nome || 'Distribuidor') + '<br><span class="ga-muted">' + esc(label) + '</span></td>' +
        '<td class="ga-mono">' + (r.cnpjs.length ? r.cnpjs.map(function (c) { return esc(fmtCnpj(c)); }).join('<br>') : '<span class="ga-muted">Não informado</span>') + '</td>' +
        '<td>' + buttons + '</td></tr>';
    }, '<tr><td colspan="5" class="ga-empty">Nenhum registro</td></tr>', q, renderDists);
    syncRevokeBar();
  }
  function loadDists() {
    $('ga-dist-body').innerHTML = '<tr><td colspan="5" class="ga-empty">Carregando…</td></tr>';
    return Promise.all([loadCatalog(), api('GET', '/api/admin/distribuidores-ids')]).then(function (res) {
      state.dists = res[1].items || []; state.distsLoaded = true;
      var keep = {};
      state.dists.filter(isSelectable).forEach(function (r) { if (revokeSel[selKey(r)]) keep[selKey(r)] = true; });
      revokeSel = keep;
      renderDists(); renderPicker();
    }).catch(function (e) { $('ga-dist-body').innerHTML = '<tr><td colspan="5" class="ga-empty">' + esc(e.message) + '</td></tr>'; });
  }

  var EMAIL_STATUS_MSG = { sent: ' (e-mail de acesso enviado)', failed: ' (atenção: e-mail de acesso não enviado)' };

  function afterDistChange(j, okMsg) {
    okMsg += (j && EMAIL_STATUS_MSG[j.email]) || '';
    if (j && j.audit_error) toast(okMsg + ' (atenção: falha ao gravar o histórico)', false);
    else toast(okMsg, !(j && j.email === 'failed'));
    state.auditLoaded = false;
    return loadDists();
  }

  function emailStatsMsg(stats) {
    stats = stats || {};
    var parts = [];
    if (stats.sent) parts.push(stats.sent + ' e-mail(s) enviado(s)');
    if (stats.failed) parts.push(stats.failed + ' e-mail(s) não enviado(s)');
    return parts.length ? ' · ' + parts.join(', ') : '';
  }

  function findDist(email, cnpj) {
    return state.dists.filter(function (r) { return r.user_email === email && r.cnpj === cnpj; })[0];
  }

  function onDistAction(act, email, cnpj) {
    var r = findDist(email, cnpj);
    if (!r) return;
    var e = '<b>' + esc(email) + '</b>';
    var current = { nome: r.distributor_name, cnpj: r.cnpj };
    var others = activeLinksOf(email).length - (r.is_active ? 1 : 0);
    if (act === 'add') {
      $('ga-dist-email').value = email;
      clearChips();
      renderPicker();
      $('ga-dist-form').scrollIntoView({ block: 'center', behavior: 'smooth' });
      $('ga-dist-search').focus();
    } else if (act === 'revoke') {
      confirmDialog({
        title: 'Revogar acesso do distribuidor',
        body: '<p>Revogar o acesso de ' + e + ' a <b>' + esc(distLabel(current)) + '</b>?</p>' +
          (others > 0
            ? '<p>Os outros ' + others + ' distribuidor(es) deste e-mail continuam liberados.</p>'
            : '<p>Era o único distribuidor deste e-mail: o usuário deixa de ver os dados do portal.</p>') +
          '<p>O registro fica no histórico e pode ser reativado.</p>' +
          '<label for="ga-dmotivo">Motivo (opcional)</label><input type="text" id="ga-dmotivo" maxlength="500">',
        ok: 'Revogar',
        danger: true,
        onOk: function (ov) {
          var motivo = ov.querySelector('#ga-dmotivo').value.trim();
          return api('DELETE', '/api/admin/distribuidores-acessos/' + encodeURIComponent(email), { cnpj: cnpj, motivo: motivo })
            .then(function (j) { return afterDistChange(j, 'Acesso de ' + email + ' a ' + (current.nome || fmtCnpj(cnpj)) + ' revogado'); });
        }
      });
    } else if (act === 'change') {
      confirmDialog({
        title: 'Trocar distribuidor',
        body: '<p>Trocar <b>' + esc(distLabel(current)) + '</b> por outro distribuidor para ' + e + '.' +
          (others > 0 ? ' Os outros ' + others + ' vínculo(s) não mudam.' : '') + '</p>' +
          '<label for="ga-dpick">Novo distribuidor (nome ou CNPJ)</label>' +
          '<input type="text" id="ga-dpick" list="ga-dist-options" placeholder="Digite para buscar…">',
        ok: 'Trocar',
        onOk: function (ov) {
          var d = resolveDist(ov.querySelector('#ga-dpick').value);
          if (!d) return Promise.reject(new Error('Selecione um distribuidor da lista'));
          if (d.cnpjs.length !== 1 || d.ambiguous.length) return Promise.reject(new Error('Para trocar, escolha um distribuidor com um único CNPJ sem conflito. Para outros casos, conceda e revogue os vínculos desejados.'));
          if (d.cnpj === cnpj) return Promise.reject(new Error('Escolha um distribuidor diferente do atual'));
          return api('PATCH', '/api/admin/distribuidores-acessos/' + encodeURIComponent(email), { from_cnpj: cnpj, cnpj: d.cnpj })
            .then(function (j) { return afterDistChange(j, 'Vínculo trocado: ' + email + ' → ' + (d.nome || fmtCnpj(d.cnpj))); });
        }
      });
    } else if (act === 'reactivate') {
      confirmDialog({
        title: 'Reativar acesso do distribuidor',
        body: '<p>Reativar o acesso de ' + e + ' a <b>' + esc(distLabel(current)) + '</b>?</p>',
        ok: 'Reativar',
        onOk: function () {
          return api('POST', '/api/admin/distribuidores-acessos', { email: email, cnpj: cnpj })
            .then(function (j) { return afterDistChange(j, 'Acesso reativado: ' + email + ' → ' + (current.nome || fmtCnpj(cnpj))); });
        }
      });
    }
  }

  /* Formulário: vários distribuidores para o mesmo e-mail, marcados na lista (chips mostram a seleção) */
  var chips = [];
  function renderChips() {
    var box = $('ga-dist-chips');
    box.classList.toggle('has-items', chips.length > 0);
    box.innerHTML = chips.map(function (d, i) {
      return '<span class="ga-chip"><span>' + esc(d.nome || '(sem nome)') + '</span><small>' + esc(d.cnpjs.map(fmtCnpj).join(' / ')) + '</small>' +
        '<button type="button" data-chip="' + i + '" aria-label="Remover ' + esc(d.nome || d.cnpj) + '">' +
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button></span>';
    }).join('');
    $('ga-dist-submit').textContent = chips.length > 1 ? 'Conceder ' + chips.length + ' acessos' : 'Conceder acesso';
  }
  function clearChips() { chips = []; renderChips(); }
  function grantedIds() {
    var email = $('ga-dist-email').value.trim().toLowerCase();
    return activeLinksOf(email).map(function (r) { return String(r.id); });
  }
  function pickerRows() {
    var q = $('ga-dist-search').value.trim().toLowerCase();
    var qd = q.replace(/\D/g, '');
    return state.catalog.filter(function (d) {
      return d.id && (!q || (d.nome || '').toLowerCase().indexOf(q) !== -1 || String(d.id) === q ||
        (qd.length >= 3 && d.cnpjs.some(function (c) { return c.indexOf(qd) !== -1; })));
    });
  }
  function renderPicker() {
    var granted = grantedIds();
    // Quem já tem o acesso não precisa continuar selecionado ao trocar o e-mail
    chips = chips.filter(function (c) { return granted.indexOf(String(c.id)) === -1; });
    renderChips();
    var rows = pickerRows();
    $('ga-dist-all').textContent = 'Marcar todos (' + rows.filter(function (d) { return granted.indexOf(String(d.id)) === -1; }).length + ')';
    $('ga-dist-list').innerHTML = rows.length ? rows.map(function (d) {
      var has = granted.indexOf(String(d.id)) !== -1;
      var on = has || chips.some(function (c) { return c.id === d.id; });
      return '<label class="ga-pick-item' + (has ? ' is-granted' : '') + '"><input type="checkbox" value="' + esc(d.id) + '"' + (on ? ' checked' : '') + (has ? ' disabled' : '') + '>' +
        '<span class="ga-pick-name">' + esc(d.nome || '(sem nome)') + '</span>' +
        '<small>' + (has ? 'Já liberado' : 'ID ' + esc(d.id)) + '</small></label>';
    }).join('') : '<p class="ga-pick-empty">Nenhum distribuidor encontrado</p>';
  }
  function onPickerToggle(e) {
    var d = state.catalog.filter(function (x) { return String(x.id) === e.target.value; })[0];
    if (!d) return;
    if (e.target.checked) chips.push(d);
    else chips = chips.filter(function (c) { return c.id !== d.id; });
    renderChips();
  }
  function onPickerAll() {
    var granted = grantedIds();
    pickerRows().forEach(function (d) {
      if (granted.indexOf(String(d.id)) === -1 && !chips.some(function (c) { return c.id === d.id; })) chips.push(d);
    });
    renderPicker();
  }

  function onDistSubmit(ev) {
    ev.preventDefault();
    var email = $('ga-dist-email').value.trim().toLowerCase();
    if (!ANY_EMAIL_RE.test(email)) { toast('Informe um e-mail válido', false); $('ga-dist-email').focus(); return; }
    if (!chips.length) { toast('Marque pelo menos um distribuidor', false); $('ga-dist-search').focus(); return; }
    var adm = findItem(email);
    if (adm && adm.is_active) { toast(email + ' é ' + adm.role + ' ativo; revogue o acesso de administrador antes', false); return; }
    var todo = chips.slice();
    confirmDialog({
      title: 'Conceder acesso por ID',
      body: '<p>Liberar para <b>' + esc(email) + '</b>:</p><ul>' + todo.map(function (d) {
        return '<li><b>' + esc(d.nome) + '</b> — ID ' + esc(d.id) + '</li>';
      }).join('') + '</ul><p>O acesso inclui todos os registros desses IDs, inclusive CNPJs novos ou não informados.</p>',
      ok: 'Conceder',
      onOk: function () {
        return api('POST', '/api/admin/distribuidores-ids', { email: email, ids: todo.map(function (d) { return d.id; }) }).then(function (j) {
          $('ga-dist-email').value = ''; $('ga-dist-search').value = ''; clearChips();
          return afterDistChange(j, 'Acesso por ID concedido para ' + email);
        });
      }
    });
  }

  /* ── Carga em massa: colar do Excel / abrir CSV → validar no servidor → gravar ── */
  var EMAIL_IN_TEXT = /[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}/i;
  var CNPJ_IN_TEXT = /\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}|\b\d{1,14}\b/g;
  var bulkPlan = null;

  // Cada linha vira um ou mais pares (e-mail, CNPJ). As colunas são reconhecidas pelo conteúdo,
  // então a ordem das colunas e o cabeçalho não importam; linhas sem e-mail (cabeçalho, total) são ignoradas.
  function parseBulk(text) {
    var out = [];
    String(text || '').split(/\r?\n/).forEach(function (line, i) {
      if (!line.trim()) return;
      var cells = line.split(/\t|;/);
      if (cells.length === 1) cells = line.split(',');
      var email = null, cnpjs = [];
      cells.forEach(function (c) {
        var m = c.match(EMAIL_IN_TEXT);
        if (m && !email) { email = m[0].toLowerCase(); return; }
        (c.match(CNPJ_IN_TEXT) || []).forEach(function (raw) { cnpjs.push(raw.replace(/\D/g, '')); });
      });
      if (!email) return;
      if (!cnpjs.length) cnpjs.push('');
      cnpjs.forEach(function (c) { out.push({ linha: i + 1, email: email, cnpj: c }); });
    });
    return out;
  }

  var STATUS_TXT = { new: 'Novo acesso', reactivate: 'Reativar', exists: 'Já liberado', error: 'Erro' };

  function renderBulk(j) {
    var s = j.summary || {};
    $('ga-bulk-summary').innerHTML =
      '<span class="ga-sum ga-sum-new">Novos <b>' + (s.new || 0) + '</b></span>' +
      '<span class="ga-sum ga-sum-reactivate">Reativar <b>' + (s.reactivate || 0) + '</b></span>' +
      '<span class="ga-sum">Já liberados <b>' + (s.exists || 0) + '</b></span>' +
      '<span class="ga-sum ga-sum-error">Com erro <b>' + (s.error || 0) + '</b></span>';
    // Erros primeiro: é o que pede ação antes de gravar
    var order = { error: 0, new: 1, reactivate: 2, exists: 3 };
    var items = (j.items || []).slice().sort(function (a, b) { return order[a.status] - order[b.status] || a.linha - b.linha; });
    $('ga-bulk-body').innerHTML = items.map(function (r) {
      return '<tr>' +
        '<td class="ga-mono">' + esc(r.linha) + '</td>' +
        '<td>' + dash(r.email) + '</td>' +
        '<td>' + dash(r.nome) + '</td>' +
        '<td class="ga-mono">' + dash(r.cnpj_fmt) + '</td>' +
        '<td><span class="ga-st ga-st-' + esc(r.status) + '">' + esc(STATUS_TXT[r.status] || r.status) +
          (r.motivo ? '<span class="ga-st-why">' + esc(r.motivo) + '</span>' : '') + '</span></td>' +
      '</tr>';
    }).join('');
    var n = (s.new || 0) + (s.reactivate || 0);
    var btn = $('ga-bulk-commit');
    btn.disabled = n === 0;
    btn.textContent = n ? 'Gravar ' + n + ' acesso' + (n > 1 ? 's' : '') : 'Nada a gravar';
    $('ga-bulk-result').hidden = false;
  }

  function onBulkValidate() {
    var items = parseBulk($('ga-bulk-text').value);
    if (!items.length || items.length > 1000) { toast('Informe de 1 a 1.000 linhas com e-mail e ID.', false); return; }
    Promise.all([loadCatalog(), state.distsLoaded ? Promise.resolve() : loadDists()]).then(function () {
      var seen = {}, summary = {new: 0, reactivate: 0, exists: 0, error: 0};
      var plan = items.map(function (r) {
        var d = resolveDist(r.cnpj), key = r.email + '|' + (d && d.id), row = {linha:r.linha, email:r.email, id:d && d.id,
          nome:d && d.nome, cnpj_fmt:d && d.id ? 'ID ' + d.id : r.cnpj};
        if (!ANY_EMAIL_RE.test(r.email) || !d || !d.id) { row.status='error'; row.motivo='E-mail inválido ou ID/CNPJ sem correspondência única'; }
        else if (seen[key]) { row.status='error'; row.motivo='Repetido neste lote'; }
        else {
          seen[key] = true;
          var old = state.dists.find(function (x) { return x.user_email === r.email && String(x.id) === String(d.id); });
          var legacy = state.dists.some(function (x) { return x.user_email === r.email && x.legacy; });
          if (legacy) { row.status='error'; row.motivo='Usuário possui vínculo legado por CNPJ'; }
          else row.status = old ? (old.is_active ? 'exists' : 'reactivate') : 'new';
        }
        summary[row.status]++; return row;
      });
      bulkPlan = plan; renderBulk({items:plan, summary:summary});
    }).catch(function (e) { toast(e.message, false); });
  }
  function onBulkCommit() {
    if (!bulkPlan) return;
    var grouped = {};
    bulkPlan.filter(function (r) { return r.status === 'new' || r.status === 'reactivate'; }).forEach(function (r) {
      (grouped[r.email] || (grouped[r.email] = [])).push(r.id);
    });
    var emails = Object.keys(grouped), saved = 0, failed = 0, btn = $('ga-bulk-commit');
    btn.disabled = true; showLoadingToast('Gravando acessos por ID...');
    emails.reduce(function (chain, email) { return chain.then(function () {
      return api('POST', '/api/admin/distribuidores-ids', {email:email, ids:grouped[email]}).then(function () { saved += grouped[email].length; }).catch(function () { failed += grouped[email].length; });
    }); }, Promise.resolve()).then(function () {
      toast(saved + ' acesso(s) gravado(s)' + (failed ? '; ' + failed + ' não gravado(s). Valide novamente.' : ''), !failed);
      bulkPlan = null; $('ga-bulk-result').hidden = true; state.auditLoaded = false; return loadDists();
    });
  }

  function downloadCsv(name, rows) {
    // ; e BOM: o Excel em português abre direto em colunas e com acentos corretos
    var csv = '﻿' + rows.map(function (r) {
      return r.map(function (v) { v = String(v == null ? '' : v); return /[;"\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }).join(';');
    }).join('\r\n');
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  function onExportDistributorReference() {
    var btn = $('ga-export-dist-reference');
    btn.disabled = true;
    api('GET', '/api/admin/distribuidores/referencia').then(function (j) {
      var items = j.items || [];
      if (!items.length) { toast('Nenhum distribuidor encontrado na referência.', false); return; }
      // Evita que planilhas interpretem texto da origem como fórmula.
      function safe(v) {
        v = String(v == null ? '' : v);
        return /^[\s\x00-\x1f]*[=+@-]/.test(v) ? "'" + v : v;
      }
      var rows = items.map(function (r) { return [safe(r.id), safe(r.nome), safe(r.cnpj || 'Não informado')]; });
      downloadCsv('referencia_distribuidores.csv', [['ID do distribuidor', 'Distribuidor', 'CNPJ']].concat(rows));
    }).catch(function (e) { toast(e.message || 'Falha ao exportar a referência.', false); })
      .finally(function () { btn.disabled = false; });
  }

  function onBulkTemplate() {
    downloadCsv('modelo_acessos_distribuidores.csv', [
      ['email', 'id_distribuidor', 'distribuidor (opcional, só para conferência)'],
      ['joao.silva@distribuidor.com.br', '138', 'Distribuidor Exemplo'],
      ['joao.silva@distribuidor.com.br', '177', 'Outro distribuidor']
    ]);
  }

  function onBulkExport() {
    var go = state.distsLoaded ? Promise.resolve() : loadDists();
    go.then(function () {
      var rows = state.dists.filter(function (r) { return r.is_active; }).map(function (r) {
        return [r.user_email, r.id || '', r.distributor_name || '', String(r.valid_from_date || '').slice(0, 10), r.created_by_user || ''];
      });
      downloadCsv('acessos_distribuidores_ativos.csv', [['email', 'id_distribuidor', 'distribuidor', 'desde', 'concedido por']].concat(rows));
    });
  }

  function onBulkFile(ev) {
    var f = ev.target.files && ev.target.files[0];
    if (!f) return;
    var reader = new FileReader();
    reader.onload = function () {
      var text = String(reader.result || '');
      // CSV salvo pelo Excel costuma vir em Windows-1252: se aparecer o caractere inválido, relê nesse encoding
      if (text.indexOf('�') !== -1) {
        var r2 = new FileReader();
        r2.onload = function () { $('ga-bulk-text').value = String(r2.result || ''); onBulkValidate(); };
        r2.readAsText(f, 'windows-1252');
        return;
      }
      $('ga-bulk-text').value = text.replace(/^﻿/, '');
      onBulkValidate();
    };
    reader.readAsText(f, 'utf-8');
    ev.target.value = '';
  }

  /* ── Histórico ── */
  function renderAudit() {
    var q = $('ga-audit-filter').value.trim().toLowerCase();
    var rows = state.audit.filter(function (r) {
      if (!q) return true;
      return [r.actor_email, r.target_email, r.action, ACTION_LABELS[r.action], r.details, r.old_role, r.new_role, r.source]
        .join(' ').toLowerCase().indexOf(q) !== -1;
    });
    if (!rows.length) {
      $('ga-audit-body').innerHTML = '<tr><td colspan="7" class="ga-empty">Nenhum evento</td></tr>';
      return;
    }
    $('ga-audit-body').innerHTML = rows.map(function (r) {
      var roles = (r.old_role || r.new_role)
        ? (r.old_role ? roleBadge(r.old_role) : '<span class="ga-muted">—</span>') + ' → ' + (r.new_role ? roleBadge(r.new_role) : '<span class="ga-muted">—</span>')
        : '<span class="ga-muted">—</span>';
      return '<tr>' +
        '<td style="white-space:nowrap">' + fmtMs(r.event_ms) + '</td>' +
        '<td>' + dash(r.actor_email) + '</td>' +
        '<td><span class="ga-act ga-act-' + esc(r.action) + '">' + esc(ACTION_LABELS[r.action] || r.action) + '</span></td>' +
        '<td>' + dash(r.target_email) + '</td>' +
        '<td style="white-space:nowrap">' + roles + '</td>' +
        '<td>' + dash(r.details) + '</td>' +
        '<td>' + dash(r.source) + '</td>' +
      '</tr>';
    }).join('');
  }

  function loadAudit() {
    $('ga-audit-body').innerHTML = '<tr><td colspan="7" class="ga-empty">Carregando…</td></tr>';
    var refreshBtn = $('ga-audit-refresh');
    if (refreshBtn) { refreshBtn.disabled = true; refreshBtn.innerHTML = '<span class="amb-spinner"></span> Atualizando...'; }
    return api('GET', '/api/admin/auditoria?limit=500').then(function (j) {
      state.audit = j.items || [];
      state.auditLoaded = true;
      renderAudit();
    }).catch(function (e) {
      $('ga-audit-body').innerHTML = '<tr><td colspan="7" class="ga-empty">' + esc(e.message) + '</td></tr>';
    }).finally(function () {
      if (refreshBtn) { refreshBtn.disabled = false; refreshBtn.textContent = 'Atualizar'; }
    });
  }

  /* ── Distribuidores no Portal (tbl_dim_distribuidor_portal) ── */
  function renderPortalCandidates() {
    var box = $('ga-pd-cand-list');
    if (!box) return;
    var q = ($('ga-pd-search') ? $('ga-pd-search').value : '').trim().toLowerCase();
    var qd = q.replace(/\D/g, '');
    var selectedSet = new Set(state.pdSelected.map(String));
    var list = (state.portalCandidates || []).filter(function (c) {
      if (!q) return true;
      var hay = [c.nome, c.id, c.cnpj].concat(c.cnpjs || []).join(' ').toLowerCase();
      return hay.indexOf(q) !== -1 || (qd && hay.indexOf(qd) !== -1);
    });
    if (!list.length) {
      box.innerHTML = '<p class="ga-pick-empty">' +
        (state.portalCandidates.length ? 'Nenhum distribuidor corresponde à busca.' : 'Todos os distribuidores do Unity Catalog já estão cadastrados na lista abaixo.') +
        '</p>';
      return;
    }
    box.innerHTML = list.map(function (c) {
      var sid = String(c.id);
      var checked = selectedSet.has(sid) ? ' checked' : '';
      var hasCompras = c.compras && c.compras.length > 0;
      return '<label class="ga-pick-item">' +
        '<input type="checkbox" value="' + esc(sid) + '"' + checked + '>' +
        '<span class="ga-pick-name" title="' + esc(c.nome) + '">' + esc(c.nome) + '</span>' +
        '<small>ID ' + esc(sid) + (hasCompras ? '' : ' · s/ compra') + '</small>' +
      '</label>';
    }).join('');
  }

  function renderPortalDists() {
    var tbody = $('ga-pd-body');
    if (!tbody) return;
    var q = ($('ga-pd-filter') ? $('ga-pd-filter').value : '').trim().toLowerCase();
    var qd = q.replace(/\D/g, '');
    var activeList = state.portalDists.filter(function (r) { return r.is_active !== false; });
    if ($('ga-pd-title')) {
      $('ga-pd-title').textContent = 'Distribuidores no portal (' + activeList.length + ')';
    }
    var rows = activeList.filter(function (r) {
      if (!q) return true;
      var hay = [r.id, r.nome, r.nome_referencia, r.cnpj_referencia, fmtCnpj(r.cnpj_referencia), r.notes].join(' ').toLowerCase();
      return hay.indexOf(q) !== -1 || (qd && hay.indexOf(qd) !== -1);
    });
    renderPagedTable('ga-pd-body', rows, function (r) {
      var refDiff = r.nome_referencia && r.nome_referencia.trim().toLowerCase() !== (r.nome || '').trim().toLowerCase();
      var refHtml = refDiff ? '<div class="ga-muted" style="font-size:12px">Ref. planilha: ' + esc(r.nome_referencia) + '</div>' : '';
      var cnpjTxt = r.cnpj_referencia ? fmtCnpj(r.cnpj_referencia) : '—';
      var extraCnpjs = (r.cnpjs_uc || []).length > 1 ? ' <span class="ga-count" title="' + esc(r.cnpjs_uc.map(fmtCnpj).join(', ')) + '">+' + (r.cnpjs_uc.length - 1) + ' filial</span>' : '';
      var btnToggle = '<button type="button" class="ga-btn ga-btn-danger ga-btn-sm" data-pd-act="disable" data-id="' + esc(r.id) + '">Desativar</button>';
      var btnNotes = '<button type="button" class="ga-btn ga-btn-outline ga-btn-sm" data-pd-act="notes" data-id="' + esc(r.id) + '">Observação</button>';
      return '<tr>' +
        '<td class="ga-mono"><b>' + esc(r.id) + '</b></td>' +
        '<td><b>' + esc(r.nome) + '</b>' + refHtml + '</td>' +
        '<td class="ga-mono">' + esc(cnpjTxt) + extraCnpjs + '</td>' +
        '<td>' + dash(r.notes) + '</td>' +
        '<td><div class="ga-actions">' + btnToggle + btnNotes + '</div></td>' +
      '</tr>';
    }, '<tr><td colspan="5" class="ga-empty">Nenhum distribuidor ativo encontrado para este filtro.</td></tr>', q, renderPortalDists);
  }

  function loadPortalDists() {
    if ($('ga-pd-body')) $('ga-pd-body').innerHTML = '<tr><td colspan="5" class="ga-empty">Carregando…</td></tr>';
    return api('GET', '/api/admin/distribuidores-portal').then(function (j) {
      state.portalDists = j.items || [];
      state.portalCandidates = j.candidates || [];
      state.portalDistsLoaded = true;
      renderPortalCandidates();
      renderPortalDists();
    }).catch(function (e) {
      if ($('ga-pd-body')) $('ga-pd-body').innerHTML = '<tr><td colspan="5" class="ga-empty">' + esc(e.message) + '</td></tr>';
    });
  }

  function onPortalDistSubmit(ev) {
    ev.preventDefault();
    var ids = state.pdSelected.slice();
    var manualRaw = ($('ga-pd-manual-id') ? $('ga-pd-manual-id').value : '').trim();
    if (manualRaw) {
      if (!/^\d+$/.test(manualRaw) || parseInt(manualRaw, 10) <= 0) {
        toast('Informe um ID_DISTRIBUIDOR numérico válido (> 0)', false);
        $('ga-pd-manual-id').focus();
        return;
      }
      var mid = String(parseInt(manualRaw, 10));
      if (ids.indexOf(mid) === -1) ids.push(mid);
    }
    if (!ids.length) {
      toast('Marque ao menos um distribuidor da lista ou informe o ID manualmente.', false);
      return;
    }
    var notes = ($('ga-pd-notes') ? $('ga-pd-notes').value : '').trim();
    var labels = ids.map(function (id) {
      var c = state.portalCandidates.find(function (x) { return String(x.id) === String(id); }) ||
              state.portalDists.find(function (x) { return String(x.id) === String(id); });
      return c ? ('<b>' + esc(c.nome) + '</b> (ID ' + esc(id) + ')') : ('<b>ID ' + esc(id) + '</b>');
    });
    confirmDialog({
      title: 'Liberar distribuidor no portal',
      body: '<p>Ativar no portal ' + (ids.length === 1 ? 'o distribuidor ' + labels[0] : (ids.length + ' distribuidores')) + '?</p>' +
        (ids.length > 1 ? '<ul class="ga-revoke-list"><li>' + labels.join('</li><li>') + '</li></ul>' : '') +
        '<p>Ele passará a aparecer imediatamente no seletor de distribuidores, na visão consolidada ("Todos") e seus usuários vinculados poderão acessar o portal.</p>',
      ok: 'Liberar no portal',
      background: true,
      onOk: function () {
        state.pdSelected = [];
        if ($('ga-pd-manual-id')) $('ga-pd-manual-id').value = '';
        if ($('ga-pd-notes')) $('ga-pd-notes').value = '';
        toast((ids.length === 1 ? 'Distribuidor liberado no portal' : (ids.length + ' distribuidores liberados no portal')) + ' (sincronizando em segundo plano)', true);
        return api('POST', '/api/admin/distribuidores-portal', { ids: ids, notes: notes }).then(function (j) {
          state.catalog = [];
          state.auditLoaded = false;
          if (j && j.items) {
            state.portalDists = j.items;
            state.portalCandidates = j.candidates || [];
            renderPortalCandidates();
            renderPortalDists();
            return;
          }
          return loadPortalDists();
        });
      }
    });
  }

  function onPortalDistAction(act, id) {
    var row = state.portalDists.find(function (x) { return String(x.id) === String(id); });
    if (!row) return;
    if (act === 'notes') {
      confirmDialog({
        title: 'Observação · ' + row.nome + ' (ID ' + row.id + ')',
        body: '<label for="ga-pd-edit-notes">Observação</label>' +
          '<input type="text" id="ga-pd-edit-notes" maxlength="500" value="' + esc(row.notes || '') + '" placeholder="Ex.: Sell-out validado">',
        ok: 'Salvar',
        background: true,
        onOk: function (ov) {
          var newNotes = ov.querySelector('#ga-pd-edit-notes').value.trim();
          row.notes = newNotes;
          row.updated_by = (state.me && state.me.email) || row.updated_by;
          row.updated_ms = Date.now();
          renderPortalDists();
          toast('Observação atualizada (sincronizando em segundo plano)', true);
          return api('PATCH', '/api/admin/distribuidores-portal/' + encodeURIComponent(row.id), { notes: newNotes }).then(function (j) {
            state.auditLoaded = false;
            if (j && j.items) {
              state.portalDists = j.items;
              state.portalCandidates = j.candidates || [];
              renderPortalDists();
            }
          });
        }
      });
      return;
    }
    var toActive = act === 'enable';
    var nActive = state.portalDists.filter(function (x) { return x.is_active; }).length;
    var isLast = !toActive && row.is_active && nActive <= 1;
    confirmDialog({
      title: (toActive ? 'Ativar' : 'Desativar') + ' distribuidor no portal',
      body: '<p>' + (toActive ? 'Ativar' : 'Desativar') + ' <b>' + esc(row.nome) + '</b> (ID <b>' + esc(row.id) + '</b>) no portal?</p>' +
        (toActive
          ? '<p>O distribuidor voltará a aparecer no seletor, na visão consolidada e seus usuários vinculados terão acesso liberado.</p>'
          : '<p>O distribuidor deixará de aparecer no portal imediatamente e os usuários vinculados somente a ele verão a mensagem de portal indisponível.</p>') +
        (isLast ? '<p class="ga-revoke-warn">Atenção: este é o último distribuidor ativo. Desativá-lo deixará o portal vazio.</p>' : '') +
        '<label for="ga-pd-toggle-notes">Observação (opcional)</label>' +
        '<input type="text" id="ga-pd-toggle-notes" maxlength="500" value="' + esc(row.notes || '') + '">',
      ok: toActive ? 'Ativar no portal' : 'Desativar',
      danger: !toActive,
      background: true,
      onOk: function (ov) {
        var newNotes = ov.querySelector('#ga-pd-toggle-notes').value.trim();
        if (!toActive) {
          state.portalDists = state.portalDists.filter(function (x) { return String(x.id) !== String(row.id); });
          if (!state.portalCandidates.some(function (c) { return String(c.id) === String(row.id); })) {
            state.portalCandidates.push({
              id: row.id,
              nome: row.nome,
              cnpj: row.cnpj_referencia || '',
              cnpjs: row.cnpjs_uc || [],
              compras: row.compras || []
            });
            state.portalCandidates.sort(function (a, b) { return String(a.nome).localeCompare(String(b.nome), 'pt-BR'); });
          }
        } else {
          row.is_active = true;
          row.notes = newNotes;
          row.updated_by = (state.me && state.me.email) || row.updated_by;
          row.updated_ms = Date.now();
        }
        renderPortalCandidates();
        renderPortalDists();
        toast(row.nome + (toActive ? ' ativado no portal' : ' removido do portal') + ' (sincronizando em segundo plano)', true);
        return api('PATCH', '/api/admin/distribuidores-portal/' + encodeURIComponent(row.id), {
          is_active: toActive,
          notes: newNotes,
          force_last: isLast
        }).then(function (j) {
          state.catalog = [];
          state.auditLoaded = false;
          if (j && j.items) {
            state.portalDists = j.items;
            state.portalCandidates = j.candidates || [];
            renderPortalCandidates();
            renderPortalDists();
            return;
          }
          return loadPortalDists();
        });
      }
    });
  }

  function onPortalDistExport() {
    var go = state.portalDistsLoaded ? Promise.resolve() : loadPortalDists();
    go.then(function () {
      var rows = state.portalDists.map(function (r) {
        return [
          r.id,
          r.nome || '',
          r.nome_referencia || '',
          r.cnpj_referencia ? fmtCnpj(r.cnpj_referencia) : '',
          r.is_active ? 'ATIVO' : 'INATIVO',
          r.notes || '',
          r.updated_by || ''
        ];
      });
      downloadCsv('distribuidores_no_portal.csv', [
        ['ID_DISTRIBUIDOR', 'NOME_PORTAL_DNA', 'NOME_REFERENCIA', 'CNPJ_INFORMATIVO', 'STATUS', 'OBSERVACAO', 'ATUALIZADO_POR']
      ].concat(rows));
    });
  }

  /* ── Custom Select Padrão do Portal (.custom-select.qf-select) ── */
  function makeCustomSelect(selectId, placeholderName) {
    var container = $(selectId);
    if (!container || container._initialized) return;
    container._initialized = true;
    placeholderName = placeholderName || 'Todos';

    var input = container.querySelector('.search-input');
    var optionsContainer = container.querySelector('.options-container');
    var allOptions = [];
    var selectedValues = new Set();

    function updateTriggerText() {
      if (selectedValues.size === 0) {
        input.value = '';
        input.placeholder = placeholderName;
      } else if (selectedValues.size === 1) {
        var val = Array.from(selectedValues)[0];
        var opt = allOptions.find(function (o) { return String(o.value) === String(val); });
        input.value = opt ? opt.label : val;
      } else {
        input.value = selectedValues.size + ' sel.';
      }
    }

    function showDropdown() {
      document.querySelectorAll('.custom-select').forEach(function (cs) {
        if (cs !== container) {
          cs.classList.remove('active');
          var opt = cs.querySelector('.options-container');
          if (opt) opt.style.display = 'none';
        }
      });
      optionsContainer.style.display = 'block';
      container.classList.add('active');
      optionsContainer.querySelectorAll('.option-item').forEach(function (item) { item.style.display = 'flex'; });
      if (document.activeElement !== input) input.focus();
      try { input.select(); } catch (e) {}
    }

    function closeDropdown() {
      optionsContainer.style.display = 'none';
      container.classList.remove('active');
      updateTriggerText();
    }

    container.addEventListener('click', function (e) {
      if (optionsContainer.contains(e.target)) return;
      e.stopPropagation();
      if (optionsContainer.style.display === 'block') closeDropdown();
      else showDropdown();
    });

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeDropdown();
      else if ((e.key === 'ArrowDown' || e.key === 'Enter') && optionsContainer.style.display !== 'block') showDropdown();
    });

    document.addEventListener('click', function (e) {
      if (!container.contains(e.target)) closeDropdown();
    });

    container.populate = function (options, initialSelected, emptyPlaceholder) {
      allOptions = options || [];
      optionsContainer.innerHTML = '';
      selectedValues.clear();
      (initialSelected || []).forEach(function (v) { selectedValues.add(String(v)); });

      if (allOptions.length === 0) {
        optionsContainer.innerHTML = '<div class="option-item" style="color:#94A3B8;font-style:italic;cursor:default;justify-content:center;padding:10px;">' + esc(emptyPlaceholder || 'Nenhum valor') + '</div>';
        updateTriggerText();
        return;
      }

      var selectAllItem = document.createElement('div');
      selectAllItem.className = 'option-item select-all-item';
      selectAllItem.innerHTML = '<input type="checkbox" /><span style="font-weight:700;">Selecionar Todos</span>';
      var selectAllCb = selectAllItem.querySelector('input');

      selectAllItem.addEventListener('click', function (e) {
        e.stopPropagation();
        if (e.target !== selectAllCb) selectAllCb.checked = !selectAllCb.checked;
        var isChecked = selectAllCb.checked;
        optionsContainer.querySelectorAll('.option-item:not(.select-all-item) input').forEach(function (cb) {
          cb.checked = isChecked;
          if (isChecked) selectedValues.add(cb.value);
          else selectedValues.delete(cb.value);
        });
        updateTriggerText();
        container.dispatchEvent(new Event('change', { bubbles: true }));
      });
      optionsContainer.appendChild(selectAllItem);

      allOptions.forEach(function (opt) {
        var item = document.createElement('div');
        item.className = 'option-item';
        item.innerHTML = '<input type="checkbox" value="' + esc(opt.value) + '" /><span title="' + esc(opt.label) + '">' + esc(opt.label) + '</span>';
        var cb = item.querySelector('input');
        if (selectedValues.has(String(opt.value))) cb.checked = true;
        item.addEventListener('click', function (e) {
          e.stopPropagation();
          if (e.target !== cb) cb.checked = !cb.checked;
          if (cb.checked) selectedValues.add(cb.value);
          else selectedValues.delete(cb.value);
          var allCbs = Array.from(optionsContainer.querySelectorAll('.option-item:not(.select-all-item) input'));
          selectAllCb.checked = allCbs.length > 0 && allCbs.every(function (x) { return x.checked; });
          updateTriggerText();
          container.dispatchEvent(new Event('change', { bubbles: true }));
        });
        optionsContainer.appendChild(item);
      });

      var allCbsInit = Array.from(optionsContainer.querySelectorAll('.option-item:not(.select-all-item) input'));
      selectAllCb.checked = allCbsInit.length > 0 && allCbsInit.every(function (x) { return x.checked; });
      updateTriggerText();
    };

    input.addEventListener('input', function () {
      var filter = input.value.toLowerCase();
      optionsContainer.querySelectorAll('.option-item:not(.select-all-item)').forEach(function (item) {
        item.style.display = item.textContent.toLowerCase().indexOf(filter) !== -1 ? 'flex' : 'none';
      });
    });

    container.getSelectedValues = function () { return Array.from(selectedValues); };
    container.clear = function () {
      selectedValues.clear();
      optionsContainer.querySelectorAll('input').forEach(function (cb) { cb.checked = false; });
      updateTriggerText();
    };
    container.setSelected = function (values) {
      selectedValues.clear();
      (values || []).forEach(function (v) { selectedValues.add(String(v)); });
      optionsContainer.querySelectorAll('.option-item:not(.select-all-item) input').forEach(function (cb) { cb.checked = selectedValues.has(cb.value); });
      var all = optionsContainer.querySelector('.select-all-item input');
      if (all) all.checked = false;
      updateTriggerText();
    };
  }

  function getUsoFilterValues(id) {
    var el = $(id);
    if (el && typeof el.getSelectedValues === 'function') return el.getSelectedValues();
    return [];
  }

  var MES_NOMES_PT = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
  var usoSort = { key: 'data', dir: -1 };

  function fmtIsoBr(iso) {
    if (!iso || String(iso).length < 10) return '—';
    var p = String(iso).slice(0, 10).split('-');
    return p.length === 3 ? (p[2] + '/' + p[1] + '/' + p[0]) : iso;
  }

  function populateUsoDias() {
    var sel = $('ga-uso-dia');
    if (!sel || !sel.populate) return;
    var anos = getUsoFilterValues('ga-uso-ano');
    var meses = getUsoFilterValues('ga-uso-mes');
    var maxDia = 31;
    if (anos.length === 1 && meses.length === 1) {
      maxDia = new Date(parseInt(anos[0], 10), parseInt(meses[0], 10), 0).getDate();
    } else if (meses.length === 1) {
      maxDia = new Date(2026, parseInt(meses[0], 10), 0).getDate();
    }
    var cur = getUsoFilterValues('ga-uso-dia').filter(function (d) { return parseInt(d, 10) <= maxDia; });
    var opts = [];
    for (var d = 1; d <= maxDia; d++) {
      var dd = String(d).padStart(2, '0');
      opts.push({ value: dd, label: dd });
    }
    sel.populate(opts, cur);
  }

  function initUsoSelects() {
    var nowBr = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Sao_Paulo' }));
    var curAno = String(nowBr.getFullYear());
    var curMes = String(nowBr.getMonth() + 1).padStart(2, '0');

    var anosList = ['2025', '2026'];
    if (anosList.indexOf(curAno) === -1) anosList.push(curAno);
    anosList.sort();

    makeCustomSelect('ga-uso-ano', 'Todos');
    makeCustomSelect('ga-uso-mes', 'Todos');
    makeCustomSelect('ga-uso-dia', 'Todos');
    makeCustomSelect('ga-uso-perfil', 'Todos');

    if ($('ga-uso-ano') && $('ga-uso-ano').populate) {
      $('ga-uso-ano').populate(anosList.map(function (a) { return { value: a, label: a }; }), [curAno]);
    }
    if ($('ga-uso-mes') && $('ga-uso-mes').populate) {
      $('ga-uso-mes').populate([
        { value: '01', label: 'Jan' },
        { value: '02', label: 'Fev' },
        { value: '03', label: 'Mar' },
        { value: '04', label: 'Abr' },
        { value: '05', label: 'Mai' },
        { value: '06', label: 'Jun' },
        { value: '07', label: 'Jul' },
        { value: '08', label: 'Ago' },
        { value: '09', label: 'Set' },
        { value: '10', label: 'Out' },
        { value: '11', label: 'Nov' },
        { value: '12', label: 'Dez' }
      ], [curMes]);
    }
    populateUsoDias();
    if ($('ga-uso-perfil') && $('ga-uso-perfil').populate) {
      $('ga-uso-perfil').populate([
        { value: 'distribuidor', label: 'Distribuidores' },
        { value: 'admin', label: 'Administradores' },
        { value: 'simulacao', label: 'Simulações' }
      ], ['distribuidor']);
    }
  }

  /* ── Uso do Portal (tbl_log_app_access — granularidade diária) ── */
  function getFilteredUsoRows(includeDia) {
    var data = state.uso;
    if (!data) return [];
    var raw = data.rows || data.users || [];
    var q = ($('ga-uso-filter') ? $('ga-uso-filter').value : '').trim().toLowerCase();
    var pfs = getUsoFilterValues('ga-uso-perfil');
    var diasSel = includeDia ? getUsoFilterValues('ga-uso-dia') : [];
    var filtered = raw.filter(function (u) {
      if (pfs.length > 0 && pfs.indexOf(u.perfil) === -1) return false;
      if (diasSel.length > 0) {
        var dd = String(u.dia || '').padStart(2, '0');
        if (diasSel.indexOf(dd) === -1) return false;
      }
      if (!q) return true;
      var hay = [u.user_email, u.perfil, u.role, fmtIsoBr(u.data)].concat(u.dist_nomes || [], u.dist_ids || []).join(' ').toLowerCase();
      return hay.indexOf(q) !== -1;
    });
    if (includeDia) {
      filtered = filtered.slice().sort(function (a, b) {
        var dir = usoSort.dir;
        if (usoSort.key === 'email') return String(a.user_email || '').localeCompare(String(b.user_email || '')) * dir;
        if (usoSort.key === 'acessos') return ((Number(a.total_acessos) || 0) - (Number(b.total_acessos) || 0)) * dir || ((Number(b.ultimo_acesso_ms) || 0) - (Number(a.ultimo_acesso_ms) || 0));
        if (usoSort.key === 'ultimo') return ((Number(a.ultimo_acesso_ms) || 0) - (Number(b.ultimo_acesso_ms) || 0)) * dir;
        return (String(a.data || '').localeCompare(String(b.data || '')) * dir) || (((Number(b.ultimo_acesso_ms) || 0) - (Number(a.ultimo_acesso_ms) || 0)));
      });
    }
    return filtered;
  }

  function renderUsoCalendar(baseRows) {
    var wrap = $('ga-uso-cal-wrap');
    var note = $('ga-uso-cal-note');
    var grid = $('ga-uso-cal-grid');
    var sumEl = $('ga-uso-cal-summary');
    var clearBtn = $('ga-uso-cal-clear');
    if (!wrap || !grid) return;

    var anos = getUsoFilterValues('ga-uso-ano');
    var meses = getUsoFilterValues('ga-uso-mes');
    if (anos.length !== 1 || meses.length !== 1) {
      wrap.hidden = true;
      if (note) note.hidden = false;
      return;
    }
    wrap.hidden = false;
    if (note) note.hidden = true;

    var y = parseInt(anos[0], 10);
    var m = parseInt(meses[0], 10);
    var ymPrefix = anos[0] + '-' + String(m).padStart(2, '0') + '-';
    var daysInMonth = new Date(y, m, 0).getDate();
    var firstWd = new Date(y, m - 1, 1).getDay();

    var byDay = {};
    var totalAcessosMes = 0;
    var activeDays = 0;
    var maxUsers = 0;
    baseRows.forEach(function (r) {
      if (!r.data || r.data.indexOf(ymPrefix) !== 0) return;
      var d = parseInt(r.dia || r.data.slice(8, 10), 10);
      if (!d || d < 1 || d > daysInMonth) return;
      if (!byDay[d]) byDay[d] = { emails: Object.create(null), usersCount: 0, acessos: 0 };
      if (!byDay[d].emails[r.user_email]) {
        byDay[d].emails[r.user_email] = true;
        byDay[d].usersCount += 1;
      }
      var ac = Number(r.total_acessos) || 0;
      byDay[d].acessos += ac;
      totalAcessosMes += ac;
    });
    Object.keys(byDay).forEach(function (k) {
      activeDays += 1;
      if (byDay[k].usersCount > maxUsers) maxUsers = byDay[k].usersCount;
    });

    var diasSel = getUsoFilterValues('ga-uso-dia');
    if (clearBtn) clearBtn.hidden = diasSel.length === 0;
    if (sumEl) {
      sumEl.innerHTML = '<b>' + esc((MES_NOMES_PT[m] || '') + ' ' + anos[0]) + '</b> · ' +
        activeDays + ' dia(s) com acesso · ' + totalAcessosMes + ' acesso(s)';
    }

    var nowBr = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Sao_Paulo' }));
    var todayD = (nowBr.getFullYear() === y && (nowBr.getMonth() + 1) === m) ? nowBr.getDate() : -1;

    var html = [];
    for (var pad = 0; pad < firstWd; pad++) {
      html.push('<div class="ga-cal-pad" aria-hidden="true"></div>');
    }
    for (var d = 1; d <= daysInMonth; d++) {
      var dd = String(d).padStart(2, '0');
      var info = byDay[d] || null;
      var uCnt = info ? info.usersCount : 0;
      var aCnt = info ? info.acessos : 0;
      var sel = diasSel.indexOf(dd) !== -1;
      var tier = uCnt === 0 ? '' : ((maxUsers >= 2 && uCnt >= Math.ceil(maxUsers * 0.6)) ? ' is-high' : ' is-hit');
      var todayCls = (d === todayD) ? ' is-today' : '';
      var dtStr = dd + '/' + String(m).padStart(2, '0') + '/' + anos[0];
      var tip = uCnt > 0
        ? (dtStr + ': ' + uCnt + ' usuário(s), ' + aCnt + ' acesso(s) — clique para filtrar')
        : (dtStr + ': sem acessos registrados');
      var valHtml = uCnt > 0
        ? '<span class="cd-v"><span class="cd-v-full">' + uCnt + ' usu.</span><span class="cd-v-short">' + uCnt + 'u</span></span>'
        : '';
      html.push(
        '<button type="button" class="ga-cal-day' + tier + todayCls + '" data-cal-dia="' + dd + '" aria-pressed="' + String(sel) + '" title="' + esc(tip) + '" aria-label="' + esc(tip) + '">' +
          '<span class="cd-n">' + d + '</span>' + valHtml +
        '</button>'
      );
    }
    grid.innerHTML = html.join('');
  }

  function renderUsoSortHeaders() {
    var thead = $('ga-uso-thead');
    if (!thead) return;
    thead.querySelectorAll('th[data-uso-sort]').forEach(function (th) {
      var k = th.getAttribute('data-uso-sort');
      th.setAttribute('aria-sort', k === usoSort.key ? (usoSort.dir === 1 ? 'ascending' : 'descending') : 'none');
    });
  }

  function renderUso() {
    var data = state.uso;
    if (!data) return;
    var q = ($('ga-uso-filter') ? $('ga-uso-filter').value : '').trim().toLowerCase();
    var pfs = getUsoFilterValues('ga-uso-perfil');
    var diasSel = getUsoFilterValues('ga-uso-dia');
    var baseRows = getFilteredUsoRows(false);
    renderUsoCalendar(baseRows);
    renderUsoSortHeaders();

    var rows = getFilteredUsoRows(true);
    if ($('ga-uso-users-title')) $('ga-uso-users-title').textContent = 'Acessos no portal (' + rows.length + ')';
    renderPagedTable('ga-uso-users-body', rows, function (u) {
      var perfilBadge = u.role
        ? roleBadge(u.role) + (u.perfil === 'simulacao' ? ' <span class="ga-pill ga-pill-off">Simulação</span>' : '')
        : '<span class="ga-pill ga-pill-on">DISTRIBUIDOR</span>';
      var distTxt = (u.dist_nomes && u.dist_nomes.length)
        ? u.dist_nomes.map(function (n, idx) {
            var id = (u.dist_ids || [])[idx];
            return '<b>' + esc(n) + '</b>' + (id ? ' <span class="ga-muted">(ID ' + esc(id) + ')</span>' : '');
          }).join(', ')
        : '<span class="ga-muted">Visão global</span>';
      return '<tr>' +
        '<td style="white-space:nowrap;font-variant-numeric:tabular-nums">' + esc(fmtIsoBr(u.data)) + '</td>' +
        '<td><b>' + esc(u.user_email) + '</b></td>' +
        '<td>' + perfilBadge + '</td>' +
        '<td>' + distTxt + '</td>' +
        '<td style="white-space:nowrap;font-variant-numeric:tabular-nums">' + fmtMs(u.ultimo_acesso_ms) + '</td>' +
        '<td class="num ga-mono"><b>' + esc(u.total_acessos) + '</b></td>' +
      '</tr>';
    }, '<tr><td colspan="6" class="ga-empty">Nenhum acesso registrado para os filtros selecionados.</td></tr>', q + '|' + pfs.join(',') + '|' + diasSel.join(',') + '|' + usoSort.key + ':' + usoSort.dir, renderUso);
  }

  function loadUso() {
    var ano = getUsoFilterValues('ga-uso-ano').join(',');
    var mes = getUsoFilterValues('ga-uso-mes').join(',');
    var btn = $('ga-uso-refresh');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="amb-spinner"></span> Atualizando...'; }
    if ($('ga-uso-users-body')) $('ga-uso-users-body').innerHTML = '<tr><td colspan="6" class="ga-empty">Carregando…</td></tr>';
    return api('GET', '/api/admin/uso-portal?ano=' + encodeURIComponent(ano) + '&mes=' + encodeURIComponent(mes)).then(function (j) {
      state.uso = j;
      state.usoLoaded = true;
      renderUso();
    }).catch(function (e) {
      if ($('ga-uso-users-body')) $('ga-uso-users-body').innerHTML = '<tr><td colspan="6" class="ga-empty">' + esc(e.message) + '</td></tr>';
    }).finally(function () {
      if (btn) { btn.disabled = false; btn.textContent = 'Atualizar'; }
    });
  }

  function onUsoExport() {
    var go = state.usoLoaded ? Promise.resolve() : loadUso();
    go.then(function () {
      var list = getFilteredUsoRows(true);
      var rows = list.map(function (u) {
        var dt = u.ultimo_acesso_ms ? new Date(parseInt(u.ultimo_acesso_ms, 10)).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' }) : '';
        return [
          fmtIsoBr(u.data),
          u.user_email,
          u.role || u.perfil || 'distribuidor',
          (u.dist_nomes || []).join(', '),
          (u.dist_ids || []).join(', '),
          dt,
          String(u.total_acessos || 0)
        ];
      });
      downloadCsv('uso_portal_distribuidores.csv', [
        ['DATA', 'EMAIL', 'PERFIL', 'DISTRIBUIDORES', 'IDS_DISTRIBUIDOR', 'ULTIMO_ACESSO_BRASILIA', 'ACESSOS_NO_DIA']
      ].concat(rows));
    });
  }

  function showPanel(name) {
    document.querySelectorAll('.ga-tab').forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-panel') === name); });
    if ($('panel-admins')) $('panel-admins').style.display = name === 'admins' ? 'block' : 'none';
    if ($('panel-distribuidores')) $('panel-distribuidores').style.display = name === 'distribuidores' ? 'block' : 'none';
    if ($('panel-portal-dists')) $('panel-portal-dists').style.display = name === 'portal-dists' ? 'block' : 'none';
    if ($('panel-uso')) $('panel-uso').style.display = name === 'uso' ? 'block' : 'none';
    if ($('panel-historico')) $('panel-historico').style.display = name === 'historico' ? 'block' : 'none';
    if (name === 'historico' && !state.auditLoaded) loadAudit();
    if (name === 'distribuidores' && !state.distsLoaded) loadDists();
    if (name === 'portal-dists' && !state.portalDistsLoaded) loadPortalDists();
    if (name === 'uso' && !state.usoLoaded) loadUso();
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.ga-tab').forEach(function (b) {
      b.addEventListener('click', function () { showPanel(b.getAttribute('data-panel')); });
    });
    document.querySelectorAll('[data-goto-panel]').forEach(function (b) {
      b.addEventListener('click', function () { showPanel(b.getAttribute('data-goto-panel')); });
    });
    if ($('ga-show-revoked')) $('ga-show-revoked').addEventListener('change', renderAdmins);
    $('ga-add-form').addEventListener('submit', onAddSubmit);
    $('ga-admins-body').addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-act]');
      if (btn && !btn.disabled) onAction(btn.getAttribute('data-act'), btn.getAttribute('data-email'));
    });
    attachUserSuggest($('ga-email'), { filter: function (u) { return EMAIL_RE.test(u.email); } });
    attachUserSuggest($('ga-dist-email'), { onPick: function () { renderPicker(); $('ga-dist-search').focus(); } });
    $('ga-dist-form').addEventListener('submit', onDistSubmit);
    $('ga-dist-filter').addEventListener('input', renderDists);
    if ($('ga-dist-show-revoked')) $('ga-dist-show-revoked').addEventListener('change', renderDists);
    $('ga-dist-body').addEventListener('change', onRevokeToggle);
    $('ga-dist-sel-all').addEventListener('change', onRevokeAll);
    $('ga-revoke-clear').addEventListener('click', onRevokeClear);
    $('ga-revoke-submit').addEventListener('click', onRevokeSubmit);
    $('ga-dist-body').addEventListener('click', function (e) {
      var legacy = e.target.closest('button[data-legacy-revoke]');
      if (legacy) {
        var oldEmail = legacy.getAttribute('data-email'), oldCnpj = legacy.getAttribute('data-legacy-revoke');
        confirmDialog({ title: 'Revogar vínculo legado', body: '<p>Revogar acesso de <b>' + esc(oldEmail) + '</b> ao CNPJ ' + esc(fmtCnpj(oldCnpj)) + '?</p>', ok: 'Revogar', danger: true,
          onOk: function () { return api('DELETE', '/api/admin/distribuidores-acessos/' + encodeURIComponent(oldEmail), {cnpj: oldCnpj}).then(function (j) { return afterDistChange(j, 'Acesso revogado'); }); }
        }); return;
      }
      var btn = e.target.closest('button[data-id-action]');
      if (!btn || btn.disabled) return;
      var email = btn.getAttribute('data-email'), id = btn.getAttribute('data-id'), act = btn.getAttribute('data-id-action');
      confirmDialog({ title: act === 'revoke' ? 'Revogar acesso por ID' : 'Reativar acesso por ID',
        body: '<p>' + (act === 'revoke' ? 'Revogar' : 'Reativar') + ' acesso de <b>' + esc(email) + '</b> ao ID <b>' + esc(id) + '</b>?</p>',
        ok: act === 'revoke' ? 'Revogar' : 'Reativar', danger: act === 'revoke',
        onOk: function () { return (act === 'revoke' ? api('DELETE', '/api/admin/distribuidores-ids/' + encodeURIComponent(email) + '/' + id) : api('POST', '/api/admin/distribuidores-ids', {email: email, ids: [id]})).then(function (j) { return afterDistChange(j, 'Acesso atualizado'); }); }
      });
    });
    $('ga-dist-email').addEventListener('input', renderPicker);
    $('ga-dist-search').addEventListener('input', renderPicker);
    // Enter na busca não envia o formulário
    $('ga-dist-search').addEventListener('keydown', function (e) { if (e.key === 'Enter') e.preventDefault(); });
    $('ga-dist-list').addEventListener('change', onPickerToggle);
    $('ga-dist-all').addEventListener('click', onPickerAll);
    $('ga-dist-none').addEventListener('click', function () { clearChips(); renderPicker(); });
    $('ga-dist-chips').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-chip]');
      if (b) { chips.splice(parseInt(b.getAttribute('data-chip'), 10), 1); renderPicker(); $('ga-dist-search').focus(); }
    });
    if ($('ga-bulk')) $('ga-bulk').addEventListener('toggle', function () { if (this.open) loadCatalog(); });
    if ($('ga-bulk-validate')) $('ga-bulk-validate').addEventListener('click', onBulkValidate);
    if ($('ga-bulk-commit')) $('ga-bulk-commit').addEventListener('click', onBulkCommit);
    if ($('ga-bulk-clear')) $('ga-bulk-clear').addEventListener('click', function () { bulkPlan = null; $('ga-bulk-text').value = ''; $('ga-bulk-result').hidden = true; $('ga-bulk-text').focus(); });
    if ($('ga-bulk-template')) $('ga-bulk-template').addEventListener('click', onBulkTemplate);
    if ($('ga-export-dist-reference')) $('ga-export-dist-reference').addEventListener('click', onExportDistributorReference);
    if ($('ga-bulk-export')) $('ga-bulk-export').addEventListener('click', onBulkExport);
    if ($('ga-bulk-file')) $('ga-bulk-file').addEventListener('change', onBulkFile);
    if ($('ga-bulk-text')) $('ga-bulk-text').addEventListener('input', function () { if (bulkPlan) { bulkPlan = null; $('ga-bulk-result').hidden = true; } });
    if ($('ga-audit-filter')) $('ga-audit-filter').addEventListener('input', renderAudit);
    if ($('ga-audit-refresh')) $('ga-audit-refresh').addEventListener('click', loadAudit);

    // Eventos: Distribuidores no portal
    if ($('ga-pd-form')) $('ga-pd-form').addEventListener('submit', onPortalDistSubmit);
    if ($('ga-pd-search')) {
      $('ga-pd-search').addEventListener('input', renderPortalCandidates);
      $('ga-pd-search').addEventListener('keydown', function (e) { if (e.key === 'Enter') e.preventDefault(); });
    }
    if ($('ga-pd-cand-list')) {
      $('ga-pd-cand-list').addEventListener('change', function (e) {
        var cb = e.target;
        if (!cb || cb.type !== 'checkbox') return;
        var v = String(cb.value);
        var idx = state.pdSelected.indexOf(v);
        if (cb.checked && idx === -1) state.pdSelected.push(v);
        else if (!cb.checked && idx !== -1) state.pdSelected.splice(idx, 1);
      });
    }
    if ($('ga-pd-all')) {
      $('ga-pd-all').addEventListener('click', function () {
        Array.prototype.forEach.call($('ga-pd-cand-list').querySelectorAll('input[type="checkbox"]'), function (cb) {
          cb.checked = true;
          if (state.pdSelected.indexOf(String(cb.value)) === -1) state.pdSelected.push(String(cb.value));
        });
      });
    }
    if ($('ga-pd-none')) {
      $('ga-pd-none').addEventListener('click', function () {
        state.pdSelected = [];
        renderPortalCandidates();
      });
    }
    if ($('ga-pd-filter')) $('ga-pd-filter').addEventListener('input', renderPortalDists);
    if ($('ga-pd-status')) $('ga-pd-status').addEventListener('change', renderPortalDists);
    if ($('ga-pd-export')) $('ga-pd-export').addEventListener('click', onPortalDistExport);
    if ($('ga-pd-body')) {
      $('ga-pd-body').addEventListener('click', function (e) {
        var btn = e.target.closest('button[data-pd-act]');
        if (btn && !btn.disabled) onPortalDistAction(btn.getAttribute('data-pd-act'), btn.getAttribute('data-id'));
      });
    }

    // Eventos: Uso do portal
    initUsoSelects();
    if ($('ga-uso-filter')) $('ga-uso-filter').addEventListener('input', renderUso);
    if ($('ga-uso-perfil')) $('ga-uso-perfil').addEventListener('change', function (e) { if (e.target === $('ga-uso-perfil')) renderUso(); });
    if ($('ga-uso-dia')) $('ga-uso-dia').addEventListener('change', function (e) { if (e.target === $('ga-uso-dia')) renderUso(); });
    if ($('ga-uso-ano')) $('ga-uso-ano').addEventListener('change', function (e) { if (e.target === $('ga-uso-ano')) { populateUsoDias(); loadUso(); } });
    if ($('ga-uso-mes')) $('ga-uso-mes').addEventListener('change', function (e) { if (e.target === $('ga-uso-mes')) { populateUsoDias(); loadUso(); } });
    if ($('ga-uso-cal-grid')) {
      $('ga-uso-cal-grid').addEventListener('click', function (e) {
        var btn = e.target.closest('button[data-cal-dia]');
        if (!btn || !$('ga-uso-dia') || !$('ga-uso-dia').setSelected) return;
        var dd = btn.getAttribute('data-cal-dia');
        var cur = getUsoFilterValues('ga-uso-dia');
        var idx = cur.indexOf(dd);
        if (idx === -1) cur.push(dd);
        else cur.splice(idx, 1);
        cur.sort();
        $('ga-uso-dia').setSelected(cur);
        renderUso();
      });
    }
    if ($('ga-uso-cal-clear')) {
      $('ga-uso-cal-clear').addEventListener('click', function () {
        if ($('ga-uso-dia') && $('ga-uso-dia').clear) $('ga-uso-dia').clear();
        renderUso();
      });
    }
    if ($('ga-uso-thead')) {
      $('ga-uso-thead').addEventListener('click', function (e) {
        var btn = e.target.closest('th[data-uso-sort] .th-sort');
        if (!btn) return;
        var k = btn.closest('th').getAttribute('data-uso-sort');
        if (usoSort.key === k) usoSort.dir = -usoSort.dir;
        else { usoSort.key = k; usoSort.dir = k === 'email' ? 1 : -1; }
        renderUso();
      });
    }
    if ($('ga-uso-refresh')) $('ga-uso-refresh').addEventListener('click', loadUso);
    if ($('ga-uso-export')) $('ga-uso-export').addEventListener('click', onUsoExport);

    var isUsoPage = location.pathname.indexOf('uso') !== -1 || (new URLSearchParams(location.search).get('modo') === 'uso');
    state.isUsoPage = isUsoPage;
    if (isUsoPage) {
      document.title = 'Uso do Portal · Portal Distribuidores';
      if ($('ga-amb-view')) $('ga-amb-view').textContent = 'Uso do Portal';
      if ($('ga-page-title')) $('ga-page-title').textContent = 'Uso do Portal';
      if ($('ga-page-sub')) $('ga-page-sub').textContent = 'Histórico de quem acessou o portal no período selecionado.';
      if ($('ga-tabs')) $('ga-tabs').style.display = 'none';
      if ($('ga-readonly')) $('ga-readonly').style.display = 'none';
      showPanel('uso');
    }
    loadAdmins();
  });
})();
