"""Process-wide configuration singleton."""

from .loaders import load_config
from .schema import AppConfig, BrowserConfig, ConfigurationError, ServerConfig

_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Return the configuration, loading it on first use."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: AppConfig) -> None:
    global _config
    _config = config


def reset_config() -> None:
    global _config
    _config = None


__all__ = [
    "AppConfig",
    "BrowserConfig",
    "ConfigurationError",
    "ServerConfig",
    "get_config",
    "reset_config",
    "set_config",
]
