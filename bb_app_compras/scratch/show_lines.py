with open("scratch/app_from_workspace.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for idx, l in enumerate(lines[4705:4740], 4706):
    print(f"{idx}: {l}", end="")
