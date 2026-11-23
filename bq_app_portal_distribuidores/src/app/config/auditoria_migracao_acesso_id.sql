-- Auditoria de migração de acessos por CNPJ para ID_DISTRIBUIDOR.
-- Somente leitura. Exibe os vínculos ativos sem correspondência única para revisão.
WITH distribuidores AS (
  SELECT DISTINCT LPAD(CAST(CNPJ_DISTRIBUIDOR AS STRING), 14, '0') AS cnpj,
         CAST(ID_DISTRIBUIDOR AS STRING) AS id_distribuidor,
         DESC_DISTRIBUIDOR_DNA AS nome
  FROM cat_dnabb_dv.opebrapodis_sz.tbl_factdy_sellin
  WHERE ID_DISTRIBUIDOR > 0
  UNION
  SELECT DISTINCT LPAD(CAST(CNPJ_DISTRIBUIDOR AS STRING), 14, '0'),
         CAST(ID_DISTRIBUIDOR AS STRING), DESC_DISTRIBUIDOR_DNA
  FROM cat_dnabb_dv.opebrapodis_sz.tbl_factdy_sellout
  WHERE ID_DISTRIBUIDOR > 0
), candidatos AS (
  SELECT cnpj, COUNT(DISTINCT id_distribuidor) AS quantidade_ids,
         SORT_ARRAY(COLLECT_SET(id_distribuidor)) AS ids
  FROM distribuidores GROUP BY cnpj
)
SELECT LOWER(TRIM(m.user_email)) AS email,
       LPAD(REGEXP_REPLACE(CAST(m.distributor_cnpj_code AS STRING), '[^0-9]', ''), 14, '0') AS cnpj,
       m.distributor_name AS nome_cadastrado,
       COALESCE(c.quantidade_ids, 0) AS quantidade_ids,
       c.ids
FROM cat_dnabb_dv.opebrapodis_sz.tbl_dim_distributor_user_mapping m
LEFT JOIN candidatos c
  ON c.cnpj = LPAD(REGEXP_REPLACE(CAST(m.distributor_cnpj_code AS STRING), '[^0-9]', ''), 14, '0')
WHERE m.is_active = TRUE
  AND (m.valid_to_date IS NULL OR m.valid_to_date >= CURRENT_DATE())
  AND COALESCE(c.quantidade_ids, 0) <> 1
ORDER BY email, cnpj;
