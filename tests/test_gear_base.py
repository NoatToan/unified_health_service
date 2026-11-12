from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scrapers.gear_base import (
    GearItem,
    apply_cached_detail,
    clean_description,
    common_variant_sku_prefix,
    cut_before_care_section,
    drop_boilerplate_specs,
    enrich_with_detail,
    extract_bullet_facts,
    extract_code_from_title,
    extract_description_candidate,
    extract_line_specs,
    extract_table_pairs,
    fill_missing_gender_from_text,
    gender_from_shopify_tags,
    gender_from_text,
    normalize_gender,
    parse_shopify_decimal_price,
    resolve_listing_gender,
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


def test_apply_cached_detail_keeps_listing_gender_when_cache_has_none():
    """A per-gender *listing* tag (gear_base.resolve_listing_gender, applied
    by lining_gear.py/coolmate_gear.py before enrichment) must survive a
    cache replay whose own detail fetch never found a gender tag - the
    cache's null must not clobber it.
    """
    item = GearItem(
        id="x-1",
        name="Fresh Name",
        brand="Brand",
        category="shoes",
        sourceName="x",
        priceVnd=100,
        productUrl="https://example.com/p",
        crawledAt="2026-11-12T00:00:00Z",
        gender="women",
    )
    previous_raw = {
        "description": "Cached description.",
        "gender": None,
        "detailFetchedAt": "2026-11-05T00:00:00Z",
    }

    merged = apply_cached_detail(item, previous_raw)

    assert merged.gender == "women"
    assert merged.description == "Cached description."


def test_enrich_with_detail_keeps_listing_gender_when_fetch_has_none():
    """Same guard as above, for a fresh (non-cached) detail fetch: a PDP
    that genuinely has no gender tag must not erase a gender this item
    already carries from its source's own per-gender listing.
    """
    item = GearItem(
        id="x-1",
        name="Fresh Name",
        brand="Brand",
        category="shoes",
        sourceName="x",
        productUrl="https://example.com/p",
        crawledAt="2026-11-12T00:00:00Z",
        gender="men",
    )

    def fetch_detail(_client, _item):
        return {"description": "Real PDP description.", "gender": None}

    enriched = enrich_with_detail(
        client=None,
        items=[item],
        previous_by_url=None,
        fetch_detail=fetch_detail,
        source_name="x",
    )

    assert enriched[0].gender == "men"
    assert enriched[0].description == "Real PDP description."


def test_resolve_listing_gender_resolves_single_tag_and_unions_to_unisex():
    assert resolve_listing_gender(None) is None
    assert resolve_listing_gender(set()) is None
    assert resolve_listing_gender({"men"}) == "men"
    assert resolve_listing_gender({"women"}) == "women"
    assert resolve_listing_gender({"men", "women"}) == "unisex"


def test_gender_from_text_matches_whole_word_keywords_en_and_vn():
    assert gender_from_text("Running Shoes Men") == "men"
    assert gender_from_text("Men's Running Tee") == "men"
    assert gender_from_text("Mens Training Shorts") == "men"
    assert gender_from_text("Giày chạy bộ Nam") == "men"
    assert gender_from_text("Running Shoes Women") == "women"
    assert gender_from_text("Women's Running Tee") == "women"
    assert gender_from_text("Womens Training Shorts") == "women"
    assert gender_from_text("Nike Wmns Running Shoes") == "women"
    assert gender_from_text("Giày chạy bộ Nữ") == "women"
    assert gender_from_text("Mũ Thể Thao Unisex") == "unisex"
    assert gender_from_text("Women's & Men's Running Tee") == "unisex"
    assert gender_from_text("Kids Running Shoes") == "kids"
    assert gender_from_text("Giày chạy bộ trẻ em") == "kids"
    assert gender_from_text("Junior Training Shorts") == "kids"


def test_gender_from_text_avoids_substring_false_positives():
    # The task brief's own called-out case: "nam" must not fire on the
    # country name "Việt Nam"/"Vietnam".
    assert gender_from_text("Áo chạy bộ Việt Nam 2026") is None
    assert gender_from_text("Running Jacket Vietnam Edition") is None
    # "nu" (from "nữ") must not substring-match inside an unrelated word.
    assert gender_from_text("Áo khoác màu Nude") is None


def test_gender_from_text_returns_none_without_a_keyword_or_input():
    assert gender_from_text("Night Runner V3 Running Shoes") is None
    assert gender_from_text(None) is None
    assert gender_from_text("") is None


def test_fill_missing_gender_from_text_only_fills_null_items():
    already_tagged = GearItem(
        id="x-1",
        name="Running Shoes Women",
        brand="B",
        category="shoes",
        sourceName="x",
        productUrl="https://example.com/1",
        crawledAt="2026-11-12T00:00:00Z",
        gender="men",  # some explicit source signal disagreeing with the
        # name - must be left alone, keyword fallback is last resort only.
    )
    untagged = GearItem(
        id="x-2",
        name="Running Shoes Women",
        brand="B",
        category="shoes",
        sourceName="x",
        productUrl="https://example.com/2",
        crawledAt="2026-11-12T00:00:00Z",
    )
    unknown = GearItem(
        id="x-3",
        name="Night Runner V3",
        brand="B",
        category="shoes",
        sourceName="x",
        productUrl="https://example.com/3",
        crawledAt="2026-11-12T00:00:00Z",
    )

    result = fill_missing_gender_from_text([already_tagged, untagged, unknown])

    assert result[0].gender == "men"
    assert result[1].gender == "women"
    assert result[2].gender is None
