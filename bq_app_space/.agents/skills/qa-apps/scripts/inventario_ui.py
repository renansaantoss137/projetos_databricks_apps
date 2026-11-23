#!/usr/bin/env python3
"""Inventário dos controles interativos de cada página (Playwright).

Lista botões, links, campos, selects, abas, chaves, itens de menu, <summary> e
elementos com onclick, com nome acessível, estado e tamanho. Aponta problemas:
sem nome, div/span clicável, link sem destino, alvo pequeno no celular.

Requisitos: pip install playwright && python -m playwright install chromium

Exemplos:
  python inventario_ui.py --url http://localhost:8000/ --url http://localhost:8000/vendometro --saida inventario.md
  python inventario_ui.py --url http://localhost:8000/vendometro --largura 390 --json inventario.json
"""
import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

COLETA_JS = r"""
(minAlvo) => {
  const sel = 'button, a, input, select, textarea, summary, [role=button], [role=link], [role=tab], [role=switch], [role=checkbox], [role=radio], [role=menuitem], [role=menuitemradio], [role=option], [onclick], [tabindex]:not([tabindex="-1"])';
  const vistos = new Set(); const itens = [];
  const nomeDe = (el) => {
    const lbl = el.getAttribute('aria-label'); if (lbl && lbl.trim()) return lbl.trim();
    const by = el.getAttribute('aria-labelledby');
    if (by) { const t = by.split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim(); if (t) return t; }
    if (el.labels && el.labels.length) { const t = [...el.labels].map(l => l.textContent).join(' ').trim(); if (t) return t; }
    if (['INPUT','TEXTAREA'].includes(el.tagName)) { const t = el.getAttribute('placeholder') || (['button','submit','reset'].includes(el.type) ? el.value : ''); if (t) return t.trim(); }
    const txt = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim(); if (txt) return txt;
    const img = el.querySelector('img[alt]'); if (img && img.alt.trim()) return img.alt.trim();
    const svgT = el.querySelector('svg title'); if (svgT && svgT.textContent.trim()) return svgT.textContent.trim();
    return (el.getAttribute('title') || '').trim();
  };
  const seletor = (el) => {
    if (el.id) return '#' + CSS.escape(el.id);
    const tid = el.getAttribute('data-testid'); if (tid) return `[data-testid="${tid}"]`;
    const partes = []; let e = el;
    while (e && e.nodeType === 1 && partes.length < 4) {
      let p = e.tagName.toLowerCase();
      if (e.id) { partes.unshift('#' + CSS.escape(e.id)); break; }
      const irm = e.parentElement ? [...e.parentElement.children].filter(c => c.tagName === e.tagName) : [];
      if (irm.length > 1) p += `:nth-of-type(${irm.indexOf(e) + 1})`;
      partes.unshift(p); e = e.parentElement;
    }
    return partes.join(' > ');
  };
  for (const el of document.querySelectorAll(sel)) {
    if (vistos.has(el)) continue; vistos.add(el);
    const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    const visivel = r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && !el.closest('[hidden],[aria-hidden="true"]');
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || '';
    const tipo = tag === 'input' ? `input[${el.type}]` : (role ? `${tag}[role=${role}]` : tag);
    const nome = nomeDe(el);
    const problemas = [];
    if (visivel && !nome) problemas.push('sem nome acessível');
    if (['div','span','li','td','img','i','svg'].includes(tag) && !role && (el.hasAttribute('onclick') || el.getAttribute('tabindex') !== null)) problemas.push('elemento não semântico clicável');
    if (tag === 'a' && !el.getAttribute('href') && !role) problemas.push('link sem href');
    if (visivel && minAlvo && (r.width < minAlvo || r.height < minAlvo) && !['input[checkbox]','input[radio]'].includes(tipo)) problemas.push(`alvo ${Math.round(r.width)}x${Math.round(r.height)} < ${minAlvo}px`);
    if (tag === 'a' && el.target === '_blank' && !/noopener|noreferrer/.test(el.rel || '')) problemas.push('target=_blank sem rel=noopener');
    itens.push({
      tipo, nome: nome.slice(0, 80), seletor: seletor(el), visivel,
      desabilitado: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
      destino: tag === 'a' ? (el.getAttribute('href') || '') : '',
      expandido: el.getAttribute('aria-expanded') || '',
      largura: Math.round(r.width), altura: Math.round(r.height), problemas,
    });
  }
  return itens;
}
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", action="append", required=True, help="página a inventariar (repita para várias)")
    ap.add_argument("--largura", type=int, default=1440, help="largura da janela (390 para celular)")
    ap.add_argument("--altura", type=int, default=900)
    ap.add_argument("--esperar", help="seletor a aguardar antes de inventariar (ex.: quando os dados chegam)")
    ap.add_argument("--init-js", action="append", default=[], help="JS executado antes da página (tema, token de teste...)")
    ap.add_argument("--incluir-ocultos", action="store_true", help="lista também os elementos invisíveis (menus fechados etc.)")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--json", help="salva o inventário completo em JSON")
    ap.add_argument("--saida", help="salva o relatório em Markdown")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright

    alvo_min = 44 if a.largura <= 640 else 0
    relatorio = [f"# Inventário de controles (largura {a.largura}px)", ""]
    completo = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": a.largura, "height": a.altura}, is_mobile=a.largura <= 640, has_touch=a.largura <= 640)
        for js in a.init_js:
            ctx.add_init_script(js)
        page = ctx.new_page()
        for url in a.url:
            page.goto(url, wait_until="domcontentloaded", timeout=a.timeout * 1000)
            if a.esperar:
                page.wait_for_selector(a.esperar, timeout=a.timeout * 1000)
            try:
                page.wait_for_load_state("networkidle", timeout=a.timeout * 1000)
            except Exception:
                pass
            itens = page.evaluate(COLETA_JS, alvo_min)
            completo[url] = itens
            mostrar = itens if a.incluir_ocultos else [i for i in itens if i["visivel"]]
            ocultos = len(itens) - len([i for i in itens if i["visivel"]])
            com_prob = [i for i in mostrar if i["problemas"]]
            relatorio += [f"## {url}", "",
                          f"{len(mostrar)} controles visíveis ({ocultos} ocultos) · {len(com_prob)} com problema", "",
                          "| # | Tipo | Nome | Seletor | Estado | Tamanho | Problemas |", "|---|---|---|---|---|---|---|"]
            for n, i in enumerate(mostrar, 1):
                estado = ", ".join(x for x in [("desabilitado" if i["desabilitado"] else ""), (f"expandido={i['expandido']}" if i["expandido"] else ""),
                                               (f"→ {i['destino']}" if i["destino"] else ""), ("" if i["visivel"] else "oculto")] if x) or "—"
                nome = (i["nome"] or "**(sem nome)**").replace("|", "/")
                relatorio.append(f"| {n} | {i['tipo']} | {nome} | `{i['seletor']}` | {estado} | {i['largura']}×{i['altura']} | {'; '.join(i['problemas']) or '—'} |")
            relatorio.append("")
        browser.close()

    total_prob = sum(1 for itens in completo.values() for i in itens if i["problemas"] and (i["visivel"] or a.incluir_ocultos))
    relatorio += ["## Próximo passo", "",
                  "Para cada controle, escreva o resultado esperado (o que muda na tela ou qual requisição sai) e cubra com um teste. "
                  f"Corrija os {total_prob} problema(s) apontados ou justifique."]
    texto = "\n".join(relatorio)
    print(texto)
    if a.json:
        Path(a.json).write_text(json.dumps(completo, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.saida:
        Path(a.saida).write_text(texto + "\n", encoding="utf-8")
        print(f"\nRelatório salvo em {a.saida}")


if __name__ == "__main__":
    main()
