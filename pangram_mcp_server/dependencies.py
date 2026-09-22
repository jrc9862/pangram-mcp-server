"""Hand tools a ready client, and clean up when the session turns out dead."""

from fastmcp import Context

from pangram_mcp_server.drivers.browser import close_browser, get_or_create_browser
from pangram_mcp_server.scraping.client import PangramClient

_client: PangramClient | None = None


async def get_ready_client(ctx: Context | None = None) -> PangramClient:
    global _client
    browser = await get_or_create_browser()
    if _client is None or _client.page is not browser.page:
        _client = PangramClient(browser.page)
    return _client


async def handle_auth_error() -> None:
    """Drop the browser so the next call re-checks the session from scratch.

    Never opens a headed login from inside the server: a window appearing
    mid-conversation, possibly on a machine with nobody at it, is worse than a
    clear instruction to run --login.
    """
    global _client
    _client = None
    await close_browser()


def reset_client_for_testing() -> None:
    global _client
    _client = None
