# Nội dung pitch — MSB Knowledge Assistant

> Bản PDF: `docs/slides/MSB-Knowledge-Assistant-pitch.pdf` (13 trang, khổ 16:9).
> Bản trình chiếu tương tác: mở `docs/slides/index.html` trong trình duyệt (phím ← → chuyển slide, N bật lời dẫn, F toàn màn hình, Ctrl/⌘+P in PDF). Bộ 13 slide có ảnh chụp màn hình thật từ bản deploy, mở bằng bài toán quản trị AI của ngân hàng rồi đi qua năm lớp quản trị của sản phẩm; tệp này giữ nội dung chi tiết và phần hỏi đáp.

13 slide, khoảng 9 phút nói cộng 5 phút demo. Mỗi slide ghi sẵn **nội dung đưa lên màn hình** và
**lời dẫn**. Con số trong đây đều lấy từ hệ thống đang chạy, không ước lượng.

---

## Slide 1 — Mở đầu

> # MSB Knowledge Assistant
> ### Hỏi quy trình, nhận câu trả lời kèm đúng Điều khoản
> Đội **[tên đội]** · MSB AI Hackathon
> Demo: `59-153-246-116.sslip.io`

**Lời dẫn:** "Chúng tôi làm một trợ lý tri thức nội bộ cho ngân hàng. Điểm khác biệt nằm ở chỗ nó
không chỉ trả lời, mà chỉ ra được câu trả lời dựa vào Điều nào của văn bản nào, phiên bản nào."

---

## Slide 2 — Bài toán

> **Một cán bộ RM muốn biết: hồ sơ này đủ điều kiện giải ngân chưa?**
>
> Hôm nay anh ấy phải:
> - Mở 3 văn bản, mỗi cái hàng trăm trang
> - Tự đoán bản nào còn hiệu lực
> - Mở tiếp BPM xem hồ sơ đang ở bước nào
> - Hoặc hỏi đồng nghiệp, nhanh nhưng không có vết
>
> **ChatGPT không giải được:** không đọc được văn bản nội bộ, không biết HS2026-0412 là gì,
> và đưa dữ liệu khách hàng ra ngoài.

**Lời dẫn:** Kể một tình huống cụ thể thay vì nói chung chung. Nhấn vào chỗ "không có vết" vì đó là
thứ Compliance quan tâm nhất.

---

## Slide 3 — Ba ràng buộc thật

> | | |
> |---|---|
> | **Trích dẫn được** | Trả lời sai một điều kiện giải ngân là rủi ro tín dụng thật |
> | **Phân quyền theo khối** | Văn bản EB không được rò sang Vận hành; khách hàng chỉ đọc kho công khai |
> | **Kiểm toán được** | Ai hỏi gì, máy trả lời gì, dựa trên văn bản nào |

**Lời dẫn:** "Ba ràng buộc này là lý do một con chatbot gắn API không đủ. Chúng quyết định toàn bộ
kiến trúc phía sau."

---

## Slide 4 — Giải pháp trong một hình

> ```
> Văn bản nội bộ ─► cắt theo Chương/Mục/Điều ─► pgvector
>                                                   │
> Cán bộ ──┐                                        ▼
> Khách ───┤
> Website ─┼──► che PII ──► RAG / Luồng / Agent ──► câu trả lời + [#trích dẫn]
> Extension┤                      │                        │
> Quản trị ┘                      ▼                        ▼
>                          hệ thống lõi, MCP          nhật ký truy vấn
> ```
>
> **Năm mặt tiếp xúc, một lõi, một nhật ký.**

**Lời dẫn:** "Cán bộ gặp trợ lý ở năm nơi khác nhau, nhưng đằng sau chỉ có một bộ luật phân quyền
và một nhật ký. Thêm kênh không có nghĩa là thêm lỗ hổng."

---

## Slide 5 — Thứ tạo ra khác biệt: cắt đoạn theo Điều

> **Cắt theo độ dài** → "theo tài liệu Quy trình cấp tín dụng…"
>
> **Cắt theo cấu trúc** → "**Điều 5, Quy trình cấp tín dụng KHDN v3.2, hiệu lực 01/03/2026**"
>
> Văn bản pháp lý Việt Nam có sẵn cây `Chương → Mục → Điều`.
> Mỗi đoạn mang breadcrumb, truy hồi đọc ngược ra để dựng trích dẫn.
>
> *Ảnh chụp: câu trả lời với 5 chip nguồn, mỗi chip ghi rõ Điều và ngày hiệu lực.*

**Lời dẫn:** "Đây là chi tiết kỹ thuật nhỏ nhưng quyết định việc cán bộ có dám dùng hay không. Cắt
đoạn thuần theo độ dài thì mất thông tin Điều, và không có cách nào khôi phục về sau."

---

## Slide 6 — Trợ lý chạm được vào hệ thống thật

> Không dừng ở đọc tài liệu. Trợ lý gọi được:
> - **API lõi** tra hồ sơ, hạn mức, xếp hạng rủi ro
> - **MCP server** hệ thống quản trị rủi ro, kho dữ liệu báo cáo
> - **Tính toán nghiệp vụ** lịch trả nợ, lãi tiền gửi, ngày làm việc
>
> **Thao tác ghi thì dừng lại chờ người duyệt.**
> *Ảnh chụp: thẻ vàng "Cần anh/chị xác nhận thao tác — Gia hạn hồ sơ HS2026-0518, 3 ngày".*

**Lời dẫn:** "AI không tự ghi dữ liệu vào hệ thống. Nó dừng, hiện đúng tham số, chờ cán bộ bấm
duyệt. Đây là điều kiện để đưa được vào môi trường ngân hàng."

---

## Slide 7 — Từ hỏi đáp tới việc chạy được

> | | |
> |---|---|
> | **Báo cáo** | Luồng báo cáo xuất Word/Excel, chạy nền, đặt lịch cron, gửi theo chức danh |
> | **Biểu mẫu** | Điền sẵn từ hệ thống lõi, AI soạn phần tự luận, xuất .docx |
> | **Xuất Excel bất kỳ** | "Xuất cái này ra Excel" — dựng .xlsx từ đúng nội dung đang trao đổi |
> | **Dựng luồng xử lý** | Mô tả bằng tiếng Việt, trợ lý vận hành dựng bản nháp luồng cho quản trị viên |
> | **Kỹ năng** | Bí kíp nghiệp vụ nạp khi cần, theo chuẩn mở Agent Skills, xuất nhập được |
> | **Bộ nhớ cá nhân** | Nhớ cách từng cán bộ làm việc, không bao giờ nhớ dữ liệu khách hàng |
>
> *Ảnh chụp: nút tải tệp ngay dưới câu trả lời trong khung chat.*

**Lời dẫn:** "Trợ lý không chỉ trả lời rồi thôi. Cán bộ xin báo cáo ngay trong chat và nhận file
Excel mở lên là tính được, không phải ảnh chụp bảng."

---

## Slide 7b — Trợ lý cho chính người vận hành

> **Ai hướng dẫn người quản trị hệ thống?**
>
> Bong bóng ở góc mọi trang quản trị:
> - Trả lời cách vận hành, **có trích dẫn** từ cẩm nang 12 tài liệu
> - Tra được trạng thái thật: văn bản lập chỉ mục lỗi, bộ lập lịch, token
> - **Mô tả bằng tiếng Việt → dựng ra luồng xử lý**
>
> *Ảnh chụp: thẻ "bản nháp, chưa lưu" liệt kê từng bước, kèm nút Tạo luồng.*
>
> ### Nó không tự lưu gì cả
> AI đề xuất, người vận hành bấm nút, và luồng được tạo bằng quyền của chính họ.

**Lời dẫn:** "Đây là chỗ chúng tôi tự tin nhất. Quản trị viên nghiệp vụ không phải lập trình viên,
nhưng mô tả một câu là có luồng chạy được. Mẹo kỹ thuật: mô hình không vẽ đồ thị, nó chỉ liệt kê
các bước, còn máy chủ mới nối cạnh và kiểm. Nhờ vậy nó đúng ngay lần đầu thay vì sai lung tung."

---

## Slide 8 — An toàn ở mức mã nguồn

> Không tin vào việc mô hình sẽ ngoan.
>
> | Lớp | Làm gì |
> |---|---|
> | Che PII | Presidio + nhận dạng tiếng Việt: CCCD, số tài khoản, CIF, OTP. **Số tiền và ngày tháng giữ nguyên** |
> | Chống tiêm prompt | Văn bản và kết quả công cụ bọc trong khối dữ liệu, ảnh và HTML bị lọc |
> | Bộ lọc đầu ra | Phát hiện rò rỉ system prompt thì cắt luồng |
> | Phân quyền | Kiểm ở máy chủ, không phải ẩn nút trên giao diện |
>
> ### Red team: 22 kịch bản tấn công, chặn 22
> Tiêm prompt qua văn bản, qua endpoint công cụ độc hại, đòi lộ system prompt, SSRF qua tham số
> công cụ, vượt bước duyệt, rò dữ liệu sang khối khác.

**Lời dẫn:** "Chúng tôi tự tấn công hệ thống của mình 22 kiểu. Slide này là thứ tôi muốn ban giám
khảo nhớ nhất, vì nó là khác biệt giữa một demo và một thứ dám đưa vào ngân hàng."

---

## Slide 9 — Kiến trúc

> *Chèn sơ đồ mermaid từ `README.md` mục 5.*
>
> | | |
> |---|---|
> | Web | Next.js 16 · React 19 |
> | API | FastAPI · async SQLAlchemy · 125 endpoint · 25 bảng · 28 migration |
> | Vector | Postgres 16 + pgvector, 1536 chiều |
> | Nền | Redis + RQ: worker lập chỉ mục, worker báo cáo, bộ lập lịch |
> | Mô hình | **GreenNode MaaS (VNG Cloud)** · `google/gemma-4-31b-it` |
> | Agent | LangGraph có checkpointer Postgres để dừng chờ duyệt |

**Lời dẫn:** "Mô hình chạy trên GreenNode MaaS của VNG như quy định. Lớp provider theo chuẩn
OpenAI nên đổi sang model khác chỉ là đổi một dòng cấu hình trong giao diện quản trị."

---

## Slide 10 — Kết quả

> ### Đã chạy thật trên server, không phải localhost
> `https://59-153-246-116.sslip.io`
>
> | | |
> |---|---|
> | Mã nguồn | ~36.600 dòng · 21.700 Python · 14.900 TypeScript |
> | Kiểm thử API chạy thật | **19 bộ, 0 lỗi** |
> | Toàn tuyến đầu cuối | **67/67** |
> | Tấn công đối kháng | **22/22** |
> | Kiểm thử đơn vị | **174 ca** |
> | Kiểm thử trình duyệt | **7 spec** Playwright, gồm nạp Chrome extension thật |
>
> Dữ liệu demo: 4 khối · 5 kho tri thức · 30 văn bản mô phỏng · 12 trợ lý · 25 công cụ · 5 báo cáo Excel có biểu đồ · 4 biểu mẫu · 9 kỹ năng

**Lời dẫn:** "Mọi con số này chạy trên bản deploy, không phải mock. Ban giám khảo bấm vào link là
thao tác được ngay bằng tài khoản chúng tôi gửi kèm."

---

## Slide 11 — Hướng mở rộng

> 1. **Embedding chuyển sang GreenNode** khi platform có model embedding
> 2. **Hỏi kèm ảnh** — đã kiểm chứng Gemma trên GreenNode đọc được ảnh; cần thêm lớp che PII cho ảnh chứng từ
> 3. **Đo chất lượng tự động** — bộ câu hỏi vàng chạy định kỳ, đo tỉ lệ trích dẫn đúng Điều
> 4. **SSO nội bộ** thay mật khẩu riêng
> 5. **Gửi báo cáo qua email và webhook**
>
> Mở rộng nghiệp vụ: mỗi khối tự tạo kho tri thức và trợ lý của mình mà không cần lập trình viên.

**Lời dẫn:** "Nền tảng đã đa đơn vị từ đầu, nên mở rộng sang khối mới là việc cấu hình chứ không
phải việc code."

---

## Slide 12 — Chốt

> ### Trợ lý trả lời có trích dẫn, chạm được hệ thống, và để lại vết
>
> - Demo: `59-153-246-116.sslip.io`
> - Mã nguồn + hướng dẫn chạy: repo, `README.md`
> - **Không dùng dữ liệu thật của MSB, TNTalent hay TNEX**
>
> Xin cảm ơn.

---

## Phụ lục — câu hỏi hay gặp

| Câu hỏi | Trả lời ngắn |
|---|---|
| Văn bản mới, cập nhật thế nào? | Tải lên là tự lập chỉ mục. Văn bản cũ tắt một nút, mọi đường trả lời ngừng dùng ngay |
| Model trả lời sai thì sao? | Mỗi câu có trích dẫn để đối chiếu; cán bộ bấm 👎 kèm lý do, Compliance lọc được đúng các lượt đó |
| Chi phí kiểm soát ra sao? | Mỗi lượt gọi mô hình ghi một dòng token theo thành phần, kênh, khối và trợ lý; có trang thống kê riêng |
| Dữ liệu khách hàng có ra ngoài không? | Che PII chạy trước khi câu hỏi tới mô hình; vì vậy công cụ được thiết kế quanh mã nghiệp vụ chứ không phải CIF hay số tài khoản |
| Bao lâu thì thêm được một khối mới? | Tạo đơn vị, tạo kho, tải văn bản, tạo trợ lý. Không cần lập trình viên |
| Vì sao không dùng thẳng một sản phẩm có sẵn? | Ba ràng buộc ở slide 3: trích dẫn tới Điều, phân quyền theo khối, và nhật ký kiểm toán |
