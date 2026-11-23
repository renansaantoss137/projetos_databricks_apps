with open("scratch/app_from_workspace.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find exact line indices:
sem_oc_end = None
for i, l in enumerate(lines):
    if "EXCEPTIONS-TABLE [sem_oc] ERROR" in l:
        sem_oc_end = i + 2 # return jsonify(rows) is next line
        break

urg_start = None
urg_end = None
for i, l in enumerate(lines):
    if "# For emergencial: override date filter to use oc.DATA_OC" in l:
        urg_start = i
    if urg_start is not None and "exc_comp_and = ''" in l:
        urg_end = i + 1
        break

type_check_start = None
type_check_end = None
for i, l in enumerate(lines):
    if "if exc_type == 'urgente':" in l and i > urg_end:
        type_check_start = i
    if type_check_start is not None and "# type == 'all'" in l:
        type_check_end = i + 1
        break

print("sem_oc_end:", sem_oc_end, repr(lines[sem_oc_end-1]))
print("urg_start:", urg_start, repr(lines[urg_start]))
print("urg_end:", urg_end, repr(lines[urg_end-1]))
print("type_check_start:", type_check_start, repr(lines[type_check_start]))
print("type_check_end:", type_check_end, repr(lines[type_check_end-1]))
