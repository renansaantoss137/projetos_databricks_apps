"""
Comprehensive UI/UX polish script for cadastros.html to achieve 40/40 Nielsen score.
Fixes all detector findings and implements rich interactivity, error prevention,
undo/revert, keyboard shortcuts, and integrated documentation.
"""
import re

with open("src/app/cadastros.html", "r", encoding="utf-8") as f:
    html = f.read()

# 1. Fix stat card 3 color (replace violet with sky blue)
old_purple = """    .cd-stat-card:nth-child(3) .cd-stat-icon {
      background: rgba(168, 85, 247, 0.12);
      color: #c084fc;
    }"""
new_sky = """    .cd-stat-card:nth-child(3) .cd-stat-icon {
      background: rgba(2, 132, 199, 0.14);
      color: #38bdf8;
    }"""
if old_purple in html:
    html = html.replace(old_purple, new_sky, 1)

# 2. Fix fonts and glowing shadows in CSS
html = html.replace("font-size: 0.72rem;\n      text-transform: uppercase;", "font-size: 0.75rem;\n      text-transform: uppercase;")
html = html.replace("font-size: 0.7rem;\n      color: var(--fr-txt-soft, #7a9dba);\n      opacity: 0.8;", "font-size: 0.76rem;\n      color: var(--fr-txt-soft, #7a9dba);\n      opacity: 0.9;")
html = html.replace("box-shadow: 0 2px 10px rgba(37, 99, 235, 0.35);", "box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);")
html = html.replace("box-shadow: 0 2px 10px rgba(16, 185, 129, 0.35);", "box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);")
html = html.replace("content: ' ▲';\n      font-size: 0.65rem;", "content: ' ▲';\n      font-size: 0.75rem;")
html = html.replace("content: ' ▼';\n      font-size: 0.65rem;", "content: ' ▼';\n      font-size: 0.75rem;")

# 3. Add CSS for validation errors, badges, and help modal
extra_css = """
    /* Duplicate / Invalid PK Real-Time Highlighting */
    .cd-grid td.cell-error-duplicate {
      background: rgba(239, 68, 68, 0.22) !important;
      color: #fca5a5 !important;
      border: 1px solid #ef4444 !important;
      font-weight: 700;
    }
    .cd-grid td.cell-error-empty {
      background: rgba(245, 158, 11, 0.20) !important;
      color: #fde68a !important;
      border: 1px dashed #f59e0b !important;
    }
    .cd-badge-new {
      display: inline-block;
      padding: 1px 5px;
      font-size: 0.75rem;
      font-weight: 700;
      border-radius: 4px;
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
      margin-left: 4px;
    }
    .cd-badge-mod {
      display: inline-block;
      padding: 1px 5px;
      font-size: 0.75rem;
      font-weight: 700;
      border-radius: 4px;
      background: rgba(59, 130, 246, 0.2);
      color: #93c5fd;
      margin-left: 4px;
    }
    .cd-shortcut-hint {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 0.75rem;
      color: var(--fr-txt-soft, #7a9dba);
      padding: 3px 8px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--cd-border-subtle);
    }
    .cd-btn-revert {
      background: rgba(245, 158, 11, 0.12);
      color: #fbbf24;
      border-color: rgba(245, 158, 11, 0.35);
    }
    .cd-btn-revert:hover:not(:disabled) {
      background: rgba(245, 158, 11, 0.25);
      border-color: #fbbf24;
    }
    .cd-help-card {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--cd-border-subtle);
      border-radius: 10px;
      padding: 1rem 1.25rem;
      margin-bottom: 1rem;
    }
    .cd-help-card h4 {
      margin: 0 0 0.5rem 0;
      font-size: 0.92rem;
      color: #93c5fd;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
"""

if "/* Duplicate / Invalid PK Real-Time Highlighting */" not in html:
    html = html.replace("</style>", extra_css + "\n  </style>", 1)

# 4. Add "Guia das Tabelas" button in hero actions
hero_old = """        <span class="cd-change-tag" id="operatorBadge" style="border-color:rgba(59,130,246,0.35); color:#93c5fd; background:rgba(59,130,246,0.1); display:none;">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          <span id="operatorEmailText">Usuário Autorizado</span>
        </span>
      </div>"""

hero_new = """        <span class="cd-change-tag" id="operatorBadge" style="border-color:rgba(59,130,246,0.35); color:#93c5fd; background:rgba(59,130,246,0.1); display:none;">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          <span id="operatorEmailText">Usuário Autorizado</span>
        </span>
        <button class="cd-btn cd-btn-outline" onclick="openHelpModal()" title="Ver guia completo das tabelas de apoio, finalidade e arquitetura Lakebase" style="height:30px; font-size:0.75rem; padding:0 0.75rem;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:13px; height:13px;"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          Guia das Tabelas
        </button>
      </div>"""

if hero_old in html:
    html = html.replace(hero_old, hero_new, 1)

# 5. Add "Reverter" button & keyboard shortcut hint in Toolbar
tb_old = """          <!-- Add Row -->
          <button class="cd-btn cd-btn-outline" onclick="addNewRow()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Nova Linha
          </button>"""

tb_new = """          <!-- Add Row -->
          <button class="cd-btn cd-btn-outline" onclick="addNewRow()" title="Adicionar nova linha em branco no topo (Ctrl+N)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Nova Linha
          </button>

          <!-- Revert / Discard Changes -->
          <button class="cd-btn cd-btn-revert" id="btnDiscardChanges" onclick="discardWorkingChanges()" disabled title="Descartar todas as edições pendentes e recarregar dados originais (Ctrl+Z)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
            Reverter
          </button>"""

if tb_old in html:
    html = html.replace(tb_old, tb_new, 1)

# Add shortcut hints next to Save button
save_btn_old = """          <!-- Save Changes -->
          <button class="cd-btn cd-btn-save" id="btnSave" onclick="openSaveModal()" disabled>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            Salvar Alterações
          </button>"""

save_btn_new = """          <!-- Save Changes -->
          <button class="cd-btn cd-btn-save" id="btnSave" onclick="openSaveModal()" disabled title="Salvar todas as alterações pendentes no Lakebase (Ctrl+S)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            Salvar Alterações
          </button>
          <div class="cd-shortcut-hint" title="Atalhos rápidos do teclado">
            <span>⌨️ <strong>Ctrl+S</strong> Salvar | <strong>Ctrl+N</strong> Nova | <strong>Ctrl+Z</strong> Reverter</span>
          </div>"""

if save_btn_old in html:
    html = html.replace(save_btn_old, save_btn_new, 1)

# 6. Add Documentation Modal HTML before toast container
help_modal_html = """
  <!-- Modal: Guia e Documentação das Tabelas -->
  <div class="cd-modal-backdrop" id="helpModal">
    <div class="cd-modal" style="max-width: 820px;">
      <div class="cd-modal-header">
        <div class="cd-modal-title">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          Guia das Tabelas de Apoio & Regras de Negócio
        </div>
        <button class="cd-modal-close" onclick="closeHelpModal()">&times;</button>
      </div>
      <div class="cd-modal-body" style="font-size: 0.86rem; line-height: 1.6; color: var(--fr-txt, #E8F4FD);">
        <div class="cd-help-card">
          <h4>📑 Fornecedores sem OC (<code>fornecedores_sem_oc</code>)</h4>
          <p>
            Fornecedores autorizados pela governança Bimbo a emitir notas fiscais sem Ordem de Compra prévia (sem atuação direta da equipe de Compras).
            <strong>Impacto nas Abas:</strong> O filtro global padrão <code>['COM ATUAÇÃO']</code> isola esses parceiros para permitir que a equipe acompanhe o spend negociável real. Caso queira auditar despesas sem OC, selecione <code>['SEM OC']</code> no filtro de fornecedores.
          </p>
        </div>

        <div class="cd-help-card">
          <h4>🚫 Fornecedores Não Negociáveis (<code>fornecedores_nao_negociaveis</code>)</h4>
          <p>
            Parceiros com preços tabelados, concessionárias públicas (água, energia, gás) ou prestadores regulados por órgãos públicos. 
            Não entram na apuração de metas de savings de negociação de suprimentos.
          </p>
        </div>

        <div class="cd-help-card">
          <h4>🏢 Fornecedores Especiais (<code>fornecedores_especiais</code>)</h4>
          <p>
            Fornecedores sob contratos globais estruturados ou regime diferenciado (commodities, utilities, impostos, aluguéis).
            Permite filtrar análises de despesas corporativas no módulo de Gastos.
          </p>
        </div>

        <div class="cd-help-card">
          <h4>👤 Compradores Funcionais (<code>compradores_funcionais</code>)</h4>
          <p>
            Mapeamento de usuários Oracle (<code>usuario_oracle</code>) com a respectiva área e unidade. 
            <strong>Regra Crítica:</strong> Qualquer pedido realizado por compradores de Compras (área = 'Compras') é classificado como <strong>Centralizado</strong> e nunca gera alerta de 'Descentralizada &gt; R$ 30K'.
          </p>
        </div>

        <div class="cd-help-card" style="border-color:rgba(16, 185, 129, 0.3); background:rgba(16, 185, 129, 0.04);">
          <h4 style="color:#34d399;">⚡ Arquitetura Zero-Deploy</h4>
          <p>
            Ao clicar em <strong>Salvar Alterações</strong>:
            1) Um backup com data/hora e seu e-mail é gerado em <code>/Volumes/.../backups/</code>;
            2) O CSV oficial é atualizado no Volume gerenciado;
            3) A tabela correspondente no Lakebase PostgreSQL é sincronizada atomicamente;
            4) Os flags de negócio são recalculados em segundo plano. Os dados entram em vigor <em>imediatamente</em> sem necessidade de deploy.
          </p>
        </div>
      </div>
      <div class="cd-modal-footer">
        <button class="cd-btn cd-btn-primary" onclick="closeHelpModal()">Fechar Guia</button>
      </div>
    </div>
  </div>
"""

if "id=\"helpModal\"" not in html:
    html = html.replace("<!-- Toast Container -->", help_modal_html + "\n  <!-- Toast Container -->", 1)

# 7. JavaScript: Add discardWorkingChanges(), openHelpModal(), closeHelpModal(), and real-time duplicate PK checking
js_funcs = """
    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       AJUDA & DOCUMENTAÇÃO
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function openHelpModal() {
      document.getElementById('helpModal').classList.add('active');
    }
    function closeHelpModal() {
      document.getElementById('helpModal').classList.remove('active');
    }

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       REVERTER & DESFAZER (USER CONTROL & FREEDOM)
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function discardWorkingChanges() {
      if (!STATE.hasUnsavedChanges) return;
      if (!confirm('Deseja descartar todas as alterações não salvas e restaurar o estado original da tabela?')) return;
      
      STATE.workingRows = JSON.parse(JSON.stringify(STATE.originalRows)).map(r => ({
        ...r,
        _uid: 'row_' + Math.random().toString(36).substr(2, 9),
        _isNew: false,
        _modified: false
      }));
      STATE.selectedIndices.clear();
      STATE.hasUnsavedChanges = false;
      renderGrid();
      updatePendingChangesState();
      showToast('Alterações descartadas. Dados restaurados.', 'info');
    }
"""

if "function openHelpModal()" not in html:
    html = html.replace("/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n     ESTADO GLOBAL DA APLICAÇÃO", js_funcs + "\n    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n     ESTADO GLOBAL DA APLICAÇÃO", 1)

# 8. Update updatePendingChangesState to also manage #btnDiscardChanges
upd_old = """      if (btnSave) {
        btnSave.disabled = !STATE.hasUnsavedChanges;"""

upd_new = """      const btnDiscard = document.getElementById('btnDiscardChanges');
      if (btnDiscard) {
        btnDiscard.disabled = !STATE.hasUnsavedChanges;
      }

      if (btnSave) {
        btnSave.disabled = !STATE.hasUnsavedChanges;"""

if upd_old in html:
    html = html.replace(upd_old, upd_new, 1)

# 9. Update renderTbody to perform duplicate PK checking and show [NOVO] / [MODIFICADO] chips
old_render_tbody_loop = """        // Células editáveis
        STATE.columns.forEach(col => {
          const val = row[col.key] !== undefined && row[col.key] !== null ? String(row[col.key]) : '';
          const isMod = isCellModified(row, col.key);
          const cellClass = `editable ${isMod ? 'cell-modified' : ''}`;
          html += `<td class="${cellClass}" 
                      ondblclick="startEditCell(this, '${row._uid}', '${col.key}')" 
                      title="Duplo clique para editar"
                      data-key="${col.key}">${escapeHtml(val)}</td>`;
        });"""

new_render_tbody_loop = """        // Células editáveis com validação em tempo real de PK
        STATE.columns.forEach(col => {
          const val = row[col.key] !== undefined && row[col.key] !== null ? String(row[col.key]) : '';
          const isMod = isCellModified(row, col.key);
          const isPk = col.key === STATE.primaryKey;
          
          let cellExtraClass = '';
          let cellTitle = 'Duplo clique para editar';
          
          if (isPk) {
            const trimmed = val.trim();
            if (!trimmed) {
              cellExtraClass = 'cell-error-empty';
              cellTitle = 'Campo obrigatório! A chave primária não pode estar vazia.';
            } else {
              const occurrences = STATE.workingRows.filter(r => String(r[STATE.primaryKey] || '').trim() === trimmed).length;
              if (occurrences > 1) {
                cellExtraClass = 'cell-error-duplicate';
                cellTitle = 'Atenção: Chave primária duplicada no grid! Corrija antes de salvar.';
              }
            }
          }
          
          const cellClass = `editable ${isMod ? 'cell-modified' : ''} ${cellExtraClass}`;
          let displayVal = escapeHtml(val);
          if (isPk && row._isNew) {
            displayVal += `<span class="cd-badge-new">NOVO</span>`;
          } else if (isPk && isMod) {
            displayVal += `<span class="cd-badge-mod">EDIT</span>`;
          }

          html += `<td class="${cellClass}" 
                      ondblclick="startEditCell(this, '${row._uid}', '${col.key}')" 
                      title="${cellTitle}"
                      data-key="${col.key}">${displayVal}</td>`;
        });"""

if old_render_tbody_loop in html:
    html = html.replace(old_render_tbody_loop, new_render_tbody_loop, 1)

# 10. Update setupKeyboardShortcuts to add Ctrl+N, Ctrl+Z, Escape
keys_old = """      // Atalho Ctrl+S para salvar
      window.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
          e.preventDefault();
          if (STATE.hasUnsavedChanges) openSaveModal();
        }
      });"""

keys_new = """      // Atalhos de teclado abrangentes (Ctrl+S, Ctrl+N, Ctrl+Z, Esc)
      window.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
          e.preventDefault();
          if (STATE.hasUnsavedChanges) openSaveModal();
        } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
          e.preventDefault();
          addNewRow();
        } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
          if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault();
            if (STATE.hasUnsavedChanges) discardWorkingChanges();
          }
        } else if (e.key === 'Escape') {
          closeSaveModal();
          closeImportModal();
          closeHelpModal();
        }
      });"""

if keys_old in html:
    html = html.replace(keys_old, keys_new, 1)

with open("src/app/cadastros.html", "w", encoding="utf-8") as f:
    f.write(html)

print("Successfully applied UI/UX improvements to cadastros.html")
