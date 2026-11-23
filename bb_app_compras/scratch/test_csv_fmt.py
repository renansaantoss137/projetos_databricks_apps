import io
import csv

val_test = [
    ("52", "300000910471574", "26089060703", "2026-09-26", 726000.0, "IRMAOS MELLO; LTDA", "SP4-26002 - BB: PÃO RUSTIK")
]

col_types = ['text', 'text', 'text', 'date', 'currency', 'text', 'text']
header_labels = ['Nota Fiscal', 'Nº RI', 'Nº OC', 'Data Lançamento', 'Valor Líquido BRL', 'Fornecedor', 'Descrição']

def fmt_val(val, c_type):
    if val is None:
        return ''
    elif c_type == 'date':
        s = str(val).strip()
        if len(s) >= 10 and s[4] == '-' and s[7] == '-':
            return f'{s[8:10]}/{s[5:7]}/{s[0:4]}'
        return s
    elif c_type == 'currency':
        try:
            return f'{float(val):.2f}'.replace('.', ',')
        except:
            return str(val)
    elif c_type == 'integer':
        try:
            return str(int(round(float(val))))
        except:
            return str(val)
    else:
        s = str(val).replace('"', '""')
        return f'"{s}"'

lines = ['\ufeff']
lines.append(';'.join([f'"{h}"' for h in header_labels]) + '\r\n')
for r in val_test:
    line_vals = [fmt_val(r[i], col_types[i]) for i in range(len(r))]
    lines.append(';'.join(line_vals) + '\r\n')

csv_text = "".join(lines)
print("CSV text snippet:")
print(csv_text[:200])
print("UTF-8 BOM present:", csv_text.startswith('\ufeff'))
