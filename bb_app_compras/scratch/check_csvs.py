for fname in ['fornecedores_nao_negociaiveis.csv', 'fornecedores_especiais.csv', 'COMPRADORES_FUNCIONAIS(BASE_COMPRAS).csv']:
    path = f'src/dados/{fname}'
    for enc in ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']:
        try:
            with open(path, 'r', encoding=enc) as f:
                lines = [f.readline().strip() for _ in range(5)]
            print(f"=== {fname} ({enc}) ===")
            for l in lines:
                print("  ", l)
            break
        except Exception:
            continue
