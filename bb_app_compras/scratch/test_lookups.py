import sys, os
sys.path.insert(0, os.path.abspath('src/app'))

from app import _read_lookup_rows, LOOKUP_CONFIG

print("LOOKUP_CONFIG keys:", list(LOOKUP_CONFIG.keys()))
for key in LOOKUP_CONFIG.keys():
    rows, err = _read_lookup_rows(key)
    print(f"Lookup '{key}': total rows = {len(rows)}, err = {err}")
    if rows:
        print(f"  First row sample of '{key}':", rows[0])
