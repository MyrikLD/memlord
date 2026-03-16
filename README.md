# Mnemos

Self-hosted MCP memory server with hybrid BM25 + semantic search, backed by PostgreSQL + pgvector.

## Features

- **Hybrid search** — BM25 (full-text) + vector KNN (pgvector) fused via Reciprocal Rank Fusion
- **7 MCP tools** — store, retrieve, recall, list, search by tag, delete, health check
- **Web UI** — browse, search, edit and delete memories in the browser; export/import JSON
- **OAuth 2.1** — optional, full in-process authorization server
- **PostgreSQL** — pgvector for embeddings, tsvector for full-text search

## Quickstart

```bash
# Install dependencies
uv sync --dev

# Download ONNX model (~23 MB)
uv run python scripts/download_model.py

# Run migrations
alembic upgrade head

# Start the server
mnemos
```

Open **http://localhost:8000** for the Web UI. The MCP endpoint is at `/mcp`.

## Docker

```bash
cp .env.example .env
docker compose up
```

## Configuration

All settings use the `MNEMOS_` prefix. See [`.env.example`](.env.example) for the full list.

| Variable                  | Default                                              | Description                     |
|---------------------------|------------------------------------------------------|---------------------------------|
| `MNEMOS_DB_URL`           | `postgresql+asyncpg://postgres:postgres@localhost/mnemos` | PostgreSQL connection URL  |
| `MNEMOS_PORT`             | `8000`                                               | Server port                     |
| `MNEMOS_BASE_URL`         | —                                                    | Public URL (required for OAuth) |
| `MNEMOS_OAUTH_JWT_SECRET` | —                                                    | Enables OAuth when set          |
| `MNEMOS_PASSWORD`         | —                                                    | Web UI login password           |

OAuth is enabled only when `MNEMOS_BASE_URL`, `MNEMOS_OAUTH_JWT_SECRET`, and `MNEMOS_PASSWORD` are all set.

## MCP Tools

| Tool                    | Description                                    |
|-------------------------|------------------------------------------------|
| `store_memory`          | Save a memory (idempotent by content)          |
| `retrieve_memory`       | Hybrid semantic + full-text search             |
| `recall_memory`         | Search by natural-language time expression     |
| `list_memories`         | Paginated list with type/tag filters           |
| `search_by_tag`         | AND/OR tag search                              |
| `delete_memory`         | Delete by ID                                   |
| `check_database_health` | DB stats and extension status                  |

## Development

```bash
pyright src/           # type check
black .                # format
pytest                 # run tests
alembic-autogen-check  # verify migrations are up to date
```
