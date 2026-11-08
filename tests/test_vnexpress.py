from __future__ import annotations

from scrapers import vnexpress
from tests.conftest import FakeClient, read_fixture


def test_scrape_vnexpress_fixture():
    html = read_fixture("vnexpress_listing.html")
    client = FakeClient({vnexpress.LISTING_URL: html})

    races = vnexpress.scrape(client)

    assert len(races) >= 5
    first = next(r for r in races if r.name == "Hanoi Marathon Heritage Race")
    assert first.startDate == "2026-11-08"
    assert first.province == "Hà Nội"
    assert first.terrain == "road"
    labels = [d.label for d in first.distances]
    assert "42km" in labels
    assert any(d.km == 42.195 for d in first.distances if d.label == "42km")
    assert first.sources[0].name == "vnexpress"
    assert first.sources[0].url == vnexpress.LISTING_URL

    # December entries (second month header) should also be parsed with the
    # right year carried over.
    december_names = [r.name for r in races if r.startDate.startswith("2026-12")]
    assert december_names, "expected at least one December race"


def test_scrape_vnexpress_missing_container_returns_empty():
    client = FakeClient({vnexpress.LISTING_URL: "<html><body>nothing here</body></html>"})
    races = vnexpress.scrape(client)
    assert races == []
