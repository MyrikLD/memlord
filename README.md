# Memlord

Self-hosted MCP memory server with hybrid BM25 + semantic search, backed by PostgreSQL + pgvector.

## Features

- **Hybrid search** — BM25 (full-text) + vector KNN (pgvector) fused via Reciprocal Rank Fusion
- **Multi-user** — each user sees only their own memories; workspaces for shared team knowledge
- **8 MCP tools** — store, retrieve, recall, list, search by tag, get, update, delete
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
memlord
```

Open **http://localhost:8000** for the Web UI. The MCP endpoint is at `/mcp`.

## Docker

```bash
cp .env.example .env
docker compose up
```

## Configuration

All settings use the `MEMLORD_` prefix. See [`.env.example`](.env.example) for the full list.

| Variable                  | Default                                                   | Description                |
|---------------------------|-----------------------------------------------------------|----------------------------|
| `MEMLORD_DB_URL`           | `postgresql+asyncpg://postgres:postgres@localhost/memlord` | PostgreSQL connection URL  |
| `MEMLORD_PORT`             | `8000`                                                    | Server port                |
| `MEMLORD_BASE_URL`         | —                                                         | Public URL (enables OAuth) |
| `MEMLORD_OAUTH_JWT_SECRET` | `memlord-dev-secret-please-change`                         | JWT signing secret         |

OAuth is enabled when `MEMLORD_BASE_URL` is set. Without it, the server starts without authentication.

## MCP Tools

| Tool              | Description                                              |
|-------------------|----------------------------------------------------------|
| `store_memory`    | Save a memory (idempotent per workspace by content)      |
| `retrieve_memory` | Hybrid semantic + full-text search                       |
| `recall_memory`   | Search by natural-language time expression               |
| `list_memories`   | Paginated list with type/tag filters                     |
| `search_by_tag`   | AND/OR tag search                                        |
| `get_memory`      | Fetch a single memory by ID                              |
| `update_memory`   | Update content, type, tags, or metadata by ID            |
| `delete_memory`   | Delete by ID                                             |
| `list_workspaces` | List workspaces you are a member of (including personal) |

Workspace management (create, invite, join, leave) is handled via the Web UI.

## Development

```bash
pyright src/           # type check
black .                # format
pytest                 # run tests
alembic-autogen-check  # verify migrations are up to date
```

## License

Memlord is dual-licensed:

- **[AGPL-3.0](LICENSE)** — free for open-source use. If you run a modified version as a network service, you must publish your source code.
- **[Commercial License](LICENSE-COMMERCIAL)** — for proprietary or closed-source deployments. Contact myrik260138@gmail.com or 5783354@gmail.com to purchase.
