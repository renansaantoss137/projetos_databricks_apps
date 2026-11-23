from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Check warehouse
warehouses = list(w.warehouses.list())
wh_id = warehouses[0].id if warehouses else None
print(f"Using warehouse: {wh_id}")

if wh_id:
    # 1. Query Rafael Cordeiro in vw_dim_colaborador_atual
    stmt = w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement="""
            SELECT matricula, id_colaborador, nome_completo, email, area, diretoria, nm_unidade 
            FROM cat_dnabb_dv.cmpbragp360_sz.vw_dim_colaborador_atual
            WHERE UPPER(nome_completo) LIKE '%CORDEIRO%' 
               OR UPPER(nome_completo) LIKE '%CANUTE%'
               OR UPPER(nome_completo) LIKE '%MIRANDA%VITORIA%'
               OR UPPER(nome_completo) LIKE '%MARLENE%SILVA%'
               OR UPPER(nome_completo) LIKE '%MONIQUE%CARVALHO%'
            LIMIT 10
        """,
        wait_timeout="30s"
    )
    print("Colaboradores result:")
    if stmt.result and stmt.result.data_array:
        for row in stmt.result.data_array:
            print(row)
    else:
        print("No rows or error:", stmt.status)

    # 2. Query OC 26089064670 in vw_ordens_compra / OCs
    stmt2 = w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement="""
            SELECT NUMERO_OC, NOME_REQUISITANTE, DEPARTAMENTO_REQUISITANTE, AREA, UNIDADE, COMPRADOR, DEPARTAMENTO_COMPRADOR
            FROM (SELECT * FROM cat_ocloud_r5_dv.rg5glofsn_cz.vw_po_headers_all WHERE SEGMENT1 = '26089064670')
            LIMIT 5
        """,
        wait_timeout="30s"
    )
    print("OC Headers result:")
    if stmt2.result and stmt2.result.data_array:
        for row in stmt2.result.data_array:
            print(row)
