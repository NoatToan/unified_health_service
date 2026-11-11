from __future__ import annotations

from pipeline.news_main import dedupe_by_url
from scrapers.news_base import NewsItem


def _item(url: str, title: str = "T", published: str = "2026-11-08T00:00:00Z") -> NewsItem:
    return NewsItem(
        id=f"src-{url}",
        title=title,
        sourceName="src",
        sourceUrl=url,
        publishedAt=published,
    )


def test_dedupe_by_url_drops_exact_duplicate_urls():
    a = _item("https://example.com/a")
    b = _item("https://example.com/a", title="Different title, same URL")
    c = _item("https://example.com/b")

    result = dedupe_by_url([a, b, c])

    urls = {i.sourceUrl for i in result}
    assert urls == {"https://example.com/a", "https://example.com/b"}
    assert len(result) == 2


def test_dedupe_by_url_keeps_distinct_urls():
    items = [_item("https://example.com/a"), _item("https://example.com/b")]
    assert len(dedupe_by_url(items)) == 2
