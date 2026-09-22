"""Run tool calls one at a time; they all share one browser page."""

import asyncio
import logging

import mcp.types as mt
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult

logger = logging.getLogger(__name__)


class SequentialToolExecutionMiddleware(Middleware):
    """Serialize tool calls within this process.

    Two concurrent calls would navigate and fetch on the same page at once, and
    one scan's polling could read the other's state.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        async with self._lock:
            logger.debug("Running tool '%s'", context.message.name)
            return await call_next(context)
