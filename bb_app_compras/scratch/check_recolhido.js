const fs = require('fs');
const files = ['performance.html', 'spend.html', 'ordens.html', 'comercial.html', 'governanca.html', 'relatorios.html'];
console.log('Verificacao de estadoInicial e data-filtros:');
files.forEach(f => {
  const c = fs.readFileSync('src/app/' + f, 'utf-8');
  console.log(f, {
    dataFiltrosRecolhido: c.includes('data-filtros="recolhido"'),
    estadoInicialRecolhido: c.includes("estadoInicial: 'recolhido'")
  });
});
const css = fs.readFileSync('src/app/styles.css', 'utf-8');
console.log('CSS ocultando Gastos:', css.includes('a[href="spend.html"]') && css.includes('display: none !important'));
