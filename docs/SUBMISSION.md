# Hồ sơ dự thi — MSB AI Hackathon

Tài liệu này gom đúng ba thành phần ban tổ chức yêu cầu, kèm tài khoản để giám khảo tự thao tác.

| # | Thành phần | Ở đâu |
|---|---|---|
| 01 | **Link sản phẩm demo** | https://59-153-246-116.sslip.io — tài khoản ở mục 2 bên dưới |
| 02 | **Git repo** | Chính repo này. Cách chạy: [`README.md`](../README.md) mục 4 |
| 03 | **Pitch deck** | Nội dung từng slide: [`PITCH_DECK.md`](PITCH_DECK.md) |

---

## 1. Tuân thủ quy định cuộc thi

| Quy định | Cách đáp ứng |
|---|---|
| Dùng **GreenNode AI Agent Platform / API Keys / AI Model do platform cung cấp** | LLM chạy trên **GreenNode MaaS (VNG Cloud AI Platform)**, endpoint `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1`, model `google/gemma-4-31b-it` do platform cấp. Khai báo trong Quản trị → Cài đặt AI, provider **"GreenNode MaaS — VNG Cloud"**. Hai model khác của platform (`qwen/qwen3.6-flash`, `z-ai/glm-5.2-hackathon`) đã có sẵn trong danh sách chọn. |
| | *Ngoại lệ có lý do:* **embedding** dùng OpenRouter `openai/text-embedding-3-small`, vì endpoint MaaS chỉ expose 3 model chat, không có model embedding (kiểm chứng bằng `GET /v1/models`). Đổi sang embedding của platform chỉ cần thêm một dòng trong Quản trị → Cài đặt AI, không phải sửa mã. |
| Deploy lên nền tảng public | Đã deploy lên VPS công khai, HTTPS qua Caddy: https://59-153-246-116.sslip.io |
| **KHÔNG dùng dữ liệu thật của MSB / TNTalent / TNEX** | 30 văn bản nghiệp vụ trong `apps/api/seed_data/docs/` do nhóm tự viết theo văn phong MSB, mỗi tệp mang dòng "TÀI LIỆU MÔ PHỎNG". 3 hệ thống trong `demo-mock/` sinh số liệu giả (hồ sơ, điện SWIFT, khiếu nại, kho dữ liệu báo cáo, sàng lọc cấm vận). Bản deploy được reset về đúng bộ seed này bằng `remote.sh reset-demo`. Không có dữ liệu thật nào trong repo hay trên server. Quy tắc này ghi thành ràng buộc trong `CLAUDE.md` để không ai vô tình vi phạm. |

## 2. Tài khoản demo

Mật khẩu chung cho tài khoản nghiệp vụ: `demo123`.

| Vai trò | Đăng nhập tại | Tài khoản | Xem được gì |
|---|---|---|---|
| **Super admin / Compliance** | `/login` | `admin@querion.io` · *(mật khẩu gửi kèm bài nộp)* | Toàn bộ: kho tri thức, trợ lý, luồng, công cụ, nhật ký, token |
| **Cán bộ RM** (Khối KHDN) | `/staff/login` | `rm.an@msb-demo.vn` | Trợ lý tín dụng, hỏi có trích dẫn, xin báo cáo, điền biểu mẫu |
| **Cán bộ CA** (Khối KHDN) | `/staff/login` | `ca.binh@msb-demo.vn` | Cùng đơn vị, để thấy hộp báo cáo là riêng từng người |
| **Giao dịch viên** (Khối Vận hành) | `/staff/login` | `gdv.cuong@msb-demo.vn` | Chỉ thấy trợ lý đơn vị mình, để thấy phân quyền |
| **Admin đơn vị** | `/login` | `admin.eb@msb-demo.vn` | Chỉ quản trị Khối KHDN |
| **Khách hàng** | không cần đăng nhập | link `/kh/...` in ra ở cuối lệnh seed | Hỏi biểu phí, sản phẩm |

Website mô phỏng có bong bóng chat nhúng: https://demo.59-153-246-116.sslip.io
(trang chủ dành cho khách hàng, `/intranet.html` dành cho cán bộ).

## 3. Đề xuất đường đi cho giám khảo (10 phút)

1. **Cán bộ hỏi nghiệp vụ.** Vào `/staff/login` bằng `rm.an`, chọn *Trợ lý Tín dụng KHDN*, hỏi
   *"Điều kiện giải ngân cho khách hàng doanh nghiệp có TSBĐ?"*. Chú ý phần **Nguồn trích dẫn**:
   mỗi đoạn chỉ đúng Điều và ngày hiệu lực.
2. **Trợ lý tra hệ thống và xin duyệt.** Đổi sang *Trợ lý Hồ sơ Tín dụng*, hỏi
   *"Hạn mức còn lại và xếp hạng rủi ro của hồ sơ HS2026-0518?"* rồi
   *"Gia hạn hồ sơ HS2026-0518 thêm 3 ngày"* — thao tác ghi dừng lại chờ bấm duyệt.
3. **Xuất Excel.** Gõ *"Cho tôi báo cáo kinh doanh tháng 09/2026 bản Excel"* — có nút tải tệp
   ngay dưới câu trả lời, mở lên là số liệu dùng được, không phải ảnh chụp bảng.
4. **Phân quyền.** Đăng nhập `gdv.cuong` để thấy danh sách trợ lý khác hẳn.
5. **Compliance.** Vào `/login` bằng tài khoản admin → **Nhật ký truy vấn**, mở một lượt hỏi để
   xem người hỏi, câu trả lời đầy đủ, các nguồn, từng bước xử lý và số token đã dùng.
6. **Che PII.** Hỏi kèm một số CCCD hoặc số tài khoản bất kỳ, xem nhật ký: con số đã bị thay bằng
   nhãn trước khi tới mô hình.
7. **Trợ lý Vận hành.** Vẫn ở trang quản trị, mở **bong bóng góc phải dưới**. Hỏi *"Vì sao văn bản
   của tôi lập chỉ mục lỗi?"* để thấy nó trả lời có trích dẫn từ cẩm nang vận hành. Rồi vào
   `/workflows` và gõ *"Dựng luồng: tra kho tín dụng rồi soạn prompt và sinh câu trả lời"* — nó
   dựng **bản nháp luồng** kèm nút tạo. Bấm tạo, mở canvas, bấm Chạy thử. Trợ lý soạn nháp;
   người vận hành là người bấm nút.

Kịch bản đầy đủ 10 phút kèm lời dẫn: [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).

## 4. Bằng chứng chất lượng

Chạy thật trên bản deploy server, không phải mock. Lệnh và số liệu chi tiết ở
[`README.md`](../README.md) mục 7.

| | |
|---|---|
| Bộ kiểm thử API chạy thật | **19 bộ, 0 lỗi** (bộ seed chuẩn 61/61, e2e 67/67, kỹ năng 44/44, bộ nhớ 42/42, trợ lý vận hành 40/40, công cụ 39/39, xuất Excel 36/36, biểu mẫu 32/32, lịch chạy 28/28, …); 16 bộ chạy thẳng vào bản deploy này ngay sau khi reset về bộ seed chuẩn |
| Tấn công đối kháng | **22/22** chặn được |
| Kiểm thử đơn vị | **174 ca** |
| Kiểm thử trình duyệt | **7 spec** Playwright, gồm nạp Chrome extension thật vào Chromium và bong bóng trợ lý vận hành |

## 5. Giới hạn đã biết

Nói trước để giám khảo không phải tự phát hiện:

- **Embedding chưa chạy trên GreenNode** vì endpoint MaaS chưa có model embedding (xem mục 1).
- **Trợ lý Vận hành chỉ soạn nháp, không tự sửa cấu hình.** Đây là lựa chọn có chủ đích chứ không
  phải thiếu tính năng: một câu hiểu nhầm không được phép đổi cấu hình sản xuất.
- **Che PII chỉ áp dụng cho chữ.** Hệ thống chưa nhận ảnh trong chat; nếu mở tính năng đó thì cần
  thêm lớp che PII trên ảnh.
- **`code_execute` trong luồng xử lý không phải sandbox thật**, nên mặc định tắt bằng biến môi
  trường và không dùng trong bản demo.
- **Cờ bật extension cho từng trợ lý là kiểm soát sản phẩm, không phải hàng rào bảo mật** với
  chính cán bộ, vì họ vốn đã có token. Ranh giới thật vẫn là phân quyền theo đơn vị.
- **Giới hạn tần suất fail-open**: nếu Redis chết thì cho request đi qua thay vì chặn, đây là lựa
  chọn có chủ đích để demo không gãy, production nên đổi thành fail-closed.
