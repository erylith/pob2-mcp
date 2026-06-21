"""Pool of LuaBridge instances — one per loaded build.

Keeps multiple LuaJIT subprocesses alive simultaneously so builds can be
compared or switched without reloading. Evicts the least-recently-used build
when the pool reaches capacity.
"""

import logging
import threading
from pathlib import Path
from typing import Any

from .config import BRIDGE_POOL_MAX_BUILDS
from .lua_bridge import LuaBridge, LuaBridgeError

logger = logging.getLogger(__name__)


class LuaBridgePool:
    """Manages multiple LuaBridge instances, one per loaded build.

    All public methods are thread-safe. The pool lock is held only during
    bookkeeping — never during the actual Lua command — so concurrent calls
    to different builds proceed in parallel.
    """

    def __init__(self, max_builds: int = BRIDGE_POOL_MAX_BUILDS):
        self._max_builds = max_builds
        self._builds: dict[str, LuaBridge] = {}
        self._active: str | None = None
        self._lru: list[str] = []          # index 0 = least recently used
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Pool management
    # ------------------------------------------------------------------

    def load_build(
        self,
        name: str,
        path: str | None = None,
        xml: str | None = None,
        new: bool = False,
    ) -> None:
        """Load a build into its own bridge instance and make it active.

        If the build is already loaded, just switches to it.
        Evicts the least-recently-used build when the pool is full.

        Args:
            name: Unique key for this build within the pool.
            path: Absolute path to a .xml build file.
            xml:  Raw build XML string.
            new:  If True, create a new empty build (ignores path/xml).
        """
        if not name:
            raise LuaBridgeError("Build name must not be empty")
        if not new and path is None and xml is None:
            raise LuaBridgeError("Either 'path', 'xml', or new=True must be provided")

        with self._lock:
            if name in self._builds:
                self._set_active_locked(name)
                return

            # Evict LRU if at capacity
            if len(self._builds) >= self._max_builds:
                evict = self._lru.pop(0)
                logger.info("Pool full — evicting build '%s'", evict)
                self._builds[evict].shutdown()
                del self._builds[evict]
                if self._active == evict:
                    self._active = None

            # Spin up a new bridge for this build
            bridge = LuaBridge()

        # Start the bridge outside the lock — startup is slow (~1-2 s)
        bridge.start()

        if new:
            bridge.send_command("new_build")
        elif path is not None:
            bridge.send_command("load_build_file", {"path": path})
        else:
            bridge.send_command("load_build_xml", {"xml": xml, "name": name})

        with self._lock:
            self._builds[name] = bridge
            self._set_active_locked(name)
            logger.info("Build '%s' loaded (pool size: %d)", name, len(self._builds))

    def switch_build(self, name: str) -> None:
        """Make a previously-loaded build the active one.

        Args:
            name: Build name as supplied to load_build.
        """
        with self._lock:
            if name not in self._builds:
                raise LuaBridgeError(f"Build not loaded: '{name}'")
            self._set_active_locked(name)

    def unload_build(self, name: str) -> None:
        """Shut down a build's bridge and remove it from the pool.

        Args:
            name: Build name to remove.
        """
        with self._lock:
            if name not in self._builds:
                raise LuaBridgeError(f"Build not loaded: '{name}'")
            bridge = self._builds.pop(name)
            self._lru.remove(name)
            if self._active == name:
                self._active = self._lru[-1] if self._lru else None
                if self._active:
                    logger.info("Active build unloaded; switched to '%s'", self._active)

        bridge.shutdown()
        logger.info("Build '%s' unloaded", name)

    def list_builds(self) -> list[dict[str, Any]]:
        """Return metadata for all builds currently in the pool."""
        with self._lock:
            return [
                {
                    "name": name,
                    "active": name == self._active,
                    "is_running": bridge.is_running,
                }
                for name, bridge in self._builds.items()
            ]

    def shutdown_all(self) -> None:
        """Gracefully shut down every bridge in the pool."""
        with self._lock:
            items = list(self._builds.items())
            self._builds.clear()
            self._lru.clear()
            self._active = None

        for name, bridge in items:
            try:
                bridge.shutdown()
            except Exception:
                logger.exception("Error shutting down bridge for build '%s'", name)
        logger.info("All bridges shut down")

    # ------------------------------------------------------------------
    # Command routing
    # ------------------------------------------------------------------

    def call(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        build_name: str | None = None,
    ) -> dict[str, Any]:
        """Route a command to the specified or active build's bridge.

        Args:
            command:    Lua bridge command name.
            params:     Command parameters.
            build_name: Target build name; defaults to the active build.
        """
        with self._lock:
            target = build_name or self._active
            if target is None:
                raise LuaBridgeError(
                    "No active build. Load a build first with load_build_file or load_build_xml."
                )
            if target not in self._builds:
                raise LuaBridgeError(f"Build not loaded: '{target}'")
            bridge = self._builds[target]
            # Update LRU without popping from the middle repeatedly
            if self._lru and self._lru[-1] != target:
                self._lru.remove(target)
                self._lru.append(target)

        return bridge.send_command(command, params)

    def call_any(
        self,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Route a command to any available bridge, bootstrapping one if needed.

        Use for commands that don't require a loaded build (e.g. list_builds,
        search_base_items). If no build is loaded, a minimal new-build bridge
        is started automatically.
        """
        with self._lock:
            bridge = self._builds.get(self._lru[-1]) if self._lru else None

        if bridge is None:
            logger.info("No bridge available — bootstrapping a new-build bridge")
            self.load_build(name="__bootstrap__", new=True)
            with self._lock:
                bridge = self._builds["__bootstrap__"]

        return bridge.send_command(command, params)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_active_locked(self, name: str) -> None:
        """Set active build and move to MRU end of LRU list. Caller holds lock."""
        self._active = name
        if name in self._lru:
            self._lru.remove(name)
        self._lru.append(name)

    @property
    def active_build(self) -> str | None:
        """Name of the currently active build, or None if pool is empty."""
        with self._lock:
            return self._active

    @property
    def size(self) -> int:
        """Number of builds currently in the pool."""
        with self._lock:
            return len(self._builds)
