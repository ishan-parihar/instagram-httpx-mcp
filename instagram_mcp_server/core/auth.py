"""Authentication functions for Instagram.

No browser is required.  Authentication relies on Instagram session cookies
(sessionid + csrftoken) extracted from a real browser once via
``cookie_import`` and reused across restarts.
"""

import logging


logger = logging.getLogger(__name__)


def is_logged_in(page: object = None) -> bool:
    """No-op stub. Session validity is determined by API response codes."""
    return True


async def detect_auth_barrier(page: object = None) -> str | None:
    """No-op stub. Auth barriers are detected via API response codes."""
    return None


async def detect_auth_barrier_quick(page: object = None) -> str | None:
    """No-op stub. Auth barriers are detected via API response codes."""
    return None
