"""Scraping engine — API client replaces the old DOM-based extractor."""

from .api_client import InstagramAPIClient
from .fields import (
    INSIGHTS_SECTIONS,
    USER_SECTIONS,
    parse_insights_sections,
    parse_user_sections,
)

__all__ = [
    "INSIGHTS_SECTIONS",
    "InstagramAPIClient",
    "USER_SECTIONS",
    "parse_insights_sections",
    "parse_user_sections",
]
