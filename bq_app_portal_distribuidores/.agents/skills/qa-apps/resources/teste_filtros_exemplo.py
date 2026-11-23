"""Modelo de teste funcional de filtro com Playwright + pytest.

Instalação:  pip install pytest pytest-playwright && python -m playwright install chromium
Execução:    pytest resources/teste_filtros_exemplo.py --base-url http://localhost:8000
             (adicione --headed para ver o navegador)

Troque os seletores e rotas marcados com AJUSTE pelos do seu app. Cada teste
precisa provar algo observável: a requisição saiu com o parâmetro certo, o
número da tela mudou de acordo, o estado voltou ao padrão.
"""
import re
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, expect

ROTA = "/vendometro"                    # AJUSTE
API_KPIS = "/api/kpis"                  # AJUSTE: endpoint chamado ao aplicar filtros
KPI = "#kpi-sellin .valor"              # AJUSTE: um número que muda com o filtro
CANAL_SECAO = "[data-filtro=canal]"     # AJUSTE
APLICAR = "#fpAplicar"                  # AJUSTE
LIMPAR = "#fpLimpar"                    # AJUSTE
CHIPS = "#fpChips .chip"                # AJUSTE


def params(url):
    return {k: v for k, v in parse_qs(urlparse(url).query).items()}


def test_filtro_canal_envia_parametro_e_muda_valor(page: Page):
    page.goto(ROTA)
    expect(page.locator(KPI)).not_to_have_text(re.compile(r"^\s*(--|—)?\s*$"))
    valor_inicial = page.locator(KPI).inner_text()

    page.click(f"{CANAL_SECAO} summary")
    page.click(f"{CANAL_SECAO} li:has-text('QSR') .fp-somente")
    with page.expect_response(lambda r: API_KPIS in r.url) as resp:
        page.click(APLICAR)
    p = params(resp.value.url)
    assert "QSR" in ",".join(p.get("canal", [])), f"parâmetro canal não enviado: {resp.value.url}"
    assert resp.value.ok, f"API respondeu {resp.value.status}"

    expect(page.locator(KPI)).not_to_have_text(valor_inicial)          # o número mudou
    expect(page.locator(CHIPS)).to_contain_text(["Canal: QSR"])        # o filtro aplicado aparece


def test_limpar_volta_ao_padrao(page: Page):
    page.goto(ROTA)
    valor_inicial = page.locator(KPI).inner_text()
    page.click(f"{CANAL_SECAO} summary")
    page.click(f"{CANAL_SECAO} li:has-text('QSR') .fp-somente")
    page.click(APLICAR)
    expect(page.locator(KPI)).not_to_have_text(valor_inicial)

    page.click(LIMPAR)
    expect(page.locator(KPI)).to_have_text(valor_inicial)              # volta ao número original
    expect(page.locator(CHIPS)).to_have_count(0)


def test_sem_erros_de_console_ao_filtrar(page: Page):
    erros = []
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.goto(ROTA)
    page.click(f"{CANAL_SECAO} summary")
    page.click(f"{CANAL_SECAO} li:has-text('QSR') .fp-somente")
    page.click(APLICAR)
    page.wait_for_load_state("networkidle")
    assert not erros, f"erros no console: {erros}"
