import asyncio, asyncpg

async def check():
    conn = await asyncpg.connect(
        user='postgres.wxggbdhaguoexbcweoel',
        password='@Teenwolf1234',
        host='aws-0-eu-west-1.pooler.supabase.com',
        port=5432,
        database='postgres'
    )
    rows = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    for r in rows:
        print(r['table_name'])
    await conn.close()

asyncio.run(check())
