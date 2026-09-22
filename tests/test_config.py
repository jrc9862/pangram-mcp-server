import pytest

from pangram_mcp_server.config.loaders import load_config
from pangram_mcp_server.config.schema import ConfigurationError


def test_defaults():
    config = load_config([])
    assert config.browser.headless is True
    assert config.server.transport == "stdio"
    assert config.browser.user_data_dir == "~/.pangram-mcp/profile"


def test_env_overrides_defaults(monkeypatch):
    monkeypatch.setenv("PANGRAM_MCP_HEADLESS", "false")
    monkeypatch.setenv("PANGRAM_MCP_PORT", "9000")
    config = load_config([])
    assert config.browser.headless is False
    assert config.server.port == 9000


def test_args_override_env(monkeypatch):
    monkeypatch.setenv("PANGRAM_MCP_PORT", "9000")
    config = load_config(["--port", "9100", "--transport", "streamable-http"])
    assert config.server.port == 9100
    assert config.server.transport == "streamable-http"


def test_empty_env_is_unset(monkeypatch):
    monkeypatch.setenv("PANGRAM_MCP_USER_DATA_DIR", "")
    assert load_config([]).browser.user_data_dir == "~/.pangram-mcp/profile"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("PANGRAM_MCP_HEADLESS", "maybe"),
        ("PANGRAM_MCP_PORT", "eighty"),
        ("PANGRAM_MCP_PROXY_SERVER", "proxy.example:8080"),
    ],
)
def test_invalid_env_is_refused(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ConfigurationError):
        load_config([])


def test_login_modes_are_exclusive():
    with pytest.raises(SystemExit):
        load_config(["--login", "--logout"])
