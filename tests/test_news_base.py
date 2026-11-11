from __future__ import annotations

from scrapers.news_base import classify_category, make_news_id, strip_tracking_params


def test_classify_category_gear():
    assert classify_category("Review giày chạy bộ Nike mới nhất") == "gear"
    assert classify_category("Đập hộp Garmin Forerunner 970") == "gear"


def test_classify_category_training_tips():
    assert classify_category("Hướng dẫn giáo án luyện tập cho người mới") == "training-tips"
    assert classify_category("Chấn thương thường gặp khi chạy bộ") == "training-tips"


def test_classify_category_event_recap():
    assert classify_category("Hoàng Nguyên Thanh vô địch giải marathon") == "event-recap"
    assert classify_category("VĐV phá kỷ lục quốc gia") == "event-recap"


def test_classify_category_defaults_to_race_news():
    assert classify_category("Khởi động giải Marathon Quốc tế TP.HCM mùa 9") == "race-news"
    assert classify_category("Hoàn toàn không liên quan gì tới chạy") == "race-news"


def test_make_news_id_strips_extension_and_query():
    assert make_news_id("vnexpress", "https://vnexpress.net/abc-xyz-5142970.html") == (
        "vnexpress-abc-xyz-5142970"
    )
    assert make_news_id("tuoitre", "https://tuoitre.vn/mot-bai-viet-12345.htm") == (
        "tuoitre-mot-bai-viet-12345"
    )


def test_make_news_id_is_stable_across_trailing_slash():
    a = make_news_id("vnrun", "https://vnrun.com/bai-viet/")
    b = make_news_id("vnrun", "https://vnrun.com/bai-viet")
    assert a == b


def test_strip_tracking_params_removes_utm():
    url = "https://vnrun.com/bai-viet/?utm_source=rss&utm_medium=rss&id=5"
    cleaned = strip_tracking_params(url)
    assert "utm_source" not in cleaned
    assert "utm_medium" not in cleaned
    assert "id=5" in cleaned


def test_strip_tracking_params_noop_without_query():
    url = "https://vnrun.com/bai-viet/"
    assert strip_tracking_params(url) == url
