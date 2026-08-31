import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/apix'
os.environ['CORS_ALLOWED_ORIGINS'] = 'http://localhost:3000'

from api.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)