import os

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from mnemos.config import settings
from mnemos.db import MCPSessionDep
from mnemos.models import Memory, SchemaVersion
from mnemos.schemas import HealthResult
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

mcp = FastMCP()


@mcp.tool(
    output_schema=HealthResult.model_json_schema(),
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def check_database_health(s: AsyncSession = MCPSessionDep) -> HealthResult:  # type: ignore[assignment]
    """Return database health status and statistics."""
    total = await s.scalar(select(func.count()).select_from(Memory)) or 0

    schema_version = await s.scalar(select(func.max(SchemaVersion.version)))

    vec_extension = await s.scalar(text("SELECT vec_version()"))
    await s.execute(text("SELECT COUNT(*) FROM memories_fts"))

    return HealthResult(
        status="ok",
        total_memories=total,
        db_path=str(settings.db_path),
        db_size_bytes=os.path.getsize(settings.db_path),
        schema_version=schema_version,
        vec_extension=vec_extension,
        fts_extension="fts5",
    )
