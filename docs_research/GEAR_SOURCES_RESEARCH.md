# unified_health_service: runner gear recommendations crawler — research spec

Research output from a Claude agent, 2026-11-11. **Methodology note**: this session's shell access was
intermittently sandboxed to an unrelated Android repo's git worktree for stretches of this task (an
infra condition outside this agent's control, tied to a concurrent session's own worktree use on the
same machine — see the handoff report). Initial source discovery (§1, robots.txt, sitemaps, platform
identification) was done with the `WebFetch`/`WebSearch` tools during a blocked stretch - real findings,
gathered from the live sites, but that fetch tool summarizes pages rather than returning raw HTML, so it
could not confirm exact markup. Once shell access came back, every finding was re-verified directly
(`httpx` fetches, `pytest`, live HTTP spot-checks) and the implementation below reflects what was
actually confirmed against raw responses, not a guess - see §6 for the one rough edge that's left.

**2026-11-12 update**: re-checked every held-back v1 candidate (Decathlon, Nike, Adidas, Asics) plus
three new candidates the brief asked for (Coolmate, Li-Ning, and a re-check of Puma's own coverage),
this time entirely with real `curl`/`httpx` against raw responses from the start - no summarizing fetch
tool in the loop at any point this round. Shipped: **Li-Ning Vietnam** and **Coolmate** (both genuinely
scrapable, see §1). Also fixed two real bugs found in the already-shipped Puma scraper (category
mis-tagging + missing pagination - see "Puma re-check" below) and definitively confirmed Decathlon/
Nike/Adidas/Asics stay held back, now with raw-HTML evidence instead of the previous round's "needs a
direct check" open questions. See §7 for this round's live verification numbers.

## 1. Sources

### Ship in v1

| # | Source | Platform | What it shows | Scrapability (checked) |
|---|---|---|---|---|
| 1 | **PUMA Vietnam**, `https://vn.puma.com/vn/en/sports/running/running-shoes` (+ `running-apparel`, `running-accessories`) | Salesforce Commerce Cloud **PWA Kit** (React app, server-rendered for first load - not the classic SFCC template family the initial pass assumed) | Running shoes, apparel (shorts, tees, tights) and accessories (waist bags, caps) under one `/sports/running` vertical with dedicated per-division sub-category pages. Real brand, real VN storefront, VND pricing, free-shipping threshold in VND — genuinely sells to Vietnam. | Confirmed server-rendered: every listing page embeds one `<script id="mobify-data" type="application/json">` tag holding the page's full server-fetched React Query cache, including a `/product-search` entry with structured `hits` (`productName`, `price`/`c_salePrice`, `c_canonicalUrl`, `imageGroups`, and `c_colorSwatches` - a per-product array of every color with its real name, e.g. "Zen Blue", "Puma Black", each with its own image and product id). `scrapers/puma_gear.py` parses this JSON directly - no CSS-selector guessing, no JS execution. `robots.txt`: `Allow` by default, only disallows `*account*`, `*checkout*`, `*cart*`, `*wishlist*`, `*login*`, `*registration*`, `*reset-password*`, `*callback*` — none of which this pipeline touches. Sitemap index at `sitemap_index.xml`. **Re-checked 2026-11-12** (see "Puma re-check" below) - two real bugs found and fixed: the old `shoes` listing was the generic `/sports/running` landing page, which turned out to mix in apparel hits too; and every listing paginates but the scraper only ever fetched page 1. Verified end-to-end post-fix: `python -m pipeline.gear_main` run live on 2026-11-12 returned 204 Puma items (117 shoes / 76 apparel / 11 accessories), 104 with real multi-color `variants`; a sample of product/image URLs spot-checked HTTP 200 (§7). |
| 2 | **Salomon Vietnam**, `https://vn.salomon.com/collections/road-running-1` (+ `trail-running`, `ao-quan`, `phu-kien`) | Shopify (Vietnamese reseller storefront, platform note in its own `robots.txt`: "we use Haravan as our ecommerce platform" — actually Shopify theme markup on inspection, Haravan is the checkout/ops backend) | Trail and road running shoes, running apparel, and accessories (backpacks, caps, hydration vests, water bottles) across four confirmed real collections pulled from this storefront's own sitemap. Real brand, dedicated VN storefront, VND pricing. | `scrapers/salomon_gear.py` uses Shopify's standard public `/collections/<handle>/products.json` endpoint directly (confirmed live, returns structured `title`/`handle`/`product_type`/`images`/`variants`) rather than HTML-scraping the collection page - no HTML parser needed for this source at all. `robots.txt`: only disallows `/admin`, `/cart(s)`, `/orders`, `/checkout(s)`, `/account`, `/search`, `/discount/*`, URL-encoded `+` in `/collections/*`/`/blogs/*` — none of which this pipeline touches. Unchanged this round; still 111 items on the 2026-11-12 live run (§7). |
| 3 | **Li-Ning Vietnam**, `https://lining.com.vn/collections/giay-chay-bo-2` (+ `giay-chay-bo-nam-2`, `giay-chay-bo-nu-2`, `running-series-2026`) | Haravan (same platform family as Salomon's reseller storefront) - its own `robots.txt` states "we use Haravan as our ecommerce platform", and the storefront exposes the same Shopify-compatible public `products.json` endpoint. | Running shoes under `vendor: "Li-Ning"`, VND pricing, real VN storefront (title: "Li-Ning Sport Vietnam - Cửa hàng trực tuyến chính thức"). Confirmed real running-specific collections via this storefront's own `sitemap_collections_1.xml` (`giay-chay-bo-*`, `chay-bo-*`, `running-series*`, `quan-chay-bo`, `phu-kien-chay-bo`, ...). | `scrapers/lining_gear.py` reuses Salomon's exact `/collections/<handle>/products.json` approach - confirmed live to return the same structured Shopify-shape JSON (`title`/`handle`/`vendor`/`product_type`/`images`/`variants`), `vendor` always `"Li-Ning"`. `robots.txt`: only disallows `/admin`, `/cart(s)`, `/orders`, `/checkout(s)`, `/account`, `/collections/*+*` (+ percent-encoded), `/blogs/*+*`, `/search`, `/discount/*` — none of which this pipeline touches. **Only shoes shipped**: every running-specific apparel/accessories collection on this storefront (`quan-chay-bo`, `phu-kien-chay-bo`, `phu-kien-chay-bo-1`, `chay-bo-nam`, `chay-bo-nu`, `running-series`, several `giay-chay-bo-*-1` handles) returned `{"products": []}` live on 2026-11-12 - rather than ship an empty or fabricated apparel/accessories category, this source is shoes-only until the storefront actually stocks something there. Each colorway is its own separate product here too (every inspected SKU's "Màu sắc" option had exactly one value) - `variants` correctly empty, same as Salomon. Verified end-to-end: live run on 2026-11-12 returned 112 Li-Ning items, all `category: "shoes"`; sample product/image URLs spot-checked HTTP 200 (§7). |
| 4 | **Coolmate**, `https://www.coolmate.me/collection/quan-ao-chay-bo` (+ `quan-ao-chay-bo-nu`, `phu-kien-chay-bo`) | Custom Next.js **App Router** storefront (own house brand, Vietnamese D2C menswear/activewear) - not Shopify/Haravan/SFCC like every other source here. | A real dedicated "chạy bộ" (running) line: apparel (tees, shorts, tights, jackets) and accessories (socks, masks, bags) in VND. Confirmed **no running shoes** anywhere on this storefront (checked its own `sitemap/collection0.xml` for any shoe-type running collection - none exists), so this source never emits a `shoes` item. | `robots.txt` (`User-agent: *`) is permissive - only disallows `/account`, `/cart`, `/profile`, `/blog/wp-admin/`, `/spotlight` (a separate `meta-webindexer` UA group disallows a few filter query params that don't apply to this bot and that this scraper never requests anyway). The collection page's product grid isn't in a simple embedded-JSON tag like Puma's - it's streamed as React Server Component ("RSC") payload chunks (`self.__next_f.push([1,"<escaped JSON>"])`), confirmed live to be genuinely server-rendered (present in the plain HTTP response, no JS execution needed): decoding and concatenating every chunk's JSON-string-literal content and locating the real (non-empty) `"products":[...]` array inside it recovers the full structured product data (`title`/`href`/`id`/`regular_price`/`compare_price`/`mapped_variants`) directly. `scrapers/coolmate_gear.py` implements this text-only parse. Colors on one product (`mapped_variants`, keyed by accented Vietnamese color names) share one product URL - no distinct per-color URL/query param exists on the real PDP (checked live: the PDP only exposes short, non-matching `?color=den/xam/xanh`-style family slugs), so `GearVariant.productUrl` correctly points at the same base product for every color rather than guessing one - only `imageUrl` differs per color (real per-color data). Verified end-to-end: live run on 2026-11-12 returned 59 Coolmate items (39 apparel / 20 accessories); sample product/image URLs spot-checked HTTP 200 (§7). |

#### Puma re-check (2026-11-12)

Re-verified Puma's own coverage per the brief's explicit ask ("check whether more running categories
should be covered, e.g. if only some listings are crawled") by live-checking raw HTTP responses (no
fetch-tool summarization this round):

- **Category mis-tagging bug, now fixed**: the v1 scraper's `shoes` listing was
  `/vn/en/sports/running` - the vertical's generic landing page. A live check of its raw hits found
  apparel items in the results too (e.g. "VELOCITY Running Tee Men", "VELOCITY 5-inch Running Shorts
  Men", "RUN CLOUDSPUN Tee Women") - confirmed by the page's own `c_productDivision` facet breaking its
  `total: 451` hits into `Footwear: 311 / Apparel: 120 / Accessories: 20` (311+120+20=451, i.e. this one
  URL's result set genuinely spans all three divisions). Every one of those apparel hits was being
  mis-tagged `category: "shoes"`. Switched to the dedicated `/sports/running/running-shoes` page
  instead - confirmed (via its own query's `refine: cgid=sports/running/running-shoes`, `total: 311`)
  to return only footwear.
- **Missing pagination, now fixed**: every listing paginates (`?page=N`, 1-indexed,
  `offset=(page-1)*limit`, confirmed live - `?page=2` returns `offset:16` with different products than
  page 1) and the v1 scraper only ever fetched page 1. `scrapers/puma_gear.py`'s `scrape()` now follows
  each listing's own `total`/`limit` (captured from that listing's first page and reused for the
  stopping check, since a live catalog's tail page was observed to report a smaller or all-empty
  `limit` that would otherwise throw off the math) until the real catalog is exhausted, capped at
  `scrapers.base.MAX_PAGES_PER_SOURCE` (30) total page-fetches for the whole `scrape()` call - the same
  politeness constant `scrapers/irace.py` already uses for the races pipeline. At the totals seen live
  on 2026-11-12 (shoes 311 / apparel 120 / accessories 21, `limit=16`), that's 20 + 8 + 2 = 30 page
  fetches - exactly the budget, with nothing wasted on a pointless trailing page.
- Base-product dedup (`seen_base_ids`) is now scoped to the whole `scrape()` call rather than
  per-listing-page, needed for pagination correctness (so the same product's later color-hit rows
  across pages don't produce duplicate `GearItem`s) and harmless for category correctness too, since
  shoes/apparel/accessories are genuinely disjoint divisions once each listing is scoped correctly.

### Checked and held back for v2

| # | Source | Why held back |
|---|---|---|
| 5 | **Hoka Vietnam**, `vn.hoka.com` | Real official store (opened its first physical VN store at Saigon Centre, HCMC, April 2025 — distributed by Central Brand & Specialty Group), also a Shopify storefront, `robots.txt` is permissive (`Allow: /`, standard Shopify disallow list for cart/checkout/admin, sitemap at `/sitemap.xml`). **Held back purely on observed behavior, not policy**: two polite, several-seconds-apart `WebFetch` requests during this research session both got `HTTP 429 Too Many Requests` with a `Retry-After: 60` header. That's a real signal this storefront rate-limits more aggressively than Puma/Salomon did under the same light request pattern — worth a v2 pass with the project's actual `PoliteClient` (which already waits `REQUEST_DELAY_SECONDS` between requests and retries once on 429) rather than assuming it'll misbehave, but not confirmed safe today, so not shipped in v1. Not re-checked this round (not in the 2026-11-12 brief's source list). |
| 6 | **Decathlon Vietnam**, `decathlon.vn` | `robots.txt` is permissive for category/product paths and it genuinely sells running shoes/apparel/accessories under real (if house) running brands — **Kiprun** and **Kalenji** — with Vietnam availability and VND pricing confirmed from the product sitemap. **Re-checked 2026-11-12 with real `curl`/raw HTML (both open questions from the previous round now definitively settled, not just "maybe")**: (a) `robots.txt` confirmed to have a literal, blanket `Disallow: *?*` line (distinct from the several specific-param `Disallow` rules above it) — **every URL with a query string is off-limits**, full stop; (b) fetched a real men's-running-shoes category page directly and inspected its `__NEXT_DATA__` payload: `pageProps.seoProducts` is a tiny 3-item SEO sample (of a `seoProductCount: 49` category) with Algolia-shaped fields (`objectID`, `_snippetResult`) and `pageProps.dehydratedState.queries` holds only navigation/locale queries — **no product-search query is embedded for SSR**, meaning the real product grid (all 49+ items, color/size switching) is fetched client-side via JS calling Algolia's search API after hydration. This is the same "needs JS" situation the project's hard rule holds back for, now confirmed directly rather than inferred — calling Algolia's endpoint ourselves with its page-exposed public search key would be exactly the workaround-via-a-different-host the hard rule prohibits, so that route wasn't pursued either. Not shipped. |
| 7 | **Nike Vietnam**, `nike.com/vn` | Has a real `/vn/` storefront with running shoes in VND. **Re-checked 2026-11-12 with real `curl`/raw HTML** (settles the previous round's open question): fetched `https://www.nike.com/vn/w/mens-running-shoes-37v7jznik1zy7ok` directly and parsed its `__NEXT_DATA__` - `props.pageProps` only has `cloudUrlFragment`/`initialState.global.metaTags`/`initialState.localization` (page title, meta tags, locale/currency config); there is no product/grid data anywhere in the pre-hydration payload (`__N_SSP: true` confirms this page uses `getServerSideProps`, but the actual product list is evidently fetched by the client after hydration, not embedded). Confirmed "needs JS" - held back per the project's hard rule, not worked around. `robots.txt` itself is permissive (`Disallow: */p/`, `*/checkout/*`, a few locale redirects — none block the `/vn/w/...` listing path), so this is purely the "no JS execution" rule, not a block. |
| 8 | **Adidas Vietnam**, `adidas.com.vn` | **Re-checked 2026-11-12 with real `curl`** using the project's actual `UnifiedHealthRaceBot` UA (settles the previous round's "could be a fetch-tool artifact" open question): `robots.txt` still returns `HTTP 403 Forbidden`, served by Adidas's own Akamai bot-defense page ("A security issue was automatically identified... extra security in place to prevent bots entering our site", reference-coded, `page_owner: AKAMAI`). This is a real block of this project's real UA, not a fetch-tool quirk — confirmed, not shipped, no workaround attempted per the hard "no anti-bot bypass" rule. |
| 9 | **Asics Vietnam** | **Re-checked 2026-11-12**: the official store does exist at `www.asics.com/vn` (confirmed via web search: head office in HCMC, `customers-vn@asics.com`), but every VN-locale path checked with real `curl` (`/vn/`, `/vn/en-vn/`, `/vn/vi-vn/`, `/vn/vi-vn/running/c/asx0101/`) returns `HTTP 403 Forbidden` with an Akamai "Access Denied" edge response (`errors.edgesuite.net` reference) to this project's real UA — same situation as Adidas, a real bot-defense block, not a missing storefront. Resellers found (`ash.vn`, `oss.com.vn`) are general multi-brand sneaker shops that happen to carry ASICS among other brands, not confirmed to be *the* official distributor storefront the brief's bar requires ("resellers only if clearly the official distributor storefront") — not pursued. Not shipped. |
| 10 | **Brooks Running** | Confirmed to have a Vietnam presence (Brooks Sports Vietnam LLC, a sourcing/production office in HCMC) but **no Brooks-owned retail storefront** — Brooks explicitly sells only through "authorised resellers," and this round didn't identify a specific VN reseller with a clean public catalog. Not re-checked this round (not in the 2026-11-12 brief's source list); would need a named reseller site vetted on its own merits to reconsider. |

### Do not scrape

- Anything requiring JS execution/client-side rendering to see the product grid — same "no browser"
  rule as the races and news pipelines.
- Any storefront behind login/membership-gated pricing.
- Facebook/Instagram shop pages — login-walled, unreliable, same exclusion as the other two docs.

## 2. Legality, politeness, and scope guardrails

This is **commercial product data**, a third category of content alongside the races and news
pipelines, and the most sensitive of the three — it's the one place where "republishing marketing
copy" or "implying this is a store" would be an actual problem, not just bad etiquette. The schema
(§3) is deliberately scoped as a **metadata + link-out catalog, never a store**, same spirit as the
project's "this is a crawler, not a checkout flow" rule:

- Store **name, brand, category, a factual description, price if publicly listed, image URL(s), and
  the brand's own product page URL** — the product page is always present and is the only way to
  actually buy it. Never store availability/stock *counts*, never touch a cart/checkout/payment
  endpoint, never collect user data.
- **2026-11-12 policy update**: `description` used to be deliberately reduced to a thin
  "`<Brand> <category>.`" placeholder out of caution about reproducing marketing copy. That's
  superseded now that this pipeline does real per-product detail (PDP) enrichment (§8): `description`
  is the **source's own real product description**, mechanically stripped of HTML, whitespace-
  normalized, and truncated to ~500 chars (`scrapers.gear_base.clean_description`/
  `truncate_text`) — not a hand-written paraphrase, and never fabricated. The same real-data rule
  applies to the new `specs`/`features` fields: both are only ever populated from a structured field
  or a genuine spec table/bullet list the PDP itself publishes (§8 has the exact source per field),
  never guessed or invented. `description`/`specs`/`features` are all nullable/emptyable — a source
  or item that doesn't expose something real for a field leaves it null/empty rather than a
  placeholder or a guess. `productUrl` remains the only way to actually buy the item, and nothing a
  detail fetch touches is a cart/checkout/account endpoint (see §8).
- Same `UnifiedHealthRaceBot/1.0` UA, same `PoliteClient` (robots.txt check once per host, rate limit,
  retry-once) as the other two pipelines — no parallel HTTP stack, no special-casing that skips
  politeness. `docs/bot.html` is extended in this branch to disclose the gear pipeline the same way it
  already discloses races and news. The detail-enrichment PDP fetches (§8) go through the exact same
  `PoliteClient`, so they're rate-limited and robots.txt-checked identically to every listing fetch -
  nothing about them is a parallel, less-polite path.
- Listing pages give name+price+image+URL+color-variant rows directly (confirmed above). §8 adds one
  *extra*, budgeted request per product (capped by `MAX_DETAIL_FETCHES_PER_SOURCE`, with a 7-day
  cache) to its own real PDP for the richer detail fields - never a cart/checkout/account URL, and
  never more than one extra request per product per cache-miss.
- Vietnam-market relevance is treated as a hard filter, same as the brief asked: both v1 sources are
  real brands' own `.vn`/`vn.*` storefronts selling in VND with VN shipping, not a generic global site
  with Vietnam merely able to view prices. Sources where VN availability was unclear or absent (Brooks:
  confirmed office presence but no owned storefront; Asics: no VN-specific storefront found) are held
  back or skipped rather than shipped with a guess.

## 3. Data schema

Field names mirror `docs/races/latest.json` / `docs/news/latest.json` (camelCase, `schemaVersion` /
`generatedAt` / `sources[]` wrapper, UTC `...Z` timestamps, `id`/`productUrl` naming).

### Variant/color handling (added after initial schema draft, per updated requirement)

The Android app's upcoming "wardrobe" feature needs the user to pick **which color** of a product they
own, so a product with multiple colorways needs those colors modeled, not one flat item per color.
What the two v1 sources actually expose turned out to differ, and the schema follows what's real
rather than forcing one shape:

- **PUMA Vietnam exposes real per-color swatch data**, confirmed on live pages: a category listing page
  (`/sports/running/running-accessories`) lists the *same* numeric product id twice — once per color —
  each row with its own `?color=NN` query param, its own templated CDN image
  (`.../global/<id>/<colorCode>/sv01/fnd/VNM/fmt/png`), and (on the PDP) a swatch selector exposing
  every other color code for that id (confirmed 10 swatches on one shoe). The scraper groups listing
  rows that share the same numeric product id into one `GearItem` with a `variants` array, one entry
  per distinct color row encountered.
- **Salomon Vietnam does not** — each colorway is its own separate product (own handle, own URL, own
  Shopify product id; confirmed via the `.json` endpoint, where the `Color` option on one SKU had only
  one value, and via the PDP, which showed no sibling-color links). For this source `variants` is
  correctly omitted/empty per item — there's no fabricated color data, just one color per `GearItem`,
  which is the honest shape for what this storefront exposes.
- **Li-Ning Vietnam** (added 2026-11-12) is the same shape as Salomon — one color per product, `Màu
  sắc` option always a single value, `variants` empty.
- **Coolmate** (added 2026-11-12) *does* expose real multi-color data (`mapped_variants`, keyed by
  color name) but, unlike Puma, has **no distinct URL per color** - every `GearVariant.productUrl` for
  this source points at the same base product page (still real, dereferenceable, just not
  color-specific), while `imageUrl` is real per-color data. See `scrapers/coolmate_gear.py`'s
  docstring for why a per-color URL wasn't guessed.

Real example item **with** variants (Puma "Everyday Running Baseball Cap", product id `026998` —
straight from a live `python -m pipeline.gear_main` run on 2026-11-11, not hand-constructed):

```json
{
  "id": "puma-026998",
  "name": "Everyday Running Baseball Cap",
  "brand": "Puma",
  "category": "accessories",
  "sourceName": "puma",
  "priceVnd": 650000,
  "description": "Puma running accessories.",
  "imageUrl": "https://images.puma.com/image/upload/f_auto,q_auto,w_600,b_rgb:FAFAFA/global/026998/05/fnd/VNM/fmt/png",
  "productUrl": "https://vn.puma.com/vn/en/pd/everyday-running-baseball-cap/026998.html?color=05",
  "variants": [
    { "color": "Sandstone", "imageUrl": "https://images.puma.com/image/upload/f_auto,q_auto,w_600,b_rgb:FAFAFA/global/026998/04/fnd/VNM/fmt/png", "productUrl": "https://vn.puma.com/vn/en/pd/everyday-running-baseball-cap/026998.html?color=04" },
    { "color": "PUMA Black", "imageUrl": "https://images.puma.com/image/upload/f_auto,q_auto,w_600,b_rgb:FAFAFA/global/026998/01/fnd/VNM/fmt/png", "productUrl": "https://vn.puma.com/vn/en/pd/everyday-running-baseball-cap/026998.html?color=01" },
    { "color": "Inky Depths", "imageUrl": "https://images.puma.com/image/upload/f_auto,q_auto,w_600,b_rgb:FAFAFA/global/026998/05/fnd/VNM/fmt/png", "productUrl": "https://vn.puma.com/vn/en/pd/everyday-running-baseball-cap/026998.html?color=05" },
    { "color": "Light Lavender", "imageUrl": "https://images.puma.com/image/upload/f_auto,q_auto,w_600,b_rgb:FAFAFA/global/026998/06/fnd/VNM/fmt/png", "productUrl": "https://vn.puma.com/vn/en/pd/everyday-running-baseball-cap/026998.html?color=06" },
    { "color": "PUMA White", "imageUrl": "https://images.puma.com/image/upload/f_auto,q_auto,w_600,b_rgb:FAFAFA/global/026998/02/fnd/VNM/fmt/png", "productUrl": "https://vn.puma.com/vn/en/pd/everyday-running-baseball-cap/026998.html?color=02" }
  ],
  "crawledAt": "2026-11-11T05:09:53Z"
}
```

Real example item **without** variants (Salomon — single color exposed by the source), also straight
from the same live run:

```json
{
  "id": "salomon-giay-chay-bo-nam-salomon-drx-bliss-l47200500",
  "name": "Giày Chạy Bộ Nam Salomon DRX Bliss L47200500",
  "brand": "Salomon",
  "category": "shoes",
  "sourceName": "salomon",
  "priceVnd": 2160000,
  "description": "Salomon Giày Running.",
  "imageUrl": "https://product.hstatic.net/200000931659/product/giay-chay-bo-nam-salomon-drx-bliss-l47200500__1__7e177413dedd4bb2b507eb1fea304bef.png",
  "productUrl": "https://vn.salomon.com/products/giay-chay-bo-nam-salomon-drx-bliss-l47200500",
  "variants": [],
  "crawledAt": "2026-11-11T05:09:54Z"
}
```

Field notes:

- `id`: `{sourceName}-{stable per-source key}` — for Puma, the numeric product id shared by every color
  row (`026998`); for Salomon, the Shopify product handle (already unique and stable, same spirit as
  `make_news_id`'s URL-derived slug).
- `brand`: the actual gear brand, not the storefront's own name when they differ (not a concern for v1
  — both sources are single-brand stores; this field exists so a future multi-brand source like
  Decathlon can set it per-product from the title's house-brand prefix rather than equaling
  `sourceName`).
- `category`: `shoes | apparel | accessories` — assigned from which listing URL a scraper function was
  pointed at (e.g. `scrape(client, LISTING_URL, category="accessories")`), the same "explicit source
  hint first" pattern `guess_terrain()` already uses for terrain — not a keyword guess, since both v1
  sources already segment their own catalogs into clean listing pages per category.
- `priceVnd`: nullable integer, VND, parsed the same way as the races pipeline's
  `parse_vnd_price()` (strip everything but digits). Null if a listing shows no price (rare for these
  two sources, but e.g. a sold-out/unlisted item might).
- `imageUrl` / `productUrl` at the top level: the *default* variant's image/URL (first color
  encountered for a multi-color item; the only image/URL for a single-color item) — so a consumer that
  doesn't care about color picking can just use the top-level fields.
- `variants`: array, possibly empty, never fabricated. Each entry is `{ "color": str, "imageUrl": str,
  "productUrl": str }`, plus optional per-variant `priceVnd`/`images`/`sizes` when a source genuinely
  exposes per-color detail for them (added 2026-11-12, §8 - still never fabricated when it isn't).
  Deliberately a flat list rather than nesting size under color at the top level (size now lives in
  the item-level `sizes` field, §8).
- `description`: the source's own real product description (§2's 2026-11-12 policy update, §8),
  nullable - null when the PDP has nothing real to extract, never a placeholder, never a guess.
- **2026-11-12 schema additions (§8 has the full source-by-source rationale)**: `images` (full
  gallery), `originalPriceVnd` (list price when on sale), `sizes` (`{label, available}`), `inStock`,
  `gender` (`men`/`women`/`unisex`/`kids`, only when the source states it explicitly), `sku`, `specs`
  (factual spec dict, source's own labels), `features` (short factual bullets, capped at 8), and
  `detailFetchedAt` (drives the detail-cache reuse window). All additive/optional - `schemaVersion`
  stays `1`.
- `crawledAt`: UTC `...Z`, stamped per item at crawl time (this pipeline has no dated-snapshot history
  like races, same reasoning as news — the catalog is slow-moving but a `latest.json`-only approach
  keeps this fully additive and simple for v1).

Top level (`docs/gear/latest.json`):

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-11T05:00:00Z",
  "sources": [
    { "name": "puma", "ok": true, "count": 0, "error": null },
    { "name": "salomon", "ok": true, "count": 0, "error": null }
  ],
  "items": [ /* shoes, then apparel, then accessories; stable order per source */ ]
}
```

**Dedup**: by the item's top-level `productUrl` (`pipeline/gear_main.py:dedupe_by_url`), same simple
exact-match rule the news pipeline uses — a grouped multi-color Puma item's `productUrl` is its default
variant's URL, which is already unique per base product id, so this is safe.

## 4. Architecture

Fully additive, no changes to any races/news pipeline file's logic:

```
scrapers/
  gear_base.py      # GearItem + GearVariant models, slugify/make_gear_id()
  puma_gear.py      # parses embedded `mobify-data` JSON (3 listing URLs: shoes/apparel/accessories), paginated, real c_colorSwatches -> variants
  salomon_gear.py   # Shopify /collections/<handle>/products.json endpoint (4 collections: shoes x2, apparel, accessories), one color per item
  lining_gear.py    # Haravan /collections/<handle>/products.json endpoint (4 shoes collections), one color per item
  coolmate_gear.py  # parses embedded Next.js RSC `self.__next_f.push(...)` chunks (3 listing URLs: apparel x2, accessories), real mapped_variants -> variants
pipeline/
  gear_main.py      # runs every gear scraper, dedupes by productUrl, writes docs/gear/*.json
tests/
  fixtures/puma_running_accessories.html, salomon_phu_kien_products.json,
           lining_giay_chay_bo_products.json, coolmate_quan_ao_chay_bo.html  # real captured responses
  test_puma_gear.py, test_salomon_gear.py, test_lining_gear.py, test_coolmate_gear.py, test_gear_pipeline_main.py
docs/
  gear/latest.json
```

New dependency: none — reuses `httpx`/`pydantic`/`unidecode` already in `requirements.txt`
(`selectolax` isn't needed by any gear scraper - all four parse structured JSON/JSON-in-HTML, not
HTML markup via CSS selectors).

**Workflow**: extended `.github/workflows/crawl.yml` with a third `continue-on-error: true` step
(`python -m pipeline.gear_main`), same reasoning as the news step — one shared `pip install`, one
shared "commit docs/ if changed" step, one final step that fails the job if any of the three crawls
failed. Considered a separate workflow file (so a gear-pipeline failure can't be confused with a
races/news failure in the Actions UI) but rejected for the same reason news did: the three pipelines
want the same daily cadence and the per-step `continue-on-error` + final status-check step already
makes each one's pass/fail independently visible in the job log without a second workflow file's
duplication.

**Safety rule**, same spirit as both existing pipelines: if every gear source fails in the same run
(zero items total) while a previous run had items, `pipeline.gear_main` refuses to overwrite
`latest.json` and exits non-zero.

## 5. Category mapping

`shoes | apparel | accessories`, assigned explicitly per listing URL a scraper targets (see §3) —
not a keyword guess, because every shipped source already publishes clean, separate listing pages per
category:

- Puma: `/sports/running/running-shoes`, `/sports/running/running-apparel`,
  `/sports/running/running-accessories` (switched off the generic `/sports/running` landing page on
  2026-11-12 - see "Puma re-check" in §1 for why).
- Salomon: `/collections/road-running-1` + `/collections/trail-running` (shoes), `/collections/ao-quan`
  (apparel — "shirts and shorts"), `/collections/phu-kien` (accessories — general), all four confirmed
  real collection handles from this storefront's own sitemap.
- Li-Ning: `/collections/giay-chay-bo-2` + `/collections/giay-chay-bo-nam-2` +
  `/collections/giay-chay-bo-nu-2` + `/collections/running-series-2026` — all four `shoes`. No apparel/
  accessories category is used for this source today (see §1 - the running-specific apparel/accessories
  collections on this storefront are currently empty).
- Coolmate: `/collection/quan-ao-chay-bo` + `/collection/quan-ao-chay-bo-nu` (apparel),
  `/collection/phu-kien-chay-bo` (accessories). No `shoes` category is used for this source (Coolmate
  doesn't sell running shoes at all - confirmed via its own sitemap, see §1).

## 6. Needs a human call before this goes live

- **Resolved 2026-11-12**: item descriptions used to be very thin (`"Puma running accessories."` /
  `"Salomon Giày Running."` - brand + category, nothing else, out of caution about reproducing
  marketing copy verbatim). §8 below replaces this with real per-product detail-page (PDP)
  enrichment: `description`/`specs`/`features`/`sizes`/`inStock`/`gender`/`sku`/`originalPriceVnd`/
  `images`, all pulled from structured fields or spec tables/bullet lists the PDP itself publishes,
  never fabricated, capped/cached so the extra per-product request stays within the pipeline's
  politeness and CI-time budget.
- **Hoka's 429s** (§1, held back) are worth a deliberate retry with the project's real `PoliteClient`
  (which already rate-limits and retries once) before concluding it's actually hostile to this crawler
  — this round's fetches during the research phase don't prove much on their own. Not re-checked this
  round (not in the 2026-11-12 brief's source list).
- **Decathlon, Nike, Adidas, Asics**: all four were re-checked live on 2026-11-12 with real `curl`/raw
  HTML (not the summarizing fetch tool) and all four are now confirmed held back with concrete evidence
  rather than an open question - see §1's held-back table. Nothing left to resolve for these unless the
  underlying sites change (e.g. Asics/Adidas lift their Akamai bot rule for this UA, or Decathlon/Nike
  start server-rendering their real product grid).
- **Li-Ning's apparel/accessories gap**: the storefront has real collection *pages* for running apparel
  and accessories (`quan-chay-bo`, `phu-kien-chay-bo`, ...) but they're empty today. Worth a periodic
  re-check (not a code change) in case the brand starts stocking them - `scrapers/lining_gear.py`'s
  `COLLECTIONS` list would just need those handles added back once they have real products.
- **Coolmate's per-color `variants` have no real per-color URL** (see `scrapers/coolmate_gear.py`'s
  docstring) - every variant's `productUrl` is the same base product page, only `imageUrl` differs per
  color. This is the honest shape for what this storefront exposes (confirmed: the PDP's `?color=`
  query param uses short family slugs, e.g. `den`/`xam`/`xanh`, that don't correspond 1:1 to the full
  accented display names in the listing data) - flagging so a future reviewer doesn't mistake the
  repeated URL for a bug.
- **Puma's per-color `variants` only come from the category listing page's own search-index snapshot**
  (`c_colorSwatches`), which is real, source-provided data — but it's possible (not observed, just worth
  naming) that a color shown out of stock still appears in this array; `orderable`/`comingSoon` fields
  exist on each swatch (seen in the raw data) but aren't surfaced in the schema today since this is a
  reference catalog, not a store, and stock state is exactly the kind of transient fact this pipeline
  is scoped to avoid. Flagging only so a future reviewer knows the omission was deliberate.

## 7. Local verification

### 2026-11-11 (first shipped round - Puma + Salomon)

```
$ python -m pipeline.gear_main
Wrote 137 gear items to docs/gear/latest.json
Sources OK: ['puma', 'salomon']
```

- `docs/gear/latest.json`: valid JSON, every item round-trips through `GearItem.model_validate()`
  with zero errors (137/137).
- Item counts: 137 total — 111 Salomon, 26 Puma. By category: 59 accessories, 48 apparel, 30 shoes.
- Dedup: zero duplicate `productUrl`s across the full run.
- 23 items (all Puma) carry real multi-color `variants`; all 111 Salomon items correctly have `variants:
  []` (no fabricated colors for a source that doesn't expose them).
- A random sample of 8 items' `productUrl` and `imageUrl` were fetched live (same `UnifiedHealthRaceBot`
  UA): all 8 returned HTTP 200 for both.
- `pytest`: 87 passed (80 pre-existing + 7 new gear tests: `test_puma_gear.py`, `test_salomon_gear.py`,
  `test_gear_pipeline_main.py`), 0 failed.

### 2026-11-12 (this round - Li-Ning + Coolmate added, Puma bugs fixed)

```
$ python -m pipeline.gear_main
Wrote 486 gear items to docs/gear/latest.json
Sources OK: ['puma', 'salomon', 'lining', 'coolmate']
```

- `docs/gear/latest.json`: valid JSON, every item round-trips through `GearItem.model_validate()`
  with zero errors (486/486).
- Item counts: 486 total — 204 Puma (117 shoes / 76 apparel / 11 accessories, up from 26 pre-fix),
  111 Salomon (22 shoes / 39 apparel / 50 accessories, unchanged), 112 Li-Ning (all `shoes`), 59
  Coolmate (39 apparel / 20 accessories, no `shoes` - this source doesn't sell any).
- Dedup: zero duplicate `productUrl`s and zero duplicate `id`s across the full run.
- Puma: 30 page-fetches total across its 3 listings (its full real catalog at the time of this run -
  20 pages shoes / 8 pages apparel / 2 pages accessories), confirming the pagination fix actually
  reaches every page within the `MAX_PAGES_PER_SOURCE` budget rather than silently stopping early.
- A random sample of 12 items' `productUrl` and `imageUrl` (across all four sources) were fetched live
  (same `UnifiedHealthRaceBot` UA): all 12 returned HTTP 200 for both.
- `pytest`: 93 passed (87 pre-existing + 6 new/changed: 2 new pagination-regression tests in
  `test_puma_gear.py`, `test_lining_gear.py`, `test_coolmate_gear.py`), 0 failed.

### 2026-11-12 (detail enrichment round - two live runs)

Cold-cache run 1 (no item had a `detailFetchedAt` yet, so every item is a cache miss):

```
$ python -m pipeline.gear_main
puma_gear: detail fetch failed for .../deviate-nitro-3-ekiden-running-shoes-men/313422.html?color=01: 404 Not Found
puma_gear: detail fetch failed for .../deviate-nitro-3-ekiden-running-shoes-women/313423.html?color=01: 404 Not Found
Wrote 486 gear items to docs/gear/latest.json
Sources OK: ['puma', 'salomon', 'lining', 'coolmate']
```

Salomon (111 items)/Li-Ning (112)/Coolmate (59) each fit entirely under `MAX_DETAIL_FETCHES_PER_SOURCE`
(120) and reached full/near-full detail coverage in this single run. Puma (204 items) hit the cap:
118/204 enriched, 2 of its 120 attempts genuinely 404d (a since-delisted "Deviate Nitro 3 Ekiden"
shoe still appears in the search-index listing hits but its own PDP is gone - confirmed by hand, not
a scraper bug) - per the brief, ran it again:

```
$ python -m pipeline.gear_main
puma_gear: detail fetch failed for .../deviate-nitro-3-ekiden-running-shoes-men/313422.html?color=01: 404 Not Found
puma_gear: detail fetch failed for .../deviate-nitro-3-ekiden-running-shoes-women/313423.html?color=01: 404 Not Found
Wrote 485 gear items to docs/gear/latest.json
Sources OK: ['puma', 'salomon', 'lining', 'coolmate']
```

Run 2 reused Salomon/Li-Ning/Coolmate's now-fresh cached details (zero re-fetches for those three -
confirmed by timing: run 2 finished in a few minutes vs. run 1's ~19) and spent its whole Puma budget
on the 84 items run 1 hadn't reached yet, bringing Puma to 201/203 (the same 2 real 404s persisted -
expected, since that product is actually gone). Total item count dropped 486 → 485 between runs from
ordinary catalog drift (one item fell out of a listing between the two live fetches), not a bug.

Per-source, per-field fill rate after run 2 (count of non-null/non-empty ÷ total items for that
source; `description`/`images`/`sizes`/`inStock`/`gender`/`sku`/`specs`/`features`/`detailFetchedAt`
are all populated by the 2026-11-12 detail enrichment, §8):

| Source | n | description | images | originalPriceVnd | sizes | inStock | gender | sku | specs | features | detailFetchedAt |
|---|---|---|---|---|---|---|---|---|---|---|---|
| puma | 203 | 99.0% | 99.0% | 68.0% | 99.0% | 99.0% | 97.5% | 99.0% | 99.0% | 92.6% | 99.0% |
| salomon | 111 | 100.0% | 100.0% | 44.1% | 85.6% | 100.0% | 87.4% | 100.0% | 96.4% | 27.9% | 100.0% |
| lining | 112 | 100.0% | 100.0% | 45.5% | 100.0% | 100.0% | 96.4% | 100.0% | 99.1% | 10.7% | 100.0% |
| coolmate | 59 | 91.5% | 100.0% | 20.3% | 96.6% | 100.0% | 100.0% | 100.0% | 96.6% | 3.4% | 100.0% |

`detailFetchedAt` coverage **is** the real detail-enrichment coverage rate - 99-100% for every source
(the only gaps left are Puma's 2 confirmed-dead PDPs). `originalPriceVnd` and `features` are
genuinely low for some sources, not a bug: `originalPriceVnd` is null whenever an item isn't
currently on sale (most aren't), and `features` is null whenever a PDP has no real bullet/chip list
to extract from (common for Salomon/Li-Ning's plainer product templates - see §8's "what's not
exposed" notes). `sizes` at 85.6% for Salomon reflects real one-size-fits-all accessories (water
bottles, some caps) that have no size option at all, not a parsing gap.

- `docs/gear/latest.json`: valid JSON, all 485/485 items round-trip through `GearItem.model_validate()`
  with zero errors; zero duplicate `productUrl`s or `id`s.
- Spot-check: 3 items per source (12 total, different items than the 2026-11-12 pagination round's
  sample) had both `productUrl` and `imageUrl` fetched live - all 24 URLs returned HTTP 200. One
  Salomon item's description ("ERO GLIDE 2 cho phép bạn...") was checked against its live PDP and
  confirmed to be a literal transcription of a real typo in Salomon's own `body_html` (a stray
  `<strong>` tag swallows the leading "A" of "AERO GLIDE 2" in the source's own markup) - not
  introduced by this pipeline's parsing.
- `pytest`: 120 passed (93 pre-existing + 27 new: `tests/test_gear_base.py` (17 tests for the new
  HTML/text/cache helpers) plus detail-enrichment + cache-reuse tests in each of
  `test_puma_gear.py`/`test_salomon_gear.py`/`test_lining_gear.py`/`test_coolmate_gear.py` and two new
  `run_scrapers` wiring tests in `test_gear_pipeline_main.py`), 0 failed.

## 8. 2026-11-12 detail enrichment

Full per-product detail (PDP) fetch added for all four sources - one extra request per product
(capped by `scrapers.gear_base.MAX_DETAIL_FETCHES_PER_SOURCE` = 120/source/run, with a 7-day
detail-cache reuse keyed by `productUrl` so a product's detail is only re-fetched once it's stale -
see `scrapers.gear_base.should_reuse_cached_detail`/`apply_cached_detail`/`enrich_with_detail`).
Every detail fetch reuses the same `PoliteClient` (robots.txt, rate limit, retry) as the listing
fetches, goes to the item's own real `productUrl`/PDP (never a cart/checkout/account endpoint), and
a failed or budget-exhausted fetch never drops the item - it just keeps its listing-only data.

| Field | Puma | Salomon / Li-Ning (Shopify/Haravan) | Coolmate |
|---|---|---|---|
| `description` | `longDescription`'s "PRODUCT STORY" prose (HTML stripped, headings/tables/lists removed first) | `body_html`'s intro prose (same stripping) | `short_desc`, with the site-wide "✓Giá tốt ✓COD toàn quốc ✓60 ngày đổi trả" promo badge suffix cut off |
| `images` | `imageGroups` (`large-VNM` view), deduped | `images[].src` | `images[].src`, `IMAGE_CDN`-qualified |
| `originalPriceVnd` | `c_listPrice` when it exceeds `c_salePrice`/`price` | default variant's `compare_at_price` when it exceeds `price` | `compare_price` when it exceeds `regular_price` |
| `sizes` | `variationAttributes` id `"size"` values, each with its own `orderable` | the option named like "size"/"Kích thước", per-variant `available` | the option named like "size"/"Kích thước", per-variant `quantity > 0` |
| `inStock` | `inventory.orderable` | top-level `available` | top-level `available` |
| `gender` | `c_gender` (normalized) | the spec table's "Giới tính" row, else a `GT_Nam`/`GT_Nữ`-style tag (`gender_from_shopify_tags`) | `gender_type` (`MALE`/`FEMALE`/...) |
| `sku` | `master.masterId` (fallback `c_styleNumber`) | the spec table's "Mã SKU" row, else a caps alphanumeric code embedded in the title (`extract_code_from_title`), else the variants' common SKU prefix | every variant's `sync_product[0].label` common prefix (no direct SKU field exists) |
| `specs` | `longDescription`'s "DETAILS"/"FEATURES & BENEFITS" `<li>` "Label: Value" bullets, plus `c_mainMaterial`/`c_fabricsType`/`c_SportType`/`c_ageGroup`/`c_articleType` | `body_html`'s spec table (`<table>`), "Label: Value" `<li>` bullets, and `<br>`-separated "Label: Value" lines - whichever shape that product's template uses; importer/manufacturer-address rows dropped as boilerplate | `extra.p_extra_features` (`{title, value[]}` pairs - already structured, no HTML parsing needed) |
| `features` | `longDescription`'s non-colon `<li>` bullets | non-colon `<li>` bullets (material/tech lists only - cut before any "bảo quản"/care-instructions heading so washing instructions are never misclassified as a feature) | `extra.p_extra_attributes` chips where `checked: true` |
| `variants[].priceVnd`/`images`/`sizes` | not populated (Puma's `variants` already carry per-color `imageUrl`; no further per-color detail was worth the extra complexity this round) | n/a (`variants` is empty for these sources - one color per product, see §1/§3) | not populated this round (`mapped_variants`/`variants` do have a real per-size `quantity` per color, but wiring it through to each `GearVariant.sizes` was left for a future pass - flagging, not silently skipped) |
| `detailFetchedAt` | stamped on every successful fetch | stamped on every successful fetch | stamped on every successful fetch |

What each source does **not** expose, confirmed live (left null/empty rather than guessed):

- **Puma**: no explicit fabric-composition percentage breakdown (only `c_mainMaterial`, a single
  material name); no weight/drop numbers for apparel/accessories (only shoes' detail pages tend to
  carry a size-spec table, and even then `c_sizeSpecTable` is dimensional, not drop/stack-height).
- **Salomon/Li-Ning**: not every product's `body_html` has a real spec table - some (seen on
  accessories) only have `<br>`-separated lines, and a few products have essentially no structured
  facts at all beyond the intro paragraph, so `specs`/`features` are legitimately empty for those.
- **Coolmate**: no numeric weight/dimensions field was found on any inspected product (`extra.p_extra_features`
  covers fabric/technology/fit/use, not physical measurements); `sku` has no direct field, only the
  derived common-prefix (see table above).

## 9. 2026-11-12 (round 2) `gender` field (men/women/unisex/kids/null)

The brief asked for an optional per-item `gender` so the app can filter Nam/Nữ. §8 already landed
one real source-provided signal per source (`c_gender`/the "Giới tính" spec-table row/a `GT_Nam`/
`GT_Nữ` Shopify tag/`gender_type`), but that still left real items null whenever a product's own PDP
genuinely doesn't carry a gender field or tag (confirmed live - see the per-source null examples
below). This round adds two more layers **on top of** that existing signal, same "same project
policy" guardrails (robots.txt respected, `PoliteClient`, no anti-bot bypass, no fabricated data) and
same additive/optional schema (`schemaVersion` unchanged) - never replacing a source-provided value,
only filling what was genuinely still `null`. Fixed priority order, most-trusted first
(`scrapers.gear_base`'s docstring on `GearItem.gender` has the same list):

1. **Source-provided field/tag** (§8, unchanged) - Puma's `c_gender`, Salomon/Li-Ning's spec-table
   "Giới tính" row or `GT_Nam`/`GT_Nữ` tag, Coolmate's `gender_type`.
2. **Per-gender listing membership** (new) - for the two sources whose own collection *structure*,
   not just the PDP, is explicitly gendered:
   - **Li-Ning**: `giay-chay-bo-nam-2` (confirmed real, non-empty, "giày chạy bộ **nam**" = men's
     running shoes) and `giay-chay-bo-nu-2` ("... **nữ**" = women's) - both already crawled by
     `lining_gear.py` for product coverage, just not previously used as a gender signal.
   - **Coolmate**: `quan-ao-chay-bo-nu` ("quần áo chạy bộ **nữ**" = women's running apparel) -
     already crawled for product coverage, same story. Its sibling `quan-ao-chay-bo` is the
     storefront's *general* running-apparel listing, not a men's-only one by any signal the
     storefront itself states (Coolmate being characterized as a menswear-first brand in `README.md`/
     the module docstring is a house-brand description, not a per-collection gender statement the
     storefront makes) - so, per the "never guess" rule, that collection is deliberately **not**
     treated as a men's signal. Salomon/Puma have no per-gender collection at all (confirmed in §1 -
     Salomon's four collections are `road-running-1`/`trail-running`/`ao-quan`/`phu-kien`, none
     gendered; Puma's listing hits carry no gender field, only its PDP does), so this layer is a
     no-op for those two sources.
   - `scrapers.gear_base.resolve_listing_gender(genders: set[str]) -> str | None` collapses the set
     of gender tags a product was seen under, across *every* collection a scraper crawls (tracked in
     a two-pass `scrape()`: first gather every collection's products and which gender tag, if any,
     its own collection carries, then resolve each distinct product once all collections have been
     scanned) - one tag if there's only one, `"unisex"` if the same product genuinely appeared under
     both a men's and a women's listing, `null` if it wasn't seen under any gendered listing. A
     listing-derived gender is never later clobbered back to `null` by a PDP fetch (cached or fresh)
     that simply doesn't carry its own gender field - `apply_cached_detail`/`enrich_with_detail` both
     only overwrite `gender` when the detail fetch's own value is non-null (regression-tested in
     `tests/test_gear_base.py`).
3. **Name/title keyword fallback** (new, last resort) - `scrapers.gear_base.gender_from_text`,
   applied once centrally in `pipeline/gear_main.py` (`fill_missing_gender_from_text`, right after
   dedup) to whatever is still `null` after layers 1-2. Matches, diacritics-insensitive and
   whole-word only (never a substring match): `women's`/`womens`/`wmns`/`women`/`nữ` → `women`;
   `men's`/`mens`/`men`/`nam` → `men`; `unisex` → `unisex`; `kids`/`kid`/`junior`/`trẻ em` → `kids`.
   A name matching both a men's and a women's keyword (e.g. "Women's & Men's Running Tee") resolves
   to `unisex` rather than picking a side arbitrarily. The one false positive the brief explicitly
   called out - `"nam"` as a substring of the country name - is handled by stripping
   `"việt nam"`/`"vietnam"` out of the text *before* scanning for keywords, so a product named e.g.
   "Áo chạy bộ Việt Nam 2026" correctly resolves to `null`, not `"men"`. Verified live: before this
   fallback, items like "VELOCITY 7-inch Running Shorts Men", "Deviate NITRO™ 3 Ekiden Running Shoes
   Women", and four Li-Ning "Giày chạy bộ trẻ em YKFW002-*V" kids' shoes were sitting at `gender:
   null` purely because their own PDP had no gender field/tag that round - this layer now recovers
   exactly those from the name itself. Accessories with no gender wording at all (backpacks, water
   bottles, socks, belts - genuinely gender-neutral gear) correctly stay `null`, not guessed.
4. Otherwise `null` - never guessed blindly, same as every other nullable field in this schema.

**Before this round** (source-provided field/tag only, from the §7 run-2 numbers): gender fill rate
was puma 97.5%, salomon 87.4%, lining 96.4%, coolmate 100% - already high, but with real,
explainable gaps (Puma: a couple of items whose PDP genuinely has no `c_gender`; Salomon: ~14 items,
mostly gender-neutral accessories *and* a few real misses like "Mũ Thể Thao Unisex..." that said
"Unisex" plainly in the name but had no spec-table/tag row for it). Layers 2-3 close the two kinds of
remaining gap: layer 2 for Li-Ning/Coolmate products whose PDP detail fetch missed the window (cold
cache, budget-exhausted, or simply didn't carry the field) but whose *listing* already proves the
gender; layer 3 for the plain "says it in the name" cases across every source. Genuinely
gender-neutral items (most accessories) are expected to stay `null` regardless - that's the schema
working as intended, not a coverage gap.

## Sources checked

- https://vn.puma.com/robots.txt, https://vn.puma.com/sitemap_index.xml
- https://vn.puma.com/vn/en/sports/running, https://vn.puma.com/vn/en/sports/running/running-accessories
- https://vn.puma.com/vn/en/pd/fast-rb-nitrotm-elite-2-running-shoes-men/314984.html
- https://vn.puma.com/vn/en/pd/deviate-pure-nitrotm-running-shoes-men/313904.html
- https://vn.puma.com/vn/en/pd/everyday-running-waist-bag/092404.html?color=05 (raw HTML fetched
  directly once shell access returned — the embedded `#mobify-data` JSON and its `/product-search`
  cache entry with `c_colorSwatches` were found and parsed from this live response)
- https://vn.salomon.com/robots.txt, https://vn.salomon.com/sitemap.xml, .../sitemap_collections_1.xml
- https://vn.salomon.com/collections/trail-running, .../collections/road-running-1,
  .../collections/ao-quan, .../collections/phu-kien, .../collections/balo, .../collections/mu-non-the-thao
- https://vn.salomon.com/collections/phu-kien/products.json (the real public endpoint the scraper uses)
- https://vn.salomon.com/products/giay-chay-the-thao-nam-salomon-alphacross-5-l47313300-grey
- https://vn.salomon.com/products/giay-chay-the-thao-nam-salomon-alphacross-5-l47313300-grey.json
- https://vn.hoka.com/robots.txt (429 on two follow-up page fetches)
- https://www.decathlon.vn/robots.txt, https://www.decathlon.vn/en-VN/c/sitemap_1.xml, .../p/sitemap_1.xml
- https://www.decathlon.vn/en-VN/p/jogflow-190-1-women-s-running-shoes-dark-blue-pink-decathlon-8757341.html
- https://www.nike.com/robots.txt (web search for nike.com/vn running shoes listings)
- https://www.adidas.com.vn/robots.txt (403)
- https://www.asics.com/robots.txt (404 on /vn/en/ path; web search for VN availability)
- Web search: Hoka VN official store opening, Brooks Running VN presence/reseller model

### 2026-11-12 (this round, all via real `curl`/`httpx` with the project's actual UA)

- https://www.decathlon.vn/robots.txt (full file - confirmed blanket `Disallow: *?*`),
  https://www.decathlon.vn/en-VN/c/running-walking/road-running-marathon/running-shoes/men-running-shoes.html
  (raw HTML + its `__NEXT_DATA__` payload - `pageProps.seoProducts` tiny SEO sample,
  `pageProps.dehydratedState.queries` has no product-search entry)
- https://www.coolmate.me/robots.txt (301 → https://www.coolmate.me/robots.txt, 200),
  https://www.coolmate.me/sitemap/collection0.xml, .../sitemap/product0.xml
- https://www.coolmate.me/collection/quan-ao-chay-bo, .../quan-ao-chay-bo-nu, .../phu-kien-chay-bo
  (raw HTML - RSC `self.__next_f.push(...)` chunks decoded and parsed for the real `products` array)
- https://www.coolmate.me/product/quan-shorts-nam-chay-bo-2-lop-essentials-fast-free-run-v3-nhanh-kho
  (confirmed `?color=` uses short family slugs, not matching the listing's full color names)
- https://mcdn.coolmate.me/... (image CDN host for `default_thumbnail`/`colorImage` paths)
- https://lining.com.vn/robots.txt ("we use Haravan as our ecommerce platform"),
  https://lining.com.vn/sitemap.xml, .../sitemap_collections_1.xml
- https://lining.com.vn/collections/giay-chay-bo-2/products.json, .../giay-chay-bo-nam-2/products.json,
  .../giay-chay-bo-nu-2/products.json, .../running-series-2026/products.json (all non-empty, real data)
- https://lining.com.vn/collections/quan-chay-bo/products.json, .../phu-kien-chay-bo/products.json,
  .../chay-bo-nam/products.json, .../chay-bo-nu/products.json, .../running-series/products.json, and
  several `giay-chay-bo-*-1` handles (all confirmed `{"products": []}` live)
- https://vn.puma.com/vn/en/sports/running (confirmed to mix apparel hits into its "shoes" results -
  the bug being fixed), https://vn.puma.com/vn/en/sports/running/running-shoes,
  .../running-apparel, .../running-accessories, each with `?page=2`/`?page=3` (confirmed real
  pagination, `offset`/`total`/`limit` fields inspected directly from each page's `/product-search`
  React Query cache entry)
- https://www.nike.com/robots.txt, https://www.nike.com/vn/w/mens-running-shoes-37v7jznik1zy7ok
  (raw HTML + its `__NEXT_DATA__` payload - no product data in `pageProps`, confirmed client-fetched)
- https://www.adidas.com.vn/robots.txt (403, Akamai bot-defense page, inspected in full)
- https://www.asics.com/robots.txt (200), https://www.asics.com/vn/, .../vn/en-vn/, .../vn/vi-vn/,
  .../vn/vi-vn/running/c/asx0101/ (all 403, Akamai "Access Denied" edge response)
- Web search: official ASICS Vietnam online store confirmation + VN reseller names (`ash.vn`,
  `oss.com.vn`)

### 2026-11-12 detail-enrichment audit (all via real `curl`/`httpx` with the project's actual UA)

- https://vn.puma.com/vn/en/pd/everyday-running-waist-bag/092404.html?color=05,
  .../pd/essentials-running-5-panel-cap/026168.html?color=01 (raw HTML + embedded `mobify-data`'s
  `/products/<id>` React Query entry - `longDescription`, `c_gender`, `inventory`,
  `variationAttributes`, `c_listPrice`/`c_salePrice`, `imageGroups`, `master.masterId` all inspected
  directly)
- https://vn.salomon.com/products/giay-chay-the-thao-nam-salomon-alphacross-5-l47313300-grey.json,
  .../products/balo-hiking-salomon-cross-12-black-lc2185700.json (raw JSON - `body_html`'s spec table
  vs. `<br>`-separated lines confirmed as two different real templates on this one storefront)
- https://lining.com.vn/products/giay-chay-bo-super-light-23-nam-arbw017-17v.json,
  .../products/giay-chay-bo-infinity-6-nu-arhw018-6v.json (raw JSON - confirmed the `GT_Nam`/`GT_Nữ`
  tag convention on two real products, one of each)
- https://www.coolmate.me/product/quan-shorts-nam-chay-bo-2-lop-essentials-fast-free-run-v3-nhanh-kho
  (raw HTML - the PDP's own `self.__next_f.push` RSC chunk holding `"initialProduct":{...}`, confirmed
  self-contained in one chunk; `short_desc`, `extra.p_extra_features`/`p_extra_attributes`,
  `gender_type`, `available`, `regular_price`/`compare_price`, `variants[].sync_product[0].label` all
  inspected directly)
- Live spot-checks after both pipeline runs: 12 `productUrl`/`imageUrl` pairs (3 per source, sampled
  from the actual `docs/gear/latest.json` output) fetched live, all HTTP 200 - see §7's "detail
  enrichment round" for the list and the one confirmed vendor-side typo found along the way.
