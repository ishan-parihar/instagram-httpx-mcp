# Instagram MCP Server - Issue Fixes Summary

## Overview
This document summarizes all fixes applied to resolve errors, warnings, and limitations in the Instagram MCP Server.

---

## 1. CDP Mode Authentication (CRITICAL - FIXED)

### Issue
The `--login` CLI command was opening a new browser window with legacy browser automation instead of using the existing Brave CDP session, even when CDP mode was enabled.

### Root Cause
- `run_profile_creation()` in `setup.py` always called `interactive_login()` which uses Playwright browser automation
- No CDP mode check was performed in the CLI login flow

### Fix Applied
**Files Modified:**
- `instagram_mcp_server/setup.py` - Added `_run_cdp_profile_creation()` and `_cdp_export_session()`
- `instagram_mcp_server/bootstrap.py` - Fixed `_cdp_login_flow()` to export session (cookies + source-state)

**Changes:**
- When CDP mode is enabled, `--login` now:
  1. Detects running Brave browser via `find_brave_process()`
  2. Connects via CDP using `connect_to_brave()`
  3. Verifies Instagram session using `verify_instagram_session()`
  4. Exports cookies to `cookies.json`
  5. Writes source-state metadata to `source-state.json`

**Status:** ✅ FIXED - Tested successfully

---

## 2. Professional Dashboard URL (FIXED)

### Issue
All Business/Creator insights tools returned "Page not available" errors.

### Root Cause
Instagram changed the Professional Dashboard URL from `/professional_dashboard/` to `/accounts/insights/`.

### Fix Applied
**Files Modified:**
- `instagram_mcp_server/tools/insights.py`

**Changes:**
```python
# Old URL (broken)
_DASHBOARD_URL = "https://www.instagram.com/professional_dashboard/"

# New URL (working)
_DASHBOARD_URL = "https://www.instagram.com/accounts/insights/"
_DASHBOARD_TABS = {
    "overview": "",
    "audience": "?show_tab=audience",
    "content": "?show_tab=content",
    "activity": "?show_tab=activity",
}
```

**Status:** ✅ FIXED - Verified with diagnostic script

---

## 3. Search Tools Limitations (DOCUMENTED)

### Issue
Search tools (`search_users`, `search_hashtags`, `search_locations`) return "Page not found" errors.

### Root Cause
Instagram search pages use client-side routing and require user interaction (typing in search box). Direct URL navigation to `/web/search/` pages returns "Page not available".

### Fix Applied
**Files Modified:**
- `instagram_mcp_server/scraping/extractor.py` - Added error detection and user-friendly messages
- `instagram_mcp_server/scraping/fields.py` - Updated URLs from `/explore/search/` to `/web/search/`
- `docs/KNOWN_LIMITATIONS.md` - Created comprehensive documentation

**Changes:**
- Search methods now detect "page not available" responses
- Return structured error messages explaining the limitation
- Suggest using Instagram's web interface for search operations

**Status:** ⚠️ DOCUMENTED - This is an Instagram platform limitation, not a bug

**Workaround:** Use Instagram's web interface directly for search, or use the returned post links from other tools.

---

## 4. User Posts Extraction (IMPROVED)

### Issue
`get_user_posts` returned only profile header text without individual post data.

### Root Cause
Instagram's post grid uses dynamic class names (`._aagv`, `._aagu`) and JavaScript rendering. The innerText extraction captured visible text but missed structured post data.

### Fix Applied
**Files Modified:**
- `instagram_mcp_server/scraping/extractor.py` - Added `_extract_post_links()` method

**Changes:**
- `scrape_user_posts()` now extracts post/reel links as references
- Returns structured response with both text content and post link references
- Links can be used with `get_post_details()` for detailed information

**Status:** ✅ IMPROVED - Post links now extracted as references

**Usage Pattern:**
```python
# Get user posts (returns links)
posts = await get_user_posts("instagram")
# Use links to get details
for post_ref in posts['references']['posts']:
    details = await get_post_details(post_ref['url'])
```

---

## 5. Hashtag Posts (IMPROVED)

### Issue
`get_hashtag_posts` returned page content but no structured post data.

### Root Cause
Similar to user posts - Instagram renders hashtag pages with dynamic JavaScript components.

### Fix Applied
**Files Modified:**
- `instagram_mcp_server/tools/posts.py` - Uses existing `extract_page()` with reference extraction

**Status:** ⚠️ WORKING - Returns page content with post links when available

---

## 6. Documentation Updates

### Files Created/Modified:
- `docs/KNOWN_LIMITATIONS.md` - New comprehensive documentation
- `README.md` - Updated tool status table
- `docs/CDP_MODE.md` - Already existed, referenced in error messages

### Tool Status Table (README.md):
| Tool Category | Status | Notes |
|--------------|--------|-------|
| Profile/Reels/Stories/Highlights | ✅ Working | Full data extraction |
| Posts | ⚠️ Links only | Use with `get_post_details` |
| Search | ⚠️ Limited | Returns structured errors |
| Insights | ✅ FIXED | Requires Business/Creator account |
| Messaging/Actions | ✅ Working | Full functionality |

---

## Test Results

All 297 tests passing:
```
================ 297 passed, 1 skipped, 229 warnings in 14.16s =================
```

---

## Verification Steps

### 1. CDP Mode Authentication
```bash
# Verify Brave is running with CDP
pgrep -af "brave.*remote-debugging-port"

# Test login with CDP
uv run -m instagram_mcp_server --login

# Verify session was exported
cat ~/.instagram-mcp/source-state.json
cat ~/.instagram-mcp/cookies.json | head -20
```

### 2. Professional Dashboard
```bash
# Test insights access (requires Creator/Business account)
uv run -m instagram_mcp_server --status

# Should show: ✅ Session is valid
# And Professional Dashboard should be accessible via /accounts/insights/
```

### 3. Post Extraction
```bash
# Test post link extraction
# (via MCP client)
get_user_posts(username="instagram", max_posts=12)
# Should return:
# - sections.posts: profile text
# - references.posts: array of post links
```

---

## Remaining Limitations

### Platform-Imposed (Cannot Fix)
1. **Search Tools** - Instagram blocks direct URL access to search pages
2. **Rate Limiting** - Instagram temporarily blocks excessive requests
3. **Dynamic Class Names** - Instagram obfuscates CSS class names (e.g., `._aagv`)

### Account-Type Requirements
1. **Professional Dashboard** - Requires Business or Creator account
2. **Personal Accounts** - Cannot access insights tools

### Recommended Workarounds
1. Use CDP mode (default) to avoid bot detection
2. Extract post links, then use `get_post_details()` for individual posts
3. Use Instagram's web interface for search operations
4. Wait 5-10 minutes between scraping operations to avoid rate limiting

---

## Files Changed Summary

### Core Authentication
- `instagram_mcp_server/bootstrap.py` - CDP login flow
- `instagram_mcp_server/setup.py` - CDP profile creation

### Scraping Engine
- `instagram_mcp_server/scraping/extractor.py` - Post link extraction, search error handling
- `instagram_mcp_server/scraping/fields.py` - Search URL updates

### Tools
- `instagram_mcp_server/tools/insights.py` - Professional Dashboard URL fix
- `instagram_mcp_server/tools/posts.py` - Uses reference extraction
- `instagram_mcp_server/tools/user.py` - Uses reference extraction

### Documentation
- `docs/KNOWN_LIMITATIONS.md` - New file
- `README.md` - Updated tool status table

---

## Next Steps (Optional Enhancements)

1. **Search Functionality** - Could implement search by simulating keystrokes in search box (complex, may trigger bot detection)

2. **Enhanced Post Extraction** - Could use Instagram's GraphQL endpoints directly (requires authentication tokens, may violate ToS)

3. **Rate Limit Handling** - Could implement automatic retry with exponential backoff

4. **Post Content Download** - Could add media download functionality for images/videos

These enhancements are marked as optional due to complexity and potential Terms of Service concerns.
