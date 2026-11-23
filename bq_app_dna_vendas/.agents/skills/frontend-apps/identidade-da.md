# Identidade D&A Brasil: padrão DNA de Vendas

Padrão visual dos apps do time D&A Brasil no Databricks Apps. A referência é o app **DNA de Vendas**:
- **Home e tema escuro:** azul-marinho profundo, cartões sóbrios e azul como cor de ação;
- **tema claro:** o das telas internas dos apps (fundo cinza-azulado, cartões brancos).

- **Quando usar:** apps novos, apps sem identidade própria e reformulações que pedirem o padrão D&A ou DNA.
- **Quando não usar:** app com identidade própria que o pedido não manda trocar. Nesse caso use este arquivo só como régua de qualidade.
- **Origem dos valores:** as cores foram extraídas de capturas de tela, então são aproximações. Se o código do DNA de Vendas estiver disponível, os valores dele prevalecem.

## Princípios

| Princípio | Tradução |
|---|---|
| Sobriedade corporativa | Superfícies lisas, bordas sutis e sombra leve. Nada de gradiente atrás de texto, brilho ou efeitos decorativos. |
| Azul é ação | Azul para ação, seleção, foco e o dado em destaque. O resto da interface é neutro. |
| Cor com função | Verde, âmbar e vermelho só para status, sempre com texto ou sinal. Cartões não ganham borda colorida por enfeite. |
| Vermelho é marca | O vermelho Bimbo aparece só no logotipo. Alerta usa o token `--danger`, nunca o vermelho da marca. |
| Hierarquia por tipografia | Títulos fortes e curtos, descrições em cinza e números grandes com `tabular-nums`. |

## Tokens

Cole no topo do CSS.

```css
:root {
  /* Superfícies */
  --bg-page:        #F0F4F8;
  --bg-glow:        none;
  --bg-header:      #FFFFFF;
  --surface:        #FFFFFF;
  --surface-alt:    #F6F9FC;
  --surface-hover:  #EEF3FA;
  --border:         #DCE3EC;   /* divisórias e contorno de cartões (decorativo) */
  --border-input:   #7D8CA1;   /* contorno de campos e controles: >= 3:1 */

  /* Texto */
  --text-primary:   #1E2432;
  --text-secondary: #465468;
  --text-muted:     #5A6B82;
  --text-on-accent: #FFFFFF;
  --link:           #1D4ED8;

  /* Ação e marca */
  --primary:        #2563EB;
  --primary-strong: #1D4ED8;
  --primary-soft:   #E3ECFD;
  --focus-ring:     #2563EB;
  --brand-red:      #C02830;   /* somente logotipo */

  /* Ícones em blocos coloridos */
  --tint-blue:  #E3ECFD;  --tint-teal: #DDF1F6;  --tint-green: #DCF3E6;

  /* Gráficos */
  --chart-focus:    #3B82F6;   /* período atual, série principal */
  --chart-context:  #B1CDFB;   /* períodos anteriores (contexto intencionalmente claro) */
  --chart-compare:  #64748B;   /* meta, ano anterior */
  --chart-grid:     #E5EAF1;

  /* Status (texto sobre o -soft passa 4,5:1) */
  --success: #15803D;  --success-soft: #DCFCE7;
  --warning: #B45309;  --warning-soft: #FEF3C7;
  --danger:  #B91C1C;  --danger-soft:  #FEE2E2;
  --info:    #1D4ED8;  --info-soft:    #DBEAFE;

  /* Forma */
  --r-card: 14px;  --r-control: 8px;  --r-pill: 999px;
  --shadow-card: 0 1px 2px rgba(15,23,42,.04), 0 4px 16px rgba(15,23,42,.06);
  --shadow-menu: 0 12px 32px rgba(15,23,42,.18);
}

:root[data-theme="dark"] {
  --bg-page:        #060A12;
  --bg-glow:        radial-gradient(1100px 420px at 50% 0%, #13203A 0%, transparent 70%);
  --bg-header:      #080C17;
  --surface:        #171C28;
  --surface-alt:    #141B29;
  --surface-hover:  #1D2433;
  --border:         #1F2532;
  --border-input:   #5E6E86;

  --text-primary:   #F0F4F8;
  --text-secondary: #C6D0DC;
  --text-muted:     #94A2B8;
  --text-on-accent: #FFFFFF;
  --link:           #60A5FA;

  --primary:        #3B82F6;
  --primary-strong: #2563EB;
  --primary-soft:   #142444;
  --focus-ring:     #60A5FA;
  --brand-red:      #C02830;

  --tint-blue:  #24314B;  --tint-teal: #1E3647;  --tint-green: #1F363D;

  --chart-focus:    #3B82F6;
  --chart-context:  #35558A;
  --chart-compare:  #94A2B8;
  --chart-grid:     rgba(255,255,255,.06);

  --success: #4ADE80;  --success-soft: rgba(74,222,128,.14);
  --warning: #FBBF24;  --warning-soft: rgba(251,191,36,.14);
  --danger:  #FCA5A5;  --danger-soft:  rgba(248,113,113,.14);
  --info:    #93C5FD;  --info-soft:    #142444;

  --shadow-card: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35);
  --shadow-menu: 0 16px 40px rgba(0,0,0,.55);
}

body { background: var(--bg-glow), var(--bg-page); color: var(--text-primary); }
```

**Tema:**
- Na primeira visita, siga `prefers-color-scheme`. A escolha do usuário fica na chave "Tema escuro" do menu do app e é guardada em `localStorage`, dentro de `try/catch`.
- **Um tema por página, inteiro.** Cabeçalho, trilho, fundo, faixa de abertura, cartões e rodapé usam os tokens do tema ativo. Nenhum trecho fica com cor fixa de um tema enquanto os componentes usam o outro (ex.: fundo azul-marinho com cartões brancos no tema claro). Vale também para a Home.
- Antes da entrega, meça o contraste sobre o fundo real de cada texto, nos dois temas.

### Contraste medido

| Par | Claro (branco / fundo) | Escuro (cartão / brilho) | Mínimo |
|---|---|---|---|
| `--text-primary` | 15,5 / 14,0 | 15,4 / 14,7 | 4,5 |
| `--text-secondary` | 7,7 / 7,0 | 10,9 / 10,4 | 4,5 |
| `--text-muted` | 5,4 / 4,9 | 6,6 / 6,3 | 4,5 |
| `--link` | 6,7 / 6,1 | 6,7 / 6,4 | 4,5 |
| Status (texto sobre `-soft`) | ≥ 4,5 | ≥ 7,3 | 4,5 |
| Texto branco no botão `--primary` | 5,2 | 5,2 | 4,5 |
| `--border-input` | 3,4 / 3,1 | 3,3 | 3 |
| `--chart-focus` | 3,7 / 3,3 | 4,6 | 3 |
| `--chart-compare` | 4,8 / 4,3 | 6,6 | 3 |

**Regras que saem da tabela:**
- `--chart-context` fica abaixo de 3:1 de propósito, porque é contexto. Nunca o use para a série que sustenta a conclusão nem para a meta.
- `--border` é decorativo. Campo de formulário, select e botão secundário usam `--border-input`.
- Texto em `--text-muted` só sobre `--surface` ou `--bg-page`, nunca sobre os blocos `--tint-*`.

## Tipografia

Fonte: Inter, com fallback `'Segoe UI', system-ui, sans-serif`. O layout precisa continuar íntegro se a rede bloquear o Google Fonts.

| Elemento | Tamanho/peso | Cor | Extra |
|---|---|---|---|
| H1 da Home | 40–56/800 (fluido com `clamp`) | `--text-primary` | caixa alta, `letter-spacing: -.02em` |
| Subtítulo da Home | 16–18/400 | `--text-muted` | no máximo 70 caracteres por linha |
| Título da página | 20/700 | `--text-primary` | |
| Título de cartão | 15/600 (Home: 22/700) | `--text-primary` | de preferência com a conclusão |
| Rótulo de KPI e de filtro | 11/600 | `--text-muted` | caixa alta, `letter-spacing: .06em` |
| Valor de KPI | 28–32/700 | `--text-primary` | `tabular-nums` |
| Variação | 12/600 | cor de status | sinal (▲/▼, +/−) e base ("vs meta", "vs mês anterior") |
| Corpo, tabela, navegação | 14/400–500 | `--text-primary` / `--text-secondary` | |
| Metadado e eixo | 12/400 | `--text-muted` | |
| Etiqueta (tag, badge) | 11/600 | conforme a variante | caixa alta na Home |

No celular, nenhum texto de conteúdo fica abaixo de 12 px, e os campos de formulário usam 16 px.

## Espaçamento e grid

- **Escala (base 4):** 4 · 8 · 12 · 16 · 20 · 24 · 32 · 48.
- **Conteúdo:** largura máxima de 1440 px. Gutter de 32 px no desktop, 24 px no tablet e 16 px no celular.
- **Cartões:** gap de 16 px entre eles e padding interno de 20 px (24 px na Home).
- **Grid das telas internas:**
  - 12 colunas no desktop: KPIs em 3 ou 4 colunas, gráfico principal em 7 ou 8 e apoio em 4 ou 5.
  - 2 colunas no tablet; 1 coluna no celular.

## Componentes

### Navegação e cabeçalho (telas internas)
Padrão do DNA de Vendas: trilho vertical à esquerda e cabeçalho à direita dele. **Nada de abas de módulos no cabeçalho.**

- **Trilho de navegação (desktop e tablet):**
  - fixo à esquerda, com altura total, 80 px de largura, fundo `--bg-header` e borda direita `--border`;
  - primeiro item: Início (Home); depois, os módulos na ordem do app;
  - cada item tem ícone em contorno (22 px) e rótulo curto embaixo (11–12 px, até 2 linhas, nunca cortado), com área mínima de 64 × 56 px;
  - item ativo: fundo `--primary-soft`, ícone e texto em `--primary-strong` (no escuro, `--link`), raio 10 e `aria-current="page"`.
- **Cabeçalho (à direita do trilho):**
  - 64 px de altura, fundo `--bg-header` e borda inferior `--border`. Fica fixo no topo sem cobrir conteúdo nem foco.
  - **Esquerda:** logotipo D&A com 32 px de altura (mínimo de 28), legível nos dois temas. Ele é link para a Home, com `aria-label="Ir para a Home"` e área de clique de pelo menos 44 × 44 px. Ao lado vão o número e o nome do módulo.
  - **Direita:** só o **menu do app**. Metadados como "Dados atualizados em…" podem vir antes do menu no desktop.
- **Componente único:** trilho, cabeçalho e menu são um só componente compartilhado por todas as telas, sem cópia por página, e funcionam igual em todas as rotas.
- **Celular (≤ 640 px):** o trilho sai.
  - Até 5 destinos: barra inferior com ícone e rótulo.
  - Mais que isso: 4 destinos e "Mais", ou um drawer aberto por botão no cabeçalho.
  - Respeite `env(safe-area-inset-bottom)`, com o último conteúdo visível acima da barra.
- **Com painel de filtros:** trilho à esquerda, conteúdo no meio e filtros à direita. O conteúdo funciona com o painel aberto e recolhido.

### Menu do app (canto superior direito)
Padrão do menu do Portal Distribuidores v2. Copie esse padrão, sem acrescentar seções, títulos ou rodapé.
- **Gatilho:**
  - ícone de pessoa em contorno num círculo de 36 px (fundo `--surface-hover`, ícone `--text-primary`), com um chevron ao lado que aponta para cima quando aberto;
  - sem iniciais; área de toque de pelo menos 44 px;
  - `aria-haspopup="menu"`, `aria-expanded` e `aria-label="Menu do usuário"`.
- **Painel:** cerca de 360 px, ancorado à direita do gatilho, em `--surface` com raio 12, `--shadow-menu` e borda `--border`. Fica por cima de qualquer elemento fixo, sem ser cortado por `overflow` de um ancestral.
- **Itens:**
  - uma linha por item, com ícone em contorno (20 px) à esquerda, texto de 16 px, altura de 52–56 px e padding lateral de 20 px;
  - sem cabeçalho com nome ou e-mail, sem títulos de seção, sem selos (ex.: "ADMIN") e sem rodapé de versão;
  - **item indisponível:** texto em `--text-muted`, linha de ajuda de 14 px abaixo (ex.: "Escolha um distribuidor primeiro") e `aria-disabled="true"`;
  - **item de administrador:** aparece só para quem tem a permissão, pela regra que o app já usa, e nunca com selo.
- **Ordem:**
  1. ações e ferramentas do app (ex.: Guia do Usuário, Cadastro de Planilhas, Gestão de Acessos);
  2. divisória e **Idioma**: ícone de globo, texto "Idioma" e seletor compacto PT | EN | ES à direita, com o ativo destacado;
  3. **Tema escuro**: ícone de lua, texto e chave liga/desliga à direita (`role="switch"` e `aria-checked`);
  4. divisória e **Sair**, com ícone de saída. Só aparece se o app tiver logout real.
- **Comportamento:**
  - abre por clique ou Enter/Espaço; ↑/↓ navegam; Esc ou clique fora fecha e devolve o foco;
  - trocar idioma ou tema mantém a página, os filtros e a posição de rolagem;
  - abre em todas as rotas.
- **Celular (≤ 640 px):** o mesmo painel em largura total, abaixo do cabeçalho ou como folha inferior, com itens de 56 px.
- **Identidade do usuário:** o menu padrão não mostra nome. Se o app precisar dela, o Databricks Apps envia os cabeçalhos HTTP `X-Forwarded-Preferred-Username` e `X-Forwarded-Email`; localmente, simule.

### Página inicial (Home institucional)
Todo app D&A abre numa Home que apresenta o projeto. O cabeçalho tem o logotipo e o menu do app; o trilho é opcional, porque os cartões já levam aos módulos. A página inteira segue o tema ativo: fundo `--bg-page` (com `--bg-glow` no escuro), cartões `--surface`, rodapé no fundo da página. Seções, nesta ordem:

1. **Abertura com o objetivo da solução:**
   - etiqueta-pílula (`--primary-soft`, texto `--info`, caixa alta; ex.: "DATABRICKS APPS · D&A ANALYTICS");
   - H1 em caixa alta com o nome do app;
   - subtítulo de 1 a 2 frases: que problema resolve, para quem e com quais dados;
   - divisor curto em `--primary` (48 × 3 px).
2. **Principais funcionalidades:** cartões de módulo.
   - Grid de 3 colunas no desktop, 2 no tablet e 1 no celular.
   - Cada cartão tem bloco de ícone (48 px, fundo `--tint-*`), etiqueta de perfil (ex.: EXECUTIVO, EXPLORADOR), título, descrição em `--text-muted`, divisória e até 3 destaques com ✓ em `--primary`.
   - O cartão inteiro é um único link (sem botão aninhado). Todos os cartões são idênticos. Hover e foco: só borda `--primary` e elevação leve, sem gradiente nem fundo especial. A borda não muda de cor por módulo.
3. **Benefícios para o negócio:** 3 ou 4 itens, cada um com ícone, título curto e uma frase.
   - Benefícios qualitativos, ou números que estejam documentados no projeto, com a fonte.
   - Nunca invente números. Benefício sem fonte vira item marcado como "validar com o dono do produto" na entrega.
4. **Guia rápido de utilização:** 3 a 5 passos numerados, com os nomes reais das telas e botões do app (ex.: "Abra o Vendômetro", "Ajuste os filtros no painel à direita e clique em Aplicar", "Exporte em XLSX").
   - Termina com um link para o Guia do Usuário completo.
5. **Rodapé:** "Grupo Bimbo Brasil · Data & Analytics · Databricks Apps · ano", em `--text-muted`. Precisa ser legível.

Critérios de aceite da Home:

| # | Critério |
|---|---|
| H1 | As quatro seções (objetivo, funcionalidades, benefícios, guia rápido) existem nessa ordem, com título visível em cada uma. |
| H2 | Os textos vêm da documentação e das telas do próprio app (README, Guia, telas). Nada inventado; o que precisar de validação aparece listado na entrega. |
| H3 | Cada cartão de módulo leva ao módulo correspondente, e o guia rápido cita botões e telas que existem. |
| H4 | Textos nos idiomas que o app oferece, pelo mecanismo de i18n existente. |
| H5 | Celular: tudo em uma coluna, sem rolagem horizontal, com o guia rápido legível sem zoom. |
| H6 | Tema claro inteiramente claro e tema escuro inteiramente escuro (fundo, abertura, cartões, ícones, rodapé), com contraste medido sobre o fundo real nos dois. |
| H7 | Nenhum cartão tem gradiente, cor de fundo própria ou vermelho. Todos têm a mesma aparência. |

### Painel de filtros (lateral, retrátil à direita)
A implementação de referência é `filtros-referencia.html`. Copie o comportamento e adapte só a sintaxe ao framework do app. Os critérios abaixo entram como requisitos na matriz de conformidade.

| # | Critério de aceite |
|---|---|
| F1 | Desktop (≥ 1200 px): painel à **direita**, com 320 px aberto. Recolhe para um **trilho de 48 px** com ícone, contador de filtros aplicados e "FILTROS" na vertical. O botão de recolher fica no topo do painel e o trilho inteiro expande, os dois com `aria-expanded` e `aria-controls`. |
| F2 | O conteúdo ocupa o espaço liberado (grid, sem sobreposição) e os gráficos se redimensionam. O painel fica fixo abaixo do cabeçalho (`sticky`), com rolagem interna e Limpar/Aplicar fixos no rodapé. |
| F3 | O estado aberto/recolhido fica salvo por usuário (`localStorage` com `try/catch`). Na primeira visita, abre aberto a partir de 1440 px e recolhido entre 1200 e 1439 px. |
| F4 | Cada filtro é uma seção expansível (`<details>`) com o nome e o resumo do valor: "Todos", o nome (um item) ou "n selecionados". Com filtro ativo, o resumo fica em negrito, na cor de destaque. |
| F5 | Multiseleção com **caixa por item**, **Selecionar todos** (indeterminado quando parcial) e **Somente** em cada item (visível no hover e no foco; sempre visível em toque). |
| F6 | **Busca** a partir de 8 opções. Com busca ativa, o primeiro item vira "Somente os resultados (n)". Cada abertura começa sem busca. |
| F7 | Seleção única (rádio) para Mês, Ano e afins. |
| F8 | Alterações ficam em rascunho até **Aplicar**, que fica desabilitado sem mudança. **Limpar** volta ao padrão e aplica. Toda lista reflete mudanças feitas por fora dela (Limpar, chip, gaveta). |
| F9 | Acima do conteúdo, **uma única linha de chips removíveis** com os filtros aplicados e "Limpar tudo". A linha some quando não há filtro aplicado, e o excesso rola na horizontal dentro dela. |
| F10 | Tablet e celular (< 1200 px): botão **Filtros (n)** na linha de chips abre uma gaveta à direita (`<dialog>`), com 400 px no tablet e largura total no celular. Opções e botões têm 44 px. Fechar sem aplicar descarta o rascunho. |
| F11 | Teclado: ↑/↓ percorrem as opções, Espaço marca e Esc fecha a gaveta. Ao recolher ou expandir, o foco vai para o controle oposto. O contrato com o backend é o que o app já usa; lista vazia = sem filtro. Um filtro que um bloco ignora é avisado no próprio bloco. |

### KPI
- **Base:** cartão `--surface` com borda `--border` neutra (nunca colorida por enfeite) e ícone opcional em bloco `--tint-*`.
- **Conteúdo:** rótulo, valor e uma linha de contexto (variação com sinal e base, ou meta).
- **Cor:** só a variação ou o status ganham cor. O valor fica em `--text-primary`. Uma exceção é aceitável quando o próprio valor é o status: até um destaque por linha de KPIs.
- **Linha de KPIs:** 4 por linha no desktop. Mais do que isso vira 2 linhas ou passa o secundário para um detalhe.

### Tabela
- **Base:** fundo `--surface`, cabeçalho fixo em `--surface-alt` com rótulos de 11/600 em caixa alta e divisórias `--border`.
- **Números:** alinhados à direita, com `tabular-nums`.
- **Interação:** ordenação com `aria-sort` e filtro por coluna em menu acessível por teclado.
- **Texto truncado:** usa ellipsis, com o valor completo em `title` e acessível por toque (linha expansível ou detalhe).
- **Rodapé:** contagem de registros, paginação e exportação (CSV/XLSX) no cabeçalho do cartão.
- **Celular:** cartões por linha com os 3 ou 4 campos principais e "ver detalhes", ou rolagem horizontal localizada com a primeira coluna fixa.

### Abas internas e seletores segmentados
- Fundo `--surface-alt`. O item ativo tem fundo `--primary`, texto `--text-on-accent` e `aria-selected`.
- Se não couberem no celular, viram rolagem horizontal com indicação de continuidade, ou um select.

### Botões
- **Primário:** `--primary` com texto branco 13/600, raio 8 e altura de 36 px (44 px no celular). No máximo um por bloco.
- **Secundário:** `--surface` com borda `--border-input`.
- **Fantasma:** texto em `--link`.
- **Destrutivo:** texto `--danger`, com confirmação antes de executar.
- **Exportar (XLSX/CSV):** botão secundário com ícone de download.

### Estados
- **Carregamento:** skeleton no formato do conteúdo.
- **Vazio:** explicação e próxima ação.
- **Erro:** o que aconteceu e "Tentar novamente".
- **Sem permissão:** explicação e caminho de acesso.
- **Alertas condicionais:** blocos de alerta só aparecem quando há algo a alertar. Com valor zero, o bloco vira uma nota neutra ou some.

## Gráficos (Chart.js 4)

- **Barras com comparação (realizado vs meta, budget ou ano anterior):** parta de `grafico-referencia.html`, que é a referência obrigatória (origem: gráfico "Sell-in vs meta" do Portal Distribuidores v2). Critérios de aceite:

| # | Critério |
|---|---|
| G1 | Cabeçalho com eyebrow, título curto e legenda (quadrado da barra, traço da comparação). À direita, pílula "Acumulado vs …" com selo de status e, se houver visões, seletor segmentado. |
| G2 | Comparação como **traço horizontal** por mês, um pouco mais largo que a barra. Nunca como barra. |
| G3 | Meses comuns em tom discreto, mês filtrado em cor forte e mês sob o cursor em tom intermediário. |
| G4 | Rótulo de dado **só no mês filtrado**, logo acima da barra. |
| G5 | Sem eixo Y e sem grade, só a linha de base. Mês filtrado em negrito no eixo X. |
| G6 | Pílulas de percentual abaixo dos meses, coloridas pela regra de status que o app já usa. Sem pílula quando falta dado ou o denominador é zero. |
| G7 | Tooltip escuro com o mês por extenso, série, comparação, % e diferença; % e diferença na cor do status. Nunca sai da tela. |
| G8 | Tabela alternativa em `<details>`, rolagem localizada no celular e formatação pelo locale. |

- **Rankings:** os 3 primeiros em `--chart-focus`, o resto em `--chart-compare`, ordenados por valor.
- **Eixos (demais gráficos):** sem grade no X, grade `--chart-grid` no Y, sem borda de eixo e no máximo 5 ticks.
- **Interação e acessibilidade:** `interaction: { mode: 'index', intersect: false }`, `locale` do produto, `<canvas role="img" aria-label>` e tabela alternativa.
- **Tema:** as cores são lidas dos tokens com `getComputedStyle`. Ao trocar o tema, destrua e recrie os gráficos.

As regras de escolha de visual, título e integridade estão em `dashboards-swd.md`.

## Checklist da identidade

- [ ] Tokens claro e escuro no topo do CSS, sem cor fixa fora deles
- [ ] Vermelho só no logotipo; alertas usam `--danger`
- [ ] Cartões e KPIs com borda neutra; cor só em status e variação
- [ ] Um tema por página, inteiro; contraste medido sobre o fundo real nos dois temas
- [ ] Trilho de navegação à esquerda (sem abas no cabeçalho); logotipo de 32 px, link para a Home
- [ ] Menu do app no padrão Portal Distribuidores, funcionando em todas as rotas
- [ ] Painel de filtros lateral retrátil atendendo F1 a F11
- [ ] Campos e controles com `--border-input`; texto e links com contraste ≥ 4,5:1
- [ ] Home institucional atendendo H1 a H7, com cartões de módulo clicáveis por inteiro e rodapé legível
- [ ] Barras com comparação no padrão `grafico-referencia.html` (G1 a G8)
- [ ] Gráficos recriados na troca de tema
