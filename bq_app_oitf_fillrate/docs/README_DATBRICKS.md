# Deploy no Databricks Apps

Este repositório já está preparado para ser publicado como um Databricks App.

## O que já está pronto

- `app.py` contém o Flask app e serve a UI em `otif.html`.
- `requirements.txt` lista as dependências necessárias.
- `app.yaml` já contém o comando de execução e variáveis de ambiente básicas.
- `app.py` tenta ler credenciais do Databricks Secrets em `dbutils` e cai em `.env` apenas em dev local.

## Passos para publicar

1. Abra o Databricks e vá para `Apps`.
2. Crie uma nova aplicação personalizada no novo UI do Databricks Apps.
3. Importe o código deste repositório ou use Git para apontar para ele.
4. Configure o app para executar o comando:
   - `python app.py`

## Configurações importantes

- O app define `PORT` em `app.yaml` como `8000`. O Databricks Apps deve expor essa porta automaticamente.
- O app usa estas variáveis de ambiente:
  - `DB_SERVER` = `bbraclbbsqlcp02.database.windows.net`
  - `DB_NAME` = `ACL-DNA-BRPROD`

## Segredos do Databricks

No Databricks, crie um secret scope chamado `kvsecret-DnABrazil` com as chaves:

- `kvsecret-AzSQL-cz-BB-sql-Usr`
- `kvsecret-AzSQL-cz-BB-sql-psw`

O `app.py` irá ler essas credenciais automaticamente no ambiente de produção.

## Acessando o app

- A aplicação serve a página principal em `/` redirecionando para `otif.html`.
- Depois de publicada, acesse o URL do App Databricks e abra a interface.

## Observações

- Se precisar de ajustes no app ou no manifesto do Databricks, posso atualizar `app.yaml` ou preparar um `Dockerfile` caso a plataforma exija.
