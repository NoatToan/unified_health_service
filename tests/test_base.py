from __future__ import annotations

from datetime import date

from scrapers.base import (
    DistanceResult,
    Race,
    SourceRef,
    TopFinisher,
    compute_race_status,
    extract_description,
    extract_og_image,
    guess_terrain,
    is_probable_detail_url,
    label_to_km,
    looks_like_trail,
    make_id,
    normalize_name_for_id,
    parse_dd_mm,
    parse_dd_mm_yyyy,
    parse_vn_month_header,
    parse_vnd_price,
    slugify,
    truncate_text,
)


def test_parse_vn_month_header():
    assert parse_vn_month_header("Tháng\n11 2026 ") == (11, 2026)
    assert parse_vn_month_header("Tháng 12 2026") == (12, 2026)
    assert parse_vn_month_header("garbage") is None


def test_parse_dd_mm():
    assert parse_dd_mm("08/11 ", 2026).isoformat() == "2026-11-08"
    assert parse_dd_mm("not a date", 2026) is None


def test_parse_dd_mm_yyyy():
    assert parse_dd_mm_yyyy("15/11/2026").isoformat() == "2026-11-15"
    assert parse_dd_mm_yyyy("31/02/2026") is None  # invalid calendar date


def test_parse_vnd_price():
    assert parse_vnd_price("450.000đ") == 450_000
    assert parse_vnd_price("Từ 450.000đ") == 450_000
    assert parse_vnd_price("Đóng đăng ký") is None


def test_label_to_km_uses_official_distances():
    assert label_to_km("42km") == 42.195
    assert label_to_km("21KM") == 21.0975
    assert label_to_km("10km") == 10.0
    assert label_to_km("no digits") is None


def test_slugify_strips_accents_and_punctuation():
    assert slugify("Cà Mau Marathon!") == "ca-mau-marathon"


def test_normalize_name_for_id_strips_year_and_boilerplate():
    normalized = normalize_name_for_id("Giải chạy Cà Mau Marathon 2026")
    assert "2026" not in normalized
    assert normalized == "ca-mau-marathon"


def test_make_id_combines_name_and_date():
    assert make_id("Cà Mau Marathon", "2026-11-15") == "ca-mau-marathon-2026-11-15"


def test_guess_terrain_from_explicit_label():
    assert guess_terrain("Some Race", explicit="Road") == "road"
    assert guess_terrain("Some Race", explicit="City Trail") == "city_trail"


def test_guess_terrain_from_name_fallback():
    assert guess_terrain("Ultra Trail Cao Bang") == "ultra"
    assert guess_terrain("Vung Tau City Trail") == "city_trail"
    assert guess_terrain("Some Random 10km Run") == "road"


def test_guess_terrain_detects_jungle_and_mountain_keywords_in_name():
    assert guess_terrain("Cuc Phuong Jungle Paths") == "trail"
    assert guess_terrain("Ultra Trail Cao Bang - Mountain Edition") == "ultra"  # "ultra" still wins
    assert guess_terrain("Da Lat Forest Challenge") == "trail"


def test_guess_terrain_uses_vietnamese_keywords_in_name():
    assert guess_terrain("Giai Chay Xuyen Rung Sau Cao Bang") == "trail"


def test_guess_terrain_falls_back_to_description_when_name_gives_no_hint():
    assert guess_terrain("Legacy Marathon 2026", description="Chạy xuyên rừng sâu và núi cao.") == "trail"
    assert guess_terrain("Legacy Marathon 2026", description="Giải chạy đường phố trung tâm thành phố.") == "road"


def test_guess_terrain_explicit_label_wins_over_keywords():
    # An explicit "Road" label should win even if the name sounds trail-ish.
    assert guess_terrain("Some Jungle Race", explicit="Road") == "road"


def test_looks_like_trail():
    assert looks_like_trail("chay xuyen rung, nui cao") is True
    assert looks_like_trail("off-road adventure run") is True
    assert looks_like_trail("Marathon duong pho") is False


# --------------------------------------------------------------------------- #
# Detail-page enrichment helpers
# --------------------------------------------------------------------------- #

def test_extract_og_image_finds_meta_tag_regardless_of_attribute_order():
    html = """
    <html><head>
      <meta content="https://example.com/banner.jpg" property="og:image">
    </head><body></body></html>
    """
    assert extract_og_image(html) == "https://example.com/banner.jpg"


def test_extract_og_image_falls_back_to_twitter_image():
    html = '<html><head><meta property="twitter:image" content="https://example.com/t.jpg"></head></html>'
    assert extract_og_image(html) == "https://example.com/t.jpg"


def test_extract_og_image_returns_none_when_absent():
    assert extract_og_image("<html><head></head><body>no image here</body></html>") is None


def test_extract_description_prefers_og_description_meta():
    html = """
    <html><head>
      <meta property="og:description" content="Giải chạy ven biển với 4 cự ly, xuất phát sớm, nhiều cảnh đẹp.">
    </head><body><p>Some other unrelated paragraph that is long enough to pass the length check too.</p></body></html>
    """
    desc = extract_description(html)
    assert desc == "Giải chạy ven biển với 4 cự ly, xuất phát sớm, nhiều cảnh đẹp."


def test_extract_description_falls_back_to_first_substantial_paragraph():
    html = """
    <html><body>
      <p>Hi</p>
      <p>Giải chạy bộ thường niên tổ chức tại trung tâm thành phố, thu hút hàng nghìn vận động viên tham gia.</p>
    </body></html>
    """
    desc = extract_description(html)
    assert desc is not None
    assert desc.startswith("Giải chạy bộ thường niên")


def test_extract_description_returns_none_when_nothing_reasonable():
    html = "<html><body><p>Hi</p><p>Ok</p></body></html>"
    assert extract_description(html) is None


def test_extract_description_truncates_long_text():
    long_text = "Đây là một đoạn mô tả rất dài. " * 30
    html = f"<html><body><p>{long_text}</p></body></html>"
    desc = extract_description(html, max_length=100)
    assert desc is not None
    assert len(desc) <= 101  # allow for the trailing ellipsis character
    assert desc.endswith("…") or desc.endswith(".")


def test_truncate_text_keeps_short_text_unchanged():
    assert truncate_text("short text") == "short text"


def test_is_probable_detail_url():
    assert is_probable_detail_url("https://ticket.irace.vn/some-race-2026") is True
    assert is_probable_detail_url("https://example.com/cart") is False
    assert is_probable_detail_url("https://example.com/checkout?x=1") is False
    assert is_probable_detail_url(None) is False
    assert is_probable_detail_url("") is False


def test_compute_race_status_past_vs_upcoming():
    run_date = date(2026, 11, 8)
    assert compute_race_status("2026-11-07", run_date) == "past"
    assert compute_race_status("2026-11-08", run_date) == "upcoming"
    assert compute_race_status("2026-11-09", run_date) == "upcoming"


def test_compute_race_status_defaults_to_upcoming_on_bad_date():
    assert compute_race_status("not-a-date", date(2026, 11, 8)) == "upcoming"


def test_race_defaults_results_to_none():
    race = Race(
        id="x",
        name="X",
        startDate="2026-11-15",
        sources=[SourceRef(name="vbm", url="https://example.com", lastSeenAt="2026-11-08T00:00:00Z")],
        firstSeenAt="2026-11-08T00:00:00Z",
        lastUpdatedAt="2026-11-08T00:00:00Z",
    )
    assert race.results is None
    assert race.raceStatus == "upcoming"


def test_race_accepts_results_payload():
    race = Race(
        id="x",
        name="X",
        startDate="2026-11-01",
        results=[
            DistanceResult(
                distance="42km",
                topFinishers=[TopFinisher(rank=1, name="Nguyen Van A", timeSeconds=9240)],
            )
        ],
        sources=[SourceRef(name="vbm", url="https://example.com", lastSeenAt="2026-11-08T00:00:00Z")],
        firstSeenAt="2026-11-08T00:00:00Z",
        lastUpdatedAt="2026-11-08T00:00:00Z",
    )
    assert race.results[0].distance == "42km"
    assert race.results[0].topFinishers[0].name == "Nguyen Van A"
