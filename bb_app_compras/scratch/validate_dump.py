import csv

with open('scratch/lista_sem_oc_dump.csv', 'r', encoding='utf-8-sig') as f:
    rows = list(csv.reader(f, delimiter=';'))

print(f"Total rows in dump: {len(rows)}")
print("Header:", rows[0])
data = rows[1:]
print(f"Total data rows: {len(data)}")
pks = [r[1].strip() for r in data if len(r) > 1]
print(f"Unique supplier numbers: {len(set(pks))}")
empty = [r for r in data if len(r) < 2 or not r[1].strip()]
print(f"Empty supplier numbers: {len(empty)}")
if empty:
    print("Empty rows:", empty)

# Check for duplicate numbers
from collections import Counter
counts = Counter(pks)
duplicates = {k: v for k, v in counts.items() if v > 1}
print(f"Duplicate supplier numbers: {duplicates}")

print("\nSample 10 rows:")
for i, r in enumerate(data[:10]):
    print(f"  {i+1}: Cod={r[1]} | Nome={r[0]}")
