# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync --dev

# Run migrations
alembic upgrade head

# Create a new migration (autogenerate)
alembic revision --autogenerate -m "description"

# Check migrations are up to date (CI)
alembic-autogen-check

# Run the server
mnemos

# Type check
pyright src/

# Format
black .

# Run tests
pytest

# Run a single test
pytest tests/path/test_file.py::test_name -x
```

## Architecture

**Mnemos** is an MCP memory server with hybrid BM25 + vector search, backed by PostgreSQL + pgvector.

**Request path:** FastAPI app (root `/`) mounts FastMCP at `/mcp`. Single uvicorn process, single port. OAuth 2.1 is optional — enabled only when all three are set: `MNEMOS_OAUTH_JWT_SECRET`, `MNEMOS_OAUTH_PASSWORD`, `MNEMOS_BASE_URL`.

**Search pipeline:** query → parallel BM25 (`search_vector @@ websearch_to_tsquery`) + vector KNN (`embedding <=>`, cosine distance) → Reciprocal Rank Fusion (`rrf = 1/(k+rank_bm25) + 1/(k+rank_vec)`, k=60) → top-N.

**Embedding pipeline:** `content` → tokenizer.json → ONNX inference (all-MiniLM-L6-v2) → mean pooling with attention mask → L2 normalize → `float32[384]` stored as `vector(384)` column in `memories`.

**DB sync:** `search_vector` is a `TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED` computed column — updated automatically by PostgreSQL. `embedding` is updated manually by the application on write.

## Key Conventions

**SQLAlchemy usage:** Core queries only — no ORM relationships (`relationship`), no lazy loading. Queries are written with `select()`, `insert()`, etc. Use `sa.text()` only for PostgreSQL-specific syntax that cannot be expressed via Core. Use `.mappings().all()` for multi-column row results — access by column name, not index. Sessions used as async context managers via `session()` (general use) or `SessionDep` (FastAPI dependency). **Never call `commit()` or `rollback()` manually** — `session()` commits on success and rolls back on exception automatically.

**Vector parameters:** Pass `list[float]` directly — `Vector(384).bind_processor` converts to `'[v1,v2,...]'` string, asyncpg sends as text, PostgreSQL casts server-side. Do NOT use `register_vector` (causes codec conflict with bind_processor). Do NOT manually format vec strings.

**FastMCP tool structure:** Each tool file defines its own `mcp = FastMCP()` and registers tools with `@mcp.tool`. `tools/__init__.py` re-exports each `mcp` instance. `server.py` mounts them via `mcp.mount()`. Sessions injected via `s: AsyncSession = SessionDep  # type: ignore[assignment]` using `fastmcp.dependencies.Depends`.

**Model style:** Models are defined with `import sqlalchemy as sa` and classical `sa.Column(...)` — no `Mapped`, no `mapped_column`, no type annotations on columns, no `from __future__ import annotations`, no `__all__`.

**Structured data:** Use Pydantic `BaseModel` for structured objects — no `dataclass`.

**Alembic engine:** `migrations/env.py` uses `create_async_engine` with asyncpg and runs migrations via `asyncio.run()`. No sync driver needed — pgvector is a server-side extension, no client-side loading required.

**No logic in `__init__.py`:** All logic lives in dedicated modules. `__init__.py` files are re-exports only.

**Config prefix:** All env vars use `MNEMOS_` prefix. `.env` file is supported.

**ONNX model files** (`src/mnemos/onnx/model.onnx`, `tokenizer.json`) are excluded from git. Download before running: `uv run python scripts/download_model.py`. Downloaded from `sentence-transformers/all-MiniLM-L6-v2` on HuggingFace.

## Project Layout

```
src/mnemos/
├── config.py          # pydantic-settings, MNEMOS_* env vars
├── db.py              # async SQLAlchemy engine (asyncpg)
├── embeddings.py      # ONNX session, tokenize, mean pool, L2 norm
├── search.py          # BM25 + vector KNN + RRF fusion (PostgreSQL Core queries)
├── oauth.py           # custom OAuthProvider (fastmcp.server.auth)
├── main.py            # FastAPI app + mount MCP + uvicorn entrypoint
├── models/            # table definitions (no relationships)
├── schemas/           # Pydantic request/response schemas
├── tools/             # one file per MCP tool
├── ui/                # web UI (FastAPI routers)
│   ├── __init__.py    # assembles ui_router from sub-routers
│   ├── base.py        # pages: index, search, memory detail, update, delete
│   ├── data.py        # export/import JSON (uses ImportItem schema)
│   ├── login.py       # login form (GET/POST /ui/login)
│   └── utils.py       # templates, session_token, require_auth
└── onnx/              # model.onnx + tokenizer.json (committed)
migrations/
├── env.py             # async alembic env (asyncpg)
└── versions/          # migrations
```
