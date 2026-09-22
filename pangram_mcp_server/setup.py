"""Interactive login: open a visible browser and wait for the user to sign in."""

import logging
import shutil
from pathlib import Path

from pangram_mcp_server.browser_launch import build_launch_options, describe_launch
from pangram_mcp_server.config import get_config
from pangram_mcp_server.core.auth import (
    DASHBOARD_URL,
    LOGIN_URL,
    check_session,
    wait_for_manual_login,
)
from pangram_mcp_server.core.browser import BrowserManager
from pangram_mcp_server.session_state import (
    get_profile_dir,
    load_source_state,
    portable_cookie_path,
    profile_in_use,
    source_state_path,
    write_source_state,
)

logger = logging.getLogger(__name__)


class ProfileInUseError(RuntimeError):
    pass


def _refuse_if_in_use(profile_dir: Path) -> None:
    if profile_in_use(profile_dir):
        raise ProfileInUseError(
            f"A browser is already running on {profile_dir}. "
            "Stop the MCP server (or close that browser) first."
        )


async def interactive_login() -> int:
    """Run a headed login and record it. Returns how many cookies were saved."""
    config = get_config()
    profile_dir = get_profile_dir()
    _refuse_if_in_use(profile_dir)

    launch_options, viewport = build_launch_options(config.browser)
    describe_launch(launch_options)
    async with BrowserManager(
        user_data_dir=profile_dir,
        headless=False,
        slow_mo=config.browser.slow_mo,
        viewport=viewport,
        default_timeout=config.browser.default_timeout,
        **launch_options,
    ) as browser:
        # An existing session skips the form: the login page would redirect
        # anyway, and landing on the dashboard is what the wait looks for.
        await browser.page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
        if "/dashboard" not in browser.page.url:
            await browser.page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print(
            "Log in to Pangram in the browser window. "
            "Use email and password if Google sign-in refuses this browser."
        )
        await wait_for_manual_login(browser.page, config.browser.login_timeout)
        count = await browser.export_cookies(portable_cookie_path(profile_dir))

    write_source_state(profile_dir)
    logger.info("Login saved (%d cookies)", count)
    return count


async def session_status() -> tuple[bool, str]:
    """Open the saved profile headless and check the dashboard loads."""
    config = get_config()
    profile_dir = get_profile_dir()
    state = load_source_state(profile_dir)
    if state is None:
        return False, "No saved login. Run with --login."
    _refuse_if_in_use(profile_dir)

    launch_options, viewport = build_launch_options(config.browser)
    async with BrowserManager(
        user_data_dir=profile_dir,
        headless=config.browser.headless,
        viewport=viewport,
        default_timeout=config.browser.default_timeout,
        **launch_options,
    ) as browser:
        valid = await check_session(browser.page)
    if valid:
        return True, f"Session valid (logged in {state.created_at})."
    return False, "Session expired. Run with --login."


def logout() -> str:
    """Delete the saved profile, but only one this server created.

    ``source-state.json`` naming exactly this profile is the proof of
    ownership: ``--user-data-dir`` accepts any path, and a mistyped one must
    not cost a directory nobody meant to name.
    """
    profile_dir = get_profile_dir()
    state = load_source_state(profile_dir)
    if state is None or Path(state.profile_path) != profile_dir:
        return (
            f"Not deleting {profile_dir}: no login record from this server "
            "names it. Remove it by hand if you are sure."
        )
    _refuse_if_in_use(profile_dir)
    shutil.rmtree(profile_dir, ignore_errors=False)
    portable_cookie_path(profile_dir).unlink(missing_ok=True)
    source_state_path(profile_dir).unlink(missing_ok=True)
    return f"Deleted {profile_dir} and its saved cookies."
