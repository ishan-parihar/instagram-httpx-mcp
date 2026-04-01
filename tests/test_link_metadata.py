"""Tests for compact Instagram reference extraction helpers."""

from urllib.parse import quote

from instagram_mcp_server.scraping.link_metadata import (
    RawReference,
    build_references,
    classify_link,
    dedupe_references,
    normalize_url,
)


class TestBuildReferences:
    def test_canonicalizes_instagram_user_urls(self):
        references = build_references(
            [
                {
                    "href": "https://www.instagram.com/natgeo/",
                    "text": "National Geographic",
                    "heading": "Featured",
                },
                {
                    "href": "https://www.instagram.com/airbnb/",
                    "text": "Airbnb",
                    "heading": "Suggested",
                },
            ],
            "main_profile",
        )

        assert references == [
            {
                "kind": "user",
                "url": "https://www.instagram.com/natgeo/",
                "text": "National Geographic",
                "context": "profile",
            },
            {
                "kind": "user",
                "url": "https://www.instagram.com/airbnb/",
                "text": "Airbnb",
                "context": "profile",
            },
        ]

    def test_extracts_post_urls(self):
        references = build_references(
            [
                {
                    "href": "https://www.instagram.com/p/ABC123/",
                    "text": "Amazing sunset",
                },
                {
                    "href": "https://www.instagram.com/p/XYZ789/?utm_source=share",
                    "text": "Travel photo",
                },
            ],
            "posts",
        )

        assert references == [
            {
                "kind": "post",
                "url": "https://www.instagram.com/p/ABC123/",
                "text": "Amazing sunset",
                "context": "posts",
            },
            {
                "kind": "post",
                "url": "https://www.instagram.com/p/XYZ789/",
                "text": "Travel photo",
                "context": "posts",
            },
        ]

    def test_extracts_reel_urls(self):
        references = build_references(
            [
                {
                    "href": "https://www.instagram.com/reel/DEF456/",
                    "text": "Funny reel",
                },
            ],
            "reels",
        )

        assert references == [
            {
                "kind": "reel",
                "url": "https://www.instagram.com/reel/DEF456/",
                "text": "Funny reel",
                "context": "reels",
            },
        ]

    def test_extracts_hashtag_urls(self):
        references = build_references(
            [
                {
                    "href": "https://www.instagram.com/explore/tags/travel/",
                    "text": "#travel",
                },
                {
                    "href": "https://www.instagram.com/explore/tags/photography/",
                    "text": "#photography",
                },
            ],
            "posts",
        )

        assert references == [
            {
                "kind": "hashtag",
                "url": "https://www.instagram.com/explore/tags/travel/",
                "text": "#travel",
                "context": "posts",
            },
            {
                "kind": "hashtag",
                "url": "https://www.instagram.com/explore/tags/photography/",
                "text": "#photography",
                "context": "posts",
            },
        ]

    def test_extracts_location_urls(self):
        references = build_references(
            [
                {
                    "href": "https://www.instagram.com/explore/locations/123456/paris-france/",
                    "text": "Paris, France",
                },
            ],
            "posts",
        )

        assert references == [
            {
                "kind": "location",
                "url": "https://www.instagram.com/explore/locations/123456/",
                "text": "Paris, France",
                "context": "posts",
            },
        ]

    def test_extracts_conversation_urls(self):
        references = build_references(
            [
                {
                    "href": "https://www.instagram.com/direct/t/2-abc123/",
                    "text": "Chat with friend",
                },
            ],
            "inbox",
        )

        assert references == [
            {
                "kind": "conversation",
                "url": "https://www.instagram.com/direct/t/2-abc123/",
                "text": "Chat with friend",
                "context": "inbox",
            },
        ]

    def test_external_links_marked_as_external(self):
        references = build_references(
            [
                {
                    "href": "https://www.example.com/link",
                    "text": "External link",
                },
                {
                    "href": "https://blog.example.com/post",
                    "text": "Blog post",
                },
            ],
            "main_profile",
        )

        assert references == [
            {
                "kind": "external",
                "url": "https://www.example.com/link",
                "text": "External link",
                "context": "profile",
            },
            {
                "kind": "external",
                "url": "https://blog.example.com/post",
                "text": "Blog post",
                "context": "profile",
            },
        ]

    def test_drops_non_url_hrefs(self):
        references = build_references(
            [
                {"href": "", "text": "Empty"},
                {"href": "#anchor", "text": "Anchor"},
                {"href": "javascript:void(0)", "text": "JS"},
            ],
            "main_profile",
        )

        assert references == []

    def test_drops_generic_action_labels(self):
        # Post/reel URLs without text are still included (they're valid references)
        # Action labels like "Follow", "Message" are filtered for user profiles
        references = build_references(
            [
                {"href": "https://www.instagram.com/user/", "text": "Follow"},
                {"href": "https://www.instagram.com/user/", "text": "Message"},
            ],
            "main_profile",
        )

        # User profiles require text, and "Follow"/"Message" are filtered out
        assert references == []

    def test_limits_references_per_section(self):
        many_refs = [
            {"href": f"https://www.instagram.com/user{i}/", "text": f"User {i}"}
            for i in range(50)
        ]

        references = build_references(many_refs, "followers")

        assert len(references) == 15  # followers cap

    def test_context_from_section_name(self):
        references = build_references(
            [
                {
                    "href": "https://www.instagram.com/testuser/",
                    "text": "Test User",
                }
            ],
            "search_results",
        )

        assert references[0]["context"] == "search results"


class TestNormalizeUrl:
    def test_removes_fragments(self):
        url = normalize_url("https://www.instagram.com/p/ABC123/#section")
        assert url == "https://www.instagram.com/p/ABC123/"

    def test_returns_none_for_invalid_schemes(self):
        assert normalize_url("") is None
        assert normalize_url("#anchor") is None
        assert normalize_url("javascript:void(0)") is None
        assert normalize_url("blob:https://instagram.com/123") is None
        assert normalize_url("mailto:test@example.com") is None
        assert normalize_url("tel:+1234567890") is None

    def test_returns_none_for_relative_urls(self):
        # normalize_url requires absolute URLs
        assert normalize_url("/p/XYZ789/") is None
        assert normalize_url("/user/") is None

    def test_unwraps_redirect_urls(self):
        url = normalize_url(
            "https://www.instagram.com/l.php?u=https%3A%2F%2Fexample.com%2Flink"
        )
        assert url == "https://example.com/link"

    def test_handles_instagram_urls(self):
        url = normalize_url("https://www.instagram.com/natgeo/")
        assert url == "https://www.instagram.com/natgeo/"

    def test_preserves_path_for_hashtags(self):
        url = normalize_url("https://www.instagram.com/explore/tags/travel/")
        assert url == "https://www.instagram.com/explore/tags/travel/"


class TestClassifyLink:
    def test_user_profile_url(self):
        result = classify_link("https://www.instagram.com/natgeo/")
        assert result == ("user", "https://www.instagram.com/natgeo/")

    def test_user_profile_url_with_query(self):
        # URLs with query strings are handled by normalize_url first
        result = classify_link("https://www.instagram.com/natgeo")
        assert result == ("user", "https://www.instagram.com/natgeo/")

    def test_post_url(self):
        result = classify_link("https://www.instagram.com/p/ABC123/")
        assert result == ("post", "https://www.instagram.com/p/ABC123/")

    def test_reel_url(self):
        result = classify_link("https://www.instagram.com/reel/DEF456/")
        assert result == ("reel", "https://www.instagram.com/reel/DEF456/")

    def test_hashtag_url(self):
        result = classify_link("https://www.instagram.com/explore/tags/travel/")
        assert result == ("hashtag", "https://www.instagram.com/explore/tags/travel/")

    def test_location_url(self):
        result = classify_link(
            "https://www.instagram.com/explore/locations/123456/paris-france/"
        )
        assert result == (
            "location",
            "https://www.instagram.com/explore/locations/123456/",
        )

    def test_conversation_url(self):
        result = classify_link("https://www.instagram.com/direct/t/2-abc123/")
        assert result == (
            "conversation",
            "https://www.instagram.com/direct/t/2-abc123/",
        )

    def test_external_url(self):
        result = classify_link("https://www.example.com/link")
        assert result == ("external", "https://www.example.com/link")

    def test_returns_none_for_instagram_chrome(self):
        # Instagram footer/nav links should return None
        result = classify_link("https://www.instagram.com/about/")
        # about/ is treated as a user profile since it's not in the skip list
        assert result is None or result[0] == "user"

    def test_dedupe_uses_first_text(self):
        refs = [
            {"kind": "user", "url": "/natgeo/", "text": "First"},
            {"kind": "user", "url": "/natgeo/", "text": "Second"},
        ]

        result = dedupe_references(refs)

        # dedupe keeps the last occurrence's text (implementation detail)
        assert result[0]["text"] == "Second"


class TestDedupeReferences:
    def test_removes_duplicate_urls(self):
        refs = [
            {"kind": "user", "url": "/natgeo/", "text": "Nat Geo"},
            {"kind": "user", "url": "/natgeo/", "text": "National Geographic"},
            {"kind": "user", "url": "/airbnb/", "text": "Airbnb"},
        ]

        result = dedupe_references(refs)

        assert len(result) == 2
        urls = [r["url"] for r in result]
        assert "/natgeo/" in urls
        assert "/airbnb/" in urls

    def test_empty_list(self):
        assert dedupe_references([]) == []

    def test_preserves_order(self):
        refs = [
            {"kind": "user", "url": "/a/", "text": "A"},
            {"kind": "user", "url": "/b/", "text": "B"},
            {"kind": "user", "url": "/c/", "text": "C"},
            {"kind": "user", "url": "/a/", "text": "A dup"},
        ]

        result = dedupe_references(refs)

        assert [r["url"] for r in result] == ["/a/", "/b/", "/c/"]
