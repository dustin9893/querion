"""Unit tests for the PII masker (Microsoft Presidio engine + regex fallback).

Run: cd apps/api && pytest tests/test_pii.py -v
Requires the spaCy model: python -m spacy download en_core_web_sm
"""

import pytest

from app.services import pii
from app.services.pii import PLACEHOLDER, mask_pii, notice_for

MUST_MASK = [
    ("Số tài khoản của tôi là 0123456789012, phí chuyển khoản bao nhiêu?", "account", "0123456789012"),
    ("STK 19035678901234 ở MSB chuyển sang Vietcombank mất phí không?", "account", "19035678901234"),
    ("Tôi là Nguyễn Văn An, tài khoản 0011002233445 (Vietcombank). Có được rút không?", "account", "0011002233445"),
    ("CCCD 001099012345 của tôi hết hạn, mở thẻ được không?", "id", "001099012345"),
    ("CMND 012345678 còn dùng được không?", "id", "012345678"),
    ("Hộ chiếu B1234567 mở tài khoản được không?", "id", "B1234567"),
    ("Liên hệ tôi qua 0912 345 678 nhé", "phone", "0912 345 678"),
    ("số điện thoại 0912345678", "phone", "0912345678"),
    ("Gọi +84 912345678 nhé", "phone", "912345678"),
    ("Email anhnv@gmail.com của tôi", "email", "anhnv@gmail.com"),
    ("Mã OTP của tôi là 482913, tại sao không chuyển được?", "otp", "482913"),
    ("mật khẩu 123456 của tôi", "otp", "123456"),
    ("Số thẻ 4111 1111 1111 1111 bị khóa, làm sao mở?", "card", "4111 1111 1111 1111"),
    ("CIF 1234567 của khách hàng này có được vay không?", "cif", "1234567"),
]

MUST_KEEP = [
    "Khoản vay 500.000.000 đồng lãi suất bao nhiêu?",
    "Quy trình QT.TD.EB.01 phiên bản 3.2 hiệu lực từ 01/03/2025",
    "Trạng thái STEB01 là gì? Mất 100.000 USD phí?",
    "Điều 5 khoản 2 quy định gì về TSBĐ?",
    "Phí duy trì thẻ 50.000đ/năm, hạn mức 20 triệu",
    "Năm 2024 doanh thu 1.234.567.890 đồng",
    "Mở sổ tiết kiệm kỳ hạn 12 tháng lãi 5,5%/năm",
    "Chuyển 2000000 đồng thì phí bao nhiêu?",
    "Mã khách hàng cần bao nhiêu chữ số?",
    "Văn bản số 1234/QĐ-MSB ngày 12/05/2024 quy định gì?",
    "Lãi suất 6.8% cho khoản vay 1.500.000.000, thời hạn 240 tháng",
    "Khoản vay 500.000.000 đồng, kỳ hạn 0912 tháng?",
]


@pytest.fixture(scope="module")
def presidio_ready():
    engine = pii.warm_up()
    if engine != "presidio":
        pytest.skip("Presidio / spaCy model not installed")


@pytest.mark.parametrize("text,kind,secret", MUST_MASK)
def test_masks_sensitive_values(presidio_ready, text, kind, secret):
    res = mask_pii(text)
    assert res.engine == "presidio"
    assert res.found
    assert kind in res.kinds, res
    assert secret not in res.text, res.text
    assert any(ph in res.text for ph in PLACEHOLDER.values()), res.text


@pytest.mark.parametrize("text", MUST_KEEP)
def test_keeps_amounts_dates_and_codes(presidio_ready, text):
    res = mask_pii(text)
    assert not res.found, res
    assert res.text == text


def test_red_team_sentence_masks_everything(presidio_ready):
    text = ("Số tài khoản của tôi là 0123456789012, CCCD 079123456789, số điện thoại 0912345678, "
            "mã OTP vừa nhận là 482913. Kiểm tra giúp phí SMS Banking áp cho tài khoản này.")
    res = mask_pii(text)
    for secret in ("0123456789012", "079123456789", "0912345678", "482913"):
        assert secret not in res.text
    assert set(res.kinds) == {"account", "id", "phone", "otp"}
    assert "phí SMS Banking" in res.text  # the actual question survives
    assert "số tài khoản" in notice_for(res.kinds) and "mã OTP" in notice_for(res.kinds)


def test_empty_and_none():
    assert mask_pii("").text == ""
    assert mask_pii(None).text == ""
    assert not mask_pii(None).found


def test_regex_fallback(monkeypatch):
    monkeypatch.setattr(pii.settings, "PII_ENGINE", "regex")
    res = mask_pii("STK 0123456789012, OTP 482913, gọi 0912345678, mail a@b.vn")
    assert res.engine == "regex"
    for secret in ("0123456789012", "482913", "0912345678", "a@b.vn"):
        assert secret not in res.text
    assert {"otp", "phone", "email"} <= set(res.kinds)


def test_off_mode(monkeypatch):
    monkeypatch.setattr(pii.settings, "PII_ENGINE", "off")
    text = "STK 0123456789012"
    res = mask_pii(text)
    assert res.text == text and not res.found and res.engine == "off"
