import pytest

from pangram_mcp_server.core.auth import is_auth_blocker_url, is_authenticated_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.pangram.com/login",
        "https://www.pangram.com/login?next=/dashboard",
        "https://www.pangram.com/signup",
        "https://accounts.google.com/o/oauth2/auth",
    ],
)
def test_blocker_urls(url):
    assert is_auth_blocker_url(url)
    assert not is_authenticated_url(url)


@pytest.mark.parametrize(
    "url",
    ["https://www.pangram.com/dashboard", "https://www.pangram.com/dashboard/"],
)
def test_authenticated_urls(url):
    assert is_authenticated_url(url)
    assert not is_auth_blocker_url(url)


def test_marketing_pages_are_neither():
    url = "https://www.pangram.com/pricing"
    assert not is_auth_blocker_url(url)
    assert not is_authenticated_url(url)


def test_lookalike_host_is_not_authenticated():
    assert not is_authenticated_url("https://www.pangram.com.evil.test/dashboard")


@pytest.mark.parametrize(
    "url",
    ["https://www.pangram.com/fr/login", "https://www.pangram.com/pt-br/signup"],
)
def test_localized_login_routes_are_blockers(url):
    assert is_auth_blocker_url(url)


def test_localized_dashboard_is_authenticated():
    assert is_authenticated_url("https://www.pangram.com/de/dashboard")


def test_suffix_lookalike_host_is_a_blocker():
    assert is_auth_blocker_url("https://evilpangram.com/dashboard")
