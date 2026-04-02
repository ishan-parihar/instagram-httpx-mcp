# Known Scraping Limitations

This document describes known limitations of Instagram scraping due to Instagram's anti-bot measures and dynamic page structure.

## Search Tools

**Affected tools:**
- `search_users`
- `search_hashtags`
- `search_locations`

**Current behavior:** Search tools now use interactive search box simulation instead of direct URL navigation. The implementation:
1. Navigates to Instagram home page
2. Clicks the search box
3. Types the search query
4. Selects the appropriate tab (Users/Hashtags/Places)
5. Extracts search results

**Limitations:**
- Requires being logged into Instagram
- Results may be limited compared to the web interface
- Search box interaction may fail if Instagram changes their UI structure

**Error messages:**
```
Could not interact with Instagram search box. Ensure you are logged in and try again.
```

**Technical details:**
- Search uses client-side interaction via Playwright browser automation
- Search results are extracted from the rendered page after interaction
- Tab selection (Users/Hashtags/Places) is attempted but may not always succeed

## User Posts (Partial Data)

**Affected tools:**
- `get_user_posts`

**Issue:** Instagram's post grid uses dynamic loading with obfuscated class names. While post links are extracted, detailed post metadata (captions, like counts, timestamps) may not be captured through text extraction alone.

**Current behavior:**
- Post/reel links are extracted and returned as references
- Page text content includes profile info but limited post details
- Individual post data requires navigating to each post URL

**Workaround:** Use `get_post_details` with the post URLs returned from `get_user_posts` to retrieve detailed information for specific posts.

**Technical details:**
- Posts are loaded via infinite scroll with dynamic class names (e.g., `._aagv`, `._aagu`)
- Post metadata is embedded in JavaScript-rendered components
- innerText extraction captures visible text but misses structured data

## Hashtag Posts (Limited Data)

**Affected tools:**
- `get_hashtag_posts`

**Issue:** Hashtag pages may render in "Instagram Lite" mode with reduced content. Post extraction relies on link references rather than full content scraping.

**Current behavior:**
- Hashtag page loads but may show simplified layout
- Post links are extracted when available
- Full post details require individual post navigation

**Workaround:** Use the returned post links with `get_post_details` for detailed information.

## Business/Creator Insights (Account Type Required)

**Affected tools:**
- `get_business_insights`
- `get_audience_insights`
- `get_content_insights`
- `get_activity_insights`

**Issue:** Professional Dashboard tools require a Business or Creator Instagram account. Personal accounts cannot access these insights.

**Error message:**
```
Professional Dashboard not accessible
```

**Workaround:** Convert your Instagram account to a Business or Creator account to access professional dashboard insights.

## Rate Limiting

Instagram may temporarily block scraping operations that make too many requests in a short period.

**Symptoms:**
- Pages return rate limit messages
- Tools return `[Rate limited]` errors
- Temporary inability to access Instagram content

**Mitigation:**
- Wait 5-10 minutes between scraping operations
- Use CDP mode (default) which uses your existing browser session
- Avoid scraping large numbers of posts/users in rapid succession

## Recommendations

1. **Use CDP mode** (enabled by default) - Connects to your existing Brave browser session to avoid bot detection

2. **Extract references** - Many tools return post/profile links as references. Use these for follow-up operations.

3. **Batch operations carefully** - Add delays between scraping operations to avoid rate limiting

4. **Check error responses** - Tools return structured error information in `section_errors` when scraping fails

5. **Use the right tool for the job:**
   - Profile data: `get_user_profile` ✓ (works well)
   - Reels: `get_user_reels` ✓ (works well)
   - Stories: `get_user_stories` ✓ (works well)
   - Highlights: `get_user_highlights` ✓ (works well)
   - Posts: `get_user_posts` ⚠ (links only, use with `get_post_details`)
   - Search: `search_*` ⚠ (requires login, results may vary)
   - Insights: `get_*_insights` ⚠ (requires Business/Creator account)

## Reporting Issues

If you encounter scraping issues not documented here:

1. Check if you're logged into Instagram in your Brave browser
2. Verify Brave is running with `--remote-debugging-port=9222`
3. Check for rate limiting (wait and retry)
4. Review the structured error response for details
5. File an issue with the error message and affected tool name
