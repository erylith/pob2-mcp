#!/usr/bin/env python3
"""Entry point for the Path of Building PoE2 MCP + REST unified server.

Default transport is streamable-http, which serves both the MCP protocol
(for Claude Desktop) and REST endpoints (for the Chrome extension) on the
same port:

  /mcp   — MCP streamable-HTTP endpoint (Claude Desktop)
  /api/* — REST endpoints (Chrome extension background worker)

Claude Desktop config (streamable-http, remote server):
{
  "mcpServers": {
    "pob-poe2": {
      "type": "streamable-http",
      "url": "https://your-server/mcp"
    }
  }
}

Claude Desktop config (stdio, local install, no extension):
{
  "mcpServers": {
    "pob-poe2": {
      "command": "python",
      "args": ["/path/to/PathOfBuilding-PoE2/api/run_mcp.py", "--transport", "stdio"],
      "env": { "POB_PATH": "/path/to/PathOfBuilding-PoE2" }
    }
  }
}
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.python.mcp_server import run_server

if __name__ == "__main__":
    run_server()
