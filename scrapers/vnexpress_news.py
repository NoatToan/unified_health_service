"""News/knowledge-content scraper: VnExpress "Thông tin chạy bộ" (running
news hub) - race announcements, training tips, gear, and recaps, all in one
listing.

https://vnexpress.net/the-thao/marathon/tin-tuc

Server-rendered static HTML, same `article.item-news` markup family as the
rest of VnExpress's site. The listing only publishes a `dd/MM` date (no
year, no time) - see `_resolve_year()` for how the year is inferred, and
`publishedAt` is set to that date at 00:00:00 UTC since no time-of-day is
available on this listing page (best-effort, consistent with this project's
"metadata/snippet aggregator" scope - exact publish time isn't needed for
sorting purposes beyond the day).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from scrapers.base import PoliteClient, truncate_text
from scrapers.news_base import NewsItem, classify_category, make_news_id

SOURCE_NAME = "vnexpress"
LISTING_URL = "https://vnexpress.net/the-thao/marathon/tin-tuc"


def scrape(client: PoliteClient) -> list[NewsItem]:
    resp = client.get(LISTING_URL)
    tree = HTMLParser(resp.text)

    today = datetime.now(timezone.utc).date()
    items: list[NewsItem] = []
    for node in tree.css("article.item-news"):
        item = _parse_item(node, today)
        if item is not None:
            items.append(item)
    return items


def _resolve_year(month: int, run_date: date) -> int:
    """The listing has no year in its `dd/MM` dates. Since this page only
    ever shows already-published (i.e. past-or-today) articles, the year is
    `run_date.year` unless the parsed month is later than today's month -
    which only happens right after a year boundary (e.g. a December article
    still showing while running in January) - in which case it's the
    previous year.
    """
    return run_date.year - 1 if month > run_date.month else run_date.year


def _parse_item(item, run_date: date) -> NewsItem | None:
    title_a = item.css_first("h2.title-news a")
    if title_a is None:
        return None
    url = (title_a.attributes.get("href") or "").strip()
    title = (title_a.attributes.get("title") or title_a.text(strip=True)).strip()
    if not url or not title:
        return None

    meta = item.css_first("p.meta-news")
    date_text = meta.text(deep=False, strip=True) if meta is not None else ""
    published_iso = _parse_date(date_text, run_date)
    if published_iso is None:
        return None

    summary = None
    desc_p = item.css_first("p.description")
    if desc_p is not None:
        full_text = desc_p.text(strip=True)
        loc_stamp = desc_p.css_first(".location-stamp")
        if loc_stamp is not None:
            loc_text = loc_stamp.text(strip=True)
            if full_text.startswith(loc_text):
                full_text = full_text[len(loc_text):].strip()
        if full_text:
            summary = truncate_text(full_text)

    image_url = None
    thumb_img = item.css_first(".thumb-art img")
    if thumb_img is not None:
        src = (thumb_img.attributes.get("src") or "").strip()
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


def _parse_date(text: str, run_date: date) -> str | None:
    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})", text)
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    year = _resolve_year(month, run_date)
    try:
        d = date(year, month, day)
    except ValueError:
        return None
    return d.strftime("%Y-%m-%dT00:00:00Z")
