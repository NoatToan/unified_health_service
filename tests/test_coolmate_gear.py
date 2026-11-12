from __future__ import annotations

from scrapers import coolmate_gear
from scrapers.base import now_iso
from tests.conftest import FakeClient, read_fixture


def _fake_client() -> FakeClient:
    fixture = read_fixture("coolmate_quan_ao_chay_bo.html")
    pages = {
        f"{coolmate_gear.BASE_URL}/collection/{handle}": fixture
        for handle, _category in coolmate_gear.COLLECTIONS
    }
    return FakeClient(pages, default="<html></html>")


def test_scrape_coolmate_gear_fixture():
    client = _fake_client()

    items = coolmate_gear.scrape(client)

    # Same fixture is returned for every collection handle, but scrape()
    # dedupes by product id within one run.
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids))
    assert len(items) > 0

    shorts = next(i for i in items if "Fast & Free III" in i.name)
    assert shorts.sourceName == "coolmate"
    assert shorts.brand == "Coolmate"
    assert shorts.category == "apparel"
    assert shorts.priceVnd == 329000
    assert shorts.productUrl == (
        "https://www.coolmate.me/product/"
        "quan-shorts-nam-chay-bo-2-lop-essentials-fast-free-run-v3-nhanh-kho"
    )
    assert shorts.imageUrl is not None
    assert shorts.imageUrl.startswith("https://mcdn.coolmate.me/")

    # Real multi-color data (several named colors on this one product) -
    # never fabricated. This storefront has no per-color URL, so every
    # variant must point back at the same real product page rather than a
    # guessed one.
    colors = {v.color for v in shorts.variants}
    assert len(colors) >= 2
    for variant in shorts.variants:
        assert variant.productUrl == shorts.productUrl
        assert variant.imageUrl is not None


def test_scrape_coolmate_gear_no_products_returns_empty():
    empty_pages = {
        f"{coolmate_gear.BASE_URL}/collection/{handle}": "<html><body>no data here</body></html>"
        for handle, _category in coolmate_gear.COLLECTIONS
    }
    client = FakeClient(empty_pages)
    assert coolmate_gear.scrape(client) == []


_DETAIL_HREF = "/product/quan-shorts-nam-chay-bo-2-lop-essentials-fast-free-run-v3-nhanh-kho"


def _rsc_chunk_html(text: str) -> str:
    """Wrap `text` as a single `self.__next_f.push([1, "..."])` RSC chunk,
    same shape `_decode_chunks` expects - `text` itself is JSON-string-
    literal-escaped so `_decode_chunks` recovers it byte for byte.
    """
    import json as _json

    escaped = _json.dumps(text)[1:-1]
    return f'<html><body><script>self.__next_f.push([1,"{escaped}"])</script></body></html>'


def _listing_html_for_product(product: dict) -> str:
    import json as _json

    # No spaces around `:`/`,` so this matches `_PRODUCTS_ARRAY_RE`'s literal
    # `"products":[{` the same way a real RSC payload does.
    products_json = _json.dumps([product], ensure_ascii=False, separators=(",", ":"))
    return _rsc_chunk_html('"products":' + products_json)


def test_scrape_coolmate_gear_enriches_item_with_pdp_detail():
    """A real captured PDP (trimmed to its self-contained `initialProduct`
    RSC chunk - tests/fixtures/coolmate_product_detail.html) should fill
    description/specs/features/sizes/gender/sku/originalPriceVnd -
    regression test for the 2026-11-12 detail-enrichment feature.
    """
    handle, _ = coolmate_gear.COLLECTIONS[0]
    listing_product = {
        "id": "6617587040fbdd2b1f09bd70",
        "title": "Quần Shorts Chạy Bộ 2 lớp Fast & Free III",
        "href": _DETAIL_HREF,
        "default_thumbnail": "/image/test-thumb.jpg",
        "regular_price": 329000,
        "mapped_variants": {},
    }
    product_url = coolmate_gear.BASE_URL + _DETAIL_HREF
    pages = {
        f"{coolmate_gear.BASE_URL}/collection/{handle}": _listing_html_for_product(listing_product),
        product_url: read_fixture("coolmate_product_detail.html"),
    }
    client = FakeClient(pages, default="<html></html>")

    items = coolmate_gear.scrape(client)

    item = next(i for i in items if i.productUrl == product_url)
    assert item.description is not None
    assert "✓" not in item.description
    assert item.gender == "men"
    assert item.sku == "24CM.MAWRN.SOZ793"
    assert item.inStock is True
    assert item.originalPriceVnd == 399000
    assert item.specs.get("Chất liệu") == "55% Recycled Polyester, 14% Spandex"
    assert "Co giãn" in item.features
    assert any(s.label == "M" and s.available for s in item.sizes)
    assert item.detailFetchedAt is not None


def test_scrape_coolmate_gear_reuses_fresh_cached_detail_without_refetching():
    handle, _ = coolmate_gear.COLLECTIONS[0]
    listing_product = {
        "id": "6617587040fbdd2b1f09bd70",
        "title": "Quần Shorts Chạy Bộ 2 lớp Fast & Free III",
        "href": _DETAIL_HREF,
        "default_thumbnail": "/image/test-thumb.jpg",
        "regular_price": 329000,
        "mapped_variants": {},
    }
    product_url = coolmate_gear.BASE_URL + _DETAIL_HREF
    # Deliberately no PDP page mapped for `product_url` - a cache miss here
    # would surface as a missing-detail item, not a crash.
    pages = {
        f"{coolmate_gear.BASE_URL}/collection/{handle}": _listing_html_for_product(listing_product),
    }
    client = FakeClient(pages, default="<html></html>")

    previous_by_url = {
        product_url: {
            "description": "Cached shorts description.",
            "gender": "men",
            "sku": "24CM.MAWRN.SOZ793",
            "specs": {"Chất liệu": "Polyester"},
            "features": ["Cached feature"],
            "images": [],
            "sizes": [],
            "inStock": True,
            "originalPriceVnd": None,
            "detailFetchedAt": now_iso(),
        }
    }

    items = coolmate_gear.scrape(client, previous_by_url)

    item = next(i for i in items if i.productUrl == product_url)
    assert item.description == "Cached shorts description."
    assert item.features == ["Cached feature"]
