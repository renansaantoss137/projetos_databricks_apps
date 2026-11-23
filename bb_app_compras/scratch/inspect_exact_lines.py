with open("src/app/app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("Line 4610-4625:")
for i in range(4608, 4625):
    print(f"{i+1}: {repr(lines[i])}")

print("\nLine 4745-4770:")
for i in range(4745, min(len(lines), 4775)):
    if 'type_filter' in lines[i] or 'urg_parts' in lines[i] or 'oc_pos_cte' in lines[i]:
        print(f"{i+1}: {repr(lines[i])}")
