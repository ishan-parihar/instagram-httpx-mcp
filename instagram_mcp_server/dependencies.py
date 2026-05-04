"""Dependency injection for MCP tools — creates an API client from saved cookies."""

from __future__ import annotations

import json
import logging
from typing import NoReturn

from fastmcp import Context

from instagram_mcp_server.bootstrap import (
    ensure_tool_ready_or_raise,
    invalidate_auth_and_trigger_relogin,
)
from instagram_mcp_server.core.exceptions import AuthenticationError
from instagram_mcp_server.drivers.browser import get_profile_dir
from instagram_mcp_server.error_handler import raise_tool_error
from instagram_mcp_server.scraping import InstagramAPIClient

logger = logging.getLogger(__name__)


async def handle_auth_error(
    error: AuthenticationError,
    ctx: Context | None,
) -> NoReturn:
    """Trigger interactive re-login."""
    logger.warning("Stale session detected; triggering re-login")
    await invalidate_auth_and_trigger_relogin(ctx)


async def get_ready_extractor(
    ctx: Context | None,
    *,
    tool_name: str,
) -> InstagramAPIClient:
    """Run bootstrap gating, then create an authenticated API client."""
    try:
        await ensure_tool_ready_or_raise(tool_name, ctx)
        client = _build_api_client()
        return client
    except AuthenticationError as e:
        await handle_auth_error(e, ctx)
    except Exception as e:
        raise_tool_error(e, tool_name)


def _build_api_client() -> InstagramAPIClient:
    """Load cookies from disk and return an :class:`InstagramAPIClient`."""
    profile_dir = get_profile_dir()
    cookie_file = profile_dir / "cookies.json"

    if not cookie_file.exists():
        # Fallback to session_state portable path
        from instagram_mcp_server.session_state import portable_cookie_path

        cookie_file = portable_cookie_path(profile_dir)
        if not cookie_file.exists():
            raise AuthenticationError(
                "No Instagram session found. Run with --login to create one."
            )

    raw = json.loads(cookie_file.read_text())

    # Support both list-of-dicts and dict-from-firefox formats
    if isinstance(raw, list):
        cookies = {c["name"]: c["value"] for c in raw if "name" in c and "value" in c}
    elif isinstance(raw, dict):
        cookies = raw
    else:
        cookies = {}

    if "sessionid" not in cookies:
        raise AuthenticationError(
            "Saved cookies are missing sessionid. Run with --login to re-authenticate."
        )

    logger.info(
        "API client created from %s (%d cookies)",
        cookie_file,
        len(cookies),
    )
    return InstagramAPIClient(cookies)
