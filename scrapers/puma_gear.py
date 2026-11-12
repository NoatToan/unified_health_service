"""Runner-gear scraper: PUMA Vietnam's storefront.

https://vn.puma.com/vn/en/sports/running/running-shoes (+ running-apparel, running-accessories)

This storefront is a Salesforce Commerce Cloud PWA Kit app (React, server-
rendered for first load) rather than a classic SFCC template - its listing
pages don't have simple, stable CSS class names the way the rest of this
repo's scrapers rely on. Confirmed live on 2026-11-11 (see
docs_research/GEAR_SOURCES_RESEARCH.md §1/§3/§6): every listing page embeds a
single `<script id="mobify-data" type="application/json">` tag containing
the page's full server-fetched state, including a `/product-search` React
Query cache entry with structured hits - `productName`, `price`, canonical
URL, and (crucially) `c_colorSwatches`: a per-product array of every
available color, each with its own human-readable name ("Zen Blue", "Puma
Black", ...), swatch/product image, and group id. This is parsed directly
(no CSS-selector guessing, no JS execution) instead of the HTML markup.

Each product can appear as more than one `hit` in the same search response
(one per color, e.g. "Everyday Running Baseball Cap" id 026998 appeared as
both `026998_05` and `026998_06`) but every one of those hits already carries
the *same* full `c_colorSwatches` list for that product - so this scraper
only needs to process the first hit seen per base product id and build
`variants` straight from its `c_colorSwatches`, rather than grouping rows
itself.

Re-checked live on 2026-11-12 (docs_research/GEAR_SOURCES_RESEARCH.md §1,
"Puma re-check"), two fixes from the original v1 shape:

1. The old `shoes` listing (`/sports/running`, the vertical's generic landing
   page) actually mixes all three divisions - a live check found apparel
   items ("VELOCITY Running Tee Men") in its hits alongside shoes, which
   would have mis-tagged them as `category="shoes"`. Switched to the
   dedicated `/sports/running/running-shoes` page instead, confirmed (via
   its own query's `refine: cgid=sports/running/running-shoes`) to return
   only footwear.
2. Every listing paginates (`?page=N`, 1-indexed, `offset=(page-1)*limit`,
   confirmed live) and the old scraper only ever fetched page 1 - missing
   most of the catalog (confirmed totals: 311 shoes / 120 apparel / 21
   accessories at `limit=16` per page, i.e. up to ~30 pages total across all
   three listings). `scrape()` now follows `total`/`limit` from each page's
   own response until the listing is exhausted, capped by
   `scrapers.base.MAX_PAGES_PER_SOURCE` across the whole call (politeness -
   same constant the races pipeline already uses for `irace.py`).

**2026-11-12 detail enrichment**: each item's own PDP (same URL as its
`productUrl`, e.g. `.../pd/everyday-running-waist-bag/092404.html?color=05`)
embeds the exact same `mobify-data` shape as a listing page, just with a
`/products/092404_05` React Query cache entry instead of `/product-search`.
That entry is far richer than a listing hit: `longDescription` (real HTML
with "PRODUCT STORY"/"FEATURES & BENEFITS"/"DETAILS" sections - the first is
used as `description`, the bullet lists become `specs`/`features`),
`c_gender` ("Unisex"/"Men's"/"Women's"), `inventory.orderable` (`inStock`),
`variationAttributes` (the `size` entry's values, each with its own
`orderable` flag -> `sizes`), `c_listPrice`/`c_salePrice` (`originalPriceVnd`
when they differ), the full `imageGroups` gallery (`images`), and
`master.masterId`/`c_styleNumber` (`sku`). One extra request per item -
`scrapers.gear_base.enrich_with_detail` caps it at `MAX_DETAIL_FETCHES_PER_SOURCE`
and reuses a previous run's detail (`detailFetchedAt` < 7 days old) for
everything else, so a cold run enriches a bounded slice and later runs fill
in the rest cheaply.
"""
from __future__ import annotations

import json
import re

from scrapers.base import MAX_PAGES_PER_SOURCE, PoliteClient, now_iso
from scrapers.gear_base import (
    GearItem,
    GearSize,
    GearVariant,
    clean_description,
    enrich_with_detail,
    extract_bullet_facts,
    extract_description_candidate,
    make_gear_id,
    normalize_gender,
)

SOURCE_NAME = "puma"
SITE_ROOT = "https://vn.puma.com/vn/en"
BRAND = "Puma"

LISTINGS: list[tuple[str, str]] = [
    ("https://vn.puma.com/vn/en/sports/running/running-shoes", "shoes"),
    ("https://vn.puma.com/vn/en/sports/running/running-apparel", "apparel"),
    ("https://vn.puma.com/vn/en/sports/running/running-accessories", "accessories"),
]

_MOBIFY_DATA_RE = re.compile(
    r'<script id="mobify-data" type="application/json">(.*?)</script>', re.DOTALL
)


def scrape(
    client: PoliteClient, previous_by_url: dict[str, dict] | None = None
) -> list[GearItem]:
    items: list[GearItem] = []
    seen_base_ids: set[str] = set()
    pages_fetched = 0

    for listing_url, category in LISTINGS:
        # `total`/`limit` are fixed from this listing's *first* page and
        # reused for every later page's stopping check - a live catalog's
        # last page was observed to sometimes report a smaller `limit`
        # (matching just its own remaining hit count) or a trailing
        # all-empty page, which would otherwise throw off the
        # `page_num * limit >= total` math and waste budget re-deriving it
        # from an already-exhausted page.
        total: int | None = None
        limit: int | None = None
        page_num = 1
        while pages_fetched < MAX_PAGES_PER_SOURCE:
            url = listing_url if page_num == 1 else f"{listing_url}?page={page_num}"
            resp = client.get(url)
            pages_fetched += 1

            hits, page_total, page_limit = _product_search_page(resp.text)
            if total is None:
                total, limit = page_total, page_limit

            for hit in hits:
                base_id = str(hit.get("productId", "")).split("_", 1)[0]
                if not base_id or base_id in seen_base_ids:
                    continue
                item = _parse_hit(hit, category)
                if item is None:
                    continue
                seen_base_ids.add(base_id)
                items.append(item)

            if not total or not limit:
                break  # no pagination info (e.g. a fixture with no real
                       # `total`/`limit`) - one page is all we can get.
            if page_num * limit >= total:
                break  # reached the end of this listing's real catalog.
            page_num += 1

    return enrich_with_detail(client, items, previous_by_url, _fetch_detail, SOURCE_NAME)


def _product_search_page(html: str) -> tuple[list[dict], int | None, int | None]:
    """Returns `(hits, total, limit)` for one listing page's `/product-search`
    React Query cache entry - `total`/`limit` drive `scrape()`'s pagination.
    """
    match = _MOBIFY_DATA_RE.search(html)
    if match is None:
        return [], None, None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return [], None, None

    pre_state = data.get("__PRELOADED_STATE__") or {}
    queries = (pre_state.get("__reactQuery") or {}).get("queries") or []

    hits: list[dict] = []
    seen_base_ids: set[str] = set()
    total: int | None = None
    limit: int | None = None
    for query in queries:
        key = query.get("queryKey")
        if not isinstance(key, list) or "/product-search" not in key:
            continue
        pages = ((query.get("state") or {}).get("data") or {}).get("pages") or []
        for page in pages:
            if total is None:
                total = page.get("total")
            if limit is None:
                limit = page.get("limit")
            for hit in page.get("hits") or []:
                base_id = str(hit.get("productId", "")).split("_", 1)[0]
                if not base_id or base_id in seen_base_ids:
                    continue
                seen_base_ids.add(base_id)
                hits.append(hit)
    return hits, total, limit


def _parse_hit(hit: dict, category: str) -> GearItem | None:
    product_id = str(hit.get("productId", ""))
    base_id = product_id.split("_", 1)[0]
    name = (hit.get("productName") or "").strip()
    canonical_url = hit.get("c_canonicalUrl") or ""
    if not base_id or not name or not canonical_url:
        return None

    path = canonical_url.split("?", 1)[0]
    default_url = SITE_ROOT + canonical_url

    price_vnd = hit.get("c_salePrice") or hit.get("price") or hit.get("c_listPrice")
    price_vnd = int(price_vnd) if isinstance(price_vnd, (int, float)) else None

    default_image = None
    image_groups = hit.get("imageGroups") or []
    if image_groups:
        images = image_groups[0].get("images") or []
        if images:
            default_image = images[0].get("link")

    swatches = hit.get("c_colorSwatches") or []
    variants: list[GearVariant] = []
    for swatch in swatches:
        color = (swatch.get("name") or "").strip()
        value = swatch.get("value")
        if not color or not value:
            continue
        image_url = (swatch.get("productImage") or {}).get("disBaseLink")
        variants.append(
            GearVariant(
                color=color,
                imageUrl=image_url,
                productUrl=f"{SITE_ROOT}{path}?color={value}",
            )
        )

    return GearItem(
        id=make_gear_id(SOURCE_NAME, base_id),
        name=name,
        brand=BRAND,
        category=category,
        sourceName=SOURCE_NAME,
        priceVnd=price_vnd,
        description=None,  # filled by detail enrichment when a PDP fetch
        # succeeds (see module docstring's "2026-11-12 detail enrichment");
        # never the old "<Brand> running <category>." placeholder.
        imageUrl=default_image,
        productUrl=default_url,
        variants=variants if len(variants) > 1 else [],
        crawledAt=now_iso(),
    )


# --------------------------------------------------------------------------- #
# Detail (PDP) enrichment
# --------------------------------------------------------------------------- #

_FAVOR_VIEW_TYPE = "large-VNM"


def _fetch_detail(client: PoliteClient, item: GearItem) -> dict | None:
    """Fetch `item.productUrl` (its own PDP) and parse the `/products/<id>`
    React Query cache entry the page embeds - same `mobify-data` shape as a
    listing page, just a richer query. Returns a dict of GearItem fields to
    merge in, or None if the page didn't embed a usable product entry.
    """
    resp = client.get(item.productUrl)
    match = _MOBIFY_DATA_RE.search(resp.text)
    if match is None:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    pre_state = data.get("__PRELOADED_STATE__") or {}
    queries = (pre_state.get("__reactQuery") or {}).get("queries") or []
    for query in queries:
        key = query.get("queryKey")
        if not isinstance(key, list) or "/products/" not in key:
            continue
        prod = ((query.get("state") or {}).get("data")) or {}
        if prod:
            return _parse_pdp_detail(prod)
    return None


# c_* fields that are short factual labels (not already covered by
# description/features/sizes/gender/stock) worth keeping as `specs` -
# mapped to a plain-English key since c_* names aren't meant for display.
_SPEC_FIELD_MAP: list[tuple[str, str]] = [
    ("c_mainMaterial", "material"),
    ("c_fabricsType", "fabricType"),
    ("c_SportType", "sportType"),
    ("c_ageGroup", "ageGroup"),
    ("c_articleType", "articleType"),
]


def _parse_pdp_detail(prod: dict) -> dict:
    """Pure parse of one `/products/<id>` React Query cache entry (a PDP's
    full product JSON) into the subset of GearItem fields a detail fetch
    can fill. See the module docstring's "2026-11-12 detail enrichment" for
    where each field comes from.
    """
    name = (prod.get("name") or "").strip()
    long_description_html = prod.get("longDescription") or ""

    specs, features = extract_bullet_facts(long_description_html)
    for field, label in _SPEC_FIELD_MAP:
        value = prod.get(field)
        if isinstance(value, str) and value.strip():
            specs.setdefault(label, value.strip())

    description = None
    if long_description_html:
        description = clean_description(
            extract_description_candidate(long_description_html), name
        )

    images: list[str] = []
    seen_images: set[str] = set()
    groups = prod.get("imageGroups") or []
    preferred = [g for g in groups if g.get("viewType") == _FAVOR_VIEW_TYPE] or groups
    for group in preferred:
        for image in group.get("images") or []:
            link = image.get("link")
            if link and link not in seen_images:
                seen_images.add(link)
                images.append(link)

    list_price = prod.get("c_listPrice")
    sale_price = prod.get("c_salePrice")
    if not isinstance(sale_price, (int, float)):
        sale_price = prod.get("price")
    original_price_vnd = None
    if (
        isinstance(list_price, (int, float))
        and isinstance(sale_price, (int, float))
        and list_price > sale_price
    ):
        original_price_vnd = int(list_price)

    sizes: list[GearSize] = []
    for attr in prod.get("variationAttributes") or []:
        if attr.get("id") != "size":
            continue
        for value in attr.get("values") or []:
            label = (value.get("name") or "").strip()
            if not label:
                continue
            sizes.append(GearSize(label=label, available=value.get("orderable")))

    in_stock = None
    inventory = prod.get("inventory") or {}
    if isinstance(inventory.get("orderable"), bool):
        in_stock = inventory["orderable"]

    gender = normalize_gender(prod.get("c_gender"))

    sku = None
    master = prod.get("master") or {}
    if isinstance(master.get("masterId"), str) and master["masterId"]:
        sku = master["masterId"]
    elif isinstance(prod.get("c_styleNumber"), str) and prod["c_styleNumber"]:
        sku = prod["c_styleNumber"]

    return {
        "description": description,
        "images": images,
        "originalPriceVnd": original_price_vnd,
        "sizes": sizes,
        "inStock": in_stock,
        "gender": gender,
        "sku": sku,
        "specs": specs,
        "features": features,
        "detailFetchedAt": now_iso(),
    }
