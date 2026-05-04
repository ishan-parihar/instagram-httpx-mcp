"""Tests for auth functions (stubs since API-based auth)."""

from instagram_mcp_server.core.auth import (
    detect_auth_barrier,
    detect_auth_barrier_quick,
    is_logged_in,
)


async def test_detect_auth_barrier_returns_none():
    result = await detect_auth_barrier()
    assert result is None


async def test_detect_auth_barrier_quick_returns_none():
    result = await detect_auth_barrier_quick()
    assert result is None


async def test_is_logged_in_returns_true():
    assert is_logged_in() is True
