"""News/knowledge-content scraper: VNRUN's RSS feed - a Vietnamese running
community media outlet, mostly gear reviews and training-tip articles.

https://vnrun.com/feed/

A real RSS 2.0 feed (standard WordPress `/feed/`), parsed with `feedparser`
rather than HTML-scraped - fetched through the same `PoliteClient` as every
other source (still checks robots.txt/rate-limits, no special-casing), just
with XML parsing instead of CSS selectors. `<description>` is WordPress's
own auto-excerpt (already truncated with "[…]"), not the full article body
- `content:encoded` (the full post) is only ever used here to pull the
post's first image, never its text.
"""
from __future__ import annotations

import html
import re
import time

import feedparser

from scrapers.base import PoliteClient, truncate_text
from scrapers.news_base import NewsItem, classify_category, make_news_id, strip_tracking_params

SOURCE_NAME = "vnrun"
FEED_URL = "https://vnrun.com/feed/"

_TAG_RE = re.compile(r"<[^>]+>")
_WP_MORE_SUFFIX_RE = re.compile(r"The post .* first appeared on .*\.?\s*$", re.IGNORECASE | re.DOTALL)
_IMG_SRC_RE = re.compile(r'<img[^>]+src="([^"]+)"')


def scrape(client: PoliteClient) -> list[NewsItem]:
    resp = client.get(FEED_URL)
    parsed = feedparser.parse(resp.text)

    items: list[NewsItem] = []
    for entry in parsed.entries:
        item = _parse_entry(entry)
        if item is not None:
            items.append(item)
    return items


def _parse_entry(entry) -> NewsItem | None:
    url = strip_tracking_params((entry.get("link") or "").strip())
    title = (entry.get("title") or "").strip()
    if not url or not title:
        return None

    published_iso = None
    if entry.get("published_parsed"):
        published_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", entry.published_parsed)
    if published_iso is None:
        return None

    summary = _clean_summary(entry.get("summary"))

    image_url = None
    content_list = entry.get("content")
    if content_list:
        m = _IMG_SRC_RE.search(content_list[0].get("value", ""))
        if m:
            image_url = m.group(1)

    category_hint = " ".join(t.get("term", "") for t in entry.get("tags", []))

    return NewsItem(
        id=make_news_id(SOURCE_NAME, url),
        title=title,
        sourceName=SOURCE_NAME,
        sourceUrl=url,
        publishedAt=published_iso,
        summary=summary,
        imageUrl=image_url,
        category=classify_category(title, f"{summary or ''} {category_hint}"),
    )


def _clean_summary(raw_html: str | None) -> str | None:
    if not raw_html:
        return None
    no_wp_suffix = _WP_MORE_SUFFIX_RE.sub("", raw_html)
    text = _TAG_RE.sub(" ", no_wp_suffix)
    text = html.unescape(text)
    text = " ".join(text.split())
    if not text:
        return None
    return truncate_text(text)
