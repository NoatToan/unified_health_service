from __future__ import annotations

from scrapers import vbm
from tests.conftest import FakeClient, read_fixture


def test_scrape_vbm_fixture_only_upcoming():
    html = read_fixture("vbm_listing.html")
    client = FakeClient({vbm.LISTING_URL: html})

    races = vbm.scrape(client)

    assert len(races) >= 10
    # VBM mixes past and upcoming races; only "upcoming" should come through.
    assert all(r.startDate >= "2026-01-01" for r in races)

    ca_mau = next(r for r in races if "Cà Mau" in r.name)
    assert ca_mau.startDate == "2026-11-15"
    assert ca_mau.province == "Cà Mau"
    labels = [d.label for d in ca_mau.distances]
    assert "42km" in labels
    assert ca_mau.registrationUrl is not None
    assert ca_mau.registrationUrl.startswith("https://bestmarathon.vn/")
    assert ca_mau.sources[0].name == "vbm"
    # Ca Mau's row has no organizer banner image yet (SVG placeholder only in
    # the fixture), but it does have the one-line blurb.
    assert ca_mau.imageUrl is None
    assert ca_mau.description is not None
    assert ca_mau.description.startswith("Giải dự kiến tổ chức ngày 15/11/2026")


def test_scrape_vbm_picks_up_banner_image_when_present():
    html = read_fixture("vbm_listing.html")
    client = FakeClient({vbm.LISTING_URL: html})
    races = vbm.scrape(client)

    trang_an = next(r for r in races if "Trang An" in r.name)
    assert trang_an.imageUrl == "https://anh.bestmarathon.vn/raceLogo/TAM15.11.26.jpg"
    assert trang_an.description is not None


def test_scrape_vbm_terrain_inferred_from_name():
    html = read_fixture("vbm_listing.html")
    client = FakeClient({vbm.LISTING_URL: html})
    races = vbm.scrape(client)

    ultra = next(r for r in races if "Ultra Trail" in r.name)
    assert ultra.terrain == "ultra"

    city_trail = next(r for r in races if "City Trail" in r.name)
    assert city_trail.terrain == "city_trail"
