"""Re-embed all memories after changing the embedding model.

Run after downloading the new model:
    uv run python scripts/download_model.py
    uv run python scripts/reembed.py
"""

import asyncio

import sqlalchemy as sa

from memlord.db import get_engine
from memlord.embeddings import embed
from memlord.models import Memory


async def main() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (await conn.execute(sa.select(Memory.id, Memory.content))).fetchall()

    print(f"Re-embedding {len(rows)} memories...")

    async with engine.begin() as conn:
        for i, (memory_id, content) in enumerate(rows, 1):
            vector = await embed(content)
            await conn.execute(
                sa.update(Memory).where(Memory.id == memory_id).values(embedding=vector)
            )
            print(f"  [{i}/{len(rows)}] id={memory_id}")

    print("Done.")


asyncio.run(main())
