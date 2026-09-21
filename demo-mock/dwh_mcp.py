"""MCP server giả lập "Kho dữ liệu báo cáo (DWH)" — nguồn số liệu tổng hợp cho báo cáo định kỳ.

TOÀN BỘ DỮ LIỆU LÀ MÔ PHỎNG, không lấy từ hệ thống thật của ngân hàng. Khác với mock core
(tra cứu từng hồ sơ), server này trả **số liệu đã tổng hợp theo chiều** (chi nhánh, nhóm nợ,
ngày, cán bộ) — đúng thứ một báo cáo Excel cần.

Chạy:  ./scripts/mock-dwh.sh      (mặc định http://localhost:8097/mcp)
"""

import os
from datetime import date, timedelta

from mcp.server.fastmcp import FastMCP

PORT = int(os.getenv("PORT", "8097"))
HOST = os.getenv("MCP_HOST", "127.0.0.1")  # 0.0.0.0 inside a container
mcp = FastMCP("msb-dwh-gia-lap", host=HOST, port=PORT)

KY_MAC_DINH = "09/2026"

# Doanh số giải ngân theo chi nhánh (tỷ lệ hoàn thành kế hoạch tính sẵn để báo cáo khỏi tính lại).
DOANH_SO = {
    "09/2026": [
        {"chi_nhanh": "CN Hà Nội", "khoi": "EB", "so_ho_so": 34, "giai_ngan": 412_000_000_000,
         "ke_hoach": 450_000_000_000, "du_no_cuoi_ky": 1_820_000_000_000},
        {"chi_nhanh": "CN Hồ Chí Minh", "khoi": "EB", "so_ho_so": 41, "giai_ngan": 528_500_000_000,
         "ke_hoach": 500_000_000_000, "du_no_cuoi_ky": 2_140_000_000_000},
        {"chi_nhanh": "CN Đống Đa", "khoi": "EB", "so_ho_so": 18, "giai_ngan": 176_300_000_000,
         "ke_hoach": 220_000_000_000, "du_no_cuoi_ky": 742_000_000_000},
        {"chi_nhanh": "CN Cầu Giấy", "khoi": "EB", "so_ho_so": 22, "giai_ngan": 233_900_000_000,
         "ke_hoach": 230_000_000_000, "du_no_cuoi_ky": 905_000_000_000},
        {"chi_nhanh": "Hội sở", "khoi": "EB", "so_ho_so": 11, "giai_ngan": 96_400_000_000,
         "ke_hoach": 120_000_000_000, "du_no_cuoi_ky": 388_000_000_000},
    ],
    "08/2026": [
        {"chi_nhanh": "CN Hà Nội", "khoi": "EB", "so_ho_so": 29, "giai_ngan": 361_000_000_000,
         "ke_hoach": 430_000_000_000, "du_no_cuoi_ky": 1_690_000_000_000},
        {"chi_nhanh": "CN Hồ Chí Minh", "khoi": "EB", "so_ho_so": 37, "giai_ngan": 474_000_000_000,
         "ke_hoach": 480_000_000_000, "du_no_cuoi_ky": 2_010_000_000_000},
        {"chi_nhanh": "CN Đống Đa", "khoi": "EB", "so_ho_so": 15, "giai_ngan": 151_500_000_000,
         "ke_hoach": 210_000_000_000, "du_no_cuoi_ky": 705_000_000_000},
        {"chi_nhanh": "CN Cầu Giấy", "khoi": "EB", "so_ho_so": 19, "giai_ngan": 205_700_000_000,
         "ke_hoach": 225_000_000_000, "du_no_cuoi_ky": 861_000_000_000},
        {"chi_nhanh": "Hội sở", "khoi": "EB", "so_ho_so": 9, "giai_ngan": 81_200_000_000,
         "ke_hoach": 115_000_000_000, "du_no_cuoi_ky": 360_000_000_000},
    ],
}

# Nợ quá hạn theo nhóm nợ (nhóm 1–5 theo cách phân loại quen thuộc trong ngành).
NO_QUA_HAN = {
    "09/2026": [
        {"nhom_no": 1, "ten_nhom": "Nợ đủ tiêu chuẩn", "so_khach_hang": 412, "du_no": 5_640_000_000_000, "ty_le_trich_lap": 0.0},
        {"nhom_no": 2, "ten_nhom": "Nợ cần chú ý", "so_khach_hang": 37, "du_no": 286_000_000_000, "ty_le_trich_lap": 0.05},
        {"nhom_no": 3, "ten_nhom": "Nợ dưới tiêu chuẩn", "so_khach_hang": 9, "du_no": 61_500_000_000, "ty_le_trich_lap": 0.20},
        {"nhom_no": 4, "ten_nhom": "Nợ nghi ngờ", "so_khach_hang": 4, "du_no": 23_800_000_000, "ty_le_trich_lap": 0.50},
        {"nhom_no": 5, "ten_nhom": "Nợ có khả năng mất vốn", "so_khach_hang": 2, "du_no": 11_200_000_000, "ty_le_trich_lap": 1.0},
    ],
}
NO_QUA_HAN["08/2026"] = [
    {**row, "du_no": int(row["du_no"] * 0.94), "so_khach_hang": max(1, int(row["so_khach_hang"] * 0.96))}
    for row in NO_QUA_HAN["09/2026"]
]

# KPI cán bộ quan hệ khách hàng — mã cán bộ, không kèm dữ liệu định danh khách hàng.
KPI_CAN_BO = {
    "09/2026": [
        {"ma_can_bo": "MSB01001", "ho_ten": "Nguyễn Văn An", "chi_nhanh": "CN Hà Nội", "so_ho_so": 12,
         "giai_ngan": 148_000_000_000, "ty_le_dung_han": 0.83, "so_ho_so_qua_han": 2},
        {"ma_can_bo": "MSB01002", "ho_ten": "Trần Thị Bình", "chi_nhanh": "Hội sở", "so_ho_so": 9,
         "giai_ngan": 96_500_000_000, "ty_le_dung_han": 0.89, "so_ho_so_qua_han": 1},
        {"ma_can_bo": "MSB01004", "ho_ten": "Phạm Minh Dũng", "chi_nhanh": "CN Hồ Chí Minh", "so_ho_so": 15,
         "giai_ngan": 201_300_000_000, "ty_le_dung_han": 0.93, "so_ho_so_qua_han": 1},
        {"ma_can_bo": "MSB01007", "ho_ten": "Vũ Thị Hạnh", "chi_nhanh": "CN Cầu Giấy", "so_ho_so": 8,
         "giai_ngan": 74_900_000_000, "ty_le_dung_han": 0.75, "so_ho_so_qua_han": 3},
    ],
}
KPI_CAN_BO["08/2026"] = [
    {**row, "giai_ngan": int(row["giai_ngan"] * 0.91), "so_ho_so": max(1, row["so_ho_so"] - 2)}
    for row in KPI_CAN_BO["09/2026"]
]


def _ky(thang: str | None) -> str:
    return (thang or "").strip() or KY_MAC_DINH


@mcp.tool()
def doanh_so_theo_chi_nhanh(thang: str = KY_MAC_DINH) -> dict:
    """Doanh số giải ngân, kế hoạch và dư nợ cuối kỳ của từng chi nhánh trong một tháng (MM/YYYY, vd 09/2026)."""
    ky = _ky(thang)
    rows = DOANH_SO.get(ky)
    if rows is None:
        return {"tim_thay": False, "thang": ky, "ky_co_san": sorted(DOANH_SO)}
    out = [{**r, "ty_le_hoan_thanh": round(r["giai_ngan"] / r["ke_hoach"], 4)} for r in rows]
    return {
        "tim_thay": True, "thang": ky, "so_chi_nhanh": len(out),
        "tong_giai_ngan": sum(r["giai_ngan"] for r in out),
        "tong_ke_hoach": sum(r["ke_hoach"] for r in out),
        "chi_nhanh": out,
    }


@mcp.tool()
def no_qua_han_theo_nhom(thang: str = KY_MAC_DINH) -> dict:
    """Dư nợ và số khách hàng theo nhóm nợ 1–5, kèm số trích lập dự phòng ước tính, trong một tháng (MM/YYYY)."""
    ky = _ky(thang)
    rows = NO_QUA_HAN.get(ky)
    if rows is None:
        return {"tim_thay": False, "thang": ky, "ky_co_san": sorted(NO_QUA_HAN)}
    out = [{**r, "trich_lap_uoc_tinh": int(r["du_no"] * r["ty_le_trich_lap"])} for r in rows]
    xau = sum(r["du_no"] for r in out if r["nhom_no"] >= 3)
    tong = sum(r["du_no"] for r in out)
    return {
        "tim_thay": True, "thang": ky, "tong_du_no": tong, "du_no_xau": xau,
        "ty_le_no_xau": round(xau / tong, 4) if tong else 0,
        "tong_trich_lap": sum(r["trich_lap_uoc_tinh"] for r in out),
        "nhom": out,
    }


@mcp.tool()
def kpi_can_bo(thang: str = KY_MAC_DINH, chi_nhanh: str = "") -> dict:
    """KPI của cán bộ quan hệ khách hàng trong tháng (số hồ sơ, doanh số giải ngân, tỷ lệ đúng hạn), lọc được theo chi nhánh."""
    ky = _ky(thang)
    rows = KPI_CAN_BO.get(ky)
    if rows is None:
        return {"tim_thay": False, "thang": ky, "ky_co_san": sorted(KPI_CAN_BO)}
    if chi_nhanh.strip():
        rows = [r for r in rows if chi_nhanh.strip().lower() in r["chi_nhanh"].lower()]
    return {"tim_thay": True, "thang": ky, "so_can_bo": len(rows),
            "tong_giai_ngan": sum(r["giai_ngan"] for r in rows), "can_bo": rows}


@mcp.tool()
def giao_dich_ttqt_theo_ngay(so_ngay: int = 7) -> dict:
    """Số lượng và giá trị giao dịch thanh toán quốc tế theo từng ngày trong `so_ngay` ngày gần nhất (1–31)."""
    days = max(1, min(int(so_ngay or 7), 31))
    today = date(2026, 9, 18)
    rows = []
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        if day.weekday() >= 5:  # cuối tuần không có giao dịch
            continue
        base = 18 + (day.day * 7) % 11
        rows.append({
            "ngay": day.strftime("%d/%m/%Y"),
            "so_giao_dich": base,
            "gia_tri_usd": base * 41_500 + (day.day % 5) * 12_000,
            "cho_ksv_duyet": max(0, (day.day * 3) % 5),
        })
    return {"tim_thay": True, "so_ngay": days, "so_dong": len(rows),
            "tong_gia_tri_usd": sum(r["gia_tri_usd"] for r in rows), "theo_ngay": rows}


# Huy động & cho vay KHCN theo chi nhánh — số liệu mô phỏng.
KHCN = {
    "09/2026": [
        {"chi_nhanh": "CN Hà Nội", "huy_dong": 2_310_000_000_000, "ke_hoach_huy_dong": 2_200_000_000_000, "cho_vay": 1_180_000_000_000,
         "khach_hang_moi": 1_240, "the_tin_dung_moi": 310, "ty_le_no_xau": 0.011},
        {"chi_nhanh": "CN Hồ Chí Minh", "huy_dong": 2_890_000_000_000, "ke_hoach_huy_dong": 2_700_000_000_000, "cho_vay": 1_560_000_000_000,
         "khach_hang_moi": 1_610, "the_tin_dung_moi": 425, "ty_le_no_xau": 0.014},
        {"chi_nhanh": "CN Đà Nẵng", "huy_dong": 640_000_000_000, "ke_hoach_huy_dong": 700_000_000_000, "cho_vay": 410_000_000_000,
         "khach_hang_moi": 380, "the_tin_dung_moi": 96, "ty_le_no_xau": 0.009},
        {"chi_nhanh": "CN Cầu Giấy", "huy_dong": 980_000_000_000, "ke_hoach_huy_dong": 950_000_000_000, "cho_vay": 520_000_000_000,
         "khach_hang_moi": 560, "the_tin_dung_moi": 142, "ty_le_no_xau": 0.012},
        {"chi_nhanh": "CN Đống Đa", "huy_dong": 760_000_000_000, "ke_hoach_huy_dong": 800_000_000_000, "cho_vay": 395_000_000_000,
         "khach_hang_moi": 410, "the_tin_dung_moi": 101, "ty_le_no_xau": 0.016},
    ],
}
KHCN["08/2026"] = [{**r, "huy_dong": int(r["huy_dong"] * 0.97), "cho_vay": int(r["cho_vay"] * 0.95),
                    "khach_hang_moi": int(r["khach_hang_moi"] * 0.9)} for r in KHCN["09/2026"]]

# Chuỗi theo tháng cho biểu đồ đường — 6 tháng gần nhất.
XU_HUONG = {
    "giai_ngan_eb": {"ten": "Giải ngân KHDN", "don_vi": "VND", "gia_tri": {
        "04/2026": 1_120_000_000_000, "05/2026": 1_205_000_000_000, "06/2026": 1_180_000_000_000,
        "07/2026": 1_260_000_000_000, "08/2026": 1_273_400_000_000, "09/2026": 1_447_100_000_000}},
    "huy_dong_rb": {"ten": "Huy động KHCN", "don_vi": "VND", "gia_tri": {
        "04/2026": 6_900_000_000_000, "05/2026": 7_050_000_000_000, "06/2026": 7_180_000_000_000,
        "07/2026": 7_260_000_000_000, "08/2026": 7_352_000_000_000, "09/2026": 7_580_000_000_000}},
    "cho_vay_rb": {"ten": "Cho vay KHCN", "don_vi": "VND", "gia_tri": {
        "04/2026": 3_420_000_000_000, "05/2026": 3_510_000_000_000, "06/2026": 3_590_000_000_000,
        "07/2026": 3_700_000_000_000, "08/2026": 3_862_000_000_000, "09/2026": 4_065_000_000_000}},
    "giao_dich_ttqt": {"ten": "Số điện TTQT", "don_vi": "giao dịch", "gia_tri": {
        "04/2026": 418, "05/2026": 452, "06/2026": 439, "07/2026": 487, "08/2026": 471, "09/2026": 503}},
    "khieu_nai": {"ten": "Khiếu nại tiếp nhận", "don_vi": "hồ sơ", "gia_tri": {
        "04/2026": 61, "05/2026": 58, "06/2026": 72, "07/2026": 66, "08/2026": 54, "09/2026": 49}},
    "ty_le_no_xau": {"ten": "Tỷ lệ nợ xấu toàn hàng", "don_vi": "%", "gia_tri": {
        "04/2026": 1.62, "05/2026": 1.58, "06/2026": 1.66, "07/2026": 1.61, "08/2026": 1.55, "09/2026": 1.60}},
}

# Khiếu nại theo loại trong tháng — số liệu mô phỏng.
KHIEU_NAI = {
    "09/2026": [
        {"loai": "Chuyển tiền nhầm / chưa nhận", "so_luong": 18, "dung_han": 15, "thoi_gian_tb_ngay": 3.4},
        {"loai": "Giao dịch thẻ tranh chấp", "so_luong": 11, "dung_han": 9, "thoi_gian_tb_ngay": 21.0},
        {"loai": "ATM nuốt tiền / thẻ", "so_luong": 7, "dung_han": 7, "thoi_gian_tb_ngay": 1.8},
        {"loai": "Thu phí sai", "so_luong": 6, "dung_han": 6, "thoi_gian_tb_ngay": 1.2},
        {"loai": "Điện quốc tế chậm", "so_luong": 4, "dung_han": 2, "thoi_gian_tb_ngay": 12.5},
        {"loai": "Thái độ phục vụ", "so_luong": 3, "dung_han": 1, "thoi_gian_tb_ngay": 4.0},
    ],
}
KHIEU_NAI["08/2026"] = [{**r, "so_luong": r["so_luong"] + 1, "dung_han": r["dung_han"] + 1} for r in KHIEU_NAI["09/2026"]]


@mcp.tool()
def huy_dong_cho_vay_khcn(thang: str = KY_MAC_DINH) -> dict:
    """Huy động, kế hoạch huy động, cho vay, khách hàng mới và thẻ tín dụng mở mới của từng chi nhánh Khối KHCN trong một tháng (MM/YYYY)."""
    ky = _ky(thang)
    rows = KHCN.get(ky)
    if rows is None:
        return {"tim_thay": False, "thang": ky, "ky_co_san": sorted(KHCN)}
    out = [{**r, "ty_le_hoan_thanh_huy_dong": round(r["huy_dong"] / r["ke_hoach_huy_dong"], 4)} for r in rows]
    return {"tim_thay": True, "thang": ky, "so_chi_nhanh": len(out),
            "tong_huy_dong": sum(r["huy_dong"] for r in out), "tong_cho_vay": sum(r["cho_vay"] for r in out),
            "tong_khach_hang_moi": sum(r["khach_hang_moi"] for r in out), "chi_nhanh": out}


@mcp.tool()
def xu_huong_theo_thang(chi_tieu: str = "giai_ngan_eb", so_thang: int = 6) -> dict:
    """Chuỗi giá trị theo tháng của một chỉ tiêu để vẽ biểu đồ đường: giai_ngan_eb, huy_dong_rb, cho_vay_rb, giao_dich_ttqt, khieu_nai, ty_le_no_xau."""
    key = chi_tieu.strip().lower()
    row = XU_HUONG.get(key)
    if row is None:
        return {"tim_thay": False, "chi_tieu": chi_tieu, "ho_tro": list(XU_HUONG)}
    n = max(1, min(int(so_thang or 6), 6))
    items = list(row["gia_tri"].items())[-n:]
    dau, cuoi = items[0][1], items[-1][1]
    return {"tim_thay": True, "chi_tieu": key, "ten": row["ten"], "don_vi": row["don_vi"], "so_thang": n,
            "tang_truong_phan_tram": round((cuoi - dau) / dau * 100, 1) if dau else None,
            "theo_thang": [{"thang": t, "gia_tri": v} for t, v in items]}


@mcp.tool()
def khieu_nai_theo_loai(thang: str = KY_MAC_DINH) -> dict:
    """Số khiếu nại tiếp nhận, số giải quyết đúng hạn và thời gian xử lý trung bình theo từng loại trong một tháng (MM/YYYY)."""
    ky = _ky(thang)
    rows = KHIEU_NAI.get(ky)
    if rows is None:
        return {"tim_thay": False, "thang": ky, "ky_co_san": sorted(KHIEU_NAI)}
    out = [{**r, "qua_han": r["so_luong"] - r["dung_han"], "ty_le_dung_han": round(r["dung_han"] / r["so_luong"], 4)} for r in rows]
    tong = sum(r["so_luong"] for r in out)
    return {"tim_thay": True, "thang": ky, "tong_so": tong, "tong_dung_han": sum(r["dung_han"] for r in out),
            "ty_le_dung_han": round(sum(r["dung_han"] for r in out) / tong, 4) if tong else 0, "loai": out}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
