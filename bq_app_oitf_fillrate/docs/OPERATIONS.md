# Guia de Operação e Deploy

**Projeto:** Cockpit Logístico OTIF & Fill Rate — Bimbo QSR Brasil  
**Última atualização:** 2026-07-16

---

## 1. Arquitetura de Deploy

```
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────────┐
│  Browser/User   │ ───▶ │  Databricks Apps   │ ───▶ │  Azure SQL Server      │
│  (HTTPS)        │     │  (Flask + HTML)    │     │  ACL-DNA-BRPROD        │
└─────────────────┘     └──────────────────┘     └───────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Databricks Secrets │
                    │  (Key Vault)       │
                    └──────────────────┘
```

---

## 2. Pré-requisitos

### 2.1 Secrets (Produção)

| Scope | Key | Descrição |
|-------|-----|----------|
| `kvsecret-DnABrazil` | `kvsecret-AzSQL-cz-BB-sql-Usr` | Usuário do Azure SQL |
| `kvsecret-DnABrazil` | `kvsecret-AzSQL-cz-BB-sql-psw` | Senha do Azure SQL |

### 2.2 Variáveis de Ambiente (Dev Local)

Criar arquivo `.env` baseado no `.env.example`:

```env
DB_USER=seu_usuario@dominio.com
DB_PASSWORD=sua_senha
DB_SERVER=bbraclbbsqlcp02.database.windows.net
DB_NAME=ACL-DNA-BRPROD
```

### 2.3 Dependências Python

Ver `requirements.txt`. Principais:
- Flask
- flask-cors
- pymssql
- python-dotenv
- databricks-sdk

---

## 3. Deploy

### 3.1 Via Databricks Apps UI

1. Navegar para o App `bq-oitf-fillrate-dev` no workspace
2. Clicar em "Deploy" (usa source code path configurado)
3. Aguardar status `SUCCEEDED`

### 3.2 Via CLI

```bash
databricks apps deploy bq-oitf-fillrate-dev \
  --source-code-path /Workspace/Users/renan.ferreira@grupobimbo.com/BQ_OTIF_FILLRATE_DEV
```

### 3.3 Configuração do App

| Parâmetro | Valor |
|-----------|------|
| Nome | `bq-oitf-fillrate-dev` |
| Compute Size | MEDIUM |
| Source Code Path | `/Workspace/Users/renan.ferreira@grupobimbo.com/BQ_OTIF_FILLRATE_DEV` |
| Deploy Mode | SNAPSHOT |

---

## 4. Health Check

### Endpoint de Diagnóstico

```
GET https://bq-oitf-fillrate-dev-8674310331778219.19.azure.databricksapps.com/api/diag
```

**Resposta esperada (sucesso):**
```json
{
  "python": "3.x.x",
  "drivers": { "pyodbc": null, "pymssql": "2.x.x" },
  "credentials_source": "databricks-secrets",
  "db_server": "bbraclbbsqlcp02.database.windows.net",
  "db_name": "ACL-DNA-BRPROD",
  "connection": { "status": "OK", "server_time": "..." }
}
```

### Checklist de Validação Pós-Deploy

- [ ] `/api/diag` retorna `connection.status = "OK"`
- [ ] Página inicial carrega sem erros no console
- [ ] Filtros de data/planta/grupo funcionam
- [ ] KPI cards mostram valores coerentes
- [ ] Painel Executivo carrega Pareto e Evolução
- [ ] OTIF v2 diferencia CIF e FOB
- [ ] Dark mode e Light mode funcionam

---

## 5. Comportamento de Conexão

| Aspecto | Configuração |
|---------|-------------|
| TTL da conexão | 5 minutos (300s) |
| Health check | `SELECT 1` antes de cada uso |
| Reconexão automática | Sim, transparente |
| Driver primário | pyodbc (ODBC 17) |
| Driver fallback | pymssql (pure Python) |
| Connection timeout | 30 segundos |
| Thread safety | Thread-local connections |

---

## 6. Troubleshooting

### Erro: "Nenhum driver disponível"

**Causa:** Nem pyodbc nem pymssql estão instalados.  
**Solução:** Verificar `requirements.txt` inclui `pymssql`. Re-deploy.

### Erro: "Login failed for user"

**Causa:** Credenciais inválidas ou expiradas.  
**Solução:**
1. Verificar secrets no scope `kvsecret-DnABrazil`
2. Confirmar que o usuário tem acesso ao banco `ACL-DNA-BRPROD`
3. Verificar se a autenticação Azure AD está ativa

### Erro: Timeout nas queries

**Causa:** Volume excessivo de dados ou filtro muito amplo.  
**Solução:** Verificar se o usuário está filtrando por período. Sem filtro de data, assume 90 dias (pode ser pesado).

### Erro: App status "FAILED"

**Causa:** Erro de sintaxe no código ou depêndencia não resolvida.  
**Solução:**
1. Verificar logs: `databricks apps logs bq-oitf-fillrate-dev`
2. Corrigir o erro no source code
3. Re-deploy

### Erro: "Connection reset" ou "Broken pipe"

**Causa:** Conexão Azure SQL cortada por inatividade (firewall/timeout).  
**Solução:** O TTL de 5 min já mitiga. Se persistir, verificar regras de firewall do Azure SQL.

---

## 7. Logs

### Acessar logs do app

```bash
databricks apps logs bq-oitf-fillrate-dev
```

### Nível de log

Default: `INFO`. Logs incluem:
- Conexões estabelecidas/reconectadas
- Erros de query
- Requests ao `/api/diag`

---

## 8. Backup e Recuperação

| Item | Estratégia |
|------|----------|
| Código-fonte | Workspace Databricks (versionado por deploy snapshot) |
| Secrets | Azure Key Vault (gerenciado separadamente) |
| Dados | Azure SQL Server (backup gerenciado pela infra Azure) |
| Configuração do App | `app.yaml` no source code path |

### Rollback

Em caso de deploy com problema, re-deploy a partir do código anterior ou reverta as alterações no workspace.

---

## 9. Monitoramento

| O que monitorar | Como |
|-----------------|------|
| App status | `databricks apps get bq-oitf-fillrate-dev` |
| Conexão SQL | `GET /api/diag` |
| Performance | Tempo de resposta das APIs (logs) |
| Erros | Logs do app + console do browser |
