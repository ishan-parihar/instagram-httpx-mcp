"""Tests for the InstagramExtractor scraping engine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from instagram_mcp_server.callbacks import ProgressCallback
from instagram_mcp_server.core.exceptions import (
    AuthenticationError,
    InstagramScraperException,
)
from instagram_mcp_server.scraping.connection import (
    _extract_action_area,
    detect_connection_state,
)
from instagram_mcp_server.scraping.extractor import (
    ExtractedSection,
    InstagramExtractor,
    _RATE_LIMITED_MSG,
    _truncate_instagram_noise,
    strip_instagram_noise,
)
from instagram_mcp_server.scraping.link_metadata import Reference


def extracted(
    text: str,
    references: list[Reference] | None = None,
    error: dict | None = None,
) -> ExtractedSection:
    """Create an ExtractedSection for tests."""
    return ExtractedSection(text=text, references=references or [], error=error)


@pytest.fixture
def mock_page():
    """Create a mock Patchright page."""
    page = MagicMock()
    page.goto = AsyncMock()
    page.title = AsyncMock(return_value="Instagram")
    page.wait_for_selector = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.evaluate = AsyncMock(
        return_value={"source": "root", "text": "Sample page text", "references": []}
    )
    page.url = "https://www.instagram.com/testuser/"
    page.locator = MagicMock()
    # Default: no modals, no CAPTCHA
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=0)
    mock_locator.is_visible = AsyncMock(return_value=False)
    mock_locator.first = mock_locator
    mock_locator.inner_text = AsyncMock(return_value="normal page content")
    page.locator.return_value = mock_locator
    page.main_frame = object()
    page.on = MagicMock()
    page.remove_listener = MagicMock()
    return page


class TestExtractPage:
    async def test_extract_page_returns_text(self, mock_page):
        mock_page.evaluate = AsyncMock(
            return_value={
                "source": "root",
                "text": "Sample profile text",
                "references": [],
            }
        )
        extractor = InstagramExtractor(mock_page)
        # Patch scroll_to_bottom and detect_rate_limit to avoid complex mock chains
        with (
            patch(
                "instagram_mcp_server.scraping.extractor.scroll_to_bottom",
                new_callable=AsyncMock,
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.detect_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.handle_modal_close",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = await extractor.extract_page(
                "https://www.instagram.com/testuser/",
                section_name="main_profile",
            )

        assert result.text == "Sample profile text"
        assert result.references == []
        mock_page.goto.assert_awaited_once()

    async def test_root_content_filters_empty_href_before_resolution(self, mock_page):
        mock_page.evaluate = AsyncMock(
            return_value={
                "source": "root",
                "text": "Sample profile text",
                "references": [],
            }
        )
        extractor = InstagramExtractor(mock_page)

        await extractor._extract_root_content(["main"])

        await_args = mock_page.evaluate.await_args
        assert await_args is not None
        script = await_args.args[0]
        assert "MAX_HEADING_CONTAINERS = 300" in script
        assert "MAX_REFERENCE_ANCHORS = 500" in script
        assert "const getPreviousHeading = node =>" in script
        assert "index < 3" in script
        assert "if (!rawHref || rawHref === '#')" in script
        assert ".slice(0, MAX_REFERENCE_ANCHORS)" in script
        assert "in_list" not in script
        assert ".filter(Boolean);" in script

    async def test_extract_page_returns_empty_on_failure(self, mock_page):
        mock_page.goto = AsyncMock(side_effect=Exception("Network error"))
        extractor = InstagramExtractor(mock_page)

        with patch(
            "instagram_mcp_server.scraping.extractor.build_issue_diagnostics",
            return_value={"issue_template_path": "/tmp/issue.md"},
        ):
            result = await extractor.extract_page(
                "https://www.instagram.com/bad/",
                section_name="main_profile",
            )
        assert result.text == ""
        assert result.references == []
        assert result.error == {"issue_template_path": "/tmp/issue.md"}

    async def test_extract_page_raises_auth_error_for_account_picker(self, mock_page):
        mock_page.goto = AsyncMock(side_effect=Exception("net::ERR_TOO_MANY_REDIRECTS"))
        extractor = InstagramExtractor(mock_page)

        with (
            patch(
                "instagram_mcp_server.scraping.extractor.detect_auth_barrier",
                new_callable=AsyncMock,
                return_value="auth barrier text: welcome back + sign in using another account",
            ),
            pytest.raises(AuthenticationError, match="--login"),
        ):
            await extractor.extract_page(
                "https://www.instagram.com/testuser/",
                section_name="main_profile",
            )

    async def test_rate_limit_detected(self, mock_page):
        from instagram_mcp_server.core.exceptions import RateLimitError

        extractor = InstagramExtractor(mock_page)
        with (
            patch(
                "instagram_mcp_server.scraping.extractor.detect_rate_limit",
                new_callable=AsyncMock,
                side_effect=RateLimitError("Rate limited", suggested_wait_time=3600),
            ),
            pytest.raises(RateLimitError),
        ):
            await extractor.extract_page(
                "https://www.instagram.com/testuser/",
                section_name="main_profile",
            )

    async def test_returns_rate_limited_msg_after_retry(self, mock_page):
        """When both attempts return only noise, surface rate limit message."""
        noise_only = (
            "Sorry, something went wrong\n\n"
            "We restrict certain activity that violates our terms\n\n"
            "About\nHelp\nPrivacy\nTerms"
        )
        mock_page.evaluate = AsyncMock(
            return_value={"source": "root", "text": noise_only, "references": []}
        )
        extractor = InstagramExtractor(mock_page)
        with (
            patch(
                "instagram_mcp_server.scraping.extractor.scroll_to_bottom",
                new_callable=AsyncMock,
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.detect_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.handle_modal_close",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await extractor.extract_page(
                "https://www.instagram.com/testuser/details/experience/",
                section_name="experience",
            )

        assert result.text == _RATE_LIMITED_MSG
        # goto called twice (initial + retry)
        assert mock_page.goto.await_count == 2

    async def test_retry_succeeds_after_rate_limit(self, mock_page):
        """When first attempt is rate-limited but retry succeeds, return content."""
        noise_only = "More to explore\n\nAbout\nHelp\nPrivacy\nTerms"
        call_count = 0

        async def evaluate_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return noise_only
            return "Education\nTest University\n2020 – 2024"

        async def root_content_side_effect(*args, **kwargs):
            return {
                "source": "root",
                "text": await evaluate_side_effect(),
                "references": [],
            }

        mock_page.evaluate = AsyncMock(side_effect=root_content_side_effect)
        extractor = InstagramExtractor(mock_page)
        with (
            patch(
                "instagram_mcp_server.scraping.extractor.scroll_to_bottom",
                new_callable=AsyncMock,
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.detect_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.handle_modal_close",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await extractor.extract_page(
                "https://www.instagram.com/testuser/details/education/",
                section_name="education",
            )

        assert result.text == "Education\nTest University\n2020 – 2024"

    async def test_media_only_controls_are_not_misclassified_as_rate_limited(
        self, mock_page
    ):
        mock_page.evaluate = AsyncMock(
            return_value={
                "source": "root",
                "text": "Play\nLoaded: 100.00%\nRemaining time 0:07\nShow captions",
                "references": [],
            }
        )
        extractor = InstagramExtractor(mock_page)
        with (
            patch(
                "instagram_mcp_server.scraping.extractor.scroll_to_bottom",
                new_callable=AsyncMock,
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.detect_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.handle_modal_close",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = await extractor._extract_page_once(
                "https://www.instagram.com/testuser/recent-activity/all/",
                section_name="posts",
            )

        assert result.text == ""
        assert result.references == []


class TestNavigationDiagnostics:
    async def test_goto_with_auth_checks_raises_on_navigation_error(self, mock_page):
        extractor = InstagramExtractor(mock_page)

        mock_page.goto = AsyncMock(side_effect=Exception("net::ERR_TOO_MANY_REDIRECTS"))

        with (
            patch(
                "instagram_mcp_server.scraping.extractor.detect_auth_barrier",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(Exception, match="ERR_TOO_MANY_REDIRECTS"),
        ):
            await extractor._goto_with_auth_checks(
                "https://www.instagram.com/testuser/"
            )

    async def test_goto_with_auth_checks_unhooks_listener_on_auth_barrier(
        self, mock_page
    ):
        extractor = InstagramExtractor(mock_page)
        listener_events: list[str] = []

        def record_on(event_name, callback):
            listener_events.append(f"on:{event_name}")

        def record_remove(event_name, callback):
            listener_events.append(f"off:{event_name}")

        mock_page.on.side_effect = record_on
        mock_page.remove_listener.side_effect = record_remove

        with (
            patch(
                "instagram_mcp_server.scraping.extractor.detect_auth_barrier_quick",
                new_callable=AsyncMock,
                return_value="account picker",
            ),
            pytest.raises(AuthenticationError),
        ):
            await extractor._goto_with_auth_checks(
                "https://www.instagram.com/testuser/"
            )

        assert listener_events == [
            "on:framenavigated",
            "off:framenavigated",
        ]

    async def test_goto_with_auth_checks_records_original_failure(self, mock_page):
        extractor = InstagramExtractor(mock_page)
        mock_page.goto = AsyncMock(side_effect=Exception("net::ERR_TOO_MANY_REDIRECTS"))

        with (
            patch(
                "instagram_mcp_server.scraping.extractor.record_page_trace",
                new_callable=AsyncMock,
            ) as mock_trace,
            patch(
                "instagram_mcp_server.scraping.extractor.detect_auth_barrier",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(Exception, match="ERR_TOO_MANY_REDIRECTS"),
        ):
            await extractor._goto_with_auth_checks(
                "https://www.instagram.com/testuser/"
            )

        trace_steps = [call.args[1] for call in mock_trace.await_args_list]
        assert "extractor-navigation-error" in trace_steps

    async def test_goto_with_auth_checks_logs_failure_context(self, mock_page):
        extractor = InstagramExtractor(mock_page)
        mock_page.goto = AsyncMock(side_effect=Exception("net::ERR_TOO_MANY_REDIRECTS"))

        with (
            patch(
                "instagram_mcp_server.scraping.extractor.detect_auth_barrier",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                extractor,
                "_log_navigation_failure",
                new_callable=AsyncMock,
            ) as mock_log_failure,
            pytest.raises(Exception, match="ERR_TOO_MANY_REDIRECTS"),
        ):
            await extractor._goto_with_auth_checks(
                "https://www.instagram.com/testuser/"
            )

        mock_log_failure.assert_awaited_once()
        mock_page.on.assert_called_once()
        mock_page.remove_listener.assert_called_once()


class TestScrapeUserUrls:
    """Test that scrape_user visits the correct URLs per section set."""

    async def test_baseline_always_included(self, mock_page):
        """Passing only reels still visits main profile."""
        extractor = InstagramExtractor(mock_page)
        with (
            patch.object(
                extractor,
                "extract_page",
                new_callable=AsyncMock,
                return_value=extracted("text"),
            ) as mock_extract,
            patch(
                "instagram_mcp_server.scraping.extractor.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await extractor.scrape_user("testuser", {"reels"})

        urls = [call.args[0] for call in mock_extract.call_args_list]
        assert "main_profile" in result["sections"]
        assert any(u.endswith("/testuser/") for u in urls)
        assert any("/reels/" in u for u in urls)

    async def test_basic_info_only_visits_main_profile(self, mock_page):
        extractor = InstagramExtractor(mock_page)
        with (
            patch.object(
                extractor,
                "extract_page",
                new_callable=AsyncMock,
                return_value=extracted("profile text"),
            ) as mock_extract,
            patch(
                "instagram_mcp_server.scraping.extractor.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await extractor.scrape_user("testuser", {"main_profile"})

        urls = [call.args[0] for call in mock_extract.call_args_list]
        assert len(urls) == 1
        assert urls[0].endswith("/testuser/")
        assert set(result["sections"]) == {"main_profile"}

    async def test_scrape_user_returns_section_errors(self, mock_page):
        extractor = InstagramExtractor(mock_page)
        with (
            patch.object(
                extractor,
                "extract_page",
                new_callable=AsyncMock,
                side_effect=[
                    extracted("profile text"),
                    extracted("", error={"issue_template_path": "/tmp/issue.md"}),
                ],
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await extractor.scrape_user("testuser", {"posts"})

        assert result["sections"]["main_profile"] == "profile text"
        assert (
            result["section_errors"]["posts"]["issue_template_path"] == "/tmp/issue.md"
        )

    async def test_reels_tagged_visits_correct_urls(self, mock_page):
        extractor = InstagramExtractor(mock_page)
        with (
            patch.object(
                extractor,
                "extract_page",
                new_callable=AsyncMock,
                return_value=extracted("text"),
            ) as mock_extract,
            patch(
                "instagram_mcp_server.scraping.extractor.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await extractor.scrape_user(
                "testuser", {"main_profile", "reels", "tagged"}
            )

        urls = [call.args[0] for call in mock_extract.call_args_list]
        assert len(urls) == 3
        assert any(u.endswith("/testuser/") for u in urls)
        assert any("/reels/" in u for u in urls)
        assert any("/tagged/" in u for u in urls)
        assert set(result["sections"]) == {"main_profile", "reels", "tagged"}

    async def test_all_sections_visit_all_urls(self, mock_page):
        extractor = InstagramExtractor(mock_page)
        all_sections = {
            "main_profile",
            "posts",
            "reels",
            "tagged",
            "followers",
            "following",
        }
        with (
            patch.object(
                extractor,
                "extract_page",
                new_callable=AsyncMock,
                return_value=extracted("text"),
            ) as mock_extract,
            patch(
                "instagram_mcp_server.scraping.extractor.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await extractor.scrape_user("testuser", all_sections)

        page_urls = [call.args[0] for call in mock_extract.call_args_list]
        # Verify each expected suffix was navigated
        assert any(u.endswith("/testuser/") for u in page_urls)
        assert any("/reels/" in u for u in page_urls)
        assert any("/tagged/" in u for u in page_urls)
        assert any("/followers/" in u for u in page_urls)
        assert any("/following/" in u for u in page_urls)
        assert set(result["sections"]) == all_sections

    async def test_posts_visits_main_profile(self, mock_page):
        extractor = InstagramExtractor(mock_page)
        with (
            patch.object(
                extractor,
                "extract_page",
                new_callable=AsyncMock,
                return_value=extracted("Post 1\nPost 2"),
            ) as mock_extract,
            patch(
                "instagram_mcp_server.scraping.extractor.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await extractor.scrape_user("test-user", {"posts"})


class TestStripInstagramNoise:
    def test_strips_footer(self):
        text = "User bio here\n\nAbout\nHelp\nAPI\nJobs\nTerms"
        assert strip_instagram_noise(text) == "User bio here"

    def test_strips_footer_with_press_variant(self):
        text = "Profile content here\n\nAbout\nPress\nAPI\nJobs"
        assert strip_instagram_noise(text) == "Profile content here"

    def test_strips_sidebar_recommendations(self):
        text = "Feed post content\n\nSuggested for you\nRandom User\n1K followers"
        assert strip_instagram_noise(text) == "Feed post content"

    def test_strips_discover_more(self):
        text = "Post content\n\nDiscover more\nTrending posts"
        assert strip_instagram_noise(text) == "Post content"

    def test_picks_earliest_marker(self):
        text = "Content\n\nSuggested for you\nStuff\n\nAbout\nHelp\nMore stuff"
        assert strip_instagram_noise(text) == "Content"

    def test_no_noise_returns_unchanged(self):
        text = "Clean content with no Instagram chrome"
        assert strip_instagram_noise(text) == "Clean content with no Instagram chrome"

    def test_empty_string(self):
        assert strip_instagram_noise("") == ""

    def test_truncate_noise_preserves_media_controls_for_rate_limit_detection(self):
        text = "Play\nLoaded: 100.00%\nRemaining time 0:07\nShow captions"
        assert _truncate_instagram_noise(text) == text
        assert strip_instagram_noise(text) == ""

    def test_about_in_profile_content_not_stripped(self):
        """'About' followed by actual content (not footer links) should be preserved."""
        text = "About the author\nChair of the Foundation.\n\nFeatured\nPost"
        # This shouldn't be stripped because it doesn't match the footer pattern
        result = strip_instagram_noise(text)
        assert "About the author" in result

    def test_real_footer_with_meta(self):
        text = "Company info\n\nMeta\nAbout\nBlog\nHelp\nAPI\nJobs\nPrivacy\nTerms"
        assert strip_instagram_noise(text) == "Company info"

    def test_preserves_real_content(self):
        text = "Amazing sunset photo from my trip to Bali"
        assert strip_instagram_noise(text) == text

    def test_strips_media_controls_lines(self):
        text = (
            "Feed post number 1\n"
            "Play\n"
            "Loaded: 100.00%\n"
            "Remaining time 0:07\n"
            "Playback speed\n"
            "Actual post content\n"
            "Show captions\n"
            "Close modal window"
        )
        assert strip_instagram_noise(text) == "Feed post number 1\nActual post content"


class TestScrapeUserCallbacks:
    """Test that scrape_user invokes callbacks at each stage."""

    async def test_scrape_user_calls_callbacks(self, mock_page):
        extractor = InstagramExtractor(mock_page)
        cb = MagicMock(spec=ProgressCallback)
        cb.on_start = AsyncMock()
        cb.on_progress = AsyncMock()
        cb.on_complete = AsyncMock()
        cb.on_error = AsyncMock()

        with (
            patch.object(
                extractor,
                "extract_page",
                new_callable=AsyncMock,
                return_value=extracted("text"),
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await extractor.scrape_user("testuser", {"reels", "tagged"}, callbacks=cb)

        cb.on_start.assert_awaited_once()
        assert cb.on_start.call_args[0][0] == "user profile"

        # 3 sections: main_profile (always) + reels + tagged
        assert cb.on_progress.await_count == 3
        messages = [c.args[0] for c in cb.on_progress.call_args_list]
        assert messages == [
            "Scraped main_profile (1/3)",
            "Scraped reels (2/3)",
            "Scraped tagged (3/3)",
        ]
        # Last section should be at 95%
        assert cb.on_progress.call_args_list[-1].args[1] == 95

        cb.on_complete.assert_awaited_once()
        assert cb.on_complete.call_args[0][0] == "user profile"
        cb.on_error.assert_not_awaited()

    async def test_scrape_user_no_callbacks_by_default(self, mock_page):
        """Without callbacks, scrape_user works identically to before."""
        extractor = InstagramExtractor(mock_page)
        with (
            patch.object(
                extractor,
                "extract_page",
                new_callable=AsyncMock,
                return_value=extracted("text"),
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await extractor.scrape_user("testuser", {"main_profile"})

        assert "main_profile" in result["sections"]

    async def test_scrape_user_calls_on_error(self, mock_page):
        extractor = InstagramExtractor(mock_page)
        cb = MagicMock(spec=ProgressCallback)
        cb.on_start = AsyncMock()
        cb.on_progress = AsyncMock()
        cb.on_complete = AsyncMock()
        cb.on_error = AsyncMock()

        with (
            patch.object(
                extractor,
                "extract_page",
                new_callable=AsyncMock,
                side_effect=InstagramScraperException("boom"),
            ),
            patch(
                "instagram_mcp_server.scraping.extractor.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            with pytest.raises(InstagramScraperException):
                await extractor.scrape_user("testuser", {"main_profile"}, callbacks=cb)

        cb.on_start.assert_awaited_once()
        cb.on_error.assert_awaited_once()
        error_arg = cb.on_error.call_args[0][0]
        assert isinstance(error_arg, InstagramScraperException)
        assert "boom" in str(error_arg)
        cb.on_complete.assert_not_awaited()
