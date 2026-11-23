-- Nova função; a ativação dos filtros fica separada para permitir validação e rollback.
CREATE OR REPLACE FUNCTION cat_dnabb_dv.opebrapodis_sz.fn_rls_distribuidor_id(
  id_distribuidor_linha STRING, cnpj_distribuidor_linha STRING
)
RETURN
LOWER(TRIM(session_user())) LIKE '%46439f81%'
  OR LOWER(TRIM(session_user())) = 'ed51e6cf-8b26-4cd4-aeb7-77d84ebef197'
  OR LOWER(TRIM(session_user())) LIKE '%05577799%'
  OR LOWER(TRIM(session_user())) LIKE '%portal-distribuidores%'
  OR LOWER(TRIM(session_user())) IN (
    '46439f81-6e3f-4c66-ae17-232900143dc9',
    '05577799-e0de-4e37-8e4b-d06a8f306e72',
    'app-4q6vld portal-distribuidores-dev',
    'app-4q6vld portal-distribuidores'
  )
  -- 2. Admin/Master ativo: acesso total (precedência sobre o mapping)
  OR EXISTS (
    SELECT 1 FROM cat_dnabb_dv.opebrapodis_sz.tbl_dim_app_admin a
    WHERE LOWER(TRIM(a.user_email)) = LOWER(TRIM(session_user()))
      AND a.is_active = TRUE
  )
  OR EXISTS (
    SELECT 1 FROM cat_dnabb_dv.opebrapodis_sz.tbl_dim_distributor_user_id_mapping d
    WHERE LOWER(TRIM(d.user_email)) = LOWER(TRIM(session_user()))
      AND d.is_active = TRUE
      AND (d.valid_to_date IS NULL OR d.valid_to_date >= CURRENT_DATE())
      AND CAST(d.id_distribuidor AS STRING) = CAST(id_distribuidor_linha AS STRING)
  )
  OR (
    NOT EXISTS (SELECT 1 FROM cat_dnabb_dv.opebrapodis_sz.tbl_dim_distributor_user_id_mapping i
                WHERE LOWER(TRIM(i.user_email)) = LOWER(TRIM(session_user())))
    AND EXISTS (
      SELECT 1 FROM cat_dnabb_dv.opebrapodis_sz.tbl_dim_distributor_user_mapping d
      WHERE LOWER(TRIM(d.user_email)) = LOWER(TRIM(session_user()))
        AND d.is_active = TRUE
        AND (d.valid_to_date IS NULL OR d.valid_to_date >= CURRENT_DATE())
        AND LPAD(REGEXP_REPLACE(d.distributor_cnpj_code, '[^0-9]', ''), 14, '0')
          = LPAD(REGEXP_REPLACE(cnpj_distribuidor_linha, '[^0-9]', ''), 14, '0')
    )
  )
