import io
import os
import sys
import unittest
import openpyxl

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "app")))
from app import app, _gerar_workbook_oficial_bytes, OFFICIAL_EXCEL_COLUMNS

class TestExcelExport(unittest.TestCase):

    def test_export_excel_format_and_styles(self):
        """Valida se a planilha exportada possui todas as características oficiais de BQ LANDING.xlsx."""
        sample_rows = [
            {
                "Ano": 2026,
                "Mês": 1,
                "Grupo de Clientes": "MC DONALDS",
                "Cod_GR_Cliente": "1",
                "Diretor": "Ronaldo Pernambuco",
                "Gerente": "Juliana Kitz",
                "Canal": "QSR",
                "Sub_Canal": "Mc Donald's",
                "Setor": "I",
                "Categoria": "Buns",
                "Sub_Categoria": "Buns",
                "RECEITA | VOLUME": "Receita",
                "BGT": 16747557.55,
                "FCST": 18829763.84,
                "LANDING": 17059068.11,
                "REALIZADO": "-",
                "COMENTÁRIOS": "-"
            },
            {
                "ano": 2026,
                "mes": 2,
                "grupo_de_clientes": "BURGER KING",
                "cod_gr_cliente": "58",
                "diretor": "Ronaldo Pernambuco",
                "gerente": "Lumena Minsor",
                "canal": "QSR",
                "sub_canal": "Zamp",
                "setor": "II",
                "categoria": "Buns",
                "sub_categoria": "Buns",
                "receita_volume": "Receita",
                "bgt": 9668708.9,
                "fcst": 9755023.1,
                "landing": 9787094.1,
                "realizado": "-",
                "comentarios": "-"
            }
        ]

        excel_bytes = _gerar_workbook_oficial_bytes(sample_rows)
        self.assertGreater(len(excel_bytes), 1000)

        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
        
        # 1. Todas as 5 abas devem estar presentes
        expected_sheets = ["De_Para", "Base de Landing", "Total QSR", "Total Categoria", "Resumo"]
        for s in expected_sheets:
            self.assertIn(s, wb.sheetnames, f"Aba '{s}' não encontrada no workbook exportado!")

        ws = wb["Base de Landing"]
        
        # 2. Cabeçalhos oficiais na linha 1 (20 colunas com Unidade de Medida)
        expected_headers = [
            "Ano", "Mês", "Grupo de Clientes", "Cod_GR_Cliente", "Diretor", "Gerente",
            "Canal", "Sub_Canal", "Setor", "Categoria", "Sub_Categoria", "Unidade de Medida",
            "RECEITA | VOLUME", "BGT", "FCST", "LANDING", "DIF. BGT", "DIF. FCST", "REALIZADO", "COMENTÁRIOS"
        ]
        for col_idx, expected_h in enumerate(expected_headers, start=1):
            actual_h = ws.cell(1, col_idx).value
            self.assertEqual(actual_h, expected_h, f"Coluna {col_idx} esperava '{expected_h}', mas obteve '{actual_h}'")

        # 3. Tabela 'Tabela2' com 'TableStyleLight2'
        self.assertIn("Tabela2", ws.tables, "Tabela 'Tabela2' não encontrada na aba Base de Landing!")
        tab = ws.tables["Tabela2"]
        self.assertEqual(tab.ref, "A1:T3", f"Ref da Tabela2 deveria ser 'A1:T3', obteve '{tab.ref}'")
        self.assertEqual(tab.tableStyleInfo.name, "TableStyleLight2", f"Estilo da tabela deveria ser 'TableStyleLight2', obteve '{tab.tableStyleInfo.name}'")
        self.assertTrue(tab.tableStyleInfo.showRowStripes, "Linhas zebradas (showRowStripes) devem estar ativadas!")

        # 4. Formatação de números e fórmulas
        self.assertEqual(ws.cell(2, 14).number_format, "#,##0")
        self.assertEqual(ws.cell(2, 15).number_format, "#,##0")
        self.assertEqual(ws.cell(2, 16).number_format, "#,##0")
        self.assertEqual(ws.cell(2, 17).number_format, "#,##0")
        self.assertEqual(ws.cell(2, 18).number_format, "#,##0")
        self.assertEqual(ws.cell(2, 17).value, "=P2-N2")
        self.assertEqual(ws.cell(2, 18).value, "=P2-O2")

        # 5. Tipografia Aptos Narrow tamanho 9
        self.assertEqual(ws.cell(2, 1).font.name, "Aptos Narrow")
        self.assertEqual(ws.cell(2, 1).font.size, 9.0)

        # 6. Alinhamentos (esquerda para descrições, centro para códigos/métricas)
        self.assertEqual(ws.cell(2, 3).alignment.horizontal, "left")
        self.assertEqual(ws.cell(2, 5).alignment.horizontal, "left")
        self.assertEqual(ws.cell(2, 1).alignment.horizontal, "center")
        self.assertEqual(ws.cell(2, 13).alignment.horizontal, "center")

    def test_endpoint_export_excel(self):
        """Testa o endpoint GET /api/lookups/base_landing/export_excel."""
        client = app.test_client()
        resp = client.get("/api/lookups/base_landing/export_excel")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("Content-Disposition", resp.headers)
        self.assertIn("BQ_LANDING_", resp.headers["Content-Disposition"])

        wb = openpyxl.load_workbook(io.BytesIO(resp.data))
        self.assertIn("Base de Landing", wb.sheetnames)
        ws = wb["Base de Landing"]
        self.assertIn("Tabela2", ws.tables)
        tab = ws.tables["Tabela2"]
        self.assertEqual(tab.tableStyleInfo.name, "TableStyleLight2")

    def test_preview_merge_with_blank_unidade_de_medida(self):
        """Testa se a importação com Unidade de Medida em branco é auto-preenchida sem erros."""
        client = app.test_client()
        payload = {
            "mode": "merge",
            "rows": [
                {
                    "Ano": 2026,
                    "Mês": 1,
                    "Grupo de Clientes": "MC DONALDS",
                    "Cod_GR_Cliente": "1",
                    "Diretor": "Ronaldo Pernambuco",
                    "Gerente": "Juliana Kitz",
                    "Canal": "QSR",
                    "Sub_Canal": "Mc Donald's",
                    "Setor": "I",
                    "Categoria": "Buns",
                    "Sub_Categoria": "Buns",
                    "Unidade de Medida": "",  # Em branco!
                    "RECEITA | VOLUME": "Receita",
                    "BGT": 1000,
                    "FCST": 1100,
                    "LANDING": 1050,
                    "COMENTÁRIOS": "Teste automatizado"
                },
                {
                    "Ano": 2026,
                    "Mês": 1,
                    "Grupo de Clientes": "MC DONALDS",
                    "Cod_GR_Cliente": "1",
                    "Diretor": "Ronaldo Pernambuco",
                    "Gerente": "Juliana Kitz",
                    "Canal": "QSR",
                    "Sub_Canal": "Mc Donald's",
                    "Setor": "I",
                    "Categoria": "No Buns",
                    "Sub_Categoria": "Tortas",
                    "Unidade de Medida": None,  # None!
                    "RECEITA | VOLUME": "Receita",
                    "BGT": 500,
                    "FCST": 550,
                    "LANDING": 520,
                    "COMENTÁRIOS": "Teste tortas"
                }
            ]
        }
        resp = client.post("/api/lookups/base_landing/preview_merge", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("stats", data)

    def test_cookies_unidade_de_medida_and_no_duplication(self):
        """Valida que cookies é sempre Unidades e que alterar unidade não duplica linhas no merge."""
        from app import _infer_unidade_de_medida, _smart_merge_rows, LOOKUP_CONFIG

        # 1. Inferência sempre retorna Unidades para Cookies, inclusive Paraguai/Exportação
        r_cookies_paraguai = {
            "Categoria": "No Buns",
            "Sub_Categoria": "Cookies",
            "Grupo de Clientes": "PARAGUAI",
            "Sub_Canal": "Exportação"
        }
        self.assertEqual(_infer_unidade_de_medida(r_cookies_paraguai), "Unidades")

        # 2. Mesclagem inteligente com troca de unidade de Caixas para Unidades atualiza em vez de duplicar
        cfg = LOOKUP_CONFIG["base_landing"]
        col_defs = cfg["columns"]
        composite_keys = cfg["composite_keys"]

        current_rows = [
            {
                "ano": "2026", "mes": "10", "grupo_de_clientes": "PARAGUAI", "cod_gr_cliente": "1",
                "diretor": "Thais Gnoatto", "gerente": "-", "canal": "QSR", "sub_canal": "Exportação",
                "setor": "II", "categoria": "No Buns", "sub_categoria": "Cookies",
                "unidade_de_medida": "Caixas", "receita_volume": "Volume",
                "bgt": 30000, "fcst": 0, "landing": 0, "dif_bgt": -30000, "dif_fcst": 0,
                "realizado": "-", "comentarios": "Embarque antecipado"
            }
        ]

        imported_rows = [
            {
                "ano": "2026", "mes": "10", "grupo_de_clientes": "PARAGUAI", "cod_gr_cliente": "1",
                "diretor": "Thais Gnoatto", "gerente": "-", "canal": "QSR", "sub_canal": "Exportação",
                "setor": "II", "categoria": "No Buns", "sub_categoria": "Cookies",
                "unidade_de_medida": "Unidades", "receita_volume": "Volume",
                "bgt": 30000, "fcst": 0, "landing": 0, "dif_bgt": -30000, "dif_fcst": 0,
                "realizado": "-", "comentarios": "Embarque antecipado"
            }
        ]

        merged, stats = _smart_merge_rows(current_rows, imported_rows, composite_keys, col_defs, mode="merge")
        self.assertEqual(len(merged), 1, "A linha com Cookies não deve ser duplicada ao trocar a unidade!")
        self.assertEqual(stats["atualizados"], 1)
        self.assertEqual(stats["novos"], 0)
        self.assertEqual(merged[0]["unidade_de_medida"], "Unidades")

        # 3. Se a base já tiver duplicatas (uma Caixas e uma Unidades), consolida em apenas uma com Unidades
        base_with_duplicates = [
            dict(current_rows[0], unidade_de_medida="Caixas"),
            dict(current_rows[0], unidade_de_medida="Unidades")
        ]
        consolidated, dup_stats = _smart_merge_rows(base_with_duplicates, [], composite_keys, col_defs, mode="merge")
        self.assertEqual(len(consolidated), 1)
        self.assertEqual(dup_stats["duplicatas_removidas_base"], 1)
        self.assertEqual(consolidated[0]["unidade_de_medida"], "Unidades")

if __name__ == "__main__":
    unittest.main()

