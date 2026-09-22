"""AI-detection tools: text, URL and file."""

import logging
from pathlib import Path
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field

from pangram_mcp_server.config.schema import DEFAULT_TOOL_TIMEOUT_SECONDS
from pangram_mcp_server.core.auth import PANGRAM_BASE_URL
from pangram_mcp_server.core.exceptions import AuthenticationError
from pangram_mcp_server.dependencies import get_ready_client, handle_auth_error
from pangram_mcp_server.error_handler import raise_tool_error
from pangram_mcp_server.scraping.client import render_text, summarize

logger = logging.getLogger(__name__)

_ANNOTATIONS = {"readOnlyHint": False, "openWorldHint": True, "idempotentHint": False}


def scan_url(scan_id: str | None) -> str:
    if scan_id:
        return f"{PANGRAM_BASE_URL}/history/{scan_id}"
    return f"{PANGRAM_BASE_URL}/dashboard"


def build_result(raw: dict[str, Any], **extra: Any) -> dict[str, Any]:
    summary = summarize(raw)
    return {
        "url": scan_url(summary.get("scan_id")),
        "sections": {
            "result": render_text(summary, raw.get("text") or raw.get("prompt"))
        },
        **summary,
        **extra,
    }


def register_detect_tools(
    mcp: FastMCP, *, tool_timeout: float = DEFAULT_TOOL_TIMEOUT_SECONDS
) -> None:
    @mcp.tool(
        timeout=tool_timeout,
        title="Detect AI Text",
        annotations=_ANNOTATIONS,
        tags={"detection"},
        exclude_args=["client"],
    )
    async def detect_ai_text(
        ctx: Context,
        text: Annotated[
            str, Field(description="Text to check; at least 50 words.", min_length=1)
        ],
        client: Any | None = None,
    ) -> dict[str, Any]:
        """
        Check whether text was written by AI, using the user's Pangram account.

        Costs 1 credit per 100 words from the user's Pangram balance, and the
        scan is saved in their Pangram history. Minimum 50 words.

        Returns:
            url: the scan in Pangram's history.
            sections.result: plain-text report.
            verdict: "AI", "Human" or "Mixed"; plus headline, prediction,
            fraction_ai, fraction_ai_assisted, fraction_human, ai_likelihood,
            word_count, model_version, credits_remaining, and segments
            (start_index/end_index into the scanned text, label, confidence).
        """
        try:
            client = client or await get_ready_client(ctx)
            await ctx.report_progress(progress=0, total=100, message="Scanning")
            raw = await client.classify_text(text)
            await ctx.report_progress(progress=100, total=100, message="Complete")
            return build_result(raw)
        except AuthenticationError as e:
            await handle_auth_error()
            raise_tool_error(e, "detect_ai_text")
        except Exception as e:
            raise_tool_error(e, "detect_ai_text")

    @mcp.tool(
        timeout=tool_timeout,
        title="Detect AI Text at URL",
        annotations=_ANNOTATIONS,
        tags={"detection"},
        exclude_args=["client"],
    )
    async def detect_ai_url(
        ctx: Context,
        url: Annotated[str, Field(description="http(s) URL of the page to check.")],
        client: Any | None = None,
    ) -> dict[str, Any]:
        """
        Extract a web page's text with Pangram's URL reader, then check it for AI.

        Costs credits like detect_ai_text, based on the extracted word count.
        Google Docs links are not supported; paste their text instead.

        Returns the same fields as detect_ai_text, plus source_url and
        truncated (whether Pangram cut the page text short).
        """
        try:
            client = client or await get_ready_client(ctx)
            await ctx.report_progress(progress=0, total=100, message="Reading page")
            page = await client.extract_url(url)
            await ctx.report_progress(progress=30, total=100, message="Scanning")
            raw = await client.classify_text(page["text"])
            await ctx.report_progress(progress=100, total=100, message="Complete")
            return build_result(
                raw,
                source_url=page.get("url") or url,
                truncated=bool(page.get("truncated")),
            )
        except AuthenticationError as e:
            await handle_auth_error()
            raise_tool_error(e, "detect_ai_url")
        except Exception as e:
            raise_tool_error(e, "detect_ai_url")

    @mcp.tool(
        timeout=tool_timeout,
        title="Detect AI Text in File",
        annotations=_ANNOTATIONS,
        tags={"detection"},
        exclude_args=["client"],
    )
    async def detect_ai_file(
        ctx: Context,
        path: Annotated[
            str,
            Field(description="Local path to a .docx, .pdf, .rtf, .txt or .md file."),
        ],
        client: Any | None = None,
    ) -> dict[str, Any]:
        """
        Upload a local document to Pangram and check it for AI.

        .txt and .md are read locally and scanned as text; .docx, .pdf and .rtf
        go through Pangram's upload. Costs credits by word count.

        Returns the same fields as detect_ai_text, plus file_name.
        """
        try:
            client = client or await get_ready_client(ctx)
            await ctx.report_progress(progress=0, total=100, message="Uploading")
            raw = await client.classify_file(Path(path))
            await ctx.report_progress(progress=100, total=100, message="Complete")
            return build_result(raw, file_name=Path(path).name)
        except AuthenticationError as e:
            await handle_auth_error()
            raise_tool_error(e, "detect_ai_file")
        except Exception as e:
            raise_tool_error(e, "detect_ai_file")
