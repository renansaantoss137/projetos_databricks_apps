/* Portal Distribuidores v2 — helper único de formatação pt-BR.
   Usado por cards, gráficos, tooltips e tabelas. Apenas apresentação: não altera valores. */
(function (global) {
  'use strict';
  var LOCALE = 'pt-BR';
  var nf = {
    int: new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 }),
    dec1: new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
    money: new Intl.NumberFormat(LOCALE, { style: 'currency', currency: 'BRL', minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    money0: new Intl.NumberFormat(LOCALE, { style: 'currency', currency: 'BRL', minimumFractionDigits: 0, maximumFractionDigits: 0 })
  };
  var MONTHS_SHORT = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
  var MONTHS_LONG = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
  var WEEKDAYS_SHORT = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
  var WEEKDAYS_LONG = ['Domingo', 'Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado'];

  function n(v) { var x = typeof v === 'number' ? v : parseFloat(v); return isFinite(x) ? x : 0; }
  function nbsp(s) { return String(s).replace(/\u00a0/g, ' '); }

  /* Número compacto: 950 · 198,7 mil · 1,2 mi · 3,4 bi */
  function compact(v) {
    var x = n(v), a = Math.abs(x), s = x < 0 ? '-' : '';
    if (a >= 1e9) return s + nf.dec1.format(a / 1e9) + ' bi';
    if (a >= 1e6) return s + nf.dec1.format(a / 1e6) + ' mi';
    if (a >= 1e3) return s + nf.dec1.format(a / 1e3) + ' mil';
    return s + nf.int.format(Math.round(a));
  }
  /* Moeda compacta: R$ 950 · R$ 198,7 mil · R$ 1,2 mi */
  function moneyCompact(v) {
    var x = n(v), s = x < 0 ? '-' : '';
    return s + 'R$ ' + compact(Math.abs(x));
  }
  function money(v) { return nbsp(nf.money.format(n(v))); }
  function money0(v) { return nbsp(nf.money0.format(n(v))); }
  function int(v) { return nf.int.format(Math.round(n(v))); }
  function pct(v, digits) {
    var d = typeof digits === 'number' ? digits : 0;
    return new Intl.NumberFormat(LOCALE, { minimumFractionDigits: d, maximumFractionDigits: d }).format(n(v)) + '%';
  }
  function signedPct(v, digits) {
    var x = n(v);
    return (x > 0 ? '+' : x < 0 ? '−' : '') + pct(Math.abs(x), digits);
  }
  /* Valor de métrica conforme modo Valor/Volume */
  function metric(v, isVolume, unit) {
    return isVolume ? compact(v) + (unit ? ' ' + unit : '') : moneyCompact(v);
  }
  function dateTime(d) {
    if (!(d instanceof Date) || isNaN(d)) return '';
    var p = function (x) { return String(x).padStart(2, '0'); };
    return p(d.getDate()) + '/' + p(d.getMonth() + 1) + '/' + d.getFullYear() + ' às ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }
  /* "23/10/2026 às 10:23" -> Date */
  function parseBr(s) {
    var m = String(s || '').match(/(\d{2})\/(\d{2})\/(\d{4})\D+(\d{2}):(\d{2})/);
    if (!m) return null;
    return new Date(+m[3], +m[2] - 1, +m[1], +m[4], +m[5]);
  }
  function relative(d) {
    if (!d) return '';
    var mins = Math.round((Date.now() - d.getTime()) / 60000);
    if (mins < 1) return 'agora';
    if (mins < 60) return 'há ' + mins + ' min';
    var h = Math.floor(mins / 60);
    if (h < 24) return 'há ' + h + ' h';
    var dd = Math.floor(h / 24);
    return 'há ' + dd + (dd === 1 ? ' dia' : ' dias');
  }
  function cnpj(c) {
    var d = String(c || '').replace(/\D/g, '').padStart(14, '0');
    return d.length === 14 ? d.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5') : c;
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  global.Fmt = {
    compact: compact, moneyCompact: moneyCompact, money: money, money0: money0, int: int,
    pct: pct, signedPct: signedPct, metric: metric, dateTime: dateTime, parseBr: parseBr,
    relative: relative, cnpj: cnpj, esc: esc,
    MONTHS_SHORT: MONTHS_SHORT, MONTHS_LONG: MONTHS_LONG, WEEKDAYS_SHORT: WEEKDAYS_SHORT, WEEKDAYS_LONG: WEEKDAYS_LONG
  };
})(window);
