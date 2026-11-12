from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scrapers.gear_base import (
    GearItem,
    apply_cached_detail,
    clean_description,
    common_variant_sku_prefix,
    cut_before_care_section,
    drop_boilerplate_specs,
    extract_bullet_facts,
    extract_code_from_title,
    extract_description_candidate,
    extract_line_specs,
    extract_table_pairs,
    gender_from_shopify_tags,
    normalize_gender,
    parse_shopify_decimal_price,
    should_reuse_cached_detail,
    split_label_value,
    strip_html_text,
)


def test_normalize_gender_maps_vietnamese_and_english_labels():
    assert normalize_gender("Nam") == "men"
    assert normalize_gender("Nữ") == "women"
    assert normalize_gender("MALE") == "men"
    assert normalize_gender("Female") == "women"
    assert normalize_gender("Unisex") == "unisex"
    assert normalize_gender("Kids") == "kids"
    assert normalize_gender(None) is None
    assert normalize_gender("") is None
    assert normalize_gender("Blue") is None


def test_strip_html_text_removes_tags_without_gluing_words():
    html = "<p>Hello<strong>World</strong></p><p>Second</p>"
    assert strip_html_text(html) == "Hello World Second"


def test_extract_table_pairs_reads_two_column_rows():
    html = (
        "<table><tr><td>Trọng lượng</td><td>265g</td></tr>"
        "<tr><td>Màu</td><td>Grey</td></tr>"
        "<tr><td>OnlyOneCell</td></tr></table>"
    )
    pairs = extract_table_pairs(html)
    assert pairs == {"Trọng lượng": "265g", "Màu": "Grey"}


def test_split_label_value_rejects_long_prose_with_a_colon():
    assert split_label_value("Độ dốc: 11 mm") == ("Độ dốc", "11 mm")
    assert split_label_value("no colon here") is None
    long_prose = "This is a very long sentence that happens to contain: a colon in it"
    assert split_label_value(long_prose) is None


def test_extract_bullet_facts_splits_specs_from_features():
    html = (
        "<ul><li>Chất liệu vải : Vải + TPU</li>"
        "<li>Main compartment</li></ul>"
    )
    specs, features = extract_bullet_facts(html)
    assert specs == {"Chất liệu vải": "Vải + TPU"}
    assert features == ["Main compartment"]


def test_extract_line_specs_reads_br_separated_label_value_lines():
    html = (
        '<p>Chiều dài lưng (cm): 44<br style="color:red">'
        "Thể tích (lít): 12<br>Không có dấu hai chấm ở đây</p>"
    )
    specs = extract_line_specs(html)
    assert specs == {"Chiều dài lưng (cm)": "44", "Thể tích (lít)": "12"}


def test_cut_before_care_section_drops_trailing_care_instructions():
    html = "<ul><li>Real fact</li></ul><h4>Hướng dẫn bảo quản</h4><ul><li>Wash cold</li></ul>"
    cut = cut_before_care_section(html)
    assert "Real fact" in cut
    assert "Wash cold" not in cut


def test_cut_before_care_section_is_a_no_op_without_the_marker():
    html = "<p>No care section here</p>"
    assert cut_before_care_section(html) == html


def test_drop_boilerplate_specs_removes_importer_rows_only():
    specs = {
        "Trọng lượng": "265g",
        "Nhà nhập khẩu và phân phối": "ANTA SPORTS VIỆT NAM CO.,LTD",
        "Địa chỉ": "Some address",
        "Nhà sản xuất": "Amer Sports",
    }
    assert drop_boilerplate_specs(specs) == {"Trọng lượng": "265g"}


def test_extract_description_candidate_drops_headings_tables_and_lists():
    html = (
        "<h4>Product Title</h4><p>Real intro sentence.</p>"
        "<table><tr><td>Weight</td><td>265g</td></tr></table>"
        "<ul><li>Feature one</li></ul>"
    )
    candidate = extract_description_candidate(html)
    assert candidate == "Real intro sentence."


def test_clean_description_trims_duplicate_leading_name_and_truncates():
    name = "Everyday Running Waist Bag"
    text = f"{name} - a great bag for running with plenty of pockets."
    cleaned = clean_description(text, name)
    assert cleaned is not None
    assert not cleaned.lower().startswith(name.lower())
    assert clean_description("   ", name) is None
    assert clean_description(None, name) is None


def test_gender_from_shopify_tags_prefers_explicit_gt_prefix():
    assert gender_from_shopify_tags("2026,GIAY,GT_Nữ,NV1111") == "women"
    assert gender_from_shopify_tags("Salomon,Running,Giày Nam,Trail Running Nam") == "men"
    assert gender_from_shopify_tags(None) is None
    assert gender_from_shopify_tags("Salomon,Running,2024") is None


def test_extract_code_from_title_picks_last_digit_bearing_caps_token():
    assert extract_code_from_title("Giày chạy bộ Super Light 23 Nam ARBW017-17V") == "ARBW017-17V"
    assert (
        extract_code_from_title("Giày Chạy Thể Thao Nam Salomon Alphacross 5 L47313300 Grey")
        == "L47313300"
    )
    assert extract_code_from_title("No code here at all") is None


def test_common_variant_sku_prefix_trims_trailing_size_suffix():
    skus = ["ARBW017-17V6.5", "ARBW017-17V7", "ARBW017-17V7.5"]
    assert common_variant_sku_prefix(skus) == "ARBW017-17V"
    assert common_variant_sku_prefix([]) is None
    assert common_variant_sku_prefix([None, ""]) is None


def test_parse_shopify_decimal_price_rounds_decimal_strings():
    assert parse_shopify_decimal_price("1600000.00") == 1600000
    assert parse_shopify_decimal_price(None) is None
    assert parse_shopify_decimal_price("not a number") is None


def _fresh_timestamp(days_ago: float) -> str:
    moment = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_should_reuse_cached_detail_honors_the_max_age_window():
    assert should_reuse_cached_detail(None) is False
    assert should_reuse_cached_detail({}) is False
    assert should_reuse_cached_detail({"detailFetchedAt": _fresh_timestamp(1)}) is True
    assert should_reuse_cached_detail({"detailFetchedAt": _fresh_timestamp(10)}) is False
    assert should_reuse_cached_detail({"detailFetchedAt": "not-a-date"}) is False


def test_apply_cached_detail_overlays_only_detail_fields():
    item = GearItem(
        id="x-1",
        name="Fresh Name",
        brand="Brand",
        category="shoes",
        sourceName="x",
        priceVnd=100,
        productUrl="https://example.com/p",
        crawledAt="2026-11-12T00:00:00Z",
    )
    previous_raw = {
        "description": "Cached description.",
        "sku": "CODE-1",
        "gender": "men",
        "specs": {"material": "Mesh"},
        "features": ["Breathable"],
        "detailFetchedAt": "2026-11-05T00:00:00Z",
    }

    merged = apply_cached_detail(item, previous_raw)

    assert merged.name == "Fresh Name"  # listing field untouched
    assert merged.description == "Cached description."
    assert merged.sku == "CODE-1"
    assert merged.specs == {"material": "Mesh"}
    assert merged.features == ["Breathable"]
    assert merged.detailFetchedAt == "2026-11-05T00:00:00Z"
