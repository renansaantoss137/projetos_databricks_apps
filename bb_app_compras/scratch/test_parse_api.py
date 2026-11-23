import sys, os
sys.path.insert(0, os.path.abspath('src/app'))
import io

from app import app

client = app.test_client()

file_path = r'C:\Users\renan.ferreira\Downloads\Lista de fornecedores sem OC.xlsx'
with open(file_path, 'rb') as f:
    file_bytes = f.read()

data = {
    'file': (io.BytesIO(file_bytes), 'Lista de fornecedores sem OC.xlsx')
}

res = client.post('/api/lookups/parse-file', data=data, content_type='multipart/form-data')
print("Status code:", res.status_code)
json_data = res.get_json()
print("Success:", json_data.get('success'))
print("Count:", json_data.get('count'))
print("Columns:", json_data.get('columns'))
if json_data.get('rows'):
    print("First 3 rows:")
    for r in json_data['rows'][:3]:
        print(" ", r)
