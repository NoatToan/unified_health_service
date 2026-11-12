from __future__ import annotations

import pipeline.gear_main as gear_main
from pipeline.gear_main import dedupe_by_url, run_scrapers
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


def test_run_scrapers_passes_previous_items_keyed_by_url_to_each_scraper(monkeypatch):
    """`run_scrapers` must build a `productUrl -> raw item dict` map from the
    previous run's `latest.json` and pass it to every scraper, so each
    scraper's own `enrich_with_detail` call can decide whether a product's
    cached detail is still fresh enough to reuse - regression test for the
    2026-11-12 detail-cache wiring.
    """
    received: dict = {}

    def fake_scrape(client, previous_by_url=None):
        received["previous_by_url"] = previous_by_url
        return [_item("https://example.com/new", source="fake")]

    monkeypatch.setattr(gear_main, "SCRAPERS", [("fake", fake_scrape)])

    previous_raw_item = {
        "sourceName": "fake",
        "productUrl": "https://example.com/old",
        "detailFetchedAt": "2026-11-05T00:00:00Z",
    }
    previous = {"items": [previous_raw_item]}

    items, reports = run_scrapers(client=None, previous=previous)

    assert received["previous_by_url"] == {"https://example.com/old": previous_raw_item}
    assert reports == [{"name": "fake", "ok": True, "count": 1, "error": None}]
    assert [i.productUrl for i in items] == ["https://example.com/new"]


def test_run_scrapers_with_no_previous_run_passes_empty_map(monkeypatch):
    received: dict = {}

    def fake_scrape(client, previous_by_url=None):
        received["previous_by_url"] = previous_by_url
        return [_item("https://example.com/new", source="fake")]

    monkeypatch.setattr(gear_main, "SCRAPERS", [("fake", fake_scrape)])

    run_scrapers(client=None, previous=None)

    assert received["previous_by_url"] == {}
