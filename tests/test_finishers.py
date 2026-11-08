from __future__ import annotations

from scrapers import finishers
from tests.conftest import FakeClient, read_fixture


def test_scrape_finishers_fixture():
    html = read_fixture("finishers_vietnam.html")
    client = FakeClient({finishers.LISTING_URL: html})

    races = finishers.scrape(client)

    assert len(races) >= 10

    hanoi = next(r for r in races if "Hanoi Marathon Heritage Race" in r.name)
    assert hanoi.startDate == "2026-11-07"
    assert hanoi.terrain == "road"
    labels = [d.label for d in hanoi.distances]
    assert "42km" in labels
    assert hanoi.registrationUrl == "https://www.finishers.com/event/hanoi-marathon"
    assert hanoi.sources[0].name == "finishers"

    ironman = next(r for r in races if "Ironman" in r.name)
    assert ironman.terrain == "triathlon"

    # A distance reported as a float number of meters (21097.5) should still
    # resolve to the conventional half-marathon label, not a stray decimal.
    for r in races:
        for d in r.distances:
            assert "." not in d.label or d.label not in ("21.0975km",)


def test_scrape_finishers_missing_next_data_returns_empty():
    client = FakeClient({finishers.LISTING_URL: "<html><body>no data here</body></html>"})
    assert finishers.scrape(client) == []
