"""
Interactive setup flows for Instagram MCP Server authentication.

Handles session creation through interactive browser login using Patchright
with persistent context. Profile state auto-persists to user_data_dir.
"""

import asyncio
from pathlib import Path
from typing import Any

from instagram_mcp_server.config import get_config
from instagram_mcp_server.core import (
    BrowserManager,
    wait_for_manual_login,
    warm_up_browser,
)
from instagram_mcp_server.session_state import (
    portable_cookie_path,
    write_source_state,
)

from instagram_mcp_server.drivers.browser import get_profile_dir
from instagram_mcp_server.cookie_import import import_cookies_interactive


async def interactive_login(
    user_data_dir: Path | None = None, warm_up: bool = True
) -> bool:
    """
    Open browser for manual Instagram login with persistent profile.

    Opens a non-headless browser, navigates to Instagram login page,
    and waits for user to complete authentication (including 2FA, captcha, etc.).
    Profile state auto-persists to user_data_dir.

    Args:
        user_data_dir: Path to browser profile. Defaults to config's user_data_dir.
        warm_up: Visit normal sites first to appear more human-like (default: True)

    Returns:
        True if login was successful

    Raises:
        Exception: If login fails or times out
    """
    if user_data_dir is None:
        user_data_dir = get_profile_dir()

    print("Opening browser for Instagram login...")
    print("   Please log in manually. You have 5 minutes to complete authentication.")
    print("   (This handles 2FA, captcha, and any security challenges)")

    launch_options: dict[str, Any] = {}
    config = get_config()

    # Use system Brave browser by default - critical for avoiding bot detection
    # Patchright's bundled Chromium is detected by Instagram's advanced bot detection
    if config.browser.chrome_path:
        launch_options["executable_path"] = config.browser.chrome_path
    else:
        # Default to Brave if available (most resistant to fingerprinting)
        brave_paths = [
            "/opt/brave-bin/brave",
            "/usr/bin/brave-browser",
            "/usr/bin/brave",
            Path.home() / ".local/bin/brave",
        ]
        for brave_path in brave_paths:
            brave_exe = Path(brave_path) if isinstance(brave_path, str) else brave_path
            if brave_exe.exists():
                launch_options["executable_path"] = str(brave_exe)
                print(f"   Using Brave browser: {brave_exe}")
                break
        else:
            print("   Warning: Brave not found, using default browser")

    viewport = {
        "width": config.browser.viewport_width,
        "height": config.browser.viewport_height,
    }

    async with BrowserManager(
        user_data_dir=user_data_dir,
        headless=False,
        slow_mo=config.browser.slow_mo,
        user_agent=config.browser.user_agent,
        viewport=viewport,
        **launch_options,
    ) as browser:
        # Warm up browser to appear more human-like and avoid security checkpoints
        if warm_up:
            print("   Warming up browser (visiting normal sites first)...")
            await warm_up_browser(browser.page)

        # Navigate to Instagram login page
        # Using /accounts/login/ directly instead of homepage to avoid redirects
        print("   Navigating to Instagram login...")
        await browser.page.goto("https://www.instagram.com/accounts/login/")

        # Wait for page to fully load and any auto-redirects to complete
        await asyncio.sleep(1)

        # Wait for manual login completion
        # 3 minute timeout (180000ms) allows time for 2FA, captcha, security challenges
        await wait_for_manual_login(browser.page, timeout=180000)

        # Wait for persistent context to flush cookies to disk
        await asyncio.sleep(1)

        # Verify session cookie was persisted
        cookies = await browser.context.cookies()
        sessionid = [c for c in cookies if c["name"] == "sessionid"]
        if not sessionid:
            print("   Warning: Session cookie not found. Login may not have persisted.")
            print("   Waiting longer for cookie propagation...")
            await asyncio.sleep(2)

        # Export source-session cookies for the one-time foreign-runtime bridge.
        # Docker now checkpoint-commits its own derived runtime profile after the
        # first successful /feed/ recovery instead of relying on browser teardown.
        if await browser.export_cookies(portable_cookie_path(user_data_dir)):
            print("   Cookies exported for Docker portability")
            source_state = write_source_state(user_data_dir)
            print(f"   Source session generation: {source_state.login_generation}")
        else:
            print(
                "   Warning: cookie export failed; Docker bridge may not work. "
                "Run --login again to retry."
            )
            return False
        print(f"Profile saved to {user_data_dir}")
        return True


def run_profile_creation(user_data_dir: str | None = None) -> bool:
    """
    Create profile via interactive login with persistent context.

    Args:
        user_data_dir: Path to profile directory. Defaults to config's user_data_dir.

    Returns:
        True if profile was created successfully
    """
    from instagram_mcp_server.drivers.browser import _cdp_mode_enabled

    if _cdp_mode_enabled():
        return _run_cdp_profile_creation(user_data_dir)

    if user_data_dir:
        profile_dir = Path(user_data_dir).expanduser()
    else:
        profile_dir = get_profile_dir()

    print("Instagram MCP Server - Profile Creation")
    print(f"   Profile will be saved to: {profile_dir}")
    print()

    # First, try to import cookies from existing Brave session
    print("Step 1: Attempting to import cookies from Brave browser...")
    if import_cookies_interactive():
        print("   ✓ Cookie import successful!")
        print("   You can now use the MCP server.")
        return True

    print()
    print("Step 2: Automated browser login...")
    print()

    try:
        success = asyncio.run(interactive_login(profile_dir))
        if success:
            return True

        # Automated login failed, offer manual cookie import
        print()
        print("=" * 60)
        print("Automated login failed. Instagram's bot detection blocked the")
        print("browser. Please use the manual cookie import method:")
        print("=" * 60)
        print()

        from instagram_mcp_server.cookie_import import manual_cookie_import_guide

        manual_cookie_import_guide()

        return False

    except Exception as e:
        print(f"Login failed: {e}")
        print()
        print("Please use the manual cookie import method.")
        from instagram_mcp_server.cookie_import import manual_cookie_import_guide

        manual_cookie_import_guide()
        return False


def _run_cdp_profile_creation(user_data_dir: str | None = None) -> bool:
    """
    Create profile using CDP mode (connect to running Brave browser).

    Args:
        user_data_dir: Path to profile directory. Defaults to config's user_data_dir.

    Returns:
        True if profile was created successfully
    """
    if user_data_dir:
        profile_dir = Path(user_data_dir).expanduser()
    else:
        profile_dir = get_profile_dir()

    print("Instagram MCP Server - Profile Creation (CDP Mode)")
    print(f"   Profile will be saved to: {profile_dir}")
    print()

    # First, try to import cookies from existing Brave session
    print("Step 1: Attempting to import cookies from Brave browser...")
    if import_cookies_interactive():
        print("   ✓ Cookie import successful!")
        print("   You can now use the MCP server.")
        return True

    print()
    print("Step 2: Export session from running Brave browser...")
    print()

    try:
        success = asyncio.run(_cdp_export_session(profile_dir))
        if success:
            return True

        # CDP export failed, offer manual cookie import
        print()
        print("=" * 60)
        print("Session export failed. Please use the manual cookie import method:")
        print("=" * 60)
        print()

        from instagram_mcp_server.cookie_import import manual_cookie_import_guide

        manual_cookie_import_guide()

        return False

    except Exception as e:
        print(f"Session export failed: {e}")
        print()
        print("Please use the manual cookie import method.")
        from instagram_mcp_server.cookie_import import manual_cookie_import_guide

        manual_cookie_import_guide()
        return False


async def _cdp_export_session(profile_dir: Path) -> bool:
    """
    Export Instagram session from running Brave browser via CDP.

    Args:
        profile_dir: Path to save profile data

    Returns:
        True if export was successful
    """
    from instagram_mcp_server.drivers.brave_cdp import (
        connect_to_brave,
        find_brave_process,
        verify_instagram_session,
    )
    from instagram_mcp_server.session_state import portable_cookie_path
    from instagram_mcp_server.common_utils import secure_write_text
    import json

    print("   Checking for running Brave browser with remote debugging...")

    if not find_brave_process():
        print("   ⚠ Brave browser not running with --remote-debugging-port=9222")
        print()
        print("   Please launch Brave with remote debugging enabled:")
        print("     brave-browser --remote-debugging-port=9222")
        print()
        print("   Or use the helper script:")
        print("     uv run instagram-launch-brave")
        return False

    print("   ✓ Brave detected! Connecting...")

    try:
        browser = await connect_to_brave(timeout=30)
    except Exception as e:
        print(f"   ⚠ Failed to connect to Brave: {e}")
        print()
        print("   Make sure Brave is running with --remote-debugging-port=9222")
        return False

    try:
        print("   Verifying Instagram session...")
        has_session = await verify_instagram_session(browser)

        if not has_session:
            print("   ⚠ Not logged in to Instagram")
            print()
            print("   Please log into Instagram in the Brave browser:")
            print("     1. Navigate to https://www.instagram.com/")
            print("     2. Log in with your credentials")
            print("     3. Run --login again to export the session")
            return False

        print("   ✓ Instagram session verified!")

        # Export cookies
        cookie_path = portable_cookie_path(profile_dir)
        print(f"   Exporting cookies to {cookie_path}...")

        if not browser.contexts:
            context = await browser.new_context()
        else:
            context = browser.contexts[0]

        cookies = await context.cookies()
        secure_write_text(cookie_path, json.dumps(cookies, indent=2))
        print(f"   ✓ Exported {len(cookies)} cookies")

        # Write source state
        print("   Writing source state metadata...")
        source_state = write_source_state(profile_dir)
        print(f"   ✓ Source session generation: {source_state.login_generation}")

        print()
        print("   ✓ Profile creation successful!")
        print(f"   Profile saved to {profile_dir}")
        return True

    except Exception as e:
        print(f"   ⚠ Failed to export session: {e}")
        return False
    finally:
        try:
            await browser.close()
        except Exception:
            pass


def run_interactive_setup() -> bool:
    """
    Run interactive setup - browser login only.

    Returns:
        True if setup completed successfully
    """
    print("Instagram MCP Server Setup")
    print("   Opening browser for manual login...")

    try:
        return asyncio.run(interactive_login())
    except Exception as e:
        print(f"Login failed: {e}")
        return False
