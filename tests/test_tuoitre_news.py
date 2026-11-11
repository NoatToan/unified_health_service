from __future__ import annotations

from scrapers import tuoitre_news
from tests.conftest import FakeClient, read_fixture


def test_scrape_tuoitre_news_fixture():
    html = read_fixture("tuoitre_news_listing.html")
    client = FakeClient({tuoitre_news.LISTING_URL: html})

    items = tuoitre_news.scrape(client)

    assert len(items) >= 10
    first = next(
        i for i in items if "Hoàng Nguyên Thanh vô địch" in i.title
    )
    assert first.sourceName == "tuoitre"
    assert first.sourceUrl == (
        "https://tuoitre.vn/hoang-nguyen-thanh-vo-dich-giai-marathon-"
        "di-san-ha-noi-2026-100261108105511592.htm"
    )
    # "11:06 08/11/2026" local (Vietnam, UTC+7) -> "2026-11-08T04:06:00Z"
    assert first.publishedAt == "2026-11-08T04:06:00Z"
    assert first.summary is not None
    assert first.imageUrl is not None
    assert first.imageUrl.startswith("https://")
    assert first.category == "event-recap"


def test_scrape_tuoitre_news_missing_container_returns_empty():
    client = FakeClient({tuoitre_news.LISTING_URL: "<html><body>nothing here</body></html>"})
    assert tuoitre_news.scrape(client) == []


def test_parse_timestamp_handles_am_pm():
    assert tuoitre_news._parse_timestamp("11/8/2026 11:06:00 AM") == "2026-11-08T04:06:00Z"
    assert tuoitre_news._parse_timestamp("11/8/2026 11:06:00 PM") == "2026-11-08T16:06:00Z"
    assert tuoitre_news._parse_timestamp(None) is None
    assert tuoitre_news._parse_timestamp("not a date") is None
