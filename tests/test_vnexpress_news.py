from __future__ import annotations

from datetime import date

from scrapers import vnexpress_news
from tests.conftest import FakeClient, read_fixture


def test_scrape_vnexpress_news_fixture():
    html = read_fixture("vnexpress_news_listing.html")
    client = FakeClient({vnexpress_news.LISTING_URL: html})

    items = vnexpress_news.scrape(client)

    assert len(items) >= 10
    first = next(
        i for i in items if "Người phụ nữ đầu tiên chạy 160 km ở Nam Cực" in i.title
    )
    assert first.sourceName == "vnexpress"
    assert first.sourceUrl.startswith("https://vnexpress.net/")
    assert first.publishedAt == "2026-11-11T00:00:00Z"
    assert first.summary is not None
    assert "phù thủy" not in first.summary  # sanity: this is a different item
    assert first.imageUrl is not None
    assert first.category in {"race-news", "training-tips", "gear", "event-recap"}

    # No location-stamp leaking into the summary without a separating space.
    weather_item = next(
        i for i in items if "phù thủy" in i.title
    )
    assert weather_item.summary is not None
    assert not weather_item.summary.startswith("Mỹ")  # location-stamp stripped
    assert "Lo ngại" in weather_item.summary


def test_scrape_vnexpress_news_missing_container_returns_empty():
    client = FakeClient({vnexpress_news.LISTING_URL: "<html><body>nothing here</body></html>"})
    assert vnexpress_news.scrape(client) == []


def test_resolve_year_wraps_at_year_boundary():
    # Running the crawl in January, an article dated in December must
    # resolve to the previous year.
    assert vnexpress_news._resolve_year(12, date(2027, 1, 5)) == 2026
    assert vnexpress_news._resolve_year(11, date(2026, 11, 20)) == 2026
