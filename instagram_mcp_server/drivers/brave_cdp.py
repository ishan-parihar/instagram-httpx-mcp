"""
Brave browser CDP (Chrome DevTools Protocol) connection.

Connects to an already-running Brave browser instance instead of
launching automated browsers. This eliminates bot detection by using
the real browser's fingerprint and session.
"""

import logging
import subprocess
import sys
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
    if sys.platform == "win32":
        return _find_brave_process_windows()
    else:
        return _find_brave_process_unix()


def _find_brave_process_unix() -> int | None:
    """Find Brave process on Unix-like systems (Linux, macOS)."""
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


def _find_brave_process_windows() -> int | None:
    """Find Brave process on Windows with remote debugging enabled."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq brave.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, "CREATE_NO_WINDOW")
            else 0,
        )

        if result.returncode == 0 and "brave.exe" in result.stdout.lower():
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if (
                    "brave.exe" in line.lower()
                    and "remote-debugging-port" in line.lower()
                ):
                    parts = line.split(",")
                    if len(parts) >= 2:
                        pid_str = parts[1].strip('"')
                        if pid_str.isdigit():
                            return int(pid_str)
        return None
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        return None


def get_debugging_address(port: int | None = None) -> str:
    """
    Get the CDP debugging address for Brave browser.

    Args:
        port: Remote debugging port. Defaults to 9222 or config value.

    Returns:
        CDP WebSocket address
    """
    if port is None:
        from instagram_mcp_server.config import get_config

        config = get_config()
        port = config.browser.cdp_port

    # Use 127.0.0.1 instead of localhost to avoid IPv6 issues
    return f"http://127.0.0.1:{port}"


async def connect_to_brave(
    port: int | None = None,
    timeout: float = 60.0,
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

        # Connect to existing Brave instance via CDP
        # Use the browser endpoint - Playwright will discover available contexts
        browser = await playwright.chromium.connect_over_cdp(
            debugging_address,
            timeout=timeout * 1000,  # Convert to milliseconds
        )

        logger.info("Successfully connected to Brave browser via CDP")
        return browser

    except Exception as e:
        logger.error(f"Failed to connect to Brave: {e}")
        raise ConnectionError(
            f"Could not connect to Brave browser at {debugging_address}. "
            f"Ensure Brave is running with --remote-debugging-port={port or DEFAULT_DEBUGGING_PORT}\n"
            f"Error: {e}"
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
