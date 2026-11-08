from __future__ import annotations

from scrapers import irace
from tests.conftest import FakeClient, read_fixture


def test_scrape_irace_fixture_page1_only():
    html = read_fixture("irace_listing_page1.html")
    # Only page 1 has content; later pages return empty HTML so pagination
    # stops immediately (keeps the test fast and deterministic).
    client = FakeClient({irace.BASE_URL: html}, default="<html><body></body></html>")

    races = irace.scrape(client)

    assert len(races) == 9

    nghe_an = next(r for r in races if "Nghệ An Legacy" in r.name)
    assert nghe_an.startDate == "2026-12-06"
    assert nghe_an.province == "Nghệ An"
    assert nghe_an.priceFromVnd == 450_000
    assert nghe_an.registrationStatus == "open"
    assert nghe_an.registrationUrl == "https://ticket.irace.vn/nghe-an-legacy-marathon-2026"
    # Listing-page card image is picked up directly - no extra request needed.
    assert nghe_an.imageUrl == (
        "https://w.irace.com.vn/m/o/photos/events/nghe-an-legacy-marathon-2026/6a4f6456ae3f4.png"
    )

    closed = next(r for r in races if "Hai Phong Legacy" in r.name)
    assert closed.registrationStatus == "closed"
    assert closed.priceFromVnd is None


def test_scrape_irace_stops_when_no_cards():
    client = FakeClient({}, default="<html><body>no events</body></html>")
    races = irace.scrape(client)
    assert races == []
