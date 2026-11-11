from __future__ import annotations

from pipeline.gear_main import dedupe_by_url
from scrapers.gear_base import GearItem


def _item(url: str, name: str = "T", source: str = "src") -> GearItem:
    return GearItem(
        id=f"{source}-{url}",
        name=name,
        brand="Brand",
        category="shoes",
        sourceName=source,
        productUrl=url,
        crawledAt="2026-11-11T00:00:00Z",
    )


def test_dedupe_by_url_drops_exact_duplicate_urls():
    a = _item("https://example.com/a")
    b = _item("https://example.com/a", name="Different name, same URL")
    c = _item("https://example.com/b")

    result = dedupe_by_url([a, b, c])

    urls = {i.productUrl for i in result}
    assert urls == {"https://example.com/a", "https://example.com/b"}
    assert len(result) == 2


def test_dedupe_by_url_keeps_distinct_urls():
    items = [_item("https://example.com/a"), _item("https://example.com/b")]
    assert len(dedupe_by_url(items)) == 2
