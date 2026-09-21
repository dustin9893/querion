"""MCP server giả lập "Hệ thống quản trị rủi ro" cho demo loại công cụ MCP.

TOÀN BỘ DỮ LIỆU LÀ MÔ PHỎNG. Chạy qua HTTP (streamable-http), vì MCP qua stdio bị chặn
mặc định trong API (ENABLE_MCP_STDIO=false).

Chạy:  ./scripts/mock-mcp.sh      (mặc định http://localhost:8096/mcp)
"""

import os

from mcp.server.fastmcp import FastMCP

PORT = int(os.getenv("PORT", "8096"))
HOST = os.getenv("MCP_HOST", "127.0.0.1")  # 0.0.0.0 inside a container
mcp = FastMCP("msb-rui-ro-gia-lap", host=HOST, port=PORT)

# Keyed by file number: CIF is masked as PII before the model sees it.
XEP_HANG = {
    "HS2026-0412": {"ten": "Công ty CP Thép Đông Á", "xep_hang": "BBB", "nhom_no": 1, "canh_bao": []},
    "HS2026-0518": {"ten": "Công ty TNHH Dệt may Sao Mai", "xep_hang": "BB-", "nhom_no": 2,
                    "canh_bao": ["Tỷ lệ sử dụng hạn mức trên 95%", "Có khoản nợ nhóm 2 trong 3 tháng gần nhất"]},
    "HS2026-0731": {"ten": "Công ty CP Logistics Bình Minh", "xep_hang": "A-", "nhom_no": 1, "canh_bao": []},
}

TY_LE_CHO_VAY = {
    "bat_dong_san": 70, "o_to": 70, "so_tiet_kiem": 95, "hang_ton_kho": 50, "may_moc_thiet_bi": 60,
}


@mcp.tool()
def tra_xep_hang_tin_dung(ma_ho_so: str) -> dict:
    """Tra xếp hạng tín dụng nội bộ, nhóm nợ và cảnh báo rủi ro của khách hàng doanh nghiệp theo mã hồ sơ tín dụng (vd HS2026-0518)."""
    row = XEP_HANG.get(ma_ho_so.strip().upper())
    if not row:
        return {"tim_thay": False, "ma_ho_so": ma_ho_so, "goi_y": list(XEP_HANG)}
    return {"tim_thay": True, "ma_ho_so": ma_ho_so.strip().upper(), **row}


@mcp.tool()
def tra_ty_le_cho_vay_toi_da(loai_tsbd: str) -> dict:
    """Tra tỷ lệ cho vay tối đa (%) trên giá trị tài sản bảo đảm theo loại: bat_dong_san, o_to, so_tiet_kiem, hang_ton_kho, may_moc_thiet_bi."""
    key = loai_tsbd.strip().lower()
    if key not in TY_LE_CHO_VAY:
        return {"tim_thay": False, "loai_tsbd": loai_tsbd, "ho_tro": list(TY_LE_CHO_VAY)}
    return {"tim_thay": True, "loai_tsbd": key, "ty_le_toi_da_phan_tram": TY_LE_CHO_VAY[key]}


# Danh sách cấm vận / cảnh báo MÔ PHỎNG: tên đối tác hư cấu, không phải danh sách thật.
DANH_SACH_CANH_BAO = [
    {"ten": "Golden Sands Trading LLC", "danh_sach": "OFAC SDN (mô phỏng)", "quoc_gia": "UAE"},
    {"ten": "Northern Star Shipping Co", "danh_sach": "EU consolidated (mô phỏng)", "quoc_gia": "Nga"},
    {"ten": "Pyong Trading Corporation", "danh_sach": "UN 1718 (mô phỏng)", "quoc_gia": "Triều Tiên"},
    {"ten": "Blue Lotus Import Export", "danh_sach": "Cảnh báo AML nội bộ", "quoc_gia": "Việt Nam"},
]
QUOC_GIA_RUI_RO_CAO = {"iran", "triều tiên", "trieu tien", "north korea", "syria", "myanmar", "cuba", "nga", "russia", "belarus"}

# Dấu hiệu cảnh báo sớm (EWS) theo hồ sơ — số liệu mô phỏng.
CANH_BAO_SOM = {
    "HS2026-0412": {"tong_diem": 12, "muc": "Thấp", "dau_hieu": [
        {"ma": "EWS-05", "mo_ta": "Doanh thu quý 2 giảm 8% so với cùng kỳ", "muc_do": "thap", "ngay": "05/09/2026"}]},
    "HS2026-0518": {"tong_diem": 58, "muc": "Cao", "dau_hieu": [
        {"ma": "EWS-01", "mo_ta": "Tỷ lệ sử dụng hạn mức trên 95% liên tục 60 ngày", "muc_do": "cao", "ngay": "01/09/2026"},
        {"ma": "EWS-03", "mo_ta": "Phát sinh nợ nhóm 2 tại TCTD khác (CIC)", "muc_do": "cao", "ngay": "28/08/2026"},
        {"ma": "EWS-07", "mo_ta": "Chậm nộp báo cáo tài chính bán niên 20 ngày", "muc_do": "trung_binh", "ngay": "20/08/2026"}]},
    "HS2026-0731": {"tong_diem": 4, "muc": "Thấp", "dau_hieu": []},
    "HS2026-0620": {"tong_diem": 31, "muc": "Trung bình", "dau_hieu": [
        {"ma": "EWS-04", "mo_ta": "Dòng tiền về tài khoản giảm 25% trong 3 tháng", "muc_do": "trung_binh", "ngay": "10/09/2026"},
        {"ma": "EWS-09", "mo_ta": "Có vụ kiện tranh chấp hợp đồng với nhà thầu phụ", "muc_do": "trung_binh", "ngay": "02/09/2026"}]},
}


def _giong(a: str, b: str) -> float:
    """Độ giống thô giữa hai tên (Jaccard theo từ) — đủ cho demo, không phải fuzzy-matching thật."""
    wa, wb = set(a.lower().split()), set(b.lower().split())
    return round(len(wa & wb) / len(wa | wb), 2) if wa and wb else 0.0


@mcp.tool()
def sang_loc_cam_van(ten_doi_tac: str, quoc_gia: str = "") -> dict:
    """Sàng lọc tên đối tác / người hưởng và quốc gia với danh sách cấm vận (OFAC, EU, UN) và cảnh báo AML nội bộ. Trả về không trùng, trùng một phần hay trùng khớp, kèm hướng xử lý."""
    ten = ten_doi_tac.strip()
    best = max(({"diem": _giong(ten, r["ten"]), **r} for r in DANH_SACH_CANH_BAO), key=lambda x: x["diem"])
    if best["diem"] >= 0.8:
        ket_qua, huong_dan = "trung_khop", "Dừng giao dịch, báo KSV và bộ phận Tuân thủ xác nhận trước khi tiếp tục."
    elif best["diem"] >= 0.4:
        ket_qua, huong_dan = "trung_mot_phan", "Đối chiếu thêm địa chỉ, quốc gia, mã số; KSV xác nhận false positive bằng văn bản."
    else:
        ket_qua, huong_dan = "khong_trung", "Không có cảnh báo về tên; vẫn kiểm mục đích và chứng từ như thường."
    qg = quoc_gia.strip().lower()
    rui_ro = bool(qg) and qg in QUOC_GIA_RUI_RO_CAO
    return {"ten_doi_tac": ten, "quoc_gia": quoc_gia or None, "ket_qua": ket_qua, "diem_tuong_dong": best["diem"],
            "khop_gan_nhat": {"ten": best["ten"], "danh_sach": best["danh_sach"]} if best["diem"] >= 0.4 else None,
            "quoc_gia_rui_ro_cao": rui_ro, "huong_dan": huong_dan,
            "luu_y": "Kết quả sàng lọc mô phỏng phục vụ demo; không thay cho hệ thống sàng lọc thật."}


@mcp.tool()
def canh_bao_som(ma_ho_so: str) -> dict:
    """Dấu hiệu cảnh báo sớm (EWS) của một khách hàng doanh nghiệp theo mã hồ sơ tín dụng: tổng điểm, mức rủi ro và từng dấu hiệu."""
    row = CANH_BAO_SOM.get(ma_ho_so.strip().upper())
    if not row:
        return {"tim_thay": False, "ma_ho_so": ma_ho_so, "goi_y": list(CANH_BAO_SOM)}
    return {"tim_thay": True, "ma_ho_so": ma_ho_so.strip().upper(), **row,
            "khuyen_nghi": "Trình tái thẩm định" if row["tong_diem"] >= 50 else
                           ("Theo dõi sát, cập nhật hồ sơ tài chính" if row["tong_diem"] >= 25 else "Theo dõi định kỳ")}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
