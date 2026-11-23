-- Portal Distribuidores: lista de distribuidores liberados (sell-out validado) e log de acesso.
-- Rodar uma vez no SQL Warehouse. Depois disso a lista é mantida pela aba
-- "Distribuidores no portal" da Gestão de Acessos (MASTER/ADMIN).
-- Deploy: o service principal do app precisa de SELECT e MODIFY nas duas tabelas.

CREATE TABLE IF NOT EXISTS cat_dnabb_dv.opebrapodis_sz.tbl_dim_distribuidor_portal (
  id_distribuidor INT NOT NULL COMMENT 'ID_DISTRIBUIDOR (COD_GR_CLIENTE). Chave da regra.',
  nome_referencia STRING COMMENT 'Nome informado no cadastro (só referência, o portal exibe DESC_DISTRIBUIDOR_DNA)',
  cnpj_referencia STRING COMMENT 'CNPJ informativo, 14 dígitos. Não é usado na regra.',
  is_active BOOLEAN NOT NULL COMMENT 'TRUE: aparece no portal e seus usuários acessam',
  notes STRING,
  created_by STRING,
  created_at TIMESTAMP,
  updated_by STRING,
  updated_at TIMESTAMP
) COMMENT 'Distribuidores exibidos no Portal Distribuidores (sell-out validado). Mantida pelo app.';

CREATE TABLE IF NOT EXISTS cat_dnabb_dv.opebrapodis_sz.tbl_log_app_access (
  event_id STRING NOT NULL,
  event_ts TIMESTAMP NOT NULL,
  event_date DATE NOT NULL COMMENT 'Data em America/Sao_Paulo',
  user_email STRING NOT NULL,
  role STRING COMMENT 'MASTER, ADMIN, VISUALIZADOR ou NULL (distribuidor)',
  perfil STRING COMMENT 'admin, distribuidor ou simulacao',
  pagina STRING,
  dist_ids STRING COMMENT 'IDs de distribuidor do usuário, separados por vírgula',
  session_id STRING,
  source STRING COMMENT 'APP ou LOCAL'
) COMMENT 'Acessos ao Portal Distribuidores: no máximo 1 registro por usuário/página a cada 30 min.';

MERGE INTO cat_dnabb_dv.opebrapodis_sz.tbl_dim_distribuidor_portal t
USING (SELECT * FROM VALUES
  (86, 'ALPI DISTRIBUIDORA DE PRODUTOS ALIMENTICIOS LTDA', '46780581000122'),
  (176, 'ALPI MARILIA DISTRIBUIDORA', '46780581000807'),
  (171, 'BLUE FOOD', '55504737000214'),
  (133, 'BRASSOL TO', '08529883000133'),
  (11, 'BURGUER FOODS JEDIMIX', '31448685000167'),
  (169, 'BUY FOOD SERVICE', '55794744000117'),
  (147, 'CASTRO DISTRIBUIDORA', '24378897000150'),
  (84, 'COMERCIAL AC DISTRIBOM', '38212891000112'),
  (135, 'DALAC', '22801194000167'),
  (138, 'DEMARCHI BELEM', '36748710000141'),
  (155, 'DEMARCHI BRASILIA', '07646239000182'),
  (106, 'DEMARCHI CURITIBA', '26020678000120'),
  (107, 'DEMARCHI MARINGÁ', '10862181000119'),
  (113, 'DEMARCHI MINAS ACCIMIX', '06249941000140'),
  (137, 'Demarchi Recife', '18434711000130'),
  (127, 'DEMARCHI SP NETFEIRA', '03974724000205'),
  (88, 'FAMILY GO', '33116163000193'),
  (36, 'FOCATTO', '04902760000145'),
  (83, 'GARDEN FOODS', '02152891000127'),
  (170, 'GLOBAL MALLE DISTRIBUICAO LTDA', '34734539000196'),
  (85, 'K2 DISTRIBUIDORA', '32805719000196'),
  (116, 'MONTE SION', '86921160000784'),
  (112, 'MULTIFRIOS MS', '10705634000101'),
  (144, 'PAZOTTI', '52612033000196'),
  (35, 'POLINA', '77663169000156'),
  (158, 'RIOFRUT COMERCIAL LTDA', '03908177000189'),
  (87, 'SPEERS FOODS', '04767553000125')
  AS v(id_distribuidor, nome_referencia, cnpj_referencia)) s
ON t.id_distribuidor = s.id_distribuidor
WHEN NOT MATCHED THEN INSERT (id_distribuidor, nome_referencia, cnpj_referencia, is_active, notes, created_by, created_at, updated_by, updated_at)
  VALUES (s.id_distribuidor, s.nome_referencia, s.cnpj_referencia, TRUE, 'Carga inicial (DTs Ok.xlsx)', 'renan.ferreira@grupobimbo.com', from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo'), 'renan.ferreira@grupobimbo.com', from_utc_timestamp(current_timestamp(), 'America/Sao_Paulo'));
