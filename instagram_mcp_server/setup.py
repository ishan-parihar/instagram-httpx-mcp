"""
Interactive setup flows for Instagram MCP Server authentication.

Handles session creation through interactive browser login or multi-browser
cookie import. Supports ALL major browsers: Brave, Chrome, Edge, Firefox,
Zen, Helium, Chromium, Opera, Arc, Vivaldi, LibreWolf, Waterfox, Floorp.
"""

from __future__ import annotations

import asyncio
import json
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
from instagram_mcp_server.cookie_import import (
    BROWSER_REGISTRY,
    detect_installed_browsers,
    extract_cookies_from_browser,
    find_browser_executable,
    find_any_browser_with_cdp,
    find_browser_with_cdp,
    import_cookies_interactive,
    save_cookies_to_profile,
    validate_cookies,
    choose_browser_interactive,
    manual_cookie_import_guide,
)


def _choose_browser_or_auto() -> str | None:
    """Interactive browser selection. Returns browser_id or None if cancelled."""
    return choose_browser_interactive()


async def interactive_login(
    user_data_dir: Path | None = None,
    warm_up: bool = True,
    browser_id: str | None = None,
) -> bool:
    """
    Open browser for manual Instagram login with persistent profile.

    Opens a non-headless browser, navigates to Instagram login page,
    and waits for user to complete authentication (including 2FA, captcha, etc.).
    Profile state auto-persists to user_data_dir.

    Args:
        user_data_dir: Path to browser profile. Defaults to config's user_data_dir.
        warm_up: Visit normal sites first to appear more human-like (default: True)
        browser_id: Browser to use for login. If None, auto-detects.

    Returns:
        True if login was successful

    Raises:
        Exception: If login fails or times out
    """
    if user_data_dir is None:
        user_data_dir = get_profile_dir()

    # Resolve browser
    if browser_id is None:
        browser_id = _choose_browser_or_auto()
        if browser_id is None:
            print("   ⚠ No browser selected. Falling back to auto-detection.")
            installed = detect_installed_browsers()
            if installed:
                browser_id = installed[0][0]
            else:
                print("   ✗ No supported browsers found.")
                return False

    profile = BROWSER_REGISTRY.get(browser_id)
    if profile is None:
        print(f"   ✗ Unknown browser: {browser_id}")
        return False

    print(f"Opening {profile.name} for Instagram login...")
    print("   Please log in manually. You have 5 minutes to complete authentication.")
    print("   (This handles 2FA, captcha, and any security challenges)")

    launch_options: dict[str, Any] = {}
    config = get_config()

    # Use the selected browser's executable
    exe = find_browser_executable(profile) or config.browser.chrome_path
    if exe:
        launch_options["executable_path"] = str(exe)
        print(f"   Using {profile.name}: {exe}")
    else:
        print(f"   Warning: {profile.name} executable not found, using default")

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


def run_profile_creation(
    user_data_dir: str | None = None,
    browser_id: str | None = None,
) -> bool:
    """
    Create profile via interactive login with persistent context.

    Steps:
    1. Ask which browser to import cookies from (or use specified browser_id)
    2. Try to import cookies from the selected browser
    3. If that fails, offer automated browser login
    4. If that fails, guide manual cookie import

    Args:
        user_data_dir: Path to profile directory. Defaults to config's user_data_dir.
        browser_id: Pre-selected browser ID. If None, prompts user interactively.

    Returns:
        True if profile was created successfully
    """
    from instagram_mcp_server.drivers.browser import _cdp_mode_enabled

    if _cdp_mode_enabled():
        return _run_cdp_profile_creation(user_data_dir, browser_id=browser_id)

    if user_data_dir:
        profile_dir = Path(user_data_dir).expanduser()
    else:
        profile_dir = get_profile_dir()

    print("Instagram MCP Server - Profile Creation")
    print(f"   Profile will be saved to: {profile_dir}")
    print()

    # Step 1: Ask which browser to import cookies from
    print("=" * 60)
    print("  STEP 1: Choose your browser for cookie import")
    print("=" * 60)

    if browser_id is None:
        browser_id = _choose_browser_or_auto()
    if browser_id is None:
        print("   ⚠ No browser selected. Trying auto-detection...")
        installed = detect_installed_browsers()
        if installed:
            browser_id = installed[0][0]
            prof = BROWSER_REGISTRY[browser_id]
            print(f"   Auto-detected: {prof.name}")
        else:
            print("   ✗ No supported browsers detected.")
            print()
            manual_cookie_import_guide()
            return False

    print(f"\n   Importing cookies from {BROWSER_REGISTRY[browser_id].name}...")
    if import_cookies_interactive(browser_id=browser_id):
        print("   ✓ Cookie import successful!")
        print("   You can now use the MCP server.")
        return True

    print()
    print("=" * 60)
    print("  STEP 2: Automated browser login")
    print("=" * 60)
    print()

    try:
        success = asyncio.run(interactive_login(profile_dir, browser_id=browser_id))
        if success:
            return True

        # Automated login failed, offer manual cookie import
        print()
        print("=" * 60)
        print("Automated login failed. Instagram's bot detection blocked the")
        print("browser. Please use the manual cookie import method:")
        print("=" * 60)
        print()

        manual_cookie_import_guide()
        return False

    except Exception as e:
        print(f"Login failed: {e}")
        print()
        print("Please use the manual cookie import method.")
        manual_cookie_import_guide()
        return False


def _run_cdp_profile_creation(
    user_data_dir: str | None = None,
    browser_id: str | None = None,
) -> bool:
    """
    Create profile using CDP mode (connect to running browser).

    Steps:
    1. Ask which browser to import cookies from (or use specified browser_id)
    2. Try cookie extraction from the selected browser
    3. If that fails, try CDP export from a running instance
    4. Fall back to manual import

    Args:
        user_data_dir: Path to profile directory. Defaults to config's user_data_dir.
        browser_id: Pre-selected browser ID. If None, prompts user interactively.

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

    # Step 1: Ask which browser to use
    print("=" * 60)
    print("  STEP 1: Choose your browser for cookie import")
    print("=" * 60)
    print()

    if browser_id is None:
        browser_id = _choose_browser_or_auto()
    if browser_id is None:
        # Auto-detect any browser with CDP enabled
        result = find_any_browser_with_cdp()
        if result:
            browser_id, pid = result
            prof = BROWSER_REGISTRY[browser_id]
            print(f"   Auto-detected: {prof.name} running with CDP (PID: {pid})")
        else:
            print("   ⚠ No browser selected and no CDP-enabled browser detected.")
            print("   Falling back to cookie extraction from installed browsers...")
            installed = detect_installed_browsers()
            if installed:
                browser_id = installed[0][0]
                print(f"   Trying: {BROWSER_REGISTRY[browser_id].name}")
            else:
                print("   ✗ No supported browsers detected.")
                print()
                manual_cookie_import_guide()
                return False

    profile = BROWSER_REGISTRY[browser_id]

    # Step 2: Try direct cookie extraction from browser's SQLite DB
    print(f"\n   Attempting to extract cookies from {profile.name}...")
    cookies = extract_cookies_from_browser(browser_id)

    if cookies:
        is_valid, missing = validate_cookies(cookies)
        if is_valid:
            if save_cookies_to_profile(cookies, profile_dir, source_browser=browser_id):
                print(f"   ✓ Extracted {len(cookies)} cookies from {profile.name}!")
                source_state = write_source_state(profile_dir)
                print(
                    f"   ✓ Source session generation: {source_state.login_generation}"
                )
                print("   You can now use the MCP server.")
                return True
            else:
                print("   ✗ Failed to save extracted cookies.")
        else:
            print(f"   ⚠ Missing required cookies: {missing}")

    # Step 3: Try CDP export from running instance
    print()
    print("=" * 60)
    print("  STEP 2: Export session from running browser (CDP)")
    print("=" * 60)
    print()

    try:
        success = asyncio.run(_cdp_export_session(profile_dir, browser_id=browser_id))
        if success:
            return True

        # CDP export failed, offer manual cookie import
        print()
        print("=" * 60)
        print("Session export failed. Please use the manual cookie import method:")
        print("=" * 60)
        print()

        manual_cookie_import_guide()
        return False

    except Exception as e:
        print(f"Session export failed: {e}")
        print()
        print("Please use the manual cookie import method.")
        manual_cookie_import_guide()
        return False


async def _cdp_export_session(
    profile_dir: Path,
    browser_id: str | None = None,
) -> bool:
    """
    Export Instagram session from a running browser via CDP.

    Args:
        profile_dir: Path to save profile data
        browser_id: Specific browser to connect to. If None, scans all Chromium browsers.

    Returns:
        True if export was successful
    """
    from patchright.async_api import async_playwright

    from instagram_mcp_server.session_state import portable_cookie_path
    from instagram_mcp_server.common_utils import secure_write_text
    from instagram_mcp_server.core.auth import detect_auth_barrier_quick

    if browser_id:
        profile = BROWSER_REGISTRY.get(browser_id)
        if profile is None:
            print(f"   ✗ Unknown browser: {browser_id}")
            return False

        if profile.engine != "chromium":
            print(f"   ⚠ {profile.name} does not support CDP (remote debugging).")
            print("   CDP is only available for Chromium-based browsers.")
            print("   Please use cookie extraction instead (Step 1).")
            return False

        # Check if this specific browser is running with CDP
        pid = find_browser_with_cdp(browser_id)
        if pid is None:
            print(
                f"   ⚠ {profile.name} is not running with --remote-debugging-port=9222"
            )
            print()
            exe = find_browser_executable(profile)
            exe_cmd = exe or profile.name.lower()
            print(f"   Please launch {profile.name} with remote debugging enabled:")
            print(f"     {exe_cmd} --remote-debugging-port=9222")
            return False

        print(f"   ✓ {profile.name} detected (PID: {pid})! Connecting...")
    else:
        # Auto-detect any Chromium browser with CDP
        result = find_any_browser_with_cdp()
        if result is None:
            print("   ⚠ No Chromium-based browser found running with CDP enabled.")
            print()
            print("   Supported browsers (Chromium-based):")
            for bid, prof in BROWSER_REGISTRY.items():
                if prof.engine == "chromium":
                    exe = find_browser_executable(prof)
                    exe_path = f" [{exe}]" if exe else ""
                    print(f"     - {prof.name}{exe_path}")
            print()
            print("   Launch your browser with: --remote-debugging-port=9222")
            return False

        browser_id, pid = result
        profile = BROWSER_REGISTRY[browser_id]
        print(f"   ✓ {profile.name} detected with CDP (PID: {pid})! Connecting...")

    # Connect via CDP
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.connect_over_cdp(
            "http://127.0.0.1:9222",
            timeout=30000,
        )
    except Exception as e:
        print(f"   ✗ Failed to connect to {profile.name}: {e}")
        print()
        print(
            f"   Make sure {profile.name} is running with --remote-debugging-port=9222"
        )
        return False

    try:
        print("   Verifying Instagram session...")

        # Get the first context (or create one if needed)
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

        barrier = await detect_auth_barrier_quick(page)
        if barrier:
            print(f"   ✗ Not logged in to Instagram (auth barrier: {barrier})")
            print()
            print(f"   Please log into Instagram in {profile.name}:")
            print("     1. Navigate to https://www.instagram.com/")
            print("     2. Log in with your credentials")
            print("     3. Run --login again to export the session")
            return False

        print("   ✓ Instagram session verified!")

        # Export cookies
        cookie_path = portable_cookie_path(profile_dir)
        print(f"   Exporting cookies to {cookie_path}...")

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
        print(f"   ✗ Failed to export session: {e}")
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

    # Ask which browser to use
    browser_id = _choose_browser_or_auto()

    try:
        return asyncio.run(interactive_login(browser_id=browser_id))
    except Exception as e:
        print(f"Login failed: {e}")
        return False
