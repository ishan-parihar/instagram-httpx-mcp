# Instagram MCP Server

<p align="left">
  <a href="https://pypi.org/project/instagram-scraper-mcp/" target="_blank"><img src="https://img.shields.io/pypi/v/instagram-scraper-mcp?color=blue" alt="PyPI Version"></a>
  <a href="https://github.com/stickerdaniel/instagram-mcp-server/actions/workflows/ci.yml" target="_blank"><img src="https://github.com/stickerdaniel/instagram-mcp-server/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI Status"></a>
  <a href="https://github.com/stickerdaniel/instagram-mcp-server/actions/workflows/release.yml" target="_blank"><img src="https://github.com/stickerdaniel/instagram-mcp-server/actions/workflows/release.yml/badge.svg?branch=main" alt="Release"></a>
  <a href="https://github.com/stickerdaniel/instagram-mcp-server/blob/main/LICENSE" target="_blank"><img src="https://img.shields.io/badge/License-Apache%202.0-%233fb950?labelColor=32383f" alt="License"></a>
  <img src="https://img.shields.io/badge/Python-3.12+-blue" alt="Python Version">
</p>

Model Context Protocol server that lets AI assistants (Claude, Cursor, Windsurf, etc.) interact with Instagram. Access profiles, posts, reels, Business/Creator insights, direct messages, and account actions with zero UX interference.

## Quick Start

**1. Install**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2. Configure your MCP client**

Add to your client's MCP config (see [full configs below](#mcp-client-configuration)):

```json
{
  "mcpServers": {
    "instagram": {
      "command": "uvx",
      "args": ["instagram-scraper-mcp"]
    }
  }
}
```

**3. First tool call**

Restart your MCP client. On the first Instagram tool call, a login window opens if no session exists. Log in once, and cookies persist across restarts.

## How It Works

The server extracts your Instagram session cookies from your running browser (Chrome, Firefox, Edge, Brave, and 10+ others), saves them to `~/.instagram-mcp/profile/`, and launches an **isolated Patchright Chromium instance** with those cookies injected. All scraping happens in this separate browser. Your primary browser is never touched.

```
Your browser (logged into Instagram)
  → cookies detected from SQLite cookie store
  → saved to ~/.instagram-mcp/profile/
  → injected into isolated Patchright Chromium
  → all scraping runs in isolated instance
```

## Authentication

| Scenario | What happens |
|----------|-------------|
| **First run** | Login browser window opens. Complete sign-in (including 2FA if needed). |
| **Subsequent runs** | Cookies loaded from `~/.instagram-mcp/profile/` automatically. |
| **Session expired** | Re-run `uvx instagram-scraper-mcp --login` to re-authenticate. |
| **Clear session** | Run `uvx instagram-scraper-mcp --logout` to remove stored cookies. |

> Instagram may request a login confirmation on your mobile app for new sessions. If you encounter a captcha, use `--login` to solve it manually in the opened browser.

## MCP Client Configuration

### Claude Desktop

```json
{
  "mcpServers": {
    "instagram": {
      "command": "uvx",
      "args": ["instagram-scraper-mcp"]
    }
  }
}
```

### Cursor

```json
{
  "mcpServers": {
    "instagram": {
      "command": "uvx",
      "args": ["instagram-scraper-mcp"]
    }
  }
}
```

### Windsurf

```json
{
  "mcpServers": {
    "instagram": {
      "command": "uvx",
      "args": ["instagram-scraper-mcp"]
    }
  }
}
```

### Generic MCP Client

```json
{
  "mcpServers": {
    "instagram": {
      "command": "uv",
      "args": ["run", "-m", "instagram_mcp_server"]
    }
  }
}
```

## Tools

### Profile & Content (6 tools)

| Tool | Description |
|------|-------------|
| `get_user_profile` | Get profile info. Optional sections: posts, reels, stories, highlights, followers, following |
| `get_user_posts` | Get structured post data (ID, shortcode, URL, thumbnail, media type) |
| `get_user_reels` | Get reels with IDs, URLs, thumbnails, and view counts |
| `get_user_stories` | Get active stories with media URLs and expiry timestamps |
| `get_user_highlights` | Get story highlights with titles, cover URLs, and highlight IDs |
| `get_post_details` | Get detailed post/reel info including caption, engagement, audio info, and optional comments |

### Search & Discovery (5 tools)

| Tool | Description |
|------|-------------|
| `search_users` | Search for users by name or keywords |
| `search_hashtags` | Search for hashtags by keywords |
| `search_locations` | Search for Instagram locations |
| `get_hashtag_posts` | Get posts for a given hashtag |
| `get_location_posts` | Get posts tagged at a specific location |

### Messaging & Actions (9 tools)

| Tool | Description |
|------|-------------|
| `get_direct_inbox` | List recent DM conversations |
| `get_dm_conversation` | Read a specific DM conversation |
| `send_dm` | Send a direct message to a user |
| `follow_user` | Follow a user (sends follow request for private accounts) |
| `unfollow_user` | Unfollow a user |
| `like_post` | Like a post or reel |
| `unlike_post` | Unlike a post or reel |
| `save_post` | Save a post or reel to a collection |
| `comment_on_post` | Post a comment on a post or reel |

### Business/Creator Insights (4 tools)

> All require a Business or Creator account (accessed via Professional Dashboard).

| Tool | Description |
|------|-------------|
| `get_business_insights` | Get reach, impressions, and engagement metrics |
| `get_audience_insights` | Get audience demographics |
| `get_content_insights` | Get content performance data |
| `get_activity_insights` | Get profile activity metrics |

### Transcription (2 tools)

> Requires the `caption` CLI tool (Whisper-based). See [docs/TRANSCRIPTION.md](docs/TRANSCRIPTION.md).

| Tool | Description |
|------|-------------|
| `transcribe_user_reels` | Download and transcribe multiple reels to SRT subtitles |
| `transcribe_reel` | Transcribe a single reel by URL to SRT |

### AI Analysis (2 tools)

> Requires `GEMINI_API_KEY` environment variable. Uses Google Gemini 2.0 Flash. See [docs/GEMINI_ANALYSIS.md](docs/GEMINI_ANALYSIS.md).

| Tool | Description |
|------|-------------|
| `analyze_reel_with_gemini` | Multimodal reel analysis (summary, transcript, topics, quotes) |
| `bulk_analyze_reels_with_gemini` | Analyze multiple reels with Gemini AI |

## Optional Features

### Gemini AI Analysis

Set your API key before starting the server:

```bash
export GEMINI_API_KEY="your-api-key"
uvx instagram-scraper-mcp
```

### Local Transcription

Install the [`caption`](https://github.com/oliverguhr/caption) CLI tool for local Whisper-based transcription. Alternatively, use `analyze_reel_with_gemini` for AI transcription without local dependencies.

### CDP Mode (Opt-in)

Connect directly to a running Brave browser via Chrome DevTools Protocol instead of using cookie import:

```bash
# Start Brave with remote debugging
brave --remote-debugging-port=9222

# Connect via CLI flag
uvx instagram-scraper-mcp --cdp

# Or via environment variable
export INSTAGRAM_USE_CDP_MODE=1
uvx instagram-scraper-mcp
```

See [docs/CDP_MODE.md](docs/CDP_MODE.md) for details.

## Docker Setup

Docker runs headless, so create a browser profile on your host first and mount it.

**1. Create profile (one-time)**

```bash
uvx instagram-scraper-mcp --login
```

**2. Configure MCP client**

```json
{
  "mcpServers": {
    "instagram": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "${HOME}/.instagram-mcp:/home/pwuser/.instagram-mcp",
        "stickerdaniel/instagram-mcp-server:latest"
      ]
    }
  }
}
```

See [docs/docker-hub.md](docs/docker-hub.md) for full Docker documentation including HTTP mode and troubleshooting.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **No cookies found** | Ensure you are logged into Instagram in a supported browser. Run `uvx instagram-scraper-mcp --login` to open the login flow. |
| **Session expired** | Re-run `uvx instagram-scraper-mcp --login` to create a fresh session. |
| **Captcha challenge** | Use `--login` to solve it manually in the opened browser. |
| **Page timeout** | Increase timeout: `--timeout 10000` (or higher for slow connections). |
| **Chrome not found** | Set custom path: `--chrome-path /path/to/chrome` or `CHROME_PATH` env var. |
| **Multiple Instagram sessions** | Instagram may conflict with concurrent sessions. Log out of other active sessions. |
| **Browser profile location** | Profile stored at `~/.instagram-mcp/profile/`. Use `--logout` to clear. |

For debug output, add `--log-level DEBUG`. Use `--no-headless` to watch browser actions.

## Development & Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture guidelines, development commands, and the contribution workflow. Please [open an issue](https://github.com/stickerdaniel/instagram-mcp-server/issues) before submitting a PR.

## License & Acknowledgements

Licensed under the [Apache 2.0 License](LICENSE).

Built with [FastMCP](https://gofastmcp.com/) and [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python).

Use in accordance with [Instagram's Terms of Use](https://help.instagram.com/581066165581870). Web scraping may violate Instagram's terms. This tool is for personal use only.
