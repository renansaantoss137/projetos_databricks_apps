#!/usr/bin/env python3
"""Confere valores entre tela, resposta da API recebida pela página, API direta e banco.

Lê um JSON de cenários (modelo em resources/conferencia.exemplo.json). Para cada
cenário: abre a página, executa as ações (clicar, selecionar filtro...), lê os
textos da tela (pt-BR: "R$ 8,6 mi", "1.709", "93,4%", "−R$ 9,0 mi", "—"),
captura o JSON que a página recebeu, chama a API direta e roda o SQL de
referência. Compara tudo com tolerância coerente com o arredondamento exibido.
Também aplica regras de consistência: soma, razão e igualdade.
Sai com código 1 se alguma checagem falhar.

Banco: Databricks SQL (pip install databricks-sql-connector; variáveis
DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN) ou SQLite
local ("sql": {"tipo": "sqlite", "arquivo": "dados.db"}).

Requisitos: pip install playwright && python -m playwright install chromium

Exemplos:
  python conferir_valores.py --config conferencia.json
  python conferir_valores.py --config conferencia.json --cenario "Vendômetro" --saida conferencia.md
  python conferir_valores.py --testar-leitura "R$ 8,6 mi"
"""
import argparse
import json
import math
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MULT = {"mil": 1e3, "k": 1e3, "mi": 1e6, "milhão": 1e6, "milhao": 1e6, "milhões": 1e6, "milhoes": 1e6, "mm": 1e6, "m": 1e6,
        "bi": 1e9, "bilhão": 1e9, "bilhao": 1e9, "bilhões": 1e9, "bilhoes": 1e9, "b": 1e9}
NUMERO = re.compile(
    r"(?P<sinal>[-+])?\s*(?:R\$|US\$|\$|€)?\s*(?P<sinal2>[-+])?\s*(?P<num>\d[\d.\s]*(?:,\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?P<mult>mil|milh[õo]es|milh[ãa]o|mi|bilh[õo]es|bilh[ãa]o|bi|mm|k|m|b)?(?![a-zà-ú])\s*(?P<pct>%|p\.?\s?p\.?)?",
    re.IGNORECASE)
SEM_DADO = {"", "—", "–", "-", "n/d", "n/a", "sem dados", "sem dado"}


def ler_numero(texto, indice=0):
    """Converte texto exibido em número. Retorna dict(valor, passo, pct) ou None (sem dado)."""
    if texto is None:
        return None
    t = str(texto).replace(" ", " ").replace(" ", " ").replace("−", "-").replace("–", "-").strip()
    if t.lower() in SEM_DADO:
        return None
    achados = [m for m in NUMERO.finditer(t) if m.group("num").strip()]
    if not achados or indice >= len(achados):
        raise ValueError(f"nenhum número na posição {indice} em {texto!r}")
    m = achados[indice]
    num = re.sub(r"\s", "", m.group("num"))
    if "," in num:                                   # padrão brasileiro: 1.234,56
        inteiro, dec = num.replace(".", "").split(",", 1)
    elif num.count(".") == 1 and len(num.split(".")[1]) != 3:   # decimal com ponto: 198.7 (formato EN)
        inteiro, dec = num.split(".")
    else:                                            # milhar com ponto: 1.709 / 12.345.678
        inteiro, dec = num.replace(".", ""), ""
    valor = float(f"{inteiro}.{dec}" if dec else inteiro)
    mult = MULT.get((m.group("mult") or "").lower(), 1.0)
    passo = (10 ** -len(dec)) * mult
    valor *= mult
    if m.group("sinal") == "-" or m.group("sinal2") == "-":
        valor = -valor
    return {"valor": valor, "passo": passo, "pct": bool(m.group("pct"))}


def pegar_campo(dado, caminho):
    """'kpis.sellin.realizado', 'meses[3].valor', 'meses[mes=10].valor', 'linhas[0][2]'"""
    atual = dado
    for parte in re.findall(r"[^.\[\]]+|\[[^\]]*\]", caminho):
        if parte.startswith("["):
            dentro = parte[1:-1]
            if "=" in dentro:
                k, v = dentro.split("=", 1)
                atual = next((x for x in atual if str(x.get(k.strip())) == v.strip().strip("'\"")), None)
            else:
                atual = atual[int(dentro)]
        else:
            atual = atual[parte] if isinstance(atual, dict) else None
        if atual is None:
            return None
    return atual


def como_numero(v, escala=1.0):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        if v.lower() in SEM_DADO:
            return None
        try:
            v = float(v)
        except ValueError:
            return ler_numero(v)["valor"] * escala
    return float(v) * escala


class Banco:
    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.con = None
        self.erro = None

    def consultar(self, sql):
        if self.erro:
            raise RuntimeError(self.erro)
        if self.con is None:
            tipo = self.cfg.get("tipo", "databricks")
            try:
                if tipo == "sqlite":
                    import sqlite3
                    self.con = sqlite3.connect(self.cfg["arquivo"])
                else:
                    host, path, token = (os.environ.get(k) for k in ("DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN"))
                    if not (host and path and token):
                        raise RuntimeError("defina DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH e DATABRICKS_TOKEN")
                    from databricks import sql as dbsql
                    self.con = dbsql.connect(server_hostname=host, http_path=path, access_token=token)
            except Exception as e:
                self.erro = f"banco indisponível: {e}"
                raise RuntimeError(self.erro)
        cur = self.con.cursor()
        try:
            cur.execute(sql)
            linha = cur.fetchone()
        finally:
            cur.close()
        return None if linha is None else linha[0]


def get_json(url, headers, timeout):
    req = urllib.request.Request(url, headers={"Accept": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def br(v):
    if v is None:
        return "—"
    if isinstance(v, str):
        return v
    s = f"{v:,.4f}".rstrip("0").rstrip(".")
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def tol_rel(a, b, rel=1e-6, abs_=0.0):
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b), 1e-12))


def executar_acoes(page, acoes, timeout):
    for ac in acoes or []:
        if "clicar" in ac:
            page.click(ac["clicar"], timeout=timeout)
        elif "selecionar" in ac:
            sel, val = ac["selecionar"]
            page.select_option(sel, val, timeout=timeout)
        elif "preencher" in ac:
            sel, val = ac["preencher"]
            page.fill(sel, val, timeout=timeout)
        elif "marcar" in ac:
            page.check(ac["marcar"], timeout=timeout)
        elif "esperar" in ac:
            page.wait_for_selector(ac["esperar"], state="visible", timeout=timeout)
        elif "esperar_ms" in ac:
            page.wait_for_timeout(ac["esperar_ms"])
        elif "esperar_rede" in ac:
            try:
                page.wait_for_load_state("networkidle", timeout=timeout)
            except Exception:
                pass
        elif "js" in ac:
            page.evaluate(ac["js"])
        else:
            raise ValueError(f"ação desconhecida: {ac}")


def ler_tela(page, seletor, indice_numero=0):
    loc = page.locator(seletor)
    if loc.count() == 0:
        raise RuntimeError(f"seletor não encontrado: {seletor}")
    texto = loc.first.inner_text().strip()
    return texto, ler_numero(texto, indice_numero)


def conferir_cenario(page, cen, cfg, banco, a):
    resultados = []
    respostas = []

    def guardar(resp):
        try:
            if "json" in (resp.headers.get("content-type") or ""):
                respostas.append((resp.url, resp.json()))
        except Exception:
            pass

    page.on("response", guardar)
    base = cfg["base"].rstrip("/")
    timeout = a.timeout * 1000
    page.goto(base + cen["url"], wait_until="domcontentloaded", timeout=timeout)
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    executar_acoes(page, cen.get("acoes"), timeout)
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    page.wait_for_timeout(cen.get("pausa_ms", 300))
    headers = cfg.get("headers", {})

    for ch in cen.get("checagens", []):
        nome = ch.get("nome", "(sem nome)")
        linha = {"cenario": cen["nome"], "nome": nome, "tela": None, "resposta": None, "api": None, "sql": None,
                 "tol": "", "status": "OK", "detalhe": []}
        try:
            regra = ch.get("regra")
            if regra:
                aplicar_regra(page, ch, linha)
            else:
                fontes = {}
                passo_tela = None
                if "tela" in ch:
                    texto, lido = ler_tela(page, ch["tela"], ch.get("indice_numero", 0))
                    linha["tela"] = texto
                    fontes["tela"] = None if lido is None else lido["valor"]
                    passo_tela = None if lido is None else lido["passo"]
                esc = ch.get("escala", 1.0)
                if "resposta" in ch:
                    r = ch["resposta"]
                    cand = [j for (u, j) in respostas if r["url_contem"] in u]
                    if not cand:
                        raise RuntimeError(f"a página não recebeu resposta com '{r['url_contem']}'")
                    v = como_numero(pegar_campo(cand[-1], r["campo"]), ch.get("escala_resposta", esc))
                    fontes["resposta"], linha["resposta"] = v, v
                if "api" in ch:
                    r = ch["api"]
                    j = get_json(base + r["url"], headers, a.timeout)
                    v = como_numero(pegar_campo(j, r["campo"]), ch.get("escala_api", esc))
                    fontes["api"], linha["api"] = v, v
                if "sql" in ch:
                    if a.sem_sql:
                        linha["detalhe"].append("SQL não executado (--sem-sql)")
                    else:
                        try:
                            v = como_numero(banco.consultar(ch["sql"]), ch.get("escala_sql", esc))
                            fontes["sql"], linha["sql"] = v, v
                        except RuntimeError as e:
                            linha["detalhe"].append(f"SQL não executado: {e}")
                comparar(fontes, passo_tela, ch, linha)
        except Exception as e:
            linha["status"] = "ERRO"
            linha["detalhe"].append(f"{type(e).__name__}: {e}")
        resultados.append(linha)
    page.remove_listener("response", guardar)
    return resultados


def comparar(fontes, passo_tela, ch, linha):
    tol = ch.get("tolerancia", "formato")
    tol_abs = float(ch.get("tolerancia_abs", 0))
    nomes = list(fontes)
    if len(nomes) < 2:
        linha["status"] = "NÃO CONFERIDO"
        linha["detalhe"].append("só uma fonte disponível")
        return
    if tol == "formato" and passo_tela is not None:
        linha["tol"] = f"±{br(passo_tela / 2)} (arredondamento da tela)"
    elif isinstance(tol, (int, float)):
        linha["tol"] = f"±{br(tol)}"
    elif isinstance(tol, str) and tol.endswith("%"):
        linha["tol"] = f"±{tol}"
    for i in range(len(nomes)):
        for j in range(i + 1, len(nomes)):
            x, y = nomes[i], nomes[j]
            a, b = fontes[x], fontes[y]
            if a is None and b is None:
                continue
            if a is None or b is None:
                linha["status"] = "FALHA"
                linha["detalhe"].append(f"{x}={br(a)} × {y}={br(b)}: um lado sem valor")
                continue
            if isinstance(tol, (int, float)):
                ok = abs(a - b) <= tol
            elif isinstance(tol, str) and tol.endswith("%"):
                ok = tol_rel(a, b, float(tol[:-1].replace(",", ".")) / 100)
            elif "tela" in (x, y) and passo_tela is not None:
                ok = abs(a - b) <= passo_tela / 2 + 1e-9 * max(abs(a), abs(b), 1) + tol_abs
            else:
                ok = tol_rel(a, b, 1e-6, tol_abs)
            if not ok:
                linha["status"] = "FALHA"
                linha["detalhe"].append(f"{x}={br(a)} × {y}={br(b)} (diferença {br(a - b)})")


def aplicar_regra(page, ch, linha):
    regra = ch["regra"]
    if regra == "soma":
        partes = [ler_tela(page, s)[1] for s in ch["partes"]]
        txt_total, total = ler_tela(page, ch["total"])
        if total is None or any(p is None for p in partes):
            raise RuntimeError("parte ou total sem valor")
        soma = sum(p["valor"] for p in partes)
        tol = sum(p["passo"] for p in partes) / 2 + total["passo"] / 2
        linha["tela"] = f"soma {br(soma)} × total {txt_total}"
        linha["tol"] = f"±{br(tol)}"
        if abs(soma - total["valor"]) > tol + 1e-9:
            linha["status"] = "FALHA"
            linha["detalhe"].append(f"partes somam {br(soma)}, total exibido {br(total['valor'])}")
    elif regra == "razao":
        n, d = ler_tela(page, ch["numerador"])[1], ler_tela(page, ch["denominador"])[1]
        txt_p, pct = ler_tela(page, ch["percentual"], ch.get("indice_numero", 0))
        if None in (n, d, pct) or d["valor"] == 0:
            raise RuntimeError("numerador, denominador ou percentual sem valor (ou denominador zero)")
        calc = n["valor"] / d["valor"] * 100
        tol = pct["passo"] / 2 + 100 * (n["passo"] / 2 / abs(d["valor"]) + abs(n["valor"]) * d["passo"] / 2 / d["valor"] ** 2)
        linha["tela"] = f"{txt_p} × calculado {br(round(calc, 4))}%"
        linha["tol"] = f"±{br(round(tol, 4))} p.p."
        if abs(calc - pct["valor"]) > tol + 1e-9:
            linha["status"] = "FALHA"
            linha["detalhe"].append(f"exibido {br(pct['valor'])}%, calculado {br(round(calc, 4))}%")
    elif regra == "igual":
        ta, va = ler_tela(page, ch["a"], ch.get("indice_numero_a", 0))
        tb, vb = ler_tela(page, ch["b"], ch.get("indice_numero_b", 0))
        linha["tela"] = f"{ta} × {tb}"
        if va is None or vb is None:
            if not (va is None and vb is None):
                linha["status"] = "FALHA"
                linha["detalhe"].append("um lado sem valor")
            return
        tol = (va["passo"] + vb["passo"]) / 2
        linha["tol"] = f"±{br(tol)}"
        if abs(va["valor"] - vb["valor"]) > tol + 1e-9:
            linha["status"] = "FALHA"
            linha["detalhe"].append(f"{br(va['valor'])} × {br(vb['valor'])}")
    else:
        raise ValueError(f"regra desconhecida: {regra}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="JSON de cenários (modelo: resources/conferencia.exemplo.json)")
    ap.add_argument("--cenario", action="append", default=[], help="roda só cenários cujo nome contém este texto (repita)")
    ap.add_argument("--sem-sql", action="store_true", help="não consulta o banco (só tela × resposta × API)")
    ap.add_argument("--timeout", type=int, default=60, help="tempo máximo por espera, em segundos")
    ap.add_argument("--testar-leitura", help="só mostra como um texto da tela é convertido (ex.: 'R$ 8,6 mi') e sai")
    ap.add_argument("--saida", help="salva o relatório em Markdown")
    a = ap.parse_args()

    if a.testar_leitura is not None:
        print(json.dumps(ler_numero(a.testar_leitura), ensure_ascii=False))
        return
    if not a.config:
        ap.error("informe --config")
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    cenarios = [c for c in cfg["cenarios"] if not a.cenario or any(f.lower() in c["nome"].lower() for f in a.cenario)]
    banco = Banco(cfg.get("sql"))

    from playwright.sync_api import sync_playwright

    todos = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": cfg.get("largura", 1440), "height": 900}, accept_downloads=True,
                                  extra_http_headers=cfg.get("headers_navegador", {}))
        for js in cfg.get("init_js", []):
            ctx.add_init_script(js)
        for cen in cenarios:
            page = ctx.new_page()
            try:
                todos += conferir_cenario(page, cen, cfg, banco, a)
            except Exception as e:
                todos.append({"cenario": cen["nome"], "nome": "(abrir cenário)", "tela": None, "resposta": None, "api": None,
                              "sql": None, "tol": "", "status": "ERRO", "detalhe": [f"{type(e).__name__}: {e}"]})
            page.close()
        browser.close()

    cont = {}
    for r in todos:
        cont[r["status"]] = cont.get(r["status"], 0) + 1
    rel = ["# Conferência de valores", "", f"{time.strftime('%Y-%m-%d %H:%M')} · base {cfg['base']} · " +
           " · ".join(f"{k}: {v}" for k, v in sorted(cont.items())), "",
           "| Cenário | Checagem | Tela | Resposta | API | SQL | Tolerância | Resultado | Detalhe |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in todos:
        cel = lambda v: br(v).replace("|", "/") if not isinstance(v, str) else v.replace("|", "/").replace("\n", " ")
        rel.append(f"| {r['cenario']} | {r['nome']} | {cel(r['tela'])} | {cel(r['resposta'])} | {cel(r['api'])} | {cel(r['sql'])} | "
                   f"{r['tol'] or '—'} | {r['status']} | {'; '.join(r['detalhe']).replace('|', '/') or '—'} |")
    rel += ["", "Legenda: OK = todas as fontes batem dentro da tolerância · FALHA = divergência real · "
                "ERRO = não foi possível ler (seletor, rede, campo) · NÃO CONFERIDO = só uma fonte."]
    texto = "\n".join(rel)
    print(texto)
    if a.saida:
        Path(a.saida).write_text(texto + "\n", encoding="utf-8")
        print(f"\nRelatório salvo em {a.saida}")
    sys.exit(1 if any(r["status"] in ("FALHA", "ERRO") for r in todos) else 0)


if __name__ == "__main__":
    main()
