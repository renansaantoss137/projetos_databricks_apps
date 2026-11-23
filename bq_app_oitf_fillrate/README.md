# BQ OTIF / Fill Rate - Databricks Asset Bundle (DAB)

Projeto oficial de monitoramento de OTIF e Fill Rate Bimbo QSR via Databricks Apps, estruturado como **Databricks Asset Bundle (DAB)**.

## Estrutura do Repositório

```text
├── databricks.yml                # Configuracao central do bundle (targets dev e prod)
├── resources/
│   └── bq_oitf_fillrate.app.yml  # Declaracao do Databricks App e permissoes
├── src/
│   └── app/                      # Codigo-fonte do Databricks App
│       ├── app.py                # Servidor Flask / Waitress
│       ├── app.yaml              # Manifesto de execucao do Databricks App
│       ├── requirements.txt      # Dependencias Python
│       ├── styles.css            # Estilos da aplicacao
│       ├── index.html            # Pagina inicial
│       ├── otif.html             # Painel OTIF consolidado
│       ├── otif-detalhe.html     # Detalhamento de entregas OTIF
│       ├── fillrate.html         # Painel Fill Rate
│       ├── gestao-pedidos.html   # Gestao de pedidos
│       ├── painel-executivo.html # Painel executivo
│       └── *.png                 # Imagens e logotipos
├── scripts/
│   └── deploy.ps1                # Script PowerShell de deploy
├── docs/                         # Documentacao tecnica e funcional
└── README.md
```

## Ambientes e URLs

| Ambiente | Nome do App | URL Databricks App |
| :--- | :--- | :--- |
| **Dev** | `bq-oitf-fillrate-dev` | [bq-oitf-fillrate-dev](https://bq-oitf-fillrate-dev-8674310331778219.19.azure.databricksapps.com) |
| **Prod** | `bq-oitf-fillrate` | [bq-oitf-fillrate](https://bq-oitf-fillrate-8674310331778219.19.azure.databricksapps.com) |

## Deploy via Databricks CLI

### 1. Validar configuracao
```bash
databricks bundle validate -t dev
databricks bundle validate -t prod
```

### 2. Executar Deploy
Utilizando o script PowerShell:
```powershell
.\scripts\deploy.ps1 -Target dev
# ou producao:
.\scripts\deploy.ps1 -Target prod
```

Ou diretamente via Databricks CLI:
```bash
databricks bundle deploy -t dev
databricks bundle deploy -t prod
```

## Desenvolvimento Local

1. Crie e ative um ambiente virtual:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. Instale as dependencias:
   ```bash
   pip install -r src/app/requirements.txt
   ```
3. Configure as credenciais no arquivo `src/app/.env` (baseado no `.env.example`).
4. Execute o app:
   ```bash
   cd src/app
   python app.py
   ```
5. Acesse em `http://localhost:5000` (ou porta configurada).