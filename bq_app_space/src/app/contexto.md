# Contexto de Alterações

Este arquivo registra todas as alterações efetuadas no projeto Space Databricks de forma a documentar o histórico do desenvolvimento.

## Histórico de Alterações (14/07/2026)

### 1. Correção da Busca Global nas Páginas de Áreas
- **Arquivos modificados**:
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/app.py): Rota `/area/<area_key>` atualizada para enviar a lista de dashboards (`dashboards=all_dashboards`) para o template.
  - [area.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/templates/area.html): Adicionada a lista `#search-suggestions` ao input de busca e injetado o array `window.ALL_DASHBOARDS`.
  - [script.js](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/static/js/script.js): Tratamento de clique nas sugestões adaptado para detectar qual versão do `openDashViewer` está na página (abertura por parâmetro na Home, ou por elemento DOM na área).

### 2. Acesso Livre ao Painel de Administração em Modo Local
- **Arquivos modificados**:
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/app.py): O decorator `@require_admin_group` foi ajustado para liberar acesso completo quando `LOCAL_MODE` estiver ativado no `.env`, ignorando a verificação de cabeçalhos de autenticação do Databricks/Azure AD.

### 3. Sistema Ocultar / Exibir (Dashboards, Apps e Áreas)
- **Arquivos modificados**:
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/app.py):
    - Coluna/campo `hidden` inserido no esquema do banco (PostgreSQL) e no snapshot de memória local.
    - Criados os métodos helper `db_toggle_item_visibility` e `db_toggle_area_visibility` e rotas correspondentes `/admin/toggle-item` e `/admin/toggle-area`.
  - [admin.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/templates/admin.html): Adicionada coluna "Visível" com botões de olho (👁️/👁️‍f) na tabela de componentes e seção "Visibilidade das Áreas".
  - [style.css](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/static/css/style.css): Adicionados estilos para linhas esmaecidas (`row-hidden`) e badges de itens ocultos.

### 4. Layout de Abas no Painel de Administração
- **Arquivos modificados**:
  - [admin.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/templates/admin.html): Criadas abas "Componentes" e "Áreas" para encolher a rolagem vertical da página, alternadas via JavaScript.
  - [style.css](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/static/css/style.css): Adicionada estilização premium para `.admin-tabs`, botões e painéis ativos.

### 5. Estilização dos Quadrantes e Remoção de Sidebar nas Áreas
- **Arquivos modificados**:
  - [area.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/templates/area.html):
    - Ocultada a barra lateral global da direita (`apps-sidebar`) nas telas de área.
    - Adicionado condicional Jinja para renderizar apenas quadrantes (Applications/Dashboards) que possuam dados.
  - [style.css](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/static/css/style.css):
    - Removidos resets de background do botão de dashboard (`button.db-card-btn`) permitindo que herde o fundo cinza de `.area-card`.
    - Adicionados estilos para a classe `.single-column` para centralizar e ajustar largura caso apenas um quadrante esteja ativo na tela.

### 6. Criação de Áreas e Configuração de KPIs Gerais
- **Arquivos modificados**:
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/app.py):
    - Cadastrada a área `geral` em `DEFAULT_AREA_DATA` para atuar como semente e poder ser oculta pelo admin.
    - Criada a função `db_add_area` e a rota `/admin/add-area` (POST) para gerenciar o cadastro de novas áreas pelo painel administrativo.
  - [index.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/templates/index.html):
    - O card "General KPIs" da Home e do Suggested foi convertido para utilizar `onclick` com `openDashViewer()`, abrindo a URL `https://prioridades-bb-8674310331778219.19.azure.databricksapps.com` em formato iframe na mesma tela (sem abrir nova aba).
    - O grid estático de 16 áreas foi reescrito para um laço Jinja dinâmico sobre `area_options`, permitindo a exibição automática de áreas recém-criadas na administração.
  - [admin.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/templates/admin.html): Inserido o formulário "Nova Área" no painel da aba "Áreas", exibido em duas colunas ao lado do grid de visibilidade.

### 7. Renomeação de KPIs Gerais para Operational Discipline
- **Arquivos modificados**:
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/app.py): Título do dashboard da área geral alterado de "KPIs Gerais" para "Operational Discipline" e chave alterada para `operational_discipline`.
  - [script.js](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/static/js/script.js): Tradução da chave `general_kpis` atualizada para retornar "Operational Discipline" em português, inglês e espanhol.
  - [index.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/templates/index.html): Atualizadas as referências estáticas, parâmetros de chamada à função `openDashViewer` e textos de fallback do card para "Operational Discipline".

### 8. Persistência do Estado das Abas de Administração
- **Arquivos modificados**:
  - [admin.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/templates/admin.html): Modificado o controlador de abas para armazenar no `localStorage` a aba ativa sob a chave `admin_active_tab` e restaurá-la automaticamente no carregamento da página. Isso corrige o bug de resetar a aba após exibir/ocultar ou criar uma nova área.

### 9. Tradução Completa (i18n) e Responsividade do Painel de Administração
- **Arquivos modificados**:
  - [script.js](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/static/js/script.js): Adicionadas todas as chaves de tradução da página de administração em português, inglês e espanhol. Adicionado suporte dinâmico no `setLanguage` para traduzir o placeholder do input de busca, placeholders dos formulários (`placeholderTargets`), textos descritivos (`data-i18n-html`) e tooltips de botões (`data-i18n-title`).
  - [admin.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/templates/admin.html): Vinculadas as tags `data-i18n`, `data-i18n-html` e `data-i18n-title` em todas as strings estáticas (títulos, formulários, tabelas, descrições, status dinâmicos, tooltips de botões e placeholders) do painel administrativo.
  - [style.css](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/static/css/style.css): Adicionada a propriedade `flex-wrap: wrap;` nas abas administrativas (`.admin-tabs`) para evitar quebra de layout em telas pequenas. Adicionada limitação de largura e truncamento por elipse de links longos (`.table-link-preview` com `text-overflow: ellipsis; max-width: 100%` e `.td-link` com `max-width: 250px`), além de ajustar as colunas do `.admin-grid` para usar `minmax(0, ...)` a fim de possibilitar scroll horizontal interno na tabela de componentes cadastrados no celular.

### 10. Alinhamento e Organização Visual do Layout Responsivo (Mobile)
- **Arquivos modificados**:
  - [style.css](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/static/css/style.css):
    - Configurado `.cards-horizontal` para usar `display: grid` com `grid-template-columns: repeat(auto-fill, minmax(130px, 1fr))` no mobile, garantindo que os cards de dashboards tenham o mesmo tamanho de coluna (simetria perfeita).
    - Ajustado o card `.tile-card` para remover `max-width` no mobile, evitando que cards fiquem alinhados com tamanhos desproporcionais e espaços vazios à direita.
    - Otimizada a `.topbar` no mobile para se dividir em duas linhas (primeira linha com logo à esquerda e botões/tema/idioma à direita; segunda linha com o input de busca ocupando 100% da largura), removendo o visual espremido e a quebra de texto do input.
    - Reconfigurados a `.drawer` e o `.drawer-overlay` para abrir a partir do topo (`top: 0`) no mobile, sobrepondo o cabeçalho como um menu de tela cheia nativo, eliminando qualquer dependência da altura dinâmica da topbar.

### 11. Preparação para Deploy no Databricks Apps (Waitress & yml)
- **Arquivos modificados**:
  - [requirements.txt](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/requirements.txt): Adicionada dependência do servidor WSGI de produção `waitress`.
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/app.py): Configurada a execução padrão do WSGI server `waitress` no bloco `__main__`.
  - [databricks.yml](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/databricks.yml): Inserida a propriedade `root_path` apontando para `/Shared/Databricks_Apps/Space_Databricks/dev` e desativada a diretiva `mode: development` para permitir o deploy em diretórios compartilhados de produção do workspace.

### 12. Validação de Acesso Administrativo por Tabela de E-mails
- **Arquivos modificados**:
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/app.py):
    - Adicionado a tabela `space_portal.admin_users` no schema `CREATE_SCHEMA_SQL`.
    - Adicionado seeding automático de e-mails em `ensure_schema()` (`vitor.saes@grupobimbo.com` e `bruno.fellipe@grupobimbo.com`).
    - Criada a função `check_admin_email()` para buscar no banco de dados (ou na lista estática local se em `LOCAL_MODE`).
    - Atualizados `is_current_user_admin()` e o decorator `@require_admin_group` para realizar a validação com base no e-mail do usuário.
  - [admin_users.sql](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/admin_users.sql) [NEW]: Criado script SQL para provisionamento manual e carga inicial dos administradores no Databricks SQL ou PostgreSQL.

### 13. Validação de Grupos via Autenticação OBO (On-Behalf-Of)
- **Arquivos modificados**:
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/app.py):
    - Refatorada a função `get_user_groups_from_obo(obo_token)` para consultar diretamente o Microsoft Graph API (`/v1.0/me/transitiveMemberOf`) utilizando o token Bearer OBO do próprio usuário logado (`x-forwarded-access-token`), sem necessidade de credenciais de Service Principal / App Registration (`AZURE_CLIENT_ID`/`SECRET`).
    - Mantido o fallback para a API de SCIM do Databricks (`WorkspaceClient().current_user.me()`).
    - Atualizada a função `get_current_user_groups()` para ler tokens OBO dos cabeçalhos HTTP, `x-forwarded-groups`, ou usar simulação no desenvolvimento local.
    - Atualizada a rota de diagnóstico `/api/azure-status` para exibir o status do token OBO.

### 14. Liberação do Acesso a Áreas Restritas e Limpeza do Painel Administrativo
- **Arquivos modificados**:
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/app.py):
    - Modificada a função `user_has_access(required_group)` para retornar sempre `True`. Com isso, o bloqueio de áreas restritas por grupos foi desativado e todas as áreas, dashboards e aplicativos do portal ficam livres e acessíveis a todos os usuários sem redirecionamento para `area_403.html`.
  - [admin.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/templates/admin.html):
### 15. Remoção da Conexão e Notificação via Microsoft Teams
- **Arquivos modificados**:
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/app.py):
    - Removida a função `send_teams_notification()` e a variável de ambiente `TEAMS_WEBHOOK_URL`. A rota `/request-access` passa a gravar as solicitações apenas na base de dados/cooldown sem realizar envios via Webhook para o Teams.
### 16. Correção do NameError: ensure_schema is not defined
- **Arquivos modificados**:
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/app.py):
    - Recriada e implementada a função `ensure_schema()` para inicialização e migração segura do esquema PostgreSQL/Lakebase (`space_portal`).
    - Atualizado o script SQL `CREATE_SCHEMA_SQL` para incluir a tabela `space_portal.access_requests` e colunas `tagline` e `about` na tabela `space_portal.area`.
    - Adicionado suporte a *auto-seeding* inicial dos e-mails de admin (`space_portal.admin_users`), áreas padrão (`DEFAULT_AREA_DATA`) e aplicativos da sidebar (`DEFAULT_SIDEBAR_APPS`) caso as tabelas estejam vazias durante a primeira execução no Databricks Apps.

### 17. Correção na Exibição da Sidebar e do Digital Maturity das Áreas
- **Arquivos modificados**:
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/app.py):
    - Refatoradas as funções `load_data()` e `db_save_digital_maturity()` para realizar *parse* defensivo de JSON (caso a coluna `about` do banco de dados retorne como `string`) e mesclagem (*merge*) profunda com a estrutura de `about` padrão (`DEFAULT_AREA_DATA`).
    - Isso impede que a atualização do `digital_maturity` sobrescreva ou apague os 3 pilares estratégicos (`pillars`), descrição e estatísticas da área.
  - [area.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks/templates/area.html):
    - Tornadas as buscas por dimensões no gráfico de radar insensíveis a acentos (ex: `Adoção` vs `Adocao`, `Capacitação` vs `Capacitacao`).

### 19. Consulta de Cargo e Sugestão Dinâmica de Dashboards (Unity Catalog KNN)
- **Arquivos modificados**:
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks_2/Space_Databricks/dev/files/app.py):
    - Implementada a função `_exec_databricks_sql()` utilizando `databricks-sdk` (`WorkspaceClient().statement_execution`) para consultar tabelas do Databricks SQL Warehouse.
    - Criada a função `get_user_suggested_dashboards(user_email, all_dashboards)` que:
      1. Consulta `cat_dnabb_dv.grobbjrnl_cz.colaboradores` filtrando por `COLAB_EMAIL` para obter o `CARGO`.
      2. Consulta `cat_dnabb_dv.grobbjrnl_cz.sugestao_dashboards_knn` filtrando por `CARGO` (ou `COLAB_EMAIL`) para selecionar os relatórios `RELATORIO_1`, `RELATORIO_2`, `RELATORIO_3` e `RELATORIO_4`.
      3. Faz a associação dos nomes sugeridos com a lista de dashboards cadastrados no portal Space.
      4. Implementa cache em memória (TTL de 5 min) e fallback gracioso para modo local ou caso o usuário não seja encontrado.
    - Atualizada a rota `index()` para passar `suggested_dashboards` ao template.
  - [index.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks_2/Space_Databricks/dev/files/templates/index.html):
    - Quadrante "Dashboards Sugeridos" atualizado para renderizar dinamicamente a lista de relatórios sugeridos via laço Jinja `{% for dash in suggested_dashboards %}` com suporte completo a favoritos e modal iframe.
  - [app.yaml](file:///c:/Users/vitor.saes/Downloads/Space_Databricks_2/Space_Databricks/dev/files/app.yaml):
    - Adicionada a variável de ambiente opcional `DATABRICKS_WAREHOUSE_ID`.

### 20. Otimização de Layout para Zoom do Windows (125% DPI Scale)
- **Arquivos modificados**:
  - [style.css](file:///c:/Users/vitor.saes/Downloads/Space_Databricks_12-08/Space_Databricks/dev/files/static/css/style.css):
    - Reduzido o gatilho `min-height` da `@media (min-width: 1200px) and (min-height: 850px)` para `min-height: 600px`. Em monitores Full HD (1080p) com zoom do Windows em 125%, a altura útil da janela de navegação fica em torno de ~720px. Ao ajustar para 600px, o layout fixo sem rolagem vertical global é ativado corretamente nessas resoluções.
    - Configurado `grid-template-rows: repeat(4, 1fr)` em `body.home-page-body .cards-grid-4` (substituindo o antigo `align-content: start`). Agora as 4 linhas do grid de Áreas se distribuem proporcionalmente preenchendo 100% da altura do contêiner sem sobras de espaço em branco no fundo.
    - Corrigido o cálculo de altura da caixa de Favoritos no Mobile (`@media (max-width: 1200px)`): A regra `flex: 0 1 340px` (que em alinhamento vertical `flex-direction: column` forçava 340px de altura) foi isolada apenas para telas Desktop (`min-width: 1201px`). No mobile, a seção passou a usar `flex: 0 0 auto !important; height: auto !important;`, tornando a caixa compacta e ajustada apenas ao seu conteúdo real.

### 21. Correção de Quebra e Corte Vertical na Barra de Favoritos
- **Arquivos modificados**:
  - [style.css](file:///c:/Users/vitor.saes/Downloads/Space_Databricks_12-08/Space_Databricks/dev/files/static/css/style.css):
    - Corrigida a quebra vertical (`flex-wrap: wrap`) no contêiner `#favorites-container`: agora utiliza `flex-wrap: nowrap` e rolagem horizontal suave (`overflow-x: auto; overflow-y: hidden; max-height: none`), eliminando qualquer possibilidade de cards ficarem cortados pela metade na parte inferior ao ultrapassar 2 favoritos.
    - Ajustado o dimensionamento da `.favorites-section` e `.suggested-section` para `flex: 1 1 0` com `overflow: hidden` e `flex-wrap: nowrap` nos cards de sugestões (`.suggested-section .cards-horizontal`), eliminando qualquer vazamento/sobreposição de cards de Dashboards Sugeridos sobre a seção de Favoritos.
    - Adicionada estilização refinada para a barra de rolagem horizontal em `#favorites-container`.
  - [script.js](file:///c:/Users/vitor.saes/Downloads/Space_Databricks_12-08/Space_Databricks/dev/files/static/js/script.js):
    - Adicionado suporte a rolagem horizontal via *mouse wheel* em `#favorites-container`.
    - Ajustada a renderização de favoritos para exibir até 9 favoritos na barra (`slice(0, 9)`).
    - Adicionadas traduções multilíngues (`pt`, `en`, `es`) para a mensagem de favoritos vazios (`no_favorites_text`) e exportado o dicionário de traduções globalmente (`window.SPACE_TRANSLATIONS`).
  - [index.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks_12-08/Space_Databricks/dev/files/templates/index.html):
    - Incrementada a versão do cache buster de CSS e JS (`?v=20260819_04`) para garantir que os navegadores de todos os usuários recebam as novas regras imediatamente sem cache residual.

### 22. Fixação da Imagem Estática do App Radar Bimbo no Código
- **Arquivos modificados**:
  - [static/images/radar_bimbo.png](file:///c:/Users/vitor.saes/Downloads/Space_Databricks_12-08/Space_Databricks/dev/files/static/images/radar_bimbo.png): Salvo o logo oficial em alta resolução diretamente como arquivo estático versionado no repositório.
  - [templates/index.html](file:///c:/Users/vitor.saes/Downloads/Space_Databricks_12-08/Space_Databricks/dev/files/templates/index.html): Atualizada a tag `<img>` do card do Radar Bimbo para apontar diretamente para `url_for('static', filename='images/radar_bimbo.png')`, garantindo que o logo seja sempre carregado diretamente do código sem depender de upload temporário.
  - [app.py](file:///c:/Users/vitor.saes/Downloads/Space_Databricks_12-08/Space_Databricks/dev/files/app.py): Adicionado `radar_bimbo` na lista nativa `DEFAULT_SIDEBAR_APPS` com o link oficial e ícone estático, garantindo a persistência do app no deploy do Databricks e no seed inicial do banco Lakebase.
  - [local_sidebar_apps.json](file:///c:/Users/vitor.saes/Downloads/Space_Databricks_12-08/Space_Databricks/dev/files/local_sidebar_apps.json): Atualizado o arquivo de apps locais para usar `radar_bimbo` com o caminho estático `/static/images/radar_bimbo.png`.
