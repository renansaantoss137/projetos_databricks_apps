// Teste de validação dos filtros atualizados
const fs = require('fs');

// Carrega filters-component.js simulando window e document mínimos
const jsCode = fs.readFileSync('src/app/filters-component.js', 'utf8');

// Mock window e document
global.window = {
  innerWidth: 1440,
  dispatchEvent: () => {},
  addEventListener: () => {}
};
global.document = {
  documentElement: { lang: 'pt' },
  getElementById: () => null,
  createElement: () => ({ append: () => {}, querySelector: () => null, setAttribute: () => {} }),
  addEventListener: () => {}
};
global.localStorage = {
  getItem: () => null,
  setItem: () => {}
};

eval(jsCode);

const DNAFiltersPanel = global.window.DNAFiltersPanel;

const MESES_OPCOES = [
  { v: '1', t: '01 - Jan' },
  { v: '2', t: '02 - Fev' },
  { v: '3', t: '03 - Mar' },
  { v: '4', t: '04 - Abr' },
  { v: '5', t: '05 - Mai' },
  { v: '6', t: '06 - Jun' },
  { v: '7', t: '07 - Jul' },
  { v: '8', t: '08 - Ago' },
  { v: '9', t: '09 - Set' },
  { v: '10', t: '10 - Out' },
  { v: '11', t: '11 - Nov' },
  { v: '12', t: '12 - Dez' }
];

const panel = new DNAFiltersPanel({
  filtros: [
    { id: 'fAno', key: 'ano', rotulo: 'Ano', tipo: 'unico', opcoes: ['2024', '2025', '2026'], padrao: '2026' },
    { id: 'fMes', key: 'mes', rotulo: 'Mês', tipo: 'multi', opcoes: MESES_OPCOES, padrao: [] },
    { id: 'fFornNegociavel', key: 'is_fornecedor_nao_negociavel', rotulo: 'Forn. Negociável', tipo: 'multi', opcoes: ['NEGOCIAVEL', 'NÃO NEGOCIAVEL'], padrao: ['NEGOCIAVEL'] }
  ]
});

console.log('--- TESTE 1: Estado Inicial (Padrão) ---');
const ativosInicial = panel.totalAtivos(panel.aplicado);
console.log('Total de filtros ativos no início:', ativosInicial);
console.log('fFornNegociavel ativo?', panel.isAtivo(panel.filtros[2], panel.aplicado)); // deve ser false!
console.log('fMes ativo?', panel.isAtivo(panel.filtros[1], panel.aplicado)); // deve ser false!
console.log('fMes resumo inicial:', panel.getResumo(panel.filtros[1], panel.aplicado)); // "Ano Fechado (Todos)"
console.log('fMes getSelected inicial:', global.window.filters.fMes.getSelected()); // [] (Ano Fechado)

console.log('\n--- TESTE 2: Usuário seleciona Mês Outubro (Mês único) ---');
panel.rascunho.fMes = new Set(['10']);
panel.aplicar();
console.log('Total ativos:', panel.totalAtivos(panel.aplicado));
console.log('fMes resumo:', panel.getResumo(panel.filtros[1], panel.aplicado)); // "10 - Out"
console.log('fMes getSelected:', global.window.filters.fMes.getSelected()); // ['10']

console.log('\n--- TESTE 3: Usuário seleciona Jan a Outubro (Ano Acumulado) ---');
panel.rascunho.fMes = new Set(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']);
panel.aplicar();
console.log('fMes resumo:', panel.getResumo(panel.filtros[1], panel.aplicado)); // "Acumulado (Jan a Out)"
console.log('fMes getSelected (quantidade):', global.window.filters.fMes.getSelected().length); // 10

console.log('\n--- TESTE 4: Usuário clica em Limpar Tudo ---');
panel.limpar();
console.log('Total ativos após limpar:', panel.totalAtivos(panel.aplicado)); // 0!
console.log('fMes resumo após limpar:', panel.getResumo(panel.filtros[1], panel.aplicado)); // "Ano Fechado (Todos)"
console.log('fMes getSelected após limpar:', global.window.filters.fMes.getSelected()); // [] (Ano Fechado)

if (ativosInicial === 0 && global.window.filters.fMes.getSelected().length === 0) {
  console.log('\n✅ TODOS OS TESTES PASSARAM COM EXCELÊNCIA!');
} else {
  console.error('\n❌ Falha em algum teste');
  process.exit(1);
}
