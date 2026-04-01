"""Scraping engine using innerText extraction."""

from .extractor import InstagramExtractor
from .fields import (
    INSIGHTS_SECTIONS,
    USER_SECTIONS,
    parse_insights_sections,
    parse_user_sections,
)

__all__ = [
    "INSIGHTS_SECTIONS",
    "InstagramExtractor",
    "USER_SECTIONS",
    "parse_insights_sections",
    "parse_user_sections",
]
