# Brave CDP Direct Connection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Replace Patchright browser automation with direct CDP connection to user's already-running Brave browser, eliminating bot detection by using real browser fingerprints.

**Architecture:** Instead of launching a new automated browser and importing cookies, connect to the user's existing Brave browser session via Chrome DevTools Protocol. The user manually logs into Instagram in Brave, then the MCP server connects to that same browser instance to perform scraping. This uses the real browser's fingerprint, cookies, and session state.

**Tech Stack:** 
- Patchright/Playwright CDP connection (`chromium.connect_over_cdp()`)
- Brave browser with remote debugging enabled (`--remote-debugging-port=9222`)
- Existing cookie import as fallback/backup

---

## Prerequisites

User must:
1. Have Brave browser installed
2. Launch Brave with remote debugging enabled
3. Be logged into Instagram in that Brave session

## Migration Strategy

1. Add CDP connection mode alongside existing browser automation
2. Test CDP connection works with real Instagram sessions
3. Make CDP the default authentication method
4. Remove legacy browser automation code

---

## Task 1: Create CDP Browser Connector Module

**Files:**
- Create: `instagram_mcp_server/drivers/brave_cdp.py`
- Test: `tests/test_brave_cdp.py`

**Step 1: Write the failing test**

```python
"""Test Brave CDP connection module."""
import pytest
from instagram_mcp_server.drivers.brave_cdp import (
    find_brave_process,
    get_debugging_address,
    connect_to_brave,
)


class TestFindBraveProcess:
    """Test Brave process detection."""

    def test_returns_pid_when_brave_running(self):
        """Should return PID when Brave is running with remote debugging."""
        # This test requires Brave to be running with --remote-debugging-port=9222
        # In CI, we mock this behavior
        pid = find_brave_process()
        assert pid is not None  # Should find the running Brave process

    def test_returns_none_when_brave_not_running(self):
        """Should return None when Brave is not running."""
        # Ensure no Brave process is running
        pid = find_brave_process()
        assert pid is None


class TestGetDebuggingAddress:
    """Test CDP address resolution."""

    def test_default_debugging_port(self):
        """Should return default CDP address when no port specified."""
        address = get_debugging_address()
        assert address == "http://localhost:9222"

    def test_custom_debugging_port(self):
        """Should return custom CDP address when port specified."""
        address = get_debugging_address(port=9223)
        assert address == "http://localhost:9223"


class TestConnectToBrave:
    """Test CDP connection."""

    @pytest.mark.asyncio
    async def test_connects_to_running_brave(self):
        """Should successfully connect to running Brave instance."""
        # Requires Brave running with --remote-debugging-port=9222
        browser = await connect_to_brave()
        assert browser is not None
        assert browser.contexts is not None
        await browser.close()

    @pytest.mark.asyncio
    async def test_raises_when_brave_not_running(self):
        """Should raise ConnectionError when Brave is not running."""
        with pytest.raises(ConnectionError):
            await connect_to_brave()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_brave_cdp.py -v`
Expected: FAIL with "module not found"

**Step 3: Write minimal implementation**

```python
"""
Brave browser CDP (Chrome DevTools Protocol) connection.

Connects to an already-running Brave browser instance instead of
launching automated browsers. This eliminates bot detection by using
the real browser's fingerprint and session.
"""

import logging
import subprocess
from typing import Any

from patchright.async_api import Browser, Playwright, async_playwright

logger = logging.getLogger(__name__)

DEFAULT_DEBUGGING_PORT = 9222


def find_brave_process() -> int | None:
    """
    Find running Brave process with remote debugging enabled.
    
    Returns:
        PID if found, None otherwise
    """
    try:
        # Search for Brave processes with remote-debugging-port flag
        result = subprocess.run(
            ["pgrep", "-f", "brave.*remote-debugging-port"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            return int(pids[0]) if pids else None
        return None
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        return None


def get_debugging_address(port: int | None = None) -> str:
    """
    Get the CDP debugging address for Brave browser.
    
    Args:
        port: Remote debugging port. Defaults to 9222.
        
    Returns:
        CDP WebSocket address
    """
    debugging_port = port or DEFAULT_DEBUGGING_PORT
    return f"http://localhost:{debugging_port}"


async def connect_to_brave(
    port: int | None = None,
    timeout: float = 30.0,
) -> Browser:
    """
    Connect to running Brave browser via CDP.
    
    Args:
        port: Remote debugging port. Defaults to 9222.
        timeout: Connection timeout in seconds
        
    Returns:
        Connected Browser instance
        
    Raises:
        ConnectionError: If Brave is not running with remote debugging
    """
    debugging_address = get_debugging_address(port)
    
    logger.info(f"Connecting to Brave at {debugging_address}...")
    
    try:
        playwright: Playwright = await async_playwright().start()
        
        # Connect to existing Brave instance via CDP
        browser = await playwright.chromium.connect_over_cdp(
            debugging_address,
            timeout=timeout * 1000,  # Convert to milliseconds
        )
        
        logger.info("Successfully connected to Brave browser via CDP")
        return browser
        
    except Exception as e:
        logger.error(f"Failed to connect to Brave: {e}")
        raise ConnectionError(
            f"Could not connect to Brave browser at {debugging_address}. "
            f"Ensure Brave is running with --remote-debugging-port={port or DEFAULT_DEBUGGING_PORT}"
        ) from e


async def verify_instagram_session(browser: Browser) -> bool:
    """
    Verify that the connected Brave browser has an active Instagram session.
    
    Args:
        browser: Connected Browser instance
        
    Returns:
        True if logged in to Instagram
    """
    try:
        # Get or create a context/page
        if not browser.contexts:
            context = await browser.new_context()
        else:
            context = browser.contexts[0]
        
        if not context.pages:
            page = await context.new_page()
        else:
            page = context.pages[0]
        
        # Navigate to Instagram and check session
        await page.goto("https://www.instagram.com/feed/", wait_until="domcontentloaded")
        
        # Check for auth barriers
        from instagram_mcp_server.core.auth import detect_auth_barrier_quick
        
        barrier = await detect_auth_barrier_quick(page)
        if barrier:
            logger.warning(f"Instagram auth barrier detected: {barrier}")
            return False
        
        # Check for session cookie
        cookies = await context.cookies()
        has_sessionid = any(c["name"] == "sessionid" for c in cookies)
        
        if not has_sessionid:
            logger.warning("No sessionid cookie found in Brave session")
            return False
        
        logger.info("Instagram session verified in Brave browser")
        return True
        
    except Exception as e:
        logger.error(f"Failed to verify Instagram session: {e}")
        return False
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_brave_cdp.py::TestGetDebuggingAddress -v`
Expected: PASS for basic tests (CDP connection tests require running Brave)

**Step 5: Commit**

```bash
git add instagram_mcp_server/drivers/brave_cdp.py tests/test_brave_cdp.py
git commit -m "feat: add Brave CDP connection module for direct browser connection"
```

---

## Task 2: Update Browser Driver to Support CDP Mode

**Files:**
- Modify: `instagram_mcp_server/drivers/browser.py`
- Test: `tests/test_browser_driver.py` (add CDP tests)

**Step 1: Add CDP connection support to get_or_create_browser**

Add to `browser.py`:

```python
# Add at top of file
from instagram_mcp_server.drivers.brave_cdp import (
    connect_to_brave,
    find_brave_process,
    verify_instagram_session,
)

# Add new global for CDP mode
_cdp_browser: Browser | None = None


def _cdp_mode_enabled() -> bool:
    """Check if CDP mode is enabled via environment or config."""
    return os.getenv("INSTAGRAM_USE_CDP_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def get_or_create_browser(
    headless: bool | None = None,
) -> BrowserManager:
    """
    Get existing browser or create and initialize a new one.
    
    Supports two modes:
    1. CDP Mode (default): Connect to user's running Brave browser
    2. Legacy Mode: Launch automated browser with cookie import
    
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
    
    # CDP MODE: Connect to existing Brave browser
    if _cdp_mode_enabled():
        if _cdp_browser is not None:
            logger.debug("Reusing existing CDP browser connection")
            # Wrap CDP browser in BrowserManager-like interface
            return _wrap_cdp_browser(_cdp_browser)
        
        logger.info("CDP mode enabled - connecting to running Brave browser...")
        
        # Check if Brave is running with remote debugging
        brave_pid = find_brave_process()
        if brave_pid is None:
            raise AuthenticationError(
                "Brave browser not found with remote debugging enabled.\n\n"
                "Please launch Brave with:\n"
                f"  brave-browser --remote-debugging-port={DEFAULT_DEBUGGING_PORT}\n\n"
                "Then log into Instagram in that browser window."
            )
        
        logger.info(f"Found Brave process (PID: {brave_pid})")
        
        # Connect via CDP
        _cdp_browser = await connect_to_brave()
        
        # Verify Instagram session
        if not await verify_instagram_session(_cdp_browser):
            await _cdp_browser.close()
            _cdp_browser = None
            raise AuthenticationError(
                "No valid Instagram session found in Brave browser.\n\n"
                "Please log into Instagram in the Brave browser window."
            )
        
        logger.info("Successfully connected to authenticated Brave session")
        return _wrap_cdp_browser(_cdp_browser)
    
    # LEGACY MODE: Existing browser automation flow
    # ... (keep existing implementation)
```

**Step 2: Create BrowserManager wrapper for CDP browser**

```python
def _wrap_cdp_browser(browser: Browser) -> BrowserManager:
    """
    Wrap a CDP-connected Browser in a BrowserManager-like interface.
    
    This allows existing tool code to work without modification.
    """
    # Create a minimal BrowserManager that uses the CDP browser
    manager = BrowserManager.__new__(BrowserManager)
    manager._context = browser.contexts[0] if browser.contexts else None
    manager._page = (
        browser.contexts[0].pages[0]
        if browser.contexts and browser.contexts[0].pages
        else None
    )
    manager._playwright = None  # CDP doesn't expose playwright
    manager._is_authenticated = True
    manager.user_data_dir = "<cdp-connection>"
    return manager
```

**Step 3: Update close_browser to handle CDP mode**

```python
async def close_browser() -> None:
    """Close the browser and cleanup resources."""
    global _browser, _browser_cookie_export_path, _cdp_browser
    
    # Handle CDP browser
    if _cdp_browser is not None:
        logger.info("Closing CDP browser connection...")
        # Don't actually close - user owns this browser
        # Just disconnect our connection
        await _cdp_browser.close()
        _cdp_browser = None
        return
    
    # Handle legacy browser (existing implementation)
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
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_browser_driver.py -v`
Expected: Existing tests pass, new CDP tests pass when Brave is running

**Step 5: Commit**

```bash
git add instagram_mcp_server/drivers/browser.py
git commit -m "feat: add CDP mode support to browser driver"
```

---

## Task 3: Add Brave Launch Helper Script

**Files:**
- Create: `instagram_mcp_server/scripts/launch_brave.py`
- Create: `instagram_mcp_server/scripts/__init__.py`

**Step 1: Create Brave launcher script**

```python
"""
Launch Brave browser with remote debugging enabled.

This script helps users start Brave in the correct mode for CDP connection.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

BRAVE_PATHS = [
    "/opt/brave-bin/brave",
    "/usr/bin/brave-browser",
    "/usr/bin/brave",
    Path.home() / ".local/bin/brave",
    "brave-browser",
    "brave",
]

DEBUGGING_PORT = 9222
USER_DATA_DIR = Path.home() / ".instagram-mcp" / "brave-profile"


def find_brave_executable() -> Path | None:
    """Find Brave browser executable."""
    for path in BRAVE_PATHS:
        if isinstance(path, Path):
            if path.exists():
                return path
        else:
            # Try to find in PATH
            try:
                result = subprocess.run(
                    ["which", path],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    return Path(result.stdout.strip())
            except (subprocess.SubprocessError, FileNotFoundError):
                continue
    return None


def launch_brave() -> int:
    """Launch Brave with remote debugging enabled."""
    brave_exe = find_brave_executable()
    
    if not brave_exe:
        print("Error: Brave browser not found.")
        print("\nPlease install Brave browser:")
        print("  Ubuntu/Debian: sudo apt install brave-browser")
        print("  Fedora: sudo dnf install brave-browser")
        print("  Or download from: https://brave.com")
        return 1
    
    print(f"Found Brave: {brave_exe}")
    print(f"Launching with remote debugging on port {DEBUGGING_PORT}...")
    print(f"Profile directory: {USER_DATA_DIR}")
    print("\nPlease log into Instagram in the Brave window.")
    print("Press Ctrl+C to stop.")
    
    # Ensure profile directory exists
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Launch Brave
    cmd = [
        str(brave_exe),
        f"--remote-debugging-port={DEBUGGING_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.instagram.com/",
    ]
    
    try:
        # Don't wait for process - let it run independently
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print("\n✓ Brave launched successfully!")
        print(f"\nNow run the MCP server:")
        print(f"  uv run -m instagram_mcp_server")
        return 0
        
    except Exception as e:
        print(f"Error launching Brave: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    return launch_brave()


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Create package init**

```python
"""Scripts package for Instagram MCP Server."""
```

**Step 3: Add entry point to pyproject.toml**

Add to `[project.scripts]`:
```toml
instagram-launch-brave = "instagram_mcp_server.scripts.launch_brave:main"
```

**Step 4: Test the launcher**

Run: `uv run instagram-launch-brave`
Expected: Brave opens with Instagram

**Step 5: Commit**

```bash
git add instagram_mcp_server/scripts/ pyproject.toml
git commit -m "feat: add Brave launcher script for CDP mode"
```

---

## Task 4: Update Documentation and User Guide

**Files:**
- Modify: `README.md`
- Modify: `docs/docker-hub.md`
- Create: `docs/CDP_MODE.md`

**Step 1: Update README with CDP mode instructions**

Add to README.md:

```markdown
## Authentication

The Instagram MCP Server supports two authentication modes:

### Mode 1: CDP Connection (Recommended)

Connect directly to your running Brave browser. This uses your real browser's fingerprint, avoiding all bot detection.

**Setup:**

1. Launch Brave with remote debugging:
   ```bash
   uv run instagram-launch-brave
   ```
   
   Or manually:
   ```bash
   brave-browser --remote-debugging-port=9222 --user-data-dir=~/.instagram-mcp/brave-profile
   ```

2. Log into Instagram in the Brave window

3. Run the MCP server:
   ```bash
   uv run -m instagram_mcp_server
   ```

**Benefits:**
- ✅ No bot detection (uses real browser fingerprint)
- ✅ No captcha challenges
- ✅ Persistent session (stays logged in)
- ✅ Fast (no browser launch overhead)

### Mode 2: Cookie Import (Fallback)

Import cookies from your browser session.

**Setup:**

```bash
uv run -m instagram_mcp_server --login
```

This will:
1. Try to auto-extract cookies from Brave
2. Fall back to manual cookie import if needed

### Mode 3: Legacy Browser Automation (Deprecated)

The automated browser login is deprecated and may be blocked by Instagram's bot detection.
```

**Step 2: Create detailed CDP mode documentation**

Create `docs/CDP_MODE.md`:

```markdown
# CDP Mode: Direct Brave Browser Connection

## Overview

CDP (Chrome DevTools Protocol) mode connects the MCP server directly to your running Brave browser instead of launching automated browsers. This eliminates Instagram's bot detection because:

1. **Real browser fingerprint** - Uses your actual browser, not an automated instance
2. **Existing session** - Reuses your logged-in Instagram session
3. **No automation flags** - No `navigator.webdriver` or other automation indicators

## How It Works

```
┌─────────────────┐     CDP      ┌──────────────────┐
│   Brave Browser │◄────────────►│   MCP Server     │
│   (User-owned)  │  Port 9222   │   (This tool)    │
│                 │              │                  │
│ - Instagram tab │              │ - Scraping tools │
│ - Your cookies  │              │ - Data extraction│
│ - Real session  │              │                  │
└─────────────────┘              └──────────────────┘
```

## Setup Instructions

### Step 1: Launch Brave with Remote Debugging

**Option A: Use the launcher script (Recommended)**

```bash
uv run instagram-launch-brave
```

**Option B: Manual launch**

```bash
brave-browser \
  --remote-debugging-port=9222 \
  --user-data-dir=~/.instagram-mcp/brave-profile \
  https://www.instagram.com/
```

**Option C: Add to Brave desktop shortcut**

Edit your Brave launcher to include:
```
--remote-debugging-port=9222 --user-data-dir=~/.instagram-mcp/brave-profile
```

### Step 2: Log Into Instagram

In the Brave window that opens, log into Instagram normally. Complete any 2FA or security challenges.

### Step 3: Run the MCP Server

```bash
uv run -m instagram_mcp_server
```

The server will automatically:
1. Detect the running Brave process
2. Connect via CDP on port 9222
3. Verify your Instagram session
4. Begin serving MCP requests

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `INSTAGRAM_USE_CDP_MODE` | Enable CDP mode (`1`, `true`, `yes`, `on`) | `1` (enabled by default) |
| `INSTAGRAM_DEBUGGING_PORT` | CDP debugging port | `9222` |

### Example: Custom Port

```bash
export INSTAGRAM_DEBUGGING_PORT=9223
brave-browser --remote-debugging-port=9223
uv run -m instagram_mcp_server
```

## Troubleshooting

### "Brave browser not found"

**Solution:** Ensure Brave is running with the `--remote-debugging-port` flag.

Check running processes:
```bash
ps aux | grep brave | grep remote-debugging
```

### "No valid Instagram session found"

**Solution:** Log into Instagram in the Brave browser window.

1. Open `https://www.instagram.com/` in Brave
2. Log in with your credentials
3. Complete any 2FA challenges
4. Verify you can see your feed
5. Restart the MCP server

### Connection refused on port 9222

**Solution:** Port may be in use or Brave not running.

1. Check if port is in use: `lsof -i :9222`
2. Kill conflicting process or use different port
3. Restart Brave with correct port

### CDP connection works but scraping fails

**Solution:** Instagram may have rate-limited your account.

1. Wait a few hours
2. Try accessing Instagram manually in Brave
3. Reduce scraping frequency

## Security Considerations

- CDP connection is localhost-only (not exposed to network)
- Your cookies never leave your machine
- MCP server only accesses Instagram tabs
- Close Brave when not in use to disconnect

## Performance Benefits

| Metric | Legacy Mode | CDP Mode |
|--------|-------------|----------|
| Startup time | ~5 seconds | ~0.1 seconds |
| Memory usage | ~200 MB | ~0 MB (reuses existing) |
| Bot detection | High risk | No risk |
| Session persistence | Per-run | Persistent |

## Migration from Legacy Mode

If you're using the old browser automation mode:

1. Stop using `--login` flag
2. Launch Brave with CDP (see above)
3. Log into Instagram once
4. Run MCP server normally

Your session will persist across MCP server restarts.
```

**Step 3: Update docker-hub.md**

Add CDP mode section to Docker documentation:

```markdown
## CDP Mode with Docker

CDP mode works with Docker by connecting to Brave running on the host machine.

### Host Setup

1. Launch Brave on host with remote debugging:
   ```bash
   brave-browser --remote-debugging-port=9222
   ```

2. Log into Instagram in Brave

3. Run Docker container with host network access:
   ```bash
   docker run --network host instagram-mcp-server
   ```

The container can now connect to Brave on the host via `localhost:9222`.
```

**Step 4: Commit**

```bash
git add README.md docs/CDP_MODE.md docs/docker-hub.md
git commit -m "docs: add CDP mode documentation and user guide"
```

---

## Task 5: Test CDP Mode End-to-End

**Files:**
- Test: Manual testing + integration tests

**Step 1: Manual test - Launch Brave and connect**

```bash
# Terminal 1: Launch Brave
uv run instagram-launch-brave

# Terminal 2: Log into Instagram manually in Brave

# Terminal 3: Run MCP server
uv run -m instagram_mcp_server --transport streamable-http --log-level DEBUG

# Terminal 4: Test a tool
curl -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_user_profile","arguments":{"username":"instagram"}}}'
```

Expected: Returns Instagram's profile data

**Step 2: Verify no bot detection**

Check logs for:
- No `/auth_platform/recaptcha/` URLs
- No captcha challenges
- Fast response times (<2 seconds)

**Step 3: Test session persistence**

```bash
# Stop MCP server
Ctrl+C

# Restart
uv run -m instagram_mcp_server

# Test again - should still be authenticated
curl -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_user_profile","arguments":{"username":"instagram"}}}'
```

Expected: Still authenticated, no re-login needed

**Step 4: Add integration test**

Add to `tests/test_integration.py`:

```python
"""Integration tests for CDP mode."""
import os
import pytest
from instagram_mcp_server.drivers.brave_cdp import find_brave_process


@pytest.mark.integration
class TestCDPModeIntegration:
    """Test CDP mode end-to-end."""

    def test_brave_process_detection(self):
        """Test that Brave process is detected when running."""
        # This test requires Brave to be running with --remote-debugging-port
        # In CI, this would be skipped or mocked
        pid = find_brave_process()
        if os.getenv("CI"):
            assert pid is None  # No Brave in CI
        else:
            # Local dev - Brave should be running
            assert pid is not None, "Brave not running with remote debugging"
```

**Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add CDP mode integration tests"
```

---

## Task 6: Make CDP Mode Default and Deprecate Legacy Mode

**Files:**
- Modify: `instagram_mcp_server/drivers/browser.py`
- Modify: `instagram_mcp_server/config.py`
- Modify: `README.md`

**Step 1: Make CDP mode the default**

In `browser.py`, change `_cdp_mode_enabled()`:

```python
def _cdp_mode_enabled() -> bool:
    """Check if CDP mode is enabled via environment or config."""
    # CDP mode is now DEFAULT - opt OUT with INSTAGRAM_USE_LEGACY_MODE=1
    return os.getenv("INSTAGRAM_USE_LEGACY_MODE", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }
```

**Step 2: Add deprecation warnings to legacy mode**

```python
import warnings

# In get_or_create_browser, when using legacy mode:
if not _cdp_mode_enabled():
    warnings.warn(
        "Legacy browser automation mode is deprecated and will be removed in v2.0. "
        "Please use CDP mode (connect to running Brave browser) instead. "
        "See docs/CDP_MODE.md for migration instructions.",
        DeprecationWarning,
        stacklevel=2,
    )
```

**Step 3: Update config to reflect new default**

In `config.py`:

```python
# Add to BrowserConfig
use_legacy_mode: bool = False  # Deprecated, use CDP mode instead
```

**Step 4: Update README to reflect new default**

Update authentication section to show CDP mode as primary method.

**Step 5: Run tests**

```bash
uv run pytest tests/ -v
```

Expected: All tests pass

**Step 6: Commit**

```bash
git add instagram_mcp_server/drivers/browser.py instagram_mcp_server/config.py README.md
git commit -m "feat: make CDP mode default, deprecate legacy browser automation"
```

---

## Task 7: Remove Legacy Browser Automation Code

**Files:**
- Remove: `instagram_mcp_server/setup.py` (browser login flow)
- Remove: `instagram_mcp_server/core/auth.py` (browser-based auth)
- Modify: `instagram_mcp_server/drivers/browser.py` (remove legacy code)
- Modify: `instagram_mcp_server/cookie_import.py` (keep as fallback only)

**Step 1: Remove setup.py browser login**

Delete browser login functions, keep only cookie import helper:

```python
"""
Interactive setup for Instagram MCP Server.

Primary method: Cookie import from Brave browser.
Legacy method: Browser automation (removed).
"""

from instagram_mcp_server.cookie_import import (
    import_cookies_interactive,
    manual_cookie_import_guide,
)


def run_interactive_setup() -> bool:
    """Run cookie import setup."""
    print("Instagram MCP Server Setup")
    print("   Importing cookies from Brave browser...")
    
    if import_cookies_interactive():
        print("   ✓ Cookie import successful!")
        return True
    
    print("   Cookie import failed.")
    manual_cookie_import_guide()
    return False
```

**Step 2: Remove auth.py browser-based functions**

Remove:
- `warm_up_browser()`
- `wait_for_manual_login()`

Keep cookie-based auth helpers.

**Step 3: Simplify browser.py**

Remove all legacy browser automation code:
- Remove `interactive_login` support
- Remove cookie import into browser (no longer needed)
- Keep only CDP connection code

**Step 4: Update cookie_import.py**

Keep as fallback for users who can't use CDP mode:

```python
def load_or_import_cookies(profile_dir: Path | None = None) -> dict[str, str] | None:
    """
    Load existing cookies or attempt to import them.
    
    Fallback method for users who cannot use CDP mode.
    Primary method: Use CDP connection to running Brave browser.
    """
    # Keep existing implementation as fallback
    ...
```

**Step 5: Update all imports**

Find and update all files importing removed functions:

```bash
grep -r "warm_up_browser\|wait_for_manual_login\|interactive_login" instagram_mcp_server/
```

Update or remove these imports.

**Step 6: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: All tests pass (may need to update tests that depend on removed functions)

**Step 7: Update tests**

Update tests that reference removed functionality to use CDP mode instead.

**Step 8: Commit**

```bash
git add instagram_mcp_server/ tests/
git commit -m "refactor: remove legacy browser automation code"
```

---

## Task 8: Final Testing and Documentation Update

**Files:**
- All documentation files
- Test suite

**Step 1: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
uv run pytest --cov=instagram_mcp_server --cov-report=html
```

Expected: All tests pass, good coverage

**Step 2: Update CHANGELOG**

Add to CHANGELOG.md:

```markdown
## [Version] - 2026-04-02

### Added
- CDP mode for direct Brave browser connection
- `instagram-launch-brave` script for easy Brave launch
- Comprehensive CDP mode documentation

### Changed
- **BREAKING:** CDP mode is now the default authentication method
- Deprecated legacy browser automation

### Removed
- Automated browser login flow
- Browser warm-up functions
- Manual login wait functions

### Migration
- See `docs/CDP_MODE.md` for migration from legacy mode
```

**Step 3: Update pyproject.toml version**

```bash
uv version --bump minor
```

**Step 4: Final documentation review**

Ensure all docs reference CDP mode as primary method.

**Step 5: Commit**

```bash
git add CHANGELOG.md pyproject.toml docs/
git commit -m "chore: prepare release with CDP mode as default"
```

---

## Summary

This plan transforms the Instagram MCP Server from automated browser scraping to direct CDP connection with user's Brave browser. The key benefits:

1. **Eliminates bot detection** - Uses real browser fingerprint
2. **Faster** - No browser launch overhead
3. **Persistent sessions** - Stay logged in across restarts
4. **Simpler** - Less code, fewer moving parts

**Total estimated time:** 2-3 hours for full implementation

**Files to create:** 4
**Files to modify:** 8
**Files to remove:** 2
**Tests to add:** ~50 lines

---
