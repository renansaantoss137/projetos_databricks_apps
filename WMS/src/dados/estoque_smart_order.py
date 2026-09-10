# Databricks notebook source
pip install openpyxl

# COMMAND ----------

import io
import re
import pandas as pd
import os

# 1. Recebe a pasta do Volume enviada pelo Job (ex: /Volumes/cat_dnabb_dv/.../)
location = dbutils.widgets.get("arquivo")

# 2. Lista todos os arquivos da pasta
arquivos = dbutils.fs.ls(location)
planilhas = [f for f in arquivos if f.name.endswith('.xlsx')]

if not planilhas:
    raise FileNotFoundError(f"Nenhum arquivo Excel encontrado no volume: {location}")

# 3. Descobre o horário de modificação do arquivo mais recente
max_mtime = max(os.path.getmtime(f.path.replace("dbfs:", "")) for f in planilhas)

# 4. Filtra APENAS os arquivos modificados no mesmo lote (nos últimos 3 minutos em relação ao mais recente)
JANELA_TOLERANCIA_MS = 3 * 60 * 1000  # 3 minutos em milissegundos
JANELA_TOLERANCIA_SEG = 180  # 3 minutos em segundos
planilhas_lote = [
    f for f in planilhas 
    if (max_mtime - os.path.getmtime(f.path.replace("dbfs:", ""))) <= JANELA_TOLERANCIA_SEG
]
print(f"🎯 Total de arquivo(s) no volume: {len(planilhas)}")
print(f"📦 Arquivo(s) recém-chegado(s) no gatilho atual: {len(planilhas_lote)}")

lista_dfs = []
nomes_limpos_processados = set()

# 5. Processa APENAS os arquivos recém-chegados/substituídos
for arq in planilhas_lote:
    file_path = arq.path
    nome_arquivo_original = arq.name
    
    # Limpa o nome do arquivo (Remove _YYYYWW mantendo a extensão .xlsx)
    nome_arquivo_limpo = re.sub(r'_\d{4,6}(?=\.xlsx$)', '', nome_arquivo_original)
    nomes_limpos_processados.add(nome_arquivo_limpo)
    
    print(f"  -> Lendo arquivo recente: {nome_arquivo_original} (Mapeado como: {nome_arquivo_limpo})")
    
    # Processa o arquivo Excel
    df_binary = spark.read.format("binaryFile").load(file_path)
    file_bytes = df_binary.select("content").collect()[0]["content"]
    
    pdf = pd.read_excel(io.BytesIO(file_bytes))
    
    def clean_text(col):
        return pdf[col].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    pdf_temp = pd.DataFrame({
        'COD_PROD_BIMBO': clean_text('COD_PROD_BIMBO'),
        'CNPJ': clean_text('CNPJ'),
        'SEMANA': pd.to_numeric(pdf['SEMANA'], errors='coerce').round(0),
        'Estoque Quantidade': pd.to_numeric(pdf['Estoque Quantidade'], errors='coerce').round(0),
        'NOME_ARQUIVO': nome_arquivo_limpo
    })
    lista_dfs.append(pdf_temp)

# 6. Concatenar apenas os DataFrames do lote recente
df_final_pd = pd.concat(lista_dfs, ignore_index=True)
df_spark = spark.createDataFrame(df_final_pd)
df_spark.createOrReplaceTempView("vw_estoque_temp")

# 7. Limpa registros antigos na tabela Delta apenas dos arquivos que chegaram no lote
arquivos_in_sql = ", ".join([f"'{nome}'" for nome in nomes_limpos_processados])
spark.sql(f"DELETE FROM cat_dnabb_dv.default.tbl_estoque_smart_order WHERE NOME_ARQUIVO IN ({arquivos_in_sql})")

# 8. Insere os novos dados com o storeday (data/hora da leitura)
spark.sql("""
    INSERT INTO cat_dnabb_dv.default.tbl_estoque_smart_order
    SELECT 
        CAST(COD_PROD_BIMBO AS STRING),
        CAST(CNPJ AS STRING),
        CAST(SEMANA AS BIGINT),
        CAST(`Estoque Quantidade` AS BIGINT),
        CAST(NOME_ARQUIVO AS STRING),
        current_timestamp() AS storeday
    FROM vw_estoque_temp
""")

print(f"✅ Sucesso! {len(df_final_pd)} linha(s) processada(s) do lote recente.")
