"""Utility functions (no browser dependencies)."""

import logging


logger = logging.getLogger(__name__)


async def detect_rate_limit(page: object = None) -> None:
    """No-op: rate limits are detected via API response codes."""
    pass


async def scroll_to_bottom(page: object = None) -> None:
    """No-op: pagination is handled via API cursors."""
    pass


async def handle_modal_close(page: object = None) -> bool:
    """No-op: there are no modal dialogs in the API."""
    return False
