import json
from unittest.mock import MagicMock

import pytest

from instagram_mcp_server.bootstrap import (
    AuthState,
    _force_move_auth_state_aside,
    ensure_tool_ready_or_raise,
    get_bootstrap_state,
    get_runtime_policy,
    initialize_bootstrap,
    invalidate_auth_and_trigger_relogin,
    reset_bootstrap_for_testing,
    SetupState,
    start_background_browser_setup_if_needed,
)
from instagram_mcp_server.exceptions import (
    AuthenticationInProgressError,
    AuthenticationStartedError,
    DockerHostLoginRequiredError,
)
from instagram_mcp_server.session_state import (
    portable_cookie_path,
    source_state_path,
)


class TestBootstrap:
    async def test_managed_startup_sets_ready(self):
        initialize_bootstrap("managed")
        await start_background_browser_setup_if_needed()
        state = get_bootstrap_state()
        assert state.setup_state is SetupState.READY

    async def test_setup_is_always_ready(self, monkeypatch):
        monkeypatch.setattr("instagram_mcp_server.bootstrap._auth_ready", lambda: True)
        initialize_bootstrap("managed")
        await ensure_tool_ready_or_raise("search_posts")

    async def test_missing_auth_starts_login(self, monkeypatch):
        async def fake_start_login(ctx=None) -> None:
            raise AuthenticationStartedError("No valid Instagram session was found.")

        monkeypatch.setattr("instagram_mcp_server.bootstrap._auth_ready", lambda: False)
        monkeypatch.setattr(
            "instagram_mcp_server.bootstrap._start_login_if_needed", fake_start_login
        )
        initialize_bootstrap("managed")
        with pytest.raises(AuthenticationStartedError):
            await ensure_tool_ready_or_raise("get_user_profile")

    async def test_login_in_progress_reuses_existing_session(self, monkeypatch):
        monkeypatch.setattr("instagram_mcp_server.bootstrap._auth_ready", lambda: False)
        initialize_bootstrap("managed")
        state = get_bootstrap_state()
        state.auth_state = AuthState.IN_PROGRESS
        state.login_task = MagicMock(done=lambda: False)
        with pytest.raises(AuthenticationInProgressError):
            await ensure_tool_ready_or_raise("get_user_profile")

    async def test_docker_requires_host_login(self, monkeypatch):
        monkeypatch.setattr("instagram_mcp_server.bootstrap._auth_ready", lambda: False)
        initialize_bootstrap("docker")
        with pytest.raises(DockerHostLoginRequiredError):
            await ensure_tool_ready_or_raise("search_posts")

    def test_reset_bootstrap_clears_state(self):
        initialize_bootstrap("managed")
        reset_bootstrap_for_testing()
        state = get_bootstrap_state()
        assert state.runtime_policy is None
        assert state.initialized is False

    def test_reset_bootstrap_is_idempotent(self):
        initialize_bootstrap("managed")
        reset_bootstrap_for_testing()
        reset_bootstrap_for_testing()
        state = get_bootstrap_state()
        assert state.runtime_policy is None

    def test_reset_bootstrap_cancels_running_tasks(self):
        setup_task = MagicMock()
        setup_task.done.return_value = False
        login_task = MagicMock()
        login_task.done.return_value = False
        initialize_bootstrap("managed")
        state = get_bootstrap_state()
        state.setup_task = setup_task
        state.login_task = login_task
        reset_bootstrap_for_testing()
        setup_task.cancel.assert_called_once_with()
        login_task.cancel.assert_called_once_with()

    def test_browser_setup_is_always_ready(self):
        from instagram_mcp_server.bootstrap import browser_setup_ready

        assert browser_setup_ready() is True

    def test_runtime_policy_uses_initialized_value(self):
        initialize_bootstrap("managed")
        assert get_runtime_policy() == "managed"


def _make_auth_ready(profile_dir):
    """Create all files that _auth_ready() checks."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "Default").mkdir(parents=True, exist_ok=True)
    (profile_dir / "Default" / "Cookies").write_text("placeholder")
    cookie_path = portable_cookie_path(profile_dir)
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(
        json.dumps([{"name": "sessionid", "domain": ".instagram.com"}])
    )
    source_state_path(profile_dir).write_text(
        json.dumps(
            {
                "version": 1,
                "source_runtime_id": "macos-arm64-host",
                "login_generation": "gen-1",
                "created_at": "2026-03-12T17:00:00Z",
                "profile_path": str(profile_dir),
                "cookies_path": str(cookie_path),
            }
        )
    )


class TestInvalidateAuthAndTriggerRelogin:
    async def test_force_moves_files_and_starts_login(
        self, isolate_profile_dir, monkeypatch
    ):
        _make_auth_ready(isolate_profile_dir)

        async def fake_login_flow():
            return None

        monkeypatch.setattr(
            "instagram_mcp_server.bootstrap._run_login_flow", fake_login_flow
        )
        initialize_bootstrap("managed")

        with pytest.raises(AuthenticationStartedError, match="Session expired"):
            await invalidate_auth_and_trigger_relogin()

        assert not isolate_profile_dir.exists()
        assert not portable_cookie_path(isolate_profile_dir).exists()
        assert not source_state_path(isolate_profile_dir).exists()
        state = get_bootstrap_state()
        assert state.auth_state is AuthState.STARTING
        assert state.login_task is not None

    async def test_login_in_progress_does_not_move_files(
        self, isolate_profile_dir, monkeypatch
    ):
        _make_auth_ready(isolate_profile_dir)
        initialize_bootstrap("managed")
        state = get_bootstrap_state()
        state.login_task = MagicMock(done=lambda: False)
        state.auth_state = AuthState.IN_PROGRESS
        with pytest.raises(AuthenticationInProgressError):
            await invalidate_auth_and_trigger_relogin()
        assert isolate_profile_dir.exists()
        assert portable_cookie_path(isolate_profile_dir).exists()

    def test_force_move_skips_auth_ready_guard(self, isolate_profile_dir):
        _make_auth_ready(isolate_profile_dir)
        from instagram_mcp_server.bootstrap import _auth_ready

        assert _auth_ready()
        _force_move_auth_state_aside()
        assert not isolate_profile_dir.exists()
        assert not portable_cookie_path(isolate_profile_dir).exists()
        assert not source_state_path(isolate_profile_dir).exists()
