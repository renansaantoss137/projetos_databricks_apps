from databricks.sdk import WorkspaceClient
import json

w = WorkspaceClient()

queries = {
    "count_vendas": "SELECT count(*) as total_rows, min(DT_ENTREGA) as min_dt, max(DT_ENTREGA) as max_dt FROM cat_dnabb_dv.grobbbqb_sz.vendas_pedidos_bq",
    "kpis_outubro": """
        SELECT 
            sum(VENDA_LIQUIDA_VLR) as total_invoiced,
            count(*) as qtd_pedidos
        FROM cat_dnabb_dv.grobbbqb_sz.vendas_pedidos_bq
        WHERE year(DT_ENTREGA) = 2026 AND month(DT_ENTREGA) = 10
    """,
    "budget_forecast_outubro": """
        SELECT 
            TIPO_REGISTRO,
            sum(FORECAST_VALOR) as total_valor,
            sum(FORECAST_QTDE) as total_qtde
        FROM cat_dnabb_dv.grobbbqb_sz.budget_forecast_bq
        WHERE ANO = 2026 AND MES = 10
        GROUP BY TIPO_REGISTRO
    """,
    "count_produtos": "SELECT count(*) FROM cat_dnabb_dv.bracatlg_lz.produtos_view",
    "count_grupo_clientes": "SELECT count(*) FROM cat_dnabb_dv.bracatlg_lz.grupo_clientes_view"
}

for name, q in queries.items():
    print(f"\n--- Running: {name} ---")
    res = w.statement_execution.execute_statement(
        warehouse_id="f4a2e26b8410f1e3",
        statement=q,
        wait_timeout="45s"
    )
    if res.result and res.result.data_array:
        print("Columns:", [col.name for col in res.manifest.schema.columns])
        for row in res.result.data_array:
            print("Row:", row)
    else:
        print("State:", res.status.state, "Error:", res.status.error)
