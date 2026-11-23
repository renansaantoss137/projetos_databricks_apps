# Databricks notebook source
# Ingestão de Dados BQ Landing -> Unity Catalog Delta Table
# Grupo Bimbo Brasil - DNA Analytics

# COMMAND ----------
# MAGIC %pip install openpyxl pandas

# COMMAND ----------
import io
import os
import re
import pandas as pd
from datetime import datetime
from pyspark.sql import functions as F

# COMMAND ----------
# 1. Recuperação de parâmetros enviados pelo Job (com fallbacks para execução manual)
try:
    dbutils.widgets.text("arquivo", "/Volumes/cat_dnabb_dv/grobbbqb_sz/dev_bq_landing/base_landing.xlsx", "Arquivo do Volume")
    dbutils.widgets.text("catalogo", "cat_dnabb_dv", "Catálogo")
    dbutils.widgets.text("esquema", "grobbbqb_sz", "Esquema")
    dbutils.widgets.text("tabela", "tbl_bq_landing", "Tabela Destino")

    location = dbutils.widgets.get("arquivo")
    catalogo = dbutils.widgets.get("catalogo")
    esquema = dbutils.widgets.get("esquema")
    tabela = dbutils.widgets.get("tabela")
except Exception:
    location = "/Volumes/cat_dnabb_dv/grobbbqb_sz/dev_bq_landing/base_landing.xlsx"
    catalogo = "cat_dnabb_dv"
    esquema = "grobbbqb_sz"
    tabela = "tbl_bq_landing"

tabela_completa = f"{catalogo}.{esquema}.{tabela}"
print(f"🚀 Iniciando ingestão do arquivo: {location}")
print(f"🎯 Tabela de destino: {tabela_completa}")

# COMMAND ----------
# 2. Resolução do caminho do arquivo no Volume
# Se o location passado pelo gatilho for a pasta do volume, busca o base_landing.xlsx dentro dela
if location.endswith("/"):
    arquivo_excel = os.path.join(location, "base_landing.xlsx").replace("\\", "/")
else:
    arquivo_excel = location

# Normaliza caminho POSIX
posix_path = arquivo_excel.replace("dbfs:", "")
if not os.path.exists(posix_path):
    # Se não achar o arquivo específico, lista os arquivos .xlsx disponíveis na pasta
    pasta_volume = os.path.dirname(posix_path)
    if os.path.exists(pasta_volume):
        arquivos = [os.path.join(pasta_volume, f).replace("\\", "/") for f in os.listdir(pasta_volume) if f.endswith(".xlsx") and "backup" not in f.lower()]
        if arquivos:
            posix_path = max(arquivos, key=os.path.getmtime)
            print(f"⚠️ Usando arquivo mais recente da pasta: {posix_path}")
        else:
            raise FileNotFoundError(f"Nenhum arquivo .xlsx encontrado na pasta do volume: {pasta_volume}")
    else:
        raise FileNotFoundError(f"Caminho não encontrado: {posix_path}")

print(f"📂 Lendo arquivo: {posix_path}")

# COMMAND ----------
# 3. Leitura e Sanitização do Excel via Pandas (Aba 'Base de Landing' ou 'Base de Dados')
xl = pd.ExcelFile(posix_path)
nome_aba = "Base de Landing" if "Base de Landing" in xl.sheet_names else ("Base de Dados" if "Base de Dados" in xl.sheet_names else xl.sheet_names[0])
print(f"📄 Lendo aba específica: '{nome_aba}'...")
pdf = pd.read_excel(posix_path, sheet_name=nome_aba)
print(f"📊 Total de linhas lidas: {len(pdf)}")
print(f"📋 Colunas originais: {list(pdf.columns)}")

# Sanitiza os nomes das colunas para compatibilidade com Delta Lake / SQL
def sanitizar_coluna(col):
    col = str(col).strip()
    col = re.sub(r'[ ,;{}()\n\t=]', '_', col)
    col = re.sub(r'_+', '_', col).strip('_')
    return col.upper()

# Sanitiza e filtra linhas
pdf.columns = [sanitizar_coluna(c) for c in pdf.columns]

# Descarta linhas 'Total' ou vazias
if 'ANO' in pdf.columns:
    pdf = pdf[pdf['ANO'].astype(str).str.strip().str.upper() != 'TOTAL'].copy()

# Se a planilha tem ANO e MES mas não DATA, compõe DATA (YYYY-MM-01)
col_mes = next((c for c in pdf.columns if 'MES' in c), None)
if 'ANO' in pdf.columns and col_mes and 'DATA' not in pdf.columns:
    def _montar_data(r):
        try:
            a = int(float(str(r['ANO']).split('.')[0].strip()))
            m = int(float(str(r[col_mes]).split('.')[0].strip()))
            return f'{a:04d}-{m:02d}-01'
        except Exception:
            return ''
    pdf['DATA'] = pdf.apply(_montar_data, axis=1)

# Converte todas as colunas de texto/objeto para string limpa
for col in pdf.columns:
    if pdf[col].dtype == 'object':
        pdf[col] = pdf[col].fillna('').astype(str).str.strip()

# Adiciona metadados de auditoria
pdf['NOME_ARQUIVO_ORIGEM'] = os.path.basename(posix_path)

# COMMAND ----------
# 4. Conversão para PySpark DataFrame
df_spark = spark.createDataFrame(pdf)
df_spark = df_spark.withColumn("STOREDAY", F.current_timestamp())

# COMMAND ----------
# 5. Gravação na Tabela Delta do Unity Catalog
print(f"💾 Gravando dados na tabela Delta: {tabela_completa}...")

# Cria a tabela ou sobrescreve com esquema evolutivo
(
    df_spark.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(tabela_completa)
)

print(f"✅ Ingestão finalizada com sucesso na tabela: {tabela_completa}")
display(spark.table(tabela_completa).limit(10))
