"""Core extraction engine using innerText instead of DOM selectors."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote_plus

from patchright.async_api import Page
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from instagram_mcp_server.core import (
    detect_auth_barrier,
    detect_auth_barrier_quick,
    resolve_remember_me_prompt,
)
from instagram_mcp_server.core.exceptions import (
    AuthenticationError,
    InstagramScraperException,
)
from instagram_mcp_server.core.utils import (
    detect_rate_limit,
    handle_modal_close,
    scroll_to_bottom,
)
from instagram_mcp_server.debug_trace import record_page_trace
from instagram_mcp_server.debug_utils import stabilize_navigation
from instagram_mcp_server.error_diagnostics import build_issue_diagnostics
from instagram_mcp_server.scraping.link_metadata import (
    Reference,
    build_references,
)

from .fields import USER_SECTIONS

if TYPE_CHECKING:
    from instagram_mcp_server.callbacks import ProgressCallback

logger = logging.getLogger(__name__)

WaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]

# Delay between page navigations (optimized for speed)
_NAV_DELAY = 0.5

# Backoff before retrying a rate-limited page
_RATE_LIMIT_RETRY_DELAY = 2.0

# Returned as section text when Instagram rate-limits the page
_RATE_LIMITED_MSG = "[Rate limited] Instagram blocked this section. Try again later or request fewer sections."

# Instagram chrome detection — noise prefixes found in footer/sidebar text
_NOISE_PREFIXES = (
    "Instagram",
    "Meta",
    "About",
    "Help",
    "Press",
    "API",
    "Jobs",
    "Privacy",
    "Terms",
    "Locations",
    "Language",
)

# Patterns that mark the start of Instagram page chrome (footer/sidebar).
# Everything from the earliest match onwards is stripped.
_NOISE_MARKERS: list[re.Pattern[str]] = [
    # Footer: "About" followed by typical footer links
    re.compile(r"^About\n+(?:Help|Press|API|Jobs|Terms|Privacy)", re.MULTILINE),
    # Footer copyright line
    re.compile(r"^© \d{4} Instagram from Meta$", re.MULTILINE),
    # Sidebar suggestions
    re.compile(r"^Suggested for you$", re.MULTILINE),
    # Discover more section
    re.compile(r"^Discover more$", re.MULTILINE),
    # Meta footer cluster
    re.compile(
        r"^(?:Meta|About|Blog|Help|API|Jobs|Privacy|Terms|Locations|Language)\n+"
        r"(?:About|Blog|Help|API|Jobs|Privacy|Terms|Locations|Language)",
        re.MULTILINE,
    ),
]

_NOISE_LINE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^Instagram$"),
    re.compile(r"^Meta$"),
    re.compile(r"^© \d{4} Instagram from Meta$"),
    re.compile(r"^(Home|Search|Explore|Reels|Messages|Notifications|Create|Profile)$"),
    re.compile(r"^(Verified|Follow|Following|Message|Subscribe)$"),
]

# Noise lines to filter after truncation
_NOISE_LINES: list[re.Pattern[str]] = [
    re.compile(r"^(?:Play|Pause|Playback speed|Turn fullscreen on|Fullscreen)$"),
    re.compile(r"^(?:Show captions|Close modal window|Media player modal window)$"),
    re.compile(r"^(?:Loaded:.*|Remaining time.*|Stream Type.*)$"),
]

# Markers indicating the bottom-of-content Instagram chrome region
INSTAGRAM_NOISE_TRUNCATE_MARKERS = (
    "Suggested for you",
    "Discover more",
    "More posts",
    "© Instagram",
    "About",
    "Help",
    "Press",
    "API",
    "Jobs",
    "Privacy",
    "Terms",
    "Locations",
    "Language",
)

# Instagram rate limit detection
_RATE_LIMIT_MARKERS = (
    "sorry, something went wrong",
    "we restrict certain activity",
    "try again later",
    "you're temporarily blocked",
    "action blocked",
)

_DIALOG_SELECTOR = 'dialog[open], [role="dialog"]'
_DIALOG_TEXTAREA_SELECTOR = '[role="dialog"] textarea, dialog textarea'
_DIALOG_INPUT_SELECTOR = '[role="dialog"] input, dialog input'

# DM compose selectors (Instagram Direct)
_DM_COMPOSE_SELECTOR = (
    'div[role="textbox"][contenteditable="true"], '
    'textarea[placeholder*="Message"], '
    'div[aria-label*="Message"][contenteditable="true"]'
)
_DM_SEND_SELECTOR = (
    'button[type="submit"]:not([disabled]), button[aria-label*="Send"]:not([disabled])'
)
_DM_SEARCH_SELECTOR = 'input[placeholder*="Search"], input[aria-label*="Search"]'


def _action_result(
    url: str,
    status: str,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    """Build a structured response for an action (follow, like, dm, etc.)."""
    result: dict[str, Any] = {
        "url": url,
        "status": status,
        "message": message,
    }
    result.update(extra)
    return result


def _parse_number(value: str | None) -> int | None:
    """Parse a number that may be abbreviated (e.g. '1.2K', '10.3M').

    Used across the extractor for engagement metrics and view counts.
    """
    if not value:
        return None
    value = value.strip().lower()
    try:
        if value.endswith("k"):
            return int(float(value[:-1]) * 1_000)
        elif value.endswith("m"):
            return int(float(value[:-1]) * 1_000_000)
        elif value.endswith("b"):
            return int(float(value[:-1]) * 1_000_000_000)
        elif value.isdigit():
            return int(value)
        elif "," in value:
            return int(value.replace(",", ""))
        else:
            return int(float(value))
    except (ValueError, IndexError):
        return None


@dataclass
class ExtractedSection:
    """Text and compact references extracted from a loaded Instagram section."""

    text: str
    references: list[Reference]
    error: dict[str, Any] | None = None


def strip_instagram_noise(text: str, *, page_type: str = "default") -> str:
    """Remove Instagram page chrome (footer, sidebar recommendations) from innerText.

    Finds the earliest occurrence of any known noise marker and truncates there.

    Args:
        text: Raw innerText to clean.
        page_type: Context hint for noise stripping.
            - "default": Full noise stripping (profile pages, etc.)
            - "grid": Grid pages (reels, posts, hashtag, location) — only strips
              true footer chrome, preserves inline "Suggested for you" / "Discover more".
            - "profile": Profile page — standard stripping.
    """
    cleaned = _truncate_instagram_noise(text, page_type=page_type)
    return _filter_instagram_noise_lines(cleaned)


def _filter_instagram_noise_lines(text: str) -> str:
    """Remove known media/control noise lines from already-truncated content."""
    filtered_lines = [
        line
        for line in text.splitlines()
        if not any(pattern.match(line.strip()) for pattern in _NOISE_LINES)
    ]
    return "\n".join(filtered_lines).strip()


def _truncate_instagram_noise(text: str, *, page_type: str = "default") -> str:
    """Trim known Instagram chrome blocks before any per-line noise filtering.

    On grid pages (reels, posts, hashtag, location), inline markers like
    "Suggested for you" and "Discover more" mark the end-of-grid recommendations
    — not the footer. Only true footer markers are stripped on grid pages.
    """
    earliest = len(text)

    # Inline markers that appear mid-content on grid pages — skip these on grids
    inline_pattern_strings = {
        r"^Suggested for you$",
        r"^Discover more$",
        r"^More posts$",
    }

    for pattern in _NOISE_MARKERS:
        # On grid pages, skip inline markers that are not footer noise
        if page_type == "grid" and pattern.pattern in inline_pattern_strings:
            continue
        match = pattern.search(text)
        if match and match.start() < earliest:
            earliest = match.start()

    return text[:earliest].strip()


def _detect_rate_limit_text(text: str) -> bool:
    """Check if extracted text indicates an Instagram rate limit."""
    lower = text.lower()
    return any(marker in lower for marker in _RATE_LIMIT_MARKERS)


class InstagramExtractor:
    """Extracts Instagram page content via navigate-scroll-innerText pattern."""

    def __init__(self, page: Page):
        self._page = page

    @staticmethod
    def _normalize_body_marker(value: Any) -> str:
        """Compress body text into a short, single-line diagnostic marker."""
        if not isinstance(value, str):
            return ""
        return re.sub(r"\s+", " ", value).strip()[:200]

    @staticmethod
    def _single_section_result(
        url: str,
        section_name: str,
        text: str,
        references: list[Reference] | None = None,
    ) -> dict[str, Any]:
        """Build a standard single-section scraping response."""
        result: dict[str, Any] = {"url": url, "sections": {}}
        if text:
            result["sections"][section_name] = text
            if references:
                result["references"] = {section_name: references}
        return result

    @staticmethod
    def _message_action_result(
        url: str,
        status: str,
        message: str,
        *,
        recipient_selected: bool = False,
        sent: bool = False,
    ) -> dict[str, Any]:
        """Build a structured response for the send_message tool."""
        return {
            "url": url,
            "status": status,
            "message": message,
            "recipient_selected": recipient_selected,
            "sent": sent,
        }

    async def _log_navigation_failure(
        self,
        target_url: str,
        wait_until: str,
        navigation_error: Exception,
        hops: list[str],
    ) -> None:
        """Emit structured diagnostics for a failed target navigation."""
        try:
            title = await self._page.title()
        except Exception:
            title = ""

        try:
            auth_barrier = await detect_auth_barrier(self._page)
        except Exception:
            auth_barrier = None

        try:
            body_marker = self._normalize_body_marker(
                await self._page.evaluate("() => document.body?.innerText || ''")
            )
        except Exception:
            body_marker = ""

        logger.warning(
            "Navigation to %s failed (wait_until=%s, error=%s). "
            "current_url=%s title=%r auth_barrier=%s hops=%s body_marker=%r",
            target_url,
            wait_until,
            navigation_error,
            self._page.url,
            title,
            auth_barrier,
            hops,
            body_marker,
        )

    async def _raise_if_auth_barrier(
        self,
        url: str,
        *,
        navigation_error: Exception | None = None,
    ) -> None:
        """Raise an auth error when Instagram shows login UI."""
        barrier = await detect_auth_barrier(self._page)
        if not barrier:
            return

        logger.warning("Authentication barrier detected on %s: %s", url, barrier)
        message = (
            "Instagram requires interactive re-authentication. "
            "Run with --login and complete the account selection/sign-in flow."
        )
        if navigation_error is not None:
            raise AuthenticationError(message) from navigation_error
        raise AuthenticationError(message)

    async def _goto_with_auth_checks(
        self,
        url: str,
        *,
        wait_until: WaitUntil = "domcontentloaded",
        allow_remember_me: bool = True,
    ) -> None:
        """Navigate to an Instagram page and fail fast on auth barriers."""
        hops: list[str] = []
        listener_registered = False

        def record_navigation(frame: Any) -> None:
            if frame != self._page.main_frame:
                return
            frame_url = getattr(frame, "url", "")
            if frame_url and (not hops or hops[-1] != frame_url):
                hops.append(frame_url)

        def unregister_navigation_listener() -> None:
            nonlocal listener_registered
            if not listener_registered:
                return
            self._page.remove_listener("framenavigated", record_navigation)
            listener_registered = False

        self._page.on("framenavigated", record_navigation)
        listener_registered = True
        try:
            await record_page_trace(
                self._page,
                "extractor-before-goto",
                extra={"target_url": url, "wait_until": wait_until},
            )
            try:
                await self._page.goto(url, wait_until=wait_until, timeout=30000)
                await stabilize_navigation(f"goto {url}", logger)
                await record_page_trace(
                    self._page,
                    "extractor-after-goto",
                    extra={"target_url": url, "wait_until": wait_until},
                )
            except Exception as exc:
                if allow_remember_me and await resolve_remember_me_prompt(self._page):
                    await stabilize_navigation(
                        f"remember-me resolution for {url}", logger
                    )
                    await record_page_trace(
                        self._page,
                        "extractor-navigation-error-before-remember-me-retry",
                        extra={
                            "target_url": url,
                            "wait_until": wait_until,
                            "error": f"{type(exc).__name__}: {exc}",
                            "hops": hops,
                        },
                    )
                    await record_page_trace(
                        self._page,
                        "extractor-after-remember-me",
                        extra={
                            "target_url": url,
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                    )
                    unregister_navigation_listener()
                    await self._goto_with_auth_checks(
                        url,
                        wait_until=wait_until,
                        allow_remember_me=False,
                    )
                    return
                await record_page_trace(
                    self._page,
                    "extractor-navigation-error",
                    extra={
                        "target_url": url,
                        "wait_until": wait_until,
                        "error": f"{type(exc).__name__}: {exc}",
                        "hops": hops,
                    },
                )
                await self._log_navigation_failure(url, wait_until, exc, hops)
                await self._raise_if_auth_barrier(url, navigation_error=exc)
                raise

            barrier = await detect_auth_barrier_quick(self._page)
            if not barrier:
                return

            if allow_remember_me and await resolve_remember_me_prompt(self._page):
                await stabilize_navigation(f"remember-me retry for {url}", logger)
                await record_page_trace(
                    self._page,
                    "extractor-after-remember-me-retry",
                    extra={"target_url": url, "barrier": barrier},
                )
                unregister_navigation_listener()
                await self._goto_with_auth_checks(
                    url,
                    wait_until=wait_until,
                    allow_remember_me=False,
                )
                return

            await record_page_trace(
                self._page,
                "extractor-auth-barrier",
                extra={"target_url": url, "barrier": barrier},
            )
            logger.warning("Authentication barrier detected on %s: %s", url, barrier)
            raise AuthenticationError(
                "Instagram requires interactive re-authentication. "
                "Run with --login and complete the account selection/sign-in flow."
            )
        finally:
            unregister_navigation_listener()

    async def _navigate_to_page(self, url: str) -> None:
        """Navigate to an Instagram page and fail fast on auth barriers."""
        await self._goto_with_auth_checks(url)

    # ------------------------------------------------------------------
    # Generic browser helpers
    # ------------------------------------------------------------------

    async def click_button_by_text(
        self, text: str, *, scope: str = "main", timeout: int = 5000
    ) -> bool:
        """Click the first button/link whose visible text is exactly *text*.

        Uses a regex filter for exact matching to avoid substring false positives.
        Returns True if clicked, False if no match found.
        """
        matches = (
            self._page.locator(scope)
            .locator("button, a, [role='button']")
            .filter(has_text=re.compile(rf"^{re.escape(text)}$"))
        )
        count = await matches.count()
        logger.debug("click_button_by_text(%r): %d matches in %s", text, count, scope)
        if count == 0:
            return False
        target = matches.first
        try:
            await target.scroll_into_view_if_needed(timeout=timeout)
        except Exception:
            logger.debug("Scroll failed for button '%s'", text, exc_info=True)
        try:
            await target.click(timeout=timeout)
            return True
        except Exception:
            logger.debug("Click failed for button '%s'", text, exc_info=True)
            return False

    async def _dialog_is_open(self, *, timeout: int = 1000) -> bool:
        """Return whether a dialog is currently open (structural check)."""
        locator = self._page.locator(_DIALOG_SELECTOR)
        try:
            if await locator.count() == 0:
                return False
            await locator.first.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    async def _click_dialog_primary_button(self, *, timeout: int = 5000) -> bool:
        """Click the last (primary) button in the open dialog."""
        buttons = self._page.locator(
            f"{_DIALOG_SELECTOR} button, {_DIALOG_SELECTOR} [role='button']"
        )
        count = await buttons.count()
        if count == 0:
            return False
        await buttons.nth(count - 1).click(timeout=timeout)
        return True

    async def _fill_dialog_textarea(self, value: str, *, timeout: int = 5000) -> bool:
        """Fill the first textarea inside the open dialog (structural)."""
        locator = self._page.locator(_DIALOG_TEXTAREA_SELECTOR).first
        try:
            if await self._page.locator(_DIALOG_TEXTAREA_SELECTOR).count() == 0:
                return False
            await locator.fill(value, timeout=timeout)
            return True
        except Exception:
            return False

    async def _dismiss_dialog(self) -> None:
        """Dismiss any open dialog via Escape key (structural)."""
        await self._page.keyboard.press("Escape")
        try:
            await self._page.wait_for_selector(
                _DIALOG_SELECTOR, state="hidden", timeout=3000
            )
        except PlaywrightTimeoutError:
            pass

    async def _locator_is_visible(self, selector: str, *, timeout: int = 2000) -> bool:
        """Return whether the first matching locator is visible."""
        locator = self._page.locator(selector)
        try:
            if await locator.count() == 0:
                return False
        except Exception:
            return False

        first = locator.first
        try:
            await first.wait_for(state="visible", timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            return False
        except Exception:
            try:
                return bool(await first.is_visible())
            except Exception:
                return False

    async def _click_first(self, selector: str, *, timeout: int = 5000) -> None:
        """Click the first visible locator that matches a selector."""
        target = self._page.locator(selector).first
        try:
            await target.scroll_into_view_if_needed(timeout=timeout)
        except Exception:
            logger.debug("Could not scroll %s into view", selector, exc_info=True)
        await target.click(timeout=timeout)

    async def _wait_for_main_text(
        self,
        *,
        minimum_length: int = 100,
        timeout: int = 10000,
        log_context: str,
    ) -> None:
        """Wait for main content to populate enough text to scrape."""
        try:
            await self._page.wait_for_function(
                """({ minimumLength }) => {
                    const main = document.querySelector('main');
                    if (!main) return false;
                    return main.innerText.length > minimumLength;
                }""",
                arg={"minimumLength": minimum_length},
                timeout=timeout,
            )
        except PlaywrightTimeoutError:
            logger.debug("%s content did not appear", log_context)

    async def _scroll_main_scrollable_region(
        self,
        *,
        position: Literal["top", "bottom"],
        attempts: int,
        pause_time: float = 0.5,
    ) -> None:
        """Scroll the largest scrollable region inside main when one exists."""
        for _ in range(attempts):
            await self._page.evaluate(
                """({ position }) => {
                    const main = document.querySelector('main');
                    if (!main) return false;

                    const isScrollable = element => {
                        const style = window.getComputedStyle(element);
                        return (
                            (style.overflowY === 'auto' || style.overflowY === 'scroll') &&
                            element.scrollHeight > element.clientHeight + 20
                        );
                    };

                    const candidates = [main, ...main.querySelectorAll('*')].filter(isScrollable);
                    const target = candidates.sort(
                        (left, right) => right.scrollHeight - left.scrollHeight
                    )[0] || main;
                    target.scrollTop = position === 'top' ? 0 : target.scrollHeight;
                    return true;
                }""",
                {"position": position},
            )
            await asyncio.sleep(pause_time)

    # ------------------------------------------------------------------
    # Core page extraction
    # ------------------------------------------------------------------

    async def extract_page(
        self,
        url: str,
        section_name: str,
    ) -> ExtractedSection:
        """Navigate to a URL, scroll to load lazy content, and extract innerText.

        Retries once after a backoff when the page returns only Instagram chrome
        (footer/sidebar noise with no actual content), which indicates a soft
        rate limit.

        Raises InstagramScraperException subclasses (rate limit, auth, etc.).
        Returns _RATE_LIMITED_MSG sentinel when soft-rate-limited after retry.
        Returns empty string for unexpected non-domain failures (error isolation).
        """
        try:
            result = await self._extract_page_once(url, section_name)
            if result.text != _RATE_LIMITED_MSG:
                return result

            # Retry once after backoff
            logger.info("Retrying %s after %.0fs backoff", url, _RATE_LIMIT_RETRY_DELAY)
            await asyncio.sleep(_RATE_LIMIT_RETRY_DELAY)
            return await self._extract_page_once(url, section_name)

        except InstagramScraperException:
            raise
        except Exception as e:
            logger.warning("Failed to extract page %s: %s", url, e)
            return ExtractedSection(
                text="",
                references=[],
                error=build_issue_diagnostics(
                    e,
                    context="extract_page",
                    target_url=url,
                    section_name=section_name,
                ),
            )

    async def _extract_page_once(
        self,
        url: str,
        section_name: str,
    ) -> ExtractedSection:
        """Single attempt to navigate, scroll, and extract innerText."""
        await self._navigate_to_page(url)
        await detect_rate_limit(self._page)

        # Wait for main content to render
        try:
            await self._page.wait_for_selector("main")
        except PlaywrightTimeoutError:
            logger.debug("No <main> element found on %s", url)

        # Dismiss any modals blocking content
        await handle_modal_close(self._page)

        # Derive page_type from URL for context-aware noise stripping
        page_type = (
            "grid"
            if any(
                p in url
                for p in (
                    "/reels/",
                    "/tagged/",
                    "/explore/tags/",
                    "/explore/locations/",
                )
            )
            else "default"
        )

        # Profile pages with lazy-loaded content need extra scroll
        is_profile = (
            "/reels/" in url or "/tagged/" in url or url.rstrip("/").count("/") <= 4
        )
        if is_profile:
            try:
                await self._page.wait_for_function(
                    """() => {
                        const main = document.querySelector('main');
                        if (!main) return false;
                        return main.innerText.length > 200;
                    }""",
                    timeout=10000,
                )
            except PlaywrightTimeoutError:
                logger.debug("Profile content did not appear on %s", url)

        # Scroll to trigger lazy loading
        if is_profile:
            await scroll_to_bottom(self._page, pause_time=1.0, max_scrolls=10)
        else:
            await scroll_to_bottom(self._page, pause_time=0.5, max_scrolls=5)

        # Extract text from main content area
        raw_result = await self._extract_root_content(["main"])
        raw = raw_result["text"]

        if not raw:
            return ExtractedSection(text="", references=[])
        truncated = _truncate_instagram_noise(raw, page_type=page_type)
        if not truncated and raw.strip():
            logger.warning(
                "Page %s returned only Instagram chrome (likely rate-limited)", url
            )
            return ExtractedSection(text=_RATE_LIMITED_MSG, references=[])
        cleaned = _filter_instagram_noise_lines(truncated)

        # Check for rate limit in content text
        if _detect_rate_limit_text(cleaned):
            logger.warning("Rate limit detected in page content: %s", url)
            return ExtractedSection(text=_RATE_LIMITED_MSG, references=[])

        return ExtractedSection(
            text=cleaned,
            references=build_references(raw_result["references"], section_name),
        )

    async def extract_current_page(self, section_name: str) -> ExtractedSection:
        """Extract innerText from the currently loaded page without re-navigating.

        Used after SPA tab switches where calling extract_page() would
        re-navigate to the base URL and lose the active tab state.
        """
        url = self._page.url
        await detect_rate_limit(self._page)

        try:
            await self._page.wait_for_selector("main", timeout=5000)
        except PlaywrightTimeoutError:
            logger.debug("No <main> element found on current page")

        await handle_modal_close(self._page)

        page_type = (
            "grid"
            if any(
                p in url
                for p in (
                    "/reels/",
                    "/tagged/",
                    "/explore/tags/",
                    "/explore/locations/",
                )
            )
            else "default"
        )

        try:
            await self._page.wait_for_function(
                """() => {
                    const main = document.querySelector('main');
                    if (!main) return false;
                    return main.innerText.length > 200;
                }""",
                timeout=8000,
            )
        except PlaywrightTimeoutError:
            logger.debug("Page content did not load on current page")

        await scroll_to_bottom(self._page, pause_time=0.5, max_scrolls=5)

        raw_result = await self._extract_root_content(["main"])
        raw = raw_result["text"]

        if not raw:
            return ExtractedSection(text="", references=[])
        truncated = _truncate_instagram_noise(raw, page_type=page_type)
        if not truncated and raw.strip():
            return ExtractedSection(text=_RATE_LIMITED_MSG, references=[])
        cleaned = _filter_instagram_noise_lines(truncated)

        if _detect_rate_limit_text(cleaned):
            return ExtractedSection(text=_RATE_LIMITED_MSG, references=[])

        return ExtractedSection(
            text=cleaned,
            references=build_references(raw_result["references"], section_name),
        )

    # ------------------------------------------------------------------
    # Structured data extraction (OG meta, video URLs, engagement)
    # ------------------------------------------------------------------

    async def extract_og_metadata(self) -> dict[str, str]:
        """Extract all Open Graph meta tags from the current page.

        Returns dict of property -> content for all og:* meta tags.
        Common keys: og:title, og:description, og:image, og:video,
        og:video:secure_url, og:like_count, og:video_view_count,
        og:comment_count, article:published_time.
        """
        return await self._page.evaluate("""() => {
            const metas = document.querySelectorAll('meta[property^="og:"], meta[property="article:published_time"]');
            const data = {};
            metas.forEach(m => {
                const prop = m.getAttribute('property');
                const content = m.getAttribute('content');
                if (prop && content) data[prop] = content;
            });
            return data;
        }""")

    async def extract_video_url(self) -> str | None:
        """Extract the video CDN URL from the current reel/post page.

        Tries multiple strategies: og:video meta tag, <video> src,
        and source element within <video>.
        """
        # Strategy 1: OG video meta tag
        og_data = await self.extract_og_metadata()
        video_url = og_data.get("og:video") or og_data.get("og:video:secure_url")
        if video_url:
            return video_url

        # Strategy 2: <video> element src
        video_url = await self._page.evaluate("""() => {
            const video = document.querySelector('video');
            if (video?.src && video.src.startsWith('http')) return video.src;
            const source = document.querySelector('video source');
            if (source?.src && source.src.startsWith('http')) return source.src;
            return null;
        }""")
        return video_url

    async def extract_thumbnail_url(self) -> str | None:
        """Extract the thumbnail/cover image URL from the current page.

        Tries og:image, then falls back to <img> within post/reel card.
        """
        # Strategy 1: OG image meta tag
        og_data = await self.extract_og_metadata()
        thumbnail = og_data.get("og:image")
        if thumbnail:
            return thumbnail

        # Strategy 2: First meaningful img in main (excluding icons, emojis)
        thumbnail = await self._page.evaluate("""() => {
            const main = document.querySelector('main');
            if (!main) return null;
            // Look for images from CDN (not icons)
            const imgs = main.querySelectorAll('img[src*="cdninstagram.com"]');
            for (const img of imgs) {
                const src = img.src || img.getAttribute('src');
                if (src && !src.includes('chrome-extension') && !src.includes('data:')) {
                    return src;
                }
            }
            return null;
        }""")
        return thumbnail

    async def extract_engagement_from_meta(self) -> dict[str, int | None]:
        """Extract engagement metrics from Open Graph meta tags on the current page.

        Returns dict with keys: views, likes, comments, shares (all nullable int).
        Falls back to parsing from page text if meta tags are unavailable.
        """

        og_data = await self.extract_og_metadata()
        views = og_data.get("og:video_view_count")
        likes = og_data.get("og:like_count")
        comments = og_data.get("og:comment_count")

        result = {
            "views": _parse_number(views),
            "likes": _parse_number(likes),
            "comments": _parse_number(comments),
        }

        # Fallback: parse engagement from page text if meta tags are empty
        # Instagram shows "X likes, Y comments" in the caption area
        if result["likes"] is None or result["comments"] is None:
            page_text = await self._page.evaluate("""() => {
                const main = document.querySelector('main');
                return main ? main.innerText || '' : '';
            }""")

            # Pattern: "10 likes, 1 comments - username on ..."
            like_match = re.search(r"([\d,.KkMm]+)\s*likes?", page_text)
            comment_match = re.search(r"([\d,.KkMm]+)\s*comments?", page_text)
            view_match = re.search(r"([\d,.KkMm]+)\s*views?", page_text)

            if result["likes"] is None and like_match:
                result["likes"] = _parse_number(like_match.group(1))
            if result["comments"] is None and comment_match:
                result["comments"] = _parse_number(comment_match.group(1))
            if result["views"] is None and view_match:
                result["views"] = _parse_number(view_match.group(1))

        return result

    async def extract_timestamp(self) -> str | None:
        """Extract the publication timestamp from the current page.

        Tries <time datetime>, article:published_time meta, then
        falls back to parsing relative time text from innerText.
        """
        # Strategy 1: <time datetime> element
        timestamp = await self._page.evaluate("""() => {
            const time = document.querySelector('time[datetime]');
            return time?.getAttribute('datetime') || null;
        }""")
        if timestamp:
            return timestamp

        # Strategy 2: article:published_time meta
        og_data = await self.extract_og_metadata()
        published = og_data.get("article:published_time")
        if published:
            return published

        return None

    async def extract_audio_info(self) -> dict[str, str | None]:
        """Extract audio/music information from the current reel page.

        Returns dict with keys: audio_name, audio_artist.
        Filters out UI noise like "Audio is muted".
        """
        return await self._page.evaluate("""() => {
            // Audio info is typically in a link near the reel
            const audioLinks = document.querySelectorAll('a[href*="/reels/audio/"]');
            if (audioLinks.length > 0) {
                const text = audioLinks[0].innerText || audioLinks[0].textContent || '';
                // Filter out UI noise
                const noise = ['Audio is muted', 'Audio', 'Original audio', 'Muted'];
                if (noise.includes(text.trim())) {
                    // Try the next audio link or return the text as-is if it has more content
                    for (let i = 1; i < audioLinks.length; i++) {
                        const altText = audioLinks[i].innerText || audioLinks[i].textContent || '';
                        if (!noise.includes(altText.trim()) && altText.trim()) {
                            const parts = altText.split('•').map(s => s.trim()).filter(Boolean);
                            if (parts.length >= 2) {
                                return { audio_name: parts[1], audio_artist: parts[0] };
                            }
                            return { audio_name: altText || null, audio_artist: null };
                        }
                    }
                    // If all audio links are noise, return null
                    return { audio_name: null, audio_artist: null };
                }
                // Format is typically "Artist • Track Name" or "Track Name"
                const parts = text.split('•').map(s => s.trim()).filter(Boolean);
                if (parts.length >= 2) {
                    return { audio_name: parts[1], audio_artist: parts[0] };
                }
                return { audio_name: text || null, audio_artist: null };
            }
            return { audio_name: null, audio_artist: null };
        }""")

    async def extract_caption_from_page(self) -> str | None:
        """Extract the post/reel caption from the current page.

        Tries JSON-LD structured data first (full caption), then falls back to
        og:description (may be truncated), then to parsing the caption section
        from innerText.
        """
        # Try JSON-LD first — it has the full caption, unlike og:description
        try:
            json_ld_caption = await self._page.evaluate("""() => {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const script of scripts) {
                    try {
                        const data = JSON.parse(script.textContent);
                        // Instagram uses schema.org Article or VideoObject
                        if (data && data.description) {
                            return data.description;
                        }
                        // Check nested @graph
                        if (data && data['@graph']) {
                            for (const item of data['@graph']) {
                                if (item.description) {
                                    return item.description;
                                }
                            }
                        }
                    } catch (e) { /* skip malformed JSON */ }
                }
                return null;
            }""")
            if json_ld_caption:
                return json_ld_caption
        except Exception:
            logger.debug("Failed to extract caption from JSON-LD")

        # Try extracting from sharedData / window._sharedData
        try:
            shared_caption = await self._page.evaluate("""() => {
                try {
                    // Try __additionalDataInjected first
                    if (window.__additionalDataInjected) {
                        const keys = Object.keys(window.__additionalDataInjected);
                        for (const key of keys) {
                            const data = window.__additionalDataInjected[key].data;
                            if (data && data.shortcode_media) {
                                return data.shortcode_media.edge_media_to_caption.edges[0]?.node?.text || null;
                            }
                        }
                    }
                    // Try __initialDataInjected
                    if (window.__initialDataInjected) {
                        const text = window.__initialDataInjected;
                        if (text && text.includes('edge_media_to_caption')) {
                            const match = text.match(/"text":"((?:[^"\\\\]|\\\\.)*)"/);
                            if (match) return match[1].replace(/\\\\n/g, '\n');
                        }
                    }
                } catch (e) { /* skip */ }
                return null;
            }""")
            if shared_caption:
                return shared_caption
        except Exception:
            logger.debug("Failed to extract caption from shared data")

        return None

    # ------------------------------------------------------------------
    # Reel and Post structured extraction
    # ------------------------------------------------------------------

    async def _extract_reel_links(self, max_links: int = 50) -> list[Reference]:
        """Extract reel links from the current reels grid page.

        Returns a list of Reference objects with reel URLs and context.
        """
        links = await self._page.evaluate(f"""() => {{
            const anchors = Array.from(document.querySelectorAll('a[href*="/reel/"]'));
            return anchors.slice(0, {max_links}).map(a => {{
                // Filter out extension-injected anchors (e.g. download helpers)
                if (a.href.startsWith('chrome-extension:') || a.href.startsWith('moz-extension:')) return null;
                const href = a.href;
                const match = href.match(/\/reel\/([A-Za-z0-9_-]+)/);
                const reelId = match ? match[1] : '';
                // Get view count from nearby text or aria-label
                const parent = a.closest('article, div');
                let viewCount = '';
                if (parent) {{
                    const text = parent.innerText || '';
                    const numbers = text.match(/[\\d,]+/g);
                    if (numbers && numbers.length > 0) {{
                        viewCount = numbers[0];
                    }}
                }}
                return {{
                    url: href,
                    text: `reel:${{reelId}}`,
                    context: viewCount,
                    reel_id: reelId,
                }};
            }}).filter(Boolean);
        }}""")

        return [
            Reference(
                kind="reel",
                url=link["url"],
                text=link["text"],
                context=link.get("context", ""),
            )
            for link in links
            if link["url"]
        ]

    async def _extract_reels_from_grid(
        self, max_reels: int = 50
    ) -> list[dict[str, Any]]:
        """Extract structured reel data from the reels grid page.

        Returns list of dicts with basic reel info available from the grid
        (ID, URL, thumbnail, approximate view count). Full details require
        navigating to individual reel pages.
        """
        return await self._page.evaluate(
            """({ maxReels }) => {
            const anchors = Array.from(document.querySelectorAll('a[href*="/reel/"]'));
            const results = [];
            for (let i = 0; i < Math.min(anchors.length, maxReels); i++) {
                const a = anchors[i];
                if (a.href.startsWith('chrome-extension:') || a.href.startsWith('moz-extension:')) continue;

                const href = a.href || '';
                const match = href.match(/\/reel\/([A-Za-z0-9_-]+)/);
                const reelId = match ? match[1] : '';

                // Get thumbnail from multiple strategies (Instagram lazy-loads images)
                let thumbnail = null;

                const extractCdnUrl = (url) => {
                    if (!url) return null;
                    url = url.trim().split(' ')[0];
                    if (url.startsWith('chrome-extension:') || url.startsWith('moz-extension:') || url.startsWith('data:')) return null;
                    if (url.includes('cdninstagram.com') || url.includes('instagram.f')) return url;
                    return null;
                };

                // Strategy 1: Check descendant divs with background-image (Instagram's current grid layout)
                const bgDiv = a.querySelector('div[style*="background-image"][style*="instagram"]');
                if (bgDiv) {
                    const style = bgDiv.getAttribute('style') || '';
                    const urlStart = style.indexOf('url(');
                    if (urlStart !== -1) {
                        let urlInner = style.substring(urlStart + 4).trim();
                        if (urlInner.startsWith('"') || urlInner.startsWith("'")) {
                            urlInner = urlInner.substring(1);
                        }
                        const endIdx = urlInner.search(/["')\s]/);
                        const url = endIdx !== -1 ? urlInner.substring(0, endIdx) : urlInner;
                        if (url.includes('instagram')) thumbnail = url;
                    }
                }

                // Strategy 2: Check img elements (fallback for older layouts)
                if (!thumbnail) {
                    const imgs = Array.from(a.querySelectorAll('img'));
                    let largestArea = 0;
                    for (const img of imgs) {
                        const srcset = img.srcset || img.getAttribute('srcset') || '';
                        if (srcset) {
                            const entries = srcset.split(',').map(e => e.trim());
                            for (const entry of entries) {
                                const url = entry.split(/\s+/)[0];
                                const cdnUrl = extractCdnUrl(url);
                                if (cdnUrl) { thumbnail = cdnUrl; break; }
                            }
                        }
                        if (!thumbnail) {
                            const dataSrc = img.dataset?.src || img.getAttribute('data-src') || img.getAttribute('data-lazy-src') || '';
                            const cdnUrl = extractCdnUrl(dataSrc);
                            if (cdnUrl) { thumbnail = cdnUrl; }
                        }
                        if (!thumbnail) {
                            const src = img.src || img.getAttribute('src') || '';
                            const cdnUrl = extractCdnUrl(src);
                            if (cdnUrl) {
                                const area = (img.width || 0) * (img.height || 0);
                                if (area > largestArea) { largestArea = area; thumbnail = cdnUrl; }
                            }
                        }
                    }
                }

                // Strategy 2: Check <picture><source> elements
                if (!thumbnail) {
                    const pictures = Array.from(a.querySelectorAll('picture'));
                    for (const pic of pictures) {
                        const sources = Array.from(pic.querySelectorAll('source'));
                        for (const src of sources) {
                            const srcset = src.srcset || src.getAttribute('srcset') || '';
                            if (srcset) {
                                const url = srcset.split(',')[0].split(/\s+/)[0];
                                const cdnUrl = extractCdnUrl(url);
                                if (cdnUrl) { thumbnail = cdnUrl; break; }
                            }
                        }
                        if (thumbnail) break;
                    }
                }

                // Strategy 3: Last resort - any CDN URL found in the anchor's innerHTML
                if (!thumbnail) {
                    const htmlMatch = a.innerHTML.match(/https?:\/\/[^"'\s]*cdninstagram\.com[^"'\s]*/);
                    if (htmlMatch) {
                        thumbnail = htmlMatch[0];
                    }
                }

                let viewCountText = '';
                const ariaLabel = a.getAttribute('aria-label') || '';
                if (ariaLabel) {
                    const viewMatch = ariaLabel.match(/([\\d,]+)\\s*views?/i);
                    if (viewMatch) viewCountText = viewMatch[1];
                }
                if (!viewCountText) {
                    const text = a.innerText || '';
                    const numbers = text.match(/[\\d,]+/g);
                    if (numbers && numbers.length > 0) {
                        viewCountText = numbers[0];
                    }
                }

                results.push({
                    index: i,
                    id: reelId || null,
                    shortcode: reelId || null,
                    url: href.startsWith('http') ? href : `https://www.instagram.com${href}`,
                    thumbnail_url: thumbnail,
                    video_url: null,
                    view_count_text: viewCountText,
                    media_type: 'reel',
                });
            }
            return results;
        }""",
            {"maxReels": max_reels},
        )

    async def _extract_posts_from_grid(
        self, max_posts: int = 50
    ) -> list[dict[str, Any]]:
        """Extract structured post data from the posts grid page.

        Returns list of dicts with basic post info available from the grid.
        Only extracts posts (not reels) — use _extract_reels_from_grid for reels.
        """
        return await self._page.evaluate(
            """({ maxPosts }) => {
            // Only match /p/ links — exclude /reel/ to prevent mixing content types
            const anchors = Array.from(document.querySelectorAll('a[href*="/p/"]'));
            const results = [];
            for (let i = 0; i < Math.min(anchors.length, maxPosts); i++) {
                const a = anchors[i];
                // Skip extension-injected anchors
                if (a.href.startsWith('chrome-extension:') || a.href.startsWith('moz-extension:')) continue;

                const href = a.href || '';
                const isReel = href.includes('/reel/');
                const type = isReel ? 'reel' : 'post';
                const idMatch = href.match(/\/(p|reel)\/([A-Za-z0-9_-]+)/);
                const shortcode = idMatch ? idMatch[2] : '';

                // Get thumbnail: prefer largest CDN image, skip extension icons
                const imgs = Array.from(a.querySelectorAll('img'));
                let thumbnail = null;
                let largestArea = 0;
                for (const img of imgs) {
                    const src = img.src || img.getAttribute('src') || '';
                    if (src.startsWith('chrome-extension:') || src.startsWith('moz-extension:') || src.startsWith('data:')) continue;
                    if (src.includes('cdninstagram.com')) {
                        const area = (img.width || 0) * (img.height || 0);
                        if (area > largestArea) {
                            largestArea = area;
                            thumbnail = src;
                        }
                    }
                }
                if (!thumbnail && imgs.length > 0) {
                    for (const img of imgs) {
                        const src = img.src || img.getAttribute('src') || '';
                        if (src.includes('cdninstagram.com') && !src.startsWith('chrome-extension:')) {
                            thumbnail = src;
                            break;
                        }
                    }
                }

                results.push({
                    index: i,
                    id: shortcode || null,
                    shortcode: shortcode || null,
                    url: href.startsWith('http') ? href : `https://www.instagram.com${href}`,
                    thumbnail_url: thumbnail,
                    video_url: null,
                    media_type: type,
                });
            }
            return results;
        }""",
            {"maxPosts": max_posts},
        )

    # ------------------------------------------------------------------
    # User profile scraping
    # ------------------------------------------------------------------

    async def scrape_user(
        self,
        username: str,
        requested: set[str],
        callbacks: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Scrape an Instagram user profile with configurable sections.

        Returns:
            {url, sections: {name: text}}
        """
        requested = requested | {"main_profile"}
        base_url = f"https://www.instagram.com/{username}"
        sections: dict[str, str] = {}
        references: dict[str, list[Reference]] = {}
        section_errors: dict[str, dict[str, Any]] = {}

        requested_ordered = [
            (name, suffix, is_overlay)
            for name, (suffix, is_overlay) in USER_SECTIONS.items()
            if name in requested
        ]
        total = len(requested_ordered)

        if callbacks:
            await callbacks.on_start("user profile", base_url)

        try:
            for i, (section_name, suffix, is_overlay) in enumerate(requested_ordered):
                if i > 0:
                    await asyncio.sleep(_NAV_DELAY)

                url = base_url + suffix
                try:
                    extracted = await self.extract_page(url, section_name=section_name)

                    if extracted.text and extracted.text != _RATE_LIMITED_MSG:
                        sections[section_name] = extracted.text
                        if extracted.references:
                            references[section_name] = extracted.references
                    elif extracted.error:
                        section_errors[section_name] = extracted.error

                except InstagramScraperException:
                    raise
                except Exception as e:
                    logger.warning("Error scraping section %s: %s", section_name, e)
                    section_errors[section_name] = build_issue_diagnostics(
                        e,
                        context="scrape_user",
                        target_url=url,
                        section_name=section_name,
                    )

                if callbacks:
                    percent = round((i + 1) / total * 95)
                    await callbacks.on_progress(
                        f"Scraped {section_name} ({i + 1}/{total})", percent
                    )
        except InstagramScraperException as e:
            if callbacks:
                await callbacks.on_error(e)
            raise

        result: dict[str, Any] = {
            "url": f"{base_url}/",
            "sections": sections,
        }
        if references:
            result["references"] = references
        if section_errors:
            result["section_errors"] = section_errors

        if callbacks:
            await callbacks.on_complete("user profile", result)

        return result

    async def scrape_user_posts(
        self,
        username: str,
        max_posts: int = 12,
        callbacks: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Scrape posts from a user's profile, scrolling to load more.

        Returns structured post data extracted from the grid page.
        Note: Only extracts image/carousel posts (/p/), not reels (/reel/).
        Use scrape_user_reels for reel data.

        Returns:
            {url, posts: [{id, url, thumbnail_url, media_type, ...}],
             total_posts, sections: {posts: text}, references?: {posts: [post_links]}}
        """
        url = f"https://www.instagram.com/{username}/"
        if callbacks:
            await callbacks.on_start("user posts", url)

        # Timeout guard for large accounts
        try:
            await asyncio.wait_for(self._navigate_to_page(url), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("Navigation timeout for user posts page: %s", url)
            result = {
                "url": url,
                "posts": [],
                "total_posts": 0,
                "sections": {},
                "warnings": [
                    f"Navigation to {url} timed out. "
                    f"The account may have too much content to load."
                ],
            }
            if callbacks:
                await callbacks.on_complete("user posts", result)
            return result
        except Exception as e:
            logger.error("Navigation failed for user posts page %s: %s", url, e)
            result = {
                "url": url,
                "posts": [],
                "total_posts": 0,
                "sections": {},
                "warnings": [f"Navigation failed: {e}"],
            }
            if callbacks:
                await callbacks.on_complete("user posts", result)
            return result

        try:
            await detect_rate_limit(self._page)

            try:
                await self._page.wait_for_selector("main", timeout=10000)
            except PlaywrightTimeoutError:
                logger.debug("No <main> element found on user posts page %s", url)

            await handle_modal_close(self._page)

            # Scroll to load posts (optimized for speed)
            scrolls = max(1, max_posts // 12)
            await scroll_to_bottom(self._page, pause_time=0.5, max_scrolls=scrolls)

            # Wait for posts to render after scrolling
            await asyncio.sleep(1.0)

            # Extract structured post data from the grid (posts only, not reels)
            posts_data = await self._extract_posts_from_grid(max_posts)

            # Extract post links as references
            post_links = await self._extract_post_links(max_posts)

            # Filter references to only include posts (not reels) for consistency
            post_only_links = [ref for ref in post_links if ref.kind == "post"]

            # Extract text section for backward compatibility
            raw_result = await self._extract_root_content(["main"])
            raw = raw_result["text"]
            cleaned = strip_instagram_noise(raw, page_type="grid") if raw else ""

            warnings: list[str] = []
            if not posts_data and not post_links:
                warnings.append(
                    "No posts found. The account may be private, have no posts, "
                    "or the page may not have fully loaded."
                )

            result: dict[str, Any] = {
                "url": url,
                "posts": posts_data,
                "total_posts": len(posts_data),
                "sections": {},
            }
            if warnings:
                result["warnings"] = warnings
            if cleaned:
                result["sections"]["posts"] = cleaned
            if post_only_links:
                result["references"] = {"posts": post_only_links}

            if callbacks:
                await callbacks.on_complete("user posts", result)
            return result

        except Exception as e:
            logger.error(
                "scrape_user_posts failed for %s: %s", username, e, exc_info=True
            )
            # Return partial results instead of raising — the calling tool
            # should surface warnings, not crash.
            return {
                "url": url,
                "posts": posts_data if "posts_data" in locals() else [],
                "total_posts": len(posts_data) if "posts_data" in locals() else 0,
                "sections": {},
                "warnings": [
                    f"Scraping encountered an error: {e}. "
                    f"Some or all posts may be missing. "
                    f"Try again with a smaller max_posts value."
                ],
            }

    async def _extract_post_links(self, max_links: int = 50) -> list[Reference]:
        """Extract post and reel links from the current page.

        Returns references with kind='post' for /p/ links and kind='reel' for /reel/ links.
        """
        links = await self._page.evaluate(f"""() => {{
            const anchors = Array.from(document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]'));
            return anchors.slice(0, {max_links}).map(a => {{
                // Skip extension-injected anchors
                if (a.href.startsWith('chrome-extension:') || a.href.startsWith('moz-extension:')) return null;
                const href = a.href;
                const match = href.match(/\/(p|reel)\/([A-Za-z0-9_-]+)/);
                const postId = match ? match[2] : '';
                const type = href.includes('/reel/') ? 'reel' : 'post';
                return {{
                    url: href,
                    text: `${{type}}:${{postId}}`,
                    context: (a.innerText || '').slice(0, 100).replace(/\\s+/g, ' ').trim(),
                    type: type,
                }};
            }}).filter(Boolean);
        }}""")

        from instagram_mcp_server.scraping.link_metadata import Reference

        return [
            Reference(
                kind=link["type"],
                url=link["url"],
                text=link["text"],
                context=link["context"],
            )
            for link in links
            if link["url"]
        ]

    async def scrape_user_reels(
        self,
        username: str,
        max_reels: int = 12,
        callbacks: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Scrape reels from a user's profile reels page.

        Returns structured reel data extracted from the grid page
        without navigating to individual reels (avoids N+1 problem).

        Returns:
            {url, reels: [{id, url, thumbnail_url, view_count_text, ...}],
             total_reels, sections: {reels: text}, references: {reels: [...]}}
        """
        url = f"https://www.instagram.com/{username}/reels/"
        if callbacks:
            await callbacks.on_start("user reels", url)

        # Timeout guard for large accounts (max 30s for navigation + scroll)
        import time

        try:
            await asyncio.wait_for(self._navigate_to_page(url), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("Navigation timeout for reels page: %s", url)
            result = {
                "url": url,
                "reels": [],
                "total_reels": 0,
                "sections": {},
                "warnings": [
                    f"Navigation to {url} timed out. "
                    f"The account may have too much content to load. "
                    f"Try again with a smaller max_reels value."
                ],
            }
            if callbacks:
                await callbacks.on_complete("user reels", result)
            return result
        except Exception as e:
            logger.error("Navigation failed for reels page %s: %s", url, e)
            result = {
                "url": url,
                "reels": [],
                "total_reels": 0,
                "sections": {},
                "warnings": [f"Navigation failed: {e}"],
            }
            if callbacks:
                await callbacks.on_complete("user reels", result)
            return result

        start_time = time.time()
        try:
            await detect_rate_limit(self._page)
            try:
                await self._page.wait_for_selector("main", timeout=10000)
            except PlaywrightTimeoutError:
                pass
            await handle_modal_close(self._page)

            # Scroll to load more reels
            scrolls = max(1, max_reels // 12)
            await scroll_to_bottom(self._page, pause_time=0.5, max_scrolls=scrolls)
            await asyncio.sleep(0.5)

            elapsed = time.time() - start_time
            if elapsed > 25:
                logger.warning(
                    "Reels extraction took %.1fs for %s, may have hit rate limit",
                    elapsed,
                    username,
                )

            # Extract structured reel data from the grid
            reels_data = await self._extract_reels_from_grid(max_reels)

            # Race-condition retry: if 0 reels found, wait and re-scroll
            if not reels_data:
                logger.debug("No reels on first attempt, retrying with extra wait...")
                await asyncio.sleep(2.0)
                await scroll_to_bottom(self._page, pause_time=0.5, max_scrolls=scrolls)
                await asyncio.sleep(1.0)
                reels_data = await self._extract_reels_from_grid(max_reels)

            # Parse view_count_text into integer view_count for each reel
            for reel in reels_data:
                view_text = reel.get("view_count_text")
                reel["view_count"] = _parse_number(view_text) if view_text else None

            # Also extract post/reel links as references for backward compatibility
            reel_links = await self._extract_reel_links(max_reels)

            # Extract text section for backward compatibility
            raw_result = await self._extract_root_content(["main"])
            raw = raw_result["text"]
            cleaned = strip_instagram_noise(raw, page_type="grid") if raw else ""

            warnings: list[str] = []
            if not reels_data and not reel_links:
                warnings.append(
                    "No reels found. The account may be private, have no reels, "
                    "or the page may not have fully loaded."
                )
            elif len(reels_data) < max_reels and len(reel_links) >= max_reels:
                warnings.append(
                    f"Only extracted {len(reels_data)} of {max_reels} requested reels. "
                    f"Increase max_reels or try scrolling more for additional results."
                )

            result: dict[str, Any] = {
                "url": url,
                "reels": reels_data,
                "total_reels": len(reels_data),
                "sections": {},
            }
            if warnings:
                result["warnings"] = warnings
            if cleaned:
                result["sections"]["reels"] = cleaned
            if reel_links:
                result["references"] = {"reels": reel_links}

            if callbacks:
                await callbacks.on_complete("user reels", result)
            return result
        except Exception as e:
            logger.error(
                "scrape_user_reels failed for %s: %s", username, e, exc_info=True
            )
            # Return partial results instead of raising — the calling tool
            # should surface warnings, not crash.
            return {
                "url": url,
                "reels": reels_data if "reels_data" in locals() else [],
                "total_reels": len(reels_data) if "reels_data" in locals() else 0,
                "sections": {},
                "warnings": [
                    f"Scraping encountered an error: {e}. "
                    f"Some or all reels may be missing. "
                    f"Try again with a smaller max_reels value."
                ],
            }

    async def scrape_user_stories(
        self,
        username: str,
        callbacks: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Scrape active stories from a user's profile.

        Returns:
            {url, sections: {stories: text}, stories: [{media_url, timestamp}]}
        """
        url = f"https://www.instagram.com/stories/{username}/"
        if callbacks:
            await callbacks.on_start("user stories", url)

        await self._navigate_to_page(url)
        await detect_rate_limit(self._page)

        # Check if we were redirected to the profile page (no active stories)
        current_url = self._page.url
        if username in current_url and "/stories/" not in current_url:
            # Redirected to profile — no active stories
            result = {
                "url": url,
                "sections": {"stories": f"No active stories for @{username}"},
                "stories": [],
                "warnings": [
                    f"No active stories found for @{username}. "
                    f"Stories expire after 24 hours."
                ],
            }
            if callbacks:
                await callbacks.on_complete("user stories", result)
            return result

        try:
            await self._page.wait_for_selector("main, [role='dialog']")
        except PlaywrightTimeoutError:
            pass

        # Try to extract structured story data
        stories_data = []
        try:
            stories_data = await self._page.evaluate("""() => {
                // Stories are typically in a full-screen viewer
                const video = document.querySelector('video');
                const img = document.querySelector('img[src*="cdninstagram.com"]');
                const timeEl = document.querySelector('time[datetime]');
                return {
                    has_video: !!video,
                    has_image: !!img,
                    timestamp: timeEl?.getAttribute('datetime') || null,
                    video_src: video?.src || null,
                    img_src: img?.src || null,
                };
            }""")
        except Exception:
            pass

        raw_result = await self._extract_root_content(["main", "[role='dialog']"])
        raw = raw_result["text"]
        cleaned = strip_instagram_noise(raw) if raw else ""

        result = self._single_section_result(url, "stories", cleaned)
        if stories_data:
            result["stories"] = [stories_data]

        if callbacks:
            await callbacks.on_complete("user stories", result)
        return result

    async def scrape_user_highlights(
        self,
        username: str,
        callbacks: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Scrape story highlights from a user's profile.

        Returns:
            {url, sections: {highlights: text}, references?}
        """
        url = f"https://www.instagram.com/{username}/"
        if callbacks:
            await callbacks.on_start("user highlights", url)

        await self._navigate_to_page(url)
        await detect_rate_limit(self._page)
        try:
            await self._page.wait_for_selector("main")
        except PlaywrightTimeoutError:
            pass
        await handle_modal_close(self._page)

        # Highlights are at the TOP of the profile page — scroll to top first,
        # then scroll down just enough to ensure they render, but not so far
        # that we scroll past them.
        await self._page.evaluate("""() => {
            window.scrollTo(0, 0);
        }""")
        await asyncio.sleep(1.0)

        # Extract highlight references using multiple strategies
        highlight_refs = []
        try:
            links = await self._page.evaluate("""() => {
                const anchors = document.querySelectorAll('a[href*="/stories/highlights/"]');
                return Array.from(anchors).map(a => ({
                    kind: 'story',
                    url: a.getAttribute('href') || '',
                    text: (a.textContent || '').trim(),
                    aria_label: (a.getAttribute('aria-label') || '').trim(),
                }));
            }""")
            if links:
                for link in links:
                    title = link.get("aria_label") or link.get("text") or ""
                    # Clean up "View X highlight" prefix noise
                    title = re.sub(r"^View\s+", "", title)
                    title = re.sub(r"\s+highlight$", "", title, flags=re.IGNORECASE)
                    title = title.strip()
                    highlight_refs.append(
                        {
                            "kind": link.get("kind", "story"),
                            "url": link.get("url", ""),
                            "text": title or "Unknown",
                        }
                    )
        except Exception:
            pass

        # Also extract text for backward compatibility — but only the header area
        # where highlights appear (don't scroll past them)
        raw_result = await self._extract_root_content(["main"])
        raw = raw_result["text"]
        # Use a lighter noise stripping for highlights — preserve more content
        cleaned = strip_instagram_noise(raw, page_type="default") if raw else ""

        # Truncate to just the header + highlights area
        # Highlights appear after bio and before "Suggested for you"
        if "Suggested for you" in cleaned:
            cleaned = cleaned.split("Suggested for you")[0].strip()
        if "Discover more" in cleaned:
            cleaned = cleaned.split("Discover more")[0].strip()

        result = self._single_section_result(url, "highlights", cleaned)
        if highlight_refs:
            result["references"] = {"highlights": highlight_refs}

        if callbacks:
            await callbacks.on_complete("user highlights", result)
        return result

    # ------------------------------------------------------------------
    # Business/Creator insights
    # ------------------------------------------------------------------

    async def scrape_business_insights(
        self,
        callbacks: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Scrape business/creator dashboard overview.

        Returns:
            {url, sections: {overview: text}}
        """
        url = "https://www.instagram.com/accounts/insights/"
        if callbacks:
            await callbacks.on_start("business insights", url)

        extracted = await self.extract_page(url, section_name="overview")
        sections: dict[str, str] = {}
        section_errors: dict[str, dict[str, Any]] = {}

        if extracted.text and extracted.text != _RATE_LIMITED_MSG:
            sections["overview"] = extracted.text
        elif extracted.error:
            section_errors["overview"] = extracted.error

        result: dict[str, Any] = {"url": url, "sections": sections}
        if section_errors:
            result["section_errors"] = section_errors

        if callbacks:
            await callbacks.on_complete("business insights", result)
        return result

    async def scrape_audience_insights(
        self,
        callbacks: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Scrape audience insights tab from professional dashboard.

        Returns:
            {url, sections: {audience: text}}
        """
        url = "https://www.instagram.com/accounts/insights/?show_tab=audience"
        if callbacks:
            await callbacks.on_start("audience insights", url)

        extracted = await self.extract_page(url, section_name="audience")
        sections: dict[str, str] = {}
        section_errors: dict[str, dict[str, Any]] = {}

        if extracted.text and extracted.text != _RATE_LIMITED_MSG:
            sections["audience"] = extracted.text
        elif extracted.error:
            section_errors["audience"] = extracted.error

        result: dict[str, Any] = {"url": url, "sections": sections}
        if section_errors:
            result["section_errors"] = section_errors

        if callbacks:
            await callbacks.on_complete("audience insights", result)
        return result

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def _perform_search_interaction(
        self,
        query: str,
        search_type: Literal["users", "locations"] = "users",
    ) -> tuple[str, str]:
        """Navigate to Instagram search and extract results using search box interaction.

        Uses search box interaction for all search types as direct URL navigation
        is often blocked by Instagram's client-side routing.

        Returns:
            Tuple of (final_url, extracted_text)
        """
        # Navigate to explore page (more reliable than home page for search)
        await self._navigate_to_page("https://www.instagram.com/explore/")
        await detect_rate_limit(self._page)

        try:
            await self._page.wait_for_selector("main", timeout=10000)
        except PlaywrightTimeoutError:
            pass
        await handle_modal_close(self._page)

        # Try to find search input with multiple strategies
        search_found = await self._find_and_fill_search(query)

        if not search_found:
            logger.warning("Could not find search input on Instagram explore page")
            # Fallback: try direct URL navigation to search results
            search_type_path = "people" if search_type == "users" else "location"
            fallback_url = f"https://www.instagram.com/explore/search/{search_type_path}/?q={quote_plus(query)}"
            try:
                await self._navigate_to_page(fallback_url)
                await asyncio.sleep(3.0)
                raw_result = await self._extract_root_content(["main"])
                raw = raw_result["text"]
                cleaned = strip_instagram_noise(raw, page_type="grid") if raw else ""
                if cleaned and not self._looks_like_home_feed(cleaned):
                    return self._page.url, cleaned
            except Exception:
                pass
            return self._page.url, ""

        # Wait for search results dropdown to appear
        try:
            await self._page.wait_for_selector(
                '[role="listbox"], [role="menu"], div[role="dialog"]',
                timeout=8000,
            )
        except PlaywrightTimeoutError:
            logger.debug(
                "Search results dropdown did not appear, waiting for async render"
            )
            await asyncio.sleep(3.0)

        # Click the appropriate search tab (if applicable)
        if search_type == "users":
            await self._click_search_tab("Users")
        elif search_type == "locations":
            await self._click_search_tab("Places")

        await asyncio.sleep(2.0)

        # Scroll to load more results
        await self._scroll_main_scrollable_region(
            position="bottom", attempts=3, pause_time=0.5
        )
        await asyncio.sleep(1.0)

        raw_result = await self._extract_root_content(["main"])
        raw = raw_result["text"]
        cleaned = strip_instagram_noise(raw, page_type="grid") if raw else ""

        # Validate: if it looks like a home feed, the search failed
        if cleaned and self._looks_like_home_feed(cleaned):
            logger.warning("Search returned home feed instead of results")
            return self._page.url, ""

        return self._page.url, cleaned

    async def _find_and_fill_search(self, query: str) -> bool:
        """Find and fill the search input using multiple strategies.

        Returns:
            True if search was successful, False otherwise
        """
        # Strategy 0: Click search icon in sidebar first (Instagram often hides
        # the search input until the search panel is opened)
        try:
            # Try clicking the search nav item in the left sidebar
            search_nav = self._page.locator(
                'a[href*="/explore"], [aria-label="Search"], '
                '[role="button"][aria-label*="search"], '
                'nav a[href="/explore/"]'
            ).first
            await search_nav.wait_for(state="visible", timeout=3000)
            await search_nav.click()
            await asyncio.sleep(1.0)
            logger.debug("Clicked search navigation icon")
        except Exception:
            pass  # Search may already be visible

        # Strategy 1: Try common search input selectors
        search_selectors = [
            'input[aria-label*="Search"]',
            'input[placeholder*="Search"]',
            'input[type="text"][aria-label*="search"]',
            'input[data-testid*="search"]',
            'input[role="searchbox"]',
            'nav input[type="text"]',
            'header input[type="text"]',
            'div[role="search"] input',
            'input[name="searchBoxInput"]',
        ]

        for selector in search_selectors:
            try:
                search_input = self._page.locator(selector).first
                await search_input.wait_for(state="visible", timeout=2000)
                await search_input.click()
                await asyncio.sleep(0.3)
                await search_input.fill(query)
                logger.debug("Found search input using selector: %s", selector)
                return True
            except Exception:
                continue

        # Strategy 2: Try to find by label text
        try:
            search_input = self._page.get_by_label("Search", exact=False).first
            await search_input.wait_for(state="visible", timeout=2000)
            await search_input.click()
            await asyncio.sleep(0.3)
            await search_input.fill(query)
            logger.debug("Found search input by label")
            return True
        except Exception:
            pass

        # Strategy 3: Try to find by placeholder text
        try:
            search_input = self._page.get_by_placeholder("Search", exact=False).first
            await search_input.wait_for(state="visible", timeout=2000)
            await search_input.click()
            await asyncio.sleep(0.3)
            await search_input.fill(query)
            logger.debug("Found search input by placeholder")
            return True
        except Exception:
            pass

        # Strategy 4: Try keyboard shortcut (Ctrl+K or /) to open search
        try:
            await self._page.keyboard.press("/")
            await asyncio.sleep(0.5)
            await self._page.keyboard.type(query, delay=30)
            logger.debug("Used keyboard shortcut for search")
            return True
        except Exception:
            pass

        # Strategy 5: Try navigating to search page directly and using JS
        try:
            await self._navigate_to_page(
                f"https://www.instagram.com/explore/search/people/?q={quote_plus(query)}"
            )
            await asyncio.sleep(2.0)
            raw_result = await self._extract_root_content(["main"])
            if raw_result.get("text") and len(raw_result["text"]) > 200:
                logger.debug("Direct search URL navigation succeeded")
                return True
        except Exception:
            pass

        return False

    async def _click_search_tab(self, tab_name: str) -> None:
        """Click a search tab by text content.

        Args:
            tab_name: Name of the tab to click (e.g., "Users", "Hashtags", "Places")
        """
        # Map tab names to Instagram's actual tab labels
        # Instagram search tabs: "Top", "Accounts", "Audio", "Hashtags", "Places", "Reels"
        tab_label_map = {
            "Users": ["Accounts", "Top"],
            "Hashtags": ["Hashtags"],
            "Places": ["Places"],
        }
        possible_labels = tab_label_map.get(tab_name, [tab_name])

        # Strategy 1: Try using getByRole with tab role (most reliable)
        for label in possible_labels:
            try:
                tab = self._page.get_by_role("tab", name=label, exact=False).first
                await tab.wait_for(state="visible", timeout=2000)
                await tab.scroll_into_view_if_needed(timeout=2000)
                await asyncio.sleep(0.3)
                await tab.click(timeout=3000)
                await asyncio.sleep(1.5)
                logger.debug("Clicked search tab using getByRole(tab): %s", label)
                return
            except Exception:
                pass

        # Strategy 2: Try button role
        for label in possible_labels:
            try:
                tab = self._page.get_by_role("button", name=label, exact=False).first
                await tab.wait_for(state="visible", timeout=2000)
                await tab.scroll_into_view_if_needed(timeout=2000)
                await asyncio.sleep(0.3)
                await tab.click(timeout=3000)
                await asyncio.sleep(1.5)
                logger.debug("Clicked search tab using getByRole(button): %s", label)
                return
            except Exception:
                pass

        # Strategy 3: Try locator with text filter
        for label in possible_labels:
            try:
                tabs = self._page.locator('[role="tab"], button').filter(has_text=label)
                await tabs.first.wait_for(state="visible", timeout=2000)
                await tabs.first.scroll_into_view_if_needed(timeout=2000)
                await asyncio.sleep(0.3)
                await tabs.first.click(timeout=3000)
                await asyncio.sleep(1.5)
                logger.debug("Clicked search tab using locator filter: %s", label)
                return
            except Exception:
                pass

        # Strategy 4: Try finding by innerText match (original approach)
        tab_selectors = [
            '[role="tab"]',
            "button[type='button']",
            'div[role="button"]',
        ]

        for selector in tab_selectors:
            tabs = self._page.locator(selector)
            try:
                count = await tabs.count()
                for i in range(min(count, 30)):
                    try:
                        tab_element = tabs.nth(i)
                        await tab_element.wait_for(state="visible", timeout=1000)
                        text = await tab_element.inner_text(timeout=1000)
                        text_clean = text.strip().lower()

                        for label in possible_labels:
                            if (
                                label.lower() in text_clean
                                or text_clean in label.lower()
                            ):
                                await tab_element.scroll_into_view_if_needed(
                                    timeout=2000
                                )
                                await asyncio.sleep(0.3)
                                await tab_element.click(timeout=3000)
                                await asyncio.sleep(1.5)
                                logger.debug(
                                    "Clicked search tab: %s (matched '%s')",
                                    tab_name,
                                    label,
                                )
                                return
                    except Exception:
                        continue
            except Exception:
                continue

        logger.debug(
            "Could not find search tab: %s (tried labels: %s)",
            tab_name,
            possible_labels,
        )

    def _looks_like_home_feed(self, text: str) -> bool:
        """Detect if extracted text looks like Instagram home feed instead of search results.

        Home feed typically contains mixed content from various accounts with post timestamps,
        rather than focused search results like hashtag posts or location-tagged content.

        Returns:
            True if text appears to be home feed content
        """
        if not text or len(text) < 50:
            return False

        text_lower = text.lower()

        # Explicit home feed markers
        home_feed_indicators = [
            "suggested for you",
            "see everyday moments",
            "from your close friends",
            "log into instagram",
            "welcome back",
        ]

        for indicator in home_feed_indicators:
            if indicator in text_lower:
                logger.debug("Home feed detected by indicator: %s", indicator)
                return True

        # Count post metadata separators (•) - home feed has multiple posts
        dot_separator_count = text.count("\n•\n")
        logger.debug("Dot separator count: %d", dot_separator_count)

        if dot_separator_count >= 3:
            # Count unique short lines that look like usernames
            lines = text.split("\n")
            short_lines_no_space = [
                line.strip()
                for line in lines
                if line.strip() and len(line.strip()) < 35 and " " not in line.strip()
            ]
            # Filter out common non-username patterns
            username_like = [
                line
                for line in short_lines_no_space
                if not line.startswith(("http", "•", "www", "instagram"))
                and not line.isdigit()
                and len(line) >= 3
            ]
            logger.debug("Username-like lines: %d", len(username_like))
            # Home feed has many different accounts posting
            if len(username_like) >= 8:
                logger.debug("Home feed detected by username pattern")
                return True

        return False

    async def search_users(
        self,
        query: str,
        max_results: int = 25,
    ) -> dict[str, Any]:
        """Search for Instagram users.

        Note: Instagram search requires being logged in and uses client-side
        rendering. Results may be limited compared to the web interface.

        Returns:
            {url, sections: {search_results: text}}
        """
        try:
            url, search_text = await self._perform_search_interaction(query, "users")
        except Exception as e:
            logger.warning("User search failed: %s", e)
            url = f"https://www.instagram.com/explore/search/people/?q={quote_plus(query)}"
            search_text = ""

        sections: dict[str, str] = {}
        references: dict[str, list[Reference]] = {}
        section_errors: dict[str, dict[str, Any]] = {}

        if search_text and search_text != _RATE_LIMITED_MSG:
            if (
                "page isn't available" in search_text.lower()
                or "page not found" in search_text.lower()
            ):
                section_errors["search_results"] = {
                    "error_type": "page_unavailable",
                    "error_message": (
                        f"Instagram search page returned 'Page not found' for query '{query}'. "
                        f"Instagram's search requires interactive login and client-side rendering. "
                        f"Try: (1) Ensure you're logged in, (2) Use direct username lookup instead, "
                        f"(3) Search directly on instagram.com."
                    ),
                    "issue_template_path": "docs/known_issues.md",
                }
            else:
                sections["search_results"] = search_text
        elif not search_text:
            section_errors["search_results"] = {
                "error_type": "search_interaction_failed",
                "error_message": (
                    f"Could not interact with Instagram search for query '{query}'. "
                    f"Instagram's search UI requires an active browser session with valid authentication. "
                    f"Ensure you completed --login and try again."
                ),
                "issue_template_path": "docs/known_issues.md",
            }

        result: dict[str, Any] = {"url": url, "sections": sections}
        if references:
            result["references"] = references
        if section_errors:
            result["section_errors"] = section_errors
        return result

    async def search_locations(
        self,
        query: str,
        max_results: int = 25,
    ) -> dict[str, Any]:
        """Search for Instagram locations.

        Note: Instagram search requires being logged in and uses client-side
        rendering. Results may be limited compared to the web interface.

        Returns:
            {url, sections: {search_results: text}}
        """
        try:
            url, search_text = await self._perform_search_interaction(
                query, "locations"
            )
        except Exception as e:
            logger.warning("Location search failed: %s", e)
            url = f"https://www.instagram.com/explore/search/location/?q={quote_plus(query)}"
            search_text = ""

        sections: dict[str, str] = {}
        references: dict[str, list[Reference]] = {}
        section_errors: dict[str, dict[str, Any]] = {}

        if search_text and search_text != _RATE_LIMITED_MSG:
            if (
                "page isn't available" in search_text.lower()
                or "page not found" in search_text.lower()
            ):
                section_errors["search_results"] = {
                    "error_type": "page_unavailable",
                    "error_message": "Instagram location search page returned 'Page not found'. Try searching from Instagram's web interface instead.",
                    "issue_template_path": "docs/known_issues.md",
                }
            elif self._looks_like_home_feed(search_text):
                # Search returned home feed instead of location results
                section_errors["search_results"] = {
                    "error_type": "search_interaction_failed",
                    "error_message": f"Instagram search returned home feed instead of location results for '{query}'. This is a known limitation with Instagram's client-side search. Try searching directly on Instagram's web interface.",
                    "issue_template_path": "docs/known_issues.md",
                }
            else:
                sections["search_results"] = search_text
        elif not search_text:
            section_errors["search_results"] = {
                "error_type": "search_interaction_failed",
                "error_message": f"Could not retrieve location results for '{query}'. Try searching directly on Instagram's web interface.",
                "issue_template_path": "docs/known_issues.md",
            }

        result: dict[str, Any] = {"url": url, "sections": sections}
        if references:
            result["references"] = references
        if section_errors:
            result["section_errors"] = section_errors
        return result

    # ------------------------------------------------------------------
    # Direct Messages
    # ------------------------------------------------------------------

    async def scrape_dm_inbox(self, limit: int = 20) -> dict[str, Any]:
        """List recent conversations from the Instagram DM inbox.

        Returns:
            {url, sections: {inbox: text}}
        """
        url = "https://www.instagram.com/direct/inbox/"
        await self._navigate_to_page(url)
        await detect_rate_limit(self._page)
        await self._wait_for_main_text(log_context="DM inbox")
        await handle_modal_close(self._page)

        scrolls = max(1, limit // 10)
        await self._scroll_main_scrollable_region(
            position="bottom", attempts=scrolls, pause_time=0.5
        )

        raw_result = await self._extract_root_content(["main"])
        raw = raw_result["text"]
        cleaned = strip_instagram_noise(raw) if raw else ""
        references: list[Reference] = (
            build_references(raw_result["references"], "inbox") if cleaned else []
        )

        return self._single_section_result(
            url,
            "inbox",
            cleaned,
            references=references,
        )

    async def scrape_dm_conversation(
        self,
        thread_id: str | None = None,
        username: str | None = None,
    ) -> dict[str, Any]:
        """Read a specific DM conversation by thread ID or username.

        Returns:
            {url, sections: {conversation: text}}
        """
        if not thread_id and not username:
            raise InstagramScraperException(
                "Provide at least one of thread_id or username"
            )

        if thread_id:
            url = f"https://www.instagram.com/direct/t/{thread_id}/"
            await self._navigate_to_page(url)
        else:
            # Navigate to DM inbox and search for username
            await self._navigate_to_page("https://www.instagram.com/direct/inbox/")
            await detect_rate_limit(self._page)
            await handle_modal_close(self._page)
            await self._wait_for_main_text(
                log_context="DM inbox for conversation lookup"
            )

            # Try searching for the user in the inbox
            search_input = self._page.locator(_DM_SEARCH_SELECTOR)
            try:
                await search_input.first.wait_for(timeout=5000)
                await search_input.first.click()
                await self._page.keyboard.type(username or "", delay=30)
                await asyncio.sleep(1.5)
            except (PlaywrightTimeoutError, Exception):
                logger.debug("DM search input not found for conversation lookup")

            url = self._page.url

        await detect_rate_limit(self._page)
        await self._wait_for_main_text(log_context="DM conversation")
        await handle_modal_close(self._page)
        await self._scroll_main_scrollable_region(
            position="top", attempts=3, pause_time=0.5
        )

        raw_result = await self._extract_root_content(["main"])
        raw = raw_result["text"]
        cleaned = strip_instagram_noise(raw) if raw else ""
        references = (
            build_references(raw_result["references"], "conversation")
            if cleaned
            else []
        )
        return self._single_section_result(
            self._page.url,
            "conversation",
            cleaned,
            references=references,
        )

    async def send_dm(
        self,
        username: str,
        message: str,
    ) -> dict[str, Any]:
        """Send a DM to an Instagram user.

        Navigates to the user's profile, clicks Message, types and sends.

        Returns:
            {url, status, message, sent}
        """
        profile_url = f"https://www.instagram.com/{username}/"
        await self._navigate_to_page(profile_url)
        await detect_rate_limit(self._page)

        try:
            await self._page.wait_for_selector("main")
        except PlaywrightTimeoutError:
            logger.debug("Profile page did not load for %s", username)

        await handle_modal_close(self._page)

        # Click the "Message" button on the profile
        message_clicked = await self.click_button_by_text("Message", scope="main")
        if not message_clicked:
            return self._message_action_result(
                profile_url,
                "message_unavailable",
                "No Message button found on this profile. The account may not allow messages.",
            )

        await asyncio.sleep(1.0)

        # Wait for the compose area
        compose_box = self._page.locator(_DM_COMPOSE_SELECTOR)
        try:
            await compose_box.first.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeoutError:
            return self._message_action_result(
                self._page.url,
                "composer_unavailable",
                "DM composer did not appear after clicking Message.",
            )

        # Type the message
        await compose_box.first.click()
        await compose_box.first.press_sequentially(message, delay=30)
        await asyncio.sleep(0.5)

        # Click send
        send_button = self._page.locator(_DM_SEND_SELECTOR).last
        try:
            await send_button.click(timeout=5000)
        except PlaywrightTimeoutError:
            return self._message_action_result(
                self._page.url,
                "send_unavailable",
                "Send button was not available or enabled.",
            )

        return self._message_action_result(
            self._page.url,
            "sent",
            "Message sent.",
            sent=True,
        )

    # ------------------------------------------------------------------
    # Social actions
    # ------------------------------------------------------------------

    async def follow_user(self, username: str) -> dict[str, Any]:
        """Follow an Instagram user from their profile page.

        Returns:
            {url, status, message}
        """
        profile_url = f"https://www.instagram.com/{username}/"
        await self._navigate_to_page(profile_url)
        await detect_rate_limit(self._page)

        try:
            await self._page.wait_for_selector("main")
        except PlaywrightTimeoutError:
            pass

        await handle_modal_close(self._page)

        # Try clicking "Follow" button
        followed = await self.click_button_by_text("Follow", scope="main")
        if followed:
            return _action_result(
                profile_url,
                "followed",
                f"Now following @{username}.",
            )

        # Check if already following
        following = await self.click_button_by_text("Following", scope="main")
        if following:
            return _action_result(
                profile_url,
                "already_following",
                f"Already following @{username}.",
            )

        return _action_result(
            profile_url,
            "unavailable",
            f"Could not find a Follow button for @{username}.",
        )

    async def unfollow_user(self, username: str) -> dict[str, Any]:
        """Unfollow an Instagram user from their profile page.

        Returns:
            {url, status, message}
        """
        profile_url = f"https://www.instagram.com/{username}/"
        await self._navigate_to_page(profile_url)
        await detect_rate_limit(self._page)

        try:
            await self._page.wait_for_selector("main")
        except PlaywrightTimeoutError:
            pass

        await handle_modal_close(self._page)

        # Click "Following" button to open unfollow dialog
        clicked = await self.click_button_by_text("Following", scope="main")
        if not clicked:
            return _action_result(
                profile_url,
                "not_following",
                f"Not currently following @{username}.",
            )

        await asyncio.sleep(0.5)

        # Look for "Unfollow" confirmation in the dialog
        unfollowed = await self.click_button_by_text("Unfollow", scope=_DIALOG_SELECTOR)
        if unfollowed:
            return _action_result(
                profile_url,
                "unfollowed",
                f"Unfollowed @{username}.",
            )

        # Try alternate: the button might directly toggle
        await handle_modal_close(self._page)
        return _action_result(
            profile_url,
            "unfollowed",
            f"Unfollow action completed for @{username}.",
        )

    async def like_post(self, post_url: str) -> dict[str, Any]:
        """Like an Instagram post by navigating to its URL.

        Returns:
            {url, status, message}
        """
        await self._navigate_to_page(post_url)
        await detect_rate_limit(self._page)
        try:
            await self._page.wait_for_selector("main")
        except PlaywrightTimeoutError:
            pass
        await handle_modal_close(self._page)

        # Click the Like button (usually has aria-label containing "Like")
        like_button = self._page.locator(
            'button[aria-label*="Like"], svg[aria-label="Like"]'
        ).first
        try:
            await like_button.click(timeout=5000)
            return _action_result(post_url, "liked", "Post liked.")
        except PlaywrightTimeoutError:
            return _action_result(
                post_url,
                "unavailable",
                "Like button not found or post already liked.",
            )

    async def unlike_post(self, post_url: str) -> dict[str, Any]:
        """Unlike an Instagram post by navigating to its URL.

        Returns:
            {url, status, message}
        """
        await self._navigate_to_page(post_url)
        await detect_rate_limit(self._page)
        try:
            await self._page.wait_for_selector("main")
        except PlaywrightTimeoutError:
            pass
        await handle_modal_close(self._page)

        # Click the Unlike button (usually has aria-label containing "Unlike")
        unlike_button = self._page.locator(
            'button[aria-label*="Unlike"], svg[aria-label="Unlike"]'
        ).first
        try:
            await unlike_button.click(timeout=5000)
            return _action_result(post_url, "unliked", "Post unliked.")
        except PlaywrightTimeoutError:
            return _action_result(
                post_url,
                "unavailable",
                "Unlike button not found or post was not liked.",
            )

    async def save_post(
        self,
        post_url: str,
        collection: str | None = None,
    ) -> dict[str, Any]:
        """Save an Instagram post, optionally to a specific collection.

        Returns:
            {url, status, message}
        """
        await self._navigate_to_page(post_url)
        await detect_rate_limit(self._page)
        try:
            await self._page.wait_for_selector("main")
        except PlaywrightTimeoutError:
            pass
        await handle_modal_close(self._page)

        # Click the Save/Bookmark button
        save_button = self._page.locator(
            'button[aria-label*="Save"], svg[aria-label="Save"]'
        ).first
        try:
            await save_button.click(timeout=5000)
        except PlaywrightTimeoutError:
            return _action_result(
                post_url,
                "unavailable",
                "Save button not found.",
            )

        if not collection:
            return _action_result(post_url, "saved", "Post saved.")

        # If collection specified, try to select it from the dialog
        await asyncio.sleep(0.5)
        selected = await self.click_button_by_text(collection, scope=_DIALOG_SELECTOR)
        if selected:
            return _action_result(
                post_url,
                "saved",
                f"Post saved to collection '{collection}'.",
            )

        await handle_modal_close(self._page)
        return _action_result(
            post_url,
            "saved",
            f"Post saved (collection '{collection}' not found, saved to default).",
        )

    async def comment_on_post(
        self,
        post_url: str,
        comment: str,
    ) -> dict[str, Any]:
        """Comment on an Instagram post.

        Returns:
            {url, status, message}
        """
        await self._navigate_to_page(post_url)
        await detect_rate_limit(self._page)
        try:
            await self._page.wait_for_selector("main")
        except PlaywrightTimeoutError:
            pass
        await handle_modal_close(self._page)

        # Find the comment textarea
        comment_box = self._page.locator(
            'textarea[placeholder*="comment"], '
            'textarea[aria-label*="comment"], '
            "form textarea"
        ).first
        try:
            await comment_box.wait_for(state="visible", timeout=5000)
            await comment_box.click()
            await comment_box.fill(comment)
            await asyncio.sleep(0.3)
        except PlaywrightTimeoutError:
            return _action_result(
                post_url,
                "unavailable",
                "Comment input not found on this post.",
            )

        # Submit the comment (press Enter or click Post button)
        post_button = self._page.locator(
            'button[type="submit"]:not([disabled]), button:has-text("Post")'
        )
        try:
            if await post_button.count() > 0:
                await post_button.first.click(timeout=3000)
            else:
                await self._page.keyboard.press("Enter")
        except Exception:
            await self._page.keyboard.press("Enter")

        await asyncio.sleep(1.0)
        return _action_result(post_url, "commented", "Comment posted.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _extract_root_content(
        self,
        selectors: list[str],
    ) -> dict[str, Any]:
        """Extract innerText and raw anchor metadata from the first matching root."""
        result = await self._page.evaluate(
            """({ selectors }) => {
                const normalize = value => (value || '').replace(/\\s+/g, ' ').trim();
                const containerSelector = 'section, article, li, div';
                const headingSelector = 'h1, h2, h3';
                const directHeadingSelector = ':scope > h1, :scope > h2, :scope > h3';
                const MAX_HEADING_CONTAINERS = 300;
                const MAX_REFERENCE_ANCHORS = 500;

                const getHeadingText = element => {
                    if (!element) return '';

                    const heading =
                        element.matches && element.matches(headingSelector)
                            ? element
                            : element.querySelector
                              ? element.querySelector(directHeadingSelector)
                              : null;

                    return normalize(heading?.innerText || heading?.textContent);
                };

                const getPreviousHeading = node => {
                    let sibling = node?.previousElementSibling || null;
                    for (let index = 0; sibling && index < 3; index += 1) {
                        const heading = getHeadingText(sibling);
                        if (heading) {
                            return heading;
                        }
                        sibling = sibling.previousElementSibling;
                    }
                    return '';
                };

                const root = selectors
                    .map(selector => document.querySelector(selector))
                    .find(Boolean);
                const source = root ? 'root' : 'body';
                const container = root || document.body;
                const text = container ? (container.innerText || '').trim() : '';
                const headingMap = new WeakMap();

                const candidateContainers = [
                    container,
                    ...Array.from(container.querySelectorAll(containerSelector)).slice(
                        0,
                        MAX_HEADING_CONTAINERS,
                    ),
                ];
                candidateContainers.forEach(node => {
                    const ownHeading = getHeadingText(node);
                    const previousHeading = getPreviousHeading(node);
                    const heading = ownHeading || previousHeading;
                    if (heading) {
                        headingMap.set(node, heading);
                    }
                });

                const findHeading = element => {
                    let current = element.closest(containerSelector) || container;
                    for (let depth = 0; current && depth < 4; depth += 1) {
                        const heading = headingMap.get(current);
                        if (heading) {
                            return heading;
                        }
                        if (current === container) {
                            break;
                        }
                        current = current.parentElement?.closest(containerSelector) || null;
                    }
                    return '';
                };

                const references = Array.from(container.querySelectorAll('a[href]'))
                    .slice(0, MAX_REFERENCE_ANCHORS)
                    .map(anchor => {
                        const rawHref = (anchor.getAttribute('href') || '').trim();
                        if (!rawHref || rawHref === '#') {
                            return null;
                        }

                        const href = rawHref.startsWith('#')
                            ? rawHref
                            : (anchor.href || rawHref);

                        return {
                            href,
                            text: normalize(anchor.innerText || anchor.textContent),
                            aria_label: normalize(anchor.getAttribute('aria-label')),
                            title: normalize(anchor.getAttribute('title')),
                            heading: findHeading(anchor),
                            in_article: Boolean(anchor.closest('article')),
                            in_nav: Boolean(anchor.closest('nav')),
                            in_footer: Boolean(anchor.closest('footer')),
                        };
                    })
                    .filter(Boolean);

                return { source, text, references };
            }""",
            {"selectors": selectors},
        )
        return result
