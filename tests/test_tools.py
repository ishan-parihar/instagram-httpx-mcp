from typing import Any, Callable, Coroutine
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP

from instagram_mcp_server.callbacks import MCPContextProgressCallback
from instagram_mcp_server.scraping.extractor import ExtractedSection, _RATE_LIMITED_MSG


async def get_tool_fn(
    mcp: FastMCP, name: str
) -> Callable[..., Coroutine[Any, Any, dict[str, Any]]]:
    """Extract tool function from FastMCP by name using public API."""
    tool = await mcp.get_tool(name)
    if tool is None:
        raise ValueError(f"Tool '{name}' not found")
    return tool.fn  # type: ignore[attr-defined]


def _make_mock_extractor(scrape_result: dict) -> MagicMock:
    """Create a mock InstagramExtractor that returns the given result."""
    mock = MagicMock()
    mock.scrape_user = AsyncMock(return_value=scrape_result)
    mock.scrape_user_posts = AsyncMock(return_value=scrape_result)
    mock.scrape_user_reels = AsyncMock(return_value=scrape_result)
    mock.search_users = AsyncMock(return_value=scrape_result)
    mock.search_hashtags = AsyncMock(return_value=scrape_result)
    mock.search_locations = AsyncMock(return_value=scrape_result)
    mock.scrape_dm_inbox = AsyncMock(return_value=scrape_result)
    mock.scrape_dm_conversation = AsyncMock(return_value=scrape_result)
    mock.send_dm = AsyncMock(return_value=scrape_result)
    mock.extract_page = AsyncMock(
        return_value=ExtractedSection(text="some text", references=[])
    )
    mock.follow_user = AsyncMock(return_value=scrape_result)
    mock.unfollow_user = AsyncMock(return_value=scrape_result)
    mock.like_post = AsyncMock(return_value=scrape_result)
    mock.unlike_post = AsyncMock(return_value=scrape_result)
    mock.save_post = AsyncMock(return_value=scrape_result)
    mock.comment_on_post = AsyncMock(return_value=scrape_result)
    return mock


class TestUserTools:
    async def test_get_user_profile_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/test-user/",
            "sections": {"main_profile": "John Doe\nSoftware Engineer"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.user import register_user_tools

        mcp = FastMCP("test")
        register_user_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_user_profile")
        result = await tool_fn("test-user", mock_context, extractor=mock_extractor)
        assert result["url"] == "https://www.instagram.com/test-user/"
        assert "main_profile" in result["sections"]
        assert "pages_visited" not in result
        assert "sections_requested" not in result

    async def test_get_user_profile_with_sections(self, mock_context):
        """Verify sections parameter is passed through."""
        expected = {
            "url": "https://www.instagram.com/test-user/",
            "sections": {
                "main_profile": "John Doe",
                "posts": "Post grid",
                "followers": "Followers list",
            },
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.user import register_user_tools

        mcp = FastMCP("test")
        register_user_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_user_profile")
        result = await tool_fn(
            "test-user",
            mock_context,
            sections="posts,followers",
            extractor=mock_extractor,
        )
        assert "main_profile" in result["sections"]
        assert "posts" in result["sections"]
        assert "followers" in result["sections"]
        # Verify scrape_user was called exactly once with a set[str]
        mock_extractor.scrape_user.assert_awaited_once()
        call_args = mock_extractor.scrape_user.call_args
        assert isinstance(call_args[0][1], set)
        assert "posts" in call_args[0][1]
        assert "followers" in call_args[0][1]

    async def test_get_user_profile_passes_callbacks(self, mock_context):
        """Verify tool wires MCPContextProgressCallback to the extractor."""
        expected = {
            "url": "https://www.instagram.com/test-user/",
            "sections": {"main_profile": "John Doe"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.user import register_user_tools

        mcp = FastMCP("test")
        register_user_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_user_profile")
        await tool_fn("test-user", mock_context, extractor=mock_extractor)

        call_kwargs = mock_extractor.scrape_user.call_args.kwargs
        assert "callbacks" in call_kwargs
        assert isinstance(call_kwargs["callbacks"], MCPContextProgressCallback)

    async def test_get_user_profile_unknown_section(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/test-user/",
            "sections": {"main_profile": "John Doe"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.user import register_user_tools

        mcp = FastMCP("test")
        register_user_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_user_profile")
        result = await tool_fn(
            "test-user",
            mock_context,
            sections="bogus_section",
            extractor=mock_extractor,
        )
        assert result["unknown_sections"] == ["bogus_section"]

    async def test_get_user_profile_error(self, mock_context):
        from fastmcp.exceptions import ToolError

        from instagram_mcp_server.exceptions import SessionExpiredError

        mock_extractor = MagicMock()
        mock_extractor.scrape_user = AsyncMock(side_effect=SessionExpiredError())

        from instagram_mcp_server.tools.user import register_user_tools

        mcp = FastMCP("test")
        register_user_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_user_profile")
        with pytest.raises(ToolError, match="Session expired"):
            await tool_fn("test-user", mock_context, extractor=mock_extractor)

    async def test_get_user_profile_auth_error(self, monkeypatch):
        """Auth failures in the DI layer trigger auto-relogin and report the login browser."""
        from fastmcp.exceptions import ToolError

        from instagram_mcp_server.core.exceptions import AuthenticationError
        from instagram_mcp_server.exceptions import AuthenticationStartedError

        mock_browser = MagicMock()
        mock_browser.page = MagicMock()
        monkeypatch.setattr(
            "instagram_mcp_server.dependencies.ensure_tool_ready_or_raise",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "instagram_mcp_server.dependencies.get_or_create_browser",
            AsyncMock(return_value=mock_browser),
        )
        monkeypatch.setattr(
            "instagram_mcp_server.dependencies.ensure_authenticated",
            AsyncMock(side_effect=AuthenticationError("Session expired or invalid.")),
        )
        monkeypatch.setattr(
            "instagram_mcp_server.dependencies.get_runtime_policy",
            lambda: "managed",
        )
        monkeypatch.setattr(
            "instagram_mcp_server.dependencies.close_browser",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "instagram_mcp_server.dependencies.invalidate_auth_and_trigger_relogin",
            AsyncMock(
                side_effect=AuthenticationStartedError(
                    "Session expired. A login browser window has been opened."
                )
            ),
        )

        from instagram_mcp_server.tools.user import register_user_tools

        mcp = FastMCP("test")
        register_user_tools(mcp)

        with pytest.raises(ToolError, match="Session expired"):
            await mcp.call_tool("get_user_profile", {"username": "test"})

    async def test_get_user_posts_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/test-user/",
            "sections": {"posts": "Post 1\nPost 2"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.user import register_user_tools

        mcp = FastMCP("test")
        register_user_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_user_posts")
        result = await tool_fn("test-user", mock_context, extractor=mock_extractor)
        assert "posts" in result["sections"]
        mock_extractor.scrape_user_posts.assert_awaited_once_with(
            "test-user", 50, callbacks=ANY
        )

    async def test_get_user_posts_passes_callbacks(self, mock_context):
        """Verify tool wires MCPContextProgressCallback to the extractor."""
        expected = {
            "url": "https://www.instagram.com/test-user/",
            "sections": {"posts": "Post 1"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.user import register_user_tools

        mcp = FastMCP("test")
        register_user_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_user_posts")
        await tool_fn("test-user", mock_context, extractor=mock_extractor)

        call_kwargs = mock_extractor.scrape_user_posts.call_args.kwargs
        assert "callbacks" in call_kwargs
        assert isinstance(call_kwargs["callbacks"], MCPContextProgressCallback)

    async def test_get_user_reels_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/test-user/",
            "sections": {"reels": "Reel 1\nReel 2"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.user import register_user_tools

        mcp = FastMCP("test")
        register_user_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_user_reels")
        result = await tool_fn("test-user", mock_context, extractor=mock_extractor)
        assert "reels" in result["sections"]
        mock_extractor.scrape_user_reels.assert_awaited_once_with(
            "test-user", 50, callbacks=ANY
        )

    async def test_get_user_reels_passes_callbacks(self, mock_context):
        """Verify tool wires MCPContextProgressCallback to the extractor."""
        expected = {
            "url": "https://www.instagram.com/test-user/",
            "sections": {"reels": "Reel 1"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.user import register_user_tools

        mcp = FastMCP("test")
        register_user_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_user_reels")
        await tool_fn("test-user", mock_context, extractor=mock_extractor)

        call_kwargs = mock_extractor.scrape_user_reels.call_args.kwargs
        assert "callbacks" in call_kwargs
        assert isinstance(call_kwargs["callbacks"], MCPContextProgressCallback)


class TestInsightsTools:
    async def test_get_business_insights(self, mock_context):
        mock_extractor = MagicMock()
        mock_extractor.extract_page = AsyncMock(
            return_value=ExtractedSection(
                text="Reach: 10K\nImpressions: 50K", references=[]
            )
        )

        from instagram_mcp_server.tools.insights import register_insights_tools

        mcp = FastMCP("test")
        register_insights_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_business_insights")
        result = await tool_fn(mock_context, extractor=mock_extractor)
        assert "overview" in result["sections"]
        assert "pages_visited" not in result

    async def test_get_business_insights_omits_rate_limited(self, mock_context):
        mock_extractor = MagicMock()
        mock_extractor.extract_page = AsyncMock(
            return_value=ExtractedSection(text=_RATE_LIMITED_MSG, references=[])
        )

        from instagram_mcp_server.tools.insights import register_insights_tools

        mcp = FastMCP("test")
        register_insights_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_business_insights")
        result = await tool_fn(mock_context, extractor=mock_extractor)
        assert result["sections"] == {}

    async def test_get_audience_insights(self, mock_context):
        mock_extractor = MagicMock()
        mock_extractor.extract_page = AsyncMock(
            return_value=ExtractedSection(
                text="Age: 25-34\nLocation: US", references=[]
            )
        )

        from instagram_mcp_server.tools.insights import register_insights_tools

        mcp = FastMCP("test")
        register_insights_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_audience_insights")
        result = await tool_fn(mock_context, extractor=mock_extractor)
        assert "audience" in result["sections"]
        assert "pages_visited" not in result

    async def test_get_content_insights(self, mock_context):
        mock_extractor = MagicMock()
        mock_extractor.extract_page = AsyncMock(
            return_value=ExtractedSection(
                text="Top posts: Photo 1, Reel 1", references=[]
            )
        )

        from instagram_mcp_server.tools.insights import register_insights_tools

        mcp = FastMCP("test")
        register_insights_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_content_insights")
        result = await tool_fn(mock_context, extractor=mock_extractor)
        assert "content" in result["sections"]

    async def test_get_activity_insights(self, mock_context):
        mock_extractor = MagicMock()
        mock_extractor.extract_page = AsyncMock(
            return_value=ExtractedSection(
                text="Profile visits: 500\nFollowers gained: 20", references=[]
            )
        )

        from instagram_mcp_server.tools.insights import register_insights_tools

        mcp = FastMCP("test")
        register_insights_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_activity_insights")
        result = await tool_fn(mock_context, extractor=mock_extractor)
        assert "activity" in result["sections"]


class TestPostTools:
    async def test_get_post_details_success(self, mock_context):
        mock_extractor = MagicMock()
        mock_extractor.extract_page = AsyncMock(
            return_value=ExtractedSection(
                text="Beautiful sunset at the beach", references=[]
            )
        )

        from instagram_mcp_server.tools.posts import register_post_tools

        mcp = FastMCP("test")
        register_post_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_post_details")
        result = await tool_fn(
            "https://www.instagram.com/p/ABC123/",
            mock_context,
            extractor=mock_extractor,
        )
        assert "main" in result["sections"]
        assert result["sections"]["main"] == "Beautiful sunset at the beach"
        assert "pages_visited" not in result

    async def test_get_post_details_with_comments(self, mock_context):
        mock_extractor = MagicMock()
        mock_extractor.extract_page = AsyncMock(
            return_value=ExtractedSection(
                text="Post body\nComment 1\nComment 2", references=[]
            )
        )

        from instagram_mcp_server.tools.posts import register_post_tools

        mcp = FastMCP("test")
        register_post_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_post_details")
        result = await tool_fn(
            "https://www.instagram.com/p/ABC123/",
            mock_context,
            include_comments=True,
            extractor=mock_extractor,
        )
        assert "main" in result["sections"]
        assert "comments" in result["sections"]

    async def test_get_hashtag_posts_success(self, mock_context):
        mock_extractor = MagicMock()
        mock_extractor.extract_page = AsyncMock(
            return_value=ExtractedSection(
                text="Hashtag post 1\nHashtag post 2", references=[]
            )
        )

        from instagram_mcp_server.tools.posts import register_post_tools

        mcp = FastMCP("test")
        register_post_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_hashtag_posts")
        result = await tool_fn("travel", mock_context, extractor=mock_extractor)
        assert "main" in result["sections"]
        assert "https://www.instagram.com/explore/tags/travel/" == result["url"]

    async def test_get_location_posts_success(self, mock_context):
        mock_extractor = MagicMock()
        mock_extractor.extract_page = AsyncMock(
            return_value=ExtractedSection(
                text="Location post 1\nLocation post 2", references=[]
            )
        )

        from instagram_mcp_server.tools.posts import register_post_tools

        mcp = FastMCP("test")
        register_post_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_location_posts")
        result = await tool_fn("123456", mock_context, extractor=mock_extractor)
        assert "main" in result["sections"]
        assert "/explore/locations/123456/" in result["url"]


class TestSearchTools:
    async def test_search_users_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/explore/search/?keywords=photographer",
            "sections": {"search_results": "Jane Doe\nPhotographer"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.search import register_search_tools

        mcp = FastMCP("test")
        register_search_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "search_users")
        result = await tool_fn("photographer", mock_context, extractor=mock_extractor)
        # search_users renames search_results -> users
        assert "users" in result["sections"]
        mock_extractor.search_users.assert_awaited_once()

    async def test_search_hashtags_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/explore/search/?keywords=travel",
            "sections": {"search_results": "#travel\n#travelphotography"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.search import register_search_tools

        mcp = FastMCP("test")
        register_search_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "search_hashtags")
        result = await tool_fn("travel", mock_context, extractor=mock_extractor)
        # search_hashtags renames search_results -> hashtags
        assert "hashtags" in result["sections"]
        mock_extractor.search_hashtags.assert_awaited_once()

    async def test_search_locations_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/explore/search/?keywords=Paris",
            "sections": {"search_results": "Paris, France\nParis Cafe"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.search import register_search_tools

        mcp = FastMCP("test")
        register_search_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "search_locations")
        result = await tool_fn("Paris", mock_context, extractor=mock_extractor)
        # search_locations renames search_results -> locations
        assert "locations" in result["sections"]
        mock_extractor.search_locations.assert_awaited_once()


class TestMessagingTools:
    async def test_get_direct_inbox_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/direct/",
            "sections": {"inbox": "Conversation 1\nConversation 2"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.messaging import register_messaging_tools

        mcp = FastMCP("test")
        register_messaging_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_direct_inbox")
        result = await tool_fn(mock_context, extractor=mock_extractor)

        assert result["sections"]["inbox"] == "Conversation 1\nConversation 2"
        mock_extractor.scrape_dm_inbox.assert_awaited_once_with(limit=20)

    async def test_get_dm_conversation_by_username(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/direct/thread/abc123/",
            "sections": {"conversation": "Hello!\nHi there!"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.messaging import register_messaging_tools

        mcp = FastMCP("test")
        register_messaging_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_dm_conversation")
        result = await tool_fn(
            mock_context, username="testuser", extractor=mock_extractor
        )

        assert result["sections"]["conversation"] == "Hello!\nHi there!"
        mock_extractor.scrape_dm_conversation.assert_awaited_once_with(
            thread_id=None, username="testuser"
        )

    async def test_get_dm_conversation_by_thread_id(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/direct/thread/abc123/",
            "sections": {"conversation": "Hello!\nHi there!"},
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.messaging import register_messaging_tools

        mcp = FastMCP("test")
        register_messaging_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_dm_conversation")
        result = await tool_fn(
            mock_context, thread_id="abc123", extractor=mock_extractor
        )

        assert result["sections"]["conversation"] == "Hello!\nHi there!"
        mock_extractor.scrape_dm_conversation.assert_awaited_once_with(
            thread_id="abc123", username=None
        )

    async def test_get_dm_conversation_missing_args(self, mock_context):
        from fastmcp.exceptions import ToolError

        from instagram_mcp_server.tools.messaging import register_messaging_tools

        mcp = FastMCP("test")
        register_messaging_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "get_dm_conversation")
        with pytest.raises(ToolError, match="Provide at least one"):
            await tool_fn(mock_context, extractor=_make_mock_extractor({}))

    async def test_send_dm_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/direct/thread/abc123/",
            "status": "sent",
            "sent": True,
            "message": "Message sent.",
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.messaging import register_messaging_tools

        mcp = FastMCP("test")
        register_messaging_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "send_dm")
        result = await tool_fn(
            "testuser",
            "Hello!",
            True,
            mock_context,
            extractor=mock_extractor,
        )

        assert result["status"] == "sent"
        assert result["sent"] is True
        mock_extractor.send_dm.assert_awaited_once_with("testuser", "Hello!")

    async def test_send_dm_not_confirmed(self, mock_context):
        mock_extractor = _make_mock_extractor({})

        from instagram_mcp_server.tools.messaging import register_messaging_tools

        mcp = FastMCP("test")
        register_messaging_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "send_dm")
        result = await tool_fn(
            "testuser",
            "Hello!",
            False,
            mock_context,
            extractor=mock_extractor,
        )

        assert result["status"] == "not_sent"
        assert result["sent"] is False
        mock_extractor.send_dm.assert_not_awaited()

    async def test_send_dm_error(self, mock_context):
        from fastmcp.exceptions import ToolError

        from instagram_mcp_server.exceptions import SessionExpiredError

        mock_extractor = MagicMock()
        mock_extractor.send_dm = AsyncMock(side_effect=SessionExpiredError())

        from instagram_mcp_server.tools.messaging import register_messaging_tools

        mcp = FastMCP("test")
        register_messaging_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "send_dm")
        with pytest.raises(ToolError, match="Session expired"):
            await tool_fn(
                "testuser",
                "Hello!",
                True,
                mock_context,
                extractor=mock_extractor,
            )


class TestActionTools:
    async def test_follow_user_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/test-user/",
            "status": "following",
            "message": "Now following test-user.",
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.actions import register_action_tools

        mcp = FastMCP("test")
        register_action_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "follow_user")
        result = await tool_fn("test-user", mock_context, extractor=mock_extractor)

        assert result["status"] == "following"
        mock_extractor.follow_user.assert_awaited_once_with("test-user")

    async def test_follow_user_auth_error(self, monkeypatch):
        from fastmcp.exceptions import ToolError

        from instagram_mcp_server.core.exceptions import AuthenticationError
        from instagram_mcp_server.exceptions import AuthenticationStartedError

        mock_browser = MagicMock()
        mock_browser.page = MagicMock()
        monkeypatch.setattr(
            "instagram_mcp_server.dependencies.ensure_tool_ready_or_raise",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "instagram_mcp_server.dependencies.get_or_create_browser",
            AsyncMock(return_value=mock_browser),
        )
        monkeypatch.setattr(
            "instagram_mcp_server.dependencies.ensure_authenticated",
            AsyncMock(side_effect=AuthenticationError("Session expired or invalid.")),
        )
        monkeypatch.setattr(
            "instagram_mcp_server.dependencies.get_runtime_policy",
            lambda: "managed",
        )
        monkeypatch.setattr(
            "instagram_mcp_server.dependencies.close_browser",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "instagram_mcp_server.dependencies.invalidate_auth_and_trigger_relogin",
            AsyncMock(
                side_effect=AuthenticationStartedError(
                    "Session expired. A login browser window has been opened."
                )
            ),
        )

        from instagram_mcp_server.tools.actions import register_action_tools

        mcp = FastMCP("test")
        register_action_tools(mcp)

        with pytest.raises(ToolError, match="Session expired"):
            await mcp.call_tool("follow_user", {"username": "test"})

    async def test_unfollow_user_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/test-user/",
            "status": "unfollowed",
            "message": "Unfollowed test-user.",
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.actions import register_action_tools

        mcp = FastMCP("test")
        register_action_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "unfollow_user")
        result = await tool_fn("test-user", mock_context, extractor=mock_extractor)

        assert result["status"] == "unfollowed"
        mock_extractor.unfollow_user.assert_awaited_once_with("test-user")

    async def test_like_post_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/p/ABC123/",
            "status": "liked",
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.actions import register_action_tools

        mcp = FastMCP("test")
        register_action_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "like_post")
        result = await tool_fn(
            "https://www.instagram.com/p/ABC123/",
            mock_context,
            extractor=mock_extractor,
        )

        assert result["status"] == "liked"
        mock_extractor.like_post.assert_awaited_once_with(
            "https://www.instagram.com/p/ABC123/"
        )

    async def test_unlike_post_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/p/ABC123/",
            "status": "unliked",
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.actions import register_action_tools

        mcp = FastMCP("test")
        register_action_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "unlike_post")
        result = await tool_fn(
            "https://www.instagram.com/p/ABC123/",
            mock_context,
            extractor=mock_extractor,
        )

        assert result["status"] == "unliked"
        mock_extractor.unlike_post.assert_awaited_once_with(
            "https://www.instagram.com/p/ABC123/"
        )

    async def test_save_post_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/p/ABC123/",
            "status": "saved",
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.actions import register_action_tools

        mcp = FastMCP("test")
        register_action_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "save_post")
        result = await tool_fn(
            "https://www.instagram.com/p/ABC123/",
            mock_context,
            extractor=mock_extractor,
        )

        assert result["status"] == "saved"
        mock_extractor.save_post.assert_awaited_once_with(
            "https://www.instagram.com/p/ABC123/", None
        )

    async def test_save_post_with_collection(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/p/ABC123/",
            "status": "saved",
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.actions import register_action_tools

        mcp = FastMCP("test")
        register_action_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "save_post")
        result = await tool_fn(
            "https://www.instagram.com/p/ABC123/",
            mock_context,
            collection="Favorites",
            extractor=mock_extractor,
        )

        assert result["status"] == "saved"
        mock_extractor.save_post.assert_awaited_once_with(
            "https://www.instagram.com/p/ABC123/", "Favorites"
        )

    async def test_comment_on_post_success(self, mock_context):
        expected = {
            "url": "https://www.instagram.com/p/ABC123/",
            "status": "commented",
            "message": "Comment posted.",
        }
        mock_extractor = _make_mock_extractor(expected)

        from instagram_mcp_server.tools.actions import register_action_tools

        mcp = FastMCP("test")
        register_action_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "comment_on_post")
        result = await tool_fn(
            "https://www.instagram.com/p/ABC123/",
            "Great post!",
            True,
            mock_context,
            extractor=mock_extractor,
        )

        assert result["status"] == "commented"
        mock_extractor.comment_on_post.assert_awaited_once_with(
            "https://www.instagram.com/p/ABC123/", "Great post!"
        )

    async def test_comment_on_post_not_confirmed(self, mock_context):
        mock_extractor = _make_mock_extractor({})

        from instagram_mcp_server.tools.actions import register_action_tools

        mcp = FastMCP("test")
        register_action_tools(mcp)

        tool_fn = await get_tool_fn(mcp, "comment_on_post")
        result = await tool_fn(
            "https://www.instagram.com/p/ABC123/",
            "Great post!",
            False,
            mock_context,
            extractor=mock_extractor,
        )

        assert result["status"] == "cancelled"
        mock_extractor.comment_on_post.assert_not_awaited()


class TestToolTimeouts:
    async def test_all_tools_have_global_timeout(self):
        from instagram_mcp_server.constants import TOOL_TIMEOUT_SECONDS
        from instagram_mcp_server.server import create_mcp_server

        mcp = create_mcp_server()

        tool_names = (
            # User tools
            "get_user_profile",
            "get_user_posts",
            "get_user_reels",
            "get_user_stories",
            "get_user_highlights",
            # Insights tools
            "get_business_insights",
            "get_audience_insights",
            "get_content_insights",
            "get_activity_insights",
            # Post tools
            "get_post_details",
            "get_hashtag_posts",
            "get_location_posts",
            # Search tools
            "search_users",
            "search_hashtags",
            "search_locations",
            # Messaging tools
            "get_direct_inbox",
            "get_dm_conversation",
            "send_dm",
            # Action tools
            "follow_user",
            "unfollow_user",
            "like_post",
            "unlike_post",
            "save_post",
            "comment_on_post",
            # Session
            "close_session",
        )

        for name in tool_names:
            tool = await mcp.get_tool(name)
            assert tool is not None, f"Tool '{name}' not found"
            assert tool.timeout == TOOL_TIMEOUT_SECONDS
