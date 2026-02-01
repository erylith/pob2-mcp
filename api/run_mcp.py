#!/usr/bin/env python3
"""Entry point for the Path of Building PoE2 MCP server.

Configure in Claude Desktop's config (claude_desktop_config.json):
{
  "mcpServers": {
    "pob-poe2": {
      "command": "python",
      "args": ["/path/to/PathOfBuilding-PoE2/api/run_mcp.py"],
      "env": {
        "POB_PATH": "/path/to/PathOfBuilding-PoE2"
      }
    }
  }
}

For HTTP streaming mode:
  python api/run_mcp.py --transport sse --port 8080
"""

import sys
from pathlib import Path

# Add project root to path so we can import the api package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.python.mcp_server import run_server

if __name__ == "__main__":
    run_server()
