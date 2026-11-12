from __future__ import annotations

import json

from scrapers import lining_gear
from scrapers.base import now_iso
from tests.conftest import FakeClient, read_fixture


def _fake_client() -> FakeClient:
    fixture = read_fixture("lining_giay_chay_bo_products.json")
    pages = {
        f"{lining_gear.BASE_URL}/collections/{handle}/products.json?limit={lining_gear.PRODUCTS_PER_PAGE}": fixture
        for handle, _category in lining_gear.COLLECTIONS
    }
    return FakeClient(pages, default='{"products": []}')


def test_scrape_lining_gear_fixture():
    client = _fake_client()

    items = lining_gear.scrape(client)

    # Same fixture is returned for every collection handle, but scrape()
    # dedupes by product handle within one run, so each real product in the
    # fixture should appear exactly once despite being "found" 4 times.
    urls = [i.productUrl for i in items]
    assert len(urls) == len(set(urls))
    assert len(items) > 0

    shoe = next(i for i in items if "ARHW017-8V" in i.name)
    assert shoe.sourceName == "lining"
    assert shoe.brand == "Li-Ning"
    assert shoe.category == "shoes"
    assert shoe.priceVnd == 1659273
    assert shoe.productUrl == (
        "https://lining.com.vn/products/giay-chay-bo-infinity-6-nam-arhw017-8v"
    )
    assert shoe.imageUrl is not None
    # No sibling-color navigation exists on this storefront (confirmed in
    # docs_research/GEAR_SOURCES_RESEARCH.md) - variants must never be
    # fabricated for a source that doesn't expose them.
    assert shoe.variants == []


def test_scrape_lining_gear_empty_collection_returns_empty():
    client = FakeClient({}, default='{"products": []}')
    assert lining_gear.scrape(client) == []


_DETAIL_HANDLE = "giay-chay-bo-super-light-23-nam-arbw017-17v"


def _listing_payload_for_handle(handle: str) -> str:
    return json.dumps(
        {
            "products": [
                {
                    "title": "Giày chạy bộ Super Light 23 Nam ARBW017-17V",
                    "handle": handle,
                    "images": [{"src": "https://cdn.hstatic.net/listing.jpg"}],
                    "variants": [{"price": "2444727.00"}],
                    "product_type": "Giày chạy bộ",
                }
            ]
        }
    )


def test_scrape_lining_gear_enriches_item_with_pdp_detail():
    """A real captured `/products/<handle>.json` detail payload (trimmed
    fixture tests/fixtures/lining_product_detail.json) should fill
    description/specs/features/sizes/gender/sku - regression test for the
    2026-11-12 detail-enrichment feature.
    """
    handle, _ = lining_gear.COLLECTIONS[0]
    listing_url = (
        f"{lining_gear.BASE_URL}/collections/{handle}/products.json"
        f"?limit={lining_gear.PRODUCTS_PER_PAGE}"
    )
    product_url = f"{lining_gear.BASE_URL}/products/{_DETAIL_HANDLE}"
    pages = {
        listing_url: _listing_payload_for_handle(_DETAIL_HANDLE),
        f"{product_url}.json": read_fixture("lining_product_detail.json"),
    }
    client = FakeClient(pages, default='{"products": []}')

    items = lining_gear.scrape(client)

    item = next(i for i in items if i.productUrl == product_url)
    assert item.description is not None
    assert "boom" in item.description.lower() or "li-ning" in item.description.lower()
    assert item.gender == "men"
    assert item.sku == "ARBW017-17V"
    assert item.specs.get("Công nghệ") == "BOOM +Boom Fiber+Tempo Technology"
    assert "Dùng khăn ẩm lau bụi bẩn và bùn đất." not in item.features
    assert any(s.label == "7.5" and s.available for s in item.sizes)
    assert item.detailFetchedAt is not None


def test_scrape_lining_gear_reuses_fresh_cached_detail_without_refetching():
    handle, _ = lining_gear.COLLECTIONS[0]
    listing_url = (
        f"{lining_gear.BASE_URL}/collections/{handle}/products.json"
        f"?limit={lining_gear.PRODUCTS_PER_PAGE}"
    )
    product_url = f"{lining_gear.BASE_URL}/products/{_DETAIL_HANDLE}"
    pages = {listing_url: _listing_payload_for_handle(_DETAIL_HANDLE)}
    client = FakeClient(pages, default='{"products": []}')

    previous_by_url = {
        product_url: {
            "description": "Cached Li-Ning description.",
            "gender": "men",
            "sku": "ARBW017-17V",
            "specs": {"Công nghệ": "BOOM"},
            "features": [],
            "images": [],
            "sizes": [],
            "inStock": True,
            "originalPriceVnd": None,
            "detailFetchedAt": now_iso(),
        }
    }

    items = lining_gear.scrape(client, previous_by_url)

    item = next(i for i in items if i.productUrl == product_url)
    assert item.description == "Cached Li-Ning description."
    assert item.sku == "ARBW017-17V"
