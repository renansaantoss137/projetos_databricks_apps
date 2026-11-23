#!/usr/bin/env python3
"""Mede o carregamento de páginas no navegador (Chromium headless via Playwright).

Para cada URL e repetição (cache vazio): tempo até o 1º byte, DOMContentLoaded,
LCP, tempo até o elemento --pronto aparecer (dados na tela), número de
requisições, KB transferidos, tarefas longas de JavaScript, erros de console e
requisições com falha. Lista também as requisições mais lentas.

Requisitos: pip install playwright && python -m playwright install chromium

Exemplos:
  python medir_pagina.py --url http://localhost:8000/vendometro --pronto "#grafico canvas"
  python medir_pagina.py --url http://localhost:8000/ --url http://localhost:8000/report --rede 4g --cpu 4 --largura 390
  python medir_pagina.py --url http://localhost:8000/vendometro --pronto ".kpi-valor" --trace traces/
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REDES = {
    # latência em ms; download/upload em bytes por segundo
    "4g": {"latency": 150, "downloadThroughput": 9 * 1024 * 1024 / 8, "uploadThroughput": 1.5 * 1024 * 1024 / 8},
    "3g": {"latency": 300, "downloadThroughput": 1.6 * 1024 * 1024 / 8, "uploadThroughput": 750 * 1024 / 8},
}

INIT_JS = """
window.__lt = []; window.__lcp = 0;
try { new PerformanceObserver(l => l.getEntries().forEach(e => window.__lt.push(e.duration))).observe({type: 'longtask', buffered: true}); } catch (e) {}
try { new PerformanceObserver(l => l.getEntries().forEach(e => { window.__lcp = e.startTime; })).observe({type: 'largest-contentful-paint', buffered: true}); } catch (e) {}
"""


def mediana(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None


def fmt(v, casas=0):
    return "—" if v is None else f"{v:,.{casas}f}".replace(",", ".")


def medir(browser, url, a, rodada, trace_dir):
    ctx = browser.new_context(viewport={"width": a.largura, "height": a.altura}, device_scale_factor=1,
                              is_mobile=a.largura <= 640, has_touch=a.largura <= 640, ignore_https_errors=True)
    for js in a.init_js:
        ctx.add_init_script(js)
    ctx.add_init_script(INIT_JS)
    if trace_dir:
        ctx.tracing.start(screenshots=True, snapshots=True)
    page = ctx.new_page()
    if a.rede != "nenhuma" or a.cpu > 1:
        cdp = ctx.new_cdp_session(page)
        if a.rede != "nenhuma":
            cdp.send("Network.enable")
            cdp.send("Network.emulateNetworkConditions", {"offline": False, **REDES[a.rede]})
        if a.cpu > 1:
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": a.cpu})

    reqs, erros, falhas, avisos = [], [], [], []
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("requestfailed", lambda r: falhas.append(f"{r.method} {r.url} ({r.failure})"))

    def terminou(r):
        try:
            resp = r.response()
            t = r.timing
            dur = t["responseEnd"] if t and t.get("responseEnd", -1) >= 0 else None   # já é relativo ao início
            tam = r.sizes().get("responseBodySize", 0) + r.sizes().get("responseHeadersSize", 0)
            if resp is not None and resp.status >= 400:
                falhas.append(f"{r.method} {r.url} -> {resp.status}")
            reqs.append({"url": r.url, "tipo": r.resource_type, "ms": dur, "bytes": tam})
        except Exception:
            pass

    page.on("requestfinished", terminou)
    t0 = time.perf_counter()
    page.goto(url, wait_until="domcontentloaded", timeout=a.timeout * 1000)
    pronto_ms = None
    if a.pronto:
        try:
            page.wait_for_selector(a.pronto, state="visible", timeout=a.timeout * 1000)
            # espera o conteúdo real: ignora textos de espera ("—", "--", vazio, "Carregando...")
            page.wait_for_function(
                """(sel) => { const el = document.querySelector(sel); if (!el) return false;
                   if (['CANVAS','IMG','SVG'].includes(el.tagName.toUpperCase())) return true;
                   const t = (el.innerText || '').trim();
                   return t !== '' && !/^(—|–|-|--|\\.\\.\\.|…)$/.test(t) && !/carregando|loading|aguarde/i.test(t); }""",
                arg=a.pronto, timeout=a.timeout * 1000)
            pronto_ms = (time.perf_counter() - t0) * 1000
        except Exception:
            avisos.append(f"--pronto '{a.pronto}' não apareceu em {a.timeout}s")
    try:
        page.wait_for_load_state("networkidle", timeout=a.timeout * 1000)
    except Exception:
        pass
    page.wait_for_timeout(300)
    nav = page.evaluate("""() => { const n = performance.getEntriesByType('navigation')[0] || {};
        return {ttfb: n.responseStart, dcl: n.domContentLoadedEventEnd, load: n.loadEventEnd}; }""")
    lt = page.evaluate("window.__lt || []")
    lcp = page.evaluate("window.__lcp || 0") or None
    largura_ok = page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    if trace_dir:
        Path(trace_dir).mkdir(parents=True, exist_ok=True)
        nome = url.split("//", 1)[-1].replace("/", "_").replace("?", "_").replace(":", "_")
        ctx.tracing.stop(path=str(Path(trace_dir) / f"trace_{nome}_{rodada}.zip"))
    ctx.close()
    return {
        "ttfb": nav.get("ttfb"), "dcl": nav.get("dcl"), "load": nav.get("load"), "lcp": lcp, "pronto": pronto_ms,
        "n_req": len(reqs), "kb": sum(r["bytes"] for r in reqs) / 1024, "lt_n": sum(1 for d in lt if d > 50),
        "lt_max": max(lt) if lt else 0, "erros": erros, "falhas": falhas, "avisos": avisos, "reqs": reqs, "overflow": not largura_ok,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", action="append", required=True, help="página a medir (repita para várias)")
    ap.add_argument("--pronto", help="seletor que só aparece quando os dados chegaram (ex.: '#grafico canvas')")
    ap.add_argument("--repeticoes", type=int, default=3, help="medições por URL, cada uma com cache vazio (padrão 3)")
    ap.add_argument("--rede", choices=["nenhuma", "4g", "3g"], default="nenhuma", help="simular rede lenta")
    ap.add_argument("--cpu", type=float, default=1, help="desacelerar a CPU (ex.: 4 = 4x mais lenta, para simular celular)")
    ap.add_argument("--largura", type=int, default=1440, help="largura da janela em px (390 para celular)")
    ap.add_argument("--altura", type=int, default=900, help="altura da janela em px")
    ap.add_argument("--init-js", action="append", default=[], help="JS executado antes da página (ex.: definir tema ou token de teste)")
    ap.add_argument("--timeout", type=int, default=60, help="tempo máximo de espera, em segundos")
    ap.add_argument("--trace", help="pasta para salvar o trace do Playwright (abrir com: playwright show-trace arquivo.zip)")
    ap.add_argument("--meta-pronto", type=float, default=2000, help="meta de tempo até os dados, em ms (padrão 2000)")
    ap.add_argument("--saida", help="salva o relatório em Markdown neste arquivo")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright

    cond = f"largura {a.largura}px · rede {a.rede} · CPU {a.cpu:g}x · {a.repeticoes} repetições com cache vazio"
    linhas, lentas, avisos = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for url in a.url:
            rs = [medir(browser, url, a, i, a.trace) for i in range(a.repeticoes)]
            m = {k: mediana([r[k] for r in rs]) for k in ("ttfb", "dcl", "lcp", "pronto", "n_req", "kb", "lt_n", "lt_max")}
            erros = sorted({e for r in rs for e in r["erros"]})
            falhas = sorted({f for r in rs for f in r["falhas"]})
            avs = sorted({x for r in rs for x in r["avisos"]})
            obs = []
            if a.pronto and m["pronto"] is not None and m["pronto"] > a.meta_pronto:
                obs.append(f"dados acima de {a.meta_pronto:.0f} ms")
            if m["lt_max"] and m["lt_max"] > 200:
                obs.append(f"tarefa longa de {m['lt_max']:.0f} ms")
            if avs:
                obs.append("dados não apareceram (--pronto)")
            if erros:
                obs.append(f"{len(erros)} erro(s) de console")
            if falhas:
                obs.append(f"{len(falhas)} requisição(ões) com falha")
            if any(r["overflow"] for r in rs):
                obs.append("rolagem horizontal na página")
            linhas.append(f"| {url} | {fmt(m['ttfb'])} | {fmt(m['dcl'])} | {fmt(m['lcp'])} | {fmt(m['pronto']) if a.pronto else 'n/d'} | "
                          f"{fmt(m['n_req'])} | {fmt(m['kb'], 1)} | {fmt(m['lt_n'])} / {fmt(m['lt_max'])} | {'; '.join(obs) or 'OK'} |")
            ult = sorted([r for r in rs[-1]["reqs"] if r["ms"] is not None], key=lambda r: -r["ms"])[:6]
            lentas.append(f"**{url}**")
            lentas += [f"- {r['ms']:.0f} ms · {r['bytes'] / 1024:.1f} KB · {r['tipo']} · {r['url']}" for r in ult]
            lentas.append("")
            for x in avs:
                avisos.append(f"- {url} · {x}")
            for e in erros:
                avisos.append(f"- {url} · console: {e[:300]}")
            for f in falhas:
                avisos.append(f"- {url} · falha: {f[:300]}")
        browser.close()

    rel = [
        "# Medição de páginas", "", f"Condições: {cond} · {time.strftime('%Y-%m-%d %H:%M')}", "",
        "Valores em ms (mediana das repetições). 'Dados na tela' = tempo até o seletor --pronto ficar visível.", "",
        "| URL | 1º byte | DOM pronto | LCP | Dados na tela | Requisições | KB | Tarefas longas (qtd / maior ms) | Observação |",
        "|---|---|---|---|---|---|---|---|---|", *linhas, "",
        "## Requisições mais lentas (última repetição)", "", *lentas,
        "## Erros e falhas", "", *(avisos or ["Nenhum."]),
    ]
    if not a.pronto:
        rel += ["", "Aviso: sem --pronto, o tempo até os dados aparecerem não foi medido."]
    if a.rede != "nenhuma":
        rel += ["", "Com rede simulada, a coluna '1º byte' do navegador não inclui a latência simulada; compare 'DOM pronto' e 'Dados na tela'."]
    texto = "\n".join(rel)
    print(texto)
    if a.saida:
        Path(a.saida).write_text(texto + "\n", encoding="utf-8")
        print(f"\nRelatório salvo em {a.saida}")


if __name__ == "__main__":
    main()
