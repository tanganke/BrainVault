"""BrainVault CLI entry-point.

Available commands:
    brainvault init     – Initialise a new vault in the current directory
    brainvault status   – Show the current vault configuration and DB stats
    brainvault migrate  – Migrate between storage / database backends
    brainvault serve    – Start the MCP server
    brainvault search   – Full-text search across wiki pages
    brainvault sync     – Sync all wiki pages into the database
"""

from __future__ import annotations

import sys

import click
from rich.console import Console

console = Console()


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(package_name="brainvault")
def cli() -> None:
    """BrainVault – Persistent State Infrastructure for the AI Era.

    A pluggable DB + Markdown hybrid knowledge operating system with
    first-class support for multiple database and storage backends.
    """


# ---------------------------------------------------------------------------
# `init` command
# ---------------------------------------------------------------------------


@cli.command("init")
@click.argument("path", default=".", type=click.Path())
@click.option("--db", "db_type", default="sqlite", type=click.Choice(["sqlite", "postgresql"]),
              show_default=True, help="Database backend to use.")
@click.option("--storage", "storage_type", default="local",
              type=click.Choice(["local", "s3"]), show_default=True,
              help="Storage backend to use.")
@click.option("--force", is_flag=True, default=False,
              help="Re-initialise even if the vault already exists.")
def init_command(path: str, db_type: str, storage_type: str, force: bool) -> None:
    """Initialise a new BrainVault at PATH (default: current directory)."""
    from brainvault.cli.init_cmd import run_init

    run_init(path=path, db_type=db_type, storage_type=storage_type, force=force)


# ---------------------------------------------------------------------------
# `status` command
# ---------------------------------------------------------------------------


@cli.command("status")
@click.argument("path", default=".", type=click.Path(exists=True))
def status_command(path: str) -> None:
    """Show the vault configuration and database statistics."""
    from brainvault.cli.status_cmd import run_status

    run_status(path=path)


# ---------------------------------------------------------------------------
# `migrate` command
# ---------------------------------------------------------------------------


@cli.command("migrate")
@click.option("--from", "from_backend", required=True,
              help="Source backend descriptor, e.g. sqlite-local or postgresql-s3.")
@click.option("--to", "to_backend", required=True,
              help="Destination backend descriptor, e.g. postgresql-s3 or sqlite-local.")
@click.option("--vault", "vault_path", default=".", type=click.Path(exists=True),
              help="Path to the vault root directory.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Show what would be migrated without making changes.")
def migrate_command(from_backend: str, to_backend: str, vault_path: str, dry_run: bool) -> None:
    """Migrate a vault between storage/database backends.

    Example:

        brainvault migrate --from sqlite-local --to postgresql-s3
    """
    from brainvault.cli.migrate_cmd import run_migrate

    run_migrate(
        vault_path=vault_path,
        from_backend=from_backend,
        to_backend=to_backend,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# `serve` command
# ---------------------------------------------------------------------------


@cli.command("serve")
@click.argument("path", default=".", type=click.Path(exists=True))
def serve_command(path: str) -> None:
    """Start the BrainVault MCP server for the vault at PATH."""
    import signal
    import time

    from brainvault.config import load_config
    from brainvault.factory import make_database, make_storage
    from brainvault.mcp.server import MCPServer

    cfg = load_config(path)
    storage = make_storage(cfg)
    db = make_database(cfg)
    db.initialize()
    server = MCPServer(config=cfg, storage=storage, db=db)
    server.start()
    console.print(f"[green]MCP server started[/green] → {server.socket_path}")
    console.print("Press Ctrl+C to stop.")

    def _stop(sig, frame):  # noqa: ANN001
        console.print("\n[yellow]Stopping MCP server…[/yellow]")
        server.stop()
        db.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    while True:
        time.sleep(1)


# ---------------------------------------------------------------------------
# `search` command
# ---------------------------------------------------------------------------


@cli.command("search")
@click.argument("query")
@click.option("--vault", "vault_path", default=".", type=click.Path(exists=True))
@click.option("--limit", default=10, show_default=True, help="Maximum results to return.")
def search_command(query: str, vault_path: str, limit: int) -> None:
    """Full-text search across all wiki pages."""
    from brainvault.config import load_config
    from brainvault.factory import make_database

    cfg = load_config(vault_path)
    db = make_database(cfg)
    db.initialize()
    if not hasattr(db, "search"):
        console.print("[red]Search is not supported by this database adapter.[/red]")
        sys.exit(1)
    rows = db.search(query, limit=limit)
    if not rows:
        console.print("[yellow]No results found.[/yellow]")
    else:
        for row in rows:
            console.print(f"[bold]{row['path']}[/bold]  {row.get('title', '')}")
    db.close()


# ---------------------------------------------------------------------------
# `sync` command
# ---------------------------------------------------------------------------


@cli.command("sync")
@click.argument("path", default=".", type=click.Path(exists=True))
def sync_command(path: str) -> None:
    """Sync all wiki pages in the vault into the database."""
    from brainvault.cli.sync_cmd import run_sync

    run_sync(vault_path=path)


if __name__ == "__main__":
    cli()
