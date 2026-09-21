# Nghiên cứu: Luồng tạo báo cáo · Biểu mẫu · Lịch chạy tự động

> **Trạng thái (18/09/2026): đã triển khai xong P1–P3 và đang chạy trên server.**
> P1 báo cáo (migration 0024, node `tool_call` + `render_document`, queue `querion-jobs`),
> P2 lịch chạy (0025, `app/scheduler.py`, trang “Lịch chạy”, “Báo cáo của tôi”),
> P3 biểu mẫu (0026, `/forms` + `/staff/forms`). Chi tiết cách hoạt động nằm ở CLAUDE.md,
> mục “Reports, forms and schedules”. Phần còn lại (P4: webhook/email, xuất PDF, `for_each`)
> vẫn để sau. Tài liệu này giữ nguyên để tra lại lý do thiết kế.

Tài liệu thiết kế cho ba tính năng kế tiếp của MSB Knowledge Assistant. Phần 1 tóm tắt những gì
code hiện có đã hỗ trợ và còn thiếu; phần 2–4 là thiết kế từng tính năng; phần 5 là lộ trình đề xuất
và các quyết định cần chốt.

---

## 1. Hiện trạng (đọc từ code, không phải từ docs/starter)

| Thành phần | Có sẵn | Thiếu cho báo cáo / biểu mẫu / lịch |
|---|---|---|
| **Workflow runtime** `services/workflow_runtime.py` | DAG tuyến tính + `if_else`, 10 loại node (`input, retrieve, compose_prompt, llm_generate, parameter_extract, if_else, http_request, code_execute, answer, output`), state dict, ghi `run_steps`, đo token | Chỉ chạy **đồng bộ trong request** (`POST /v1/workflows/{id}/run` chờ tới khi xong). Không có node gọi **công cụ đã đăng ký**, không có node **xuất file**, không có vòng lặp. `http_request` tự viết lại SSRF guard, không dùng secret/allowlist của registry công cụ. |
| **Input của workflow** | `RunRequest.query` + `inputs: dict` tự do | Node `input` không khai báo **schema** → UI không dựng được form nhập, scheduler không biết cần tham số gì. |
| **Kiểu workflow** | `workflows.type` = `chatflow` \| `workflow` (chỉ là nhãn) | Chưa có kiểu "report" chạy không cần câu hỏi. |
| **Công cụ (0020)** | Registry theo đơn vị: `http` (SSRF guard, secret, `TOOL_INTERNAL_ALLOWLIST`), `builtin`, `mcp`; chốt duyệt | Chỉ agent gọi được; workflow chưa gọi được. |
| **Worker** | RQ, 1 queue `querion-indexing`, sync SQLAlchemy, image riêng | Không có queue việc nền khác, không có scheduler. Image API (`querion/api`) đã chứa toàn bộ code runtime → có thể chạy thêm worker từ image này. |
| **Lưu file** | MinIO (`storage.upload_file / download_file`), bucket `querion-docs` | Chưa có bảng lưu **file đầu ra** (artifact) và endpoint tải về có kiểm quyền. |
| **Thư viện** | `python-docx` (worker, chỉ để đọc), `httpx`, `jinja2` (transitive) | Chưa có `docxtpl` (điền template .docx), `croniter` (tính lịch), engine PDF. |
| **Audit / token** | `runs` (channel, workspace, app, employee/user), `token_usage` theo run | Cần thêm channel `scheduled` / `report`, và liên kết run → file đầu ra. |
| **Thông báo** | Không có SMTP, webhook, hay hộp thư trong cổng cán bộ | Cần cho "báo cáo chạy xong thì gửi cho ai". |

Kết luận: nền tảng đủ để **mở rộng**, không cần viết lại runtime. Ba tính năng chia sẻ chung một
hạ tầng mới: **việc chạy nền (jobs) + file đầu ra (artifacts) + schema input**.

---

## 2. Luồng tạo báo cáo (Report workflow)

### 2.1 Bài toán
Cán bộ/quản lý cần các báo cáo lặp lại: "danh sách hồ sơ tín dụng quá SLA sáng nay", "tổng hợp
giao dịch TTQT chờ kiểm soát", "tóm tắt câu hỏi cán bộ tuần này theo chủ đề". Dữ liệu đến từ hệ
thống nghiệp vụ (qua công cụ HTTP/MCP) và từ kho tri thức (quy định, SLA để đối chiếu); LLM tổng
hợp, diễn giải; kết quả là **một file** (DOCX/Markdown, sau này PDF) lưu lại được và gửi được.

### 2.2 Thiết kế

**Kiểu workflow mới `report`** (bên cạnh `chatflow`): không có `query`, chạy bằng `inputs` theo
schema, luôn chạy **nền** (RQ) vì có thể mất vài phút, kết thúc bằng node `output` sinh file.

**Node mới (3 node, thêm vào `ALLOWED_NODE_TYPES` + runtime + canvas):**

1. `tool_call` — gọi một công cụ đã đăng ký trong registry (`tool_id`, `args` có `{{var}}`).
   Dùng lại toàn bộ `services/tools/executor.py`: SSRF guard, allowlist nội bộ, secret server-side,
   timeout, `response_path`, và kiểm tra `jsonschema`. Kết quả ghi `state["tool_results"][alias]`
   (JSON đã parse nếu được). Đây là **nguồn dữ liệu chính** của báo cáo; nên khuyến nghị dùng thay
   `http_request` (giữ `http_request` để tương thích).
2. `render_document` — điền template ra file:
   - `format`: `docx` (thư viện `docxtpl`, template .docx do đơn vị tải lên, placeholder Jinja
     `{{ ten_bien }}`, `{% for hs in ho_so %}` cho bảng) hoặc `markdown` (template text → `.md`,
     và cũng hiển thị được ngay trong chat).
   - Biến có sẵn: `inputs`, `tool_results`, `answer` (LLM), `retrieved_chunks`, `now`, `unit`.
   - Jinja chạy trong **`SandboxedEnvironment`**, autoescape, không cho gọi thuộc tính `_*`
     (template do admin đơn vị soạn, không do LLM sinh → không có template injection từ chat,
     nhưng vẫn phải sandbox).
   - Kết quả: bytes → MinIO `reports/<workspace>/<run_id>/<tên>.docx` + một dòng `artifacts`.
3. `for_each` (**phase sau**) — lặp một nhánh con trên danh sách (ví dụ tóm tắt từng hồ sơ).
   Phase 1 không cần: LLM nhận cả danh sách trong một prompt là đủ cho demo.

**Node `input` có schema**: `data.fields = [{name, label, type: string|number|date|select|boolean,
required, default, options, description}]`. Runtime kiểm tra `inputs` theo schema trước khi chạy;
UI (dialog "Chạy", scheduler, cổng cán bộ) **tự dựng form** từ schema. Đây cũng là nền cho biểu mẫu.

**Bảng mới**

```
artifacts(id, workspace_id, run_id, workflow_id, schedule_id?, kind report|form,
          filename, content_type, storage_key, size, created_by_user_id?, created_by_employee_id?,
          created_at, expires_at)
```
Không FK cứng tới run (audit history), có index theo workspace + created_at.
Tải về: `GET /v1/artifacts/{id}/download` — kiểm quyền: admin cùng đơn vị (viewer trở lên) hoặc
cán bộ cùng đơn vị (báo cáo publish cho cán bộ). Stream từ MinIO qua API (không lộ MinIO ra
ngoài, khớp với việc cổng 9000 đang đóng trên server).

**Chạy nền**

- `POST /v1/workflows/{id}/jobs` `{inputs}` → tạo `Run(channel="report", status="queued")`,
  enqueue RQ queue **`querion-jobs`** với `run_id`. Trả `run_id` ngay.
- **Worker thứ hai chạy từ image `querion/api`** (service `jobs-worker` trong compose:
  `rq worker querion-jobs`), vì image này có sẵn `workflow_runtime`, registry công cụ, MinIO,
  token metering. Task: `asyncio.run(run_workflow(...))` với `async_session_factory` của API.
  Không đụng worker lập chỉ mục hiện tại.
- UI theo dõi: `GET /v1/audit/runs/{id}` đã có; thêm `artifacts` vào chi tiết run.
  Trang workflow thêm tab **"Lần chạy & báo cáo"**: trạng thái, thời gian, token, nút tải file.

**Báo cáo trong chat** (tuỳ chọn, rẻ): trợ lý gắn `workflow` kiểu `report` → khi cán bộ hỏi,
runtime chạy như hiện nay và trả lời bằng nội dung Markdown + link tải DOCX (`artifact_id`).
SSE thêm event `{"type":"artifact","id","filename","url"}`; `AssistantChat` hiện chip tải về.

### 2.3 Dữ liệu demo
Mở rộng `demo-mock/core_api.py` (synthetic): `GET /v1/ho-so?trang_thai=&qua_han=true`,
`GET /v1/giao-dich-ttqt?ngay=` trả danh sách 10–20 dòng giả lập; đăng ký thành công cụ
`danh_sach_ho_so_qua_han`, `giao_dich_ttqt_cho_ksv` trong seed. Template DOCX mẫu
`seed_data/templates/bao_cao_ho_so_qua_han.docx` (tự sinh bằng python-docx trong seed, không copy
mẫu thật của ngân hàng).

### 2.4 An toàn / tuân thủ
- Dữ liệu nghiệp vụ đi thẳng công cụ → template, **không qua ô chat** nên không bị `mask_pii`
  che; nhưng nội dung đưa vào **LLM** để tóm tắt thì vẫn nên là mã hồ sơ/số liệu, không CIF/CCCD
  (ràng buộc giống agent hiện tại). Node `llm_generate` trong report nên có cờ `mask_pii_input`.
- File đầu ra chỉ tải trong đơn vị; `expires_at` mặc định 30 ngày; xoá file MinIO khi hết hạn
  (job dọn dẹp chạy bằng scheduler mục 4).
- Mọi lần chạy có `run` + `run_steps` + `token_usage` → hiện trong Nhật ký truy vấn và Token sử dụng
  (channel `report` / `scheduled`).

---

## 3. Biểu mẫu (Forms)

### 3.1 Hai nghĩa của "biểu mẫu" và cách gom lại
1. **Form nhập tham số** cho workflow/báo cáo/lịch → giải quyết bằng `input.fields` (mục 2.2).
2. **Biểu mẫu nghiệp vụ** (tờ trình, đề nghị giải ngân, phiếu kiểm soát TTQT…): cán bộ điền,
   AI hỗ trợ điền sẵn, xuất DOCX đúng mẫu đơn vị. Đây là tính năng người dùng nhìn thấy.

Cả hai dùng chung: **schema trường** + **template DOCX** + node `render_document`. Một biểu mẫu
nghiệp vụ về bản chất là một workflow `report` rất ngắn: `input(fields) → [tool_call điền sẵn] →
render_document → output`. Vì vậy không cần runtime riêng, chỉ cần **bảng khai báo + UI**.

### 3.2 Thiết kế

```
form_templates(id, workspace_id, name, description, doc_type (mau_bieu),
               fields JSON  -- schema như input.fields, thêm: source: user|tool|llm, pii: bool
               template_storage_key,  -- file .docx có placeholder
               prefill_tool_id?, prefill_arg_field?,  -- ví dụ tra_ho_so(ma_ho_so) → điền khach_hang, so_tien…
               prefill_mapping JSON,  -- {"khach_hang": "$.khach_hang", ...} (JSONPath đơn giản)
               share_scope unit|bank, is_published, created_at, updated_at)
```

**Luồng trên cổng cán bộ** (`/staff/forms`, mục mới "Biểu mẫu"):
1. Chọn biểu mẫu → form dựng từ `fields`.
2. Nhập khoá nghiệp vụ (mã hồ sơ) → **"Điền sẵn"** gọi `prefill_tool` (qua registry, có audit) →
   các trường có `source: tool` được điền, cán bộ vẫn sửa được.
3. Trường tự luận (`source: llm`, ví dụ "nhận xét thẩm định") → nút **"Gợi ý"**: LLM soạn dựa trên
   dữ liệu đã điền (không PII) + kho tri thức liên quan; cán bộ duyệt lại.
4. **Xuất DOCX** → `artifacts(kind=form)` → tải về; ghi `run(channel="form")`.

**Điểm quan trọng về PII**: các trường `pii: true` (tên KH, CCCD, số TK) **không bao giờ đi qua
LLM**; chỉ đi từ tool/ô nhập → template. `mask_pii` hiện chạy trên tin nhắn chat; form không đi
qua chat nên không bị che, nhưng ta phải chủ động không gửi những trường này vào prompt gợi ý.
Đây là lý do điền biểu mẫu nên là **UI form**, không phải "nhắn cho trợ lý điền hộ" (chat sẽ che
mất CCCD/số TK và biểu mẫu sẽ sai).

**Biểu mẫu từ chat (bổ trợ)**: đăng ký công cụ builtin `tao_bieu_mau(form_id, ma_ho_so)` cần
duyệt (`requires_approval`) → agent gọi khi cán bộ nói "lập đề nghị giải ngân cho HS2026-0518";
sau khi duyệt, công cụ tạo bản **nháp đã điền sẵn từ tool**, trả link mở form để cán bộ hoàn tất.
Không xuất file thẳng từ chat.

**Quản trị** (`/forms`, cạnh "Công cụ"): tải template .docx, khai báo trường (bảng chỉnh sửa),
chọn công cụ điền sẵn + mapping, "Xem trước" với dữ liệu giả, publish. Kiểm tra template khi tải
lên: đúng .docx, chỉ dùng placeholder có trong `fields` (docxtpl `get_undeclared_template_variables`).

---

## 4. Lịch chạy tự động (Scheduler)

### 4.1 Bài toán
Chạy workflow `report` (và job dọn dẹp) theo lịch: "8:00 mỗi ngày làm việc", "thứ Hai 7:30",
"ngày 1 hàng tháng"; xem lịch sử, chạy ngay, tắt/bật; kết quả đến đúng người.

### 4.2 Lựa chọn engine

| Phương án | Ưu | Nhược |
|---|---|---|
| APScheduler trong tiến trình API | Dễ | API có thể chạy nhiều replica → chạy trùng; restart mất trạng thái in-memory |
| `rq-scheduler` | Có sẵn với RQ | Thêm tiến trình và thư viện ít bảo trì; lịch nằm trong Redis (Redis không phải nguồn sự thật của ta) |
| RQ `enqueue_at` + tự re-enqueue | Không thêm lib | Lịch lặp phải tự nối đuôi; đổi cron khó, mất job nếu Redis mất |
| **Ticker riêng, DB là nguồn sự thật** (đề xuất) | Đơn giản, idempotent, sống qua redeploy, dễ debug bằng SQL | Tự viết ~150 dòng |

**Đề xuất**: service `scheduler` từ image `querion/api` (`python -m app.scheduler`), vòng lặp 30 s:

```sql
SELECT * FROM schedules
WHERE enabled AND next_run_at <= now()
FOR UPDATE SKIP LOCKED
```
→ với mỗi dòng: tạo `Run(channel="scheduled", schedule_id)`, enqueue `querion-jobs`,
`next_run_at = croniter(cron, now, tz).get_next()`, `last_enqueued_at = now()`, commit.
`SKIP LOCKED` cho phép chạy 2 ticker mà không trùng. Nếu ticker chết vài giờ: chính sách
`catch_up = skip|run_once` (mặc định `run_once`: chạy 1 lần rồi nhảy tới mốc kế, không chạy bù n lần).

```
schedules(id, workspace_id, workflow_id, name, cron VARCHAR(64), timezone (mặc định Asia/Ho_Chi_Minh),
          inputs JSON, enabled, catch_up, next_run_at, last_run_at, last_status, last_run_id,
          deliver JSON {staff_ids|positions|emails|webhook}, retention_days,
          created_by, created_at, updated_at)
```
Thư viện: `croniter` (hoặc `cronsim`). Cron 5 trường + preset UI (hàng ngày lúc…, ngày làm việc
T2–T6, hàng tuần, hàng tháng) sinh cron; hiển thị "3 lần chạy kế tiếp" khi soạn.

### 4.3 API & UI
- `GET/POST/PATCH/DELETE /v1/schedules` (editor của đơn vị; workflow phải cùng đơn vị),
  `POST /v1/schedules/{id}/run-now`, `GET /v1/schedules/{id}/runs`.
- Trang **Quản trị → "Lịch chạy"** (sidebar, `ownerOk`): bảng lịch (tên, workflow, cron đọc
  được "08:00 các ngày T2–T6", lần chạy kế, lần cuối + trạng thái + link báo cáo), toggle, chạy
  ngay, form tạo/sửa: chọn workflow `report` → form inputs từ schema → chu kỳ → người nhận.
- Cổng cán bộ: mục **"Báo cáo của tôi"**: artifacts mà `deliver` nhắm tới cán bộ đó / vị trí
  (CCO, KSV) trong đơn vị; badge chưa đọc. Đây là kênh giao báo cáo **phase 1** (không cần SMTP).
- Nhật ký truy vấn / Token: filter channel `scheduled`; chi tiết run hiện `schedule_id`.

### 4.4 Giao kết quả (delivery) — theo giai đoạn
1. Hộp "Báo cáo của tôi" trong cổng cán bộ (phase 1).
2. Webhook nội bộ (URL qua SSRF guard + allowlist, ký HMAC) — ví dụ bắn vào hệ thống thông báo
   nội bộ / chat nội bộ (phase 2).
3. Email SMTP (cấu hình trong Cài đặt hệ thống, mật khẩu Fernet như API key) — phase 2/3.

### 4.5 Vận hành
- Compose thêm `jobs-worker` và `scheduler` (đều `image: querion/api:latest`, `pull_policy: never`),
  `deploy/remote.sh` không cần đổi (up -d + healthcheck: scheduler ghi `heartbeat_at` vào Redis).
- Server hiện 4 vCPU/8 GB: thêm 2 tiến trình Python nhẹ (~150 MB mỗi cái) là ổn.
- Job dọn dẹp artifact hết hạn = một `schedules` dòng hệ thống (workflow builtin), không cần cron OS.

---

## 5. Lộ trình đề xuất

| Giai đoạn | Nội dung | Ước lượng |
|---|---|---|
| **P1 – Nền báo cáo** | migration `artifacts`; node `tool_call` + `render_document` (docx/markdown, sandbox Jinja); `input.fields` schema + form tự dựng ở dialog Chạy; workflow type `report`; queue `querion-jobs` + `jobs-worker`; endpoint jobs/artifacts/download; tab "Lần chạy & báo cáo"; mở rộng mock core + seed 1 báo cáo demo; smoke test | 2–3 ngày |
| **P2 – Lịch chạy** | migration `schedules`; service ticker; API + trang "Lịch chạy"; "Báo cáo của tôi" ở cổng cán bộ; channel `scheduled` trong audit/token; job dọn artifact; compose + deploy | 1,5–2 ngày |
| **P3 – Biểu mẫu** | migration `form_templates`; upload/validate template; trang quản trị `/forms`; cổng cán bộ `/staff/forms` (điền sẵn qua tool, gợi ý LLM cho trường không PII, xuất DOCX); công cụ `tao_bieu_mau` cần duyệt; 1 biểu mẫu demo (đề nghị giải ngân) | 2 ngày |
| **P4 – Giao kết quả & PDF** | webhook ký HMAC, SMTP, xuất PDF (LibreOffice headless trong image riêng hoặc dịch vụ ngoài), `for_each` | sau hackathon |

Kịch bản demo sau P1+P2: *"7:30 sáng, Trợ lý tự chạy báo cáo 'Hồ sơ tín dụng quá SLA' cho khối
EB: lấy danh sách từ core (công cụ), đối chiếu SLA trong Quy trình cấp tín dụng (kho tri thức),
LLM tóm tắt điểm cần lưu ý, xuất DOCX; CCO mở cổng cán bộ thấy báo cáo mới; compliance xem
nhật ký thấy đúng công cụ đã gọi và số token đã tiêu."*

### Quyết định cần chốt trước khi làm
1. **Định dạng đầu ra P1**: DOCX + Markdown (đề xuất) hay cần PDF ngay? PDF kéo theo LibreOffice
   (~400 MB image) hoặc WeasyPrint (HTML→PDF, font tiếng Việt phải cài) — để P4.
2. **Nguồn dữ liệu báo cáo demo**: mở rộng mock core (đề xuất) hay đọc trực tiếp DB nội bộ
   (không nên: cần cơ chế SQL read-only riêng, rủi ro cao).
3. **Ai tạo lịch/biểu mẫu**: editor của đơn vị (đề xuất) hay chỉ owner.
4. **Kênh giao báo cáo P1**: chỉ "Báo cáo của tôi" trong cổng cán bộ (đề xuất) — chưa cần SMTP.
5. **Thời gian lưu file**: 30 ngày mặc định, owner đổi được theo lịch.
