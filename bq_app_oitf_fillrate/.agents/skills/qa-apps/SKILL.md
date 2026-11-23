---
name: qa-apps
description: Conferir se um app web de dados funciona de verdade - botões, filtros, menus, exportações e navegação - e se os valores da tela batem com a API e com o banco. Use antes de entregar uma mudança, depois de um redesign ou otimização, ou quando pedirem teste, QA, validação ou conferência de valores.
---

# Testes e conferência de apps de dados

Prova, com execução real, que cada controle do app faz o que promete e que cada número da tela é o mesmo do backend e do banco. A entrega é um relatório com o que passou, o que falhou e o que não foi possível testar. Nunca uma afirmação de que "está tudo certo" sem execução.

## Regras

- **Teste falhou = problema encontrado.** Não altere o teste, o seletor ou a tolerância para fazê-lo passar. Também não mude regra de negócio para o número bater. Descubra em qual camada está a diferença (banco → API → tela) e registre.
- **Sem mocks na conferência de valores.** Ela usa o app rodando com dados reais (ou o ambiente de teste do projeto) e o banco real.
- **Tudo ao mesmo tempo.** Tela, API e SQL são consultados na mesma execução, porque os dados mudam ao longo do dia.
- **"Não executado" é diferente de "passou".** Se faltar acesso ao banco, um seletor ou um login, marque como não executado e diga o que falta.
- **Os scripts aceitam `--help`;** rode com `--help` antes, em vez de ler o código.
- **Requisitos:** `pip install playwright` e `python -m playwright install chromium`. Para conferir com o Databricks: `pip install databricks-sql-connector` e as variáveis `DATABRICKS_SERVER_HOSTNAME`, `DATABRICKS_HTTP_PATH` e `DATABRICKS_TOKEN`.

## Passo 1. Inventário dos controles

```bash
python scripts/inventario_ui.py --url http://localhost:8000/ --url http://localhost:8000/vendometro --saida inventario.md
python scripts/inventario_ui.py --url http://localhost:8000/vendometro --largura 390 --saida inventario-celular.md
```

O script lista, por tela, todos os elementos clicáveis ou editáveis: botões, links, campos, selects, abas, chaves, itens de menu e elementos com `onclick`. Para cada um mostra nome acessível, estado e tamanho, e aponta problemas:
- sem nome (leitor de tela e teste automatizado não conseguem achar);
- `div` ou `span` clicável (o teclado não alcança);
- link sem destino;
- alvo pequeno no celular.

**Cada linha do inventário vira um caso de teste:** o que deveria acontecer ao usar aquele controle.

## Passo 2. Fumaça em todas as telas

```bash
python scripts/smoke_rotas.py --base http://localhost:8000 --rota / --rota /vendometro --rota /report --larguras 390,1440 --capturas capturas/ --saida smoke.md
```

Para cada tela e largura, o script verifica:
- erros de console e de JavaScript;
- requisições com status 4xx/5xx ou que falharam;
- rolagem horizontal;
- texto quebrado na tela: `NaN`, `undefined`, `null`, `Infinity`, `[object Object]`, `R$ NaN`, `{{` sem preencher.

Também salva uma captura de cada tela. Para testar outro estado, como tema escuro ou um token de teste, use `--init-js` (ex.: `--init-js "localStorage.setItem('theme','dark')"`).

## Passo 3. Funcionamento dos controles

Escreva testes Playwright (pytest) para os fluxos do inventário. O modelo está em `resources/teste_filtros_exemplo.py`. Cada teste precisa de uma verificação observável: nada de "clicou e não deu erro".

| Controle | O que provar |
|---|---|
| Filtro | A requisição sai com o parâmetro escolhido; os números da tela mudam de acordo; o chip ou resumo mostra a seleção; Limpar volta ao padrão e aos números originais |
| Busca | Filtra a lista; sem resultado mostra mensagem; limpar a busca restaura |
| Ordenação | A primeira linha muda; ordem crescente e decrescente corretas (números como número, datas como data) |
| Paginação | Página 2 traz outras linhas; total de registros coerente; botões desabilitam nas pontas |
| Exportação | O arquivo baixa, abre e tem as mesmas linhas e totais da tela com os mesmos filtros; números exportados como número |
| Abas e alternâncias (Sell-in/Sell-out, 6/12 meses) | O conteúdo troca, e os valores trocados batem com a API |
| Menu, tema, idioma | Abrem e funcionam em **todas** as rotas; a troca mantém página e filtros |
| Expandir/detalhar (ex.: itens do pedido) | Os rótulos dos campos correspondem aos dados certos |
| Link externo | Abre o destino correto em nova aba |

Rode nas larguras 390 e 1440. Num controle que só existe no celular (gaveta, barra inferior), teste no celular.

## Passo 4. Conferência de valores: tela × API × banco

Configure um JSON com os cenários e as checagens (modelo em `resources/conferencia.exemplo.json`) e rode:

```bash
python scripts/conferir_valores.py --config conferencia.json --saida conferencia.md
```

**Fontes que o script compara** (use as que fizerem sentido para cada checagem):
- `tela`: o texto exibido (seletor CSS), convertido de pt-BR. Entende "R$ 8,6 mi", "1.709", "93,4%", "−R$ 9,0 mi", "mil", "mi", "bi", "K", "M" e "—" (sem dado).
- `resposta`: o JSON que a própria página recebeu durante o cenário. É o que prova se o front transformou certo.
- `api`: uma chamada direta à API.
- `sql`: consulta independente no banco (Databricks SQL). É a verdade de referência.

**Tolerância:** por padrão (`"tolerancia": "formato"`), é metade da última casa mostrada na tela. Exemplo: "R$ 8,6 mi" aceita diferença de até R$ 50 mil em relação ao valor exato. Entre API e SQL, a comparação é exata (diferença relativa de até 0,0001%), salvo outra tolerância configurada.

**Regras de consistência** (não precisam de banco):
- `soma`: as partes somam o total (ex.: faturado + carteira = total).
- `razao`: o percentual exibido é igual a numerador ÷ denominador (ex.: atingimento = realizado ÷ meta).
- `igual`: o mesmo número em dois lugares (ex.: rótulo do gráfico = KPI).

**O que conferir, no mínimo:**
1. Todo KPI de cada tela, com os filtros padrão.
2. Os mesmos KPIs com ao menos um filtro aplicado (o filtro precisa chegar ao SQL).
3. "Todos" igual à soma de cada opção de um filtro (ex.: soma por canal = total).
4. O ponto do mês filtrado no gráfico igual ao KPI do mês.
5. Totais da tabela e do arquivo exportado iguais aos da tela.
6. Período corrente parcial e ausência de dado: "—", e não zero.

Quando valores divergem, ache a camada:
- **SQL ≠ API:** a consulta do backend ou um filtro está errado.
- **API ≠ resposta:** cache ou parâmetro diferente.
- **Resposta ≠ tela:** formatação, unidade, escala (fração × percentual) ou arredondamento no front.

## Entrega

1. Relatórios dos scripts (inventário, fumaça, conferência) e resultado dos testes Playwright.
2. **Matriz:** cada controle e cada checagem com status (Passou / Falhou / Não executado), evidência (arquivo, captura ou trecho do relatório) e, nas falhas, a camada provável.
3. **Correções feitas,** se o pedido incluía corrigir, cada uma com o teste que agora passa. Mudanças em regra de negócio só com confirmação do dono do app.
4. **O que não foi testado** e por quê.
