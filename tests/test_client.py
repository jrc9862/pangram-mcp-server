"""PangramClient against a fake page that answers like the captured API."""

from typing import Any, cast

import pytest
from patchright.async_api import Page

from pangram_mcp_server.core.exceptions import (
    AuthenticationError,
    InvalidInputError,
    QuotaExceededError,
    ScanFailedError,
)
from pangram_mcp_server.scraping import client as client_module
from pangram_mcp_server.scraping.client import (
    PangramClient,
    credits_for,
    render_text,
    summarize,
)

WORDS_60 = " ".join(["word"] * 60)

# Trimmed from the live capture in docs/web-app-notes.md.
RESULT: dict[str, Any] = {
    "text": WORDS_60,
    "textquery_uuid": "a0ccf921-bc2e-48e5-8cb4-d5a045906a71",
    "credits_remaining": 18,
    "response": {
        "overall": {
            "prediction_short": "Mixed",
            "headline": "AI Detected",
            "prediction": "We believe that this text is a mix of AI and human-written content.",
            "fraction_ai": 0.57,
            "fraction_ai_assisted": 0.0,
            "fraction_human": 0.43,
            "fraction_mixed": 0.0,
            "avg_ai_likelihood": 0.52,
            "word_count": 60,
            "version": "4.0",
            "windows": [
                {
                    "start_index": 0,
                    "end_index": 20,
                    "label": "AI-Generated",
                    "confidence": "Low",
                    "ai_likelihood": 0.55,
                    "word_count": 4,
                    "is_humanized": False,
                },
                {
                    "start_index": 20,
                    "end_index": 40,
                    "label": "Human",
                    "confidence": "Low",
                    "ai_likelihood": 0.49,
                    "word_count": 4,
                    "is_humanized": False,
                },
            ],
        }
    },
}

SESSION = {
    "isAuthenticated": True,
    "email": "user@example.com",
    "creditsRemaining": 20,
    "creditsTotal": 20,
    "plan": None,
}


class FakePage:
    """Routes the client's in-page fetches to canned (status, body) replies."""

    def __init__(self, routes):
        self.url = "https://www.pangram.com/dashboard"
        self.routes = routes
        self.calls = []

    async def goto(self, url, **kwargs):
        self.url = url

    async def evaluate(self, script, arg):
        path = arg["url"].removeprefix(client_module.API_BASE)
        self.calls.append((arg.get("method", "POST"), path, arg.get("json")))
        for prefix, reply in self.routes.items():
            if path.startswith(prefix):
                status, body = reply(arg) if callable(reply) else reply
                return {"status": status, "body": body}
        raise AssertionError(f"unexpected call {path}")


def make_client(page: FakePage) -> PangramClient:
    return PangramClient(cast(Page, page))


def base_routes(**overrides):
    routes = {
        "/accounts/get-csrf/": (200, {"csrfToken": "tok"}),
        "/session-status/": (200, SESSION),
    }
    routes.update(overrides)
    return routes


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", instant)


def test_credits_round_up():
    assert credits_for(1) == 1
    assert credits_for(100) == 1
    assert credits_for(101) == 2


async def test_classify_polls_until_success():
    polls = iter(
        [
            (200, {"tasks": [{"task_id": "t1", "status": "background_processing"}]}),
            (
                200,
                {"tasks": [{"task_id": "t1", "status": "success", "result": RESULT}]},
            ),
        ]
    )
    page = FakePage(
        base_routes(
            **{
                "/classify-text-sliding-window/status/": lambda _: next(polls),
                "/classify-text-sliding-window/": (
                    202,
                    {"status": "background_processing", "task_id": "t1"},
                ),
            }
        )
    )
    result = await make_client(page).classify_text(WORDS_60)
    assert result is RESULT
    submit = next(c for c in page.calls if c[1] == "/classify-text-sliding-window/")
    assert submit[2]["text"] == WORDS_60
    assert submit[2]["include_plagiarism"] is False


async def test_short_text_is_refused_before_any_call():
    page = FakePage(base_routes())
    with pytest.raises(InvalidInputError, match="at least 50 words"):
        await make_client(page).classify_text("too short")
    assert page.calls == []


async def test_insufficient_credits_is_refused_before_submitting():
    page = FakePage(
        base_routes(**{"/session-status/": (200, {**SESSION, "creditsRemaining": 1})})
    )
    with pytest.raises(QuotaExceededError, match="needs 3 credits"):
        await make_client(page).classify_text(" ".join(["w"] * 250))
    assert not any("classify" in c[1] for c in page.calls)


async def test_server_quota_error_is_reported():
    page = FakePage(
        base_routes(
            **{
                "/classify-text-sliding-window/": (
                    429,
                    {"error": "Daily scan limit reached."},
                )
            }
        )
    )
    with pytest.raises(QuotaExceededError, match="Daily scan limit"):
        await make_client(page).classify_text(WORDS_60)


async def test_failed_task_raises():
    page = FakePage(
        base_routes(
            **{
                "/classify-text-sliding-window/status/": (
                    200,
                    {"tasks": [{"task_id": "t1", "status": "failed"}]},
                ),
                "/classify-text-sliding-window/": (202, {"task_id": "t1"}),
            }
        )
    )
    with pytest.raises(ScanFailedError, match="failed"):
        await make_client(page).classify_text(WORDS_60)


async def test_logged_out_session_raises_auth_error():
    page = FakePage(
        base_routes(**{"/session-status/": (200, {"isAuthenticated": False})})
    )
    with pytest.raises(AuthenticationError):
        await make_client(page).account()


async def test_page_on_login_route_raises_auth_error():
    class StuckOnLogin(FakePage):
        async def goto(self, url, **kwargs):
            pass

    page = StuckOnLogin(base_routes())
    page.url = "https://www.pangram.com/login"
    with pytest.raises(AuthenticationError):
        await make_client(page).account()


async def test_rejected_csrf_is_retried_once_then_auth_error():
    page = FakePage(
        base_routes(**{"/classify-text-sliding-window/": (403, {"detail": "CSRF"})})
    )
    with pytest.raises(AuthenticationError):
        await make_client(page).classify_text(WORDS_60)
    csrf_fetches = [c for c in page.calls if c[1] == "/accounts/get-csrf/"]
    assert len(csrf_fetches) == 2


async def test_history_item_rejects_non_uuid():
    with pytest.raises(InvalidInputError):
        await make_client(FakePage(base_routes())).history_item("../../etc")


async def test_file_rejects_unknown_extension(tmp_path):
    f = tmp_path / "x.exe"
    f.write_bytes(b"MZ")
    with pytest.raises(InvalidInputError, match="Unsupported"):
        await make_client(FakePage(base_routes())).classify_file(f)


async def test_text_file_is_scanned_as_text(tmp_path, monkeypatch):
    f = tmp_path / "essay.txt"
    f.write_text(WORDS_60)
    seen = {}

    async def fake_classify(self, text):
        seen["text"] = text
        return RESULT

    monkeypatch.setattr(PangramClient, "classify_text", fake_classify)
    await make_client(FakePage(base_routes())).classify_file(f)
    assert seen["text"] == WORDS_60


def test_summarize_flattens_result():
    s = summarize(RESULT)
    assert s["verdict"] == "Mixed"
    assert s["scan_id"] == RESULT["textquery_uuid"]
    assert s["credits_remaining"] == 18
    assert [seg["label"] for seg in s["segments"]] == ["AI-Generated", "Human"]


def test_render_text_quotes_segments():
    text = render_text(summarize(RESULT), RESULT["text"])
    assert text.startswith("Verdict: Mixed (AI Detected)")
    assert "AI 57%" in text
    assert "Segment 2: Human" in text
