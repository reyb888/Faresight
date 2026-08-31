import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

_engine = None
_AsyncSessionLocal = None


def get_engine():
    global _engine, _AsyncSessionLocal
    if _engine is None:
        raw_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres.ladhxsgrucuunsdorfdf:Reyansh%40008@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres",
        ).strip()
        
        # Ensure postgresql+asyncpg prefix
        if raw_url.startswith("postgresql://"):
            raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        _engine = create_async_engine(
            raw_url,
            echo=False,
            pool_pre_ping=True,
        )
        _AsyncSessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine, _AsyncSessionLocal


async def get_session() -> AsyncSession:
    _, session_factory = get_engine()
    async with session_factory() as session:
        yield session