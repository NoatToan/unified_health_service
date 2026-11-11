from __future__ import annotations

from scrapers import vnrun_news
from tests.conftest import FakeClient, read_fixture


def test_scrape_vnrun_news_fixture():
    xml = read_fixture("vnrun_news_feed.xml")
    client = FakeClient({vnrun_news.FEED_URL: xml})

    items = vnrun_news.scrape(client)

    assert len(items) == 10
    first = next(
        i for i in items if "Top đồng hồ chạy bộ" in i.title
    )
    assert first.sourceName == "vnrun"
    # Tracking params (utm_*) stripped from the RSS-provided link.
    assert "utm_" not in first.sourceUrl
    assert first.sourceUrl == "https://vnrun.com/top-dong-ho-chay-bo-ngon-bo-re-danh-cho-runner-moi-bat-dau/"
    assert first.publishedAt == "2026-03-10T18:34:33Z"
    assert first.summary is not None
    # WordPress's own "[...]" truncation marker should be HTML-unescaped,
    # and the auto-appended "The post ... first appeared on ..." boilerplate
    # must not leak into the snippet.
    assert "…" in first.summary or "..." in first.summary
    assert "first appeared on" not in first.summary
    assert first.imageUrl is not None
    assert first.imageUrl.endswith(".jpg")
    assert first.category == "gear"


def test_scrape_vnrun_news_empty_feed_returns_empty():
    client = FakeClient({vnrun_news.FEED_URL: "<rss><channel></channel></rss>"})
    assert vnrun_news.scrape(client) == []
