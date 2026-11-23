import time
import io
from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo

t0 = time.time()
wb = Workbook()
ws = wb.active
ws.title = "Notas Fiscais"

headers = ["Nota Fiscal", "Nº OC", "CNPJ Bimbo", "Fornecedor", "Data", "Valor"]
ws.append(headers)

for i in range(50000):
    ws.append(["52", "26089060703", "35402759000185", "IRMAOS MELLO LTDA", "26/09/2026", 726000.0])

tab = Table(displayName="TabelaRelatorio", ref=f"A1:F{50001}")
style = TableStyleInfo(name="TableStyleLight1", showFirstColumn=False,
                       showLastColumn=False, showRowStripes=True, showColumnStripes=False)
tab.tableStyleInfo = style
ws.add_table(tab)

buf = io.BytesIO()
wb.save(buf)
t1 = time.time()
print(f"Generated 50,000 rows XLSX in {t1 - t0:.2f}s, size: {len(buf.getvalue())/1024:.1f} KB")
