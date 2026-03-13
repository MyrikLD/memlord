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
black src/ migrations/

# Run tests
pytest

# Run a single test
pytest tests/path/test_file.py::test_name -x
```

## Architecture

**Mnemos** is an MCP memory server with hybrid BM25 + vector search.

**Request path:** FastAPI app (root `/`) mounts FastMCP at `/mcp`. Single uvicorn process, single port. OAuth 2.1 is optional — enabled only when all three are set: `MCP_MEMORY_OAUTH_JWT_SECRET`, `MCP_MEMORY_OAUTH_PASSWORD`, `MCP_MEMORY_BASE_URL`.

**Search pipeline:** query → parallel BM25 (FTS5 `MATCH`) + vector KNN (sqlite-vec) → Reciprocal Rank Fusion (`rrf = 1/(k+rank_bm25) + 1/(k+rank_vec)`, k=60) → top-N.

**Embedding pipeline:** `content` → tokenizer.json → ONNX inference (all-MiniLM-L6-v2) → mean pooling with attention mask → L2 normalize → `float32[384]` stored in `memories_vec`.

**DB sync:** `memories_fts` (FTS5) is kept in sync with `memories` via SQL triggers (INSERT/UPDATE/DELETE). `memories_vec` is updated manually by the application on write (no trigger — vec0 doesn't support DML triggers).

## Key Conventions

**SQLAlchemy usage:** Core queries only — no ORM relationships (`relationship`), no lazy loading. Queries are written with `select()`, `insert()`, etc. Sessions used as async context managers via `session()` (general use) or `get_session()` (FastAPI dependency); explicit `commit()` on success, automatic `rollback()` on error.

**Model style:** Models are defined with `import sqlalchemy as sa` and classical `sa.Column(...)` — no `Mapped`, no `mapped_column`, no type annotations on columns, no `from __future__ import annotations`, no `__all__`.

**Alembic engine:** `migrations/env.py` uses a **synchronous** `create_engine("sqlite:///...")` (not aiosqlite). This is required because `AsyncAdapt_aiosqlite_connection` does not expose `enable_load_extension`, which is needed to load `sqlite-vec` during migrations.

**No logic in `__init__.py`:** All logic lives in dedicated modules. `__init__.py` files are re-exports only.

**Config prefix:** All env vars use `MCP_MEMORY_` prefix. `.env` file is supported

**ONNX model files** (`src/mnemos/onnx/model.onnx`, `tokenizer.json`) are committed to git — no runtime downloads.

## Project Layout

```
src/mnemos/
├── config.py          # pydantic-settings, MCP_MEMORY_* env vars
├── db.py              # async SQLAlchemy engine + sqlite-vec loader
├── embeddings.py      # ONNX session, tokenize, mean pool, L2 norm
├── search.py          # BM25 + vector KNN + RRF fusion
├── oauth.py           # custom OAuthProvider (fastmcp.server.auth)
├── main.py            # FastAPI app + mount MCP + uvicorn entrypoint
├── models/            # table definitions (no relationships)
├── schemas/           # Pydantic request/response schemas
├── tools/             # one file per MCP tool
└── onnx/              # model.onnx + tokenizer.json (committed)
migrations/
├── env.py             # sync engine for alembic
└── versions/
```
