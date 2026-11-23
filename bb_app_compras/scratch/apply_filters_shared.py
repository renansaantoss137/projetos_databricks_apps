import shutil

JS_PATH = 'src/app/filters-shared.js'
shutil.copy2(JS_PATH, JS_PATH + '.bak_before_sem_oc')

with open(JS_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. setOptions
old_set = '''    if (this.key === 'is_fornecedor_nao_negociavel' || (this.container && this.container.id === 'fFornNegociavel')) {
      this.selected = new Set(['NEGOCIAVEL']);
    } else {'''

new_set = '''    if (this.key === 'is_fornecedor_nao_negociavel' || (this.container && this.container.id === 'fFornNegociavel')) {
      this.selected = new Set(['NEGOCIAVEL']);
    } else if (this.key === 'is_fornecedor_sem_oc' || (this.container && this.container.id === 'fFornSemOC')) {
      this.selected = new Set(['COM ATUAÇÃO']);
    } else {'''

assert old_set in content, "Could not find old_set in filters-shared.js"
content = content.replace(old_set, new_set, 1)

# 2. updateOptions
old_upd = '''    } else if (this.key === 'is_fornecedor_nao_negociavel' || (this.container && this.container.id === 'fFornNegociavel')) {
      this.selected = this.options.includes('NEGOCIAVEL') ? new Set(['NEGOCIAVEL']) : new Set(this.options);
    } else {'''

new_upd = '''    } else if (this.key === 'is_fornecedor_nao_negociavel' || (this.container && this.container.id === 'fFornNegociavel')) {
      this.selected = this.options.includes('NEGOCIAVEL') ? new Set(['NEGOCIAVEL']) : new Set(this.options);
    } else if (this.key === 'is_fornecedor_sem_oc' || (this.container && this.container.id === 'fFornSemOC')) {
      this.selected = this.options.includes('COM ATUAÇÃO') ? new Set(['COM ATUAÇÃO']) : new Set(this.options);
    } else {'''

assert old_upd in content, "Could not find old_upd in filters-shared.js"
content = content.replace(old_upd, new_upd, 1)

# 3. clearAllFilters loop
old_clear = '''    if (ms.key === 'is_fornecedor_nao_negociavel' || (ms.container && ms.container.id === 'fFornNegociavel')) {
      ms.selected = new Set(['NEGOCIAVEL']);
    } else {'''

new_clear = '''    if (ms.key === 'is_fornecedor_nao_negociavel' || (ms.container && ms.container.id === 'fFornNegociavel')) {
      ms.selected = new Set(['NEGOCIAVEL']);
    } else if (ms.key === 'is_fornecedor_sem_oc' || (ms.container && ms.container.id === 'fFornSemOC')) {
      ms.selected = new Set(['COM ATUAÇÃO']);
    } else {'''

assert old_clear in content, "Could not find old_clear in filters-shared.js"
content = content.replace(old_clear, new_clear, 1)

# 4. clearAllFilters specific assignment
old_spec = '''  // Default: fornecedor negociável = NEGOCIAVEL
  if (filters.fFornNegociavel) {
    filters.fFornNegociavel.selected = new Set(['NEGOCIAVEL']);
    filters.fFornNegociavel.renderOptions();
    filters.fFornNegociavel.updateLabel();
  }'''

new_spec = '''  // Default: fornecedor negociável = NEGOCIAVEL
  if (filters.fFornNegociavel) {
    filters.fFornNegociavel.selected = new Set(['NEGOCIAVEL']);
    filters.fFornNegociavel.renderOptions();
    filters.fFornNegociavel.updateLabel();
  }
  // Default: fornecedor sem OC = COM ATUAÇÃO
  if (filters.fFornSemOC) {
    filters.fFornSemOC.selected = new Set(['COM ATUAÇÃO']);
    filters.fFornSemOC.renderOptions();
    filters.fFornSemOC.updateLabel();
  }'''

assert old_spec in content, "Could not find old_spec in filters-shared.js"
content = content.replace(old_spec, new_spec, 1)

with open(JS_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"✓ filters-shared.js updated successfully!")
