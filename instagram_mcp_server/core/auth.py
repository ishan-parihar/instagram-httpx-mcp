"""Authentication functions for Instagram."""

import asyncio
import logging
import re
from urllib.parse import urlparse

from patchright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from .exceptions import AuthenticationError

logger = logging.getLogger(__name__)

_AUTH_BLOCKER_URL_PATTERNS = (
    "/accounts/login",
    "/accounts/emailsignup",
    "/challenge",
    "/checkpoint",
)
_LOGIN_TITLE_PATTERNS = (
    "instagram login",
    "sign up • instagram",
    "log in • instagram",
)
_AUTH_BARRIER_TEXT_MARKERS = (
    ("log in", "sign up"),
    ("forgot password", "don't have an account"),
    ("we restrict certain activity",),
    ("something went wrong",),
)


async def warm_up_browser(page: Page) -> None:
    """Visit normal sites to appear more human-like before Instagram access."""
    sites = [
        "https://www.google.com",
        "https://www.instagram.com",
    ]

    logger.info("Warming up browser by visiting normal sites...")

    failures = 0
    for site in sites:
        try:
            await page.goto(site, wait_until="domcontentloaded", timeout=10000)
            await asyncio.sleep(1)
            logger.debug("Visited %s", site)
        except Exception as e:
            failures += 1
            logger.debug("Could not visit %s: %s", site, e)
            continue

    if failures == len(sites):
        logger.warning("Browser warm-up failed: none of %d sites reachable", len(sites))
    else:
        logger.info("Browser warm-up complete")


async def is_logged_in(page: Page) -> bool:
    """Check if currently logged in to Instagram.

    Uses a three-tier strategy:
    1. Fail-fast on auth blocker URLs
    2. Check for Instagram navigation elements (primary)
    3. URL-based fallback for authenticated-only pages
    """
    try:
        current_url = page.url

        # Step 1: Fail-fast on auth blockers
        if _is_auth_blocker_url(current_url):
            return False

        # Step 2: Selector check (PRIMARY) — Instagram nav elements
        selectors = (
            'nav a[href*="/direct/inbox"]',
            'svg[aria-label="Home"]',
            'svg[aria-label*="profile picture"]',
        )
        has_nav_elements = False
        for sel in selectors:
            try:
                if await page.locator(sel).count() > 0:
                    has_nav_elements = True
                    break
            except Exception:
                continue

        # Step 3: URL fallback for authenticated-only pages
        authenticated_only_pages = [
            "/feed/",
            "/direct/",
            "/explore/",
        ]
        is_authenticated_page = any(
            pattern in current_url for pattern in authenticated_only_pages
        )

        if not is_authenticated_page:
            return has_nav_elements

        if has_nav_elements:
            return True

        # Empty authenticated-only pages are a false positive during cookie
        # bridge recovery. Require some real page content before trusting URL.
        body_text = await page.evaluate("() => document.body?.innerText || ''")
        if not isinstance(body_text, str):
            return False

        return bool(body_text.strip())
    except PlaywrightTimeoutError:
        logger.warning(
            "Timeout checking login status on %s — treating as not logged in",
            page.url,
        )
        return False
    except Exception:
        logger.error("Unexpected error checking login status", exc_info=True)
        raise


async def detect_auth_barrier(page: Page) -> str | None:
    """Detect Instagram auth/account barriers on the current page."""
    return await _detect_auth_barrier(page, include_body_text=True)


async def _detect_auth_barrier(
    page: Page,
    *,
    include_body_text: bool,
) -> str | None:
    """Detect Instagram auth/account barriers on the current page."""
    try:
        current_url = page.url
        if _is_auth_blocker_url(current_url):
            return f"auth blocker URL: {current_url}"

        try:
            title = (await page.title()).strip().lower()
        except Exception:
            title = ""
        if any(pattern in title for pattern in _LOGIN_TITLE_PATTERNS):
            return f"login title: {title}"

        if not include_body_text:
            return None

        try:
            body_text = await page.evaluate("() => document.body?.innerText || ''")
        except Exception:
            body_text = ""
        if not isinstance(body_text, str):
            body_text = ""

        normalized = re.sub(r"\s+", " ", body_text).strip().lower()
        for marker_group in _AUTH_BARRIER_TEXT_MARKERS:
            if all(marker in normalized for marker in marker_group):
                return f"auth barrier text: {' + '.join(marker_group)}"

        return None
    except PlaywrightTimeoutError:
        logger.warning(
            "Timeout checking auth barrier on %s — continuing without barrier detection",
            page.url,
        )
        return None
    except Exception:
        logger.error("Unexpected error checking auth barrier", exc_info=True)
        return None


async def detect_auth_barrier_quick(page: Page) -> str | None:
    """Cheap auth-barrier check for normal navigations.

    Uses URL and title only, avoiding a full body-text fetch on healthy pages.
    """
    return await _detect_auth_barrier(page, include_body_text=False)


async def resolve_remember_me_prompt(page: Page) -> bool:
    """Instagram does not have a remember-me prompt — always returns False."""
    return False


def _is_auth_blocker_url(url: str) -> bool:
    """Return True only for real auth routes, not arbitrary slug substrings."""
    path = urlparse(url).path or "/"

    if path in _AUTH_BLOCKER_URL_PATTERNS:
        return True

    return any(
        path == f"{pattern}/" or path.startswith(f"{pattern}/")
        for pattern in _AUTH_BLOCKER_URL_PATTERNS
    )


async def wait_for_manual_login(page: Page, timeout: int = 300000) -> None:
    """Wait for user to manually complete login.

    Args:
        page: Patchright page object
        timeout: Timeout in milliseconds (default: 5 minutes)

    Raises:
        AuthenticationError: If timeout or login not completed
    """
    logger.info(
        "Please complete the login process manually in the browser. "
        "Waiting up to 5 minutes..."
    )

    loop = asyncio.get_running_loop()
    start_time = loop.time()

    while True:
        if await is_logged_in(page):
            logger.info("Manual login completed successfully")
            return

        elapsed = (loop.time() - start_time) * 1000
        if elapsed > timeout:
            raise AuthenticationError(
                "Manual login timeout. Please try again and complete login faster."
            )

        await asyncio.sleep(1)
