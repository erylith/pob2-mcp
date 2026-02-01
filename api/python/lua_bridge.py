"""Manages a persistent LuaJIT subprocess running bridge.lua.

Communicates via JSON-line protocol over stdin/stdout of the subprocess.
Thread-safe: uses a lock to serialize access (Lua is single-threaded).
Works on Windows, macOS, and Linux.
"""

import json
import logging
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from .config import BRIDGE_COMMAND_TIMEOUT, BRIDGE_STARTUP_TIMEOUT, get_luajit_path, get_pob_path

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"


class LuaBridgeError(Exception):
    """Raised when the Lua bridge returns an error."""


class LuaBridgeTimeout(LuaBridgeError):
    """Raised when a command times out."""


class LuaBridge:
    """Manages a persistent LuaJIT subprocess running bridge.lua."""

    def __init__(
        self,
        pob_path: str | Path | None = None,
        luajit_path: str | None = None,
    ):
        self._pob_path = Path(pob_path) if pob_path else get_pob_path()
        self._luajit_path = luajit_path or get_luajit_path()
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stdout_queue: queue.Queue[str | None] = queue.Queue()
        self._started = False

    def start(self, timeout: float | None = None) -> None:
        """Start the LuaJIT subprocess and wait for the ready signal."""
        if self._started:
            return

        timeout = timeout or BRIDGE_STARTUP_TIMEOUT
        src_dir = self._pob_path / "src"
        bridge_script = self._pob_path / "api" / "lua" / "bridge.lua"

        if not src_dir.is_dir():
            raise LuaBridgeError(f"PoB src directory not found: {src_dir}")
        if not bridge_script.is_file():
            raise LuaBridgeError(f"Bridge script not found: {bridge_script}")

        logger.info("Starting LuaJIT subprocess: %s %s (cwd: %s)", self._luajit_path, bridge_script, src_dir)

        env = os.environ.copy()

        # Set LUA_PATH so LuaJIT can find pure-Lua modules in runtime/lua/
        env["LUA_PATH"] = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;;"

        # On Windows, set LUA_CPATH so LuaJIT can find native DLLs in runtime/
        # (lua-utf8.dll, lzip.dll, etc.)
        if IS_WINDOWS:
            env["LUA_CPATH"] = "../runtime/?.dll;;"

        self._process = subprocess.Popen(
            [self._luajit_path, str(bridge_script)],
            cwd=str(src_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,  # Line-buffered
        )

        # Start stdout reader thread (cross-platform: avoids select() which
        # doesn't work on pipes on Windows)
        self._stdout_queue = queue.Queue()
        self._stdout_thread = threading.Thread(
            target=self._read_stdout,
            daemon=True,
            name="lua-bridge-stdout",
        )
        self._stdout_thread.start()

        # Start stderr reader thread
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            daemon=True,
            name="lua-bridge-stderr",
        )
        self._stderr_thread.start()

        # Wait for ready signal
        logger.info("Waiting for bridge ready signal (timeout: %.1fs)...", timeout)
        ready_line = self._read_line(timeout=timeout)
        if ready_line is None:
            self._kill()
            raise LuaBridgeError("Bridge subprocess did not produce any output")

        try:
            ready_msg = json.loads(ready_line)
        except json.JSONDecodeError as e:
            self._kill()
            raise LuaBridgeError(f"Bridge ready message was not valid JSON: {ready_line!r}") from e

        if not ready_msg.get("ready"):
            self._kill()
            raise LuaBridgeError(f"Unexpected ready message: {ready_msg}")

        self._started = True
        logger.info("Bridge is ready")

    def send_command(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a command to the Lua bridge and return the result.

        Raises LuaBridgeError on error responses, LuaBridgeTimeout on timeout.
        """
        if not self._started:
            self.start()

        timeout = timeout or BRIDGE_COMMAND_TIMEOUT

        with self._lock:
            return self._send_command_locked(command, params, timeout)

    def _send_command_locked(
        self,
        command: str,
        params: dict[str, Any] | None,
        timeout: float,
    ) -> dict[str, Any]:
        """Send a command while holding the lock."""
        if self._process is None or self._process.poll() is not None:
            raise LuaBridgeError("Bridge subprocess is not running")

        request = {"command": command}
        if params:
            request["params"] = params

        request_json = json.dumps(request, separators=(",", ":"))
        logger.debug("Sending: %s", request_json)

        try:
            self._process.stdin.write(request_json + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise LuaBridgeError(f"Failed to write to bridge: {e}") from e

        response_line = self._read_line(timeout=timeout)
        if response_line is None:
            raise LuaBridgeTimeout(f"Command '{command}' timed out after {timeout}s")

        try:
            response = json.loads(response_line)
        except json.JSONDecodeError as e:
            raise LuaBridgeError(f"Invalid JSON response: {response_line!r}") from e

        if not response.get("ok"):
            raise LuaBridgeError(response.get("error", "Unknown error from bridge"))

        return response.get("result", {})

    def _read_stdout(self) -> None:
        """Read lines from stdout in a background thread, pushing to queue."""
        if self._process is None or self._process.stdout is None:
            return
        try:
            for line in self._process.stdout:
                stripped = line.rstrip("\n\r")
                if stripped:
                    self._stdout_queue.put(stripped)
        except (OSError, ValueError):
            pass
        finally:
            # Signal EOF
            self._stdout_queue.put(None)

    def _read_line(self, timeout: float) -> str | None:
        """Read a single line from the stdout queue with timeout."""
        try:
            line = self._stdout_queue.get(timeout=timeout)
            return line  # None means EOF
        except queue.Empty:
            return None

    def _read_stderr(self) -> None:
        """Read stderr from the subprocess and log it."""
        if self._process is None or self._process.stderr is None:
            return
        try:
            for line in self._process.stderr:
                line = line.rstrip()
                if line:
                    logger.info("[lua] %s", line)
        except (OSError, ValueError):
            pass

    def _kill(self) -> None:
        """Kill the subprocess."""
        if self._process is not None:
            try:
                self._process.kill()
                self._process.wait(timeout=5)
            except Exception:
                pass
            self._process = None
        self._started = False

    def shutdown(self) -> None:
        """Send shutdown command and wait for clean exit."""
        if not self._started:
            return

        try:
            with self._lock:
                if self._process and self._process.poll() is None:
                    try:
                        self._send_command_locked("shutdown", None, timeout=5.0)
                    except Exception:
                        pass
                    try:
                        self._process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait(timeout=5)
        except Exception:
            self._kill()
        finally:
            self._process = None
            self._started = False

    @property
    def is_running(self) -> bool:
        """Check if the bridge subprocess is alive."""
        return (
            self._started
            and self._process is not None
            and self._process.poll() is None
        )

    def __del__(self) -> None:
        self.shutdown()
