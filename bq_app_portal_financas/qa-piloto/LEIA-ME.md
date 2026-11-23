# Piloto de correção do QA

O arquivo `conferir_valores_candidato.py` é uma cópia local do script publicado na skill `bimbo-app-qa`, recuperado em 06/11/2026. Não foi publicado nem aplicado à fonte corporativa.

## Defeito reproduzido

Quando o SQL está previsto na checagem mas é pulado ou indisponível, a versão publicada pode apresentar `OK` se as demais fontes coincidirem. Isso não comprova a comparação com SQL. O leitor também retorna `pct: true` tanto para `1,2%` quanto para `1,2 p.p.`; a distinção de unidade continua pendente.

## Correção candidata

Se o SQL previsto não for executado e as comparações disponíveis coincidirem, a checagem passa a `NÃO CONFERIDO`. O processo retorna código diferente de zero para resultados diferentes de `OK` ou ausência de checagens, evitando que execução incompleta seja interpretada como gate aprovado. Uma divergência entre fontes continua como `FALHA`.

## Evidência

`test_conferencia.py`: dois testes executados com Playwright/Chromium, página e API locais e SQLite de teste. Resultado: 2 aprovados. O primeiro compara tela, API e SQL; o segundo omite SQL e verifica `NÃO CONFERIDO` com código de saída 1. São testes sintéticos: não comprovam integração com dados reais nem cobrem toda a skill. A suíte emitiu aviso de permissão no cache do pytest, sem afetar os resultados.

## Pendente

Testar falha real de autenticação e banco; corrigir distinção de percentual e pontos percentuais; conferir filtros, exportações e números em DEV com dados reais; avaliar os demais scripts e gates; revisar a proposta, atualizar a fonte editável e somente depois publicar e verificar a skill. Não declarar cobertura total ou aprovação em PROD antes desses passos.
