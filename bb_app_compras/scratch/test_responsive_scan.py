import os
import re
import glob

workspace = r"c:\Users\renan.ferreira\OneDrive - Corporativo Bimbo, S.A. de C. V\Área de Trabalho\Projetos Databricks Apps\bb_app_compras"
app_dir = os.path.join(workspace, "src", "app")

html_files = glob.glob(os.path.join(app_dir, "*.html"))
css_files = glob.glob(os.path.join(app_dir, "*.css"))
js_files = glob.glob(os.path.join(app_dir, "*.js"))

print("=== CHECKLIST RESPONSIVO: VARREDURA ESTÁTICA ===")
print(f"Arquivos HTML encontrados: {len(html_files)}")
for f in html_files:
    print(" -", os.path.basename(f))

issues = []

# 1. Viewport Meta tag
for hf in html_files:
    fname = os.path.basename(hf)
    with open(hf, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    if '<meta name="viewport"' not in content:
        issues.append((fname, "CRITICAL: Meta viewport tag não encontrada"))
    else:
        if "width=device-width" not in content:
            issues.append((fname, "WARNING: Meta viewport sem width=device-width"))

    # Check app-menu.js inclusion
    if "app-menu.js" not in content:
        issues.append((fname, "CRITICAL: app-menu.js não incluído"))

    # Check app-menu-container presence
    if 'id="app-menu-container"' not in content:
        issues.append((fname, "CRITICAL: #app-menu-container não encontrado"))

    # Check for hardcoded KPI rainbow borders
    rainbow_matches = re.findall(r'(border-(?:left|top|right|bottom)\s*:\s*[3456]px\s+solid\s+[^;\}]+)', content, re.IGNORECASE)
    for rm in rainbow_matches:
        if any(color in rm.lower() for color in ['#22c55e', '#ef4444', '#f59e0b', '#3b82f6', '#8b5cf6', '#06b6d4', '#e11d48']):
            issues.append((fname, f"WARNING: Possível borda colorida decorativa em elemento: {rm}"))

# 2. Check CSS files
for cf in css_files:
    fname = os.path.basename(cf)
    with open(cf, "r", encoding="utf-8", errors="ignore") as f:
        css = f.read()

    # Verify standard tokens exist
    required_tokens = ['--primary', '--surface', '--border-subtle', '--text-primary', '--text-muted', '--font-family-base']
    for token in required_tokens:
        if token not in css:
            issues.append((fname, f"WARNING: Token D&A '{token}' ausente em styles.css"))

    # Check if kpi-card neutral border rule exists
    if '.kpi-card' in css:
        print(" [OK] styles.css contém regras para .kpi-card")

# 3. Check i18n keys
with open(os.path.join(app_dir, "i18n.js"), "r", encoding="utf-8", errors="ignore") as f:
    i18n_code = f.read()

for key in ['fmtPct', 'fmtPp', 'nav_ordens', 'lbl_atencao']:
    if key in i18n_code:
        print(f" [OK] i18n.js contém '{key}'")
    else:
        issues.append(("i18n.js", f"WARNING: i18n.js não contém '{key}'"))

print("\n=== RESULTADO DA VARREDURA ===")
if not issues:
    print("Sucesso! Nenhum problema crítico ou violação de padrão detectada.")
else:
    for src, issue in issues:
        print(f"[{src}] {issue}")
