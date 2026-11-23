with open("src/app/cadastros.html", "r", encoding="utf-8") as f:
    h = f.read()

# Fix heading hierarchy in helpModal
old_body = '<div class="cd-modal-body" style="font-size: 0.86rem; line-height: 1.6; color: var(--fr-txt, #E8F4FD);">'
new_body = '''<div class="cd-modal-body" style="font-size: 0.86rem; line-height: 1.6; color: var(--fr-txt, #E8F4FD);">
        <h2 style="font-size:1rem; font-weight:700; margin:0 0 1rem 0; color:#93c5fd; border-bottom:1px solid var(--cd-border-subtle); padding-bottom:0.4rem;">
          Estrutura das Tabelas e Diretrizes de Governança
        </h2>'''

if old_body in h:
    h = h.replace(old_body, new_body, 1)

h = h.replace('<h4>📑 Fornecedores sem OC', '<h3>📑 Fornecedores sem OC')
h = h.replace('</h4>\n          <p>\n            Fornecedores autorizados', '</h3>\n          <p>\n            Fornecedores autorizados')
h = h.replace('<h4>🚫 Fornecedores Não Negociáveis', '<h3>🚫 Fornecedores Não Negociáveis')
h = h.replace('</h4>\n          <p>\n            Parceiros com preços', '</h3>\n          <p>\n            Parceiros com preços')
h = h.replace('<h4>🏢 Fornecedores Especiais', '<h3>🏢 Fornecedores Especiais')
h = h.replace('</h4>\n          <p>\n            Fornecedores sob contratos', '</h3>\n          <p>\n            Fornecedores sob contratos')
h = h.replace('<h4>👤 Compradores Funcionais', '<h3>👤 Compradores Funcionais')
h = h.replace('</h4>\n          <p>\n            Mapeamento de usuários', '</h3>\n          <p>\n            Mapeamento de usuários')
h = h.replace('<h4 style="color:#34d399;">⚡ Arquitetura Zero-Deploy</h4>', '<h3 style="color:#34d399;">⚡ Arquitetura Zero-Deploy</h3>')

# Fix zero-offset chromatic box-shadow glows
h = h.replace('box-shadow: 0 0 0 1px var(--cd-primary);', 'outline: 1px solid var(--cd-primary);')
h = h.replace('box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);', 'outline: 2px solid rgba(59, 130, 246, 0.3);')
h = h.replace('box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);', 'outline: 2px solid rgba(59, 130, 246, 0.4);')

with open("src/app/cadastros.html", "w", encoding="utf-8") as f:
    f.write(h)

print("Updated cadastros.html headings and box-shadows successfully")
