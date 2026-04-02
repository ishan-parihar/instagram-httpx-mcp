"""Section config dicts for Instagram scraping."""

import logging

logger = logging.getLogger(__name__)

# User profile sections - each maps to one Instagram URL
USER_SECTIONS: dict[str, tuple[str, bool]] = {
    "main_profile": ("/", False),
    "posts": ("/", False),  # Posts are on main profile page
    "reels": ("/reels/", False),
    "tagged": ("/tagged/", False),
    "followers": ("/followers/", False),
    "following": ("/following/", False),
}

# Business/Creator insights sections
INSIGHTS_SECTIONS: dict[str, tuple[str, bool]] = {
    "overview": ("/professional_dashboard/", False),
    "audience": ("/professional_dashboard/?tab=audience", False),
    "content": ("/professional_dashboard/?tab=content", False),
    "activity": ("/professional_dashboard/?tab=activity", False),
}

# Search sections
# Instagram search uses client-side routing - these URLs may require being logged in
SEARCH_SECTIONS: dict[str, tuple[str, bool]] = {
    "users": ("/web/search/top/?q=", False),
    "hashtags": ("/web/search/top/?q=%23", False),
    "locations": ("/web/search/locations/?q=", False),
}


def parse_user_sections(
    sections: str | None,
) -> tuple[set[str], list[str]]:
    """Parse comma-separated section names into a set of requested sections.

    "main_profile" is always included. Empty/None returns {"main_profile"} only.
    Unknown section names are logged as warnings and returned.

    Returns:
        Tuple of (requested_sections, unknown_section_names).
    """
    requested: set[str] = {"main_profile"}
    unknown: list[str] = []
    if not sections:
        return requested, unknown
    for name in sections.split(","):
        name = name.strip().lower()
        if not name:
            continue
        if name in USER_SECTIONS:
            requested.add(name)
        else:
            unknown.append(name)
            logger.warning(
                "Unknown user section %r ignored. Valid: %s",
                name,
                ", ".join(sorted(USER_SECTIONS)),
            )
    return requested, unknown


def parse_insights_sections(
    sections: str | None,
) -> tuple[set[str], list[str]]:
    """Parse comma-separated section names into a set of requested sections.

    "overview" is always included. Empty/None returns {"overview"} only.
    Unknown section names are logged as warnings and returned.

    Returns:
        Tuple of (requested_sections, unknown_section_names).
    """
    requested: set[str] = {"overview"}
    unknown: list[str] = []
    if not sections:
        return requested, unknown
    for name in sections.split(","):
        name = name.strip().lower()
        if not name:
            continue
        if name in INSIGHTS_SECTIONS:
            requested.add(name)
        else:
            unknown.append(name)
            logger.warning(
                "Unknown insights section %r ignored. Valid: %s",
                name,
                ", ".join(sorted(INSIGHTS_SECTIONS)),
            )
    return requested, unknown
