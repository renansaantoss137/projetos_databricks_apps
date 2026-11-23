---
name: DNA de Vendas Bimbo QSR
description: Databricks App corporativo de performance comercial, vendômetro e relatórios analíticos
colors:
  primary: "#2563EB"
  primary-dark: "#3B82F6"
  primary-strong: "#1D4ED8"
  primary-soft: "#E3ECFD"
  brand-red: "#C02830"
  neutral-bg: "#F0F4F8"
  neutral-bg-dark: "#060A12"
  surface: "#FFFFFF"
  surface-dark: "#171C28"
  surface-alt: "#F6F9FC"
  surface-hover: "#EEF3FA"
  border: "#DCE3EC"
  border-dark: "#1F2532"
  border-input: "#7D8CA1"
  text-primary: "#1E2432"
  text-primary-dark: "#F0F4F8"
  text-secondary: "#465468"
  text-muted: "#5A6B82"
  success: "#15803D"
  success-soft: "#DCFCE7"
  warning: "#B45309"
  warning-soft: "#FEF3C7"
  danger: "#B91C1C"
  danger-soft: "#FEE2E2"
typography:
  display:
    fontFamily: "Inter, 'Segoe UI', system-ui, sans-serif"
    fontSize: "clamp(2rem, 4vw, 2.75rem)"
    fontWeight: 800
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Inter, 'Segoe UI', system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Inter, 'Segoe UI', system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "Inter, 'Segoe UI', system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  caption:
    fontFamily: "Inter, 'Segoe UI', system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.4
  label:
    fontFamily: "Inter, 'Segoe UI', system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.04em"
rounded:
  xs: "2px"
  sm: "4px"
  control: "8px"
  card: "14px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#FFFFFF"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "{colors.primary-strong}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "40px"
  pill-toggle:
    backgroundColor: "{colors.surface-alt}"
    textColor: "{colors.text-muted}"
    rounded: "{rounded.control}"
    padding: "3px"
---

# Design System: DNA de Vendas Bimbo QSR

## Overview

**Creative North Star: "Torre de Controle Operacional"**

O DNA de Vendas é concebido como a cabine de comando e controle analítico diário para equipes comerciais, gerências e distribuidores Bimbo QSR. A estética abandona artifícios puramente decorativos em favor de rigor cirúrgico, alta densidade informacional e tempos de leitura inferiores a 5 segundos para tomada de decisão em campo e na diretoria.

O ambiente opera nativamente em dois modos complementares: um tema Escuro profundo (Deep Slate / Navy `#060A12`) otimizado para longas sessões de análise e foco visual nas métricas luminosas, e um tema Claro corporativo (`#F0F4F8`) com alto contraste de texto e separação tonal nítida. Em ambos os modos, a hierarquia é estritamente orientada aos dados: o faturamento realizado, os pedidos em carteira e a cobertura de metas (Budget & Forecast) dominam o primeiro plano visual.

**Key Characteristics:**
- **Rigor Operacional & Alta Densidade:** Máximo aproveitamento do viewport sem sensação de aperto ou poluição.
- **Camadas Tonais Sutis:** Separação hierárquica baseada em matizes de superfície e bordas de 1px, sem dependência de sombras pesadas.
- **Acento Funcional Exclusivo:** O azul elétrico e os alertas de semáforo são ativados unicamente para conduzir a leitura e a ação analítica.
- **Resiliência Multi-dispositivo:** Transição transparente entre desktop widescreen corporativo (painel fixo 320px) e smartphones (drawer inferior e bottom-nav de 56px).

## Colors

A paleta equilibra a credibilidade analítica corporativa com a identidade do Grupo Bimbo e Bimbo QSR.

### Primary
- **Bimbo Electric Royal** (`#2563EB` no tema Claro / `#3B82F6` no tema Escuro): Utilizado exclusivamente para ações primárias, links, estados ativos e linhas de foco analítico. Transmite precisão técnica e energia Databricks/D&A.
- **Bimbo Heritage Red** (`#C02830`): Preservado como acento de marca institucional Grupo Bimbo em selos institucionais e pontos focais de identidade corporativa.

### Secondary
- **Data Insight Teal & Ice** (`#0284c7` / `#06b6d4` / `#E3ECFD`): Cores de apoio para curvas de Forecast, preenchimentos suaves de badges e estados de seleção secundários.

### Neutral
- **Executive Ink / High Contrast Text** (`#1E2432` no Claro / `#F0F4F8` no Escuro): Cor principal de tipografia para leitura infalível de números e títulos.
- **Slate Secondary** (`#465468` no Claro / `#C6D0DC` no Escuro): Rótulos, metadados e subtítulos de suporte.
- **Slate Muted** (`#5A6B82` no Claro / `#94A2B8` no Escuro): Unidades de medida (R$, kg, %), placeholders e datas de atualização.
- **Surface Canvas** (`#FFFFFF` e `#F6F9FC` no Claro / `#171C28` e `#141B29` no Escuro): Superfícies de cards e gavetas de controle.
- **Precision Border** (`#DCE3EC` no Claro / `#1F2532` no Escuro): Delimitação cirúrgica de quadrantes analíticos.

### Status (KPI Performance)
- **Positive / Above Target** (`#15803D` Claro / `#4ADE80` Escuro, Soft: `#DCFCE7`): Atingimento de meta ≥ 100% ou crescimento positivo.
- **Warning / Near Target** (`#B45309` Claro / `#FBBF24` Escuro, Soft: `#FEF3C7`): Atingimento entre 90% e 99.9%.
- **Negative / Off Target** (`#B91C1C` Claro / `#FCA5A5` Escuro, Soft: `#FEE2E2`): Desvio de meta < 90% ou queda de performance.

### Named Rules
**The Purpose-Driven Blue Rule.** O azul primário e acentos coloridos são reservados estritamente para elementos interativos, seleções ativas e indicadores de foco analítico, nunca para preenchimentos ornamentais ou fundos estáticos.

**The Semantic Status Rule.** Cores de semáforo (verde, amarelo e vermelho) só podem ser empregadas quando houver relação direta com meta ou status de pedido (Faturado, Carteira, Cancelado). Nenhum elemento decorativo neutro pode usar essas cores.

## Typography

**Display Font:** `Inter` (com fallback para `'Segoe UI', system-ui, -apple-system, sans-serif`)
**Body Font:** `Inter` (com fallback para `'Segoe UI', system-ui, sans-serif`)
**Label/Numbers:** `Inter` com formatação tabular numérico (`font-variant-numeric: tabular-nums`)

**Character:** A tipografia é técnica, altamente legível e desenhada para densidade de dashboards executivos, garantindo clareza numérica imediata e escaneabilidade em qualquer escala.

### Hierarchy
- **Display** (800, `clamp(2rem, 4vw, 2.75rem)`, line-height 1.15): Títulos de impacto institucional na Home/Portal.
- **Headline** (700, `1.5rem` / 24px, line-height 1.25): Títulos de página e totalizadores principais de Vendômetro.
- **Title** (600, `1.05rem` / 17px, line-height 1.35): Títulos de cards de KPI, cabeçalhos de quadrantes e seções de filtros.
- **Body** (400 / 500, `13px`, line-height 1.5): Textos correntes, células de tabelas dinâmicas, opções de seleção e documentação.
- **Label** (700, `11px`, letter-spacing `0.04em`, uppercase): Eyebrows, badges de canal/regional, tags de status e títulos de eixos gráficos.

### Named Rules
**The Tabular Numbers Rule.** Todo e qualquer valor monetário (R$), quantitativo de caixas/toneladas (kg) ou percentual de cobertura (%) deve renderizar com dígitos tabulares para garantir alinhamento vertical perfeito em tabelas e cards.

**The Label Case Rule.** Rótulos de categorização e metadados auxiliares utilizam tipografia caixa-alta compacta (11px) com tracking expandido (`0.04em`) para rápida diferenciação em relação ao conteúdo numérico.

## Layout

O ecossistema é baseado em um modelo estruturado com grid de 12 colunas e painel lateral ancorado:

- **Desktop Widescreen (≥ 1280px):**
  - Cabeçalho global fixo no topo com altura de 64px (`--topo: 64px`).
  - Painel lateral de filtros multidimensionais com 320px de largura (`--fp-aberto: 320px`), recolhível para trilho vertical de 48px (`--fp-recolhido: 48px`).
  - Grid de conteúdo de 12 colunas (`.vend-grid-12`) com gap uniforme de 16px. No Vendômetro: 8 colunas para gráficos/tabelas analíticas e 4 colunas para detalhamento/rankings.
  - Grade de KPIs executivos com 5 colunas distribuídas horizontalmente (`grid-template-columns: repeat(5, minmax(0, 1fr))`).
- **Tablet / Médio (641px – 900px):**
  - Grade de KPIs reorganizada em 2 colunas com quebra equilibrada.
  - Filtros recolhidos por padrão com abertura em drawer sobreposto.
- **Mobile (≤ 640px):**
  - Navegação superior migra para barra inferior fixa de 56px (`.dna-mobile-nav`) com suporte a safe-area.
  - KPIs dispostos em coluna única empilhada com leitura imediata.
  - Filtros operam via gaveta de tela cheia (bottom sheet / modal gaveta) com botões táteis de altura mínima de 44px.

## Elevation & Depth

O sistema adota uma filosofia de camadas tonais sutis (*Layered Tonal*). A profundidade é comunicada pela sobreposição ordenada de superfícies e pelo contraste fino de bordas (`border: 1px solid var(--border)`), mantendo o layout nítido e estável.

### Shadow Vocabulary
- **Card Rest & Structure** (`box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 4px 16px rgba(15,23,42,.06)` Claro / `0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35)` Escuro): Utilizado em cards de métricas, banners e painéis para criar descolamento suave do fundo da página.
- **Elevated Overlay & Menus** (`box-shadow: 0 12px 32px rgba(15,23,42,.18)` Claro / `0 16px 40px rgba(0,0,0,.55)` Escuro): Utilizado exclusivamente para dropdowns de usuário, modais, tooltips de gráficos e gavetas de filtros.

### Named Rules
**The Grounded Elevation Rule.** Superfícies analíticas permanecem contidas e estáveis ao repouso. Sombras pronunciadas são restritas a elementos temporários flutuantes (menus e drawers).

## Shapes

O sistema de formas equilibra precisão técnica corporativa com cantos amigáveis e ergonômicos:

- **Controles e Entradas (`--r-control: 8px`):** Botões, inputs de texto, seletores de filtro e abas de navegação.
- **Containers e Superfícies (`--r-card: 14px`):** Cards de KPI, banners executivos, modais e o painel de filtros lateral.
- **Pills e Badges (`--r-pill: 999px`):** Indicadores de status de pedido, badges de QSR, contadores de filtros ativos e tags institucionais.
- **Bordas Estruturais:** Traço contínuo fino de 1px com cor tokenizada (`--border`), sem chanfros ou cantos pontiagudos.

## Components

### Buttons
- **Shape:** Raio de 8px (`--r-control`), altura padrão de 40px (desktop) e 44px (touch/mobile).
- **Primary (`.btn-primario`):** Fundo `var(--primary)` (#2563EB), texto branco, peso 600, padding `0 14px`. Hover escurece para `var(--primary-strong)` (#1D4ED8). Estado desabilitado em `var(--surface-alt)` com texto atenuado.
- **Secondary (`.btn-secundario`):** Fundo `var(--surface)`, borda de 1px em `var(--border-input)`, texto `var(--text-primary)`. Hover com fundo `var(--surface-hover)`.
- **Ghost / Fantasma (`.btn-fantasma`):** Fundo transparente, texto em cor de link (`var(--link)`), hover suave. Usado para "Limpar tudo" e ações terciárias.
- **Icon Button (`.btn-icone`):** Botão quadrado (40x40px) centralizado em grid, sem borda em repouso, hover em `var(--surface-hover)`.

### Chips & Badges
- **Brand Pill (`.dna-brand-badge`, `.sp-qsr-pill`):** Pílula compacta com padding `3px 8px`, tipografia 11px negrito, fundo em `var(--primary-soft)` com borda fina em tom de azul.
- **Counter Pill (`.contador`):** Pílula circular/oval com altura de 20px, fundo no azul primário e texto branco, indicando contagem de seleções ativas no painel de filtros.

### Cards / Containers
- **KPI Card (`.sp-kpi-card`):** Raio de 14px, fundo `var(--surface)`, borda `1px solid var(--border)`, padding interno de 1.15rem (~18px), min-height 120px. Cabeçalho com título compacto em 11px uppercase e valor numérico proeminente.
- **Executive Banner (`.sp-banner`):** Bloco horizontal com raio de 14px, combinando headline de impacto executivo à esquerda e toggle segmentado de métrica à direita.

### Segmented Metric Toggle (`.sp-metric-pill`)
- **Structure:** Container com borda fina e fundo `var(--surface-alt)`, contendo botões-pílula (`.sp-pill-btn`).
- **State:** O botão ativo recebe fundo `var(--primary)` com texto branco; o inativo mantém texto `var(--text-muted)` sobre fundo transparente.

### Inputs / Fields
- **Filter Search (`.fp-busca`):** Altura de 36px (44px no mobile), padding lateral de 10px, raio de 8px, borda em `var(--border-input)`, fundo `var(--surface-alt)`.
- **Option Row (`.fp-opcao`):** Item de seleção com checkbox nativo com `accent-color: var(--primary)`, hover com preenchimento em `var(--surface-hover)` e link de atalho "somente" visível no hover/foco.

### Navigation
- **Header Global (`.dna-header`):** Barra sticky de 64px com logotipo institucional Bimbo/DNA, abas centrais de navegação (`.dna-nav-tab`) com indicador de página ativa via fundo `var(--primary-soft)` e menu do usuário à direita.
- **Bottom Navigation Mobile (`.dna-mobile-nav`):** Barra inferior fixa com 3 itens em grid de distribuição simétrica, ícones de 20px e labels de 11px.

## Do's and Don'ts

### Do:
- **Do** manter a altura dos controles clicáveis em no mínimo 44px em ambientes touch/mobile.
- **Do** aplicar `tabular-nums` em todas as colunas de tabelas e valores numéricos de KPIs.
- **Do** preservar a proporcionalidade estrita dos logotipos SVG (máximo 16px na barra de abas e 32px no cabeçalho).
- **Do** utilizar as variáveis de cores semânticas (`--success`, `--warning`, `--danger`) exclusivamente para status e metas de negócio.
- **Do** suportar nativamente ambos os temas (`data-theme="dark"` e `data-theme="light"`), respeitando a transição de contraste.

### Don't:
- **Don't** aplicar gradientes multicoloridos ou fundos vibrantes por trás de números analíticos de faturamento ou budget.
- **Don't** inventar cores de acento avulsas fora dos tokens corporativos Bimbo QSR.
- **Don't** quebrar o alinhamento da grade de 12 colunas com margens assimétricas ou posicionamentos arbitrários.
- **Don't** remover a delimitação sutil de borda (1px) dos cards e blocos de conteúdo.
- **Don't** exibir sombras pesadas, difusas ou coloridas em elementos no estado de repouso.
