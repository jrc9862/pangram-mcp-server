"""Configuration dataclasses and defaults."""

from dataclasses import dataclass, field
from typing import Literal

DEFAULT_USER_DATA_DIR = "~/.pangram-mcp/profile"
DEFAULT_TOOL_TIMEOUT_SECONDS = 180.0
DEFAULT_LOGIN_TIMEOUT_SECONDS = 1800

Transport = Literal["stdio", "streamable-http"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class ConfigurationError(Exception):
    """Raised when the configuration is invalid."""


@dataclass
class BrowserConfig:
    headless: bool = True
    slow_mo: int = 0
    viewport_width: int = 1280
    viewport_height: int = 900
    #: Playwright default timeout for navigation and waits, in milliseconds.
    default_timeout: int = 30_000
    user_data_dir: str = DEFAULT_USER_DATA_DIR
    #: Seconds to wait for a manual login; 0 waits indefinitely.
    login_timeout: int = DEFAULT_LOGIN_TIMEOUT_SECONDS
    proxy_server: str | None = None
    proxy_username: str | None = None
    proxy_password: str | None = None

    def proxy_settings(self) -> dict[str, str] | None:
        if not self.proxy_server:
            return None
        proxy = {"server": self.proxy_server}
        if self.proxy_username:
            proxy["username"] = self.proxy_username
        if self.proxy_password:
            proxy["password"] = self.proxy_password
        return proxy


@dataclass
class ServerConfig:
    transport: Transport = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"
    log_level: LogLevel = "WARNING"
    tool_timeout: float = DEFAULT_TOOL_TIMEOUT_SECONDS
    login: bool = False
    status: bool = False
    logout: bool = False


@dataclass
class AppConfig:
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

    def validate(self) -> None:
        if not 1 <= self.server.port <= 65535:
            raise ConfigurationError(f"Invalid port: {self.server.port}")
        if not self.server.path.startswith("/"):
            raise ConfigurationError(
                f"HTTP path must start with '/': {self.server.path}"
            )
        if self.server.tool_timeout <= 0:
            raise ConfigurationError("Tool timeout must be positive")
        if self.browser.login_timeout < 0:
            raise ConfigurationError("Login timeout must be 0 or positive")
        if self.browser.proxy_server and "://" not in self.browser.proxy_server:
            raise ConfigurationError(
                "PANGRAM_MCP_PROXY_SERVER needs a scheme, e.g. http://host:8080"
            )
