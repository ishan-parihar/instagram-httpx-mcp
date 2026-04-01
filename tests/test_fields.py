"""Tests for scraping section config dicts and section parsers."""

from instagram_mcp_server.scraping.fields import (
    INSIGHTS_SECTIONS,
    USER_SECTIONS,
    parse_insights_sections,
    parse_user_sections,
)


class TestUserSections:
    def test_expected_keys(self):
        expected = {
            "main_profile",
            "posts",
            "reels",
            "tagged",
            "followers",
            "following",
        }
        assert set(USER_SECTIONS) == expected

    def test_no_overlays(self):
        for name, (_suffix, is_overlay) in USER_SECTIONS.items():
            assert is_overlay is False, f"{name} should not be an overlay"

    def test_all_suffixes_start_with_slash(self):
        for name, (suffix, _) in USER_SECTIONS.items():
            assert suffix.startswith("/"), f"{name} suffix should start with /"


class TestInsightsSections:
    def test_expected_keys(self):
        assert set(INSIGHTS_SECTIONS) == {"overview", "audience", "content", "activity"}

    def test_no_overlays(self):
        for name, (_suffix, is_overlay) in INSIGHTS_SECTIONS.items():
            assert is_overlay is False, f"{name} should not be an overlay"


class TestParseUserSections:
    def test_none_returns_baseline_only(self):
        requested, unknown = parse_user_sections(None)
        assert requested == {"main_profile"}
        assert unknown == []

    def test_empty_string_returns_baseline_only(self):
        requested, unknown = parse_user_sections("")
        assert requested == {"main_profile"}
        assert unknown == []

    def test_single_section(self):
        requested, unknown = parse_user_sections("reels")
        assert requested == {"main_profile", "reels"}
        assert unknown == []

    def test_multiple_sections(self):
        requested, unknown = parse_user_sections("reels,tagged")
        assert requested == {"main_profile", "reels", "tagged"}
        assert unknown == []

    def test_invalid_names_returned(self):
        requested, unknown = parse_user_sections("reels,bogus,tagged")
        assert requested == {"main_profile", "reels", "tagged"}
        assert unknown == ["bogus"]

    def test_multiple_invalid_names(self):
        requested, unknown = parse_user_sections("reels,foo,bar")
        assert requested == {"main_profile", "reels"}
        assert unknown == ["foo", "bar"]

    def test_whitespace_and_case_handling(self):
        requested, unknown = parse_user_sections(" Reels , TAGGED ")
        assert requested == {"main_profile", "reels", "tagged"}
        assert unknown == []

    def test_baseline_passed_explicitly_not_unknown(self):
        requested, unknown = parse_user_sections("main_profile,reels")
        assert requested == {"main_profile", "reels"}
        assert unknown == []

    def test_all_sections(self):
        requested, unknown = parse_user_sections(
            "posts,reels,tagged,followers,following"
        )
        assert requested == set(USER_SECTIONS)
        assert unknown == []


class TestParseInsightsSections:
    def test_none_returns_baseline_only(self):
        requested, unknown = parse_insights_sections(None)
        assert requested == {"overview"}
        assert unknown == []

    def test_empty_string_returns_baseline_only(self):
        requested, unknown = parse_insights_sections("")
        assert requested == {"overview"}
        assert unknown == []

    def test_single_section(self):
        requested, unknown = parse_insights_sections("audience")
        assert requested == {"overview", "audience"}
        assert unknown == []

    def test_multiple_sections(self):
        requested, unknown = parse_insights_sections("audience,content")
        assert requested == {"overview", "audience", "content"}
        assert unknown == []

    def test_invalid_names_returned(self):
        requested, unknown = parse_insights_sections("audience,bogus")
        assert requested == {"overview", "audience"}
        assert unknown == ["bogus"]

    def test_baseline_passed_explicitly_not_unknown(self):
        requested, unknown = parse_insights_sections("overview,audience")
        assert requested == {"overview", "audience"}
        assert unknown == []

    def test_whitespace_and_case_handling(self):
        requested, unknown = parse_insights_sections(" Audience , CONTENT ")
        assert requested == {"overview", "audience", "content"}
        assert unknown == []


class TestConfigCompleteness:
    """Ensure every config dict section has a valid suffix."""

    def test_user_sections_all_have_suffixes(self):
        for name, (suffix, _) in USER_SECTIONS.items():
            assert isinstance(suffix, str) and len(suffix) > 0, (
                f"{name} has empty suffix"
            )

    def test_insights_sections_all_have_suffixes(self):
        for name, (suffix, _) in INSIGHTS_SECTIONS.items():
            assert isinstance(suffix, str) and len(suffix) > 0, (
                f"{name} has empty suffix"
            )
