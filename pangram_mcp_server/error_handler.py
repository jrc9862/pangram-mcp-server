"""Turn client errors into MCP tool errors the model can act on."""

import logging
from typing import NoReturn

from fastmcp.exceptions import ToolError

from pangram_mcp_server.core.exceptions import (
    AuthenticationError,
    BrowserNotInstalledError,
    InvalidInputError,
    PangramError,
    QuotaExceededError,
    ScanFailedError,
)

logger = logging.getLogger(__name__)


def raise_tool_error(exc: BaseException, tool_name: str) -> NoReturn:
    """Re-raise *exc* as a ToolError with an actionable message.

    Unknown exceptions are re-raised untouched so FastMCP's error masking
    applies and the traceback reaches the log.
    """
    if isinstance(exc, ToolError):
        raise exc
    if isinstance(exc, AuthenticationError):
        raise ToolError(
            f"{exc} The user must log in again in a terminal; "
            "tool calls cannot open a login window."
        ) from exc
    if isinstance(exc, QuotaExceededError):
        raise ToolError(
            f"Pangram quota reached: {exc} Do not retry until credits refresh."
        ) from exc
    if isinstance(exc, (InvalidInputError, ScanFailedError, BrowserNotInstalledError)):
        raise ToolError(str(exc)) from exc
    if isinstance(exc, PangramError):
        raise ToolError(f"Pangram error: {exc}") from exc
    logger.exception("Unexpected error in %s", tool_name)
    raise exc
