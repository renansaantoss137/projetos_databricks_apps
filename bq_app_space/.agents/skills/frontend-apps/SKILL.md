---
name: frontend-apps
description: Criar ou reformular o frontend de apps web (dashboards, portais, ferramentas internas) com identidade D&A, adaptação real a celular/tablet/desktop e sem alterar regras de negócio. Não usar para tarefas só de backend ou ETL.
---

# Frontend de apps D&A

Entregue o frontend implementado, não só uma proposta, com acabamento de produto profissional: identidade coerente, leitura rápida e uso confortável em celular, tablet e desktop, sem mudar o que o app faz.

## Arquivos de apoio

Ficam nesta mesma pasta. Leia cada um quando o gatilho ocorrer:

| Arquivo | Leia quando |
|---|---|
| `identidade-da.md` | For criar um app, o app não tiver identidade própria ou o pedido citar o padrão D&A |
| `filtros-referencia.html` | Houver painel de filtros. É implementação de referência: copie o comportamento |
| `grafico-referencia.html` | Houver gráfico de barras com comparação (vs meta, budget ou ano anterior). Copie a estrutura |
| `obo-databricks-apps.md` | O pedido envolver OBO ou permissão por usuário. É backend: só com pedido explícito |
| `dashboards-swd.md` | Houver gráficos, KPIs, scorecards ou tabelas analíticas |
| `checklist-responsivo.md` | Antes de concluir qualquer entrega |

Se algum não estiver disponível, siga este documento e informe a ausência na entrega.

## 1. Classifique o pedido

- **Criar:** app novo. Defina telas, navegação, direção visual e tokens antes de escrever componentes. Use a identidade D&A, salvo briefing diferente.
- **Reformular:** app existente com nova direção visual. Mantenha marca obrigatória, conteúdo factual e comportamento.
- **Refinar:** app existente, mesma identidade. Corrija hierarquia, consistência, responsividade e acessibilidade sem mudar a cara do produto.

Se o pedido ficar entre reformular e refinar, trate como refinar e diga isso no diagnóstico.

Classifique também a finalidade de cada tela, porque ela decide densidade e expressão:

- **Operar** (dashboards, formulários, configurações, ferramentas): leitura rápida, controles familiares, conclusão da tarefa. O acabamento aparece em precisão e consistência.
- **Ler** (conteúdo, ajuda, documentação): hierarquia editorial, linhas de 60 a 80 caracteres, orientação na navegação.
- **Decidir** (aprovação, comparação de opções, apresentação): mensagem, evidência e uma ação principal.
- **Explorar** (catálogos, galerias): o conteúdo lidera e os controles ficam discretos.

## 2. Entenda antes de construir

**App existente:**
- Descubra stack, rotas, navegação, componentes compartilhados, tokens e temas, e a camada de dados (endpoints, data layers JS, arquivos de configuração).
- Rode e observe o estado atual quando o ambiente permitir. Diferencie o que está documentado do que você inferiu.
- Critique a interface antes de mexer: o que atrapalha a tarefa principal de cada tela.
- Respeite alterações preexistentes do usuário e o escopo pedido.

**App novo:**
- Defina público, tarefa principal de cada tela e dispositivo predominante (ex.: gestor consultando no celular × analista operando no desktop).
- Confirme a fonte dos dados e o contrato (formato, campos, unidades) antes de desenhar a tela.
- Liste telas e navegação antes de codar.

Pergunte só quando a resposta mudar materialmente o trabalho e não estiver no projeto. Enquanto isso, avance nas partes independentes.

## 3. Referências e critérios de aceite

Instruções como "siga o padrão do app X" são a maior causa de retrabalho. O usuário não deve precisar repetir pedidos.

- **A referência precisa ser legível.** URL de app do Databricks exige login, e você não consegue abri-la. Para seguir outro app, use o código-fonte dele (no repositório ou numa pasta indicada), capturas fornecidas ou as especificações desta skill. Sem nenhum desses, pare e peça o material. Nunca reconstrua a referência de memória.
- **Componentes da skill são copiados no comportamento.** Painel de filtros → `filtros-referencia.html`; barras com comparação → `grafico-referencia.html`; trilho de navegação, menu do app, Home institucional e demais componentes → `identidade-da.md`. Adapte só a sintaxe ao framework do app. Mudar o comportamento exige pedido explícito.
- **Antes de codar, transforme o pedido em requisitos numerados e verificáveis** (R1, R2…): um para cada coisa que o usuário pediu, mais os critérios do componente de referência usado. Mostre a lista no diagnóstico.
- **Antes de entregar, preencha a matriz de conformidade** (`checklist-responsivo.md`, seção D):
  - cada requisito recebe status (atendido, não atendido ou bloqueado), onde foi implementado (arquivo e trecho) e como foi verificado;
  - requisito sem status, ou "não atendido" sem motivo, impede a conclusão. Corrija antes de entregar.
- **No final, releia o pedido original** e compare com a matriz.

## 4. Proteja o produto

O trabalho é apresentação e interação. Regras de negócio pertencem ao app.

- Preserve cálculos, validações, permissões, autenticação, RLS e perfis de acesso, integrações, persistência, filtros, rotas públicas e significado dos dados.
- Não duplique lógica de negócio no frontend nem crie implementações separadas para mobile e desktop.
- Não substitua dados reais por mocks. Dados fictícios só em demonstração claramente identificada.
- Não apresente botão, filtro ou link sem funcionamento.
- Não altere backend, configuração de deploy (ex.: `app.yaml`), permissões ou dependências por motivo visual.
- Autenticação e autorização (ex.: OBO) só mudam quando o pedido disser isso explicitamente, e então seguindo `obo-databricks-apps.md`.
- Em apps orientados a configuração (regras em JSON, tabelas de parâmetros, data layers separados), mantenha a separação: a interface lê a configuração, nunca a troca por valores fixos.
- **Regressão de dados é falha grave.** Depois da reformulação, cada tela mostra, para os mesmos filtros, os mesmos valores de antes, sem erro no console. Um erro de script que derruba a tela inteira (filtros sem campos, KPIs "--") não pode chegar à entrega.
- Preserve os estados de carregamento, vazio, erro e recuperação. Uma mudança de fluxo mantém todas as capacidades e um caminho claro até cada uma.

## 5. Respeite o framework

- **HTML/JS autocontido:** um arquivo, sem build. Tokens em custom properties. Bibliotecas por CDN com versão fixa, nunca `@latest`. Não introduza framework.
- **Flask/FastAPI com templates:** tokens e componentes num CSS base compartilhado pelos templates. Preserve as rotas e o contexto passado a cada template.
- **Streamlit/Dash/Gradio:** use primeiro o tema nativo (ex.: `.streamlit/config.toml`, pasta `assets/` no Dash) e os layouts do framework. Evite CSS preso a classes internas geradas, que quebra em upgrade. Quando o framework limitar o resultado, diga o que não foi possível.
- **React/Vue com build:** siga a estrutura de componentes, o design system e as convenções existentes.

## 6. Direção visual

**Referências de qualidade.** Busque as qualidades abaixo conforme a afinidade com a tarefa da tela. Não transplante o padrão de um tipo de app para outro (ex.: feed num app de comparação tabular).
- *Financeiro:* valores monetários com destaque e alinhamento impecável; confirmação clara antes e depois de cada ação; estado de cada operação inequívoco.
- *Mensageria:* campo de envio sempre alcançável, inclusive com teclado aberto; histórico que preserva a posição; feedback imediato de envio.
- *Conteúdo:* a mídia lidera; controles discretos; poucos destinos na navegação inferior.
- *Ferramenta operacional:* densidade útil, filtros previsíveis, tabelas legíveis, ações em lote quando o app já as tiver.

Se o usuário fornecer imagens ou URLs de referência, analise composição, densidade, hierarquia, navegação e estados, e registre a origem. Não alegue ter visto o que não viu. Nunca copie logotipos, identidade ou telas de terceiros.

**Sistema.**
- Defina ou ajuste tokens para superfícies, texto, bordas, ação, status, tipografia, espaçamento e raios. Nenhuma cor, raio ou sombra fora dos tokens.
- Padronize botões, campos, filtros, listas, tabelas, menus, toasts e mensagens em todas as telas do escopo. Reutilize a biblioteca de ícones existente.
- Preserve o tema claro/escuro se o produto já oferecer os dois. Em apps novos, ofereça os dois.

**Hierarquia.**
- Uma pergunta principal por superfície: informação e estado primeiro, detalhe e edição sob demanda.
- Organize com espaçamento e tipografia antes de recorrer a cartões. Evite cartões aninhados, badges decorativos, ícone em todo bloco, títulos enormes em telas operacionais e grades repetitivas de cartões sem hierarquia.
- Escala tipográfica contida em telas operacionais. Números tabulares em valores comparáveis.
- O acabamento está nos detalhes: alinhamento de texto e ícones, espaço entre grupos, proporção dos controles, estados consistentes. Paleta nova sobre componentes desalinhados não conclui uma reformulação.

**Cor.**
- Cor de destaque para ação, seleção e o dado principal. Cores de status com significado fixo e sempre acompanhadas de texto ou ícone.
- Alerta só para o que exige atenção. Se tudo estiver vermelho, nada está.

**Efeitos.**
- A identidade D&A **não usa** gradiente em cartões, glassmorphism nem brilho decorativo. A única exceção é o brilho radial de fundo (`--bg-glow`) no tema escuro. Nenhum cartão recebe tratamento especial: destaque é borda `--primary` e elevação leve.
- Se a identidade de outro app exigir vidro ou gradiente: nunca atrás de texto, contraste medido contra o fundo mais desfavorável e fallback sólido para `backdrop-filter` e `prefers-reduced-transparency`.
- **Um tema por página, inteiro:** nenhum trecho com cor fixa de um tema enquanto os componentes usam o outro.

**Movimento.** Transições curtas (150 a 250 ms) para feedback e mudança de estado. Respeite `prefers-reduced-motion`. Telas operacionais dispensam animação de entrada.

**Texto.** No idioma do produto, com ações específicas ("Aprovar pedido", não "OK"). Erros dizem o que aconteceu e como continuar. Nunca invente métricas, depoimentos ou promessas.

## 7. Formatação regional

- Use o locale do produto: `pt-BR` para o Brasil, `es-CO` ou `es-MX` para Colômbia e México.
- Formate números, moeda, percentuais e datas com `Intl.NumberFormat` e `Intl.DateTimeFormat` no JS, ou com biblioteca de locale no backend (ex.: Babel em Python). Nunca concatene `"R$ " + valor` nem use `toFixed` para exibição.
- Defina as casas decimais de cada métrica. Para moeda usada sem centavos na prática (ex.: COP), use `maximumFractionDigits: 0`.
- Abreviações (mil, mi, bi) consistentes na tela e coerentes com o locale (`notation: 'compact'`).
- Diferencie variação percentual (%) de variação em pontos percentuais (p.p.).
- Datas no padrão do locale, nunca ambíguas. Mostre "Atualizado em" quando o dado não for em tempo real.

## 8. Adaptação responsiva

Adapte estrutura e fluxo, não só dimensões. Comece pela menor largura útil e acrescente complexidade conforme o conteúdo permite. Aproveite a arquitetura de CSS existente em vez de reescrevê-la.

- **Layout:** Grid/Flex com breakpoints guiados pelo conteúdo, sem larguras fixas que estourem a página. No desktop, limite largura e densidade úteis. Considere tablet e celular deitado.
- **Navegação:** no celular, barra inferior com até 5 destinos nomeados (ícone e rótulo) ou drawer com acesso explícito aos demais. No desktop, navegação lateral. Item só com ícone exige nome acessível e não pode depender de tooltip por hover.
- **Conteúdo:** não esconda funcionalidade essencial para caber. Use detalhes expansíveis e telas de detalhe para o secundário. Preserve filtros, seleção e posição ao navegar.
- **Filtros no celular:** botão "Filtros (n)" que abre um painel com Aplicar e Limpar, e chips dos filtros ativos visíveis na tela.
- **Tabelas:** viram lista ou cartões quando isso preservar comparação e significado. Tabelas realmente bidimensionais ganham rolagem horizontal localizada e perceptível, com primeira coluna fixa quando ajudar. Nunca use `overflow-x: hidden` na página como correção.
- **Toque:** alvos de cerca de 44 × 44 px nas ações comuns, com espaço entre eles. Nenhuma função depende só de hover ou de arrastar.
- **Campos:** 16 px no celular para evitar zoom automático, com o teclado adequado (`type`, `inputmode`).
- **Overlays:** modais, drawers e menus cabem na altura disponível, rolam por dentro e mantêm as ações visíveis. Trate teclado virtual, `safe-area` e barras fixas: o último conteúdo e o foco nunca ficam encobertos. Prefira `dvh` a `vh` em alturas de tela cheia.
- **Chat:** área de conversa preservada e campo de envio acessível com o teclado aberto.
- **Gráficos:** rótulos legíveis e valores exatos por toque, teclado ou tabela alternativa. Tooltip só de hover não atende o celular.
- **Imagens:** responsivas e com dimensões declaradas.

## 9. Acessibilidade

- HTML semântico, nomes acessíveis, labels, foco visível e ordem de teclado coerente.
- Menus e disclosures expõem o estado (`aria-expanded`). Overlays fecham com Esc, devolvem o foco e não ficam presos em ancestrais com `overflow`. Modais gerenciam o foco; disclosures não recebem comportamento modal.
- Contraste mínimo de 4,5:1 para texto normal e de 3:1 para texto grande e elementos gráficos essenciais. Não reduza contraste para deixar a tela "mais calma".
- Funcione com zoom de 200% e com reflow em 320 px de largura.

## 10. Execução

1. **Diagnóstico breve:** modo do pedido, problemas principais, direção escolhida, escopo e a lista de requisitos numerados. Avance com escolhas reversíveis, sem pedir aprovação a cada etapa.
2. **Sistema primeiro:** tokens e componentes compartilhados, depois as telas e os fluxos do escopo. Não pare na tela inicial quando o pedido cobrir o app inteiro.
3. **Verifique** com `checklist-responsivo.md`: renderizado quando o ambiente permitir, estático sempre, mais a **conferência de dados** (valores iguais aos de antes) e os **componentes compartilhados em todas as rotas** (menu, trilho, filtros).
4. **Rode** build, lint, verificação de tipos e testes que o projeto já tiver. Crie testes só para mudança de comportamento ou risco concreto de regressão, nunca testes que repetem estilos.
5. **Corrija** o que a verificação encontrar.
6. **Entregue:**
   - a matriz de conformidade preenchida, com todos os requisitos;
   - o que mudou e quais telas foram cobertas;
   - direção visual, tokens e padrões responsivos efetivamente implementados (atualize a documentação visual do projeto, se existir);
   - verificações executadas, separando renderizada, estática e pendente de teste manual;
   - limitações reais. Viewport emulado não é aparelho físico, Chromium não comprova Safari e captura não comprova gesto.

Não publique, não faça deploy (inclusive `databricks apps deploy` e `databricks bundle deploy`) e não altere serviços externos sem autorização explícita no pedido.
