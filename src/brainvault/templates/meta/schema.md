# BrainVault Schema – LLM Maintainer Instructions

This file defines the rules and conventions the LLM wiki-compiler must follow
when reading, writing, and maintaining the BrainVault knowledge base.

---

## Core Principles

1. **Raw sources are immutable.** Never modify anything under `raw/`.
2. **The wiki is the compounding asset.** Everything under `wiki/` is
   compiled, synthesised, and continually improved by the LLM.
3. **The database is derived.** The DB is always re-derivable from the
   Markdown in `wiki/`; treat it as a hot index, not a source of truth.
4. **Portability first.** Never hard-code filesystem paths, SQLite commands,
   or any backend-specific APIs.

---

## Backend Abstraction Rules (v1.1)

- **Never** hard-code filesystem paths or raw SQL dialects in compiled pages.
- Use the Storage Adapter and Database Adapter provided by the MCP server / CLI.
- For any file operation, call:
  - `storage.read(path)` / `storage.write(path, content)`
  - `storage.list(prefix)` / `storage.delete(path)`
  - `storage.exists(path)`
- For DB operations, always use the abstract SQL interface
  (same SQL works for both SQLite and PostgreSQL):
  - `db.execute("INSERT OR REPLACE INTO pages ...")`
  - `db.query("SELECT * FROM pages WHERE path=?", [path])`
  - `db.sync_page(filepath, content)` — preferred single-call shortcut

---

## Supported Database Backends

| Backend    | Use case                            | Notes                            |
|------------|-------------------------------------|----------------------------------|
| SQLite     | Personal / offline / zero-config    | Default; file at `db/brainvault.db` |
| PostgreSQL | Team / cloud / high-concurrency     | Connection string in `config.yaml` |

---

## Supported Storage Backends

| Backend | Use case                  | Notes                                         |
|---------|---------------------------|-----------------------------------------------|
| local   | Personal, Obsidian, git   | Standard filesystem; default                  |
| s3      | Cloud, team, large assets | S3-compatible (AWS, Tencent COS, MinIO, OSS)  |

When using S3, all Markdown and raw files are stored as objects.
Enable versioning on the bucket for full auditability.

---

## Wiki Directory Layout

```
wiki/
├── index.md         ← Master index of all topics
├── log.md           ← Chronological activity log
├── entities/        ← Named entities (people, orgs, products, …)
├── concepts/        ← Abstract ideas and definitions
├── sources/         ← Per-source summary pages
├── syntheses/       ← Cross-source insight documents
├── queries/         ← Saved research queries and their answers
└── orphans/         ← Incoming but not yet categorised pages
```

---

## Atomic Operations

After updating **any** Markdown file:

1. Write to the storage backend:
   ```
   storage.write("wiki/concepts/example.md", content)
   ```
2. Synchronise the database:
   ```
   db.sync_page("wiki/concepts/example.md", content)
   ```
   The adapter automatically updates:
   - the `pages` table,
   - the FTS index (`fts_pages` / `tsvector`),
   - the `links` back-link graph,
   - and (if configured) the `embeddings` table.

You **must** output in your response:
- Exact storage paths written
- Exact adapter calls made (or SQL executed)
- Any backend-specific logs or errors

---

## Page Frontmatter Convention

Every wiki page **should** begin with YAML frontmatter:

```yaml
---
title: "Human-Readable Title"
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

---

## Link Conventions

- Use `[[WikiLink]]` for internal cross-references between pages in the same vault.
- Use `[text](relative/path.md)` for relative Markdown links.
- Never use absolute filesystem paths in links.
- When referencing a source document, link to its summary page under
  `wiki/sources/` rather than directly to `raw/sources/`.

---

## FTS Search

Use the `db.search(query)` call to locate relevant pages before synthesising.
The query language is the native FTS syntax of the active backend:
- SQLite FTS5: `python AND ai`, `"exact phrase"`, `NOT deprecated`
- PostgreSQL: `plainto_tsquery` is used; plain English words work directly.
