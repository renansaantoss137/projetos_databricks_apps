import subprocess
import json

cmd = ["databricks", "schemas", "list", "cat_dnabb_dv", "-o", "json"]
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0:
    schemas = json.loads(res.stdout)
    schema_names = [s.get("name") for s in schemas]
    print(f"Total schemas in cat_dnabb_dv: {len(schema_names)}")
    for s in sorted(schema_names):
        print("  -", s)
else:
    print("Error:", res.stderr)
