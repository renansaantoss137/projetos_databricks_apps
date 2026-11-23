import shutil

# 1. spend.html
path = 'src/app/spend.html'
shutil.copy2(path, path + '.bak_before_sem_oc')
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

old_defs = "{ id: 'fFornNegociavel', key: 'is_fornecedor_nao_negociavel', rotulo: 'Forn. Negociável', tipo: 'multi', opcoes: ['NEGOCIAVEL', 'NÃO NEGOCIAVEL'] }"
new_defs = old_defs + ",\n    { id: 'fFornSemOC', key: 'is_fornecedor_sem_oc', rotulo: 'Forn. sem OC', tipo: 'multi', opcoes: ['COM ATUAÇÃO', 'SEM OC'], padrao: ['COM ATUAÇÃO'] }"
assert old_defs in c, "spend.html old_defs not found"
c = c.replace(old_defs, new_defs, 1)

old_reset = "if(filters.fFornNegociavel){filters.fFornNegociavel.selected=new Set(['NEGOCIAVEL']);filters.fFornNegociavel.renderOptions();filters.fFornNegociavel.updateLabel();}"
new_reset = old_reset + "if(filters.fFornSemOC){filters.fFornSemOC.selected=new Set(['COM ATUAÇÃO']);filters.fFornSemOC.renderOptions();filters.fFornSemOC.updateLabel();}"
assert old_reset in c, "spend.html old_reset not found"
c = c.replace(old_reset, new_reset, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print("spend.html updated")

# 2. performance.html
path = 'src/app/performance.html'
shutil.copy2(path, path + '.bak_before_sem_oc')
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

assert old_defs in c, "performance.html old_defs not found"
c = c.replace(old_defs, new_defs, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print("performance.html updated")

# 3. comercial.html
path = 'src/app/comercial.html'
shutil.copy2(path, path + '.bak_before_sem_oc')
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

assert old_defs in c, "comercial.html old_defs not found"
c = c.replace(old_defs, new_defs, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print("comercial.html updated")

# 4. governanca.html
path = 'src/app/governanca.html'
shutil.copy2(path, path + '.bak_before_sem_oc')
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

old_gov = "{ id: 'fFornNegociavel', key: 'is_fornecedor_nao_negociavel', rotulo: 'Forn. Negociável', tipo: 'multi', opcoes: ['NEGOCIAVEL', 'NÃO NEGOCIAVEL'] }"
new_gov = old_gov + ",\n        { id: 'fFornSemOC', key: 'is_fornecedor_sem_oc', rotulo: 'Forn. sem OC', tipo: 'multi', opcoes: ['COM ATUAÇÃO', 'SEM OC'], padrao: ['COM ATUAÇÃO'] }"
assert old_gov in c, "governanca.html old_gov not found"
c = c.replace(old_gov, new_gov, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print("governanca.html updated")

# 5. ordens.html
path = 'src/app/ordens.html'
shutil.copy2(path, path + '.bak_before_sem_oc')
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

old_ord_defs = "{ id: 'fFornNegociavel', key: 'is_fornecedor_nao_negociavel', rotulo: 'Forn. Negociável', tipo: 'multi', opcoes: ['NEGOCIAVEL','NÃO NEGOCIAVEL'] }"
new_ord_defs = old_ord_defs + ",\n    { id: 'fFornSemOC', key: 'is_fornecedor_sem_oc', rotulo: 'Forn. sem OC', tipo: 'multi', opcoes: ['COM ATUAÇÃO', 'SEM OC'], padrao: ['COM ATUAÇÃO'] }"
assert old_ord_defs in c, "ordens.html old_ord_defs not found"
c = c.replace(old_ord_defs, new_ord_defs, 1)

old_ord_reset = "if(filters.fFornNegociavel){filters.fFornNegociavel.selected=new Set(['NEGOCIAVEL']);filters.fFornNegociavel.renderOptions();filters.fFornNegociavel.updateLabel();}"
new_ord_reset = old_ord_reset + "if(filters.fFornSemOC){filters.fFornSemOC.selected=new Set(['COM ATUAÇÃO']);filters.fFornSemOC.renderOptions();filters.fFornSemOC.updateLabel();}"
assert old_ord_reset in c, "ordens.html old_ord_reset not found"
c = c.replace(old_ord_reset, new_ord_reset, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print("ordens.html updated")

# 6. relatorios.html
path = 'src/app/relatorios.html'
shutil.copy2(path, path + '.bak_before_sem_oc')
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# Add to defs
assert old_defs in c, "relatorios.html old_defs not found"
c = c.replace(old_defs, new_defs, 1)

# Add to getFilterParams
old_rel_fn = """    // Fornecedor Negociável
    const fn = vals.is_fornecedor_nao_negociavel || ['NEGOCIAVEL'];
    (Array.isArray(fn) ? fn : [fn]).forEach(v => p.append('is_fornecedor_nao_negociavel', v));"""

new_rel_fn = """    // Fornecedor Negociável
    const fn = vals.is_fornecedor_nao_negociavel || ['NEGOCIAVEL'];
    (Array.isArray(fn) ? fn : [fn]).forEach(v => p.append('is_fornecedor_nao_negociavel', v));

    // Fornecedor sem OC
    const fso = vals.is_fornecedor_sem_oc || ['COM ATUAÇÃO'];
    (Array.isArray(fso) ? fso : [fso]).forEach(v => p.append('is_fornecedor_sem_oc', v));"""

assert old_rel_fn in c, "relatorios.html old_rel_fn not found"
c = c.replace(old_rel_fn, new_rel_fn, 1)

old_excl = "if (['empresa', 'ano', 'mes', 'is_fornecedor_nao_negociavel'].includes(k)) return;"
new_excl = "if (['empresa', 'ano', 'mes', 'is_fornecedor_nao_negociavel', 'is_fornecedor_sem_oc'].includes(k)) return;"
assert old_excl in c, "relatorios.html old_excl not found"
c = c.replace(old_excl, new_excl, 1)

old_fb = "p.append('is_fornecedor_nao_negociavel', 'NEGOCIAVEL');"
new_fb = "p.append('is_fornecedor_nao_negociavel', 'NEGOCIAVEL');\n    p.append('is_fornecedor_sem_oc', 'COM ATUAÇÃO');"
assert old_fb in c, "relatorios.html old_fb not found"
c = c.replace(old_fb, new_fb, 1)

# Add to ALL_COLS
old_col = "{key:'IS_FORNECEDOR_NAO_NEGOCIAVEL', label:'Negociabilidade', on:false},"
new_col = "{key:'IS_FORNECEDOR_NAO_NEGOCIAVEL', label:'Negociabilidade', on:false},\n    {key:'IS_FORNECEDOR_SEM_OC', label:'Forn. sem OC / Atuação', on:false},"
assert old_col in c, "relatorios.html old_col not found"
c = c.replace(old_col, new_col, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print("relatorios.html updated")

print("All 6 dashboard HTML pages successfully updated!")
