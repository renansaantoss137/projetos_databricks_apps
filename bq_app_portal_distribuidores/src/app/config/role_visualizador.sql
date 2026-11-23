-- Libera o papel VISUALIZADOR em tbl_dim_app_admin (vê todos os distribuidores, sem governança).
-- Rodar antes de conceder o primeiro VISUALIZADOR: sem isso o INSERT falha em chk_role.
ALTER TABLE cat_dnabb_dv.opebrapodis_sz.tbl_dim_app_admin DROP CONSTRAINT chk_role;
ALTER TABLE cat_dnabb_dv.opebrapodis_sz.tbl_dim_app_admin
  ADD CONSTRAINT chk_role CHECK (role IN ('MASTER', 'ADMIN', 'VISUALIZADOR'));
ALTER TABLE cat_dnabb_dv.opebrapodis_sz.tbl_dim_app_admin
  ALTER COLUMN role COMMENT 'Perfil: MASTER (vê tudo + gerencia admins), ADMIN (vê todos os distribuidores + concede acessos) ou VISUALIZADOR (vê todos os distribuidores, sem governança)';

-- Rollback (revogue antes os VISUALIZADOR ativos e inativos, ou o ADD CONSTRAINT falha):
-- ALTER TABLE cat_dnabb_dv.opebrapodis_sz.tbl_dim_app_admin DROP CONSTRAINT chk_role;
-- ALTER TABLE cat_dnabb_dv.opebrapodis_sz.tbl_dim_app_admin ADD CONSTRAINT chk_role CHECK (role IN ('MASTER', 'ADMIN'));
