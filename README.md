# unified_health_service

A small Python service that crawls Vietnamese running-race listing sites once a day,
merges and deduplicates the results into one JSON file, and publishes it via GitHub
Pages. It exists so a separate Android app (part of a broader "one app for all watch
brands" health project) can show users a unified calendar of upcoming races in Vietnam
without each client having to scrape anything itself.

## JSON endpoint

```
https://noattoan.github.io/unified_health_service/races/latest.json
```

This file is regenerated daily by a GitHub Actions workflow and always reflects the
most recent successful crawl. Dated snapshots (`races/YYYY-MM-DD.json`) are also kept
for the last 90 days, written only on days the content actually changed.

A plain HTML landing page lives at `https://noattoan.github.io/unified_health_service/`
for humans, and `bot.html` explains what the crawler does (it's also referenced from
the crawler's User-Agent string).

## Sources

| Source | What it contributes |
|---|---|
| [VnExpress "Lịch giải chạy"](https://vnexpress.net/the-thao/marathon/lich-giai-chay) | Distances, terrain, province |
| [iRace ticket portal](https://ticket.irace.vn/categories/marathon) | Price, registration status/link |
| [Vietnam's Best Marathons](https://bestmarathon.vn/race-info/) | Widest coverage; distances, terrain, organizer |
| [Finishers.com](https://www.finishers.com/en/destinations/asia/vietnam) | Cross-check, mostly major/international races |

The first three are the "Tier 1" sources the pipeline depends on; Finishers is a
Tier-2 extra. Only public pages are fetched — `robots.txt` is checked before every
host's first request, requests are rate-limited and capped per source, and nothing
requiring login or bypassing anti-bot protection is ever touched. See
`docs_research/RACE_SOURCES_RESEARCH.md` for the full research behind these choices,
and `docs/bot.html` for the crawler's public-facing policy statement.

## Data schema

Top level of `races/latest.json`:

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-08T14:30:55Z",
  "sources": [
    { "name": "irace", "ok": true, "count": 88, "error": null }
  ],
  "races": [ /* Race objects, sorted by startDate, startDate >= today-1 */ ]
}
```

`sources[]` reports the health of each scraper on the last run: `ok: false` means
that source failed (site layout changed, network error, etc.) and its races were
carried over unchanged from the previous `latest.json` instead of being dropped.

One race entry:

```json
{
  "id": "vnexpress-marathon-hanoi-midnight-2026-11-29",
  "name": "Vnexpress Marathon Hanoi Midnight",
  "startDate": "2026-11-29",
  "endDate": null,
  "province": "Hà Nội",
  "location": "Hà Nội",
  "terrain": "road",
  "distances": [
    { "label": "42km", "km": 42.195, "priceVnd": null, "status": "unknown" }
  ],
  "priceFromVnd": 790000,
  "registrationStatus": "open",
  "organizer": null,
  "registrationUrl": "https://ticket.irace.vn/vnexpress-marathon-hanoi-midnight-2026",
  "imageUrl": "https://i1-thethao.vnecdn.net/.../thumb.jpg",
  "description": "Vnexpress Marathon Hanoi Midnight quay trở lại với cung đường chạy đêm qua các địa danh nổi bật của thủ đô...",
  "raceStatus": "upcoming",
  "results": null,
  "sources": [
    { "name": "vnexpress", "url": "https://vnexpress.net/...", "lastSeenAt": "2026-11-08T14:30:55Z" },
    { "name": "irace", "url": "https://ticket.irace.vn/...", "lastSeenAt": "2026-11-08T14:30:55Z" },
    { "name": "vbm", "url": "https://bestmarathon.vn/...", "lastSeenAt": "2026-11-08T14:30:55Z" }
  ],
  "firstSeenAt": "2026-10-01T23:05:00Z",
  "lastUpdatedAt": "2026-11-08T14:30:55Z"
}
```

- `terrain`: `road | trail | city_trail | ultra | triathlon | virtual`
- `registrationStatus` / per-distance `status`: `open | closed | sold_out | unknown`
- `raceStatus`: `upcoming | past`, computed fresh on every run by comparing `startDate` to
  the crawl's current date (Vietnam time, same as `generatedAt`'s basis) - no extra network
  calls. Both upcoming and past races are kept in the same file; this field is only there
  so a client can filter without having to parse/compare dates itself.
- `imageUrl`: a real official race image, in priority order: (1) a thumbnail/banner already
  present on the source's listing page (`vnexpress`/`irace`/`vbm` all have one), otherwise
  (2) the `og:image` meta tag scraped from the race's own detail page. `null` if neither
  yielded anything.
- `description`: a short best-effort text block (a line already on the listing page for VBM,
  or `og:description`/first substantial `<p>` from the detail page otherwise), truncated to
  a few sentences. `null` if nothing reasonable was found.
- `results`: `{ distance, topFinishers: [{ rank, name, timeSeconds }] }[]`, or `null`. Reserved
  for past races' top finishers - see "Results" below for why it's `null` on every race today.
- `id` is stable across days: `slugify(name with year/sponsor words stripped) + "-" + startDate`.
- `firstSeenAt` is preserved across runs (when a race is first discovered); `lastUpdatedAt`
  only moves forward when the race's actual content changes, not just because the bot
  re-confirmed it exists (that's what each source's own `lastSeenAt` is for).

### Dedup and merge rules

Races are deduplicated first by exact `id` match, then by a fuzzy name match
(`rapidfuzz` token-set ratio ≥ 90) for races sharing the same `startDate` — this
catches cases like iRace appending "Powered by PUMA" to a name VnExpress/VBM report
more plainly. When the same race comes from multiple sources, fields are merged with
fixed precedence:

- **`priceFromVnd`** is `min(distances[].priceVnd)` across the merged race's own distances
  (skipping `null`/`0`), computed *after* merging - not copied from whichever single source
  happened to advertise a "from" price, since that source isn't necessarily the one that ends
  up winning `distances`. Only falls back to **iRace**'s advertised price when no distance
  has a price at all (true for every scraper today - none publish a per-distance breakdown
  yet, so this is a no-op in practice until one does).
- **iRace** wins for `registrationStatus`, `registrationUrl`.
- **VBM** / **VnExpress** win for `distances`, `terrain`, `imageUrl` and `description`
  (falling back to whichever source has a non-empty value when neither has one).
- `sources[]` is the union of every contributing source.
- `raceStatus` isn't merged from any source - it's computed once on the final
  deduplicated list, see `pipeline/main.py`.

See `pipeline/merge.py` for the implementation.

## Results (top finishers for past races)

The schema reserves a `results` field per race (see above) for top-finisher data once
a race has happened, but it is `null` for every race in the current pipeline. This was
investigated and deliberately deferred rather than shipped half-working:

- **iRace** (`ticket.irace.vn`) is a registration/ticketing portal only - even long-finished
  events' pages have no results/ranking section at all (checked directly).
- **VBM** (`bestmarathon.vn`) detail pages advertise results in their `<title>` ("— Kết quả,
  ảnh giải, thông tin"), but the pages we checked contain no actual finish-time data in the
  HTML - results there appear to live inside VBM's mobile app, not the public website.
- **SportStats** (`sportstats.one`) *does* host real per-race leaderboards (rank/name/time)
  for VnExpress Marathon races, with a clean URL per distance
  (`/event/<slug>/leaderboard/<id>`). But the table is a client-side skeleton that fetches
  from `/api/...` after page load, and that path is explicitly disallowed by
  `sportstats.one/robots.txt` - off-limits under this project's "never bypass
  robots.txt/anti-bot protection" rule.
- **UTMB World** (`utmb.world/utmb-index/races/...`) is the one source that's genuinely
  scrapable: `robots.txt` allows everything, and the finisher table (rank, name, country,
  time) is present in the plain server-rendered HTML - no JS execution needed. It covers the
  handful of VN trail races in the UTMB World Series/Index (Vietnam Mountain Marathon,
  Vietnam Ultra Marathon, Vietnam Trail Marathon, Vietnam Jungle Marathon, Vietnam Highlands
  Trail). The blocker is discovery, not scraping: there's no public search/listing endpoint
  to find a race's UTMB URL from its name, and the numeric race id in the URL changes every
  edition/year, so wiring this in would mean hand-maintaining a per-year id mapping that goes
  stale silently - exactly the kind of fragile, guess-based scraper this project avoids.

If a reliable, per-race-discoverable VN results source turns up later, `results` is already
in the schema and `pipeline/merge.py` already passes it through - only a new scraper/enrichment
step would be needed, no schema migration.

## News feed (running news/knowledge content)

A second, independent pipeline crawls Vietnamese-language running **news and knowledge
content** (race recaps, training tips, gear, event write-ups) - not race listings, that's
the pipeline above. It publishes:

```
https://noattoan.github.io/unified_health_service/news/latest.json
```

This is a **metadata/snippet aggregator, not a full-text republisher**: every item keeps
`sourceUrl` as the only way to read the full article, and `summary` is always a short
best-effort excerpt (never the full article body). See
`docs_research/NEWS_SOURCES_RESEARCH.md` for the source research behind this pipeline
(RSS vs. scrape decisions, sample item shapes, what was held back for v2 and why).

Top level of `news/latest.json`:

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-11T04:17:39Z",
  "sources": [
    { "name": "vnexpress", "ok": true, "count": 15, "error": null }
  ],
  "items": [ /* NewsItem objects, sorted by publishedAt, newest first */ ]
}
```

One news item:

```json
{
  "id": "vnexpress-nguoi-phu-nu-dau-tien-chay-160-km-o-nam-cuc-5142970",
  "title": "Người phụ nữ đầu tiên chạy 160 km ở Nam Cực",
  "sourceName": "vnexpress",
  "sourceUrl": "https://vnexpress.net/nguoi-phu-nu-dau-tien-chay-160-km-o-nam-cuc-5142970.html",
  "publishedAt": "2026-11-11T00:00:00Z",
  "summary": "Stephanie Case vượt qua gió mạnh và cái lạnh tới âm 35 độ C để trở thành người phụ nữ đầu tiên chạy 100 dặm (160,93 km) ở Nam Cực, với thành tích nhanh hơn kỷ lục cũ hơn 5 giờ.",
  "imageUrl": "https://i1-thethao.vnecdn.net/2026/11/10/vdv-1794297436-7271-1794298028.png?w=900&h=540&q=100&dpr=1&fit=crop&s=6NnfxrNlvZOD7QAWmYKaRw",
  "category": "event-recap"
}
```

- `category`: `race-news | training-tips | gear | event-recap` - a best-effort keyword
  heuristic (`scrapers/news_base.py:classify_category`), same spirit as the races
  pipeline's `guess_terrain()`. It isn't a precise taxonomy (an opinion piece or
  human-interest story with no matching keyword falls back to `race-news`) - acceptable
  for a snippet aggregator.
- `publishedAt`: always UTC. Sources that only publish a date (no time-of-day) are
  stamped at `T00:00:00Z` for that date.
- **Dedup is by exact `sourceUrl` match only** (`pipeline/news_main.py:dedupe_by_url`) -
  unlike the races pipeline, there's no cross-source fuzzy name matching, since a news
  article is a single page from a single publisher.
- `id` is stable across runs: `sourceName + "-" + slugify(url's last path segment)`.
- No dated snapshots (unlike `races/YYYY-MM-DD.json`) - not needed for v1.

Sources (see `docs_research/NEWS_SOURCES_RESEARCH.md` for the full writeup):

| Source | Type | What it contributes |
|---|---|---|
| [VnExpress "Thông tin chạy bộ"](https://vnexpress.net/the-thao/marathon/tin-tuc) | HTML scrape | Race announcements, training tips, gear, international running news |
| [Tuổi Trẻ Online "marathon" tag](https://tuoitre.vn/marathon.html) | HTML scrape | Race recaps/results, runner stories |
| [VNRUN](https://vnrun.com/feed/) | RSS feed | Gear reviews, training-tip articles |

## Gear catalog (runner gear reference)

A third, independent pipeline crawls a small, fixed set of running-brand storefronts' public
category listing pages and publishes a reference catalog of running shoes, apparel, and
accessories:

```
https://noattoan.github.io/unified_health_service/gear/latest.json
```

This is a **metadata + link-out catalog, never a store**: every item keeps `productUrl` as the
only way to actually buy it, all detail (description, specs, sizes, stock, gallery) comes from the
vendor's own product page and is never fabricated, and nothing here ever touches a cart/checkout/payment endpoint or
collects user data. See `docs_research/GEAR_SOURCES_RESEARCH.md` for the full source research,
schema rationale, and which sources were checked and held back (Decathlon, Nike, Adidas, Asics,
Hoka, Brooks) and why.

Top level of `gear/latest.json`:

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-12T12:36:34Z",
  "sources": [
    { "name": "puma", "ok": true, "count": 204, "error": null }
  ],
  "items": [ /* GearItem objects: shoes, then apparel, then accessories per source */ ]
}
```

One gear item:

```json
{
  "id": "puma-312587",
  "name": "Darter Pro 2 Running Shoes Unisex",
  "brand": "Puma",
  "category": "shoes",
  "sourceName": "puma",
  "priceVnd": 1360000,
  "originalPriceVnd": 1700000,
  "description": "Lightweight, responsive, and built to move, Darter Pro shoes give you the essentials...",
  "imageUrl": "https://images.puma.com/...",
  "images": ["https://images.puma.com/...", "https://images.puma.com/..."],
  "productUrl": "https://vn.puma.com/vn/en/pd/darter-pro-2-running-shoes-unisex/312587.html?color=16",
  "variants": [
    { "color": "PUMA White-Ultra Red-Silver Mist-Flat Dark Gray", "imageUrl": "https://images.puma.com/...", "productUrl": "https://vn.puma.com/...", "priceVnd": null, "images": [], "sizes": [] }
  ],
  "sizes": [ { "label": "40", "available": false }, { "label": "41", "available": true } ],
  "inStock": true,
  "gender": "unisex",
  "sku": "312587",
  "specs": { "Heel-to-toe drop": "6mm", "Cushioning": "Medium", "Pronation": "Neutral", "material": "Textile" },
  "features": ["The upper of the shoes is made with at least 30% recycled materials."],
  "detailFetchedAt": "2026-11-12T13:10:55Z",
  "crawledAt": "2026-11-12T05:09:53Z"
}
```

- `category`: `shoes | apparel | accessories`, assigned explicitly per listing URL a scraper
  targets - not a keyword guess, since every source already publishes clean, separate listing
  pages per category.
- `variants`: real per-color data where (and only where) a source genuinely exposes it - never
  fabricated. Most sources only sell one color per product page, so `variants` is correctly
  empty for most items.
- Detail fields (`description`, `images`, `originalPriceVnd`, `sizes`, `inStock`, `gender`,
  `sku`, `specs`, `features`, `detailFetchedAt`) come from one extra fetch of each item's own
  product page. They're null/empty when the source doesn't publish them. Details are cached for 7
  days via the previous `latest.json`, with at most 120 fresh product-page fetches per source per run.
- `gender`: `men | women | unisex | kids | null`, resolved in a fixed, additive priority order so the
  app can filter Nam/Nữ (schema stays optional, `schemaVersion` unchanged):
  1. **Source-provided**, preferred whenever a storefront exposes it: Puma's PDP `c_gender`;
     Salomon/Li-Ning's spec-table "Giới tính" row or `GT_Nam`/`GT_Nữ`-style Shopify/Haravan tag
     (`scrapers.gear_base.gender_from_shopify_tags`); Coolmate's PDP `gender_type`.
  2. **Per-gender listing membership**, for the two sources whose own collection structure is
     explicitly gendered (Li-Ning's `giay-chay-bo-nam-2`/`giay-chay-bo-nu-2`, Coolmate's
     `quan-ao-chay-bo-nu`): a product seen only under one such listing is tagged that gender; one
     seen under *both* a men's and a women's listing resolves to `unisex`
     (`scrapers.gear_base.resolve_listing_gender`) rather than picking one arbitrarily. This never
     gets clobbered back to null by a later PDP fetch that simply doesn't carry its own gender field.
  3. **Name/title keyword fallback** (`scrapers.gear_base.gender_from_text`, applied once centrally
     in `pipeline/gear_main.py` to whatever is still `null` after 1-2): VN/EN keywords, diacritics-
     insensitive, whole-word only - `women's`/`womens`/`wmns`/`nữ`, `men's`/`mens`/`nam`, `unisex`,
     `kids`/`trẻ em`/`junior`. A name matching both a men's and a women's keyword (e.g. "Women's &
     Men's...") resolves to `unisex`; "nam" never fires on the substring inside "Việt Nam"/"Vietnam".
  4. Otherwise `null` - never guessed blindly.
- **Dedup is by exact `productUrl` match** (`pipeline/gear_main.py:dedupe_by_url`).
- No dated snapshots (unlike `races/YYYY-MM-DD.json`) - a `latest.json`-only catalog, same
  reasoning as the news pipeline.

Sources (see `docs_research/GEAR_SOURCES_RESEARCH.md` for the full writeup):

| Source | Platform | What it contributes |
|---|---|---|
| [PUMA Vietnam](https://vn.puma.com/vn/en/sports/running/running-shoes) | Salesforce Commerce Cloud (PWA Kit) | Running shoes, apparel, accessories; real multi-color `variants` |
| [Salomon Vietnam](https://vn.salomon.com/collections/road-running-1) | Shopify (Haravan-backed reseller) | Trail/road running shoes, apparel, accessories |
| [Li-Ning Vietnam](https://lining.com.vn/collections/giay-chay-bo-2) | Haravan | Running shoes (apparel/accessories collections exist but are currently empty) |
| [Coolmate](https://www.coolmate.me/collection/quan-ao-chay-bo) | Custom Next.js storefront | Running apparel and accessories (no running shoes sold) |

## Running locally

Requires Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m pipeline.main

# News/knowledge-content pipeline (separate, independent of the races one above):
python -m pipeline.news_main

# Gear reference catalog (separate, independent of the two pipelines above):
python -m pipeline.gear_main
```

`pipeline.main` fetches all race sources live, merges/dedupes, validates with pydantic,
and writes `docs/races/latest.json` (plus a dated snapshot if anything changed). It
prints a summary of which sources succeeded/failed. If the total race count would drop
more than 50% versus the previous `latest.json`, it refuses to overwrite it and exits
non-zero instead (a safety net against publishing a broken crawl).

`pipeline.news_main` fetches all news sources live, de-dupes by URL, sorts newest
first, and writes `docs/news/latest.json`. Same safety-net philosophy: if every news
source fails in the same run, it refuses to overwrite `latest.json` with an empty feed.

`pipeline.gear_main` fetches all gear sources live, de-dupes by `productUrl`, and writes
`docs/gear/latest.json`. Same safety-net philosophy: if every gear source fails in the
same run, it refuses to overwrite `latest.json` with an empty catalog.

Run the test suite (uses saved HTML/RSS fixtures in `tests/fixtures/`, no network needed):

```bash
pytest
```

## Repo layout

```
scrapers/
  base.py          # Race/Distance/SourceRef models, polite HTTP client, VN date/price parsers
  vnexpress.py      # Tier 1
  irace.py          # Tier 1
  vbm.py            # Tier 1
  finishers.py       # Tier 2 (parses the page's __NEXT_DATA__ JSON)
  news_base.py          # NewsItem model, category classifier, id/tracking-param helpers
  vnexpress_news.py      # HTML scrape
  tuoitre_news.py        # HTML scrape
  vnrun_news.py           # RSS feed (feedparser)
  gear_base.py            # GearItem/GearVariant models, slugify/make_gear_id()
  puma_gear.py            # embedded `mobify-data` JSON, paginated
  salomon_gear.py         # Shopify /collections/<handle>/products.json
  lining_gear.py          # Haravan /collections/<handle>/products.json
  coolmate_gear.py        # embedded Next.js RSC `self.__next_f.push(...)` chunks
pipeline/
  merge.py          # normalize, dedupe, field-precedence merge (races only)
  main.py           # runs every race scraper, validates, writes docs/races/*.json
  news_main.py      # runs every news scraper, dedupes by URL, writes docs/news/latest.json
  gear_main.py      # runs every gear scraper, dedupes by productUrl, writes docs/gear/latest.json
tests/
  fixtures/         # saved HTML/RSS/JSON fixtures per source
  test_*.py
docs/
  index.html, bot.html
  races/latest.json, races/YYYY-MM-DD.json
  news/latest.json
  gear/latest.json
docs_research/
  RACE_SOURCES_RESEARCH.md
  NEWS_SOURCES_RESEARCH.md
  GEAR_SOURCES_RESEARCH.md
.github/workflows/crawl.yml
```

## Automation

`.github/workflows/crawl.yml` runs all three pipelines (`python -m pipeline.main`, then
`python -m pipeline.news_main`, then `python -m pipeline.gear_main`) daily at 03:00
Vietnam time (`0 20 * * *` UTC) and on manual `workflow_dispatch`, then commits `docs/`
under a `race-bot` git identity if anything changed. Any one pipeline can fail
independently (`continue-on-error`) without blocking the others' output from being
committed; the job itself still fails (and sends the usual GitHub Actions failure
email) if any of them did. GitHub Pages serves this repo's `main` branch, `/docs`
folder.
