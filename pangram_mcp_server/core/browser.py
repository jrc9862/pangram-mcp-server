"""Browser lifecycle using a Patchright persistent context."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Self

from patchright.async_api import BrowserContext, Page, Playwright, async_playwright

from pangram_mcp_server.common_utils import secure_mkdir, secure_write_text

from .exceptions import BrowserNotInstalledError

logger = logging.getLogger(__name__)

PANGRAM_COOKIE_DOMAIN = "pangram.com"
_CLEANUP_TIMEOUT_SECONDS = 10


class BrowserManager:
    """Async context manager around one persistent Chromium profile.

    Cookies, localStorage and IndexedDB persist in ``user_data_dir`` between
    runs, which is what keeps the login.
    """

    def __init__(
        self,
        user_data_dir: str | Path,
        headless: bool = True,
        slow_mo: int = 0,
        viewport: dict[str, int] | None = None,
        default_timeout: int = 30_000,
        **launch_options: Any,
    ):
        # Refused rather than ignored: an override changes the UA string but
        # not the client hints, and never reaches service workers, so the
        # browser would contradict itself. The browser reports its own identity.
        if "user_agent" in launch_options:
            raise TypeError("BrowserManager does not accept a user_agent.")
        if "no_viewport" in launch_options:
            raise TypeError("BrowserManager decides no_viewport from headless=.")

        self.user_data_dir = Path(user_data_dir).expanduser()
        self.headless = headless
        self.slow_mo = slow_mo
        self.viewport = viewport
        self.default_timeout = default_timeout
        self.launch_options = launch_options

        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("Browser not started")
        return self._context

    def _geometry(self) -> dict[str, Any]:
        # A headed window reports its real size. A headless browser with no
        # viewport collapses to 800x600, so it gets an explicit one.
        if self.headless:
            return {"viewport": self.viewport or {"width": 1280, "height": 900}}
        return {"no_viewport": True}

    async def start(self) -> None:
        if self._context is not None:
            raise RuntimeError("Browser already started. Call close() first.")
        try:
            self._playwright = await async_playwright().start()
            secure_mkdir(self.user_data_dir)
            options: dict[str, Any] = {
                "headless": self.headless,
                "slow_mo": self.slow_mo,
                **self._geometry(),
                **self.launch_options,
            }
            try:
                self._context = (
                    await self._playwright.chromium.launch_persistent_context(
                        str(self.user_data_dir), **options
                    )
                )
            except Exception as exc:
                if "Executable doesn't exist" in str(exc):
                    raise BrowserNotInstalledError(
                        "Chromium is not installed. Run: "
                        "uv run patchright install chromium"
                    ) from exc
                raise
            self._context.set_default_timeout(self.default_timeout)
            self._page = (
                self._context.pages[0]
                if self._context.pages
                else await self._context.new_page()
            )
            logger.info(
                "Browser started (headless=%s, profile=%s)",
                self.headless,
                self.user_data_dir,
            )
        except BaseException:
            # A cancelled or failed launch may already have Chromium running on
            # the profile; leaving it would hold the profile lock.
            await asyncio.shield(self.close())
            raise

    async def close(self) -> None:
        context, playwright = self._context, self._playwright
        self._context = self._playwright = self._page = None
        if context is not None:
            try:
                await asyncio.wait_for(context.close(), _CLEANUP_TIMEOUT_SECONDS)
            except Exception as exc:
                logger.warning("Browser context did not close cleanly: %s", exc)
        if playwright is not None:
            try:
                await asyncio.wait_for(playwright.stop(), _CLEANUP_TIMEOUT_SECONDS)
            except Exception as exc:
                logger.warning("Playwright did not stop cleanly: %s", exc)

    async def export_cookies(self, path: Path) -> int:
        """Write the pangram.com cookies to *path*; return how many."""
        cookies = [
            c
            for c in await self.context.cookies()
            if c.get("domain", "").lstrip(".").endswith(PANGRAM_COOKIE_DOMAIN)
        ]
        secure_mkdir(path.parent)
        secure_write_text(path, json.dumps(cookies, indent=2) + "\n")
        return len(cookies)
