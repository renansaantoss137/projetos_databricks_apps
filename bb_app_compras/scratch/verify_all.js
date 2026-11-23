const fs = require('fs');

const pages = [
  'src/app/index.html',
  'src/app/performance.html',
  'src/app/spend.html',
  'src/app/ordens.html',
  'src/app/comercial.html',
  'src/app/governanca.html',
  'src/app/relatorios.html',
  'src/app/guia.html',
  'src/app/cadastros.html'
];

console.log('--- RELATÓRIO DE CONFORMIDADE DE ESTRUTURA HTML ---');
let allOk = true;

pages.forEach(p => {
  const html = fs.readFileSync(p, 'utf8');
  const isHome = p.includes('index.html');
  const isContentOnly = p.includes('guia.html') || p.includes('cadastros.html');
  const hasMenu = html.includes('id="app-menu-container"');
  const hasDnaLogoLink = isHome ? (html.includes('dna-logo-link') && html.includes('aria-label="Ir para a Home"')) : !html.includes('dna-logo-img');
  const hasRail = isHome || (html.includes('sp-sidebar') && html.includes('sp-main'));
  const hasMobileNav = isHome || html.includes('dna-mobile-nav');
  const hasFpResumo = isHome || isContentOnly || html.includes('id="fpResumo"');
  const hasFpLateral = isHome || isContentOnly || html.includes('id="fpLateral"');
  const hasFpGaveta = isHome || isContentOnly || html.includes('id="fpGaveta"');
  const filtersOk = isHome || isContentOnly ? true : (hasFpResumo && hasFpLateral && hasFpGaveta);

  const ok = hasMenu && hasDnaLogoLink && hasRail && hasMobileNav && filtersOk;
  if (!ok) allOk = false;

  console.log(p.padEnd(26), {
    menu: hasMenu,
    logoHomeLink: hasDnaLogoLink,
    rail: hasRail,
    mobileNav: hasMobileNav,
    filtersPanel: isHome || isContentOnly ? 'N/A' : (hasFpResumo && hasFpLateral && hasFpGaveta)
  });
});

console.log('\nStatus Geral:', allOk ? 'TODAS AS TELAS CONFORMES COM SUCESSO!' : 'ATENÇÃO: HÁ PENDÊNCIAS');
