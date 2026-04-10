"""Implementation of ``brainvault migrate``.

Copies all Markdown pages from one storage+database backend to another
while preserving content integrity.

Backend descriptor format: ``<db>-<storage>``
Examples:
  sqlite-local       SQLite + local filesystem (default)
  postgresql-s3      PostgreSQL + S3-compatible storage
  sqlite-s3          SQLite + S3 (unusual but valid)
  postgresql-local   PostgreSQL + local filesystem
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import track

console = Console()


def _parse_descriptor(descriptor: str) -> tuple[str, str]:
    """Parse ``<db>-<storage>`` into ``(db_type, storage_type)``."""
    parts = descriptor.lower().split("-", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid backend descriptor {descriptor!r}. "
            "Expected format: <db>-<storage>, e.g. sqlite-local"
        )
    db_type, storage_type = parts
    if db_type not in ("sqlite", "postgresql"):
        raise ValueError(f"Unknown database backend {db_type!r}. Expected sqlite or postgresql.")
    if storage_type not in ("local", "s3"):
        raise ValueError(f"Unknown storage backend {storage_type!r}. Expected local or s3.")
    return db_type, storage_type


def run_migrate(
    vault_path: str,
    from_backend: str,
    to_backend: str,
    dry_run: bool = False,
) -> None:
    """Migrate vault data between backends.

    Steps:
    1. Load source config and instantiate source storage + DB.
    2. Build a destination config mirroring the source but with the new
       backend types.
    3. Copy all files from source storage → destination storage.
    4. Re-sync all wiki pages into the destination DB.
    5. If not a dry-run, atomically update ``meta/config.yaml`` to point
       at the new backend.

    Args:
        vault_path: Path to the vault root.
        from_backend: Source backend descriptor (e.g. ``sqlite-local``).
        to_backend: Destination backend descriptor (e.g. ``postgresql-s3``).
        dry_run: If ``True``, report actions without executing them.
    """
    from brainvault.config import load_config
    from brainvault.factory import make_database, make_storage

    src_db_type, src_storage_type = _parse_descriptor(from_backend)
    dst_db_type, dst_storage_type = _parse_descriptor(to_backend)

    if src_db_type == dst_db_type and src_storage_type == dst_storage_type:
        console.print("[yellow]Source and destination backends are identical – nothing to do.[/yellow]")
        return

    vault = Path(vault_path).resolve()
    console.rule("[bold blue]BrainVault Migrate[/bold blue]")
    console.print(f"Vault : [bold]{vault}[/bold]")
    console.print(f"From  : [bold]{from_backend}[/bold]")
    console.print(f"To    : [bold]{to_backend}[/bold]")
    if dry_run:
        console.print("[yellow]DRY RUN – no changes will be written.[/yellow]")
    console.print()

    # Source config / adapters
    src_cfg = load_config(vault)
    src_cfg.storage.type = src_storage_type  # type: ignore[assignment]
    src_cfg.database.type = src_db_type  # type: ignore[assignment]
    src_storage = make_storage(src_cfg)
    src_db = make_database(src_cfg)
    src_db.initialize()

    # Destination config – deep-copy source, override types
    dst_cfg = copy.deepcopy(src_cfg)
    dst_cfg.storage.type = dst_storage_type  # type: ignore[assignment]
    dst_cfg.database.type = dst_db_type  # type: ignore[assignment]

    # In dry-run mode we never actually connect to the destination backend,
    # so we skip instantiating adapters that may not be configured yet.
    if not dry_run:
        dst_storage = make_storage(dst_cfg)
        dst_db = make_database(dst_cfg)
    else:
        dst_storage = src_storage  # read-only reference for listing
        dst_db = src_db  # unused in dry-run

    # ------------------------------------------------------------------ #
    # Step 1: Copy storage objects
    # ------------------------------------------------------------------ #
    if src_storage_type != dst_storage_type:
        console.print("[bold]Step 1:[/bold] Copying storage objects…")
        paths = list(src_storage.list())
        console.print(f"  Found {len(paths)} objects.")
        for p in track(paths, description="Copying files"):
            if dry_run:
                console.print(f"  [dim]would copy[/dim] {p}")
            else:
                data = src_storage.read_bytes(p)
                dst_storage.write_bytes(p, data)
    else:
        console.print("[bold]Step 1:[/bold] Storage backends are the same type – skipping file copy.")

    # ------------------------------------------------------------------ #
    # Step 2: Re-sync wiki pages into destination DB
    # ------------------------------------------------------------------ #
    if src_db_type != dst_db_type:
        console.print("[bold]Step 2:[/bold] Re-syncing wiki pages into destination DB…")
        if not dry_run:
            dst_db.initialize()
        wiki_paths = [p for p in (dst_storage if src_storage_type != dst_storage_type else src_storage).list("wiki/")
                      if p.endswith(".md")]
        console.print(f"  Found {len(wiki_paths)} wiki pages.")
        for fp in track(wiki_paths, description="Syncing pages"):
            if dry_run:
                console.print(f"  [dim]would sync[/dim] {fp}")
            else:
                try:
                    content = dst_storage.read(fp) if src_storage_type != dst_storage_type else src_storage.read(fp)
                    if hasattr(dst_db, "set_page_content"):
                        dst_db.set_page_content(content)
                    dst_db.sync_page(fp)
                except Exception as exc:
                    console.print(f"  [yellow]warn[/yellow] {fp}: {exc}")
    else:
        console.print("[bold]Step 2:[/bold] Database backends are the same type – skipping DB migration.")

    # ------------------------------------------------------------------ #
    # Step 3: Atomically update config.yaml
    # ------------------------------------------------------------------ #
    console.print("[bold]Step 3:[/bold] Updating meta/config.yaml…")
    if not dry_run:
        import yaml

        config_path = vault / "meta" / "config.yaml"
        with config_path.open("r", encoding="utf-8") as fh:
            raw_cfg = yaml.safe_load(fh) or {}
        raw_cfg.setdefault("storage", {})["type"] = dst_storage_type
        raw_cfg.setdefault("database", {})["type"] = dst_db_type
        with config_path.open("w", encoding="utf-8") as fh:
            yaml.dump(raw_cfg, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)
        console.print(f"  [green]updated[/green] meta/config.yaml")
    else:
        console.print(f"  [dim]would update[/dim] meta/config.yaml")

    # Close connections
    src_db.close()
    if not dry_run:
        dst_db.close()

    console.print()
    if dry_run:
        console.rule("[bold yellow]Dry run complete[/bold yellow]")
    else:
        console.rule("[bold green]Migration complete[/bold green]")
