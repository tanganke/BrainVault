"""BrainVault MCP (Model Context Protocol) server.

The MCP server exposes vault operations to LLMs and AI agents over a
Unix domain socket.  It translates JSON-RPC 2.0 messages into calls on
the storage and database adapters so that the LLM never needs to know
which backend is active.

Protocol (JSON-RPC 2.0 over newline-delimited messages):
    Each request is a single JSON line; each response is a single JSON line.

Supported methods:
    storage.read(path)               → {content: str}
    storage.write(path, content)     → {ok: true}
    storage.list(prefix?)            → {paths: [str, ...]}
    storage.delete(path)             → {ok: true}
    storage.exists(path)             → {exists: bool}
    db.execute(sql, params?)         → {ok: true}
    db.query(sql, params?)           → {rows: [{...}, ...]}
    db.sync_page(filepath, content)  → {ok: true}
    db.search(query, limit?)         → {rows: [{...}, ...]}
    vault.status()                   → {version, storage_type, db_type}
    vault.ping()                     → {pong: true}
"""

from __future__ import annotations

import json
import logging
import os
import selectors
import socket
import threading
from pathlib import Path
from typing import Any

from brainvault.config import VaultConfig
from brainvault.core.database import DatabaseAdapter
from brainvault.core.storage import StorageAdapter

logger = logging.getLogger(__name__)


class MCPServer:
    """Unix-socket JSON-RPC 2.0 server for BrainVault.

    Args:
        config: The vault configuration (used for socket path and metadata).
        storage: Initialised storage adapter.
        db: Initialised database adapter.
    """

    def __init__(
        self,
        config: VaultConfig,
        storage: StorageAdapter,
        db: DatabaseAdapter,
    ) -> None:
        self._config = config
        self._storage = storage
        self._db = db
        self._socket_path = str(
            Path(config.vault_root) / config.mcp.socket_path
        )
        self._server_socket: socket.socket | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the MCP server in a background daemon thread."""
        Path(self._socket_path).parent.mkdir(parents=True, exist_ok=True)
        # Remove stale socket file
        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass

        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(self._socket_path)
        self._server_socket.listen(16)
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True, name="brainvault-mcp")
        self._thread.start()
        logger.info("MCP server listening on %s", self._socket_path)

    def stop(self) -> None:
        """Stop the MCP server and clean up the socket file."""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("MCP server stopped")

    # ------------------------------------------------------------------
    # Internal server loop
    # ------------------------------------------------------------------

    def _serve(self) -> None:
        sel = selectors.DefaultSelector()
        sel.register(self._server_socket, selectors.EVENT_READ)
        while self._running:
            try:
                events = sel.select(timeout=0.5)
            except OSError:
                break
            for key, _ in events:
                if key.fileobj is self._server_socket:
                    try:
                        conn, _ = self._server_socket.accept()
                    except OSError:
                        break
                    t = threading.Thread(
                        target=self._handle_client, args=(conn,), daemon=True
                    )
                    t.start()
        sel.close()

    def _handle_client(self, conn: socket.socket) -> None:
        buf = b""
        try:
            with conn:
                conn.settimeout(30)
                while True:
                    try:
                        chunk = conn.recv(4096)
                    except (OSError, socket.timeout):
                        break
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        line = line.strip()
                        if line:
                            response = self._dispatch(line)
                            conn.sendall(json.dumps(response).encode() + b"\n")
        except Exception:
            logger.exception("Unhandled error in MCP client handler")

    def _dispatch(self, raw: bytes) -> dict:
        """Parse one JSON-RPC request and return a JSON-RPC response dict."""
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as exc:
            return self._error(-32700, f"Parse error: {exc}")

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        try:
            result = self._call(method, params)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except FileNotFoundError as exc:
            return self._error(-32001, str(exc), req_id)
        except TypeError as exc:
            return self._error(-32602, f"Invalid params: {exc}", req_id)
        except Exception as exc:
            logger.exception("Error handling method %s", method)
            return self._error(-32603, f"Internal error: {exc}", req_id)

    @staticmethod
    def _error(code: int, message: str, req_id: Any = None) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }

    def _call(self, method: str, params: dict | list) -> Any:
        """Route a method name to the appropriate adapter call."""
        if isinstance(params, list):
            # Positional params not supported; require named params
            raise TypeError("Positional params are not supported; use named params.")

        if method == "vault.ping":
            return {"pong": True}

        elif method == "vault.status":
            return {
                "version": self._config.version,
                "storage_type": self._config.storage.type,
                "db_type": self._config.database.type,
                "socket_path": self._socket_path,
            }

        elif method == "storage.read":
            path = params["path"]
            content = self._storage.read(path)
            return {"content": content}

        elif method == "storage.write":
            path = params["path"]
            content = params["content"]
            self._storage.write(path, content)
            return {"ok": True}

        elif method == "storage.list":
            prefix = params.get("prefix", "")
            paths = list(self._storage.list(prefix))
            return {"paths": paths}

        elif method == "storage.delete":
            path = params["path"]
            self._storage.delete(path)
            return {"ok": True}

        elif method == "storage.exists":
            path = params["path"]
            return {"exists": self._storage.exists(path)}

        elif method == "db.execute":
            sql = params["sql"]
            db_params = params.get("params")
            self._db.execute(sql, db_params)
            return {"ok": True}

        elif method == "db.query":
            sql = params["sql"]
            db_params = params.get("params")
            rows = self._db.query(sql, db_params)
            return {"rows": rows}

        elif method == "db.sync_page":
            filepath = params["filepath"]
            content = params["content"]
            # Stage content then sync
            if hasattr(self._db, "set_page_content"):
                self._db.set_page_content(content)
            self._db.sync_page(filepath)
            return {"ok": True}

        elif method == "db.search":
            query = params["query"]
            limit = int(params.get("limit", 20))
            if hasattr(self._db, "search"):
                rows = self._db.search(query, limit)
            else:
                rows = []
            return {"rows": rows}

        else:
            raise NotImplementedError(f"Unknown method: {method!r}")

    @property
    def socket_path(self) -> str:
        """The filesystem path of the Unix domain socket."""
        return self._socket_path

    @property
    def is_running(self) -> bool:
        """``True`` if the server has been started."""
        return self._running
