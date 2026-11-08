# unified_health_service: Vietnam race crawler — research spec

Research output from an Opus agent, 2026-11-08. Live-verified via curl/robots.txt checks against
the actual sites on that date — not guessed. Anything marked **(unverified)** was not inspected.

## 1. Sources

### Tier 1: build these first (aggregators, server-rendered)

| # | Source | What it shows | Scrapability (checked) |
|---|---|---|---|
| 1 | **VnExpress "Lịch giải chạy"**, `https://vnexpress.net/the-thao/marathon/lich-giai-chay` | Name, start date (`dd/MM`, with year in a month header `<h2 class="date-month">Tháng 11 2026`), province, terrain (Road/Trail/City Trail), distances. No price. Registration link is probably on each item's detail page. | Static HTML, easy. Entries sit in clean markup: `#content-list-tournament .list-run-plan .item`, with `.month`, `.title-news p[title]`, `.location .address`, `.distance span`. robots.txt allows `/`. Page only shows ~2 months ahead. Follow-up: check whether a `month_time` filter/AJAX loads later months. |
| 2 | **iRace ticket portal**, `https://ticket.irace.vn/categories/marathon` (also homepage) | Name, date or date range, province, "Từ 450.000đ" (lowest price), registration link, "Đóng đăng ký" (closed). Main ticketing platform for Vietnamese races, including the VnExpress Marathon series. | Static HTML, easy (33 KB, all data in HTML). Paginated via "Trang kế". robots.txt is `Disallow:` (empty) — everything allowed. Best source for price/registration status. Per-distance prices on detail pages — needs follow-up check. |
| 3 | **Vietnam's Best Marathons (VBM)**, `https://bestmarathon.vn/race-info/` | Claims "600+ giải chạy". Name, date `dd/MM/yyyy`, province, distance pills (`span.pill-dist`), organizer facets. | Static WordPress output, easy but heavy (878 KB in one page). robots.txt only blocks `/wp-admin/`. Not exposed via REST API (`/wp-json/wp/v2/types` lacks a race type) — parse HTML. Widest coverage, includes past races — filter for date ≥ today. |

### Tier 2: useful extras

| # | Source | Notes |
|---|---|---|
| 4 | **Finishers**, `https://www.finishers.com/en/destinations/asia/vietnam` | Next.js page with embedded `__NEXT_DATA__` JSON — parse that, not the DOM. ~19 major/international races, exact distances, confirmed-date flag. robots.txt blocks only query-filtered `/courses?...`, not needed. |
| 5 | **84RACE**, `https://84race.com/` | Mostly virtual/online races. Static HTML, robots.txt allows all + sitemap. Low value for real races — skip in v1 or flag as "virtual". |
| 6 | **Organizer sites**: `hcmcmarathon.com`, `vietnamtrailseries.com` (WordPress, static); `ironman.com/races/im703-vietnam` (Drupal, static, 800 KB) | One race each. Only worth it for flagship events the aggregators lack detail on — aggregators already cover them, **not needed in v1**. |

### Do not scrape

- **Ahotu** (`ahotu.com`) — Cloudflare-challenges even robots.txt, effectively bot-blocked.
- **marathon.vnexpress.net** — 0 bytes / no connection via curl. Use VnExpress listing + iRace instead.
- **Facebook groups/pages** — login-walled, against ToS, unreliable.
- **Strava clubs/events** — needs login + API agreement.
- **Blog round-ups** (decathlon.vn, imsports.vn, linh.academy, thegioichaybo.vn, vietrunning.vn) — hand-written, goes stale, layout-unstable. Cross-check coverage only.
- **marathonguide.com, justrunlah.com** — thin Vietnam coverage.

**Follow-up before writing each scraper:** for iRace/VBM/VnExpress, check detail-page fields (per-distance price/status, organizer, registration URL) and pagination. Check Finishers' `__NEXT_DATA__` paths.

## 2. Legality and politeness

- Fetch and obey `robots.txt` (`urllib.robotparser`) before every host's first request; skip + log if disallowed.
- User-Agent: `UnifiedHealthRaceBot/1.0 (+https://<user>.github.io/unified_health_service/bot.html)`, with a contact page.
- Run once a day. One request at a time per host, 2-5s delay (or honor `Crawl-delay`), cap pages per source (~30). Retry w/ backoff on 429/5xx, max 2 tries, then give up for the day.
- Only fetch public pages. Never log in, never bypass Cloudflare/captchas, never touch checkout/registration POST endpoints.
- Store facts only (name, date, place, distances, price, link) — not images or article text. Always keep `sourceUrl` for attribution (both polite and legal safe harbor).

## 3. Data schema

One race entry:
```json
{
  "id": "vnexpress-marathon-hanoi-midnight-2026-11-29",
  "name": "VnExpress Marathon Hanoi Midnight 2026",
  "startDate": "2026-11-29",
  "endDate": null,
  "province": "Hà Nội",
  "location": "Hà Nội",
  "terrain": "road",
  "distances": [
    { "label": "42km", "km": 42.195, "priceVnd": 790000, "status": "open" }
  ],
  "priceFromVnd": 790000,
  "registrationStatus": "open",
  "organizer": null,
  "registrationUrl": "https://ticket.irace.vn/...",
  "imageUrl": null,
  "sources": [
    { "name": "irace", "url": "https://ticket.irace.vn/...", "lastSeenAt": "2026-11-08T23:05:00Z" }
  ],
  "firstSeenAt": "2026-10-01T23:05:00Z",
  "lastUpdatedAt": "2026-11-08T23:05:00Z"
}
```
- `terrain`: `road | trail | city_trail | ultra | triathlon | virtual`.
- `status`/`registrationStatus`: `open | closed | sold_out | unknown`.

**Stable id:** `slugify(name with year/sponsor words removed) + "-" + startDate`. Strip accents (`unidecode`), drop words like "giải chạy"/"powered by"/years. Dedupe by (normalized name, startDate, province), fuzzy fallback (`rapidfuzz` ratio ≥ 90, same date). On merge: combine `sources[]`, take each field from the source that owns it (iRace → price/status, VBM/VnExpress → distances/terrain).

Top level (`docs/races/latest.json`):
```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-08T23:05:00Z",
  "sources": [ { "name": "irace", "ok": true, "count": 9, "error": null } ],
  "races": [ /* sorted by startDate, only startDate >= today-1 */ ]
}
```
Per-source `ok`/`count` lets the app or maintainer spot a broken scraper.

## 4. Architecture

**Stack:** Python 3.12 + `httpx` + `selectolax` (or `beautifulsoup4`+`lxml`) + `python-dateutil`/custom VN date parsing + `unidecode` + `rapidfuzz` + `pydantic` for schema validation. Installs in ~10s on Actions vs ~1min for Playwright+browser. **No Playwright needed** — every Tier 1/2 source checked is server-rendered or embeds JSON.

Repo layout:
```
scrapers/
  base.py          # Race model, polite HTTP client (UA, robots, delay), VN date/price parsers
  vnexpress.py     # def scrape(client) -> list[Race]
  irace.py
  vbm.py
  finishers.py
pipeline/
  merge.py         # normalize, dedupe, field precedence
  main.py          # run each scraper in try/except, validate, write outputs
tests/fixtures/    # saved HTML per source + parser tests (catch layout drift offline)
docs/
  races/latest.json
  races/2026-11-08.json
  index.html, bot.html
.github/workflows/crawl.yml
```

Safety rules in `main.py`:
- One source failing never fails the whole run — mark `ok:false`, carry over that source's races from the previous `latest.json`.
- If total race count drops >50% vs yesterday, don't overwrite `latest.json`, exit non-zero (triggers GitHub's failure email).

Workflow (`crawl.yml`):
```yaml
on:
  schedule: [{ cron: "0 20 * * *" }]   # 03:00 Vietnam time
  workflow_dispatch: {}
permissions: { contents: write }
concurrency: { group: crawl, cancel-in-progress: false }
jobs:
  crawl:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r requirements.txt
      - run: python -m pipeline.main
      - run: |
          git config user.name "race-bot"; git config user.email "race-bot@users.noreply.github.com"
          git add docs/
          git diff --cached --quiet || (git commit -m "races: $(date -u +%F)" && git push)
```
Pages deploys from `main` `/docs`. App fetches `https://<user>.github.io/unified_health_service/races/latest.json`.

Note: GitHub disables scheduled workflows after 60 days of repo inactivity. The daily commit keeps it active, but only on days data changes — may need a periodic no-op nudge if data is ever fully static for 60+ days.

**Snapshots: yes, keep dated files.** Write `docs/races/YYYY-MM-DD.json` only when content changed; delete files older than 90 days in `main.py`. Exclude `generatedAt`/`lastSeenAt` when diffing for "did anything change" (otherwise a commit every day regardless).

## Sources checked
- https://vnexpress.net/the-thao/marathon/lich-giai-chay
- https://ticket.irace.vn/categories/marathon
- https://bestmarathon.vn/race-info/
- https://www.finishers.com/en/destinations/asia/vietnam
- https://www.ahotu.com/calendar/running/vietnam
- https://84race.com/
- https://www.ironman.com/races/im703-vietnam
- https://www.vietnamtrailseries.com/
- https://hcmcmarathon.com/
- https://www.decathlon.vn/blog/giai-chay-2026/
