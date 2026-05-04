import pytest

from instagram_mcp_server.config.schema import (
    AppConfig,
    ConfigurationError,
    CookieConfig,
    ServerConfig,
)


class TestCookieConfig:
    def test_defaults(self):
        config = CookieConfig()
        assert config.profile_dir == "~/.instagram-mcp/profile"

    def test_validate_passes(self):
        CookieConfig().validate()


class TestServerConfig:
    def test_defaults(self):
        config = ServerConfig()
        assert config.transport == "stdio"
        assert config.port == 8000


class TestAppConfig:
    def test_validate_invalid_port(self):
        config = AppConfig()
        config.server.port = 99999
        with pytest.raises(ConfigurationError):
            config.validate()


class TestConfigSingleton:
    def test_get_config_returns_same_instance(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["instagram-mcp-server"])
        from instagram_mcp_server.config import get_config

        config = get_config()
        assert config is get_config()
        from instagram_mcp_server.config import reset_config

        reset_config()
        re_loaded = get_config()
        assert re_loaded is not config
