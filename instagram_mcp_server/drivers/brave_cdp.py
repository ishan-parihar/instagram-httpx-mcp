"""
Brave browser CDP (Chrome DevTools Protocol) connection.

Connects to an already-running Brave browser instance instead of
launching automated browsers. This eliminates bot detection by using
the real browser's fingerprint and session.
"""

import logging
import subprocess
from typing import Any

from patchright.async_api import Browser, Playwright, async_playwright

logger = logging.getLogger(__name__)

DEFAULT_DEBUGGING_PORT = 9222


def find_brave_process() -> int | None:
    """
    Find running Brave process with remote debugging enabled.

    Returns:
        PID if found, None otherwise
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", "brave.*remote-debugging-port"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            return int(pids[0]) if pids else None
        return None
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        return None


def get_debugging_address(port: int | None = None) -> str:
    """
    Get the CDP debugging address for Brave browser.

    Args:
        port: Remote debugging port. Defaults to 9222.

    Returns:
        CDP WebSocket address
    """
    debugging_port = port or DEFAULT_DEBUGGING_PORT
    return f"http://localhost:{debugging_port}"


async def connect_to_brave(
    port: int | None = None,
    timeout: float = 30.0,
) -> Browser:
    """
    Connect to running Brave browser via CDP.

    Args:
        port: Remote debugging port. Defaults to 9222.
        timeout: Connection timeout in seconds

    Returns:
        Connected Browser instance

    Raises:
        ConnectionError: If Brave is not running with remote debugging
    """
    debugging_address = get_debugging_address(port)

    logger.info(f"Connecting to Brave at {debugging_address}...")

    try:
        playwright: Playwright = await async_playwright().start()

        browser = await playwright.chromium.connect_over_cdp(
            debugging_address,
            timeout=timeout * 1000,
        )

        logger.info("Successfully connected to Brave browser via CDP")
        return browser

    except Exception as e:
        logger.error(f"Failed to connect to Brave: {e}")
        raise ConnectionError(
            f"Could not connect to Brave browser at {debugging_address}. "
            f"Ensure Brave is running with --remote-debugging-port={port or DEFAULT_DEBUGGING_PORT}"
        ) from e


async def verify_instagram_session(browser: Browser) -> bool:
    """
    Verify that the connected Brave browser has an active Instagram session.

    Args:
        browser: Connected Browser instance

    Returns:
        True if logged in to Instagram
    """
    try:
        if not browser.contexts:
            context = await browser.new_context()
        else:
            context = browser.contexts[0]

        if not context.pages:
            page = await context.new_page()
        else:
            page = context.pages[0]

        await page.goto(
            "https://www.instagram.com/feed/", wait_until="domcontentloaded"
        )

        from instagram_mcp_server.core.auth import detect_auth_barrier_quick

        barrier = await detect_auth_barrier_quick(page)
        if barrier:
            logger.warning(f"Instagram auth barrier detected: {barrier}")
            return False

        cookies = await context.cookies()
        has_sessionid = any(c["name"] == "sessionid" for c in cookies)

        if not has_sessionid:
            logger.warning("No sessionid cookie found in Brave session")
            return False

        logger.info("Instagram session verified in Brave browser")
        return True

    except Exception as e:
        logger.error(f"Failed to verify Instagram session: {e}")
        return False
