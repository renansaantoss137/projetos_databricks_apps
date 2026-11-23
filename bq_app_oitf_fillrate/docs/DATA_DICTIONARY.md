# Dicionário de Dados

**Projeto:** Cockpit Logístico OTIF & Fill Rate — Bimbo QSR Brasil  
**Última atualização:** 2026-07-16

---

## 1. Fonte de Dados

| Parâmetro | Valor |
|-----------|------|
| Servidor | `bbraclbbsqlcp02.database.windows.net` |
| Banco de Dados | `ACL-DNA-BRPROD` |
| Schema | `BQB` |
| Autenticação | Azure Active Directory Password |
| Driver primário | ODBC Driver 17 for SQL Server |
| Driver fallback | pymssql (FreeTLS) |

---

## 2. Tabelas Principais

### 2.1 `BQB.MCANET_DB_PEDIDO_PROD` (Itens de Pedido)

Tabela principal de itens de pedido do sistema Mercanet.

| Coluna | Tipo | Descrição |
|--------|------|----------|
| `DB_PEDI_PEDIDO` | INT | Número do pedido (FK para DB_PEDIDO) |
| `DB_PEDI_PRODUTO` | VARCHAR | Código do produto |
| `db_pedi_situacao` | INT | Status do item (0, 1, 2, 9) |
| `db_pedi_qtde_solic` | DECIMAL | Quantidade solicitada |
| `db_pedi_qtde_atend` | DECIMAL | Quantidade atendida/faturada |
| `db_pedi_qtde_canc` | DECIMAL | Quantidade cancelada |
| `db_pedi_preco_liq` | DECIMAL | Preço líquido unitário |
| `DB_PEDI_PRECO_UNIT` | DECIMAL | Preço unitário bruto |
| `DB_PEDI_ATD_DATA` | DATETIME | Data real de faturamento |
| `DB_PEDI_VU_ICMS` | DECIMAL | Valor ICMS bruto |
| `DB_PEDI_ICMSDEST` | DECIMAL | % ICMS destino |
| `status_registro` | VARCHAR | Flag de registro ativo/inativo |

### 2.2 `BQB.MCANET_DB_PEDIDO` (Cabeçalho de Pedido)

Cabeçalho do pedido Mercanet.

| Coluna | Tipo | Descrição |
|--------|------|----------|
| `DB_PED_NRO` | INT | Número do pedido (PK) |
| `DB_PED_EMPRESA` | VARCHAR(3) | Código da empresa (QRA, QRB, etc.) |
| `DB_PED_CLIENTE` | INT | Código do cliente |
| `DB_PED_DT_EMISSAO` | DATETIME | Data de emissão do pedido |
| `DB_PED_DT_PREVENT` | DATETIME | Data planejada de faturamento (data planejada do Mercanet) |
| `DB_PED_DATA_ENVIO` | DATETIME | Data de envio ao cliente |

### 2.3 `BQB.base_otm_otif_bq` (Base OTIF — Dados OTM)

Base consolidada de remessas vindas do OTM (Oracle Transportation Management).

| Coluna | Tipo | Descrição |
|--------|------|----------|
| `PEDIDO_MERCANET` | INT | Número do pedido Mercanet (FK) |
| `REMESSA` | VARCHAR | Identificador da remessa OTM |
| `CLIENTE` | VARCHAR | Nome do cliente |
| `ID_GRUPO_CLIENTE` | INT | Código do grupo de clientes |
| `DESC_GRUPO_CLIENTE` | VARCHAR | Descrição do grupo de clientes |
| `TIPO_FRETE` | VARCHAR | Tipo de frete: "CIF" ou "FOB" |
| `TRANSPORTADORA` | VARCHAR | Nome da transportadora |
| `ORIGEM` | VARCHAR | Planta de origem (nome completo) |
| `DATA_GRADE` | DATETIME | Data/hora da grade (janela de coleta/envio) |
| `DATA_AGENDA_ENTREGA` | DATETIME | Data agendada de entrega ao cliente (CIF) |
| `DATA_CHEGADA_PLANTA` | DATETIME | Data/hora real de chegada na planta (FOB) |
| `DATA_CHEGADA_DESTINO` | DATETIME | Data/hora real de chegada no destino final (CIF) |
| `QT_SOLIC_MERCANET` | DECIMAL | Quantidade solicitada (Mercanet) |
| `QT_ATEND_MERCANET` | DECIMAL | Quantidade atendida (Mercanet) |
| `QT_CANC_MERCANET` | DECIMAL | Quantidade cancelada (Mercanet) |
| `CLUSTER_FILL_RATE_OTIF` | VARCHAR | Canal/cluster para agrupamento |

### 2.4 `BQB.MCANET_DB_CLIENTE` (Cadastro de Clientes)

| Coluna | Tipo | Descrição |
|--------|------|----------|
| `DB_CLI_CODIGO` | INT | Código do cliente (PK) |
| `DB_CLI_CGCMF` | VARCHAR | CNPJ do cliente |
| `DB_CLI_RAMATIV` | INT | Código ramo de atividade (FK) |

### 2.5 `BQB.MCANET_DB_TB_RAMO_ATIV` (Ramo de Atividade)

| Coluna | Tipo | Descrição |
|--------|------|----------|
| `DB_TBATV_CODIGO` | INT | Código do ramo (PK) |

### 2.6 `BQB.GRUPO_CLIENTES_VIEW` (Grupos de Clientes)

View que mapeia grupo de cliente para canal e responsável.

| Coluna | Tipo | Descrição |
|--------|------|----------|
| `COD_GR_CLIENTE` | INT | Código do grupo de clientes (PK) |
| `GRUPO_CLIENTE_DESC` | VARCHAR | Descrição do grupo |
| `CLUSTER_FILL_RATE_OTIF` | VARCHAR | Canal/cluster para segmentação |
| `NM_NV1` | VARCHAR | Responsável (Nível 1) |

---

## 3. Mapeamento Empresa → Planta

| Código Empresa | Planta | CNPJ Bimbo |
|----------------|--------|------------|
| QRA | JAG (Jaguaríuna) | 35402759011110 |
| QRC | JDF (Juiz de Fora) | 35402759011209 |
| QRB | OSA (Osasco) | 35402759011381 |
| QRE | QRE | 35402759011462 |
| QRJ | GUA (Guarulhos) | — |
| QRD | POU (Pouso Alegre) | 35402759011543 |
| QRF | OSA (Osasco) | 35402759011624 |

**Nota:** QRB e QRF ambos mapeiam para OSA (Osasco).

---

## 4. Mapeamento Origem OTM → Planta

| Origem (OTM) | Planta (Abreviada) |
|--------------|--------------------|
| GUARULHOS | GUA |
| JAGUARIUNA | JAG |
| JUIZ DE FORA | JDF |
| POUSO ALEGRE | POU |
| OSASCO | OSA |

---

## 5. Mapeamento de Status de Pedido

| Código | Descrição | Entra no Fill Rate? | Entra no OTIF? |
|--------|-----------|--------------------|-----------------|
| 0 | Aberto | Sim (como base) | Não |
| 1 | Faturado Parcial | Sim | Sim |
| 2 | Faturado | Sim | Sim |
| 9 | Cancelado | Sim (subtrai do denominador) | Não |

---

## 6. Joins Principais

```
MCANET_DB_PEDIDO_PROD (I)
  └── INNER JOIN MCANET_DB_PEDIDO (P)
      ON I.DB_PEDI_PEDIDO = P.DB_PED_NRO
  └── LEFT JOIN MCANET_DB_CLIENTE (dc)
      ON P.DB_PED_CLIENTE = dc.DB_CLI_CODIGO
  └── LEFT JOIN MCANET_DB_TB_RAMO_ATIV (R)
      ON dc.DB_CLI_RAMATIV = R.DB_TBATV_CODIGO
  └── LEFT JOIN GRUPO_CLIENTES_VIEW (G)
      ON TRY_CAST(R.DB_TBATV_CODIGO AS INT) = G.COD_GR_CLIENTE
```

```
base_otm_otif_bq (o)
  └── LEFT JOIN GRUPO_CLIENTES_VIEW (gc)
      ON o.ID_GRUPO_CLIENTE = gc.COD_GR_CLIENTE
  └── LEFT JOIN MCANET_DB_PEDIDO (p_inner)
      ON o.PEDIDO_MERCANET = p_inner.DB_PED_NRO
```

---

## 7. CNPJs Especiais

| CNPJ | Tratamento |
|------|------------|
| `099999999999999` | Substituído por '0' (CNPJ genérico) |
| `99999999999999` | Substituído por '0' (CNPJ genérico) |

---

## 8. Filtros Disponíveis na Aplicação

| Filtro | Tipo | Descrição |
|--------|------|----------|
| `dt_ini` / `dt_fim` | Date range | Período livre |
| `ano` | Multi-select | Ano(s) |
| `mes` | Multi-select | Mês(es) |
| `dia` | Multi-select | Dia(s) do mês |
| `semana` | Multi-select | Semana (formato: `YYYY-MM-DD\|YYYY-MM-DD`) |
| `planta` | Multi-select | Planta(s) |
| `grupo_cliente` | Multi-select | Grupo(s) de cliente |
| `canal` | Multi-select | Canal/Cluster |
| `responsavel` | Multi-select | Responsável N1 |
| `status` | Multi-select | Status do pedido |
| `busca` | Text | Busca livre por nº pedido ou CNPJ |
| `tipo_frete` | Multi-select | CIF / FOB |
| `transportadora` | Multi-select | Transportadora |
| `remessa` | Multi-select | Nº da remessa |
