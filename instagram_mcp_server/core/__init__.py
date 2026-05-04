"""Core authentication and scraping utilities."""

from .auth import (
    detect_auth_barrier,
    detect_auth_barrier_quick,
    is_logged_in,
)
from .exceptions import (
    AuthenticationError,
    ElementNotFoundError,
    InstagramScraperException,
    NetworkError,
    ProfileNotFoundError,
    RateLimitError,
    ScrapingError,
)
from .utils import detect_rate_limit

__all__ = [
    "AuthenticationError",
    "detect_auth_barrier",
    "detect_auth_barrier_quick",
    "ElementNotFoundError",
    "InstagramScraperException",
    "NetworkError",
    "ProfileNotFoundError",
    "RateLimitError",
    "ScrapingError",
    "detect_rate_limit",
    "is_logged_in",
]
