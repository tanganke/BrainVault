"""Implementation of ``brainvault status``."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()


def run_status(path: str = ".") -> None:
    """Print vault configuration and database statistics."""
    from brainvault.config import load_config
    from brainvault.factory import make_database

    vault = Path(path).resolve()
    console.rule("[bold blue]BrainVault Status[/bold blue]")

    # Load config
    try:
        cfg = load_config(vault)
    except Exception as exc:
        console.print(f"[red]Failed to load config:[/red] {exc}")
        return

    # Config table
    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Key", style="bold cyan")
    tbl.add_column("Value")
    tbl.add_row("Vault root", str(cfg.vault_root))
    tbl.add_row("Config version", cfg.version)
    tbl.add_row("Storage backend", cfg.storage.type)
    tbl.add_row("Database backend", cfg.database.type)
    tbl.add_row("LLM provider", cfg.llm.provider)
    tbl.add_row("LLM model", cfg.llm.model)
    tbl.add_row("MCP enabled", str(cfg.mcp.enabled))
    tbl.add_row("MCP socket", cfg.mcp.socket_path)
    console.print(tbl)

    # State file
    state_path = vault / ".brainvault" / "state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            console.print()
            console.print(f"Initialised : [bold]{state.get('initialized_at', 'unknown')}[/bold]")
            console.print(f"Last sync   : [bold]{state.get('last_sync', 'never')}[/bold]")
            console.print(f"Page count  : [bold]{state.get('page_count', 0)}[/bold]")
        except Exception:
            pass

    # DB stats
    try:
        db = make_database(cfg)
        db.initialize()
        rows = db.query("SELECT COUNT(*) AS n FROM pages")
        page_count = rows[0]["n"] if rows else 0
        console.print(f"\nDB pages    : [bold]{page_count}[/bold]")

        rows = db.query("SELECT COUNT(*) AS n FROM links")
        link_count = rows[0]["n"] if rows else 0
        console.print(f"DB links    : [bold]{link_count}[/bold]")
        db.close()
    except Exception as exc:
        console.print(f"\n[yellow]DB stats unavailable:[/yellow] {exc}")
