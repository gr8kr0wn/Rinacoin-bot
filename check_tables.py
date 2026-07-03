import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text


async def check():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        return

    sync_url = database_url.replace("+asyncpg", "")
    engine = create_async_engine(sync_url)
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
        )
        for row in result:
            print(row[0])
    await engine.dispose()


asyncio.run(check())
