from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from mnemos.db import MCPSessionDep
from mnemos.embeddings import embed
from mnemos.models import Memory, MemoryTag, Tag
from mnemos.schemas import StoreResult
from sqlalchemy import insert, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

mcp = FastMCP()


@mcp.tool(
    output_schema=StoreResult.model_json_schema(),
    annotations=ToolAnnotations(idempotentHint=True, destructiveHint=False),
)
async def store_memory(
    content: str,
    memory_type: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    client_hostname: str | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
) -> StoreResult:
    """Save a new memory. Idempotent: returns existing if content already stored."""
    row = await s.execute(
        select(Memory.id, Memory.created_at).where(Memory.content == content)
    )
    existing = row.one_or_none()

    if existing is not None:
        memory_id, created_at = existing
        return StoreResult(id=memory_id, created_at=str(created_at), created=False)

    memory_id, created_at = (
        await s.execute(
            insert(Memory)
            .values(
                content=content,
                memory_type=memory_type,
                extra_data=metadata,
                client_hostname=client_hostname,
            )
            .returning(Memory.id, Memory.created_at)
        )
    ).one()

    # Embed and store in vec (no trigger for vec0, must use raw SQL)
    vector = embed(content)
    vec_str = "[" + ",".join(str(v) for v in vector) + "]"
    await s.execute(
        text("INSERT INTO memories_vec(memory_id, embedding) VALUES (:id, :vec)"),
        {"id": memory_id, "vec": vec_str},
    )

    # Upsert tags
    for tag_name in tags or []:
        normalized = tag_name.lower().strip()
        if not normalized:
            continue
        await s.execute(
            sqlite_insert(Tag).values(name=normalized).on_conflict_do_nothing()
        )
        tag_id = await s.scalar(select(Tag.id).where(Tag.name == normalized))
        await s.execute(
            sqlite_insert(MemoryTag)
            .values(memory_id=memory_id, tag_id=tag_id)
            .on_conflict_do_nothing()
        )

    return StoreResult(id=memory_id, created_at=str(created_at), created=True)
