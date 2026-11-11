"""News/knowledge-content scraper: Tuổi Trẻ Online's "marathon" tag page -
race recaps, results, and running-related stories from a national
newspaper.

https://tuoitre.vn/marathon.html

Server-rendered static HTML (`article.box-category-item`). robots.txt
(`Allow: /`, with only search/print/login-script paths disallowed) permits
this page. Each item carries a full local-time timestamp in
`span.box-category-time[title]` (format `M/D/YYYY h:mm:ss AM/PM`,
Vietnam time, UTC+7) - converted to UTC for `publishedAt`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from scrapers.base import PoliteClient, truncate_text
from scrapers.news_base import NewsItem, classify_category, make_news_id

SOURCE_NAME = "tuoitre"
LISTING_URL = "https://tuoitre.vn/marathon.html"
_BASE_URL = "https://tuoitre.vn"
_VN_OFFSET = timedelta(hours=7)


def scrape(client: PoliteClient) -> list[NewsItem]:
    resp = client.get(LISTING_URL)
    tree = HTMLParser(resp.text)

    items: list[NewsItem] = []
    for node in tree.css("article.box-category-item"):
        item = _parse_item(node)
        if item is not None:
            items.append(item)
    return items


def _parse_item(item) -> NewsItem | None:
    title_a = item.css_first("a.box-category-link-title")
    if title_a is None:
        return None
    href = (title_a.attributes.get("href") or "").strip()
    title = (title_a.attributes.get("title") or title_a.text(strip=True)).strip()
    if not href or not title:
        return None
    url = urljoin(_BASE_URL, href)

    time_span = item.css_first("span.box-category-time")
    published_iso = _parse_timestamp(time_span.attributes.get("title") if time_span else None)
    if published_iso is None:
        return None

    summary = None
    sapo = item.css_first("p.box-category-sapo")
    if sapo is not None:
        text = sapo.text(strip=True)
        if text:
            summary = truncate_text(text)

    image_url = None
    avatar = item.css_first("img.box-category-avatar")
    if avatar is not None:
        src = (avatar.attributes.get("src") or "").strip()
        if src:
            image_url = src

    return NewsItem(
        id=make_news_id(SOURCE_NAME, url),
        title=title,
        sourceName=SOURCE_NAME,
        sourceUrl=url,
        publishedAt=published_iso,
        summary=summary,
        imageUrl=image_url,
        category=classify_category(title, summary),
    )


def _parse_timestamp(text: str | None) -> str | None:
    """Parse the `title` attribute of `span.box-category-time`, e.g.
    "11/8/2026 11:06:00 AM" (M/D/YYYY, Vietnam local time) -> UTC ISO-8601.
    """
    if not text:
        return None
    try:
        local = datetime.strptime(text.strip(), "%m/%d/%Y %I:%M:%S %p")
    except ValueError:
        return None
    utc = (local - _VN_OFFSET).replace(tzinfo=timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")
