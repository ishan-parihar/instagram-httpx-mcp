from instagram_mcp_server.setup import run_profile_creation


class TestRunProfileCreation:
    def test_returns_true_on_success(self, monkeypatch):
        monkeypatch.setattr(
            "instagram_mcp_server.setup.import_cookies_interactive",
            lambda browser_id=None: True,
        )
        monkeypatch.setattr(
            "instagram_mcp_server.setup.choose_browser_interactive",
            lambda: "zen",
        )
        result = run_profile_creation("/tmp/test-profile", browser_id="zen")
        assert result is True

    def test_returns_false_on_failure(self, monkeypatch):
        monkeypatch.setattr(
            "instagram_mcp_server.setup.import_cookies_interactive",
            lambda browser_id=None: False,
        )
        monkeypatch.setattr(
            "instagram_mcp_server.setup.choose_browser_interactive",
            lambda: "zen",
        )
        result = run_profile_creation("/tmp/test-profile", browser_id="zen")
        assert result is False
