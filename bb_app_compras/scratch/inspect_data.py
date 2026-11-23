import sys
import os
sys.path.insert(0, os.path.abspath('src/app'))
from app import _get_conn

try:
    conn = _get_conn()
    with conn.cursor() as cur:
        # 1. Status de aprovacao em ordens_compra
        cur.execute("""
            SELECT status_aprovacao, COUNT(*), COUNT(DISTINCT numero_oc), SUM(valor_original_brl)
            FROM compras.ordens_compra
            GROUP BY status_aprovacao
        """)
        print("=== STATUS APROVACAO EM ORDENS_COMPRA ===")
        for row in cur.fetchall():
            print(row)

        # 2. Status fechamento em ordens_compra
        cur.execute("""
            SELECT status_fechamento, COUNT(*), COUNT(DISTINCT numero_oc)
            FROM compras.ordens_compra
            GROUP BY status_fechamento
            ORDER BY count DESC
            LIMIT 10
        """)
        print("\n=== STATUS FECHAMENTO EM ORDENS_COMPRA (TOP 10) ===")
        for row in cur.fetchall():
            print(row)

        # 3. Requisicoes - colunas e amostragem
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'compras' AND table_name = 'requisicoes'
        """)
        print("\n=== COLUNAS DE REQUISICOES ===")
        for row in cur.fetchall():
            print(row)

        # 4. Amostra de requisicoes vs ordens_compra
        cur.execute("""
            SELECT r.requisicao, r.numero_oc, r.valor_requisicao, r.status, r.status_ordem,
                   oc.valor_original_brl, oc.moeda, oc.taxa_cambio
            FROM compras.requisicoes r
            JOIN compras.ordens_compra oc ON r.numero_oc = oc.numero_oc
            WHERE r.numero_oc IS NOT NULL AND r.numero_oc != 'Requisicao sem OC'
            LIMIT 10
        """)
        print("\n=== AMOSTRA REQ VS OC ===")
        for row in cur.fetchall():
            print(row)

        # 5. Indiretos: OCs com e sem requisicao
        cur.execute("""
            SELECT 
                CASE WHEN r.requisicao IS NOT NULL THEN 'COM_REQ' ELSE 'SEM_REQ' END as tem_req,
                COUNT(DISTINCT oc.numero_oc) as qtd_oc,
                SUM(oc.valor_original_brl) as spend_oc
            FROM compras.ordens_compra oc
            LEFT JOIN compras.requisicoes r ON oc.numero_oc = r.numero_oc
            WHERE UPPER(TRIM(COALESCE(oc.grupo_compras_oc, ''))) = 'INDIRETOS'
            GROUP BY 1
        """)
        print("\n=== INDIRETOS: OC COM VS SEM REQ ===")
        for row in cur.fetchall():
            print(row)

        # 6. Moedas nas ordens de compra de indiretos
        cur.execute("""
            SELECT moeda, COUNT(*), COUNT(DISTINCT numero_oc), SUM(valor_original_brl)
            FROM compras.ordens_compra
            WHERE UPPER(TRIM(COALESCE(grupo_compras_oc, ''))) = 'INDIRETOS'
            GROUP BY moeda
        """)
        print("\n=== MOEDAS EM INDIRETOS ===")
        for row in cur.fetchall():
            print(row)

        # 7. Total Requisicoes vs Total OCs em Indiretos
        cur.execute("""
            SELECT COUNT(DISTINCT requisicao), SUM(valor_requisicao)
            FROM compras.requisicoes
        """)
        print("\n=== TOTAL REQUISICOES ===")
        for row in cur.fetchall():
            print(row)

    conn.close()
except Exception as e:
    import traceback
    traceback.print_exc()
