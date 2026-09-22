from unittest.mock import AsyncMock, MagicMock

import pytest

from pangram_mcp_server.config import AppConfig, reset_config, set_config
from pangram_mcp_server.dependencies import reset_client_for_testing
from pangram_mcp_server.drivers.browser import reset_browser_for_testing


@pytest.fixture(autouse=True)
def ignore_the_developers_environment(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith("PANGRAM_MCP_"):
            monkeypatch.delenv(key)
    # load_dotenv() must not pull a developer's .env into a test.
    monkeypatch.setattr("pangram_mcp_server.config.loaders.load_dotenv", lambda: None)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path):
    config = AppConfig()
    config.browser.user_data_dir = str(tmp_path / "auth" / "profile")
    set_config(config)
    yield config
    reset_config()


@pytest.fixture(autouse=True)
def reset_singletons():
    reset_browser_for_testing()
    reset_client_for_testing()
    yield
    reset_browser_for_testing()
    reset_client_for_testing()


@pytest.fixture
def profile_dir(isolated_config):
    from pangram_mcp_server.session_state import get_profile_dir

    path = get_profile_dir()
    path.mkdir(parents=True)
    (path / "Default").mkdir()
    return path


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    return ctx
