import io
from datetime import datetime
from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

wb = Workbook()
ws = wb.active
ws.title = "Notas Fiscais"

active_defs = [
    ('NOTA_FISCAL', 'Nota Fiscal', 'text'),
    ('NUMERO_OC', 'Nº OC', 'text'),
    ('CNPJ_BIMBO', 'CNPJ Bimbo', 'text'),
    ('NOME_FORNECEDOR', 'Fornecedor', 'text'),
    ('DT_NOTA', 'Dt Emissão NF', 'date'),
    ('VALOR_LIQUIDO_BRL', 'Valor Líquido BRL', 'currency'),
    ('QUANTIDADE', 'Quantidade', 'integer'),
]

headers = [d[1] for d in active_defs]
ws.append(headers)

sample_data = [
    ['58', '26089060703', '35402759000185', 'IRMAOS MELLO INDUSTRIA E COMERCIO LTDA', '2026-10-02', 726000.0, 1],
    ['58', '26089060703', '35402759000185', 'IRMAOS MELLO INDUSTRIA E COMERCIO LTDA', '2026-10-02', 0.0, 1],
    ['52', '26089060703', '35402759000185', 'IRMAOS MELLO INDUSTRIA E COMERCIO LTDA', '2026-09-08', 726000.0, 1],
    ['52', '26089060703', '35402759000185', 'IRMAOS MELLO INDUSTRIA E COMERCIO LTDA', '2026-09-08', 0.0, 1],
]

row_count = 0
for row in sample_data:
    row_count += 1
    row_vals = []
    for idx, val in enumerate(row):
        c_type = active_defs[idx][2]
        if val is None or val == '':
            row_vals.append(None)
        elif c_type == 'date':
            s = str(val).strip()
            if len(s) >= 10 and s[4] == '-' and s[7] == '-':
                row_vals.append(f'{s[8:10]}/{s[5:7]}/{s[0:4]}')
            else:
                row_vals.append(s)
        elif c_type == 'currency':
            try:
                row_vals.append(float(val))
            except:
                row_vals.append(val)
        elif c_type == 'integer':
            try:
                row_vals.append(int(round(float(val))))
            except:
                row_vals.append(val)
        else:
            row_vals.append(str(val))
    ws.append(row_vals)

# Formatar como Tabela Clara
if row_count > 0:
    last_col = get_column_letter(len(headers))
    last_row = row_count + 1
    tab = Table(displayName="TabelaRelatorio", ref=f"A1:{last_col}{last_row}")
    tab_style = TableStyleInfo(
        name="TableStyleLight1",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False
    )
    tab.tableStyleInfo = tab_style
    ws.add_table(tab)

# Moedas
for idx, d in enumerate(active_defs):
    if d[2] == 'currency':
        col_letter = get_column_letter(idx + 1)
        for row_idx in range(2, row_count + 2):
            ws[f'{col_letter}{row_idx}'].number_format = 'R$ #,##0.00;[Red]-R$ #,##0.00;"R$ 0,00"'

# Auto-adjust column widths
for col_idx, d in enumerate(active_defs, start=1):
    col_letter = get_column_letter(col_idx)
    max_len = len(d[1])
    for r in range(2, min(row_count + 2, 202)):
        val_str = str(ws[f'{col_letter}{r}'].value or '')
        if len(val_str) > max_len:
            max_len = len(val_str)
    ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 45)

buf = io.BytesIO()
wb.save(buf)
print("XLSX Bytes size:", len(buf.getvalue()))
