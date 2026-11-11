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

## 1. Sources

### Ship in v1

| # | Source | Platform | What it shows | Scrapability (checked) |
|---|---|---|---|---|
| 1 | **PUMA Vietnam**, `https://vn.puma.com/vn/en/sports/running` | Salesforce Commerce Cloud **PWA Kit** (React app, server-rendered for first load - not the classic SFCC template family the initial pass assumed) | Running shoes, apparel (shorts, tees, tights) and accessories (waist bags, caps) under one `/sports/running` vertical with sub-category pages (`/running-apparel`, `/running-accessories`). Real brand, real VN storefront, VND pricing, free-shipping threshold in VND — genuinely sells to Vietnam. | Confirmed server-rendered: every listing page embeds one `<script id="mobify-data" type="application/json">` tag holding the page's full server-fetched React Query cache, including a `/product-search` entry with structured `hits` (`productName`, `price`/`c_salePrice`, `c_canonicalUrl`, `imageGroups`, and `c_colorSwatches` - a per-product array of every color with its real name, e.g. "Zen Blue", "Puma Black", each with its own image and product id). `scrapers/puma_gear.py` parses this JSON directly - no CSS-selector guessing, no JS execution. `robots.txt`: `Allow` by default, only disallows `*account*`, `*checkout*`, `*cart*`, `*wishlist*`, `*login*`, `*registration*`, `*reset-password*`, `*callback*` — none of which this pipeline touches. Sitemap index at `sitemap_index.xml`. Verified end-to-end: `python -m pipeline.gear_main` run live on 2026-11-11 returned 26 Puma items, 23 with real multi-color `variants`; a sample of product/image URLs spot-checked HTTP 200 (§7 in the handoff report). |
| 2 | **Salomon Vietnam**, `https://vn.salomon.com/collections/road-running-1` (+ `trail-running`, `ao-quan`, `phu-kien`) | Shopify (Vietnamese reseller storefront, platform note in its own `robots.txt`: "we use Haravan as our ecommerce platform" — actually Shopify theme markup on inspection, Haravan is the checkout/ops backend) | Trail and road running shoes, running apparel, and accessories (backpacks, caps, hydration vests, water bottles) across four confirmed real collections pulled from this storefront's own sitemap. Real brand, dedicated VN storefront, VND pricing. | `scrapers/salomon_gear.py` uses Shopify's standard public `/collections/<handle>/products.json` endpoint directly (confirmed live, returns structured `title`/`handle`/`product_type`/`images`/`variants`) rather than HTML-scraping the collection page - no HTML parser needed for this source at all. `robots.txt`: only disallows `/admin`, `/cart(s)`, `/orders`, `/checkout(s)`, `/account`, `/search`, `/discount/*`, URL-encoded `+` in `/collections/*`/`/blogs/*` — none of which this pipeline touches. Verified end-to-end: `python -m pipeline.gear_main` run live on 2026-11-11 returned 111 Salomon items across all three categories; a sample of product/image URLs spot-checked HTTP 200. |

### Checked and held back for v2

| # | Source | Why held back |
|---|---|---|
| 3 | **Hoka Vietnam**, `vn.hoka.com` | Real official store (opened its first physical VN store at Saigon Centre, HCMC, April 2025 — distributed by Central Brand & Specialty Group), also a Shopify storefront, `robots.txt` is permissive (`Allow: /`, standard Shopify disallow list for cart/checkout/admin, sitemap at `/sitemap.xml`). **Held back purely on observed behavior, not policy**: two polite, several-seconds-apart `WebFetch` requests during this research session both got `HTTP 429 Too Many Requests` with a `Retry-After: 60` header. That's a real signal this storefront rate-limits more aggressively than Puma/Salomon did under the same light request pattern — worth a v2 pass with the project's actual `PoliteClient` (which already waits `REQUEST_DELAY_SECONDS` between requests and retries once on 429) rather than assuming it'll misbehave, but not confirmed safe today, so not shipped in v1. |
| 4 | **Decathlon Vietnam**, `decathlon.vn` | `robots.txt` is permissive for category/product paths (`Allow: /`, sitemaps at `.../c/sitemap_1.xml`, `.../p/sitemap_1.xml`, `.../s/sitemap_1.xml`) and it genuinely sells running shoes/apparel/accessories under real (if house) running brands — **Kiprun** and **Kalenji** — with Vietnam availability and VND pricing confirmed from the product sitemap (e.g. `kiprun-ks900-2-women-s-running-shoes...html`, `tws500-running-earphones-100-wireless-kiprun...html`). Held back for two reasons: (a) `robots.txt` has a blanket `Disallow: *?*` — **any URL with a query string is off-limits** — and this platform's (PrestaShop-family) color/size switching could not be confirmed to work without one (no sibling-color links or embedded combination JSON were found in the one PDP inspected, but that inspection went through the same imperfect summarizing fetch noted above, not a raw-HTML check); (b) Kiprun/Kalenji are Decathlon's own house brands rather than an independent runner-facing brand, which is "real" but a slightly different flavor than Puma/Salomon — worth a dedicated v2 pass rather than rushing it into v1 on an unconfirmed variant story. |
| 5 | **Nike Vietnam**, `nike.com/vn` | Has a real `/vn/` storefront with running shoes in VND (confirmed via search: Pegasus/Vomero/Vaporfly lines, ₫2.1M–₫5.0M range). Not inspected for raw scrapability this round (time budget) and Nike's global `robots.txt` had no `/vn/`-specific rules in what the fetch tool returned, which itself is a little surprising for a site this size and worth confirming isn't an artifact of the summarizing fetch before trusting it. Nike.com is also known to ship a heavier React/Next.js frontend than Puma's SFCC templates; whether the product grid is present in the pre-hydration HTML (like Puma) or only in client-rendered JS needs a direct check this session couldn't do reliably. Candidate for v2 once that's confirmed one way or the other. |
| 6 | **Adidas Vietnam**, `adidas.com.vn` | `robots.txt` fetch returned `HTTP 403 Forbidden` to this session's fetch tool — could be a bot-defense rule keyed on the fetch tool's own request signature rather than a real blanket block, but it couldn't be told apart from here. Needs a direct check (ideally real `curl` with the project's actual `UnifiedHealthRaceBot` UA) before deciding either way. Not shipped. |
| 7 | **Asics Vietnam** | No dedicated `asics.com/vn/...` path resolved (404) during this session's check; Asics VN availability appears to go through resellers (e.g. Supersports) rather than a brand-owned `.vn`/`/vn/` storefront. Not pursued further this round — candidate if a real Asics VN storefront surfaces later. |
| 8 | **Brooks Running** | Confirmed to have a Vietnam presence (Brooks Sports Vietnam LLC, a sourcing/production office in HCMC) but **no Brooks-owned retail storefront** — Brooks explicitly sells only through "authorised resellers," and this round didn't identify a specific VN reseller with a clean public catalog. Skipped for v1; would need a named reseller site vetted on its own merits (robots.txt, static HTML) to reconsider. |

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

- Store **name, brand, category, a short factual description written in this project's own words
  (not copy-pasted marketing copy), price if publicly listed, image URL(s), and the brand's own
  product page URL** — the product page is always present and is the only way to actually buy it.
  Never store availability/stock counts, never touch a cart/checkout/payment endpoint, never collect
  user data.
- `description` is a short, factual restatement (shoe type, notable spec like cushioning/drop/weight
  if the listing states it plainly) — not a copy of the brand's marketing paragraph. Several of the
  product pages inspected this round had marketing language ("the rulebreaker is back and faster than
  ever") that must NOT be stored verbatim; a scraper should either paraphrase mechanically (strip to
  bare facts only) or, if a clean factual sentence isn't extractable, leave `description` null rather
  than lightly-reworded marketing copy.
- Same `UnifiedHealthRaceBot/1.0` UA, same `PoliteClient` (robots.txt check once per host, rate limit,
  retry-once) as the other two pipelines — no parallel HTTP stack, no special-casing that skips
  politeness. `docs/bot.html` is extended in this branch to disclose the gear pipeline the same way it
  already discloses races and news.
- Listing pages only, same "one page deep" discipline as the news pipeline: category/collection
  listing pages for shoes/apparel/accessories give name+price+image+URL+color-variant rows directly
  (confirmed above), so no per-product detail-page fetch is needed for v1 the way the races pipeline
  needs one for description enrichment. If a future pass wants richer descriptions, that would be a
  deliberate, budgeted addition (one extra request per product, same shape as
  `pipeline/main.py:enrich_images_and_descriptions`), not a default.
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
  "productUrl": str }`. Deliberately a flat list rather than nesting size under color (no source
  exposed size-level data worth capturing for a reference catalog, and size/variant-level stock is
  exactly the kind of transient "store" data this pipeline is scoped to avoid).
- `description`: short, factual, own words, nullable — see §2's rule against reworded marketing copy.
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
  puma_gear.py      # parses embedded `mobify-data` JSON (3 listing URLs: shoes/apparel/accessories), real c_colorSwatches -> variants
  salomon_gear.py   # Shopify /collections/<handle>/products.json endpoint (4 collections: shoes x2, apparel, accessories), one color per item
pipeline/
  gear_main.py      # runs every gear scraper, dedupes by productUrl, writes docs/gear/*.json
tests/
  fixtures/puma_running_accessories.html, salomon_phu_kien_products.json  # real captured responses
  test_puma_gear.py, test_salomon_gear.py, test_gear_pipeline_main.py
docs/
  gear/latest.json
```

New dependency: none — reuses `httpx`/`pydantic`/`unidecode` already in `requirements.txt`
(`selectolax` isn't needed by either v1 gear scraper - both parse structured JSON, not HTML).

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
not a keyword guess, because both v1 sources already publish clean, separate listing pages per
category:

- Puma: `/sports/running` (shoes — the vertical's own landing/shoe grid), `/sports/running/running-apparel`,
  `/sports/running/running-accessories`.
- Salomon: `/collections/road-running-1` + `/collections/trail-running` (shoes), `/collections/ao-quan`
  (apparel — "shirts and shorts"), `/collections/phu-kien` (accessories — general), all four confirmed
  real collection handles from this storefront's own sitemap.

## 6. Needs a human call before this goes live

- **Item descriptions are currently very thin** (`"Puma running accessories."` /
  `"Salomon Giày Running."` - brand + category, nothing else). This is a deliberate safety choice, not
  an oversight: both storefronts' real description fields are marketing copy (Puma's PDP text, Shopify's
  `body_html`), and this project's own rule (§2) is to never store that verbatim or lightly reworded.
  Rather than risk a bad paraphrase, the scraper only uses structured facts it can fully vouch for. A
  future pass could do better (e.g. surface a shoe's listed weight/drop/cushioning spec, if structured,
  rather than just brand+category) but that's a deliberate quality investment to schedule, not a bug to
  silently patch with heavier text processing.
- **Hoka's 429s** (§1, held back) are worth a deliberate retry with the project's real `PoliteClient`
  (which already rate-limits and retries once) before concluding it's actually hostile to this crawler
  — this round's fetches during the research phase don't prove much on their own.
- **Decathlon's `Disallow: *?*`** (§1, held back) needs an actual look at the raw PDP HTML to confirm
  whether color switching really requires a query string, before deciding if it's scrapable at all for
  the color-variant feature.
- **Nike VN and Adidas VN** (§1, held back) each need a direct, unambiguous scrapability check (Nike:
  is the product grid in pre-hydration HTML; Adidas: is the 403 a real block or specific to one fetch
  method) that this round didn't reach.
- **Puma's per-color `variants` only come from the category listing page's own search-index snapshot**
  (`c_colorSwatches`), which is real, source-provided data — but it's possible (not observed, just worth
  naming) that a color shown out of stock still appears in this array; `orderable`/`comingSoon` fields
  exist on each swatch (seen in the raw data) but aren't surfaced in the schema today since this is a
  reference catalog, not a store, and stock state is exactly the kind of transient fact this pipeline
  is scoped to avoid. Flagging only so a future reviewer knows the omission was deliberate.

## 7. Local verification (live run, 2026-11-11, once shell access was available)

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
