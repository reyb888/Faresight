import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/apix'

from fastapi.testclient import TestClient
from api.routers.index import router

client = TestClient(router)
# Test /v1/index endpoint
response = client.get("/v1/index?frequency=daily")
print(f"Status: {response.status_code}")
if response.status_code == 200:
    print(f"Body: {response.json()}")
else:
    print(f"Body: {response.text}")