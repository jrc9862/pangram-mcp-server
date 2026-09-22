# pangram-mcp-server

An MCP server that runs [Pangram](https://www.pangram.com) AI-text detection
through your own logged-in Pangram account. It drives a real Chromium profile
with Patchright, the same way
[linkedin-mcp-server](https://github.com/stickerdaniel/linkedin-mcp-server)
does: you log in once in a visible browser, and tool calls reuse that session
headless.

> Pangram's Terms of Service (§5.2, §10) prohibit accessing the service
> through software other than Pangram's own. Using this server may get the
> account suspended. The official, supported route is the
> [Pangram API](https://docs.pangram.com/api-reference/introduction).

## Tools

| Tool | Cost | What it does |
|---|---|---|
| `detect_ai_text` | 1 credit / 100 words | Scan text (50-word minimum) |
| `detect_ai_url` | by extracted words | Read a web page with Pangram's extractor, then scan it |
| `detect_ai_file` | by words | Scan a `.docx`, `.pdf`, `.rtf`, `.txt` or `.md` file |
| `get_account` | free | Plan and remaining credits |
| `get_scan_history` | free | Past scans, newest first |
| `get_scan` | free | Full result of a past scan |
| `close_session` | free | Close the browser |

Scans return a verdict (`AI`, `Human`, `Mixed`), the AI / AI-assisted / human
fractions, per-segment labels with confidence, and a link to the scan in your
Pangram history.

## Setup

```bash
uv sync
uv run patchright install chromium
uv run -m pangram_mcp_server --login     # log in in the window that opens
uv run -m pangram_mcp_server --status    # check the saved session
```

Use email and password if Google sign-in refuses the automated browser.

Add it to Claude Code:

```bash
claude mcp add pangram -- uv --directory "$HOME/Coding Projects/pangram-mcp-server" run -m pangram_mcp_server
```

## Configuration

CLI flags override `PANGRAM_MCP_*` environment variables (also read from `.env`).

| Flag | Env | Default |
|---|---|---|
| `--no-headless` | `PANGRAM_MCP_HEADLESS=false` | headless |
| `--transport` | `PANGRAM_MCP_TRANSPORT` | `stdio` |
| `--host` / `--port` / `--path` | `PANGRAM_MCP_HOST` / `_PORT` / `_HTTP_PATH` | `127.0.0.1` / `8000` / `/mcp` |
| `--user-data-dir` | `PANGRAM_MCP_USER_DATA_DIR` | `~/.pangram-mcp/profile` |
| `--tool-timeout` | `PANGRAM_MCP_TOOL_TIMEOUT` | `180` s |
| `--login-timeout` | `PANGRAM_MCP_LOGIN_TIMEOUT` | `1800` s (0 = no limit) |
| `--proxy-server` etc. | `PANGRAM_MCP_PROXY_*` | none |

`--logout` deletes the saved profile, but only one this server created.

## Development

```bash
uv sync --group dev
uv run ruff check . && uv run ruff format --check . && uv run ty check
uv run pytest --cov
```

`docs/web-app-notes.md` records the Pangram endpoints this server calls and
how they were measured.
