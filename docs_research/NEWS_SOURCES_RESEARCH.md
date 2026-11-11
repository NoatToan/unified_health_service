# unified_health_service: Vietnam running news/knowledge crawler — research spec

Research output from a Claude agent, 2026-11-11. Live-verified via `curl`/`robots.txt` checks and
direct feed fetches against the actual sites on that date — not guessed. Anything marked
**(unverified)** was not inspected. Mirrors the structure of `RACE_SOURCES_RESEARCH.md`, but for
**news and knowledge content** (articles, training tips, race recaps, gear) rather than race
listings — a different, more legally-sensitive kind of content (see §2).

## 1. Sources

### Ship in v1

| # | Source | Type | What it shows | Scrapability (checked) |
|---|---|---|---|---|
| 1 | **VnExpress "Thông tin chạy bộ"**, `https://vnexpress.net/the-thao/marathon/tin-tuc` | HTML scrape | VnExpress's own dedicated running-news vertical: race announcements, training tips, gear, injury/health pieces, international running news — 15 items per page. | Static server-rendered HTML, same `article.item-news` family of markup the races crawler already parses elsewhere on this site (`h2.title-news a`, `p.description`, `.thumb-art img`). `robots.txt`: `User-agent: * / Allow: /` with only specific scraper bots (Scrapy, AmazonBot, Archive.org_bot, …) blocked — our custom UA isn't one of them. **Caveat**: the listing only publishes a `dd/MM` date, no year/time — year is inferred (`vnexpress_news.py:_resolve_year`, "previous year if parsed month > today's month", correct except exactly at a Dec→Jan boundary which it also handles), and `publishedAt` is stamped at `T00:00:00Z` for that date (no time-of-day available one page deep). |
| 2 | **Tuổi Trẻ Online "marathon" tag**, `https://tuoitre.vn/marathon.html` | HTML scrape | A national newspaper's tag page for marathon-related stories: results/recaps, runner profiles, incident reports, race announcements — 10 items per page. | Static server-rendered HTML, clean `article.box-category-item` markup with a **full absolute timestamp** in `span.box-category-time[title]` (`M/D/YYYY h:mm:ss AM/PM`, Vietnam local time) — better date precision than VnExpress's listing. `robots.txt`: `Allow: /`, only disallows `/tim-kiem.htm` (search), `/print/`, login/video-signal JS, `/ImageView.aspx`, `/ajax-box-mua-sam/` — none of which this page touches. |
| 3 | **VNRUN**, `https://vnrun.com/feed/` | **RSS feed** | A Vietnamese running-community media outlet: gear reviews ("Top đồng hồ chạy bộ…", shoe brand deep-dives) and training-tip articles. | Real RSS 2.0 (`application/rss+xml`), standard WordPress `/feed/`. `robots.txt`: `Disallow: /wp-admin/` only (with `admin-ajax.php` explicitly re-allowed) — `/feed/` itself is unrestricted. `<description>` is WordPress's own auto-excerpt (already truncated with "…") — `content:encoded` (the full post body) is parsed only to pull the post's first `<img>` for `imageUrl`, never for text. **Caveat**: most recent item at check time was from March 2026 (~8 months stale) — the feed is real and correctly formatted, just low-frequency; included anyway for its gear/training-tip angle that the two newspaper sources don't cover as well, and de-dup-by-URL means a quiet feed just contributes fewer items, never breaks anything. |

### Checked and held back for v2

| # | Source | Why held back |
|---|---|---|
| 4 | **Chay365** (`chay365.com`) — the most established Vietnamese running-community site (10 years, ~81k FB followers), genuinely excellent editorial content (training, nutrition, injuries, gear). | **(verified)** WordPress site but its own `/feed/`, `/feed`, `/?feed=rss2` and a category feed all return `404` — the WP feed appears disabled (common anti-scraping/security hardening). Homepage HTML is heavy Thrive-Themes page-builder markup: post blocks repeat with per-post inline `<style>` blocks for responsive background-images, and dates/categories aren't in a clean, stable location one page deep. Scrapable in principle but meaningfully more fragile than the three v1 sources — holding back for a v2 pass that budgets time for a dedicated-detail-page scrape instead of the noisy homepage. |
| 5 | **Thanh Niên** (`thanhnien.vn`) | **(verified)** Has a general `rss/the-thao.rss` (sports) feed, but no dedicated marathon/running tag page was found (`/marathon.htm` 301-redirects elsewhere) and `/tim-kiem.htm` (search) is explicitly disallowed by `robots.txt`, so there's no clean way to get a running-specific slice without heavy keyword-filtering the general sports feed (mostly football) — low signal-to-noise for v1. |
| 6 | **Tuổi Trẻ general sports feed** (`tuoitre.vn/rss/the-thao.rss`) | **(verified)** Valid RSS, but same problem as Thanh Niên's — general sports, mostly football, would need keyword filtering. Redundant with and lower-precision than source #2 (the dedicated marathon tag page), which is already a clean superset of the running content this feed would otherwise surface. Not shipped. |
| 7 | **VnExpress general sports feed** (`vnexpress.net/rss/the-thao.rss`) | **(verified)** Same reasoning as #6 — general sports RSS, mostly football/other sports with running content appearing only occasionally; source #1 (the dedicated running vertical) is already the clean, on-topic version of this. Not shipped. |
| 8 | **PhongTraoChayBo** (`phongtraochaybo.vn`) — "running movement" news aggregator, exactly on-topic by name/description. | **(verified)** `robots.txt` request returns the SPA's own `index.html` (Angular, `ng-app="App"`) instead of an actual robots.txt file — content is rendered client-side, so a plain HTTP fetch sees no article markup at all. Out of scope for v1 under this project's "no JS execution" rule (same rule that excluded SportStats for race results in the races crawler). |
| 9 | **Thế Giới Chạy Bộ blog** (`www.thegioichaybo.vn/blogs/giai-chay`) | **(verified)** `robots.txt` (`# we use Haravan as our ecommerce platform`) allows `/blogs/`, so technically scrapable — but it's a gear retailer's own blog (Haravan e-commerce platform), i.e. promotional/commerce-affiliated content, and redundant with VNRUN for the gear angle. Held back rather than adding a second, less editorially-independent gear source in v1. |
| 10 | **Mê Chạy Bộ** (`mechaybo.com.vn`) | **(verified)** `robots.txt` uses the new IETF "Content-Signal" TDM-opt-out format rather than classic `Disallow` rules — ambiguous enough to warrant a human legal read before crawling (see §6, "needs a human call"). Also, on inspection this is primarily a virtual-race/registration platform (medals, Strava sync), not an editorial news/knowledge site — low relevance to this task's "news and knowledge content" scope even if crawling were greenlit. Skipped, not just held back. |
| 11 | **Biji Vietnam** (`vn.running.biji.co`) | **(unverified)** — a sports-tracking app's content hub; not inspected this round given time budget and that v1 already has 3 solid sources. Candidate for a future pass. |

### Do not scrape

- **Facebook groups/pages** (various running communities) — login-walled, against ToS, unreliable (same exclusion as the races research doc).
- Anything requiring JS execution/client-side rendering to see article content (PhongTraoChayBo, above) — this project doesn't run a browser, by design (fast, cheap CI, same reasoning as "no Playwright" in the races pipeline).

## 2. Legality and politeness

This is new, more legally-sensitive territory than the race-listings crawler: race listings are
largely factual/structured data (name, date, place), while this pipeline touches **editorial
content** (articles, journalism, community blog posts). The schema (§3) is deliberately scoped as a
**metadata/snippet aggregator, never a full-text republisher** to stay on the right side of that line:

- Store **title, source name, source URL, publish date, a short best-effort snippet, an image URL,
  and a category tag** — never the full article body. `sourceUrl` is always present and is the only
  way to read the full article; this is both the polite and the legally-safer pattern (same
  `sourceUrl`-always-kept rule the races crawler already follows).
- RSS/Atom feeds (VNRUN) are treated as implicitly fine for headline+snippet+link aggregation — a
  publisher that exposes a feed has made that content available for exactly this kind of use. Even
  so, feeds are still fetched through the same rate-limited, robots.txt-respecting `PoliteClient` as
  everything else — no special-casing that skips politeness, only a different parser (`feedparser`
  instead of CSS selectors).
- Sources with no feed are scraped **one page deep only** (a single listing page, never pagination
  or per-article detail pages) — a deliberately narrower rule than the races crawler, which does
  fetch one detail page per race for image/description enrichment. News articles are the content
  itself (not a ticket/registration flow), so going no deeper than the listing's own excerpt is the
  more conservative choice here.
- Same `robots.txt` check (`urllib.robotparser`, once per host, before the first request), same
  `UnifiedHealthRaceBot/1.0` User-Agent (the existing bot identity — see note below), same
  `REQUEST_DELAY_SECONDS` (2.5s) per-host rate limit and retry-once-on-429/5xx policy, reused as-is
  from `scrapers/base.py:PoliteClient` — no parallel HTTP stack.
- **Note on User-Agent naming**: the shared `PoliteClient`'s UA string is `UnifiedHealthRaceBot/1.0`,
  named for the already-live races pipeline. This crawler reuses it rather than introducing a second
  bot identity, since renaming a UA string that real sites have already seen in their logs under the
  races pipeline (already in production) would not be purely additive. `docs/bot.html` — the page
  that UA string points to — has been updated to disclose the news pipeline too, so the bot's public
  policy page stays accurate even though its name is race-flavored. Worth revisiting (a neutral
  `UnifiedHealthBot/1.0` name) in a future pass that doesn't need to stay additive to a live system.
- Skipped per source: PhongTraoChayBo (JS-rendered, can't tell from a plain fetch what it even
  shows), Chay365's actual `/feed/` paths (404 — feed is disabled) are the only "disallowed" results
  encountered; nothing was skipped specifically because `robots.txt` disallowed it (unlike the races
  research, which excluded Ahotu and SportStats on exactly that basis) — the three v1 sources' and
  held-back sources' `robots.txt` files were all permissive for the paths this pipeline touches.

## 3. Data schema

Field names and conventions deliberately mirror `docs/races/latest.json`'s style (camelCase,
`schemaVersion`/`generatedAt`/`sources[]` wrapper, UTC `...Z` timestamps, `id`/`sourceUrl` naming) for
consistency across the two feeds this repo now publishes.

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

- `id`: stable across runs — `sourceName + "-" + slugify(url's last path segment, extension/query
  stripped)`. Deterministic from the URL alone, so it survives a source tweaking a title slightly on
  re-publish.
- `sourceUrl`: the canonical article URL, with tracking query params (`utm_*`, `fbclid`, `gclid`)
  stripped (`scrapers/news_base.py:strip_tracking_params`) — needed in practice because VNRUN's own
  WordPress RSS plugin appends `utm_source=rss&utm_medium=rss&...` to every link.
- `publishedAt`: always UTC `YYYY-MM-DDTHH:MM:SSZ`. Sources with a full local timestamp (Tuổi Trẻ,
  VNRUN) convert properly; VnExpress's listing only has a `dd/MM` date, so it's stamped at
  `T00:00:00Z` for that date (documented limitation, not a bug — see §1).
- `summary`: optional, short (truncated via the same `truncate_text()` helper the races crawler
  already uses for its `description` field — cuts at a sentence/word boundary, adds "…"). Never the
  full article body: for VnExpress/Tuổi Trẻ it's the listing page's own blurb; for VNRUN it's
  WordPress's own auto-excerpt (already truncated at source) with the auto-appended "The post … first
  appeared on VNRUN." boilerplate stripped and HTML entities unescaped.
- `imageUrl`: optional. Listing-page thumbnail for the two HTML-scraped sources; for VNRUN, the first
  `<img>` found in `content:encoded` (the image is fine to reference — it's a URL, not republished
  content — even though the surrounding full-text body is not used for anything else).
- `category`: `race-news | training-tips | gear | event-recap` — see §5.

Top level (`docs/news/latest.json`):

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-11T04:17:39Z",
  "sources": [
    { "name": "vnexpress", "ok": true, "count": 15, "error": null },
    { "name": "tuoitre", "ok": true, "count": 10, "error": null },
    { "name": "vnrun", "ok": true, "count": 10, "error": null }
  ],
  "items": [ /* sorted by publishedAt, newest first */ ]
}
```

Per-source `ok`/`count` mirrors the races schema exactly, same purpose (spot a broken scraper).

**Dedup**: exact match on `sourceUrl` only (`pipeline/news_main.py:dedupe_by_url`) — simpler than the
races pipeline's fuzzy name+date matching, because a news article is inherently a single page from a
single publisher (no cross-source "same event, different name" problem to solve).

## 4. Architecture

Fully additive to the existing repo — no changes to any races-pipeline file's logic:

```
scrapers/
  news_base.py        # NewsItem model, classify_category(), make_news_id(), strip_tracking_params()
  vnexpress_news.py    # HTML scrape
  tuoitre_news.py       # HTML scrape
  vnrun_news.py          # RSS feed (feedparser)
pipeline/
  news_main.py         # runs every news scraper, dedupes by URL, writes docs/news/*.json
tests/
  fixtures/news_*       # saved HTML/RSS fixtures per source
  test_news_*.py
docs/
  news/latest.json
```

New dependency: `feedparser==6.0.14` (pure Python, no C extensions, ~10ms parse time) added to the
shared `requirements.txt` — everything else (`httpx`, `selectolax`, `pydantic`, `unidecode`) is
reused from the races pipeline's existing stack.

**Workflow**: extended the existing `.github/workflows/crawl.yml` with a second step
(`python -m pipeline.news_main`) rather than adding a second workflow file. Reasoning: both pipelines
want the same daily cadence, the same `pip install -r requirements.txt` (one shared
`requirements.txt` already covers both), and the same "commit `docs/` once if anything changed"
step — a second workflow file would just duplicate all of that for no benefit. Each pipeline step
uses `continue-on-error: true` so one pipeline's failure doesn't block the other's output from being
committed; a final step inspects both steps' outcomes and fails the job (triggering the normal GitHub
Actions failure email) if either one failed, so failures are still visible.

**Safety rule**, same spirit as the races pipeline: if every news source fails in the same run
(zero items total) while a previous run had items, `pipeline.news_main` refuses to overwrite
`latest.json` and exits non-zero, rather than silently publishing an empty feed.

No dated snapshots (unlike `races/YYYY-MM-DD.json`) — the news feed is fast-moving and a snapshot
history isn't a requirement for v1; easy to add later if the Android app ever wants a "what's new
since yesterday" view.

## 5. Category classification

`scrapers/news_base.py:classify_category(title, extra_text)` — a keyword heuristic on
accent-stripped, lowercased text, checked in priority order: `gear` → `training-tips` →
`event-recap` → default `race-news`. Same spirit as the races pipeline's `guess_terrain()`.

Known limitation (acceptable for a best-effort metadata field, documented rather than "fixed" with
more keyword surgery): the word "kỷ lục" ("record") is ambiguous between a retrospective sense
("broke a record" → correctly `event-recap`) and a prospective one ("expected to draw a
record-breaking number of entrants" → a race announcement, but still matches the same keyword and
gets mis-tagged `event-recap`). Observed once in the live verification run (§8) on a VnExpress
"giải khởi động" announcement. Not worth a bigger NLP investment for a best-effort tag on a snippet
aggregator; flagged here for visibility.

## 6. Needs a human call before this goes live

- **Mê Chạy Bộ's `robots.txt`** uses the IETF "Content-Signal" TDM-opt-out draft format rather than
  classic `Disallow` rules. This wasn't crawled (see §1, held back), but if it's ever revisited, its
  legal meaning for a non-AI-training aggregation use case like this one is genuinely ambiguous and
  worth a non-engineering read before acting on it either way.
- **VNRUN's content staleness** (~8 months since its last post at check time) is disclosed above as
  a known characteristic, not a bug — worth confirming this is an acceptable inclusion given it may
  contribute very little/nothing on most days, versus holding it back entirely until it's confirmed
  still an active, maintained publication.
- **The shared bot identity still being named `UnifiedHealthRaceBot`** for a pipeline that now also
  crawls news (see §2) — fine for now (and avoids touching a live system's UA string), but a rename
  to something brand-neutral is worth scheduling once both pipelines are stable, rather than carrying
  a slightly-misleading name indefinitely.

## Sources checked

- https://vnexpress.net/the-thao/marathon/tin-tuc
- https://vnexpress.net/rss/the-thao.rss
- https://vnexpress.net/robots.txt
- https://tuoitre.vn/marathon.html
- https://tuoitre.vn/rss/the-thao.rss
- https://tuoitre.vn/robots.txt
- https://thanhnien.vn/rss/the-thao.rss
- https://thanhnien.vn/robots.txt
- https://chay365.com/ (+ /feed/, /feed, /?feed=rss2, /category/.../feed/, /robots.txt)
- https://vnrun.com/feed/
- https://vnrun.com/robots.txt
- https://phongtraochaybo.vn/robots.txt
- https://www.thegioichaybo.vn/blogs/giai-chay (+ /robots.txt)
- https://mechaybo.com.vn/robots.txt (+ /feed/)
