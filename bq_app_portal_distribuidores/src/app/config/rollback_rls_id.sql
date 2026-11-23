-- Rollback dos filtros nativos. Os aplicativos também devem voltar às versões anteriores
-- para retomar a autorização por CNPJ; a tabela por ID permanece preservada.
ALTER TABLE cat_dnabb_dv.opebrapodis_sz.tbl_factdy_sellin SET ROW FILTER cat_dnabb_dv.opebrapodis_sz.fn_rls_distribuidor ON (CNPJ_DISTRIBUIDOR);
ALTER TABLE cat_dnabb_dv.opebrapodis_sz.tbl_factdy_sellout SET ROW FILTER cat_dnabb_dv.opebrapodis_sz.fn_rls_distribuidor ON (CNPJ_DISTRIBUIDOR);
ALTER TABLE cat_dnabb_dv.opebrapodis_sz.tbl_factdy_stock SET ROW FILTER cat_dnabb_dv.opebrapodis_sz.fn_rls_distribuidor ON (CNPJ_DISTRIBUIDOR);
ALTER TABLE cat_dnabb_dv.opebrapodis_sz.tbl_factdy_order DROP ROW FILTER;
