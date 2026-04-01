"""Test Brave CDP connection module."""

import pytest
from instagram_mcp_server.drivers.brave_cdp import (
    find_brave_process,
    get_debugging_address,
    connect_to_brave,
)


def brave_running() -> bool:
    """Check if Brave is running with remote debugging."""
    return find_brave_process() is not None


class TestFindBraveProcess:
    """Test Brave process detection."""

    def test_returns_pid_or_none(self):
        """Should return PID when Brave is running, None otherwise."""
        pid = find_brave_process()
        assert isinstance(pid, int) or pid is None


class TestGetDebuggingAddress:
    """Test CDP address resolution."""

    def test_default_debugging_port(self):
        """Should return default CDP address when no port specified."""
        address = get_debugging_address()
        assert address == "http://localhost:9222"

    def test_custom_debugging_port(self):
        """Should return custom CDP address when port specified."""
        address = get_debugging_address(port=9223)
        assert address == "http://localhost:9223"


class TestConnectToBrave:
    """Test CDP connection."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not brave_running(), reason="Brave not running with remote debugging"
    )
    async def test_connects_to_running_brave(self):
        """Should successfully connect to running Brave instance."""
        browser = await connect_to_brave()
        assert browser is not None
        assert browser.contexts is not None
        await browser.close()

    @pytest.mark.asyncio
    @pytest.mark.skipif(brave_running(), reason="Brave is running")
    async def test_raises_when_brave_not_running(self):
        """Should raise ConnectionError when Brave is not running."""
        with pytest.raises(ConnectionError):
            await connect_to_brave()
