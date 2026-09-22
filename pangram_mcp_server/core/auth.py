"""Decide whether the browser holds a working Pangram session.

Only URL patterns are used: they do not depend on the page's language or on
class names that change with every front-end deploy.
"""

import asyncio
import logging
import re
import time
from urllib.parse import urlparse

from patchright.async_api import Page

from .exceptions import AuthenticationError

logger = logging.getLogger(__name__)

PANGRAM_BASE_URL = "https://www.pangram.com"
LOGIN_URL = f"{PANGRAM_BASE_URL}/login"
DASHBOARD_URL = f"{PANGRAM_BASE_URL}/dashboard"

_AUTH_BLOCKER_PATHS = ("/login", "/signup", "/sign-in", "/sign-up", "/auth")
_AUTHENTICATED_PATHS = ("/dashboard",)


def _is_pangram_host(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host == "pangram.com" or host.endswith(".pangram.com")


def _route(url: str) -> str:
    """The path with any locale prefix removed: ``/fr/login`` -> ``/login``."""
    path = urlparse(url).path.rstrip("/").lower()
    return re.sub(r"^/[a-z]{2}(?:-[a-z]{2})?(?=/)", "", path)


def is_auth_blocker_url(url: str) -> bool:
    path = _route(url)
    return any(
        path == p or path.startswith(p + "/") for p in _AUTH_BLOCKER_PATHS
    ) or not _is_pangram_host(url)


def is_authenticated_url(url: str) -> bool:
    if not _is_pangram_host(url):
        return False
    path = _route(url)
    return any(path == p or path.startswith(p + "/") for p in _AUTHENTICATED_PATHS)


async def is_logged_in(page: Page) -> bool:
    """True when the page sits on an authenticated route and has rendered."""
    if not is_authenticated_url(page.url):
        return False
    text = await page.evaluate("() => document.body?.innerText || ''")
    return isinstance(text, str) and bool(text.strip())


async def check_session(page: Page, *, settle_seconds: float = 8.0) -> bool:
    """Load the dashboard and report whether it stays there.

    The app may redirect a logged-out visitor on the client after first paint,
    so a single URL read right after ``goto`` is not proof. Poll until the URL
    lands on a login route (fail) or has stayed on the dashboard with content
    for the whole settle window (pass).
    """
    await page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
    deadline = time.monotonic() + settle_seconds
    while time.monotonic() < deadline:
        if is_auth_blocker_url(page.url):
            return False
        await asyncio.sleep(0.5)
    return await is_logged_in(page)


async def wait_for_manual_login(page: Page, timeout_seconds: int) -> None:
    """Poll once a second until the user reaches the dashboard.

    ``timeout_seconds == 0`` waits indefinitely.
    """
    deadline = time.monotonic() + timeout_seconds if timeout_seconds else None
    while deadline is None or time.monotonic() < deadline:
        try:
            if await is_logged_in(page):
                return
        except Exception as exc:
            # Navigation in progress destroys the execution context; retry.
            logger.debug("Login check deferred: %s", exc)
        await asyncio.sleep(1)
    raise AuthenticationError(
        f"Login not completed within {timeout_seconds} seconds. "
        "Run --login again, or raise --login-timeout."
    )
