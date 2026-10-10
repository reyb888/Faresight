import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/apix'
os.environ['API_KEYS'] = 'test-key'
os.environ['CORS_ALLOWED_ORIGINS'] = 'http://localhost'

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app, headers={'x-api-key': 'test-key'})

# Test /v1/index endpoint
response = client.get("/v1/index?frequency=daily")
print(f"/v1/index status: {response.status_code}")
if response.status_code == 200:
    print(f"Body: {response.json()}")
else:
    print(f"Body: {response.text[:200]}")

# Test /v1/backtest
response = client.get("/v1/backtest")
print(f"\n/v1/backtest status: {response.status_code}")
if response.status_code == 200:
    print(f"Body: {response.json()}")
else:
    print(f"Body: {response.text[:200]}")

# Test /v1/routes
response = client.get("/v1/routes/DEL/BOM?days=30")
print(f"\n/v1/routes/DEL/BOM status: {response.status_code}")
if response.status_code == 200:
    print(f"Body: {response.json()}")
else:
    print(f"Body: {response.text[:200]}")

# Test /v1/heatmap
response = client.get("/v1/heatmap")
print(f"\n/v1/heatmap status: {response.status_code}")
if response.status_code == 200:
    print(f"Body: {response.json()}")
else:
    print(f"Body: {response.text[:200]}")

# Test /v1/elasticity
response = client.get("/v1/routes/DEL/BOM/elasticity")
print(f"\n/v1/routes/DEL/BOM/elasticity status: {response.status_code}")
if response.status_code == 200:
    print(f"Body: {response.json()}")
else:
    print(f"Body: {response.text[:200]}")