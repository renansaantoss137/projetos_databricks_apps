import csv
from datetime import datetime

with open('scratch/lista_sem_oc_dump.csv', 'r', encoding='utf-8-sig') as f:
    rows = list(csv.reader(f, delimiter=';'))

data = rows[1:]
header = ["Cód. Fornecedor (Oracle)", "Nome Fornecedor (Oracle)", "Produto / Serviço", "Área", "Justificativa", "Data Registro"]
today_str = datetime.now().strftime("%d/%m/%Y")

out_rows = []
for r in data:
    nome = r[0].strip()
    cod = r[1].strip()
    if cod:
        out_rows.append([
            cod,
            nome,
            "Faturamento sem PO autorizado",
            "Geral",
            "Fornecedor sem atuação de compras - faturamento direto sem OC autorizado",
            today_str
        ])

target_path = 'src/dados/fornecedores_sem_oc.csv'
with open(target_path, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f, delimiter=';')
    writer.writerow(header)
    writer.writerows(out_rows)

print(f"Generated {target_path} with {len(out_rows)} suppliers successfully!")
