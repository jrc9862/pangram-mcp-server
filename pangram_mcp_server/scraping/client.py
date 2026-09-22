"""Pangram-specific calls, made through the logged-in page.

The dashboard is a Next.js front end over a JSON API at
``https://web.pangram.com/api/``. Rather than fill the textarea and read the
rendered result, every call here runs ``fetch`` inside the page, from the
``www.pangram.com`` origin, with the page's own cookies and the CSRF token the
app itself fetches. The requests are the ones the dashboard sends, and nothing
depends on class names, button text or the UI language.

Endpoints and payloads were captured from the live app; see
``docs/web-app-notes.md``.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from patchright.async_api import Page

from pangram_mcp_server.core.auth import PANGRAM_BASE_URL, is_auth_blocker_url
from pangram_mcp_server.core.exceptions import (
    AuthenticationError,
    InvalidInputError,
    PangramError,
    QuotaExceededError,
    ScanFailedError,
)

logger = logging.getLogger(__name__)

API_BASE = "https://web.pangram.com/api"
MIN_WORDS = 50
WORDS_PER_CREDIT = 100
POLL_INTERVAL_SECONDS = 2.0
SCAN_TIMEOUT_SECONDS = 150.0
FILE_EXTENSIONS = {".docx", ".pdf", ".rtf", ".txt", ".md"}
MAX_FILE_BYTES = 20 * 1024 * 1024

# One round trip through the page. Returns {status, body} and never throws, so
# an HTTP error reaches Python with its body intact.
_FETCH_JS = """
async ({url, method, json, csrf}) => {
  const headers = {accept: 'application/json'};
  if (csrf) headers['X-CSRFToken'] = csrf;
  const init = {method, headers, credentials: 'include'};
  if (json !== null && json !== undefined) {
    headers['content-type'] = 'application/json';
    init.body = JSON.stringify(json);
  }
  try {
    const r = await fetch(url, init);
    const text = await r.text();
    let body = text;
    try { body = JSON.parse(text); } catch (e) {}
    return {status: r.status, body};
  } catch (e) {
    return {status: 0, body: String(e)};
  }
}
"""

_UPLOAD_JS = """
async ({url, csrf, name, b64, mime}) => {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const form = new FormData();
  form.append('file', new Blob([bytes], {type: mime}), name);
  try {
    const r = await fetch(url, {
      method: 'POST', body: form, credentials: 'include',
      headers: {accept: 'application/json', 'X-CSRFToken': csrf},
    });
    const text = await r.text();
    let body = text;
    try { body = JSON.parse(text); } catch (e) {}
    return {status: r.status, body};
  } catch (e) {
    return {status: 0, body: String(e)};
  }
}
"""

_MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".rtf": "application/rtf",
}


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def credits_for(word_count: int) -> int:
    return max(1, math.ceil(word_count / WORDS_PER_CREDIT))


@dataclass
class ApiResponse:
    status: int
    body: Any

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def message(self) -> str:
        if isinstance(self.body, dict):
            for key in ("error", "message", "detail"):
                if isinstance(self.body.get(key), str):
                    return self.body[key]
        return str(self.body)[:300]


class PangramClient:
    """Pangram operations over one logged-in page."""

    def __init__(self, page: Page):
        self.page = page
        self._csrf: str | None = None

    # -- transport -------------------------------------------------------

    async def _ensure_origin(self) -> None:
        """``fetch`` needs the www.pangram.com origin for its cookies and CORS."""
        if not self.page.url.startswith(PANGRAM_BASE_URL):
            await self.page.goto(f"{PANGRAM_BASE_URL}/dashboard", wait_until="commit")
        if is_auth_blocker_url(self.page.url):
            raise AuthenticationError("Pangram session expired. Run with --login.")

    async def _csrf_token(self) -> str:
        if self._csrf is None:
            resp = await self._call("GET", "/accounts/get-csrf/", csrf=False)
            token = resp.body.get("csrfToken") if isinstance(resp.body, dict) else None
            if not resp.ok or not token:
                raise PangramError(f"Could not get a CSRF token: {resp.message()}")
            self._csrf = token
        return self._csrf

    async def _call(
        self,
        method: str,
        path: str,
        json: Any = None,
        *,
        csrf: bool = True,
        retried: bool = False,
    ) -> ApiResponse:
        await self._ensure_origin()
        token = await self._csrf_token() if csrf else None
        raw = await self.page.evaluate(
            _FETCH_JS,
            {"url": f"{API_BASE}{path}", "method": method, "json": json, "csrf": token},
        )
        resp = ApiResponse(status=raw["status"], body=raw["body"])
        logger.debug("%s %s -> %s", method, path, resp.status)
        if resp.status in (401, 403) and not _is_quota(resp):
            # A rejected CSRF token also answers 403; retry once with a new one
            # before calling the session dead.
            if csrf and not retried:
                self._csrf = None
                return await self._call(method, path, json, csrf=csrf, retried=True)
            raise AuthenticationError(
                f"Pangram rejected the session ({resp.status}). Run with --login."
            )
        if resp.status == 0:
            raise PangramError(f"Network error calling Pangram: {resp.body}")
        return resp

    # -- account ---------------------------------------------------------

    async def session_status(self) -> dict[str, Any]:
        resp = await self._call("GET", "/session-status/", csrf=False)
        if not resp.ok or not isinstance(resp.body, dict):
            raise PangramError(f"session-status failed: {resp.message()}")
        if not resp.body.get("isAuthenticated"):
            raise AuthenticationError("Pangram session expired. Run with --login.")
        return resp.body

    async def account(self) -> dict[str, Any]:
        s = await self.session_status()
        return {
            "email": s.get("email"),
            "plan": s.get("plan") or "Free",
            "credits_remaining": s.get("creditsRemaining"),
            "credits_total": s.get("creditsTotal"),
            "last_free_credit_refresh": s.get("lastFreeCreditUpdated"),
            "paid_features": bool(s.get("haveAccessToPaidFeatures")),
        }

    # -- text ------------------------------------------------------------

    async def classify_text(self, text: str) -> dict[str, Any]:
        """Run one AI-detection scan and return the finished result."""
        text = text.strip()
        words = count_words(text)
        if words < MIN_WORDS:
            raise InvalidInputError(
                f"Pangram needs at least {MIN_WORDS} words; got {words}."
            )
        status = await self.session_status()
        needed = credits_for(words)
        remaining = status.get("creditsRemaining")
        if isinstance(remaining, int) and remaining < needed:
            raise QuotaExceededError(
                f"This scan needs {needed} credits ({words} words) and "
                f"{remaining} remain."
            )

        resp = await self._call(
            "POST",
            "/classify-text-sliding-window/",
            {
                # Same body the dashboard sends. `logging` keeps the scan in
                # history, as a scan from the dashboard would be.
                "text": text,
                "source": "product",
                "logging": True,
                "distinctId": status.get("email"),
                "include_plagiarism": False,
            },
        )
        _raise_for_scan(resp)
        body = resp.body
        if isinstance(body, dict) and body.get("task_id"):
            return await self._wait_for_task(body["task_id"])
        # Short texts may be answered inline rather than queued.
        if isinstance(body, dict) and "response" in body:
            return body
        raise ScanFailedError(f"Unexpected response from Pangram: {resp.message()}")

    async def _wait_for_task(self, task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + SCAN_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            resp = await self._call(
                "POST",
                "/classify-text-sliding-window/status/",
                {"task_ids": [task_id]},
            )
            _raise_for_scan(resp)
            tasks = resp.body.get("tasks") if isinstance(resp.body, dict) else None
            task = tasks[0] if tasks else {}
            state = task.get("status")
            if state == "success" and isinstance(task.get("result"), dict):
                return task["result"]
            if state not in (None, "background_processing", "pending", "processing"):
                raise ScanFailedError(f"Pangram scan ended with status {state!r}.")
        raise ScanFailedError(
            f"Pangram did not finish the scan within {SCAN_TIMEOUT_SECONDS:.0f}s."
        )

    # -- url -------------------------------------------------------------

    async def extract_url(self, url: str) -> dict[str, Any]:
        """Fetch a page's text through Pangram's extractor (no credits)."""
        if not re.match(r"^https?://", url):
            raise InvalidInputError("URL must start with http:// or https://.")
        resp = await self._call("POST", "/url-scan/extract/", {"url": url})
        if not resp.ok or not isinstance(resp.body, dict) or not resp.body.get("text"):
            raise ScanFailedError(f"Pangram could not read that URL: {resp.message()}")
        return resp.body

    # -- files -----------------------------------------------------------

    async def classify_file(self, path: Path) -> dict[str, Any]:
        """Upload a document through the dashboard's batch flow and wait for it."""
        path = path.expanduser()
        if not path.is_file():
            raise InvalidInputError(f"No such file: {path}")
        suffix = path.suffix.lower()
        if suffix not in FILE_EXTENSIONS:
            raise InvalidInputError(
                f"Unsupported file type {suffix!r}; use one of "
                + ", ".join(sorted(FILE_EXTENSIONS))
            )
        if suffix in (".txt", ".md"):
            # Plain text needs no server-side extraction; scan it as text.
            return await self.classify_text(path.read_text(errors="replace"))
        data = path.read_bytes()
        if len(data) > MAX_FILE_BYTES:
            raise InvalidInputError(f"{path.name} is over 20 MB.")
        await self.session_status()

        created = await self._call("POST", "/batch-upload/", {})
        _raise_for_scan(created)
        batch_id = created.body.get("id") if isinstance(created.body, dict) else None
        if not batch_id:
            raise ScanFailedError(f"Could not create an upload: {created.message()}")

        raw = await self.page.evaluate(
            _UPLOAD_JS,
            {
                "url": f"{API_BASE}/upload/batch/{batch_id}/",
                "csrf": await self._csrf_token(),
                "name": path.name,
                "b64": base64.b64encode(data).decode(),
                "mime": _MIME_TYPES[suffix],
            },
        )
        uploaded = ApiResponse(status=raw["status"], body=raw["body"])
        _raise_for_scan(uploaded)

        deadline = time.monotonic() + SCAN_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            resp = await self._call(
                "GET", f"/batch-upload/{batch_id}/status/", csrf=False
            )
            _raise_for_scan(resp)
            done = _finished_file(resp.body)
            if done is not None:
                uuid = done.get("uuid") or done.get("textquery_uuid")
                if uuid:
                    return await self.history_item(uuid)
                return done
        raise ScanFailedError(
            f"Pangram did not finish {path.name} within {SCAN_TIMEOUT_SECONDS:.0f}s."
        )

    # -- history ---------------------------------------------------------

    async def history(
        self, limit: int = 10, offset: int = 0, search: str = ""
    ) -> dict[str, Any]:
        from urllib.parse import urlencode

        query = urlencode(
            {
                "search": search,
                "order": "DESC",
                "limit": limit,
                "offset": offset,
                "prediction": "Human,AI,Mixed",
            }
        )
        resp = await self._call("GET", f"/history-list/?{query}", csrf=False)
        if not resp.ok or not isinstance(resp.body, dict):
            raise PangramError(f"history-list failed: {resp.message()}")
        return resp.body

    async def history_item(self, uuid: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", uuid):
            raise InvalidInputError("scan_id must be a UUID from get_scan_history.")
        resp = await self._call("GET", f"/history/{uuid}/")
        if resp.status == 404:
            raise InvalidInputError(f"No scan {uuid} in this account's history.")
        if not resp.ok or not isinstance(resp.body, dict):
            raise PangramError(f"history lookup failed: {resp.message()}")
        return resp.body


def _is_quota(resp: ApiResponse) -> bool:
    if resp.status in (402, 429):
        return True
    text = resp.message().lower()
    return any(w in text for w in ("credit", "limit", "quota", "upgrade", "scans"))


def _raise_for_scan(resp: ApiResponse) -> None:
    if resp.ok:
        return
    if _is_quota(resp):
        raise QuotaExceededError(resp.message())
    if resp.status == 400:
        raise InvalidInputError(resp.message())
    raise ScanFailedError(f"Pangram returned {resp.status}: {resp.message()}")


def _finished_file(body: Any) -> dict[str, Any] | None:
    """Return the file entry once the batch reports it finished, else None.

    The batch status shape is read defensively: it was taken from the app's
    bundle, not from a captured response.
    """
    if not isinstance(body, dict):
        return None
    files = body.get("files") or body.get("batch_files") or []
    for entry in files if isinstance(files, list) else []:
        state = str(entry.get("analysis_status") or entry.get("status") or "").lower()
        if state in ("failed", "error"):
            raise ScanFailedError(
                entry.get("error") or entry.get("message") or "Pangram failed the file."
            )
        if state in ("success", "completed", "complete", "done"):
            return entry
    state = str(body.get("status") or "").lower()
    if state in ("failed", "error"):
        raise ScanFailedError(body.get("error") or "Pangram failed the upload.")
    return None


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    """Flatten a classify or history result into the tool's structured fields."""
    overall = (result.get("response") or {}).get("overall") or {}
    segments = [
        {
            "start_index": w.get("start_index"),
            "end_index": w.get("end_index"),
            "label": w.get("label"),
            "confidence": w.get("confidence"),
            "ai_likelihood": w.get("ai_likelihood"),
            "word_count": w.get("word_count"),
            "is_humanized": w.get("is_humanized"),
        }
        for w in overall.get("windows") or []
    ]
    summary: dict[str, Any] = {
        "scan_id": result.get("textquery_uuid") or result.get("uuid"),
        "verdict": overall.get("prediction_short") or result.get("category_label"),
        "headline": overall.get("headline"),
        "prediction": overall.get("prediction") or result.get("prediction"),
        "fraction_ai": overall.get("fraction_ai"),
        "fraction_ai_assisted": overall.get("fraction_ai_assisted"),
        "fraction_human": overall.get("fraction_human"),
        "fraction_mixed": overall.get("fraction_mixed"),
        "ai_likelihood": overall.get("avg_ai_likelihood")
        or result.get("ai_likelihood")
        or result.get("prediction_prob"),
        "word_count": overall.get("word_count"),
        "model_version": overall.get("version"),
        "segments": segments,
    }
    if "credits_remaining" in result:
        summary["credits_remaining"] = result["credits_remaining"]
    return {k: v for k, v in summary.items() if v is not None}


def render_text(summary: dict[str, Any], text: str | None = None) -> str:
    """A short plain-text report for ``sections.result``."""
    lines = [
        f"Verdict: {summary.get('verdict', 'unknown')}"
        + (f" ({summary['headline']})" if summary.get("headline") else ""),
    ]
    if summary.get("prediction"):
        lines.append(summary["prediction"])
    fractions = [
        (label, summary.get(key))
        for label, key in (
            ("AI", "fraction_ai"),
            ("AI-assisted", "fraction_ai_assisted"),
            ("Human", "fraction_human"),
        )
    ]
    if any(v is not None for _, v in fractions):
        lines.append(
            "Share: "
            + ", ".join(f"{label} {v:.0%}" for label, v in fractions if v is not None)
        )
    for i, seg in enumerate(summary.get("segments", []), 1):
        excerpt = ""
        if text is not None and seg.get("start_index") is not None:
            chunk = text[seg["start_index"] : seg["end_index"]]
            excerpt = " — " + " ".join(chunk.split())[:120]
        lines.append(
            f"Segment {i}: {seg.get('label')} "
            f"(confidence {seg.get('confidence')}, "
            f"likelihood {seg.get('ai_likelihood', 0):.2f}){excerpt}"
        )
    return "\n".join(lines)
