"""Runner-gear scraper: Li-Ning Vietnam's Haravan storefront.

https://lining.com.vn/collections/giay-chay-bo-2 (+ giay-chay-bo-nam-2,
giay-chay-bo-nu-2, running-series-2026)

Same platform family as `scrapers/salomon_gear.py`: `robots.txt` states
"we use Haravan as our ecommerce platform" (same note Salomon's reseller
storefront carries) and the storefront exposes the same Shopify-compatible
public `/collections/<handle>/products.json` endpoint, parsed directly - no
HTML parser or JS execution needed. Confirmed live on 2026-11-12 (see
docs_research/GEAR_SOURCES_RESEARCH.md §1 "Li-Ning Vietnam"): real brand
(`vendor: "Li-Ning"`), real VN storefront, VND pricing.

`robots.txt` only disallows `/admin`, `/cart(s)`, `/orders`, `/checkout(s)`,
`/account`, `/collections/*+*` (and its percent-encoded forms), `/blogs/*+*`,
`/search`, `/discount/*`, `/apple-app-site-association` - none of which this
touches.

Each colorway is its own separate product on this storefront (confirmed:
every inspected SKU's "Màu sắc" (color) option had exactly one value, same
shape as Salomon) - so `variants` is intentionally left empty here rather
than fabricated.

Only the running-*shoe* collections had real products on this storefront as
of 2026-11-12 - the dedicated running apparel/accessories collections that
exist on the site (`quan-chay-bo`, `phu-kien-chay-bo`, `chay-bo-nam`,
`chay-bo-nu`, `running-series`, ...) all returned zero products when
checked live. Rather than ship an empty/fabricated apparel or accessories
category for this source, this scraper only covers `shoes` for now; see the
research doc for the full list of collections checked and their counts.

**2026-11-12 detail enrichment**: same platform family as Salomon, so this
reuses `scrapers.gear_base.parse_shopify_product_detail` against
`/products/<handle>.json` (confirmed live to return the identical shape:
`body_html` bullet-list specs, `options`/`variants` with per-size
`available`, `tags` with an explicit `GT_Nam`/`GT_Nữ` gender marker - a
cleaner signal than Salomon's own table, confirmed on two real products).
"""
from __future__ import annotations

from scrapers.base import PoliteClient, now_iso
from scrapers.gear_base import (
    GearItem,
    enrich_with_detail,
    make_gear_id,
    parse_shopify_product_detail,
    resolve_listing_gender,
)

SOURCE_NAME = "lining"
BASE_URL = "https://lining.com.vn"
BRAND = "Li-Ning"

# Collection handle -> category. Confirmed real, non-empty collections on
# this storefront via its own sitemap_collections_1.xml
# (docs_research/GEAR_SOURCES_RESEARCH.md §1). All four are men's/women's/
# general running-shoe collections with overlapping products - scrape()
# dedupes by product handle, same as salomon_gear.py's seen_handles.
COLLECTIONS: list[tuple[str, str]] = [
    ("giay-chay-bo-2", "shoes"),
    ("giay-chay-bo-nam-2", "shoes"),
    ("giay-chay-bo-nu-2", "shoes"),
    ("running-series-2026", "shoes"),
]

# Collections whose handle itself is an explicit gender signal ("giày chạy
# bộ nam"/"giày chạy bộ nữ" - confirmed real, non-empty collections, see
# module docstring). `giay-chay-bo-2`/`running-series-2026` are the general
# listings and carry no gender signal of their own. A product seen under
# both the men's and women's handle resolves to "unisex"
# (gear_base.resolve_listing_gender) rather than picking one arbitrarily.
GENDER_BY_HANDLE: dict[str, str] = {
    "giay-chay-bo-nam-2": "men",
    "giay-chay-bo-nu-2": "women",
}

PRODUCTS_PER_PAGE = 250


def scrape(
    client: PoliteClient, previous_by_url: dict[str, dict] | None = None
) -> list[GearItem]:
    items: list[GearItem] = []
    item_handles: list[str] = []
    seen_handles: set[str] = set()
    genders_by_handle: dict[str, set[str]] = {}

    for handle, category in COLLECTIONS:
        gender_tag = GENDER_BY_HANDLE.get(handle)
        for product in _fetch_collection_products(client, handle):
            product_handle = product["handle"]
            if gender_tag:
                genders_by_handle.setdefault(product_handle, set()).add(gender_tag)
            if product_handle in seen_handles:
                continue  # same product listed in more than one collection
            item = _parse_product(product, category)
            if item is not None:
                items.append(item)
                item_handles.append(product_handle)
                seen_handles.add(product_handle)

    for index, product_handle in enumerate(item_handles):
        resolved = resolve_listing_gender(genders_by_handle.get(product_handle))
        if resolved:
            items[index] = items[index].model_copy(update={"gender": resolved})

    return enrich_with_detail(client, items, previous_by_url, _fetch_detail, SOURCE_NAME)


def _fetch_detail(client: PoliteClient, item: GearItem) -> dict | None:
    """Fetch `item.productUrl`'s own `.json` detail endpoint and parse it
    with the shared Shopify/Haravan detail parser (same platform as
    Salomon - see module docstring).
    """
    resp = client.get(f"{item.productUrl}.json")
    data = resp.json()
    product = data.get("product")
    if not product:
        return None
    return parse_shopify_product_detail(product)


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

    return GearItem(
        id=make_gear_id(SOURCE_NAME, handle),
        name=title,
        brand=BRAND,
        category=category,
        sourceName=SOURCE_NAME,
        priceVnd=price_vnd,
        description=None,  # filled by detail enrichment - see module
        # docstring's "2026-11-12 detail enrichment"; never the old
        # "<Brand> <product_type>." placeholder.
        imageUrl=image_url,
        productUrl=product_url,
        variants=[],
        crawledAt=now_iso(),
    )


def _parse_price(raw: object) -> int | None:
    """Like Salomon's, this storefront's `products.json` prices VND as a
    decimal string - VND has no sub-unit, so this just rounds to an int.
    """
    if raw is None:
        return None
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return None
