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
  // 502/503/504 vem do proxy do Databricks Apps (pagina de erro, sem log no app) e sao transitorios:
  // GET de dados e idempotente, entao tenta de novo ate 2x com espera crescente. 500 (erro do app/banco)
  // NAO e repetido: e erro real e mostra o aviso na hora.
  const TRANSIENT = new Set([502, 503, 504]);
  const RETRY_DELAYS = [800, 2500];
  const sleep = ms => new Promise(r => setTimeout(r, ms + Math.floor(Math.random() * 300)));
  // Limite GLOBAL de chamadas de dados simultaneas, compartilhado por todas as abas-iframe (mesma origem).
  // Sem isso o index dispara ~40 GETs juntos: a fila do servidor chega a 22, consultas sobem de <1 s para
  // 10-27 s e o proxy derruba a conexao (ERR_CONNECTION_RESET / HTTP2_PROTOCOL_ERROR / 502) em rajada.
  const MAX_INFLIGHT = 6;
  const gate = (function () {
    const mk = () => ({ active: 0, queue: [] });
    try { const t = window.top; return t.__c360Gate || (t.__c360Gate = mk()); } catch (e) { return window.__c360Gate || (window.__c360Gate = mk()); }
  })();
  // Cada janela controla as proprias vagas: se o iframe recarregar ("Tentar novamente"), devolve tudo.
  const me = { active: 0, dead: false };
  function pump() {
    while (gate.active < MAX_INFLIGHT && gate.queue.length) {
      const e = gate.queue.shift();
      if (e.owner.dead) continue;
      gate.active++; e.owner.active++;
      try { e.resolve(); } catch (err) { /* janela descarregada */ }
    }
  }
  function acquire() {
    if (gate.active < MAX_INFLIGHT && !gate.queue.length) { gate.active++; me.active++; return Promise.resolve(); }
    return new Promise(resolve => { gate.queue.push({ resolve, owner: me }); pump(); });
  }
  function release() {
    if (me.dead) return;
    me.active = Math.max(0, me.active - 1);
    gate.active = Math.max(0, gate.active - 1);
    pump();
  }
  window.addEventListener('pagehide', () => {
    me.dead = true;
    gate.queue = gate.queue.filter(e => e.owner !== me);
    gate.active = Math.max(0, gate.active - me.active);
    me.active = 0;
    pump();
  });
  async function gatedFetch(self, input, init) {
    await acquire();
    try { return await originalFetch.call(self, input, init); } finally { release(); }
  }
  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : input.url;
    const dataRequest = /\/api\/(performance|commercial|governance|orders|reports|filters)\//.test(url || '');
    const method = String((init && init.method) || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
    const retriable = dataRequest && method === 'GET';
    const path = String(url).split('?')[0];
    for (let attempt = 0; ; attempt++) {
      try {
        const response = dataRequest ? await gatedFetch(this, input, init) : await originalFetch.call(this, input, init);
        if (retriable && TRANSIENT.has(response.status) && attempt < RETRY_DELAYS.length) {
          console.warn('Falha transitória, nova tentativa:', path, 'HTTP', response.status, 'tentativa', attempt + 1);
          await sleep(RETRY_DELAYS[attempt]);
          continue;
        }
        if (dataRequest && !response.ok) {
          console.error('Falha ao carregar dados:', path, 'HTTP', response.status,
            'request_id', response.headers.get('X-Request-Id') || '-', 'tentativas', attempt + 1);
          showError();
        }
        return response;
      } catch (error) {
        if (error.name === 'AbortError') throw error;
        if (retriable && attempt < RETRY_DELAYS.length) {
          console.warn('Falha de conexão, nova tentativa:', path, 'tentativa', attempt + 1);
          await sleep(RETRY_DELAYS[attempt]);
          continue;
        }
        if (dataRequest) {
          console.error('Falha de conexão ao carregar dados:', path, error);
          showError();
        }
        throw error;
      }
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
