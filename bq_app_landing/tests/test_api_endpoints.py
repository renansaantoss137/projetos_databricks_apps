import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import json
import pandas as pd
from src.app.app import app, LOOKUP_CONFIG

class TestApiEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        # Mock de usuário admin
        self.headers = {
            "Content-Type": "application/json",
            "X-Forwarded-Email": "renan.ferreira@grupobimbo.com"
        }
        # Lê linhas de fixtures/base_landing.xlsx
        df = pd.read_excel('fixtures/base_landing.xlsx', sheet_name='Base de Landing')
        self.sample_rows = []
        for _, r in df.iterrows():
            if str(r.get("Ano", "")).strip().lower() == "total":
                continue
            d = {}
            for c in LOOKUP_CONFIG["base_landing"]["columns"]:
                val = r.get(c["label"]) if c["label"] in r else r.get(c["key"], "")
                d[c["key"]] = "" if pd.isna(val) else str(val)
            if "Data" in r and pd.notna(r["Data"]):
                dt = pd.to_datetime(r["Data"])
                d["ano"] = str(dt.year)
                d["mes"] = str(dt.month)
            self.sample_rows.append(d)

    def test_preview_merge_identical(self):
        """Testa o endpoint /api/lookups/base_landing/preview_merge com as 696 linhas."""
        res = self.client.post(
            '/api/lookups/base_landing/preview_merge',
            data=json.dumps({"rows": self.sample_rows, "mode": "merge"}),
            headers=self.headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        stats = data.get("stats")
        self.assertEqual(stats.get("total_importado"), 696)
        # Como a base tem 696 linhas, as idênticas devem ser identificadas
        self.assertEqual(stats.get("novos"), 0)
        self.assertEqual(stats.get("total_final"), 696)

    def test_preview_merge_with_updates_and_new(self):
        """Testa com 1 linha modificada e 1 linha nova."""
        rows = [dict(r) for r in self.sample_rows[:10]] # envia apenas 10 linhas
        rows[0]["landing"] = 1234567.0 # modifica a primeira
        nova = dict(rows[0])
        nova["grupo_de_clientes"] = "CLIENTE TESTE TOTALMENTE NOVO"
        rows.append(nova) # adiciona uma nova

        res = self.client.post(
            '/api/lookups/base_landing/preview_merge',
            data=json.dumps({"rows": rows, "mode": "merge"}),
            headers=self.headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        stats = data.get("stats")
        self.assertEqual(stats.get("novos"), 1)
        self.assertEqual(stats.get("atualizados"), 1)
        self.assertEqual(stats.get("inalterados"), 9)
        self.assertEqual(stats.get("total_final"), 697) # 696 existentes + 1 nova


    def test_preview_merge_with_calculated_formulas_and_one_comment_modified(self):
        """
        Valida que colunas calculadas (DIF. BGT, DIF. FCST) vindas preenchidas do Excel
        NÃO geram falsos positivos de linhas modificadas, e que apenas a alteração real
        de 1 comentário é detectada.
        """
        from src.app.app import _read_lookup_rows
        current_rows, _ = _read_lookup_rows("base_landing")
        rows = [dict(r) for r in current_rows]
        # Simula Excel preenchendo DIF. BGT e DIF. FCST em todas as linhas
        for idx, r in enumerate(rows):
            r["dif_bgt"] = 12345.67 + idx
            r["dif_fcst"] = -9876.54 + idx
        # Modifica apenas 1 comentário
        rows[10]["comentarios"] = "Comentário único modificado para teste"

        res = self.client.post(
            '/api/lookups/base_landing/preview_merge',
            data=json.dumps({"rows": rows, "mode": "merge"}),
            headers=self.headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        stats = data.get("stats")
        self.assertEqual(stats.get("total_importado"), len(rows))
        self.assertEqual(stats.get("novos"), 0)
        self.assertEqual(stats.get("atualizados"), 1)
        self.assertEqual(stats.get("inalterados"), len(rows) - 1)


if __name__ == '__main__':
    unittest.main()
