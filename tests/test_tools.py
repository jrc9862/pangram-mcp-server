from collections.abc import Callable, Coroutine
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import FunctionTool

from pangram_mcp_server.core.exceptions import AuthenticationError, QuotaExceededError
from pangram_mcp_server.server import create_mcp_server
from tests.test_client import RESULT


async def get_tool_fn(
    mcp: FastMCP, name: str
) -> Callable[..., Coroutine[Any, Any, dict[str, Any]]]:
    tool = await mcp.get_tool(name)
    if tool is None:
        raise ValueError(f"Tool '{name}' not found")
    return cast(FunctionTool, tool).fn


@pytest.fixture
def mcp():
    return create_mcp_server()


def mock_client(**methods):
    client = MagicMock()
    for name, value in methods.items():
        setattr(
            client,
            name,
            AsyncMock(side_effect=value)
            if isinstance(value, BaseException)
            else AsyncMock(return_value=value),
        )
    return client


async def test_all_tools_registered(mcp):
    names = {t.name for t in await mcp.list_tools()}
    assert names == {
        "detect_ai_text",
        "detect_ai_url",
        "detect_ai_file",
        "get_account",
        "get_scan_history",
        "get_scan",
        "close_session",
    }


async def test_client_is_not_exposed_as_an_argument(mcp):
    tool = await mcp.get_tool("detect_ai_text")
    assert "client" not in tool.parameters["properties"]


async def test_detect_ai_text_shapes_result(mcp, mock_context):
    fn = await get_tool_fn(mcp, "detect_ai_text")
    result = await fn(mock_context, text="x", client=mock_client(classify_text=RESULT))
    assert result["url"].endswith("/history/a0ccf921-bc2e-48e5-8cb4-d5a045906a71")
    assert result["verdict"] == "Mixed"
    assert "Verdict: Mixed" in result["sections"]["result"]


async def test_detect_ai_url_adds_source(mcp, mock_context):
    fn = await get_tool_fn(mcp, "detect_ai_url")
    client = mock_client(
        extract_url={"text": "page text", "url": "https://e.test/a", "truncated": True},
        classify_text=RESULT,
    )
    result = await fn(mock_context, url="https://e.test/a", client=client)
    client.classify_text.assert_awaited_once_with("page text")
    assert result["source_url"] == "https://e.test/a"
    assert result["truncated"] is True


async def test_quota_error_becomes_tool_error(mcp, mock_context):
    fn = await get_tool_fn(mcp, "detect_ai_text")
    client = mock_client(classify_text=QuotaExceededError("0 credits remain."))
    with pytest.raises(ToolError, match="quota reached"):
        await fn(mock_context, text="x", client=client)


async def test_auth_error_closes_browser_and_says_login(mcp, mock_context, monkeypatch):
    closed = AsyncMock()
    monkeypatch.setattr("pangram_mcp_server.tools.detect.handle_auth_error", closed)
    fn = await get_tool_fn(mcp, "detect_ai_text")
    client = mock_client(classify_text=AuthenticationError("Run with --login."))
    with pytest.raises(ToolError, match="--login"):
        await fn(mock_context, text="x", client=client)
    closed.assert_awaited_once()


async def test_history_lists_scans(mcp, mock_context):
    page = {
        "count": 1,
        "results": [
            {
                "uuid": "574c4bf7-3780-463a-a605-5d41a8bc9e43",
                "timestamp": "2026-09-22T15:40:48-04:00",
                "file_name": "Text Query",
                "category_label": "AI",
                "prediction_prob": 0.88,
                "input_type": "text",
                "prompt": "Some   scanned\n text",
            }
        ],
    }
    fn = await get_tool_fn(mcp, "get_scan_history")
    result = await fn(mock_context, client=mock_client(history=page))
    assert result["total"] == 1
    assert result["scans"][0]["verdict"] == "AI"
    assert result["scans"][0]["preview"] == "Some scanned text"


async def test_no_saved_login_is_a_clear_tool_error(mcp, mock_context):
    fn = await get_tool_fn(mcp, "get_account")
    with pytest.raises(ToolError, match="--login"):
        await fn(mock_context)
