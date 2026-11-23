(function () {
  'use strict';
  const copy = {
    pt: ['Não foi possível carregar parte dos dados. Confira a conexão e tente novamente.', 'Tentar novamente'],
    en: ['Some data could not be loaded. Check your connection and try again.', 'Try again'],
    es: ['No se pudieron cargar algunos datos. Compruebe la conexión e inténtelo de nuevo.', 'Reintentar']
  };
  function showError() {
    if (document.getElementById('analyticsLoadError')) return;
    const host = document.querySelector('.fr-content, .conteudo, .layout');
    if (!host) return;
    const message = copy[(document.documentElement.lang || 'pt').slice(0,2)] || copy.pt;
    const box = document.createElement('div');
    box.id = 'analyticsLoadError'; box.className = 'ui-load-error'; box.setAttribute('role', 'alert');
    box.append(document.createTextNode(message[0]));
    const retry = document.createElement('button');
    retry.type = 'button'; retry.textContent = message[1];
    retry.addEventListener('click', () => window.location.reload());
    box.append(retry); host.prepend(box);
  }
  // Preserve request/response contracts; surface failures instead of console-only feedback.
  const originalFetch = window.fetch;
  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : input.url;
    const dataRequest = /\/api\/(performance|commercial|governance|orders|reports|filters)\//.test(url || '');
    try {
      const response = await originalFetch.call(this, input, init);
      if (dataRequest && !response.ok) {
        console.error('Falha ao carregar dados:', String(url).split('?')[0], 'HTTP', response.status);
        showError();
      }
      return response;
    } catch (error) {
      if (dataRequest && error.name !== 'AbortError') {
        console.error('Falha de conexão ao carregar dados:', String(url).split('?')[0], error);
        showError();
      }
      throw error;
    }
  };
  function chartDefaults() {
    if (!window.Chart) return;
    const css = getComputedStyle(document.documentElement);
    Chart.defaults.color = css.getPropertyValue('--text-secondary').trim();
    Chart.defaults.font.family = 'Inter, Segoe UI, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.plugins.tooltip.backgroundColor = css.getPropertyValue('--gr-tip-bg').trim();
    Chart.defaults.plugins.tooltip.titleColor = css.getPropertyValue('--gr-tip-titulo').trim();
    Chart.defaults.plugins.tooltip.bodyColor = css.getPropertyValue('--gr-tip-valor').trim();
  }
  chartDefaults();
  new MutationObserver(chartDefaults).observe(document.documentElement, {attributes:true, attributeFilter:['data-theme']});
  document.addEventListener('click', function (event) {
    const button = event.target.closest('.kpi-help');
    document.querySelectorAll('.kpi-help[aria-expanded="true"]').forEach(item => {
      if (item !== button) item.setAttribute('aria-expanded', 'false');
    });
    if (button) button.setAttribute('aria-expanded', String(button.getAttribute('aria-expanded') !== 'true'));
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') document.querySelectorAll('.kpi-help[aria-expanded="true"]').forEach(item => item.setAttribute('aria-expanded', 'false'));
  });
  document.addEventListener('DOMContentLoaded', function () {
    const header = document.querySelector('.dna-header');
    const summary = document.getElementById('fpResumo');
    const right = header && header.querySelector('.header-right');
    if (header && summary && right && !document.documentElement.classList.contains('is-embedded')) {
      header.insertBefore(summary, right);
      header.classList.add('has-filter-summary');
      const toggle = document.createElement('button');
      toggle.type = 'button'; toggle.className = 'header-filter-toggle';
      toggle.setAttribute('aria-controls', summary.id);
      toggle.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
      function setCollapsed(collapsed) {
        header.classList.toggle('header-collapsed', collapsed);
        toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.setAttribute('aria-label', collapsed ? 'Mostrar filtros aplicados' : 'Recolher filtros aplicados');
        toggle.title = toggle.getAttribute('aria-label');
        try { sessionStorage.setItem('compras_header_collapsed', collapsed ? '1' : '0'); } catch (_) {}
      }
      let collapsed = false;
      try { collapsed = sessionStorage.getItem('compras_header_collapsed') === '1'; } catch (_) {}
      setCollapsed(collapsed);
      toggle.addEventListener('click', () => setCollapsed(!header.classList.contains('header-collapsed')));
      right.insertBefore(toggle, right.firstChild);
    }
  });
})();
