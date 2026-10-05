"""Hybrid search: full-text + vector, fused with RRF.

- FTS uses the 'memlord' text search config (zhparser if available, else 'simple').
- Query terms are OR-combined (single-char CJK terms dropped when longer terms exist).
- search_vector = setweight(name,'A') || setweight(content,'B'); ts_rank weights title higher.
- Title boost applied after RRF fusion (exact name match >> partial name match).
- Each SearchResult carries a ~160-char snippet centred on the first matched term.
"""

import re
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, bindparam, cast, func, literal, or_, select, text
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.config import settings
from memlord.embeddings import embed
from memlord.filters import not_expired
from memlord.fts import TS_CONFIG
from memlord.models import Memory, MemoryTag, Tag
from memlord.models.workspace import Workspace
from memlord.schemas import MemoryType, SearchResult

SNIPPET_LEN = 160
EXACT_NAME_BOOST = 1.0
PARTIAL_NAME_BOOST = 0.02

_LEXEME_RE = re.compile(r"'((?:[^']|'')*)'")
_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def _is_single_cjk(term: str) -> bool:
    return len(term) == 1 and bool(_CJK_RE.match(term))


async def _query_terms(session: AsyncSession, query: str) -> list[str]:
    """Tokenize the query with the same parser used for the index."""
    if not query or not query.strip():
        return []
    raw = await session.scalar(
        text("SELECT plainto_tsquery(CAST(:cfg AS regconfig), :q)::text"),
        {"cfg": TS_CONFIG, "q": query},
    )
    terms: list[str] = []
    for m in _LEXEME_RE.finditer(raw or ""):
        t = m.group(1).replace("''", "'")
        if t and t not in terms:
            terms.append(t)
    multi = [t for t in terms if not _is_single_cjk(t)]
    return multi if multi else terms


def _or_tsquery_text(terms: list[str]) -> str:
    return " | ".join("'" + t.replace("'", "''") + "'" for t in terms)


def make_snippet(content: str, terms: list[str], length: int = SNIPPET_LEN) -> str:
    if not content:
        return ""
    lower = content.lower()
    pos = -1
    hit_len = 0
    for t in sorted(terms, key=len, reverse=True):
        i = lower.find(t.lower())
        if i != -1 and (pos == -1 or i < pos):
            pos, hit_len = i, len(t)
    if pos == -1:
        snippet = content[:length]
        return snippet + ("…" if len(content) > length else "")
    start = max(0, pos + hit_len // 2 - length // 2)
    end = min(len(content), start + length)
    start = max(0, end - length)
    snippet = content[start:end].replace("\n", " ")
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(content) else "")


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
    threshold = similarity_threshold if similarity_threshold is not None else settings.sim_threshold

    # Build access filter: all workspaces the user is a member of
    access = Memory.workspace_id.in_(workspace_ids or [])

    conditions = [access, not_expired()]
    if date_from:
        conditions.append(Memory.created_at >= date_from)
    if date_to:
        conditions.append(Memory.created_at <= date_to)
    if memory_type:
        conditions.append(Memory.memory_type == memory_type)

    terms = await _query_terms(session, query)

    cols = (
        Memory.id,
        Memory.name,
        Memory.content,
        Memory.memory_type,
        Memory.workspace_id,
        Workspace.name.label("workspace"),
    )

    # Full-text with OR semantics
    bm25_rows = []
    if terms:
        tsquery = cast(literal(_or_tsquery_text(terms)), TSQUERY)
        ts_rank_expr = func.ts_rank(Memory.search_vector, tsquery)
        bm25_rank = func.row_number().over(order_by=ts_rank_expr.desc()).label("bm25_rank")

        tag_match = (
            select(MemoryTag.memory_id)
            .join(Tag, MemoryTag.tag_id == Tag.id)
            .where(
                MemoryTag.memory_id == Memory.id,
                func.to_tsvector(TS_CONFIG, Tag.name).op("@@")(tsquery),
            )
            .exists()
        )

        bm25_q = (
            select(*cols, bm25_rank)
            .join(Workspace, Memory.workspace_id == Workspace.id)
            .where(
                (Memory.search_vector.op("@@")(tsquery)) | tag_match,
                *conditions,
            )
            .order_by(ts_rank_expr.desc())
            .limit(n)
        )
        bm25_rows = (await session.execute(bm25_q)).fetchall()

    # Name matches (exact / contains / contained-in), so title hits are always candidates
    name_rows = []
    qn = _norm(query or "")
    if qn:
        name_norm = func.lower(func.regexp_replace(Memory.name, r"\s+", "", "g"))
        name_q = (
            select(*cols)
            .join(Workspace, Memory.workspace_id == Workspace.id)
            .where(
                or_(
                    name_norm == qn,
                    name_norm.contains(qn, autoescape=True),
                    func.strpos(literal(qn), name_norm) > 0,
                ),
                func.length(name_norm) >= 2,
                *conditions,
            )
            .limit(n)
        )
        name_rows = (await session.execute(name_q)).fetchall()

    # Vector KNN via pgvector cosine distance
    vector = await embed(query)
    vec_param = bindparam("vec", type_=Vector(384))
    distance = Memory.embedding.op("<=>", return_type=Float)(vec_param).label("distance")
    vec_rank = func.row_number().over(order_by=distance).label("vec_rank")

    vec_q = (
        select(*cols, distance, vec_rank)
        .join(Workspace, Memory.workspace_id == Workspace.id)
        .where(Memory.embedding.isnot(None), *conditions)
        .order_by(distance)
        .limit(n)
    )
    vec_rows = (await session.execute(vec_q, {"vec": vector})).fetchall()

    # Build rank maps
    bm25_ranks: dict[int, int] = {row.id: row.bm25_rank for row in bm25_rows}
    vec_ranks: dict[int, int] = {row.id: row.vec_rank for row in vec_rows}
    vec_distances: dict[int, float] = {row.id: row.distance for row in vec_rows}
    contents: dict[int, tuple[str, str, MemoryType, str, int]] = {}
    for rows in (bm25_rows, name_rows, vec_rows):
        for row in rows:
            contents[row.id] = (
                row.name,
                row.content,
                row.memory_type,
                row.workspace,
                row.workspace_id,
            )

    # Title boost map
    name_boost: dict[int, float] = {}
    for doc_id, (name, *_rest) in contents.items():
        nn = _norm(name)
        if not qn or len(nn) < 2:
            continue
        if nn == qn:
            name_boost[doc_id] = EXACT_NAME_BOOST
        elif qn in nn or nn in qn:
            name_boost[doc_id] = PARTIAL_NAME_BOOST

    # RRF fusion + title boost
    all_ids = set(bm25_ranks) | set(vec_ranks) | set(name_boost)
    scored: list[SearchResult] = []
    for doc_id in all_ids:
        rrf = 0.0
        if doc_id in bm25_ranks:
            rrf += 1.0 / (k + bm25_ranks[doc_id])
        if doc_id in vec_ranks:
            rrf += 1.0 / (k + vec_ranks[doc_id])
        rrf += name_boost.get(doc_id, 0.0)

        distance = vec_distances.get(doc_id)
        # pgvector <=> is cosine distance: similarity = 1 - distance
        similarity = (1.0 - distance) if distance is not None else None

        # Text/tag/title hits are always included; threshold only filters pure vec
        # matches that lack any text/tag/title signal.
        if (
            doc_id not in bm25_ranks
            and doc_id not in name_boost
            and similarity is not None
            and similarity < threshold
        ):
            continue

        name, content, memory_type, workspace, workspace_id = contents[doc_id]
        scored.append(
            SearchResult(
                id=doc_id,
                name=name,
                content=content,
                memory_type=memory_type,  # type: ignore[arg-type]
                workspace=workspace,
                workspace_id=workspace_id,
                rrf_score=rrf,
                vec_similarity=similarity,
                snippet=make_snippet(content, terms),
            )
        )

    scored.sort(key=lambda r: r.rrf_score, reverse=True)
    return scored[: limit or settings.default_limit]
