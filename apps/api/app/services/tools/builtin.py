"""Built-in tools: pure local computation, no network, no data access.

These are the safest kind of tool. They exist because an LLM is bad at arithmetic but
bank staff constantly need it: repayment schedules, transfer fees, working-day deadlines.
Each entry declares the JSON Schema the model sees, so `tools.params_schema` can be left
empty for kind="builtin" and filled from here.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

MAX_MONTHS = 600          # 50 years
MAX_AMOUNT = 1e15         # 1 triệu tỷ, guards against nonsense input
MAX_SCHEDULE_ROWS = 12    # only the first year is returned, plus totals


def _money(x: float) -> float:
    return round(float(x), 2)


# ---------------------------------------------------------------------------
# 1. Repayment schedule
# ---------------------------------------------------------------------------

def tinh_lich_tra_no(so_tien: float, lai_suat_nam: float, so_thang: int, phuong_thuc: str = "du_no_giam_dan") -> dict:
    if so_tien <= 0 or so_tien > MAX_AMOUNT:
        raise ValueError("so_tien không hợp lệ")
    if not (0 <= lai_suat_nam <= 100):
        raise ValueError("lai_suat_nam phải trong khoảng 0 đến 100")
    if not (1 <= so_thang <= MAX_MONTHS):
        raise ValueError(f"so_thang phải từ 1 đến {MAX_MONTHS}")

    r = lai_suat_nam / 100 / 12
    rows: list[dict] = []
    if phuong_thuc == "niem_kim":  # annuity: equal total payment every month
        pay = so_tien * r / (1 - (1 + r) ** -so_thang) if r else so_tien / so_thang
        bal, total_i = so_tien, 0.0
        for m in range(1, so_thang + 1):
            interest = bal * r
            principal = pay - interest
            bal -= principal
            total_i += interest
            if m <= MAX_SCHEDULE_ROWS:
                rows.append({"ky": m, "goc": _money(principal), "lai": _money(interest), "tong": _money(pay), "du_no": _money(max(bal, 0))})
        return {"phuong_thuc": "Niên kim (trả góp đều)", "so_tien_vay": _money(so_tien), "lai_suat_nam": lai_suat_nam,
                "so_thang": so_thang, "tra_hang_thang": _money(pay), "tong_lai": _money(total_i),
                "tong_phai_tra": _money(so_tien + total_i), "ky_dau": rows,
                "ghi_chu": f"Chỉ liệt kê {len(rows)} kỳ đầu." if so_thang > MAX_SCHEDULE_ROWS else None}

    # declining balance: equal principal, interest on the outstanding balance
    principal = so_tien / so_thang
    bal, total_i = so_tien, 0.0
    for m in range(1, so_thang + 1):
        interest = bal * r
        total_i += interest
        bal -= principal
        if m <= MAX_SCHEDULE_ROWS:
            rows.append({"ky": m, "goc": _money(principal), "lai": _money(interest),
                         "tong": _money(principal + interest), "du_no": _money(max(bal, 0))})
    return {"phuong_thuc": "Dư nợ giảm dần", "so_tien_vay": _money(so_tien), "lai_suat_nam": lai_suat_nam,
            "so_thang": so_thang, "tra_ky_dau": _money(principal + so_tien * r), "tong_lai": _money(total_i),
            "tong_phai_tra": _money(so_tien + total_i), "ky_dau": rows,
            "ghi_chu": f"Chỉ liệt kê {len(rows)} kỳ đầu." if so_thang > MAX_SCHEDULE_ROWS else None}


# ---------------------------------------------------------------------------
# 2. Percentage fee with floor / cap
# ---------------------------------------------------------------------------

def tinh_phi_giao_dich(so_tien: float, ty_le_phan_tram: float, toi_thieu: float = 0, toi_da: float = 0) -> dict:
    if so_tien < 0 or so_tien > MAX_AMOUNT:
        raise ValueError("so_tien không hợp lệ")
    if not (0 <= ty_le_phan_tram <= 100):
        raise ValueError("ty_le_phan_tram phải trong khoảng 0 đến 100")
    raw = so_tien * ty_le_phan_tram / 100
    fee, applied = raw, "theo tỷ lệ"
    if toi_thieu and fee < toi_thieu:
        fee, applied = toi_thieu, "áp mức tối thiểu"
    if toi_da and fee > toi_da:
        fee, applied = toi_da, "áp mức tối đa"
    return {"so_tien": _money(so_tien), "ty_le_phan_tram": ty_le_phan_tram, "phi_theo_ty_le": _money(raw),
            "phi_ap_dung": _money(fee), "quy_tac": applied,
            "ghi_chu": "Chưa gồm VAT và phí ngân hàng đại lý nếu có."}


# ---------------------------------------------------------------------------
# 3. Working-day deadline
# ---------------------------------------------------------------------------

def ngay_lam_viec(ngay_bat_dau: str, so_ngay_lam_viec: int) -> dict:
    try:
        d, m, y = (int(x) for x in ngay_bat_dau.replace("-", "/").split("/"))
        start = date(y, m, d) if y > 31 else date(d, m, y)  # accept dd/mm/yyyy and yyyy/mm/dd
    except Exception:
        raise ValueError("ngay_bat_dau phải theo dạng dd/mm/yyyy")
    if not (-365 <= so_ngay_lam_viec <= 365):
        raise ValueError("so_ngay_lam_viec phải trong khoảng -365 đến 365")

    step = 1 if so_ngay_lam_viec >= 0 else -1
    remaining, cur = abs(so_ngay_lam_viec), start
    while remaining:
        cur += timedelta(days=step)
        if cur.weekday() < 5:          # Mon–Fri
            remaining -= 1
    return {"ngay_bat_dau": start.strftime("%d/%m/%Y"), "so_ngay_lam_viec": so_ngay_lam_viec,
            "ket_qua": cur.strftime("%d/%m/%Y"), "thu": ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"][cur.weekday()],
            "ghi_chu": "Chỉ trừ thứ Bảy và Chủ Nhật, chưa trừ ngày lễ."}


# ---------------------------------------------------------------------------
# 4. Savings interest
# ---------------------------------------------------------------------------

def tinh_lai_tien_gui(so_tien: float, lai_suat_nam: float, so_thang: int) -> dict:
    if so_tien <= 0 or so_tien > MAX_AMOUNT:
        raise ValueError("so_tien không hợp lệ")
    if not (0 <= lai_suat_nam <= 100):
        raise ValueError("lai_suat_nam phải trong khoảng 0 đến 100")
    if not (1 <= so_thang <= MAX_MONTHS):
        raise ValueError(f"so_thang phải từ 1 đến {MAX_MONTHS}")
    interest = so_tien * lai_suat_nam / 100 * so_thang / 12
    return {"so_tien_gui": _money(so_tien), "lai_suat_nam": lai_suat_nam, "so_thang": so_thang,
            "tien_lai": _money(interest), "tong_nhan": _money(so_tien + interest),
            "ghi_chu": "Lãi cuối kỳ, chưa trừ thuế và chưa tính tái tục."}


def kiem_tra_kha_nang_tra_no(thu_nhap_thang: float, no_hien_tai_thang: float, so_tien_vay: float,
                             lai_suat_nam: float, so_thang: int, dti_toi_da: float = 70) -> dict:
    """Ước tính hệ số DTI sau khi vay thêm; ngưỡng do văn bản quy định, mặc định 70%.

    Chỉ là phép tính hỗ trợ tư vấn — kết luận cho vay hay không thuộc cấp thẩm định.
    """
    thu_nhap = float(thu_nhap_thang)
    if thu_nhap <= 0:
        return {"loi": "Thu nhập tháng phải lớn hơn 0"}
    lich = tinh_lich_tra_no(so_tien_vay, lai_suat_nam, so_thang, "niem_kim")
    tra_moi = float(lich["tra_hang_thang"])
    tong_no = float(no_hien_tai_thang) + tra_moi
    dti = tong_no / thu_nhap * 100
    dat = dti <= float(dti_toi_da)
    # số tiền vay tối đa để DTI vừa chạm ngưỡng, giữ nguyên lãi suất và kỳ hạn
    room = max(0.0, thu_nhap * float(dti_toi_da) / 100 - float(no_hien_tai_thang))
    toi_da = _money(so_tien_vay * room / tra_moi) if tra_moi > 0 else 0
    return {
        "tra_no_khoan_moi_thang": _money(tra_moi),
        "tong_nghia_vu_thang": _money(tong_no),
        "dti_phan_tram": round(dti, 1),
        "dti_toi_da_phan_tram": float(dti_toi_da),
        "dat_nguong": dat,
        "so_tien_vay_toi_da_uoc_tinh": toi_da,
        "luu_y": "Ước tính theo phương thức trả góp đều; kết quả thẩm định cuối cùng do ngân hàng quyết định.",
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _num(desc: str) -> dict:
    return {"type": "number", "description": desc}


BUILTINS: dict[str, dict[str, Any]] = {
    "tinh_lich_tra_no": {
        "fn": tinh_lich_tra_no,
        "name": "Tính lịch trả nợ",
        "description": "Tính lịch trả nợ khoản vay: số tiền trả hàng tháng, tổng lãi, tổng phải trả và các kỳ đầu. "
                       "Hỗ trợ dư nợ giảm dần và niên kim (trả góp đều).",
        "schema": {"type": "object", "properties": {
            "so_tien": _num("Số tiền vay (VND)"),
            "lai_suat_nam": _num("Lãi suất năm, đơn vị phần trăm, ví dụ 9.5"),
            "so_thang": {"type": "integer", "description": "Số tháng vay"},
            "phuong_thuc": {"type": "string", "enum": ["du_no_giam_dan", "niem_kim"],
                            "description": "Phương thức trả nợ, mặc định dư nợ giảm dần"},
        }, "required": ["so_tien", "lai_suat_nam", "so_thang"]},
    },
    "tinh_phi_giao_dich": {
        "fn": tinh_phi_giao_dich,
        "name": "Tính phí giao dịch",
        "description": "Tính phí theo tỷ lệ phần trăm có mức tối thiểu và tối đa, ví dụ phí chuyển tiền quốc tế.",
        "schema": {"type": "object", "properties": {
            "so_tien": _num("Số tiền giao dịch"),
            "ty_le_phan_tram": _num("Tỷ lệ phí, ví dụ 0.2 cho 0,20%"),
            "toi_thieu": _num("Mức phí tối thiểu, 0 nếu không có"),
            "toi_da": _num("Mức phí tối đa, 0 nếu không có"),
        }, "required": ["so_tien", "ty_le_phan_tram"]},
    },
    "ngay_lam_viec": {
        "fn": ngay_lam_viec,
        "name": "Tính ngày làm việc",
        "description": "Cộng hoặc trừ số ngày làm việc từ một ngày, bỏ qua thứ Bảy và Chủ Nhật. "
                       "Dùng để tính hạn xử lý hồ sơ.",
        "schema": {"type": "object", "properties": {
            "ngay_bat_dau": {"type": "string", "description": "Ngày bắt đầu dạng dd/mm/yyyy"},
            "so_ngay_lam_viec": {"type": "integer", "description": "Số ngày làm việc cần cộng, số âm để trừ"},
        }, "required": ["ngay_bat_dau", "so_ngay_lam_viec"]},
    },
    "kiem_tra_kha_nang_tra_no": {
        "fn": kiem_tra_kha_nang_tra_no,
        "name": "Kiểm tra khả năng trả nợ (DTI)",
        "description": "Ước tính hệ số DTI (tổng nghĩa vụ trả nợ / thu nhập) sau khi vay thêm và số tiền vay "
                       "tối đa để không vượt ngưỡng. Dùng khi tư vấn khách hàng cá nhân vay bao nhiêu là vừa.",
        "schema": {"type": "object", "properties": {
            "thu_nhap_thang": _num("Thu nhập ròng đã chứng minh mỗi tháng (VND)"),
            "no_hien_tai_thang": _num("Tổng số tiền đang phải trả nợ mỗi tháng cho các khoản vay khác (VND), 0 nếu không có"),
            "so_tien_vay": _num("Số tiền định vay thêm (VND)"),
            "lai_suat_nam": _num("Lãi suất năm, đơn vị phần trăm"),
            "so_thang": {"type": "integer", "description": "Kỳ hạn vay tính bằng tháng"},
            "dti_toi_da": _num("Ngưỡng DTI tối đa theo quy định, phần trăm, mặc định 70"),
        }, "required": ["thu_nhap_thang", "no_hien_tai_thang", "so_tien_vay", "lai_suat_nam", "so_thang"]},
    },
    "tinh_lai_tien_gui": {
        "fn": tinh_lai_tien_gui,
        "name": "Tính lãi tiền gửi",
        "description": "Tính tiền lãi và tổng nhận của sổ tiết kiệm lãi cuối kỳ.",
        "schema": {"type": "object", "properties": {
            "so_tien": _num("Số tiền gửi (VND)"),
            "lai_suat_nam": _num("Lãi suất năm, đơn vị phần trăm"),
            "so_thang": {"type": "integer", "description": "Kỳ hạn tính bằng tháng"},
        }, "required": ["so_tien", "lai_suat_nam", "so_thang"]},
    },
}


def get_builtin(fn_name: str) -> tuple[Callable[..., dict], dict] | None:
    """Return (callable, json schema) for a builtin, or None when unknown."""
    entry = BUILTINS.get(fn_name)
    return (entry["fn"], entry["schema"]) if entry else None
