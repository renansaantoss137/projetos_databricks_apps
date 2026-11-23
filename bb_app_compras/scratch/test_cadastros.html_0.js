
    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ESTADO GLOBAL DA APLICAÇÃO
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    const STATE = {
      currentTableKey: 'fornecedores_especiais',
      tablesSummary: {},
      columns: [],
      primaryKey: 'cod_fornecedor_oracle',
      originalRows: [],      // Estado vindo do servidor
      workingRows: [],       // Estado atual editado pelo usuário
      selectedIndices: new Set(),
      searchQuery: '',
      sortCol: '',
      sortDir: 'ASC',
      currentPage: 1,
      perPage: 50,
      hasUnsavedChanges: false,
      importedDataCache: null
    };

    // Inicialização ao carregar a página
    document.addEventListener('DOMContentLoaded', async () => {
      setupDropzone();
      setupKeyboardShortcuts();
      fetch('/api/auth/me')
        .then(r => r.json())
        .then(u => {
          if (u && u.email) {
            const badge = document.getElementById('operatorBadge');
            const txt = document.getElementById('operatorEmailText');
            if (badge && txt) {
              const role = u.is_admin ? 'Admin' : 'Autorizado';
              txt.textContent = `${u.email} (${role})`;
              badge.style.display = 'inline-flex';
            }
          }
        }).catch(() => {});
      await loadSummary();
      await switchTable('fornecedores_especiais');
    });

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       CARREGAR DADOS & ALTERNAR TABELAS
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    async function loadSummary() {
      try {
        const res = await fetch('/api/lookups/summary');
        const data = await res.json();
        if (data.success && data.tables) {
          data.tables.forEach(t => {
            STATE.tablesSummary[t.key] = t;
            const el = document.getElementById(`cnt_${t.key}`);
            if (el) el.innerText = Number(t.total || 0).toLocaleString('pt-BR');
          });
        }
      } catch (e) {
        console.warn('Erro ao carregar resumo de tabelas:', e);
      }
    }

    async function switchTable(tableKey) {
      if (STATE.hasUnsavedChanges) {
        const leave = confirm('Você possui alterações não salvas nesta tabela. Deseja descartar e trocar de tabela?');
        if (!leave) return;
      }

      STATE.currentTableKey = tableKey;
      STATE.selectedIndices.clear();
      STATE.searchQuery = '';
      STATE.currentPage = 1;
      STATE.hasUnsavedChanges = false;
      document.getElementById('gridSearchInput').value = '';

      // Atualizar abas visuais
      document.querySelectorAll('.cd-stat-card').forEach(c => c.classList.remove('active'));
      const activeTab = document.getElementById(`tab_${tableKey}`);
      if (activeTab) activeTab.classList.add('active');

      showToast(`Carregando ${tableKey}...`, 'info');
      document.getElementById('gridTbody').innerHTML = `<tr><td colspan="10" style="text-align:center; padding:3rem; color:var(--fr-txt-soft);">Carregando dados do Lakebase...</td></tr>`;

      try {
        const res = await fetch(`/api/lookups/${tableKey}`);
        const data = await res.json();
        if (data.success) {
          STATE.columns = data.columns || [];
          STATE.primaryKey = data.primary_key || 'id';
          STATE.originalRows = JSON.parse(JSON.stringify(data.rows || []));
          STATE.workingRows = JSON.parse(JSON.stringify(data.rows || []));
          
          // Marca rows com _uid para rastreamento
          STATE.workingRows.forEach((r, i) => {
            r._uid = 'row_' + i + '_' + Date.now();
            r._isNew = false;
            r._modified = false;
          });

          renderGrid();
          updatePendingChangesState();
        } else {
          showToast(data.error || 'Erro ao carregar tabela', 'error');
        }
      } catch (e) {
        showToast('Erro de comunicação com o servidor: ' + e.message, 'error');
      }
    }

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       RENDERIZAÇÃO DA GRADE (SPREADSHEET GRID)
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function renderGrid() {
      renderThead();
      renderTbody();
      renderFooter();
    }

    function renderThead() {
      const thead = document.getElementById('gridThead');
      let html = `<tr>`;
      
      // Checkbox Select All
      html += `<th style="width:40px; text-align:center;">
        <input type="checkbox" id="masterCheckbox" onchange="toggleSelectAll(this.checked)" title="Selecionar todas">
      </th>`;

      // Linha #
      html += `<th style="width:50px; text-align:center;">#</th>`;

      // Colunas da tabela
      STATE.columns.forEach(col => {
        const isSort = STATE.sortCol === col.key;
        const sortClass = isSort ? (STATE.sortDir === 'ASC' ? 'sort-asc' : 'sort-desc') : '';
        const reqClass = col.required ? 'required-col' : '';
        html += `<th class="${sortClass} ${reqClass}" onclick="sortBy('${col.key}')" title="Clique para ordenar por ${col.label}">
          ${col.label}
        </th>`;
      });

      // Ações
      html += `<th style="width:60px; text-align:center;">Ações</th>`;
      html += `</tr>`;
      thead.innerHTML = html;
    }

    function renderTbody() {
      const tbody = document.getElementById('gridTbody');
      const filtered = getFilteredRows();

      if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${STATE.columns.length + 3}" style="text-align:center; padding:3rem; color:var(--fr-txt-soft);">Nenhum registro encontrado com os filtros aplicados.</td></tr>`;
        return;
      }

      // Paginação
      const startIdx = STATE.perPage === 'all' ? 0 : (STATE.currentPage - 1) * STATE.perPage;
      const endIdx = STATE.perPage === 'all' ? filtered.length : Math.min(startIdx + STATE.perPage, filtered.length);
      const pageRows = filtered.slice(startIdx, endIdx);

      let html = '';
      pageRows.forEach((row, idx) => {
        const globalIdx = startIdx + idx;
        const isSelected = STATE.selectedIndices.has(row._uid);
        const rowClass = (isSelected ? 'selected ' : '') + (row._isNew ? 'new-row ' : '');

        html += `<tr class="${rowClass}" data-uid="${row._uid}">`;
        
        // Checkbox
        html += `<td style="text-align:center;">
          <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="toggleSelectRow('${row._uid}', this.checked)">
        </td>`;

        // Linha #
        html += `<td style="text-align:center; color:var(--fr-txt-soft); font-size:0.72rem;">${globalIdx + 1}</td>`;

        // Células editáveis
        STATE.columns.forEach(col => {
          const val = row[col.key] !== undefined && row[col.key] !== null ? String(row[col.key]) : '';
          const isMod = isCellModified(row, col.key);
          const cellClass = `editable ${isMod ? 'cell-modified' : ''}`;
          html += `<td class="${cellClass}" 
                      ondblclick="startEditCell(this, '${row._uid}', '${col.key}')" 
                      title="Duplo clique para editar"
                      data-key="${col.key}">${escapeHtml(val)}</td>`;
        });

        // Ações da linha
        html += `<td style="text-align:center;">
          <button class="cd-row-action" onclick="deleteRow('${row._uid}')" title="Excluir linha">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </td>`;

        html += `</tr>`;
      });

      tbody.innerHTML = html;
      updateDeleteSelectedButton();
    }

    function renderFooter() {
      const filtered = getFilteredRows();
      const total = filtered.length;
      const start = total === 0 ? 0 : (STATE.perPage === 'all' ? 1 : (STATE.currentPage - 1) * STATE.perPage + 1);
      const end = STATE.perPage === 'all' ? total : Math.min(start + STATE.perPage - 1, total);

      document.getElementById('footerInfoText').innerHTML = 
        `Mostrando <strong>${start}</strong> a <strong>${end}</strong> de <strong>${total}</strong> registros (Total na base: ${STATE.workingRows.length})`;

      // Paginação
      const totalPages = STATE.perPage === 'all' ? 1 : Math.ceil(total / STATE.perPage);
      const paginationEl = document.getElementById('paginationControls');
      if (totalPages <= 1) {
        paginationEl.innerHTML = '';
        return;
      }

      let phtml = '';
      phtml += `<button class="cd-page-btn" onclick="goToPage(${STATE.currentPage - 1})" ${STATE.currentPage === 1 ? 'disabled' : ''}>&laquo;</button>`;
      
      let startP = Math.max(1, STATE.currentPage - 2);
      let endP = Math.min(totalPages, startP + 4);
      if (endP - startP < 4) startP = Math.max(1, endP - 4);

      for (let p = startP; p <= endP; p++) {
        phtml += `<button class="cd-page-btn ${p === STATE.currentPage ? 'active' : ''}" onclick="goToPage(${p})">${p}</button>`;
      }
      phtml += `<button class="cd-page-btn" onclick="goToPage(${STATE.currentPage + 1})" ${STATE.currentPage === totalPages ? 'disabled' : ''}>&raquo;</button>`;
      paginationEl.innerHTML = phtml;
    }

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       FILTRAGEM, PESQUISA E ORDENAÇÃO
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function getFilteredRows() {
      let rows = [...STATE.workingRows];
      const q = STATE.searchQuery.trim().toLowerCase();
      if (q) {
        rows = rows.filter(r => {
          return STATE.columns.some(col => {
            const v = String(r[col.key] || '').toLowerCase();
            return v.includes(q);
          });
        });
      }

      if (STATE.sortCol) {
        const key = STATE.sortCol;
        const dir = STATE.sortDir === 'ASC' ? 1 : -1;
        rows.sort((a, b) => {
          const valA = String(a[key] || '').toLowerCase();
          const valB = String(b[key] || '').toLowerCase();
          return valA.localeCompare(valB, undefined, { numeric: true }) * dir;
        });
      }
      return rows;
    }

    function onSearchChange(val) {
      STATE.searchQuery = val;
      STATE.currentPage = 1;
      renderGrid();
    }

    function sortBy(colKey) {
      if (STATE.sortCol === colKey) {
        STATE.sortDir = STATE.sortDir === 'ASC' ? 'DESC' : 'ASC';
      } else {
        STATE.sortCol = colKey;
        STATE.sortDir = 'ASC';
      }
      renderGrid();
    }

    function goToPage(p) {
      const filtered = getFilteredRows();
      const totalPages = STATE.perPage === 'all' ? 1 : Math.ceil(filtered.length / STATE.perPage);
      if (p >= 1 && p <= totalPages) {
        STATE.currentPage = p;
        renderTbody();
        renderFooter();
      }
    }

    function changePerPage(val) {
      STATE.perPage = val === 'all' ? 'all' : parseInt(val, 10);
      STATE.currentPage = 1;
      renderGrid();
    }

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       EDIÇÃO DE CÉLULAS (INLINE EDITING)
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function startEditCell(tdElement, rowUid, colKey) {
      if (tdElement.querySelector('.cd-cell-input')) return; // Já está editando

      const currentVal = tdElement.innerText.trim();
      const input = document.createElement('input');
      input.type = 'text';
      input.className = 'cd-cell-input';
      input.value = currentVal;

      tdElement.innerHTML = '';
      tdElement.appendChild(input);
      input.focus();
      input.select();

      function finishEdit() {
        const newVal = input.value.trim();
        const row = STATE.workingRows.find(r => r._uid === rowUid);
        if (row) {
          row[colKey] = newVal;
          row._modified = true;
          STATE.hasUnsavedChanges = true;
        }
        tdElement.innerText = newVal;
        if (isCellModified(row, colKey)) {
          tdElement.classList.add('cell-modified');
        } else {
          tdElement.classList.remove('cell-modified');
        }
        updatePendingChangesState();
      }

      input.addEventListener('blur', finishEdit);
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          input.blur();
        } else if (e.key === 'Escape') {
          input.value = currentVal;
          input.blur();
        }
      });
    }

    function isCellModified(row, colKey) {
      if (!row) return false;
      if (row._isNew) return true;
      const orig = STATE.originalRows.find(r => String(r[STATE.primaryKey]) === String(row[STATE.primaryKey]));
      if (!orig) return true;
      return String(orig[colKey] || '').trim() !== String(row[colKey] || '').trim();
    }

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ADICIONAR & EXCLUIR LINHAS
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function addNewRow() {
      const newRow = {
        _uid: 'new_' + Date.now(),
        _isNew: true,
        _modified: true
      };
      STATE.columns.forEach(c => {
        newRow[c.key] = '';
      });

      // Adiciona no início da lista
      STATE.workingRows.unshift(newRow);
      STATE.hasUnsavedChanges = true;
      STATE.currentPage = 1;
      renderGrid();
      updatePendingChangesState();

      // Foca automaticamente na primeira célula da nova linha
      setTimeout(() => {
        const firstRow = document.querySelector('#gridTbody tr');
        if (firstRow) {
          const firstEditable = firstRow.querySelector('.editable');
          if (firstEditable) startEditCell(firstEditable, newRow._uid, STATE.columns[0].key);
        }
      }, 50);

      showToast('Nova linha inserida. Preencha os dados e salve.', 'info');
    }

    function deleteRow(uid) {
      const row = STATE.workingRows.find(r => r._uid === uid);
      const name = row ? (row[STATE.primaryKey] || 'esta linha') : 'a linha';
      if (!confirm(`Deseja remover o registro [${name}]?`)) return;

      STATE.workingRows = STATE.workingRows.filter(r => r._uid !== uid);
      STATE.selectedIndices.delete(uid);
      STATE.hasUnsavedChanges = true;
      renderGrid();
      updatePendingChangesState();
      showToast('Linha removida.', 'info');
    }

    function deleteSelectedRows() {
      const count = STATE.selectedIndices.size;
      if (count === 0) return;
      if (!confirm(`Confirma a exclusão de ${count} registros selecionados?`)) return;

      STATE.workingRows = STATE.workingRows.filter(r => !STATE.selectedIndices.has(r._uid));
      STATE.selectedIndices.clear();
      STATE.hasUnsavedChanges = true;
      renderGrid();
      updatePendingChangesState();
      showToast(`${count} registros removidos.`, 'info');
    }

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       SELEÇÃO DE LINHAS (CHECKBOXES)
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function toggleSelectRow(uid, isChecked) {
      if (isChecked) {
        STATE.selectedIndices.add(uid);
      } else {
        STATE.selectedIndices.delete(uid);
      }
      updateRowSelectionUI();
    }

    function toggleSelectAll(isChecked) {
      const filtered = getFilteredRows();
      if (isChecked) {
        filtered.forEach(r => STATE.selectedIndices.add(r._uid));
      } else {
        filtered.forEach(r => STATE.selectedIndices.delete(r._uid));
      }
      updateRowSelectionUI();
      renderTbody();
    }

    function updateRowSelectionUI() {
      const count = STATE.selectedIndices.size;
      document.getElementById('selectedCountBadge').innerText = count;
      document.getElementById('btnDeleteSelected').disabled = count === 0;

      const master = document.getElementById('masterCheckbox');
      const filtered = getFilteredRows();
      if (master && filtered.length > 0) {
        master.checked = filtered.every(r => STATE.selectedIndices.has(r._uid));
        master.indeterminate = count > 0 && !master.checked;
      }
    }

    function updateDeleteSelectedButton() {
      updateRowSelectionUI();
    }

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ESTADO DE ALTERAÇÕES PENDENTES
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function updatePendingChangesState() {
      let added = 0;
      let modified = 0;

      STATE.workingRows.forEach(r => {
        if (r._isNew) added++;
        else if (STATE.columns.some(col => isCellModified(r, col.key))) modified++;
      });

      const deleted = Math.max(0, STATE.originalRows.length - (STATE.workingRows.length - added));
      const totalChanges = added + modified + deleted;

      STATE.hasUnsavedChanges = totalChanges > 0;
      const btnSave = document.getElementById('btnSave');
      const pendingBadge = document.getElementById('pendingChangesCount');

      if (btnSave) {
        btnSave.disabled = !STATE.hasUnsavedChanges;
        if (STATE.hasUnsavedChanges) {
          btnSave.classList.add('pending');
          btnSave.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/></svg> Salvar (${totalChanges})`;
        } else {
          btnSave.classList.remove('pending');
          btnSave.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/></svg> Salvar Alterações`;
        }
      }

      if (pendingBadge) {
        pendingBadge.innerText = totalChanges;
        pendingBadge.style.color = totalChanges > 0 ? '#fbbf24' : 'var(--fr-txt)';
      }
    }

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       EXPORTAÇÃO (EXCEL & CSV)
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function exportExcel() {
      if (typeof XLSX === 'undefined') {
        showToast('Biblioteca SheetJS ainda não carregou.', 'error');
        return;
      }

      const rowsToExport = STATE.workingRows.map(r => {
        const rowObj = {};
        STATE.columns.forEach(c => {
          rowObj[c.label] = r[c.key] || '';
        });
        return rowObj;
      });

      const worksheet = XLSX.utils.json_to_sheet(rowsToExport);
      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(workbook, worksheet, STATE.currentTableKey.substring(0, 31));

      const fileName = `${STATE.currentTableKey}_atual_${new Date().toISOString().slice(0,10)}.xlsx`;
      XLSX.writeFile(workbook, fileName);
      showToast(`Planilha Excel baixada com sucesso (${rowsToExport.length} registros).`, 'success');
    }

    function exportCSV() {
      window.location.href = `/api/lookups/${STATE.currentTableKey}/export`;
    }

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       IMPORTAÇÃO DE ARQUIVOS (EXCEL / CSV)
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function openImportModal() {
      const modal = document.getElementById('importModal');
      const curCfg = STATE.tablesSummary[STATE.currentTableKey];
      document.getElementById('modalTargetTableName').innerText = curCfg ? curCfg.title : STATE.currentTableKey;
      document.getElementById('importPreviewBox').style.display = 'none';
      document.getElementById('btnConfirmImport').disabled = true;
      document.getElementById('importFileInput').value = '';
      STATE.importedDataCache = null;
      modal.classList.add('active');
    }

    function closeImportModal() {
      document.getElementById('importModal').classList.remove('active');
    }

    function setupDropzone() {
      const dropzone = document.getElementById('fileDropzone');
      if (!dropzone) return;

      ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropzone.classList.add('dragover');
        });
      });

      ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropzone.classList.remove('dragover');
        });
      });

      dropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
          handleFileSelected(files[0]);
        }
      });
    }

    function handleFileSelected(file) {
      if (!file) return;

      const reader = new FileReader();
      const ext = file.name.split('.').pop().toLowerCase();

      reader.onload = function(e) {
        try {
          const data = e.target.result;
          let parsedRows = [];

          if (ext === 'csv') {
            // Decodifica CSV
            const text = new TextDecoder('utf-8').decode(data);
            parsedRows = parseCsvClient(text);
          } else {
            // Decodifica Excel via XLSX
            const workbook = XLSX.read(data, { type: 'array' });
            const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
            parsedRows = XLSX.utils.sheet_to_json(firstSheet, { defval: '' });
          }

          processImportedRows(parsedRows, file.name);
        } catch (err) {
          showToast('Falha ao ler o arquivo: ' + err.message, 'error');
        }
      };

      if (ext === 'csv') {
        reader.readAsArrayBuffer(file);
      } else {
        reader.readAsArrayBuffer(file);
      }
    }

    function parseCsvClient(text) {
      const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0);
      if (lines.length === 0) return [];

      // Detecta cabeçalho
      let headerIdx = 0;
      for (let i = 0; i < Math.min(10, lines.length); i++) {
        const up = lines[i].toUpperCase();
        if (up.includes('FORNECEDOR') || up.includes('USUARIO') || up.includes('COMPRADOR')) {
          headerIdx = i;
          break;
        }
      }

      const sep = lines[headerIdx].includes(';') ? ';' : ',';
      const headers = lines[headerIdx].split(sep).map(h => h.trim().replace(/^["']|["']$/g, ''));
      const rows = [];

      for (let i = headerIdx + 1; i < lines.length; i++) {
        const parts = lines[i].split(sep).map(p => p.trim().replace(/^["']|["']$/g, ''));
        const obj = {};
        headers.forEach((h, idx) => {
          if (h) obj[h] = parts[idx] || '';
        });
        rows.push(obj);
      }
      return rows;
    }

    function processImportedRows(rawRows, fileName) {
      if (!rawRows || rawRows.length === 0) {
        showToast('Nenhum dado encontrado no arquivo selecionado.', 'error');
        return;
      }

      // Normalização e correspondência de colunas
      const normalizedList = [];
      const colMap = {};

      // Mapeia colunas do arquivo para as colunas oficiais
      const sampleRow = rawRows[0];
      const fileHeaders = Object.keys(sampleRow);

      fileHeaders.forEach(fh => {
        const norm = fh.toLowerCase().replace(/[^a-z0-9]/g, '');
        STATE.columns.forEach(col => {
          const colNorm = col.key.toLowerCase().replace(/[^a-z0-9]/g, '');
          const labelNorm = col.label.toLowerCase().replace(/[^a-z0-9]/g, '');
          if (norm === colNorm || norm === labelNorm || norm.includes(colNorm) || colNorm.includes(norm)) {
            colMap[fh] = col.key;
          }
        });
      });

      rawRows.forEach((r, idx) => {
        const item = {
          _uid: 'imported_' + idx + '_' + Date.now(),
          _isNew: true,
          _modified: true
        };
        STATE.columns.forEach(c => {
          item[c.key] = '';
        });

        Object.keys(r).forEach(k => {
          const targetKey = colMap[k];
          if (targetKey) {
            item[targetKey] = String(r[k] || '').trim();
          }
        });

        // Só considera se tiver chave primária preenchida
        if (item[STATE.primaryKey]) {
          normalizedList.push(item);
        }
      });

      if (normalizedList.length === 0) {
        showToast(`Nenhuma linha válida com o campo obrigatório '${STATE.primaryKey}' foi identificada.`, 'error');
        return;
      }

      STATE.importedDataCache = normalizedList;
      document.getElementById('importFileName').innerText = fileName;
      document.getElementById('importValidBadge').innerText = `${normalizedList.length} registros prontos`;
      document.getElementById('importFileDetails').innerHTML = 
        `Colunas mapeadas: <strong>${Object.values(colMap).length} de ${STATE.columns.length}</strong>.`;
      document.getElementById('importPreviewBox').style.display = 'block';
      document.getElementById('btnConfirmImport').disabled = false;
    }

    function applyImportedData() {
      if (!STATE.importedDataCache || STATE.importedDataCache.length === 0) return;

      const mode = document.querySelector('input[name="importMode"]:checked').value;
      if (mode === 'replace') {
        STATE.workingRows = [...STATE.importedDataCache];
      } else {
        // Append / Merge
        const existingMap = new Map();
        STATE.workingRows.forEach(r => existingMap.set(String(r[STATE.primaryKey]), r));

        STATE.importedDataCache.forEach(imp => {
          const pk = String(imp[STATE.primaryKey]);
          if (existingMap.has(pk)) {
            // Atualiza existente
            const target = existingMap.get(pk);
            STATE.columns.forEach(c => {
              if (imp[c.key]) target[c.key] = imp[c.key];
            });
            target._modified = true;
          } else {
            // Insere novo
            STATE.workingRows.push(imp);
          }
        });
      }

      STATE.hasUnsavedChanges = true;
      STATE.currentPage = 1;
      closeImportModal();
      renderGrid();
      updatePendingChangesState();
      showToast(`${STATE.importedDataCache.length} registros carregados na grade com sucesso. Clique em Salvar para persistir.`, 'success');
    }

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       CONFIRMAÇÃO & EXECUÇÃO DO SALVAMENTO
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function openSaveModal() {
      if (!STATE.hasUnsavedChanges) return;

      let added = 0;
      let modified = 0;
      STATE.workingRows.forEach(r => {
        if (r._isNew) added++;
        else if (STATE.columns.some(col => isCellModified(r, col.key))) modified++;
      });
      const deleted = Math.max(0, STATE.originalRows.length - (STATE.workingRows.length - added));

      const curCfg = STATE.tablesSummary[STATE.currentTableKey];
      document.getElementById('saveModalTableName').innerText = curCfg ? curCfg.title : STATE.currentTableKey;
      document.getElementById('saveSummaryTotal').innerText = STATE.workingRows.length.toLocaleString('pt-BR');
      document.getElementById('saveSummaryAdded').innerText = added;
      document.getElementById('saveSummaryModified').innerText = modified;
      document.getElementById('saveSummaryDeleted').innerText = deleted;

      document.getElementById('saveModal').classList.add('active');
    }

    function closeSaveModal() {
      document.getElementById('saveModal').classList.remove('active');
    }

    async function executeSave() {
      const btn = document.getElementById('btnExecuteSave');
      btn.disabled = true;
      btn.innerText = 'Salvando no Lakebase...';

      try {
        // Remove campos internos antes de enviar payload
        const payloadRows = STATE.workingRows.map(r => {
          const clean = {};
          STATE.columns.forEach(c => {
            clean[c.key] = r[c.key] !== undefined && r[c.key] !== null ? String(r[c.key]).trim() : '';
          });
          return clean;
        });

        const res = await fetch(`/api/lookups/${STATE.currentTableKey}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rows: payloadRows })
        });

        const data = await res.json();
        if (data.success) {
          closeSaveModal();
          showToast(data.message || 'Dados salvos com sucesso!', 'success');
          
          // Atualiza o estado original com o novo estado salvo
          STATE.originalRows = JSON.parse(JSON.stringify(payloadRows));
          STATE.workingRows.forEach(r => {
            r._isNew = false;
            r._modified = false;
          });
          STATE.hasUnsavedChanges = false;
          
          document.getElementById('lastSavedTime').innerText = `Salvo às ${new Date().toLocaleTimeString('pt-BR')}`;
          await loadSummary();
          renderGrid();
          updatePendingChangesState();
        } else {
          showToast('Erro ao salvar: ' + (data.error || 'Erro desconhecido'), 'error');
        }
      } catch (err) {
        showToast('Falha na requisição de salvamento: ' + err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerText = 'Confirmar e Salvar Agora';
      }
    }

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ATALHOS DE TECLADO E COPIAR/COLAR DO EXCEL
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function setupKeyboardShortcuts() {
      // Suporte a colar dados do Excel (Ctrl+V)
      window.addEventListener('paste', (e) => {
        // Se estiver editando um campo de texto normal, não intercepta
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        const clipboardData = e.clipboardData || window.clipboardData;
        const pastedText = clipboardData.getData('text');
        if (!pastedText || !pastedText.includes('\t')) return; // É texto tabular

        e.preventDefault();
        const lines = pastedText.split(/\r?\n/).filter(l => l.trim().length > 0);
        if (lines.length === 0) return;

        const newPastedRows = [];
        lines.forEach((line, idx) => {
          const cells = line.split('\t');
          const rowObj = {
            _uid: 'pasted_' + idx + '_' + Date.now(),
            _isNew: true,
            _modified: true
          };
          STATE.columns.forEach((col, cIdx) => {
            rowObj[col.key] = cells[cIdx] ? cells[cIdx].trim() : '';
          });
          if (rowObj[STATE.primaryKey]) {
            newPastedRows.push(rowObj);
          }
        });

        if (newPastedRows.length > 0) {
          STATE.workingRows.unshift(...newPastedRows);
          STATE.hasUnsavedChanges = true;
          STATE.currentPage = 1;
          renderGrid();
          updatePendingChangesState();
          showToast(`${newPastedRows.length} linhas coladas do Excel com sucesso!`, 'success');
        }
      });

      // Atalho Ctrl+S para salvar
      window.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
          e.preventDefault();
          if (STATE.hasUnsavedChanges) openSaveModal();
        }
      });
    }

    /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       TOASTS & UTILITÁRIOS
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
    function showToast(msg, type = 'info') {
      const container = document.getElementById('toastContainer');
      const toast = document.createElement('div');
      toast.className = `cd-toast cd-toast-${type}`;

      let icon = 'ℹ️';
      if (type === 'success') icon = '✓';
      if (type === 'error') icon = '⚠️';

      toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(msg)}</span>`;
      container.appendChild(toast);

      setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s ease';
        setTimeout(() => toast.remove(), 300);
      }, 4000);
    }

    function escapeHtml(text) {
      if (!text) return '';
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    function toggleTheme() {
      const html = document.documentElement;
      const current = html.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      localStorage.setItem('portal_theme', next);
    }

    // Inicializa tema salvo
    (function() {
      const saved = localStorage.getItem('portal_theme');
      if (saved) document.documentElement.setAttribute('data-theme', saved);
    })();
  