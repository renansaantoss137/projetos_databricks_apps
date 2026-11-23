"""Cronometragem por etapa para FastAPI, devolvida no cabeçalho Server-Timing.

Uso no app:

    from server_timing_fastapi import ServerTimingMiddleware, medir

    app = FastAPI()
    app.add_middleware(ServerTimingMiddleware)

    @app.get("/api/kpis")
    def kpis(mes: int):                      # 'def': o FastAPI roda em thread e não trava o servidor
        with medir("sql_kpis"):
            linhas = executar_sql(...)
        with medir("montar_json"):
            ...
        return resultado

Cada `medir("nome")` vira uma entrada `nome;dur=123.4` no cabeçalho, mais `total`.
O script medir_api.py lê esse cabeçalho. Ele também aparece no DevTools do
navegador (aba Network › Timing). O log registra rota, status e tempos de cada
requisição. Não registra filtros nem dados do usuário.

Pode ficar ligado em produção: o custo é desprezível e o cabeçalho não expõe dados.
Para desligar, remova o add_middleware.
"""
import contextvars
import logging
import time
from contextlib import contextmanager

from starlette.middleware.base import BaseHTTPMiddleware

_etapas = contextvars.ContextVar("server_timing_etapas", default=None)
log = logging.getLogger("server_timing")


class ServerTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        etapas = []
        token = _etapas.set(etapas)
        t0 = time.perf_counter()
        try:
            resposta = await call_next(request)
        finally:
            _etapas.reset(token)
        total = (time.perf_counter() - t0) * 1000
        partes = [f"{nome};dur={dur:.1f}" for nome, dur in etapas] + [f"total;dur={total:.1f}"]
        resposta.headers["Server-Timing"] = ", ".join(partes)
        log.info("%s %s %s %.0fms %s", request.method, request.url.path, resposta.status_code, total,
                 " ".join(f"{n}={d:.0f}ms" for n, d in etapas))
        return resposta


@contextmanager
def medir(nome):
    """Cronometra um trecho e registra no Server-Timing da requisição atual."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        etapas = _etapas.get()
        if etapas is not None:
            seguro = "".join(c if c.isalnum() or c in "_-" else "_" for c in nome)
            etapas.append((seguro, (time.perf_counter() - t0) * 1000))
