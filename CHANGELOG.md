# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-04-02

### Added

- **CDP mode is now the default authentication method** - Connects directly to your running Brave browser instead of launching automated browsers
- `--cdp` and `--no-cdp` CLI flags for explicit CDP mode control
- `--cdp-port` CLI flag for custom CDP debugging port (default: 9222)
- `CDPConnectionError` exception with helpful setup instructions
- Windows support for CDP mode via `tasklist` process detection
- `instagram-launch-brave` script for easy Brave browser launch with remote debugging
- Comprehensive CDP mode documentation in `docs/CDP_MODE.md`

### Changed

- **BREAKING:** CDP mode enabled by default (set `INSTAGRAM_USE_CDP_MODE=0` to use legacy mode)
- Error messages now reference `instagram_mcp_server` instead of `linkedin_mcp_server`
- Browser setup skipped in lifespan when using CDP mode for faster startup
- `--status` check uses CDP when available
- Bootstrap login flow guides users to launch Brave with CDP

### Fixed

- All copy-paste errors from LinkedIn fork (task names, error messages, comments)
- IPv6 issues with CDP connection (uses 127.0.0.1 instead of localhost)
- Documentation mismatch for CDP default value
- BrowserManager.close() not properly closing context

### Deprecated

- Legacy browser automation mode (use CDP mode instead)
- Cookie import via SQLite extraction (use CDP mode)

### Migration Guide

If you're using the old browser automation mode:

1. Launch Brave with remote debugging:
   ```bash
   uv run instagram-launch-brave
   ```

2. Log into Instagram in the Brave window

3. Run the MCP server (automatically connects via CDP):
   ```bash
   uv run -m instagram_mcp_server
   ```

Your Instagram session will persist across server restarts.

To disable CDP mode and use legacy browser automation:
```bash
uv run -m instagram_mcp_server --no-cdp
```

## [1.0.0] - 2026-02-XX

### Added

- Initial release
- Instagram profile, posts, reels, stories scraping
- Business/Creator insights
- Search functionality (users, hashtags, locations)
- Direct messaging tools
- Account actions (follow, like, comment, save)
- Persistent browser profile authentication
- Docker support
