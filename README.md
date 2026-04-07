<p align="center">
  <img src="https://raw.githubusercontent.com/MyrikLD/memlord/refs/heads/main/media/logo.svg" alt="Self-hosted MCP memory server with hybrid BM25 + semantic search, backed by PostgreSQL +
pgvector" width="100%">
</p>

<h2 align="center">Self-hosted MCP memory server for personal use and teams</h4>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL%203.0-blue.svg" alt="License"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.12-brightgreen.svg" alt="Python"></a>
  <a href="https://github.com/MyrikLD/memlord/releases"><img src="https://img.shields.io/github/v/tag/MyrikLD/memlord?label=version&color=green" alt="Version"></a>
  <a href="https://github.com/modelcontextprotocol/servers"><img src="https://img.shields.io/badge/MCP-compatible-purple.svg" alt="MCP"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://glama.ai/mcp/servers/MyrikLD/memlord"><img src="https://glama.ai/mcp/servers/MyrikLD/memlord/badges/score.svg" alt="MCP score"></a>
</p>

<p align="center">
  <a href="#-quickstart">Quickstart</a> •
  <a href="#-how-it-works">How It Works</a> •
  <a href="#️-mcp-tools">MCP Tools</a> •
  <a href="#️-configuration">Configuration</a> •
  <a href="#-system-requirements">Requirements</a> •
  <a href="#-license">License</a>
</p>

---

## ✨ Features

- 🔍 **Hybrid search** — BM25 (full-text) + vector KNN (pgvector) fused via Reciprocal Rank Fusion
- 📂 **Multi-user** — each user sees only their own memories; workspaces for shared team knowledge
- 🛠️ **10 MCP tools** — store, retrieve, recall, list, search by tag, get, update, delete, move, list workspaces
- 🌐 **Web UI** — browse, search, edit and delete memories in the browser; export/import JSON
- 🔒 **OAuth 2.1** — full in-process authorization server, always enabled
- 🐘 **PostgreSQL** — pgvector for embeddings, tsvector for full-text search
- 📊 **Progressive disclosure** — search returns compact snippets by default; call `get_memory(id)` only for what you
  need, reducing token usage
- 🔁 **Deduplication** — automatically detects near-identical memories before saving, preventing noise accumulation

---

## 🆚 How Memlord compares

|                       | **Memlord**                                | [**OpenMemory**](https://github.com/mem0ai/mem0/tree/main/openmemory) | [**mcp-memory-service**](https://github.com/doobidoo/mcp-memory-service) | [**basic-memory**](https://github.com/basicmachines-co/basic-memory) |
|-----------------------|--------------------------------------------|-----------------------------------------------------------------------|--------------------------------------------------------------------------|----------------------------------------------------------------------|
| **Search**            | BM25 + vector + RRF                        | Vector only (Qdrant)                                                  | BM25 + vector + RRF                                                      | BM25 + vector                                                        |
| **Embeddings**        | Local ONNX, zero config                    | OpenAI default; Ollama optional                                       | Local ONNX, zero config                                                  | Local FastEmbed                                                      |
| **Storage**           | PostgreSQL + pgvector                      | PostgreSQL + Qdrant                                                   | SQLite-vec / Cloudflare Vectorize                                        | SQLite + Markdown files                                              |
| **Multi-user**        | ✅                                          | ❌ single-user in practice                                             | ⚠️ agent-ID scoping, no isolation                                        | ❌                                                                    |
| **Workspaces**        | ✅ shared + personal, invite links          | ⚠️ "Apps" namespace                                                   | ⚠️ tags + conversation_id                                                | ✅ per-project flag                                                   |
| **Authentication**    | ✅ OAuth 2.1                                | ❌ none (self-hosted)                                                  | ✅ OAuth 2.0 + PKCE                                                       | ❌                                                                    |
| **Web UI**            | ✅ browse, edit, export                     | ✅ Next.js dashboard                                                   | ✅ rich UI, graph viz, quality scores                                     | ❌ local; cloud only                                                  |
| **MCP tools**         | 10                                         | 5                                                                     | 15+                                                                      | ~20                                                                  |
| **Self-hosted**       | ✅ single process                           | ✅ Docker (3 containers)                                               | ✅                                                                        | ✅                                                                    |
| **Memory input**      | Manual (explicit store)                    | Auto-extracted by LLM                                                 | Manual                                                                   | Manual (Markdown notes)                                              |
| **Memory types**      | fact / preference / instruction / feedback | auto-extracted facts                                                  | —                                                                        | observations + wiki links                                            |
| **Time-aware search** | ✅ natural language dates                   | ⚠️ REST only, not in MCP tools                                        | —                                                                        | ✅ recent_activity                                                    |
| **Token efficiency**  | ✅ progressive disclosure                   | ❌                                                                     | —                                                                        | ✅ build_context traversal                                            |
| **Import / Export**   | ✅ JSON                                     | ✅ ZIP (JSON + JSONL)                                                  | —                                                                        | ✅ Markdown (human-readable)                                          |
| **License**           | AGPL-3.0 / Commercial                      | Apache 2.0                                                            | Apache 2.0                                                               | AGPL-3.0                                                             |

**Where competitors have a real edge:**

- **OpenMemory** — auto-extracts memories from raw conversation text; no need to decide what to store manually; good
  import/export
- **mcp-memory-service** — richer web UI (graph visualization, quality scoring, 8 tabs); more permissive license (Apache
  2.0); multiple transport options (stdio, SSE, HTTP)
- **basic-memory** — memories are human-readable Markdown files you can edit, version-control, and read without any
  server; wiki-style entity links form a local knowledge graph; ~20 MCP tools

**When to pick Memlord:**

- You want **zero-config local embeddings** — ONNX model ships with the server, no Ollama or external API needed
- You run a **multi-user team server** with proper OAuth 2.1 auth and invite-based workspaces
- You want a **production-grade database** (PostgreSQL) that scales beyond a single machine's SQLite
- You manage memories **explicitly** — store exactly what matters, typed and tagged, not everything the LLM decides to
  extract
- You want a **self-hosted Web UI** with full CRUD and JSON export, without a cloud subscription

---

## 🚀 Quickstart

### 🐳 Docker

```bash
cp .env.example .env
docker compose up
```

### HTTP server (multi-user, Web UI, OAuth)

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

### STDIO (local single-user, no OAuth)

STDIO mode runs the MCP server over stdin/stdout — no HTTP port, no OAuth. Ideal for local use with Claude Desktop or
Claude Code.

Set `MEMLORD_STDIO_USER_ID` to your user ID (created after first HTTP login, or `1` for a fresh DB) so all memories are
scoped to your account.

```bash
pip install memlord
```

Create `.mcp.json` and adjust the paths and env vars:

```json
{
  "mcpServers": {
    "memlord-local": {
      "command": "python",
      "args": [
        "memlord",
        "--stdio"
      ],
      "env": {
        "MEMLORD_DB_URL": "postgresql+asyncpg://postgres:postgres@localhost/memlord",
        "MEMLORD_STDIO_USER_ID": "1"
      }
    }
  }
}
```

---

## 🔍 How It Works

Each search request runs BM25 and vector KNN **in parallel**, then merges results via **Reciprocal Rank Fusion**:

```mermaid
flowchart TD
    Q([query]) --> BM25["BM25\nsearch_vector @@ websearch_to_tsquery"]
    Q --> EMB["ONNX embed\nall-MiniLM-L6-v2 · 384d · local"]
    EMB --> KNN["KNN\nembedding <=> query_vector\ncosine distance"]
    BM25 --> RRF["RRF fusion\nscore = 1/(k+rank_bm25) + 1/(k+rank_vec)\nk=60"]
    KNN --> RRF
    RRF --> R([top-N results])
```

---

## ⚙️ Configuration

All settings use the `MEMLORD_` prefix. See [`.env.example`](.env.example) for the full list.

| Variable                   | Default                                                    | Description                                       |
|----------------------------|------------------------------------------------------------|---------------------------------------------------|
| `MEMLORD_DB_URL`           | `postgresql+asyncpg://postgres:postgres@localhost/memlord` | PostgreSQL connection URL                         |
| `MEMLORD_PORT`             | `8000`                                                     | Server port                                       |
| `MEMLORD_BASE_URL`         | `http://localhost:8000`                                    | Public URL for OAuth (HTTP mode)                  |
| `MEMLORD_OAUTH_JWT_SECRET` | `memlord-dev-secret-please-change`                         | JWT signing secret (HTTP mode)                    |
| `MEMLORD_STDIO_USER_ID`    | —                                                          | User ID to use in STDIO mode (required for stdio) |

In HTTP mode, set `MEMLORD_BASE_URL` to your public URL and change `MEMLORD_OAUTH_JWT_SECRET` before deploying.
In STDIO mode, OAuth is skipped — set `MEMLORD_STDIO_USER_ID` to your numeric user ID instead.

---

## 🛠️ MCP Tools

| Tool              | Description                                                             |
|-------------------|-------------------------------------------------------------------------|
| `store_memory`    | Save a memory (idempotent by content); raises on near-duplicates        |
| `retrieve_memory` | Hybrid semantic + full-text search; returns snippets by default         |
| `recall_memory`   | Search by natural-language time expression; returns snippets by default |
| `list_memories`   | Paginated list with type/tag filters                                    |
| `search_by_tag`   | AND/OR tag search                                                       |
| `get_memory`      | Fetch a single memory by ID with full content                           |
| `update_memory`   | Update content, type, tags, or metadata by ID                           |
| `delete_memory`   | Delete by ID                                                            |
| `move_memory`     | Move a memory to a different workspace                                  |
| `list_workspaces` | List workspaces you are a member of (including personal)                |

Workspace management (create, invite, join, leave) is handled via the Web UI.

---

## 💻 System Requirements

- **Python** 3.12
- **PostgreSQL** ≥ 15 with [pgvector](https://github.com/pgvector/pgvector) extension
- **uv** — Python package manager

---

## 👨‍💻 Development

```bash
pyright src/           # type check
ruff format .          # format
pytest                 # run tests
alembic-autogen-check  # verify migrations are up to date
```

---

## 📄 License

Memlord is dual-licensed:

- **[AGPL-3.0](LICENSE)** — free for open-source use. If you run a modified version as a network service, you must
  publish your source code.
- **[Commercial License](LICENSE-COMMERCIAL)** — for proprietary or closed-source deployments. Contact
  sergey@memlord.com or dmitry@memlord.com to purchase.
