import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from ecommerce_ops.models.db import engine, Base, init_db

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created in SQLite.")
    try:
        await init_db()
        print("Initial demo seeds inserted.")
    except Exception as e:
        print("Seed warning:", e)

if __name__ == "__main__":
    asyncio.run(main())
