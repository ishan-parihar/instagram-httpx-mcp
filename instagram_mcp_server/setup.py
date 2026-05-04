"""
Interactive setup flows for Instagram MCP Server authentication.

Handles session creation through cookie extraction from supported browsers:
Brave, Chrome, Edge, Firefox, Zen, Helium, Chromium, Opera, Arc, Vivaldi,
LibreWolf, Waterfox, Floorp.

No browser is launched.  Cookies are extracted directly from the browser's
SQLite cookie store.
"""

from __future__ import annotations

from pathlib import Path

from instagram_mcp_server.cookie_import import (
    BROWSER_REGISTRY,
    choose_browser_interactive,
    detect_installed_browsers,
    import_cookies_interactive,
    manual_cookie_import_guide,
)
from instagram_mcp_server.drivers.browser import get_profile_dir


def _choose_browser_or_auto() -> str | None:
    """Interactive browser selection. Returns browser_id or None if cancelled."""
    return choose_browser_interactive()


def run_profile_creation(
    user_data_dir: str | None = None,
    browser_id: str | None = None,
) -> bool:
    """
    Create profile via cookie extraction from a real browser.

    Steps:
    1. Ask which browser to import cookies from (or use specified browser_id)
    2. Extract cookies from the selected browser's SQLite cookie store
    3. Save to profile directory

    Args:
        user_data_dir: Path to profile directory. Defaults to config default.
        browser_id: Pre-selected browser ID. If None, prompts user interactively.

    Returns:
        True if profile was created successfully
    """
    if user_data_dir:
        profile_dir = Path(user_data_dir).expanduser()
    else:
        profile_dir = get_profile_dir()

    print("Instagram MCP Server - Profile Creation")
    print(f"   Profile will be saved to: {profile_dir}")
    print()

    print("=" * 60)
    print("  Choose your browser for cookie import")
    print("=" * 60)

    if browser_id is None:
        browser_id = _choose_browser_or_auto()
    if browser_id is None:
        print("   No browser selected. Trying auto-detection...")
        installed = detect_installed_browsers()
        if installed:
            browser_id = installed[0][0]
            prof = BROWSER_REGISTRY[browser_id]
            print(f"   Auto-detected: {prof.name}")
        else:
            print("   No supported browsers detected.")
            print()
            manual_cookie_import_guide()
            return False

    print()
    print(f"   Importing cookies from {BROWSER_REGISTRY[browser_id].name}...")
    if import_cookies_interactive(browser_id=browser_id):
        print("   Cookie import successful!")
        print("   You can now use the MCP server.")
        return True

    print()
    print("Cookie import failed. Manual cookie import may be required.")
    manual_cookie_import_guide()
    return False


def run_interactive_setup() -> bool:
    """
    Run interactive setup - cookie extraction only.

    Returns:
        True if setup completed successfully
    """
    browser_id = _choose_browser_or_auto()
    if browser_id is None:
        return False
    return import_cookies_interactive(browser_id=browser_id)
