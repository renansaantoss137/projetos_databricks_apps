import json
import sqlite3
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


SCRIPT = Path(__file__).with_name('conferir_valores_candidato.py')


@pytest.fixture
def ambiente(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"valor":100}' if self.path == '/api' else b'<span id="valor">100</span>'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json' if self.path == '/api' else 'text/html')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    db = tmp_path / 'valores.db'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE valores (valor INTEGER)')
        con.execute('INSERT INTO valores VALUES (100)')
    yield f'http://127.0.0.1:{server.server_port}', db, tmp_path
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize('sem_sql, esperado, codigo', [(False, 'OK', 0), (True, 'NÃO CONFERIDO', 1)])
def test_comparacao_respeita_execucao_sql(ambiente, sem_sql, esperado, codigo):
    base, db, tmp_path = ambiente
    cfg = {'base': base, 'sql': {'tipo': 'sqlite', 'arquivo': str(db)}, 'cenarios': [{
        'nome': 'valor', 'url': '/', 'checagens': [{
            'nome': 'valor', 'tela': '#valor', 'api': {'url': '/api', 'campo': 'valor'},
            'sql': 'SELECT valor FROM valores'}]}]}
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(cfg), encoding='utf-8')
    args = [sys.executable, str(SCRIPT), '--config', str(config)]
    if sem_sql:
        args.append('--sem-sql')
    resultado = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    assert resultado.returncode == codigo, resultado.stdout + resultado.stderr
    assert esperado in resultado.stdout
