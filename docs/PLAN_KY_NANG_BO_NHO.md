# Plan: Kỹ năng (Skill) và Bộ nhớ (Memory) cho trợ lý

Nghiên cứu hai tính năng, mỗi tính năng xét trên ba lớp: **kiến trúc**, **UI UX**, và **nghiệp vụ
ngân hàng**. Kết luận trước, chi tiết sau.

---

## 0. Kết luận ngắn

| | Kỹ năng | Bộ nhớ |
|---|---|---|
| Làm được không | Có, lắp trên agent và bộ công cụ sẵn có | Có, nhưng **phải thu hẹp cố ý** vì dữ liệu cá nhân |
| Nó là gì trong app này | Bí kíp nghiệp vụ tái sử dụng, nạp **khi cần** thay vì nhồi vào system prompt | Trợ lý nhớ **cách làm việc của cán bộ**, không nhớ khách hàng, không nhớ quy định |
| Chuẩn bám theo | Agent Skills, chuẩn mở tại agentskills.io, để xuất nhập được với Claude, Codex, Copilot | Nguyên tắc UX bộ nhớ đã thành mặc định ở ChatGPT và Claude: thấy được, sửa được, xoá được, tạm dừng được |
| Hiện trạng | Không có. "Kiến thức cách làm" hiện chỉ có chỗ chứa là `system_prompt`, luôn nạp toàn bộ | Chỉ có 10 tin nhắn gần nhất của **một** hội thoại. Sang hội thoại mới là quên hết |
| Rủi ro lớn nhất | Kỹ năng chồng chéo làm mô hình kích hoạt nhầm | Bộ nhớ biến thành nguồn sự thật thay cho văn bản, hoặc chứa dữ liệu khách hàng |
| Ước tính | 2,5 ngày | 3 ngày |

Một ranh giới xuyên suốt cả hai: **văn bản mới là nguồn sự thật về quy định**. Kỹ năng chỉ dạy cách
làm việc với văn bản, bộ nhớ chỉ nhớ người hỏi thích làm việc thế nào. Không cái nào được thay
thế trích dẫn.

---

## 1. Kỹ năng

### 1.1 Vì sao cần, và nó khác gì ba thứ đã có

App có ba cách "dạy" trợ lý, mỗi cách một chỗ hở:

| Cách hiện có | Bản chất | Chỗ hở |
|---|---|---|
| `system_prompt` | Luôn nạp, toàn bộ | Mỗi lần thêm một bí kíp là prompt dài thêm, cho **mọi** câu hỏi kể cả câu không liên quan |
| Công cụ | Một hàm có tham số | Không dạy được "cách suy nghĩ", chỉ trả dữ liệu |
| Luồng xử lý | Đồ thị cố định | Cứng; một câu lệch khỏi kịch bản là hỏng |

Kỹ năng lấp đúng chỗ hở đầu tiên. Nó là một **bí kíp có điều kiện**: mô hình chỉ thấy tên và một
câu "dùng khi nào" của mọi kỹ năng, và chỉ đọc toàn văn kỹ năng nào khớp câu hỏi. Chuẩn Agent Skills
gọi đây là nạp dần theo ba mức: siêu dữ liệu khoảng 100 token mỗi kỹ năng, toàn văn dưới 5000 token
khi kích hoạt, tài liệu tham chiếu chỉ khi cần. Trợ lý có thể "biết" ba mươi kỹ năng với chi phí
ngữ cảnh ít hơn một kỹ năng đang mở.

Ví dụ nghiệp vụ: một RM hỏi "hồ sơ này đủ điều kiện giải ngân chưa". Không có kỹ năng, trợ lý tra
kho rồi tóm tắt điều khoản. Có kỹ năng "Kiểm tra điều kiện giải ngân", nó đi theo đúng checklist mà
CPC đang dùng: hồ sơ trên BPM ở trạng thái nào, TSBĐ đã hoàn thiện chưa, chứng từ nào còn thiếu,
rồi kết luận "chưa đủ vì thiếu X", và **vẫn trích dẫn Điều** vì kỹ năng bảo nó phải làm vậy.

### 1.2 Mô hình dữ liệu

Bám theo bảng `tools` vì cùng bài toán quản trị: thuộc đơn vị, chia sẻ toàn ngân hàng cần owner,
gắn vào trợ lý qua bảng nối.

```
skills
  id, workspace_id, slug (a-z0-9-, ≤64, theo chuẩn), name (tiếng Việt), description (≤1024, "dùng khi nào"),
  body (markdown, ≤500 dòng), version, effective_from, status (draft|published),
  share_scope (unit|bank), allow_customer (bool),
  allowed_tool_ids (jsonb), preferred_dataset_ids (jsonb), reference_document_ids (jsonb),
  created_by, approved_by, created_at, updated_at
app_skills (app_id, skill_id, position)
```

- `slug` theo đúng ràng buộc của chuẩn để **xuất được ra thư mục `SKILL.md`** và nhập từ thư mục về.
  Đây là điểm ăn tiền khi trình bày: kỹ năng viết cho trợ lý MSB chạy được trên mọi agent theo chuẩn.
- `reference_document_ids` trỏ vào văn bản trong kho tri thức. Kỹ năng **phải** dựa trên văn bản có
  thật, và Compliance xem được nó dựa trên gì.
- `allow_customer` mặc định tắt, như công cụ. Kỹ năng cho khách hàng phải được owner mở riêng.

### 1.3 Runtime: hai đường kích hoạt

**Mức 1, luôn nạp.** Khối `KỸ NĂNG SẴN CÓ` trong system prompt, mỗi dòng một kỹ năng:
`- kiem-tra-dieu-kien-giai-ngan: <description>`. Khoảng 80 token mỗi dòng.

**Mức 2, kích hoạt.** Hai cách, dùng cả hai vì app có hai loại trợ lý:

| Trợ lý | Cách kích hoạt | Vì sao |
|---|---|---|
| Có agent | Công cụ nội bộ `kich_hoat_ky_nang(slug)` trả toàn văn về dưới dạng khối dữ liệu | Mô hình tự quyết, đúng tinh thần chuẩn; dùng lại đúng seam của ops tools |
| RAG thuần, không agent | **Chọn trước ở máy chủ**: embed câu hỏi, so với embedding của `description`, khớp trên ngưỡng thì nạp toàn văn vào prompt luôn | Không tốn thêm một vòng gọi mô hình, giữ độ trễ cho kênh cán bộ và khách hàng |

Kỹ năng đang mở làm ba việc với ngữ cảnh: chèn `body` vào system prompt; nếu có
`preferred_dataset_ids` thì truy hồi ưu tiên kho đó; nếu có `allowed_tool_ids` thì chỉ mời mô hình các
công cụ đó. Mỗi lần kích hoạt ghi một `run_steps` loại `skill_activate` với slug và điểm khớp, nên
nhật ký truy vấn trả lời được câu "câu này trợ lý làm theo bí kíp nào".

### 1.4 UI UX

**Trang `/skills`**, cùng khuôn với `/tools`: bảng có cột tên, "dùng khi nào", phiên bản, hiệu lực,
phạm vi, trạng thái, số trợ lý đang gắn.

**Trình soạn kỹ năng**, đây là chỗ quyết định chất lượng:

- Tên tiếng Việt, slug tự sinh và sửa được, báo lỗi ngay nếu vi phạm chuẩn.
- Ô "Dùng khi nào" có **thước đo chất lượng**: dưới 60 ký tự hoặc không có từ khoá nghiệp vụ thì
  cảnh báo, kèm ví dụ tốt và ví dụ tệ lấy đúng từ chuẩn. Đây là trường quyết định kích hoạt đúng hay
  nhầm, nên đáng đầu tư UX nhất.
- Thân bài có sẵn khung năm mục: *Khi nào dùng · Các bước · Quy tắc bắt buộc · Ví dụ hỏi đáp · Trường
  hợp đặc biệt*. Đếm dòng, cảnh báo khi vượt 500.
- Chọn văn bản tham chiếu từ kho tri thức, chọn kho ưu tiên, chọn công cụ được phép.
- **Cảnh báo chồng chéo**: khi lưu, so embedding của "dùng khi nào" với các kỹ năng khác trong cùng
  đơn vị; quá giống thì hiện "Kỹ năng này dễ bị nhầm với X". Chặn từ gốc rủi ro lớn nhất.
- **Thử kỹ năng** ngay trong trang: gõ một câu, thấy điểm khớp và kỹ năng nào sẽ được kích hoạt. Không
  cần gắn vào trợ lý mới thử được.
- Xuất thư mục `SKILL.md` dạng zip, nhập ngược lại.

**Trang trợ lý** thêm tab `🎯 Kỹ năng`, giao diện giống tab Công cụ: tick để gắn, kéo để đổi thứ tự.
Trợ lý khách hàng chỉ thấy kỹ năng có `allow_customer`.

**Trong khung chat**, câu trả lời có kỹ năng thì hiện chip nhỏ dưới câu trả lời, cạnh chip công cụ:
`🎯 Kiểm tra điều kiện giải ngân`. Bấm vào thấy "dùng khi nào" và văn bản tham chiếu. Cán bộ hiểu
vì sao trợ lý trả lời theo kiểu đó, Compliance bấm từ nhật ký cũng thấy đúng chip ấy.

### 1.5 Nghiệp vụ

- Kỹ năng đối xử **như một văn bản hướng dẫn**: có phiên bản, ngày hiệu lực, người soạn, người duyệt.
  Đơn vị nào cũng có SOP; kỹ năng là SOP viết cho trợ lý.
- Chia sẻ toàn ngân hàng cần **owner** duyệt, như công cụ. Kỹ năng của Khối Tín dụng không tự trôi
  sang Khối Vận hành.
- Kỹ năng **không được** chứa số liệu quy định. Câu "hạn mức tối đa 70% giá trị TSBĐ" phải nằm trong
  văn bản để trích dẫn, kỹ năng chỉ nói "tra tỉ lệ cho vay tối đa trong Quy định TSBĐ rồi so với hồ
  sơ". Nếu không, đổi quy định là kỹ năng sai âm thầm. Trình soạn có gợi ý nhắc điều này.
- Bốn kỹ năng seed, mỗi cái gắn với văn bản mô phỏng đã có:

| Kỹ năng | Đơn vị | Tham chiếu |
|---|---|---|
| Kiểm tra điều kiện giải ngân | EB | Hướng dẫn giải ngân v1.4, Quy định TSBĐ v2.1 |
| Soạn thông báo bổ sung hồ sơ tín dụng | EB | Quy trình cấp tín dụng KHDN v3.2, công cụ tra hồ sơ |
| Tra soát điện chuyển tiền quốc tế | OPS | Hướng dẫn TTR v2.0, MCP quản trị rủi ro |
| Giải thích biểu phí cho khách hàng | RB, cho khách | Biểu phí dịch vụ 2026.1 |

---

## 2. Bộ nhớ

### 2.1 Ba tầng, ba chủ sở hữu, ba vòng đời

Gọi chung là "bộ nhớ" nhưng là ba thứ khác nhau. Gộp lại là sai ở cả kỹ thuật lẫn pháp lý.

| Tầng | Nhớ gì | Ai sở hữu | Sống bao lâu | Hiện trạng |
|---|---|---|---|---|
| **Bộ nhớ làm việc** | Diễn biến của hội thoại đang mở | Hội thoại | Đến khi đóng | Có, nhưng cắt cứng 10 tin |
| **Bộ nhớ cá nhân** | Cán bộ làm việc thế nào: vai trò, phạm vi, thói quen trình bày, bối cảnh công việc đang theo | **Cán bộ** | 180 ngày, gia hạn khi dùng, xoá được bất cứ lúc nào | Không có |
| **Bộ nhớ tổ chức** | Điều cả đơn vị muốn trợ lý nhớ | Đơn vị | Theo phiên bản | **Không xây**, xem 2.2 |

**Bộ nhớ làm việc** chỉ cần sửa nhỏ: khi hội thoại vượt 10 tin thì tóm tắt phần cũ thành một đoạn
lưu ở `conversations.summary`, nạp đoạn đó thay cho việc cắt phăng. Hội thoại dài về một hồ sơ
không còn "quên đầu quên đuôi".

**Bộ nhớ cá nhân** là trọng tâm của plan này.

### 2.2 Quyết định quan trọng nhất: không xây bộ nhớ tổ chức tự học

Cám dỗ lớn là để trợ lý "học" từ mọi cán bộ rồi dùng cho mọi người. Trong ngân hàng đó là đường
thẳng tới sai phạm: một cán bộ nói sai, trợ lý nhớ, ngày mai nói lại với người khác như sự thật,
không có trích dẫn, không ai duyệt. Điều đơn vị muốn trợ lý nhớ đã có hai chỗ đúng để đặt: **văn
bản** trong kho tri thức và **kỹ năng** ở mục 1. Cả hai đều có phiên bản và người duyệt. Bộ nhớ
không được là đường tắt vòng qua hai chỗ đó.

Ràng buộc viết thẳng vào prompt: *bộ nhớ chỉ dùng để chọn giọng, độ dài, phạm vi và bối cảnh; mọi
điều về quy định vẫn phải lấy từ tài liệu và trích dẫn.*

### 2.3 Được nhớ gì, không được nhớ gì

Đây là phần nghiệp vụ, và phải cứng bằng mã chứ không bằng lời dặn mô hình.

| Loại | Ví dụ | Xử lý |
|---|---|---|
| **Cách trình bày** | "thích ngắn gọn", "muốn có bước đánh số", "hay dùng tiếng Anh cho thuật ngữ" | Nhớ |
| **Vai trò và phạm vi** | "RM phụ trách KHDN FDI tại chi nhánh Hà Nội" | Nhớ; phần vai trò lấy sẵn từ hồ sơ cán bộ, không cần trích |
| **Bối cảnh công việc** | "đang theo hồ sơ HS2026-0412 chờ CCO2" | Nhớ **theo mã hồ sơ**, hết hạn sau 30 ngày |
| **Thuật ngữ riêng** | "gọi Khối Vận hành là OPS" | Nhớ |
| Dữ liệu khách hàng | tên, CIF, số tài khoản, số tiền của một khách | **Từ chối ghi** |
| Kết quả nghiệp vụ | "hồ sơ X được duyệt", "khách Y bị từ chối" | **Từ chối ghi** |
| Thông tin về đồng nghiệp | "chị Lan hay duyệt chậm" | **Từ chối ghi** |
| Nội dung văn bản | "tỉ lệ cho vay tối đa 70%" | **Từ chối ghi**, đó là việc của kho tri thức |

Ba lớp chặn, thứ tự từ chắc tới mềm:

1. `mask_pii` đã chạy trước mọi thứ. Bản ghi nhớ chứa bất kỳ nhãn che nào, kiểu `[SỐ TÀI KHOẢN]`,
   bị loại ngay, không cần hỏi mô hình.
2. Bộ trích xuất trả JSON có `category` trong bốn loại được phép; loại khác bị loại. Prompt trích xuất
   được dặn rõ: chỉ ghi về **người đang hỏi**, không ghi về khách hàng, đồng nghiệp hay quy định.
3. Bộ lọc mẫu cho tên riêng đi kèm chữ "khách", "anh", "chị" và cho số tiền.

Khách hàng **không có bộ nhớ dài hạn**. Họ không có tài khoản, và Luật Bảo vệ dữ liệu cá nhân số
91/2025/QH15, hiệu lực từ 1/1/2026, cho họ quyền được biết, đồng ý, truy cập, sửa và xoá; giữ bất kỳ
thứ gì của một người ẩn danh là gánh nợ pháp lý không có cách trả. Kênh khách hàng chỉ có bộ nhớ
làm việc trong phiên.

### 2.4 Kiến trúc

**Lưu ở đâu.** LangGraph có `AsyncPostgresStore` sẵn trong venv, có tìm kiếm ngữ nghĩa và không gian
tên. Nhưng nó tạo bảng riêng ngoài Alembic, khó nối với bảng cán bộ và nhật ký, và giao diện cần
liệt kê, sửa, ghim, xoá theo người. Đề xuất **bảng riêng, tự quản**:

```
memories
  id, employee_id (hoặc user_id cho quản trị viên), workspace_id, category,
  text (≤240 ký tự), embedding vector(1536), pinned (bool),
  source_run_id, source_conversation_id, created_at, last_used_at, expires_at
```

pgvector đã có, embedding đi qua `embed_query` với cùng provider và cùng quy ước 1536 chiều, đo token
theo thành phần mới `memory_embedding`. Bộ lập lịch sẵn có dọn dòng hết hạn, giống dọn tệp báo cáo.

**Đọc.** Mỗi lượt chat cán bộ: lấy mọi dòng `pinned` cộng 3 đến 5 dòng gần nghĩa nhất với câu hỏi,
cập nhật `last_used_at`, chèn dưới dạng khối dữ liệu:

```
<<<ĐIỀU TRỢ LÝ NHỚ VỀ NGƯỜI HỎI (dữ liệu để chọn cách trả lời, KHÔNG phải nguồn về quy định)
- Thích câu trả lời ngắn, có bước đánh số
- Đang theo hồ sơ HS2026-0412
>>>
```

Ghi `run_steps` loại `memory_read` với danh sách id, để nhật ký cho biết câu trả lời đã được cá nhân
hoá bằng gì.

**Ghi.** Sau `[DONE]`, cùng chỗ với việc đặt tiêu đề hội thoại, một lời gọi mô hình nhỏ trích xuất
bản ghi nhớ mới. Chạy ngay trong request thay vì chạy nền để **báo cho người dùng ngay**, xem 2.5;
chi phí một lời gọi ngắn với model mặc định. Ghi `run_steps` loại `memory_write`. Nếu bản ghi trùng
nghĩa với dòng cũ trên ngưỡng thì cập nhật dòng cũ thay vì thêm dòng mới, để bộ nhớ không phình.

Không dùng `langmem`: nó chưa có trong venv, và phần khó của bài này không phải trích xuất mà là
**bộ lọc nghiệp vụ** ở 2.3, thứ phải tự viết dù dùng thư viện nào.

### 2.5 UI UX

Nguyên tắc đã thành mặc định ở các sản phẩm lớn: người dùng không thấy bộ nhớ thì cá nhân hoá giống
rò rỉ hơn là tính năng. Mọi dòng phải xem, sửa, xoá được; có tạm dừng tách khỏi xoá sạch; có thời
điểm cập nhật.

**Lần đầu**, một thông báo ngắn ngay trong khung chat, hiện đúng một lần: trợ lý sẽ nhớ cách anh/chị
làm việc để trả lời hợp hơn; không bao giờ nhớ thông tin khách hàng; xem và xoá bất cứ lúc nào tại
"Trợ lý nhớ gì về tôi". Hai nút: *Đồng ý* và *Không dùng bộ nhớ*. Đây là quyền được biết và quyền
đồng ý của luật, làm ngay từ đầu chứ không giấu trong cài đặt.

**Ngay sau câu trả lời**, khi có bản ghi mới, một dòng nhỏ dưới câu trả lời:
`🧠 Đã ghi nhớ: anh ưu tiên bước đánh số · Hoàn tác`, tự mờ sau vài giây, "Hoàn tác" xoá ngay. Người
dùng biết trợ lý vừa học gì đúng lúc nó học, và sửa được trong một bấm. Sự kiện SSE mới
`memory_saved` sau `message_saved`.

**Trang `/staff/memory` "Trợ lý nhớ gì về tôi"**, thêm vào hàng liên kết cạnh "Báo cáo của tôi" và
"Biểu mẫu":

- Danh sách theo nhóm: cách trình bày, vai trò, bối cảnh công việc, thuật ngữ. Mỗi dòng: nội dung
  sửa được tại chỗ, ghim, xoá, "dùng lần cuối", liên kết tới hội thoại đã sinh ra nó.
- Đầu trang: hồ sơ nghề nghiệp lấy từ bảng cán bộ, ghi rõ "phần này do đơn vị quản lý".
- Hai công tắc tách rời: **Tạm dừng ghi nhớ** giữ nguyên bộ nhớ nhưng không học thêm, và **Xoá tất cả**
  có xác nhận. Người dùng thường muốn cái thứ nhất chứ không phải cái thứ hai.
- Khối "Trợ lý không bao giờ nhớ" liệt kê đúng bảng cấm ở 2.3, bằng ngôn ngữ thường.

**Quản trị**: trang đơn vị có mục "Bộ nhớ cá nhân của cán bộ": bật tắt cho đơn vị, số ngày lưu, số
dòng tối đa mỗi người. Nhật ký truy vấn: cột "cá nhân hoá" và trong chi tiết lượt hỏi có khối "bộ
nhớ đã dùng" và "bộ nhớ đã ghi", ngang hàng với nguồn trích dẫn và công cụ. Compliance thấy nội dung
bộ nhớ như đang thấy câu hỏi; không giấu vì giấu thì không kiểm toán được.

**Khi cán bộ nghỉ việc**: vô hiệu hoá tài khoản kéo theo xoá bộ nhớ, ghi một dòng nhật ký. Quyền xoá
của luật, và không để lại dữ liệu mồ côi.

### 2.6 Trợ lý Vận hành cũng được lợi

Cùng bảng, không gian tên theo `user_id`. Nó nhớ quản trị viên hay làm việc ở đơn vị nào, thích trả
lời kiểu gì, đang dựng luồng nào. Làm sau khi tầng cán bộ ổn.

---

## 3. Việc cần làm

### Kỹ năng

| Tệp | Nội dung |
|---|---|
| `alembic/versions/0029_skills.py` | Bảng `skills`, `app_skills`; cột `skills.description_embedding vector(1536)` cho chọn trước và cảnh báo chồng chéo |
| `app/models/skill.py` | Model, export ở `__init__.py` |
| `app/services/skills.py` | Kiểm slug theo chuẩn, đo chất lượng description, tìm chồng chéo, chọn trước theo ngưỡng, xuất nhập `SKILL.md` |
| `app/routers/skills.py` | CRUD, publish cần owner khi `share_scope=bank`, `POST /skills/{id}/try`, `GET /skills/{id}/export`, `POST /skills/import` |
| `app/routers/apps.py` | `skill_ids` như `tool_ids`, kiểm `allow_customer` |
| `app/services/chat.py` | Khối `KỸ NĂNG SẴN CÓ`; chọn trước cho đường RAG; `run_steps` loại `skill_activate` |
| `app/services/agent_runtime.py`, `tools/registry.py` | Công cụ nội bộ `kich_hoat_ky_nang` dựng khi trợ lý có kỹ năng, cùng seam với ops tools |
| `seed_demo.py` | Bốn kỹ năng ở 1.5 |
| Web | `/skills` + trình soạn, tab Kỹ năng trên trợ lý, chip kỹ năng trong `AssistantChat` và `staff/chat` |
| Kiểm thử | `tests/test_skills.py` (slug, chất lượng, chồng chéo, chọn trước); `scratch/smoke_skills.py`; e2e |

### Bộ nhớ

| Tệp | Nội dung |
|---|---|
| `alembic/versions/0030_memories.py` | Bảng `memories`; `conversations.summary`; cấu hình đơn vị `memory_enabled`, `memory_retention_days` |
| `app/services/memory.py` | Ba lớp chặn, trích xuất, gộp trùng, đọc theo nghĩa, tóm tắt hội thoại dài |
| `app/routers/staff_auth.py` | `GET/PATCH/DELETE /v1/staff/memory`, `POST /v1/staff/memory/pause`, sự kiện `memory_saved` |
| `app/services/chat.py`, `agent_runtime.py` | Đọc trước, ghi sau, `run_steps` `memory_read` và `memory_write` |
| `app/scheduler.py` | Dọn dòng hết hạn |
| `routers/employees.py` | Vô hiệu hoá cán bộ kéo theo xoá bộ nhớ |
| `routers/audit.py` | Khối bộ nhớ trong chi tiết lượt hỏi |
| Web | `/staff/memory`, thông báo lần đầu, dòng "Đã ghi nhớ · Hoàn tác", mục quản trị đơn vị, khối trong nhật ký |
| Kiểm thử | `tests/test_memory_guard.py` là bộ quan trọng nhất: mọi ví dụ trong bảng cấm ở 2.3 phải bị từ chối; `scratch/smoke_memory.py`; e2e |

---

## 4. Rủi ro và cách chặn

| Rủi ro | Cách chặn |
|---|---|
| Bộ nhớ thành nguồn sự thật về quy định | Không có bộ nhớ tổ chức; khối bộ nhớ ghi rõ "không phải nguồn về quy định"; câu trả lời vẫn bắt buộc trích dẫn; lớp chặn loại bỏ nội dung văn bản |
| Dữ liệu khách hàng lọt vào bộ nhớ | Ba lớp chặn, lớp đầu là mã không phải mô hình; bộ kiểm với đủ ví dụ trong bảng cấm; khách hàng không có bộ nhớ |
| Kỹ năng chồng chéo, kích hoạt nhầm | Cảnh báo chồng chéo lúc lưu; thước đo chất lượng description; nút Thử kỹ năng; ngưỡng chọn trước, dưới ngưỡng thì không kích hoạt |
| Kỹ năng chứa số liệu quy định rồi lệch âm thầm | Trình soạn nhắc; bắt buộc có văn bản tham chiếu; phiên bản và hiệu lực |
| Cá nhân hoá mà người dùng không biết | Thông báo lần đầu có hai nút; dòng "Đã ghi nhớ" kèm hoàn tác; trang xem sửa xoá |
| Tốn token | Siêu dữ liệu kỹ năng khoảng 80 token mỗi dòng; bộ nhớ 5 dòng khoảng 200 token; trích xuất một lời gọi ngắn; tất cả đo theo thành phần |
| Bộ nhớ phình | Gộp trùng theo nghĩa; trần số dòng mỗi người; hết hạn tự dọn; bối cảnh công việc chỉ 30 ngày |

---

## 5. Lộ trình

| Bước | Nội dung | Ước tính |
|---|---|---|
| 1 | Kỹ năng: bảng, CRUD, gắn trợ lý, nạp mức 1, kích hoạt hai đường, chip, bốn kỹ năng seed | 2 ngày |
| 2 | Trình soạn với thước đo, cảnh báo chồng chéo, thử kỹ năng, xuất nhập `SKILL.md` | 0,5 ngày |
| 3 | Bộ nhớ cá nhân: bảng, ba lớp chặn, đọc ghi, dòng "Đã ghi nhớ", trang `/staff/memory` | 2 ngày |
| 4 | Thông báo lần đầu, quản trị đơn vị, nhật ký, dọn hết hạn, xoá khi nghỉ việc | 0,5 ngày |
| 5 | Tóm tắt hội thoại dài | 0,5 ngày |
| 6 | Bộ nhớ cho Trợ lý Vận hành | 0,5 ngày |

Làm kỹ năng trước. Nó không đụng dữ liệu cá nhân nên không có rủi ro pháp lý, và nó là thứ đội
tín dụng cảm nhận được ngay trong demo.

---

## 6. Bốn lựa chọn cần chốt

1. **Bộ nhớ theo cán bộ hay theo từng trợ lý?** Đề xuất theo cán bộ, dùng chung cho mọi trợ lý cán bộ
   họ được thấy. Người ta không muốn dạy lại "tôi thích ngắn gọn" cho từng trợ lý.
2. **Khách hàng hoàn toàn không có bộ nhớ dài hạn.** Đề xuất giữ. Đây là ranh giới pháp lý, không phải
   thiếu tính năng.
3. **Compliance đọc được nội dung bộ nhớ trong nhật ký.** Đề xuất có, ngang với việc đọc được câu hỏi.
   Ghi rõ trong thông báo lần đầu cho cán bộ.
4. **Kích hoạt kỹ năng cho trợ lý RAG thuần bằng chọn trước ở máy chủ.** Đề xuất có, để không tăng độ
   trễ; ngưỡng khớp cấu hình được ở từng trợ lý.

---

## Nguồn tham khảo

- Chuẩn Agent Skills, bản đặc tả: agentskills.io/specification. Trường `name` tối đa 64 ký tự thường
  và gạch nối, `description` tối đa 1024 ký tự, thân bài nên dưới 5000 token và 500 dòng, nạp dần ba
  mức. Bản v1.0 dự kiến nửa cuối 2026; khoảng 40 sản phẩm tương thích tính đến giữa 2026.
- LangGraph long-term memory: `BaseStore` với `put/get/search`, không gian tên dạng tuple,
  `PostgresStore` có chỉ mục ngữ nghĩa qua `IndexConfig(embed, dims)`. Đã có trong venv nhưng plan chọn
  bảng tự quản, lý do ở 2.4.
- LangMem: hai đường ghi bộ nhớ, trong hội thoại bằng công cụ hoặc trích xuất nền sau hội thoại.
  Không dùng, lý do ở 2.4.
- OpenAI, "Memory and new controls for ChatGPT" và Memory FAQ: danh sách bộ nhớ xem sửa xoá được,
  tắt riêng "saved memories" và "chat history".
- AI UX Playground, "How to design AI memory and personalization UX": mọi dòng phải kiểm được, có
  "cập nhật lần cuối", tách tạm dừng khỏi xoá sạch.
- Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15, hiệu lực 1/1/2026, thay Nghị định 13/2023/NĐ-CP cùng
  Nghị định 356/2025/NĐ-CP: quyền được biết, đồng ý, truy cập, chỉnh sửa, yêu cầu xoá.
