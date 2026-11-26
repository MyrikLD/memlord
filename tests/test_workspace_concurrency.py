import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from memlord.access import Principal, WorkspaceGrant
from memlord.dao import MemoryDao
from memlord.dao.user import UserDao
from memlord.dao.workspace import WorkspaceDao
from memlord.models.memory import Memory
from memlord.schemas import MemoryType


@pytest.mark.parametrize("operation", ["move", "edit"])
async def test_concurrent_move_preserves_workspace_boundary(test_db_url, operation):
    engine = create_async_engine(test_db_url)
    try:
        async with AsyncSession(engine) as owner, AsyncSession(engine) as agent:
            user = await UserDao(owner).create(f"{uuid4()}@example.org", "Owner", "unused")
            uid = user.id
            workspaces = WorkspaceDao(owner, uid)
            source = (await workspaces.get_personal()).id
            target = (await workspaces.create(f"target-{uid}")).id
            private = (await workspaces.create(f"private-{uid}")).id
            memories = MemoryDao(owner, uid)
            mid, _ = await memories.create(
                name="original", content="original", memory_type=MemoryType.fact,
                metadata={}, tags=set(), workspace_id=source, force=True,
            )
            await owner.commit()
            pid = await agent.scalar(text("select pg_backend_pid()"))
            restricted = MemoryDao(agent, Principal(uid, {
                source: WorkspaceGrant.write, target: WorkspaceGrant.write,
            }))
            await memories.move(mid, source, private)
            pending = asyncio.create_task(
                restricted.move(mid, source, target) if operation == "move"
                else restricted.update(mid, source, name="changed")
            )
            try:
                async with asyncio.timeout(10):
                    while not await owner.scalar(
                        text("select pg_backend_pid() = any(pg_blocking_pids(:pid))"), {"pid": pid}
                    ):
                        await asyncio.sleep(0.02)
                await owner.commit()
                with pytest.raises(ValueError, match="not found"):
                    await pending
                await agent.commit()
                row = (await owner.execute(
                    select(Memory.workspace_id, Memory.name).where(Memory.id == mid)
                )).one()
                assert tuple(row) == (private, "original")
            finally:
                await owner.rollback()
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    finally:
        await engine.dispose()
