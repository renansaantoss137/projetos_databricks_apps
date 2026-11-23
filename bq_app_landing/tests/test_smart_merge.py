import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import pandas as pd
from src.app.app import _smart_merge_rows, LOOKUP_CONFIG

CFG = LOOKUP_CONFIG["base_landing"]
COMPOSITE_KEYS = CFG["composite_keys"]
COLUMNS_CFG = CFG["columns"]


class TestSmartMerge(unittest.TestCase):
    def setUp(self):
        # Carrega as 696 linhas oficiais de fixtures/base_landing.xlsx
        self.df_base = pd.read_excel('fixtures/base_landing.xlsx', sheet_name='Base de Landing')
        self.base_rows = []
        for _, r in self.df_base.iterrows():
            if str(r.get("Ano", "")).strip().lower() == "total":
                continue
            d = {}
            for col in COLUMNS_CFG:
                d[col["key"]] = r.get(col["label"]) if col["label"] in r else r.get(col["key"], "")
                if pd.isna(d[col["key"]]):
                    d[col["key"]] = ""
            
            # Se a planilha tiver apenas 'Data', deriva 'ano' e 'mes'
            if "Data" in r and pd.notna(r["Data"]):
                try:
                    dt = pd.to_datetime(r["Data"])
                    d["ano"] = str(dt.year)
                    d["mes"] = str(dt.month)
                    d["data"] = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

            self.base_rows.append(d)

    def test_identical_import_no_duplicates(self):
        """Caso reportado: importar exatamente as mesmas 696 linhas NÃO deve duplicar para 1392."""
        imported_rows = [dict(r) for r in self.base_rows]
        final_rows, stats = _smart_merge_rows(self.base_rows, imported_rows, COMPOSITE_KEYS, COLUMNS_CFG, mode="merge")
        self.assertEqual(len(final_rows), 696)
        self.assertEqual(stats["total_final"], 696)
        self.assertEqual(stats["inalterados"], 696)
        self.assertEqual(stats["atualizados"], 0)
        self.assertEqual(stats["novos"], 0)

    def test_modified_rows_updates_in_place(self):
        """Alterar 5 linhas deve atualizar apenas essas 5 linhas e manter total em 696."""
        imported_rows = [dict(r) for r in self.base_rows]
        for i in range(5):
            imported_rows[i]["landing"] = 999999.0
            imported_rows[i]["comentarios"] = "Valor atualizado pelo teste"

        final_rows, stats = _smart_merge_rows(self.base_rows, imported_rows, COMPOSITE_KEYS, COLUMNS_CFG, mode="merge")
        self.assertEqual(len(final_rows), 696)
        self.assertEqual(stats["inalterados"], 691)
        self.assertEqual(stats["atualizados"], 5)
        self.assertEqual(stats["novos"], 0)
        # Verifica se o valor foi efetivamente atualizado
        self.assertEqual(float(final_rows[0]["landing"]), 999999.0)

    def test_new_rows_insertion(self):
        """Adicionar nova linha com chave inédita deve incrementar a base."""
        imported_rows = [dict(r) for r in self.base_rows]
        nova_linha = dict(self.base_rows[0])
        nova_linha["grupo_de_clientes"] = "NOVO CLIENTE TESTE"
        nova_linha["sub_canal"] = "CANAL NOVO"
        imported_rows.append(nova_linha)

        final_rows, stats = _smart_merge_rows(self.base_rows, imported_rows, COMPOSITE_KEYS, COLUMNS_CFG, mode="merge")
        self.assertEqual(len(final_rows), 697)
        self.assertEqual(stats["novos"], 1)
        self.assertEqual(stats["inalterados"], 696)

    def test_cure_corrupted_1392_base(self):
        """Se a base já estiver com 1392 linhas duplicadas, o smart_merge deve consolidar de volta para 696."""
        corrupted_base = self.base_rows + self.base_rows # 1392 linhas!
        imported_rows = [dict(r) for r in self.base_rows]

        final_rows, stats = _smart_merge_rows(corrupted_base, imported_rows, COMPOSITE_KEYS, COLUMNS_CFG, mode="merge")
        self.assertEqual(len(final_rows), 696)
        self.assertEqual(stats["duplicatas_removidas_base"], 696)
        self.assertEqual(stats["total_final"], 696)

    def test_replace_mode(self):
        """Modo replace deve substituir a base inteira e deduplicar internamente se necessário."""
        imported_rows = [dict(self.base_rows[0]), dict(self.base_rows[1]), dict(self.base_rows[0])] # 3 rows with 1 duplicate
        final_rows, stats = _smart_merge_rows(self.base_rows, imported_rows, COMPOSITE_KEYS, COLUMNS_CFG, mode="replace")
        self.assertEqual(len(final_rows), 2)
        self.assertEqual(stats["total_final"], 2)


if __name__ == '__main__':
    unittest.main()
