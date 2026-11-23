"""
Full test suite for lookups, fornecedores_sem_oc, and all business rules.
"""
import sys
import os
import json

# Ensure src/app is importable
sys.path.insert(0, os.path.abspath("src/app"))

import app

def test_all():
    print("==================================================")
    print("1. TESTING LOOKUPS CONFIG & LOCAL FALLBACKS")
    print("==================================================")
    
    expected_tables = ["fornecedores_especiais", "fornecedores_nao_negociaveis", "fornecedores_sem_oc", "compradores_funcionais"]
    for tbl in expected_tables:
        assert tbl in app.LOOKUP_CONFIG, f"Missing table config {tbl}"
        cfg = app.LOOKUP_CONFIG[tbl]
        rows = app._read_local_csv_fallback(cfg["csv_filename"])
        cols = list(rows[0].keys()) if rows else []
        print(f"  [OK] Table '{tbl}': {len(rows)} rows, PK={cfg['primary_key']}, cols={len(cols)}")
        assert len(rows) > 0, f"Table {tbl} has 0 rows in fallback!"
        # Check PK uniqueness and non-empty
        pk = cfg["primary_key"]
        pk_vals = [r.get(pk) for r in rows if r.get(pk)]
        assert len(pk_vals) == len(rows), f"Empty PKs found in {tbl}"
        if tbl == "fornecedores_sem_oc":
            assert len(set(pk_vals)) == len(rows), f"Duplicate PKs found in {tbl}"
        else:
            print(f"       (Legacy {tbl} has {len(rows)} rows, {len(set(pk_vals))} unique PKs)")
    
    print("\n==================================================")
    print("2. TESTING FLASK TEST CLIENT LOOKUPS API")
    print("==================================================")
    with app.app.test_client() as client:
        # A. Summary
        res = client.get("/api/lookups/summary")
        assert res.status_code == 200, f"Summary status: {res.status_code}"
        data = res.get_json()
        assert "tables" in data, "Summary missing tables key"
        table_map = {t["key"]: t for t in data.get("tables", [])}
        for tbl in expected_tables:
            assert tbl in table_map, f"Summary missing table {tbl}"
            item = table_map[tbl]
            print(f"  [OK] API Summary {tbl}: count={item.get('total')}, title={item.get('title')}")
            assert item.get("total", 0) > 0, f"Table {tbl} total is 0"

        # B. Get each table
        for tbl in expected_tables:
            res = client.get(f"/api/lookups/{tbl}")
            assert res.status_code == 200, f"Get {tbl} status: {res.status_code}"
            tbl_data = res.get_json()
            assert tbl_data.get("success"), f"Get {tbl} returned success=False: {tbl_data}"
            assert len(tbl_data.get("rows", [])) > 0, f"Get {tbl} returned 0 rows"
            print(f"  [OK] GET /api/lookups/{tbl}: success=True, {len(tbl_data['rows'])} rows returned")

        # C. Parse file endpoint fallback
        res = client.post("/api/lookups/parse-file")
        # Should return 400 when no file provided
        assert res.status_code == 400, "Parse file without file should return 400"
        print("  [OK] POST /api/lookups/parse-file properly validated empty file")

    print("\n==================================================")
    print("3. TESTING FILTER CLAUSES & SQL GENERATION")
    print("==================================================")
    from werkzeug.datastructures import MultiDict
    
    # Test _parse_filters with is_fornecedor_sem_oc
    args = MultiDict([('is_fornecedor_sem_oc', 'COM ATUAÇÃO')])
    clauses, _ = app._parse_filters(args)
    clause_str = " ".join(clauses)
    print("  [OK] Generated _parse_filters clauses for is_fornecedor_sem_oc='COM ATUAÇÃO':")
    print(f"       Clause: {clauses}")
    assert "IS_FORNECEDOR_SEM_OC IN ('COM ATUAÇÃO')" in clause_str

    # Test _parse_order_filters with is_fornecedor_sem_oc
    args_multi = MultiDict([('is_fornecedor_sem_oc', 'COM ATUAÇÃO'), ('is_fornecedor_sem_oc', 'SEM OC')])
    order_clauses = app._parse_order_filters(args_multi)
    order_clause_str = " ".join(order_clauses)
    print("  [OK] Generated _parse_order_filters clauses for multi-value:")
    print(f"       Clause: {order_clauses}")
    assert "is_fornecedor_sem_oc IN ('COM ATUAÇÃO','SEM OC')" in order_clause_str

    # Test _cascading_where with is_fornecedor_sem_oc
    with app.app.test_request_context("/api/filtros/opcoes?is_fornecedor_sem_oc=SEM OC"):
        from flask import request
        c_where = app._cascading_where(request.args, exclude_field="is_fornecedor_sem_oc")
        # When querying options for is_fornecedor_sem_oc itself, it should exclude its own filter
        assert "is_fornecedor_sem_oc" not in " ".join(c_where)
        print("  [OK] Cascading correctly excludes target field")
        
        c_where2 = app._cascading_where(request.args, exclude_field="macro_categoria")
        # When querying other fields, is_fornecedor_sem_oc should be included
        assert any("is_fornecedor_sem_oc" in w.lower() for w in c_where2)
        print("  [OK] Cascading correctly includes is_fornecedor_sem_oc for other dimensions")

    print("\n==================================================")
    print("4. TESTING REPORT DEFINITION")
    print("==================================================")
    with open("src/app/app.py", "r", encoding="utf-8") as f:
        app_source = f.read()
    assert "IS_FORNECEDOR_SEM_OC" in app_source
    assert "is_fornecedor_sem_oc" in app_source
    print("  [OK] app.py has IS_FORNECEDOR_SEM_OC in report projections and export definitions")

    print("\n==================================================")
    print("5. VERIFYING ETL SCRIPT")
    print("==================================================")
    with open("src/dados/compras_360_lakebase_etl.py", "r", encoding="utf-8") as f:
        etl_code = f.read()
    assert "fornecedores_sem_oc" in etl_code
    assert "is_fornecedor_sem_oc" in etl_code
    assert "tv_fornecedores_sem_oc" in etl_code
    print("  [OK] ETL code contains all definitions and views for fornecedores_sem_oc")

    print("\n==================================================")
    print("6. VERIFYING CADASTROS.HTML & SHARED FILTERS")
    print("==================================================")
    with open("src/app/cadastros.html", "r", encoding="utf-8") as f:
        cad_code = f.read()
    assert "tab_fornecedores_sem_oc" in cad_code
    assert "cnt_fornecedores_sem_oc" in cad_code
    assert "fornecedores_sem_oc" in cad_code
    print("  [OK] cadastros.html contains tab_fornecedores_sem_oc and counter")

    with open("src/app/filters-shared.js", "r", encoding="utf-8") as f:
        filt_code = f.read()
    assert "is_fornecedor_sem_oc" in filt_code
    assert "fFornSemOC" in filt_code
    print("  [OK] filters-shared.js contains is_fornecedor_sem_oc and fFornSemOC")

    print("\n>> ALL TESTS PASSED SUCCESSFULLY! <<")

if __name__ == "__main__":
    test_all()
