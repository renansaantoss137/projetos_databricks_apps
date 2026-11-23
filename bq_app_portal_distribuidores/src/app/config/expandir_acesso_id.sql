-- Etapa expansiva: cadastro por ID, sem modificar os vínculos anteriores.
CREATE TABLE IF NOT EXISTS cat_dnabb_dv.opebrapodis_sz.tbl_dim_distributor_user_id_mapping (
  user_email STRING NOT NULL,
  id_distribuidor STRING NOT NULL,
  distributor_name STRING,
  is_active BOOLEAN,
  valid_from_date DATE,
  valid_to_date DATE,
  created_by_user STRING,
  storeday TIMESTAMP
) USING DELTA;

-- Migrar apenas CNPJs com exatamente um ID observado. Os demais continuam na tabela antiga.
MERGE INTO cat_dnabb_dv.opebrapodis_sz.tbl_dim_distributor_user_id_mapping AS destino
USING (
  WITH fatos AS (
    SELECT DISTINCT LPAD(CAST(CNPJ_DISTRIBUIDOR AS STRING), 14, '0') AS cnpj,
      CAST(ID_DISTRIBUIDOR AS STRING) AS id_distribuidor
    FROM cat_dnabb_dv.opebrapodis_sz.tbl_factdy_sellin WHERE ID_DISTRIBUIDOR > 0
    UNION
    SELECT DISTINCT LPAD(CAST(CNPJ_DISTRIBUIDOR AS STRING), 14, '0'),
      CAST(ID_DISTRIBUIDOR AS STRING)
    FROM cat_dnabb_dv.opebrapodis_sz.tbl_factdy_sellout WHERE ID_DISTRIBUIDOR > 0
  ), unicos AS (
    SELECT cnpj, MIN(id_distribuidor) AS id_distribuidor
    FROM fatos WHERE cnpj <> '00000000000000'
    GROUP BY cnpj HAVING COUNT(DISTINCT id_distribuidor) = 1
  )
  SELECT LOWER(TRIM(m.user_email)) AS user_email, u.id_distribuidor,
    MAX(m.distributor_name) AS distributor_name,
    MIN(m.valid_from_date) AS valid_from_date,
    CASE WHEN COUNT_IF(m.valid_to_date IS NULL) > 0 THEN CAST(NULL AS DATE)
         ELSE MAX(m.valid_to_date) END AS valid_to_date
  FROM cat_dnabb_dv.opebrapodis_sz.tbl_dim_distributor_user_mapping m
  JOIN unicos u ON u.cnpj = LPAD(REGEXP_REPLACE(CAST(m.distributor_cnpj_code AS STRING), '[^0-9]', ''), 14, '0')
  WHERE m.is_active = TRUE AND (m.valid_to_date IS NULL OR m.valid_to_date >= CURRENT_DATE())
  GROUP BY LOWER(TRIM(m.user_email)), u.id_distribuidor
) AS origem
ON destino.user_email = origem.user_email AND destino.id_distribuidor = origem.id_distribuidor
WHEN NOT MATCHED THEN INSERT (user_email, id_distribuidor, distributor_name, is_active, valid_from_date, valid_to_date, created_by_user, storeday)
VALUES (origem.user_email, origem.id_distribuidor, origem.distributor_name, TRUE, origem.valid_from_date, origem.valid_to_date, 'migration_id', CURRENT_TIMESTAMP());
