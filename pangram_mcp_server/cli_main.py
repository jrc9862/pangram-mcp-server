"""Command-line entry point: one-shot modes, or run the MCP server."""

import asyncio
import logging
import sys

from pangram_mcp_server.config import ConfigurationError, get_config
from pangram_mcp_server.core.exceptions import PangramError
from pangram_mcp_server.logging_config import configure_logging
from pangram_mcp_server.setup import (
    ProfileInUseError,
    interactive_login,
    logout,
    session_status,
)

logger = logging.getLogger(__name__)


def main() -> None:
    try:
        config = get_config()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(2)
    configure_logging(config.server.log_level)

    try:
        if config.server.login:
            count = asyncio.run(interactive_login())
            print(f"Logged in. Saved {count} cookies.")
            return
        if config.server.status:
            ok, message = asyncio.run(session_status())
            print(message)
            sys.exit(0 if ok else 1)
        if config.server.logout:
            print(logout())
            return
    except (PangramError, ProfileInUseError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)

    from pangram_mcp_server.server import create_mcp_server

    mcp = create_mcp_server(tool_timeout=config.server.tool_timeout)
    if config.server.transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=config.server.host,
            port=config.server.port,
            path=config.server.path,
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
