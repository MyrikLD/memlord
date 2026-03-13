from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.config import settings
from mnemos.embeddings import embed
from mnemos.schemas import SearchResult


def fts5_escape(query: str) -> str:
    """Wrap each whitespace-separated token in double quotes to suppress FTS5 operator parsing."""
    tokens = query.split()
    return " ".join('"' + t.replace('"', "") + '"' for t in tokens if t)


async def hybrid_search(
    session: AsyncSession,
    query: str,
    limit: int | None = None,
    similarity_threshold: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[SearchResult]:
    n = (limit or settings.default_limit) * 4  # over-fetch before RRF cutoff
    k = settings.rrf_k
    threshold = (
        similarity_threshold
        if similarity_threshold is not None
        else settings.sim_threshold
    )

    date_filter = ""
    date_params: dict = {}
    if date_from:
        date_filter += " AND m.created_at >= :date_from"
        date_params["date_from"] = date_from
    if date_to:
        date_filter += " AND m.created_at <= :date_to"
        date_params["date_to"] = date_to

    # BM25 via FTS5
    bm25_sql = text(f"""
        SELECT m.id, m.content, m.memory_type,
               ROW_NUMBER() OVER (ORDER BY bm25(memories_fts)) AS bm25_rank
        FROM memories_fts
        JOIN memories m ON memories_fts.memory_id = m.id
        WHERE memories_fts MATCH :query {date_filter}
        ORDER BY bm25(memories_fts)
        LIMIT :n
    """)

    bm25_rows = (
        await session.execute(
            bm25_sql, {"query": fts5_escape(query), "n": n, **date_params}
        )
    ).fetchall()

    # Vector KNN via sqlite-vec
    vector = embed(query)
    vec_str = "[" + ",".join(str(v) for v in vector) + "]"

    vec_sql = text(f"""
        SELECT m.id, m.content, m.memory_type,
               v.distance,
               ROW_NUMBER() OVER (ORDER BY v.distance) AS vec_rank
        FROM memories_vec v
        JOIN memories m ON v.memory_id = m.id
        WHERE v.embedding MATCH :vec AND k = :n {date_filter}
        ORDER BY v.distance
        LIMIT :n
    """)

    vec_rows = (
        await session.execute(vec_sql, {"vec": vec_str, "n": n, **date_params})
    ).fetchall()

    # Build rank maps
    bm25_ranks: dict[int, int] = {row.id: row.bm25_rank for row in bm25_rows}
    vec_ranks: dict[int, int] = {row.id: row.vec_rank for row in vec_rows}
    vec_distances: dict[int, float] = {row.id: row.distance for row in vec_rows}
    contents: dict[int, tuple] = {
        row.id: (row.content, row.memory_type) for row in bm25_rows
    }
    contents.update({row.id: (row.content, row.memory_type) for row in vec_rows})

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
        # L2 distance on unit vectors → cosine similarity = 1 - dist²/2
        similarity = (1.0 - (distance**2) / 2) if distance is not None else None

        if similarity is not None and similarity < threshold:
            continue

        content, memory_type = contents[doc_id]
        scored.append(
            SearchResult(
                id=doc_id,
                content=content,
                memory_type=memory_type,
                rrf_score=rrf,
                vec_similarity=similarity,
            )
        )

    scored.sort(key=lambda r: r.rrf_score, reverse=True)
    return scored[: limit or settings.default_limit]
