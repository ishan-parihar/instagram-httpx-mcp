"""Custom exceptions for Instagram scraping operations."""


class InstagramScraperException(Exception):
    """Base exception for Instagram scraper."""

    pass


class AuthenticationError(InstagramScraperException):
    """Raised when authentication fails."""

    pass


class RateLimitError(InstagramScraperException):
    """Raised when rate limiting is detected."""

    def __init__(self, message: str, suggested_wait_time: int = 300):
        super().__init__(message)
        self.suggested_wait_time = suggested_wait_time


class ElementNotFoundError(InstagramScraperException):
    """Raised when an expected element is not found."""

    pass


class ProfileNotFoundError(InstagramScraperException):
    """Raised when a profile/page returns 404."""

    pass


class NetworkError(InstagramScraperException):
    """Raised when network-related issues occur."""

    pass


class ScrapingError(InstagramScraperException):
    """Raised when scraping fails for various reasons."""

    pass
