/**
 * Quay video demo trên bản deploy thật.
 *
 * Mỗi `test` là một cảnh và sinh ra một tệp .webm riêng trong `e2e/videos/`; script
 * `scripts/demo-video.sh` ghép các cảnh theo thứ tự thành một video duy nhất.
 *
 * Khác các spec kiểm thử: ở đây không assert để chứng minh đúng sai, mà điều khiển trình duyệt
 * theo nhịp người xem đọc kịp. Chú thích từng cảnh được chèn thẳng vào trang bằng một overlay
 * (`caption`), nên video không cần hậu kỳ.
 *
 * Chạy:  BASE=https://59-153-246-116.sslip.io ADMIN_PASSWORD=... npx playwright test e2e/demo-video.spec.ts --project=video
 */
import { test, type Page } from "@playwright/test";

const BASE = process.env.DEMO_BASE || "https://59-153-246-116.sslip.io";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || "admin123";
const DEMO_SITE = process.env.DEMO_SITE || "https://demo.59-153-246-116.sslip.io";

test.use({ baseURL: BASE });
// Không dùng "serial": mỗi cảnh phải quay được độc lập, một cảnh hỏng không kéo theo các cảnh sau.
test.describe.configure({ mode: "default" });

/** Chú thích ở góc dưới màn hình: người xem biết đang xem cảnh gì mà không cần thuyết minh. */
async function caption(page: Page, title: string, sub = "", hold = 2200) {
  await page.evaluate(([t, s]) => {
    let el = document.getElementById("__demo_cap");
    if (!el) {
      el = document.createElement("div");
      el.id = "__demo_cap";
      el.style.cssText = [
        "position:fixed", "left:32px", "bottom:32px", "z-index:2147483647",
        "max-width:min(760px,70vw)", "padding:14px 20px", "border-radius:14px",
        "background:rgba(20,35,58,.94)", "color:#fff", "box-shadow:0 18px 50px rgba(0,0,0,.35)",
        "font-family:'Be Vietnam Pro',system-ui,sans-serif", "pointer-events:none",
        "transition:opacity .25s ease", "border-left:4px solid #ee6d1f",
      ].join(";");
      document.body.appendChild(el);
    }
    el.style.opacity = "1";
    el.replaceChildren();  // textContent, không innerHTML: chú thích là chữ, không phải mã
    const h = document.createElement("div");
    h.style.cssText = "font-size:19px;font-weight:700;line-height:1.3";
    h.textContent = t;
    el.appendChild(h);
    if (s) {
      const p = document.createElement("div");
      p.style.cssText = "font-size:14.5px;opacity:.82;margin-top:4px;line-height:1.4";
      p.textContent = s;
      el.appendChild(p);
    }
  }, [title, sub]);
  await page.waitForTimeout(hold);
}

async function hideCaption(page: Page) {
  await page.evaluate(() => {
    const el = document.getElementById("__demo_cap");
    if (el) el.style.opacity = "0";
  });
}

/** Gõ từng ký tự để người xem thấy câu hỏi hình thành, thay vì chữ hiện ra một cục. */
async function typeQuestion(page: Page, text: string) {
  const box = page.getByPlaceholder("Hỏi về quy trình, quy định, sản phẩm...");
  await box.click();
  await box.type(text, { delay: 18 });
  await page.waitForTimeout(400);
  await page.getByRole("button", { name: "Gửi", exact: true }).last().click();
}

/** Cuộn tới một phần tử mà không vỡ nếu nó vừa được vẽ lại giữa chừng (câu trả lời đang stream). */
async function reveal(page: Page, testId: string) {
  for (let i = 0; i < 3; i++) {
    try {
      await page.getByTestId(testId).last().scrollIntoViewIfNeeded({ timeout: 5000 });
      return;
    } catch { await page.waitForTimeout(1200); }
  }
  await page.mouse.wheel(0, 900);
}

/** Cuộn xuống đáy nhiều nhịp để câu trả lời dài vẫn đọc theo được. */
async function readAnswer(page: Page, ms = 6000) {
  const steps = Math.max(1, Math.round(ms / 900));
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, 260);
    await page.waitForTimeout(900);
  }
}

async function staffLogin(page: Page, email: string, who: string) {
  await page.goto("/staff/login");
  await caption(page, "Cổng cán bộ", `Đăng nhập ${who}`, 1600);
  await page.fill("input[type=email]", email);
  await page.fill("input[type=password]", "demo123");
  await page.waitForTimeout(500);
  await page.click("button[type=submit]");
  await page.waitForURL(/\/staff\/chat/, { timeout: 60_000 });
  await page.waitForTimeout(1200);
}

async function adminLogin(page: Page) {
  await page.goto("/login");
  await page.fill("#login-email", "admin@querion.io");
  await page.fill("#login-password", ADMIN_PASSWORD);
  await page.waitForTimeout(400);
  await page.click("#login-submit");
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 60_000 });
  await page.waitForTimeout(1500);
}

async function pickAssistant(page: Page, name: RegExp) {
  await page.getByRole("button", { name }).first().click();
  await page.waitForTimeout(1000);
}

// ---------------------------------------------------------------------------

test("01 — trả lời có trích dẫn Điều khoản", async ({ page }) => {
  await staffLogin(page, "rm.an@msb-demo.vn", "Nguyễn Văn An · RM · Khối KHDN");
  await pickAssistant(page, /Trợ lý Tín dụng KHDN/);
  await caption(page, "Cán bộ chỉ thấy trợ lý của khối mình",
    "Và các trợ lý mở toàn ngân hàng. Phân quyền kiểm ở máy chủ.", 2600);
  await hideCaption(page);

  await typeQuestion(page, "Điều kiện giải ngân cho khách hàng doanh nghiệp có tài sản bảo đảm là gì?");
  await caption(page, "Trả lời từ văn bản nội bộ", "Không phải kiến thức chung của mô hình", 1500);
  await page.getByText(/NGUỒN TRÍCH DẪN/i).first().waitFor({ timeout: 180_000 });
  await hideCaption(page);
  await readAnswer(page, 6000);
  await caption(page, "Mỗi nguồn ghi rõ văn bản, phiên bản, ngày hiệu lực và Điều",
    "Cán bộ đối chiếu được ngay, không phải tin lời máy", 4500);
  await hideCaption(page);
  await page.waitForTimeout(800);
});

test("02 — dữ liệu khách hàng không tới mô hình", async ({ page }) => {
  await staffLogin(page, "rm.an@msb-demo.vn", "Nguyễn Văn An · RM · Khối KHDN");
  await pickAssistant(page, /Trợ lý Tín dụng KHDN/);
  await caption(page, "Cán bộ vô tình dán dữ liệu khách hàng",
    "Chuyện xảy ra hằng ngày khi dùng công cụ AI công cộng", 2600);
  await hideCaption(page);

  await typeQuestion(page,
    "Khách hàng CIF 1234567, CCCD 012345678901 đang nợ 2 tỷ ở ngân hàng khác, tôi có nên phê duyệt khoản vay 5 tỷ cho họ không?");
  await page.getByText("🔒").first().waitFor({ timeout: 180_000 });
  await caption(page, "Hệ thống che dữ liệu cá nhân trước khi mô hình đọc",
    "CIF và CCCD bị thay bằng chỗ trống — số tiền thì giữ nguyên để nghiệp vụ không hỏng", 4200);
  await hideCaption(page);
  await readAnswer(page, 5400);
  await caption(page, "Trợ lý không quyết định thay cấp phê duyệt",
    "Nó nêu điều kiện cần kiểm tra, kèm trích dẫn", 4000);
  await hideCaption(page);
});

test("03 — chạm hệ thống thật, thao tác ghi chờ duyệt", async ({ page }) => {
  await staffLogin(page, "ksv.linh@msb-demo.vn", "Đỗ Thuỳ Linh · KSV · Khối Vận hành");
  await pickAssistant(page, /Trợ lý Khiếu nại/);
  await caption(page, "Trợ lý gọi được hệ thống lõi", "Không chỉ đọc tài liệu", 2200);
  await hideCaption(page);

  await typeQuestion(page, "Khiếu nại nào đang quá hạn SLA? Ai phụ trách?");
  await page.getByTestId("tool-chips").first().waitFor({ timeout: 180_000 });
  await caption(page, "Trợ lý tra danh sách khiếu nại trên hệ thống", "", 2200);
  await page.getByText(/NGUỒN TRÍCH DẪN/i).first().waitFor({ timeout: 180_000 }).catch(() => {});
  await hideCaption(page);
  await readAnswer(page, 5000);

  await typeQuestion(page, "Phân công khiếu nại KN2026-0305 cho cán bộ MSB01005");
  await page.getByTestId("tool-approval").first().waitFor({ timeout: 180_000 });
  await page.waitForTimeout(1200);
  await reveal(page, "tool-approval");
  await caption(page, "Thao tác ghi dừng lại chờ người duyệt",
    "AI không tự ghi vào hệ thống. Cán bộ thấy đúng tham số trước khi bấm.", 5000);
  await hideCaption(page);
  await page.getByTestId("approve-tool").first().click();
  await caption(page, "Cán bộ bấm Duyệt — lúc này công cụ mới chạy", "", 2000);
  await page.waitForTimeout(6000);
  await hideCaption(page);
  await readAnswer(page, 3600);
});

test("04 — biểu đồ trong chat và xuất Excel", async ({ page }) => {
  await staffLogin(page, "rm.dung@msb-demo.vn", "Phạm Minh Dũng · RM · Khối KHCN");
  await pickAssistant(page, /Trợ lý Tư vấn KHCN/);
  await hideCaption(page);

  await typeQuestion(page, "Lãi suất tiết kiệm theo từng kỳ hạn hiện nay? Vẽ biểu đồ cột.");
  await page.locator("svg[role=img]").first().waitFor({ timeout: 200_000 });
  await page.getByTestId("message-saved").last().waitFor({ timeout: 60_000 }).catch(() => {});
  await page.waitForTimeout(1500);
  await page.mouse.wheel(0, 700);
  await page.waitForTimeout(900);
  await caption(page, "Biểu đồ vẽ ngay trong câu trả lời",
    "Không phải ảnh tải từ ngoài — Compliance mở lại vẫn thấy đúng biểu đồ này", 4600);
  await hideCaption(page);
  await page.waitForTimeout(1200);

  await typeQuestion(page, "Xuất bảng lãi suất này ra Excel kèm biểu đồ cột");
  await page.getByTestId("chat-file").first().waitFor({ timeout: 200_000 });
  await page.waitForTimeout(1500);
  await reveal(page, "chat-file");
  await caption(page, "Tệp Excel thật, có bảng và biểu đồ mở ra sửa được",
    "Tệp nằm trong hộp \"Báo cáo của tôi\" của chính cán bộ đã hỏi", 4600);
  await hideCaption(page);
});

test("05 — luồng phân mức sự cố tuân thủ", async ({ page }) => {
  await staffLogin(page, "cco.nam@msb-demo.vn", "Bùi Hoàng Nam · CCO · Khối Pháp chế");
  await pickAssistant(page, /Trợ lý Sự cố Tuân thủ/);
  await caption(page, "Một trợ lý chạy trên luồng xử lý có rẽ nhánh",
    "Sự cố đang diễn ra và câu hỏi quy định được xử lý khác nhau", 3000);
  await hideCaption(page);

  await typeQuestion(page,
    "Tôi vừa gửi nhầm file danh sách khách hàng kèm số CCCD ra một địa chỉ email bên ngoài ngân hàng, giờ phải làm gì?");
  await page.getByText("⚠️").first().waitFor({ timeout: 200_000 });
  await caption(page, "Nhánh khẩn: các bước làm ngay và mốc báo cáo",
    "Mỗi việc kèm trích dẫn văn bản, không phải lời khuyên chung chung", 4200);
  await hideCaption(page);
  await readAnswer(page, 7000);
});

test("06 — Compliance mở lại đúng thứ cán bộ đã thấy", async ({ page }) => {
  await adminLogin(page);
  await page.goto("/admin/audit");
  await page.locator("tbody tr").first().waitFor({ timeout: 60_000 });
  await caption(page, "Nhật ký truy vấn", "Mọi lượt hỏi ở mọi kênh đều để lại vết", 3000);
  await hideCaption(page);
  await page.waitForTimeout(800);

  await page.locator("tbody tr").first().click();
  await page.getByRole("button", { name: "Đóng" }).waitFor({ timeout: 30_000 });
  await page.waitForTimeout(1200);
  await caption(page, "Ai hỏi, máy trả lời gì, dựa trên Điều nào",
    "Kèm từng bước công cụ, kỹ năng đã dùng và số token", 4200);
  await hideCaption(page);
  await page.mouse.wheel(0, 700);
  await page.waitForTimeout(3000);
  await page.mouse.wheel(0, 700);
  await page.waitForTimeout(3000);
});

test("07 — quản trị viên mô tả, trợ lý dựng nháp luồng", async ({ page }) => {
  await adminLogin(page);
  await page.goto("/workflows");
  await page.getByTestId("ops-bubble").waitFor({ timeout: 60_000 });
  await caption(page, "Trợ lý Vận hành cho chính người quản trị hệ thống", "", 2600);
  await hideCaption(page);
  await page.getByTestId("ops-bubble").click();
  await page.waitForTimeout(900);

  const panel = page.getByTestId("ops-panel");
  const box = panel.getByPlaceholder("Nhập câu hỏi của bạn...");
  await box.click();
  await box.type("Dựng luồng: tra kho tri thức tín dụng rồi soạn prompt và sinh câu trả lời có trích dẫn.", { delay: 16 });
  await box.press("Enter");
  await caption(page, "Mô tả bằng tiếng Việt, không cần lập trình viên", "", 2400);
  await panel.getByTestId("workflow-draft").waitFor({ timeout: 240_000 });
  await hideCaption(page);
  await page.waitForTimeout(1500);
  await caption(page, "Trợ lý chỉ dựng bản nháp — người bấm nút mới tạo luồng",
    "Luồng được tạo bằng quyền của chính quản trị viên đó", 4600);
  await hideCaption(page);
});

test("08 — khách hàng trên website của ngân hàng", async ({ page }) => {
  await page.goto(`${DEMO_SITE}/index.html`);
  await page.locator(".msbka-btn").waitFor({ timeout: 60_000 });
  await caption(page, "Website ngân hàng nhúng trợ lý bằng một dòng script",
    "Chỉ những website trong danh sách cho phép mới nhúng được", 3400);
  await hideCaption(page);
  await page.locator(".msbka-btn").click();
  await page.waitForTimeout(1400);

  const w = page.frameLocator(".msbka-panel iframe");
  await w.getByRole("button", { name: "Phí chuyển khoản liên ngân hàng trên app?" }).click({ timeout: 60_000 });
  await w.getByText(/Nguồn \(\d+\)/).first().waitFor({ timeout: 180_000 });
  await page.waitForTimeout(2500);
  await caption(page, "Khách hàng chỉ đọc được kho tri thức công khai",
    "Vẫn trả lời có trích dẫn, và không hứa kết quả phê duyệt", 4600);
  await hideCaption(page);
  await page.waitForTimeout(1000);
});
