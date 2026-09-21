"""Bộ chặn của bộ nhớ cá nhân — bài kiểm quan trọng nhất của tính năng.

Một trợ lý ngân hàng nhớ nhầm tên khách hàng, hay nhớ một con số quy định rồi nói lại như sự thật,
là sự cố chứ không phải lỗi nhỏ. Vì vậy bộ lọc phải là mã chứ không phải lời dặn mô hình, và mọi ví
dụ trong bảng cấm của thiết kế đều phải có một bài kiểm ở đây.

Nguyên tắc khi sửa: thêm một loại nội dung bị cấm thì thêm bài kiểm trước, sửa `rejection_reason`
sau.
"""

import pytest

from app.services.memory import (
    CATEGORIES,
    MAX_TEXT,
    allowed,
    memory_block,
    parse_json_block,
    rejection_reason,
)


# --------------------------------------------------------------------------- được phép nhớ

@pytest.mark.parametrize("category,text", [
    ("trinh_bay", "Thích câu trả lời ngắn gọn, có các bước đánh số"),
    ("trinh_bay", "Muốn phần kết luận đặt lên đầu câu trả lời"),
    ("vai_tro", "Là cán bộ quan hệ khách hàng phụ trách khách hàng doanh nghiệp FDI"),
    ("vai_tro", "Làm việc tại chi nhánh Hà Nội, mảng thanh toán quốc tế"),
    ("boi_canh", "Đang theo hồ sơ HS2026-0412"),
    ("boi_canh", "Tuần này tập trung vào các hồ sơ sắp tới hạn SLA"),
    ("thuat_ngu", "Quen gọi Khối Vận hành và Thanh toán quốc tế là OPS"),
    ("thuat_ngu", "Dùng từ tiếng Anh cho thuật ngữ tín dụng"),
])
def test_allowed_examples(category, text):
    assert rejection_reason(text, category) is None, rejection_reason(text, category)


# --------------------------------------------------------------------------- dữ liệu khách hàng

@pytest.mark.parametrize("text", [
    "Khách hàng Nguyễn Văn An hay hỏi về lãi suất",
    "Anh Bình ở công ty ABC cần giải ngân gấp",
    "Chị Lan là kế toán trưởng của khách",
])
def test_named_customers_refused(text):
    assert rejection_reason(text, "boi_canh") is not None
    assert "tên người" in rejection_reason(text, "boi_canh")


@pytest.mark.parametrize("text", [
    "Hồ sơ này đề nghị vay 5.000.000.000 VND",
    "Khoản vay 2.500.000 đồng đã tất toán",
    "Hạn mức 120.000 USD",
])
def test_amounts_refused(text):
    assert "số tiền" in (rejection_reason(text, "boi_canh") or "")


def test_masked_pii_refused():
    """`mask_pii` chạy trước, nên còn nhãn che nghĩa là đang cố nhớ đúng thứ vừa bị che."""
    assert "đã bị che" in (rejection_reason("Số tài khoản của khách là [SỐ TÀI KHOẢN]", "boi_canh") or "")
    assert "đã bị che" in (rejection_reason("Hay dùng [CCCD] để tra cứu", "trinh_bay") or "")


# --------------------------------------------------------------------------- kết quả nghiệp vụ

@pytest.mark.parametrize("text", [
    "Hồ sơ HS2026-0412 đã được duyệt",
    "Đề nghị của khách bị từ chối",
    "Khoản vay này đã giải ngân xong",
])
def test_business_outcomes_refused(text):
    assert "kết quả nghiệp vụ" in (rejection_reason(text, "boi_canh") or "")


# --------------------------------------------------------------------------- nội dung quy định

@pytest.mark.parametrize("text", [
    "Tỉ lệ cho vay tối đa là 70%",
    "Theo Điều 5 thì hồ sơ phải có TSBĐ",
    "Thông tư 39 quy định về lãi suất",
    "Hạn mức không quá 3 lần vốn chủ sở hữu",
])
def test_regulation_content_refused(text):
    """Con số quy định phải nằm trong văn bản để trích dẫn được. Nhét vào bộ nhớ thì đổi quy định
    là bộ nhớ sai âm thầm, không ai biết."""
    assert "quy định" in (rejection_reason(text, "vai_tro") or "")


# --------------------------------------------------------------------------- khung

def test_unknown_category_refused():
    assert "không nằm trong bốn loại" in (rejection_reason("Thích ngắn gọn", "so_thich") or "")
    assert "không nằm trong bốn loại" in (rejection_reason("Thích ngắn gọn", "") or "")


def test_empty_and_too_long():
    assert rejection_reason("", "trinh_bay") == "rỗng"
    assert rejection_reason("   ", "trinh_bay") == "rỗng"
    assert "dài quá" in (rejection_reason("x" * (MAX_TEXT + 1), "trinh_bay") or "")


def test_exactly_four_categories():
    """Thêm loại thứ năm là mở rộng phạm vi dữ liệu cá nhân được lưu, phải là quyết định có ý thức."""
    assert set(CATEGORIES) == {"trinh_bay", "vai_tro", "boi_canh", "thuat_ngu"}


def test_allowed_is_a_thin_wrapper():
    assert allowed("Thích câu trả lời ngắn gọn có bước đánh số", "trinh_bay") is True
    assert allowed("Khách hàng Nguyễn Văn An thích gọi điện", "vai_tro") is False


# --------------------------------------------------------------------------- khối prompt

def test_memory_block_says_it_is_not_a_source_of_truth():
    """Ranh giới quan trọng nhất phải nằm ngay cạnh dữ liệu, không chỉ nằm trong tài liệu thiết kế."""

    class Row:
        text = "Thích câu trả lời ngắn"

    block = memory_block([Row()])
    assert "KHÔNG phải nguồn về quy định" in block
    assert "Thích câu trả lời ngắn" in block


def test_memory_block_empty_when_nothing_to_say():
    assert memory_block([]) == ""


# --------------------------------------------------------------------------- đọc JSON của mô hình

def test_parse_json_block_handles_fenced_output():
    assert parse_json_block('```json\n{"ghi_nho": []}\n```') == {"ghi_nho": []}
    assert parse_json_block('Đây là kết quả: {"ghi_nho": [{"loai": "trinh_bay"}]}') == {
        "ghi_nho": [{"loai": "trinh_bay"}]}


def test_parse_json_block_returns_none_on_garbage():
    assert parse_json_block("không phải json") is None
    assert parse_json_block("") is None
    assert parse_json_block("[1, 2, 3]") is None
