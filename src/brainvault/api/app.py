"""BrainVault REST API application factory and entry-point.

The application exposes a full RESTful interface to one or more vaults
with JWT-based authentication.

Usage::

    # Programmatic
    from brainvault.api.app import create_app
    app = create_app(vault_dirs={"my-vault": "/data/vaults/my-vault"})

    # CLI (via console_scripts)
    brainvault-api --vault my-vault:/data/vaults/my-vault --port 8000
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from brainvault.api.routes import create_router
from brainvault.api.vault_manager import VaultManager


def create_app(
    vault_dirs: dict[str, str | Path] | None = None,
    vault_manager: VaultManager | None = None,
) -> FastAPI:
    """Build a FastAPI application for the BrainVault REST API.

    Args:
        vault_dirs: Mapping of ``{vault_id: vault_path}`` to register on
            startup.  Paths should point to initialised vault directories.
        vault_manager: Optional pre-configured :class:`VaultManager`.  If
            not supplied a new one is created and populated from
            *vault_dirs*.

    Returns:
        A FastAPI ``app`` instance ready to be served by Uvicorn.
    """
    if vault_manager is None:
        vault_manager = VaultManager()

    # Register pre-configured vaults eagerly so they are available
    # immediately (including during tests that never trigger startup).
    if vault_dirs:
        for vid, vpath in vault_dirs.items():
            vault_manager.register_directory(vid, Path(vpath))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # startup – nothing extra needed (vaults registered above)
        yield
        # shutdown
        vault_manager.close_all()

    app = FastAPI(
        title="BrainVault API",
        description="Multi-user, multi-vault RESTful API for BrainVault",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Store the manager on the app so tests / extensions can access it.
    app.state.vault_manager = vault_manager  # type: ignore[attr-defined]

    # Mount the v1 router
    router = create_router(vault_manager)
    app.include_router(router)

    return app


# ---------------------------------------------------------------------------
# Console script entry-point
# ---------------------------------------------------------------------------


def main() -> None:
    """``brainvault-api`` console-script entry-point."""
    parser = argparse.ArgumentParser(
        description="Start the BrainVault REST API server",
    )
    parser.add_argument(
        "--vault",
        action="append",
        metavar="ID:PATH",
        help=(
            "Register a vault as ID:PATH (repeatable).  "
            "Example: --vault my-vault:/data/vaults/my-vault"
        ),
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default 8000)")
    args = parser.parse_args()

    vault_dirs: dict[str, str] = {}
    if args.vault:
        for entry in args.vault:
            if ":" not in entry:
                print(f"Error: vault spec must be ID:PATH, got {entry!r}", file=sys.stderr)
                sys.exit(1)
            vid, vpath = entry.split(":", 1)
            vault_dirs[vid] = vpath

    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is required to run the API server. "
            "Install it with: pip install brainvault[api]",
            file=sys.stderr,
        )
        sys.exit(1)

    app = create_app(vault_dirs=vault_dirs)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
