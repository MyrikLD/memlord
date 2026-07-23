from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.schemas.tools import DreamReport, ExpiryItem, SimilarPair

mcp = FastMCP()


@mcp.tool(
    output_schema=DreamReport.model_json_schema(),
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def dream_report(
    workspace: str | None = Field(
        None,
        description="Limit the report to one workspace (must have write access). "
        "Omit to cover all write-accessible workspaces.",
    ),
    similarity_threshold: float = Field(
        0.6,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity for a pair of memories to be reported.",
    ),
    max_pairs: int = Field(20, ge=1, le=100),
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> DreamReport:
    """Candidates for memory consolidation: similar pairs, expired and expiring memories.

    Read-only. The report only proposes candidates — reviewing and acting on them
    (merge, supersede, extend, delete) is done via the regular memory tools.
    Similar pairs are always within a single workspace, ordered by similarity.
    Use the `dream` prompt for the full guided consolidation procedure.
    """
    ws_id: int | None = None
    if workspace is not None:
        ws = await WorkspaceDao(s, uid).get_by_name(workspace)
        if ws is None:
            raise ValueError(f"Workspace {workspace!r} not found")
        ws_id = ws.id

    dao = MemoryDao(s, uid)
    pairs = await dao.similar_pairs(
        workspace_id=ws_id, similarity_threshold=similarity_threshold, limit=max_pairs
    )
    expired, expiring_soon = await dao.expiry_report(workspace_id=ws_id)

    return DreamReport(
        similar_pairs=[SimilarPair(**p) for p in pairs],
        expired=[ExpiryItem(**e) for e in expired],
        expiring_soon=[ExpiryItem(**e) for e in expiring_soon],
    )


@mcp.prompt(name="dream")
def dream(workspace: str | None = None) -> str:
    """Guided memory consolidation pass: review similar, conflicting and expiring memories."""
    scope = f'workspace="{workspace}"' if workspace else "all write-accessible workspaces"
    return f"""Run a memory consolidation pass ("dream") over {scope}.

1. Call dream_report({f'workspace="{workspace}"' if workspace else ""}) to get candidates:
   similar memory pairs, expired memories, and memories expiring soon.

2. Group similar pairs by topic and work through one topic at a time. Never combine
   memories from unrelated topics in a single operation.

3. For each pair, fetch both memories in full with get_memory(name, workspace) and classify:
   - EXACT DUPLICATE - same information: keep the richer memory, delete the other
     with delete_memory.
   - COMPLEMENTARY - same topic, different details: create one consolidated memory via
     store_memory with memory_type="insight" and metadata={{"sources": [<source names>]}},
     then retire the sources by setting expires_at about 30 days ahead with update_memory.
     Do not delete the sources immediately.
   - CONFLICT - the memories contradict each other: keep the newer one active and retire
     the superseded one via expires_at, recording what it superseded in the newer memory's
     metadata. If it is unclear which is current, leave both untouched and report the
     conflict to the user.
   - UNRELATED - similarity is incidental: leave both untouched.

4. Before every write, verify the operation against three checks:
   - coverage: no information from the sources is lost;
   - preservation: no valid memory is deleted or distorted without justification;
   - faithfulness: the new content is fully grounded in the sources - nothing invented.
   If any check is uncertain, skip the operation. A skipped merge costs nothing;
   a wrong merge corrupts memory permanently.

5. For expiring-soon memories that are still valuable, extend expires_at.
   List expired memories to the user and let them decide about purging - do not
   mass-delete them yourself.

6. Finish with a short report: what was merged, superseded, extended, skipped, and
   any conflicts left for the user to resolve."""
