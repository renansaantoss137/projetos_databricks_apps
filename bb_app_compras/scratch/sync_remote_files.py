import base64
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace

w = WorkspaceClient()

# 1. Upload docs/sql/vw_ordens_compra.sql
with open("docs/sql/vw_ordens_compra.sql", "r", encoding="utf-8") as f:
    sql_content = f.read()

target_sql = "/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/prod/files/docs/sql/vw_ordens_compra.sql"
w.workspace.import_(
    path=target_sql,
    content=base64.b64encode(sql_content.encode("utf-8")).decode("utf-8"),
    format=workspace.ExportFormat.AUTO,
    overwrite=True
)
print("[OK] Uploaded vw_ordens_compra.sql to", target_sql)

# 2. Upload src/dados/compras_360_lakebase_etl (as source notebook)
with open("src/dados/compras_360_lakebase_etl.py", "r", encoding="utf-8") as f:
    etl_content = f.read()

target_etl = "/Workspace/Shared/CONSULTAS_AUTOMATIZADAS/compras_360/prod/files/src/dados/compras_360_lakebase_etl"
w.workspace.import_(
    path=target_etl,
    content=base64.b64encode(etl_content.encode("utf-8")).decode("utf-8"),
    format=workspace.ExportFormat.SOURCE,
    language=workspace.Language.PYTHON,
    overwrite=True
)
print("[OK] Uploaded compras_360_lakebase_etl to", target_etl)
