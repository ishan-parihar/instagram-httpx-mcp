"""Security-focused tests for browser profile/cookie persistence."""

import os
import stat
from unittest.mock import AsyncMock, MagicMock

import pytest

from instagram_mcp_server.core.browser import BrowserManager, _harden_instagram_tree


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX permission bits are not portable on Windows"
)
def test_harden_instagram_tree_hardens_dirs(tmp_path):
    root = tmp_path / ".instagram-mcp"
    profile = root / "profile"

    root.mkdir(mode=0o755)
    profile.mkdir(mode=0o755)

    _harden_instagram_tree(profile)

    assert _mode(root) == 0o700
    assert _mode(profile) == 0o700


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX permission bits are not portable on Windows"
)
def test_harden_instagram_tree_does_not_harden_unrelated_parent(tmp_path):
    parent = tmp_path / "custom"
    profile = parent / ".instagram-mcp" / "profile"

    parent.mkdir(mode=0o755)
    profile.mkdir(parents=True, mode=0o755)

    _harden_instagram_tree(profile)

    assert _mode(parent) == 0o755
    assert _mode(profile) == 0o700
    assert _mode(profile.parent) == 0o700


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX permission bits are not portable on Windows"
)
def test_harden_instagram_tree_noop_outside_instagram(tmp_path):
    """Dirs that are not inside .instagram-mcp are left untouched."""
    unrelated = tmp_path / "other" / "data"
    unrelated.mkdir(parents=True, mode=0o755)

    _harden_instagram_tree(unrelated)

    assert _mode(unrelated) == 0o755
    assert _mode(unrelated.parent) == 0o755


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name == "nt", reason="POSIX permission bits are not portable on Windows"
)
async def test_export_cookies_writes_owner_only_file(tmp_path):
    manager = BrowserManager(user_data_dir=tmp_path / ".instagram-mcp" / "profile")
    manager._context = MagicMock()
    manager._context.cookies = AsyncMock(
        return_value=[
            {"name": "sessionid", "domain": ".instagram.com", "value": "secret-value"}
        ]
    )

    cookie_path = tmp_path / ".instagram-mcp" / "cookies.json"
    ok = await manager.export_cookies(cookie_path)

    assert ok is True
    assert cookie_path.exists()
    assert _mode(cookie_path.parent) == 0o700
    assert _mode(cookie_path) == 0o600


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name == "nt", reason="POSIX permission bits are not portable on Windows"
)
async def test_export_storage_state_hardens_file(tmp_path):
    manager = BrowserManager(user_data_dir=tmp_path / ".instagram-mcp" / "profile")
    manager._context = MagicMock()

    storage_path = tmp_path / ".instagram-mcp" / "storage.json"

    async def _fake_storage_state(*, path, indexed_db=True):
        path.write_text("{}")

    manager._context.storage_state = _fake_storage_state

    ok = await manager.export_storage_state(storage_path)

    assert ok is True
    assert storage_path.exists()
    assert _mode(storage_path.parent) == 0o700
    assert _mode(storage_path) == 0o600
