from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, bindparam, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.config import settings
from mnemos.embeddings import embed
from mnemos.models import Memory, MemoryTag, Tag
from mnemos.schemas import SearchResult


async def hybrid_search(
    session: AsyncSession,
    query: str,
    workspace_ids: list[int] | None = None,
    limit: int | None = None,
    similarity_threshold: float | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    memory_type: str | None = None,
) -> list[SearchResult]:
    n = (limit or settings.default_limit) * 4
    k = settings.rrf_k
    threshold = (
        similarity_threshold
        if similarity_threshold is not None
        else settings.sim_threshold
    )

    # Build access filter: all workspaces the user is a member of
    access = Memory.workspace_id.in_(workspace_ids or [])

    conditions = [access]
    if date_from:
        conditions.append(Memory.created_at >= date_from)
    if date_to:
        conditions.append(Memory.created_at <= date_to)
    if memory_type:
        conditions.append(Memory.memory_type == memory_type)

    # BM25 via PostgreSQL FTS
    tsquery = func.websearch_to_tsquery("simple", query)
    ts_rank_expr = func.ts_rank(Memory.search_vector, tsquery)
    bm25_rank = func.row_number().over(order_by=ts_rank_expr.desc()).label("bm25_rank")

    tag_match = (
        select(MemoryTag.memory_id)
        .join(Tag, MemoryTag.tag_id == Tag.id)
        .where(
            MemoryTag.memory_id == Memory.id,
            func.to_tsvector("simple", Tag.name).op("@@")(tsquery),
        )
        .exists()
    )

    bm25_q = (
        select(
            Memory.id,
            Memory.content,
            Memory.memory_type,
            Memory.workspace_id,
            bm25_rank,
        )
        .where(
            (Memory.search_vector.op("@@")(tsquery)) | tag_match,
            *conditions,
        )
        .order_by(ts_rank_expr.desc())
        .limit(n)
    )
    bm25_rows = (await session.execute(bm25_q)).fetchall()

    # Vector KNN via pgvector cosine distance
    vector = embed(query)
    vec_param = bindparam("vec", type_=Vector(384))
    distance = Memory.embedding.op("<=>", return_type=Float)(vec_param).label(
        "distance"
    )
    vec_rank = func.row_number().over(order_by=distance).label("vec_rank")

    vec_q = (
        select(
            Memory.id,
            Memory.content,
            Memory.memory_type,
            Memory.workspace_id,
            distance,
            vec_rank,
        )
        .where(Memory.embedding.isnot(None), *conditions)
        .order_by(distance)
        .limit(n)
    )
    vec_rows = (await session.execute(vec_q, {"vec": vector})).fetchall()

    # Build rank maps
    bm25_ranks: dict[int, int] = {row.id: row.bm25_rank for row in bm25_rows}
    vec_ranks: dict[int, int] = {row.id: row.vec_rank for row in vec_rows}
    vec_distances: dict[int, float] = {row.id: row.distance for row in vec_rows}
    contents: dict[int, tuple] = {
        row.id: (row.content, row.memory_type, row.workspace_id) for row in bm25_rows
    }
    contents.update(
        {row.id: (row.content, row.memory_type, row.workspace_id) for row in vec_rows}
    )

    # RRF fusion
    all_ids = set(bm25_ranks) | set(vec_ranks)
    scored: list[SearchResult] = []
    for doc_id in all_ids:
        rrf = 0.0
        if doc_id in bm25_ranks:
            rrf += 1.0 / (k + bm25_ranks[doc_id])
        if doc_id in vec_ranks:
            rrf += 1.0 / (k + vec_ranks[doc_id])

        distance = vec_distances.get(doc_id)
        # pgvector <=> is cosine distance: similarity = 1 - distance
        similarity = (1.0 - distance) if distance is not None else None

        # BM25 hits (content or tag match) are always included; threshold only
        # filters pure vec matches that lack any text/tag signal.
        if (
            doc_id not in bm25_ranks
            and similarity is not None
            and similarity < threshold
        ):
            continue

        content, memory_type, workspace_id = contents[doc_id]
        scored.append(
            SearchResult(
                id=doc_id,
                content=content,
                memory_type=memory_type,  # type: ignore[arg-type]
                workspace_id=workspace_id,
                rrf_score=rrf,
                vec_similarity=similarity,
            )
        )

    scored.sort(key=lambda r: r.rrf_score, reverse=True)
    return scored[: limit or settings.default_limit]
