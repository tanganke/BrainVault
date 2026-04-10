"""Implementation of ``brainvault init``."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

# Sub-directories to create inside the vault root
_VAULT_DIRS = [
    "raw/sources",
    "raw/assets",
    "wiki/entities",
    "wiki/concepts",
    "wiki/sources",
    "wiki/syntheses",
    "wiki/queries",
    "wiki/orphans",
    "db",
    "meta/skills",
    "meta/versions",
    ".brainvault/cache",
    ".brainvault/mcp",
    ".obsidian",
]

# Templates to copy: (template_relative_path, destination_relative_path)
_COPY_MAP = [
    ("meta/config.yaml", "meta/config.yaml"),
    ("meta/schema.md", "meta/schema.md"),
    ("meta/profile.json", "meta/profile.json"),
    ("wiki/index.md", "wiki/index.md"),
    ("wiki/log.md", "wiki/log.md"),
    (".brainvault/state.json", ".brainvault/state.json"),
    ("gitignore", ".gitignore"),
    (".obsidian/app.json", ".obsidian/app.json"),
]


def _template_dir() -> Path:
    """Return the path to the bundled templates directory."""
    try:
        # Python 3.9+: use importlib.resources.files
        pkg = resources.files("brainvault") / "templates"
        # Materialise the path (works for both installed and editable installs)
        return Path(str(pkg))
    except AttributeError:
        # Fallback for older Python
        import brainvault

        return Path(brainvault.__file__).parent / "templates"


def run_init(
    path: str = ".",
    db_type: str = "sqlite",
    storage_type: str = "local",
    force: bool = False,
) -> None:
    """Initialise a new BrainVault vault.

    Args:
        path: Target directory (created if it does not exist).
        db_type: ``"sqlite"`` or ``"postgresql"``.
        storage_type: ``"local"`` or ``"s3"``.
        force: If ``True``, skip the already-initialised guard.
    """
    vault = Path(path).resolve()
    state_file = vault / ".brainvault" / "state.json"

    if state_file.exists() and not force:
        console.print(
            f"[yellow]Vault already initialised at[/yellow] {vault}\n"
            "Use [bold]--force[/bold] to reinitialise."
        )
        return

    console.rule("[bold blue]BrainVault Init[/bold blue]")
    console.print(f"Vault root : [bold]{vault}[/bold]")
    console.print(f"DB backend : [bold]{db_type}[/bold]")
    console.print(f"Storage    : [bold]{storage_type}[/bold]")
    console.print()

    # 1. Create directory skeleton
    for rel in _VAULT_DIRS:
        d = vault / rel
        d.mkdir(parents=True, exist_ok=True)
        console.print(f"  [dim]mkdir[/dim] {rel}/")

    # 2. Copy template files
    tmpl_dir = _template_dir()
    for src_rel, dst_rel in _COPY_MAP:
        src = tmpl_dir / src_rel
        dst = vault / dst_rel
        if dst.exists() and not force:
            console.print(f"  [dim]skip[/dim]  {dst_rel} (already exists)")
            continue
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            console.print(f"  [green]write[/green] {dst_rel}")
        else:
            console.print(f"  [yellow]warn[/yellow]  Template not found: {src_rel}")

    # 3. Patch config.yaml with selected backends
    _patch_config(vault, db_type=db_type, storage_type=storage_type)

    # 4. Update state.json with initialisation timestamp
    _write_state(vault)

    # 5. Initialise the database schema
    _init_db(vault)

    console.print()
    console.rule("[bold green]Done[/bold green]")
    console.print(
        f"Your BrainVault is ready at [bold]{vault}[/bold]\n\n"
        "Next steps:\n"
        "  1. Edit [bold]meta/config.yaml[/bold] to configure backends.\n"
        "  2. Add source documents to [bold]raw/sources/[/bold].\n"
        "  3. Run [bold]brainvault serve[/bold] to start the MCP server.\n"
        "  4. Open the vault in Obsidian (it's just Markdown!)."
    )


def _patch_config(vault: Path, db_type: str, storage_type: str) -> None:
    """Update meta/config.yaml to reflect the chosen backend types."""
    import yaml

    config_path = vault / "meta" / "config.yaml"
    if not config_path.exists():
        return

    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    raw.setdefault("storage", {})["type"] = storage_type
    raw.setdefault("database", {})["type"] = db_type

    with config_path.open("w", encoding="utf-8") as fh:
        yaml.dump(raw, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _write_state(vault: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    state = {
        "version": "0.1.0",
        "initialized_at": now,
        "last_sync": None,
        "page_count": 0,
    }
    state_path = vault / ".brainvault" / "state.json"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _init_db(vault: Path) -> None:
    """Create the database schema for the configured backend."""
    try:
        from brainvault.config import load_config
        from brainvault.factory import make_database

        cfg = load_config(vault)
        db = make_database(cfg)
        db.initialize()
        db.close()
        console.print("  [green]db[/green]    Schema initialised")
    except Exception as exc:
        console.print(f"  [yellow]db[/yellow]    Schema init skipped: {exc}")
