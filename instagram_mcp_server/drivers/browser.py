"""
Patchright browser management for Instagram scraping.

Provides async browser lifecycle management using BrowserManager with persistent
context. Implements a singleton pattern for browser reuse across tool calls with
automatic profile persistence.

Supports two modes:
1. CDP Mode (default): Connect to user's running Brave browser via CDP
2. Legacy Mode: Launch automated browser with cookie import (deprecated)
"""

import logging
import os
import warnings
from pathlib import Path

from patchright.async_api import Browser as CDPBrowser

from instagram_mcp_server.common_utils import secure_mkdir
from instagram_mcp_server.core import (
    AuthenticationError,
    BrowserManager,
    detect_auth_barrier_quick,
    detect_rate_limit,
    is_logged_in,
)

from instagram_mcp_server.common_utils import utcnow_iso
from instagram_mcp_server.config import get_config
from instagram_mcp_server.debug_trace import record_page_trace
from instagram_mcp_server.debug_utils import stabilize_navigation
from instagram_mcp_server.drivers.brave_cdp import (
    connect_to_brave,
    find_brave_process,
    verify_instagram_session,
)
from instagram_mcp_server.session_state import (
    SourceState,
    clear_runtime_profile,
    get_runtime_id,
    get_source_profile_dir,
    load_runtime_state,
    load_source_state,
    portable_cookie_path,
    profile_exists as session_profile_exists,
    runtime_profile_dir,
    runtime_storage_state_path,
    write_runtime_state,
)

logger = logging.getLogger(__name__)


# Default persistent profile directory
DEFAULT_PROFILE_DIR = Path.home() / ".instagram-mcp" / "profile"
# Global browser instance (singleton)
_browser: BrowserManager | None = None
_browser_cookie_export_path: Path | None = None
_headless: bool = True
_cdp_browser: CDPBrowser | None = None


def _debug_skip_checkpoint_restart() -> bool:
    """Return whether to keep the fresh bridged browser alive for this run."""
    return os.getenv("INSTAGRAM_DEBUG_SKIP_CHECKPOINT_RESTART", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _debug_bridge_every_startup() -> bool:
    """Return whether to force a fresh bridge on every foreign-runtime startup."""
    return os.getenv("INSTAGRAM_DEBUG_BRIDGE_EVERY_STARTUP", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def experimental_persist_derived_runtime() -> bool:
    """Return whether Docker-style foreign runtimes should reuse derived profiles."""
    return os.getenv(
        "INSTAGRAM_EXPERIMENTAL_PERSIST_DERIVED_SESSION", ""
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _apply_browser_settings(browser: BrowserManager) -> None:
    """Apply configuration settings to browser instance."""
    config = get_config()
    browser.page.set_default_timeout(config.browser.default_timeout)


async def _log_feed_failure_context(
    browser: BrowserManager,
    reason: str,
    exc: Exception | None = None,
) -> None:
    """Log the page state when /feed/ validation fails."""
    page = browser.page

    try:
        title = await page.title()
    except Exception:
        title = ""

    try:
        body_text = await page.evaluate("() => document.body?.innerText || ''")
    except Exception:
        body_text = ""

    if not isinstance(body_text, str):
        body_text = ""

    logger.warning(
        "Feed auth check failed on %s: %s title=%r body_marker=%r",
        page.url,
        reason,
        title,
        " ".join(body_text.split())[:200],
        exc_info=exc,
    )


async def _feed_auth_succeeds(
    browser: BrowserManager,
) -> bool:
    """Validate that /feed/ loads without an auth barrier."""
    try:
        await browser.page.goto(
            "https://www.instagram.com/feed/",
            wait_until="domcontentloaded",
        )
        await stabilize_navigation("feed navigation", logger)
        await record_page_trace(
            browser.page,
            "feed-after-goto",
        )
        barrier = await detect_auth_barrier_quick(browser.page)
        if barrier is not None:
            await record_page_trace(
                browser.page,
                "feed-auth-barrier",
                extra={"barrier": barrier},
            )
            await _log_feed_failure_context(browser, barrier)
            return False
        return True
    except Exception as exc:
        await record_page_trace(
            browser.page,
            "feed-navigation-error",
            extra={"error": f"{type(exc).__name__}: {exc}"},
        )
        await _log_feed_failure_context(browser, str(exc), exc)
        return False


def _cdp_mode_enabled() -> bool:
    """Check if CDP mode is enabled via environment or config. Default is True."""
    value = os.getenv("INSTAGRAM_USE_CDP_MODE", "1").strip().lower()
    return value not in {
        "0",
        "false",
        "no",
        "off",
    }


def _wrap_cdp_browser(browser: CDPBrowser) -> BrowserManager:
    """
    Wrap a CDP-connected Browser in a BrowserManager-like interface.

    This allows existing tool code to work without modification.
    """
    manager = BrowserManager.__new__(BrowserManager)
    manager._context = browser.contexts[0] if browser.contexts else None
    manager._page = (
        browser.contexts[0].pages[0]
        if browser.contexts and browser.contexts[0].pages
        else None
    )
    manager._playwright = None
    manager._is_authenticated = True
    manager.user_data_dir = "<cdp-connection>"
    return manager


def _launch_options() -> tuple[dict[str, str], dict[str, int]]:
    config = get_config()
    viewport = {
        "width": config.browser.viewport_width,
        "height": config.browser.viewport_height,
    }
    launch_options: dict[str, str] = {}
    if config.browser.chrome_path:
        launch_options["executable_path"] = config.browser.chrome_path
        logger.info("Using custom Chrome path: %s", config.browser.chrome_path)
    return launch_options, viewport


def _make_browser(
    profile_dir: Path,
    *,
    launch_options: dict[str, str],
    viewport: dict[str, int],
) -> BrowserManager:
    config = get_config()
    return BrowserManager(
        user_data_dir=profile_dir,
        headless=_headless,
        slow_mo=config.browser.slow_mo,
        user_agent=config.browser.user_agent,
        viewport=viewport,
        **launch_options,
    )


async def _authenticate_existing_profile(
    profile_dir: Path,
    *,
    launch_options: dict[str, str],
    viewport: dict[str, int],
) -> BrowserManager:
    browser = _make_browser(
        profile_dir, launch_options=launch_options, viewport=viewport
    )
    try:
        await browser.start()
        if not await _feed_auth_succeeds(browser):
            raise AuthenticationError(
                f"Stored runtime profile is invalid: {profile_dir}. Run with --login to refresh the source session."
            )
        browser.is_authenticated = True
        return browser
    except Exception:
        await browser.close()
        raise


async def _bridge_runtime_profile(
    profile_dir: Path,
    *,
    cookie_path: Path,
    source_state: SourceState,
    runtime_id: str,
    launch_options: dict[str, str],
    viewport: dict[str, int],
    persist_runtime: bool,
) -> BrowserManager:
    source_profile_dir = get_source_profile_dir()
    bridge_started_at = utcnow_iso()
    clear_runtime_profile(runtime_id, source_profile_dir)
    secure_mkdir(profile_dir.parent)
    storage_state_path = runtime_storage_state_path(runtime_id, source_profile_dir)
    browser = _make_browser(
        profile_dir, launch_options=launch_options, viewport=viewport
    )
    try:
        await browser.start()
        await record_page_trace(
            browser.page,
            "bridge-browser-started",
            extra={"profile_dir": str(profile_dir)},
        )
        await browser.page.goto(
            "https://www.instagram.com/feed/", wait_until="domcontentloaded"
        )
        await stabilize_navigation("pre-import feed navigation", logger)
        await record_page_trace(browser.page, "bridge-after-pre-import-feed")
        if not await browser.import_cookies(cookie_path):
            raise AuthenticationError(
                "Portable authentication could not be imported. Run with --login to create a fresh source session."
            )
        await stabilize_navigation("bridge cookie import", logger)
        await record_page_trace(
            browser.page,
            "bridge-after-cookie-import",
            extra={"cookie_path": str(cookie_path)},
        )
        if not await _feed_auth_succeeds(browser):
            raise AuthenticationError(
                "No authentication found. Run with --login to create a profile."
            )
        await stabilize_navigation("post-import feed validation", logger)
        await record_page_trace(browser.page, "bridge-after-feed-validation")
        if not persist_runtime:
            logger.info(
                "Foreign runtime %s authenticated via fresh bridge "
                "(derived runtime persistence disabled)",
                runtime_id,
            )
            browser.is_authenticated = True
            return browser
        if _debug_skip_checkpoint_restart():
            logger.warning(
                "Skipping checkpoint restart for derived runtime profile %s "
                "(INSTAGRAM_DEBUG_SKIP_CHECKPOINT_RESTART enabled)",
                profile_dir,
            )
            browser.is_authenticated = True
            return browser
        if not await browser.export_storage_state(storage_state_path, indexed_db=True):
            raise AuthenticationError(
                "Derived runtime session could not be checkpointed. Run with --login to create a fresh source session."
            )
        await stabilize_navigation("runtime storage-state export", logger)
        logger.info("Checkpoint-restarting derived runtime profile %s", profile_dir)
        await browser.close()
        reopened = _make_browser(
            profile_dir,
            launch_options=launch_options,
            viewport=viewport,
        )
        try:
            await reopened.start()
            await stabilize_navigation("derived profile reopen", logger)
            await record_page_trace(
                reopened.page,
                "bridge-after-profile-reopen",
                extra={"profile_dir": str(profile_dir)},
            )
            if not await _feed_auth_succeeds(reopened):
                logger.warning(
                    "Stored derived runtime profile failed post-commit validation"
                )
                raise AuthenticationError(
                    "Derived runtime validation failed; no automatic re-bridge will be attempted. Run with --login to create a fresh source session."
                )
            await stabilize_navigation("post-reopen feed validation", logger)
            await record_page_trace(reopened.page, "bridge-after-reopen-validation")
            write_runtime_state(
                runtime_id,
                source_state,
                storage_state_path,
                source_profile_dir,
                created_at=bridge_started_at,
            )
            logger.info("Derived runtime profile committed for %s", runtime_id)
            reopened.is_authenticated = True
            return reopened
        except Exception:
            await reopened.close()
            raise
    except Exception:
        await browser.close()
        clear_runtime_profile(runtime_id, source_profile_dir)
        raise


async def get_or_create_browser(
    headless: bool | None = None,
) -> BrowserManager:
    """
    Get existing browser or create and initialize a new one.

    Supports two modes:
    1. CDP Mode (default): Connect to user's running Brave browser via CDP
    2. Legacy Mode: Launch automated browser with cookie import (deprecated)

    Uses a singleton pattern to reuse the browser across tool calls.
    Uses persistent context for automatic profile persistence.

    Args:
        headless: Run browser in headless mode. Defaults to config value.

    Returns:
        Initialized BrowserManager instance

    Raises:
        AuthenticationError: If no valid authentication found
    """
    global _browser, _browser_cookie_export_path, _headless, _cdp_browser

    if headless is not None:
        _headless = headless

    # CDP MODE: Connect to existing Brave browser (DEFAULT)
    if _cdp_mode_enabled():
        if _cdp_browser is not None:
            logger.debug("Reusing existing CDP browser connection")
            return _wrap_cdp_browser(_cdp_browser)

        logger.info("CDP mode enabled - connecting to running Brave browser...")

        brave_pid = find_brave_process()
        if brave_pid is None:
            raise AuthenticationError(
                "Brave browser not found with remote debugging enabled.\n\n"
                "Please launch Brave with:\n"
                "  uv run instagram-launch-brave\n\n"
                "Or manually:\n"
                "  brave-browser --remote-debugging-port=9222\n\n"
                "Then log into Instagram in that browser window."
            )

        logger.info(f"Found Brave process (PID: {brave_pid})")

        _cdp_browser = await connect_to_brave()

        if not await verify_instagram_session(_cdp_browser):
            await _cdp_browser.close()
            _cdp_browser = None
            raise AuthenticationError(
                "No valid Instagram session found in Brave browser.\n\n"
                "Please log into Instagram in the Brave browser window."
            )

        logger.info("Successfully connected to authenticated Brave session")
        return _wrap_cdp_browser(_cdp_browser)

    # LEGACY MODE: Existing browser automation flow (DEPRECATED)
    warnings.warn(
        "Legacy browser automation mode is deprecated and will be removed in v2.0. "
        "Please use CDP mode (connect to running Brave browser) instead. "
        "See docs/CDP_MODE.md for migration instructions.",
        DeprecationWarning,
        stacklevel=2,
    )

    if _browser is not None:
        return _browser

    launch_options, viewport = _launch_options()
    source_profile_dir = get_profile_dir()
    cookie_path = portable_cookie_path(source_profile_dir)
    source_state = load_source_state(source_profile_dir)
    if (
        not source_state
        or not profile_exists(source_profile_dir)
        or not cookie_path.exists()
    ):
        raise AuthenticationError(
            "No source authentication found. Run with --login to create a profile."
        )

    current_runtime_id = get_runtime_id()

    if current_runtime_id == source_state.source_runtime_id:
        logger.info(
            "Using source profile for runtime %s (profile=%s)",
            current_runtime_id,
            source_profile_dir,
        )
        browser = await _authenticate_existing_profile(
            source_profile_dir,
            launch_options=launch_options,
            viewport=viewport,
        )
        _apply_browser_settings(browser)
        _browser = browser
        _browser_cookie_export_path = cookie_path
        return _browser

    persist_runtime = experimental_persist_derived_runtime()
    force_bridge = _debug_bridge_every_startup()

    if not persist_runtime:
        logger.info(
            "Using fresh bridge for foreign runtime %s "
            "(derived runtime persistence disabled by default)",
            current_runtime_id,
        )
        browser = await _bridge_runtime_profile(
            runtime_profile_dir(current_runtime_id, source_profile_dir),
            cookie_path=cookie_path,
            source_state=source_state,
            runtime_id=current_runtime_id,
            launch_options=launch_options,
            viewport=viewport,
            persist_runtime=False,
        )
        _apply_browser_settings(browser)
        _browser = browser
        _browser_cookie_export_path = None
        return _browser

    runtime_state = load_runtime_state(current_runtime_id, source_profile_dir)
    derived_profile_dir = runtime_profile_dir(current_runtime_id, source_profile_dir)
    storage_state_path = runtime_storage_state_path(
        current_runtime_id, source_profile_dir
    )
    generation_matches = (
        runtime_state is not None
        and runtime_state.source_login_generation == source_state.login_generation
    )
    if (
        not force_bridge
        and generation_matches
        and profile_exists(derived_profile_dir)
        and storage_state_path.exists()
    ):
        logger.info(
            "Using derived runtime profile for %s (profile=%s)",
            current_runtime_id,
            derived_profile_dir,
        )
        try:
            browser = await _authenticate_existing_profile(
                derived_profile_dir,
                launch_options=launch_options,
                viewport=viewport,
            )
            _apply_browser_settings(browser)
            _browser = browser
            _browser_cookie_export_path = None
            return _browser
        except AuthenticationError:
            logger.warning(
                "Derived runtime profile auth failed for %s; re-bridging from source cookies",
                current_runtime_id,
            )

    if force_bridge:
        logger.warning(
            "Forcing a fresh bridge for %s on every startup "
            "(INSTAGRAM_DEBUG_BRIDGE_EVERY_STARTUP enabled)",
            current_runtime_id,
        )
    logger.info(
        "Deriving runtime profile for %s from source generation %s",
        current_runtime_id,
        source_state.login_generation,
    )
    browser = await _bridge_runtime_profile(
        derived_profile_dir,
        cookie_path=cookie_path,
        source_state=source_state,
        runtime_id=current_runtime_id,
        launch_options=launch_options,
        viewport=viewport,
        persist_runtime=True,
    )
    _apply_browser_settings(browser)
    _browser = browser
    _browser_cookie_export_path = None
    return _browser


async def close_browser() -> None:
    """Close the browser and cleanup resources."""
    global _browser, _browser_cookie_export_path, _cdp_browser

    # Handle CDP browser - just disconnect, don't close user's browser
    if _cdp_browser is not None:
        logger.info("Closing CDP browser connection (user's browser remains open)...")
        await _cdp_browser.close()
        _cdp_browser = None
        return

    # Handle legacy browser
    browser = _browser
    cookie_export_path = _browser_cookie_export_path
    _browser = None
    _browser_cookie_export_path = None

    if browser is None:
        return

    logger.info("Closing browser...")
    if cookie_export_path is not None:
        try:
            await browser.export_cookies(cookie_export_path)
        except Exception:
            logger.debug("Cookie export on close skipped", exc_info=True)
    await browser.close()
    logger.info("Browser closed")


def get_profile_dir() -> Path:
    """Get the resolved profile directory from config."""
    return get_source_profile_dir()


def profile_exists(profile_dir: Path | None = None) -> bool:
    """Check if a persistent browser profile exists and is non-empty."""
    return session_profile_exists(profile_dir or get_profile_dir())


def set_headless(headless: bool) -> None:
    """Set headless mode for future browser creation."""
    global _headless
    _headless = headless


async def validate_session() -> bool:
    """
    Check whether startup authentication has already succeeded for this browser.

    Mid-session expiry is detected during real Instagram navigations and scraper
    auth checks rather than via a fresh login probe on every tool call.

    Returns:
        True if startup authentication succeeded for the current browser
    """
    browser = await get_or_create_browser()
    if browser.is_authenticated:
        return True
    return await is_logged_in(browser.page)


async def ensure_authenticated() -> None:
    """
    Confirm that the shared browser completed startup authentication.

    Raises:
        AuthenticationError: If no authenticated browser session is available
    """
    if not await validate_session():
        raise AuthenticationError("Session expired or invalid.")


async def check_rate_limit() -> None:
    """
    Proactively check for rate limiting.

    Should be called after navigation to detect if Instagram is blocking requests.

    Raises:
        RateLimitError: If rate limiting is detected
    """
    browser = await get_or_create_browser()
    await detect_rate_limit(browser.page)


def reset_browser_for_testing() -> None:
    """Reset global browser state for test isolation."""
    global _browser, _browser_cookie_export_path, _headless, _cdp_browser
    _browser = None
    _browser_cookie_export_path = None
    _cdp_browser = None
    _headless = True
