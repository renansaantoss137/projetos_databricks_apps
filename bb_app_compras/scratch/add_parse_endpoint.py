import py_compile

APP_PATH = 'src/app/app.py'

with open(APP_PATH, 'r', encoding='utf-8') as f:
    c = f.read()

target = "@app.route('/api/auth/me', methods=['GET'])"
assert target in c, "Could not find target in app.py"

endpoint_code = '''@app.route('/api/lookups/parse-file', methods=['POST'])
def lookups_parse_file():
    """Robust endpoint to parse uploaded spreadsheets (Excel/CSV), with fallback for RMS-protected files."""
    user_email = _get_current_user_email()
    if not _is_user_authorized_for_cadastros(user_email):
        return jsonify({"success": False, "error": "Acesso negado para o módulo de cadastros."}), 403

    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename:
        return jsonify({"success": False, "error": "Nenhum arquivo enviado."}), 400

    filename = uploaded.filename
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    file_bytes = uploaded.read()
    if not file_bytes:
        return jsonify({"success": False, "error": "Arquivo vazio."}), 400

    parsed_rows = []
    
    # 1. Try Pandas (openpyxl / xlrd / csv)
    try:
        import pandas as pd
        if ext == 'csv':
            for enc in ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']:
                try:
                    df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, sep=None, engine='python')
                    if not df.empty:
                        break
                except Exception:
                    continue
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))
        
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                item = {}
                for col in df.columns:
                    val = row[col]
                    val_str = "" if pd.isna(val) else str(val).strip()
                    if val_str.endswith(".0") and val_str[:-2].isdigit():
                        val_str = val_str[:-2]
                    item[str(col).strip()] = val_str
                if any(item.values()):
                    parsed_rows.append(item)
    except Exception as e:
        _log.warning("Pandas failed to read uploaded file %s: %s", filename, e)

    # 2. If failed and on Windows, attempt Excel COM (handles RMS/MIP encrypted files)
    if not parsed_rows and os.name == 'nt' and ext in ['xlsx', 'xls']:
        try:
            import tempfile, subprocess
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}").replace('/', '\\\\')
            with open(temp_path, "wb") as f:
                f.write(file_bytes)
            
            ps_script = f"""
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {{
    $wb = $excel.Workbooks.Open('{temp_path}')
    $sh = $wb.Sheets.Item(1)
    $used = $sh.UsedRange
    $rows = $used.Rows.Count
    $cols = $used.Columns.Count
    $headers = @()
    for ($c = 1; $c -le $cols; $c++) {{
        $h = [string]$sh.Cells.Item(1, $c).Text
        $headers += ($h -replace '[\\r\\n]+', ' ').Trim()
    }}
    $data = @()
    for ($r = 2; $r -le $rows; $r++) {{
        $rowObj = [ordered]@{{}}
        $hasVal = $false
        for ($c = 1; $c -le $cols; $c++) {{
            $val = [string]$sh.Cells.Item($r, $c).Text
            $val = ($val -replace '[\\r\\n]+', ' ').Trim()
            $key = $headers[$c - 1]
            if ($key) {{
                $rowObj[$key] = $val
                if ($val) {{ $hasVal = $true }}
            }}
        }}
        if ($hasVal) {{
            $data += [PSCustomObject]$rowObj
        }}
    }}
    $wb.Close($false)
    $data | ConvertTo-Json -Compress
}} finally {{
    $excel.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
}}
"""
            ps_res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                                   capture_output=True, text=True, timeout=45)
            if ps_res.returncode == 0 and ps_res.stdout.strip():
                raw_json = json.loads(ps_res.stdout.strip())
                if isinstance(raw_json, dict):
                    parsed_rows = [raw_json]
                elif isinstance(raw_json, list):
                    parsed_rows = raw_json
            try:
                os.remove(temp_path)
            except Exception:
                pass
        except Exception as e:
            _log.warning("Windows COM fallback failed for %s: %s", filename, e)

    if not parsed_rows:
        return jsonify({
            "success": False,
            "error": "Não foi possível extrair dados da planilha. Verifique se o arquivo está corrompido ou sem linhas de dados."
        }), 400

    return jsonify({
        "success": True,
        "filename": filename,
        "rows": parsed_rows,
        "count": len(parsed_rows),
        "columns": list(parsed_rows[0].keys()) if parsed_rows else []
    })


'''

c = c.replace(target, endpoint_code + target, 1)

with open(APP_PATH, 'w', encoding='utf-8') as f:
    f.write(c)

py_compile.compile(APP_PATH, doraise=True)
print("parse-file endpoint added and app.py compiles cleanly!")
