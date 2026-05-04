"""Text processing utilities extracted from the old DOM extractor."""

import re
import logging

logger = logging.getLogger(__name__)

_RATE_LIMITED_MSG = "[Rate limited] Instagram blocked this section. Try again later or request fewer sections."


def strip_instagram_noise(text: str, *, page_type: str = "default") -> str:
    """Remove common noise from Instagram page text.

    Strips navigation labels, empty lines, and other UI chrome that isn't
    actual content. Keeps the signal-to-noise ratio high for downstream
    consumption by LLM tools.
    """
    if not text:
        return text

    noise_phrases = [
        "instagram",
        "search",
        "explore",
        "reels",
        "messages",
        "notifications",
        "create",
        "more",
        "profile",
        "settings",
        "switch to business account",
        "switch to creator account",
        "professional dashboard",
        "insights",
        "activity",
        "saved",
        "following",
        "followers",
        "posts",
        "edit profile",
        "share profile",
        "copy link",
        "report",
        "block",
        "restrict",
        "hide",
        "mute",
        "translate",
        "share",
        "embed",
        "cancel",
        "close",
        "back",
        "delete",
        "confirm",
        "log in",
        "sign up",
        "about",
        "help",
        "press",
        "api",
        "jobs",
        "privacy",
        "terms",
        "location",
        "language",
        "© 2026 instagram from meta",
    ]

    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower() in noise_phrases:
            continue
        if re.match(r"^\d+$", stripped):
            continue
        cleaned.append(stripped)

    result = "\n".join(cleaned)
    logger.debug("Stripped noise: %d → %d chars", len(text), len(result))
    return result
