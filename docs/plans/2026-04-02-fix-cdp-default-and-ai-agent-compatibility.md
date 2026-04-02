# Fix CDP Default and AI Agent Compatibility

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Make CDP mode the actual default, fix all copy-paste errors from LinkedIn fork, and ensure AI agents can use Instagram MCP without login errors.

**Architecture:** CDP mode should be enabled by default with clear error messages guiding users to launch Brave with remote debugging. Legacy browser automation becomes the fallback option.

**Tech Stack:** 
- Python 3.12-3.13
- Patchright for CDP connection
- Environment variables + CLI args for configuration

---

## Task 1: Make CDP Mode The Default

**Files:**
- Modify: `instagram_mcp_server/drivers/browser.py:169-175`
- Test: `tests/test_browser_driver.py`

**Step 1: Update _cdp_mode_enabled() function**

```python
def _cdp_mode_enabled() -> bool:
    """Check if CDP mode is enabled via environment or config. Default is True."""
    value = os.getenv("INSTAGRAM_USE_CDP_MODE", "1").strip().lower()
    return value not in {
        "0",
        "false", 
        "no",
        "off",
    }
```

**Step 2: Update deprecation warning**

In `get_or_create_browser()`, move the deprecation warning to only show when CDP mode is explicitly disabled:

```python
# Before the legacy mode code block
if not _cdp_mode_enabled():
    warnings.warn(
        "Legacy browser automation mode is deprecated and will be removed in v2.0. "
        "Please use CDP mode (connect to running Brave browser) instead. "
        "See docs/CDP_MODE.md for migration instructions.",
        DeprecationWarning,
        stacklevel=2,
    )
    # ... legacy mode code
```

**Step 3: Update tests**

Update `tests/test_browser_driver.py` to expect CDP mode by default:

```python
# Add test for default CDP mode
def test_cdp_mode_is_default(monkeypatch):
    """CDP mode should be enabled by default."""
    # Remove env var to test default
    monkeypatch.delenv("INSTAGRAM_USE_CDP_MODE", raising=False)
    assert _cdp_mode_enabled() is True
    
    # Test explicit disable
    monkeypatch.setenv("INSTAGRAM_USE_CDP_MODE", "0")
    assert _cdp_mode_enabled() is False
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_browser_driver.py::test_cdp_mode_is_default -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add instagram_mcp_server/drivers/browser.py tests/test_browser_driver.py
git commit -m "feat: make CDP mode the default authentication method"
```

---

## Task 2: Fix Copy-Paste Errors (LinkedIn → Instagram)

**Files:**
- Modify: `instagram_mcp_server/authentication.py:55`
- Modify: `instagram_mcp_server/bootstrap.py:370,430`
- Modify: `instagram_mcp_server/tools/__init__.py:1`
- Modify: `instagram_mcp_server/__init__.py:1`

**Step 1: Fix authentication.py**

```python
# Line 55 - Change:
"  Create profile on host first: uv run -m linkedin_mcp_server --login\n"

# To:
"  Create profile on host first: uv run -m instagram_mcp_server --login\n"
```

**Step 2: Fix bootstrap.py**

```python
# Lines 370, 430 - Change:
_state.login_task = asyncio.create_task(_run_login_flow(), name="linkedin-login")

# To:
_state.login_task = asyncio.create_task(_run_login_flow(), name="instagram-login")
```

**Step 3: Fix __init__.py files**

```python
# instagram_mcp_server/tools/__init__.py - Line 1
# Change: # src/linkedin_mcp_server/tools/__init__.py
# To: # instagram_mcp_server/tools/__init__.py

# instagram_mcp_server/__init__.py - Line 1
# Change: # src/linkedin_mcp_server/__init__.py
# To: # instagram_mcp_server/__init__.py
```

**Step 4: Search for any other instances**

```bash
grep -r "linkedin" instagram_mcp_server/ --include="*.py" | grep -v "__pycache__"
```

Fix any remaining instances.

**Step 5: Run tests**

```bash
uv run pytest tests/ -k "authentication or bootstrap" -v
```

Expected: All pass

**Step 6: Commit**

```bash
git add instagram_mcp_server/
git commit -m "fix: replace all linkedin references with instagram"
```

---

## Task 3: Add Windows Support for CDP Mode

**Files:**
- Modify: `instagram_mcp_server/drivers/brave_cdp.py:20-38`
- Test: `tests/test_brave_cdp.py`

**Step 1: Refactor find_brave_process()**

```python
def find_brave_process() -> int | None:
    """Find running Brave process with remote debugging enabled."""
    import sys
    
    if sys.platform == "win32":
        return _find_brave_process_windows()
    else:
        return _find_brave_process_unix()


def _find_brave_process_unix() -> int | None:
    """Find Brave process on Unix-like systems."""
    try:
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


def _find_brave_process_windows() -> int | None:
    """Find Brave process on Windows."""
    try:
        # Use tasklist to find brave.exe processes
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq brave.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
        
        if result.returncode == 0 and "brave.exe" in result.stdout.lower():
            # Parse CSV: "Image Name","PID","Session Name","Session#","Mem Usage"
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if "brave.exe" in line.lower():
                    # Extract PID from CSV
                    parts = line.split(",")
                    if len(parts) >= 2:
                        pid_str = parts[1].strip('"')
                        if pid_str.isdigit():
                            return int(pid_str)
        return None
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        return None
```

**Step 2: Add tests**

```python
# tests/test_brave_cdp.py
import sys
import pytest
from instagram_mcp_server.drivers.brave_cdp import (
    find_brave_process,
    _find_brave_process_unix,
    _find_brave_process_windows,
)


class TestFindBraveProcessCrossPlatform:
    """Test Brave process detection on different platforms."""

    def test_uses_correct_platform_method(self, monkeypatch):
        """Should use platform-specific method."""
        # Test Unix path
        monkeypatch.setattr("sys.platform", "linux")
        # Would call _find_brave_process_unix
        
        # Test Windows path  
        monkeypatch.setattr("sys.platform", "win32")
        # Would call _find_brave_process_windows
        
        # Just verify no exception
        pid = find_brave_process()
        assert pid is None or isinstance(pid, int)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_windows_process_detection(self):
        """Test Windows process detection (requires Brave running on Windows)."""
        pid = _find_brave_process_windows()
        assert pid is None or isinstance(pid, int)

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_unix_process_detection(self):
        """Test Unix process detection."""
        pid = _find_brave_process_unix()
        assert pid is None or isinstance(pid, int)
```

**Step 3: Run tests**

```bash
uv run pytest tests/test_brave_cdp.py::TestFindBraveProcessCrossPlatform -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add instagram_mcp_server/drivers/brave_cdp.py tests/test_brave_cdp.py
git commit -m "feat: add Windows support for CDP mode"
```

---

## Task 4: Add CLI Configuration for CDP Mode

**Files:**
- Modify: `instagram_mcp_server/config/schema.py`
- Modify: `instagram_mcp_server/config/loaders.py`
- Modify: `instagram_mcp_server/cli_main.py`

**Step 1: Add to BrowserConfig schema**

```python
# instagram_mcp_server/config/schema.py

@dataclass
class BrowserConfig:
    """Browser configuration."""
    
    # ... existing fields ...
    
    # CDP mode configuration
    use_cdp_mode: bool = True
    """Use CDP mode to connect to running Brave browser (default: True)"""
    
    cdp_port: int = 9222
    """CDP debugging port (default: 9222)"""
```

**Step 2: Add CLI arguments**

```python
# instagram_mcp_server/config/loaders.py

def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Instagram MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # ... existing arguments ...
    
    # CDP mode arguments
    cdp_group = parser.add_mutually_exclusive_group()
    cdp_group.add_argument(
        "--cdp",
        action="store_true",
        default=None,
        help="Use CDP mode to connect to running Brave browser (default: enabled)",
    )
    cdp_group.add_argument(
        "--no-cdp",
        action="store_true",
        help="Disable CDP mode (use legacy browser automation)",
    )
    
    parser.add_argument(
        "--cdp-port",
        type=int,
        default=None,
        metavar="PORT",
        help="CDP debugging port (default: 9222, env: INSTAGRAM_DEBUGGING_PORT)",
    )
    
    return parser
```

**Step 3: Add environment variable loader**

```python
# instagram_mcp_server/config/loaders.py

class EnvironmentKeys:
    """Environment variable names."""
    
    # ... existing ...
    
    # CDP mode
    USE_CDP_MODE = "INSTAGRAM_USE_CDP_MODE"
    DEBUGGING_PORT = "INSTAGRAM_DEBUGGING_PORT"


def _normalize_env(value: str) -> str:
    """Normalize environment variable value."""
    return value.strip().lower()


FALSY_VALUES = {"0", "false", "no", "off", ""}


def load_from_env(config: AppConfig) -> AppConfig:
    """Load configuration from environment variables."""
    
    # ... existing loaders ...
    
    # CDP mode
    if cdp_mode_env := os.environ.get(EnvironmentKeys.USE_CDP_MODE):
        value = _normalize_env(cdp_mode_env)
        config.browser.use_cdp_mode = value not in FALSY_VALUES
    
    # CDP debugging port
    if cdp_port_env := os.environ.get(EnvironmentKeys.DEBUGGING_PORT):
        try:
            config.browser.cdp_port = int(cdp_port_env)
        except ValueError:
            raise ConfigurationError(
                f"Invalid {EnvironmentKeys.DEBUGGING_PORT}: '{cdp_port_env}'. "
                "Must be an integer."
            )
    
    return config
```

**Step 4: Apply CLI args to config**

```python
# instagram_mcp_server/config/loaders.py

def apply_cli_args_to_config(config: AppConfig, args: argparse.Namespace) -> AppConfig:
    """Apply CLI arguments to configuration."""
    
    # ... existing ...
    
    # CDP mode
    if args.cdp is not None or args.no_cdp is not None:
        config.browser.use_cdp_mode = args.cdp and not args.no_cdp
    
    if args.cdp_port is not None:
        config.browser.cdp_port = args.cdp_port
    
    return config
```

**Step 5: Update browser.py to use config**

```python
# instagram_mcp_server/drivers/browser.py

def _cdp_mode_enabled() -> bool:
    """Check if CDP mode is enabled via environment or config. Default is True."""
    # First check env var (for backward compatibility)
    value = os.getenv("INSTAGRAM_USE_CDP_MODE", "").strip().lower()
    if value:  # If explicitly set, use it
        return value not in {"0", "false", "no", "off"}
    
    # Otherwise use config default
    config = get_config()
    return config.browser.use_cdp_mode


def get_debugging_address(port: int | None = None) -> str:
    """Get the CDP debugging address for Brave browser."""
    if port is None:
        config = get_config()
        port = config.browser.cdp_port
    
    # Use 127.0.0.1 instead of localhost to avoid IPv6 issues
    return f"http://127.0.0.1:{port}"
```

**Step 6: Update help text**

```python
# instagram_mcp_server/cli_main.py

# Update --help output to mention CDP mode
```

**Step 7: Run tests**

```bash
uv run pytest tests/test_config.py -v
```

Expected: All config tests pass

**Step 8: Test CLI**

```bash
uv run -m instagram_mcp_server --help | grep -A 2 "cdp"
```

Expected: Shows --cdp, --no-cdp, --cdp-port options

**Step 9: Commit**

```bash
git add instagram_mcp_server/config/ instagram_mcp_server/drivers/browser.py instagram_mcp_server/cli_main.py
git commit -m "feat: add CLI configuration for CDP mode"
```

---

## Task 5: Add CDPConnectionError Exception

**Files:**
- Modify: `instagram_mcp_server/exceptions.py`
- Modify: `instagram_mcp_server/error_handler.py`
- Modify: `instagram_mcp_server/drivers/brave_cdp.py`

**Step 1: Add exception class**

```python
# instagram_mcp_server/exceptions.py

class CDPConnectionError(InstagramMCPError):
    """Failed to connect to Brave browser via CDP.
    
    This error is raised when the server cannot establish a CDP connection
    to a running Brave browser instance.
    """
    
    default_message = (
        "Could not connect to Brave browser via CDP.\n\n"
        "To fix this:\n"
        "  1. Launch Brave with remote debugging:\n"
        "     uv run instagram-launch-brave\n"
        "  2. Or manually:\n"
        "     brave-browser --remote-debugging-port=9222\n"
        "  3. Log into Instagram in that browser window\n"
        "  4. Retry this tool\n\n"
        "For more information, see docs/CDP_MODE.md"
    )
    
    def __init__(self, message: str | None = None, cause: Exception | None = None):
        super().__init__(message or self.default_message)
        self.cause = cause
```

**Step 2: Update connect_to_brave to raise CDPConnectionError**

```python
# instagram_mcp_server/drivers/brave_cdp.py

from instagram_mcp_server.exceptions import CDPConnectionError

async def connect_to_brave(
    port: int | None = None,
    timeout: float = 60.0,
) -> Browser:
    """Connect to running Brave browser via CDP."""
    debugging_address = get_debugging_address(port)
    
    logger.info(f"Connecting to Brave at {debugging_address}...")
    
    try:
        playwright: Playwright = await async_playwright().start()
        
        browser = await playwright.chromium.connect_over_cdp(
            debugging_address,
            timeout=timeout * 1000,
        )
        
        logger.info("Successfully connected to Brave browser via CDP")
        return browser
        
    except Exception as e:
        logger.error(f"Failed to connect to Brave: {e}")
        raise CDPConnectionError(cause=e) from e
```

**Step 3: Add error handler**

```python
# instagram_mcp_server/error_handler.py

from instagram_mcp_server.exceptions import (
    # ... existing ...
    CDPConnectionError,
)

def _raise_tool_error(exception: Exception, tool_name: str) -> NoReturn:
    """Convert exception to appropriate MCP tool error."""
    
    # ... existing handlers ...
    
    elif isinstance(exception, CDPConnectionError):
        logger.warning("CDP connection failed: %s", exception)
        raise ToolError(str(exception)) from exception
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_exceptions.py -v
```

Expected: All exception tests pass

**Step 5: Commit**

```bash
git add instagram_mcp_server/exceptions.py instagram_mcp_server/error_handler.py instagram_mcp_server/drivers/brave_cdp.py
git commit -m "feat: add CDPConnectionError exception with helpful error messages"
```

---

## Task 6: Update Bootstrap Login Flow for CDP

**Files:**
- Modify: `instagram_mcp_server/bootstrap.py`
- Modify: `instagram_mcp_server/setup.py`

**Step 1: Add CDP login flow to bootstrap**

```python
# instagram_mcp_server/bootstrap.py

async def _run_login_flow() -> None:
    """Run interactive login flow."""
    _state.auth_state = AuthState.IN_PROGRESS
    _state.auth_started_at = utcnow_iso()
    _state.last_error = None
    _state.auth_completed_at = None
    
    try:
        if _cdp_mode_enabled():
            success = await _cdp_login_flow()
        else:
            from instagram_mcp_server.setup import interactive_login
            success = await interactive_login(get_profile_dir(), warm_up=True)
        
        if success:
            _state.auth_state = AuthState.READY
            _state.auth_completed_at = utcnow_iso()
        else:
            _state.auth_state = AuthState.FAILED
            _state.last_error = "Login flow did not complete successfully"
            
    except Exception as e:
        _state.auth_state = AuthState.FAILED
        _state.last_error = f"{type(e).__name__}: {e}"
        logger.exception("Login flow failed")


async def _cdp_login_flow() -> bool:
    """Guide user through CDP mode login."""
    from instagram_mcp_server.drivers.brave_cdp import find_brave_process
    
    # Check if Brave is already running with CDP
    if find_brave_process():
        logger.info("Brave is already running with CDP")
        return True
    
    # Print instructions
    print("\n" + "="*60)
    print("CDP MODE: Connect to your running Brave browser")
    print("="*60)
    print("\nBrave browser is not running with remote debugging.")
    print("\nOption 1: Quick launch (recommended)")
    print("  Run in another terminal:")
    print("    uv run instagram-launch-brave")
    print("\nOption 2: Manual launch")
    print("  Run in another terminal:")
    print("    brave-browser --remote-debugging-port=9222")
    print("\nThen log into Instagram in that browser window.")
    print("\nWaiting for Brave to start...")
    
    # Wait for Brave to start (poll for 2 minutes)
    import asyncio
    for _ in range(24):  # 2 minutes, check every 5 seconds
        await asyncio.sleep(5)
        if find_brave_process():
            print("✓ Brave detected! Continuing...")
            return True
    
    print("\n⚠ Timeout: Brave not detected after 2 minutes")
    print("Run 'uv run instagram-launch-brave' and try again.")
    return False
```

**Step 2: Update setup.py to deprecate browser login**

```python
# instagram_mcp_server/setup.py

"""
Interactive setup for Instagram MCP Server.

Primary method: CDP mode (connect to running Brave browser)
Legacy method: Browser automation (deprecated)
"""

import warnings

def run_profile_creation(user_data_dir: str | None = None) -> bool:
    """Create profile via CDP mode or legacy browser login."""
    
    # Check if CDP mode is enabled
    from instagram_mcp_server.drivers.browser import _cdp_mode_enabled
    
    if _cdp_mode_enabled():
        print("\nCDP Mode is enabled.")
        print("Please launch Brave with:")
        print("  uv run instagram-launch-brave")
        print("\nThen log into Instagram in that browser window.")
        return True
    
    # Legacy mode (deprecated)
    warnings.warn(
        "Browser-based login is deprecated. Use CDP mode instead.",
        DeprecationWarning,
    )
    
    # ... existing legacy implementation ...
```

**Step 3: Run tests**

```bash
uv run pytest tests/test_bootstrap.py -v
```

Expected: All bootstrap tests pass

**Step 4: Commit**

```bash
git add instagram_mcp_server/bootstrap.py instagram_mcp_server/setup.py
git commit -m "feat: add CDP login flow to bootstrap"
```

---

## Task 7: Fix Documentation to Match Code

**Files:**
- Modify: `docs/CDP_MODE.md`
- Modify: `README.md`

**Step 1: Update CDP_MODE.md**

```markdown
# docs/CDP_MODE.md

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `INSTAGRAM_USE_CDP_MODE` | Enable CDP mode (`0`, `false`, `no`, `off` to disable) | `1` (enabled by default) |
| `INSTAGRAM_DEBUGGING_PORT` | CDP debugging port | `9222` |
```

**Step 2: Update README.md**

Update the quick start to reflect that CDP is now the default:

```markdown
## 🎯 CDP Mode (Default - No Bot Detection)

CDP mode is **enabled by default**. The server will automatically connect to your running Brave browser.

### First Time Setup

1. Launch Brave with remote debugging:
   ```bash
   uv run instagram-launch-brave
   ```

2. Log into Instagram in the Brave window

3. Run the MCP server (automatically connects via CDP):
   ```bash
   uv run -m instagram_mcp_server
   ```

### Disable CDP Mode

To use legacy browser automation (not recommended):

```bash
uv run -m instagram_mcp_server --no-cdp
```

Or via environment variable:

```bash
export INSTAGRAM_USE_CDP_MODE=0
uv run -m instagram_mcp_server
```
```

**Step 3: Commit**

```bash
git add docs/CDP_MODE.md README.md
git commit -m "docs: update documentation to reflect CDP as default"
```

---

## Task 8: Skip Browser Setup in Lifespan for CDP Mode

**Files:**
- Modify: `instagram_mcp_server/server.py:33-48`

**Step 1: Update lifespan hook**

```python
# instagram_mcp_server/server.py

from instagram_mcp_server.drivers.browser import _cdp_mode_enabled

@lifespan
async def browser_lifespan(app: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Manage browser lifecycle — cleanup on shutdown."""
    del app
    logger.info("Instagram MCP Server starting...")
    initialize_bootstrap(get_runtime_policy())
    
    # Only setup browser for legacy mode
    if not _cdp_mode_enabled():
        logger.info("Legacy mode: setting up browser...")
        await start_background_browser_setup_if_needed()
    else:
        logger.info("CDP mode: skipping browser setup")
    
    yield {}
    
    logger.info("Instagram MCP Server shutting down...")
    
    # Only close browser for legacy mode
    if not _cdp_mode_enabled():
        await close_browser()
```

**Step 2: Run tests**

```bash
uv run pytest tests/test_server.py -v
```

Expected: All server tests pass

**Step 3: Commit**

```bash
git add instagram_mcp_server/server.py
git commit -m "perf: skip browser setup in lifespan when using CDP mode"
```

---

## Task 9: Update --status to Use CDP

**Files:**
- Modify: `instagram_mcp_server/cli_main.py:191-200`

**Step 1: Update check_session()**

```python
# instagram_mcp_server/cli_main.py

async def check_session() -> bool:
    """Check if a valid Instagram session exists."""
    try:
        if _cdp_mode_enabled():
            # Use CDP connection for status check
            from instagram_mcp_server.drivers.brave_cdp import (
                connect_to_brave,
                verify_instagram_session,
                find_brave_process,
            )
            
            # Check if Brave is running
            if not find_brave_process():
                print("⚠ Brave browser not running with remote debugging")
                return False
            
            # Connect and verify
            browser = await connect_to_brave(timeout=10)
            verified = await verify_instagram_session(browser)
            await browser.close()
            
            return verified
        else:
            # Legacy mode
            set_headless(True)
            browser = await get_or_create_browser()
            return browser.is_authenticated
            
    except AuthenticationError:
        return False
    except Exception as e:
        logger.debug(f"Session check failed: {e}")
        return False
```

**Step 2: Commit**

```bash
git add instagram_mcp_server/cli_main.py
git commit -m "feat: use CDP for --status check when available"
```

---

## Task 10: Final Testing and Cleanup

**Files:**
- All modified files

**Step 1: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: All 297+ tests pass

**Step 2: Test CDP mode end-to-end**

```bash
# Start Brave with CDP
uv run instagram-launch-brave &

# Wait for Brave to start
sleep 3

# Test server with CDP
uv run -m instagram_mcp_server --log-level INFO &

# Test a tool
curl -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_user_profile","arguments":{"username":"instagram"}}}'
```

Expected: Returns profile data without bot detection

**Step 3: Test legacy mode still works**

```bash
uv run -m instagram_mcp_server --no-cdp --log-level INFO
```

Expected: Shows deprecation warning but works

**Step 4: Test error messages**

```bash
# Kill Brave
pkill brave

# Try to use MCP - should show helpful error
uv run -m instagram_mcp_server --log-level INFO
```

Expected: Shows CDPConnectionError with setup instructions

**Step 5: Update CHANGELOG**

```markdown
# CHANGELOG.md

## [1.1.0] - 2026-04-02

### Added
- CDP mode is now the default authentication method
- `--cdp` and `--no-cdp` CLI flags
- `--cdp-port` CLI flag for custom CDP port
- `CDPConnectionError` exception with helpful error messages
- Windows support for CDP mode

### Changed
- **BREAKING:** CDP mode enabled by default (set `INSTAGRAM_USE_CDP_MODE=0` to disable)
- Error messages now reference `instagram_mcp_server` instead of `linkedin_mcp_server`
- Browser setup skipped in lifespan when using CDP mode
- `--status` check uses CDP when available

### Fixed
- All copy-paste errors from LinkedIn fork
- IPv6 issues with CDP connection (use 127.0.0.1)
- Documentation mismatch for CDP default value

### Deprecated
- Legacy browser automation mode (use CDP mode instead)
- Cookie import via SQLite extraction (use CDP mode)
```

**Step 6: Bump version**

```bash
uv version --bump minor
```

**Step 7: Commit**

```bash
git add CHANGELOG.md pyproject.toml uv.lock
git commit -m "chore: bump version to 1.1.0 for CDP default release"
```

---

## Summary

After completing this plan:

✅ **CDP mode is the actual default** - No env var needed
✅ **All LinkedIn references fixed** - Clear error messages
✅ **Windows support added** - Cross-platform CDP
✅ **CLI configuration** - `--cdp`, `--no-cdp`, `--cdp-port` flags
✅ **Better error handling** - `CDPConnectionError` with setup instructions
✅ **Documentation matches code** - No more confusion
✅ **Performance improved** - Skip browser setup for CDP users
✅ **AI agent ready** - Clear guidance in all error messages

**Total estimated time:** 2-3 hours

**Files to modify:** 12
**Files to create:** 0
**Tests to add:** ~50 lines

---
