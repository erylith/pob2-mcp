#!/usr/bin/env python3
"""Entry point for the Path of Building PoE2 REST API server."""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path so we can import the api package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.python.config import DEFAULT_HOST, DEFAULT_PORT


def main():
    parser = argparse.ArgumentParser(description="Path of Building PoE2 REST API Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host to bind to (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to bind to (default: {DEFAULT_PORT})")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    import uvicorn
    uvicorn.run(
        "api.python.rest_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
