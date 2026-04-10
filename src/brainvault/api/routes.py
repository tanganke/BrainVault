"""REST API routes for BrainVault.

All routes are scoped under ``/api/v1`` and require a valid JWT bearer
token (except ``POST /api/v1/auth/token``).

Vault-scoped endpoints use ``{vault_id}`` as a path parameter so that
each vault's data is isolated.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from brainvault.api.auth import create_token, get_current_user
from brainvault.api.vault_manager import VaultHandle, VaultManager

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TokenRequest(BaseModel):
    user_id: str = Field(..., min_length=1, description="Unique user identifier")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VaultInfo(BaseModel):
    vault_id: str
    owner: str
    storage_type: str
    db_type: str
    version: str


class PageContent(BaseModel):
    path: str
    content: str


class PageInfo(BaseModel):
    path: str
    title: str = ""


class SearchRequest(BaseModel):
    query: str
    limit: int = 20


class SearchResult(BaseModel):
    path: str
    title: str = ""
    rank: float = 0.0


class StatusResponse(BaseModel):
    vault_id: str
    version: str
    storage_type: str
    db_type: str
    page_count: int


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_router(vault_manager: VaultManager) -> APIRouter:
    """Build and return the v1 API router.

    The *vault_manager* is closed over so that route handlers can look up
    vault handles at request time.
    """
    router = APIRouter(prefix="/api/v1")

    # ----- helpers -------------------------------------------------------

    def _get_vault(vault_id: str, user: str) -> VaultHandle:
        handle = vault_manager.get(vault_id)
        if handle is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vault {vault_id!r} not found",
            )
        return handle

    # ----- auth ----------------------------------------------------------

    @router.post("/auth/token", response_model=TokenResponse)
    def issue_token(body: TokenRequest) -> TokenResponse:
        """Issue a JWT for the given user.

        .. note::
            In a production deployment this endpoint should be behind
            an external identity provider.  The current implementation
            issues tokens without password verification and is suitable
            for development / internal use only.
        """
        token = create_token(user_id=body.user_id)
        return TokenResponse(access_token=token)

    # ----- vault management ----------------------------------------------

    @router.get("/vaults", response_model=list[VaultInfo])
    def list_vaults(
        user: str = Depends(get_current_user),
    ) -> list[VaultInfo]:
        """List all vaults accessible to the current user."""
        handles = vault_manager.list_vaults()
        return [
            VaultInfo(
                vault_id=h.vault_id,
                owner=h.owner,
                storage_type=h.config.storage.type,
                db_type=h.config.database.type,
                version=h.config.version,
            )
            for h in handles
        ]

    @router.get("/vaults/{vault_id}", response_model=VaultInfo)
    def get_vault(
        vault_id: str,
        user: str = Depends(get_current_user),
    ) -> VaultInfo:
        """Get information about a specific vault."""
        h = _get_vault(vault_id, user)
        return VaultInfo(
            vault_id=h.vault_id,
            owner=h.owner,
            storage_type=h.config.storage.type,
            db_type=h.config.database.type,
            version=h.config.version,
        )

    @router.delete("/vaults/{vault_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_vault(
        vault_id: str,
        user: str = Depends(get_current_user),
    ) -> None:
        """Unregister a vault (does **not** delete data on disk)."""
        removed = vault_manager.remove(vault_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vault {vault_id!r} not found",
            )

    # ----- vault status --------------------------------------------------

    @router.get("/vaults/{vault_id}/status", response_model=StatusResponse)
    def vault_status(
        vault_id: str,
        user: str = Depends(get_current_user),
    ) -> StatusResponse:
        """Return vault configuration and page count."""
        h = _get_vault(vault_id, user)
        rows = h.db.query("SELECT COUNT(*) AS n FROM pages")
        page_count = rows[0]["n"] if rows else 0
        return StatusResponse(
            vault_id=vault_id,
            version=h.config.version,
            storage_type=h.config.storage.type,
            db_type=h.config.database.type,
            page_count=page_count,
        )

    # ----- pages ---------------------------------------------------------

    @router.get("/vaults/{vault_id}/pages", response_model=list[PageInfo])
    def list_pages(
        vault_id: str,
        prefix: str = "wiki/",
        user: str = Depends(get_current_user),
    ) -> list[PageInfo]:
        """List wiki pages in a vault."""
        h = _get_vault(vault_id, user)
        paths = [p for p in h.storage.list(prefix) if p.endswith(".md")]
        return [PageInfo(path=p) for p in paths]

    @router.get("/vaults/{vault_id}/pages/{path:path}")
    def read_page(
        vault_id: str,
        path: str,
        user: str = Depends(get_current_user),
    ) -> dict[str, str]:
        """Read the content of a single page."""
        h = _get_vault(vault_id, user)
        try:
            content = h.storage.read(path)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Page not found: {path!r}",
            ) from exc
        return {"path": path, "content": content}

    @router.put("/vaults/{vault_id}/pages/{path:path}")
    def write_page(
        vault_id: str,
        path: str,
        body: PageContent,
        user: str = Depends(get_current_user),
    ) -> dict[str, bool]:
        """Create or update a page."""
        h = _get_vault(vault_id, user)
        h.storage.write(path, body.content)
        # Auto-sync into the database
        if hasattr(h.db, "set_page_content"):
            h.db.set_page_content(body.content)
        h.db.sync_page(path)
        return {"ok": True}

    @router.delete(
        "/vaults/{vault_id}/pages/{path:path}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_page(
        vault_id: str,
        path: str,
        user: str = Depends(get_current_user),
    ) -> None:
        """Delete a page from storage."""
        h = _get_vault(vault_id, user)
        try:
            h.storage.delete(path)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Page not found: {path!r}",
            ) from exc
        # Remove from DB
        h.db.execute("DELETE FROM pages WHERE path=?", [path])

    # ----- search --------------------------------------------------------

    @router.get("/vaults/{vault_id}/search", response_model=list[SearchResult])
    def search_pages(
        vault_id: str,
        q: str,
        limit: int = 20,
        user: str = Depends(get_current_user),
    ) -> list[SearchResult]:
        """Full-text search over wiki pages."""
        h = _get_vault(vault_id, user)
        if not hasattr(h.db, "search"):
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Search is not supported by this database adapter",
            )
        rows = h.db.search(q, limit=limit)
        return [
            SearchResult(
                path=r["path"],
                title=r.get("title", ""),
                rank=float(r.get("rank", 0.0)),
            )
            for r in rows
        ]

    # ----- sync ----------------------------------------------------------

    @router.post("/vaults/{vault_id}/sync")
    def sync_vault(
        vault_id: str,
        user: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """Trigger a full sync of wiki pages into the database."""
        h = _get_vault(vault_id, user)
        wiki_paths = [p for p in h.storage.list("wiki/") if p.endswith(".md")]
        synced = 0
        errors = 0
        for fp in wiki_paths:
            try:
                content = h.storage.read(fp)
                if hasattr(h.db, "set_page_content"):
                    h.db.set_page_content(content)
                h.db.sync_page(fp)
                synced += 1
            except Exception:
                logger.exception("Failed to sync page %s", fp)
                errors += 1
        return {"synced": synced, "errors": errors}

    return router
