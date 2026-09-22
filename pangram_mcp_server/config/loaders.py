"""Load configuration from defaults, then environment, then CLI arguments."""

import argparse
import os

from dotenv import load_dotenv

from .schema import AppConfig, ConfigurationError

TRUTHY_VALUES = {"1", "true", "yes", "on"}
FALSY_VALUES = {"0", "false", "no", "off"}


class EnvironmentKeys:
    HEADLESS = "PANGRAM_MCP_HEADLESS"
    LOG_LEVEL = "PANGRAM_MCP_LOG_LEVEL"
    TRANSPORT = "PANGRAM_MCP_TRANSPORT"
    HOST = "PANGRAM_MCP_HOST"
    PORT = "PANGRAM_MCP_PORT"
    HTTP_PATH = "PANGRAM_MCP_HTTP_PATH"
    TIMEOUT = "PANGRAM_MCP_TIMEOUT"
    TOOL_TIMEOUT = "PANGRAM_MCP_TOOL_TIMEOUT"
    LOGIN_TIMEOUT = "PANGRAM_MCP_LOGIN_TIMEOUT"
    SLOW_MO = "PANGRAM_MCP_SLOW_MO"
    USER_DATA_DIR = "PANGRAM_MCP_USER_DATA_DIR"
    PROXY_SERVER = "PANGRAM_MCP_PROXY_SERVER"
    PROXY_USERNAME = "PANGRAM_MCP_PROXY_USERNAME"
    PROXY_PASSWORD = "PANGRAM_MCP_PROXY_PASSWORD"


def _env(key: str) -> str | None:
    """Return the variable's value, treating unset and empty alike."""
    value = os.environ.get(key, "").strip()
    return value or None


def _bool(key: str, value: str) -> bool:
    lowered = value.lower()
    if lowered in TRUTHY_VALUES:
        return True
    if lowered in FALSY_VALUES:
        return False
    raise ConfigurationError(f"{key} must be true or false, got {value!r}")


def _number(key: str, value: str, kind: type[int] | type[float]) -> int | float:
    try:
        return kind(value)
    except ValueError:
        raise ConfigurationError(f"{key} must be a number, got {value!r}") from None


def load_from_env(config: AppConfig) -> AppConfig:
    keys = EnvironmentKeys
    if (v := _env(keys.HEADLESS)) is not None:
        config.browser.headless = _bool(keys.HEADLESS, v)
    if (v := _env(keys.LOG_LEVEL)) is not None:
        level = v.upper()
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise ConfigurationError(f"Invalid {keys.LOG_LEVEL}: {v!r}")
        config.server.log_level = level  # type: ignore[assignment]
    if (v := _env(keys.TRANSPORT)) is not None:
        if v not in ("stdio", "streamable-http"):
            raise ConfigurationError(f"Invalid {keys.TRANSPORT}: {v!r}")
        config.server.transport = v  # type: ignore[assignment]
    if (v := _env(keys.HOST)) is not None:
        config.server.host = v
    if (v := _env(keys.PORT)) is not None:
        config.server.port = int(_number(keys.PORT, v, int))
    if (v := _env(keys.HTTP_PATH)) is not None:
        config.server.path = v
    if (v := _env(keys.TIMEOUT)) is not None:
        config.browser.default_timeout = int(_number(keys.TIMEOUT, v, int))
    if (v := _env(keys.TOOL_TIMEOUT)) is not None:
        config.server.tool_timeout = float(_number(keys.TOOL_TIMEOUT, v, float))
    if (v := _env(keys.LOGIN_TIMEOUT)) is not None:
        config.browser.login_timeout = int(_number(keys.LOGIN_TIMEOUT, v, int))
    if (v := _env(keys.SLOW_MO)) is not None:
        config.browser.slow_mo = int(_number(keys.SLOW_MO, v, int))
    if (v := _env(keys.USER_DATA_DIR)) is not None:
        config.browser.user_data_dir = v
    config.browser.proxy_server = _env(keys.PROXY_SERVER) or config.browser.proxy_server
    config.browser.proxy_username = (
        _env(keys.PROXY_USERNAME) or config.browser.proxy_username
    )
    config.browser.proxy_password = (
        _env(keys.PROXY_PASSWORD) or config.browser.proxy_password
    )
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-server-pangram",
        description="Pangram AI-detection MCP server driven by your own browser session.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--login", action="store_true", help="Open a browser to log in to Pangram"
    )
    mode.add_argument(
        "--status", action="store_true", help="Check whether the saved session works"
    )
    mode.add_argument(
        "--logout", action="store_true", help="Delete the saved browser profile"
    )
    parser.add_argument(
        "--no-headless", action="store_true", help="Show the browser window"
    )
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=None
    )
    parser.add_argument(
        "--transport", choices=["stdio", "streamable-http"], default=None
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--path", default=None, help="HTTP path (default /mcp)")
    parser.add_argument("--user-data-dir", default=None)
    parser.add_argument(
        "--timeout", type=int, default=None, help="Page timeout in milliseconds"
    )
    parser.add_argument(
        "--tool-timeout", type=float, default=None, help="Tool timeout in seconds"
    )
    parser.add_argument(
        "--login-timeout",
        type=int,
        default=None,
        help="Seconds to wait for a manual login; 0 waits indefinitely",
    )
    parser.add_argument("--slow-mo", type=int, default=None)
    parser.add_argument("--proxy-server", default=None)
    parser.add_argument("--proxy-username", default=None)
    parser.add_argument("--proxy-password", default=None)
    return parser


def load_from_args(config: AppConfig, argv: list[str] | None = None) -> AppConfig:
    args = build_parser().parse_args(argv)
    config.server.login = args.login
    config.server.status = args.status
    config.server.logout = args.logout
    if args.no_headless:
        config.browser.headless = False
    overrides = {
        ("server", "log_level"): args.log_level,
        ("server", "transport"): args.transport,
        ("server", "host"): args.host,
        ("server", "port"): args.port,
        ("server", "path"): args.path,
        ("server", "tool_timeout"): args.tool_timeout,
        ("browser", "user_data_dir"): args.user_data_dir,
        ("browser", "default_timeout"): args.timeout,
        ("browser", "login_timeout"): args.login_timeout,
        ("browser", "slow_mo"): args.slow_mo,
        ("browser", "proxy_server"): args.proxy_server,
        ("browser", "proxy_username"): args.proxy_username,
        ("browser", "proxy_password"): args.proxy_password,
    }
    for (section, name), value in overrides.items():
        if value is not None:
            setattr(getattr(config, section), name, value)
    return config


def load_config(argv: list[str] | None = None) -> AppConfig:
    """Build the configuration: defaults, then .env and environment, then CLI."""
    load_dotenv()
    config = load_from_args(load_from_env(AppConfig()), argv)
    config.validate()
    return config
