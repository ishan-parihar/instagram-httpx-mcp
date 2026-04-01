"""
Cookie import for Instagram MCP Server.

Primary authentication method: Import cookies from user's browser session.
This bypasses Instagram's aggressive bot detection that blocks automated browsers.
"""

import json
import logging
import sqlite3
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

INSTAGRAM_COOKIES = {"sessionid", "csrftoken", "ds_user_id", "ig_did", "mid"}
REQUIRED_COOKIES = {"sessionid", "csrftoken"}


def get_brave_cookie_db() -> Path | None:
    """Find Brave browser's cookie database."""
    possible_paths = [
        Path.home() / ".config/BraveSoftware/Brave-Browser/Default/Cookies",
        Path.home() / ".config/brave/Default/Cookies",
        Path.home()
        / ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/Default/Cookies",
    ]

    for path in possible_paths:
        if path.exists():
            return path
    return None


def extract_instagram_cookies() -> dict[str, str] | None:
    """Extract Instagram cookies from Brave browser's SQLite database."""
    cookie_db = get_brave_cookie_db()
    if not cookie_db:
        logger.debug("Brave cookie database not found")
        return None

    # Copy to temp file since SQLite DB is locked by browser
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        tmp_path = Path(tmp.name)

    try:
        import shutil

        shutil.copy2(cookie_db, tmp_path)

        conn = sqlite3.connect(str(tmp_path))
        cursor = conn.cursor()

        # Query Instagram cookies
        cursor.execute("""
            SELECT name, value, encrypted_value 
            FROM cookies 
            WHERE host_key LIKE '%instagram.com%'
        """)

        cookies = {}
        for row in cursor.fetchall():
            name, value, encrypted_value = row

            if name in INSTAGRAM_COOKIES:
                if value:
                    cookies[name] = value
                elif encrypted_value:
                    # Encrypted cookies need decryption (Linux only)
                    logger.debug(f"Skipping encrypted cookie: {name}")

        conn.close()

        if cookies:
            return cookies
        return None

    finally:
        tmp_path.unlink(missing_ok=True)


def load_cookies_from_file(cookie_file: Path) -> dict[str, str] | None:
    """Load Instagram cookies from JSON file."""
    if not cookie_file.exists():
        return None

    try:
        with open(cookie_file) as f:
            data = json.load(f)

        # Handle both raw cookie dict and structured format
        if isinstance(data, dict):
            if "cookies" in data:
                # Structured format
                cookies = {}
                for cookie in data["cookies"]:
                    if cookie.get("name") in INSTAGRAM_COOKIES:
                        cookies[cookie["name"]] = cookie["value"]
                return cookies if cookies else None
            else:
                # Raw cookie dict
                return {k: v for k, v in data.items() if k in INSTAGRAM_COOKIES}

        return None
    except (json.JSONDecodeError, IOError) as e:
        logger.debug(f"Failed to load cookies: {e}")
        return None


def save_cookies_to_file(cookies: dict[str, str], profile_dir: Path) -> bool:
    """Save cookies to the MCP profile directory."""
    cookie_file = profile_dir / "cookies.json"

    try:
        cookie_data = {
            "cookies": [
                {
                    "name": name,
                    "value": value,
                    "domain": ".instagram.com",
                    "path": "/",
                    "secure": True,
                }
                for name, value in cookies.items()
            ],
            "imported_from": "brave_auto",
        }

        cookie_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cookie_file, "w") as f:
            json.dump(cookie_data, f, indent=2)

        # Set restrictive permissions
        cookie_file.chmod(0o600)

        return True
    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")
        return False


def manual_cookie_import_guide() -> None:
    """Print instructions for manual cookie import."""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  Instagram Cookie Import - Manual Method                         ║
╠══════════════════════════════════════════════════════════════════╣
║  When automated browser login fails due to bot detection,       ║
║  follow these steps to import cookies from your browser:        ║
║                                                                  ║
║  1. Open Instagram in your regular Brave/Chrome browser         ║
║     https://www.instagram.com/                                  ║
║                                                                  ║
║  2. Log in normally (complete any 2FA/captcha)                  ║
║                                                                  ║
║  3. Install a cookie editor extension:                          ║
║     - EditThisCookie (Chrome/Brave Web Store)                   ║
║     - Cookie Editor (Firefox Add-ons)                           ║
║                                                                  ║
║  4. On Instagram, click the cookie editor extension             ║
║                                                                  ║
║  5. Export cookies as JSON                                      ║
║                                                                  ║
║  6. Save to: ~/.instagram-mcp/profile/cookies.json              ║
║                                                                  ║
║  7. Run the MCP server again                                    ║
║                                                                  ║
║  Required cookies: sessionid, csrftoken                         ║
╚══════════════════════════════════════════════════════════════════╝
""")


def import_cookies_interactive() -> bool:
    """Interactive cookie import flow."""
    print("\nAttempting to import cookies from Brave browser...")

    cookies = extract_instagram_cookies()

    if not cookies:
        print("   Could not find Instagram cookies in Brave.")
        print("   Please log into Instagram in Brave first, then try again.")
        manual_cookie_import_guide()
        return False

    print(f"   Found {len(cookies)} Instagram cookies: {list(cookies.keys())}")

    # Check for required cookies
    missing = REQUIRED_COOKIES - set(cookies.keys())

    if missing:
        print(f"   Warning: Missing required cookies: {missing}")
        print("   You may need to log in again in Brave.")
        return False

    profile_dir = Path.home() / ".instagram-mcp" / "profile"

    if save_cookies_to_file(cookies, profile_dir):
        print(f"   ✓ Cookies saved to: {profile_dir}/cookies.json")
        print("   ✓ You can now run the MCP server.")
        return True
    else:
        print("   Failed to save cookies.")
        return False


def load_or_import_cookies(profile_dir: Path | None = None) -> dict[str, str] | None:
    """Load existing cookies or attempt to import them.

    Priority:
    1. Load from existing cookies.json file
    2. Auto-extract from Brave browser
    3. Return None (user needs to import manually)

    Returns:
        Cookie dict with sessionid and csrftoken, or None if not available
    """
    if profile_dir is None:
        profile_dir = Path.home() / ".instagram-mcp" / "profile"

    cookie_file = profile_dir / "cookies.json"

    # Try to load existing cookies
    cookies = load_cookies_from_file(cookie_file)
    if cookies:
        logger.info(f"Loaded {len(cookies)} cookies from {cookie_file}")
        missing = REQUIRED_COOKIES - set(cookies.keys())
        if missing:
            logger.warning(f"Missing required cookies: {missing}")
            return None
        return cookies

    # Try to auto-extract from Brave
    logger.info("No cookies.json found, attempting Brave extraction...")
    cookies = extract_instagram_cookies()

    if cookies:
        missing = REQUIRED_COOKIES - set(cookies.keys())
        if not missing:
            if save_cookies_to_file(cookies, profile_dir):
                logger.info(f"Auto-extracted and saved cookies to {cookie_file}")
                return cookies

    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = import_cookies_interactive()
    exit(0 if success else 1)
