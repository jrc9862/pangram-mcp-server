"""FastMCP server: tools, middleware and browser lifecycle."""

import logging
from collections.abc import AsyncIterator
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from pangram_mcp_server import __version__
from pangram_mcp_server.config.schema import DEFAULT_TOOL_TIMEOUT_SECONDS
from pangram_mcp_server.drivers.browser import close_browser
from pangram_mcp_server.sequential_tool_middleware import (
    SequentialToolExecutionMiddleware,
)
from pangram_mcp_server.tools.account import register_account_tools
from pangram_mcp_server.tools.detect import register_detect_tools

logger = logging.getLogger(__name__)


@lifespan
async def browser_lifespan(app: FastMCP) -> AsyncIterator[dict[str, Any]]:
    del app
    logger.info("Pangram MCP server starting")
    try:
        yield {}
    finally:
        await close_browser()


def create_mcp_server(*, tool_timeout: float = DEFAULT_TOOL_TIMEOUT_SECONDS) -> FastMCP:
    mcp = FastMCP(
        "pangram",
        version=__version__,
        instructions=(
            "Pangram AI-text detection through the user's own logged-in account. "
            "Scans cost credits (1 per 100 words, 50-word minimum) and are saved "
            "to the user's Pangram history; call get_account first when the "
            "text is long. get_account, get_scan_history and get_scan are free."
        ),
        lifespan=browser_lifespan,
        mask_error_details=True,
    )
    mcp.add_middleware(SequentialToolExecutionMiddleware())
    register_detect_tools(mcp, tool_timeout=tool_timeout)
    register_account_tools(mcp, tool_timeout=tool_timeout)

    @mcp.tool(
        title="Close Session",
        annotations={"readOnlyHint": False, "idempotentHint": True},
        tags={"session"},
    )
    async def close_session() -> dict[str, Any]:
        """Close the browser. The next tool call reopens it from the saved login."""
        from pangram_mcp_server.dependencies import handle_auth_error

        closed = await close_browser()
        await handle_auth_error()
        return {"closed": closed}

    return mcp
