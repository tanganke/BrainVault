# BrainVault

> **The Persistent State Infrastructure for the AI Era**

BrainVault is an open, local-first **State Layer** that decouples your AI Agent's "brain" from any Runtime (Claude Code, Anthropic Desktop, future OS-native agents, etc.).

It turns the LLM Wiki pattern into a production-grade, **pluggable DB + Markdown hybrid knowledge operating system** with first-class support for multiple databases and storage backends.

---

## Core Principles

| Principle | Description |
|-----------|-------------|
| **LLM as wiki compiler** | The LLM acts as a tireless "wiki compiler", continuously improving the knowledge base. |
| **Immutable raw sources** | Files under `raw/` are never modified. |
| **Compiled wiki as asset** | Everything under `wiki/` is the compounding asset – synthesised, version-controlled, and portable. |
| **Backend-agnostic** | The same MCP server and CLI work regardless of whether you use SQLite + local FS or PostgreSQL + S3. |

---

## Multi-Backend Architecture

BrainVault 1.1 introduces a **pluggable abstraction layer** (`brainvault-core`) that handles all I/O:

```
┌──────────────────────────────────────────────────┐
│         LLM / MCP Server / CLI                   │
├────────────────────┬─────────────────────────────┤
│  StorageAdapter    │       DatabaseAdapter        │
├────────┬───────────┼──────────────┬──────────────┤
│ local  │    s3     │    sqlite    │  postgresql  │
│  (FS)  │ (AWS/COS/ │   (WAL +     │  (pooled,    │
│        │  MinIO…)  │   FTS5)      │   tsvector)  │
└────────┴───────────┴──────────────┴──────────────┘
```

| Use case | Storage | Database |
|----------|---------|----------|
| Personal / offline | `local` | `sqlite` (default) |
| Team / enterprise | `s3` | `postgresql` |
| Hybrid | `s3` | `sqlite` |

Switch backends at any time with one command:

```bash
brainvault migrate --from sqlite-local --to postgresql-s3
```

---

## Installation

```bash
# Core (SQLite + local FS only – zero extra dependencies)
pip install brainvault

# With S3 support (boto3)
pip install "brainvault[s3]"

# With PostgreSQL support (psycopg2)
pip install "brainvault[postgresql]"

# Everything
pip install "brainvault[all]"
```

Python ≥ 3.10 required.

---

## Quick Start

```bash
# 1. Create a new vault in the current directory
brainvault init .

# 2. (Optional) Edit meta/config.yaml to configure backends
#    Default: SQLite + local filesystem

# 3. Start the MCP server so your AI agent can access the vault
brainvault serve .

# 4. Open wiki/ in Obsidian for a rich editing experience
```

---

## Directory Structure

```
brainvault/                          # Vault root (git repo when using local FS)
├── raw/                             # Immutable source documents
│   ├── sources/                     # PDFs, Markdown, audio transcripts, …
│   └── assets/                      # Images and attachments
│
├── wiki/                            # Compiled Markdown knowledge base
│   ├── index.md                     # Master index
│   ├── log.md                       # Chronological activity log
│   ├── entities/                    # People, organisations, products
│   ├── concepts/                    # Abstract ideas and definitions
│   ├── sources/                     # Per-source summary pages
│   ├── syntheses/                   # Cross-source insight documents
│   ├── queries/                     # Saved research queries and answers
│   └── orphans/                     # Incoming, not yet categorised
│
├── db/                              # SQLite database (ignored for PostgreSQL)
│   └── brainvault.db
│
├── meta/                            # Configuration & rules (git-tracked)
│   ├── config.yaml                  # Backend configuration ← edit this
│   ├── schema.md                    # LLM maintainer instructions
│   ├── profile.json                 # Vault owner profile
│   ├── skills/
│   └── versions/
│
├── .brainvault/                     # Internal runtime state (not git-tracked)
│   ├── cache/
│   ├── mcp/
│   │   └── brainvault.sock          # Unix domain socket for MCP
│   └── state.json
│
├── .gitignore
├── .obsidian/
└── README.md
```

---

## Configuration (`meta/config.yaml`)

```yaml
version: "1.1"

# ====================== STORAGE BACKEND ======================
storage:
  type: "local"          # or "s3"
  local:
    root_path: "."
  s3:
    endpoint: "https://s3.ap-southeast-1.amazonaws.com"
    bucket: "my-brainvault"
    prefix: "brainvault/"
    access_key_id: ""    # or set env var BRAINVAULT_S3_ACCESS_KEY
    secret_access_key: "" # or set env var BRAINVAULT_S3_SECRET_KEY
    region: "ap-southeast-1"

# ====================== DATABASE BACKEND ======================
database:
  type: "sqlite"         # or "postgresql"
  sqlite:
    file_path: "db/brainvault.db"
    journal_mode: "wal"
  postgresql:
    host: "db.brainvault.example.com"
    port: 5432
    database: "brainvault"
    user: "brainvault_user"
    password: ""         # or set env var BRAINVAULT_DB_PASSWORD
    ssl_mode: "require"
    pool_size: 10

# ====================== LLM & MCP ======================
llm:
  provider: "openclaws"
  model: "claude-3.7-sonnet"
  temperature: 0.3

mcp:
  enabled: true
  socket_path: ".brainvault/mcp/brainvault.sock"
```

### Environment Variable Overrides

Sensitive values are **never** committed to git. Supply them via environment variables instead:

| Variable | Overrides |
|----------|-----------|
| `BRAINVAULT_DB_PASSWORD` | `database.postgresql.password` |
| `BRAINVAULT_S3_ACCESS_KEY` | `storage.s3.access_key_id` |
| `BRAINVAULT_S3_SECRET_KEY` | `storage.s3.secret_access_key` |

---

## CLI Reference

```
brainvault [OPTIONS] COMMAND [ARGS]...

Commands:
  init      Initialise a new vault
  status    Show vault configuration and DB statistics
  serve     Start the MCP server
  sync      Sync all wiki pages into the database
  search    Full-text search across wiki pages
  migrate   Migrate between storage/database backends
```

### `brainvault init`

```bash
brainvault init [PATH] [--db sqlite|postgresql] [--storage local|s3] [--force]
```

Creates the full directory skeleton, copies template files, patches
`meta/config.yaml` with the chosen backends, and initialises the database schema.

### `brainvault migrate`

```bash
brainvault migrate --from <src> --to <dst> [--vault PATH] [--dry-run]
```

Backend descriptor format: `<db>-<storage>` (e.g. `sqlite-local`, `postgresql-s3`).

```bash
# Local SQLite → cloud PostgreSQL + S3
brainvault migrate --from sqlite-local --to postgresql-s3

# Preview without making changes
brainvault migrate --from sqlite-local --to postgresql-s3 --dry-run
```

### `brainvault serve`

```bash
brainvault serve [PATH]
```

Starts the MCP server on the Unix socket at `.brainvault/mcp/brainvault.sock`.
LLMs and AI agents connect to this socket using JSON-RPC 2.0.

### `brainvault sync`

```bash
brainvault sync [PATH]
```

Walks all `wiki/*.md` files and upserts them into the database (pages table,
FTS index, and back-links graph).

### `brainvault search`

```bash
brainvault search QUERY [--vault PATH] [--limit N]
```

Full-text search across all indexed wiki pages.

---

## MCP Protocol

The MCP server accepts newline-delimited JSON-RPC 2.0 messages over a Unix
domain socket.  All methods use **named parameters**.

### Storage methods

| Method | Params | Returns |
|--------|--------|---------|
| `storage.read` | `path` | `{content: str}` |
| `storage.write` | `path`, `content` | `{ok: true}` |
| `storage.list` | `prefix?` | `{paths: [str]}` |
| `storage.delete` | `path` | `{ok: true}` |
| `storage.exists` | `path` | `{exists: bool}` |

### Database methods

| Method | Params | Returns |
|--------|--------|---------|
| `db.execute` | `sql`, `params?` | `{ok: true}` |
| `db.query` | `sql`, `params?` | `{rows: [{...}]}` |
| `db.sync_page` | `filepath`, `content` | `{ok: true}` |
| `db.search` | `query`, `limit?` | `{rows: [{path, title, rank}]}` |

### Vault methods

| Method | Params | Returns |
|--------|--------|---------|
| `vault.ping` | – | `{pong: true}` |
| `vault.status` | – | `{version, storage_type, db_type, socket_path}` |

**Example (Python client):**

```python
import socket, json

def mcp_call(sock_path, method, **params):
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(sock_path)
        s.sendall(req.encode() + b"\n")
        return json.loads(s.makefile().readline())

sock = ".brainvault/mcp/brainvault.sock"
mcp_call(sock, "storage.write", path="wiki/hello.md", content="# Hello\n")
mcp_call(sock, "db.sync_page",  filepath="wiki/hello.md", content="# Hello\n")
rows = mcp_call(sock, "db.search", query="Hello")
```

---

## Database Schema

The same schema is used for both SQLite and PostgreSQL.

```sql
-- Core content table
CREATE TABLE pages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,  -- SERIAL for PostgreSQL
    path       TEXT NOT NULL UNIQUE,
    title      TEXT NOT NULL DEFAULT '',
    content    TEXT NOT NULL DEFAULT '',
    checksum   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

-- Named entities extracted from pages
CREATE TABLE entities (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id  INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    name     TEXT NOT NULL,
    type     TEXT NOT NULL DEFAULT 'unknown',
    UNIQUE(page_id, name)
);

-- Back-link graph
CREATE TABLE links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    target_path TEXT NOT NULL,
    UNIQUE(source_path, target_path)
);

-- Full-text search (SQLite FTS5 / PostgreSQL tsvector)
```

---

## Python API

```python
from brainvault.config import load_config
from brainvault.factory import make_storage, make_database

cfg = load_config("/path/to/vault")
storage = make_storage(cfg)
db = make_database(cfg)
db.initialize()

# Write a wiki page
storage.write("wiki/concepts/agent.md", "# Agent\n\nAn autonomous AI agent…")

# Sync it into the database
db.set_page_content("# Agent\n\nAn autonomous AI agent…")
db.sync_page("wiki/concepts/agent.md")

# Full-text search
results = db.search("autonomous agent")

# List all wiki pages
for path in storage.list("wiki/"):
    print(path)

db.close()
```

---

## Development

```bash
# Clone and install with all dev dependencies
git clone https://github.com/tanganke/BrainVault.git
cd BrainVault
pip install -e ".[dev,all]"

# Run tests
pytest

# Lint
ruff check src/ tests/
```

---

## Roadmap

- [ ] `brainvault import` – ingest PDFs, web pages, and audio transcripts into `raw/`
- [ ] Embedding backend (`pgvector`, `sqlite-vss`) for semantic search
- [ ] Entity extraction pipeline
- [ ] Web UI (read-only Markdown browser)
- [ ] Docker Compose stack (PostgreSQL + MinIO + BrainVault)
- [ ] GitHub Actions workflow for scheduled `auto_lint`

---

## License

MIT – see [LICENSE](LICENSE).
