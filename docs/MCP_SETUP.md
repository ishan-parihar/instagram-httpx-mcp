# Instagram MCP Server - Setup Guide

Complete setup guide for Instagram MCP Server with all features.

---

## Quick Start (5 minutes)

### 1. Install uv (Python package manager)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Configure MCP Client

**Claude Desktop** (`claude_desktop_config.json`):

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

**Other MCP Clients:**

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

### 3. First-Time Login (CDP Mode)

```bash
# 1. Close all Brave windows
pkill brave && sleep 2

# 2. Launch Brave with remote debugging
uv run instagram-launch-brave

# 3. Log into Instagram in the Brave window

# 4. Run MCP server (automatically connects to Brave)
uv run -m instagram_mcp_server
```

**Done!** You can now use Instagram tools.

---

## Configuration Options

### Environment Variables

```bash
# CDP Mode (default: enabled)
export INSTAGRAM_USE_CDP_MODE=1

# Custom CDP port (default: 9222)
export INSTAGRAM_CDP_PORT=9222

# Gemini API Key (for AI analysis tools)
export GEMINI_API_KEY="your_api_key_here"

# Log level (DEBUG, INFO, WARNING, ERROR)
export INSTAGRAM_LOG_LEVEL=WARNING
```

### CLI Options

```bash
# Login (create session)
uv run -m instagram_mcp_server --login

# Check session status
uv run -m instagram_mcp_server --status

# Logout (clear session)
uv run -m instagram_mcp_server --logout

# Debug mode (show browser window)
uv run -m instagram_mcp_server --no-headless --log-level DEBUG

# Disable CDP mode (use legacy browser automation)
uv run -m instagram_mcp_server --no-cdp

# Custom timeout (milliseconds)
uv run -m instagram_mcp_server --timeout 10000
```

---

## Feature Setup

### CDP Mode (Recommended)

**What it does:** Connects to your existing Brave browser instead of launching new instances.

**Benefits:**
- ✅ No bot detection (uses your real browser fingerprint)
- ✅ No captchas (reuses existing Instagram session)
- ✅ Fast startup (~0.1s vs ~5s)
- ✅ Persistent session

**Setup:**
```bash
# 1. Launch Brave with CDP
brave-browser --remote-debugging-port=9222

# 2. Log into Instagram

# 3. Run MCP server (auto-detects Brave)
uv run -m instagram_mcp_server
```

**Verify CDP is working:**
```bash
# Should show Brave processes with --remote-debugging-port=9222
pgrep -af "brave.*remote-debugging-port"
```

---

### Gemini AI Analysis (Optional)

**What it does:** Fast AI-powered reel analysis (3x faster than local transcription).

**Cost:** ~$0.00017 per reel (extremely cheap).

**Setup:**

1. **Get API Key:**
   - Go to https://aistudio.google.com/app/apikey
   - Click "Create API Key"
   - Copy the key

2. **Configure:**

   **Option A: Environment Variable**
   ```bash
   export GEMINI_API_KEY="your_key_here"
   ```

   **Option B: Edit Config File**
   ```python
   # instagram_mcp_server/tools/gemini_analysis.py
   GEMINI_API_KEY = "your_key_here"
   ```

3. **Test:**
   ```
   Analyze this reel: https://www.instagram.com/reel/ABC123/
   ```

**Tools:**
- `analyze_reel_with_gemini` - Single reel analysis
- `bulk_analyze_reels_with_gemini` - Bulk analysis

**Analysis Types:**
- `summary` - Quick overview (15s)
- `transcript` - Full transcription (20s)
- `topics` - Keywords/hashtags (18s)
- `quotes` - Notable quotes (18s)
- `full` - Comprehensive (25s)

---

### Local Transcription (Alternative to Gemini)

**What it does:** Download reels and generate SRT subtitles using local Whisper.

**Benefits:**
- ✅ Free (no API costs)
- ✅ Private (local processing)
- ✅ Accurate word-level timestamps

**Requirements:**
- `caption` command (from openscript project)
- `ffmpeg` installed
- Conda env `whisper-hindi`

**Setup:**
```bash
# Install ffmpeg
sudo apt install ffmpeg  # Ubuntu
brew install ffmpeg      # macOS

# Verify caption command
which caption

# Test
caption test_video.mp4
```

**Tools:**
- `transcribe_user_reels` - Bulk transcription
- `transcribe_reel` - Single reel

**Performance:** 30-60s per reel (CPU)

---

## Docker Setup

```bash
# Build
docker build -t instagram-mcp-server .

# Run with CDP mode
docker run -it --rm \
  -e INSTAGRAM_USE_CDP_MODE=1 \
  -v ~/.instagram-mcp:/root/.instagram-mcp \
  instagram-mcp-server

# Or via docker-compose
docker-compose up -d
```

**docker-compose.yml:**
```yaml
version: '3.8'
services:
  instagram-mcp:
    image: ghcr.io/ishan-parihar/instagram-mcp-server:latest
    environment:
      - INSTAGRAM_USE_CDP_MODE=1
      - GEMINI_API_KEY=your_key_here
    volumes:
      - ~/.instagram-mcp:/root/.instagram-mcp
    ports:
      - "8000:8000"
```

---

## Troubleshooting

### "No module named instagram_mcp_server"

```bash
# Reinstall
uv sync --reinstall
```

### "Brave not found"

```bash
# Install Brave
# Ubuntu
sudo apt install brave-browser

# macOS
brew install --cask brave-browser
```

### "caption command not found"

```bash
# Add to PATH
export PATH="/home/ishanp/bin:$PATH"

# Or use local transcription alternative
# (Gemini AI analysis doesn't require caption)
```

### "Gemini API key invalid"

```bash
# Get new key from https://aistudio.google.com/app/apikey
export GEMINI_API_KEY="new_key_here"
```

### "Rate limit exceeded"

Instagram may temporarily block requests.

**Solution:**
- Wait 5-10 minutes
- Use CDP mode (reduces detection)
- Reduce request frequency

### "Tool timeout"

```bash
# Increase timeout
uv run -m instagram_mcp_server --timeout 15000
```

---

## Verification

### Check Installation

```bash
# Version
uv run -m instagram_mcp_server --version

# Help
uv run -m instagram_mcp_server --help

# Status
uv run -m instagram_mcp_server --status
```

### Test Tools

```
# Profile
Get profile for @instagram

# Reels
Get 5 reels from @natgeo

# Analysis (if Gemini configured)
Analyze this reel: https://www.instagram.com/reel/ABC123/

# Transcription (if caption available)
Transcribe 3 reels from @username
```

---

## Configuration Reference

### Full MCP Config Example

```json
{
  "mcpServers": {
    "instagram": {
      "command": "uvx",
      "args": ["instagram-scraper-mcp"],
      "env": {
        "INSTAGRAM_USE_CDP_MODE": "1",
        "INSTAGRAM_CDP_PORT": "9222",
        "GEMINI_API_KEY": "your_key_here",
        "INSTAGRAM_LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

### All Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INSTAGRAM_USE_CDP_MODE` | `1` | Enable CDP mode (connect to existing Brave) |
| `INSTAGRAM_CDP_PORT` | `9222` | CDP debugging port |
| `GEMINI_API_KEY` | - | Google Gemini API key |
| `INSTAGRAM_LOG_LEVEL` | `WARNING` | Logging level |
| `INSTAGRAM_TIMEOUT` | `5000` | Browser timeout (ms) |
| `INSTAGRAM_USER_DATA_DIR` | `~/.instagram-mcp/profile` | Browser profile path |

---

## Next Steps

1. **Configure MCP client** (Claude Desktop, etc.)
2. **Login with CDP mode** (fastest, most reliable)
3. **Optional:** Get Gemini API key for AI analysis
4. **Start using tools!**

**Example prompts:**
- "Get the profile for @instagram"
- "Show me recent reels from @natgeo"
- "Analyze this reel: https://www.instagram.com/reel/ABC123/"
- "Transcribe 5 reels from @tech_channel"

---

## Support

- **Documentation:** `docs/` folder
- **Issues:** https://github.com/ishan-parihar/instagram-mcp-server/issues
- **CDP Mode:** `docs/CDP_MODE.md`
- **Transcription:** `docs/TRANSCRIPTION.md`
- **Gemini Analysis:** `docs/GEMINI_ANALYSIS.md`
