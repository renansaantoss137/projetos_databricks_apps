import subprocess
import json

candidate_schemas = [
    "grobbbqb_sz", "grobbevnd_sz", "grobbcmrcl_lz", "grobbcmrcl_sz", 
    "grobborder_cz", "bracatlg_cz", "mgtbbrepbr_lz", "mgtbbrepbr_sz"
]

for s in candidate_schemas:
    cmd = ["databricks", "tables", "list", "cat_dnabb_dv", s, "-o", "json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        try:
            tables = json.loads(res.stdout)
            names = [t.get("name") for t in tables if "name" in t]
            print(f"\n=== Schema {s} ({len(names)} tables) ===")
            for n in names:
                print(" ", n)
        except Exception as e:
            print(f"Error parsing {s}:", e)
    else:
        print(f"Error listing {s}:", res.stderr.strip()[:100])
