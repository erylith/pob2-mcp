"""Configuration for the PoB API server."""

import os
from pathlib import Path


def get_pob_path() -> Path:
    """Get the Path of Building root directory."""
    env_path = os.environ.get("POB_PATH")
    if env_path:
        return Path(env_path)
    # Default: assume we're in api/python/, go up two levels
    return Path(__file__).resolve().parent.parent.parent


def get_luajit_path() -> str:
    """Get the LuaJIT executable path."""
    return os.environ.get("LUAJIT_PATH", "luajit")


# Server defaults
DEFAULT_HOST = os.environ.get("POB_API_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("POB_API_PORT", "8000"))

# Lua bridge defaults
BRIDGE_STARTUP_TIMEOUT = float(os.environ.get("POB_BRIDGE_STARTUP_TIMEOUT", "30.0"))
BRIDGE_COMMAND_TIMEOUT = float(os.environ.get("POB_BRIDGE_COMMAND_TIMEOUT", "30.0"))

# Builds directory path override
BUILDS_PATH = os.environ.get("POB_BUILDS_PATH")  # Optional override passed to Lua bridge
