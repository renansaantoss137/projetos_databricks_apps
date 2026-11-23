with open("src/dados/compras_360_lakebase_etl.py", "r", encoding="utf-8") as f:
    code = f.read()

target = """    com_saving AS (
        SELECT *,
            -- Preço anterior: LAG sobre notas fiscais do mesmo item+fornecedor, em BRL
            LAG(CASE WHEN _preco_brl > 0 THEN _preco_brl END) OVER (
                PARTITION BY CODIGO_ITEM, _vendor_key 
                ORDER BY DT_NOTA, NUMERO_RI
            ) AS _preco_ant_brl,
            -- Primeiro preço do ano (base anual) em BRL
            FIRST_VALUE(CASE WHEN _preco_brl > 0 THEN _preco_brl END, true) OVER (
                PARTITION BY CODIGO_ITEM, _vendor_key, SUBSTRING(CAST(ANO_MES AS STRING), 1, 4)
                ORDER BY DT_NOTA, NUMERO_RI
            ) AS _base_ano_brl
        FROM base
    )"""

replacement = """    com_saving AS (
        SELECT *,
            -- Chave de item: usa CODIGO_ITEM se existir; se for nulo/vazio, usa descrição normalizada
            -- Preço anterior: LAG sobre notas fiscais do mesmo item+fornecedor/local, em BRL
            LAG(CASE WHEN _preco_brl > 0 THEN _preco_brl END) OVER (
                PARTITION BY 
                    COALESCE(
                        NULLIF(NULLIF(NULLIF(TRIM(CODIGO_ITEM), ''), '~NOVALUE~'), 'VAZIO'),
                        UPPER(TRIM(REGEXP_REPLACE(DS_ITEM, '\\\\s+', ' ')))
                    ), 
                    _vendor_key 
                ORDER BY DT_NOTA, NUMERO_RI
            ) AS _preco_ant_brl,
            -- Descrição anterior para validação de compras sem código
            LAG(DS_ITEM) OVER (
                PARTITION BY 
                    COALESCE(
                        NULLIF(NULLIF(NULLIF(TRIM(CODIGO_ITEM), ''), '~NOVALUE~'), 'VAZIO'),
                        UPPER(TRIM(REGEXP_REPLACE(DS_ITEM, '\\\\s+', ' ')))
                    ), 
                    _vendor_key 
                ORDER BY DT_NOTA, NUMERO_RI
            ) AS _ds_item_ant,
            -- Primeiro preço do ano (base anual) em BRL
            FIRST_VALUE(CASE WHEN _preco_brl > 0 THEN _preco_brl END, true) OVER (
                PARTITION BY 
                    COALESCE(
                        NULLIF(NULLIF(NULLIF(TRIM(CODIGO_ITEM), ''), '~NOVALUE~'), 'VAZIO'),
                        UPPER(TRIM(REGEXP_REPLACE(DS_ITEM, '\\\\s+', ' ')))
                    ), 
                    _vendor_key, 
                    SUBSTRING(CAST(ANO_MES AS STRING), 1, 4)
                ORDER BY DT_NOTA, NUMERO_RI
            ) AS _base_ano_brl
        FROM base
    )"""

assert target in code, "target not found in compras_360_lakebase_etl.py"
code = code.replace(target, replacement, 1)

with open("src/dados/compras_360_lakebase_etl.py", "w", encoding="utf-8", newline="") as f:
    f.write(code)
print("Updated src/dados/compras_360_lakebase_etl.py successfully!")
