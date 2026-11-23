/**
 * DNA DE VENDAS | Grupo Bimbo Brasil
 * Utilitários de Formatação Regional (R5, R6)
 * Suporte a pt-BR, en-US e es-ES via Intl nativo
 */

(function () {
  'use strict';

  function getLocale() {
    const lang = (localStorage.getItem('portalCompras_lang') || document.documentElement.lang || 'pt').slice(0, 2);
    if (lang === 'en') return 'en-US';
    if (lang === 'es') return 'es-ES';
    return 'pt-BR';
  }

  function getCurrencySymbol() {
    const lang = (localStorage.getItem('portalCompras_lang') || document.documentElement.lang || 'pt').slice(0, 2);
    if (lang === 'en') return '$ ';
    if (lang === 'es') return '$ ';
    return 'R$ ';
  }

  function getUnitMi() {
    const lang = (localStorage.getItem('portalCompras_lang') || document.documentElement.lang || 'pt').slice(0, 2);
    if (lang === 'en') return 'M';
    if (lang === 'es') return 'M';
    return 'Mi';
  }

  function fmtNumber(val, decimals = 1) {
    if (val === null || val === undefined || isNaN(val)) return '—';
    const loc = getLocale();
    return new Intl.NumberFormat(loc, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    }).format(val);
  }

  function fmtInteger(val) {
    if (val === null || val === undefined || isNaN(val)) return '—';
    const loc = getLocale();
    return new Intl.NumberFormat(loc, {
      maximumFractionDigits: 0
    }).format(Math.round(val));
  }

  function fmtCurrency(val, isMillions = false, isVolume = false) {
    if (val === null || val === undefined || isNaN(val)) return '—';
    const loc = getLocale();
    const prefix = isVolume ? '' : getCurrencySymbol();
    const suffix = isMillions ? (isVolume ? ' ' + getUnitMi() + ' un' : ' ' + getUnitMi()) : (isVolume ? ' un' : '');

    const formatted = new Intl.NumberFormat(loc, {
      minimumFractionDigits: isMillions ? 1 : 2,
      maximumFractionDigits: isMillions ? 2 : 2
    }).format(val);

    return `${prefix}${formatted}${suffix}`;
  }

  function fmtPercent(val, showSign = true) {
    if (val === null || val === undefined || isNaN(val)) return '—';
    const loc = getLocale();
    const formatted = new Intl.NumberFormat(loc, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1
    }).format(Math.abs(val));

    if (val > 0 && showSign) return `+${formatted}%`;
    if (val < 0) return `-${formatted}%`;
    return `${formatted}%`;
  }

  window.DNAFormat = {
    getLocale,
    fmtNumber,
    fmtInteger,
    fmtCurrency,
    fmtPercent
  };
})();
