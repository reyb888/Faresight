import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/apix'

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title='Test')

@app.get('/manual')
async def manual():
    return {'ok': True}

from api.routers.index import router as index_router
app.include_router(index_router)

print('APIRoute instances:')
for route in app.routes:
    if isinstance(route, APIRoute):
        print(f'  {route.path} {route.methods}')
    else:
        print(f'  Other: {type(route)} path={getattr(route, "path", "NO PATH")}')