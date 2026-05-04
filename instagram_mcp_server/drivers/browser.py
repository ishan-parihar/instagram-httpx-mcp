"""Cookie-based session management for Instagram API.

No browser is used.  Authentication relies entirely on Instagram session
cookies (sessionid + csrftoken) extracted from a real browser once, stored
at ``~/.instagram-mcp/profile/cookies.json``, and reused across restarts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from instagram_mcp_server.cookie_import import load_or_import_cookies
from instagram_mcp_server.core import AuthenticationError
from instagram_mcp_server.session_state import (
    portable_cookie_path,
    profile_exists as session_profile_exists,
)

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_DIR = Path.home() / ".instagram-mcp" / "profile"

_browser_api_client: object | None = None


def get_profile_dir() -> Path:
    """Return the source profile directory."""
    from instagram_mcp_server.session_state import get_source_profile_dir

    return get_source_profile_dir()


def profile_exists(profile_dir: Path | None = None) -> bool:
    """Check if a persistent cookie profile exists."""
    return session_profile_exists(profile_dir or get_profile_dir())


def set_headless(headless: bool) -> None:
    """No-op: retained for API compatibility."""


async def close_browser() -> None:
    """No-op: no browser to close."""
    global _browser_api_client
    _browser_api_client = None


def reset_browser_for_testing() -> None:
    """Reset global browser state for test isolation."""
    global _browser_api_client
    _browser_api_client = None


async def validate_session() -> bool:
    """Check whether Instagram session cookies are valid by making a test API call."""
    profile_dir = get_profile_dir()
    cookie_path = portable_cookie_path(profile_dir)
    if not cookie_path.exists():
        return False
    try:
        cookies_raw = json.loads(cookie_path.read_text())
        if isinstance(cookies_raw, dict) and "cookies" in cookies_raw:
            cookies_raw = cookies_raw["cookies"]
        cookie_dict = {c["name"]: c["value"] for c in cookies_raw}
        headers = {
            "X-CSRFToken": cookie_dict.get("csrftoken", ""),
            "X-IG-App-ID": "936619743392459",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
            ),
        }
        async with httpx.AsyncClient(
            cookies=cookie_dict, headers=headers, timeout=10
        ) as client:
            resp = await client.get(
                "https://www.instagram.com/api/v1/users/web_profile_info/"
                "?username=instagram"
            )
            return resp.status_code == 200 and resp.json().get("status") == "ok"
    except Exception:
        logger.exception("Session validation failed")
        return False


async def ensure_authenticated() -> None:
    """Confirm that valid cookie-based authentication is available."""
    if not await validate_session():
        raise AuthenticationError(
            "Instagram session is expired or invalid. "
            "Run with --login to create a new session."
        )


async def check_rate_limit() -> None:
    """No-op: API client handles rate limiting via response codes."""


def load_cookies(profile_dir: Path | None = None) -> dict[str, str]:
    """Load Instagram cookies from disk into a ``{name: value}`` dict.

    Automatically triggers cookie extraction from a real browser if the cookie
    file doesn't exist yet.
    """
    profile_dir = profile_dir or get_profile_dir()
    cookie_path = portable_cookie_path(profile_dir)

    if cookie_path.exists():
        try:
            raw = json.loads(cookie_path.read_text())
            if isinstance(raw, dict) and "cookies" in raw:
                raw = raw["cookies"]
            return {c["name"]: c["value"] for c in raw}
        except (OSError, json.JSONDecodeError, KeyError):
            logger.warning("Corrupt cookie file at %s; re-importing", cookie_path)

    return load_or_import_cookies(profile_dir) or {}
