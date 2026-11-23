# AGENTS.md

## Projeto
- App Flask publicado no Databricks Apps.
- Entrada: `src/app/app.py` | Config do app: `src/app/app.yaml` | Dependências: `src/app/requirements.txt`
- Banco: Lakebase (Postgres). Credenciais só via variáveis de ambiente, nunca hardcoded.

## Rodar localmente (Windows / PowerShell)
Na raiz do projeto, nesta máquina, use o ambiente já preparado fora do OneDrive:
```powershell
& "$env:LOCALAPPDATA\compras360-runtime\Scripts\python.exe" -m pip install -r src/app/requirements.txt
Push-Location src/app
try { & "$env:LOCALAPPDATA\compras360-runtime\Scripts\python.exe" app.py } finally { Pop-Location }
```
- Acesse `http://localhost:8000`. Caso o ambiente não exista, crie-o com Python 3.12: `py -3.12 -m venv "$env:LOCALAPPDATA\compras360-runtime"`.
- O acesso local ao Lakebase pode ser recusado pela política de rede do workspace; confirme `/api/health` e relate o erro, sem substituir dados reais por fictícios.
- Testes: `pytest -q --tb=short`

## Regras de trabalho (economia de contexto)
- Antes de abrir arquivos, use `rg` para localizar o trecho; leia só o necessário.
- Em arquivos grandes, leia por intervalo de linhas, nunca o arquivo inteiro.
- Não liste diretórios recursivamente; ignore `.venv/`, `__pycache__/`, `node_modules/`, `dist/`, dados e logs.
- Filtre comandos com saída longa (`| Select-Object -First 50`, `pytest -q`).
- Faça mudanças mínimas e focadas; não refatore o que não foi pedido.
- Não repita no chat código que já está no arquivo; mostre só o resumo das mudanças.

## Qualidade
- Antes de concluir, rode os testes ou suba o app e valide o endpoint alterado.
- Ao terminar, responda em até 5 linhas: o que mudou, em quais arquivos e como validar.
