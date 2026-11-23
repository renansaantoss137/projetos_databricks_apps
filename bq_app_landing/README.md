# BQ Landing - Databricks Asset Bundle (DAB) & Databricks App

Aplicação corporativa desenvolvida para ingestão automatizada e visualização de dados operacionais BQ (Grupo Bimbo), integrada ao **Unity Catalog** e empacotada via **Databricks Asset Bundles (DAB)**.

---

## 🏛️ Arquitetura da Solução

```text
[SharePoint BQ_LANDING]
          │
          ▼ (Upload / Sync)
[Unity Catalog Volume] (/Volumes/cat_dnabb_dv/grobbbqb_sz/dev_bq_landing/base_landing.xlsx)
          │
          ├──────────────────────────┐
          ▼                          ▼
[Job Ingestão (file_arrival)]   [Databricks App]
          │                          │
          ▼                          ▼
[Delta Table: cat_dnabb_dv.grobbbqb_sz.tbl_bq_landing] ◄──────┘
```

1. **Volume Landing Zone**: `/Volumes/cat_dnabb_dv/grobbbqb_sz/dev_bq_landing/base_landing.xlsx` (dev) ou `prod_bq_landing` (prod).
2. **Databricks Job**: Acionado automaticamente por gatilho `file_arrival` quando um novo arquivo chega no Volume correspondente.
3. **Databricks App**: Interface web interativa para exploração, filtros e consulta dos dados processados.

---

## 🚀 Como fazer o Deploy via Databricks Asset Bundles (DAB)

### 1. Validar a configuração do bundle
```bash
databricks bundle validate
```

### 2. Deploy no ambiente de Desenvolvimento (DEV)
```bash
databricks bundle deploy -t dev
```

### 3. Deploy no ambiente de Produção (PROD)
```bash
databricks bundle deploy -t prod

# 1. Envia os arquivos e configurações atualizados para a pasta de PROD do Workspace
databricks bundle deploy -t prod

# 2. Reinicia e sincroniza o Databricks App de produção com o novo código
databricks apps deploy bq-landing-prod --source-code-path /Workspace/Shared/CONSULTAS_AUTOMATIZADAS/bq_app_landing/prod/files/src/app

```

### 4. Executar o Databricks App localmente para desenvolvimento
```bash
cd src/app
pip install -r requirements.txt
python app.py
```
Acesse `http://localhost:8000` no navegador.
