# Cockpit Logístico OTIF & Fill Rate

**Bimbo QSR Brasil** — Plataforma de monitoramento e diagnóstico de desempenho logístico.

---

## Visão Geral

Aplicação web que consolida indicadores de **Fill Rate** e **OTIF** (On Time In Full) para operações logísticas da Bimbo Brasil QSR. Permite a gestores identificar perdas, priorizar ações e tomar decisões em tempo real.

### Principais Funcionalidades

- **Painel Executivo**: KPIs, evolução mensal, Pareto de perdas, prioridades de ação
- **Fill Rate**: Visão mensal/semanal, breakdown por planta e grupo de cliente
- **Fill Rate Detalhe**: Drill-down até nível de pedido
- **OTIF**: Separação CIF/FOB, análise por transportadora, tempo de atraso
- **OTIF Detalhe**: Visão por remessa individual
- **Gestão de Pedidos**: Tabela completa com filtros avançados, paginação e busca

---

## Stack Técnica

| Camada | Tecnologia |
|--------|------------|
| Frontend | HTML5, CSS3, JavaScript (vanilla) |
| Backend | Python (Flask) |
| Banco de Dados | Azure SQL Server |
| Hosting | Databricks Apps |
| Autenticação | Azure Active Directory (via Databricks SSO) |
| Secrets | Databricks Secrets (Azure Key Vault) |
| Driver DB | pymssql (fallback) / pyodbc |

---

## Estrutura de Arquivos

```
BQ_OTIF_FILLRATE_DEV/
├── app.py                      # Backend Flask (API + routing)
├── app.yaml                    # Configuração Databricks App
├── requirements.txt            # Dependências Python
├── styles.css                  # CSS global (dark/light mode)
├── index.html                  # Página de entrada
├── painel-executivo.html       # Painel Executivo
├── fillrate.html               # Fill Rate
├── fillrate-detalhe.html       # Fill Rate Detalhe
├── otif.html                   # OTIF
├── otif-detalhe.html           # OTIF Detalhe
├── gestao-pedidos.html         # Gestão de Pedidos
├── logo-bimbo-qsr.png          # Logo Bimbo QSR
├── logo-dna.png                # Logo DnA
├── Fundo_escuro.png            # Background dark mode
├── fundo_claro.png             # Background light mode
├── .env.example                # Template de variáveis locais
├── project_business_rules.md   # Regras (arquivo legado)
└── docs/
    ├── README.md               # Este arquivo
    ├── BUSINESS_RULES.md       # Regras de negócio completas
    ├── DATA_DICTIONARY.md      # Dicionário de dados
    ├── API_REFERENCE.md        # Referência de endpoints
    ├── DECISIONS.md            # Decisões arquiteturais (ADR)
    ├── OPERATIONS.md           # Deploy e operação
    └── CHANGELOG.md            # Histórico de versões
```

---

## Setup Local

### 1. Clonar/acessar o workspace

O código reside em:
```
/Workspace/Users/renan.ferreira@grupobimbo.com/BQ_OTIF_FILLRATE_DEV
```

### 2. Configurar credenciais

Copiar `.env.example` para `.env` e preencher:
```env
DB_USER=seu_usuario@dominio.com
DB_PASSWORD=sua_senha
DB_SERVER=bbraclbbsqlcp02.database.windows.net
DB_NAME=ACL-DNA-BRPROD
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Executar

```bash
python app.py
```

Acesso local: `http://localhost:5000`

---

## Deploy em Produção

Ver [OPERATIONS.md](./OPERATIONS.md) para o guia completo.

Resumo rápido:
```bash
databricks apps deploy bq-oitf-fillrate-dev
```

URL de produção: https://bq-oitf-fillrate-dev-8674310331778219.19.azure.databricksapps.com

---

## Documentação

| Documento | Conteúdo |
|-----------|--------|
| [BUSINESS_RULES.md](./BUSINESS_RULES.md) | Regras de cálculo de todos os KPIs |
| [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) | Tabelas, campos, mapeamentos |
| [API_REFERENCE.md](./API_REFERENCE.md) | Endpoints disponíveis |
| [DECISIONS.md](./DECISIONS.md) | Justificativas das decisões técnicas e de negócio |
| [OPERATIONS.md](./OPERATIONS.md) | Deploy, secrets, troubleshooting |
| [CHANGELOG.md](./CHANGELOG.md) | Histórico de versões |

---

## KPIs Monitorados

| KPI | Meta | Definição Resumida |
|-----|------|--------------------|
| Fill Rate | ≥ 96% | Qtde Atendida / (Qtde Pedida − Cancelada) |
| On Time CIF | ≥ 96% | Chegou no destino até a data agendada |
| On Time FOB | ≥ 96% | Chegou na planta até grade + 30 min |
| In Full | ≥ 96% | Atendeu 100% da quantidade |
| OTIF | ≥ 85% | On Time E In Full simultaneamente |

---

## Contato

| Papel | Nome |
|-------|------|
| Desenvolvedor | Renan Ferreira |
| Equipe | DnA Brazil |
| Workspace | adb-8674310331778219.19.azuredatabricks.net |
