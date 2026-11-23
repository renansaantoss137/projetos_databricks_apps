# Compras 360 - Databricks Asset Bundle (DAB) & Databricks App

Aplicação corporativa de Inteligência em Compras (Procurement Intelligence) desenvolvida para o **Grupo Bimbo Brasil (DNA Analytics)**, integrada ao **Lakebase PostgreSQL** e gerenciada via **Databricks Asset Bundles (DAB)**.

---

## 🏛️ Arquitetura da Solução

```text
[ERP / SAP / Fontes de Compras]
             │
             ▼ (ETL Lakebase)
[Lakebase PostgreSQL (Branch: production)]
             │
             ▼ (Lakebase OAuth / Databricks SDK)
[Databricks App (Flask Backend + Multi-Page SPA Frontend)]
  ├── app.py (API Flask / Endpoints analíticos e filtros)
  ├── performance.html (Performance & Metas)
  ├── comercial.html (Visão Comercial)
  ├── ordens.html (Ordens de Compra)
  ├── relatorios.html (Relatórios & Exportações)
  ├── spend.html (Análise de Spend)
  ├── governanca.html (Governança & Parâmetros)
  └── guia.html (Manual do Usuário Integrado)
```

---

## 📁 Estrutura do Projeto

```text
bb_app_compras/
├── .gitignore                   # Arquivos ignorados pelo Git
├── databricks.yml               # Configuração mestre do Databricks Asset Bundle (DAB)
├── README.md                    # Documentação do projeto e guia de deploy
├── resources/
│   ├── compras_360.app.yml      # Definição do recurso Databricks App
│   └── compras_360_etl.job.yml  # Definição do recurso Databricks Job (ETL Lakebase)
├── src/
│   ├── app/                     # Código da aplicação web (Databricks App)
│   │   ├── app.py               # Servidor Flask e rotas da API
│   │   ├── app.yaml             # Configurações de execução e variáveis de ambiente
│   │   ├── requirements.txt     # Dependências Python (Flask, psycopg2, sdk, waitress)
│   │   ├── styles.css           # Estilos globais e tema
│   │   ├── filters-shared.js    # Lógica compartilhada de filtros
│   │   ├── i18n.js              # Internacionalização e textos
│   │   ├── *.html               # Módulos e telas da aplicação
│   │   └── *.png                # Logos e imagens de fundo
│   └── dados/                   # Notebooks e Lookups de ETL
│       ├── compras_360_lakebase_etl.py  # Notebook do Job de ETL (Oracle Cloud → Lakebase)
│       └── *.csv                # Tabelas de apoio (Lookups de Compradores e Fornecedores)
└── docs/                        # Documentação e consultas de suporte
    ├── documentacao_tecnica.md  # Detalhes técnicos do sistema
    ├── guia_do_usuario.md       # Guia operacional
    └── sql/                     # Views SQL da camada analítica
```

---

## 🚀 Como Desenvolver e Fazer Deploy

### 1. Validar a configuração do Bundle
Antes de qualquer deploy, valide a sintaxe dos arquivos YAML:
```bash
databricks bundle validate -t dev


```

### 2. Deploy no Ambiente de Desenvolvimento (DEV)
Cria/atualiza o app isolado `compras-360-dev` no Databricks Apps, sem impactar o app oficial em produção:
```bash
databricks bundle deploy -t dev
```
Caso queira um deploy sem precisar 'Implementar' na plataforma do databricks, usar esse comando:
```bash
databricks apps deploy compras-360-dev --source-code-path "/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/renan.ferreira@grupobimbo.com/compras_360/dev/files/src/app"
```

### 3. Deploy no Ambiente de Produção (PROD)
Após validação e testes no ambiente de dev:
```bash
databricks bundle deploy -t prod
```

### 4. Execução Local para Desenvolvimento
Para executar o backend e frontend na máquina local:
```bash
cd src/app
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
> Acesse no navegador: `http://localhost:8000`

---

## 🔒 Segurança e Permissões
- O bundle define permissões automáticas para o criador (`workspace.current_user.userName`) e para o grupo **`DNA - GB Brasil Leaders`** com nível `CAN_MANAGE`.
- No target `dev`, os arquivos do workspace ficam isolados no diretório pessoal:
  `/Shared/CONSULTAS_AUTOMATIZADAS/<seu-usuario>/compras_360/dev/`
