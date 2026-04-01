# CDP Mode: Direct Brave Browser Connection

## Overview

CDP (Chrome DevTools Protocol) mode connects the MCP server directly to your running Brave browser instead of launching automated browsers. This eliminates Instagram's bot detection because:

1. **Real browser fingerprint** - Uses your actual browser, not an automated instance
2. **Existing session** - Reuses your logged-in Instagram session
3. **No automation flags** - No `navigator.webdriver` or other automation indicators

## How It Works

```
┌─────────────────┐     CDP      ┌──────────────────┐
│   Brave Browser │◄────────────►│   MCP Server     │
│   (User-owned)  │  Port 9222   │   (This tool)    │
│                 │              │                  │
│ - Instagram tab │              │ - Scraping tools │
│ - Your cookies  │              │ - Data extraction│
│ - Real session  │              │                  │
└─────────────────┘              └──────────────────┘
```

## Setup Instructions

### Step 1: Launch Brave with Remote Debugging

**Option A: Use the launcher script (Recommended)**

```bash
uv run instagram-launch-brave
```

This will:
- Find your Brave browser installation
- Launch with remote debugging on port 9222
- Open Instagram automatically
- Create a dedicated profile at `~/.instagram-mcp/brave-profile`

**Option B: Manual launch**

```bash
brave-browser \
  --remote-debugging-port=9222 \
  --user-data-dir=~/.instagram-mcp/brave-profile \
  https://www.instagram.com/
```

**Option C: Add to Brave desktop shortcut**

Edit your Brave launcher to include:
```
--remote-debugging-port=9222 --user-data-dir=~/.instagram-mcp/brave-profile
```

### Step 2: Log Into Instagram

In the Brave window that opens, log into Instagram normally:
1. Enter your username and password
2. Complete any 2FA challenges
3. Verify you can see your feed
4. Keep the browser window open

### Step 3: Run the MCP Server

```bash
uv run -m instagram_mcp_server
```

The server will automatically:
1. Detect the running Brave process
2. Connect via CDP on port 9222
3. Verify your Instagram session
4. Begin serving MCP requests

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `INSTAGRAM_USE_CDP_MODE` | Enable CDP mode (`1`, `true`, `yes`, `on`) | `1` (enabled by default) |
| `INSTAGRAM_DEBUGGING_PORT` | CDP debugging port | `9222` |

### Example: Custom Port

```bash
export INSTAGRAM_DEBUGGING_PORT=9223
brave-browser --remote-debugging-port=9223
uv run -m instagram_mcp_server
```

### Disable CDP Mode (Use Legacy Mode)

```bash
export INSTAGRAM_USE_CDP_MODE=0
uv run -m instagram_mcp_server
```

Note: Legacy mode is deprecated and will be removed in v2.0.

## Troubleshooting

### "Brave browser not found"

**Solution:** Ensure Brave is running with the `--remote-debugging-port` flag.

Check running processes:
```bash
ps aux | grep brave | grep remote-debugging
```

You should see something like:
```
brave-browser --remote-debugging-port=9222 ...
```

If not, launch Brave with:
```bash
uv run instagram-launch-brave
```

### "No valid Instagram session found"

**Solution:** Log into Instagram in the Brave browser window.

1. Open `https://www.instagram.com/` in Brave
2. Log in with your credentials
3. Complete any 2FA challenges
4. Verify you can see your feed
5. Restart the MCP server

### Connection refused on port 9222

**Solution:** Port may be in use or Brave not running.

1. Check if port is in use: `lsof -i :9222`
2. Kill conflicting process or use different port:
   ```bash
   export INSTAGRAM_DEBUGGING_PORT=9223
   ```
3. Restart Brave with correct port

### CDP connection works but scraping fails

**Solution:** Instagram may have rate-limited your account.

1. Wait a few hours
2. Try accessing Instagram manually in Brave
3. Reduce scraping frequency
4. Check if you can load Instagram in the Brave window

### Brave closes when I stop the MCP server

**Solution:** This shouldn't happen - CDP mode only disconnects from Brave, it doesn't close it. If Brave is closing, check:
1. You didn't accidentally close the Brave window
2. No other process is terminating Brave
3. Brave isn't running in a temporary session

## Security Considerations

- **Localhost only** - CDP connection is only accessible from your machine
- **Your cookies never leave** - All data stays on your machine
- **MCP server only accesses Instagram tabs** - Other browser data is not accessed
- **Close Brave when not in use** - Disconnects the MCP server

## Performance Benefits

| Metric | Legacy Mode | CDP Mode |
|--------|-------------|----------|
| Startup time | ~5 seconds | ~0.1 seconds |
| Memory usage | ~200 MB | ~0 MB (reuses existing) |
| Bot detection | High risk | No risk |
| Session persistence | Per-run | Persistent |
| Captcha challenges | Common | None |

## Migration from Legacy Mode

If you're using the old browser automation mode (`--login`):

1. **Stop using `--login` flag** - No longer needed
2. **Launch Brave with CDP** (see above)
3. **Log into Instagram once** - Session persists
4. **Run MCP server normally** - Automatically uses CDP mode

Your session will persist across:
- MCP server restarts
- System reboots (if Brave saves session)
- Browser updates

## Docker Users

CDP mode works with Docker by connecting to Brave running on the host machine.

### Host Setup

1. Launch Brave on host with remote debugging:
   ```bash
   brave-browser --remote-debugging-port=9222
   ```

2. Log into Instagram in Brave

3. Run Docker container with host network access:
   ```bash
   docker run --network host instagram-mcp-server
   ```

The container can now connect to Brave on the host via `localhost:9222`.

## Advanced Usage

### Multiple Browser Profiles

You can run multiple Brave instances with different profiles:

```bash
# Profile 1 - Personal account
brave-browser --remote-debugging-port=9222 --user-data-dir=~/.instagram-mcp/profile1

# Profile 2 - Business account  
brave-browser --remote-debugging-port=9223 --user-data-dir=~/.instagram-mcp/profile2
```

Then connect to specific profiles:
```bash
export INSTAGRAM_DEBUGGING_PORT=9222  # or 9223
uv run -m instagram_mcp_server
```

### Headless Brave (Advanced)

For server deployments, Brave can run headless:

```bash
brave-browser \
  --remote-debugging-port=9222 \
  --headless=new \
  --user-data-dir=~/.instagram-mcp/brave-profile
```

Note: Headless mode may be detected by Instagram. Use with caution.

## Technical Details

### What is CDP?

Chrome DevTools Protocol (CDP) is a JSON-based protocol that allows external tools to inspect, control, and automate Chromium-based browsers. It's the same protocol used by:
- Chrome DevTools
- Playwright/Puppeteer
- Browser automation tools

### Why CDP Mode Works

Instagram's bot detection looks for:
- Automated browser fingerprints (Playwright Chromium)
- `navigator.webdriver` flags
- Unusual browser configurations
- Missing browser history/cookies

CDP mode bypasses all of these because:
- Uses your real browser with your real fingerprint
- No automation flags (you manually logged in)
- Full browser history and cookies present
- Normal user behavior patterns

### Connection Lifecycle

1. **Discovery** - MCP server finds Brave process via `pgrep`
2. **Connection** - Connects via CDP WebSocket
3. **Verification** - Checks Instagram session validity
4. **Extraction** - Uses browser context for scraping
5. **Disconnect** - Cleans up on server shutdown (Brave stays open)

## Support

For issues or questions:
- Check existing issues: https://github.com/ishan-parihar/instagram-mcp-server/issues
- File a new issue with logs
- Include your Brave version and OS
