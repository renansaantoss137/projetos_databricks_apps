"""Servidor local de demonstração, sem conexão com Databricks ou banco."""
from datetime import datetime
import csv
import io
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, make_response

APP_DIR = Path(__file__).resolve().parent.parent / 'src' / 'app'
app = Flask(__name__, static_folder=None)

def demo_rows():
    return [{'NOTA_FISCAL': str(51000+i), 'NUMERO_OC': str(240000+i),
             'FORNECEDOR': f'Fornecedor Exemplo {chr(65+i%5)}', 'DS_ITEM': ['Embalagem', 'Farinha', 'Serviço de transporte'][i%3],
             'MACRO_CATEGORIA': ['Materiais', 'Ingredientes', 'Serviços'][i%3], 'EMPRESA': 'Empresa Exemplo',
             'DATA_LANCAMENTO': f'{datetime.now().year}-{i%12+1:02d}-15', 'DATA_OC': f'{datetime.now().year}-{i%12+1:02d}-10',
             'VALOR_LIQUIDO_BRL': (i+1)*12500, 'STATUS_FECHAMENTO': 'Aberta' if i%2 else 'Fechada',
             'REQUISICAO': str(90000+i), 'NUMERO_REQUISICAO': str(90000+i), 'REQUISITANTE': 'Pessoa Exemplo',
             'DESCRICAO_REQ': 'Material de demonstração', 'DT_CRIACAO': f'{datetime.now().year}-{i%12+1:02d}-08',
             'VALOR_REQUISICAO': (i+1)*12500, 'STATUS': 'Aprovada', 'STATUS_ORDEM': 'Aberta', 'COMPRADOR_SUGERIDO': 'Comprador Exemplo'} for i in range(30)]

@app.route('/api/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def api(path):
    if request.method != 'GET':
        return jsonify(error='Operação indisponível em demonstração'), 405
    year = datetime.now().year
    filters = {'anos': [str(year - 1), str(year)], 'grupos': ['Diretos', 'Indiretos'],
               'fornecedores': ['Fornecedor Exemplo A', 'Fornecedor Exemplo B']}
    if path.startswith('filters/'):
        return jsonify(filters if path.endswith(('notas', 'cascading', 'cascading-ordens', 'comercial', 'ordens')) else {})
    if path == 'health':
        return jsonify(status='demo', message='Dados fictícios, sem conexão ao Lakebase')
    if path == 'auth/me':
        return jsonify(authenticated=True, email='demonstracao@exemplo.invalid', is_admin=False, can_access_cadastros=False)
    if path == 'performance/kpis':
        return jsonify(current={'net_spend': 2900000000, 'centralization_pct': 81.2, 'avg_payment_term': 58}, previous={'net_spend': 3400000000})
    if path == 'performance/spend-yoy':
        return jsonify([{'mes': i, 'current_spend': (210 + (i * 17) % 100) * 1000000,
                         'prev_spend': (235 + (i * 13) % 90) * 1000000,
                         'current_central_pct': 75 + i % 10, 'prev_central_pct': 72 + i % 9,
                         'current_central_spend': (210 + (i * 17) % 100) * 800000,
                         'prev_central_spend': (235 + (i * 13) % 90) * 760000} for i in range(1, 13)])
    if path == 'performance/lead-time':
        stages = [{'id': key, 'name': name, 'sub': sub, 'qty': qty, 'qty_label': 'pedidos',
                   'spend': spend, 'conv_pct': round(qty / 754 * 100, 1)} for key, name, sub, qty, spend in [
                       ('emitido', 'Pedidos', 'Emitidos', 754, 2900000000),
                       ('aprovado', 'Pedidos', 'Aprovados', 675, 187000000),
                       ('fat_inicial', 'Faturamento', 'Iniciado', 438, 43000000),
                       ('fat_tot', 'Faturamento', 'Totalmente Concluído', 347, 28000000)]]
        return jsonify([{'longest_leg': 'Pedido Aprovado e 1ª NF', 'stages': stages,
                         'connectors': [{'val': 2, 'unit': 'dias'}, {'val': 3, 'unit': 'dias'}, {'val': 17, 'unit': 'horas'}]}])
    if path == 'performance/process-deviations':
        return jsonify([{'total': 100, 'regular': 85, 'pos_fatura': 9, 'sem_oc': 6}])
    if path == 'performance/attention':
        result = {key: {'qty': qty, 'pct_qty': round(qty/900*100, 1), 'valor': value,
                        'pct_valor': round(value/2900000000*100, 2)}
                  for key, qty, value in [('req_pending', 18, 1200000), ('pos_fatura', 34, 8500000),
                      ('decentral', 15, 1900000), ('oc_90', 11, 950000),
                      ('blanket_old', 7, 700000), ('sem_oc', 22, 2700000)]}
        result['price_alerts'] = [{'ds_item': item, 'nome_fornecedor': f'Fornecedor Exemplo {chr(65+i%5)}',
            'local_fornecedor': ['São Paulo', 'Campinas', 'Curitiba', 'Recife'][i%4],
            'preco_anterior': price, 'preco_atual': round(price*(1+variation/100), 2),
            'pct_var': variation, 'saving_total': round(price*variation/100*qty, 2),
            'data_anterior': f'{year}-08-12', 'data_atual': f'{year}-09-18',
            'nf_anterior': str(49000+i), 'nf_atual': str(52000+i)}
            for i, (item, price, variation, qty) in enumerate([
                ('Farinha de trigo — saca 25 kg', 82.5, 12.4, 18000), ('Filme para embalagem', 18.2, 8.6, 46000),
                ('Óleo vegetal — litro', 6.4, 15.2, 95000), ('Caixa de papelão', 3.8, 6.5, 110000),
                ('Serviço de transporte', 2450, 9.8, 150), ('Açúcar refinado — kg', 4.2, 7.3, 75000),
                ('Manutenção de equipamentos', 1850, 18.5, 90), ('Etiqueta de produto', 0.18, 11.1, 800000)])]
        return jsonify(result)
    if path == 'commercial/payment-evolution':
        return jsonify([{'mes': i, 'discount_monthly': -i * 10000, 'avg_term': 48+i,
                         'sum_pgto': (48+i)*1000000, 'sum_vlr': 1000000} for i in range(1, 13)])
    if path == 'commercial/kpis':
        return jsonify([{'avg_payment_term': 58, 'total_spend': 2900000000, 'spend_below_60': 1050000000}])
    if path == 'commercial/payment-distribution':
        return jsonify([{'bucket': label, 'net_spend': value} for label, value in [('À vista', 200000000), ('16 a 30 dias', 300000000), ('31 a 45 dias', 400000000), ('46 a 59 dias', 350000000), ('60 dias ou mais', 1650000000)]])
    if path in ('commercial/suppliers-below-60', 'commercial/renegotiation-table'):
        return jsonify([{'fornecedor': f'Fornecedor Exemplo {chr(65+i)}', 'net_spend': 120000000-i*18000000,
                         'numero_oc': str(240001+i), 'prazo': 30+i*5} for i in range(5)])
    if path == 'governance/kpis':
        return jsonify({'total_nfs_pgto': 900, 'total_spend_pgto': 2900000000, 'pos_fatura_qty': 34, 'pos_fatura_val': 8500000,
                        'urgente_qty': 12, 'urgente_val': 1800000, 'sem_oc_qty': 22, 'sem_oc_val': 2700000,
                        'decentral_qty': 15, 'decentral_val': 1900000, 'total_oc_decentral': 200,
                        'sucessivas_groups_qty': 4, 'sucessivas_qty': 9, 'sucessivas_val': 450000,
                        'total_valor_ocs_periodo': 100000000, 'blanket_old_qty': 7, 'blanket_old_val': 700000,
                        'total_oc_faturadas_pgto': 675, 'oc90_qty': 11, 'oc90_val': 950000, 'total_oc_abertas': 120})
    if path == 'governance/deviation-impact':
        return jsonify([{'label': label, 'qty': qty, 'value': value} for label, qty, value in [
            ('OC pós-fatura', 34, 8500000), ('Nota sem OC', 22, 2700000), ('OC descentralizada >30k', 15, 1900000),
            ('OC emergencial', 12, 1800000), ('OC aberta >90 dias', 11, 950000),
            ('Acordo de compra >180 dias', 7, 700000), ('OCs sucessivas', 9, 450000)]])
    if path == 'governance/by-buyer':
        return jsonify([{'buyer': f'Comprador Exemplo {chr(65+i%6)}',
                         'depart': ['Compras Diretas', 'Compras Indiretas'][i%2],
                         'tipo_excecao': ['OC pós-fatura', 'OC descentralizada >30k', 'OCs sucessivas',
                                          'OC aberta >90 dias', 'Acordo de compra >180 dias'][i%5],
                         'qty': 18-i, 'valor': 1800000-i*95000,
                         'pct_transacoes': round(8.2-i*0.4, 1)} for i in range(15)])
    if path == 'governance/exceptions-table':
        kind = request.args.get('type', 'pos_fatura')
        labels = {'pos_fatura': 'OC pós-fatura', 'sem_oc': 'Nota sem OC', 'decentral': 'OC descentralizada >30k',
                  'sucessivas': 'OCs sucessivas', 'oc_90': 'OC aberta >90 dias',
                  'blanket_old': 'Acordo de compra >180 dias', 'urgente': 'OC emergencial'}
        return jsonify([{'tipo_excecao': labels.get(kind, 'OC emergencial'),
            'NUMERO_OC': str(240001+i), 'NOTA_FISCAL': str(51000+i), 'numero_acordo': str(180001+i//3),
            'fornecedor': f'Fornecedor Exemplo {chr(65+i%5)}', 'num_forn': str(7000+i%5),
            'comprador': f'Comprador Exemplo {chr(65+i%4)}', 'depart_comprador': ['Compras Diretas', 'Compras Indiretas'][i%2],
            'solicitante': f'Solicitante Exemplo {i+1}', 'depart_solicitante': ['Produção', 'Logística', 'Manutenção'][i%3],
            'net_spend': 45000+i*17500, 'gross_spend': (45000+i*17500)*1.12,
            'data_oc': f'{year}-03-{10+i%15:02d}', 'data_criacao_oc': f'{year}-03-{10+i%15:02d}',
            'data_emissao_oc': f'{year}-03-{10+i%15:02d}', 'data_aprov_oc': f'{year}-03-{12+i%15:02d}',
            'data_fatura': f'{year}-03-05', 'data_pagamento': f'{year}-04-15', 'dias_pos_fatura': 7+i%15,
            'dias_aberto': 195+i*9 if kind == 'blanket_old' else 95+i*6,
            'acordo_dt_criacao': f'{year-1}-11-10', 'acordo_data_final': f'{year}-12-31',
            'acordo_status': 'Aberto', 'acordo_descricao': ['Fornecimento de embalagens', 'Insumos para produção', 'Serviços industriais'][i%3],
            'valor_liberado': (45000+i*17500)*0.65, 'id_grupo': f'GRP-{i//3+1:03d}',
            'item': ['Farinha de trigo', 'Embalagem flexível', 'Peças de manutenção'][i%3],
            'qtd_ocs_grupo': 3, 'diff_pct': 0 if i%2 else 4.8, 'is_similar': int(i%2 == 0),
            'is_identical': int(i%2 == 1), 'valor_total_grupo': (45000+(i//3)*3*17500)*3}
            for i in range(24)])
    if path in ('reports/data', 'reports/export'):
        rows = demo_rows()
        search = request.args.get('search', '').strip().lower()
        if search:
            rows = [row for row in rows if any(search in str(value).lower() for value in row.values())]
        col = request.args.get('date_values_col')
        if col:
            return jsonify(col=col, values=sorted({str(r.get(col.upper())) for r in rows if r.get(col.upper())}), has_empty=False)
        if path.endswith('export'):
            columns = [c for c in request.args.get('cols', '').split(',') if c] or list(rows[0] if rows else {})
            out = io.StringIO(newline='')
            writer = csv.DictWriter(out, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
            response = make_response('\ufeff' + out.getvalue())
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = 'attachment; filename="demonstracao.csv"'
            return response
        page = max(1, request.args.get('page', 1, type=int) or 1)
        per_page = max(1, min(1000, request.args.get('per_page', 500, type=int) or 500))
        sort = request.args.get('sort', '').upper()
        if sort and rows and sort in rows[0]:
            rows.sort(key=lambda row: str(row.get(sort, '')), reverse=request.args.get('dir', '').upper() == 'DESC')
        return jsonify(rows=rows[(page-1)*per_page:page*per_page], total=len(rows), page=page, per_page=per_page, source=request.args.get('source', 'notas'))
    if path == 'performance/req-pending-detail':
        return jsonify([dict(row, DT_APROVACAO=f'{year}-09-10', dias_espera=6+i)
                        for i, row in enumerate(demo_rows()[:18])])
    if path == 'orders/kpis':
        return jsonify([{'open_value': 48500000, 'open_pos': 120, 'late_pos': 47,
                         'late_value': 15200000, 'avg_delay': 26}])
    if path == 'orders/planned-vs-realized':
        return jsonify([{'mes': f'{year}-{i:02d}', 'realized': (25+i*3)*1000000,
                         'remaining': (13+i%4)*1000000} for i in range(1, 13)])
    if path == 'orders/overdue-by-supplier':
        return jsonify([{'fornecedor': f'Fornecedor Exemplo {chr(65+i)}', 'open_value': (8-i)*1000000,
                         'qty': 18-i*2, 'avg_days_late': 15+i*7} for i in range(7)])
    if path == 'orders/delay-buckets':
        return jsonify([{'bucket': label, 'valor': value, 'qty': qty} for label, value, qty in [
            ('No prazo', 33300000, 73), ('1-30 dias', 5400000, 19), ('31-60 dias', 3800000, 12),
            ('61-90 dias', 2800000, 8), ('91-120 dias', 1900000, 5), ('>120 dias', 1300000, 3)]])
    if path == 'orders/open-table':
        return jsonify(rows=[{'numero_oc': str(240000+i), 'fornecedor': f'Fornecedor Exemplo {chr(65+i%5)}',
                              'comprador': f'Comprador Exemplo {chr(65+i%3)}', 'open_value': (i+1)*25000,
                              'promised_date': f'{year}-{i%12+1:02d}-15', 'days_late': i*4} for i in range(30)])
    return jsonify(error='Dados de demonstração ainda não disponíveis para esta funcionalidade'), 501

@app.route('/')
@app.route('/<path:filename>')
def files(filename='index.html'):
    if filename.endswith('.html'):
        page = (APP_DIR / filename).resolve()
        if page.parent != APP_DIR or not page.is_file():
            return 'Não encontrado', 404
        html = page.read_text(encoding='utf-8')
        banner = '<div style="position:relative;display:block;margin:12px 12px 80px;pointer-events:none;background:#a43b00;color:white;padding:7px 14px;font:600 12px sans-serif;border-radius:6px 0 0 0">DEMONSTRAÇÃO LOCAL — DADOS FICTÍCIOS</div>'
        return make_response(html.replace('</body>', banner + '</body>'))
    return send_from_directory(APP_DIR, filename)

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='127.0.0.1', port=8002, threads=8)
