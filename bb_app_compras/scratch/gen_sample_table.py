from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

wb = Workbook()
ws = wb.active
ws.title = "Notas Fiscais"

headers = [
    "Nota Fiscal", "Nº OC", "CNPJ Bimbo", "Fornecedor", "Ds Item", 
    "Data Lançamento", "Valor Líquido BRL", "Status Pagamento"
]
ws.append(headers)

sample_rows = [
    ["58", "26089060703", "35402759000185", "IRMAOS MELLO INDUSTRIA E COMERCIO LTDA", "SP4-26002 - BB: PÃO RUSTIK", "07/10/2026", 726000.0, "Pago"],
    ["58", "26089060703", "35402759000185", "IRMAOS MELLO INDUSTRIA E COMERCIO LTDA", "SP4-26002 - BB: PÃO RUSTIK", "07/10/2026", 0.0, "Pago"],
    ["52", "26089060703", "35402759000185", "IRMAOS MELLO INDUSTRIA E COMERCIO LTDA", "SP4-26002 - BB: PÃO RUSTIK", "26/09/2026", 726000.0, "Pago"],
    ["52", "26089060703", "35402759000185", "IRMAOS MELLO INDUSTRIA E COMERCIO LTDA", "SP4-26002 - BB: PÃO RUSTIK", "26/09/2026", 0.0, "Pago"],
]

for row in sample_rows:
    ws.append(row)

# Formatar como Tabela Clara (Estilo "Clara 1" ou "Clara 2")
last_col = get_column_letter(len(headers))
last_row = len(sample_rows) + 1
tab = Table(displayName="TabelaNotas", ref=f"A1:{last_col}{last_row}")

# TableStyleLight1 = Estilo Claro 1 (zebrado em cinza/branco com bordas e cabeçalho cinza)
style = TableStyleInfo(
    name="TableStyleLight1",
    showFirstColumn=False,
    showLastColumn=False,
    showRowStripes=True,
    showColumnStripes=False
)
tab.tableStyleInfo = style
ws.add_table(tab)

# Ajustar largura das colunas
for col in ws.columns:
    max_len = max(len(str(cell.value or '')) for cell in col)
    col_letter = get_column_letter(col[0].column)
    ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

wb.save("scratch/exemplo_tabela_clara.xlsx")
print("Saved scratch/exemplo_tabela_clara.xlsx")
