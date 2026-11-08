from __future__ import annotations

from scrapers.base import (
    guess_terrain,
    label_to_km,
    make_id,
    normalize_name_for_id,
    parse_dd_mm,
    parse_dd_mm_yyyy,
    parse_vn_month_header,
    parse_vnd_price,
    slugify,
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
