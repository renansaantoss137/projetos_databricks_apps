# Space Portal (BQ) — Grupo Bimbo Brasil

Aplicação web do **Space Portal** adaptada para a realidade da **Bimbo QSR (BQ)**, construída e gerenciada através do **Databricks Asset Bundles (DABs)**.

---

## 📁 Estrutura do Projeto

O projeto segue a padronização oficial de bundles da equipe DNA Analytics:

```
bq_app_space/
├── databricks.yml              # Definição principal do Databricks Asset Bundle
├── pyproject.toml              # Metadados e dependências Python do projeto
├── README.md                   # Documentação do projeto
├── .gitignore                  # Arquivos e pastas ignoradas pelo Git
├── .vscode/
│   └── settings.json           # Configurações de desenvolvimento do VSCode
├── resources/
│   └── space_portal.app.yml    # Definição do Databricks App e recursos Lakebase
└── src/
    └── app/
        ├── app.py              # Aplicação principal Flask
        ├── app.yaml            # Configuração de inicialização e runtime do Databricks App
        ├── requirements.txt    # Dependências Python instaladas no container Databricks
        ├── contexto.md         # Histórico e documentação técnica de alterações
        ├── local_area_data.json # Base local de dados de áreas e dashboards (LOCAL_MODE)
        ├── local_acessos_space.json # Registro local de acessos
        ├── local_sidebar_apps.json  # Configuração de aplicativos da barra lateral
        ├── sugestao_knn.csv    # Base de recomendações por KNN
        ├── crc23_subespaco_spaces.csv # Metadados de subespaços
        ├── admin_users.sql     # Script SQL de usuários administradores
        ├── remove_bg.py        # Utilitário para tratamento de imagens
        ├── templates/          # Templates Jinja2 (HTML)
        │   ├── index.html      # Página inicial / Home do portal
        │   ├── area.html       # Página de visualização por área/setor
        │   ├── admin.html      # Painel de administração
        │   └── 403.html        # Página de acesso negado
        └── static/             # Arquivos estáticos
            ├── css/            # Folhas de estilo (style.css)
            ├── js/             # Scripts client-side (script.js)
            └── images/         # Imagens, logos, ícones e wallpapers
```

---

## 🚀 Ambientes e Targets

O bundle está configurado com dois ambientes no Databricks:

| Ambiente | Target | Nome do App | Caminho no Workspace |
| :--- | :--- | :--- | :--- |
| **Desenvolvimento** | `dev` *(padrão)* | `bq-app-space-dev` | `/Shared/CONSULTAS_AUTOMATIZADAS/${workspace.current_user.userName}/bq_app_space/dev/` |
| **Produção** | `prod` | `bq-app-space-prod` | `/Shared/CONSULTAS_AUTOMATIZADAS/bq_app_space/prod` |

---

## 🛠️ Comandos do Databricks Asset Bundle (DAB)

### 1. Validar a sintaxe e recursos do bundle
```bash
# Validar ambiente de desenvolvimento (padrão)
databricks bundle validate

# Validar ambiente de produção
databricks bundle validate -t prod
```

### 2. Realizar deploy para o Databricks
```bash
# Deploy no ambiente de desenvolvimento
databricks bundle deploy -t dev

# Deploy no ambiente de produção
databricks bundle deploy -t prod
```

### 3. Executar / Inicializar o App
```bash
databricks bundle run bq_app_space -t dev
```

---

## 💻 Executando Localmente

A aplicação suporta execução offline/local sem necessidade de conexão direta com o banco Lakebase PostgreSQL através do `LOCAL_MODE`:

1. Navegue até a pasta da aplicação:
   ```bash
   cd "src/app"
   ```

2. Crie ou ative seu ambiente virtual Python e instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure o arquivo `.env` (ou utilize o `.env.example` como base):
   ```ini
   LOCAL_MODE=true
   FLASK_DEBUG=1
   PORT=8080
   ADMIN_EMAIL=renan.ferreira@grupobimbo.com
   ```

4. Inicie o servidor:
   ```bash
   python app.py
   ```

5. Acesse no navegador: `http://localhost:8080`

---

## 🔐 Integração com Lakebase PostgreSQL

Quando o app é executado no Databricks Apps, a plataforma injeta automaticamente as credenciais de conexão seguras com o Lakebase via recurso:
- **Branch**: `projects/dev-space/branches/production`
- **Database**: `projects/dev-space/branches/production/databases/databricks-postgres`
- **Permissão**: `CAN_CONNECT_AND_CREATE`
