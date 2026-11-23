from playwright.sync_api import sync_playwright
from openpyxl import load_workbook
from pathlib import Path
with sync_playwright() as p:
    browser = p.chromium.launch()
    for width in (390,1440):
        page = browser.new_page(viewport={'width':width,'height':850})
        loaded=[]
        page.on('request',lambda request: loaded.append(request.url))
        page.goto('http://127.0.0.1:8002/performance.html',wait_until='networkidle',timeout=45000)
        page.wait_for_function("document.querySelector('#vSpend').textContent.trim() !== '--'")
        assert not any('xlsx.bundle' in url for url in loaded), 'XLSX carregado antes do clique'
        page.locator('#btnExportAlerts').scroll_into_view_if_needed()
        with page.expect_download(timeout=30000) as info: page.locator('#btnExportAlerts').click()
        download=info.value
        target=Path('scratch') / ('qa-alertas-%s.xlsx' % width)
        download.save_as(str(target))
        workbook=load_workbook(target,read_only=True,data_only=True)
        sheet=workbook.active
        assert sheet.max_row > 1 and sheet.max_column >= 7
        assert any('xlsx.bundle' in url for url in loaded)
        print(f'{width}px: XLSX sob demanda, {sheet.max_row - 1} linhas, {sheet.max_column} colunas; KPI {page.locator("#vSpend").inner_text()}')
        workbook.close()
        target.unlink()
        page.close()
    browser.close()

