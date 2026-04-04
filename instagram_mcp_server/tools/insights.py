"""
Instagram Business/Creator insights tools.

Uses innerText extraction for resilient insights data capture
from the Professional Dashboard.

Note: Professional Dashboard is only available for Business and Creator accounts.
"""

import logging
from typing import Any

from fastmcp import Context, FastMCP

from instagram_mcp_server.constants import TOOL_TIMEOUT_SECONDS
from instagram_mcp_server.core.exceptions import AuthenticationError
from instagram_mcp_server.dependencies import get_ready_extractor, handle_auth_error
from instagram_mcp_server.error_handler import raise_tool_error
from instagram_mcp_server.scraping.extractor import _RATE_LIMITED_MSG
from instagram_mcp_server.scraping.link_metadata import Reference

logger = logging.getLogger(__name__)

_DASHBOARD_URL = "https://www.instagram.com/accounts/insights/"

_DASHBOARD_TAB_SELECTORS = {
    "audience": '[data-tab-id="audience"], button:has-text("Audience"), [aria-label*="Audience"]',
    "content": '[data-tab-id="content"], button:has-text("Content"), [aria-label*="Content"]',
    "activity": '[data-tab-id="activity"], button:has-text("Activity"), [aria-label*="Activity"]',
}

_TAB_MARKERS = {
    "audience": ["Top locations", "Age range", "Gender"],
    "content": ["Top content", "Content type", "Media type"],
    "activity": ["Profile visits", "Website taps", "Emails"],
}

_TAB_URLS = {
    "audience": f"{_DASHBOARD_URL}?show_tab=audience",
    "content": f"{_DASHBOARD_URL}?show_tab=content",
    "activity": f"{_DASHBOARD_URL}?show_tab=activity",
}


def register_insights_tools(mcp: FastMCP) -> None:
    """Register all insights-related tools with the MCP server."""

    async def _navigate_to_dashboard_tab(
        extractor: Any, tab: str, ctx: Context
    ) -> None:
        """Navigate to a specific tab in the Professional Dashboard.

        Navigates to the dashboard, then switches tabs via URL params or button clicks.
        Modifies the extractor's page in-place. Does NOT return a URL — callers
        should extract text from the already-loaded page rather than re-navigating.
        """
        await extractor._navigate_to_page(_DASHBOARD_URL)

        if tab == "overview":
            return

        tab_url = _TAB_URLS.get(tab, _DASHBOARD_URL)
        await extractor._page.goto(
            tab_url, wait_until="domcontentloaded", timeout=30000
        )

        markers = _TAB_MARKERS.get(tab, [])

        try:
            await extractor._page.wait_for_function(
                """(markers) => {
                    const text = (document.querySelector('main') || document.body).innerText || '';
                    return markers.some(m => text.includes(m));
                }""",
                arg=markers,
                timeout=10000,
            )
            logger.info("Tab '%s' verified via content markers", tab)
        except Exception:
            selector = _DASHBOARD_TAB_SELECTORS.get(tab, "")
            if selector:
                try:
                    tab_button = extractor._page.locator(selector).first
                    await tab_button.wait_for(state="visible", timeout=5000)
                    await tab_button.click()
                    await extractor._page.wait_for_function(
                        """(markers) => {
                            const text = (document.querySelector('main') || document.body).innerText || '';
                            return markers.some(m => text.includes(m));
                        }""",
                        arg=markers,
                        timeout=10000,
                    )
                    logger.info("Tab '%s' switched via button click", tab)
                except Exception:
                    logger.warning(
                        "Tab '%s' verification failed after click attempt", tab
                    )

    async def _extract_insight(
        extractor: Any, tab: str, ctx: Context, section_name: str, progress_msg: str
    ) -> dict[str, Any]:
        """Shared extraction flow for all insight tabs."""
        await ctx.report_progress(progress=0, total=100, message=progress_msg)

        await _navigate_to_dashboard_tab(extractor, tab, ctx)
        extracted = await extractor.extract_current_page(section_name=section_name)

        sections: dict[str, str] = {}
        references: dict[str, list[Reference]] = {}
        if extracted.text and extracted.text != _RATE_LIMITED_MSG:
            sections[section_name] = extracted.text
            if extracted.references:
                references[section_name] = extracted.references

        await ctx.report_progress(progress=100, total=100, message="Complete")

        result: dict[str, Any] = {
            "url": extractor._page.url,
            "sections": sections,
        }
        if references:
            result["references"] = references
        return result

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Business Insights",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"insights", "scraping"},
    )
    async def get_business_insights(
        ctx: Context,
        time_range: str = "7d",
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get Business/Creator account insights from Professional Dashboard.

        Note: Professional Dashboard is only available for Business and Creator accounts.

        Args:
            ctx: FastMCP context for progress reporting
            time_range: Time range for insights data (7d, 30d, 90d). Default: "7d"

        Returns:
            Dict with url, sections (name -> raw text), and optional references.
            The LLM should parse the raw text in each section.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_business_insights"
            )
            logger.info("Scraping business insights (time_range=%s)", time_range)
            return await _extract_insight(
                extractor,
                "overview",
                ctx,
                "overview",
                "Navigating to Professional Dashboard",
            )

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_business_insights")
        except Exception as e:
            raise_tool_error(e, "get_business_insights")

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Audience Insights",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"insights", "scraping"},
    )
    async def get_audience_insights(
        ctx: Context,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get audience demographics from Professional Dashboard.

        Note: Professional Dashboard is only available for Business and Creator accounts.

        Args:
            ctx: FastMCP context for progress reporting

        Returns:
            Dict with url, sections (name -> raw text), and optional references.
            The LLM should parse the raw text to extract audience demographics.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_audience_insights"
            )
            logger.info("Scraping audience insights")
            return await _extract_insight(
                extractor,
                "audience",
                ctx,
                "audience",
                "Navigating to audience tab",
            )

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_audience_insights")
        except Exception as e:
            raise_tool_error(e, "get_audience_insights")

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Content Insights",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"insights", "scraping"},
    )
    async def get_content_insights(
        ctx: Context,
        time_range: str = "30d",
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get content performance insights from Professional Dashboard.

        Note: Professional Dashboard is only available for Business and Creator accounts.

        Args:
            ctx: FastMCP context for progress reporting
            time_range: Time range for insights data (7d, 30d, 90d). Default: "30d"

        Returns:
            Dict with url, sections (name -> raw text), and optional references.
            The LLM should parse the raw text to extract content performance data.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_content_insights"
            )
            logger.info("Scraping content insights (time_range=%s)", time_range)
            return await _extract_insight(
                extractor,
                "content",
                ctx,
                "content",
                "Navigating to content tab",
            )

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_content_insights")
        except Exception as e:
            raise_tool_error(e, "get_content_insights")

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Activity Insights",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"insights", "scraping"},
    )
    async def get_activity_insights(
        ctx: Context,
        time_range: str = "7d",
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get profile activity insights from Professional Dashboard.

        Note: Professional Dashboard is only available for Business and Creator accounts.

        Args:
            ctx: FastMCP context for progress reporting
            time_range: Time range for insights data (7d, 30d, 90d). Default: "7d"

        Returns:
            Dict with url, sections (name -> raw text), and optional references.
            The LLM should parse the raw text to extract profile activity data.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_activity_insights"
            )
            logger.info("Scraping activity insights (time_range=%s)", time_range)
            return await _extract_insight(
                extractor,
                "activity",
                ctx,
                "activity",
                "Navigating to activity tab",
            )

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_activity_insights")
        except Exception as e:
            raise_tool_error(e, "get_activity_insights")
