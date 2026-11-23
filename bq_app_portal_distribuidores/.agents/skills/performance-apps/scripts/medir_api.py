#!/usr/bin/env python3
"""Mede o tempo de resposta de rotas de API: 1 chamada a frio e N a quente.

Mostra p50, p95 e máximo, tempo até o primeiro byte, tamanho transferido,
se veio comprimido (gzip/br) e o cabeçalho Server-Timing (tempo por consulta),
quando o backend o envia. Usa só a biblioteca padrão do Python.

Exemplos:
  python medir_api.py --base http://localhost:8000 --rota "/api/kpis?mes=10" --rota /api/vendas -n 10
  python medir_api.py --base http://localhost:8000 --rotas rotas.txt --header "Authorization: Bearer TOKEN" --saida medicao.md
"""
import argparse
import math
import statistics
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def percentil(valores, p):
    if not valores:
        return float("nan")
    ordenados = sorted(valores)
    k = (len(ordenados) - 1) * p / 100
    baixo, alto = math.floor(k), math.ceil(k)
    if baixo == alto:
        return ordenados[int(k)]
    return ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (k - baixo)


def ler_server_timing(cabecalho):
    """'sql_kpis;dur=120.5, total;dur=180' -> {'sql_kpis': 120.5, 'total': 180.0}"""
    tempos = {}
    if not cabecalho:
        return tempos
    for parte in cabecalho.split(","):
        campos = [c.strip() for c in parte.split(";")]
        nome = campos[0]
        for c in campos[1:]:
            if c.startswith("dur="):
                try:
                    tempos[nome] = float(c[4:])
                except ValueError:
                    pass
    return tempos


def chamar(url, headers, timeout):
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip, br", **headers})
    t0 = time.perf_counter()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        status = resp.status
    except urllib.error.HTTPError as e:
        resp, status = e, e.code
    ttfb = (time.perf_counter() - t0) * 1000
    corpo = resp.read()
    total = (time.perf_counter() - t0) * 1000
    return {
        "status": status,
        "ttfb": ttfb,
        "total": total,
        "bytes": len(corpo),
        "encoding": resp.headers.get("Content-Encoding", ""),
        "server_timing": ler_server_timing(resp.headers.get("Server-Timing", "")),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="endereço do app, ex.: http://localhost:8000")
    ap.add_argument("--rota", action="append", default=[], help="rota a medir (repita para várias), ex.: /api/kpis?mes=10")
    ap.add_argument("--rotas", help="arquivo texto com uma rota por linha (linhas com # são ignoradas)")
    ap.add_argument("-n", type=int, default=10, help="chamadas a quente por rota (padrão 10)")
    ap.add_argument("--header", action="append", default=[], help='cabeçalho extra, ex.: "Authorization: Bearer xyz"')
    ap.add_argument("--timeout", type=float, default=120, help="tempo máximo por chamada, em segundos")
    ap.add_argument("--meta-p95", type=float, default=800, help="meta de p95 a quente em ms (padrão 800)")
    ap.add_argument("--meta-kb", type=float, default=300, help="meta de tamanho por resposta em KB (padrão 300)")
    ap.add_argument("--simultaneas", type=int, default=5,
                    help="dispara N chamadas ao mesmo tempo por rota para detectar fila no servidor "
                         "(ex.: endpoint async def com chamada bloqueante). 0 desliga. Padrão 5")
    ap.add_argument("--saida", help="salva o relatório em Markdown neste arquivo")
    a = ap.parse_args()

    rotas = list(a.rota)
    if a.rotas:
        with open(a.rotas, encoding="utf-8") as f:
            rotas += [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    if not rotas:
        ap.error("informe ao menos uma --rota ou --rotas")
    headers = {}
    for h in a.header:
        if ":" not in h:
            ap.error(f"cabeçalho inválido: {h}")
        k, v = h.split(":", 1)
        headers[k.strip()] = v.strip()

    linhas, detalhes, alertas = [], [], []
    for rota in rotas:
        url = a.base.rstrip("/") + (rota if rota.startswith("/") else "/" + rota)
        try:
            frio = chamar(url, headers, a.timeout)
            quentes = [chamar(url, headers, a.timeout) for _ in range(a.n)]
        except Exception as e:
            linhas.append(f"| `{rota}` | ERRO | | | | | | | | {type(e).__name__}: {e} |")
            alertas.append(f"`{rota}`: falhou ({e})")
            continue
        tot = [q["total"] for q in quentes]
        p50, p95, mx = statistics.median(tot), percentil(tot, 95), max(tot)
        ttfb50 = statistics.median(q["ttfb"] for q in quentes)
        kb = quentes[-1]["bytes"] / 1024
        enc = quentes[-1]["encoding"] or "nenhuma"
        status = {q["status"] for q in quentes} | {frio["status"]}
        obs = []
        if any(s >= 400 for s in status):
            obs.append("status de erro")
        if p95 > a.meta_p95:
            obs.append(f"p95 acima de {a.meta_p95:.0f} ms")
        if kb > a.meta_kb:
            obs.append(f"acima de {a.meta_kb:.0f} KB")
        if enc == "nenhuma" and kb > 10:
            obs.append("sem compressão")
        if frio["total"] > 3 * p50 and frio["total"] - p50 > 500:
            obs.append("1ª chamada muito mais lenta (warehouse/conexão fria?)")
        simult_txt = "—"
        if a.simultaneas > 1 and p50 >= 50:
            from concurrent.futures import ThreadPoolExecutor
            t0 = time.perf_counter()
            with ThreadPoolExecutor(max_workers=a.simultaneas) as ex:
                res = list(ex.map(lambda _: chamar(url, headers, a.timeout), range(a.simultaneas)))
            parede = (time.perf_counter() - t0) * 1000
            fator = parede / p50
            simult_txt = f"{a.simultaneas}× em {parede:.0f} ms ({fator:.1f}× o tempo de 1)"
            if fator > max(2.0, a.simultaneas * 0.6):
                obs.append(f"{a.simultaneas} chamadas simultâneas levaram {fator:.1f}× o tempo de uma: o servidor atende em fila "
                           "(async def com chamada bloqueante? poucos workers? conexão única compartilhada?)")
        linhas.append(
            f"| `{rota}` | {','.join(map(str, sorted(status)))} | {frio['total']:.0f} | {p50:.0f} | {p95:.0f} | {mx:.0f} | "
            f"{ttfb50:.0f} | {kb:.1f} ({enc}) | {simult_txt} | {'; '.join(obs) or 'OK'} |"
        )
        if obs:
            alertas.append(f"`{rota}`: {'; '.join(obs)}")
        # Server-Timing: mediana por métrica
        metricas = {}
        for q in quentes:
            for k, v in q["server_timing"].items():
                metricas.setdefault(k, []).append(v)
        if metricas or frio["server_timing"]:
            partes = ", ".join(f"{k} {statistics.median(v):.0f} ms" for k, v in sorted(metricas.items(), key=lambda kv: -statistics.median(kv[1])))
            frio_st = ", ".join(f"{k} {v:.0f} ms" for k, v in frio["server_timing"].items())
            detalhes.append(f"- `{rota}`: a quente (mediana) {partes or '—'}; a frio {frio_st or '—'}")

    rel = [
        f"# Medição de API ({a.n} chamadas a quente por rota)",
        "",
        f"Base: {a.base} · metas: p95 ≤ {a.meta_p95:.0f} ms, ≤ {a.meta_kb:.0f} KB · {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "| Rota | Status | Frio (ms) | p50 (ms) | p95 (ms) | Máx (ms) | 1º byte p50 (ms) | Tamanho (KB) | Simultâneas | Observação |",
        "|---|---|---|---|---|---|---|---|---|---|",
        *linhas,
        "",
    ]
    if detalhes:
        rel += ["## Tempo por etapa no servidor (Server-Timing)", "", *detalhes, ""]
    else:
        rel += ["Sem cabeçalho Server-Timing: instale o middleware de resources/server_timing_fastapi.py para ver o tempo de cada consulta.", ""]
    rel += ["## Alertas", "", *(f"- {x}" for x in alertas)] if alertas else ["Nenhum alerta."]
    texto = "\n".join(rel)
    print(texto)
    if a.saida:
        with open(a.saida, "w", encoding="utf-8") as f:
            f.write(texto + "\n")
        print(f"\nRelatório salvo em {a.saida}")


if __name__ == "__main__":
    main()
