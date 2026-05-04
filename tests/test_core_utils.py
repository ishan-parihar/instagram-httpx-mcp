"""Tests for core utility functions (stubs, API-based)."""

from instagram_mcp_server.core.utils import detect_rate_limit


async def test_detect_rate_limit_noop():
    """detect_rate_limit is a no-op in API mode."""
    await detect_rate_limit()  # Should not raise
    await detect_rate_limit(None)  # Should not raise
