import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# 1. Carregar arquivo base com encoding utf-8-sig
df_raw = pd.read_csv('compradores_funcionais_download.csv', sep=';', encoding='utf-8-sig')

# 2. Filtrar área de Compras
mask_compras = df_raw['Área'].astype(str).str.upper().str.contains('COMPRA')
df_compras = df_raw[mask_compras].copy()

# Normalizar colunas
df_compras['Usuário Oracle'] = df_compras['Usuário Oracle'].astype(str).str.strip()
df_compras['ID'] = df_compras['ID'].fillna('').astype(str).str.strip()
df_compras['Comprador Funcional'] = df_compras['Comprador Funcional'].astype(str).str.strip()
df_compras['E-mail'] = df_compras['E-mail'].fillna('').astype(str).str.strip()
df_compras['Área'] = df_compras['Área'].astype(str).str.strip()
df_compras['Unidade'] = df_compras['Unidade'].fillna('').astype(str).str.strip()
df_compras['Operação'] = df_compras['Operação'].fillna('').astype(str).str.strip()
df_compras['Observações'] = df_compras['Observações'].fillna('').astype(str).str.strip()

# Ordenar alfabeticamente por Nome do Comprador e Usuário Oracle
df_compras = df_compras.sort_values(by=['Comprador Funcional', 'Usuário Oracle']).reset_index(drop=True)

# 3. Criar resumo de compradores únicos
def agg_users(series):
    users = sorted(list(set(series.dropna())))
    return ', '.join(users)

df_unicos = df_compras.groupby('Comprador Funcional').agg(
    Email=('E-mail', 'first'),
    Area=('Área', lambda s: ' / '.join(sorted(set(s)))),
    Unidade=('Unidade', lambda s: ' / '.join(sorted(set(s)))),
    Operacao=('Operação', lambda s: ' / '.join(sorted(set(s)))),
    Qtd_Logins_Oracle=('Usuário Oracle', 'nunique'),
    Logins_Oracle=('Usuário Oracle', agg_users),
    Observacoes=('Observações', lambda s: ' | '.join(sorted(set([x for x in s if x]))))
).reset_index()

df_unicos = df_unicos.sort_values(by='Comprador Funcional').reset_index(drop=True)

# 4. Salvar CSV
csv_filename = "usuarios_area_compras_centralizada.csv"
df_compras.to_csv(csv_filename, sep=';', index=False, encoding='utf-8-sig')

# 5. Criar Workbook Excel formatado
excel_filename = "usuarios_area_compras_centralizada.xlsx"
wb = openpyxl.Workbook()

# Estilos
header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid") # Navy Blue
header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
meta_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
meta_font = Font(name="Calibri", size=10, italic=True, color="475569")
data_font = Font(name="Calibri", size=10, color="0F172A")
bold_font = Font(name="Calibri", size=10, bold=True, color="0F172A")

thin_border = Border(
    left=Side(style='thin', color='CBD5E1'),
    right=Side(style='thin', color='CBD5E1'),
    top=Side(style='thin', color='CBD5E1'),
    bottom=Side(style='thin', color='CBD5E1')
)

# --- ABA 1: Base Completa de Logins Oracle ---
ws1 = wb.active
ws1.title = "Logins Oracle (Compras)"
ws1.views.sheetView[0].showGridLines = True

headers1 = [
    "Usuário Oracle (Login)", "ID / Matrícula", "Nome do Comprador", 
    "E-mail", "Área Cadastrada", "Unidade", "Operação", "Observações"
]

ws1.append(headers1)
for col_num in range(1, len(headers1) + 1):
    cell = ws1.cell(row=1, column=col_num)
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

for row_idx, r in df_compras.iterrows():
    row_vals = [
        r['Usuário Oracle'], r['ID'], r['Comprador Funcional'],
        r['E-mail'], r['Área'], r['Unidade'], r['Operação'], r['Observações']
    ]
    ws1.append(row_vals)
    current_row = row_idx + 2
    for col_num in range(1, len(row_vals) + 1):
        cell = ws1.cell(row=current_row, column=col_num)
        cell.font = data_font
        cell.border = thin_border
        if col_num in (1, 2, 5, 7):
            cell.alignment = Alignment(horizontal="center", vertical="center")
        elif col_num in (3, 4, 6, 8):
            cell.alignment = Alignment(horizontal="left", vertical="center")

# Ajuste automático de largura das colunas
for col in ws1.columns:
    max_len = max(len(str(cell.value or '')) for cell in col)
    col_letter = get_column_letter(col[0].column)
    ws1.column_dimensions[col_letter].width = max(max_len + 4, 12)
ws1.row_dimensions[1].height = 26

# --- ABA 2: Resumo por Comprador Único ---
ws2 = wb.create_sheet(title="Compradores Únicos")
ws2.views.sheetView[0].showGridLines = True

headers2 = [
    "Nome do Comprador", "E-mail", "Área", "Unidade", 
    "Operação", "Qtd Logins Oracle", "Logins Oracle Vinculados", "Observações"
]
ws2.append(headers2)
for col_num in range(1, len(headers2) + 1):
    cell = ws2.cell(row=1, column=col_num)
    cell.fill = PatternFill(start_color="047857", end_color="047857", fill_type="solid") # Emerald Green
    cell.font = header_font
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

for row_idx, r in df_unicos.iterrows():
    row_vals = [
        r['Comprador Funcional'], r['Email'], r['Area'], r['Unidade'],
        r['Operacao'], r['Qtd_Logins_Oracle'], r['Logins_Oracle'], r['Observacoes']
    ]
    ws2.append(row_vals)
    current_row = row_idx + 2
    for col_num in range(1, len(row_vals) + 1):
        cell = ws2.cell(row=current_row, column=col_num)
        cell.font = data_font
        cell.border = thin_border
        if col_num in (3, 4, 5, 6):
            cell.alignment = Alignment(horizontal="center", vertical="center")
        else:
            cell.alignment = Alignment(horizontal="left", vertical="center")

for col in ws2.columns:
    max_len = max(len(str(cell.value or '')) for cell in col)
    col_letter = get_column_letter(col[0].column)
    ws2.column_dimensions[col_letter].width = max(max_len + 4, 14)
ws2.row_dimensions[1].height = 26

# --- ABA 3: Critérios e Regra de Negócio ---
ws3 = wb.create_sheet(title="Critérios de Centralização")
ws3.views.sheetView[0].showGridLines = True

criterios = [
    ["PORTAL COMPRAS — CRITÉRIOS DE CLASSIFICAÇÃO: COMPRA CENTRALIZADA", ""],
    ["", ""],
    ["Item", "Descrição da Regra de Negócio"],
    ["1. Definição de Centralização", "Uma compra ou Ordem de Compra (OC) é considerada 'CENTRALIZADA' quando é conduzida, negociada ou emitida pela Área de Compras corporativa/operacional."],
    ["2. Cadastro de Compradores (Base Oficial)", "O sistema utiliza a base oficial de Compradores Funcionais (tv_compradores_funcionais), onde os usuários cadastrados com Área = 'Compras' ou 'Compras Operacional' têm suas requisições e ordens classificadas como Centralizadas."],
    ["3. Departamento do Comprador no Oracle", "Adicionalmente, qualquer Ordem de Compra cujo agente/comprador (AGENT_ID) pertença a um departamento cujo nome contenha 'COMPRAS' é classificada como Centralizada."],
    ["4. Acordos de Compra (BPA / Blanket)", "Ordens geradas a partir de Acordos de Compra corporativos (Blanket Purchase Agreements) negociados pela equipe de Compras são automaticamente Centralizadas."],
    ["5. Total de Logins Mapeados", f"Atualmente, esta base contém {len(df_compras)} contas/logins de usuários Oracle associados à área de Compras, correspondendo a {len(df_unicos)} profissionais/compradores únicos."],
    ["", ""],
    ["Data de Extração", pd.Timestamp.now().strftime('%d/%m/%Y %H:%M:%S')],
    ["Fonte dos Dados", "Unity Catalog / Lakebase (tabela compras.compradores_funcionais)"]
]

for row in criterios:
    ws3.append(row)

# Formatação da Aba 3
ws3.merge_cells("A1:B1")
cell_title = ws3.cell(row=1, column=1)
cell_title.font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
cell_title.alignment = Alignment(horizontal="left", vertical="center")

ws3.cell(row=3, column=1).fill = header_fill
ws3.cell(row=3, column=1).font = header_font
ws3.cell(row=3, column=2).fill = header_fill
ws3.cell(row=3, column=2).font = header_font

for r in range(4, 9):
    ws3.cell(row=r, column=1).font = bold_font
    ws3.cell(row=r, column=1).border = thin_border
    ws3.cell(row=r, column=2).font = data_font
    ws3.cell(row=r, column=2).border = thin_border

ws3.column_dimensions['A'].width = 32
ws3.column_dimensions['B'].width = 110

wb.save(excel_filename)
print(f"Sucesso! Gerados:")
print(f"1. Excel: {excel_filename}")
print(f"2. CSV: {csv_filename}")
print(f"Total de registros: {len(df_compras)} logins Oracle ({len(df_unicos)} compradores únicos)")
