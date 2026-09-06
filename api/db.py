import os
import sys
from pathlib import Path
import logging

logger = logging.getLogger("faresight.db")

# Ensure paths
root_dir = Path(__file__).resolve().parent.parent
api_dir = Path(__file__).resolve().parent
for p in (str(root_dir), str(api_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

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

        try:
            _engine = create_async_engine(
                raw_url,
                echo=False,
                poolclass=NullPool,
                connect_args={"statement_cache_size": 0, "timeout": 5},
            )
            _AsyncSessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
        except Exception as e:
            logger.error(f"Failed to initialize database engine: {e}")
            _engine = None
            _AsyncSessionLocal = None
            
    return _engine, _AsyncSessionLocal


async def get_session():
    _, session_factory = get_engine()
    if session_factory is None:
        yield None
        return
    try:
        async with session_factory() as session:
            yield session
    except Exception as e:
        logger.error(f"Session error: {e}")
        yield None