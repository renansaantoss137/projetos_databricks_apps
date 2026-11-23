(function () {
  'use strict';

  // 1. Detecção de modo embutido (Seamless Continuous Frame)
  if (window.self !== window.top) {
    document.documentElement.classList.add('is-embedded');
    if (document.body) document.body.classList.add('is-embedded');
    else document.addEventListener('DOMContentLoaded', () => document.body.classList.add('is-embedded'));

    // Notificar janela mestre sobre alterações de dimensão
    let lastPostedHeight = 0;
    function postSize() {
      try {
        const doc = document.documentElement;
        const body = document.body;
        // Mede só o conteúdo (body). documentElement.scrollHeight nunca é menor que a altura
        // atual do iframe, então o frame só crescia e deixava espaço vazio ao encolher.
        const h = body ? Math.ceil(Math.max(body.scrollHeight, body.getBoundingClientRect().height)) : 0;
        if (h > 150 && Math.abs(h - lastPostedHeight) > 3) {
          lastPostedHeight = h;
          window.parent.postMessage({ type: 'SEAMLESS_FRAME_RESIZE', height: h }, '*');
        }
      } catch (_) { }
    }
    window.addEventListener('load', postSize);
    window.addEventListener('resize', postSize);
    if (window.ResizeObserver) {
      document.addEventListener('DOMContentLoaded', () => {
        new ResizeObserver(postSize).observe(document.body);
      });
    }
    return; // Em modo embutido, a sidebar e header mestres cuidam de tudo
  }

  // 3. Inicialização da navegação na página principal
  function init() {
    const side = document.querySelector('.sp-sidebar');
    if (!side) return;

    // Garantir que o módulo Gastos (Spend) permaneça oculto da navegação
    side.querySelectorAll('a[href*="spend"]').forEach(link => link.remove());
    document.querySelectorAll('.dna-mobile-nav a[href*="spend"]').forEach(link => link.remove());

    const names = {
      'index.html': 'Início', '#sec-inicio': 'Início',
      'performance.html': 'Performance de Compras', '#sec-performance': 'Performance de Compras',
      'ordens.html': 'Gestão de Ordens', '#sec-ordens': 'Gestão de Ordens',
      'comercial.html': 'Condições Comerciais', '#sec-comercial': 'Condições Comerciais',
      'governanca.html': 'Governança', '#sec-governanca': 'Governança',
      'relatorios.html': 'Relatórios', '#sec-relatorios': 'Relatórios',
      'guia.html': 'Guia do Usuário', '#sec-guia': 'Guia do Usuário',
      'cadastros.html': 'Cadastros de planilhas', '#sec-cadastros': 'Cadastros de planilhas'
    };

    side.querySelectorAll('a.sp-nav-item').forEach(link => {
      const href = link.getAttribute('href');
      const full = names[href] || names[href.replace('#sec-', '') + '.html'];
      if (!full) return;
      if (!link.querySelector('.nav-long')) {
        const text = document.createElement('span');
        text.className = 'nav-long';
        text.textContent = full;
        link.append(text);
      }
    });

    // Botão de expandir menu
    if (!side.querySelector('.nav-expand')) {
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'nav-expand';
      toggle.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg><span class="nav-expand-label">Expandir menu</span>';
      let expanded = false;
      try { expanded = localStorage.getItem('compras_nav_expanded') === '1'; } catch (_) { }
      function update() {
        document.body.classList.toggle('nav-expanded', expanded);
        toggle.setAttribute('aria-expanded', String(expanded));
        toggle.setAttribute('aria-label', expanded ? 'Recolher menu' : 'Expandir menu');
        toggle.title = toggle.getAttribute('aria-label');
        const lbl = toggle.querySelector('.nav-expand-label');
        if (lbl) lbl.textContent = toggle.title;
      }
      toggle.addEventListener('click', () => {
        expanded = !expanded;
        try { localStorage.setItem('compras_nav_expanded', expanded ? '1' : '0'); } catch (_) { }
        update();
      });
      side.prepend(toggle);
      update();
    }

    // Seção Apoio
    if (!side.querySelector('.nav-support-label')) {
      const support = document.createElement('div');
      support.className = 'nav-support-label';
      support.textContent = 'Apoio';
      side.append(support);
    }

    function addSupportLink(href, shortLabel, fullLabel, icon, isAnchor) {
      if (side.querySelector(`a[href="${href}"]`)) return;
      const a = document.createElement('a');
      a.href = href;
      a.className = 'sp-nav-item nav-support-item';
      a.title = fullLabel;
      a.innerHTML = icon + '<span>' + shortLabel + '</span><span class="nav-long">' + fullLabel + '</span>';
      side.append(a);

      const sheet = document.getElementById('dnaMoreSheet');
      if (sheet && !sheet.querySelector(`a[href="${href}"]`)) {
        const mobile = a.cloneNode(true);
        mobile.className = 'dna-more-item';
        mobile.querySelector('.nav-long')?.remove();
        sheet.append(mobile);
      }
      return a;
    }

    const continuous = !!document.getElementById('continuousContainer');
    const cadastroHref = continuous ? '#sec-cadastros' : 'cadastros.html';
    const guideHref = 'guia.html';
    const cadastroLink = addSupportLink(cadastroHref, 'Cadastros', 'Cadastros de planilhas', '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 9v12"/></svg>', true) || side.querySelector(`a[href="${cadastroHref}"]`);
    if (cadastroLink) cadastroLink.hidden = true;
    const mobileCadastro = document.querySelector(`#dnaMoreSheet a[href="${cadastroHref}"]`);
    if (mobileCadastro) mobileCadastro.hidden = true;
    addSupportLink(guideHref, 'Guia', 'Guia do Usuário', '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 4h13a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3z"/><path d="M4 17a3 3 0 0 1 3-3h13"/></svg>', false);
    fetch('/api/auth/me', { cache: 'no-store' }).then(response => {
      if (!response.ok) throw new Error('Permissão indisponível');
      return response.json();
    }).then(user => {
      const allowed = user && user.can_access_cadastros === true;
      if (cadastroLink) cadastroLink.hidden = !allowed;
      window.dispatchEvent(new CustomEvent('cadastrosAccessChanged', { detail: { allowed: allowed } }));
      if (window.refreshMobileNavigation) window.refreshMobileNavigation();
    }).catch(() => {
      window.dispatchEvent(new CustomEvent('cadastrosAccessChanged', { detail: { allowed: false } }));
    });

    // Suporte a smooth scroll para todos os links âncora (#sec-*)
    document.addEventListener('click', function (e) {
      const link = e.target.closest('a[href^="#sec-"]');
      if (!link) return;
      const targetId = link.getAttribute('href').substring(1);
      const targetEl = document.getElementById(targetId);
      if (targetEl) {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent('sectionNavigate', { detail: { targetEl, targetId } }));
        if (targetId === 'sec-inicio') window.scrollTo({ top: 0, behavior: 'smooth' });
        else targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        history.replaceState(null, '', '#' + targetId);
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
