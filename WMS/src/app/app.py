import os
import traceback
import pymssql
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from databricks.sdk.runtime import dbutils
    _DB_USER     = dbutils.secrets.get(scope="kvsecret-DnABrazil", key="kvsecret-AzSQL-cz-BB-sql-Usr")
    _DB_PASSWORD = dbutils.secrets.get(scope="kvsecret-DnABrazil", key="kvsecret-AzSQL-cz-BB-sql-psw")
except Exception:
    from dotenv import load_dotenv
    load_dotenv()
    _DB_USER     = os.getenv("DB_USER", "")
    _DB_PASSWORD = os.getenv("DB_PASSWORD", "")

_DB_SERVER = os.getenv("DB_SERVER", "bbraclbbsqlcp02.database.windows.net")
_DB_NAME   = os.getenv("DB_NAME",   "ACL-DNA-BRPROD")

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'static'))
CORS(app)


@app.after_request
def no_cache(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
    return response


def get_connection():
    return pymssql.connect(
        server=_DB_SERVER,
        user=_DB_USER,
        password=_DB_PASSWORD,
        database=_DB_NAME,
        port=1433,
        tds_version='7.4',
        login_timeout=30,
    )


_SELECT = """
    SELECT
        p.NUMERO_PEDIDO,
        CONVERT(VARCHAR(10), p.DATA_CRIACAO,      103) + ' ' + CONVERT(VARCHAR(8), p.DATA_CRIACAO,      108) AS DATA_CRIACAO,
        CONVERT(VARCHAR(10), p.DATA_ENTREGA,      103) + ' ' + CONVERT(VARCHAR(8), p.DATA_ENTREGA,      108) AS DATA_ENTREGA,
        CONVERT(VARCHAR(10), p.DATA_DISTRIBUICAO, 103) + ' ' + CONVERT(VARCHAR(8), p.DATA_DISTRIBUICAO, 108) AS DATA_DISTRIBUICAO,
        CONVERT(VARCHAR(10), p.DATA_FATURAMENTO,  103) + ' ' + CONVERT(VARCHAR(8), p.DATA_FATURAMENTO,  108) AS DATA_FATURAMENTO,
        CAST(p.ID_PRODUDO AS NVARCHAR(100))             AS ID_PRODUDO,
        ISNULL(pv.DESCRICAO_PRODUTO, '')                AS DESCRICAO_PRODUTO,
        ISNULL(TRY_CAST(pv.CUPO AS FLOAT), 0)           AS CUPO,
        ISNULL(p.QTDE_PEDIDO_ORIGINAL, 0)               AS QTDE_PEDIDO_ORIGINAL,
        CASE WHEN ISNULL(TRY_CAST(pv.CUPO AS FLOAT), 0) > 0
             THEN CAST(CEILING(ISNULL(p.QTDE_PEDIDO_ORIGINAL, 0) / TRY_CAST(pv.CUPO AS FLOAT)) AS INT)
             ELSE 0 END                                 AS QTDE_TOTAL_CESTOS,
        ISNULL(p.QTDE_DISTRIBUIDO,     0)               AS QTDE_DISTRIBUIDO,
        ISNULL(p.QTDE_FATURADO,        0)               AS QTDE_FATURADO,
        ISNULL(p.VLR_UNIT,             0)               AS VLR_UNIT,
        ISNULL(p.VLR_PEDIDO,           0)               AS VLR_PEDIDO,
        ISNULL(p.VLR_DISTRIBUIDO,      0)               AS VLR_DISTRIBUIDO,
        ISNULL(p.VLR_FATURADO,         0)               AS VLR_FATURADO,
        CAST(p.ID_CEVE AS NVARCHAR(50))                 AS ID_CEVE,
        ISNULL(UPPER(cv.DESC_CV), '')                   AS CENTRO_VENDAS,
        CAST(p.ID_CLIENTE AS NVARCHAR(50))              AS ID_CLIENTE,
        CAST(p.ID_TABELA_PRECO AS NVARCHAR(50))         AS ID_TABELA_PRECO,
        ISNULL(p.STATUS_PEDIDO, '')                     AS STATUS_PEDIDO,
        ISNULL(p.STATUS_DISTRIBUICAO, '')               AS STATUS_DISTRIBUICAO,
        ISNULL(p.STATUS_FATURADO, '')                   AS STATUS_FATURADO,
        ISNULL(p.MOTIVO_CANCELAMENTO_PEDIDO, '')        AS MOTIVO_CANCELAMENTO_PEDIDO,
        ISNULL(p.CLIENTE_CNPJ, '')                      AS CLIENTE_CNPJ,
        ISNULL(p.CLIENTE_NOME, '')                      AS CLIENTE_NOME,
        ISNULL(cmo.ENDERECO, '')                        AS ENDERECO,
        ISNULL(CAST(cmo.NUMERO AS NVARCHAR(50)), '')    AS NUMERO_ENDERECO,
        ISNULL(cmo.CIDADE, '')                          AS CIDADE,
        ISNULL(p.USER_ULT_ALT, '')                      AS USER_ULT_ALT,
        ISNULL(p.NATUREZA_PEDIDO, '')                   AS NATUREZA_PEDIDO,
        ISNULL(cmo.CANAL_RENOMEADO, '')                 AS CANAL_RENOMEADO,
        ISNULL(cmo.TERRITORIO_VENDA, '')                AS TERRITORIO_VENDA,
        ISNULL(cmo.TERRITORIO_ENTREGA, '')              AS TERRITORIO_ENTREGA,
        CONVERT(VARCHAR(10), p.mc1LastUpdate, 103) + ' ' + CONVERT(VARCHAR(8), p.mc1LastUpdate, 108) AS DT_ALTERACAO_PEDIDO,
        CASE WHEN CAST(p.mc1LastUpdate AS TIME) > '18:00:00' THEN 'SIM' ELSE 'NAO' END               AS POS_FEC_CARTEIRA
"""

_FROM = """
    FROM supply_chain.mc1_pedidos p
    LEFT JOIN catalogos.clientes_mc1_oracle cmo ON p.CLIENTE_CNPJ = cmo.CNPJ
    LEFT JOIN catalogos.produtos_view       pv  ON p.ID_PRODUDO   = pv.INVENTORY_ITEM_ID
    LEFT JOIN catalogos.cvs                 cv  ON p.ID_CEVE       = cv.COD_CV
"""


def _build_where(args):
    filters, params = [], []

    def add(clause, *vals):
        filters.append(clause)
        params.extend(vals)

    if args.get('numero_pedido'):
        add("CAST(p.NUMERO_PEDIDO AS NVARCHAR(50)) LIKE %s", f"%{args['numero_pedido']}%")
    if args.get('dt_ini'):
        add("p.DATA_ENTREGA >= CAST(%s AS DATE)", args['dt_ini'])
    if args.get('dt_fim'):
        add("p.DATA_ENTREGA <= CAST(%s AS DATE)", args['dt_fim'])
    if args.get('centro'):
        add("CAST(p.ID_CEVE AS NVARCHAR(50)) = %s", args['centro'])
    if args.get('natureza'):
        add("p.NATUREZA_PEDIDO = %s", args['natureza'])
    if args.get('busca'):
        like = f"%{args['busca']}%"
        add("(p.CLIENTE_NOME LIKE %s OR CAST(p.ID_PRODUDO AS NVARCHAR(100)) LIKE %s)", like, like)
    if args.get('motivo'):
        add("p.MOTIVO_CANCELAMENTO_PEDIDO LIKE %s", f"%{args['motivo']}%")
    if args.get('id_ceve'):
        add("CAST(p.ID_CEVE AS NVARCHAR(50)) LIKE %s", f"%{args['id_ceve']}%")
    if args.get('id_cliente'):
        add("CAST(p.ID_CLIENTE AS NVARCHAR(50)) LIKE %s", f"%{args['id_cliente']}%")
    if args.get('nome_cliente'):
        add("p.CLIENTE_NOME = %s", args['nome_cliente'])
    if args.get('id_produto'):
        add("CAST(p.ID_PRODUDO AS NVARCHAR(100)) = %s", args['id_produto'])
    if args.get('desc_produto'):
        add("ISNULL(pv.DESCRICAO_PRODUTO, '') = %s", args['desc_produto'])
    if args.get('dt_dist_ini'):
        add("p.DATA_DISTRIBUICAO >= CAST(%s AS DATE)", args['dt_dist_ini'])
    if args.get('dt_dist_fim'):
        add("p.DATA_DISTRIBUICAO <= CAST(%s AS DATE)", args['dt_dist_fim'])
    if args.get('dt_fat_ini'):
        add("p.DATA_FATURAMENTO >= CAST(%s AS DATE)", args['dt_fat_ini'])
    if args.get('dt_fat_fim'):
        add("p.DATA_FATURAMENTO <= CAST(%s AS DATE)", args['dt_fat_fim'])
    if args.get('dt_alt_ini'):
        add("CAST(p.mc1LastUpdate AS DATE) >= CAST(%s AS DATE)", args['dt_alt_ini'])
    if args.get('dt_alt_fim'):
        add("CAST(p.mc1LastUpdate AS DATE) <= CAST(%s AS DATE)", args['dt_alt_fim'])
    if args.get('pos_fec'):
        add("CASE WHEN CAST(p.mc1LastUpdate AS TIME) > '18:00:00' THEN 'SIM' ELSE 'NAO' END = %s", args['pos_fec'])
    if args.get('status_pedido'):
        add("ISNULL(p.STATUS_PEDIDO, '') = %s", args['status_pedido'])
    if args.get('status_fat'):
        add("ISNULL(p.STATUS_FATURADO, '') = %s", args['status_fat'])
    if args.get('canal'):
        add("ISNULL(cmo.CANAL_RENOMEADO, '') = %s", args['canal'])

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    return where, params


# ── Pedidos ──────────────────────────────────────────────────────────────────

@app.route('/api/pedidos')
def get_pedidos():
    args = {k: request.args.get(k, '').strip() for k in [
        'numero_pedido',
        'dt_ini', 'dt_fim', 'centro', 'natureza', 'busca',
        'status_pedido', 'motivo', 'id_ceve', 'id_cliente', 'nome_cliente', 'id_produto',
        'desc_produto',
        'dt_dist_ini', 'dt_dist_fim', 'dt_fat_ini', 'dt_fat_fim',
        'dt_alt_ini', 'dt_alt_fim', 'pos_fec', 'status_fat', 'canal',
    ]}
    page      = max(1, int(request.args.get('page', 1)))
    page_size = min(500, max(1, int(request.args.get('page_size', 50))))

    where, params = _build_where(args)
    offset = (page - 1) * page_size

    query = (
        f"{_SELECT} {_FROM} {where}"
        f" ORDER BY p.DATA_ENTREGA DESC, p.NUMERO_PEDIDO"
        f" OFFSET %s ROWS FETCH NEXT %s ROWS ONLY"
    )
    count_query = f"SELECT COUNT(*) {_FROM} {where}"

    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        cursor.execute(query, params + [offset, page_size])
        cols = [col[0] for col in cursor.description]
        rows = []
        for row in cursor.fetchall():
            d = {}
            for col, val in zip(cols, row):
                d[col] = str(val) if val is not None else None
            rows.append(d)

        conn.close()
        return jsonify({
            'rows':        rows,
            'total':       total,
            'page':        page,
            'page_size':   page_size,
            'total_pages': max(1, -(-total // page_size)),
        })
    except Exception as e:
        return jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500


# ── Diagnóstico ───────────────────────────────────────────────────────────────

@app.route('/api/ping')
def ping():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        # testa cada tabela separadamente
        results = {}
        tables = {
            'mc1_pedidos':           'SELECT TOP 1 NUMERO_PEDIDO, NATUREZA_PEDIDO FROM supply_chain.mc1_pedidos',
            'clientes_mc1_oracle':   'SELECT TOP 1 CNPJ, ENDERECO, NUMERO, CIDADE, CANAL_RENOMEADO, TERRITORIO_VENDA, TERRITORIO_ENTREGA FROM catalogos.clientes_mc1_oracle',
            'produtos_view':         'SELECT TOP 1 INVENTORY_ITEM_ID, DESCRICAO_PRODUTO, CUPO FROM catalogos.produtos_view',
            'cvs':                   'SELECT TOP 1 COD_CV, DESC_CV FROM catalogos.cvs',
        }
        for name, sql in tables.items():
            try:
                cur.execute(sql)
                cur.fetchone()
                results[name] = 'OK'
            except Exception as e:
                results[name] = str(e)
        conn.close()
        return jsonify({'status': 'connected', 'tables': results})
    except Exception as e:
        return jsonify({'status': 'connection_failed', 'error': str(e)}), 500


# ── Filtros dinâmicos ─────────────────────────────────────────────────────────

@app.route('/api/ceves')
def get_ceves():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT CAST(ID_CEVE AS NVARCHAR(50)) AS ID_CEVE"
            " FROM supply_chain.mc1_pedidos"
            " WHERE ID_CEVE IS NOT NULL ORDER BY ID_CEVE"
        )
        result = [row[0] for row in cur.fetchall()]
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/naturezas')
def get_naturezas():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT NATUREZA_PEDIDO"
            " FROM supply_chain.mc1_pedidos"
            " WHERE NATUREZA_PEDIDO IS NOT NULL AND NATUREZA_PEDIDO <> ''"
            " ORDER BY NATUREZA_PEDIDO"
        )
        result = [row[0] for row in cur.fetchall()]
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/clientes')
def get_clientes():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT TOP 1000 ISNULL(CLIENTE_NOME, '') AS CLIENTE_NOME"
            " FROM supply_chain.mc1_pedidos"
            " WHERE CLIENTE_NOME IS NOT NULL AND CLIENTE_NOME <> ''"
            " ORDER BY CLIENTE_NOME"
        )
        result = [row[0] for row in cur.fetchall()]
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/produtos')
def get_produtos():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT TOP 1000"
            " CAST(p.ID_PRODUDO AS NVARCHAR(100)) AS ID_PRODUDO,"
            " ISNULL(pv.DESCRICAO_PRODUTO, '') AS DESCRICAO_PRODUTO"
            " FROM supply_chain.mc1_pedidos p"
            " LEFT JOIN catalogos.produtos_view pv ON p.ID_PRODUDO = pv.INVENTORY_ITEM_ID"
            " WHERE p.ID_PRODUDO IS NOT NULL"
            " ORDER BY DESCRICAO_PRODUTO"
        )
        result = [{'id': row[0], 'desc': row[1]} for row in cur.fetchall()]
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/status_fat')
def get_status_fat():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT ISNULL(STATUS_FATURADO, '') AS STATUS_FATURADO"
            " FROM supply_chain.mc1_pedidos"
            " WHERE STATUS_FATURADO IS NOT NULL AND STATUS_FATURADO <> ''"
            " ORDER BY STATUS_FATURADO"
        )
        result = [row[0] for row in cur.fetchall()]
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/canais')
def get_canais():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT ISNULL(CANAL_RENOMEADO, '') AS CANAL_RENOMEADO"
            " FROM catalogos.clientes_mc1_oracle"
            " WHERE CANAL_RENOMEADO IS NOT NULL AND CANAL_RENOMEADO <> ''"
            " ORDER BY CANAL_RENOMEADO"
        )
        result = [row[0] for row in cur.fetchall()]
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/status_pedido')
def get_status_pedido():
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT ISNULL(STATUS_PEDIDO, '') AS STATUS_PEDIDO"
            " FROM supply_chain.mc1_pedidos"
            " WHERE STATUS_PEDIDO IS NOT NULL AND STATUS_PEDIDO <> ''"
            " ORDER BY STATUS_PEDIDO"
        )
        result = [row[0] for row in cur.fetchall()]
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Acordos Comerciais (Disciplina Comercial) ───────────────────────────

ACORDOS_FILE = os.path.join(os.path.dirname(__file__), 'acordos_data.json')

def load_acordos_file():
    if os.path.exists(ACORDOS_FILE):
        try:
            import json
            with open(ACORDOS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return [
        {
            "id": 101,
            "canal": "Tradicional",
            "nome": "Acordo Anual Pavuna 2026",
            "descricao": "Plano estratégico de fornecimento e bonificação por atingimento de curva A.",
            "data": "2026-01-15",
            "vigencia_inicio": "2026-01-01",
            "vigencia_fim": "2026-12-31",
            "condicoes_pactuadas": "Garantia de 95% Fill Rate com bônus de 2% sobre faturamento líquido mensal.",
            "status": "Em andamento",
            "responsavel": "PAULO CESAR DE OLIVEIRA",
            "diretores": ["PC", "Hudson", "Renan", "Dante"],
            "comentarios": [
                {"id": 1, "autor": "Hudson Brito", "data": "2026-01-16 10:30", "texto": "Alinhado com a diretoria. Aguardando validação do volume do Q1 @Hudson.", "respostas": []}
            ],
            "historico": [
                {"data": "2026-01-15 14:00", "usuario": "Hudson Brito", "acao": "Criação do Acordo"}
            ]
        },
        {
            "id": 102,
            "canal": "Distribuidores",
            "nome": "Parceria Distribuição Rio Centro",
            "descricao": "Expansion de rotas de venda direta em distribuidores parceiros.",
            "data": "2026-02-01",
            "vigencia_inicio": "2026-02-01",
            "vigencia_fim": "2026-08-31",
            "condicoes_pactuadas": "Desconto em cascata de 4% para compras acima de 1.000 caixas de pães fatiados.",
            "status": "Cumprido",
            "responsavel": "DANTE CODOGNO e HUDSON BRITO",
            "diretores": ["PC", "Renan"],
            "comentarios": [],
            "historico": [
                {"data": "2026-02-01 09:15", "usuario": "Hudson Brito", "acao": "Criação do Acordo"}
            ]
        },
        {
            "id": 103,
            "canal": "Moderno",
            "nome": "Campanha Promocional Q2 - Redes Múltiplas",
            "descricao": "Ações de ponto de venda e destaque em folhetos de ofertas.",
            "data": "2026-03-10",
            "vigencia_inicio": "2026-04-01",
            "vigencia_fim": "2026-06-30",
            "condicoes_pactuadas": "Rebaixa de tabela de 3% condicionado ao sell-out mínimo de 85%.",
            "status": "Não cumprido",
            "responsavel": "RENAN GOES",
            "diretores": ["Hudson", "Dante"],
            "comentarios": [],
            "historico": [
                {"data": "2026-03-10 16:45", "usuario": "Renan Goes", "acao": "Criação do Acordo"}
            ]
        }
    ]

def save_acordos_file(data):
    try:
        import json
        with open(ACORDOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Erro ao salvar acordos:", e)

@app.route('/api/acordos', methods=['GET'])
def get_acordos():
    acordos = load_acordos_file()
    canal = request.args.get('canal', '').strip()
    status = request.args.get('status', '').strip()
    busca = request.args.get('busca', '').strip().lower()

    filtered = acordos
    if canal:
        filtered = [a for a in filtered if a.get('canal') == canal]
    if status:
        filtered = [a for a in filtered if a.get('status') == status]
    if busca:
        filtered = [a for a in filtered if busca in a.get('nome', '').lower() or busca in a.get('condicoes_pactuadas', '').lower()]

    return jsonify(filtered)

@app.route('/api/acordos', methods=['POST'])
def create_acordo():
    acordos = load_acordos_file()
    data = request.json or {}
    new_id = max([a.get('id', 100) for a in acordos] + [100]) + 1
    data['id'] = new_id
    acordos.insert(0, data)
    save_acordos_file(acordos)
    return jsonify(data), 201

@app.route('/api/acordos/<int:acordo_id>', methods=['PUT'])
def update_acordo(acordo_id):
    acordos = load_acordos_file()
    data = request.json or {}
    for i, a in enumerate(acordos):
        if a.get('id') == acordo_id:
            acordos[i].update(data)
            save_acordos_file(acordos)
            return jsonify(acordos[i])
    return jsonify({'error': 'Acordo não encontrado'}), 404

@app.route('/api/acordos/<int:acordo_id>', methods=['DELETE'])
def delete_acordo_api(acordo_id):
    acordos = load_acordos_file()
    acordos = [a for a in acordos if a.get('id') != acordo_id]
    save_acordos_file(acordos)
    return jsonify({'success': True})


# ── Servir arquivos estáticos ─────────────────────────────────────────────────

@app.route('/')
def serve_index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/<path:filename>')
def serve_files(filename):
    return send_from_directory(BASE_DIR, filename)


# ── Inicialização ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port  = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV', 'production') == 'development'
    if debug:
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        from waitress import serve
        print(f'Servidor rodando em http://0.0.0.0:{port}')
        serve(app, host='0.0.0.0', port=port)
