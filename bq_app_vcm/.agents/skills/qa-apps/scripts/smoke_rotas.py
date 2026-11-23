#!/usr/bin/env python3
"""Teste de fumaça: abre cada tela em cada largura e procura sinais de quebra.

Verifica erros de console e de JavaScript, requisições 4xx/5xx ou com falha,
rolagem horizontal e texto quebrado na tela (NaN, undefined, null, Infinity,
[object Object], {{ }} sem preencher). Salva uma captura de cada tela.
Sai com código 1 se encontrar falha (útil em CI).

Requisitos: pip install playwright && python -m playwright install chromium

Exemplos:
  python smoke_rotas.py --base http://localhost:8000 --rota / --rota /vendometro --rota /report
  python smoke_rotas.py --base http://localhost:8000 --rota /vendometro --larguras 390,768,1440 --capturas capturas/ --saida smoke.md
  python smoke_rotas.py --base http://localhost:8000 --rota / --init-js "localStorage.setItem('theme','dark')"
"""
import argparse
import re
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TEXTO_QUEBRADO = re.compile(r"\bNaN\b|\bundefined\b|\bInfinity\b|\[object Object\]|\{\{|\}\}|(?<![\w-])null(?![\w-])")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="endereço do app, ex.: http://localhost:8000")
    ap.add_argument("--rota", action="append", required=True, help="rota a abrir (repita para várias)")
    ap.add_argument("--larguras", default="390,1440", help="larguras separadas por vírgula (padrão 390,1440)")
    ap.add_argument("--esperar", help="seletor a aguardar em todas as telas (ex.: elemento preenchido com dados)")
    ap.add_argument("--init-js", action="append", default=[], help="JS executado antes de cada página (tema, token de teste...)")
    ap.add_argument("--ignorar", action="append", default=[], help="trecho de mensagem de console a ignorar (repita)")
    ap.add_argument("--capturas", help="pasta para salvar capturas de tela")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--saida", help="salva o relatório em Markdown")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright

    larguras = [int(x) for x in a.larguras.split(",") if x.strip()]
    if a.capturas:
        Path(a.capturas).mkdir(parents=True, exist_ok=True)
    linhas, detalhes, falhou = [], [], False
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for largura in larguras:
            ctx = browser.new_context(viewport={"width": largura, "height": 900}, is_mobile=largura <= 640, has_touch=largura <= 640)
            for js in a.init_js:
                ctx.add_init_script(js)
            for rota in a.rota:
                url = a.base.rstrip("/") + (rota if rota.startswith("/") else "/" + rota)
                page = ctx.new_page()
                erros, reqs_ruins = [], []
                page.on("console", lambda m, e=erros: e.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda ex, e=erros: e.append(f"JS: {ex}"))
                page.on("requestfailed", lambda r, rr=reqs_ruins: rr.append(f"{r.method} {r.url} ({r.failure})"))
                page.on("response", lambda r, rr=reqs_ruins: rr.append(f"{r.request.method} {r.url} -> {r.status}") if r.status >= 400 else None)
                t0 = time.perf_counter()
                carregou = True
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=a.timeout * 1000)
                    if a.esperar:
                        page.wait_for_selector(a.esperar, timeout=a.timeout * 1000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=a.timeout * 1000)
                    except Exception:
                        pass
                    page.wait_for_timeout(400)
                except Exception as ex:
                    carregou = False
                    erros.append(f"não carregou: {ex}")
                ms = (time.perf_counter() - t0) * 1000
                erros = [e for e in erros if not any(i in e for i in a.ignorar)]
                quebrado, overflow = [], False
                if carregou:
                    texto = page.evaluate("document.body ? document.body.innerText : ''")
                    quebrado = sorted({m.group(0) for m in TEXTO_QUEBRADO.finditer(texto)})
                    contexto = []
                    for m in list(TEXTO_QUEBRADO.finditer(texto))[:8]:
                        trecho = texto[max(0, m.start() - 40):m.end() + 40].replace("\n", " ⏎ ")
                        if trecho not in contexto:
                            contexto.append(trecho)
                    overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
                    if a.capturas:
                        nome = (rota.strip("/") or "home").replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "-")
                        page.screenshot(path=str(Path(a.capturas) / f"{nome}_{largura}.png"), full_page=True)
                page.close()
                probs = []
                if erros:
                    probs.append(f"{len(erros)} erro(s) de console/JS")
                if reqs_ruins:
                    probs.append(f"{len(reqs_ruins)} requisição(ões) com erro")
                if quebrado:
                    probs.append("texto quebrado: " + ", ".join(quebrado))
                if overflow:
                    probs.append("rolagem horizontal")
                falhou |= bool(probs)
                linhas.append(f"| {rota} | {largura} | {'FALHA' if probs else 'OK'} | {ms:.0f} | {'; '.join(probs) or '—'} |")
                if probs:
                    detalhes.append(f"### {rota} · {largura}px")
                    detalhes += [f"- console: {e[:300]}" for e in erros]
                    detalhes += [f"- requisição: {r[:300]}" for r in reqs_ruins]
                    if quebrado:
                        detalhes += [f"- texto: …{c}…" for c in contexto]
                    detalhes.append("")
            ctx.close()
        browser.close()

    rel = ["# Teste de fumaça", "", f"Base: {a.base} · {time.strftime('%Y-%m-%d %H:%M')}", "",
           "| Rota | Largura | Resultado | Tempo (ms) | Problemas |", "|---|---|---|---|---|", *linhas, ""]
    rel += ["## Detalhes", "", *detalhes] if detalhes else ["Nenhum problema encontrado."]
    texto = "\n".join(rel)
    print(texto)
    if a.saida:
        Path(a.saida).write_text(texto + "\n", encoding="utf-8")
        print(f"\nRelatório salvo em {a.saida}")
    sys.exit(1 if falhou else 0)


if __name__ == "__main__":
    main()
