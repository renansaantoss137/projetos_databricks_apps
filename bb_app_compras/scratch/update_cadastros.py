import shutil

PATH = 'src/app/cadastros.html'
shutil.copy2(PATH, PATH + '.bak_before_sem_oc')

with open(PATH, 'r', encoding='utf-8') as f:
    c = f.read()

# 1. Update CSS for 5 stat cards
old_css_cards = '''.cd-stat-card:nth-child(2) .cd-stat-icon {
      background: rgba(239, 68, 68, 0.12);
      color: #f87171;
    }
    .cd-stat-card:nth-child(3) .cd-stat-icon {
      background: rgba(16, 185, 129, 0.12);
      color: #34d399;
    }
    .cd-stat-card:nth-child(4) .cd-stat-icon {
      background: rgba(245, 158, 11, 0.12);
      color: #fbbf24;
    }'''

new_css_cards = '''.cd-stat-card:nth-child(2) .cd-stat-icon {
      background: rgba(239, 68, 68, 0.12);
      color: #f87171;
    }
    .cd-stat-card:nth-child(3) .cd-stat-icon {
      background: rgba(168, 85, 247, 0.12);
      color: #c084fc;
    }
    .cd-stat-card:nth-child(4) .cd-stat-icon {
      background: rgba(16, 185, 129, 0.12);
      color: #34d399;
    }
    .cd-stat-card:nth-child(5) .cd-stat-icon {
      background: rgba(245, 158, 11, 0.12);
      color: #fbbf24;
    }'''

assert old_css_cards in c, "old_css_cards not found in cadastros.html"
c = c.replace(old_css_cards, new_css_cards, 1)

# 2. Add stat card for fornecedores_sem_oc
old_stat_row = '''      <div class="cd-stat-card" onclick="switchTable('fornecedores_nao_negociaveis')" id="tab_fornecedores_nao_negociaveis">
        <div class="cd-stat-icon">🚫</div>
        <div class="cd-stat-content">
          <div class="cd-stat-val" id="cnt_fornecedores_nao_negociaveis">--</div>
          <div class="cd-stat-label">Não Negociáveis</div>
          <div class="cd-stat-desc">Compras diretas / concessionárias</div>
        </div>
      </div>'''

new_stat_row = old_stat_row + '''

      <div class="cd-stat-card" onclick="switchTable('fornecedores_sem_oc')" id="tab_fornecedores_sem_oc">
        <div class="cd-stat-icon">📑</div>
        <div class="cd-stat-content">
          <div class="cd-stat-val" id="cnt_fornecedores_sem_oc">--</div>
          <div class="cd-stat-label">Fornecedores sem OC</div>
          <div class="cd-stat-desc">Faturamento sem PO permitido</div>
        </div>
      </div>'''

assert old_stat_row in c, "old_stat_row not found in cadastros.html"
c = c.replace(old_stat_row, new_stat_row, 1)

# 3. Update handleFileSelected to support backend parsing fallback
old_handle_file = '''    function handleFileSelected(file) {
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
    }'''

new_handle_file = '''    async function handleFileSelected(file) {
      if (!file) return;
      showToast('Processando e validando planilha...', 'info');

      const ext = file.name.split('.').pop().toLowerCase();
      let parsedRows = [];
      let parseSuccess = false;

      // 1. Tenta decodificar no cliente (SheetJS / CSV)
      try {
        const buffer = await file.arrayBuffer();
        if (ext === 'csv') {
          const text = new TextDecoder('utf-8').decode(buffer);
          parsedRows = parseCsvClient(text);
          if (parsedRows.length > 0) parseSuccess = true;
        } else if (typeof XLSX !== 'undefined') {
          const workbook = XLSX.read(buffer, { type: 'array' });
          if (workbook && workbook.SheetNames && workbook.SheetNames.length > 0) {
            const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
            parsedRows = XLSX.utils.sheet_to_json(firstSheet, { defval: '' });
            if (parsedRows.length > 0) parseSuccess = true;
          }
        }
      } catch (clientErr) {
        console.warn('Parser cliente não conseguiu ler diretamente (pode ser arquivo protegido/MIP ou formato legado):', clientErr);
      }

      // 2. Se o cliente não conseguiu ler (ex: arquivo corporativo com criptografia RMS/MIP ou formato composto OLE2), envia para o backend
      if (!parseSuccess || parsedRows.length === 0) {
        try {
          showToast('Lendo arquivo via serviço corporativo...', 'info');
          const formData = new FormData();
          formData.append('file', file);
          const res = await fetch('/api/lookups/parse-file', {
            method: 'POST',
            body: formData
          });
          const result = await res.json();
          if (result.success && result.rows && result.rows.length > 0) {
            parsedRows = result.rows;
            parseSuccess = true;
          } else {
            showToast('Não foi possível ler os registros da planilha: ' + (result.error || 'Formato não reconhecido'), 'error');
            return;
          }
        } catch (serverErr) {
          showToast('Falha ao ler o arquivo: ' + serverErr.message, 'error');
          return;
        }
      }

      processImportedRows(parsedRows, file.name);
    }'''

assert old_handle_file in c, "old_handle_file not found in cadastros.html"
c = c.replace(old_handle_file, new_handle_file, 1)

# 4. Enhance processImportedRows with intelligent column mapping and data validation
old_process = '''    function processImportedRows(rawRows, fileName) {
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
    }'''

new_process = '''    function processImportedRows(rawRows, fileName) {
      if (!rawRows || rawRows.length === 0) {
        showToast('Nenhum dado encontrado no arquivo selecionado.', 'error');
        return;
      }

      // Normalização e correspondência inteligente de colunas
      const normalizedList = [];
      const colMap = {};

      // Mapeia colunas do arquivo para as colunas oficiais
      const sampleRow = rawRows[0];
      const fileHeaders = Object.keys(sampleRow);

      fileHeaders.forEach(fh => {
        const norm = fh.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]/g, '');
        let matchedKey = null;

        if (norm.includes('fornecedor') && (norm.includes('num') || norm.includes('cod') || norm.includes('codigo') || norm.includes('id') || norm.includes('oracle'))) {
          matchedKey = 'cod_fornecedor_oracle';
        } else if (norm.includes('fornecedor') && (norm.includes('nome') || norm.includes('razao') || norm.includes('desc') || norm === 'fornecedor')) {
          matchedKey = 'nome_fornecedor_oracle';
        } else if (norm.includes('usuario') && (norm.includes('oracle') || norm.includes('user') || norm.includes('login') || norm.includes('matricula') || norm === 'usuario')) {
          matchedKey = 'usuario_oracle';
        } else if (norm.includes('comprador') && (norm.includes('funcional') || norm.includes('nome') || norm === 'comprador')) {
          matchedKey = 'comprador_funcional';
        } else if (norm.includes('produto') || norm.includes('servico') || norm.includes('marca') || norm.includes('especificacao')) {
          matchedKey = 'produto_servico';
        } else if (norm.includes('justificativa') || norm.includes('motivo') || norm.includes('obs')) {
          matchedKey = 'justificativa';
        } else if (norm.includes('area') || norm.includes('depto') || norm.includes('departamento') || norm.includes('setor')) {
          matchedKey = 'area';
        } else if (norm.includes('data') && norm.includes('registro')) {
          matchedKey = 'data_registro';
        } else if (norm.includes('email') || norm.includes('mail')) {
          matchedKey = 'email';
        } else if (norm.includes('unidade') || norm.includes('filial') || norm.includes('planta')) {
          matchedKey = 'unidade';
        } else if (norm.includes('operacao') || norm.includes('bu')) {
          matchedKey = 'operacao';
        }

        if (matchedKey && STATE.columns.some(c => c.key === matchedKey)) {
          colMap[fh] = matchedKey;
          return;
        }

        // Fallback para correspondência literal
        STATE.columns.forEach(col => {
          const colNorm = col.key.toLowerCase().replace(/[^a-z0-9]/g, '');
          const labelNorm = col.label.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]/g, '');
          if (norm === colNorm || norm === labelNorm || norm.includes(colNorm) || colNorm.includes(norm)) {
            colMap[fh] = col.key;
          }
        });
      });

      // Validação de dados rigorosa
      let emptyPks = 0;
      let duplicatePks = 0;
      const seenPks = new Set();
      const todayStr = new Date().toLocaleDateString('pt-BR');

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
            let val = String(r[k] !== undefined && r[k] !== null ? r[k] : '');
            // Limpa quebras de linha internas e espaços excessivos
            val = val.replace(/[\\r\\n]+/g, ' ').trim();
            // Limpa formatação decimal de inteiros do Excel (.0)
            if (targetKey === 'cod_fornecedor_oracle' && /^\\d+\\.0$/.test(val)) {
              val = val.replace(/\\.0$/, '');
            }
            item[targetKey] = val;
          }
        });

        // Preenche campos auxiliares padrão se vazios
        if (!item.data_registro && STATE.columns.some(c => c.key === 'data_registro')) {
          item.data_registro = todayStr;
        }

        const pkVal = String(item[STATE.primaryKey] || '').trim();
        if (!pkVal) {
          emptyPks++;
          return;
        }

        if (seenPks.has(pkVal)) {
          duplicatePks++;
          return;
        }
        seenPks.add(pkVal);
        normalizedList.push(item);
      });

      if (normalizedList.length === 0) {
        showToast(`Nenhuma linha válida com o campo obrigatório '${STATE.primaryKey}' foi identificada. Verifique as colunas do arquivo.`, 'error');
        return;
      }

      STATE.importedDataCache = normalizedList;
      document.getElementById('importFileName').innerText = fileName;
      document.getElementById('importValidBadge').innerText = `${normalizedList.length} registros válidos`;
      
      let detailsHtml = `Colunas mapeadas: <strong>${Object.values(colMap).length} de ${STATE.columns.length}</strong>.`;
      if (emptyPks > 0) {
        detailsHtml += ` <span style="color:#f87171">(${emptyPks} linhas vazias ignoradas)</span>`;
      }
      if (duplicatePks > 0) {
        detailsHtml += ` <span style="color:#fbbf24">(${duplicatePks} chaves duplicadas desconsideradas)</span>`;
      }
      detailsHtml += `<br><span style="font-size:0.7rem; color:var(--fr-txt-soft); margin-top:4px; display:inline-block;">Exemplo do 1º registro: <strong>${escapeHtml(normalizedList[0][STATE.primaryKey])}</strong> - ${escapeHtml(normalizedList[0].nome_fornecedor_oracle || normalizedList[0].comprador_funcional || '')}</span>`;

      document.getElementById('importFileDetails').innerHTML = detailsHtml;
      document.getElementById('importPreviewBox').style.display = 'block';
      document.getElementById('btnConfirmImport').disabled = false;
    }'''

assert old_process in c, "old_process not found in cadastros.html"
c = c.replace(old_process, new_process, 1)

with open(PATH, 'w', encoding='utf-8') as f:
    f.write(c)
print("cadastros.html updated successfully!")
