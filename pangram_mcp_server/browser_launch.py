"""Launch options shared by every browser this server starts.

The login and the tool calls build their options here so a setting added for
one cannot silently miss the other. A session created while leaking has been
leaking since the moment it existed.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pangram_mcp_server.config.schema import BrowserConfig

logger = logging.getLogger(__name__)

# WebRTC uses UDP, which an HTTP proxy does not carry, so without these it
# goes around the proxy and exposes the real address in ICE candidates. Full
# Chromium reads the plain switch; chrome-headless-shell reads only `--force-`.
# Measured in linkedin-mcp-server; see its browser_launch.py.
_WEBRTC_STAYS_ON_THE_PROXY = (
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
)


def build_launch_options(
    browser: "BrowserConfig",
) -> tuple[dict[str, Any], dict[str, int]]:
    """Return the Patchright launch options and the viewport."""
    viewport = {"width": browser.viewport_width, "height": browser.viewport_height}

    # Without a channel Playwright picks chromium-headless-shell for headless
    # and full Chromium for headed, so the login and the tool calls would run
    # two different browsers on one session. The channel pins the full one.
    launch_options: dict[str, Any] = {"channel": "chromium"}

    proxy = browser.proxy_settings()
    if proxy:
        launch_options["proxy"] = proxy
        launch_options["args"] = list(_WEBRTC_STAYS_ON_THE_PROXY)

    return launch_options, viewport


def describe_launch(launch_options: dict[str, Any]) -> None:
    """Log the launch configuration without proxy credentials."""
    proxy = launch_options.get("proxy")
    if proxy:
        logger.info("Routing browser traffic through proxy %s", proxy["server"])
        logger.info("WebRTC restricted to the proxy; direct UDP is disabled")
