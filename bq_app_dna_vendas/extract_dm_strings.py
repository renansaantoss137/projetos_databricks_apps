import zipfile
import re

pbix = r'C:\Users\renan.ferreira\OneDrive - Corporativo Bimbo, S.A. de C. V\Área de Trabalho\Projetos Databricks Apps\bq_app_dna_vendas\DNA DE VENDAS_BQ-copia.pbix'

with zipfile.ZipFile(pbix, 'r') as z:
    dm = z.read('DataModel')

# Search for text strings in dm (both utf-8 and utf-16le)
def extract_strings(data, min_len=4):
    # UTF-16LE
    pattern_u16 = re.compile(b'(?:[\x20-\x7e]\x00){' + str(min_len).encode() + b',}')
    matches_u16 = [m.group(0).decode('utf-16le') for m in pattern_u16.finditer(data)]
    
    # ASCII
    pattern_ascii = re.compile(b'[\x20-\x7e]{' + str(min_len).encode() + b',}')
    matches_ascii = [m.group(0).decode('ascii') for m in pattern_ascii.finditer(data)]
    return matches_ascii, matches_u16

ascii_s, u16_s = extract_strings(dm, min_len=5)
print(f"Total ASCII strings found: {len(ascii_s)}")
print(f"Total UTF-16 strings found: {len(u16_s)}")

# Look for DAX keywords or table definitions
keywords = ['CALCULATE', 'SUM(', 'DIVIDE', 'FROM ', 'SELECT ', 'databricks', 'cat_dnabb', 'bracatlg', 'vw_', 'tb_', 'd_tempo', 'f_']
for kw in keywords:
    found_a = [s for s in ascii_s if kw.lower() in s.lower()]
    found_u = [s for s in u16_s if kw.lower() in s.lower()]
    print(f"Keyword '{kw}': {len(found_a)} ascii, {len(found_u)} utf16")
    if found_u:
        for s in found_u[:3]:
            print("   sample u16:", s[:150])
    if found_a:
        for s in found_a[:3]:
            print("   sample ascii:", s[:150])
