const fs = require('fs');
const files = ['performance.html', 'spend.html', 'ordens.html', 'comercial.html', 'governanca.html', 'relatorios.html'];

files.forEach(f => {
  const content = fs.readFileSync('src/app/' + f, 'utf8');
  const m = content.match(/<aside class="sp-sidebar"[\s\S]*?<\/aside>/);
  if (!m) {
    console.log(f, 'SIDEBAR NOT FOUND');
    return;
  }
  const aside = m[0];
  const items = [...aside.matchAll(/<a href="([^"]+)" class="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g)].map(match => {
    const href = match[1];
    const cls = match[2];
    const text = match[3].replace(/<[^>]+>/g, '').trim();
    const hasActive = cls.includes('active');
    const svgD = [...match[3].matchAll(/(?:d|points|x1)="([^"]+)"/g)].map(x => x[1]).join('|');
    return { href, text, hasActive, svgD };
  });

  console.log(`\n=== ${f} (${items.length} items) ===`);
  items.forEach(it => {
    console.log(`  - [${it.href}] text="${it.text}" active=${it.hasActive} svgHash=${it.svgD.slice(0, 30)}...`);
  });
});
