"""Tests for auth barrier detection helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from instagram_mcp_server.core.exceptions import AuthenticationError
from instagram_mcp_server.core.auth import (
    detect_auth_barrier,
    detect_auth_barrier_quick,
    is_logged_in,
    wait_for_manual_login,
)


@pytest.mark.asyncio
async def test_detect_auth_barrier_for_account_picker():
    page = MagicMock()
    page.url = "https://www.instagram.com/accounts/login/"
    page.title = AsyncMock(return_value="Instagram Login")
    page.evaluate = AsyncMock(
        return_value="Welcome Back\nSign in using another account\nJoin now"
    )

    result = await detect_auth_barrier(page)

    assert result is not None
    assert "auth blocker URL" in result


@pytest.mark.asyncio
async def test_detect_auth_barrier_for_continue_as_account_picker():
    page = MagicMock()
    page.url = "https://www.instagram.com/accounts/login/"
    page.title = AsyncMock(return_value="Instagram Sign In")
    page.evaluate = AsyncMock(
        return_value="Continue as Daniel Sticker\nSign in using another account"
    )

    result = await detect_auth_barrier(page)

    assert result is not None


@pytest.mark.asyncio
async def test_detect_auth_barrier_for_choose_account_picker():
    page = MagicMock()
    page.url = "https://www.instagram.com/accounts/login/"
    page.title = AsyncMock(return_value="Instagram Sign In")
    page.evaluate = AsyncMock(
        return_value="Choose an account\nSign in using another account"
    )

    result = await detect_auth_barrier(page)

    assert result is not None


@pytest.mark.asyncio
async def test_detect_auth_barrier_returns_none_for_authenticated_page():
    page = MagicMock()
    page.url = "https://www.instagram.com/feed/"
    page.title = AsyncMock(return_value="Instagram Feed")
    page.evaluate = AsyncMock(return_value="Home\nMy Network\nJobs\nMessaging")

    result = await detect_auth_barrier(page)

    assert result is None


@pytest.mark.asyncio
async def test_detect_auth_barrier_quick_skips_body_text_on_authenticated_page():
    page = MagicMock()
    page.url = "https://www.instagram.com/feed/"
    page.title = AsyncMock(return_value="Instagram Feed")
    page.evaluate = AsyncMock(return_value="Home\nMy Network\nJobs\nMessaging")

    result = await detect_auth_barrier_quick(page)

    assert result is None
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_is_logged_in_rejects_empty_authenticated_only_page():
    page = MagicMock()
    page.url = "https://www.instagram.com/feed/"
    page.locator.return_value.count = AsyncMock(return_value=0)
    page.evaluate = AsyncMock(return_value="")

    result = await is_logged_in(page)

    assert result is False


@pytest.mark.asyncio
async def test_is_logged_in_accepts_authenticated_only_page_with_content():
    page = MagicMock()
    page.url = "https://www.instagram.com/feed/"
    page.locator.return_value.count = AsyncMock(return_value=0)
    page.evaluate = AsyncMock(return_value="Home\nSearch\nExplore\nReels\nMessages")

    result = await is_logged_in(page)

    assert result is True


@pytest.mark.asyncio
async def test_detect_auth_barrier_ignores_continue_as_in_page_content():
    page = MagicMock()
    page.url = "https://www.instagram.com/p/123456/"
    page.title = AsyncMock(return_value="Software Engineer at Acme - Instagram")
    page.evaluate = AsyncMock(
        return_value="We need someone to continue as a senior engineer on our team."
    )

    result = await detect_auth_barrier(page)

    assert result is None


@pytest.mark.asyncio
async def test_detect_auth_barrier_ignores_choose_account_in_page_content():
    page = MagicMock()
    page.url = "https://www.instagram.com/p/123456/"
    page.title = AsyncMock(return_value="Software Engineer at Acme - Instagram")
    page.evaluate = AsyncMock(
        return_value="You will choose an account strategy for the next quarter."
    )

    result = await detect_auth_barrier(page)

    assert result is None


@pytest.mark.asyncio
async def test_detect_auth_barrier_ignores_auth_substrings_in_slugs():
    page = MagicMock()
    page.url = "https://www.instagram.com/challenge-labs/"
    page.title = AsyncMock(return_value="Challenge Labs | Instagram")
    page.evaluate = AsyncMock(return_value="Challenge Labs builds developer tools.")

    result = await detect_auth_barrier(page)

    assert result is None


@pytest.mark.asyncio
async def test_wait_for_manual_login_returns_when_logged_in(monkeypatch):
    page = MagicMock()

    async def fake_is_logged_in(_page):
        return True

    monkeypatch.setattr(
        "instagram_mcp_server.core.auth.is_logged_in", fake_is_logged_in
    )

    await wait_for_manual_login(page, timeout=1000)


@pytest.mark.asyncio
async def test_wait_for_manual_login_times_out(monkeypatch):
    page = MagicMock()

    class _FakeLoop:
        def __init__(self):
            self._times = iter([0.0, 1.1])

        def time(self):
            return next(self._times)

    monkeypatch.setattr(
        "instagram_mcp_server.core.auth.is_logged_in",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "instagram_mcp_server.core.auth.asyncio.get_running_loop",
        lambda: _FakeLoop(),
    )

    with pytest.raises(AuthenticationError, match="Manual login timeout"):
        await wait_for_manual_login(page, timeout=1000)
