"""Helpers for extracting compact, typed references from Instagram DOM links."""

from __future__ import annotations

import re
from typing import Literal, NotRequired, Required, TypedDict
from urllib.parse import parse_qs, unquote, urlparse, urlunparse

ReferenceKind = Literal[
    "user",
    "post",
    "reel",
    "hashtag",
    "location",
    "story",
    "live",
    "external",
    "conversation",
]


class Reference(TypedDict):
    """Compact reference payload returned to MCP clients."""

    kind: Required[ReferenceKind]
    url: Required[str]
    text: NotRequired[str]
    context: NotRequired[str]


class RawReference(TypedDict, total=False):
    """Raw anchor data collected from the browser DOM."""

    href: str
    text: str
    aria_label: str
    title: str
    heading: str
    in_article: bool
    in_nav: bool
    in_footer: bool


_GENERIC_LABELS = {
    "show all",
    "follow",
    "following",
    "message",
    "like",
    "comment",
    "share",
    "save",
    "more",
    "play",
    "pause",
    "fullscreen",
    "close",
    "view story",
    "send",
    "subscribe",
    "verified",
}

_CONTEXT_LABELS = {
    "followers",
    "following",
    "posts",
    "reels",
    "tagged",
    "highlights",
    "stories",
    "bio",
}

_SECTION_CONTEXTS = {
    "main_profile": "profile",
    "posts": "posts",
    "reels": "reels",
    "tagged": "tagged",
    "followers": "followers",
    "following": "following",
    "inbox": "inbox",
    "conversation": "conversation",
    "search_results": "search results",
}

_DEFAULT_REFERENCE_CAP = 12
_REFERENCE_CAPS = {
    "main_profile": 12,
    "posts": 15,
    "reels": 12,
    "tagged": 12,
    "followers": 15,
    "following": 15,
    "search_results": 15,
    "inbox": 30,
    "conversation": 12,
}

_URL_LIKE_RE = re.compile(r"^(?:https?://|/)\S+$", re.IGNORECASE)
_DUPLICATE_HALVES_RE = re.compile(r"^(?P<value>.+?)\s+(?P=value)$")
_WHITESPACE_RE = re.compile(r"\s+")

# Instagram URL patterns
INSTAGRAM_USER_PATTERN = re.compile(r"instagram\.com/([a-zA-Z0-9_.]+)/?$")
INSTAGRAM_POST_PATTERN = re.compile(r"instagram\.com/p/([a-zA-Z0-9_-]+)/?")
INSTAGRAM_REEL_PATTERN = re.compile(r"instagram\.com/reel/([a-zA-Z0-9_-]+)/?")
INSTAGRAM_HASHTAG_PATTERN = re.compile(r"instagram\.com/explore/tags/([a-zA-Z0-9_]+)/?")
INSTAGRAM_LOCATION_PATTERN = re.compile(r"instagram\.com/explore/locations/(\d+)/?")
INSTAGRAM_STORY_PATTERN = re.compile(r"instagram\.com/stories/([a-zA-Z0-9_.]+)/(\d+)/?")
INSTAGRAM_LIVE_PATTERN = re.compile(r"instagram\.com/live/(\d+)/?")
INSTAGRAM_DIRECT_THREAD_RE = re.compile(r"instagram\.com/direct/t/([^/?#]+)/")

_MAX_REDIRECT_UNWRAP_DEPTH = 5


def build_references(
    raw_references: list[RawReference],
    section_name: str,
) -> list[Reference]:
    """Filter and normalize raw DOM anchors into compact references."""
    cap = _REFERENCE_CAPS.get(section_name, _DEFAULT_REFERENCE_CAP)
    normalized_references: list[Reference] = []

    for raw in raw_references:
        normalized = normalize_reference(raw, section_name)
        if normalized is None:
            continue
        normalized_references.append(normalized)

    return dedupe_references(normalized_references, cap=cap)


def normalize_reference(
    raw: RawReference,
    section_name: str,
) -> Reference | None:
    """Normalize one raw DOM anchor into a compact reference."""
    if raw.get("in_nav") or raw.get("in_footer"):
        return None

    href = normalize_url(raw.get("href", ""))
    if href is None:
        return None

    kind_url = classify_link(href)
    if kind_url is None:
        return None
    kind, normalized_url = kind_url

    text = choose_reference_text(raw, kind)
    if text is None and kind not in {"post", "external", "conversation"}:
        return None

    context = derive_context(section_name, raw, kind)

    reference: Reference = {
        "kind": kind,
        "url": normalized_url,
    }
    if text:
        reference["text"] = text
    if context:
        reference["context"] = context
    return reference


def normalize_url(href: str, _depth: int = 0) -> str | None:
    """Normalize a raw href and unwrap Instagram redirect URLs."""
    if _depth > _MAX_REDIRECT_UNWRAP_DEPTH:
        return None

    href = href.strip()
    if not href or href.startswith("#"):
        return None

    parsed = urlparse(href)
    scheme = parsed.scheme.lower()
    if scheme in {"blob", "javascript", "mailto", "tel"}:
        return None
    if scheme and scheme not in {"http", "https"}:
        return None

    host = parsed.netloc.lower()
    # Unwrap Instagram redirect URLs (e.g. /l.php?u=...)
    if _is_instagram_host(host) and parsed.path == "/l.php":
        target = unquote((parse_qs(parsed.query).get("u") or [""])[0]).strip()
        if not target:
            return None
        return normalize_url(target, _depth + 1)

    if not parsed.scheme:
        return None

    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def classify_link(href: str) -> tuple[ReferenceKind, str] | None:
    """Classify and canonicalize one normalized URL."""
    parsed = urlparse(href)
    host = parsed.netloc.lower()
    path = parsed.path or "/"

    if not _is_instagram_host(host):
        return "external", urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path or "/", "", "", "")
        )

    if _is_instagram_chrome(path):
        return None

    if match := INSTAGRAM_STORY_PATTERN.search(href):
        return (
            "story",
            f"https://www.instagram.com/stories/{match.group(1)}/{match.group(2)}/",
        )

    if match := INSTAGRAM_LIVE_PATTERN.search(href):
        return "live", f"https://www.instagram.com/live/{match.group(1)}/"

    if match := INSTAGRAM_REEL_PATTERN.search(href):
        return "reel", f"https://www.instagram.com/reel/{match.group(1)}/"

    if match := INSTAGRAM_POST_PATTERN.search(href):
        return "post", f"https://www.instagram.com/p/{match.group(1)}/"

    if match := INSTAGRAM_HASHTAG_PATTERN.search(href):
        return "hashtag", f"https://www.instagram.com/explore/tags/{match.group(1)}/"

    if match := INSTAGRAM_LOCATION_PATTERN.search(href):
        return (
            "location",
            f"https://www.instagram.com/explore/locations/{match.group(1)}/",
        )

    if match := INSTAGRAM_DIRECT_THREAD_RE.search(href):
        return "conversation", f"https://www.instagram.com/direct/t/{match.group(1)}/"

    if match := INSTAGRAM_USER_PATTERN.search(href):
        username = match.group(1)
        # Skip known non-profile paths
        if username in {
            "explore",
            "direct",
            "accounts",
            "stories",
            "reels",
            "p",
            "reel",
            "live",
            "nametag",
            "qr",
        }:
            return None
        return "user", f"https://www.instagram.com/{username}/"

    return None


def choose_reference_text(
    raw: RawReference,
    kind: ReferenceKind,
) -> str | None:
    """Choose the best compact human-readable label for a reference."""
    candidates: list[tuple[int, str]] = []
    for priority, candidate in enumerate(
        (
            raw.get("text", ""),
            raw.get("aria_label", ""),
            raw.get("title", ""),
        )
    ):
        cleaned = clean_label(candidate, kind)
        if cleaned:
            candidates.append((priority, cleaned))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (_label_sort_key(item[1]), item[0]))
    return candidates[0][1]


def clean_label(value: str, kind: ReferenceKind) -> str | None:
    """Normalize and compact a candidate label."""
    value = _WHITESPACE_RE.sub(" ", value).strip()
    if not value:
        return None

    value = re.sub(
        r"^(?:View:\s*|View\b\s+|Open post:\s*)",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"[’']s\s+profile$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+profile$", "", value, flags=re.IGNORECASE)
    value = value.strip(" :-")

    for separator in (" • ", " · ", " | "):
        if separator in value:
            value = value.split(separator, 1)[0].strip()

    duplicate_match = _DUPLICATE_HALVES_RE.match(value)
    if duplicate_match:
        value = duplicate_match.group("value").strip()

    if _URL_LIKE_RE.match(value):
        return None
    if value.lower() in _GENERIC_LABELS:
        return None
    if len(value) < 2:
        return None
    if len(value) > 80:
        return None
    if not re.search(r"[A-Za-z0-9]", value):
        return None

    return value


def derive_context(
    section_name: str,
    raw: RawReference,
    kind: ReferenceKind,
) -> str | None:
    """Build a compact context hint for one retained reference."""
    if section_name in _SECTION_CONTEXTS:
        return _SECTION_CONTEXTS[section_name]

    heading = clean_heading(raw.get("heading", ""))

    if section_name == "search_results":
        return "search result"

    if section_name == "posts":
        if kind == "user":
            return "post author"
        if kind == "post":
            return "post"
        return "post attachment"

    if section_name == "main_profile":
        if heading in _CONTEXT_LABELS:
            return heading
        if raw.get("in_article"):
            return "featured"
        return "profile"

    return heading if heading in _CONTEXT_LABELS else None


def clean_heading(value: str) -> str | None:
    """Normalize a raw heading into a short supported context label."""
    value = _WHITESPACE_RE.sub(" ", value).strip().lower()
    if not value:
        return None
    return value if value in _CONTEXT_LABELS else None


def _choose_better_reference(existing: Reference, new: Reference) -> Reference:
    """Keep the cleaner, richer of two duplicate-url references."""
    existing_score = _reference_score(existing)
    new_score = _reference_score(new)
    return new if new_score > existing_score else existing


def dedupe_references(
    references: list[Reference],
    cap: int | None = None,
) -> list[Reference]:
    """Dedupe references by URL while keeping the cleaner duplicate in order."""
    deduped: dict[str, Reference] = {}
    ordered_urls: list[str] = []

    for reference in references:
        url = reference["url"]
        existing = deduped.get(url)
        if existing is None:
            deduped[url] = reference
            ordered_urls.append(url)
            continue
        deduped[url] = _choose_better_reference(existing, reference)

    ordered = [deduped[url] for url in ordered_urls]
    return ordered[:cap] if cap is not None else ordered


def _reference_score(reference: Reference) -> tuple[int, int, int | float]:
    text = reference.get("text")
    context = reference.get("context")
    return (
        1 if text else 0,
        1 if context else 0,
        _text_score(text),
    )


def _label_sort_key(label: str) -> tuple[int, int]:
    """Prefer concise labels, but deprioritize short 2-character strings."""
    return (1 if len(label) < 3 else 0, len(label))


def _text_score(text: str | None) -> int | float:
    """Prefer richer labels while scoring missing text as strictly worst."""
    return len(text) if text else float("-inf")


def _is_instagram_chrome(path: str) -> bool:
    """Return True for Instagram app-chrome paths that aren't real content."""
    path = path.split("?", 1)[0].split("#", 1)[0]
    if not path.startswith("/"):
        path = f"/{path}"

    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False

    first = segments[0]

    if first in {
        "accounts",
        "nametag",
        "qr",
        "session",
        "static",
        "oauth",
        "api",
        "data",
        "graphql",
        "emails",
        "push",
        "logging",
        "client",
    }:
        return True

    return False


def _is_instagram_host(host: str) -> bool:
    return (
        host == "www.instagram.com"
        or host == "instagram.com"
        or host.endswith(".instagram.com")
    )
