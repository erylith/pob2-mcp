"""Unified server: MCP (streamable-HTTP) + REST API on a single port.

MCP tools are served at /mcp (streamable-HTTP transport).
REST endpoints for the Chrome extension are served at /api/*.

Both share the same LuaBridgePool from mcp_server.py so Claude Desktop
and the browser extension always see the same active build.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.applications import Starlette
from starlette.routing import Mount

from .lua_bridge import LuaBridgeError
from .mcp_server import call, call_any, get_pool, mcp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Route to active build bridge, converting errors to HTTP 400."""
    try:
        return call(command, params)
    except LuaBridgeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _call_any(command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Route to any available bridge, converting errors to HTTP 400."""
    try:
        return call_any(command, params)
    except LuaBridgeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _parse_stats(stats_str: str | None) -> list[str] | None:
    if not stats_str:
        return None
    return [s.strip() for s in stats_str.split(",") if s.strip()]


# ---------------------------------------------------------------------------
# REST sub-app
# ---------------------------------------------------------------------------

def _build_rest_app() -> FastAPI:
    """Build the /api FastAPI sub-app backed by the shared bridge pool."""

    api = FastAPI(
        title="PoB PoE2 REST API",
        description="REST endpoints for the Chrome extension sidecar",
        version="0.1.0",
        docs_url="/docs",
    )

    # CORS — Chrome extensions send chrome-extension:// origin.
    # allow_origins=["*"] is safe here because the bearer token gates real access.
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # ------------------------------------------------------------------
    # Health — intentionally exempt from bearer-token auth so the
    # extension can probe the server before the user has entered a token.
    # ------------------------------------------------------------------

    @api.get("/health")
    def health():
        pool = get_pool()
        return {
            "status": "ok",
            "active_build": pool.active_build,
            "pool_size": pool.size,
        }

    # ------------------------------------------------------------------
    # Pool
    # ------------------------------------------------------------------

    @api.get("/pool")
    def pool_status():
        pool = get_pool()
        return {
            "active": pool.active_build,
            "builds": pool.list_builds(),
        }

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    @api.get("/build/info")
    def build_info():
        return _call("get_build_info")

    @api.get("/build/output")
    def build_output(
        stats: str | None = Query(None, description="Comma-separated stat keys")
    ):
        params = {"stats": _parse_stats(stats)} if stats else None
        return _call("get_output", params)

    @api.get("/build/xml")
    def build_xml():
        return _call("get_build_xml")

    @api.post("/build/load/xml")
    def load_build_xml(body: dict):
        xml = body.get("xml")
        name = body.get("name", "Imported Build")
        if not xml:
            raise HTTPException(status_code=422, detail="'xml' field is required")
        try:
            get_pool().load_build(name, xml=xml)
        except LuaBridgeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"success": True, "name": name}

    # ------------------------------------------------------------------
    # Builds — list and load from the PoB builds directory
    # ------------------------------------------------------------------

    @api.get("/builds")
    def list_builds(folder: str = Query("", description="Sub-folder path within builds directory")):
        return _call_any("list_builds", {"sub_path": folder} if folder else {})

    @api.post("/builds/load")
    def load_build_file(body: dict):
        path = body.get("path", "")
        if not path:
            raise HTTPException(status_code=422, detail="'path' is required")
        result = _call_any("load_build_file", {"path": path})
        logger.debug("load_build_file | path=%s | result=%s", path, result)
        return result

    @api.post("/builds/save")
    def save_build():
        """Save the active build back to its original XML file (overwrite in-place)."""
        return _call("save_build")

    @api.post("/builds/save-as")
    def save_build_as(body: dict):
        """Save the active build to a new XML file with a given name."""
        name = body.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="'name' is required")
        params: dict = {"name": name}
        if body.get("sub_path"):
            params["sub_path"] = body["sub_path"]
        return _call("save_build_as", params)

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------

    @api.get("/items")
    def list_items():
        return _call("list_items")

    @api.get("/items/slots")
    def list_slots():
        return _call("list_slots")

    @api.post("/items/add")
    def add_item(body: dict):
        item_raw = body.get("item_raw", "")
        if not item_raw:
            raise HTTPException(status_code=422, detail="'item_raw' is required")
        params: dict = {"item_raw": item_raw}
        if body.get("slot"):
            params["slot"] = body["slot"]
        if "force_slot" in body:
            params["force_slot"] = bool(body["force_slot"])
        logger.debug(
            "add_item | force_slot=%s slot=%s | name=%s",
            params.get("force_slot"), params.get("slot"),
            item_raw.split("\n")[1] if "\n" in item_raw else "?",
        )
        result = _call("add_item", params)
        logger.debug("add_item result | item_id=%s slot=%s", result.get("item_id"), result.get("slot"))
        return result

    @api.post("/items/simulate")
    def simulate_item(body: dict):
        """Non-destructive: temporarily equip an item, diff stats, restore build.

        Accepts {item_raw, slot?, stats?}.
        Delegates to the bridge's simulate_item command which force-equips the
        item into the appropriate slot, snapshots stats before/after, and
        restores the original slot selection — all within a single Lua call.

        Returns {slot, itemType, before, after, delta}.
        """
        item_raw = body.get("item_raw", "")
        if not item_raw:
            raise HTTPException(status_code=422, detail="'item_raw' is required")

        logger.debug(
            "simulate_item request | slot=%r stats=%r | item_raw:\n%s",
            body.get("slot"), body.get("stats"), item_raw,
        )

        params: dict[str, Any] = {"item_raw": item_raw}
        if body.get("slot"):
            params["slot"] = body["slot"]
        if body.get("stats"):
            parsed = _parse_stats(body["stats"])
            if parsed:
                params["stats"] = parsed

        result = _call("simulate_item", params)

        logger.debug(
            "simulate_item response | slot=%r itemType=%r | delta keys: %s | before keys: %s",
            result.get("slot"), result.get("itemType"),
            list(result.get("delta", {}).keys()),
            list(result.get("before", {}).keys()),
        )

        return result

    @api.get("/items/all/impact")
    def all_items_impact(
        stats: str | None = Query(None, description="Comma-separated stat keys")
    ):
        params = {"stats": _parse_stats(stats)} if stats else None
        return _call("get_all_equipped_items_impact", params)

    return api


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

class _BearerAuthMiddleware:
    """ASGI middleware that enforces a bearer token on all paths except those
    listed in ``exempt_paths``."""

    def __init__(self, app: Any, token: str, exempt_paths: frozenset[str] = frozenset()):
        self._app = app
        self._expected = f"Bearer {token}"
        self._exempt = exempt_paths

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path not in self._exempt:
                headers = dict(scope.get("headers", []))
                auth = headers.get(b"authorization", b"").decode()
                if auth != self._expected:
                    await send({
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"www-authenticate", b'Bearer realm="pob-poe2"'),
                        ],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": b'{"detail":"Unauthorized"}',
                    })
                    return
        await self._app(scope, receive, send)


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def build_app(api_secret: str | None = None) -> Any:
    """Return the unified ASGI app.

    Routes:
      /mcp  → FastMCP streamable-HTTP transport (MCP tools for Claude Desktop)
      /api  → REST endpoints for the Chrome extension

    Args:
        api_secret: If provided, all requests except GET /api/health require
                    ``Authorization: Bearer <api_secret>``.

    Implementation note: FastMCP's streamable_http_app() has its own lifespan
    that initialises the StreamableHTTPSessionManager task group. Nesting it
    inside another Starlette app via Mount() silences that lifespan and causes
    a "Task group is not initialized" RuntimeError. Instead we extract the MCP
    app's routes and lifespan and fold them into a single top-level Starlette
    app so there is only one lifespan owner.
    """
    rest_app = _build_rest_app()

    # Build the MCP Starlette app so we can inspect its internals.
    mcp_starlette = mcp.streamable_http_app()

    # Pull the MCP lifespan out so we can re-use it as the combined lifespan.
    mcp_lifespan = mcp_starlette.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app: Starlette):
        async with mcp_lifespan(app):
            yield

    # Single flat Starlette app: REST at /api, MCP routes inlined at root.
    combined = Starlette(
        lifespan=combined_lifespan,
        routes=[
            Mount("/api", app=rest_app),
            *mcp_starlette.routes,          # includes the /mcp POST route
        ],
    )

    if api_secret:
        return _BearerAuthMiddleware(
            combined,
            token=api_secret,
            exempt_paths=frozenset({"/api/health"}),
        )

    return combined
