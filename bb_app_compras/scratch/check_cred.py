from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
cred = w.api_client.do('POST', '/api/2.0/postgres/credentials', body={
    'endpoint': 'projects/compras-360/branches/production/endpoints/primary'
})
print("Keys in cred:", cred.keys())
for k, v in cred.items():
    if k != 'token':
        print(f"{k}: {v}")
