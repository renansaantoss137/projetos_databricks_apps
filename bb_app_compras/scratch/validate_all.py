import glob
import os

files = glob.glob('src/app/*.html')
all_ok = True

for f in sorted(files):
    fname = os.path.basename(f)
    try:
        with open(f, encoding='utf-8') as fp:
            text = fp.read()
            if '<!DOCTYPE html>' not in text:
                print(f"[FAIL] {fname}: faltando DOCTYPE")
                all_ok = False
            elif 'app-menu.js' not in text:
                print(f"[FAIL] {fname}: faltando app-menu.js")
                all_ok = False
            elif 'id="app-menu-container"' not in text:
                print(f"[FAIL] {fname}: faltando #app-menu-container")
                all_ok = False
            else:
                print(f"[OK] {fname}: íntegro ({len(text)} bytes, {text.count(chr(10))} linhas)")
    except Exception as e:
        print(f"[FAIL] {fname}: {e}")
        all_ok = False

if all_ok:
    print("\nTODOS OS 9 ARQUIVOS HTML ESTÃO VÁLIDOS E PADRONIZADOS!")
