from databricks.sdk import WorkspaceClient
import pandas as pd

w = WorkspaceClient()

# 1. Query compradores_funcionais
print("1. Querying compradores_funcionais...")
res_cf = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement="""
    SELECT 
        TRIM(USUARIO_ORACLE) AS USUARIO_ORACLE,
        TRIM(ID) AS ID,
        TRIM(COMPRADOR_FUNCIONAL) AS NOME_COMPRADOR,
        TRIM(EMAIL) AS EMAIL,
        TRIM(AREA) AS AREA,
        TRIM(UNIDADE) AS UNIDADE,
        TRIM(OPERACAO) AS OPERACAO,
        TRIM(OBS) AS OBS
    FROM cat_dnabb_dv.grobbcompr_cz.compradores_funcionais
    WHERE UPPER(AREA) LIKE '%COMPRA%'
    ORDER BY COMPRADOR_FUNCIONAL
    """,
    wait_timeout='30s'
)

cols_cf = [c.name for c in res_cf.manifest.schema.columns]
data_cf = res_cf.result.data_array
df_cf = pd.DataFrame(data_cf, columns=cols_cf)
print(f"-> Total na tabela de Compradores Funcionais com área 'Compras': {len(df_cf)}")

# 2. Query distinct buyers from vw_ordens_compra who had CENTRALIZADO = 'CENTRALIZADO' in recent years
print("\n2. Querying distinct buyers with Centralizado in vw_ordens_compra...")
res_oc = w.statement_execution.execute_statement(
    warehouse_id='f4a2e26b8410f1e3',
    statement="""
    SELECT 
        COALESCE(COMPRADOR, NOME_USUARIO, USUARIO) AS NOME,
        USUARIO AS USUARIO_ORACLE,
        USUARIO_COMPRADOR,
        EMAIL_COMPRADOR,
        DEPARTAMENTO_COMPRADOR,
        COUNT(DISTINCT NUMERO_OC) AS QTD_OCS,
        ROUND(SUM(VALOR_ORIGINAL), 2) AS TOTAL_VALOR_BRL,
        MIN(SUBSTRING(DATA_OC, 1, 4)) AS PRIMEIRO_ANO,
        MAX(SUBSTRING(DATA_OC, 1, 4)) AS ULTIMO_ANO
    FROM cat_dnabb_dv.grobbcompr_cz.vw_ordens_compra
    WHERE CENTRALIZADO = 'CENTRALIZADO'
      AND DATA_OC >= '2024-01-01'
    GROUP BY 1, 2, 3, 4, 5
    ORDER BY TOTAL_VALOR_BRL DESC
    """,
    wait_timeout='45s'
)

cols_oc = [c.name for c in res_oc.manifest.schema.columns]
data_oc = res_oc.result.data_array
df_oc = pd.DataFrame(data_oc, columns=cols_oc)
print(f"-> Total de compradores/usuários com OCs Centralizadas (2024-2026): {len(df_oc)}")

# 3. Create unified Excel with multiple detailed tabs
out_excel = "usuarios_compra_centralizada_area_compras.xlsx"
out_csv = "usuarios_compradores_funcionais_compras.csv"

with pd.ExcelWriter(out_excel, engine='openpyxl') as writer:
    # Aba 1: Cadastro Oficial de Compradores da Área de Compras (compradores_funcionais)
    df_cf.to_excel(writer, sheet_name="Cad_Area_Compras", index=False)
    # Aba 2: Compradores com OCs Centralizadas no Sistema (2024 a 2026)
    df_oc.to_excel(writer, sheet_name="Compradores_OCs_Centralizadas", index=False)

df_cf.to_csv(out_csv, sep=';', index=False, encoding='utf-8-sig')

print(f"\nExcel gerado com sucesso: {out_excel}")
print(f"CSV gerado com sucesso: {out_csv}")
