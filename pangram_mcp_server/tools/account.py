"""Tools that read the account and scan history. None of them cost credits."""

from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field

from pangram_mcp_server.config.schema import DEFAULT_TOOL_TIMEOUT_SECONDS
from pangram_mcp_server.core.auth import PANGRAM_BASE_URL
from pangram_mcp_server.core.exceptions import AuthenticationError
from pangram_mcp_server.dependencies import get_ready_client, handle_auth_error
from pangram_mcp_server.error_handler import raise_tool_error
from pangram_mcp_server.tools.detect import build_result, scan_url

_READ_ONLY = {"readOnlyHint": True, "openWorldHint": True}


def register_account_tools(
    mcp: FastMCP, *, tool_timeout: float = DEFAULT_TOOL_TIMEOUT_SECONDS
) -> None:
    @mcp.tool(
        timeout=tool_timeout,
        title="Get Pangram Account",
        annotations=_READ_ONLY,
        tags={"account"},
        exclude_args=["client"],
    )
    async def get_account(ctx: Context, client: Any | None = None) -> dict[str, Any]:
        """
        Show the Pangram account's plan and remaining credits. Free.

        Check this before a long scan: each scan costs 1 credit per 100 words.
        """
        try:
            client = client or await get_ready_client(ctx)
            account = await client.account()
            return {
                "url": f"{PANGRAM_BASE_URL}/dashboard",
                "sections": {
                    "account": (
                        f"Plan: {account['plan']}\n"
                        f"Credits: {account['credits_remaining']} of "
                        f"{account['credits_total']} remaining"
                    )
                },
                **account,
            }
        except AuthenticationError as e:
            await handle_auth_error()
            raise_tool_error(e, "get_account")
        except Exception as e:
            raise_tool_error(e, "get_account")

    @mcp.tool(
        timeout=tool_timeout,
        title="Get Scan History",
        annotations=_READ_ONLY,
        tags={"history"},
        exclude_args=["client"],
    )
    async def get_scan_history(
        ctx: Context,
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
        offset: Annotated[int, Field(ge=0)] = 0,
        search: Annotated[str, Field(description="Filter by text or file name.")] = "",
        client: Any | None = None,
    ) -> dict[str, Any]:
        """
        List past Pangram text scans, newest first. Free.

        Returns scans[] with scan_id (pass to get_scan), date, file_name,
        verdict, ai_likelihood and a text preview, plus the total count.
        """
        try:
            client = client or await get_ready_client(ctx)
            page = await client.history(limit=limit, offset=offset, search=search)
            scans = [
                {
                    "scan_id": item.get("uuid"),
                    "date": item.get("timestamp"),
                    "file_name": item.get("file_name"),
                    "verdict": item.get("category_label"),
                    "ai_likelihood": item.get("prediction_prob"),
                    "input_type": item.get("input_type"),
                    "source_url": item.get("source_url"),
                    "preview": " ".join((item.get("prompt") or "").split())[:160],
                }
                for item in page.get("results") or []
            ]
            lines = [
                f"{s['date']}  {s['verdict']}  {s['scan_id']}  {s['preview'][:80]}"
                for s in scans
            ]
            return {
                "url": f"{PANGRAM_BASE_URL}/history",
                "sections": {"history": "\n".join(lines) or "No scans."},
                "total": page.get("count"),
                "scans": scans,
            }
        except AuthenticationError as e:
            await handle_auth_error()
            raise_tool_error(e, "get_scan_history")
        except Exception as e:
            raise_tool_error(e, "get_scan_history")

    @mcp.tool(
        timeout=tool_timeout,
        title="Get Scan",
        annotations=_READ_ONLY,
        tags={"history"},
        exclude_args=["client"],
    )
    async def get_scan(
        ctx: Context,
        scan_id: Annotated[str, Field(description="UUID from get_scan_history.")],
        client: Any | None = None,
    ) -> dict[str, Any]:
        """
        Fetch a past scan's full result, including per-segment labels. Free.

        Returns the same fields as detect_ai_text.
        """
        try:
            client = client or await get_ready_client(ctx)
            raw = await client.history_item(scan_id)
            raw.setdefault("uuid", scan_id)
            result = build_result(raw)
            result["url"] = scan_url(scan_id)
            return result
        except AuthenticationError as e:
            await handle_auth_error()
            raise_tool_error(e, "get_scan")
        except Exception as e:
            raise_tool_error(e, "get_scan")
