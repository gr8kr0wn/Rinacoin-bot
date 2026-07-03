from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from bot.config import settings
from bot.db.models import Base


def _get_engine(url: str | None = None):
    url = url or settings.database_url
    if not url:
        return None
    return create_async_engine(url, echo=settings.node_env == "development")


def _get_session_maker(url: str | None = None):
    engine = _get_engine(url)
    if engine is None:
        return None
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


_session_maker = None


def get_async_session() -> async_sessionmaker[AsyncSession]:
    global _session_maker
    if _session_maker is None:
        _session_maker = _get_session_maker()
    if _session_maker is None:
        raise RuntimeError("Database not configured. Set DATABASE_URL in .env or environment.")
    return _session_maker


async def init_db(url: str | None = None):
    engine = _get_engine(url)
    if engine is None:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
