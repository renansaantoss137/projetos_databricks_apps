-- =============================================================================
-- PORTAL DISTRIBUIDORES BIMBO QSR — SCRIPT DE SEGURANÇA DATABRICKS (RLS + STAR SCHEMA)
-- Tabela de Controle de Acesso, Views de Segurança e Relacionamento Dimensional
-- Catalog: cat_dnabb_dv | Schema: bracatlg_lz / opebrapodis_sz
-- =============================================================================

-- 1. Tabela Virtual de De-Para de Controle de Acesso de Usuários (RLS Centralizada)
CREATE TABLE IF NOT EXISTS cat_dnabb_dv.bracatlg_lz.acesso_distribuidores (
  EMAIL STRING NOT NULL,
  SENHA STRING NOT NULL,
  DESC_DISTRIBUIDOR STRING,
  CNPJ_DISTRIBUIDOR STRING,
  PERFIL STRING NOT NULL, -- 'admin' | 'distribuidor'
  STATUS STRING DEFAULT 'ATIVO',
  CRIADO_EM TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- 2. Carga Inicial dos Usuários Admin e Distribuidores Cadastrados
INSERT INTO cat_dnabb_dv.bracatlg_lz.acesso_distribuidores 
  (EMAIL, SENHA, DESC_DISTRIBUIDOR, CNPJ_DISTRIBUIDOR, PERFIL, STATUS) 
VALUES
  -- Administrador Bimbo QSR (Acesso Total a 100% da Base)
  ('admin@grupobimbo.com', 'Admin@123', NULL, NULL, 'admin', 'ATIVO'),
  ('admin.qsr@grupobimbo.com', 'Admin@123', NULL, NULL, 'admin', 'ATIVO'),

  -- Distribuidores Mapeados por E-mail, Descrição e CNPJ Oficial (Lucas -> 46780581000122)
  ('lucas.silva01@grupobimbo.com', 'Lucas@Bimbo2026!', 'ALPI DISTRIBUIDORA DE PRODUTOS ALIMENTICIOS LTDA', '46780581000122', 'distribuidor', 'ATIVO'),
  ('castro@distribuidor.com', 'Dist@123', 'CASTRO DISTRIBUIDORA', '24378897000150', 'distribuidor', 'ATIVO'),
  ('demarchi.bsb@distribuidor.com', 'Dist@123', 'DEMARCHI BRASILIA', '01234567000199', 'distribuidor', 'ATIVO'),
  ('speers@distribuidor.com', 'Dist@123', 'SPEERS FOODS', '98765432000188', 'distribuidor', 'ATIVO'),
  ('alpi@distribuidor.com', 'Dist@123', 'ALPI DISTRIBUIDORA DE PRODUTOS ALIMENTICIOS LTDA', '11223344000155', 'distribuidor', 'ATIVO'),
  ('frigodario@distribuidor.com', 'Dist@123', 'FRIGODARIO COMERCIAL E LOGISTICA LTDA', '55667788000199', 'distribuidor', 'ATIVO'),
  ('demarchi.recife@distribuidor.com', 'Dist@123', 'DEMARCHI RECIFE', '66778899000111', 'distribuidor', 'ATIVO'),
  ('demarchi.curitiba@distribuidor.com', 'Dist@123', 'DEMARCHI CURITIBA', '77889900000122', 'distribuidor', 'ATIVO'),
  ('k2@distribuidor.com', 'Dist@123', 'K2 DISTRIBUIDORA', '88990011000133', 'distribuidor', 'ATIVO'),
  ('globalmalle@distribuidor.com', 'Dist@123', 'GLOBAL MALLE DISTRIBUICAO LTDA', '99001122000144', 'distribuidor', 'ATIVO'),
  ('riofrut@distribuidor.com', 'Dist@123', 'RIOFRUT COMERCIAL LTDA', '10111213000155', 'distribuidor', 'ATIVO'),
  ('multifrios@distribuidor.com', 'Dist@123', 'MULTIFRIOS MS', '14151617000166', 'distribuidor', 'ATIVO'),
  ('montesion@distribuidor.com', 'Dist@123', 'MONTE SION', '18192021000177', 'distribuidor', 'ATIVO');


-- 3. Função de Segurança RLS Nativa do Databricks Unity Catalog
CREATE OR REPLACE FUNCTION cat_dnabb_dv.opebrapodis_sz.fn_rls_distribuidor(
  cnpj_distribuidor_linha STRING
)
RETURN 
  LOWER(TRIM(session_user())) IN (
    'bruno.fellipe@grupobimbo.com',
    'ana.ferraz@grupobimbo.com',
    'daniel.moreira@grupobimbo.com',
    'renan.ferreira@grupobimbo.com'
  )
  OR
  EXISTS (
    SELECT 1 
    FROM cat_dnabb_dv.opebrapodis_sz.tbl_dim_distributor_user_mapping d
    WHERE LOWER(TRIM(d.user_email)) = LOWER(TRIM(session_user()))
      AND d.is_active = TRUE
      AND (d.valid_to_date IS NULL OR d.valid_to_date >= CURRENT_DATE())
      AND TRY_CAST(d.distributor_cnpj_code AS BIGINT) = TRY_CAST(cnpj_distribuidor_linha AS BIGINT)
  );

-- 4. Aplicando Row Filters nas Tabelas Fato (Unity Catalog RLS)
ALTER TABLE cat_dnabb_dv.opebrapodis_sz.tbl_factdy_sellin
  SET ROW FILTER cat_dnabb_dv.opebrapodis_sz.fn_rls_distribuidor ON (CNPJ_DISTRIBUIDOR);

ALTER TABLE cat_dnabb_dv.opebrapodis_sz.tbl_factdy_sellout
  SET ROW FILTER cat_dnabb_dv.opebrapodis_sz.fn_rls_distribuidor ON (CNPJ_DISTRIBUIDOR);

ALTER TABLE cat_dnabb_dv.opebrapodis_sz.tbl_factdy_stock
  SET ROW FILTER cat_dnabb_dv.opebrapodis_sz.fn_rls_distribuidor ON (CNPJ_DISTRIBUIDOR);

-- 5. Views Dimensionais Star Schema Com RLS e Filtro Global PASTA_FONTE = 'BQB'
CREATE OR REPLACE VIEW cat_dnabb_dv.bracatlg_lz.vw_dim_clientes_rls AS
SELECT 
  c.CNPJ_CLIENTE,
  c.CNPJ_DISTRIBUIDOR,
  c.RAZAO_SOCIAL,
  c.UF,
  c.PASTA_FONTE
FROM cat_dnabb_dv.bracatlg_lz.clientes_distribuidores c
WHERE c.PASTA_FONTE = 'BQB';

CREATE OR REPLACE VIEW cat_dnabb_dv.bracatlg_lz.vw_dim_produtos_rls AS
SELECT 
  p.SKU_DISTRIB,
  p.DESC_PRODUTO_ARQUIVO_DIST,
  p.CNPJ_DISTRIBUIDOR
FROM cat_dnabb_dv.bracatlg_lz.produtos_distribuidores p;
