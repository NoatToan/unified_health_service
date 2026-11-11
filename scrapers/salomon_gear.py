"""Runner-gear scraper: Salomon Vietnam's Shopify storefront.

https://vn.salomon.com/collections/road-running-1 (+ trail-running, ao-quan, phu-kien)

Uses Shopify's standard public `/collections/<handle>/products.json` endpoint
rather than HTML-scraping the collection page - confirmed live on
2026-11-11 (see docs_research/GEAR_SOURCES_RESEARCH.md §1/§3) to return
structured `title`/`handle`/`product_type`/`images`/`variants` data directly,
which is more robust than guessing this storefront's CSS classes and doesn't
need any HTML parser for this source.

Each colorway on this storefront is its own separate product (confirmed: the
`Color` option on every inspected SKU had exactly one value, and no
sibling-color links were found on the product page) - so `variants` is
intentionally left empty here rather than fabricated. If a future product on
this storefront does expose more than one `Color` option value, this scraper
still only reads the single product it was given, so it would only ever
report that product's own listed colors, never invent one.

`robots.txt` allows all of `/collections/*/products.json` (only disallows
`/admin`, `/cart(s)`, `/orders`, `/checkout(s)`, `/account`, `/search`,
`/discount/*`, and literal `+`/`%2B` in `/collections/*`/`/blogs/*` - none of
which this touches).
"""
from __future__ import annotations

from scrapers.base import PoliteClient, now_iso
from scrapers.gear_base import GearItem, make_gear_id

SOURCE_NAME = "salomon"
BASE_URL = "https://vn.salomon.com"
BRAND = "Salomon"

# Collection handle -> our category. Confirmed real collections for this
# storefront via its own sitemap (docs_research/GEAR_SOURCES_RESEARCH.md §1).
# `ao-quan` ("shirts and shorts") and `phu-kien` ("accessories") are the
# broadest apparel/accessories collections found in the time budget this
# round had - narrower ones (ao-the-thao-nam, balo, binh-nuoc, ...) exist and
# could be added later for finer per-item category precision.
COLLECTIONS: list[tuple[str, str]] = [
    ("road-running-1", "shoes"),
    ("trail-running", "shoes"),
    ("ao-quan", "apparel"),
    ("phu-kien", "accessories"),
]

PRODUCTS_PER_PAGE = 50


def scrape(client: PoliteClient) -> list[GearItem]:
    items: list[GearItem] = []
    seen_handles: set[str] = set()
    for handle, category in COLLECTIONS:
        for product in _fetch_collection_products(client, handle):
            if product["handle"] in seen_handles:
                continue  # same product listed in more than one collection
            item = _parse_product(product, category)
            if item is not None:
                items.append(item)
                seen_handles.add(product["handle"])
    return items


def _fetch_collection_products(client: PoliteClient, handle: str) -> list[dict]:
    url = f"{BASE_URL}/collections/{handle}/products.json?limit={PRODUCTS_PER_PAGE}"
    resp = client.get(url)
    data = resp.json()
    return data.get("products", [])


def _parse_product(product: dict, category: str) -> GearItem | None:
    title = (product.get("title") or "").strip()
    handle = (product.get("handle") or "").strip()
    if not title or not handle:
        return None

    product_url = f"{BASE_URL}/products/{handle}"

    image_url = None
    images = product.get("images") or []
    if images:
        image_url = images[0].get("src")

    variants = product.get("variants") or []
    price_vnd = _parse_price(variants[0].get("price")) if variants else None

    product_type = (product.get("product_type") or "").strip()
    description = f"{BRAND} {product_type}." if product_type else None

    return GearItem(
        id=make_gear_id(SOURCE_NAME, handle),
        name=title,
        brand=BRAND,
        category=category,
        sourceName=SOURCE_NAME,
        priceVnd=price_vnd,
        description=description,
        imageUrl=image_url,
        productUrl=product_url,
        variants=[],
        crawledAt=now_iso(),
    )


def _parse_price(raw: object) -> int | None:
    """Shopify's products.json prices VND as a decimal string, e.g.
    "2400000.00" - VND has no sub-unit, so this just rounds to an int.
    """
    if raw is None:
        return None
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return None
