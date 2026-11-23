# Dashboards: princípios do Storytelling com Dados

Base: o livro *Storytelling com Dados* (Cole Nussbaumer Knaflic), adaptado para dashboards e apps com dados vivos. Aplique junto com `identidade-da.md` (cores e componentes) e com as regras do app (definições de métricas, unidades e filtros).

## 1. Comece pela pergunta

- Cada tela responde a uma pergunta de um público definido e leva a uma ação. Exemplos: "onde preciso agir hoje?", "a meta do mês está em risco?". Escreva a pergunta antes de escolher visuais.
- Ordem de leitura em Z no desktop e de cima para baixo no celular: resposta rápida (KPIs) → tendência → detalhamento → tabela.
- No máximo cerca de 7 blocos por tela. O resto vai para detalhe, aba ou drill-down.

## 2. Títulos que dizem a conclusão

- Prefira o título-afirmação ("Vendas abaixo da meta pelo 3º mês") ao título-rótulo ("Vendas mensais").
- **Em dashboard dinâmico,** o título conclusivo precisa ser gerado a partir dos dados exibidos, com a mesma regra do cálculo, ou ficar de fora. Nesse caso use título descritivo e subtítulo dinâmico. Nunca fixe no código uma conclusão que os dados podem contradizer amanhã.

## 3. Escolha do visual

| Objetivo | Use | Evite |
|---|---|---|
| Um número importante | KPI grande com contexto (vs meta, vs período anterior) | gauge decorativo |
| Poucos números | texto ou tabela simples | gráfico para 2 valores |
| Comparar categorias | barras horizontais ordenadas por valor | pizza com muitas fatias; 3D |
| Tendência no tempo | linha; colunas quando houver poucos períodos | área empilhada com muitas séries |
| Realizado vs meta, budget ou ano anterior | barra do realizado com a comparação como traço — padrão `grafico-referencia.html` | duas barras cheias lado a lado; coluna cinza para o ano anterior |
| Ponte entre dois totais | cascata (waterfall) | barras soltas |
| Parte do todo | barra 100% com poucas categorias; anel de progresso para uma proporção única | pizza de 2 fatias; donut colorido para uma métrica |
| Categoria × período | tabela com mapa de calor sutil | gráfico com dezenas de séries |
| Relação entre duas medidas | dispersão | eixo duplo sem rótulo claro |

## 4. Remova ruído

- Sem bordas de visual, sem grade no eixo X, grade leve ou nenhuma no Y e no máximo cerca de 5 ticks.
- Rótulo direto no fim da linha ou na barra no lugar de legenda, quando couber. Se não couber, use legenda compacta junto ao título.
- Use as casas decimais mínimas que preservam a decisão. A unidade vai no título ou no eixo, não repetida em cada rótulo.
- Rótulos de dados só onde ajudam. Nunca exiba "0,0%" em períodos sem dado.
- Em séries longas, mostre o período relevante (ex.: últimos 13 meses) e deixe o histórico sob demanda.

## 5. Direcione a atenção

- Uma cor de destaque por gráfico, na série ou barra que sustenta a conclusão. O restante fica em cinza (contexto) ou na cor de comparação.
- Cor de alerta só na comparação entre realizado e meta. A diferença entre dois planos (ex.: budget × forecast) é neutra. O mesmo símbolo com significados diferentes confunde.
- O cinza de contexto pode ser claro de propósito. A referência principal (meta, budget) precisa de contraste de pelo menos 3:1.
- Status com texto, cor e sinal (▲/▼, +/−), nunca só com cor.

## 6. Integridade dos números

- Barras sempre com base zero e, quando comparadas, com escala compatível.
- Ausência de dado não é zero. Mostre "—" ou uma lacuna, com explicação acessível.
- Percentual com denominador zero não é número válido: mostre "—" com nota.
- **Período corrente parcial** (mês em andamento, dados D-1): compare com a meta proporcional até a data ou marque como "parcial". Comparar mês parcial com mês fechado gera alerta falso todo dia e ensina o time a ignorar o vermelho.
- Explicite a base de toda variação (vs meta, vs mês anterior, vs ano anterior) e a unidade (%, p.p., R$, DZ, kg…).
- Mostre "Atualizado em" e a fonte quando o dado não for em tempo real.
- O redesign não muda o que o número significa. Preserve as definições, unidades, filtros e regras de exibição do app.

## 7. Celular

- KPIs primeiro: um por linha, ou em grade 2 × 2 se os valores couberem sem truncar.
- Gráficos com altura fixa no container (não proporção) e menos séries. Prefira small multiples a uma linha com muitas séries.
- Valores por toque (tooltip em modo índice) e tabela alternativa expansível.
- Séries longas: rolagem horizontal localizada e perceptível, ou agregação por período maior.

## 8. Chart.js 4: configuração base

Para barras com comparação, não parta desta base: use `grafico-referencia.html` (critérios G1 a G8 do `identidade-da.md`). A base abaixo vale para os demais gráficos.

```js
const reduzMovimento = matchMedia('(prefers-reduced-motion: reduce)').matches;
const LOCALE = 'pt-BR';
const fmtNum = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 });

const opcoesBase = {
  responsive: true,
  maintainAspectRatio: false,                      // altura vem do container
  locale: LOCALE,                                  // separadores em ticks e tooltips
  animation: reduzMovimento ? false : { duration: 250 },
  interaction: { mode: 'index', intersect: false }, // funciona com toque
  plugins: {
    legend: { display: false },                    // legenda HTML ou rótulo direto
    tooltip: {
      callbacks: {
        label: (i) => ` ${i.dataset.label}: ${i.parsed.y == null ? '—' : fmtNum.format(i.parsed.y)}`
      }
    }
  },
  scales: {
    x: { grid: { display: false }, border: { display: false } },
    y: {
      beginAtZero: true,                           // obrigatório em barras; opcional em linhas
      border: { display: false },
      ticks: { maxTicksLimit: 5, callback: (v) => fmtNum.format(v) }
    }
  }
};
```

- `null` nos dados gera lacuna na linha. Use `spanGaps: false` para não ligar pontos através da ausência.
- Para moeda, troque `fmtNum` por `new Intl.NumberFormat(LOCALE, { style: 'currency', currency: 'BRL' })`, ou pela moeda do locale do produto.
- Inclua `<canvas role="img" aria-label="…">` descrevendo o que o gráfico mostra, mais uma tabela alternativa.
- Ao trocar o tema, destrua e recrie os gráficos.

## Checklist rápido

- [ ] Cada tela tem uma pergunta, e os KPIs vêm primeiro
- [ ] Títulos conclusivos são calculados a partir dos dados, ou descritivos com subtítulo dinâmico
- [ ] Uma cor de destaque por gráfico; o resto fica em contexto
- [ ] Barras com base zero; ausência e denominador zero aparecem como "—"
- [ ] Período parcial comparado com meta proporcional ou marcado como parcial
- [ ] Toda variação tem base e unidade explícitas
- [ ] "Atualizado em" visível
- [ ] Valores acessíveis por toque e por tabela alternativa
