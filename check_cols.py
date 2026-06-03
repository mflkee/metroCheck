import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def chk():
    db = AsyncSessionLocal()
    r = await db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='protocol_files'"))
    cols = [row[0] for row in r]
    print(cols)
    print("raw_text:", "raw_text" in cols)
    await db.close()

asyncio.run(chk())
