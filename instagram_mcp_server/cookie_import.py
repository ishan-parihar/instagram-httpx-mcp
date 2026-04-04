"""
Multi-browser cookie import for Instagram MCP Server.

Primary authentication method: Import cookies from user's browser session.
Supports ALL major browsers: Brave, Chrome, Edge, Firefox, Zen, Helium,
Chromium, Opera, Arc, Vivaldi, LibreWolf, Waterfox, and more.

This bypasses Instagram's aggressive bot detection that blocks automated browsers.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from instagram_mcp_server.session_state import auth_root_dir

logger = logging.getLogger(__name__)

# ─── Cookie requirements ───────────────────────────────────────────────────
INSTAGRAM_COOKIES = {"sessionid", "csrftoken", "ds_user_id", "ig_did", "mid"}
REQUIRED_COOKIES = {"sessionid", "csrftoken"}

# ─── Browser engine types ──────────────────────────────────────────────────
BrowserEngine = Literal["chromium", "firefox", "safari"]


@dataclass
class BrowserProfile:
    """Describes a browser's cookie DB path, executable paths, and engine."""

    name: str
    engine: BrowserEngine
    cookie_db_paths: list[str]  # relative to browser profile dir
    profile_dir_paths: list[str]  # relative to home/config dirs
    executable_paths: list[str]
    cdp_flag: str = "--remote-debugging-port={port}"
    cdp_process_pattern: str = ""  # regex-like substring for process detection
    description: str = ""
    # For Firefox: uses cookies.sqlite, not Chrome-format Cookies db
    cookie_db_name: str = "Cookies"


# ─── Browser registry ──────────────────────────────────────────────────────
# Ordered by priority (most recommended first)
BROWSER_REGISTRY: dict[str, BrowserProfile] = {
    "brave": BrowserProfile(
        name="Brave",
        engine="chromium",
        description="Recommended — best bot-detection resistance",
        cookie_db_paths=["Default/Cookies", "Profile */Cookies"],
        profile_dir_paths=[
            ".config/BraveSoftware/Brave-Browser",
            ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser",
            "AppData/Local/BraveSoftware/Brave-Browser/User Data",  # Windows
            "Library/Application Support/BraveSoftware/Brave-Browser",  # macOS
        ],
        executable_paths=[
            "/opt/brave-bin/brave",
            "/usr/bin/brave-browser",
            "/usr/bin/brave",
            "/snap/bin/brave",
            "/usr/lib/brave/brave",
            "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
            "C:/Program Files (x86)/BraveSoftware/Brave-Browser/Application/brave.exe",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ],
        cdp_process_pattern="brave.*remote-debugging",
    ),
    "chrome": BrowserProfile(
        name="Google Chrome",
        engine="chromium",
        description="Most widely used",
        cookie_db_paths=["Default/Cookies", "Profile */Cookies"],
        profile_dir_paths=[
            ".config/google-chrome",
            ".var/app/com.google.Chrome/config/google-chrome",
            "AppData/Local/Google/Chrome/User Data",
            "Library/Application Support/Google/Chrome",
        ],
        executable_paths=[
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chrome",
            "/snap/bin/chromium",
            "/opt/google/chrome/chrome",
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ],
        cdp_process_pattern="chrome.*remote-debugging",
    ),
    "edge": BrowserProfile(
        name="Microsoft Edge",
        engine="chromium",
        description="Built into Windows, Chromium-based",
        cookie_db_paths=["Default/Cookies", "Profile */Cookies"],
        profile_dir_paths=[
            ".config/microsoft-edge",
            "AppData/Local/Microsoft/Edge/User Data",
            "Library/Application Support/Microsoft Edge",
        ],
        executable_paths=[
            "/usr/bin/microsoft-edge",
            "/usr/bin/microsoft-edge-stable",
            "/usr/bin/edge",
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
            "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ],
        cdp_process_pattern="msedge.*remote-debugging",
    ),
    "zen": BrowserProfile(
        name="Zen Browser",
        engine="firefox",
        description="Firefox-based, privacy-focused",
        cookie_db_paths=["Default/cookies.sqlite"],
        profile_dir_paths=[
            ".zen",
            ".config/zen",
            "AppData/Roaming/Zen",
            "Library/Application Support/Zen",
        ],
        executable_paths=[
            "/opt/zen-browser-bin/zen-bin",
            "/opt/zen-browser-bin/zen",
            "/usr/bin/zen-browser",
            "/opt/zen/zen",
            "/usr/bin/zen",
            "/usr/local/bin/zen",
            "C:/Program Files/Zen Browser/zen.exe",
            "/Applications/Zen Browser.app/Contents/MacOS/zen",
        ],
        cdp_process_pattern="",  # Firefox doesn't support CDP
        cookie_db_name="cookies.sqlite",
    ),
    "firefox": BrowserProfile(
        name="Mozilla Firefox",
        engine="firefox",
        description="Open-source, non-Chromium",
        cookie_db_paths=["cookies.sqlite"],
        profile_dir_paths=[
            ".mozilla/firefox",
            ".var/app/org.mozilla.firefox/.mozilla/firefox",
            "AppData/Roaming/Mozilla/Firefox/Profiles",
            "Library/Application Support/Firefox/Profiles",
        ],
        executable_paths=[
            "/usr/bin/firefox",
            "/usr/bin/firefox-esr",
            "/snap/bin/firefox",
            "/opt/firefox/firefox",
            "C:/Program Files/Mozilla Firefox/firefox.exe",
            "C:/Program Files (x86)/Mozilla Firefox/firefox.exe",
            "/Applications/Firefox.app/Contents/MacOS/firefox",
        ],
        cdp_process_pattern="",
        cookie_db_name="cookies.sqlite",
    ),
    "librewolf": BrowserProfile(
        name="LibreWolf",
        engine="firefox",
        description="Hardened Firefox fork",
        cookie_db_paths=["cookies.sqlite"],
        profile_dir_paths=[
            ".librewolf",
            ".var/app/io.gitlab.librewolf-community/.librewolf",
        ],
        executable_paths=[
            "/usr/bin/librewolf",
            "/usr/local/bin/librewolf",
            "/opt/librewolf/librewolf",
        ],
        cdp_process_pattern="",
        cookie_db_name="cookies.sqlite",
    ),
    "waterfox": BrowserProfile(
        name="Waterfox",
        engine="firefox",
        description="Privacy-focused Firefox fork",
        cookie_db_paths=["cookies.sqlite"],
        profile_dir_paths=[
            ".waterfox",
            "AppData/Roaming/Waterfox/Profiles",
            "Library/Application Support/Waterfox/Profiles",
        ],
        executable_paths=[
            "/usr/bin/waterfox",
            "/opt/waterfox/waterfox",
            "C:/Program Files/Waterfox/waterfox.exe",
            "/Applications/Waterfox.app/Contents/MacOS/waterfox",
        ],
        cdp_process_pattern="",
        cookie_db_name="cookies.sqlite",
    ),
    "helium": BrowserProfile(
        name="Helium",
        engine="chromium",
        description="Lightweight Chromium-based browser",
        cookie_db_paths=["Default/Cookies", "Profile */Cookies"],
        profile_dir_paths=[
            ".config/net.imput.helium",
            ".config/Helium",
            ".var/app/io.helium.browser/config/Helium",
            "AppData/Local/Helium/User Data",
            "Library/Application Support/Helium",
        ],
        executable_paths=[
            "/opt/helium-browser-bin/helium",
            "/opt/helium-browser-bin/helium-wrapper",
            "/usr/bin/helium-browser",
            "/usr/bin/helium",
            "/opt/helium/helium",
            "/usr/local/bin/helium",
        ],
        cdp_process_pattern="helium.*remote-debugging",
    ),
    "chromium": BrowserProfile(
        name="Chromium",
        engine="chromium",
        description="Open-source Chromium",
        cookie_db_paths=["Default/Cookies", "Profile */Cookies"],
        profile_dir_paths=[
            ".config/chromium",
            ".var/app/org.chromium.Chromium/config/chromium",
            "AppData/Local/Chromium/User Data",
            "Library/Application Support/Chromium",
        ],
        executable_paths=[
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
            "/usr/lib/chromium/chromium",
            "C:/Program Files/Chromium/chrome.exe",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ],
        cdp_process_pattern="chromium.*remote-debugging",
    ),
    "opera": BrowserProfile(
        name="Opera",
        engine="chromium",
        description="Feature-rich Chromium browser",
        cookie_db_paths=["Default/Cookies", "Profile */Cookies"],
        profile_dir_paths=[
            ".config/opera",
            "AppData/Roaming/Opera Software/Opera Stable",
            "Library/Application Support/com.operasoftware.Opera",
        ],
        executable_paths=[
            "/usr/bin/opera",
            "/usr/bin/opera-stable",
            "/snap/bin/opera",
            "C:/Program Files/Opera/launcher.exe",
            "C:/Program Files (x86)/Opera/launcher.exe",
            "/Applications/Opera.app/Contents/MacOS/Opera",
        ],
        cdp_process_pattern="opera.*remote-debugging",
    ),
    "vivaldi": BrowserProfile(
        name="Vivaldi",
        engine="chromium",
        description="Customizable Chromium browser",
        cookie_db_paths=["Default/Cookies", "Profile */Cookies"],
        profile_dir_paths=[
            ".config/vivaldi",
            "AppData/Local/Vivaldi/User Data",
            "Library/Application Support/Vivaldi",
        ],
        executable_paths=[
            "/usr/bin/vivaldi",
            "/usr/bin/vivaldi-stable",
            "/opt/vivaldi/vivaldi",
            "C:/Program Files/Vivaldi/Application/vivaldi.exe",
            "C:/Program Files (x86)/Vivaldi/Application/vivaldi.exe",
            "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
        ],
        cdp_process_pattern="vivaldi.*remote-debugging",
    ),
    "arc": BrowserProfile(
        name="Arc Browser",
        engine="chromium",
        description="Modern Chromium-based browser (macOS)",
        cookie_db_paths=["Default/Cookies", "Profile */Cookies"],
        profile_dir_paths=[
            "Library/Application Support/Arc/User Data",
        ],
        executable_paths=[
            "/Applications/Arc.app/Contents/MacOS/Arc",
        ],
        cdp_process_pattern="Arc.*remote-debugging",
    ),
    "floorp": BrowserProfile(
        name="Floorp",
        engine="firefox",
        description="Firefox-based with advanced customization",
        cookie_db_paths=["cookies.sqlite"],
        profile_dir_paths=[
            ".floorp",
            ".var/app/one.ablaze.floorp/.floorp",
            "AppData/Roaming/Floorp/Profiles",
            "Library/Application Support/Floorp/Profiles",
        ],
        executable_paths=[
            "/usr/bin/floorp",
            "/opt/floorp/floorp",
            "/usr/local/bin/floorp",
            "/Applications/Floorp.app/Contents/MacOS/floorp",
        ],
        cdp_process_pattern="",
        cookie_db_name="cookies.sqlite",
    ),
}


# ─── Platform helpers ──────────────────────────────────────────────────────
def _current_platform() -> Literal["linux", "darwin", "win32"]:
    return sys.platform  # type: ignore[return-value]


def _expand_browser_path(path: str) -> Path | None:
    """Resolve a browser executable path, handling platform-specific expansion."""
    p = Path(path).expanduser()
    if p.exists():
        return p
    return None


def _expand_profile_path(path: str) -> Path | None:
    """Resolve a browser profile directory path."""
    plat = _current_platform()
    if plat == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    elif plat == "darwin":
        base = Path.home()
    else:
        base = Path.home()

    candidate = base / path
    if candidate.exists():
        return candidate
    return None


# ─── Browser detection ─────────────────────────────────────────────────────
def detect_installed_browsers() -> list[tuple[str, BrowserProfile]]:
    """Detect which browsers from the registry are installed on this system.

    Returns list of (browser_id, profile) tuples, ordered by registry priority.
    """
    installed = []
    for browser_id, profile in BROWSER_REGISTRY.items():
        exe = find_browser_executable(profile)
        if exe is not None:
            installed.append((browser_id, profile))
    return installed


def find_browser_executable(profile: BrowserProfile) -> Path | None:
    """Find the first existing executable for a browser profile."""
    for path in profile.executable_paths:
        exe = _expand_browser_path(path)
        if exe is not None:
            return exe
    return None


def find_browser_profile_dir(profile: BrowserProfile) -> Path | None:
    """Find the first existing profile directory for a browser."""
    for path in profile.profile_dir_paths:
        p = _expand_profile_path(path)
        if p is not None:
            return p
    return None


def find_browser_cookie_db(browser_id: str) -> Path | None:
    """Find the cookie database for a specific browser."""
    prof = BROWSER_REGISTRY.get(browser_id)
    if prof is None:
        return None

    profile_dir = find_browser_profile_dir(prof)
    if profile_dir is None:
        return None

    # For Firefox-based browsers, find the default profile first
    if prof.engine == "firefox":
        # Firefox-style browsers use profiles.ini + cookies.sqlite in profile folders
        if browser_id in ("firefox", "librewolf", "waterfox", "floorp", "zen"):
            return _find_firefox_cookie_db(profile_dir)
        else:
            # Zen and others might have a simpler structure
            for db_path in prof.cookie_db_paths:
                candidate = profile_dir / db_path
                if candidate.exists():
                    return candidate
            # Try searching subdirectories
            for subdir in profile_dir.iterdir():
                if subdir.is_dir():
                    for db_path in prof.cookie_db_paths:
                        candidate = subdir / db_path
                        if candidate.exists():
                            return candidate
            return None

    # Chromium-based: search profile dirs for Cookies file
    for db_path in prof.cookie_db_paths:
        candidate = profile_dir / db_path
        if candidate.exists():
            return candidate

    # Try with wildcard for Profile N
    if "Profile *" in prof.cookie_db_paths:
        for item in sorted(profile_dir.iterdir()):
            if item.is_dir() and item.name.startswith("Profile "):
                candidate = item / "Cookies"
                if candidate.exists():
                    return candidate

    return None


def _find_firefox_cookie_db(profiles_dir: Path) -> Path | None:
    """Find cookies.sqlite in a Firefox-style profile directory."""
    # Direct cookies.sqlite in the profiles dir
    direct = profiles_dir / "cookies.sqlite"
    if direct.exists():
        return direct

    # Search for profiles.ini to find the default profile
    ini_path = profiles_dir / "profiles.ini"
    if ini_path.exists():
        default_profile = _parse_firefox_profiles_ini(ini_path, profiles_dir)
        if default_profile:
            cookie_db = default_profile / "cookies.sqlite"
            if cookie_db.exists():
                return cookie_db

    # Search all subdirectories for cookies.sqlite
    for subdir in profiles_dir.iterdir():
        if subdir.is_dir():
            cookie_db = subdir / "cookies.sqlite"
            if cookie_db.exists():
                return cookie_db

    return None


def _parse_firefox_profiles_ini(ini_path: Path, base_dir: Path) -> Path | None:
    """Parse profiles.ini to find the default Firefox profile directory."""
    try:
        import configparser

        config = configparser.ConfigParser()
        config.read(str(ini_path))

        # Find the default profile
        for section in config.sections():
            if config.has_option(section, "Default") and config.getboolean(
                section, "Default"
            ):
                profile_path = config.get(section, "Path")
                is_relative = config.get(section, "IsRelative", fallback="1") == "1"
                if is_relative:
                    return base_dir / profile_path
                return Path(profile_path)

        # If no default, try Profile0
        for section in config.sections():
            if section.startswith("Profile"):
                profile_path = config.get(section, "Path")
                is_relative = config.get(section, "IsRelative", fallback="1") == "1"
                if is_relative:
                    return base_dir / profile_path
                return Path(profile_path)
    except Exception:
        pass
    return None


# ─── Cookie extraction ─────────────────────────────────────────────────────
def _copy_db_to_temp(db_path: Path) -> Path:
    """Copy a locked SQLite DB to a temp file for safe reading."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=db_path.suffix)
    tmp_path = Path(tmp.name)
    tmp.close()
    shutil.copy2(db_path, tmp_path)
    return tmp_path


def extract_chromium_cookies(db_path: Path) -> dict[str, str]:
    """Extract Instagram cookies from a Chromium-style Cookies SQLite database.

    Chromium cookies may have encrypted values on Linux (using DPAPI on Windows,
    or libsecret on Linux). For simplicity, we extract plaintext values only.
    """
    cookies: dict[str, str] = {}
    tmp_path = _copy_db_to_temp(db_path)
    try:
        conn = sqlite3.connect(str(tmp_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, value, encrypted_value FROM cookies "
            "WHERE host_key LIKE '%instagram.com%'"
        )
        for name, value, encrypted_value in cursor.fetchall():
            if name in INSTAGRAM_COOKIES:
                if value:
                    cookies[name] = value
                elif encrypted_value:
                    logger.debug("Skipping encrypted cookie: %s", name)
        conn.close()
    finally:
        tmp_path.unlink(missing_ok=True)
    return cookies


def extract_firefox_cookies(db_path: Path) -> dict[str, str]:
    """Extract Instagram cookies from Firefox cookies.sqlite.

    Firefox cookie schemas vary by version/branch:
    - Modern Firefox (127+): uses 'baseDomain' column
    - Zen, Floorp, older Firefox: uses 'host' column
    We detect which column exists at runtime.
    """
    cookies: dict[str, str] = {}
    tmp_path = _copy_db_to_temp(db_path)
    try:
        conn = sqlite3.connect(str(tmp_path))
        cursor = conn.cursor()

        # Detect which host-matching column exists in this DB
        cursor.execute("PRAGMA table_info(moz_cookies)")
        col_names = {row[1] for row in cursor.fetchall()}

        if "baseDomain" in col_names:
            host_col = "baseDomain"
        elif "host" in col_names:
            host_col = "host"
        else:
            logger.error("No host column found in Firefox moz_cookies table")
            conn.close()
            return cookies

        cursor.execute(
            f"SELECT name, value FROM moz_cookies "
            f"WHERE {host_col} LIKE '%instagram.com%'"
        )
        for name, value in cursor.fetchall():
            if name in INSTAGRAM_COOKIES:
                if value:
                    cookies[name] = value
        conn.close()
    finally:
        tmp_path.unlink(missing_ok=True)
    return cookies


def extract_cookies_from_browser(browser_id: str) -> dict[str, str] | None:
    """Extract Instagram cookies from a specific browser.

    Args:
        browser_id: Browser identifier from BROWSER_REGISTRY

    Returns:
        Dict of cookie name -> value, or None if extraction failed
    """
    profile = BROWSER_REGISTRY.get(browser_id)
    if profile is None:
        logger.error("Unknown browser: %s", browser_id)
        return None

    cookie_db = find_browser_cookie_db(browser_id)
    if cookie_db is None:
        logger.debug("Cookie DB not found for %s", profile.name)
        return None

    logger.info("Found cookie DB for %s: %s", profile.name, cookie_db)

    if profile.engine == "chromium":
        return extract_chromium_cookies(cookie_db)
    elif profile.engine == "firefox":
        return extract_firefox_cookies(cookie_db)

    return None


# ─── Save cookies ──────────────────────────────────────────────────────────
def save_cookies_to_profile(
    cookies: dict[str, str],
    profile_dir: Path,
    source_browser: str = "unknown",
) -> bool:
    """Save cookies in MCP's portable JSON format.

    Args:
        cookies: Cookie name -> value mapping
        profile_dir: Target profile directory
        source_browser: Which browser the cookies came from

    Returns:
        True if saved successfully
    """
    cookie_file = auth_root_dir(profile_dir) / "cookies.json"
    try:
        cookie_data = {
            "cookies": [
                {
                    "name": name,
                    "value": value,
                    "domain": ".instagram.com",
                    "path": "/",
                    "secure": True,
                    "expires": -1,
                }
                for name, value in cookies.items()
            ],
            "imported_from": source_browser,
        }
        cookie_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cookie_file, "w") as f:
            json.dump(cookie_data, f, indent=2)
        cookie_file.chmod(0o600)
        return True
    except Exception as e:
        logger.error("Failed to save cookies: %s", e)
        return False


def validate_cookies(cookies: dict[str, str]) -> tuple[bool, set[str]]:
    """Validate that cookies contain required Instagram cookies.

    Returns:
        (is_valid, missing_required_cookies)
    """
    missing = REQUIRED_COOKIES - set(cookies.keys())
    return len(missing) == 0, missing


# ─── Interactive browser selection ─────────────────────────────────────────
def choose_browser_interactive() -> str | None:
    """Interactive prompt to select which browser to import cookies from.

    Uses inquirer to present a list of detected browsers.

    Returns:
        Browser ID string, or None if cancelled
    """
    installed = detect_installed_browsers()

    if not installed:
        print("\n⚠ No supported browsers detected on this system.")
        print("The following browsers are supported:")
        for bid, prof in BROWSER_REGISTRY.items():
            print(f"  - {prof.name} ({prof.engine})")
        return None

    choices = []
    for browser_id, profile in installed:
        exe = find_browser_executable(profile)
        label = f"{profile.name} — {profile.description} ({profile.engine})"
        if exe:
            label += f" [{exe}]"
        choices.append((label, browser_id))

    import inquirer

    questions = [
        inquirer.List(
            "browser",
            message="Which browser should we import Instagram cookies from?",
            choices=choices,
            default=choices[0][1] if choices else None,
        )
    ]

    answers = inquirer.prompt(questions)
    if answers is None:
        return None
    return answers["browser"]


# ─── Interactive cookie import flow ────────────────────────────────────────
def import_cookies_interactive(browser_id: str | None = None) -> bool:
    """Interactive cookie import from the user's browser.

    Args:
        browser_id: Specific browser to import from. If None, prompts user.

    Returns:
        True if cookies were imported successfully
    """
    if browser_id is None:
        browser_id = choose_browser_interactive()
        if browser_id is None:
            return False

    profile = BROWSER_REGISTRY.get(browser_id)
    if profile is None:
        print(f"   ⚠ Unknown browser: {browser_id}")
        return False

    print(f"\n   Importing cookies from {profile.name}...")

    cookies = extract_cookies_from_browser(browser_id)

    if not cookies:
        print(f"   ⚠ No Instagram cookies found in {profile.name}.")
        print(f"   Please log into Instagram in {profile.name} first, then try again.")
        return False

    print(f"   ✓ Found {len(cookies)} Instagram cookies: {list(cookies.keys())}")

    is_valid, missing = validate_cookies(cookies)
    if not is_valid:
        print(f"   ⚠ Missing required cookies: {missing}")
        print(f"   You may need to log in again in {profile.name}.")
        return False

    profile_dir = Path.home() / ".instagram-mcp" / "profile"

    if save_cookies_to_profile(cookies, profile_dir, source_browser=browser_id):
        print(f"   ✓ Cookies saved to: {profile_dir}/cookies.json")
        # Persist browser preference so future runs use the same browser
        try:
            from instagram_mcp_server.session_state import write_source_state

            write_source_state(profile_dir, preferred_browser=browser_id)
            print(f"   ✓ Browser preference saved: {profile.name}")
        except Exception:
            pass  # Non-critical — cookies are the primary auth artifact
        print("   ✓ You can now run the MCP server.")
        return True
    else:
        print("   ✗ Failed to save cookies.")
        return False


# ─── CDP process detection (Chromium-based only) ───────────────────────────
def find_browser_with_cdp(browser_id: str) -> int | None:
    """Find a running browser process with CDP (remote debugging) enabled.

    Only works for Chromium-based browsers.

    Args:
        browser_id: Browser identifier

    Returns:
        PID if found, None otherwise
    """
    profile = BROWSER_REGISTRY.get(browser_id)
    if profile is None:
        return None

    if profile.engine != "chromium":
        return None

    pattern = profile.cdp_process_pattern
    if not pattern:
        return None

    return _find_process_unix(pattern)


def _find_process_unix(pattern: str) -> int | None:
    """Find a process matching a pattern on Unix systems."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            return int(pids[0]) if pids else None
        return None
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        return None


def find_any_browser_with_cdp() -> tuple[str, int] | None:
    """Find ANY Chromium-based browser running with CDP enabled.

    Scans all Chromium-based browsers in registry priority order.

    Returns:
        (browser_id, pid) tuple, or None
    """
    for browser_id, profile in BROWSER_REGISTRY.items():
        if profile.engine != "chromium":
            continue
        pid = find_browser_with_cdp(browser_id)
        if pid is not None:
            return (browser_id, pid)
    return None


# ─── Manual cookie import guide ────────────────────────────────────────────
def manual_cookie_import_guide() -> None:
    """Print instructions for manual cookie import from any browser."""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  Instagram Cookie Import - Manual Method                         ║
╠══════════════════════════════════════════════════════════════════╣
║  When automated import fails, follow these steps:                ║
║                                                                  ║
║  1. Open Instagram in your browser:                              ║
║     https://www.instagram.com/                                   ║
║                                                                  ║
║  2. Log in normally (complete any 2FA/captcha)                   ║
║                                                                  ║
║  3. Install a cookie editor extension:                           ║
║     - EditThisCookie (Chrome Web Store)                          ║
║     - Cookie Editor (Firefox Add-ons)                            ║
║                                                                  ║
║  4. On Instagram, click the cookie editor extension              ║
║                                                                  ║
║  5. Export cookies as JSON                                       ║
║                                                                  ║
║  6. Save to: ~/.instagram-mcp/profile/cookies.json               ║
║                                                                  ║
║  7. Run the MCP server again                                     ║
║                                                                  ║
║  Required cookies: sessionid, csrftoken                          ║
╚══════════════════════════════════════════════════════════════════╝
""")


# ─── Load or import (auto) ────────────────────────────────────────────────
def load_cookies_from_file(cookie_file: Path) -> dict[str, str] | None:
    """Load Instagram cookies from JSON file.

    Supports three formats:
    1. {"cookies": [{"name": "x", "value": "y", ...}], "imported_from": "zen"}
    2. {"sessionid": "...", "csrftoken": "..."} (flat key-value)
    3. [{"name": "x", "value": "y", "domain": "..."}] (browser export list)
    """
    if not cookie_file.exists():
        return None
    try:
        with open(cookie_file) as f:
            data = json.load(f)
        if isinstance(data, dict):
            if "cookies" in data:
                cookies = {}
                for cookie in data["cookies"]:
                    if cookie.get("name") in INSTAGRAM_COOKIES:
                        cookies[cookie["name"]] = cookie["value"]
                return cookies if cookies else None
            else:
                return {k: v for k, v in data.items() if k in INSTAGRAM_COOKIES}
        elif isinstance(data, list):
            # Browser export format: list of cookie dicts
            cookies = {}
            for cookie in data:
                name = cookie.get("name")
                if name in INSTAGRAM_COOKIES:
                    cookies[name] = cookie.get("value", "")
            return cookies if cookies else None
        return None
    except (json.JSONDecodeError, IOError) as e:
        logger.debug("Failed to load cookies: %s", e)
        return None


def get_saved_browser_preference(cookie_file: Path) -> str | None:
    """Read the browser that was used to create this cookie file.

    Returns the ``imported_from`` field from cookies.json, or None.
    This survives even when the cookies themselves are expired/invalid.
    """
    if not cookie_file.exists():
        return None
    try:
        with open(cookie_file) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get("imported_from")
    except (json.JSONDecodeError, IOError):
        pass
    return None


def load_or_import_cookies(
    profile_dir: Path | None = None,
    browser_id: str | None = None,
) -> dict[str, str] | None:
    """Load existing cookies or attempt to import them.

    Priority:
    1. Load from existing cookies.json file
    2. Auto-extract from specified browser (or detected)
    3. Return None (user needs to import manually)

    Args:
        profile_dir: Target profile directory
        browser_id: Specific browser to extract from

    Returns:
        Cookie dict, or None
    """
    if profile_dir is None:
        profile_dir = Path.home() / ".instagram-mcp" / "profile"

    cookie_file = auth_root_dir(profile_dir) / "cookies.json"
    cookies = load_cookies_from_file(cookie_file)
    if cookies:
        logger.info("Loaded %d cookies from %s", len(cookies), cookie_file)
        is_valid, missing = validate_cookies(cookies)
        if not is_valid:
            logger.warning("Missing required cookies: %s", missing)
            return None
        return cookies

    # Try extraction from specified or previously-used browser
    cookie_file = auth_root_dir(profile_dir) / "cookies.json"
    saved_browser = browser_id or get_saved_browser_preference(cookie_file)

    if saved_browser and saved_browser in BROWSER_REGISTRY:
        cookies = extract_cookies_from_browser(saved_browser)
        if cookies:
            is_valid, missing = validate_cookies(cookies)
            if is_valid:
                if save_cookies_to_profile(
                    cookies, profile_dir, source_browser=saved_browser
                ):
                    logger.info(
                        "Re-imported cookies from saved browser: %s", saved_browser
                    )
                    return cookies

    # Fall back to detecting installed browsers in registry order
    for bid, _ in detect_installed_browsers():
        cookies = extract_cookies_from_browser(bid)
        if cookies:
            is_valid, missing = validate_cookies(cookies)
            if is_valid:
                if save_cookies_to_profile(cookies, profile_dir, source_browser=bid):
                    logger.info("Auto-extracted cookies from %s", bid)
                    return cookies

    return None


# ─── Legacy Brave compatibility ───────────────────────────────────────────
def get_brave_cookie_db() -> Path | None:
    """Legacy: Find Brave browser's cookie database. Kept for backward compat."""
    return find_browser_cookie_db("brave")


def extract_instagram_cookies() -> dict[str, str] | None:
    """Legacy: Extract Instagram cookies from Brave. Kept for backward compat."""
    return extract_cookies_from_browser("brave")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = import_cookies_interactive()
    sys.exit(0 if success else 1)
