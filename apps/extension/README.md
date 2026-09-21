# MSB Knowledge Assistant — Chrome extension (bong bóng cán bộ)

Bong bóng trợ lý trôi nổi trên **mọi trang** trong Chrome của cán bộ: kéo thả tự do, đăng nhập
một lần cho cả trình duyệt, tự mở đúng trợ lý theo trang đang xem, bôi đen đoạn chữ rồi hỏi.
Manifest V3.

```
apps/extension/
├─ manifest.json            # MV3; host_permissions được build script điền từ API_ORIGINS
├─ managed_schema.json      # cấu hình IT đẩy xuống (chrome.storage.managed)
├─ scripts/build.mjs        # Vite: panel + options (React/Tailwind), content.js (IIFE), background.js
└─ src/
   ├─ content/content.ts    # bong bóng trong Shadow DOM kín, kéo thả, iframe tới panel.html
   ├─ panel/App.tsx         # đăng nhập → chọn trợ lý → chat (tái dùng AssistantChat của web app)
   ├─ options/              # trang cấu hình (chỉ dùng khi không có policy)
   ├─ background.ts         # bấm icon trên thanh công cụ → bật/tắt bong bóng
   └─ lib/                  # api.ts (login/refresh/apps), storage.ts, bridge.ts, hosts.ts
```

## Cách hoạt động

- **Trang chủ không thấy gì.** Khung chat là trang `chrome-extension://…/panel.html` nằm trong
  iframe do content script chèn. CSP của trang chủ không áp lên nó, storage là của extension, token
  cán bộ không bao giờ chạm tới trang. `use_dynamic_url` khiến trang không đoán được URL panel để
  tự nhúng.
- **Gọi API thẳng từ extension.** Panel gọi `/v1/staff/*` với `host_permissions`, không cần CORS.
  Đăng nhập gửi `client: "extension"`; server ghi claim đó vào JWT và tự quyết định: chỉ liệt kê trợ
  lý đã bật *Browser extension* trên tab Cấu hình, từ chối chat với trợ lý chưa bật (403), ghi nhật
  ký kênh `extension` kèm origin trang (`X-Page-Origin`).
- **Chọn trợ lý.** Trang khớp `extension_hosts` của trợ lý nào thì mở sẵn trợ lý đó; không khớp thì
  mở trợ lý dùng lần trước; lần đầu hiện danh sách gom theo đơn vị. Đổi bằng nút ô vuông trên header.
- **Không chen vào web app và các trang IT loại trừ** (`disabledHosts`), và nhường chỗ cho trang đã
  nhúng `widget.js`.
- **Side Panel = cấp trình duyệt.** Extension không được vẽ lên khung Chrome hay lên các trang hệ
  thống (`chrome://`, New Tab). Thứ gần nhất Chrome cho phép là Side Panel: bấm icon trên thanh công
  cụ là mở panel dọc gắn vào cửa sổ, có trên **mọi** tab kể cả New Tab, giữ nguyên khi chuyển tab.
  Cùng một `panel.html`: khi không nằm trong iframe nó tự chuyển sang chế độ side panel, theo dõi tab
  đang mở qua `chrome.tabs` để chọn trợ lý mặc định và nhận đoạn bôi đen từ content script.
- **Một trợ lý, một chỗ tại một thời điểm.** Side panel đang mở thì bong bóng trên mọi tab ẩn đi
  (kể cả tab mở sau); đóng side panel thì bong bóng hiện lại. Panel giữ một `runtime.connect` port
  khi sống, background ghi `sidePanelOpen` vào `chrome.storage.session`, content script nghe
  `onChanged`.

## Không thấy bong bóng?

- Tab mở **trước khi** cài extension không được chèn — tải lại tab (F5).
- Extension cố ý **không** chèn vào: chính web app (đã có cổng cán bộ), trang đã nhúng `widget.js`
  (như trang demo, để không có hai bong bóng), tên miền IT loại trừ, và các trang hệ thống
  `chrome://` kể cả New Tab. Ở những trang đó icon trên thanh công cụ hiện dấu "–" và tooltip nói rõ
  lý do; **bấm icon để mở Side Panel** — panel này có ở mọi nơi.
- Thử trên một trang web bất kỳ (vnexpress, google) hoặc trang BPM mô phỏng
  `apps/web/e2e/fixtures/intranet` ở cổng 8092.

## Build

```bash
cd apps/extension && npm install
npm run build                                   # → dist/, API mặc định http://localhost:8000
API_ORIGINS="https://kb.msb.com.vn/*" VITE_DEFAULT_API_BASE="https://kb.msb.com.vn" npm run build
```

Nạp thử: `chrome://extensions` → bật *Developer mode* → *Load unpacked* → chọn `apps/extension/dist`.

## Phân phối trong ngân hàng

Chrome Enterprise policy, máy đã join domain (tự host CRX chỉ được phép trên máy quản trị):

```json
{
  "ExtensionInstallForcelist": ["<extension-id>;https://kb.msb.com.vn/extension/update.xml"],
  "3rdparty": { "extensions": { "<extension-id>": {
    "apiBase": "https://kb.msb.com.vn",
    "brandName": "MSB Knowledge Assistant",
    "disabledHosts": ["ebank.msb.com.vn"]
  } } }
}
```

Giá trị trong `3rdparty` tới extension qua `chrome.storage.managed` (xem `managed_schema.json`);
khi có `apiBase` từ policy, trang tuỳ chọn khoá lại không cho cán bộ đổi.

## Kiểm thử

- `scratch/smoke_extension.py` — 25 kiểm tra phía API: claim `client`, lọc trợ lý, 403, kênh audit,
  validate `extension_hosts`.
- `apps/web/e2e/extension.spec.ts` — nạp `dist/` vào Chromium, bong bóng trên trang không có snippet,
  kéo thả, đăng nhập trong panel, trợ lý mặc định theo trang, trả lời có trích dẫn, đổi trợ lý, hỏi
  về đoạn bôi đen.
