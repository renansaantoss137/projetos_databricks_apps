from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 for w in (390,1440):
  page=b.new_page(viewport={'width':w,'height':844})
  for route in ('performance','ordens','comercial','governanca','relatorios'):
   page.goto('http://127.0.0.1:8002/'+route+'.html',wait_until='domcontentloaded',timeout=30000)
   try:
    page.locator('#daAppMenuTrigger').click(timeout=5000)
    print(w,route,'menu',page.locator('#daAppMenuPanel').get_attribute('class'))
    page.locator('#daThemeSystem').click(timeout=5000)
    print(w,route,'tema sistema',page.locator('#daThemeSystem').get_attribute('aria-pressed'))
   except Exception as e: print(w,route,'FALHA',str(e)[:200])
  page.close()
 b.close()
