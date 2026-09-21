"""Kiểm thử đặc tả (golden) cho đường văn bản của bộ cắt đoạn `chunk_text`.

Sắp thêm một đường xử lý riêng cho bảng tính vào worker. Đường văn bản cũ (PDF/DOCX/TXT →
`chunk_text`) không được đổi khi thêm đường bảng tính: các test này ghim hành vi HIỆN TẠI,
nên bất kỳ thay đổi vô tình nào ở cách cắt tiêu đề, breadcrumb, cửa sổ 1000 ký tự hay phần
gối 200 ký tự đều làm test đỏ.

Tệp golden được sinh MỘT LẦN từ mã hiện tại (chạy từ gốc repo), không có công tắc nào trong
test để sinh lại — nếu hành vi đổi có chủ đích thì sinh lại bằng tay và xem diff:

    cd apps/worker && PYTHONUTF8=1 ../api/.venv/Scripts/python.exe -c "import json; from tests.test_chunker_golden import INPUT; from worker.pipeline.chunker import chunk_text; json.dump([[c.chunk_index, c.section, c.content] for c in chunk_text(INPUT)], open('tests/golden/chunk_text_v1.json', 'w', encoding='utf-8', newline='\n'), ensure_ascii=False, indent=1)"

Run: apps/api/.venv/Scripts/python.exe -m pytest apps/worker/tests -q
(từ gốc repo; chạy riêng với apps/api/tests vì cả hai gói đều tên là `tests`)
"""

import json
from pathlib import Path

from worker.pipeline.chunker import chunk_text

GOLDEN = Path(__file__).parent / "golden" / "chunk_text_v1.json"

# Viết bằng chuỗi có "\r\n" dạng escape để git autocrlf không thể đổi đầu vào.
INPUT = (
    # Phần mở đầu chưa có tiêu đề nào → chunk không có section.
    "NGÂN HÀNG THƯƠNG MẠI CỔ PHẦN MẪU\r\n"
    "Quy trình này áp dụng cho toàn bộ chi nhánh và phòng giao dịch trong hệ thống.\r\n"
    "\r\n"
    # Lồng CHƯƠNG → Mục → Điều.
    "CHƯƠNG I QUY ĐỊNH CHUNG\r\n"
    "Chương này nêu phạm vi và đối tượng áp dụng.\r\n"
    "Mục 1 Phạm vi điều chỉnh\r\n"
    "Mục này mô tả các nghiệp vụ tín dụng thuộc phạm vi quy trình.\r\n"
    "Điều 1. Đối tượng áp dụng\r\n"
    "Khách hàng cá nhân và doanh nghiệp có quan hệ tín dụng với ngân hàng.\r\n"
    # Tiêu đề đánh số + thân; có tab và khoảng trắng kép.
    "1. Hồ sơ vay vốn\r\n"
    "Hồ sơ gồm\tgiấy đề nghị vay vốn,  phương án sử dụng vốn\tvà tài liệu về tài sản bảo đảm.\r\n"
    # Mục đánh số giống câu (kết thúc bằng dấu chấm) → vẫn nằm trong thân.
    "2. Cán bộ tín dụng kiểm tra tính đầy đủ của hồ sơ trong vòng hai ngày làm việc.\r\n"
    "Sau khi kiểm tra, hồ sơ được chuyển cho bộ phận thẩm định.\r\n"
    # Một mục có thân dài hơn 1000 ký tự → cửa sổ và phần gối 200 ký tự.
    "Điều 2. Thẩm định khoản vay\r\n"
    "Bộ phận thẩm định đánh giá năng lực tài chính của khách hàng dựa trên báo cáo tài chính "
    "ba năm gần nhất, sao kê tài khoản sáu tháng và các nguồn thu nhập hợp pháp khác. "
    "Đối với khách hàng doanh nghiệp, cán bộ thẩm định phải phân tích dòng tiền từ hoạt động "
    "kinh doanh, hệ số thanh toán hiện hành, hệ số nợ trên vốn chủ sở hữu và vòng quay hàng "
    "tồn kho. Đối với khách hàng cá nhân, thu nhập được xác minh qua hợp đồng lao động, bảng "
    "lương có xác nhận của đơn vị chi trả hoặc sao kê tài khoản nhận lương.\r\n"
    "Tài sản bảo đảm được định giá bởi bộ phận định giá độc lập hoặc tổ chức thẩm định giá "
    "nằm trong danh sách được ngân hàng chấp thuận. Giá trị định giá có hiệu lực tối đa sáu "
    "tháng kể từ ngày lập chứng thư. Tỷ lệ cho vay tối đa trên giá trị tài sản bảo đảm là bảy "
    "mươi phần trăm đối với bất động sản và năm mươi phần trăm đối với phương tiện vận tải.\r\n"
    "Kết quả thẩm định được lập thành báo cáo theo mẫu thống nhất, nêu rõ ý kiến đề xuất cho "
    "vay hoặc từ chối, các điều kiện kèm theo và các rủi ro chính đã được nhận diện. Báo cáo "
    "phải có chữ ký của cán bộ thẩm định và trưởng bộ phận thẩm định trước khi trình cấp phê "
    "duyệt. Trường hợp khoản vay vượt thẩm quyền của chi nhánh, hồ sơ được chuyển lên hội sở "
    "để hội đồng tín dụng xem xét trong thời hạn năm ngày làm việc.\r\n"
    # Tiêu đề dài hơn 110 ký tự → breadcrumb bị cắt và kết thúc bằng "…".
    "Điều 3. Quy định về việc giải ngân, kiểm tra sau giải ngân và xử lý các trường hợp khách "
    "hàng sử dụng vốn vay sai mục đích đã cam kết\r\n"
    "Việc giải ngân chỉ được thực hiện khi khách hàng đã hoàn tất thủ tục bảo đảm tiền vay.\r\n"
)


def test_golden():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    actual = [[c.chunk_index, c.section, c.content] for c in chunk_text(INPUT)]

    assert actual == golden


def test_empty():
    assert chunk_text("") == []
    assert chunk_text("  \n\t ") == []


def test_prefix_invariant():
    chunks = chunk_text(INPUT)

    assert all(c.content.startswith(f"[{c.section}] ") for c in chunks if c.section)
