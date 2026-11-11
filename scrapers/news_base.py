"""Shared building blocks for the news/knowledge-content scrapers: the
NewsItem model and a keyword-based category classifier.

This is a METADATA/SNIPPET aggregator, not a full-text republisher: every
item always keeps `sourceUrl` as the only way to read the full article, and
`summary` is a short best-effort excerpt (never the full article body).

Reuses `scrapers.base` for the polite HTTP client, slugify and
unidecode-based keyword matching conventions already established by the
race scrapers - no parallel HTTP/robots.txt/rate-limit stack is introduced
here.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel
from unidecode import unidecode

VALID_CATEGORIES = {"race-news", "training-tips", "gear", "event-recap"}


class NewsItem(BaseModel):
    id: str
    title: str
    sourceName: str
    sourceUrl: str
    publishedAt: str
    summary: str | None = None
    imageUrl: str | None = None
    category: str = "race-news"


# --------------------------------------------------------------------------- #
# Category classification
# --------------------------------------------------------------------------- #
# Best-effort keyword heuristic, same spirit as scrapers.base.guess_terrain:
# checked in priority order (gear, then training-tips, then event-recap),
# falling back to "race-news" for anything else (announcements, opinion
# pieces, human-interest stories) - a reasonable default since the field is
# best-effort metadata, not a guaranteed-precise taxonomy.

_GEAR_KEYWORDS = [
    "giay chay", "giay", "ao chay", "quan chay", "dong ho", "danh gia",
    "review", "dap hop", "trang bi", "phu kien", "san pham", "thiet bi",
    "mu chay", "balo chay", "vo chay bo",
]
_TRAINING_KEYWORDS = [
    "luyen tap", "giao an", "chan thuong", "dinh duong", "ky thuat chay",
    "phuc hoi", "hoi phuc", "bi quyet", "huong dan", "cach chay", "tap chay",
    "suc khoe", "hrv", "vo2", "hoi chung", "nguy hiem",
    "giam can", "calo",
]
_EVENT_RECAP_KEYWORDS = [
    "vo dich", "ket qua", "ve dich", "pha ky luc", "ky luc", "chung ket",
    "hoan thanh cu ly", "tu vong", "gianh hcv", "gianh giai", "doat giai",
]


def classify_category(title: str, extra_text: str | None = None) -> str:
    """Best-effort category for a news item: `race-news | training-tips |
    gear | event-recap`. Keyword matching is done on accent-stripped,
    lowercased text (title plus any extra hint text, e.g. an RSS
    <category> tag), same normalization as guess_terrain() in
    scrapers.base.
    """
    haystack = unidecode(f"{title} {extra_text or ''}").lower()

    for kw in _GEAR_KEYWORDS:
        if kw in haystack:
            return "gear"
    for kw in _TRAINING_KEYWORDS:
        if kw in haystack:
            return "training-tips"
    for kw in _EVENT_RECAP_KEYWORDS:
        if kw in haystack:
            return "event-recap"
    return "race-news"


# --------------------------------------------------------------------------- #
# Stable id
# --------------------------------------------------------------------------- #

_URL_SLUG_RE = re.compile(r"[^a-z0-9]+")


def strip_tracking_params(url: str) -> str:
    """Drop `utm_*` (and similar) tracking query params some feeds (e.g.
    WordPress's own RSS plugin on vnrun.com) append to every link, so
    `sourceUrl` is the clean canonical article URL rather than a
    campaign-tagged one.
    """
    parsed = urlparse(url)
    if not parsed.query:
        return url
    kept = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith(("utm_", "fbclid", "gclid"))
    ]
    return urlunparse(parsed._replace(query=urlencode(kept)))


def make_news_id(source_name: str, url: str) -> str:
    """A stable id derived from the source name and the article URL's last
    path segment (stripped of its .html/.htm extension and any query
    string) - deterministic across runs for the same article, independent
    of title text that a source might tweak slightly on re-publish.
    """
    path = url.split("?", 1)[0].rstrip("/")
    last_segment = path.rsplit("/", 1)[-1]
    last_segment = re.sub(r"\.html?$", "", last_segment, flags=re.IGNORECASE)
    slug = unidecode(last_segment).lower()
    slug = _URL_SLUG_RE.sub("-", slug).strip("-")
    return f"{source_name}-{slug}"
