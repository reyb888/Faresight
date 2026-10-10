import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/apix'
os.environ['CORS_ALLOWED_ORIGINS'] = 'http://localhost:3000'

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers.index import router as index_router

app = FastAPI(title='APIx', version='1.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000'],
    allow_methods=['GET'],
    allow_headers=['x-api-key'],
)
app.include_router(index_router)
print('FastAPI app created OK')
print(f'Routes: {[r.path for r in app.routes if hasattr(r, "path")]}')