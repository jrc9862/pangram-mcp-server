# CLAUDE.md

## Development Commands

- Dependencies: `uv sync --group dev`
- Lint / format: `uv run ruff check .` / `uv run ruff format .`
- Type check: `uv run ty check`
- Tests: `uv run pytest` (coverage: `uv run pytest --cov`)
- Install browser: `uv run patchright install chromium`
- Log in: `uv run -m pangram_mcp_server --login`; check: `--status`
- Run over HTTP: `uv run -m pangram_mcp_server --transport streamable-http --log-level DEBUG`

## Rules

- **Talk to Pangram through its own JSON API, from inside the page.** All
  Pangram calls live in `scraping/client.py` and run `fetch` in the logged-in
  page against `https://web.pangram.com/api/`, with the page's cookies and the
  app's CSRF token. No DOM selectors, no button text, no class names.
- **Every endpoint and payload must be measured.** `docs/web-app-notes.md` is
  the record; update it with each change. The file-upload status shape is
  still unmeasured.
- **Credits are real money and a daily limit.** Free accounts get 20 credits and
  3 scans a day. Check credits before submitting, never retry a scan
  automatically, and keep live verification to one or two scans. Prefer the
  free calls (`session-status`, `history-list`, `history/<uuid>`,
  `url-scan/extract`) when testing.
- **No evasion.** No CAPTCHA solving, no `user_agent` overrides, no injected
  headers or fingerprints. `BrowserManager` refuses `user_agent`. If Pangram
  starts challenging the browser, stop and tell the user.
- **Tool calls run one at a time** (`SequentialToolExecutionMiddleware`);
  they share one page.
- **Never open a login window from a tool call.** On `AuthenticationError`,
  close the browser and tell the user to run `--login`.
- **Only delete what this server created.** `--logout` removes a profile only
  when `source-state.json` names it. Resolve paths with
  `session_state.canonical()`.
- **Never write credentials to disk or logs.** Discovery scripts must skip
  `input[type=password]` values and request bodies for `/api/login/`.

## Tool Return Format

`{url, sections: {name: text}, ...structured fields}`. Scan tools add
`scan_id`, `verdict`, `headline`, `prediction`, `fraction_*`,
`ai_likelihood`, `word_count`, `model_version`, `segments[]` and
`credits_remaining`.
