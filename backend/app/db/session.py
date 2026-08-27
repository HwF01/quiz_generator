from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

_SQLITE = settings.database_url.startswith("sqlite")


def apply_sqlite_pragmas(dbapi_conn) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=not _SQLITE,
    connect_args={"timeout": 30} if _SQLITE else {},
)

if _SQLITE:

    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite(dbapi_conn, _connection_record) -> None:
        apply_sqlite_pragmas(dbapi_conn)


SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
