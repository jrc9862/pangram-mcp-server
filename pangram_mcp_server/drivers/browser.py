"""The one browser this server process drives, created on first use."""

import asyncio
import logging

from pangram_mcp_server.browser_launch import build_launch_options, describe_launch
from pangram_mcp_server.config import get_config
from pangram_mcp_server.core.auth import check_session
from pangram_mcp_server.core.browser import BrowserManager
from pangram_mcp_server.core.exceptions import AuthenticationError
from pangram_mcp_server.session_state import get_profile_dir, has_saved_login

logger = logging.getLogger(__name__)

_browser: BrowserManager | None = None
_lock = asyncio.Lock()


async def get_or_create_browser() -> BrowserManager:
    """Return the running browser, starting and authenticating it if needed."""
    global _browser
    async with _lock:
        if _browser is not None:
            return _browser
        profile_dir = get_profile_dir()
        if not has_saved_login(profile_dir):
            raise AuthenticationError(
                "No saved Pangram login. Run: uv run -m pangram_mcp_server --login"
            )
        config = get_config()
        launch_options, viewport = build_launch_options(config.browser)
        describe_launch(launch_options)
        browser = BrowserManager(
            user_data_dir=profile_dir,
            headless=config.browser.headless,
            slow_mo=config.browser.slow_mo,
            viewport=viewport,
            default_timeout=config.browser.default_timeout,
            **launch_options,
        )
        await browser.start()
        try:
            if not await check_session(browser.page):
                raise AuthenticationError(
                    "Pangram session expired. Run: uv run -m pangram_mcp_server --login"
                )
        except BaseException:
            await browser.close()
            raise
        _browser = browser
        return browser


async def close_browser() -> bool:
    """Close the browser if one is running. Returns whether one was."""
    global _browser
    async with _lock:
        browser, _browser = _browser, None
    if browser is None:
        return False
    await browser.close()
    logger.info("Browser closed")
    return True


def reset_browser_for_testing() -> None:
    global _browser, _lock
    _browser = None
    _lock = asyncio.Lock()
