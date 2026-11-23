const fs = require('fs');

const html = fs.readFileSync('src/app/performance.html', 'utf8');
const lines = html.split('\n');

lines.forEach((l, i) => {
  if (l.includes("id='appLayout'") || l.includes('id="appLayout"') ||
      l.includes("id='fpLateral'") || l.includes('id="fpLateral"') ||
      l.includes("class='conteudo'") || l.includes('class="conteudo"')) {
    console.log(i + 1, l);
  }
});
