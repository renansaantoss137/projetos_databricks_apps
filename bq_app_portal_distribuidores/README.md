# Portal de Distribuidores v2 - Databricks Asset Bundle (DAB) & Databricks App

Aplicação corporativa de Inteligência e Gestão de Distribuidores Bimbo QSR desenvolvida para o **Grupo Bimbo Brasil (DNA Analytics)** e gerenciada via **Databricks Asset Bundles (DAB)**.

---

## 🏛️ Arquitetura da Solução

```text
[Lakehouse Databricks / Unity Catalog]
             │
             ▼ (Databricks SQL Statement Execution API / SDK)
[Databricks App (Flask Backend + Multi-Page SPA Frontend)]
  ├── app.py (API Flask / Endpoints analíticos, RLS e autenticação)
  ├── app.yaml (Configuração de execução do Databricks App)
  ├── index.html (Página Principal)
  ├── login.html (Autenticação do Distribuidor)
  ├── dashboard.html (Dashboard Analítico / KPIs)
  ├── dashboard_admin.html (Dashboard Administrativo)
  ├── gestao_acesso.html (Gestão de Acessos e Usuários)
  ├── acessos_v2.html (Controle de Acessos v2)
  ├── guia.html (Manual do Usuário Integrado)
  ├── css/ (Estilos, temas e design tokens)
  ├── js/ (Lógica de front-end, renderers e formatação)
  ├── img/ (Logos institucionais e identidade visual)
  └── sql/ & config/ (Scripts de RLS e configuração)
```

---

## 📁 Estrutura do Projeto

```text
bq_app_portal_distribuidores/
├── .gitignore                   # Arquivos ignorados pelo Git
├── databricks.yml               # Configuração mestre do Databricks Asset Bundle (DAB)
├── README.md                    # Documentação do projeto e guia de deploy
├── run_local.ps1                # Script para inicialização local rápida
├── resources/
│   └── portal_distribuidores_v2.app.yml  # Definição do recurso Databricks App
└── src/
    └── app/                     # Código-fonte da aplicação web (Databricks App)
        ├── app.py               # Servidor Flask e rotas da API
        ├── app.yaml             # Configurações de execução e variáveis de ambiente
        ├── requirements.txt     # Dependências Python (flask, databricks-sdk)
        ├── css/                 # Folhas de estilo (tokens, layout, temas)
        ├── js/                  # Scripts JavaScript modulares
        ├── img/                 # Ativos visuais e logos
        ├── sql/                 # Scripts SQL de segurança e RLS
        ├── config/              # Configurações de banco e RLS
        └── *.html               # Telas da aplicação
```

---

## 🚀 Como Desenvolver e Fazer Deploy

### 1. Validar a configuração do Bundle
Antes de qualquer deploy, valide a sintaxe dos arquivos YAML:
```bash
databricks bundle validate -t dev
```

### 2. Deploy no Ambiente de Desenvolvimento (DEV)
Cria/atualiza o app isolado `portal-distribuidores-v2-dev` no Databricks Apps, sem impactar o app oficial em produção:
```bash
databricks bundle deploy -t dev
```

### 3. Deploy no Ambiente de Produção (PROD)
Após validação e testes no ambiente de dev, realize o deploy oficial para `portal-distribuidores-v2`:
```bash
databricks bundle deploy -t prod
```

### 4. Execução Local para Desenvolvimento
Para executar o backend e frontend na máquina local:
```powershell
.\run_local.ps1
```
Ou manualmente via terminal:
```bash
cd src/app
python app.py
```
> Acesse no navegador: `http://localhost:8000`

---

## 🔒 Segurança e Permissões
- O bundle define permissões automáticas para o criador (`workspace.current_user.userName`) e para o grupo **`DNA - GB Brasil Leaders`** com nível `CAN_MANAGE`.
- No target `dev`, os arquivos do workspace ficam isolados no diretório pessoal:
  `/Shared/CONSULTAS_AUTOMATIZADAS/<seu-usuario>/bq-portal-distribuidores/dev/`
- No target `prod`, os arquivos residem em:
  `/Shared/CONSULTAS_AUTOMATIZADAS/bq-portal-distribuidores/prod/`
