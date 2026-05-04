"""
Cookie-based session management for Instagram scraping.

No browser is required.  Instagram session cookies are extracted from a real
browser once, saved to ``~/.instagram-mcp/profile/cookies.json``, and reused
for direct API calls via the private Instagram web API.
"""

from instagram_mcp_server.drivers.browser import (
    DEFAULT_PROFILE_DIR,
    check_rate_limit,
    close_browser,
    ensure_authenticated,
    get_profile_dir,
    load_cookies,
    profile_exists,
    reset_browser_for_testing,
    set_headless,
    validate_session,
)

__all__ = [
    "DEFAULT_PROFILE_DIR",
    "check_rate_limit",
    "close_browser",
    "ensure_authenticated",
    "get_profile_dir",
    "load_cookies",
    "profile_exists",
    "reset_browser_for_testing",
    "set_headless",
    "validate_session",
]
