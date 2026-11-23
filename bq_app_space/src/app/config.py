# ============================================================
# config.py — Inventário de dashboards do Space QSR
# Para adicionar/remover dashboards, edite SOMENTE este arquivo.
# ============================================================
#
# COMO OBTER A embed_url DE UM RELATORIO POWER BI:
# 1. Abra o relatorio no Power BI Service (app.powerbi.com)
# 2. Clique em Arquivo > Inserir relatorio > Site ou portal
# 3. Copie a URL gerada (formato: app.powerbi.com/reportEmbed?reportId=...&autoAuth=true&ctid=...)
# 4. Cole no campo "embed_url" abaixo
#
# A embed_url permite abrir o Power BI DENTRO do app (iframe).
# Se nao tiver embed_url, o dashboard abre em nova aba.
# ============================================================

AREAS = [
    {
        "id": "logistica",
        "nome": "Logística",
        "icone": "truck",
        "tagline": "Gestão logística e distribuição do Grupo Bimbo QSR",
        "pilares": [
            {"titulo": "Distribuição & Entregas", "descricao": "Gestão de rotas, rastreamento de entregas e otimização de frota."},
            {"titulo": "Performance Operacional", "descricao": "Indicadores de OTIF, Fill Rate e eficiência logística."},
            {"titulo": "Custos & Rentabilidade", "descricao": "Controle de custos de transporte, frete e rentabilidade por rota."},
        ],
    },
    {
        "id": "comercial",
        "nome": "Comercial",
        "icone": "briefcase",
        "tagline": "Inteligência comercial e gestão de vendas",
        "pilares": [
            {"titulo": "Vendas & Receita", "descricao": "Acompanhamento de vendas, metas e performance comercial."},
            {"titulo": "Clientes & Canais", "descricao": "Gestão de carteira de clientes e estratégia por canal."},
            {"titulo": "Pricing & Margem", "descricao": "Política de preços, margens e competitividade no mercado."},
        ],
    },
    {
        "id": "supply-chain",
        "nome": "Supply Chain",
        "icone": "link",
        "tagline": "Cadeia de suprimentos e planejamento de demanda",
        "pilares": [
            {"titulo": "Planejamento de Demanda", "descricao": "Forecast, S&OP e alinhamento entre produção e vendas."},
            {"titulo": "Gestão de Estoque", "descricao": "Níveis de estoque, giro e disponibilidade de produtos."},
            {"titulo": "Fornecedores & Compras", "descricao": "Relacionamento com fornecedores e eficiência em compras."},
        ],
    },
    {
        "id": "financas",
        "nome": "Finanças",
        "icone": "coins",
        "tagline": "Gestão financeira e controle orçamentário",
        "pilares": [
            {"titulo": "Resultado & P&L", "descricao": "Estado de resultados, receita líquida e análise de despesas."},
            {"titulo": "Orçamento & Forecast", "descricao": "Planejamento orçamentário e projeções financeiras."},
            {"titulo": "Tesouraria & Fluxo", "descricao": "Gestão de caixa, fluxo financeiro e capital de giro."},
        ],
    },
    {
        "id": "marketing",
        "nome": "Marketing",
        "icone": "trending-up",
        "tagline": "Marketing e performance de distribuidores",
        "pilares": [
            {"titulo": "Distribuidores & Trade", "descricao": "Performance de distribuidores e ações no ponto de venda."},
            {"titulo": "Campanhas & ROI", "descricao": "Efetividade de campanhas e retorno sobre investimento."},
            {"titulo": "Market Share & Marca", "descricao": "Participação de mercado e posicionamento de marca."},
        ],
    },
]

DASHBOARDS = [
    # --- Logística ---
    {
        "nome": "Painel Logístico",
        "area": "logistica",
        "url": "https://app.powerbi.com/reportEmbed?reportId=67e43992-3924-46c6-9528-464b40eda398&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
        "tipo": "powerbi",
        "icone": "truck",
    },
    {
        "nome": "Rentabilidade",
        "area": "logistica",
        "url": "https://app.powerbi.com/reportEmbed?reportId=c25fd9f2-8516-4a41-9a04-439d84853d61&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
        "tipo": "powerbi",
        "icone": "dollar-sign",
    },
    {
        "nome": "Painel de Projetos",
        "area": "logistica",
        "url": "https://app.powerbi.com/reportEmbed?reportId=dde8af11-8886-4dd4-8483-34ee3252b993&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
        "tipo": "powerbi",
        "icone": "clipboard-list",
    },
    {
        "nome": "Painel de Preços Equipes",
        "area": "logistica",
        "url": "https://app.powerbi.com/reportEmbed?reportId=99e45b11-0968-4203-a7d9-afb8dbb0a3a5&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
        "tipo": "powerbi",
        "icone": "tags",
    },
    {
        "nome": "Painel de Performance",
        "area": "logistica",
        "url": "https://app.powerbi.com/reportEmbed?reportId=3535a0a8-4f9c-4229-ab20-5b23651ed3a8&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
        "tipo": "powerbi",
        "icone": "gauge",
    },
    {
        "nome": "Painel de Preços",
        "area": "logistica",
        "url": "https://app.powerbi.com/reportEmbed?reportId=b1073f44-78b7-4b89-b72e-e72669ac8633&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
        "tipo": "powerbi",
        "icone": "tags",
    },
    {
        "nome": "Painel de Price Protocol",
        "area": "logistica",
        "url": "https://app.powerbi.com/reportEmbed?reportId=e5d9ae3c-3ab4-479a-a2e1-70d091b4f3f6&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
        "tipo": "powerbi",
        "icone": "file-text",
    },
    {
        "nome": "Logística CT-e",
        "area": "logistica",
        "url": "https://app.powerbi.com/reportEmbed?reportId=48248c1c-5d96-40c6-a0b2-f52153ebc77d&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
        "tipo": "powerbi",
        "icone": "file-text",
    },
    {
        "nome": "OTIF e Fill Rate",
        "area": "logistica",
        "url": "https://bq-oitf-fillrate-8674310331778219.19.azure.databricksapps.com/",
        "tipo": "databricks_app",
        "icone": "check-check",
    },
    # --- Comercial ---
    {
        "nome": "DNA de Vendas",
        "area": "comercial",
        "url": "https://app.powerbi.com/reportEmbed?reportId=c04ce17c-f4e8-4edd-a398-b88b0d920bfe&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
        "tipo": "powerbi",
        "icone": "bar-chart-3",
    },
    # --- Supply Chain ---
    {
        "nome": "Supply Chain",
        "area": "supply-chain",
        "url": "https://app.powerbi.com/reportEmbed?reportId=5de75719-aa8f-4d15-9697-061d073d780c&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
        "tipo": "powerbi",
        "icone": "link",
    },
    # --- Finanças ---
    {
        "nome": "Estado de Resultados",
        "area": "financas",
        "url": "https://app.powerbi.com/reportEmbed?reportId=568b9571-8aac-4377-83a6-7fc35b605735&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
        "tipo": "powerbi",
        "icone": "file-text",
    },
    # --- Marketing ---
    {
        "nome": "Performance de Distribuidores",
        "area": "marketing",
        "url": "https://app.powerbi.com/reportEmbed?reportId=93686707-57e1-4d67-9448-116f67f36d65&autoAuth=true&ctid=973ba820-4a58-4246-84bf-170e50b3152a",
        "tipo": "powerbi",
        "icone": "trending-up",
    },
]

# ============================================================
# APPS — Aplicativos exibidos na sidebar direita.
# Para ativar/desativar um app, altere o campo "ativo".
# ============================================================
APPS = [
    {
        "id": "fermenta",
        "nome": "Fermenta",
        "descricao": "",
        "url": "https://apps.powerapps.com/play/e/b6c0e096-cfa5-4bc7-bef0-da5c2d6cb2a2/a/9a134639-f29d-4867-affc-c15b8cf658c4?tenantId=973ba820-4a58-4246-84bf-170e50b3152a&hint=e330137b-933b-4432-8f94-201d3e1ef682&sourcetime=1764093426234&source=teamsLinkUnfurling",
        "estilo": "fermenta",
        "ativo": True,
    },
    {
        "id": "space-copilot",
        "nome": "Space Copilot",
        "descricao": "Space Copilot",
        "url": "",
        "estilo": "space-copilot",
        "ativo": False,
    },
]
