import unittest
import os

class TestPerformanceHtml(unittest.TestCase):
    def setUp(self):
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "app", "performance.html"))
        with open(path, "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_headers_and_shortened_labels(self):
        """Verifica se os cabeçalhos foram encurtados para otimizar espaço."""
        self.assertIn("DT <span", self.content)
        self.assertIn("GRP CLIENTE <span", self.content)
        self.assertIn("SUB CAT <span", self.content)
        self.assertIn('<span id="thColBase">BGT</span>', self.content)
        self.assertIn('<span id="thColVar">Δ BGT</span>', self.content)
        self.assertIn('thColBase.textContent = "BGT"', self.content)
        self.assertIn('thColVar.textContent = "Δ BGT"', self.content)
        self.assertIn('thColBase.textContent = "FCST"', self.content)
        self.assertIn('thColVar.textContent = "Δ FCST"', self.content)

    def test_default_sorting_by_comentario_desc(self):
        """Verifica se a ordenação nativa padrão é pela coluna Comentários decrescente."""
        self.assertIn('let colunaOrdenada = "comentario";', self.content)
        self.assertIn('let direcaoOrdenacao = "desc";', self.content)
        self.assertIn('class="comments-col sorted-desc"', self.content)

    def test_comment_column_width(self):
        """Verifica se a coluna de comentários teve a largura expandida no CSS."""
        self.assertIn('min-width: 240px;', self.content)

    def test_volume_unit_abbreviations(self):
        """Verifica se a função de abreviação e as siglas Cx, Un e Dz estão implementadas."""
        self.assertIn('function abreviarUnidade(um)', self.content)
        self.assertIn('"Cx"', self.content)
        self.assertIn('"Un"', self.content)
        self.assertIn('"Dz"', self.content)
        self.assertIn('Volume (Cx / Un / Dz)', self.content)
        self.assertIn('const um = abreviarUnidade(umBruta);', self.content)

    def test_setor_column_position_after_dt(self):
        """Verifica se a coluna SETOR está posicionada logo após a coluna DT no cabeçalho e linhas."""
        # No thead
        dt_pos = self.content.find('data-col="data"')
        setor_pos = self.content.find('data-col="setor"')
        sub_canal_pos = self.content.find('data-col="sub_canal"')
        self.assertTrue(dt_pos != -1 and setor_pos != -1 and sub_canal_pos != -1)
        self.assertTrue(dt_pos < setor_pos < sub_canal_pos)

        # No render do tbody
        td_dt_str = "${dataFmt}</td>"
        td_setor_str = "${row.setor || '-'}</td>"
        td_sub_canal_str = "${row.sub_canal || row.cliente || '-'}</td>"
        pos_td_dt = self.content.find(td_dt_str)
        pos_td_setor = self.content.find(td_setor_str)
        pos_td_sub_canal = self.content.find(td_sub_canal_str)
        self.assertTrue(pos_td_dt != -1 and pos_td_setor != -1 and pos_td_sub_canal != -1)
        self.assertTrue(pos_td_dt < pos_td_setor < pos_td_sub_canal)

if __name__ == "__main__":
    unittest.main()

