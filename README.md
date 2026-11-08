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

- **iRace** wins for `priceFromVnd`, `registrationStatus`, `registrationUrl`.
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

## Running locally

Requires Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m pipeline.main
```

This fetches all sources live, merges/dedupes, validates with pydantic, and writes
`docs/races/latest.json` (plus a dated snapshot if anything changed). It prints a
summary of which sources succeeded/failed. If the total race count would drop more
than 50% versus the previous `latest.json`, it refuses to overwrite it and exits
non-zero instead (a safety net against publishing a broken crawl).

Run the test suite (uses saved HTML fixtures in `tests/fixtures/`, no network needed):

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
pipeline/
  merge.py          # normalize, dedupe, field-precedence merge
  main.py           # runs every scraper, validates, writes docs/races/*.json
tests/
  fixtures/         # saved HTML/JSON per source
  test_*.py
docs/
  index.html, bot.html
  races/latest.json, races/YYYY-MM-DD.json
.github/workflows/crawl.yml
```

## Automation

`.github/workflows/crawl.yml` runs `python -m pipeline.main` daily at 03:00 Vietnam
time (`0 20 * * *` UTC) and on manual `workflow_dispatch`, then commits `docs/` under
a `race-bot` git identity if anything changed. GitHub Pages serves this repo's `main`
branch, `/docs` folder.
