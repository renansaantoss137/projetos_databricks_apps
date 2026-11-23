import os
import hashlib

def hash_file(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

prod_dir = os.path.join('scratch', 'download_prod')
local_dir = os.path.join('src', 'app')
dev_dir = os.path.join('scratch', 'download_dev')

print(f"{'Arquivo':<30} | {'Prod vs Local':<15} | {'Dev vs Local':<15} | {'Prod vs Dev':<15}")
print('-' * 80)
files = sorted(set(os.listdir(prod_dir) + os.listdir(local_dir) + os.listdir(dev_dir)))
for fname in files:
    if fname == '__pycache__':
        continue
    p_h = hash_file(os.path.join(prod_dir, fname))
    l_h = hash_file(os.path.join(local_dir, fname))
    d_h = hash_file(os.path.join(dev_dir, fname))
    
    prod_vs_local = 'IGUAL' if p_h == l_h else ('MODIFICADO' if p_h and l_h else ('SÓ NO PROD' if p_h else 'SÓ LOCAL'))
    dev_vs_local  = 'IGUAL' if d_h == l_h else ('MODIFICADO' if d_h and l_h else ('SÓ NO DEV' if d_h else 'SÓ LOCAL'))
    prod_vs_dev   = 'IGUAL' if p_h == d_h else 'DIFERENTE'
    print(f"{fname:<30} | {prod_vs_local:<15} | {dev_vs_local:<15} | {prod_vs_dev:<15}")
