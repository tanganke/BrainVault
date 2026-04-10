"""Implementation of ``brainvault sync``."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import track

console = Console()


def run_sync(vault_path: str = ".") -> None:
    """Walk all wiki pages and sync them into the database.

    Args:
        vault_path: Path to the vault root.
    """
    from brainvault.config import load_config
    from brainvault.factory import make_database, make_storage

    vault = Path(vault_path).resolve()
    cfg = load_config(vault)
    storage = make_storage(cfg)
    db = make_database(cfg)
    db.initialize()

    console.rule("[bold blue]BrainVault Sync[/bold blue]")

    wiki_paths = [p for p in storage.list("wiki/") if p.endswith(".md")]
    console.print(f"Found [bold]{len(wiki_paths)}[/bold] wiki pages to sync.")

    synced = 0
    errors = 0
    for fp in track(wiki_paths, description="Syncing"):
        try:
            content = storage.read(fp)
            if hasattr(db, "set_page_content"):
                db.set_page_content(content)
            db.sync_page(fp)
            synced += 1
        except Exception as exc:
            console.print(f"[yellow]warn[/yellow] {fp}: {exc}")
            errors += 1

    db.close()

    # Update state.json
    state_path = vault / ".brainvault" / "state.json"
    try:
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        state["last_sync"] = datetime.now(timezone.utc).isoformat()
        state["page_count"] = synced
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass

    console.print()
    console.print(f"[green]Synced[/green] {synced} pages, [red]{errors}[/red] errors.")
